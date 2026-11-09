from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import re
from typing import Any

from .align import align_project, write_manifest
from .structured import dump_structured, load_structured
from .audio import analyze_soundtrack, load_analysis
from . import cutpoints as _cutpoints
from .config import ProjectConfig, load_config
from .ollama import OllamaConfig, OllamaError
from .planner import build_plan, discover_clips
from .policy import ensure_not_inside_repo
from .probe import find_ffmpeg, find_ffprobe, probe_media
import shutil as _shutil
import sys as _sys
from .registry import (
    import_soundtrack,
    list_soundtracks,
    list_templates,
    load_curated_cut_points,
    resolve_soundtrack,
    resolve_template,
    save_curated_cut_points,
    slugify,
)
from .renderer import RenderOptions, apply_manifest, build_render_plan, load_manifest, run_render
from .select import select_project
from .template import load_template
from .timeline import load_timeline
from .workspace import load_workspace, save_workspace_config


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


def _ffmpeg_resolution() -> dict[str, Any]:
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    hints: list[str] = []
    if not ffmpeg or not ffprobe:
        hints.append("Install ffmpeg and ensure it is on PATH, or set FFMPEG/FFPROBE (or ALVEX_FFMPEG/ALVEX_FFPROBE) to the full executable paths.")
        if _sys.platform.startswith(("win", "cygwin")):
            hints.append("On Windows, Alvex also checks common WinGet install locations (e.g. Gyan.FFmpeg). If installed but not found, set FFMPEG/FFPROBE explicitly.")
    return {
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "ffmpeg_found": bool(ffmpeg),
        "ffprobe_found": bool(ffprobe),
        "path_ffmpeg": _shutil.which("ffmpeg"),
        "path_ffprobe": _shutil.which("ffprobe"),
        "hints": hints,
    }


def doctor(*, project: str | Path | None = None) -> dict[str, Any]:
    ff = _ffmpeg_resolution()
    res: dict[str, Any] = {"ffmpeg": ff, "python": _sys.version.split()[0], "platform": _sys.platform}
    issues: list[str] = []
    notes: list[str] = []
    if not ff["ffmpeg_found"]:
        issues.append("ffmpeg not found")
    if not ff["ffprobe_found"]:
        issues.append("ffprobe not found")
    if project:
        try:
            config = load_config(project)
            st = project_status(project=project)
            status = (st.get("status") or {}) if st.get("ok") else {}
            res["project"] = status
            tpl = status.get("template") or {}
            snd = status.get("soundtrack") or {}
            clips = status.get("clips_dir") or {}
            if tpl.get("path") and not tpl.get("exists"):
                issues.append(f"template missing: {tpl.get('path')}")
            if snd.get("path") and not snd.get("exists"):
                issues.append(f"soundtrack missing: {snd.get('path')}")
            if clips.get("path") and not clips.get("exists"):
                issues.append(f"clips_dir missing: {clips.get('path')}")
            sm = status.get("sources_manifest")
            sm_path = sm.get("path") if isinstance(sm, dict) else sm
            sm_exists = sm.get("exists") if isinstance(sm, dict) else (Path(sm_path).exists() if sm_path else False)
            if sm_path and not sm_exists:
                notes.append(f"sources manifest not found (optional until clips are mapped/aligned; timeline mappings may be used): {sm_path}")
            tl = status.get("timeline") or {}
            if tl and snd.get("path") and tl.get("soundtrack") and str(tl.get("soundtrack")) != str(snd.get("path")):
                notes.append("timeline soundtrack differs from project config; re-plan to refresh.")
            _ = config
        except Exception as e:
            issues.append(f"project check failed: {e}")
    if notes:
        res["notes"] = notes
    res["ok_doctor"] = not any("ffmpeg" in i or "ffprobe" in i or "project check failed" in i for i in issues)
    res["issues"] = issues
    res["hints"] = ff.get("hints") or []
    return ok("doctor", **res)


