# Agent instructions (Alvex Editor)

Template-driven, beat-aligned video production.

**Quick start:** See [`README.md`](README.md) for chat UX (MCP + OpenWebUI) setup.

**Rules:**
- **Canonical workflow:** Follow [`docs/alvex-editor-agent-guide.md`](docs/alvex-editor-agent-guide.md). OpenCode adapter: [`.opencode/skills/alvex-editor/SKILL.md`](.opencode/skills/alvex-editor/SKILL.md).
- **Invocation:** Prefer MCP server (`alvex-editor-mcp`, `[agent]`) or `alvex-editor <command> --json`. API: `alvex_editor.api`. Get config: `alvex-editor mcp`.
- **No repo changes without permission:** Don't create/edit/delete/move/rename/commit files in this repo without explicit user permission. Read-only inspection is fine.
- **Safety:** AI suggestions are **never auto-applied** (confirm with `--apply`/`apply_manifest`). Preview first (`--dry-run`/`--preview`), final render only on explicit intent. Use project-aware paths (`-p`) so config applies; re-plan after changes.
- **Formats:** **JSON only** for configs/manifests/registries/cut-points/analysis/timelines/briefs (`alvex.json`).
- **Storage:** All media/artifacts must go **outside the repo** (workspace `~/Alvex`). Only `templates/exterior-showcase.md` stays in-repo. `ALVEX_ALLOW_IN_REPO_WRITES=1` only for dev/tests.
- **AI:** Ollama optional (only for `align`/`select`). Core workflow works without it. See [`docs/ollama.md`](docs/ollama.md).
