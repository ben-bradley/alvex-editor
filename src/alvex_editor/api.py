from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import re
from typing import Any

import yaml

from .align import align_project, write_manifest
from .audio import analyze_soundtrack
from .config import ProjectConfig, load_config
from .ollama import OllamaConfig, OllamaError
from .planner import build_plan, discover_clips
from .policy import ensure_not_inside_repo
from .probe import find_ffmpeg, find_ffprobe, probe_media
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
        "sources_manifest": str(out_dir / "sources.yaml"),
        "variables": vars_out,
        "analysis": cfg_analysis,
        "ollama": dict(ollama or {}),
        "render": dict(render or {"fontfile": None, "box": False}),
        "workspace": str(ws.root),
    }
    if snd_entry:
        config_data["soundtrack_id"] = snd_entry.id
    cfg_path = proj_dir / "alvex.yaml"
    cfg_path.write_text(yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    resolved = {
        "project": config_data["name"],
        "slug": slug,
        "project_dir": str(proj_dir),
        "config": str(cfg_path),
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
