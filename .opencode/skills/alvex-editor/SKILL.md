---
name: alvex-editor
description: Produce template-driven, beat-aligned videos (e.g., real-estate exterior showcases) with Alvex Editor. Use when the user wants to generate/edit a property or template-based video from clips + soundtrack. Follows the canonical workflow with human confirmation for AI suggestions and renders.
---

# Alvex Editor (agent workflow)

Follow the **canonical guide**: `docs/alvex-editor-agent-guide.md`. Treat that document as the source of truth for steps, artifacts, and safety rules.

## Quick workflow
1. **Gather inputs** (confirm): `clips_dir`, `soundtrack` (MP3), template, `variables` (e.g. `address`, may include `\n`), output target. Project config is `alvex.yaml` (paths relative to it).
2. **Check status/tools**: `alvex-editor status -p alvex.yaml --json` (or MCP `project_status`). Ensure ffmpeg/ffprobe available; Ollama optional.
3. **Analyze soundtrack (reuse library)**: `alvex-editor analyze -p alvex.yaml --backend onsets --refresh` (build/cache) or without `--refresh` to reuse. Explicit `analysis.cut_points`/`bpm` in config override detection.
4. **Plan**: `alvex-editor plan -p alvex.yaml --map-clips` → `timeline.json`.
5. **Suggest mapping/in-points (optional, AI, CONFIRM)**: `alvex-editor align ...` / `select ...` write *suggested* manifests. **Never auto-apply** — show results, get explicit user confirmation, then re-run with `--apply` (or use `apply_manifest`). Ollama config (e.g. existing `qwen3-vl:latest`) comes from `alvex.yaml` / flags.
6. **Render (explicit)**: `alvex-editor render -p alvex.yaml --dry-run` or `--preview` first; run final only with clear user intent. 4K renders can be resource-intensive.

## Invocation (prefer structured tools)
- **MCP (if registered):** use `project_status`, `template_info`, `analyze_soundtrack`, `plan_timeline`, `suggest_clip_mapping`, `suggest_inpoints`, `apply_manifest`, `render_video` (preserves confirmation gates; `render_video` defaults `preview=true`).
- **CLI fallback:** `alvex-editor <command> --json` (or `PYTHONPATH=src python3 -m alvex_editor.cli ...` from a source checkout).

## Rules
- **Permission guard:** do not create/edit/delete/move/rename/commit files in this repository without explicit user permission. State the intended change and get a clear go-ahead first (read-only inspection is allowed).
- AI (Ollama-only) is optional; suggestions require **human confirmation** before apply.
- Renders are explicit; prefer `--dry-run`/`--preview`.
- **Storage policy:** videos, soundtracks, thumbnails, and edit plans/manifests/analysis must be saved **outside the Alvex Editor codebase** (the app enforces writes; keep only the example template `templates/exterior-showcase.md` in-repo).
- Use the song cut-point library (hash-cached onsets) to avoid re-evaluating the same soundtrack.
- Set `render.fontfile` for portable title rendering; `variables.address` supports `\n` (two-line centered overlay).
