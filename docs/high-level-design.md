# Alvex Editor — High-Level Design

*Saved for reference. Source basis: `instructions.md` and `templates/exterior-showcase.md`.*

## Goals

- Build **Alvex Editor**, a video editing/production tool.
- Primary use case: **real estate video production**; design should remain **general-purpose** for video production.
- Core workflow:
  1. Capture clips (template-driven) + provide a soundtrack (MP3).
  2. Analyze the soundtrack to determine pacing/transition points.
  3. Analyze clips and align them to a template; compose a video with intro/outro, titles, overlays, branding, and sequenced clips.
  4. Review and export (e.g., upload to YouTube later).
- Inputs a user can provide: **template**, clips, soundtrack, overlays, branding, and other media.
- **AI**: leverage models via **Ollama** (project docs should cover Ollama setup/config only, not bundling models).
- **Templates**: human-friendly **Markdown** files in `templates/`.
- **Soundtrack**: drives rhythm/pacing and transition timing.
- **Clips**: typically 8–12s; intro/outro may be longer for overlays/fades.

## Proposed high-level architecture

Use a **modular media pipeline** with a clear separation between *analysis*, *planning*, and *rendering*. This keeps the system extensible (new template types, effects, AI providers later) while making the real-estate workflow a first-class preset.

```text
Project (media + template + config)
        │
        ▼
┌────────────────────┐
│  Ingest & Validate │  discover clips/audio/overlays; normalize metadata
└─────────┬──────────┘
          ▼
┌────────────────────┐
│  Analysis Layer    │  audio beats/transitions; clip/content analysis; (optional) AI assist
└─────────┬──────────┘
          ▼
┌────────────────────┐
│  Template Planner  │  parse template → shot list/timeline plan; map clips to slots
└─────────┬──────────┘
          ▼
┌────────────────────┐
│  Timeline Builder  │  resolve cuts to beat grid; durations, transitions, overlays, fades
└─────────┬──────────┘
          ▼
┌────────────────────┐
│  Render/Export     │  deterministic render (FFmpeg or equivalent); preview + final output
└─────────┬──────────┘
          ▼
     Review / Iterate  (adjust mappings, timing, titles) → re-render
```

Key principle: **analysis produces signals; the planner makes decisions; rendering is deterministic** given a resolved timeline. This makes results reproducible and reviewable.

## Core components

1. **CLI / App shell (initial)**
   - Commands like `alvex-editor init`, `alvex-editor analyze`, `alvex-editor plan`, `alvex-editor render`, `alvex-editor preview`.
   - Later: lightweight GUI or web UI for review/mapping; the pipeline remains the same backend.

2. **Project model**
   - A project directory/config (e.g., `alvex.yaml` or `project.json`) referencing: template path, soundtrack, clip folder, branding/assets, output settings, and cached analysis artifacts.
   - Enables repeatable renders and incremental re-analysis.

3. **Template engine**
   - Parses Markdown templates from `templates/` into a structured **VideoTemplate** (sections like summary, recording guidance, and—most importantly—an edit/sequence spec).
   - Supports: ordered shot slots, optional slots (e.g., *Features*), slot metadata (intent/description), and timing/effect rules (intro fade/title, outro fade/title, cut-on-beat, target clip length).
   - `templates/exterior-showcase.md` is the starting point; formalize a small, parseable convention (headings/lists/key-value hints) while keeping templates readable.

4. **Media ingest**
   - Scans inputs; extracts technical metadata via `ffprobe`/media libraries (duration, resolution, fps, codec, rotation, audio).
   - Normalizes naming/ordering hints and builds a **clip catalog**.

5. **Audio analysis (pacing)**
   - Detects tempo/beats/onsets and proposes **cut points** aligned to the soundtrack (with constraints like 8–10s targets, min/max durations).
   - Produces a beat grid/cut-point timeline used by the planner. Implementation can start with DSP libraries; AI can assist with higher-level structure if useful.

