from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


@dataclass
class MediaInfo:
    path: str
    exists: bool = False
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    has_video: bool = False
    has_audio: bool = False
    video_codec: str | None = None
    audio_codec: str | None = None
    rotation: int | None = None
    format_name: str | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("raw", None)
        return {k: v for k, v in data.items() if v is not None and v is not False and v != ""}


def _is_snap_binary(path: str | None) -> bool:
    if not path:
        return False
    p = path.replace("\\", "/")
    return "/snap/" in p or p.startswith("/snap")


def find_ffprobe() -> str | None:
    env = os.environ.get("FFPROBE") or os.environ.get("ALVEX_FFPROBE")
    if env and Path(env).exists():
        return env
    p = shutil.which("ffprobe")
    if p:
        return p
    if sys.platform.startswith("linux"):
        for candidate in ("/snap/ffmpeg/current/bin/ffprobe", "/snap/bin/ffprobe"):
            if Path(candidate).exists():
                return candidate
    return None


def find_ffmpeg() -> str | None:
    env = os.environ.get("FFMPEG") or os.environ.get("ALVEX_FFMPEG")
    if env and Path(env).exists():
        return env
    p = shutil.which("ffmpeg")
    if p:
        return p
    if sys.platform.startswith("linux"):
        for candidate in ("/snap/ffmpeg/current/bin/ffmpeg", "/snap/bin/ffmpeg"):
            if Path(candidate).exists():
                return candidate
    return None


def mkdtemp_portable(prefix: str = "alvex-", *, for_ffmpeg: bool = True) -> Path:
    """Create a temp dir that is visible to snap-confined ffmpeg on Linux.

    Snap ffmpeg may not access host /tmp; a home-visible dir is safe. On other
    platforms (or non-snap ffmpeg), use the standard temp directory.
    """
    ff = find_ffmpeg() if for_ffmpeg else None
    if sys.platform.startswith("linux") and _is_snap_binary(ff):
        base = Path.home() / ".cache" / "alvex" / "tmp"
        base.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix=prefix, dir=str(base)))
    return Path(tempfile.mkdtemp(prefix=prefix))


def _parse_rate(value: str | None) -> float | None:
    if not value or value in ("0/0", "N/A"):
        return None
    if "/" in value:
        num, den = value.split("/", 1)
        try:
            den_f = float(den)
            if den_f == 0:
                return None
            return float(num) / den_f
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(value)
    except ValueError:
        return None


def probe_media(path: str | Path, *, ffprobe_path: str | None = None) -> MediaInfo:
    path = Path(path)
    info = MediaInfo(path=str(path), exists=path.exists())
    if not info.exists:
        info.error = "file not found"
        return info
    exe = ffprobe_path or find_ffprobe()
    if not exe:
        info.error = "ffprobe not found"
        return info
    cmd = [exe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    try:
        proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
        data = json.loads(proc.stdout or "{}")
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError) as e:
        info.error = f"ffprobe failed: {e}"
        return info
    info.raw = data
    fmt = data.get("format") or {}
    info.format_name = fmt.get("format_name")
    if fmt.get("duration") not in (None, "N/A"):
        try:
            info.duration = float(fmt["duration"])
        except (ValueError, TypeError):
            pass
    for s in data.get("streams") or []:
        ctype = s.get("codec_type")
        if ctype == "video" and not info.has_video:
            info.has_video = True
            info.video_codec = s.get("codec_name")
            info.width = s.get("width")
            info.height = s.get("height")
            info.fps = _parse_rate(s.get("avg_frame_rate")) or _parse_rate(s.get("r_frame_rate"))
            if info.duration is None and s.get("duration") not in (None, "N/A"):
                try:
                    info.duration = float(s["duration"])
                except (ValueError, TypeError):
                    pass
            tags = s.get("tags") or {}
            if tags.get("rotate") is not None:
                try:
                    info.rotation = int(tags["rotate"])
                except (ValueError, TypeError):
                    pass
            for sd in s.get("side_data_list") or []:
                if sd.get("rotation") is not None and info.rotation is None:
                    try:
                        info.rotation = int(sd["rotation"])
                    except (ValueError, TypeError):
                        pass
        elif ctype == "audio":
            info.has_audio = True
            if info.audio_codec is None:
                info.audio_codec = s.get("codec_name")
            if info.duration is None and s.get("duration") not in (None, "N/A"):
                try:
                    info.duration = float(s["duration"])
                except (ValueError, TypeError):
                    pass
    return info


def probe_many(paths: list[str | Path], *, ffprobe_path: str | None = None) -> dict[str, MediaInfo]:
    return {str(Path(p)): probe_media(p, ffprobe_path=ffprobe_path) for p in paths}
