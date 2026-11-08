from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import api
from .ollama import OllamaError


def _emit(args: argparse.Namespace, result: dict, human_lines: list[str] | None = None) -> int:
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    if not result.get("ok"):
        print(f"error: {result.get('error', 'unknown error')}", file=sys.stderr)
        return 1
    for line in (human_lines or []):
        if line.startswith("! "):
            print(line, file=sys.stderr)
        else:
            print(line)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    r = api.project_status(project=args.project)
    s = r.get("status") or {}
    lines = [
        f"Project: {s.get('project')} ({s.get('config')})",
        f"Template: {s.get('template',{}).get('path')} exists={s.get('template',{}).get('exists')}",
        f"Soundtrack: {s.get('soundtrack',{}).get('path')} exists={s.get('soundtrack',{}).get('exists')}",
        f"Clips dir: {s.get('clips_dir',{}).get('path')} exists={s.get('clips_dir',{}).get('exists')} count={s.get('clips_count','?')}",
        f"Timeline: {s.get('timeline_path')} " + (f"segments={s['timeline']['segments']} mapped={s['timeline']['mapped']} analysis={s['timeline'].get('analysis_method')}" if s.get('timeline') else "(none)"),
        f"Analysis cache: {s.get('analysis_path')} " + (f"method={s['analysis_cache'].get('method')} beats={s['analysis_cache'].get('beats')} cuts={s['analysis_cache'].get('cut_points')}" if s.get('analysis_cache') else "(none)"),
        f"ffmpeg={s.get('ffmpeg')} ffprobe={s.get('ffprobe')}",
    ]
    return _emit(args, r, lines)


def cmd_plan(args: argparse.Namespace) -> int:
    r = api.plan(project=args.project, output=args.output, map_clips=args.map_clips, run_analyze=not args.no_analyze)
    if not r.get("ok"):
        return _emit(args, r)
    a = r.get("analysis") or {}
    method = a.get("method", "unknown")
    bpm = a.get("bpm")
    extra = f", {bpm:g} BPM" if bpm else ""
    lines = [
        f"Wrote timeline: {r['output']}",
        f"Template: {r['template']}",
        f"Segments: {r['segments_total']} ({r['segments_mapped']} mapped, {r['segments_unmapped']} unmapped, {r['segments_timed']} timed)",
        f"Analysis: {method}{extra}",
    ]
    return _emit(args, r, lines)


def cmd_template(args: argparse.Namespace) -> int:
    r = api.template_info(project=args.project)
    if not r.get("ok"):
        return _emit(args, r)
    if args.json:
        # --json flag on template historically meant template JSON; honor it
        print(json.dumps(r.get("data"), indent=2, ensure_ascii=False))
        return 0
    if getattr(args, "emit_json", False):
        print(json.dumps(r, indent=2, ensure_ascii=False))
        return 0
    lines = [f"Template: {r['template_path']}", f"Title: {r['title']}", f"Edit slots: {r['slot_count']}"]
    for s in r.get("slots") or []:
        opt = " (optional)" if s.get("optional") else ""
        dur = ""
        if s.get("min_duration") and s.get("max_duration"):
            dur = f" [{s['min_duration']:g}-{s['max_duration']:g}s]"
        lines.append(f"  {s['index']:>2}. {s['name']}{opt}{dur} -> {s['slot_id']}")
    return _emit(args, r, lines)


def cmd_render(args: argparse.Namespace) -> int:
    r = api.render(
        project=args.project,
        timeline=args.timeline,
        manifest=args.manifest,
        output=args.output,
        soundtrack=args.soundtrack,
        preview=args.preview,
        dry_run=args.dry_run or args.print_filter,
        print_filter=args.print_filter,
        allow_unmapped=args.allow_unmapped,
        no_plan=args.no_plan,
        no_probe=args.no_probe,
        strict_duration=args.strict_duration,
    )
    if getattr(args, "json", False):
        return _emit(args, r)
    if not r.get("ok"):
        print(f"error: {r.get('error')}", file=sys.stderr)
        return 1
    if args.print_filter:
        print(r.get("filter_complex", ""))
    if r.get("dry_run"):
        print(r.get("script", ""), end="")
        if r.get("probe_count"):
            print(f"Probed: {r['probe_count']} input(s)")
    elif r.get("rendered"):
        print(f"Rendered: {r['output']}")
    for w in r.get("warnings") or []:
        print(f"warning: {w}")
    return 0


