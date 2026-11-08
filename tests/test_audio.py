import json
from pathlib import Path

from alvex_editor.audio import AudioAnalysis, generate_beat_grid, resolve_timing
from alvex_editor.config import load_config
from alvex_editor.planner import build_plan
from alvex_editor.timeline import Segment, SourceRef, Transition

REPO = Path(__file__).resolve().parents[1]


def test_generate_beat_grid():
    beats = generate_beat_grid(120.0, offset=0.0, end=5.0)
    assert beats[0] == 0.0
    assert abs(beats[1] - 0.5) < 1e-9
    assert abs(beats[-1] - 5.0) < 1e-9
    assert len(beats) == 11  # 0.0,0.5,...,5.0


def test_resolve_timing_snaps_to_beats_within_bounds():
    segs = [
        Segment(slot_id="a", name="A", min_duration=8.0, max_duration=10.0, transition_in=Transition(align="on-beat")),
        Segment(slot_id="b", name="B", min_duration=8.0, max_duration=10.0, transition_in=Transition(align="on-beat")),
    ]
    from alvex_editor.timeline import Timeline

    tl = Timeline(segments=segs)
    analysis = AudioAnalysis(bpm=120.0, offset=0.0, beat_times=generate_beat_grid(120.0, offset=0.0, end=60.0), method="test")
    resolve_timing(tl, analysis)
    assert segs[0].resolved_duration == 9.0
    assert segs[0].timeline_in == 0.0
    assert segs[0].timeline_out == 9.0
    assert segs[1].timeline_in == 9.0
    assert segs[1].resolved_duration == 9.0
    assert segs[1].timeline_out == 18.0
    for s in segs:
        assert 8.0 <= s.resolved_duration <= 10.0
        # on 0.5s grid
        assert abs(s.timeline_out * 2 - round(s.timeline_out * 2)) < 1e-9


def test_resolve_timing_uses_explicit_cut_points():
    segs = [
        Segment(slot_id="a", name="A", transition_in=Transition(align="on-beat")),
        Segment(slot_id="b", name="B", transition_in=Transition(align="on-beat")),
    ]
    from alvex_editor.timeline import Timeline

    tl = Timeline(segments=segs)
    analysis = AudioAnalysis(cut_points=[9.5, 18.25], method="test")
    resolve_timing(tl, analysis)
    assert segs[0].timeline_in == 0.0 and segs[0].timeline_out == 9.5
    assert segs[1].timeline_in == 9.5 and segs[1].timeline_out == 18.25
    assert segs[0].resolved_duration == 9.5


def test_resolve_timing_without_analysis_uses_targets():
    segs = [
        Segment(slot_id="a", name="A", min_duration=8.0, max_duration=10.0),
        Segment(slot_id="b", name="B", min_duration=10.0, max_duration=20.0),
    ]
    from alvex_editor.timeline import Timeline

    tl = Timeline(segments=segs)
    resolve_timing(tl, None)
    assert segs[0].resolved_duration == 9.0
    assert segs[1].resolved_duration == 15.0
    assert segs[0].timeline_out == 9.0
    assert segs[1].timeline_out == 24.0


def test_plan_with_bpm_resolves_on_beat(tmp_path):
    cfg_path = tmp_path / "alvex.yaml"
    template = (REPO / "templates" / "exterior-showcase.md").resolve()
    cfg_path.write_text(
        "\n".join(
            [
                "name: bpm-test",
                f"template: {template}",
                "analysis:",
                "  bpm: 120",
                "  offset: 0",
                "variables:",
                '  address: "1 Test St"',
            ]
        ),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    timeline = build_plan(cfg, map_clips=False)
    assert timeline.analysis.get("method") == "config.bpm"
    assert timeline.analysis.get("bpm") == 120.0
    assert len(timeline.analysis.get("beat_times", [])) > 0
    assert len(timeline.segments) == 11
    # contiguous, resolved, and beat-aligned where on-beat (skipped optional-unmapped take 0 time)
    prev = 0.0
    for s in timeline.segments:
        assert s.resolved_duration is not None
        if s.optional and s.source.status != "mapped":
            assert s.resolved_duration == 0.0
            assert s.timeline_in == prev and s.timeline_out == prev
            continue
        assert s.resolved_duration > 0
        assert abs((s.timeline_in or 0) - prev) < 1e-9
        assert abs((s.timeline_out or 0) - prev - s.resolved_duration) < 1e-9
        prev = s.timeline_out
        if s.min_duration is not None:
            assert s.resolved_duration >= s.min_duration - 1e-6
        if s.max_duration is not None:
            assert s.resolved_duration <= s.max_duration + 1e-6
        if s.transition_in.align == "on-beat":
            # 120 BPM => 0.5s grid
            assert abs(s.timeline_out * 2 - round(s.timeline_out * 2)) < 1e-6
    # verify written timeline contains analysis + timing
    out = tmp_path / "timeline.json"
    timeline.write(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["analysis"]["method"] == "config.bpm"
    assert data["segments"][0]["timeline_in"] == 0.0
    assert "resolved_duration" in data["segments"][0]
