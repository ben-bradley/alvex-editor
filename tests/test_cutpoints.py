from pathlib import Path

from alvex_editor import api
from alvex_editor import cutpoints
from alvex_editor.config import load_config

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = (REPO / "templates" / "exterior-showcase.md").resolve()


def _cfg(tmp_path, cut_points=None):
    proj = tmp_path / "proj"
    (proj / "output").mkdir(parents=True)
    cfg = {
        "name": "p",
        "template": str(TEMPLATE),
        "output_dir": "output",
        "analysis": {"cut_points": cut_points or [9.822, 19.2958, 28.816, 38.3129, 47.8331, 57.3068, 67.0, 76.324, 85.8442, 97.1291]},
    }
    p = proj / "alvex.json"
    p.write_text(__import__("json").dumps(cfg, indent=2), encoding="utf-8")
    return load_config(p)


def test_label_cut_points_features_aware(tmp_path):
    cfg = _cfg(tmp_path)
    r = cutpoints.label_cut_points(cfg)
    # exterior-showcase has 11 slots; Features optional and unmapped => 10 active boundaries
    assert r["slots_total"] == 11
    assert "features" in r["skipped_slots"]
    assert r["active_slots"] == 10
    assert len(r["boundaries"]) == 10
    assert r["boundaries"][-1]["slot_id"] == "departure"
    assert r["boundaries"][-1]["label"].endswith("(end)")


def test_detect_onset_pairs_and_second_of_pair():
    onsets = [9.0, 9.9, 19.0, 38.0, 38.95, 57.0]
    pairs = cutpoints.detect_onset_pairs(onsets, min_gap=0.8, max_gap=1.4)
    assert any(abs(p["first"] - 9.0) < 1e-6 and abs(p["second"] - 9.9) < 1e-6 for p in pairs)
    pick = cutpoints.suggest_second_of_pair(onsets, near=38.1)
    assert pick and abs(pick["second"] - 38.95) < 1e-6


def test_nudge_to_second_of_pair(tmp_path):
    cfg = _cfg(tmp_path)
    pts = list(cfg.analysis["cut_points"])
    # pair near 38s: first=38.0, second=38.95 (gap 0.95) models "cut on 2nd strong note"
    onsets = [37.0, 38.0, 38.95, 47.0]
    res = cutpoints.nudge_cut_points(pts, near=38.3, to="second-of-pair", onsets=onsets)
    assert res["reason"] == "second-of-pair"
    assert res["new"] == 38.95
    assert res["requires_confirmation"] is True


def test_suggest_cut_points_template_aware(tmp_path):
    cfg = _cfg(tmp_path)
    onsets = [float(i) for i in range(1, 120)]
    r = cutpoints.suggest_cut_points(cfg, onsets=onsets)
    assert r["ok"] is True
    assert r["template_aware_count"] == 10
    assert len(r["suggested_cut_points"]) <= 10


def test_api_cuts_show_and_nudge(tmp_path):
    cfg = _cfg(tmp_path)
    shown = api.cuts_show(project=cfg.config_path)
    assert shown["ok"] and shown["active_slots"] == 10
    nudged = api.cuts_nudge(project=cfg.config_path, near=38.3, to=38.5)
    assert nudged["ok"] and nudged["requires_confirmation"]
    assert 38.5 in nudged["cut_points"]
