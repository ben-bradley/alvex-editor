import json
from pathlib import Path

from alvex_editor.config import load_config
from alvex_editor.planner import build_plan

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "examples" / "exterior-showcase" / "alvex.yaml"


def test_load_example_config():
    cfg = load_config(CONFIG)
    assert cfg.template_path.name == "exterior-showcase.md"
    assert cfg.template_path.exists()
    assert cfg.variables["address"] == "123 Main St, Anytown, USA"


def test_build_plan_writes_valid_timeline(tmp_path):
    cfg = load_config(CONFIG)
    timeline = build_plan(cfg)
    out = tmp_path / "timeline.json"
    timeline.write(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["template"].replace("\\", "/").endswith("templates/exterior-showcase.md")
    assert data["variables"]["address"] == "123 Main St, Anytown, USA"
    assert len(data["segments"]) == 11
    statuses = {s["slot_id"]: s["source"]["status"] for s in data["segments"]}
    assert all(v == "unmapped" for v in statuses.values())
    features = next(s for s in data["segments"] if s["slot_id"] == "features")
    assert features["optional"] is True
    intro = data["segments"][0]
    assert any(e["type"] == "fade_in" for e in intro.get("video_effects", []))
    outro = data["segments"][-1]
    assert outro["audio"]["fade_out"] == 7.0


def test_build_plan_timing_overrides(tmp_path):
    template = (REPO / "templates" / "exterior-showcase.md").resolve()
    cfg_path = tmp_path / "alvex.yaml"
    cfg_path.write_text(
        "\n".join([
            "name: timing-test",
            f"template: {template}",
            "soundtrack: /media/music.mp3",
            "analysis:",
            "  bpm: 120",
            "variables:",
            '  address: "789 Pine Rd"',
            "timing:",
            "  intro_fade_seconds: 3.5",
            "  intro_title_after_seconds: 0.5",
            "  intro_title_duration_seconds: 4.0",
            "  outro_fade_seconds: 4.0",
            "  outro_title_before_end_seconds: 5.0",
        ]),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    timeline = build_plan(cfg)
    intro = timeline.segments[0]
    assert intro.audio.fade_in == 3.5
    fade_ins = [e for e in (intro.video_effects or []) if isinstance(e, dict) and e.get("type") == "fade_in"]
    assert fade_ins and fade_ins[0]["duration"] == 3.5
    titles = [o for o in (intro.overlays or []) if o.text == "${address}" and isinstance(o.start, (int, float))]
    assert titles and titles[0].start == 0.5 and titles[0].end == 4.5
    outro = timeline.segments[-1]
    assert outro.audio.fade_out == 4.0
    fade_outs = [e for e in (outro.video_effects or []) if isinstance(e, dict) and e.get("type") == "fade_out"]
    assert fade_outs and fade_outs[0]["duration"] == 4.0
    end_titles = [o for o in (outro.overlays or []) if o.text == "${address}" and str(o.start).startswith("end-")]
    assert end_titles and end_titles[0].start == "end-5" and end_titles[0].end == "end"


def test_build_plan_timing_decoupled_audio_fade(tmp_path):
    template = (REPO / "templates" / "exterior-showcase.md").resolve()
    cfg_path = tmp_path / "alvex.yaml"
    cfg_path.write_text(
        "\n".join([
            "name: timing-test",
            f"template: {template}",
            "soundtrack: /media/music.mp3",
            "analysis:",
            "  bpm: 120",
            "timing:",
            "  outro_video_fade_seconds: 7.0",
            "  outro_audio_fade_seconds: 7.0",
            "  outro_audio_fade_out_before_end_seconds: 2.629",
        ]),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    timeline = build_plan(cfg)
    outro = timeline.segments[-1]
    fade_outs = [e for e in (outro.video_effects or []) if isinstance(e, dict) and e.get("type") == "fade_out"]
    assert fade_outs and fade_outs[0]["duration"] == 7.0
    assert outro.audio.fade_out == 7.0
    assert outro.audio.fade_out_end_before == 2.629
