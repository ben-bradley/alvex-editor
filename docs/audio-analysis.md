# Audio Analysis & Beat-Aligned Timing

Alvex analyzes a soundtrack to produce a **beat/cut-point grid** and resolves each timeline segment's `resolved_duration` and contiguous `timeline_in`/`timeline_out` in `timeline.json`, respecting `min_duration`/`max_duration` and snapping `on-beat` cuts to the grid.

## Cut-point library (recommended)

The built-in **`onsets`** backend detects musically meaningful transition/onset peaks from the soundtrack using **ffmpeg + numpy** (no extra audio deps like librosa required). Results are cached in a **song cut-point library** keyed by the soundtrack's content hash so each song is analyzed once and reused across projects/runs.

```bash
# Analyze a song and (re)build its library entry
alvex analyze --project alvex.yaml --backend onsets --refresh

# Reuse cached/library analysis (default behavior when no explicit timing is set)
alvex analyze --project alvex.yaml
alvex plan --project alvex.yaml
```

- **Library cache**: `~/.cache/alvex/analysis/<soundtrack>-<hash>.json` by default (override with `analysis.library_dir`; honors `XDG_CACHE_HOME`).
- **Project cache**: also written to `analysis_path` (default `analysis.json`) for convenience.
- **Reuse**: `plan`/`analyze` reuse the library (or project cache) for a soundtrack when no explicit `bpm`/`cut_points`/`beat_times` are configured and `--refresh`/`analysis.refresh` is not set.
- **Explicit overrides win**: if `analysis.cut_points`, `analysis.bpm`, or `analysis.beat_times` are set in the project config, they take precedence over cached/detected results (useful for hand-tuned projects). Use `--backend onsets --refresh` to force a fresh detection run.

## Configure analysis (`alvex.yaml`)

```yaml
soundtrack: media/soundtrack.mp3
analysis_path: output/analysis.json   # project cache/read

analysis:
  backend: onsets     # auto | onsets | librosa | library (default: auto)
  # refresh: true     # ignore caches and recompute
  # library_dir: ~/.cache/alvex/analysis
  # min_distance: 0.35   # (onsets) minimum seconds between detected peaks

  # Explicit timing (overrides detection/cache when set):
  # bpm: 120
  # offset: 0.0
  # duration: 180
  # cut_points: [9.5, 18.0, ...]   # absolute segment-end boundaries (seconds)
  # beat_times: [0.0, 0.5, ...]    # explicit beat/onset grid
```

Shorthands: top-level `soundtrack_bpm` / `beat_offset` map into `analysis`.

## Resolution behavior

- **`cut_points`**: if enough points are provided (>= number of active/mapped segments), they are used as segment end boundaries in order.
- **`beat_times` / BPM grid** (including detected `onsets` peaks): for segments with `transition_in.align: on-beat`, the segment end is snapped to the nearest grid point that keeps the duration within `[min_duration, max_duration]` (target/midpoint preferred).
- **No analysis** (missing config/backend/soundtrack): timing is resolved from target/min/max durations without beat snapping; `analysis` records why.
- Optional unmapped segments consume **0** timeline time.

## Backends

| backend | needs | notes |
|---|---|---|
| `onsets` | `ffmpeg` + `numpy` | Detects onset/transition peaks; persisted to the song library. |
| `librosa` | `librosa` | Beat tracking; used if available. |
| `auto` | — | Reuses library/project cache; else tries librosa, then falls back to `onsets`. |
| `library` | cached entry | Reuse a previously analyzed song by hash. |

## CLI

```bash
# write analysis.json (beat/cut-point grid) and update the song library
alvex analyze --project alvex.yaml [--backend onsets|librosa|auto|library] [--refresh] [-o analysis.json] [--no-cache]

# build plan + resolve timing (runs analysis/reuse by default)
alvex plan --project alvex.yaml [-o timeline.json] [--map-clips] [--no-analyze]
```

## Timeline fields

- `timeline.analysis`: `source`, `method`, `bpm`/`offset`/`duration`, `beat_times`, `cut_points`, notes.
- per `segment`: `resolved_duration`, `timeline_in`, `timeline_out` (contiguous master-timeline placement).

These fields are the stable handoff for rendering (FFmpeg): the renderer consumes resolved segment timing/cuts rather than re-deriving pacing.
