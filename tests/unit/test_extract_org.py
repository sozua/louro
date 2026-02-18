"""Tests for extract_org from src/models.py."""

from __future__ import annotations

from src.models import extract_org


class TestExtractOrg:
    def test_basic(self):
        assert extract_org("acme/repo") == "acme"

    def test_with_dashes(self):
        assert extract_org("my-org/my-repo") == "my-org"

    def test_nested_org_name(self):
        assert extract_org("github-org/some-repo") == "github-org"
