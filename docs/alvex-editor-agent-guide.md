# Alvex Editor — Agent Guide (canonical, portable)

This is the **canonical, agent-agnostic** workflow for producing videos with Alvex Editor through a chat/AI agent. It is portable across runtimes (OpenCode, other chat agents, future MCP clients). Platform-specific “skills” should be **thin adapters** that point to this guide rather than duplicating it.

## What Alvex does

Template-driven, beat-aligned video production (primary use case: real-estate exterior showcase).

**Pipeline (deterministic given resolved inputs):** template + clips + soundtrack → analyze soundtrack for pacing/transition points → resolve a timeline → (optionally) map clips & select in-points → render with intro/outro, titles/overlays, audio → review/export.

**Key artifacts (file-backed, inspectable):**
- `alvex.yaml` — project config (template, soundtrack, `clips_dir`, `output_dir`, `analysis`, `ollama`, `render`, `variables`). Paths resolve relative to the config file. **All videos, soundtracks, thumbnails, and edit plans/manifests/analysis (and project configs/outputs) must be saved outside the Alvex Editor codebase** (use absolute paths or `~/...`; the app rejects protected writes inside the repo). The in-repo `templates/exterior-showcase.md` is the allowed bundled example template.
- `analysis.json` (project cache) — beat/onset grid (`method`, `duration`, `beat_times`, `cut_points`). May be seeded from a **curated soundtrack registry reference** (preferred, user-confirmed) or the hash-keyed onset library/cache.
- `timeline.json` — resolved plan (`analysis` + per-segment `resolved_duration`, `timeline_in/out`, `source` mapping/status, transitions/effects/overlays).
- `sources.suggested.yaml` / `sources.selected.suggested.yaml` → **`sources.yaml` (applied, human-confirmed)** — `slot_id -> {path, in_point, out_point}` plus suggestion metadata.
- `preview.mp4` / `final.mp4`.

## Workspace & registries (visible, outside the repo)

**Everything the user works with lives in an obvious, user-visible workspace outside the codebase** (not hidden dotfolders, not app-cache). The user can browse/edit these directly.

**Default workspace root:** `~/Alvex` (override via `ALVEX_WORKSPACE` or `--workspace`). Canonical layout (grouped):

```text
~/Alvex/
  templates/                 # template registry (user *.md templates + optional registry.yaml)
  soundtracks/               # soundtrack registry (self-contained)
    registry.yaml            # id/aliases -> imported file, title, tags
    <id>/
      <track>.mp3            # imported/copied into the registry
      cut-points.yaml        # CURATED, human-confirmed reference (authoritative, reusable)
  projects/                  # one folder per video/job
    <project-slug>/
      alvex.yaml
      output/                # analysis.json, timeline.json, manifests, preview.mp4, final.mp4
```

### Template registry
- **Bundled:** in-repo `templates/exterior-showcase.md` (kept in-repo as the example).
- **User library:** `~/Alvex/templates/` (outside repo). Users add templates here alongside real-estate for other project types.
- **Aliases:** e.g. `standard real estate template` / `exterior showcase` / `real-estate` → `exterior-showcase`.
- **Resolution (deterministic):** explicit path → project-relative → workspace `templates/` → bundled. CLI: `alvex-editor templates --json`. MCP: `list_templates`.

### Soundtrack registry (curated, map once — reuse)
- **Registry:** `~/Alvex/soundtracks/` is self-contained — MP3s are **copied/imported** into `soundtracks/<id>/` and indexed in `registry.yaml`.
- **Curated cut-point reference:** `soundtracks/<id>/cut-points.yaml` stores **human-confirmed** `cut_points` (and/or `bpm`/`offset`/`beat_times`, provenance). This is the **authoritative, reusable** reference: map once, reuse across projects.
- **How it’s produced:** seed candidates via onset detection (`analyze --backend onsets` / hash library), work with the user to refine boundaries, then **save only on explicit confirmation** (`alvex-editor soundtracks set-cuts ...` or MCP `save_soundtrack_cut_points`). Agent must confirm cut points with the user before saving.
- **Reuse:** project init/config resolves the registered soundtrack and applies curated `cut_points` as explicit `analysis.cut_points` (deterministic). Explicit per-project `analysis.cut_points`/`bpm`/`beat_times` always win. The hash-keyed onset detection cache (`~/.cache/alvex/analysis/...`, internal optimization) may still be used for detection seeding, but the **user-facing source of truth** is the curated file in `~/Alvex/soundtracks/`.
- CLI: `alvex-editor soundtracks [list|import|set-cuts] --json`. MCP: `list_soundtracks`, `import_soundtrack`, `save_soundtrack_cut_points`.

