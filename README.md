# Alvex Editor

Template-driven, beat-aligned video production (primary use case: real-estate exterior showcase). Produces deterministic timelines and renders with FFmpeg. Can be driven from the CLI, as a Python API, or by AI agents (MCP / `--json`) — **AI suggestions require human confirmation**.

## Getting started

### 1) Prerequisites
- **Python >= 3.11**
- **FFmpeg** (`ffmpeg` + `ffprobe`) on `PATH` (or set `FFMPEG`/`FFPROBE`)
- **Ollama (optional, for AI mapping/in-point selection):** point Alvex at the model you already have. This project is configured/tested with `qwen3-vl:latest` (vision + text/tools). *You do not need Alvex to manage your model* — just set the host/model in `alvex.json` (see below and `docs/ollama.md`).

### 2) Install (from a source checkout)
```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

pip install -e ".[dev]"
# onset soundtrack analysis (song cut-point library):
pip install -e ".[analysis]"          # or: pip install numpy
# MCP server (to let any MCP-capable AI agent call Alvex as tools):
pip install -e ".[agent]"
```

### 3) Workspace & registries (visible, outside the repo)
Keep **all user work in an obvious, user-visible workspace** (not hidden). Default root: `~/Alvex` (override `ALVEX_WORKSPACE` / `--workspace`), grouped as:

```text
~/Alvex/
  templates/      # template registry (add *.md templates alongside real-estate)
  soundtracks/    # soundtrack registry (MP3s copied/imported) + curated cut-points.json per song (map once, reuse)
  projects/       # one folder per video job (<slug>/alvex.json + output/)
```

```bash
alvex-editor workspace --json [--save]                 # confirm locations (session start)
alvex-editor doctor --json [ -p <project>/alvex.json ]  # ffmpeg/ffprobe resolution + hints
alvex-editor templates --json                           # bundled + workspace templates
alvex-editor soundtracks list --json
alvex-editor soundtracks import /path/to/song.mp3 --track-id acoustic-breeze --json
alvex-editor soundtracks set-cuts acoustic-breeze --cut-points 10.82,19.3,... --json   # explicit confirmation
```

### 4) Start a project (`init`) and run the workflow (CLI)
`alvex-editor` is the CLI (`alvex` alias kept). All work is outside the repo. From a source checkout you can also use `PYTHONPATH=src python3 -m alvex_editor.cli ...`.

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
- **MCP server (recommended for MCP clients):** `alvex-editor-mcp` (stdio). Tools include `workspace_info`, `list_templates`, `list_soundtracks`, `init_project`, `import_soundtrack`, `save_soundtrack_cut_points`, `project_status`, `doctor`, `template_info`, `analyze_soundtrack`, `plan_timeline`, `cuts_show`, `cuts_suggest`, `cuts_nudge` (suggestions, confirm-gated), `cuts_apply`/`cuts_preview` (explicit), `suggest_clip_mapping`, `suggest_inpoints`, `apply_manifest`, `render_video`. Suggestions/saved cuts are confirm-gated; `render_video` defaults `preview=true` (final only on explicit intent). Project-aware render/preview re-plans from current config unless `no_plan=true`.
- **Shell/JSON fallback:** `alvex-editor <command> --json` (all commands, including `workspace`, `doctor`, `init`, `templates`, `soundtracks`). Errors should return valid JSON in `--json` mode. If ffmpeg is installed but not on PATH, run `doctor --json` for resolved paths/hints (`FFMPEG`/`FFPROBE`).
- **Python API:** `alvex_editor.api` (structured, JSON-safe).
- **Canonical workflow + safety rules:** [`docs/alvex-editor-agent-guide.md`](docs/alvex-editor-agent-guide.md). Repo adapters: [`AGENTS.md`](AGENTS.md), [`.opencode/skills/alvex-editor/SKILL.md`](.opencode/skills/alvex-editor/SKILL.md).

> AI is **Ollama-only** and optional. Point `ollama` config at your existing model (e.g. `qwen3-vl:latest`). AI outputs and curated cut-point saves are **never auto-applied** — **review and explicitly confirm** before applying/saving. Prefer `--dry-run`/`--preview`; final render only on explicit intent.

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

## License
TBD — add a `LICENSE` file before publishing.
