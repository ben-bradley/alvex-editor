from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from .policy import ensure_not_inside_repo
from .workspace import Workspace, load_workspace

# ---- template registry ----

TEMPLATE_ALIASES = {
    "standard real estate template": "exterior-showcase",
    "standard real estate": "exterior-showcase",
    "real estate template": "exterior-showcase",
    "real-estate template": "exterior-showcase",
    "real estate": "exterior-showcase",
    "real-estate": "exterior-showcase",
    "exterior showcase": "exterior-showcase",
    "exterior-showcase": "exterior-showcase",
    "exterior_showcase": "exterior-showcase",
}


def slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "item"


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def bundled_templates_dir() -> Path:
    # repo_root/templates (read-only bundled example)
    return Path(__file__).resolve().parents[2] / "templates"


@dataclass
class TemplateEntry:
    id: str
    path: Path
    source: str  # bundled|workspace|path
    aliases: list[str] = field(default_factory=list)
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "path": str(self.path), "source": self.source, "aliases": self.aliases, "name": self.name or self.id}


def list_templates(workspace: Workspace | None = None) -> list[TemplateEntry]:
    ws = workspace or load_workspace()
    entries: dict[str, TemplateEntry] = {}

    def add(path: Path, source: str) -> None:
        if not path.exists() or not path.is_file() or path.suffix.lower() not in {".md", ".markdown"}:
            return
        tid = slugify(path.stem)
        if tid not in entries:
            entries[tid] = TemplateEntry(id=tid, path=path.resolve(), source=source, aliases=[])

    # bundled
    bdir = bundled_templates_dir()
    if bdir.exists():
        for p in sorted(bdir.glob("*.md")):
            add(p, "bundled")
    # workspace user library
    if ws.templates_dir.exists():
        for p in sorted(ws.templates_dir.glob("*.md")):
            add(p, "workspace")
        for p in sorted(ws.templates_dir.glob("*.markdown")):
            add(p, "workspace")
        idx = ws.templates_dir / "registry.yaml"
        if idx.exists():
            data = _read_yaml(idx)
            for tid, meta in (data.get("templates") or {}).items():
                if not isinstance(meta, dict):
                    continue
                tid_s = slugify(str(tid))
                target = meta.get("path")
                if target:
                    tp = Path(str(target)).expanduser()
                    if not tp.is_absolute():
                        tp = (ws.templates_dir / tp).resolve()
                    if tp.exists() and tid_s in entries:
                        entries[tid_s].path = tp
                    elif tp.exists():
                        entries[tid_s] = TemplateEntry(id=tid_s, path=tp, source="workspace", aliases=list(meta.get("aliases") or []), name=meta.get("name"))
                if tid_s in entries:
                    entries[tid_s].aliases = list({*entries[tid_s].aliases, *[str(a) for a in (meta.get("aliases") or [])]})
                    if meta.get("name"):
                        entries[tid_s].name = str(meta.get("name"))
    # built-in aliases
    for alias, tid in TEMPLATE_ALIASES.items():
        if tid in entries and alias not in entries[tid].aliases:
            entries[tid].aliases.append(alias)
    return sorted(entries.values(), key=lambda e: e.id)


def resolve_template(ref: str | Path, *, workspace: Workspace | None = None, project_dir: Path | None = None) -> Path:
    ws = workspace or load_workspace()
    if isinstance(ref, Path) or (isinstance(ref, str) and ("/" in ref or "\\" in ref or ref.endswith(".md") or ref.startswith(".") or ref.startswith("~"))):
        p = Path(ref).expanduser()
        if not p.is_absolute() and project_dir:
            p = (project_dir / p).resolve()
        elif not p.is_absolute():
            p = p.resolve()
        if p.exists():
            return p
        # try workspace templates
        cand = (ws.templates_dir / p.name).resolve()
        if cand.exists():
            return cand
        return p.resolve()
    key = slugify(str(ref))
    key = TEMPLATE_ALIASES.get(str(ref).strip().lower(), TEMPLATE_ALIASES.get(key, key))
    for e in list_templates(ws):
        if e.id == key or key in {slugify(a) for a in e.aliases} or str(ref).strip().lower() in {a.lower() for a in e.aliases}:
            return e.path
    # fallback: filename in workspace/bundled
    for base in (ws.templates_dir, bundled_templates_dir()):
        for name in (f"{key}.md", f"{key}.markdown"):
            p = (base / name)
            if p.exists():
                return p.resolve()
    raise FileNotFoundError(f"Template not found: {ref!r}. Searched workspace {ws.templates_dir} and bundled templates; use a path or add it to the template registry.")


# ---- soundtrack registry ----

def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


