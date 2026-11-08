import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from alvex_editor.probe import find_ffmpeg, find_ffprobe, probe_media
from alvex_editor.renderer import RenderOptions, build_render_plan, run_render
from alvex_editor.timeline import AudioEffect, Overlay, Segment, SourceRef, Timeline, Transition

FONT = Path("/usr/share/fonts/truetype/ubuntu/Ubuntu-M.ttf")


def _workdir():
    # snap ffmpeg has `home` access but not hidden dirs; use a visible home path.
    base = Path.home() / "alvex-test-tmp"
    base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="render-", dir=str(base)))


def _ffmpeg(*args: str) -> None:
    res = subprocess.run([find_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", *args], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg setup failed: {res.stderr or res.stdout}")


def _make_clip(path: Path, duration: float, color: str = "blue") -> None:
    # video + audio so inputs are well-formed
    _ffmpeg(
        "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d={duration}:r=30",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
    )


def test_real_render_smoke():
    assert find_ffmpeg() and find_ffprobe()
    work = _workdir()
    try:
        clip_a = work / "a.mp4"
        clip_b = work / "b.mp4"
        music = work / "music.m4a"
        _make_clip(clip_a, 3.0, "navy")
        _make_clip(clip_b, 3.0, "darkgreen")
        _ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=4", "-c:a", "aac", str(music))

        # Verify probes work (Phase 3b validation capability)
        pa = probe_media(clip_a)
        assert pa.duration is not None and pa.duration >= 2.9
        assert pa.has_video

        segs = [
            Segment(
                slot_id="intro",
                name="Intro",
                resolved_duration=1.5,
                timeline_in=0.0,
                timeline_out=1.5,
                source=SourceRef(path=str(clip_a), status="mapped", in_point=0.0),
                transition_in=Transition(align="on-beat"),
                video_effects=[{"type": "fade_in", "duration": 0.5}],
                overlays=[Overlay(type="title", text="${address}", start=0.2, end=1.2)],
                audio=AudioEffect(fade_in=0.5),
            ),
            Segment(
                slot_id="outro",
                name="Outro",
                resolved_duration=1.5,
                timeline_in=1.5,
                timeline_out=3.0,
                source=SourceRef(path=str(clip_b), status="mapped", in_point=0.0),
                transition_in=Transition(align="on-beat"),
                video_effects=[{"type": "fade_out", "duration": 0.5, "anchor": "end"}],
                overlays=[Overlay(type="title", text="${address}", start="end-0.8", end="end")],
                audio=AudioEffect(fade_out=0.5),
            ),
        ]
        tl = Timeline(project="smoke", soundtrack=str(music), variables={"address": "1 Test Way"}, segments=segs)
        opts = RenderOptions(width=320, height=240, fps=30, crf=28, preset="ultrafast", probe=True)
        if FONT.exists():
            opts.fontfile = str(FONT)
        else:
            # no drawtext dependency if font missing; strip overlays
            for s in segs:
                s.overlays = []
        out = work / "out.mp4"
        plan = build_render_plan(tl, out, options=opts, require_files=True, probe_inputs=True)
        assert not any("source missing" in w.lower() for w in plan.warnings)
        assert plan.probe  # ffprobe metadata collected
        result = run_render(plan)
        assert result.returncode == 0, (result.stderr or result.stdout or "")[-2000:]
        assert out.exists() and out.stat().st_size > 1000
        info = probe_media(out)
        assert info.has_video
        assert info.duration is not None and 2.5 <= info.duration <= 3.5
    finally:
        shutil.rmtree(work, ignore_errors=True)
