from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from src.agent.factory import create_evolution_agent, create_onboard_agent
from src.agent.retry import run_agent_with_retry
from src.db.queries import set_repository_status, upsert_repository
from src.github import client as gh
from src.knowledge.store import store_evolution, store_onboarding
from src.models import Repository, RepoStatus

logger = logging.getLogger(__name__)

# Config/meta files worth analyzing for project conventions
KEY_FILES = [
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    ".eslintrc.json",
    ".eslintrc.js",
    "eslint.config.js",
    "tsconfig.json",
    "setup.cfg",
    "setup.py",
    ".editorconfig",
    ".prettierrc",
    ".prettierrc.json",
    "Makefile",
    "README.md",
    "ARCHITECTURE.md",
    "CONTRIBUTING.md",
    "docker-compose.yml",
    "Dockerfile",
]

# File extensions we want to sample for architecture analysis
CODE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".rb",
    ".cs",
    ".swift",
    ".ex",
    ".exs",
}

# Max files to sample for the agent context
MAX_SAMPLE_FILES = 15
MAX_FILE_SIZE = 8000  # chars
_MAX_CONCURRENT_FETCHES = 5


async def onboard_repo(repo: Repository) -> None:
    # TODO: Consider decomposing into smaller functions (fetch context, run
    # architecture analysis, run evolution analysis) if this grows further.
    logger.info("Onboarding repository %s", repo.full_name)

    await upsert_repository(repo.full_name, repo.installation_id, repo.default_branch)

    try:
        tree = await gh.get_repo_tree(repo.installation_id, repo.full_name, repo.default_branch)
    except Exception:
        logger.exception("Failed to fetch repo tree for %s, aborting onboarding", repo.full_name)
        await set_repository_status(repo.full_name, RepoStatus.PENDING)
        raise
    try:
        tree_summary = "\n".join(tree[:500])

        # Fetch key config files
        key_file_contents = await _fetch_key_files(repo, tree)

        # Fetch recently changed files to understand current patterns
        recent_files = await _get_recently_changed_files(repo)
        recent_code_samples = await _fetch_code_samples(repo, recent_files)

        # Fetch a few "structural" code files (entry points, services, etc.)
        structural_samples = await _fetch_structural_samples(repo, tree)

        # Run the onboard agent for overall architecture understanding
        onboard_agent = create_onboard_agent(repo.full_name, repo.installation_id, repo.default_branch)
        onboard_prompt = (
            f"Analyze this repository: **{repo.full_name}**\n\n"
            f"**File tree:**\n```\n{tree_summary}\n```\n\n"
            f"**Configuration files:**\n{key_file_contents}\n\n"
            f"**Structural code samples (entry points, services, core modules):**\n"
            f"{structural_samples}\n\n"
            f"**Recently modified code (represents current direction):**\n"
            f"{recent_code_samples}"
        )
        onboard_response = await run_agent_with_retry(onboard_agent, prompt=onboard_prompt)
        await store_onboarding(repo.full_name, onboard_response.content)

        # Run the evolution agent to specifically analyze new vs legacy patterns
        if recent_files:
            recent_prs = await _get_recent_pr_titles(repo)
            evolution_agent = create_evolution_agent(repo.full_name, repo.installation_id, repo.default_branch)
            recent_files_text = "\n".join(recent_files[:100])
            evolution_prompt = (
                f"Analyze the evolution of **{repo.full_name}**\n\n"
                f"**Recently merged PRs:**\n{recent_prs}\n\n"
                f"**Files changed in recent commits:**\n"
                f"{recent_files_text}\n\n"
                f"**Code from recently modified files (newest patterns):**\n"
                f"{recent_code_samples}\n\n"
                f"**Older structural code (potentially legacy):**\n"
                f"{structural_samples}"
            )
            evolution_response = await run_agent_with_retry(evolution_agent, prompt=evolution_prompt)
            await store_evolution(repo.full_name, evolution_response.content)
    except Exception:
        logger.exception("Onboarding failed for %s, resetting to pending", repo.full_name)
        await set_repository_status(repo.full_name, RepoStatus.PENDING)
        raise

    await set_repository_status(repo.full_name, RepoStatus.ACTIVE)
    logger.info("Onboarding complete for %s — status set to active", repo.full_name)


