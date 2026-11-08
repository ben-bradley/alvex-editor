from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any, Iterable

import yaml

from .probe import find_ffmpeg, find_ffprobe, probe_media
from .timeline import Segment, Timeline, load_timeline


@dataclass
class RenderOptions:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    crf: int = 18
    preset: str = "medium"
    pixel_format: str = "yuv420p"
    fontfile: str | None = None
    font: str = "Sans"
    fontsize: int = 48
    fontcolor: str = "white"
    box: bool = False
    boxcolor: str = "black@0.4"
    boxborderw: int = 12
    # drawtext position expressions (ffmpeg); default centered
    title_x: str = "(w-text_w)/2"
    title_y: str = "(h-text_h)/2"
    preview: bool = False
    probe: bool = True
    strict_duration: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RenderOptions":
        data = data or {}
        opts = cls()
        for k, v in data.items():
            if hasattr(opts, k) and v is not None:
                setattr(opts, k, v)
        if opts.preview:
            opts.width = min(opts.width, 1280)
            opts.height = min(opts.height, 720)
            opts.crf = max(opts.crf, 23)
            opts.preset = "veryfast"
        return opts


@dataclass
class RenderPlan:
    timeline: Timeline
    inputs: list[Path]
    filter_complex: str
    maps: list[str]
    output: Path
    options: RenderOptions
    command: list[str]
    warnings: list[str] = field(default_factory=list)
    probe: dict[str, dict[str, Any]] = field(default_factory=dict)
    script: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "inputs": [str(p) for p in self.inputs],
            "filter_complex": self.filter_complex,
            "maps": self.maps,
            "output": str(self.output),
            "command": self.command,
            "warnings": self.warnings,
            "probe": self.probe,
        }


def _sub_vars(text: str | None, variables: dict[str, Any]) -> str | None:
    if text is None:
        return None
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return str(variables.get(key, m.group(0)))
    return re.sub(r"\$\{([^}]+)\}", repl, text)


def load_manifest(path: str | Path) -> dict[str, dict[str, Any]]:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Manifest must be a mapping: {path}")
    sources = data.get("sources", data)
    if not isinstance(sources, dict):
        raise ValueError(f"Manifest sources must be a mapping: {path}")
    out: dict[str, dict[str, Any]] = {}
    for slot_id, value in sources.items():
        if isinstance(value, str):
            out[str(slot_id)] = {"path": value}
        elif isinstance(value, dict):
            item = dict(value)
            if "path" not in item and "file" in item:
                item["path"] = item["file"]
            out[str(slot_id)] = item
        else:
            raise ValueError(f"Manifest entry for {slot_id} must be a path or mapping")
    return out


def apply_manifest(timeline: Timeline, manifest: dict[str, dict[str, Any]], *, base_dir: Path | None = None) -> None:
    base_dir = base_dir or Path.cwd()
    for seg in timeline.segments:
        m = manifest.get(seg.slot_id) or manifest.get(seg.name)
        if not m or not m.get("path"):
            continue
        p = Path(str(m["path"])).expanduser()
        if not p.is_absolute():
            p = (base_dir / p).resolve()
        seg.source.path = str(p)
        seg.source.status = "mapped"
        if "in_point" in m and m["in_point"] is not None:
            seg.source.in_point = float(m["in_point"])
        if "out_point" in m and m["out_point"] is not None:
            seg.source.out_point = float(m["out_point"])


def renderable_segments(timeline: Timeline, *, allow_unmapped: bool = False) -> list[Segment]:
    segs: list[Segment] = []
    for seg in timeline.segments:
        if seg.optional and seg.source.status != "mapped":
            continue
        if seg.source.status != "mapped" or not seg.source.path:
            if allow_unmapped:
                continue
            raise ValueError(f"Segment '{seg.slot_id}' ({seg.name}) is not mapped to a source. Provide a manifest or map clips.")
        segs.append(seg)
    if not segs:
        raise ValueError("No renderable (mapped) segments found")
    return segs


