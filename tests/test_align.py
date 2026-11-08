import json

from alvex_editor.align import manifest_from_mappings
from alvex_editor.ollama import OllamaConfig, extract_json_object
from alvex_editor.timeline import Segment, Timeline, SourceRef, Transition


def test_ollama_config_from_dict():
    c = OllamaConfig.from_dict({"host": "192.168.11.136:11434", "model": "qwen2.5-coder:latest", "vision_model": "qwen3-vl:latest", "timeout": 30})
    assert c.host == "http://192.168.11.136:11434"
    assert c.model == "qwen2.5-coder:latest"
    assert c.vision_model == "qwen3-vl:latest"
    assert c.timeout == 30.0


def test_extract_json_object():
    data = extract_json_object('```json\n{"mappings": [{"slot_id":"a","clip_path":"x.mp4"}]}\n```')
    assert data["mappings"][0]["slot_id"] == "a"
    data2 = extract_json_object('prefix {"a":1} suffix')
    assert data2 == {"a": 1}


def test_manifest_from_mappings():
    tl = Timeline(project="p", segments=[Segment(slot_id="intro", name="Intro", source=SourceRef(), transition_in=Transition())])
    mappings = {
        "mappings": [{"slot_id": "intro", "clip_path": "/clips/a.mp4", "confidence": 0.9, "rationale": "front approach"}],
        "unmapped_slots": ["features"],
        "unused_clips": ["/clips/z.mp4"],
    }
    m = manifest_from_mappings(mappings, timeline=tl)
    assert m["sources"]["intro"]["path"] == "/clips/a.mp4"
    assert m["sources"]["intro"]["_suggestion"]["confidence"] == 0.9
    assert m["unmapped_slots"] == ["features"]
    assert m["unused_clips"] == ["/clips/z.mp4"]
