from alvex_editor.select import apply_in_points_to_manifest, generate_candidates
from alvex_editor.timeline import Segment, SourceRef, Transition


def test_generate_candidates_clamped():
    seg = Segment(slot_id="a", name="A", resolved_duration=9.0, source=SourceRef(path="x.mp4"), transition_in=Transition(align="on-beat"))
    cands = generate_candidates(seg, source_duration=14.0, count=5)
    assert cands
    for c in cands:
        assert c.in_point >= 0.0
        assert c.out_point <= 14.0001
        assert abs((c.out_point - c.in_point) - 9.0) < 1e-6


def test_generate_candidates_centered_heuristic():
    seg = Segment(
        slot_id="mid-orbit-front",
        name="Mid Orbit Front",
        description="front of the house should be centered in the frame at the midpoint of the clip",
        resolved_duration=9.0,
        source=SourceRef(path="x.mp4"),
        transition_in=Transition(align="on-beat"),
    )
    cands = generate_candidates(seg, source_duration=14.9, count=5)
    # window centered on source midpoint (7.45) => in = 7.45 - 4.5 = 2.95
    assert any(abs(c.in_point - 2.95) < 0.2 and "midpoint" in c.reason for c in cands)


def test_generate_candidates_outro_prefers_end():
    seg = Segment(slot_id="departure", name="Departure", description="closing clip", resolved_duration=15.0, source=SourceRef(path="x.mp4"), transition_in=Transition())
    cands = generate_candidates(seg, source_duration=24.0, count=5)
    assert any(c.in_point >= 8.9 and "end" in c.reason for c in cands)


def test_apply_in_points_to_manifest():
    manifest = {"sources": {"intro": "/a.mp4", "main": {"path": "/b.mp4"}}}
    out = apply_in_points_to_manifest(manifest, {"intro": {"in_point": 1.5, "detail": {"method": "heuristic"}}, "main": {"in_point": 3.0}})
    assert out["sources"]["intro"]["path"] == "/a.mp4"
    assert out["sources"]["intro"]["in_point"] == 1.5
    assert out["sources"]["main"]["in_point"] == 3.0
    assert manifest["sources"]["intro"] == "/a.mp4"  # original not mutated (string case copied structurally? we deep-ish copy)
