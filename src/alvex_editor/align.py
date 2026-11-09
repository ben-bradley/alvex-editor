from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

import yaml

from .ollama import OllamaClient, OllamaConfig, OllamaError, extract_json_object
from .planner import discover_clips
from .policy import ensure_not_inside_repo
from .probe import find_ffmpeg, mkdtemp_portable, probe_media
from .timeline import Segment, Timeline, load_timeline


@dataclass
class ClipInfo:
    path: str
    name: str
    duration: float | None = None
    label: str | None = None
    label_source: str | None = None  # vision, filename, heuristic
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "name": self.name, "duration": self.duration, "label": self.label, "label_source": self.label_source, "notes": self.notes}


def catalog_clips(clips_dir: str | Path) -> list[ClipInfo]:
    clips = discover_clips(Path(clips_dir))
    out: list[ClipInfo] = []
    for p in clips:
        info = probe_media(p)
        out.append(ClipInfo(path=str(p), name=p.name, duration=info.duration, notes=[info.error] if info.error and info.exists else []))
    return out


def extract_frame(clip_path: str | Path, out_path: str | Path, *, at: float | None = None, duration: float | None = None) -> Path:
    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg not found; required for frame extraction/vision labeling")
    clip_path = Path(clip_path)
    out_path = Path(out_path)
    if at is None:
        d = duration
        if d is None:
            d = probe_media(clip_path).duration
        at = max(0.0, min((d or 2.0) / 2.0, max(0.0, (d or 2.0) - 0.1)))
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{at:.3f}", "-i", str(clip_path), "-frames:v", "1", "-update", "1", "-q:v", "3", str(out_path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"frame extraction failed for {clip_path}: {res.stderr or res.stdout}")
    return out_path


def label_clip_vision(client: OllamaClient, clip: ClipInfo, *, model: str) -> str:
    td = mkdtemp_portable(prefix="alvex-frame-", for_ffmpeg=True)
    try:
        frame = td / "frame.jpg"
        extract_frame(clip.path, frame, duration=clip.duration)
        prompt = (
            "You are labeling a drone real-estate video clip. Describe what the camera is doing and what is shown "
            "(e.g., high approach to front of house, mid/high orbit front/back, pan front/back, rising up/top-down reveal, "
            "approach to front door, departure/pull away, or a special feature like pool/barn/dock). "
            "Reply with ONLY a short label (max 12 words)."
        )
        return client.chat_vision(model=model, prompt=prompt, images=[frame]).strip()
    finally:
        shutil.rmtree(td, ignore_errors=True)


def label_clips(clips: list[ClipInfo], client: OllamaClient | None, *, vision_model: str | None = None, use_vision: bool = False) -> list[ClipInfo]:
    for clip in clips:
        if use_vision and client and vision_model:
            try:
                clip.label = label_clip_vision(client, clip, model=vision_model)
                clip.label_source = "vision"
                continue
            except Exception as e:
                clip.notes.append(f"vision label failed: {e}")
        # filename heuristic fallback
        clip.label = Path(clip.path).stem.replace("_", " ").replace("-", " ")
        clip.label_source = "filename"
    return clips


def _slot_descriptors(timeline: Timeline) -> list[dict[str, Any]]:
    slots = []
    for s in timeline.segments:
        slots.append({
            "slot_id": s.slot_id,
            "name": s.name,
            "optional": s.optional,
            "description": s.description,
            "source_hint": s.source.hint,
            "resolved_duration": s.resolved_duration,
        })
    return slots


MAPPING_SYSTEM = (
    "You assign drone real-estate clips to template slots. "
    "Use each clip at most once. Prefer the best semantic match (camera move + front/back/feature). "
    "Optional slots (e.g., features) may be left unmapped if no good clip exists. "
    "Return ONLY valid JSON with this shape: "
    '{"mappings":[{"slot_id":"...","clip_path":"...","confidence":0.0,"rationale":"..."}],"unmapped_slots":["..."],"unused_clips":["..."]}'
)


def suggest_mappings(client: OllamaClient, timeline: Timeline, clips: list[ClipInfo], *, model: str) -> dict[str, Any]:
    payload = {
        "slots": _slot_descriptors(timeline),
        "clips": [c.to_dict() for c in clips],
    }
    user = "Propose the best slot-to-clip mapping as JSON.\n\n" + json.dumps(payload, indent=2)
    raw = client.chat(model=model, messages=[{"role": "system", "content": MAPPING_SYSTEM}, {"role": "user", "content": user}], format="json")
    try:
        data = extract_json_object(raw)
    except Exception as e:
        raise OllamaError(f"Failed to parse mapping JSON: {e}\nRaw: {raw[:800]}") from e
    if not isinstance(data, dict):
        raise OllamaError(f"Mapping response must be a JSON object, got: {type(data)}")
    return data


def manifest_from_mappings(mappings: dict[str, Any], *, timeline: Timeline) -> dict[str, Any]:
    sources: dict[str, Any] = {}
    for m in mappings.get("mappings") or []:
        slot_id = m.get("slot_id")
        clip_path = m.get("clip_path")
        if slot_id and clip_path:
            entry: dict[str, Any] = {"path": clip_path}
            if m.get("in_point") is not None:
                entry["in_point"] = m["in_point"]
            if m.get("rationale") or m.get("confidence") is not None:
                entry["_suggestion"] = {k: m.get(k) for k in ("confidence", "rationale") if m.get(k) is not None}
            sources[str(slot_id)] = entry
    return {
        "sources": sources,
        "unmapped_slots": mappings.get("unmapped_slots") or [],
        "unused_clips": mappings.get("unused_clips") or [],
        "project": timeline.project,
        "template": timeline.template,
    }


def write_manifest(manifest: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    ensure_not_inside_repo(path, kind="manifest/edit plan")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def align_project(
    timeline_path: str | Path,
    clips_dir: str | Path,
    *,
    ollama: OllamaConfig | None = None,
    model: str | None = None,
    vision_model: str | None = None,
    use_vision: bool = False,
) -> tuple[dict[str, Any], list[ClipInfo]]:
    timeline = load_timeline(timeline_path)
    clips = catalog_clips(clips_dir)
    if not clips:
        raise ValueError(f"No clips found in {clips_dir}")
    client = OllamaClient(ollama or OllamaConfig()) if (ollama or model or vision_model) else None
    if (use_vision or model) and client is None:
        client = OllamaClient(ollama or OllamaConfig())
    eff_model = model or (ollama.model if ollama else None)
    eff_vision = vision_model or (ollama.vision_model if ollama else None) or eff_model
    if use_vision and not eff_vision:
        raise ValueError("Vision labeling requested but no vision model configured (set ollama.vision_model or --vision-model)")
    label_clips(clips, client, vision_model=eff_vision, use_vision=use_vision)
    if not eff_model:
        raise ValueError("No model configured for mapping suggestions (set ollama.model or --model)")
    if client is None:
        client = OllamaClient(ollama or OllamaConfig())
    mappings = suggest_mappings(client, timeline, clips, model=eff_model)
    manifest = manifest_from_mappings(mappings, timeline=timeline)
    return manifest, clips
