import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from alvex_editor.probe import find_ffmpeg, find_ffprobe, probe_media

REPO = Path(__file__).resolve().parents[1]


def _workdir():
    # snap ffmpeg has `home` access but not hidden dirs; use a visible home path.
    base = Path.home() / "alvex-test-tmp"
    base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="run-", dir=str(base)))


def test_find_tools():
    # ffmpeg/ffprobe were confirmed installed in this environment (Phase 3b precondition).
    assert find_ffmpeg() is not None
    assert find_ffprobe() is not None


def test_probe_media_synthetic():
    work = _workdir()
    try:
        src = work / "clip.mp4"
        subprocess.run(
            [
                find_ffmpeg(),
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=1.2:size=320x240:rate=30",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=1.2",
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(src),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        info = probe_media(src)
        assert info.exists
        assert info.error is None
        assert info.has_video
        assert info.has_audio
        assert info.width == 320
        assert info.height == 240
        assert info.duration is not None and 1.0 <= info.duration <= 1.5
    finally:
        shutil.rmtree(work, ignore_errors=True)
