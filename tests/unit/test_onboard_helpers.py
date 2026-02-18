"""Tests for _is_code_file from src/usecases/onboard_repo.py."""

from __future__ import annotations

import pytest

from src.usecases.onboard_repo import _is_code_file


class TestIsCodeFile:
    @pytest.mark.parametrize(
        "path",
        [
            "src/main.py",
            "app/index.ts",
            "components/Button.tsx",
            "lib/utils.js",
            "components/Form.jsx",
            "cmd/server.go",
            "src/lib.rs",
            "com/example/App.java",
            "src/Main.kt",
            "app/models.rb",
            "Services/Auth.cs",
            "Sources/App.swift",
            "lib/worker.ex",
            "test/helper.exs",
        ],
    )
    def test_code_files_return_true(self, path: str):
        assert _is_code_file(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "README.md",
            "config.yml",
            "Makefile",
            "LICENSE",
            "Dockerfile",
            ".gitignore",
            "data.json",
            "image.png",
        ],
    )
    def test_non_code_files_return_false(self, path: str):
        assert _is_code_file(path) is False

    def test_no_extension(self):
        assert _is_code_file("Makefile") is False

    def test_hidden_file_no_code_ext(self):
        assert _is_code_file(".env") is False
