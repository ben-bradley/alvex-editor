from pathlib import Path

from alvex_editor.template import load_template

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "templates" / "exterior-showcase.md"


def test_parse_exterior_showcase_slot_order():
    t = load_template(TEMPLATE)
    names = [s.name for s in t.edit_slots]
    assert names == [
        "High Approach Front",
        "Mid Orbit Front",
        "Pan Front",
        "Approach Door",
        "Rise Up",
        "High Orbit Front",
        "High Orbit Back",
        "Mid Orbit Back",
        "Pan Back",
        "Features",
        "Departure",
    ]
    assert [s.slot_id for s in t.edit_slots][0] == "high-approach-front"
    assert [s.slot_id for s in t.edit_slots][-1] == "departure"


def test_features_optional_and_durations():
    t = load_template(TEMPLATE)
    by_id = {s.slot_id: s for s in t.edit_slots}
    features = by_id["features"]
    assert features.optional is True
    assert by_id["mid-orbit-front"].min_duration == 8.0
    assert by_id["mid-orbit-front"].max_duration == 10.0
    assert by_id["departure"].min_duration == 10.0
    assert by_id["departure"].max_duration == 20.0
    assert by_id["high-approach-front"].optional is False


def test_intro_effects():
    t = load_template(TEMPLATE)
    intro = t.edit_slots[0]
    assert intro.slot_id == "high-approach-front"
    assert any(e.get("type") == "fade_in" and e.get("duration") == 5.0 for e in intro.video_effects)
    assert intro.audio.fade_in == 5.0
    titles = [o for o in intro.overlays if o.type == "title"]
    assert titles, "expected intro address title overlay"
    assert titles[0].text == "${address}"
    assert titles[0].start == 1.0
    assert titles[0].end == 6.0


def test_outro_effects():
    t = load_template(TEMPLATE)
    outro = t.edit_slots[-1]
    assert outro.slot_id == "departure"
    assert any(e.get("type") == "fade_out" and e.get("anchor") == "end" and e.get("duration") == 7.0 for e in outro.video_effects)
    assert outro.audio.fade_out == 7.0
    titles = [o for o in outro.overlays if o.type == "title" and o.text == "${address}"]
    assert titles, "expected outro address title overlay"
    assert titles[0].start == "end-7"
    assert titles[0].end == "end"
