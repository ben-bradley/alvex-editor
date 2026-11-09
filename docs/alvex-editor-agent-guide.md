# Alvex Editor — Agent Guide (canonical, portable)

This is the **canonical, agent-agnostic** workflow for producing videos with Alvex Editor through a chat/AI agent. It is portable across runtimes (OpenCode, other chat agents, future MCP clients). Platform-specific “skills” should be **thin adapters** that point to this guide rather than duplicating it.

## What Alvex does

Template-driven, beat-aligned video production (primary use case: real-estate exterior showcase).

**Pipeline (deterministic given resolved inputs):** template + clips + soundtrack → analyze soundtrack for pacing/transition points → resolve a timeline → (optionally) map clips & select in-points → render with intro/outro, titles/overlays, audio → review/export.

**Key artifacts (file-backed, inspectable):**
- `alvex.json` / project config — template, soundtrack, `clips_dir`, `output_dir`, `analysis`, `ollama`, `render`, `timing`, `variables`. Paths resolve relative to the config file. **All videos, soundtracks, thumbnails, and edit plans/manifests/analysis (and project configs/outputs) must be saved outside the Alvex Editor codebase** (use absolute paths or `~/...`; the app rejects protected writes inside the repo). The in-repo `templates/exterior-showcase.md` is the allowed bundled example template.
- `analysis.json` (project cache) — beat/onset grid (`method`, `duration`, `beat_times`, `cut_points`). May be seeded from a **curated soundtrack registry reference** (preferred, user-confirmed) or the hash-keyed onset library/cache.
- `timeline.json` — resolved plan (`analysis` + per-segment `resolved_duration`, `timeline_in/out`, `source` mapping/status, transitions/effects/overlays).
- `sources.suggested.*` / `sources.selected.suggested.*` → **applied sources manifest (human-confirmed)** — `slot_id -> {path, in_point, out_point}` plus suggestion metadata.
- `preview.mp4` / `final.mp4`.

**Format standard (decision): JSON everywhere, JSON only.** Configs, registries, manifests, cut-points, analysis, timelines, and briefs are `.json`. Do not add or keep YAML artifacts. Legacy YAML project/workspace data outside the repo must be converted to JSON to work with current tooling.

## Workspace & registries (visible, outside the repo)

**Everything the user works with lives in an obvious, user-visible workspace outside the codebase** (not hidden dotfolders, not app-cache). The user can browse/edit these directly.

**Default workspace root:** `~/Alvex` (override via `ALVEX_WORKSPACE` or `--workspace`). Canonical layout (grouped):

```text
~/Alvex/
  templates/                 # template registry (user *.md templates + optional registry.json)
  soundtracks/               # soundtrack registry (self-contained)
    registry.json            # id/aliases -> imported file, title, tags
    <id>/
      <track>.mp3            # imported/copied into the registry
      cut-points.json        # CURATED, human-confirmed reference (authoritative, reusable)
  projects/                  # one folder per video/job
    <project-slug>/
      alvex.json
      output/                # analysis.json, timeline.json, manifests, preview.mp4, final.mp4
```

### Template registry
- **Bundled:** in-repo `templates/exterior-showcase.md` (kept in-repo as the example).
- **User library:** `~/Alvex/templates/` (outside repo). Users add templates here alongside real-estate for other project types.
- **Aliases:** e.g. `standard real estate template` / `exterior showcase` / `real-estate` → `exterior-showcase`.
- **Resolution (deterministic):** explicit path → project-relative → workspace `templates/` → bundled. CLI: `alvex-editor templates --json`. MCP: `list_templates`.

### Soundtrack registry (curated, map once — reuse)
- **Registry:** `~/Alvex/soundtracks/` is self-contained — MP3s are **copied/imported** into `soundtracks/<id>/` and indexed in `registry.json`.
- **Curated cut-point reference:** `soundtracks/<id>/cut-points.json` stores **human-confirmed** `cut_points` (and/or `bpm`/`offset`/`beat_times`, provenance). This is the **authoritative, reusable** reference: map once, reuse across projects.
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
- **Ollama-only for AI.** Configure `ollama` in `alvex.json` (e.g., `model`/`vision_model: qwen3-vl:latest`). See `docs/ollama.md`. Vision labeling/extraction uses `ffmpeg`.

