# Alvex Editor

Template-driven, beat-aligned video production (primary use case: real-estate exterior showcase). Produces deterministic timelines and renders with FFmpeg. Can be driven from the CLI, as a Python API, or by AI agents (MCP / `--json`) — **AI suggestions require human confirmation**.

## Quick start (chat UX in fewest steps)

1. **Prerequisites**: Python 3.11+, [FFmpeg](https://ffmpeg.org/download.html) on PATH (or set `FFMPEG`/`FFPROBE`). [Docker](https://www.docker.com/) for OpenWebUI (recommended). Ollama optional.
2. **Install Alvex with MCP support**:
```bash
pip install -e ".[analysis,agent]"
```
3. **Set up workspace & check tools**:
```bash
alvex-editor workspace --save --json
alvex-editor doctor --json
```
4. **Start OpenWebUI + connect MCP (chat UX)**:
```bash
# Run OpenWebUI
docker run -d --name openwebui -p 3000:8080 -v openwebui-data:/app/backend/data --add-host=host.docker.internal:host-gateway ghcr.io/open-webui/open-webui:main
```
Open http://localhost:3000, create admin account. **Configure a model** (OpenWebUI requires one): install [Ollama](https://ollama.com/), pull a model (`ollama pull llama-3.1`), and add it in Admin → Settings → Connections (point to `http://host.docker.internal:11434`). Or use an OpenAI-compatible provider.

Then add the MCP server:
- Get config: `alvex-editor mcp` (or see [`docs/openwebui-docker.md`](docs/openwebui-docker.md))
- In OpenWebUI: Admin → Settings → Tools → MCP Servers → Add Server (stdio)
- Command: `python` (or your venv python), Args: `["-m", "alvex_editor.mcp_server"]`
- *Tip for Docker*: running MCP on the host is easiest for file access. If you run both in Docker, mount `~/Alvex` and your clips directories as volumes.

5. **Chat with Alvex**: In OpenWebUI, start a new chat and use the Alvex MCP tools. Tell it: "Start a new real estate video project..." and it will guide you through intake (template, soundtrack, clips, address), plan, preview, and final render. All files go to `~/Alvex/` outside the repo.

**Notes:** Core workflow works without Ollama. AI features need Ollama if used. See [`docs/alvex-editor-agent-guide.md`](docs/alvex-editor-agent-guide.md) for the full agent workflow.

## Getting started (detailed)

### Prerequisites
- **Python >= 3.11**
- **FFmpeg** (`ffmpeg` + `ffprobe`) on `PATH` (or set `FFMPEG`/`FFPROBE`)
- **Ollama (optional, for AI mapping/in-point selection):** point to your existing model (e.g., `qwen3-vl:latest`). Not required for core workflow.

### Install
```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows (PowerShell): .venv\Scripts\Activate.ps1

# Minimal + analysis + MCP
pip install -e ".[analysis,agent]"

# Or from PyPI when published: pip install alvex-editor[analysis,agent]
```

### Workspace & registries (visible, outside the repo)
Default root: `~/Alvex` (override `ALVEX_WORKSPACE` / `--workspace`):
```text
~/Alvex/
  templates/      # user templates (*.md)
  soundtracks/    # imported MP3s + curated cut-points.json (map once, reuse)
  projects/       # one folder per video job (<slug>/alvex.json + output/)
```

```bash
alvex-editor workspace --json [--save]                 # confirm locations
alvex-editor doctor --json [ -p <project>/alvex.json ]  # ffmpeg/ffprobe hints
alvex-editor templates --json                           # bundled + workspace templates
alvex-editor soundtracks list --json
alvex-editor soundtracks import /path/to/song.mp3 --track-id acoustic-breeze --json
alvex-editor soundtracks set-cuts acoustic-breeze --cut-points 10.82,19.3,... --json   # explicit confirmation
```

### Start a project (`init`) and run the workflow (CLI)
`alvex-editor` is the CLI (`alvex` alias). All work is outside the repo. From source checkout: `PYTHONPATH=src python3 -m alvex_editor.cli ...`

```bash
# scaffold a project (resolves template alias + registered soundtrack/curated cut points)
alvex-editor init --template "standard real estate template" \
  --soundtrack ~/Alvex/soundtracks/acoustic-breeze/bensound-acousticbreeze.mp3 \
  --clips /path/to/clips --address "123 Main St\nLittle Rock, Arkansas" --json
# if project exists: agent asks the user, then pass --on-exists=overwrite|suffix

alvex-editor status   -p ~/Alvex/projects/123-main-st-little-rock-arkansas/alvex.json --json
alvex-editor analyze  -p <project>/alvex.json --backend onsets
alvex-editor cuts show -p <project>/alvex.json --json                 # slot-labeled boundaries (Features-aware)
alvex-editor cuts nudge -p <project>/alvex.json --near 38.3 --to second-of-pair --json   # suggestion (confirm-gated)
alvex-editor cuts preview -p <project>/alvex.json --cut-points 9.822,...,97.129 [--save-config]
alvex-editor plan     -p <project>/alvex.json --map-clips

# optional, AI-assisted (writes suggestions for review) - CONFIRM before apply:
alvex-editor align    -p <project>/alvex.json --vision
alvex-editor align    -p <project>/alvex.json --vision --apply       # explicit confirmation
alvex-editor select   -p <project>/alvex.json --vision --apply

# render (explicit): preview -> feedback/iterate -> final (only on explicit intent)
alvex-editor render   -p <project>/alvex.json --dry-run
alvex-editor render   -p <project>/alvex.json --preview
alvex-editor render   -p <project>/alvex.json
```

Project configs are **JSON only** (`alvex.json`). Paths resolve relative to the config; media/artifacts outside the codebase. Template aliases (e.g. `standard real estate template`) resolve via the template registry; registered soundtracks reuse **curated cut points** (map once, reuse). Manifests/registries/cut-points/analysis/timelines/briefs are also JSON.

```json
{
  "name": "my-property",
  "template": "templates/exterior-showcase.md",
  "soundtrack": "/path/to/soundtrack.mp3",
  "clips_dir": "/path/to/clips",
  "output_dir": "~/Alvex/projects/my-property/output",
  "analysis_path": "~/Alvex/projects/my-property/output/analysis.json",
  "timeline_path": "~/Alvex/projects/my-property/output/timeline.json",
  "sources_manifest": "~/Alvex/projects/my-property/output/sources.json",
  "variables": { "address": "123 Main St\nLittle Rock, Arkansas" },
  "analysis": { "backend": "auto" },
  "preset": "lower-left-safe",
  "segment_overrides": { "approach-door": { "in_point": 7.352 } },
  "timing": {
    "outro_video_fade_seconds": 7.0,
    "outro_audio_fade_seconds": 7.0,
    "outro_audio_fade_out_before_end_seconds": 0.0
  },
  "render": {
    "fontfile": "/path/to/font.ttf",
    "title_x": "(w-text_w)/2",
    "title_y": "h*2/3-text_h/2",
    "text_align": "C",
    "video_filters": ["eq=contrast=1.05:saturation=1.1"]
  }
}
```

> **Storage policy:** videos, soundtracks, thumbnails, and edit plans/manifests/analysis are written **outside the Alvex Editor codebase** (the app enforces this). The visible workspace `~/Alvex` satisfies this. Only the bundled example template (`templates/exterior-showcase.md`) is kept in-repo. For local development/tests only: `ALVEX_ALLOW_IN_REPO_WRITES=1`.

All commands support `--json` for machine-readable output.

## Use from an AI chat / agent

- **Session start:** confirm the visible workspace locations (`~/Alvex` with `templates/`, `soundtracks/`, `projects/`). Intake resolves template/soundtrack (curated cut points reused) → `init` scaffolds a project → **preview** → feedback/iterate → **final on explicit intent**. On duplicate projects the agent asks what to do (non-interactive requires explicit `--on-exists`).
- **MCP server (primary):** `alvex-editor-mcp` (stdio). Works with OpenWebUI, Claude Desktop, Continue, Cline, RooCode, etc. Run `alvex-editor mcp` for config snippets. See [`docs/openwebui-docker.md`](docs/openwebui-docker.md). Tools include `workspace_info`, `list_templates`, `list_soundtracks`, `init_project`, `import_soundtrack`, `save_soundtrack_cut_points`, `project_status`, `doctor`, `template_info`, `analyze_soundtrack`, `plan_timeline`, `cuts_show`, `cuts_suggest`, `cuts_nudge` (suggestions, confirm-gated), `cuts_apply`/`cuts_preview` (explicit), `suggest_clip_mapping`, `suggest_inpoints`, `apply_manifest`, `render_video`. Suggestions/saved cuts are confirm-gated; `render_video` defaults `preview=true` (final only on explicit intent). Project-aware render/preview re-plans from current config unless `no_plan=true`. **Core workflow does not require Ollama**; AI features (`align`/`select`) are optional.
- **Shell/JSON fallback:** `alvex-editor <command> --json` (all commands, including `workspace`, `doctor`, `init`, `templates`, `soundtracks`). Errors should return valid JSON in `--json` mode. If ffmpeg is installed but not on PATH, run `doctor --json` for resolved paths/hints (`FFMPEG`/`FFPROBE`).
- **Python API:** `alvex_editor.api` (structured, JSON-safe).
- **Canonical workflow + safety rules:** [`docs/alvex-editor-agent-guide.md`](docs/alvex-editor-agent-guide.md). Repo adapters: [`AGENTS.md`](AGENTS.md), [`.opencode/skills/alvex-editor/SKILL.md`](.opencode/skills/alvex-editor/SKILL.md).

> AI features (`align`/`select`) are **optional** and use **Ollama** by default (e.g. `qwen3-vl:latest`). The core workflow (init/plan/render) works without Ollama. AI outputs and curated cut-point saves are **never auto-applied** — **review and explicitly confirm** before applying/saving. Prefer `--dry-run`/`--preview`; final render only on explicit intent.

## How it works
- **Templates**: Markdown in `templates/` (`docs/template-spec.md`).
- **Timing**: beat/onset analysis (ffmpeg+numpy `onsets`, cached per-song by hash) resolves `timeline.json` (`resolved_duration`, `timeline_in/out`). Explicit `analysis.cut_points` take precedence. (`docs/audio-analysis.md`).
- **Rendering**: FFmpeg filter graph (trim/scale/pad/concat, fades, centered drawtext overlays, soundtrack mix) over resolved timing. (`docs/rendering.md`).

## Docs
- `docs/high-level-design.md` — architecture
- `docs/template-spec.md` — template format
- `docs/audio-analysis.md` — beat/cut-point analysis & song library
- `docs/rendering.md` — FFmpeg rendering
- `docs/ollama.md` — Ollama setup/config (only)
- `docs/alvex-editor-agent-guide.md` — canonical agent/chat workflow

## Development
```bash
pip install -e ".[dev,analysis]"
PYTHONPATH=src pytest -q
```
Cross-platform (Linux/Windows/macOS). Snap-confined ffmpeg on Linux is handled (home-visible temp/cache dirs).

## Chat UX & MCP
- **MCP server (primary)**: `alvex-editor-mcp` (stdio). Tools cover workspace/templates/soundtracks/projects/plan/render/cuts/align/select. See [`docs/alvex-editor-agent-guide.md`](docs/alvex-editor-agent-guide.md).
- **OpenWebUI + Docker**: See [`docs/openwebui-docker.md`](docs/openwebui-docker.md) for setup. File access can be tricky in Docker — mounting volumes or running MCP on the host is often easiest.
- **Discover MCP config**: `alvex-editor mcp` prints config snippets for Claude Desktop, OpenWebUI, Continue, Cline/RooCode.

## Presets
Set `preset`/`style_preset` in `alvex.json` to load defaults from `project_dir/presets/`, `project_dir/`, or workspace `~/Alvex/presets/<name>.json` (JSON). Project values override preset values via deep merge.

## License
MIT License — see [`LICENSE`](LICENSE).
