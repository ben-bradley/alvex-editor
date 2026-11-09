import json
import subprocess
import sys
from pathlib import Path

from alvex_editor import api
from alvex_editor import probe
from alvex_editor.cli import main
from alvex_editor.config import load_config
from alvex_editor.structured import load_structured
from alvex_editor.timeline import Segment, SourceRef, Timeline, Transition

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = (REPO / "templates" / "exterior-showcase.md").resolve()


def _make_project(tmp_path: Path, *, render=None, timing=None, cut_points=None, manifest=None, with_mapping=False):
    proj = tmp_path / "proj"
    (proj / "output").mkdir(parents=True)
    clips = tmp_path / "clips"
    clips.mkdir()
    clip = clips / "high-approach-front.mp4"
    clip.write_bytes(b"fake")
    manifest_name = manifest or "output/sources.json"
    cfg = {
        "name": "p1",
        "template": str(TEMPLATE),
        "soundtrack": None,
        "clips_dir": str(clips),
        "output_dir": "output",
        "timeline_path": "output/timeline.json",
        "analysis_path": "output/analysis.json",
        "sources_manifest": manifest_name,
        "analysis": {"cut_points": cut_points or [5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0]},
    }
    if render:
        cfg["render"] = render
    if timing:
        cfg["timing"] = timing
    cfg_path = proj / "alvex.json"
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    if with_mapping:
        (proj / "output").mkdir(parents=True, exist_ok=True)
        (proj / "output" / "sources.json").write_text(
            json.dumps({"sources": {"high-approach-front": str(clip)}}, indent=2),
            encoding="utf-8",
        )
    return cfg_path


def test_doctor_structure_without_project(monkeypatch):
    monkeypatch.setattr(probe, "find_ffmpeg", lambda: "/bin/ffmpeg")
    monkeypatch.setattr(probe, "find_ffprobe", lambda: "/bin/ffprobe")
    # api caches nothing, but uses find_ffmpeg/find_ffprobe from probe via its own import
    from alvex_editor import api as api_mod
    monkeypatch.setattr(api_mod, "find_ffmpeg", lambda: "/bin/ffmpeg")
    monkeypatch.setattr(api_mod, "find_ffprobe", lambda: "/bin/ffprobe")
    r = api.doctor()
    assert r["ok"] and r["command"] == "doctor"
    assert r["ffmpeg"]["ffmpeg_found"] is True
    assert "issues" in r and "python" in r


def test_status_includes_ffmpeg_info(tmp_path, monkeypatch):
    from alvex_editor import api as api_mod
    monkeypatch.setattr(api_mod, "find_ffmpeg", lambda: "/bin/ffmpeg")
    monkeypatch.setattr(api_mod, "find_ffprobe", lambda: "/bin/ffprobe")
    cfg = _make_project(tmp_path)
    r = api.project_status(project=cfg)
    assert r["ok"]
    s = r["status"]
    assert "ffmpeg_info" in s
    assert isinstance(s.get("sources_manifest"), (dict, type(None)))


