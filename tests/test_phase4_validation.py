import json
from pathlib import Path

import pytest

from alvex_editor.config import load_config
from alvex_editor.planner import build_plan
from alvex_editor.validation import validate_config

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = (REPO / "templates" / "exterior-showcase.md").resolve()


def test_validate_config_unknown_keys_warn():
    r = validate_config({"template": "x.md", "render": {"title_x": "1", "bogus_render": 1}, "mystery": True})
    assert r.ok
    assert any("unknown top-level config key: mystery" in w for w in r.warnings)
    assert any("unknown render key: bogus_render" in w for w in r.warnings)


def test_validate_config_invalid_values_error():
    r = validate_config({"template": "x.md", "render": {"fontsize": "big"}, "timing": {"outro_audio_fade_seconds": -1}, "analysis": {"cut_points": "nope"}})
    assert not r.ok
    joined = "\n".join(r.errors)
    assert "render.fontsize" in joined
    assert "timing.outro_audio_fade_seconds" in joined
    assert "analysis.cut_points" in joined


def test_load_config_preset_merge(tmp_path, monkeypatch):
    monkeypatch.setenv("ALVEX_WORKSPACE", str(tmp_path / "ws"))
    (tmp_path / "ws" / "presets").mkdir(parents=True)
    (tmp_path / "ws" / "presets" / "safe.json").write_text(json.dumps({
        "render": {"title_x": "(w-text_w)/2", "text_align": "C", "video_filters": ["eq=contrast=1.0"]},
        "timing": {"outro_fade_seconds": 5.0},
    }), encoding="utf-8")
    proj = tmp_path / "proj"
    proj.mkdir()
    cfg_path = proj / "alvex.json"
    cfg_path.write_text(json.dumps({
        "template": str(TEMPLATE),
        "preset": "safe",
        "render": {"text_align": "L", "title_x": "60"},
        "analysis": {"cut_points": [5,10,15,20,25,30,35,40,45,50]},
    }, indent=2), encoding="utf-8")
    cfg = load_config(cfg_path)
    # project overrides preset
    assert cfg.raw["preset"] == "safe"
    # merged render: project wins on keys it sets
    assert (cfg.raw.get("render") or {}).get("text_align") == "L"
    assert (cfg.raw.get("render") or {}).get("title_x") == "60"


def test_segment_overrides_in_point(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    cfg_path = proj / "alvex.json"
    cfg_path.write_text(json.dumps({
        "template": str(TEMPLATE),
        "analysis": {"cut_points": [5,10,15,20,25,30,35,40,45,50]},
        "segment_overrides": {"approach-door": {"in_point": 7.352}},
    }, indent=2), encoding="utf-8")
    cfg = load_config(cfg_path)
    tl = build_plan(cfg, map_clips=False)
    seg = [s for s in tl.segments if s.slot_id == "approach-door"][0]
    assert seg.source.in_point == 7.352
