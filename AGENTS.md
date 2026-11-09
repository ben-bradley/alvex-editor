# Agent instructions (Alvex Editor)

This repository contains **Alvex Editor** (`alvex-editor`), a template-driven, beat-aligned video production tool.

- **Canonical agent workflow:** read and follow [`docs/alvex-editor-agent-guide.md`](docs/alvex-editor-agent-guide.md). It is the portable source of truth (steps, artifacts, safety/confirmation gates).
- **OpenCode skill adapter:** [`.opencode/skills/alvex-editor/SKILL.md`](.opencode/skills/alvex-editor/SKILL.md).
- **Invocation:** prefer the MCP server (`alvex-editor-mcp`, install `[agent]`) or `alvex-editor <command> --json`. Service API: `alvex_editor.api`.
- **Permission guard (repo changes):** **Do not create, edit, delete, move, rename, or commit changes to files in this repository without explicit user permission.** Before making any repo change, state what you intend to change and why, and get a clear go-ahead in the conversation. Treat an explicit instruction to perform a specific change as permission for that change only. Read-only inspection (search/read/status/diff/log) is allowed.
- **Safety:** AI suggestions (Ollama-only) are **never auto-applied**—require explicit user confirmation (`--apply` / `apply_manifest`). Prefer `render --dry-run`/`--preview`; final render only on explicit intent. When rendering a project, rely on project-aware paths (`-p`/API) so `render`/`timing` config is applied and timelines stay fresh; re-plan after config/cut-point/manifest/soundtrack changes.
- **Format standard (project decision):** **JSON everywhere, JSON only.** Project configs are `alvex.json`; manifests/registries/cut-points/analysis/timelines/briefs are `.json`. Do not add or keep YAML artifacts in this codebase/workflows.
- **Storage policy:** **all videos, soundtracks, thumbnails, and edit plans/manifests/analysis must be saved outside the Alvex Editor codebase** (absolute paths or `~/...`). The app enforces this for writes; only the in-repo example template (`templates/exterior-showcase.md`) is kept in the repo. Use `ALVEX_ALLOW_IN_REPO_WRITES=1` only for local development/testing.

See [`README.md`](README.md) for setup and getting started. Point the tool at your existing Ollama model (e.g. `qwen3-vl:latest`) via `alvex.json` `ollama`.