## Safety & human confirmation (required)

- **No repo changes without explicit permission.** Agents must not create, edit, delete, move, rename, or commit files in this repository without explicit user permission. State the intended change and get a clear go-ahead first (an explicit instruction for a specific change grants permission for that change only). Read-only inspection is allowed.
- **Session start / workspace locations:** before intake or scaffolding, **confirm the workspace root and `templates/`, `soundtracks/`, `projects/` locations** with the user (and record them in workspace config if appropriate, with permission). Never assume hidden paths; keep locations obvious. Create directories/files **outside the repo** only with explicit user intent/permission.
- **AI suggestions are never auto-applied.** `align` (clip→slot mapping) and `select` (in-point) write *suggested* manifests for review and only write the target manifest when explicitly confirmed (`--apply`).
- **Curated soundtrack cut points are saved only on explicit confirmation** after review with the user.
- **Rendering is explicit.** Prefer `--dry-run` or `--preview` first; full renders can be resource-intensive (4K sources). **Final render only on explicit user intent.**
- **Duplicate projects (non-interactive/CLI/MCP):** `init` defaults to `on_exists=fail` and returns `requires_resolution` + options (`overwrite`/`suffix`/`cancel`). In chat, **ask the user what to do**, then retry with an explicit choice (`--on-exists=overwrite|suffix`). Never overwrite silently.
- **Ollama-only for AI.** Configure `ollama` in `alvex.yaml` (e.g., `model`/`vision_model: qwen3-vl:latest`). See `docs/ollama.md`. Vision labeling/extraction uses `ffmpeg`.

## Chat workflow (recommended)

### 0. **Confirm workspace locations (session start, required)**
- Confirm `~/Alvex` (or chosen root) and that you can find `templates/`, `soundtracks/`, `projects/`. `alvex-editor workspace --json` / MCP `workspace_info`. If unset, propose the default visible layout and get confirmation; `--save`/`save=true` records it (explicit intent).

### 1. **Intake — gather & confirm inputs (natural language → structured)**
Example: “new real estate video, 123 Main St Little Rock AR, song `bensound-acousticbreeze.mp3`, clips `~/projects/123-main-street-little-rock`, standard real estate template.”
- Resolve and **confirm** with the user: `template` alias → registry path; `soundtrack` (registry id/path/file; import to registry if desired) → path + **curated cut points reused if registered** (or plan to detect/map-confirm); `clips_dir`; `variables.address` (supports `\n`); project slug/name and target folder under `~/Alvex/projects/`.
- **Scaffold** (explicit): `alvex-editor init --template "standard real estate template" --soundtrack ... --clips ... --address "..." --json` or MCP `init_project`. Creates `~/Alvex/projects/<slug>/alvex.yaml` + `output/` outside the repo. If the project exists, **ask the user** and retry with `--on-exists=overwrite|suffix`.

### 2. **Check status/tools**
- `alvex-editor status -p <project>/alvex.yaml --json` (MCP `project_status`). Ensure ffmpeg/ffprobe available; Ollama optional.

### 3. **Analyze soundtrack (reuse curated/library)**
- `alvex-editor analyze -p <project>/alvex.yaml --backend onsets` (seeds/refreshes detection) or default to reuse curated ref/library. `--refresh` recomputes detection. Explicit `analysis.cut_points`/`bpm` in config override detection.
- If **no curated cut points** exist for a chosen song and the user wants reuse: detect, **work with the user to map/refine cut points**, show them for review, then on explicit confirmation save to the soundtrack registry (`soundtracks set-cuts` / `save_soundtrack_cut_points`).
- See `docs/audio-analysis.md`.

### 4. **Plan the timeline**
```bash
alvex-editor plan -p <project>/alvex.yaml --map-clips
```
Review segment count, mapped/unmapped, and timing.

### 5. **Suggest clip mapping / in-points (optional, AI, CONFIRM)**
```bash
alvex-editor align -p <project>/alvex.yaml [--vision]   # suggested, review required
alvex-editor align -p <project>/alvex.yaml [--vision] --apply   # explicit confirmation
alvex-editor select -p <project>/alvex.yaml [--vision]  # suggested, review required
alvex-editor select -p <project>/alvex.yaml [--vision] --apply
```
**Never auto-apply.** Edit manifest `in_point`/mappings directly as needed.