## New project intake checklist (one-pass where possible)
Gather/confirm before writes (ask only for missing/ambiguous inputs):
1. **Workspace confirmed**: `~/Alvex` (or chosen root) with `templates/`, `soundtracks/`, `projects/` (`workspace --json` / `workspace_info`).
2. **Template**: alias or path (e.g. `standard real estate template` / `exterior-showcase`) resolved.
3. **Soundtrack**: registry id/path/file; if registered, report whether **curated cut points** will be reused; if not registered and reuse is desired, plan detect → review with user → save curated cuts only on explicit confirmation.
4. **Clips**: `clips_dir` path verified.
5. **Property/variables**: `variables.address` (supports `\n` for two-line overlay).
6. **Style/timing prefs (per-project, optional)**: overlay position/alignment/font (`render.title_x/title_y/text_align/fontfile`), color/vibrancy filters (`render.video_filters`), intro/outro video+audio fade prefs (`timing.*`, including decoupled audio fade `outro_audio_fade_out_before_end_seconds`).
7. **Project identity**: name/slug and target folder under `~/Alvex/projects/`.
8. **Scaffold (explicit)**: `init` / `init_project`. If project exists, **ask the user** and retry only with explicit `--on-exists=overwrite|suffix`.

## Resume / new session (start here)
1. `workspace_info`/`workspace --json`, `list_templates`, `list_soundtracks`.
2. If resuming a project: `project_status -p <project>/alvex.json|alvex.json --json` (and `doctor --json -p ...` if tools are in doubt). Read `project.brief.json` if present (created by `init`; optional resume aid), plus project config and latest `timeline.json`/analysis/manifests as needed.
3. Summarize state (template/soundtrack + curated-cuts status, clips count, timeline/mapped, manifest, resolved ffmpeg/ffprobe, last outputs) and ask only for missing/ambiguous inputs or next explicit action.

## Chat workflow (recommended)

### 0. **Confirm workspace locations (session start, required)**
- Confirm `~/Alvex` (or chosen root) and that you can find `templates/`, `soundtracks/`, `projects/`. `alvex-editor workspace --json` / MCP `workspace_info`. If unset, propose the default visible layout and get confirmation; `--save`/`save=true` records it (explicit intent). If ffmpeg/ffprobe may be missing, run `alvex-editor doctor --json` / MCP `doctor`.

### 1. **Intake — gather & confirm inputs (natural language → structured)**
Example: “new real estate video, 123 Main St Little Rock AR, song `bensound-acousticbreeze.mp3`, clips `~/projects/123-main-street-little-rock`, standard real estate template.”
- Resolve and **confirm** with the user: `template` alias → registry path; `soundtrack` (registry id/path/file; import to registry if desired) → path + **curated cut points reused if registered** (or plan to detect/map-confirm); `clips_dir`; `variables.address` (supports `\n`); project slug/name and target folder under `~/Alvex/projects/`; and any per-project style/timing prefs.
- **Scaffold** (explicit): `alvex-editor init --template "standard real estate template" --soundtrack ... --clips ... --address "..." --json` or MCP `init_project`. Creates project config + `output/` outside the repo. If the project exists, **ask the user** and retry with `--on-exists=overwrite|suffix`.

### 2. **Check status/tools**
- `alvex-editor status -p <project>/alvex.json --json` (MCP `project_status`) and/or `alvex-editor doctor --json -p <project>/alvex.json` (MCP `doctor`). Ensure ffmpeg/ffprobe available (`FFMPEG`/`FFPROBE` env or PATH; Windows WinGet locations are probed). Ollama optional.

### 3. **Analyze soundtrack (reuse curated/library)**
- `alvex-editor analyze -p <project>/alvex.json --backend onsets` (seeds/refreshes detection) or default to reuse curated ref/library. `--refresh` recomputes detection. Explicit `analysis.cut_points`/`bpm` in config override detection.
- If **no curated cut points** exist for a chosen song and the user wants reuse: detect, **work with the user to map/refine cut points**, show them for review, then on explicit confirmation save to the soundtrack registry (`soundtracks set-cuts` / `save_soundtrack_cut_points`).
- See `docs/audio-analysis.md`.

