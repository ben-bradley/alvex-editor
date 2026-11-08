from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
from typing import Any

from .align import align_project, write_manifest
from .audio import analyze_soundtrack
from .config import ProjectConfig, load_config
from .ollama import OllamaConfig, OllamaError
from .planner import build_plan, discover_clips
from .probe import find_ffmpeg, find_ffprobe, probe_media
from .renderer import RenderOptions, apply_manifest, build_render_plan, load_manifest, run_render
from .select import select_project
from .template import load_template
from .timeline import load_timeline


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def ok(command: str, **data: Any) -> dict[str, Any]:
    return {"ok": True, "command": command, **_jsonable(data)}


def fail(command: str, message: str, **data: Any) -> dict[str, Any]:
    return {"ok": False, "command": command, "error": message, **_jsonable(data)}


def _resolve_config(project: str | Path | None) -> ProjectConfig | None:
    return load_config(project) if project else None


def project_status(*, project: str | Path) -> dict[str, Any]:
    config = load_config(project)
    res: dict[str, Any] = {
        "project": config.name or config.project_dir.name,
        "config": str(config.config_path),
        "project_dir": str(config.project_dir),
        "template": {"path": str(config.template_path), "exists": config.template_path.exists()},
        "soundtrack": {"path": str(config.soundtrack_path) if config.soundtrack_path else None, "exists": bool(config.soundtrack_path and config.soundtrack_path.exists())},
        "clips_dir": {"path": str(config.clips_path) if config.clips_path else None, "exists": bool(config.clips_path and config.clips_path.exists())},
        "analysis_path": str(config.resolved_analysis_path),
        "timeline_path": str(config.resolved_timeline_path),
        "sources_manifest": str(config.resolved_sources_manifest) if config.resolved_sources_manifest else None,
        "ffmpeg": find_ffmpeg(),
        "ffprobe": find_ffprobe(),
        "ollama": {"configured": bool(config.ollama), "host": (config.ollama or {}).get("host"), "model": (config.ollama or {}).get("model"), "vision_model": (config.ollama or {}).get("vision_model")},
    }
    if config.clips_path and config.clips_path.exists():
        res["clips_count"] = len(discover_clips(config.clips_path))
    if config.resolved_timeline_path.exists():
        try:
            tl = load_timeline(config.resolved_timeline_path)
            mapped = sum(1 for s in tl.segments if s.source.status == "mapped")
            res["timeline"] = {"segments": len(tl.segments), "mapped": mapped, "unmapped": len(tl.segments) - mapped, "analysis_method": (tl.analysis or {}).get("method")}
        except Exception as e:
            res["timeline_error"] = str(e)
    if config.resolved_analysis_path.exists():
        try:
            data = json.loads(config.resolved_analysis_path.read_text(encoding="utf-8"))
            res["analysis_cache"] = {"method": data.get("method"), "beats": len(data.get("beat_times") or []), "cut_points": len(data.get("cut_points") or []), "duration": data.get("duration")}
        except Exception as e:
            res["analysis_cache_error"] = str(e)
    return ok("status", status=res)


def template_info(*, project: str | Path, as_json: bool = True) -> dict[str, Any]:
    config = load_config(project)
    template = load_template(config.template_path)
    data = template.to_dict()
    slots = []
    for s in template.edit_slots:
        slots.append({
            "index": len(slots) + 1,
            "name": s.name,
            "slot_id": s.slot_id,
            "optional": s.optional,
            "min_duration": s.min_duration,
            "max_duration": s.max_duration,
            "target_duration": s.target_duration,
        })
    return ok("template", template_path=str(template.path), title=template.title, slot_count=len(template.edit_slots), slots=slots, data=data)


def analyze(*, project: str | Path, output: str | Path | None = None, backend: str | None = None, refresh: bool = False, write_cache: bool = True) -> dict[str, Any]:
    config = load_config(project)
    template = load_template(config.template_path)
    analysis = analyze_soundtrack(config, template.edit_slots, write_cache=write_cache, backend=backend, refresh=refresh)
    if analysis is None:
        return fail("analyze", "No soundtrack analysis available. Configure analysis.bpm/cut_points or provide a soundtrack.")
    out = Path(output).expanduser().resolve() if output else config.resolved_analysis_path
    if output:
        analysis.write(out)
    elif write_cache and (analysis.beat_times or analysis.cut_points or analysis.bpm):
        out = config.resolved_analysis_path
    return ok("analyze", output=str(out), method=analysis.method, bpm=analysis.bpm, duration=analysis.duration, beats=len(analysis.beat_times), cut_points=len(analysis.cut_points), notes=analysis.notes, analysis=analysis.to_dict())


