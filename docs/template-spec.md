# Template Spec (v0.1, draft)

Templates are **human-friendly Markdown** files in `templates/`. Alvex parses them into a structured plan; the `# Clip Edit Sequence` section is the machine-relevant source for timeline slots.

This spec is implemented by `alvex_editor.template` (Phase 1: convention + heuristics). It favors readability and compatibility with existing templates like `templates/exterior-showcase.md`.

## Sections

| Section | Purpose | Parsed |
|---|---|---|
| `# <Title>` / `# Summary` | Human context | Informational |
| `# Recording Sequence` | Capture guidance | Informational (preserved) |
| `# Clip Edit Sequence` | Edit/template plan | **Yes — produces ordered slots** |

## `# Clip Edit Sequence` items

Each ordered list item defines one slot:

```md
1. **Slot Name** - Description and timing/effect intent.
```

Parser behavior (v0.1):
- **`slot_id`**: slug of the slot name (e.g., `High Approach Front` → `high-approach-front`).
- **Order**: preserved as the timeline segment order.
- **Optional**: `true` when the item/name contains `Optional`/`optional`, and always `true` for a `Features` slot.
- **Duration range**: extracted from patterns like `8-10 seconds` or `10-20 seconds` → `min_duration`/`max_duration`/`target_duration` (midpoint). Ranges are preferred; effect durations (e.g., "5 second fade in") are not treated as clip duration.
- **Transition hint**: defaults to `cut`; marked `align: on-beat` when beat-aligned cutting is indicated.
- **Source hint**: inferred from phrases like `taken from the **Mid Orbit** recording` and known slot-name mappings; used for clip alignment (Phase 1 best-effort only).
- **Effects (heuristics, best-effort)**:
  - Intro/first-item fade-in patterns like `5 second fade in` → `video_effects: fade_in` (+ `audio.fade_in` when music fade-in is stated).
  - Address title patterns → `overlays` with `text: ${address}`. Intro timing like "visible after the first 1 second of the fade in and is visible for 5 seconds" is parsed into `start`/`end`. Outro patterns like "fades in quickly at 5 seconds before the end" use end-anchored refs (e.g., `start: end-5`, `end: end`).
  - Outro/end patterns like "fade to black ... starting at 5 seconds before the end" → `video_effects: fade_out` anchored to end; music fade → `audio.fade_out`.
- **Raw description**: always preserved on the slot for review and future parsing improvements.

## Project variables

Templates may reference project variables (e.g., `${address}` for titles). Values are supplied in the project config (`alvex.yaml`, `variables:`) rather than edited into the template.

## Resolved timeline (`timeline.json`)

`alvex-editor plan` emits a deterministic, inspectable timeline (schema v1) consumed by future renderers:
- `segments[]`: `slot_id`, `name`, `optional`, duration targets, `source` (`path`/`hint`/`status` = `unmapped|mapped|missing`), `transition_in`, `overlays`, `video_effects`, `audio`, `notes`.
- Sources are `unmapped` until clips are aligned (manual or assisted). `--map-clips` enables conservative filename/hint matching.

## Known limitations (v0.1)

- Natural-language effect parsing is heuristic and tuned to the current sample; unrecognized phrasing is preserved in `description`/`notes` but not fully structured.
- No beat detection or media probing yet (Phases 2+). `on-beat` is a planning hint, not resolved timing.
- The convention will evolve; prefer adding explicit, documented directives when introducing new templates.
