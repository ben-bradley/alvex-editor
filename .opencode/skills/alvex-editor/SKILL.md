# Skill: alvex-editor

# Alvex Editor (agent workflow)

Follow the **canonical guide**: `docs/alvex-editor-agent-guide.md`. Treat that document as the source of truth for steps, artifacts, and safety rules.

## Session start (required)
- **Confirm the visible workspace locations** with the user before intake/scaffolding: root `~/Alvex` (override `ALVEX_WORKSPACE`/`--workspace`) containing `templates/`, `soundtracks/`, `projects/`. Use `alvex-editor workspace --json` / MCP `workspace_info`. Propose the default if unset and record it only with explicit intent (`--save`). Never assume hidden/cache paths; keep locations obvious and outside the repo.

## Quick workflow (intake → preview → feedback → final)
1. **Intake (confirm with user):** parse/resolve `template` alias (→ registry; “standard real estate template” = `exterior-showcase`), `soundtrack` (registry/path; reuse curated cut points if registered, else plan to detect+map+confirm), `clips_dir`, `variables` (e.g. `address`, supports `\n`), project name/slug. All artifacts outside the repo under `~/Alvex/projects/<slug>/`.
2. **Scaffold (explicit):** `alvex-editor init --template ... --soundtrack ... --clips ... --address "..." --json` (MCP `init_project`). **Duplicate project:** in chat, ask the user what to do; non-interactive returns `requires_resolution` — retry with `--on-exists=overwrite|suffix` only per explicit choice. Never overwrite silently.
3. **Check status/tools:** `alvex-editor status -p <project>/alvex.yaml --json` (MCP `project_status`). ffmpeg/ffprobe required; Ollama optional.
4. **Analyze soundtrack:** reuse curated soundtrack registry cut points (map once, reuse) or `analyze --backend onsets`; `--refresh` recomputes detection. Explicit `analysis.cut_points`/`bpm` override. To reuse a song long-term, **work with the user to map/refine cut points, then save to the soundtrack registry only on explicit confirmation** (`soundtracks set-cuts` / `save_soundtrack_cut_points`).
5. **Plan:** `alvex-editor plan -p <project>/alvex.yaml --map-clips` → `output/timeline.json`.
6. **Suggest mapping/in-points (optional, AI, CONFIRM):** `align`/`select` (or MCP `suggest_*`) write *suggested* manifests. **Never auto-apply** — show results, get explicit user confirmation, then `--apply` / `apply_manifest`. Ollama config (e.g. `qwen3-vl:latest`) from `alvex.yaml`/flags.
7. **Render PREVIEW (explicit) + feedback:** `render --dry-run` or `--preview` → share `output/preview.mp4` and collect feedback. Iterate: adjust cut points (re-plan; optionally save confirmed cuts to registry), in-points/manifest, mappings, variables; re-preview until approved.
8. **Render FINAL (explicit intent only):** run non-preview final render only when the user clearly asks to export/finalize.

## Invocation (prefer structured tools)
- **MCP (if registered):** `workspace_info`, `list_templates`, `list_soundtracks`, `init_project`, `import_soundtrack`, `save_soundtrack_cut_points` (explicit confirmation), `project_status`, `template_info`, `analyze_soundtrack`, `plan_timeline`, `suggest_clip_mapping`, `suggest_inpoints`, `apply_manifest`, `render_video` (preserves confirmation gates; `render_video` defaults `preview=true`).
- **CLI fallback:** `alvex-editor <command> --json` (or `PYTHONPATH=src python3 -m alvex_editor.cli ...` from a source checkout).

## Rules
- **Permission guard:** do not create/edit/delete/move/rename/commit files in this repository without explicit user permission. State the intended change and get a clear go-ahead first (read-only inspection is allowed).
- Confirm workspace locations at session start; keep `templates/`, `soundtracks/`, `projects/` in a visible, user-chosen location outside the repo (default `~/Alvex`).
- AI (Ollama-only) is optional; suggestions and saved curated cut points require **human confirmation** before apply/save.
- Renders are explicit; preview-first; final only on explicit intent. On duplicate projects ask the user and use explicit `on_exists`.
- **Storage policy:** videos, soundtracks, thumbnails, and edit plans/manifests/analysis must be saved **outside the Alvex Editor codebase** (workspace satisfies this). Keep only the bundled example template `templates/exterior-showcase.md` in-repo.
- Prefer curated soundtrack registry cut points (map once, reuse) over re-detecting; hash onset cache is an internal optimization.
- Set `render.fontfile` for portable title rendering; `variables.address` supports `\n` (two-line centered overlay).

Base directory for this skill: C:\Users\ben\Development\alvex-editor\.opencode\skills\alvex-editor
Relative paths in this skill (e.g., scripts/, reference/) are relative to this base directory.
Note: file list is sampled.

<skill_files>
</skill_files>
