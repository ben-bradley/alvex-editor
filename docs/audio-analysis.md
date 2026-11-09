# Audio Analysis & Beat-Aligned Timing

Alvex analyzes a soundtrack to produce a **beat/cut-point grid** and resolves each timeline segment's `resolved_duration` and contiguous `timeline_in`/`timeline_out` in `timeline.json`, respecting `min_duration`/`max_duration` and snapping `on-beat` cuts to the grid.

## Two reusable layers (know the difference)

1. **Curated soundtrack registry reference (authoritative, user-facing, recommended)** — stored in the visible workspace at `~/Alvex/soundtracks/<id>/cut-points.yaml` (indexed in `~/Alvex/soundtracks/registry.yaml`; MP3s are copied/imported into the registry). Contains **human-confirmed** `cut_points` (and/or `bpm`/`offset`/`beat_times`) with provenance. **Map once, reuse across projects.** Saved only on explicit confirmation (CLI `alvex-editor soundtracks set-cuts ...`, MCP `save_soundtrack_cut_points`). Project `init` applies curated cuts as explicit `analysis.cut_points` when available.
2. **Hash-keyed onset detection library/cache (internal optimization)** — auto-detected onset peaks cached by soundtrack content hash (default `~/.cache/alvex/analysis/<soundtrack>-<hash>.json`, honors `XDG_CACHE_HOME`; override with `analysis.library_dir`). Useful for seeding candidates and avoiding re-detection, but **not** the curated source of truth.

Explicit per-project `analysis.cut_points`/`bpm`/`beat_times` in `alvex.yaml` **always win** over curated refs and caches (hand-tuned per job).

## Cut-point mapping workflow (curated, confirm-gated)
1. Add/import the soundtrack: `alvex-editor soundtracks import /path/to/song.mp3 --track-id acoustic-breeze --title "Acoustic Breeze" --json` (copies MP3 into `~/Alvex/soundtracks/<id>/`).
2. Seed candidates: `alvex-editor analyze -p <project>/alvex.yaml --backend onsets` (detection) and/or review existing refs.
3. Work with the user to refine `cut_points` (segment-end boundaries, seconds, in order; align to beats/duration/slot count).
4. **Review, then explicitly confirm and save**: `alvex-editor soundtracks set-cuts acoustic-breeze --cut-points 10.82,19.3,28.82,... --json` (or MCP `save_soundtrack_cut_points`). The agent must confirm with the user before saving.

## Detection backends & reuse

```bash
# Seed/compute detection (updates hash library)
alvex-editor analyze --project alvex.yaml --backend onsets --refresh

# Reuse curated ref / library / project cache (default when no explicit timing overrides)
alvex-editor analyze --project alvex.yaml
alvex-editor plan --project alvex.yaml
```

- **Reuse order (when no explicit `bpm`/`cut_points`/`beat_times` in config and not forcing a refresh against overrides):** curated soundtrack registry ref (for the configured soundtrack) → hash-keyed library/project cache (per backend rules) → detection.
- **Explicit overrides win:** `analysis.cut_points`, `analysis.bpm`, or `analysis.beat_times` in config take precedence. Use `--backend onsets --refresh` to force a fresh detection run for seeding.

## Configure analysis (`alvex.yaml`)

```yaml
soundtrack: /path/or/~/Alvex/soundtracks/acoustic-breeze/bensound-acousticbreeze.mp3
analysis_path: output/analysis.json   # project cache/read

analysis:
  backend: auto       # auto | onsets | librosa | library (default: auto)
  # refresh: true     # ignore caches/refs as configured and recompute detection
  # library_dir: ~/.cache/alvex/analysis   # hash detection cache (internal)
  # min_distance: 0.35   # (onsets) minimum seconds between detected peaks

  # Explicit timing (overrides detection/cache/curated ref when set):
  # bpm: 120
  # offset: 0.0
  # duration: 180
  # cut_points: [9.5, 18.0, ...]   # absolute segment-end boundaries (seconds)
  # beat_times: [0.0, 0.5, ...]
```

Shorthands: top-level `soundtrack_bpm` / `beat_offset` map into `analysis`. `alvex-editor init` applies curated registry `cut_points` into project config when available.

## Resolution behavior

- **`cut_points`**: if enough points are provided (>= number of active/mapped segments), they are used as segment end boundaries in order.
- **`beat_times` / BPM grid** (including detected `onsets` peaks): for segments with `transition_in.align: on-beat`, the segment end is snapped to the nearest grid point that keeps the duration within `[min_duration, max_duration]` (target/midpoint preferred).
- **No analysis** (missing config/backend/soundtrack): timing is resolved from target/min/max durations without beat snapping; `analysis` records why.
- Optional unmapped segments consume **0** timeline time.

## Backends

| backend | needs | notes |
|---|---|---|
| `onsets` | `ffmpeg` + `numpy` | Detects onset/transition peaks; persisted to the hash library. |
| `librosa` | `librosa` | Beat tracking; used if available. |
| `auto` | — | Prefers curated registry ref (no explicit overrides), then library/project cache; else librosa, then `onsets`. |
| `library` | cached entry | Reuse a previously analyzed song by hash. |

## CLI

```bash
# workspace/registry (visible, outside repo)
alvex-editor workspace --json [--save]
alvex-editor soundtracks list --json
alvex-editor soundtracks import /path/to/song.mp3 --track-id ID [--title "..."] [--aliases ...] --json
alvex-editor soundtracks set-cuts ID --cut-points 10.82,19.3,... [--bpm 120] [--offset 0] --json   # explicit confirmation

# write analysis.json (beat/cut-point grid)
alvex-editor analyze --project alvex.yaml [--backend onsets|librosa|auto|library] [--refresh] [-o analysis.json] [--no-cache]

# build plan + resolve timing (runs analysis/reuse by default)
alvex-editor plan --project alvex.yaml [-o timeline.json] [--map-clips] [--no-analyze]
```

## Timeline fields

- `timeline.analysis`: `source`, `method`, `bpm`/`offset`/`duration`, `beat_times`, `cut_points`, notes.
- per `segment`: `resolved_duration`, `timeline_in`, `timeline_out` (contiguous master-timeline placement).

These fields are the stable handoff for rendering (FFmpeg): the renderer consumes resolved segment timing/cuts rather than re-deriving pacing.