def _merge_manifest_into_timeline(timeline: Any, config: ProjectConfig | None) -> list[str]:
    """Apply sources manifest in/out points (and paths) onto a planned timeline. Preserves explicit trims."""
    notes: list[str] = []
    if not config:
        return notes
    mp = config.resolved_sources_manifest
    if not mp or not mp.exists():
        return notes
    try:
        manifest = load_manifest(mp)
        apply_manifest(timeline, manifest, base_dir=mp.resolve().parent)
        notes.append(f"merged sources manifest: {mp}")
    except Exception as e:
        notes.append(f"sources manifest merge skipped: {e}")
    return notes


def _project_brief_path(config: ProjectConfig) -> Path:
    raw = (config.raw or {}).get("brief_path") or (config.raw or {}).get("brief")
    if raw:
        p = Path(str(raw)).expanduser()
        return (config.project_dir / p).resolve() if not p.is_absolute() else p.resolve()
    for name in ("project.brief.json", "brief.json"):
        p = (config.project_dir / name)
        if p.exists():
            return p
    return (config.project_dir / "project.brief.json").resolve()


def _load_project_brief(config: ProjectConfig) -> dict[str, Any] | None:
    for name in ("project.brief.json", "brief.json"):
        p = config.project_dir / name
        if p.exists():
            try:
                data = load_structured(p)
                if isinstance(data, dict):
                    data["_path"] = str(p)
                    return data
            except Exception:
                return {"_path": str(p), "_error": "unreadable"}
    raw = (config.raw or {}).get("brief_path") or (config.raw or {}).get("brief")
    if raw:
        p = Path(str(raw)).expanduser()
        p = (config.project_dir / p).resolve() if not p.is_absolute() else p.resolve()
        if p.exists():
            try:
                data = load_structured(p)
                if isinstance(data, dict):
                    data["_path"] = str(p)
                    return data
            except Exception:
                return {"_path": str(p), "_error": "unreadable"}
    return None


def _write_project_brief(config: ProjectConfig, data: dict[str, Any]) -> Path:
    p = _project_brief_path(config)
    if p.suffix.lower() != ".json":
        p = p.with_suffix(".json")
    ensure_not_inside_repo(p, kind="project brief")
    dump_structured(p, data, fmt="json")
    return p