async def _fetch_files_concurrently(
    repo: Repository,
    paths: list[str],
    formatter: Callable[[str, str], str],
) -> str:
    """Fetch file contents concurrently and format them using *formatter(path, content)*."""
    sem = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)

    async def _fetch(path: str) -> str | None:
        async with sem:
            try:
                content = await gh.get_file_content(repo.installation_id, repo.full_name, path, repo.default_branch)
            except Exception:
                logger.warning("Failed to fetch %s from %s", path, repo.full_name)
                return None
            return formatter(path, content) if content else None

    results = await asyncio.gather(*[_fetch(p) for p in paths])
    return "\n\n".join(r for r in results if r)


async def _fetch_key_files(repo: Repository, tree: list[str]) -> str:
    paths = [
        path for path in tree if (path.rsplit("/", 1)[-1] if "/" in path else path) in KEY_FILES or path in KEY_FILES
    ]
    return await _fetch_files_concurrently(
        repo,
        paths,
        lambda path, content: f"### {path}\n```\n{content[:MAX_FILE_SIZE]}\n```",
    )


async def _get_recently_changed_files(repo: Repository) -> list[str]:
    """Get a deduplicated list of files from recent commits."""
    try:
        commits = await gh.get_recent_commits(repo.installation_id, repo.full_name, repo.default_branch, count=30)
    except Exception:
        logger.warning("Could not fetch recent commits for %s", repo.full_name)
        return []

    sem = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)

    async def _get_files(sha: str) -> list[str]:
        async with sem:
            try:
                return await gh.get_commit_files(repo.installation_id, repo.full_name, sha)
            except Exception:
                return []

    # Most recent commits first — their files represent the newest patterns
    results = await asyncio.gather(*[_get_files(c["sha"]) for c in commits[:15]])
    seen: set[str] = set()
    ordered: list[str] = []
    for files in results:
        for f in files:
            if f not in seen and _is_code_file(f):
                seen.add(f)
                ordered.append(f)
    return ordered


async def _fetch_code_samples(repo: Repository, file_paths: list[str]) -> str:
    """Fetch content of recently changed code files."""
    return await _fetch_files_concurrently(
        repo,
        file_paths[:MAX_SAMPLE_FILES],
        lambda path, content: f"### {path} (recently modified)\n```\n{content[:MAX_FILE_SIZE]}\n```",
    )


async def _fetch_structural_samples(repo: Repository, tree: list[str]) -> str:
    """Fetch files that are likely architectural entry points."""
    structural_patterns = [
        "main.",
        "app.",
        "server.",
        "index.",
        "routes.",
        "router.",
        "urls.",
        "/services/",
        "/service/",
        "/usecases/",
        "/use_cases/",
        "/controllers/",
        "/handlers/",
        "/repositories/",
        "/repos/",
        "/middleware/",
        "/middleware.",
        "/models/",
        "/entities/",
        "/domain/",
    ]
    candidates: list[str] = []
    for path in tree:
        lower = path.lower()
        if not _is_code_file(path):
            continue
        if any(p in lower for p in structural_patterns):
            candidates.append(path)

    selected = candidates[:MAX_SAMPLE_FILES]
    return await _fetch_files_concurrently(
        repo,
        selected,
        lambda path, content: f"### {path}\n```\n{content[:MAX_FILE_SIZE]}\n```",
    )


async def _get_recent_pr_titles(repo: Repository) -> str:
    try:
        prs = await gh.get_recent_prs(repo.installation_id, repo.full_name, count=15)
    except Exception:
        return "(could not fetch recent PRs)"
    if not prs:
        return "(no recently merged PRs)"
    return "\n".join(f"- #{pr['number']}: {pr['title']}" for pr in prs)


def _is_code_file(path: str) -> bool:
    dot = path.rfind(".")
    if dot == -1:
        return False
    return path[dot:] in CODE_EXTENSIONS
