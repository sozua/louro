from __future__ import annotations

from agno.tools import tool

from src.github import client as gh


def make_tools(installation_id: int, repo: str, default_ref: str = "HEAD"):
    """Create agent tools with repo context baked in."""

    @tool
    async def fetch_file(path: str, ref: str = default_ref) -> str:
        """Fetch the full contents of a file from the repository.

        Args:
            path: File path within the repository.
            ref: Git ref (branch, tag, or SHA) to fetch from.
        """
        content = await gh.get_file_content(installation_id, repo, path, ref)
        if not content:
            return f"File not found: {path} at ref {ref}"
        return content

    @tool
    async def list_directory(ref: str = default_ref) -> str:
        """List all files in the repository tree.

        Args:
            ref: Git ref (branch, tag, or SHA).
        """
        files = await gh.get_repo_tree(installation_id, repo, ref)
        return "\n".join(files)

    @tool
    async def search_code(path: str, query: str, ref: str = default_ref) -> str:
        """Fetch a file and search for lines containing the query string.

        Args:
            path: File path to search within.
            query: Text to search for in the file.
            ref: Git ref (branch, tag, or SHA).
        """
        content = await gh.get_file_content(installation_id, repo, path, ref)
        if not content:
            return f"File not found: {path}"
        matches = [f"L{i + 1}: {line}" for i, line in enumerate(content.splitlines()) if query.lower() in line.lower()]
        if not matches:
            return f"No matches for '{query}' in {path}"
        return "\n".join(matches)

    return [fetch_file, list_directory, search_code]