@dataclass
class SoundtrackEntry:
    id: str
    title: str | None = None
    path: Path | None = None  # imported mp3
    aliases: list[str] = field(default_factory=list)
    cut_points_path: Path | None = None
    sha256_16: str | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title or self.id,
            "path": str(self.path) if self.path else None,
            "aliases": self.aliases,
            "cut_points_path": str(self.cut_points_path) if self.cut_points_path else None,
            "sha256_16": self.sha256_16,
            "tags": self.tags,
        }


def soundtracks_index_path(workspace: Workspace | None = None) -> Path:
    ws = workspace or load_workspace()
    return ws.soundtracks_dir / "registry.yaml"


def _load_soundtracks_index(ws: Workspace) -> dict[str, Any]:
    p = soundtracks_index_path(ws)
    if not p.exists():
        return {"version": 1, "soundtracks": {}}
    data = _read_yaml(p)
    if "soundtracks" not in data or not isinstance(data.get("soundtracks"), dict):
        data = {"version": data.get("version", 1), "soundtracks": {}}
    return data


def _save_soundtracks_index(ws: Workspace, data: dict[str, Any]) -> Path:
    ensure_not_inside_repo(ws.soundtracks_dir, kind="soundtrack registry")
    ws.soundtracks_dir.mkdir(parents=True, exist_ok=True)
    p = soundtracks_index_path(ws)
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return p


def list_soundtracks(workspace: Workspace | None = None) -> list[SoundtrackEntry]:
    ws = workspace or load_workspace()
    data = _load_soundtracks_index(ws)
    out: list[SoundtrackEntry] = []
    for sid, meta in (data.get("soundtracks") or {}).items():
        if not isinstance(meta, dict):
            continue
        sid_s = slugify(str(sid))
        raw_path = meta.get("path")
        p = Path(str(raw_path)).expanduser() if raw_path else None
        if p and not p.is_absolute():
            p = (ws.soundtracks_dir / p).resolve()
        raw_cp = meta.get("cut_points_path") or meta.get("cut_points")
        cp = Path(str(raw_cp)).expanduser() if raw_cp and isinstance(raw_cp, str) and ("/" in str(raw_cp) or str(raw_cp).endswith(('.yaml','.yml','.json'))) else None
        if cp and not cp.is_absolute():
            cp = (ws.soundtracks_dir / cp).resolve()
        if not cp:
            cp = ws.soundtracks_dir / sid_s / "cut-points.yaml"
            if not cp.exists():
                cpj = ws.soundtracks_dir / sid_s / "cut-points.json"
                cp = cpj if cpj.exists() else (ws.soundtracks_dir / sid_s / "cut-points.yaml")
        out.append(SoundtrackEntry(
            id=sid_s,
            title=meta.get("title") or meta.get("name"),
            path=p,
            aliases=[str(a) for a in (meta.get("aliases") or [])],
            cut_points_path=cp,
            sha256_16=meta.get("sha256_16") or meta.get("hash"),
            tags=[str(t) for t in (meta.get("tags") or [])],
        ))
    return sorted(out, key=lambda e: e.id)


def resolve_soundtrack(ref: str | Path, *, workspace: Workspace | None = None) -> SoundtrackEntry | None:
    ws = workspace or load_workspace()
    # direct path
    if isinstance(ref, Path) or (isinstance(ref, str) and ("/" in ref or "\\" in ref or str(ref).startswith("~") or Path(str(ref)).suffix.lower() == ".mp3")):
        p = Path(ref).expanduser().resolve()
        if p.exists():
            # match registry by hash/path
            try:
                h = _hash_file(p)
            except Exception:
                h = None
            for e in list_soundtracks(ws):
                if e.path and e.path.resolve() == p:
                    return e
                if h and e.sha256_16 == h:
                    return e
            return SoundtrackEntry(id=slugify(p.stem), title=p.stem, path=p, sha256_16=h)
        # maybe relative to soundtracks dir
        cand = (ws.soundtracks_dir / str(ref)).resolve()
        if cand.exists():
            return resolve_soundtrack(cand, workspace=ws)
        return None
    key = slugify(str(ref))
    low = str(ref).strip().lower()
    for e in list_soundtracks(ws):
        if e.id == key or low in {a.lower() for a in e.aliases} or key in {slugify(a) for a in e.aliases} or low == (e.title or "").lower():
            return e
        if e.path and (low == e.path.name.lower() or low == e.path.stem.lower()):
            return e
    return None