def cmd_align(args: argparse.Namespace) -> int:
    r = api.suggest_mapping(
        project=args.project,
        timeline=args.timeline,
        clips=args.clips,
        host=args.host,
        model=args.model,
        vision_model=getattr(args, "vision_model", None),
        vision=getattr(args, "vision", False),
        output=args.output,
        manifest=args.manifest,
        apply=args.apply,
    )
    if not r.get("ok"):
        return _emit(args, r)
    lines = [
        f"Wrote suggested manifest (review required): {r['suggested_manifest']}",
        f"Clips: {r['clips']} | Mapped: {r['mapped']} | Unmapped slots: {len(r.get('unmapped_slots') or [])}",
    ]
    for slot, info in (r.get("sources") or {}).items():
        if isinstance(info, dict):
            sug = info.get("_suggestion") or {}
            conf = sug.get("confidence")
            conf_s = f" ({conf:.0%})" if isinstance(conf, (int, float)) else ""
            lines.append(f"  - {slot}: {Path(info.get('path','')).name}{conf_s}")
    if r.get("applied"):
        lines.append(f"Applied manifest: {r['applied_manifest']}")
    else:
        lines.append("Human confirmation required: review the suggested manifest, then re-run with --apply (or pass it via --manifest).")
    return _emit(args, r, lines)


def cmd_select(args: argparse.Namespace) -> int:
    slots = [s.strip() for s in (args.slots or "").split(",") if s.strip()] or None
    r = api.suggest_inpoints(
        project=args.project,
        timeline=args.timeline,
        manifest=args.manifest,
        host=args.host,
        model=args.model,
        vision_model=getattr(args, "vision_model", None),
        vision=getattr(args, "vision", False),
        candidates=args.candidates,
        slots=slots,
        output=args.output,
        apply=args.apply,
    )
    if not r.get("ok"):
        return _emit(args, r)
    selections = r.get("selections") or {}
    applied = [s for s, v in selections.items() if isinstance(v, dict) and "in_point" in v]
    lines = [
        f"Wrote suggested in-point manifest (review required): {r['suggested_manifest']}",
        f"Selected in-points: {len(applied)} segment(s)",
    ]
    for slot_id in sorted(applied):
        v = selections[slot_id]
        detail = v.get("detail") or {}
        method = detail.get("method", "?")
        sel = (detail.get("selected") or {})
        conf = sel.get("score")
        conf_s = f", {conf:.0%}" if isinstance(conf, (int, float)) else ""
        lines.append(f"  - {slot_id}: in={v['in_point']:.3g}s [{method}{conf_s}] {sel.get('reason','')}")
    for slot_id, v in selections.items():
        if isinstance(v, dict) and "error" in v:
            lines.append(f"! {slot_id}: {v['error']}")
    if r.get("applied"):
        lines.append(f"Applied manifest: {r['applied_manifest']}")
    else:
        lines.append("Human confirmation required: review the suggested manifest, then re-run with --apply (or pass it via --manifest).")
    return _emit(args, r, lines)


