from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from .align import extract_frame, write_manifest
from .ollama import OllamaClient, OllamaConfig, OllamaError, extract_json_object
from .probe import mkdtemp_portable, probe_media
from .renderer import load_manifest
from .timeline import Segment, Timeline, load_timeline


@dataclass
class WindowCandidate:
    in_point: float
    out_point: float
    reason: str
    frame_path: Path | None = None
    score: float | None = None
    rationale: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "in_point": round(self.in_point, 4),
            "out_point": round(self.out_point, 4),
            "reason": self.reason,
            "score": self.score,
            "rationale": self.rationale,
        }


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def generate_candidates(seg: Segment, source_duration: float, *, count: int = 5) -> list[WindowCandidate]:
    seg_dur = float(seg.resolved_duration or seg.target_duration or 9.0)
    max_in = max(0.0, source_duration - seg_dur)
    if max_in <= 0.001:
        return [WindowCandidate(in_point=0.0, out_point=min(seg_dur, source_duration), reason="source fits")]

    desc = (seg.description or "").lower()
    slot = seg.slot_id.lower()
    candidates: list[WindowCandidate] = []

    # Heuristics from template intent.
    if "midpoint" in desc and "centered" in desc:
        # align window midpoint with source midpoint so the centered moment lands mid-window
        in_pt = _clamp((source_duration / 2.0) - (seg_dur / 2.0), 0.0, max_in)
        candidates.append(WindowCandidate(in_point=in_pt, out_point=in_pt + seg_dur, reason="window centered on source midpoint"))
    if slot in ("high-approach-front",) or "intro clip" in desc:
        candidates.append(WindowCandidate(in_point=0.0, out_point=seg_dur, reason="intro/start"))
    if slot in ("departure",) or "closing clip" in desc:
        candidates.append(WindowCandidate(in_point=max_in, out_point=max_in + seg_dur, reason="outro/end"))

    # Evenly spaced coverage.
    steps = max(2, count)
    for i in range(steps):
        frac = i / (steps - 1) if steps > 1 else 0.0
        in_pt = round(_clamp(max_in * frac, 0.0, max_in), 4)
        if any(abs(c.in_point - in_pt) < 0.15 for c in candidates):
            continue
        label = "start" if i == 0 else ("end" if i == steps - 1 else f"{int(frac*100)}%")
        candidates.append(WindowCandidate(in_point=in_pt, out_point=in_pt + seg_dur, reason=f"sample {label}"))

    # Keep unique, sorted, limited.
    uniq: list[WindowCandidate] = []
    for c in sorted(candidates, key=lambda x: x.in_point):
        if not any(abs(u.in_point - c.in_point) < 0.1 for u in uniq):
            uniq.append(c)
    if len(uniq) > count:
        keep = [uniq[0]]
        rest = uniq[1:]
        if rest:
            stride = max(1, len(rest) / max(1, count - 1))
            keep.extend(rest[int(i * stride)] for i in range(min(len(rest), count - 1)))
        uniq = []
        for c in sorted(keep, key=lambda x: x.in_point):
            if not any(abs(u.in_point - c.in_point) < 0.1 for u in uniq):
                uniq.append(c)
    return uniq[:count]


SELECT_SYSTEM = (
    "You select the best in-point (start time within a source clip) for a real-estate video slot. "
    "You are given the slot intent and several candidate windows (each with a representative frame image, in order). "
    "Choose the candidate whose frame best matches the slot (camera move/subject/framing/intent). "
    "Return ONLY valid JSON: "
    '{"choice_index": 0, "confidence": 0.0, "rationale": "..."} where choice_index is 0-based into candidates.'
)


def select_in_point_vision(
    client: OllamaClient,
    seg: Segment,
    candidates: list[WindowCandidate],
    *,
    model: str,
    workdir: Path,
) -> WindowCandidate | None:
    if not candidates:
        return None
    images: list[Path] = []
    cand_meta = []
    for i, c in enumerate(candidates):
        mid = c.in_point + ((c.out_point - c.in_point) / 2.0)
        frame = workdir / f"{seg.slot_id}-{i}.jpg"
        try:
            extract_frame(seg.source.path, frame, at=mid)  # type: ignore[arg-type]
            c.frame_path = frame
            images.append(frame)
            cand_meta.append({"index": i, "in_point": c.in_point, "out_point": c.out_point, "reason": c.reason})
        except Exception as e:
            c.rationale = f"frame extraction failed: {e}"
    if not images:
        return candidates[0]
    prompt = (
        f"Slot: {seg.name} (id={seg.slot_id})\n"
        f"Intent: {seg.description}\n"
        f"Hint: {seg.source.hint}\n"
        f"Resolved duration: {seg.resolved_duration}\n"
        f"Candidates (images are in the same order): {json.dumps(cand_meta)}\n"
        "Pick the best candidate index."
    )
    raw = client.chat_vision(model=model, prompt=prompt, images=images, system=SELECT_SYSTEM, format="json")
    data = extract_json_object(raw)
    if not isinstance(data, dict):
        return candidates[0]
    idx = data.get("choice_index")
    try:
        idx_i = int(idx)
    except Exception:
        idx_i = 0
    idx_i = max(0, min(idx_i, len(candidates) - 1))
    chosen = candidates[idx_i]
    chosen.score = float(data["confidence"]) if data.get("confidence") is not None else None
    chosen.rationale = str(data.get("rationale") or "")
    return chosen