### 6. **Render PREVIEW (explicit) and collect feedback**
```bash
alvex-editor render -p <project>/alvex.yaml --dry-run
alvex-editor render -p <project>/alvex.yaml --preview   # -> output/preview.mp4
```
Share the preview location/summary and **ask for feedback**.

### 7. **Iterate on feedback**
Adjust `analysis.cut_points` (re-plan) — and optionally **save confirmed cuts back to the soundtrack registry** (explicit, confirmed) — adjust in-points/manifest (re-`select`/apply or edit), remap clips (re-`align`/apply), or edit `variables.address`/render settings; re-`plan` as needed, then re-render **preview**. Repeat until approved.

### 8. **Render FINAL (explicit intent only)**
Only when the user clearly asks to export/finalize:
```bash
alvex-editor render -p <project>/alvex.yaml   # -> output/final.mp4
```

## Current invocation (today)

- **CLI:** `alvex-editor <command> ...` (compat alias: `alvex`). `--json` on all commands. Key commands: `workspace`, `init`, `templates`, `soundtracks {list,import,set-cuts}`, `status`, `template`, `analyze`, `plan`, `align`, `select`, `render`. From a source checkout: `PYTHONPATH=src python3 -m alvex_editor.cli ...`.
- **Python package:** `alvex_editor` (import/package name). Service API: `alvex_editor.api`.
- Core modules: `alvex_editor.workspace`, `alvex_editor.registry`, `alvex_editor.config.load_config`, `alvex_editor.planner.build_plan`, `alvex_editor.audio.analyze_soundtrack`, `alvex_editor.align.align_project`/`write_manifest`, `alvex_editor.select.select_project`, `alvex_editor.renderer.render_timeline`.

## Agent integration (portable)

Operations are exposed as **structured, non-interactive tools** over the same service API (`alvex_editor.api`):

- **MCP server (recommended for MCP clients):** `pip install -e ".[agent]"` then run `alvex-editor-mcp` (stdio). Tools include: `workspace_info`, `list_templates`, `list_soundtracks`, `init_project`, `import_soundtrack`, `save_soundtrack_cut_points` (explicit confirmation), `project_status`, `template_info`, `analyze_soundtrack`, `plan_timeline`, `suggest_clip_mapping`, `suggest_inpoints`, `apply_manifest`, `render_video`. **Confirmation gates preserved:** suggestions require confirmation before apply; `save_soundtrack_cut_points` only after user confirms cuts; `render_video` defaults `preview=true` (final only on explicit intent). `init_project` on duplicate returns `requires_resolution` — ask the user, then retry with explicit `on_exists`.
- **CLI JSON mode (universal fallback):** `alvex-editor <command> --json` returns `{ok, command, ...}`.
- **Canonical guide + adapters:** keep *this* document as the single source of truth. OpenCode skill and other adapters reference it.

## Adapters

### OpenCode
- The OpenCode **skill** is a thin wrapper that instructs the agent to follow this guide: confirm workspace locations at session start, confirm intake, never auto-apply AI/saved cut points, ask on duplicate projects, preview-first and iterate on feedback, final render only on explicit intent. Prefer MCP typed tools when registered.

### Other agents / MCP clients
- Provide this file as context or expose an MCP prompt that returns this workflow. Map parameters to the visible workspace layout, registries, and `alvex.yaml`/artifact paths above.

## Troubleshooting cues
- **Overlay/newlines:** use `\n` in `variables.address`; renderer emits drawtext line breaks + `line_spacing`. Set `render.fontfile` for portability.
- **Cuts/timing:** prefer curated soundtrack registry cut points (reusable). Tune `analysis.cut_points` or use beat-grid snapping; re-`plan`. Save confirmed cuts to the registry for future projects.
- **Render fails / SIGKILL (OOM):** common with 4K→preview concat on limited RAM; try `--preview`, fewer concurrent loads, or more memory; verify with `--dry-run` first.
- **ffmpeg/ffprobe missing:** install ffmpeg and ensure on `PATH` (or `FFMPEG`/`FFPROBE` env).
- **Ollama/vision:** see `docs/ollama.md`. AI steps are optional and confirm-gated.
- **Path policy:** artifacts/projects must be outside the codebase (workspace `~/Alvex` satisfies this). `ALVEX_ALLOW_IN_REPO_WRITES=1` only for local dev/tests.
