from __future__ import annotations

import os
from pathlib import Path


class PathPolicyError(ValueError):
    """Raised when an artifact would be written inside the protected codebase."""


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def repo_root() -> Path | None:
    """Return the Alvex Editor git repository root, if detectable.

    Detection is anchored to this package (not the current working directory) so
    the policy protects the codebase regardless of where commands are run from.
    """
    try:
        here = Path(__file__).resolve().parent
    except Exception:
        return None
    for parent in (here, *here.parents):
        if (parent / ".git").exists():
            return parent
    return None


def is_inside_repo(path: str | Path) -> bool:
    root = repo_root()
    if root is None:
        return False
    try:
        resolved = Path(path).expanduser().resolve(strict=False)
        root_resolved = root.resolve(strict=False)
    except Exception:
        return False
    try:
        resolved.relative_to(root_resolved)
        return True
    except ValueError:
        return False


def ensure_not_inside_repo(
    path: str | Path,
    *,
    kind: str = "artifact",
    allow_override: bool = True,
) -> Path:
    """Reject write targets inside the Alvex Editor codebase.

    Set ALVEX_ALLOW_IN_REPO_WRITES=1 to bypass (development/testing only).
    """
    p = Path(path).expanduser()
    if allow_override and _env_truthy("ALVEX_ALLOW_IN_REPO_WRITES"):
        return p
    if is_inside_repo(p):
        root = repo_root()
        raise PathPolicyError(
            f"Refusing to save {kind} inside the Alvex Editor codebase: {Path(p).resolve(strict=False)} "
            f"(repo: {root}). Configure an output/manifest/timeline/analysis path outside the codebase "
            "(e.g. under your home directory or project media folder). "
            "Set ALVEX_ALLOW_IN_REPO_WRITES=1 to override for local development."
        )
    return p