def test_render_applies_project_render_config_on_dry_run(tmp_path, monkeypatch):
    from alvex_editor import api as api_mod
    monkeypatch.setattr(api_mod, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(api_mod, "find_ffprobe", lambda: "ffprobe")
    cfg = _make_project(tmp_path, render={"title_x": "60", "title_y": "h-text_h-60", "text_align": "L", "video_filters": ["eq=saturation=1.1"]}, with_mapping=True)
    r = api.render(project=cfg, preview=True, dry_run=True, allow_unmapped=True, no_probe=True)
    assert r["ok"], r
    assert r["project_render_config_applied"] is True
    assert "x=60" in r["filter_complex"]
    assert "text_align=L" in r["filter_complex"]
    assert "eq=saturation=1.1" in r["filter_complex"]
    assert r["replanned"] is True
    assert r.get("timeline_path")


def test_render_replans_fresh_without_explicit_timeline(tmp_path, monkeypatch):
    from alvex_editor import api as api_mod
    monkeypatch.setattr(api_mod, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(api_mod, "find_ffprobe", lambda: "ffprobe")
    cfg_path = _make_project(tmp_path, cut_points=[5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0], with_mapping=True)
    # initial plan creates timeline
    p1 = api.plan(project=cfg_path)
    assert p1["ok"]
    tl_path = Path(p1["timeline_path"])
    assert tl_path.exists()
    # change config cut points
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    data["analysis"]["cut_points"] = [6.0, 12.0, 18.0, 24.0, 30.0, 36.0, 42.0, 48.0, 54.0, 60.0]
    cfg_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    r = api.render(project=cfg_path, preview=True, dry_run=True, allow_unmapped=True, no_probe=True)
    assert r["ok"], r
    assert r["replanned"] is True
    # timeline should reflect new cut points
    tl = json.loads(tl_path.read_text(encoding="utf-8"))
    assert tl["analysis"]["cut_points"] == [6.0, 12.0, 18.0, 24.0, 30.0, 36.0, 42.0, 48.0, 54.0, 60.0]


def test_render_missing_auto_manifest_is_optional(tmp_path, monkeypatch):
    from alvex_editor import api as api_mod
    monkeypatch.setattr(api_mod, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(api_mod, "find_ffprobe", lambda: "ffprobe")
    cfg_path = _make_project(tmp_path, manifest="output/sources.json", with_mapping=True)
    # remove the manifest so auto-resolved manifest is missing but mappings are in timeline? plan merges manifest; easier: plan after creating mapping, then delete manifest
    r0 = api.plan(project=cfg_path)
    assert r0["ok"]
    mp = Path(cfg_path).parent / "output" / "sources.json"
    if mp.exists():
        mp.unlink()
    r = api.render(project=cfg_path, preview=True, dry_run=True, allow_unmapped=True, no_probe=True, no_plan=True)
    assert r["ok"], r
    assert r.get("manifest_applied") is None


def test_render_explicit_missing_manifest_fails(tmp_path, monkeypatch):
    from alvex_editor import api as api_mod
    monkeypatch.setattr(api_mod, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(api_mod, "find_ffprobe", lambda: "ffmpeg")
    cfg_path = _make_project(tmp_path)
    r = api.render(project=cfg_path, manifest=str(tmp_path / "nope.json"), preview=True, dry_run=True, allow_unmapped=True, no_probe=True)
    assert not r["ok"]
    assert "Manifest not found" in r.get("error", "")


def test_cli_doctor_json(capsys, monkeypatch):
    from alvex_editor import api as api_mod
    monkeypatch.setattr(api_mod, "find_ffmpeg", lambda: "/bin/ffmpeg")
    monkeypatch.setattr(api_mod, "find_ffprobe", lambda: "/bin/ffprobe")
    rc = main(["doctor", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["ok"] and data["command"] == "doctor"


def test_cli_soundtracks_list_json(tmp_path, capsys, monkeypatch):
    ws = tmp_path / "Alvex"
    (ws / "templates").mkdir(parents=True)
    (ws / "soundtracks").mkdir(parents=True)
    (ws / "projects").mkdir(parents=True)
    rc = main(["soundtracks", "--workspace", str(ws), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["ok"] and data["command"] == "soundtracks"


def test_cli_soundtracks_set_cuts_json(tmp_path, capsys, monkeypatch):
    ws = tmp_path / "Alvex"
    (ws / "templates").mkdir(parents=True)
    (ws / "projects").mkdir(parents=True)
    (ws / "soundtracks").mkdir(parents=True)
    # register via API to ensure correct format
    src = tmp_path / "song.mp3"
    src.write_bytes(b"fake")
    r = api.soundtrack_import(source=str(src), workspace=str(ws), track_id="song1")
    assert r["ok"], r
    rc = main(["soundtracks", "set-cuts", "song1", "--cut-points", "1,2,3", "--workspace", str(ws), "--json"])
    out = capsys.readouterr().out
    assert rc == 0, out
    data = json.loads(out)
    assert data["ok"] and data.get("cut_points_path")


def test_cli_error_emits_valid_json(capsys):
    rc = main(["status", "-p", "C:/definitely/not/a/real/project/alvex.json", "--json"])
    out = capsys.readouterr().out
    assert rc == 1
    data = json.loads(out)
    assert data["ok"] is False and "error" in data
