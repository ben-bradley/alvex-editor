from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable

from .audio import analyze_soundtrack, resolve_timing
from .config import ProjectConfig
from .template import load_template
from .timeline import Segment, SourceRef, Timeline

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm"}


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def _candidate_score(segment: Segment, path: Path) -> int:
    hay = _tokens(path.stem)
    score = 0
    for key in (segment.slot_id, segment.name, segment.source.hint or ""):
        for t in _tokens(key):
            if len(t) < 3:
                continue
            if t in hay:
                score += 2 if t == segment.slot_id.replace("-", "") else 1
    # common aliases
    aliases = {
        "high-approach-front": {"intro", "approach", "front", "high"},
        "rise-up": {"rise", "up", "top", "reveal"},
        "approach-door": {"door", "entry", "walkup"},
        "departure": {"outro", "depart", "exit", "away"},
        "mid-orbit-front": {"mid", "orbit", "front"},
        "mid-orbit-back": {"mid", "orbit", "back"},
        "high-orbit-front": {"high", "orbit", "front"},
        "high-orbit-back": {"high", "orbit", "back"},
        "pan-front": {"pan", "front"},
        "pan-back": {"pan", "back"},
        "features": {"feature", "pool", "barn", "dock", "shop"},
    }
    for t in aliases.get(segment.slot_id, set()):
        if t in hay:
            score += 1
    return score


def discover_clips(clips_dir: Path) -> list[Path]:
    if not clips_dir or not clips_dir.exists():
        return []
    clips = [p for p in clips_dir.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    return sorted(clips)


def map_sources(segments: Iterable[Segment], clips: list[Path]) -> None:
    remaining = list(clips)
    for seg in segments:
        if not remaining:
            break
        scored = sorted((( _candidate_score(seg, p), p) for p in remaining), key=lambda x: (-x[0], x[1].name))
        best_score, best = scored[0]
        if best_score <= 0:
            continue
        seg.source.path = str(best)
        seg.source.status = "mapped"
        remaining.remove(best)


def build_plan(
    config: ProjectConfig,
    *,
    map_clips: bool = False,
    analyze: bool = True,
    write_analysis_cache: bool = True,
) -> Timeline:
    template = load_template(config.template_path)
    segments = []
    for s in template.edit_slots:
        seg = Segment(
            slot_id=s.slot_id,
            name=s.name,
            description=s.description,
            optional=s.optional,
            target_duration=s.target_duration,
            min_duration=s.min_duration,
            max_duration=s.max_duration,
            resolved_duration=s.resolved_duration,
            timeline_in=s.timeline_in,
            timeline_out=s.timeline_out,
            source=SourceRef(hint=s.source.hint, status=s.source.status),
            transition_in=s.transition_in,
            overlays=list(s.overlays),
            video_effects=list(s.video_effects),
            audio=s.audio,
            notes=list(s.notes),
        )
        segments.append(seg)

    clips_dir = config.clips_path
    if map_clips and clips_dir:
        clips = discover_clips(clips_dir)
        map_sources(segments, clips)
        if not clips:
            for seg in segments:
                if seg.source.status == "unmapped":
                    seg.notes.append(f"clips_dir not found or empty: {clips_dir}")
    elif clips_dir and not clips_dir.exists():
        for seg in segments:
            seg.notes.append(f"clips_dir missing: {clips_dir}")

    analysis = analyze_soundtrack(config, segments, write_cache=write_analysis_cache) if analyze else None
    timeline = Timeline(
        project=config.name or config.project_dir.name,
        template=str(config.template_path),
        soundtrack=str(config.soundtrack_path) if config.soundtrack_path else None,
        variables=dict(config.variables),
        analysis=analysis.to_dict() if analysis else {},
        segments=segments,
    )
    resolve_timing(timeline, analysis)
    return timeline