def cmd_analyze(args: argparse.Namespace) -> int:
    r = api.analyze(project=args.project, output=args.output, backend=getattr(args, "backend", None), refresh=bool(getattr(args, "refresh", False)), write_cache=not args.no_cache)
    if not r.get("ok"):
        return _emit(args, r)
    lines = [f"Wrote analysis: {r['output']}", f"Method: {r['method']}"]
    if r.get("bpm"):
        lines.append(f"BPM: {r['bpm']:g}")
    if r.get("duration"):
        lines.append(f"Duration: {r['duration']:g}s")
    lines.append(f"Beats: {r['beats']}, cut points: {r['cut_points']}")
    for n in (r.get("notes") or [])[:6]:
        lines.append(f"  note: {n}")
    return _emit(args, r, lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="alvex-editor", description="Alvex Editor - template-driven video production")
    sub = p.add_subparsers(dest="command", required=True)

    st = sub.add_parser("status", help="Show project status, artifacts, and tool availability")
    st.add_argument("--project", "-p", required=True, help="Path to project config (alvex.yaml)")
    st.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    st.set_defaults(func=cmd_status)

    plan = sub.add_parser("plan", help="Build a timeline plan from a project config and template")
    plan.add_argument("--project", "-p", required=True, help="Path to project config (alvex.yaml)")
    plan.add_argument("--output", "-o", help="Output timeline JSON path (default: timeline_path from config)")
    plan.add_argument("--map-clips", action="store_true", help="Best-effort map files from clips_dir to slots by name/hint")
    plan.add_argument("--no-analyze", action="store_true", help="Skip soundtrack analysis; resolve timing from target durations only")
    plan.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    plan.set_defaults(func=cmd_plan)

    analyze = sub.add_parser("analyze", help="Analyze soundtrack to produce beat/cut-point grid (analysis.json)")
    analyze.add_argument("--project", "-p", required=True, help="Path to project config (alvex.yaml)")
    analyze.add_argument("--output", "-o", help="Output analysis JSON path (default: analysis_path from config)")
    analyze.add_argument("--backend", choices=["auto", "onsets", "librosa", "library"], help="Analysis backend (default: auto; 'onsets' = ffmpeg+numpy, cached in library)")
    analyze.add_argument("--refresh", action="store_true", help="Ignore cached/library analysis and recompute")
    analyze.add_argument("--no-cache", action="store_true", help="Do not write the analysis cache to analysis_path")
    analyze.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    analyze.set_defaults(func=cmd_analyze)

    render = sub.add_parser("render", help="Render a resolved timeline to video (FFmpeg)")
    render.add_argument("--project", "-p", help="Path to project config (alvex.yaml)")
    render.add_argument("--timeline", "-t", help="Path to timeline JSON (overrides project's timeline_path)")
    render.add_argument("--manifest", "-m", help="Source manifest mapping slot_id -> media path (YAML/JSON; default: config sources_manifest)")
    render.add_argument("--output", "-o", help="Output video path")
    render.add_argument("--soundtrack", help="Override soundtrack audio path")
    render.add_argument("--dry-run", action="store_true", help="Print the FFmpeg command/script without executing")
    render.add_argument("--print-filter", action="store_true", help="Print filter_complex (implies --dry-run)")
    render.add_argument("--preview", action="store_true", help="Render a faster/lower-resolution preview")
    render.add_argument("--allow-unmapped", action="store_true", help="Skip unmapped non-optional segments (for testing)")
    render.add_argument("--no-plan", action="store_true", help="Do not auto-plan when project timeline is missing")
    render.add_argument("--no-probe", action="store_true", help="Skip ffprobe validation/clamping of inputs")
    render.add_argument("--strict-duration", action="store_true", help="Error if a source is shorter than the resolved duration")
    render.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    render.set_defaults(func=cmd_render)

    align = sub.add_parser("align", help="Suggest clip-to-slot mappings via Ollama (writes a manifest for human review)")
    align.add_argument("--project", "-p", help="Path to project config (alvex.yaml)")
    align.add_argument("--timeline", "-t", help="Path to timeline JSON")
    align.add_argument("--clips", help="Directory containing source clips")
    align.add_argument("--host", help="Ollama host/base URL (e.g., http://192.168.11.136:11434)")
    align.add_argument("--model", help="Ollama model for mapping suggestions (text/tools)")
    align.add_argument("--vision-model", help="Ollama vision model for clip labeling (e.g., qwen3-vl:latest)")
    align.add_argument("--vision", action="store_true", help="Label clips by extracting a frame and using the vision model")
    align.add_argument("--output", "-o", help="Suggested manifest path (default: sources.suggested.yaml)")
    align.add_argument("--manifest", "-m", help="Target manifest path for --apply (default: config sources_manifest or sources.yaml)")
    align.add_argument("--apply", action="store_true", help="Apply suggestion to the target manifest (explicit human confirmation)")
    align.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    align.set_defaults(func=cmd_align)

    select = sub.add_parser("select", help="Suggest in-points (segment selection) for mapped clips via heuristics/vision (human-confirmed)")
    select.add_argument("--project", "-p", help="Path to project config (alvex.yaml)")
    select.add_argument("--timeline", "-t", help="Path to timeline JSON")
    select.add_argument("--manifest", "-m", help="Source manifest (slot_id -> clip path; default: config sources_manifest)")
    select.add_argument("--host", help="Ollama host/base URL (e.g., http://192.168.11.136:11434)")
    select.add_argument("--model", help="Ollama model for vision selection (defaults to vision_model/model)")
    select.add_argument("--vision-model", help="Ollama vision model (e.g., qwen3-vl:latest)")
    select.add_argument("--vision", action="store_true", help="Use vision model to rank candidate windows (requires ffmpeg; slower)")
    select.add_argument("--candidates", type=int, default=5, help="Candidate windows per segment (default: 5)")
    select.add_argument("--slots", help="Comma-separated slot_ids to process (default: all mapped)")
    select.add_argument("--output", "-o", help="Suggested manifest path (default: sources.selected.suggested.yaml)")
    select.add_argument("--apply", action="store_true", help="Apply in-points to the target manifest (explicit human confirmation)")
    select.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    select.set_defaults(func=cmd_select)

    tmpl = sub.add_parser("template", help="Inspect/parse a project's template")
    tmpl.add_argument("--project", "-p", required=True, help="Path to project config (alvex.yaml)")
    tmpl.add_argument("--json", action="store_true", help="Output parsed template as JSON (template data)")
    tmpl.add_argument("--emit-json", action="store_true", dest="emit_json", help=argparse.SUPPRESS)
    tmpl.set_defaults(func=cmd_template)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as e:  # CLI boundary
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e)}, indent=2, ensure_ascii=False))
            return 1
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
