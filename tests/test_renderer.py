import json
from pathlib import Path

from alvex_editor.config import load_config
from alvex_editor.planner import build_plan
from alvex_editor.renderer import RenderOptions, apply_manifest, build_render_plan, load_manifest, renderable_segments
from alvex_editor.timeline import AudioEffect, Overlay, Segment, SourceRef, Timeline, Transition

REPO = Path(__file__).resolve().parents[1]


def _timeline_with_timing() -> Timeline:
    segs = [
        Segment(
            slot_id="intro",
            name="Intro",
            resolved_duration=5.0,
            timeline_in=0.0,
            timeline_out=5.0,
            source=SourceRef(path="/media/a.mp4", status="mapped"),
            transition_in=Transition(align="on-beat"),
            video_effects=[{"type": "fade_in", "duration": 5.0}],
            overlays=[Overlay(type="title", text="${address}", start=1.0, end=5.0)],
            audio=AudioEffect(fade_in=5.0),
        ),
        Segment(
            slot_id="main",
            name="Main",
            resolved_duration=9.0,
            timeline_in=5.0,
            timeline_out=14.0,
            source=SourceRef(path="/media/b.mp4", status="mapped"),
            transition_in=Transition(align="on-beat"),
        ),
        Segment(
            slot_id="outro",
            name="Outro",
            resolved_duration=5.0,
            timeline_in=14.0,
            timeline_out=19.0,
            source=SourceRef(path="/media/c.mp4", status="mapped"),
            transition_in=Transition(align="on-beat"),
            video_effects=[{"type": "fade_out", "duration": 5.0, "anchor": "end"}],
            overlays=[Overlay(type="title", text="${address}", start="end-5", end="end")],
            audio=AudioEffect(fade_out=5.0),
        ),
    ]
    return Timeline(project="t", soundtrack="/media/music.mp3", variables={"address": "123 Main St"}, segments=segs)


def test_manifest_apply(tmp_path):
    mpath = tmp_path / "sources.yaml"
    mpath.write_text("sources:\n  intro: /clips/intro.mp4\n  main:\n    path: clips/main.mp4\n    in_point: 1.5\n", encoding="utf-8")
    manifest = load_manifest(mpath)
    tl = _timeline_with_timing()
    tl.segments[0].source = SourceRef(status="unmapped")
    tl.segments[1].source = SourceRef(status="unmapped")
    apply_manifest(tl, manifest, base_dir=tmp_path)
    intro_path = Path(tl.segments[0].source.path)
    assert intro_path.is_absolute() or str(intro_path).replace("\\", "/").endswith("/clips/intro.mp4")
    assert tl.segments[0].source.status == "mapped"
    assert tl.segments[1].source.path == str((tmp_path / "clips/main.mp4").resolve())
    assert tl.segments[1].source.in_point == 1.5


def test_renderable_segments_skips_optional_unmapped():
    tl = _timeline_with_timing()
    tl.segments.append(Segment(slot_id="feat", name="Features", optional=True, source=SourceRef(status="unmapped")))
    segs = renderable_segments(tl)
    assert [s.slot_id for s in segs] == ["intro", "main", "outro"]


def test_build_render_plan_structure():
    tl = _timeline_with_timing()
    plan = build_render_plan(tl, "/out/final.mp4")
    assert plan.command[0] == "ffmpeg"
    assert "-filter_complex" in plan.command
    assert plan.command.count("-i") == 4  # 3 clips + soundtrack
    assert "concat=n=3:v=1:a=0[vout]" in plan.filter_complex
    assert "fade=t=in:st=0.0000:d=5.0000" in plan.filter_complex
    assert "fade=t=out" in plan.filter_complex
    assert "afade=t=in" in plan.filter_complex
    assert "afade=t=out" in plan.filter_complex
    assert "drawtext=" in plan.filter_complex
    assert "123 Main St" in plan.filter_complex  # ${address} substituted
    assert "[aout]" in plan.filter_complex
    assert "-map" in plan.command and "[vout]" in plan.command and "[aout]" in plan.command
    assert plan.output == Path("/out/final.mp4")
    assert "#!/usr/bin/env bash" in plan.script


def test_build_plan_then_render_dry_run_with_manifest(tmp_path):
    template = (REPO / "templates" / "exterior-showcase.md").resolve()
    cfg_path = tmp_path / "alvex.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                "name: render-test",
                f"template: {template}",
                "soundtrack: /media/music.mp3",
                "analysis:",
                "  bpm: 120",
                "variables:",
                '  address: "456 Oak Ave"',
            ]
        ),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    tl = build_plan(cfg)
    # Map all slots (including optional features) to dummy sources.
    for s in tl.segments:
        s.source.path = f"/clips/{s.slot_id}.mp4"
        s.source.status = "mapped"
    plan = build_render_plan(tl, tmp_path / "out.mp4", options=RenderOptions(font="Sans"))
    assert f"concat=n={len(tl.segments)}:v=1:a=0[vout]" in plan.filter_complex
    assert plan.command.count("-i") == len(tl.segments) + 1  # clips + soundtrack
    assert "456 Oak Ave" in plan.filter_complex  # ${address} substituted in title overlays
    assert "fade=t=in" in plan.filter_complex
    assert "afade=t=out" in plan.filter_complex
    assert "[vout]" in plan.command and "[aout]" in plan.command


def test_render_options_text_align_and_position():
    opts = RenderOptions.from_dict({
        "title_x": "60",
        "title_y": "h-text_h-60",
        "text_align": "L",
        "video_filters": ["eq=contrast=1.05:saturation=1.1"],
    })
    assert opts.title_x == "60"
    assert opts.title_y == "h-text_h-60"
    assert opts.text_align == "L"
    assert opts.video_filters == ["eq=contrast=1.05:saturation=1.1"]
    tl = _timeline_with_timing()
    plan = build_render_plan(tl, "/out/final.mp4", options=opts)
    assert ":x=60:y=h-text_h-60" in plan.filter_complex
    assert ":text_align=L" in plan.filter_complex
    assert "eq=contrast=1.05:saturation=1.1" in plan.filter_complex
    # default remains centered
    plan_default = build_render_plan(_timeline_with_timing(), "/out/final.mp4")
    assert ":text_align=C" in plan_default.filter_complex
