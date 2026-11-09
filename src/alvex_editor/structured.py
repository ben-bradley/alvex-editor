from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_CONFIG_NAMES = ("alvex.json",)
WORKSPACE_CONFIG_NAMES = (
    "alvex-workspace.json",
    "workspace.json",
    "alvex.workspace.json",
)


def is_json_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() == ".json"


def load_structured(path: str | Path) -> Any:
    """Load a JSON file (Alvex standard format)."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    return json.loads(text)


def dump_structured_text(data: Any, *, fmt: str = "json") -> str:
    if fmt != "json":
        raise ValueError(f"Unsupported format: {fmt} (JSON only)")
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def dump_structured(path: str | Path, data: Any, *, fmt: str | None = None) -> Path:
    """Write structured data as JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dump_structured_text(data, fmt="json"), encoding="utf-8")
    return p


def find_project_config(path_or_dir: str | Path) -> Path:
    p = Path(path_or_dir).expanduser()
    if p.is_file():
        return p.resolve()
    if p.is_dir():
        for name in PROJECT_CONFIG_NAMES:
            cand = p / name
            if cand.exists():
                return cand.resolve()
        return (p / PROJECT_CONFIG_NAMES[0]).resolve()
    if p.suffix:
        return p.with_suffix(".json").resolve() if p.suffix.lower() != ".json" else p.resolve()
    return p.resolve()


def preferred_project_config_path(project_dir: str | Path) -> Path:
    d = Path(project_dir)
    found = find_project_config(d)
    if found.exists():
        return found
    return (d / "alvex.json").resolve()


def find_workspace_config(root: str | Path) -> Path | None:
    r = Path(root)
    for name in WORKSPACE_CONFIG_NAMES:
        p = r / name
        if p.exists():
            return p
    return None