### 4. **Plan the timeline**
```bash
alvex-editor plan -p <project>/alvex.json --map-clips
```
Review segment count, mapped/unmapped, and timing.

### 5. **Suggest clip mapping / in-points (optional, AI, CONFIRM)**
```bash
alvex-editor align -p <project>/alvex.json [--vision]   # suggested, review required
alvex-editor align -p <project>/alvex.json [--vision] --apply   # explicit confirmation
alvex-editor select -p <project>/alvex.json [--vision]  # suggested, review required
alvex-editor select -p <project>/alvex.json [--vision] --apply
```
**Never auto-apply.** Edit manifest `in_point`/mappings directly as needed.

### 6. **Render PREVIEW (explicit) and collect feedback**
```bash
alvex-editor render -p <project>/alvex.json --dry-run
alvex-editor render -p <project>/alvex.json --preview   # -> output/preview.mp4
```
Share the preview location/summary and **ask for feedback**.

### 7. **Iterate on feedback**
Adjust `analysis.cut_points`/`timing`/`render`/soundtrack/manifest/in-points/mappings as needed. Use **slot-labeled cut points** (`cuts show --json`, Features/optional-skipped aware) to avoid ambiguity. For musical patterns, `cuts nudge --near <t> --to second-of-pair` (or `cuts suggest --second-of-pair`) returns **suggestions (confirm-gated, not applied)**; review then apply explicitly (`cuts apply --cut-points ...`) and/or `cuts preview --cut-points ... [--save-config]` (explicit one-step re-plan + preview using project render config/fresh timeline). **Project-aware render behavior:** with `-p <project>` and no explicit `--timeline`, render re-plans from current config and merges the sources manifest. Explicit `--timeline` uses that exact timeline. `plan` merges an existing sources manifest (preserves explicit in/out points). Re-render **preview** until approved. Optionally **save confirmed cuts to the soundtrack registry** (explicit, confirmed).

### 8. **Render FINAL (explicit intent only)**
Only when the user clearly asks to export/finalize:
```bash
alvex-editor render -p <project>/alvex.json   # -> output/final.mp4
```

## Current invocation (today)

- **CLI:** `alvex-editor <command> ...` (compat alias: `alvex`). `--json` on all commands (errors should be valid JSON in `--json` mode). Key commands: `workspace`, `doctor`, `init`, `templates`, `soundtracks {list,import,set-cuts}`, `status`, `template`, `analyze`, `cuts {show,suggest,nudge,apply,preview}`, `plan`, `align`, `select`, `render`. From a source checkout: `PYTHONPATH=src python3 -m alvex_editor.cli ...`.
- **Python package:** `alvex_editor` (import/package name). Service API: `alvex_editor.api`.
- Core modules: `alvex_editor.workspace`, `alvex_editor.registry`, `alvex_editor.config.load_config`, `alvex_editor.planner.build_plan`, `alvex_editor.audio.analyze_soundtrack`, `alvex_editor.align.align_project`/`write_manifest`, `alvex_editor.select.select_project`, `alvex_editor.renderer.render_timeline`.

## Agent integration (portable)

Operations are exposed as **structured, non-interactive tools** over the same service API (`alvex_editor.api`):

- **MCP server (recommended for MCP clients):** `pip install -e ".[agent]"` then run `alvex-editor-mcp` (stdio). Tools include: `workspace_info`, `list_templates`, `list_soundtracks`, `init_project`, `import_soundtrack`, `save_soundtrack_cut_points` (explicit confirmation), `project_status`, `doctor`, `template_info`, `analyze_soundtrack`, `plan_timeline`, `cuts_show`/`cuts_suggest`/`cuts_nudge` (suggestions, confirm-gated) and `cuts_apply`/`cuts_preview` (explicit actions; `cuts_preview` saves config only with `save_config=true`), `suggest_clip_mapping`, `suggest_inpoints`, `apply_manifest`, `render_video`. **Confirmation gates preserved:** suggestions require confirmation before apply/save; `render_video` defaults `preview=true` (final only on explicit intent). Project-aware render/preview re-plans from current config unless `no_plan=true`. `init_project` on duplicate returns `requires_resolution` — ask the user, then retry with explicit `on_exists`.
- **CLI JSON mode (universal fallback):** `alvex-editor <command> --json` returns `{ok, command, ...}` and should emit valid JSON on errors.
- **Canonical guide + adapters:** keep *this* document as the single source of truth. OpenCode skill and other adapters reference it.