def project_status(*, project: str | Path) -> dict[str, Any]:
    config = load_config(project)
    ff = _ffmpeg_resolution()
    res: dict[str, Any] = {
        "project": config.name or config.project_dir.name,
        "config": str(config.config_path),
        "project_dir": str(config.project_dir),
        "template": {"path": str(config.template_path), "exists": config.template_path.exists()},
        "soundtrack": {"path": str(config.soundtrack_path) if config.soundtrack_path else None, "exists": bool(config.soundtrack_path and config.soundtrack_path.exists())},
        "clips_dir": {"path": str(config.clips_path) if config.clips_path else None, "exists": bool(config.clips_path and config.clips_path.exists())},
        "analysis_path": str(config.resolved_analysis_path),
        "timeline_path": str(config.resolved_timeline_path),
        "sources_manifest": {"path": str(config.resolved_sources_manifest), "exists": config.resolved_sources_manifest.exists()} if config.resolved_sources_manifest else None,
        "ffmpeg": ff["ffmpeg"],
        "ffprobe": ff["ffprobe"],
        "ffmpeg_info": ff,
        "ollama": {"configured": bool(config.ollama), "host": (config.ollama or {}).get("host"), "model": (config.ollama or {}).get("model"), "vision_model": (config.ollama or {}).get("vision_model")},
    }
    if config.clips_path and config.clips_path.exists():
        res["clips_count"] = len(discover_clips(config.clips_path))
    if config.resolved_timeline_path.exists():
        try:
            tl = load_timeline(config.resolved_timeline_path)
            mapped = sum(1 for s in tl.segments if s.source.status == "mapped")
            res["timeline"] = {"segments": len(tl.segments), "mapped": mapped, "unmapped": len(tl.segments) - mapped, "analysis_method": (tl.analysis or {}).get("method"), "soundtrack": tl.soundtrack}
        except Exception as e:
            res["timeline_error"] = str(e)
    if config.resolved_analysis_path.exists():
        try:
            data = json.loads(config.resolved_analysis_path.read_text(encoding="utf-8"))
            res["analysis_cache"] = {"method": data.get("method"), "beats": len(data.get("beat_times") or []), "cut_points": len(data.get("cut_points") or []), "duration": data.get("duration")}
        except Exception as e:
            res["analysis_cache_error"] = str(e)
    brief = _load_project_brief(config)
    if brief is not None:
        res["brief"] = {"path": brief.get("_path"), "present": "_error" not in brief, "summary": {k: v for k, v in brief.items() if not str(k).startswith("_")}}
    else:
        res["brief"] = {"present": False, "path": str(_project_brief_path(config))}
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
    merge_notes = _merge_manifest_into_timeline(timeline, config)
    out = Path(output).expanduser().resolve() if output else config.resolved_timeline_path
    timeline.write(out)
    mapped = sum(1 for s in timeline.segments if s.source.status == "mapped")
    total = len(timeline.segments)
    resolved = sum(1 for s in timeline.segments if s.resolved_duration is not None)
    res = ok(
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
    if merge_notes:
        res["manifest_merge"] = merge_notes
    return res


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
    timeline_explicit = timeline is not None
    manifest_explicit = manifest is not None

    # Resolve timeline. When using a project config without an explicit timeline, re-plan fresh by default
    # so render/timing/cut-points/soundtrack/manifest changes in config are applied (avoids stale timelines).
    if timeline_explicit:
        timeline_path = Path(timeline).expanduser().resolve()
        tl = load_timeline(timeline_path)
        replanned = False
    elif config:
        timeline_path = config.resolved_timeline_path
        if no_plan:
            if not timeline_path.exists():
                return fail("render", f"Timeline not found and --no-plan set: {timeline_path}")
            tl = load_timeline(timeline_path)
            replanned = False
        else:
            tl = build_plan(config, map_clips=False, analyze=True)
            _merge_manifest_into_timeline(tl, config)
            timeline_path = tl.write(timeline_path)
            replanned = True
    else:
        return fail("render", "Provide --project or --timeline")

    options = _render_config(config, preview=preview, no_probe=no_probe, strict_duration=strict_duration)

    # Resolve manifest: explicit arg is strict; auto-resolved config manifest is optional.
    manifest_path: Path | None = None
    manifest_value = manifest
    if not manifest_value and config:
        manifest_value = config.raw.get("sources_manifest") or config.raw.get("manifest")
    if manifest_value:
        mp = Path(str(manifest_value)).expanduser()
        if config and not mp.is_absolute():
            mp = (config.project_dir / mp).resolve()
        manifest_path = mp
    if manifest_explicit and manifest_path and not manifest_path.exists():
        return fail("render", f"Manifest not found: {manifest_path}")
    if manifest_path and manifest_path.exists():
        m = load_manifest(manifest_path)
        apply_manifest(tl, m, base_dir=manifest_path.resolve().parent)
    elif manifest_path and not manifest_explicit:
        manifest_path = None  # auto-resolved but missing; timeline mappings/in-points may suffice

    if output:
        out_path = Path(output).expanduser().resolve()
    elif config:
        out_path = config.output_path / ("preview.mp4" if preview else "final.mp4")
    else:
        out_path = Path("output.mp4").resolve()

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
        "timeline_path": str(timeline_path),
        "replanned": replanned,
        "inputs": [str(p) for p in plan.inputs],
        "warnings": plan.warnings,
        "probe_count": len([k for k, v in (plan.probe or {}).items() if v.get("duration") is not None]),
        "filter_complex": plan.filter_complex,
        "script": plan.script,
        "ffmpeg_command": plan.command,
        "manifest_applied": str(manifest_path) if manifest_path else None,
        "project_render_config_applied": bool(config and isinstance((config.raw or {}).get("render"), dict) and (config.raw or {}).get("render")),
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
    suggested = Path(output).expanduser().resolve() if output else (base / "sources.suggested.json")
    suggested = write_manifest(manifest_data, suggested)
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
        target = _resolve_manifest_target(config, manifest) or (base / "sources.json")
        target = write_manifest(manifest_data, target)
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
    suggested = Path(output).expanduser().resolve() if output else (base / "sources.selected.suggested.json")
    suggested = write_manifest(manifest_data, suggested)
    res: dict[str, Any] = {
        "suggested_manifest": str(suggested),
        "selections": selections,
        "applied": False,
        "requires_confirmation": True,
    }
    if apply:
        target = _resolve_manifest_target(config, manifest) or (base / "sources.json")
        target = write_manifest(manifest_data, target)
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
    try:
        raw = load_structured(src) or {}
    except Exception:
        raw = {"sources": data}
    tgt = Path(target).expanduser().resolve() if target else (_resolve_manifest_target(config, None) or ((config.project_dir if config else src.parent) / "sources.json"))
    written = write_manifest(raw if isinstance(raw, dict) else {"sources": data}, tgt)
    return ok("apply_manifest", suggested=str(src), applied_manifest=str(written), applied=True)


# ---- workspace / registries / project init ----

def workspace_info(*, workspace: str | Path | None = None, save: bool = False) -> dict[str, Any]:
    ws = load_workspace(workspace)
    if save:
        save_workspace_config(ws)
        ws.ensure_dirs(create=True)
    return ok("workspace", workspace=ws.to_dict(), templates=list_templates(ws), soundtracks=list_soundtracks(ws))


def templates_list(*, workspace: str | Path | None = None) -> dict[str, Any]:
    ws = load_workspace(workspace)
    return ok("templates", templates=[_jsonable(t.to_dict()) for t in list_templates(ws)], workspace=ws.to_dict())


def soundtracks_list(*, workspace: str | Path | None = None) -> dict[str, Any]:
    ws = load_workspace(workspace)
    items = []
    for s in list_soundtracks(ws):
        d = s.to_dict()
        d["has_curated_cut_points"] = bool(load_curated_cut_points(s, workspace=ws))
        items.append(d)
    return ok("soundtracks", soundtracks=items, workspace=ws.to_dict())


def soundtrack_import(*, source: str | Path, workspace: str | Path | None = None, track_id: str | None = None, title: str | None = None, aliases: list[str] | None = None) -> dict[str, Any]:
    ws = load_workspace(workspace)
    entry = import_soundtrack(source, workspace=ws, track_id=track_id, title=title, aliases=aliases, copy=True)
    return ok("soundtrack_import", soundtrack=entry.to_dict(), copied=True, workspace=ws.to_dict())


def soundtrack_set_cut_points(
    *,
    soundtrack: str | Path,
    workspace: str | Path | None = None,
    cut_points: list[float] | None = None,
    bpm: float | None = None,
    offset: float | None = None,
    beat_times: list[float] | None = None,
    notes: list[str] | None = None,
    method: str = "curated",
) -> dict[str, Any]:
    ws = load_workspace(workspace)
    ref = save_curated_cut_points(soundtrack, cut_points=cut_points, bpm=bpm, offset=offset, beat_times=beat_times, notes=notes, method=method, workspace=ws)
    entry = resolve_soundtrack(soundtrack, workspace=ws)
    return ok("soundtrack_set_cut_points", cut_points_path=str(ref), soundtrack=entry.to_dict() if entry else None, curated=True)


def _derive_address_lines(address: str) -> str:
    if "\\n" in address:
        return address.replace("\\r\\n", "\\n")
    parts = [p.strip() for p in re.split(r",\s*", address) if p.strip()]
    if len(parts) >= 3:
        return parts[0] + "\n" + ", ".join(parts[1:])
    if len(parts) == 2:
        return parts[0] + "\n" + parts[1]
    return address.strip()


def _next_available_dir(base: Path) -> Path:
    if not base.exists():
        return base
    i = 2
    while True:
        cand = base.parent / f"{base.name}-{i}"
        if not cand.exists():
            return cand
        i += 1


def init_project(
    *,
    workspace: str | Path | None = None,
    name: str | None = None,
    address: str | None = None,
    template: str | Path = "standard real estate template",
    soundtrack: str | Path | None = None,
    clips_dir: str | Path | None = None,
    project_id: str | None = None,
    variables: dict[str, Any] | None = None,
    on_exists: str = "fail",
    register_soundtrack: bool = False,
    soundtrack_title: str | None = None,
    ollama: dict[str, Any] | None = None,
    analysis: dict[str, Any] | None = None,
    render: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ws = load_workspace(workspace)
    ensure_not_inside_repo(ws.root, kind="workspace")
    # resolve template
    try:
        template_path = resolve_template(template, workspace=ws)
    except Exception as e:
        return fail("init", f"Could not resolve template {template!r}: {e}")
    # resolve soundtrack
    snd_path: Path | None = None
    snd_entry = None
    curated_ref = None
    if soundtrack:
        snd_entry = resolve_soundtrack(soundtrack, workspace=ws)
        if snd_entry and snd_entry.path:
            snd_path = snd_entry.path
            curated_ref = load_curated_cut_points(snd_entry, workspace=ws)
        else:
            sp = Path(str(soundtrack)).expanduser().resolve()
            if sp.exists():
                snd_path = sp
                if register_soundtrack:
                    snd_entry = import_soundtrack(sp, workspace=ws, title=soundtrack_title, copy=True)
                    snd_path = snd_entry.path
                    curated_ref = load_curated_cut_points(snd_entry, workspace=ws)
            else:
                return fail("init", f"Soundtrack not found: {soundtrack}")
    # resolve clips
    clips: Path | None = None
    if clips_dir:
        clips = Path(str(clips_dir)).expanduser().resolve()
        if not clips.exists():
            return fail("init", f"Clips directory not found: {clips}")
    # slug/name
    slug_source = project_id or name or address or "project"
    slug = slugify(str(slug_source))
    proj_dir = ws.project_dir(slug)
    if proj_dir.exists():
        if on_exists == "fail":
            return fail(
                "init",
                f"Project already exists: {proj_dir}",
                exists=True,
                project_dir=str(proj_dir),
                requires_resolution=True,
                options=["overwrite", "suffix", "cancel"],
                hint="In chat, ask the user what to do. For CLI/MCP pass on_exists=overwrite|suffix|fail.",
            )
        if on_exists == "suffix":
            proj_dir = _next_available_dir(proj_dir)
            slug = proj_dir.name
        elif on_exists == "overwrite":
            pass
        else:
            return fail("init", f"Invalid on_exists={on_exists!r}; use fail|overwrite|suffix", requires_resolution=True)
    ensure_not_inside_repo(proj_dir, kind="project")
    out_dir = proj_dir / "output"
    proj_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    ws.ensure_dirs(create=True)
    vars_out: dict[str, Any] = dict(variables or {})
    if address and "address" not in vars_out:
        vars_out["address"] = _derive_address_lines(str(address))
    cfg_analysis: dict[str, Any] = {"backend": "auto"}
    if isinstance(analysis, dict):
        cfg_analysis.update(analysis)
    # apply curated cut points as explicit, reusable reference (map once, reuse)
    if curated_ref and not any(k in cfg_analysis for k in ("cut_points", "bpm", "beat_times")):
        if curated_ref.get("cut_points"):
            cfg_analysis["cut_points"] = curated_ref.get("cut_points")
        if curated_ref.get("bpm") is not None and "bpm" not in cfg_analysis:
            cfg_analysis["bpm"] = curated_ref.get("bpm")
        if curated_ref.get("offset") is not None and "offset" not in cfg_analysis:
            cfg_analysis["offset"] = curated_ref.get("offset")
    config_data: dict[str, Any] = {
        "version": 1,
        "name": name or (address.split(",")[0].strip() if address else slug),
        "template": str(template_path),
        "soundtrack": str(snd_path) if snd_path else None,
        "clips_dir": str(clips) if clips else None,
        "output_dir": str(out_dir),
        "analysis_path": str(out_dir / "analysis.json"),
        "timeline_path": str(out_dir / "timeline.json"),
        "sources_manifest": str(out_dir / "sources.json"),
        "variables": vars_out,
        "analysis": cfg_analysis,
        "ollama": dict(ollama or {}),
        "render": dict(render or {"fontfile": None, "box": False}),
        "workspace": str(ws.root),
    }
    if snd_entry:
        config_data["soundtrack_id"] = snd_entry.id
    cfg_path = proj_dir / "alvex.json"
    dump_structured(cfg_path, config_data, fmt="json")
    # optional project brief for session resume (JSON everywhere)
    from datetime import datetime, timezone
    brief_path = proj_dir / "project.brief.json"
    brief = {
        "version": 1,
        "project": config_data["name"],
        "slug": slug,
        "config": str(cfg_path),
        "workspace": str(ws.root),
        "template": {"ref": str(template), "resolved": str(template_path)},
        "soundtrack": {"ref": str(soundtrack) if soundtrack else None, "resolved": str(snd_path) if snd_path else None, "id": (snd_entry.id if snd_entry else None), "curated_cut_points_applied": bool(curated_ref and curated_ref.get("cut_points"))},
        "clips_dir": str(clips) if clips else None,
        "variables": vars_out,
        "render": config_data.get("render") or {},
        "timing": config_data.get("timing") or {},
        "status": "initialized",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "notes": [],
    }
    ensure_not_inside_repo(brief_path, kind="project brief")
    dump_structured(brief_path, brief, fmt="json")
    resolved = {
        "project": config_data["name"],
        "slug": slug,
        "project_dir": str(proj_dir),
        "config": str(cfg_path),
        "brief": str(brief_path),
        "workspace": ws.to_dict(),
        "template": {"ref": str(template), "resolved": str(template_path)},
        "soundtrack": {"ref": str(soundtrack) if soundtrack else None, "resolved": str(snd_path) if snd_path else None, "id": (snd_entry.id if snd_entry else None), "curated_cut_points_applied": bool(curated_ref and curated_ref.get("cut_points"))},
        "clips_dir": str(clips) if clips else None,
        "variables": vars_out,
        "output_dir": str(out_dir),
    }
    return ok("init", created=True, on_exists=on_exists, resolved=resolved, next_steps=[
        "Confirm resolved inputs (paths, address, template, soundtrack/cut points).",
        "Run analyze/plan, then render a preview (dry-run/preview first).",
        "Review preview, take feedback (adjust cut points/in-points/variables), re-render preview.",
        "Render final only on explicit intent.",
    ])


# ---- cut-point authoring / review (Phase 3) ----

def _project_cut_points_and_onsets(config: ProjectConfig) -> tuple[list[float], list[float]]:
    pts = [float(x) for x in ((config.analysis or {}).get("cut_points") or [])]
    onsets: list[float] = []
    ap = config.resolved_analysis_path
    if ap.exists():
        try:
            a = load_analysis(ap)
            onsets = list(a.beat_times or [])
            if not pts and a.cut_points:
                pts = list(a.cut_points)
        except Exception:
            pass
    tp = config.resolved_timeline_path
    if tp.exists() and not onsets:
        try:
            tl = load_timeline(tp)
            onsets = [float(x) for x in ((tl.analysis or {}).get("beat_times") or [])]
            if not pts:
                pts = [float(x) for x in ((tl.analysis or {}).get("cut_points") or [])]
        except Exception:
            pass
    return pts, onsets


def cuts_show(*, project: str | Path, cut_points: list[float] | None = None) -> dict[str, Any]:
    config = load_config(project)
    pts = [float(x) for x in cut_points] if cut_points is not None else _project_cut_points_and_onsets(config)[0]
    labeled = _cutpoints.label_cut_points(config, pts)
    return ok("cuts_show", project=str(config.config_path), **labeled)


def cuts_suggest(*, project: str | Path, onsets: list[float] | None = None, count: int | None = None, use_second_of_pair: bool = False, min_gap: float = 0.8, max_gap: float = 1.4, near: float | None = None) -> dict[str, Any]:
    config = load_config(project)
    pts, cache_onsets = _project_cut_points_and_onsets(config)
    use_onsets = [float(x) for x in onsets] if onsets is not None else cache_onsets
    res = _cutpoints.suggest_cut_points(config, onsets=use_onsets, count=count, use_second_of_pair=use_second_of_pair, min_gap=min_gap, max_gap=max_gap)
    if near is not None and use_onsets:
        pair = _cutpoints.suggest_second_of_pair(use_onsets, near=near, min_gap=min_gap, max_gap=max_gap)
        if pair:
            res["near_pair_suggestion"] = pair
    res["onsets_available"] = len(use_onsets)
    res["requires_confirmation"] = True
    return ok("cuts_suggest", **res)


def cuts_nudge(*, project: str | Path, near: float, to: float | str, onsets: list[float] | None = None, min_gap: float = 0.8, max_gap: float = 1.4, cut_points: list[float] | None = None) -> dict[str, Any]:
    config = load_config(project)
    pts, cache_onsets = _project_cut_points_and_onsets(config)
    use_pts = [float(x) for x in cut_points] if cut_points is not None else pts
    use_onsets = [float(x) for x in onsets] if onsets is not None else cache_onsets
    res = _cutpoints.nudge_cut_points(use_pts, near=near, to=to, onsets=use_onsets, min_gap=min_gap, max_gap=max_gap)
    res["labeled_preview"] = _cutpoints.label_cut_points(config, res["cut_points"])["boundaries"]
    return ok("cuts_nudge", **res)


def _save_project_config(config: ProjectConfig, data: dict[str, Any]) -> Path:
    p = config.config_path
    ensure_not_inside_repo(p, kind="project config")
    if p.suffix.lower() != ".json":
        p = p.with_suffix(".json")
    dump_structured(p, data, fmt="json")
    return p


def cuts_apply(*, project: str | Path, cut_points: list[float], save_config: bool = True) -> dict[str, Any]:
    config = load_config(project)
    pts = [round(float(x), 4) for x in cut_points]
    labeled = _cutpoints.label_cut_points(config, pts)
    res = {
        "project": str(config.config_path),
        "cut_points": pts,
        "labeled": labeled["boundaries"],
        "warnings": labeled["warnings"],
        "saved_config": False,
        "requires_confirmation": False,
    }
    if save_config:
        raw = dict(config.raw or {})
        analysis = dict(raw.get("analysis") or {})
        analysis["cut_points"] = pts
        raw["analysis"] = analysis
        path = _save_project_config(config, raw)
        res["saved_config"] = True
        res["config_path"] = str(path)
    return ok("cuts_apply", **res)


def cuts_preview(*, project: str | Path, cut_points: list[float] | None = None, save_config: bool = False, allow_unmapped: bool = True, no_probe: bool = True) -> dict[str, Any]:
    """One-step explicit iteration: optionally persist cut points, re-plan from current config, render preview. Uses project render config and fresh timeline."""
    config = load_config(project)
    if cut_points is not None and save_config:
        ar = cuts_apply(project=config.config_path, cut_points=cut_points, save_config=True)
        if not ar.get("ok"):
            return ar
        config = load_config(project)
    elif cut_points is not None and not save_config:
        # in-memory override: write temp timeline from modified analysis
        raw = dict(config.raw or {})
        analysis = dict(raw.get("analysis") or {})
        analysis["cut_points"] = [round(float(x), 4) for x in cut_points]
        raw["analysis"] = analysis
        # build via a transient config view
        from .config import ProjectConfig as _PC
        cfg2 = _PC(
            config_path=config.config_path, project_dir=config.project_dir, template=config.template,
            soundtrack=config.soundtrack, clips_dir=config.clips_dir, overlays_dir=config.overlays_dir,
            branding_dir=config.branding_dir, output_dir=config.output_dir, timeline_path=config.timeline_path,
            analysis_path=config.analysis_path, sources_manifest=config.sources_manifest, variables=config.variables,
            analysis=analysis, timing=config.timing, ollama=config.ollama, name=config.name, raw=raw,
        )
        tl = build_plan(cfg2, map_clips=False, analyze=False)
        _merge_manifest_into_timeline(tl, cfg2)
        import tempfile
        tmp = Path(tempfile.mkstemp(prefix='alvex-cuts-', suffix='.timeline.json')[1])
        tl.write(tmp)
        rr = render(project=config.config_path, timeline=tmp, preview=True, dry_run=False, allow_unmapped=allow_unmapped, no_probe=no_probe)
        rr["cuts_applied"] = list(analysis["cut_points"])
        rr["saved_config"] = False
        rr["temporary_timeline"] = str(tmp)
        return rr
    # save_config True but cut_points None: just replan+preview current config
    pr = plan(project=config.config_path)
    if not pr.get("ok"):
        return pr
    rr = render(project=config.config_path, preview=True, dry_run=False, allow_unmapped=allow_unmapped, no_probe=no_probe)
    rr["planned"] = pr
    rr["saved_config"] = bool(save_config and cut_points is not None)
    return rr
