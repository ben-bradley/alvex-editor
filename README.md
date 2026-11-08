# Alvex Editor

Template-driven, beat-aligned video production (primary use case: real-estate exterior showcase). Produces deterministic timelines and renders with FFmpeg. Can be driven from the CLI, as a Python API, or by AI agents (MCP / `--json`) — **AI suggestions require human confirmation**.

## Getting started

### 1) Prerequisites
- **Python >= 3.11**
- **FFmpeg** (`ffmpeg` + `ffprobe`) on `PATH` (or set `FFMPEG`/`FFPROBE`)
- **Ollama (optional, for AI mapping/in-point selection):** point Alvex at the model you already have. This project is configured/tested with `qwen3-vl:latest` (vision + text/tools). *You do not need Alvex to manage your model* — just set the host/model in `alvex.yaml` (see below and `docs/ollama.md`).

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

### 3) Configure a project (`alvex.yaml`)
Point to your existing Ollama model and your media. Paths resolve relative to the config file.

```yaml
name: my-property
template: templates/exterior-showcase.md
soundtrack: /path/to/soundtrack.mp3
clips_dir: /path/to/clips
output_dir: output
analysis_path: output/analysis.json
# sources_manifest: output/sources.yaml   # human-confirmed slot -> clip (+ in_point)

variables:
  address: "123 Main St\nLittle Rock, Arkansas"   # \n = second line (centered)

ollama:
  host: http://127.0.0.1:11434        # your existing Ollama host
  model: qwen3-vl:latest               # point to the model you already have
  vision_model: qwen3-vl:latest
  timeout: 240

analysis:
  backend: auto    # auto|onsets|librosa|library (onsets caches per song by hash)
  # cut_points: [10.82, 19.3, ...]     # optional hand-tuned overrides (win over detection)

render:
  fontfile: /path/to/font.ttf          # recommended for portable titles (Win/macOS)
  # box: false                          # centered title, no box (default)
```

### 4) Run the workflow (CLI)
`alvex-editor` is the CLI (`alvex` alias kept). From a source checkout you can also use `PYTHONPATH=src python3 -m alvex_editor.cli ...`.

```bash
alvex-editor status   -p alvex.yaml --json                 # check config/tools/artifacts
alvex-editor analyze  -p alvex.yaml --backend onsets --refresh
alvex-editor plan     -p alvex.yaml --map-clips -o output/timeline.json

# optional, AI-assisted (writes suggestions for review) — CONFIRM before apply:
alvex-editor align    -p alvex.yaml --vision
alvex-editor align    -p alvex.yaml --vision --apply       # explicit confirmation
alvex-editor select   -p alvex.yaml --vision --apply

# render (explicit)
alvex-editor render   -p alvex.yaml --dry-run
alvex-editor render   -p alvex.yaml --preview -o output/preview.mp4
alvex-editor render   -p alvex.yaml -o output/final.mp4
```

All commands support `--json` for machine-readable output.

## Use from an AI chat / agent

- **MCP server (recommended for MCP clients):** `alvex-editor-mcp` (stdio). Exposes `project_status`, `template_info`, `analyze_soundtrack`, `plan_timeline`, `suggest_clip_mapping`, `suggest_inpoints`, `apply_manifest`, `render_video`. Suggestions are confirm-gated; `render_video` defaults to `preview=true` (use `dry_run=true` to inspect).
- **Shell/JSON fallback:** `alvex-editor <command> --json`.
- **Python API:** `alvex_editor.api` (structured, JSON-safe).
- **Canonical workflow + safety rules:** [`docs/alvex-editor-agent-guide.md`](docs/alvex-editor-agent-guide.md). Repo adapters: [`AGENTS.md`](AGENTS.md), [`.opencode/skills/alvex-editor/SKILL.md`](.opencode/skills/alvex-editor/SKILL.md).

> AI is **Ollama-only** and optional. Point `ollama` config at your existing model (e.g. `qwen3-vl:latest`). AI outputs are suggestions — **review and explicitly confirm (`--apply` / `apply_manifest`)** before applying. Prefer `--dry-run`/`--preview` for renders.

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
