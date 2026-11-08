# Alvex Editor — Agent Guide (canonical, portable)

This is the **canonical, agent-agnostic** workflow for producing videos with Alvex Editor through a chat/AI agent. It is portable across runtimes (OpenCode, other chat agents, future MCP clients). Platform-specific “skills” should be **thin adapters** that point to this guide rather than duplicating it.

## What Alvex does

Template-driven, beat-aligned video production (primary use case: real-estate exterior showcase).

**Pipeline (deterministic given resolved inputs):** template + clips + soundtrack → analyze soundtrack for pacing/transition points → resolve a timeline → (optionally) map clips & select in-points → render with intro/outro, titles/overlays, audio → review/export.

**Key artifacts (file-backed, inspectable):**
- `alvex.yaml` — project config (template, soundtrack, `clips_dir`, `output_dir`, `analysis`, `ollama`, `render`, `variables`). Paths resolve relative to the config file.
- `output/analysis.json` (project cache) and the **song cut-point library** `~/.cache/alvex/analysis/<soundtrack>-<hash>.json` (cross-platform cache dir) — beat/onset grid (`method`, `duration`, `beat_times`, `cut_points`).
- `output/timeline.json` — resolved plan (`analysis` + per-segment `resolved_duration`, `timeline_in/out`, `source` mapping/status, transitions/effects/overlays).
- `sources.suggested.yaml` / `sources.selected.suggested.yaml` → **`sources.yaml` (applied, human-confirmed)** — `slot_id -> {path, in_point, out_point}` plus suggestion metadata.
- `output/preview.mp4` / `output/final.mp4`.

## Safety & human confirmation (required)

- **AI suggestions are never auto-applied.** `align` (clip→slot mapping) and `select` (in-point) write *suggested* manifests for review and only write the target manifest when explicitly confirmed (`--apply`).
- **Rendering is explicit.** Prefer `--dry-run` or `--preview` first; full renders can be resource-intensive (4K sources).
- **Ollama-only for AI.** Configure `ollama` in `alvex.yaml` (e.g., `model`/`vision_model: qwen3-vl:latest`). See `docs/ollama.md`. Vision labeling/extraction uses `ffmpeg`.

## Chat workflow (recommended)

1. **Gather inputs (ask/confirm with the user).**
   - `clips_dir` (source footage), `soundtrack` (MP3), template (`templates/exterior-showcase.md` or custom), and variables (e.g., `address` — supports `\n` for a second line; render with `render.box: false` for centered text by default). Confirm output targets.

2. **Create/locate the project config** (`alvex.yaml`). Ensure paths resolve (relative to the config). Check status: template parses, soundtrack/clips exist, ffmpeg/ffprobe available.

3. **Analyze the soundtrack (reusable).**
   - Build or reuse the song cut-point library (onsets via ffmpeg+numpy):
     ```bash
     alvex-editor analyze -p alvex.yaml --backend onsets --refresh   # compute & cache
     alvex-editor analyze -p alvex.yaml                              # reuse library/cache
     ```
   - Explicit `analysis.cut_points`/`bpm`/`beat_times` in config override detection (use for hand-tuned beats). See `docs/audio-analysis.md`.

4. **Plan the timeline.**
   ```bash
   alvex-editor plan -p alvex.yaml --map-clips -o output/timeline.json
   ```
   Review segment count, mapped/unmapped (optional slots like `features` may be unmapped and consume 0 time), and timing (`analysis.method`, cut points/beat alignment).

5. **Suggest clip mapping (optional, AI, confirm).**
   ```bash
   alvex-editor align -p alvex.yaml [--vision] -o output/sources.suggested.yaml
   # REVIEW suggested mappings/confidences, then explicitly confirm:
   alvex-editor align -p alvex.yaml [--vision] --apply
   ```
   You may also edit the manifest directly. `--host/--model/--vision-model` override config.

6. **Suggest in-points (optional, AI/heuristics, confirm).**
   ```bash
   alvex-editor select -p alvex.yaml [--vision] [-o output/sources.selected.suggested.yaml]
   # REVIEW, then confirm:
   alvex-editor select -p alvex.yaml [--vision] --apply
   ```
   Tune `in_point` per slot in `sources.yaml` as needed (beats/cut points are set via `analysis.cut_points` or beat-grid snapping).

