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
    assert data["template"].endswith("templates/exterior-showcase.md")
    assert data["variables"]["address"] == "123 Main St, Anytown, USA"
    assert len(data["segments"]) == 11
    statuses = {s["slot_id"]: s["source"]["status"] for s in data["segments"]}
    assert all(v == "unmapped" for v in statuses.values())
    features = next(s for s in data["segments"] if s["slot_id"] == "features")
    assert features["optional"] is True
    intro = data["segments"][0]
    assert any(e["type"] == "fade_in" for e in intro.get("video_effects", []))
    outro = data["segments"][-1]
    assert outro["audio"]["fade_out"] == 5.0
