# Ollama setup and configuration (Alvex Editor)

Alvex uses [Ollama](https://ollama.com/) for **optional AI-assisted** features with human confirmation: clip-to-slot mapping (`alvex-editor align`, Phase 4) and in-point/segment selection (`alvex-editor select`, Phase 5a), with optional vision-based frame analysis. This document covers **only** setting up Ollama and configuring Alvex to integrate with it.

## 1. Install and run Ollama

Install Ollama for your platform and ensure the Ollama server is running (default listens on `127.0.0.1:11434`).

```bash
# verify the server is reachable
curl http://127.0.0.1:11434/api/version
# list installed models
ollama list
```

If Ollama runs on another machine (for example, a LAN host), make it reachable from the machine running Alvex and note its base URL (e.g., `http://192.168.11.136:11434`). Configure Ollama on that host to listen on the appropriate interface if needed (per Ollama’s own documentation).

## 2. Pull models

Choose a model available in your Ollama instance. A vision-capable model can handle both mapping suggestions and (optionally) frame-based clip labeling:
- **`qwen3-vl:latest`** (vision + text/tools): recommended — works for mapping suggestions and for `alvex-editor align --vision` (Alvex extracts a representative frame with `ffmpeg` and asks the vision model to label it).

```bash
ollama pull qwen3-vl:latest
```

## 3. Configure Alvex (`alvex.json`)

Add an `ollama` block to your project config. Alvex reads this for `alvex-editor align` and `alvex-editor select` (CLI flags override config).

```json
# alvex.json
clips_dir: media/clips
sources_manifest: sources.json

ollama:
  host: http://127.0.0.1:11434      # or http://192.168.11.136:11434 for a LAN host
  model: qwen3-vl:latest            # mapping suggestions (and vision, if vision_model omitted)
  # vision_model: qwen3-vl:latest   # optional override for --vision labeling
  timeout: 120                      # seconds per request
```

Config keys:
- `host` / `base_url` / `endpoint`: Ollama base URL (scheme added if omitted).
- `model`: model for clip-to-slot mapping suggestions.
- `vision_model`: model for vision labeling (defaults to `model` if omitted).
- `timeout`: request timeout in seconds.

## 4. Run alignment (human confirmation required)

```bash
# LLM mapping suggestions -> writes sources.suggested.json for review
alvex align -p alvex.json --host http://192.168.11.136:11434 --model qwen3-vl:latest

# optional: vision-label clips first (requires ffmpeg; uses vision_model, defaults to model)
alvex align -p alvex.json --host http://192.168.11.136:11434 --model qwen3-vl:latest --vision

# after reviewing sources.suggested.json, apply explicitly
alvex align -p alvex.json --host http://192.168.11.136:11434 --model qwen3-vl:latest --apply
# then render using the manifest
alvex render -p alvex.json -m sources.json --dry-run
```

`alvex-editor align` **never silently applies mappings**: it writes a suggested manifest for review and only writes the target manifest when you pass `--apply` (explicit confirmation). Use `--clips`, `--timeline`, `--output`, or `--manifest` to override paths.

## 5. Run in-point / segment selection (human confirmation required)

`alvex-editor select` suggests an `in_point` (start offset) per mapped segment so the `resolved_duration` window captures the best moment in each source clip. It uses template-aware heuristics (e.g., centered-midpoint for orbit shots, intro/outro anchors) and can optionally rank candidate windows with a vision model.

```bash
# heuristic selection (ffprobe; no model call) -> writes sources.selected.suggested.yaml
alvex select -p alvex.json

# vision-ranked selection (ffmpeg frame extraction + vision model; slower)
alvex select -p alvex.json --host http://192.168.11.136:11434 --model qwen3-vl:latest --vision --candidates 5

# review, then apply explicitly
alvex select -p alvex.json --apply
alvex render -p alvex.json --dry-run
```

Uses the same `ollama` config/flags (`host`, `model`/`vision_model`, `timeout`). Like `align`, it writes a suggested manifest for review and only applies with `--apply`. Requires `ffprobe` (probing/clamping) and `ffmpeg` for `--vision` frame extraction.

## 6. Troubleshooting

- **Connection errors**: confirm `host` is correct and reachable (`curl <host>/api/version`) and that firewalls allow access to port `11434`.
- **Model not found**: ensure the model name matches `ollama list` / the Ollama `/api/tags` name.
- **Slow/timeout**: increase `ollama.timeout` (vision/thinking models like `qwen3-vl` can be slow, especially with multiple candidates), or run without `--vision`.
- **Vision analysis fails**: requires `ffmpeg` for frame extraction and a vision-capable `vision_model`; `align` falls back to filename labeling, `select` falls back to heuristics.
- **Quality**: treat suggestions as proposals — review and edit the suggested manifest (slot mappings, `in_point`, confidence/rationale) before `--apply`/render.