7. **Render (explicit).**
   ```bash
   alvex-editor render -p alvex.yaml --dry-run                         # verify filter/command
   alvex-editor render -p alvex.yaml --preview -o output/preview.mp4   # fast check
   alvex-editor render -p alvex.yaml -o output/final.mp4              # final
   ```
   Useful flags: `--no-probe`, `--strict-duration`, `--allow-unmapped` (testing), `--manifest`. Set `render.fontfile` for portable title rendering (esp. Windows/macOS).

8. **Iterate on feedback.** Adjust `analysis.cut_points` (beat boundaries), per-slot `in_point` in the manifest, `variables` (e.g., address), or template/render settings; re-`plan` as needed, then re-render. The song library avoids re-detecting the same soundtrack.

## Current invocation (today)

- **CLI:** `alvex-editor <command> ...` (compat alias: `alvex`). From a source checkout: `PYTHONPATH=src python3 -m alvex.cli <command> ...`.
- **Python package:** `alvex_editor` (import/package name).
- Core modules (for programmatic use): `alvex_editor.config.load_config`, `alvex_editor.planner.build_plan`, `alvex_editor.audio.analyze_soundtrack`, `alvex_editor.align.align_project`/`write_manifest`, `alvex_editor.select.select_project`, `alvex_editor.renderer.render_timeline`, `alvex_editor.template.load_template`.

## Agent integration (portable)

Operations are exposed as **structured, non-interactive tools** over the same service API (`alvex_editor.api`):

- **MCP server (available, recommended for MCP clients):** `pip install -e ".[agent]"` then run `alvex-editor-mcp` (stdio; `python -m alvex_editor.mcp_server`) and register it with your agent. Tools: `project_status`, `template_info`, `analyze_soundtrack`, `plan_timeline`, `suggest_clip_mapping`, `suggest_inpoints`, `apply_manifest`, `render_video`. **Confirmation gates preserved:** `suggest_*` return suggestions with `requires_confirmation`; call `apply_manifest`/`apply=true` only after explicit user approval. `render_video` defaults `preview=true` (use `dry_run=true` to inspect; only disable preview/dry-run for an intentional final render).
- **CLI JSON mode (available, universal fallback):** `alvex-editor <command> --json` returns `{ok, command, ...}` so agents that can shell out can consume output reliably.
- **Canonical guide + adapters:** keep *this* document as the single source of truth. OpenCode skill, Cursor/Claude project instructions, and MCP prompts should reference or embed it.

## Adapters

### OpenCode
- Package this guide’s workflow as an OpenCode **skill** (thin wrapper) that instructs the agent to follow the steps above and to require explicit user confirmation before `--apply` and before non-dry-run `render`. If/when an `alvex-editor` MCP server is registered, prefer its typed tools over shelling out.

### Other agents / MCP clients
- Provide this file as context (`AGENTS.md`/project docs) or expose an MCP **prompt** (e.g., `create-video`) that returns this workflow. Map prompt/tool parameters to `alvex.yaml` fields and the artifact paths listed above.

## Troubleshooting cues
- **Overlay/newlines:** use `\n` in `variables.address`; renderer emits drawtext line breaks + `line_spacing`. Set `render.fontfile` for portability.
- **Cuts/timing:** tune `analysis.cut_points` (absolute segment-end boundaries, active segments in order) or use beat-grid snapping; re-`plan`. The song library caches detected onsets by soundtrack hash.
- **Render fails / SIGKILL (OOM):** common with 4K→preview concat on limited RAM; try `--preview`, fewer concurrent loads, or a machine with more memory; verify with `--dry-run` first.
- **ffmpeg/ffprobe missing:** install ffmpeg and ensure on `PATH` (or `FFMPEG`/`FFPROBE` env). Snap ffmpeg on Linux is supported (frame temps use a snap-visible dir).
- **Ollama/vision:** see `docs/ollama.md` (host/model/vision_model, `qwen3-vl:latest`, timeouts). AI steps are optional and confirm-gated.
