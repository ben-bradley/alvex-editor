from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from .policy import ensure_not_inside_repo
from .structured import WORKSPACE_CONFIG_NAMES as _WS_CONFIG_NAMES, dump_structured, find_workspace_config, load_structured

DEFAULT_WORKSPACE_NAME = "Alvex"
WORKSPACE_CONFIG_NAMES = _WS_CONFIG_NAMES


def default_workspace_root() -> Path:
    raw = os.environ.get("ALVEX_WORKSPACE")
    if raw and raw.strip():
        return Path(raw).expanduser().resolve()
    return (Path.home() / DEFAULT_WORKSPACE_NAME).resolve()


@dataclass
class Workspace:
    root: Path

    @property
    def templates_dir(self) -> Path:
        return self.root / "templates"

    @property
    def soundtracks_dir(self) -> Path:
        return self.root / "soundtracks"

    @property
    def projects_dir(self) -> Path:
        return self.root / "projects"

    @property
    def config_path(self) -> Path:
        found = find_workspace_config(self.root)
        if found:
            return found
        # prefer JSON for new workspaces
        return self.root / "alvex-workspace.json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "templates_dir": str(self.templates_dir),
            "soundtracks_dir": str(self.soundtracks_dir),
            "projects_dir": str(self.projects_dir),
            "config_path": str(self.config_path),
            "exists": self.root.exists(),
        }

    def ensure_dirs(self, *, create: bool = True) -> "Workspace":
        if create:
            ensure_not_inside_repo(self.root, kind="workspace")
            self.templates_dir.mkdir(parents=True, exist_ok=True)
            self.soundtracks_dir.mkdir(parents=True, exist_ok=True)
            self.projects_dir.mkdir(parents=True, exist_ok=True)
        return self

    def project_dir(self, slug: str) -> Path:
        return self.projects_dir / slug


def find_workspace_config(start: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    env = os.environ.get("ALVEX_WORKSPACE_CONFIG")
    if env and env.strip():
        candidates.append(Path(env).expanduser())
    if start:
        s = Path(start).expanduser().resolve()
        for base in (s, *s.parents):
            for name in WORKSPACE_CONFIG_NAMES:
                candidates.append(base / name)
    root = default_workspace_root()
    for name in WORKSPACE_CONFIG_NAMES:
        candidates.append(root / name)
    seen: set[Path] = set()
    for c in candidates:
        try:
            r = c.resolve()
        except Exception:
            r = c
        if r in seen:
            continue
        seen.add(r)
        if r.exists() and r.is_file():
            return r
    return None


def load_workspace_config_data(path_or_ws: str | Path | Workspace | None = None) -> dict[str, Any]:
    if isinstance(path_or_ws, Workspace):
        cfg = path_or_ws.config_path if path_or_ws.config_path.exists() else find_workspace_config(path_or_ws.root)
    elif path_or_ws:
        p = Path(path_or_ws).expanduser()
        cfg = p if p.is_file() else find_workspace_config(p)
    else:
        cfg = find_workspace_config()
    if not cfg or not Path(cfg).exists():
        return {}
    try:
        data = load_structured(cfg) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_workspace(path: str | Path | None = None, *, start: str | Path | None = None) -> Workspace:
    if path:
        p = Path(path).expanduser().resolve()
        if p.is_file():
            data = load_structured(p) or {}
            if isinstance(data, dict) and data.get("root"):
                return Workspace(root=Path(str(data["root"])).expanduser().resolve())
            # config lives inside workspace root
            return Workspace(root=p.parent.resolve())
        return Workspace(root=p)
    cfg = find_workspace_config(Path(start) if start else None)
    if cfg:
        data = load_structured(cfg) or {}
        if isinstance(data, dict) and data.get("root"):
            return Workspace(root=Path(str(data["root"])).expanduser().resolve())
        return Workspace(root=cfg.parent.resolve())
    return Workspace(root=default_workspace_root())


def save_workspace_config(ws: Workspace, extra: dict[str, Any] | None = None) -> Path:
    ensure_not_inside_repo(ws.root, kind="workspace")
    ws.root.mkdir(parents=True, exist_ok=True)
    path = ws.config_path
    # JSON only
    path = ws.root / "alvex-workspace.json" if path.suffix.lower() != ".json" else path
    data: dict[str, Any] = {
        "version": 1,
        "root": str(ws.root),
        "templates_dir": str(ws.templates_dir),
        "soundtracks_dir": str(ws.soundtracks_dir),
        "projects_dir": str(ws.projects_dir),
    }
    if extra:
        data.update(extra)
    dump_structured(path, data, fmt="json")
    return path
