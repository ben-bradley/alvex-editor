from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


_KNOWN_TOP = {
    "version", "name", "project", "template", "soundtrack", "soundtrack_id", "clips_dir", "clips",
    "overlays_dir", "overlays", "branding_dir", "branding", "output_dir", "timeline_path", "analysis_path",
    "sources_manifest", "manifest", "brief_path", "brief", "variables", "analysis", "timing", "ollama",
    "render", "workspace", "preset", "presets", "style_preset", "segment_overrides", "slot_overrides",
    "soundtrack_bpm", "beat_offset",
}
_KNOWN_RENDER = {"fontfile", "font", "fontsize", "fontcolor", "box", "boxcolor", "boxborderw", "title_x", "title_y", "text_align", "video_filters", "preview", "probe", "strict_duration", "width", "height", "fps", "crf", "preset", "video_codec", "audio_codec", "pixel_format"}
_KNOWN_TIMING = {"intro_fade_seconds", "intro_video_fade_seconds", "intro_audio_fade_seconds", "intro_title_after_seconds", "intro_title_duration_seconds", "outro_fade_seconds", "outro_video_fade_seconds", "outro_audio_fade_seconds", "outro_audio_fade_out_before_end_seconds", "outro_title_before_end_seconds"}
_KNOWN_ANALYSIS = {"backend", "refresh", "cut_points", "bpm", "offset", "duration", "beat_times", "beats", "min_distance", "library_dir", "library", "method"}
_KNOWN_OVERLAY = {"type", "text", "asset", "start", "end", "fade_in", "fade_out", "position"}


def _num(name: str, val: Any, res: ValidationResult, *, min_v: float | None = 0.0, allow_int: bool = True) -> None:
    if val is None:
        return
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        res.errors.append(f"{name} must be a number, got {type(val).__name__}")
        return
    if min_v is not None and float(val) < min_v:
        res.errors.append(f"{name} must be >= {min_v:g}, got {val}")


def validate_config(raw: dict[str, Any] | None) -> ValidationResult:
    res = ValidationResult()
    data = raw or {}
    if not isinstance(data, dict):
        res.errors.append("config must be a JSON object")
        return res
    for k in data.keys():
        if k not in _KNOWN_TOP:
            res.warnings.append(f"unknown top-level config key: {k}")
    if "template" in data and data["template"] is not None and not isinstance(data["template"], str):
        res.errors.append("template must be a string path/alias")
    for key in ("soundtrack", "clips_dir", "clips", "output_dir", "timeline_path", "analysis_path", "sources_manifest", "manifest", "workspace", "preset", "style_preset", "brief_path", "brief"):
        if key in data and data[key] is not None and not isinstance(data[key], str):
            res.errors.append(f"{key} must be a string path/value")
    render = data.get("render")
    if render is not None:
        if not isinstance(render, dict):
            res.errors.append("render must be an object")
        else:
            for k, v in render.items():
                if k not in _KNOWN_RENDER:
                    res.warnings.append(f"unknown render key: {k}")
                if k in {"title_x", "title_y", "text_align", "fontfile", "font", "fontcolor", "boxcolor", "video_codec", "audio_codec", "pixel_format", "preset"} and v is not None and not isinstance(v, str):
                    res.errors.append(f"render.{k} must be a string")
                if k in {"fontsize", "boxborderw", "width", "height", "fps", "crf"} and v is not None:
                    if isinstance(v, bool) or not isinstance(v, int):
                        res.errors.append(f"render.{k} must be an integer")
                if k in {"box", "preview", "probe", "strict_duration"} and v is not None and not isinstance(v, bool):
                    res.errors.append(f"render.{k} must be a boolean")
                if k == "video_filters" and v is not None and not isinstance(v, (list, str)):
                    res.errors.append("render.video_filters must be a list of filter strings or a comma-separated string")
                if k == "video_filters" and isinstance(v, list):
                    for i, item in enumerate(v):
                        if not isinstance(item, str):
                            res.errors.append(f"render.video_filters[{i}] must be a string")
            if render.get("text_align") is not None and str(render.get("text_align")) not in {"L", "C", "R", "M", "l", "c", "r", "m"}:
                res.warnings.append("render.text_align is typically L, C, or R")
    timing = data.get("timing")
    if timing is not None:
        if not isinstance(timing, dict):
            res.errors.append("timing must be an object")
        else:
            for k, v in timing.items():
                if k not in _KNOWN_TIMING:
                    res.warnings.append(f"unknown timing key: {k}")
                _num(f"timing.{k}", v, res, min_v=0.0)
    analysis = data.get("analysis")
    if analysis is not None:
        if not isinstance(analysis, dict):
            res.errors.append("analysis must be an object")
        else:
            for k, v in analysis.items():
                if k not in _KNOWN_ANALYSIS:
                    res.warnings.append(f"unknown analysis key: {k}")
            if analysis.get("backend") is not None and str(analysis.get("backend")) not in {"auto", "onsets", "librosa", "library", "curated"}:
                res.warnings.append("analysis.backend is typically auto, onsets, librosa, library, or curated")
            for nk in ("bpm", "offset", "duration", "min_distance"):
                _num(f"analysis.{nk}", analysis.get(nk), res, min_v=0.0)
            for lk in ("cut_points", "beat_times", "beats"):
                lv = analysis.get(lk)
                if lv is not None:
                    if not isinstance(lv, list):
                        res.errors.append(f"analysis.{lk} must be a list of numbers")
                    else:
                        for i, item in enumerate(lv):
                            _num(f"analysis.{lk}[{i}]", item, res, min_v=0.0)
    for ok in ("variables", "ollama"):
        if ok in data and data[ok] is not None and not isinstance(data[ok], dict):
            res.errors.append(f"{ok} must be an object")
    seg_ov = data.get("segment_overrides") or data.get("slot_overrides")
    if seg_ov is not None and not isinstance(seg_ov, dict):
        res.errors.append("segment_overrides/slot_overrides must be an object keyed by slot_id")
    return res


def merge_preset(base: dict[str, Any], preset: dict[str, Any] | None) -> dict[str, Any]:
    """Merge preset under project config: project wins. Deep-merges render/timing/variables/analysis/ollama."""
    if not preset:
        return dict(base)
    out = dict(preset)
    for k, v in base.items():
        if k in {"render", "timing", "variables", "analysis", "ollama"} and isinstance(v, dict) and isinstance(out.get(k), dict):
            merged = dict(out.get(k) or {})
            merged.update(v)
            out[k] = merged
        elif v is not None:
            out[k] = v
    return out
