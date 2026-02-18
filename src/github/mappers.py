from __future__ import annotations

from src.models import CommentEvent, PullRequest, Repository


def map_pr_event(payload: dict) -> PullRequest:
    try:
        pr = payload["pull_request"]
        repo_data = payload["repository"]
        repo = Repository(
            full_name=repo_data["full_name"],
            installation_id=payload["installation"]["id"],
            default_branch=repo_data.get("default_branch", "main"),
        )
        return PullRequest(
            number=pr["number"],
            title=pr["title"],
            body=pr.get("body") or "",
            head_sha=pr["head"]["sha"],
            base_branch=pr["base"]["ref"],
            head_branch=pr["head"]["ref"],
            repo=repo,
            author=pr.get("user", {}).get("login", ""),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Malformed pull_request webhook payload: {exc}") from exc


def map_comment_event(payload: dict) -> CommentEvent:
    try:
        comment = payload["comment"]
        repo_data = payload["repository"]
        repo = Repository(
            full_name=repo_data["full_name"],
            installation_id=payload["installation"]["id"],
            default_branch=repo_data.get("default_branch", "main"),
        )
        pr_number = payload.get("pull_request", {}).get("number", 0)
        return CommentEvent(
            repo=repo,
            pr_number=pr_number,
            comment_id=comment["id"],
            body=comment["body"],
            path=comment.get("path"),
            line=comment.get("line") or comment.get("original_line"),
            in_reply_to_id=comment.get("in_reply_to_id"),
            diff_hunk=comment.get("diff_hunk", ""),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Malformed comment webhook payload: {exc}") from exc


def map_installation_event(payload: dict) -> list[Repository]:
    try:
        installation_id = payload["installation"]["id"]
        action = payload.get("action", "")
        if action == "removed":
            repos = payload.get("repositories_removed", [])
        elif action == "deleted":
            repos = payload.get("repositories", [])
        else:
            repos = payload.get("repositories", [])
            if not repos:
                repos = payload.get("repositories_added", [])
        return [
            Repository(
                full_name=r["full_name"],
                installation_id=installation_id,
            )
            for r in repos
        ]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Malformed installation webhook payload: {exc}") from exc
