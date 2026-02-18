"""Tests for _format_diff and _extract_review from src/usecases/review_pr.py."""

from __future__ import annotations

from src.models import FileDiff, PullRequest, Repository, ReviewCommentSchema, ReviewResponseSchema
from src.usecases.review_pr import _extract_review, _format_diff


class TestFormatDiff:
    def test_single_file(self, sample_pr: PullRequest):
        sample_pr.files = [sample_pr.files[0]]
        result = _format_diff(sample_pr)
        assert "### src/auth.py (added, +10/-0)" in result
        assert "```diff" in result
        assert "def login():" in result

    def test_multiple_files(self, sample_pr: PullRequest):
        result = _format_diff(sample_pr)
        assert "### src/auth.py" in result
        assert "### src/routes.py" in result

    def test_empty_patch_is_skipped(self, sample_repo: Repository):
        pr = PullRequest(
            number=1,
            title="t",
            body="b",
            head_sha="sha",
            base_branch="main",
            head_branch="feat",
            repo=sample_repo,
            files=[FileDiff(filename="empty.py", status="modified", patch="")],
        )
        result = _format_diff(pr)
        assert result == ""


class TestExtractReview:
    def test_structured_output(self):
        schema = ReviewResponseSchema(
            summary="All good",
            comments=[ReviewCommentSchema(path="a.py", line=1, body="fix")],
        )
        review = _extract_review(schema)
        assert review.body == "All good"
        assert len(review.comments) == 1
        assert review.comments[0].path == "a.py"
        assert review.comments[0].line == 1
        assert review.comments[0].body == "fix"

    def test_structured_output_no_comments(self):
        schema = ReviewResponseSchema(summary="LGTM")
        review = _extract_review(schema)
        assert review.body == "LGTM"
        assert review.comments == []

    def test_json_string_fallback(self):
        content = '{"summary": "All good", "comments": [{"path": "a.py", "line": 1, "body": "fix"}]}'
        review = _extract_review(content)
        assert review.body == "All good"
        assert len(review.comments) == 1
        assert review.comments[0].path == "a.py"

    def test_invalid_json_fallback(self):
        content = "This is just plain text review."
        review = _extract_review(content)
        assert review.body == "This is just plain text review."
        assert review.comments == []

    def test_missing_summary_key(self):
        content = '{"comments": [{"path": "x.py", "line": 5, "body": "nit"}]}'
        review = _extract_review(content)
        assert review.body == "Code review complete."
        assert len(review.comments) == 1

    def test_missing_comments_key(self):
        content = '{"summary": "No issues found"}'
        review = _extract_review(content)
        assert review.body == "No issues found"
        assert review.comments == []
