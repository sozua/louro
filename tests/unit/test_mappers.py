"""Tests for src/github/mappers.py — map_pr_event, map_comment_event, map_installation_event."""

from __future__ import annotations

from src.github.mappers import map_comment_event, map_installation_event, map_pr_event


class TestMapPrEvent:
    def test_minimal_payload(self, minimal_pr_payload: dict):
        pr = map_pr_event(minimal_pr_payload)
        assert pr.number == 1
        assert pr.title == "Test PR"
        assert pr.body == "description"
        assert pr.head_sha == "abc123"
        assert pr.base_branch == "main"
        assert pr.head_branch == "feature"
        assert pr.repo.full_name == "acme/repo"
        assert pr.repo.installation_id == 100
        assert pr.author == "dev"

    def test_null_body_defaults_to_empty(self, minimal_pr_payload: dict):
        minimal_pr_payload["pull_request"]["body"] = None
        pr = map_pr_event(minimal_pr_payload)
        assert pr.body == ""

    def test_missing_user_defaults_to_empty_author(self, minimal_pr_payload: dict):
        del minimal_pr_payload["pull_request"]["user"]
        pr = map_pr_event(minimal_pr_payload)
        assert pr.author == ""

    def test_missing_default_branch_defaults_to_main(self, minimal_pr_payload: dict):
        del minimal_pr_payload["repository"]["default_branch"]
        pr = map_pr_event(minimal_pr_payload)
        assert pr.repo.default_branch == "main"


class TestMapCommentEvent:
    def test_minimal_payload(self, minimal_comment_payload: dict):
        event = map_comment_event(minimal_comment_payload)
        assert event.comment_id == 999
        assert event.body == "Looks good!"
        assert event.path == "src/main.py"
        assert event.line == 10
        assert event.pr_number == 42
        assert event.repo.full_name == "acme/repo"
        assert event.diff_hunk == "@@ -1,5 +1,5 @@"

    def test_line_fallback_to_original_line(self, minimal_comment_payload: dict):
        minimal_comment_payload["comment"]["line"] = None
        event = map_comment_event(minimal_comment_payload)
        assert event.line == 8

    def test_missing_optional_fields(self, minimal_comment_payload: dict):
        del minimal_comment_payload["comment"]["path"]
        del minimal_comment_payload["comment"]["line"]
        del minimal_comment_payload["comment"]["original_line"]
        event = map_comment_event(minimal_comment_payload)
        assert event.path is None
        assert event.line is None

    def test_missing_in_reply_to_id(self, minimal_comment_payload: dict):
        event = map_comment_event(minimal_comment_payload)
        assert event.in_reply_to_id is None

    def test_with_in_reply_to_id(self, minimal_comment_payload: dict):
        minimal_comment_payload["comment"]["in_reply_to_id"] = 888
        event = map_comment_event(minimal_comment_payload)
        assert event.in_reply_to_id == 888


class TestMapInstallationEvent:
    def test_repositories_field(self, minimal_installation_payload: dict):
        repos = map_installation_event(minimal_installation_payload)
        assert len(repos) == 2
        assert repos[0].full_name == "acme/repo-a"
        assert repos[1].full_name == "acme/repo-b"
        assert all(r.installation_id == 200 for r in repos)

    def test_repositories_added_fallback(self):
        payload = {
            "installation": {"id": 300},
            "repositories_added": [{"full_name": "org/new-repo"}],
        }
        repos = map_installation_event(payload)
        assert len(repos) == 1
        assert repos[0].full_name == "org/new-repo"
        assert repos[0].installation_id == 300

    def test_empty_repositories(self):
        payload = {
            "installation": {"id": 300},
            "repositories": [],
        }
        repos = map_installation_event(payload)
        assert repos == []

    def test_no_repositories_key(self):
        payload = {"installation": {"id": 300}}
        repos = map_installation_event(payload)
        assert repos == []

    def test_removed_action_uses_repositories_removed(self):
        payload = {
            "action": "removed",
            "installation": {"id": 300},
            "repositories_removed": [{"full_name": "org/old-repo"}],
        }
        repos = map_installation_event(payload)
        assert len(repos) == 1
        assert repos[0].full_name == "org/old-repo"

    def test_deleted_action_uses_repositories(self):
        payload = {
            "action": "deleted",
            "installation": {"id": 300},
            "repositories": [
                {"full_name": "org/repo-a"},
                {"full_name": "org/repo-b"},
            ],
        }
        repos = map_installation_event(payload)
        assert len(repos) == 2
