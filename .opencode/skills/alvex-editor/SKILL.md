# Skill: alvex-editor

Follow the **canonical guide**: [`docs/alvex-editor-agent-guide.md`](../../docs/alvex-editor-agent-guide.md). See [`README.md`](../../README.md) for chat UX setup (MCP + OpenWebUI).

## Session start (required)
- Confirm workspace: `~/Alvex` with `templates/`, `soundtracks/`, `projects/` (or chosen root). Use `alvex-editor workspace --json` / MCP `workspace_info`. Save only with explicit intent.
- If resuming: run `project_status`/`doctor`, read `alvex.json`, `project.brief.json` (if present), and latest timeline/analysis/manifests. Summarize state and ask only for missing/ambiguous inputs.

## Workflow (intake → preview → feedback → final)
1. **Intake**: Resolve template, soundtrack (reuse curated cuts if registered), clips dir, address, project name/slug. Confirm with user. Artifacts go to `~/Alvex/projects/<slug>/` outside repo.
2. **Init**: `alvex-editor init ... --json` or MCP `init_project`. If project exists, ask user and use explicit `--on-exists=overwrite|suffix`.
3. **Check**: `alvex-editor status -p <project>/alvex.json --json` and/or `doctor`. ffmpeg/ffprobe required. Ollama optional.
4. **Analyze**: Reuse curated cuts or `analyze --backend onsets`. Save curated cuts to registry **only on explicit confirmation**.
5. **Plan**: `alvex-editor plan -p <project>/alvex.json --map-clips`
6. **AI suggestions (optional, CONFIRM)**: `align`/`select` write suggestions; never auto-apply. Apply only with `--apply`/`apply_manifest`.
7. **Preview**: `alvex-editor render -p <project>/alvex.json --preview` (or `--dry-run`). Collect feedback, iterate, re-preview.
8. **Final**: Render only on explicit user intent: `alvex-editor render -p <project>/alvex.json`

## Invocation
- **MCP (primary)**: `workspace_info`, `list_templates`, `list_soundtracks`, `init_project`, `import_soundtrack`, `save_soundtrack_cut_points`, `project_status`, `doctor`, `template_info`, `analyze_soundtrack`, `plan_timeline`, `cuts_*`, `suggest_*`, `apply_manifest`, `render_video` (preview by default). Get config: `alvex-editor mcp`.
- **CLI**: `alvex-editor <command> --json` (also `PYTHONPATH=src python3 -m alvex_editor.cli ...`). Expect valid JSON on errors.

## Rules
- **No repo changes without permission.**
- **Workspace outside repo** (`~/Alvex`), only `templates/exterior-showcase.md` in-repo.
- **JSON only.** AI suggestions/curated cuts require confirmation. Preview first, final only on explicit intent.
- **Ollama optional** (core workflow works without it). Use project-aware render (`-p`); re-plan after changes.

Base directory for this skill: C:\Users\ben\Development\alvex-editor\.opencode\skills\alvex-editor
Relative paths in this skill (e.g., scripts/, reference/) are relative to this base directory.
Note: file list is sampled.

<skill_files>
</skill_files>