def plan(*, project: str | Path, output: str | Path | None = None, map_clips: bool = False, run_analyze: bool = True) -> dict[str, Any]:
    config = load_config(project)
    timeline = build_plan(config, map_clips=map_clips, analyze=run_analyze)
    out = Path(output).expanduser().resolve() if output else config.resolved_timeline_path
    timeline.write(out)
    mapped = sum(1 for s in timeline.segments if s.source.status == "mapped")
    total = len(timeline.segments)
    resolved = sum(1 for s in timeline.segments if s.resolved_duration is not None)
    return ok(
        "plan",
        output=str(out),
        template=str(config.template_path),
        segments_total=total,
        segments_mapped=mapped,
        segments_unmapped=total - mapped,
        segments_timed=resolved,
        analysis=timeline.analysis,
        timeline_path=str(out),
    )


def _render_config(config: ProjectConfig | None, *, preview: bool = False, no_probe: bool = False, strict_duration: bool = False) -> RenderOptions:
    render_cfg = (config.raw.get("render") if config and isinstance(config.raw.get("render"), dict) else {}) or {}
    if preview:
        render_cfg = {**render_cfg, "preview": True}
    if no_probe:
        render_cfg = {**render_cfg, "probe": False}
    if strict_duration:
        render_cfg = {**render_cfg, "strict_duration": True}
    return RenderOptions.from_dict(render_cfg)


def render(
    *,
    project: str | Path | None = None,
    timeline: str | Path | None = None,
    manifest: str | Path | None = None,
    output: str | Path | None = None,
    soundtrack: str | Path | None = None,
    preview: bool = False,
    dry_run: bool = False,
    print_filter: bool = False,
    allow_unmapped: bool = False,
    no_plan: bool = False,
    no_probe: bool = False,
    strict_duration: bool = False,
) -> dict[str, Any]:
    config = load_config(project) if project else None
    if timeline:
        timeline_path = Path(timeline).expanduser().resolve()
    elif config:
        timeline_path = config.resolved_timeline_path
        if not timeline_path.exists() and not no_plan:
            tl = build_plan(config, map_clips=False)
            timeline_path = tl.write(timeline_path)
    else:
        return fail("render", "Provide --project or --timeline")

    options = _render_config(config, preview=preview, no_probe=no_probe, strict_duration=strict_duration)
    manifest_path = manifest
    if not manifest_path and config:
        manifest_path = config.raw.get("sources_manifest") or config.raw.get("manifest")
    if manifest_path and config and not Path(str(manifest_path)).is_absolute():
        manifest_path = str((config.project_dir / str(manifest_path)).resolve())

    if output:
        out_path = Path(output).expanduser().resolve()
    elif config:
        out_path = config.output_path / ("preview.mp4" if preview else "final.mp4")
    else:
        out_path = Path("output.mp4").resolve()

    tl = load_timeline(timeline_path)
    if manifest_path:
        m = load_manifest(manifest_path)
        apply_manifest(tl, m, base_dir=Path(str(manifest_path)).resolve().parent)
    plan = build_render_plan(
        tl,
        out_path,
        options=options,
        allow_unmapped=allow_unmapped,
        soundtrack=soundtrack,
        require_files=not (dry_run or print_filter),
        probe_inputs=options.probe,
    )
    base_res: dict[str, Any] = {
        "output": str(plan.output),
        "inputs": [str(p) for p in plan.inputs],
        "warnings": plan.warnings,
        "probe_count": len([k for k, v in (plan.probe or {}).items() if v.get("duration") is not None]),
        "filter_complex": plan.filter_complex,
        "script": plan.script,
        "ffmpeg_command": plan.command,
    }
    if dry_run or print_filter:
        return ok("render", dry_run=True, print_filter=bool(print_filter), **base_res)
    result = run_render(plan)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        tail = "\n".join(detail.splitlines()[-20:]) if detail else "no output"
        return fail("render", f"ffmpeg failed (exit {result.returncode}) for {plan.output}: {tail}", **base_res)
    return ok("render", dry_run=False, rendered=True, **base_res)


def _ollama_from_args(config: ProjectConfig | None, *, host: str | None = None, model: str | None = None, vision_model: str | None = None) -> OllamaConfig:
    raw = dict(config.ollama) if config and config.ollama else {}
    if host:
        raw["host"] = host
    if model:
        raw["model"] = model
    if vision_model:
        raw["vision_model"] = vision_model
    return OllamaConfig.from_dict(raw)


def _resolve_timeline_path(config: ProjectConfig | None, timeline: str | Path | None) -> Path:
    if timeline:
        return Path(timeline).expanduser().resolve()
    if config:
        tp = config.resolved_timeline_path
        if not tp.exists():
            tl = build_plan(config, map_clips=False)
            tp = tl.write(tp)
        return tp
    raise ValueError("Provide --project or --timeline")


