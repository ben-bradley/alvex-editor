from __future__ import annotations

import os

import pytest

from alvex_editor.policy import PathPolicyError, ensure_not_inside_repo, is_inside_repo, repo_root


def test_repo_root_detected() -> None:
    root = repo_root()
    assert root is not None
    assert (root / "pyproject.toml").exists()


def test_is_inside_repo(tmp_path) -> None:
    root = repo_root()
    assert root is not None
    assert is_inside_repo(root / "some" / "output.mp4")
    assert not is_inside_repo(tmp_path / "output.mp4")


def test_rejects_write_inside_repo(monkeypatch) -> None:
    monkeypatch.delenv("ALVEX_ALLOW_IN_REPO_WRITES", raising=False)
    root = repo_root()
    assert root is not None
    with pytest.raises(PathPolicyError, match="outside the codebase|Refusing to save"):
        ensure_not_inside_repo(root / "output" / "final.mp4", kind="rendered video/output")


def test_allows_write_outside_repo(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ALVEX_ALLOW_IN_REPO_WRITES", raising=False)
    p = ensure_not_inside_repo(tmp_path / "final.mp4", kind="rendered video/output")
    assert p == tmp_path / "final.mp4"


def test_override_allows_inside_repo(monkeypatch) -> None:
    monkeypatch.setenv("ALVEX_ALLOW_IN_REPO_WRITES", "1")
    root = repo_root()
    assert root is not None
    p = ensure_not_inside_repo(root / "output" / "final.mp4", kind="rendered video/output")
    assert p == root / "output" / "final.mp4"
