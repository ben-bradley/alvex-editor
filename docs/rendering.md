# Rendering (Phase 3)

Phase 3 provides a **deterministic FFmpeg renderer** that consumes a resolved `timeline.json` and emits an `ffmpeg` command/filter graph (and can execute it when `ffmpeg` is on `PATH`). Phase 3b adds `ffprobe` validation and trim clamping.

## Inputs
- **Timeline** (`timeline.json`): produced by `alvex-editor plan` (Phase 2 resolved timing). Segments must have `resolved_duration` (and typically `timeline_in/out`). With `--project`, a missing `timeline_path` is auto-planned unless `--no-plan`.
- **Source manifest** (recommended): maps `slot_id ->` media path (and optional `in_point`/`out_point`). Provide via `--manifest` or project config `sources_manifest`/`manifest` (resolved relative to the project). Optional slots (e.g., `features`) are skipped when unmapped; required unmapped slots error unless `--allow-unmapped`.
- **Soundtrack**: from the timeline/`--soundtrack`. Used as the master audio track (trimmed to total duration) with segment-derived audio fades.
- **Variables**: `timeline.variables` (e.g., `address`) substitute `${name}` in overlay text.

Manifest example (`sources.yaml`):
```yaml
sources:
  high-approach-front: media/clips/intro.mp4
  features:
    path: media/clips/pool.mp4
    in_point: 1.5
```

## What the renderer generates
- Per-segment video: `trim` (source `in_point` → `in_point+resolved_duration`) → normalize (`scale`/`pad`/`fps`/format) → `video_effects` (`fade_in`, `fade_out`, `anchor=end`) → `drawtext` overlays (titles, `${vars}`, `start`/`end` incl. `end-N` refs).
- Sequencing: hard cuts via `concat=n=N:v=1:a=0` on resolved boundaries.
- Audio: soundtrack `atrim` to total + `afade` in/out derived from segment audio effects (e.g., intro music fade-in, outro fade-out).
- Configurable output via `render:` in `alvex.yaml` (e.g., `width/height/fps/crf/preset/preview`, `fontfile`/font for drawtext, `probe`, `strict_duration`).

## Validation & probing (Phase 3b)

When `ffprobe` is available (default `probe: true`), Alvex probes mapped sources/soundtrack to collect `duration/width/height/fps` metadata and **clamps trims** (`in_point` + `resolved_duration`) to the actual source duration. If a source is shorter than the resolved duration, Alvex warns (and clamps) or errors with `--strict-duration` / `render.strict_duration: true`. On a real render, missing required source/soundtrack files fail clearly; `--dry-run/--print-filter` skip file-existence enforcement. Use `--no-probe` to skip probing/clamping.

`ffprobe`/`ffmpeg` discovery checks `PATH` (including snap aliases) and common snap locations.

## CLI

```bash
alvex render -p alvex.yaml -m sources.yaml -o out/final.mp4
alvex render -p alvex.yaml                          # uses config sources_manifest/timeline_path (auto-plans if missing)
alvex render -p alvex.yaml --dry-run                # print command without running
alvex render -p alvex.yaml --print-filter           # print filter_complex
alvex render -p alvex.yaml --preview                # faster/lower-res preset
alvex render -p alvex.yaml --strict-duration        # error if clips are too short
alvex render -p alvex.yaml --no-probe               # skip ffprobe validation/clamping
```

`--dry-run`/`--print-filter` work without media/`ffmpeg` execution. Actual rendering requires `ffmpeg` on `PATH` (and drawtext needs a usable font/`fontfile`); probing uses `ffprobe` when available.

## Current limitations
- Master audio is the soundtrack track (clip-audio mixing not yet implemented).
- `drawtext` font resolution is environment-dependent; set `render.fontfile` for reliability.
- Image/branding overlays and non-cut transitions are not yet implemented.
- Source in/out *selection* (best segment within a clip) is defaulted (manual `in_point` supported via manifest) — a fit for AI-assisted alignment/ingest (Phase 4).
