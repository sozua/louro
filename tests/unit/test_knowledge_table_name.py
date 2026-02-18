"""Tests for _table_name from src/knowledge/store.py."""

from __future__ import annotations

from src.knowledge.store import _table_name


class TestTableName:
    def test_includes_repo_name(self):
        assert _table_name("acme/my-repo") == "knowledge_acme_my_repo"

    def test_normalizes_case(self):
        assert _table_name("Acme/My-Repo") == "knowledge_acme_my_repo"

    def test_different_repos_get_different_tables(self):
        assert _table_name("org/repo") != _table_name("other/repo-2")

    def test_replaces_special_chars(self):
        result = _table_name("my-org/my-repo")
        assert "/" not in result
        assert "-" not in result
