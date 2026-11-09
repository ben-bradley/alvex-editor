import json
from pathlib import Path

from alvex_editor import api
from alvex_editor.audio import analyze_from_config
from alvex_editor.config import load_config
from alvex_editor.registry import (
    import_soundtrack,
    load_curated_cut_points,
    resolve_template,
    save_curated_cut_points,
)
from alvex_editor.timeline import Segment
from alvex_editor.workspace import load_workspace

REPO = Path(__file__).resolve().parents[1]


def _ws(tmp_path: Path):
    root = tmp_path / "Alvex"
    (root / "templates").mkdir(parents=True)
    (root / "soundtracks").mkdir(parents=True)
    (root / "projects").mkdir(parents=True)
    return load_workspace(root)


def test_workspace_defaults_and_layout(tmp_path):
    ws = _ws(tmp_path)
    assert ws.root.name == "Alvex"
    assert ws.templates_dir == ws.root / "templates"
    assert ws.soundtracks_dir == ws.root / "soundtracks"
    assert ws.projects_dir == ws.root / "projects"
    assert ws.project_dir("demo") == ws.root / "projects" / "demo"


def test_template_alias_resolves_bundled(tmp_path):
    ws = _ws(tmp_path)
    p = resolve_template("standard real estate template", workspace=ws)
    assert p.name == "exterior-showcase.md"
    assert p.exists()


def test_template_resolves_workspace_user_template(tmp_path):
    ws = _ws(tmp_path)
    user = ws.templates_dir / "my-custom.md"
    user.write_text("# Summary\n\n# Clip Edit Sequence\n\n1. **A** - 8-10 seconds.\n", encoding="utf-8")
    p = resolve_template("my-custom", workspace=ws)
    assert p.resolve() == user.resolve()


def test_soundtrack_import_and_curated_cut_points(tmp_path):
    ws = _ws(tmp_path)
    src = tmp_path / "bensound-acousticbreeze.mp3"
    src.write_bytes(b"ID3fake-audio")
    entry = import_soundtrack(src, workspace=ws, track_id="acoustic-breeze", title="Acoustic Breeze")
    assert entry.path and entry.path.exists()
    assert entry.path.parent == ws.soundtracks_dir / "acoustic-breeze"
    # self-contained copy
    assert entry.path.read_bytes() == b"ID3fake-audio"

    out = save_curated_cut_points(entry, cut_points=[10.82, 19.3, 28.82], bpm=120.0, notes=["confirmed"], workspace=ws)
    assert out.exists()
    ref = load_curated_cut_points(entry, workspace=ws)
    assert ref is not None
    assert ref["cut_points"] == [10.82, 19.3, 28.82]
    assert ref["bpm"] == 120.0
    assert ref["curated"] is True


def test_curated_registry_used_by_analyze_when_no_explicit_overrides(tmp_path, monkeypatch):
    # point workspace to tmp
    ws = _ws(tmp_path)
    monkeypatch.setenv("ALVEX_WORKSPACE", str(ws.root))
    src = tmp_path / "song.mp3"
    src.write_bytes(b"audio")
    entry = import_soundtrack(src, workspace=ws, track_id="song")
    save_curated_cut_points(entry, cut_points=[5.0, 10.0, 15.0], workspace=ws)

    proj = ws.projects_dir / "p1"
    proj.mkdir(parents=True)
    cfg_path = proj / "alvex.json"
    template = (REPO / "templates" / "exterior-showcase.md").resolve()
    cfg_path.write_text(json.dumps({
        "name": "p1",
        "template": str(template),
        "soundtrack": str(entry.path),
        "analysis": {"backend": "auto"},
    }, indent=2), encoding="utf-8")
    cfg = load_config(cfg_path)
    segs = [Segment(slot_id="a", name="A"), Segment(slot_id="b", name="B"), Segment(slot_id="c", name="C")]
    a = analyze_from_config(cfg, segs)
    assert a is not None
    assert a.cut_points == [5.0, 10.0, 15.0]
    assert "curated" in a.method or any("curated" in n for n in a.notes)


def test_explicit_config_cut_points_override_curated(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    monkeypatch.setenv("ALVEX_WORKSPACE", str(ws.root))
    src = tmp_path / "song.mp3"
    src.write_bytes(b"audio")
    entry = import_soundtrack(src, workspace=ws, track_id="song")
    save_curated_cut_points(entry, cut_points=[5.0, 10.0, 15.0], workspace=ws)

    proj = ws.projects_dir / "p2"
    proj.mkdir(parents=True)
    cfg_path = proj / "alvex.json"
    template = (REPO / "templates" / "exterior-showcase.md").resolve()
    cfg_path.write_text(json.dumps({
        "name": "p2",
        "template": str(template),
        "soundtrack": str(entry.path),
        "analysis": {"cut_points": [1.0, 2.0, 3.0]},
    }, indent=2), encoding="utf-8")
    cfg = load_config(cfg_path)
    segs = [Segment(slot_id="a", name="A"), Segment(slot_id="b", name="B"), Segment(slot_id="c", name="C")]
    a = analyze_from_config(cfg, segs)
    assert a is not None
    assert a.cut_points == [1.0, 2.0, 3.0]
    assert a.method == "config.cut_points"
