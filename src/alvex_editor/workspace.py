from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml

from .policy import ensure_not_inside_repo

DEFAULT_WORKSPACE_NAME = "Alvex"
WORKSPACE_CONFIG_NAMES = ("alvex-workspace.yaml", "workspace.yaml", "alvex.workspace.yaml")


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
        for name in WORKSPACE_CONFIG_NAMES:
            p = self.root / name
            if p.exists():
                return p
        return self.root / WORKSPACE_CONFIG_NAMES[0]

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


def load_workspace(path: str | Path | None = None, *, start: str | Path | None = None) -> Workspace:
    if path:
        p = Path(path).expanduser().resolve()
        if p.is_file():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict) and data.get("root"):
                return Workspace(root=Path(str(data["root"])).expanduser().resolve())
            # config lives inside workspace root
            return Workspace(root=p.parent.resolve())
        return Workspace(root=p)
    cfg = find_workspace_config(Path(start) if start else None)
    if cfg:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict) and data.get("root"):
            return Workspace(root=Path(str(data["root"])).expanduser().resolve())
        return Workspace(root=cfg.parent.resolve())
    return Workspace(root=default_workspace_root())


def save_workspace_config(ws: Workspace) -> Path:
    ensure_not_inside_repo(ws.root, kind="workspace")
    ws.root.mkdir(parents=True, exist_ok=True)
    path = ws.config_path
    data = {
        "version": 1,
        "root": str(ws.root),
        "templates_dir": str(ws.templates_dir),
        "soundtracks_dir": str(ws.soundtracks_dir),
        "projects_dir": str(ws.projects_dir),
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path
