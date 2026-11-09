from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable

from .config import ProjectConfig
from .policy import ensure_not_inside_repo
from .timeline import Segment, Timeline


@dataclass
class AudioAnalysis:
    source: str | None = None
    bpm: float | None = None
    offset: float = 0.0
    duration: float | None = None
    beat_times: list[float] = field(default_factory=list)
    cut_points: list[float] = field(default_factory=list)
    method: str = "unknown"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "bpm": self.bpm,
            "offset": self.offset,
            "duration": self.duration,
            "beat_times": [round(t, 4) for t in self.beat_times],
            "cut_points": [round(t, 4) for t in self.cut_points],
            "method": self.method,
            "notes": self.notes,
        }

    def write(self, path: str | Path) -> Path:
        path = Path(path)
        ensure_not_inside_repo(path, kind="analysis/edit plan")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return path


def load_analysis(path: str | Path) -> AudioAnalysis:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return AudioAnalysis(
        source=data.get("source"),
        bpm=data.get("bpm"),
        offset=float(data.get("offset") or 0.0),
        duration=data.get("duration"),
        beat_times=[float(t) for t in (data.get("beat_times") or [])],
        cut_points=[float(t) for t in (data.get("cut_points") or [])],
        method=data.get("method") or "file",
        notes=list(data.get("notes") or []),
    )


def _total_target_duration(segments: Iterable[Segment]) -> float:
    total = 0.0
    for s in segments:
        if s.min_duration and s.max_duration:
            total += (s.min_duration + s.max_duration) / 2
        elif s.target_duration:
            total += s.target_duration
        elif s.min_duration:
            total += s.min_duration
        elif s.max_duration:
            total += s.max_duration
        else:
            total += 9.0  # sensible default clip length
    return total


def generate_beat_grid(bpm: float, *, offset: float = 0.0, duration: float | None = None, end: float | None = None) -> list[float]:
    if bpm <= 0:
        raise ValueError("bpm must be > 0")
    interval = 60.0 / bpm
    limit = end if end is not None else duration
    if limit is None:
        raise ValueError("duration or end is required to generate a beat grid")
    # include offset as first grid point if >= 0
    t = offset
    beats: list[float] = []
    # guard against floating drift
    while t <= limit + 1e-9:
        if t >= -1e-9:
            beats.append(round(max(0.0, t), 6))
        t += interval
    if not beats:
        beats = [round(max(0.0, offset), 6)]
    return sorted(set(beats))


def _snap_to_grid(target: float, grid: list[float], *, min_v: float | None = None, max_v: float | None = None) -> float:
    candidates = grid
    if min_v is not None:
        candidates = [g for g in candidates if g >= min_v - 1e-9]
    if max_v is not None:
        candidates = [g for g in candidates if g <= max_v + 1e-9]
    if not candidates:
        # Fall back to clamped target when grid has no valid point.
        v = target
        if min_v is not None:
            v = max(v, min_v)
        if max_v is not None:
            v = min(v, max_v)
        return round(v, 4)
    return round(min(candidates, key=lambda g: (abs(g - target), g)), 4)


def _segment_target(seg: Segment) -> float:
    if seg.target_duration:
        return seg.target_duration
    if seg.min_duration and seg.max_duration:
        return (seg.min_duration + seg.max_duration) / 2
    if seg.min_duration:
        return seg.min_duration
    if seg.max_duration:
        return seg.max_duration
    return 9.0


def _is_skipped(seg: Segment) -> bool:
    # Optional segments with no mapped source are skipped in rendering and consume no timeline time.
    return bool(seg.optional and getattr(seg.source, "status", "unmapped") != "mapped" and not getattr(seg.source, "path", None))


