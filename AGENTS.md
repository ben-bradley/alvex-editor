# Agent instructions (Alvex Editor)

This repository contains **Alvex Editor** (`alvex-editor`), a template-driven, beat-aligned video production tool.

- **Canonical agent workflow:** read and follow [`docs/alvex-editor-agent-guide.md`](docs/alvex-editor-agent-guide.md). It is the portable source of truth (steps, artifacts, safety/confirmation gates).
- **OpenCode skill adapter:** [`.opencode/skills/alvex-editor/SKILL.md`](.opencode/skills/alvex-editor/SKILL.md).
- **Invocation:** prefer the MCP server (`alvex-editor-mcp`, install `[agent]`) or `alvex-editor <command> --json`. Service API: `alvex_editor.api`.
- **Safety:** AI suggestions (Ollama-only) are **never auto-applied**—require explicit user confirmation (`--apply` / `apply_manifest`). Prefer `render --dry-run`/`--preview`; final render only on explicit intent.

See [`README.md`](README.md) for setup and getting started. Point the tool at your existing Ollama model (e.g. `qwen3-vl:latest`) via `alvex.yaml` `ollama`.