def import_soundtrack(source: str | Path, *, workspace: Workspace | None = None, track_id: str | None = None, title: str | None = None, aliases: list[str] | None = None, copy: bool = True) -> SoundtrackEntry:
    ws = workspace or load_workspace()
    ensure_not_inside_repo(ws.soundtracks_dir, kind="soundtrack registry")
    src = Path(source).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"Soundtrack source not found: {src}")
    sid = slugify(track_id or title or src.stem)
    dest_dir = ws.soundtracks_dir / sid
    dest_dir.mkdir(parents=True, exist_ok=True)
    if copy:
        dest = dest_dir / src.name
        if dest.resolve() != src.resolve():
            shutil.copy2(src, dest)
    else:
        dest = src
    h = _hash_file(dest)
    data = _load_soundtracks_index(ws)
    tracks = data.setdefault("soundtracks", {})
    meta = tracks.get(sid) if isinstance(tracks.get(sid), dict) else {}
    meta.update({
        "id": sid,
        "title": title or meta.get("title") or src.stem,
        "path": str(dest),
        "sha256_16": h,
        "aliases": sorted({*[str(a) for a in (meta.get("aliases") or [])], *[str(a) for a in (aliases or [])], src.name, src.stem}),
    })
    tracks[sid] = meta
    _save_soundtracks_index(ws, data)
    cp = dest_dir / "cut-points.yaml"
    return SoundtrackEntry(id=sid, title=meta.get("title"), path=dest, aliases=list(meta.get("aliases") or []), cut_points_path=cp if cp.exists() else (dest_dir / "cut-points.yaml"), sha256_16=h)


def load_curated_cut_points(entry: SoundtrackEntry | str | Path, *, workspace: Workspace | None = None) -> dict[str, Any] | None:
    ws = workspace or load_workspace()
    if not isinstance(entry, SoundtrackEntry):
        res = resolve_soundtrack(entry, workspace=ws)
        if not res:
            return None
        entry = res
    candidates = []
    if entry.cut_points_path:
        candidates.append(entry.cut_points_path)
    candidates.append(ws.soundtracks_dir / entry.id / "cut-points.yaml")
    candidates.append(ws.soundtracks_dir / entry.id / "cut-points.yml")
    candidates.append(ws.soundtracks_dir / entry.id / "cut-points.json")
    for p in candidates:
        if p and Path(p).exists():
            try:
                text = Path(p).read_text(encoding="utf-8")
                if Path(p).suffix.lower() == ".json":
                    data = json.loads(text)
                else:
                    data = yaml.safe_load(text) or {}
                if isinstance(data, dict):
                    data.setdefault("source", str(entry.path) if entry.path else None)
                    data.setdefault("soundtrack_id", entry.id)
                    return data
            except Exception:
                continue
    # also check registry inline
    data = _load_soundtracks_index(ws)
    meta = (data.get("soundtracks") or {}).get(entry.id) or {}
    if isinstance(meta, dict) and meta.get("cut_points") and isinstance(meta.get("cut_points"), list):
        return {"cut_points": meta.get("cut_points"), "bpm": meta.get("bpm"), "offset": meta.get("offset"), "method": meta.get("method", "curated"), "source": str(entry.path) if entry.path else None, "soundtrack_id": entry.id}
    return None


def save_curated_cut_points(entry: SoundtrackEntry | str | Path, *, cut_points: list[float] | None = None, bpm: float | None = None, offset: float | None = None, beat_times: list[float] | None = None, notes: list[str] | None = None, method: str = "curated", workspace: Workspace | None = None) -> Path:
    ws = workspace or load_workspace()
    ensure_not_inside_repo(ws.soundtracks_dir, kind="soundtrack curated cut points")
    if not isinstance(entry, SoundtrackEntry):
        res = resolve_soundtrack(entry, workspace=ws)
        if not res:
            raise FileNotFoundError(f"Soundtrack not found in registry: {entry}")
        entry = res
    dest_dir = ws.soundtracks_dir / entry.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    ref: dict[str, Any] = {
        "version": 1,
        "soundtrack_id": entry.id,
        "title": entry.title,
        "source": str(entry.path) if entry.path else None,
        "sha256_16": entry.sha256_16,
        "method": method,
        "curated": True,
    }
    if bpm is not None:
        ref["bpm"] = float(bpm)
    if offset is not None:
        ref["offset"] = float(offset)
    if cut_points is not None:
        ref["cut_points"] = [round(float(x), 4) for x in cut_points]
    if beat_times is not None:
        ref["beat_times"] = [round(float(x), 4) for x in beat_times]
    if notes:
        ref["notes"] = list(notes)
    out = dest_dir / "cut-points.yaml"
    out.write_text(yaml.safe_dump(ref, sort_keys=False, allow_unicode=True), encoding="utf-8")
    # update index pointer/hash
    data = _load_soundtracks_index(ws)
    tracks = data.setdefault("soundtracks", {})
    meta = tracks.get(entry.id) if isinstance(tracks.get(entry.id), dict) else {"id": entry.id}
    meta["cut_points_path"] = str(out)
    if cut_points is not None:
        meta["cut_points_count"] = len(cut_points)
    if bpm is not None:
        meta["bpm"] = float(bpm)
    tracks[entry.id] = meta
    _save_soundtracks_index(ws, data)
    return out