def resolve_timing(timeline: Timeline, analysis: AudioAnalysis | None) -> None:
    """Resolve segment resolved_duration and timeline_in/out.

    If `analysis.cut_points` has enough points, they are used as segment end boundaries.
    Otherwise, segment durations are snapped to `analysis.beat_times` (respecting min/max).
    With no usable analysis, target/min/max durations are applied without beat snapping.
    """
    segments = [s for s in timeline.segments]  # preserve order
    if not segments:
        return

    grid = sorted(set([t for t in (analysis.beat_times if analysis else []) if t >= 0]))
    cut_points = sorted(set([t for t in (analysis.cut_points if analysis else []) if t >= 0]))
    active = [s for s in segments if not _is_skipped(s)]
    use_cuts = len(cut_points) >= len(active) and len(active) > 0
    cut_idx = 0

    cursor = 0.0
    for seg in segments:
        if _is_skipped(seg):
            seg.resolved_duration = 0.0
            seg.timeline_in = round(cursor, 4)
            seg.timeline_out = round(cursor, 4)
            seg.notes.append("skipped (optional, unmapped) - no timeline time")
            continue

        target = _segment_target(seg)
        lo = seg.min_duration
        hi = seg.max_duration

        if use_cuts:
            # cut point is the absolute end boundary for this active segment
            end_abs = cut_points[cut_idx]
            cut_idx += 1
            dur = max(0.0, end_abs - cursor)
            if lo is not None and dur < lo - 1e-6 and cut_idx < len(cut_points):
                seg.notes.append(f"cut point yields {dur:.3g}s, below min {lo:g}s")
            if hi is not None and dur > hi + 1e-6:
                seg.notes.append(f"cut point yields {dur:.3g}s, above max {hi:g}s")
            seg.resolved_duration = round(dur, 4)
            seg.timeline_in = round(cursor, 4)
            seg.timeline_out = round(end_abs, 4)
            cursor = end_abs
            seg.notes.append(f"resolved from cut point @ {end_abs:.4g}s")
            continue

        if grid and seg.transition_in.align == "on-beat":
            # snap the segment end (cursor+target) to a beat, then derive duration
            desired_end = cursor + target
            min_end = cursor + lo if lo is not None else cursor + 0.1
            max_end = cursor + hi if hi is not None else None
            end_abs = _snap_to_grid(desired_end, grid, min_v=min_end, max_v=max_end)
            dur = max(0.0, end_abs - cursor)
            seg.notes.append(f"resolved on beat grid @ end {end_abs:.4g}s")
        else:
            dur = target
            if lo is not None:
                dur = max(dur, lo)
            if hi is not None:
                dur = min(dur, hi)
            dur = round(dur, 4)
            end_abs = round(cursor + dur, 4)
            if analysis is not None:
                seg.notes.append("resolved from target duration (no beat snap)")
            else:
                seg.notes.append("resolved from target duration")

        seg.resolved_duration = round(dur, 4)
        seg.timeline_in = round(cursor, 4)
        seg.timeline_out = round(end_abs, 4)
        cursor = end_abs


# ---- soundtrack cut-point library / onset detection ----

def _soundtrack_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def library_dir(config: ProjectConfig | None = None) -> Path:
    opts = (config.analysis if config else None) or {}
    raw = opts.get("library_dir") or opts.get("library")
    if isinstance(raw, str) and raw.strip():
        p = Path(raw).expanduser()
        if not p.is_absolute() and config:
            p = (config.project_dir / p).resolve()
        return p
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        root = Path(xdg)
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = Path(local) / "alvex" / "cache" if local else (Path.home() / ".cache")
        return (root / "analysis").resolve()
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Caches"
    else:
        root = Path.home() / ".cache"
    return (root / "alvex" / "analysis").resolve()


def library_path(soundtrack: Path, config: ProjectConfig | None = None) -> Path | None:
    try:
        key = _soundtrack_hash(soundtrack)
    except OSError:
        return None
    return library_dir(config) / f"{soundtrack.stem}-{key}.json"


def load_library_entry(soundtrack: Path, config: ProjectConfig | None = None) -> AudioAnalysis | None:
    p = library_path(soundtrack, config)
    if not p or not p.exists():
        return None
    try:
        a = load_analysis(p)
        a.notes.append(f"loaded library: {p}")
        return a
    except Exception:
        return None