## Adapters

### OpenCode
- The OpenCode **skill** is a thin wrapper that instructs the agent to follow this guide: confirm workspace locations at session start, confirm intake, never auto-apply AI/saved cut points, ask on duplicate projects, preview-first and iterate on feedback, final render only on explicit intent. Prefer MCP typed tools when registered.

### Other agents / MCP clients
- Provide this file as context or expose an MCP prompt that returns this workflow. Map parameters to the visible workspace layout, registries, and `alvex.json`/artifact paths above.

## Sharp edges (avoid these)
- **Project-aware render/config:** when a project has `render`/`timing` config, use project-aware render (`-p`/MCP/`api.render(project=...)`). Do not call `build_render_plan(..., RenderOptions(...))` with raw defaults for a configured project.
- **Stale timeline/config changes:** after changing config/cut points/timing/render/soundtrack/manifest/in-points, re-plan or render with `-p` (no explicit `--timeline`) so state is fresh. Passing an explicit `--timeline` uses that exact timeline.
- **Manifest vs timeline:** sources manifest is authoritative for explicit trims/mappings when applied; `plan` merges an existing sources manifest into the planned timeline. A missing auto-resolved manifest is optional if timeline mappings/in-points are sufficient; an explicitly provided missing manifest is an error.
- **ffmpeg installed but not found:** run `doctor --json` / `status --json` for resolved paths and hints; set `FFMPEG`/`FFPROBE` (or `ALVEX_FFMPEG`/`ALVEX_FFPROBE`) to full executables (Windows WinGet installs are probed).
- **`--json` mode:** expect valid JSON (including errors). If a tool prints non-JSON, treat as a bug and use `doctor/status`/non-JSON logs to diagnose.

## Config validation, presets, and overrides (Phase 4)
- **Validation:** config load performs lightweight schema checks. Invalid values/types in `render`/`timing`/`analysis` (and key shapes) fail with clear errors; unknown keys warn. Use `--json`/status to surface issues.
- **Style presets:** set `preset`/`style_preset` to a name resolved from `project_dir/presets/`, `project_dir/`, or workspace `~/Alvex/presets/<name>.json` (JSON). Project config wins over preset; `render`/`timing`/`variables`/`analysis`/`ollama` merge deeply (project keys override).
- **Segment overrides (sensible subset):** `segment_overrides`/`slot_overrides` keyed by `slot_id` can set `in_point`/`out_point`/`path` (or `source.{...}`), `optional`, and duration hints (`target|min|max_duration`). Sources manifest merge can still override explicit trims/mappings when applied.

## Troubleshooting cues
- **Overlay/newlines:** use `\n` in `variables.address`; renderer emits drawtext line breaks + `line_spacing`. Set `render.fontfile` for portability.
- **Cuts/timing:** prefer curated soundtrack registry cut points (reusable). Tune `analysis.cut_points` or use beat-grid snapping; re-`plan`/project render refreshes timing. Save confirmed cuts to the registry for future projects.
- **Render fails / SIGKILL (OOM):** common with 4K→preview concat on limited RAM; try `--preview`, fewer concurrent loads, or more memory; verify with `--dry-run` first.
- **ffmpeg/ffprobe missing:** `doctor --json` for resolution/hints; install ffmpeg and ensure on `PATH` (or `FFMPEG`/`FFPROBE` env).
- **Ollama/vision:** see `docs/ollama.md`. AI steps are optional and confirm-gated.
- **Path policy:** artifacts/projects must be outside the codebase (workspace `~/Alvex` satisfies this). `ALVEX_ALLOW_IN_REPO_WRITES=1` only for local dev/tests.