def _resolve_manifest_target(config: ProjectConfig | None, manifest: str | Path | None) -> Path | None:
    if not manifest and config:
        manifest = config.sources_manifest or config.raw.get("sources_manifest") or config.raw.get("manifest")
    if not manifest:
        return None
    p = Path(str(manifest)).expanduser()
    if config and not p.is_absolute():
        p = (config.project_dir / p).resolve()
    return p


def suggest_mapping(
    *,
    project: str | Path | None = None,
    timeline: str | Path | None = None,
    clips: str | Path | None = None,
    host: str | None = None,
    model: str | None = None,
    vision_model: str | None = None,
    vision: bool = False,
    output: str | Path | None = None,
    manifest: str | Path | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    config = load_config(project) if project else None
    timeline_path = _resolve_timeline_path(config, timeline)
    if clips:
        clips_dir = Path(clips).expanduser().resolve()
    elif config and config.clips_path:
        clips_dir = config.clips_path
    else:
        return fail("align", "Provide --clips or set clips_dir in the project config")
    ollama = _ollama_from_args(config, host=host, model=model, vision_model=vision_model)
    manifest_data, clip_infos = align_project(
        timeline_path,
        clips_dir,
        ollama=ollama,
        model=ollama.model,
        vision_model=ollama.vision_model,
        use_vision=vision,
    )
    base = config.project_dir if config else timeline_path.parent
    suggested = Path(output).expanduser().resolve() if output else (base / "sources.suggested.yaml")
    write_manifest(manifest_data, suggested)
    res: dict[str, Any] = {
        "suggested_manifest": str(suggested),
        "clips": len(clip_infos),
        "mapped": len((manifest_data.get("sources") or {})),
        "unmapped_slots": manifest_data.get("unmapped_slots") or [],
        "sources": manifest_data.get("sources") or {},
        "applied": False,
        "requires_confirmation": True,
    }
    if apply:
        target = _resolve_manifest_target(config, manifest) or (base / "sources.yaml")
        write_manifest(manifest_data, target)
        res["applied"] = True
        res["applied_manifest"] = str(target)
        res["requires_confirmation"] = False
    return ok("align", **res)


def suggest_inpoints(
    *,
    project: str | Path | None = None,
    timeline: str | Path | None = None,
    manifest: str | Path | None = None,
    host: str | None = None,
    model: str | None = None,
    vision_model: str | None = None,
    vision: bool = False,
    candidates: int = 5,
    slots: list[str] | None = None,
    output: str | Path | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    config = load_config(project) if project else None
    timeline_path = _resolve_timeline_path(config, timeline)
    manifest_path = _resolve_manifest_target(config, manifest)
    if manifest_path and not manifest_path.exists():
        manifest_path = None
    ollama = _ollama_from_args(config, host=host, model=model, vision_model=vision_model)
    manifest_data, selections = select_project(
        timeline_path,
        manifest_path=str(manifest_path) if manifest_path else None,
        ollama=ollama,
        model=ollama.model or ollama.vision_model,
        use_vision=vision,
        candidate_count=candidates,
        slots=slots,
    )
    base = config.project_dir if config else timeline_path.parent
    suggested = Path(output).expanduser().resolve() if output else (base / "sources.selected.suggested.yaml")
    write_manifest(manifest_data, suggested)
    res: dict[str, Any] = {
        "suggested_manifest": str(suggested),
        "selections": selections,
        "applied": False,
        "requires_confirmation": True,
    }
    if apply:
        target = _resolve_manifest_target(config, manifest) or (base / "sources.yaml")
        write_manifest(manifest_data, target)
        res["applied"] = True
        res["applied_manifest"] = str(target)
        res["requires_confirmation"] = False
    return ok("select", **res)


def apply_manifest_file(*, project: str | Path | None = None, suggested: str | Path, target: str | Path | None = None) -> dict[str, Any]:
    config = load_config(project) if project else None
    src = Path(suggested).expanduser().resolve()
    if not src.exists():
        return fail("apply_manifest", f"Suggested manifest not found: {src}")
    data = load_manifest(src)
    # preserve non-source metadata if present
    raw = None
    try:
        import yaml
        raw = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
    except Exception:
        raw = {"sources": data}
    tgt = Path(target).expanduser().resolve() if target else (_resolve_manifest_target(config, None) or ((config.project_dir if config else src.parent) / "sources.yaml"))
    write_manifest(raw if isinstance(raw, dict) else {"sources": data}, tgt)
    return ok("apply_manifest", suggested=str(src), applied_manifest=str(tgt), applied=True)
