# Skill: alvex-editor

# Alvex Editor (agent workflow)

Follow the **canonical guide**: `docs/alvex-editor-agent-guide.md`. Treat that document as the source of truth for steps, artifacts, and safety rules.

## Session start (required)
- **Confirm the visible workspace locations** with the user before intake/scaffolding: root `~/Alvex` (override `ALVEX_WORKSPACE`/`--workspace`) containing `templates/`, `soundtracks/`, `projects/`. Use `alvex-editor workspace --json` / MCP `workspace_info`. Propose the default if unset and record it only with explicit intent (`--save`). Never assume hidden/cache paths; keep locations obvious and outside the repo.
- **Resume/new session:** if resuming a project, run `project_status`/`doctor` and read `project.brief.json` (if present) + project config (`alvex.json`) + latest timeline/analysis/manifests; summarize state and ask only for missing/ambiguous inputs or next explicit action.

## Quick workflow (intake → preview → feedback → final)
1. **Intake (confirm with user):** resolve `template` alias, `soundtrack` (registry/path; reuse curated cut points if registered, else detect+review+confirm-save), `clips_dir`, `variables.address` (supports `\n`), project name/slug, and per-project style/timing prefs (`render`/`timing`) as needed. All artifacts outside the repo under `~/Alvex/projects/<slug>/`.
2. **Scaffold (explicit):** `alvex-editor init ... --json` (MCP `init_project`). **Duplicate project:** ask the user; non-interactive returns `requires_resolution` — retry with `--on-exists=overwrite|suffix` only per explicit choice. Never overwrite silently.
3. **Check status/tools:** `alvex-editor status -p <project>/alvex.json --json` and/or `doctor --json -p ...` (MCP `project_status`/`doctor`). ffmpeg/ffprobe required; use `FFMPEG`/`FFPROBE` or `doctor` hints if not on PATH. Ollama optional.
4. **Analyze soundtrack:** reuse curated soundtrack registry cut points (map once, reuse) or `analyze --backend onsets`; `--refresh` recomputes detection. Explicit `analysis.cut_points`/`bpm` override. Save curated cuts to the registry **only on explicit confirmation** (`soundtracks set-cuts` / `save_soundtrack_cut_points`).
5. **Plan:** `alvex-editor plan -p <project>/alvex.json --map-clips` → `output/timeline.json` (plan merges existing sources manifest in/out points when present).
6. **Suggest mapping/in-points (optional, AI, CONFIRM):** `align`/`select` (or MCP `suggest_*`) write *suggested* manifests. **Never auto-apply** — show results, get explicit confirmation, then `--apply` / `apply_manifest`.
7. **Render PREVIEW (explicit) + feedback:** `render --dry-run` or `--preview` (`-p <project>`). With `-p` and no explicit `--timeline`, render re-plans from current config unless `--no-plan`. For cut-point tuning, use slot-labeled `cuts show` and `cuts nudge/suggest` (suggestions, confirm-gated, not applied) then explicit `cuts apply`/`cuts preview [--save-config]`. Share `output/preview.mp4` and collect feedback; iterate then re-preview until approved.
8. **Render FINAL (explicit intent only):** run non-preview final render only when the user clearly asks to export/finalize.

## Invocation (prefer structured tools)
- **MCP (if registered):** `workspace_info`, `list_templates`, `list_soundtracks`, `init_project`, `import_soundtrack`, `save_soundtrack_cut_points` (explicit confirmation), `project_status`, `doctor`, `template_info`, `analyze_soundtrack`, `plan_timeline`, `cuts_show`/`cuts_suggest`/`cuts_nudge` (suggestions, confirm-gated) / `cuts_apply`/`cuts_preview` (explicit), `suggest_clip_mapping`, `suggest_inpoints`, `apply_manifest`, `render_video` (preserves confirmation gates; `render_video` defaults `preview=true`; re-plans from current config when `project` given and `timeline` omitted unless `no_plan`).
- **CLI fallback:** `alvex-editor <command> --json` (or `PYTHONPATH=src python3 -m alvex_editor.cli ...` from a source checkout). Expect valid JSON in `--json` mode.

## Rules
- **Permission guard:** do not create/edit/delete/move/rename/commit files in this repository without explicit user permission. State the intended change and get a clear go-ahead first (read-only inspection is allowed).
- Confirm workspace locations at session start; keep `templates/`, `soundtracks/`, `projects/` in a visible, user-chosen location outside the repo (default `~/Alvex`).
- AI (Ollama-only) is optional; suggestions and saved curated cut points require **human confirmation** before apply/save.
- Renders are explicit; preview-first; final only on explicit intent. Use project-aware render so `render`/`timing` config applies; re-plan/refresh after config/cut-point/manifest/soundtrack changes (explicit `--timeline` means use that exact timeline). On duplicate projects ask the user and use explicit `on_exists`.
- **Storage policy:** videos, soundtracks, thumbnails, and edit plans/manifests/analysis must be saved **outside the Alvex Editor codebase** (workspace satisfies this). Keep only the bundled example template `templates/exterior-showcase.md` in-repo.
- **Format standard:** **JSON everywhere, JSON only.** Configs, manifests, registries, cut-points, analysis, timelines, and briefs are `.json`. Do not add YAML artifacts.
- Prefer curated soundtrack registry cut points (map once, reuse) over re-detecting; hash onset cache is an internal optimization.
- Set `render.fontfile` for portable title rendering; `variables.address` supports `\n` (two-line centered overlay). If ffmpeg is “installed but missing”, run `doctor` and set `FFMPEG`/`FFPROBE` if needed.

Base directory for this skill: C:\Users\ben\Development\alvex-editor\.opencode\skills\alvex-editor
Relative paths in this skill (e.g., scripts/, reference/) are relative to this base directory.
Note: file list is sampled.

<skill_files>
</skill_files>