def save_library_entry(analysis: AudioAnalysis, soundtrack: Path, config: ProjectConfig | None = None) -> Path | None:
    p = library_path(soundtrack, config)
    if not p:
        return None
    try:
        analysis.write(p)
        analysis.notes.append(f"saved library: {p}")
        return p
    except Exception:
        return None


def analyze_onsets(
    path: Path,
    *,
    min_distance: float = 0.35,
    threshold_percentile: float = 75.0,
    threshold_scale: float = 0.8,
    max_peaks: int = 600,
) -> AudioAnalysis:
    """Detect onset/transition peaks via ffmpeg+numpy (no librosa)."""
    try:
        import numpy as np  # type: ignore
    except Exception as e:
        raise RuntimeError(f"numpy is required for onset analysis: {e}") from e
    try:
        from .probe import find_ffmpeg
    except Exception:
        find_ffmpeg = lambda: None  # type: ignore
    ffmpeg = find_ffmpeg() or "ffmpeg"
    sr = 22050
    hop = 512
    frame = 2048
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        err = (proc.stderr or b"").decode("utf-8", "ignore").strip().splitlines()[:2]
        raise RuntimeError(f"ffmpeg decode failed for onset analysis: {' | '.join(err) or proc.returncode}")
    y = np.frombuffer(proc.stdout, dtype=np.float32)
    n = max((len(y) - frame) // hop + 1, 1)
    env = np.array([np.sqrt(np.mean(y[i * hop : i * hop + frame] ** 2) + 1e-9) for i in range(n)], dtype=np.float64)
    onset = np.maximum(0.0, np.diff(env, prepend=env[0]))
    onset = np.convolve(onset, np.ones(3) / 3.0, mode="same")
    times = np.arange(len(onset), dtype=np.float64) * (hop / sr)
    dur = float(len(y) / sr)
    min_dist_frames = max(1, int(min_distance * sr / hop))
    thr = float(np.percentile(onset, threshold_percentile) * threshold_scale) if len(onset) else 0.0
    peaks: list[float] = []
    last = -min_dist_frames
    for i in range(1, len(onset) - 1):
        if onset[i] > thr and onset[i] >= onset[i - 1] and onset[i] >= onset[i + 1] and (i - last) >= min_dist_frames:
            peaks.append(round(float(times[i]), 4))
            last = i
    # Keep reasonably strong/representative peaks if extremely dense.
    if len(peaks) > max_peaks:
        step = max(1, len(peaks) // max_peaks)
        peaks = peaks[::step]
    a = AudioAnalysis(
        source=str(path),
        duration=round(dur, 4),
        beat_times=peaks,
        method="onsets",
        notes=[f"detected {len(peaks)} onset peaks (min_dist={min_distance:g}s)", "ffmpeg+numpy RMS onset detection"],
    )
    return a


def analyze_from_config(config: ProjectConfig, segments: Iterable[Segment], *, backend: str | None = None, refresh: bool = False) -> AudioAnalysis | None:
    opts = dict(config.analysis or {})
    if refresh or opts.get("refresh"):
        opts["refresh"] = True
    refresh = bool(opts.get("refresh"))
    backend = (backend or opts.get("backend") or "auto")
    backend = str(backend).lower()

    cache = config.resolved_analysis_path
    has_explicit = any(k in opts for k in ("bpm", "cut_points", "beat_times", "beats")) or "soundtrack_bpm" in config.raw
    # Explicit backend requests detection; --refresh forces recompute (ignores library/project cache).
    force_detect = refresh and backend in ("onsets", "librosa")
    # Project cache (per-project) reuse.
    if cache.exists() and not has_explicit and not refresh and backend == "auto":
        try:
            a = load_analysis(cache)
            a.notes.append(f"loaded cache: {cache}")
            return a
        except Exception:
            pass

    # Explicit timing data in config wins, unless a detection backend is explicitly requested.
    if not force_detect and opts.get("cut_points"):
        pts = [float(x) for x in opts["cut_points"]]
        a = AudioAnalysis(source=str(config.soundtrack_path) if config.soundtrack_path else None, cut_points=pts, method="config.cut_points")
        a.notes.append(f"{len(pts)} explicit cut points")
        return a

    if not force_detect and opts.get("bpm") is not None:
        bpm = float(opts["bpm"])
        offset = float(opts.get("offset") or 0.0)
        duration = opts.get("duration")
        horizon = float(duration) if duration is not None else max(_total_target_duration(segments) + 30.0, offset + 30.0)
        beats = generate_beat_grid(bpm, offset=offset, end=horizon)
        a = AudioAnalysis(
            source=str(config.soundtrack_path) if config.soundtrack_path else None,
            bpm=bpm,
            offset=offset,
            duration=float(horizon),
            beat_times=beats,
            method="config.bpm",
        )
        a.notes.append(f"generated {len(beats)} beats from {bpm:g} BPM over {horizon:.4g}s")
        return a

    if not force_detect and (opts.get("beat_times") or opts.get("beats")):
        beat_times = opts.get("beat_times") or opts.get("beats")
        a = AudioAnalysis(source=str(config.soundtrack_path) if config.soundtrack_path else None, beat_times=[float(t) for t in beat_times], method="config.beat_times")
        return a

    snd = config.soundtrack_path
    # Global library reuse by soundtrack identity (when no explicit timing overrides).
    if snd and snd.exists() and not has_explicit and not refresh and backend in ("auto", "onsets", "library"):
        lib = load_library_entry(snd, config)
        if lib and (lib.beat_times or lib.cut_points or lib.bpm):
            return lib

    # Explicit onset backend.
    if backend == "onsets":
        if not snd:
            return AudioAnalysis(method="missing", notes=["onsets backend requires soundtrack"])
        if not snd.exists():
            return AudioAnalysis(source=str(snd), method="missing", notes=[f"soundtrack not found: {snd}"])
        try:
            min_dist = float(opts.get("min_distance", 0.35))
            a = analyze_onsets(snd, min_distance=min_dist)
            save_library_entry(a, snd, config)
            return a
        except Exception as e:
            return AudioAnalysis(source=str(snd), method="unavailable", notes=[f"onsets analysis failed: {e}"])

    # Auto-detection backends (optional deps / tools).
    if snd and snd.exists():
        try:
            a = _analyze_with_librosa(snd)
            save_library_entry(a, snd, config)
            return a
        except Exception as e:
            # Fallback: try onsets (ffmpeg+numpy) as the built-in backend.
            try:
                a = analyze_onsets(snd)
                a.notes.append(f"librosa unavailable ({e}); used onsets fallback")
                save_library_entry(a, snd, config)
                return a
            except Exception as e2:
                return AudioAnalysis(source=str(snd), method="unavailable", notes=[f"auto-analysis unavailable: {e}; onsets fallback: {e2}. Provide analysis.bpm/cut_points or use --backend onsets."])

    if snd:
        return AudioAnalysis(source=str(snd), method="missing", notes=[f"soundtrack not found: {snd}"])
    return None


def _analyze_with_librosa(path: Path) -> AudioAnalysis:
    import librosa  # optional

    y, sr = librosa.load(str(path), sr=None, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    duration = float(librosa.get_duration(y=y, sr=sr))
    bpm = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)
    a = AudioAnalysis(source=str(path), bpm=bpm, offset=float(beat_times[0]) if beat_times else 0.0, duration=duration, beat_times=[float(t) for t in beat_times], method="librosa")
    a.notes.append(f"detected {len(beat_times)} beats")
    return a


def analyze_soundtrack(
    config: ProjectConfig,
    segments: Iterable[Segment],
    *,
    write_cache: bool = True,
    backend: str | None = None,
    refresh: bool = False,
) -> AudioAnalysis | None:
    analysis = analyze_from_config(config, segments, backend=backend, refresh=refresh)
    if analysis and write_cache and config.resolved_analysis_path:
        # Only cache meaningful results.
        if analysis.beat_times or analysis.cut_points or analysis.bpm:
            analysis.write(config.resolved_analysis_path)
    return analysis