6. **Clip analysis & alignment**
   - Matches available clips to template slots. Start rule-based + metadata/filename heuristics; evolve to content-aware.
   - Uses AI (via Ollama) for tasks that benefit from semantics: classifying/labeling clips (front/back/orbit/approach/door/pan/feature), selecting best segments, or interpreting template intent. Keep a **human-confirmable mapping** step in the workflow.

7. **Timeline/plan resolver**
   - Combines: template slots + clip-to-slot mapping + beat-aligned cut points + effect rules.
   - Outputs a resolved, inspectable **Edit Decision List (EDL-like) timeline** (JSON) describing source in/out, sequence, transitions, text overlays, audio fades, branding.
   - Review happens on this plan before final render.

8. **Render & export**
   - Renders the resolved timeline to video (FFmpeg-based pipeline is the practical default). Supports preview proxies and final-quality export.
   - Export presets (YouTube-friendly settings) as configuration, not hard-coded.

9. **Ollama integration layer (AI adapter)**
   - A thin client/config boundary: endpoint, model selection per task (e.g., vision vs. text), timeouts, and graceful fallback when Ollama is unavailable.
   - AI is **assistive, not required** for a basic deterministic path (manual mapping + beat cuts + render). Project docs should cover Ollama setup/configuration only.
   - Candidate AI uses (optional): clip tagging/captioning from frames, template intent extraction, title/overlay text suggestions, QC checks.

## Template/spec format (proposed direction)

Keep templates as Markdown, but define a lightweight convention the parser can rely on:
- **Summary**: human context.
- **Recording Sequence**: guidance (informational).
- **Clip Edit Sequence** (machine-relevant): ordered list items where each slot has a stable **Slot ID/Name**, intent, and optional directives (e.g., `duration: 8-10s`, `cut: on-beat`, `source: Mid Orbit`, `effects: fade-in 5s, title[address] 1s-6s`, `optional: true` for Features).
- Allow project-level overrides (actual address, branding, which feature clips) in project config rather than editing the template.

This preserves human readability while giving the planner deterministic inputs.

## Suggested project layout (early)

```text
alvex-editor/
  instructions.md
  templates/                 # markdown templates
  docs/                      # setup/config (incl. Ollama), design
  src/                       # application code (pipeline, parsers, adapters)
  projects/ (or user-managed) # per-video projects/media + config
  tests/
```

## Technology choices (recommendation)

- **Language/runtime**: Python is a strong fit for a media+AI pipeline (audio analysis, FFmpeg orchestration, Ollama HTTP client, rapid iteration). A compiled core could come later if needed.
- **Media**: FFmpeg/ffprobe for probe + render; optional Python libs for beat/onset detection.
- **AI**: Ollama local API; model choice configurable per capability (text vs. vision).
- **Interfaces**: CLI first; structured JSON artifacts (`analysis.json`, `timeline.json`) to enable a future GUI.

(Exact stack can be finalized at implementation time; the architecture above is stack-agnostic.)

## Phased roadmap

1. **Foundation**: project config, media ingest/metadata, template parser for the edit sequence, and a resolved timeline JSON format.
2. **Audio-driven timing**: soundtrack beat/cut-point detection and mapping cuts to the template’s target durations.
3. **Deterministic render**: FFmpeg renderer for sequencing, cuts, basic fades, titles/overlays, and audio mix/fades (manual clip-to-slot mapping).
4. **AI-assisted alignment (Ollama)**: clip labeling/selection and mapping suggestions with user confirmation; document Ollama setup/config.
5. **Review & polish**: preview workflow, better segment selection, branding packs, YouTube export presets, and generalized template features beyond real estate.

## Risks / considerations

- **Template parsing ambiguity**: keep a strict, documented convention for machine-read fields; fail clearly when required info is missing.
- **Clip-to-slot accuracy**: make mapping reviewable/editable; don’t rely solely on AI guesses.
- **Audio pacing variability**: enforce duration constraints and allow manual adjustment of cut points.
- **Reproducibility**: cache analysis and version the resolved timeline alongside outputs.
- **Scope control**: start with cut-based edits + fades/titles/overlays (per template) before complex transitions/effects.