def _resolve_time(value: float | str | None, seg_dur: float, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    m = re.fullmatch(r"end(?:\s*-\s*(\d+(?:\.\d+)?))?", s, re.I)
    if m:
        off = float(m.group(1) or 0)
        return max(0.0, seg_dur - off)
    try:
        return float(s)
    except ValueError:
        return default


def _default_fontfile() -> str | None:
    candidates: list[Path] = []
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        candidates = [
            windir / "Fonts" / "arial.ttf",
            windir / "Fonts" / "segoeui.ttf",
            windir / "Fonts" / "calibri.ttf",
        ]
    elif sys.platform == "darwin":
        candidates = [
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/Library/Fonts/Arial.ttf"),
            Path("/System/Library/Fonts/Helvetica.ttc"),
        ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def _ff_escape_text(text: str) -> str:
    # ffmpeg drawtext text value escaping (for use inside text='...').
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", r"\\n")  # drawtext line break (escaped for filter graph)
    text = text.replace("\\", "\\\\") if False else text  # backslashes handled minimally
    # escape filter-special chars (but preserve \\n we just inserted)
    text = text.replace(":", "\\:")
    text = text.replace("'", "\u2019")  # normalize apostrophes for simplicity
    text = text.replace("%", "\\%")
    text = text.replace("[", "\\[")
    text = text.replace("]", "\\]")
    return text


def _ff_path(path: Path) -> str:
    # drawtext fontfile/filter paths use escaped colons/backslashes.
    return str(path).replace("\\", "/").replace(":", "\\:")


def _build_video_chain(seg: Segment, idx: int, input_index: int, seg_dur: float, in_pt: float, out_pt: float, opts: RenderOptions, variables: dict[str, Any]) -> list[str]:
    filters = [
        f"[{input_index}:v]trim=start={in_pt:.4f}:end={out_pt:.4f}",
        "setpts=PTS-STARTPTS",
        f"scale={opts.width}:{opts.height}:force_original_aspect_ratio=decrease",
        f"pad={opts.width}:{opts.height}:(ow-iw)/2:(oh-ih)/2:color=black",
        f"fps={opts.fps}",
        f"format={opts.pixel_format}",
    ]
    for eff in seg.video_effects or []:
        if not isinstance(eff, dict):
            continue
        etype = eff.get("type")
        if etype == "fade_in":
            d = float(eff.get("duration") or 0)
            if d > 0:
                filters.append(f"fade=t=in:st=0:d={d:.4f}")
        elif etype == "fade_out":
            d = float(eff.get("duration") or 0)
            if d > 0:
                st = _resolve_time(eff.get("start"), seg_dur, max(0.0, seg_dur - d))
                if eff.get("anchor") == "end" or eff.get("start") is None:
                    st = max(0.0, seg_dur - d)
                filters.append(f"fade=t=out:st={st:.4f}:d={d:.4f}")
    for ov in seg.overlays or []:
        if ov.type not in ("title", "text") or not ov.text:
            continue
        text = _sub_vars(ov.text, variables) or ""
        text = _ff_escape_text(text)
        st = _resolve_time(ov.start, seg_dur, 0.0)
        en = _resolve_time(ov.end, seg_dur, seg_dur)
        if en <= st:
            en = seg_dur
        parts = ["drawtext="]
        fontfile = opts.fontfile
        if fontfile:
            fontfile = os.path.expanduser(str(fontfile))
        elif sys.platform != "linux":
            fontfile = _default_fontfile()
        if fontfile:
            parts.append(f"fontfile={_ff_path(Path(fontfile))}")
        else:
            parts.append(f"font={_ff_escape_text(opts.font)}")
        parts.append(f":text='{text}'")
        parts.append(f":fontsize={opts.fontsize}")
        parts.append(f":fontcolor={opts.fontcolor}")
        parts.append(f":x={opts.title_x}:y={opts.title_y}")
        if "\\n" in text:
            parts.append(":line_spacing=8")
        if opts.box:
            parts.append(f":box=1:boxcolor={opts.boxcolor}:boxborderw={opts.boxborderw}")
        # escape commas inside enable expression for filter graph
        parts.append(f":enable='between(t\\,{st:.4f}\\,{en:.4f})'")
        filters.append("".join(parts))
    chain = ",".join(filters) + f"[v{idx}]"
    return [chain]


def _collect_audio_fades(segs: list[Segment], render_positions: list[tuple[float, float]] | None = None) -> list[str]:
    filters: list[str] = []
    for i, seg in enumerate(segs):
        if render_positions and i < len(render_positions):
            tin, tout = render_positions[i]
        else:
            dur = seg.resolved_duration or seg.target_duration or 0.0
            tin = seg.timeline_in or 0.0
            tout = seg.timeline_out or (tin + dur)
        if seg.audio.fade_in and seg.audio.fade_in > 0:
            filters.append(f"afade=t=in:st={float(tin):.4f}:d={float(seg.audio.fade_in):.4f}")
        if seg.audio.fade_out and seg.audio.fade_out > 0:
            d = float(seg.audio.fade_out)
            st = max(0.0, float(tout) - d)
            filters.append(f"afade=t=out:st={st:.4f}:d={d:.4f}")
    return filters


def _segment_duration(seg: Segment) -> float:
    dur = seg.resolved_duration or seg.target_duration
    if not dur:
        if seg.min_duration and seg.max_duration:
            dur = (seg.min_duration + seg.max_duration) / 2
        else:
            dur = 9.0
    return float(dur)


def _probe_path(path: Path, cache: dict[str, Any], *, enabled: bool) -> Any:
    key = str(path)
    if key in cache:
        return cache[key]
    if not enabled or not find_ffprobe():
        cache[key] = None
        return None
    info = probe_media(path)
    cache[key] = info
    return info


def build_render_plan(
    timeline: Timeline,
    output: str | Path,
    *,
    options: RenderOptions | None = None,
    allow_unmapped: bool = False,
    soundtrack: str | Path | None = None,
    require_files: bool = False,
    probe_inputs: bool | None = None,
) -> RenderPlan:
    opts = options or RenderOptions()
    probe_enabled = opts.probe if probe_inputs is None else probe_inputs
    warnings: list[str] = []
    probe_results: dict[str, dict[str, Any]] = {}
    probe_cache: dict[str, Any] = {}
    segs = renderable_segments(timeline, allow_unmapped=allow_unmapped)

    snd = Path(soundtrack) if soundtrack else (Path(timeline.soundtrack) if timeline.soundtrack else None)
    inputs: list[Path] = []
    filter_parts: list[str] = []
    actual_durations: list[float] = []
    render_positions: list[tuple[float, float]] = []
    cursor = 0.0

    for i, seg in enumerate(segs):
        assert seg.source.path
        src_path = Path(seg.source.path)
        inputs.append(src_path)
        if require_files and not src_path.exists():
            raise FileNotFoundError(f"Source for segment '{seg.slot_id}' not found: {src_path}")
        want_dur = _segment_duration(seg)
        if not seg.resolved_duration and not seg.target_duration:
            warnings.append(f"{seg.slot_id}: missing resolved_duration, using {want_dur:.4g}s")
        in_pt = float(seg.source.in_point or 0.0)
        out_pt = float(seg.source.out_point) if seg.source.out_point is not None else (in_pt + want_dur)
        seg_dur = max(0.0, out_pt - in_pt)
        info = _probe_path(src_path, probe_cache, enabled=probe_enabled)
        if info is not None:
            probe_results[str(src_path)] = info.to_dict()
            if info.error and info.exists:
                warnings.append(f"{seg.slot_id}: probe: {info.error}")
            elif not info.exists:
                msg = f"{seg.slot_id}: source missing: {src_path}"
                if require_files:
                    raise FileNotFoundError(msg)
                warnings.append(msg)
            if info.duration is not None:
                src_dur = float(info.duration)
                if in_pt > src_dur:
                    warnings.append(f"{seg.slot_id}: in_point {in_pt:.4g}s beyond source duration {src_dur:.4g}s; clamping")
                    in_pt = max(0.0, src_dur - 0.001)
                max_end = max(in_pt, src_dur)
                requested_end = in_pt + want_dur
                clamped_end = min(requested_end, max_end)
                if clamped_end < requested_end - 1e-6:
                    msg = f"{seg.slot_id}: source provides {clamped_end - in_pt:.4g}s from in_point, need {want_dur:.4g}s (resolved) — clamped"
                    if opts.strict_duration:
                        raise ValueError(msg)
                    warnings.append(msg)
                out_pt = clamped_end
                seg_dur = max(0.0, out_pt - in_pt)
        if seg_dur <= 0:
            seg_dur = 0.1
            out_pt = in_pt + seg_dur
            warnings.append(f"{seg.slot_id}: zero-length trim; using {seg_dur}s")
        actual_durations.append(seg_dur)
        render_positions.append((round(cursor, 4), round(cursor + seg_dur, 4)))
        cursor += seg_dur
        filter_parts.extend(_build_video_chain(seg, i, i, seg_dur, in_pt, out_pt, opts, timeline.variables or {}))

    concat_in = "".join(f"[v{i}]" for i in range(len(segs)))
    filter_parts.append(f"{concat_in}concat=n={len(segs)}:v=1:a=0[vout]")

    maps = ["-map", "[vout]"]
    if snd:
        inputs.append(snd)
        if require_files and not snd.exists():
            raise FileNotFoundError(f"Soundtrack not found: {snd}")
        snd_info = _probe_path(snd, probe_cache, enabled=probe_enabled)
        if snd_info is not None:
            probe_results[str(snd)] = snd_info.to_dict()
            if not snd_info.exists and require_files:
                raise FileNotFoundError(f"Soundtrack not found: {snd}")
            elif not snd_info.exists:
                warnings.append(f"soundtrack missing: {snd}")
        a_idx = len(segs)
        # Render-local total: matches the actual concatenated video duration (robust when optional segments are skipped).
        total = round(sum(actual_durations), 4)
        achain = [f"[{a_idx}:a]atrim=0:{float(total):.4f}", "asetpts=PTS-STARTPTS"]
        achain.extend(_collect_audio_fades(segs, render_positions))
        audio_chain = ",".join(achain) + "[aout]"
        filter_parts.append(audio_chain)
        maps += ["-map", "[aout]"]

    filter_complex = ";".join(filter_parts)
    out_path = Path(output)
    cmd: list[str] = ["ffmpeg", "-y"]
    for inp in inputs:
        cmd += ["-i", str(inp)]
    cmd += ["-filter_complex", filter_complex]
    cmd += maps
    if snd:
        cmd += ["-c:a", opts.audio_codec]
    cmd += ["-c:v", opts.video_codec, "-crf", str(opts.crf), "-preset", opts.preset, "-pix_fmt", opts.pixel_format, str(out_path)]

    script = "#!/usr/bin/env bash\nset -euo pipefail\n" + " ".join(shlex.quote(c) for c in cmd) + "\n"
    return RenderPlan(timeline=timeline, inputs=inputs, filter_complex=filter_complex, maps=maps, output=out_path, options=opts, command=cmd, warnings=warnings, probe=probe_results, script=script)


# ffmpeg resolution uses .probe.find_ffmpeg (PATH, env, snap-aware).


def run_render(plan: RenderPlan) -> subprocess.CompletedProcess[str]:
    exe = find_ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg not found. Install FFmpeg and ensure it is on PATH to render.")
    plan.output.parent.mkdir(parents=True, exist_ok=True)
    # Replace command[0] with resolved exe for robustness in odd PATH/snap cases.
    cmd = [exe] + plan.command[1:]
    return subprocess.run(cmd, check=False, text=True, capture_output=True)


def render_timeline(
    timeline_path: str | Path,
    output: str | Path,
    *,
    manifest_path: str | Path | None = None,
    soundtrack: str | Path | None = None,
    options: RenderOptions | None = None,
    allow_unmapped: bool = False,
    dry_run: bool = False,
    print_filter: bool = False,
) -> RenderPlan:
    timeline = load_timeline(timeline_path)
    if manifest_path:
        manifest = load_manifest(manifest_path)
        apply_manifest(timeline, manifest, base_dir=Path(manifest_path).resolve().parent)
    plan = build_render_plan(
        timeline,
        output,
        options=options,
        allow_unmapped=allow_unmapped,
        soundtrack=soundtrack,
        require_files=not (dry_run or print_filter),
        probe_inputs=(options or RenderOptions()).probe,
    )
    if print_filter:
        print(plan.filter_complex)
    if dry_run or print_filter:
        print(plan.script)
        for w in plan.warnings:
            print(f"warning: {w}")
        return plan
    result = run_render(plan)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        tail = "\n".join(detail.splitlines()[-20:]) if detail else "no output"
        raise RuntimeError(f"ffmpeg failed (exit {result.returncode}) for {plan.output}:\n{tail}")
    if plan.warnings:
        for w in plan.warnings:
            print(f"warning: {w}")
    return plan
