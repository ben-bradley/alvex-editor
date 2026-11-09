from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Iterable

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


def _timing_num(timing: dict[str, Any], key: str) -> float | None:
    if key not in timing or timing[key] is None:
        return None
    try:
        val = float(timing[key])
    except (TypeError, ValueError):
        return None
    return val if val >= 0 else None


def _apply_timing_overrides(segments: list[Segment], timing: dict[str, Any] | None) -> None:
    if not timing or not segments:
        return

    intro_fade = _timing_num(timing, "intro_fade_seconds")
    intro_video_fade = _timing_num(timing, "intro_video_fade_seconds")
    intro_audio_fade = _timing_num(timing, "intro_audio_fade_seconds")
    intro_title_after = _timing_num(timing, "intro_title_after_seconds")
    intro_title_dur = _timing_num(timing, "intro_title_duration_seconds")
    outro_fade = _timing_num(timing, "outro_fade_seconds")
    outro_video_fade = _timing_num(timing, "outro_video_fade_seconds")
    outro_audio_fade = _timing_num(timing, "outro_audio_fade_seconds")
    outro_audio_fade_before_end = _timing_num(timing, "outro_audio_fade_out_before_end_seconds")
    outro_title_before = _timing_num(timing, "outro_title_before_end_seconds")

    intro = segments[0]
    ivf = intro_video_fade if intro_video_fade is not None else intro_fade
    iaf = intro_audio_fade if intro_audio_fade is not None else intro_fade
    if ivf is not None:
        for eff in intro.video_effects or []:
            if isinstance(eff, dict) and eff.get("type") == "fade_in":
                eff["duration"] = ivf
    if iaf is not None:
        intro.audio.fade_in = iaf
    if intro_title_after is not None or intro_title_dur is not None:
        for ov in intro.overlays or []:
            if ov.type != "title" or ov.text != "${address}":
                continue
            if isinstance(ov.start, (int, float)) or isinstance(ov.end, (int, float)):
                start = intro_title_after if intro_title_after is not None else (float(ov.start) if isinstance(ov.start, (int, float)) else 0.0)
                if intro_title_dur is not None:
                    end = start + intro_title_dur
                elif isinstance(ov.end, (int, float)) and isinstance(ov.start, (int, float)):
                    end = start + (float(ov.end) - float(ov.start))
                else:
                    end = ov.end
                ov.start = start
                ov.end = end
                break

    outro = segments[-1]
    ovf = outro_video_fade if outro_video_fade is not None else outro_fade
    oaf = outro_audio_fade if outro_audio_fade is not None else outro_fade
    if ovf is not None:
        for eff in outro.video_effects or []:
            if isinstance(eff, dict) and eff.get("type") == "fade_out" and (eff.get("anchor") == "end" or eff.get("start") is None):
                eff["duration"] = ovf
    if oaf is not None:
        outro.audio.fade_out = oaf
    if outro_audio_fade_before_end is not None:
        outro.audio.fade_out_end_before = outro_audio_fade_before_end
    if outro_title_before is not None:
        for ov in outro.overlays or []:
            if ov.type != "title" or ov.text != "${address}":
                continue
            s = ov.start
            if (isinstance(s, str) and s.strip().lower().startswith("end")) or ov.end == "end":
                ov.start = f"end-{outro_title_before:g}"
                ov.end = "end"
                break




def _apply_segment_overrides(segments: list[Segment], overrides: dict[str, Any] | None) -> None:
    if not overrides or not isinstance(overrides, dict):
        return
    by_id = {s.slot_id: s for s in segments}
    for slot_id, ov in overrides.items():
        if not isinstance(ov, dict):
            continue
        seg = by_id.get(str(slot_id))
        if not seg:
            continue
        src = ov.get("source") if isinstance(ov.get("source"), dict) else {}
        if "path" in ov and ov.get("path") is not None:
            seg.source.path = str(ov.get("path"))
            seg.source.status = "mapped"
        if "in_point" in ov and ov.get("in_point") is not None:
            try: seg.source.in_point = float(ov["in_point"])
            except Exception: pass
        if "out_point" in ov and ov.get("out_point") is not None:
            try: seg.source.out_point = float(ov["out_point"])
            except Exception: pass
        for k in ("in_point", "out_point", "path"):
            if k in src and src.get(k) is not None:
                if k == "path":
                    seg.source.path = str(src["path"]); seg.source.status = "mapped"
                else:
                    try: setattr(seg.source, k, float(src[k]))
                    except Exception: pass
        if "optional" in ov and isinstance(ov["optional"], bool):
            seg.optional = ov["optional"]
        for k in ("target_duration", "min_duration", "max_duration"):
            if k in ov and ov[k] is not None:
                try: setattr(seg, k, float(ov[k]))
                except Exception: pass


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

    _apply_timing_overrides(segments, getattr(config, "timing", None))
    _apply_segment_overrides(segments, getattr(config, "segment_overrides", None))

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