def _heuristic_pick(candidates: list[WindowCandidate]) -> WindowCandidate | None:
    if not candidates:
        return None
    priority = ("outro/end", "intro/start", "window centered on source midpoint")
    for reason in priority:
        for c in candidates:
            if c.reason == reason:
                return c
    for c in candidates:
        if not c.reason.startswith("sample "):
            return c
    return candidates[0]


def select_segment_in_point(
    client: OllamaClient | None,
    seg: Segment,
    *,
    model: str | None = None,
    use_vision: bool = False,
    candidate_count: int = 5,
    workdir: Path | None = None,
) -> tuple[float, dict[str, Any]]:
    if not seg.source.path:
        raise ValueError(f"Segment {seg.slot_id} has no source path")
    info = probe_media(seg.source.path)
    if not info.duration:
        # cannot select; keep existing/default
        in_pt = float(seg.source.in_point or 0.0)
        return in_pt, {"method": "unprobed", "reason": info.error or "unknown duration"}
    cands = generate_candidates(seg, info.duration, count=candidate_count)
    chosen: WindowCandidate | None = _heuristic_pick(cands)
    method = "heuristic"
    if use_vision and client and model and cands:
        td = workdir or mkdtemp_portable(prefix="alvex-select-", for_ffmpeg=True)
        try:
            picked = select_in_point_vision(client, seg, cands, model=model, workdir=td)
            if picked:
                chosen = picked
                method = "vision"
        except Exception as e:
            method = "heuristic-fallback"
            if chosen:
                chosen.rationale = f"vision selection failed, used heuristic: {e}"
        finally:
            if workdir is None:
                shutil.rmtree(td, ignore_errors=True)
    if not chosen:
        return float(seg.source.in_point or 0.0), {"method": "none"}
    detail = {
        "method": method,
        "source_duration": info.duration,
        "resolved_duration": seg.resolved_duration,
        "candidates": [c.to_dict() for c in cands],
        "selected": chosen.to_dict(),
    }
    return chosen.in_point, detail


def apply_in_points_to_manifest(manifest: dict[str, Any], selections: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out = json.loads(json.dumps(manifest))  # deep-ish copy of jsonable
    sources = out.setdefault("sources", {})
    for slot_id, sel in selections.items():
        if "in_point" not in sel:
            continue
        entry = sources.get(slot_id)
        if isinstance(entry, str):
            entry = {"path": entry}
            sources[slot_id] = entry
        elif not isinstance(entry, dict):
            continue
        entry["in_point"] = round(float(sel["in_point"]), 4)
        sug = entry.get("_suggestion") or {}
        sug["in_point"] = entry["in_point"]
        sug["selection"] = sel.get("detail")
        entry["_suggestion"] = sug
    return out


def select_project(
    timeline_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
    ollama: OllamaConfig | None = None,
    model: str | None = None,
    use_vision: bool = False,
    candidate_count: int = 5,
    slots: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    timeline = load_timeline(timeline_path)
    manifest = load_manifest(manifest_path) if manifest_path and Path(manifest_path).exists() else {"sources": {}}
    # Apply manifest paths to timeline segments for probing/extraction; fall back to timeline mappings.
    sources = manifest.setdefault("sources", {})
    for seg in timeline.segments:
        m = sources.get(seg.slot_id)
        if isinstance(m, str):
            seg.source.path = m
            seg.source.status = "mapped"
        elif isinstance(m, dict) and m.get("path"):
            seg.source.path = str(m["path"])
            seg.source.in_point = m.get("in_point", seg.source.in_point)
            seg.source.status = "mapped"
        elif seg.source.path and seg.source.status == "mapped":
            sources[seg.slot_id] = {"path": seg.source.path}
            if seg.source.in_point is not None:
                sources[seg.slot_id]["in_point"] = seg.source.in_point

    client = OllamaClient(ollama or OllamaConfig()) if (use_vision or model) else None
    eff_model = model or (ollama.vision_model if ollama else None) or (ollama.model if ollama else None)
    selections: dict[str, dict[str, Any]] = {}
    wanted = set(slots) if slots else None
    for seg in timeline.segments:
        if wanted and seg.slot_id not in wanted:
            continue
        if seg.optional and seg.source.status != "mapped":
            continue
        if not seg.source.path:
            continue
        try:
            in_pt, detail = select_segment_in_point(
                client, seg, model=eff_model, use_vision=use_vision, candidate_count=candidate_count
            )
            selections[seg.slot_id] = {"in_point": in_pt, "detail": detail}
        except Exception as e:
            selections[seg.slot_id] = {"error": str(e)}
    updated = apply_in_points_to_manifest(manifest, selections)
    updated["project"] = timeline.project
    updated["template"] = timeline.template
    return updated, selections
