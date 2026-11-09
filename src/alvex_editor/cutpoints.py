from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .config import ProjectConfig, load_config
from .template import load_template
from .timeline import Segment


def _is_skipped_for_cutpoints(seg: Segment, *, assume_unmapped_optional: bool = True) -> bool:
    # Mirror resolve_timing's skip rule: optional + unmapped/missing path consumes no timeline.
    if not seg.optional:
        return False
    status = getattr(getattr(seg, "source", None), "status", "unmapped")
    path = getattr(getattr(seg, "source", None), "path", None)
    if status == "mapped" and path:
        return False
    return assume_unmapped_optional


def active_slots(config: ProjectConfig, *, assume_unmapped_optional: bool = True) -> list[dict[str, Any]]:
    tpl = load_template(config.template_path)
    slots = []
    for idx, s in enumerate(tpl.edit_slots, start=1):
        seg = Segment(
            slot_id=s.slot_id, name=s.name, description=s.description, optional=s.optional,
            target_duration=s.target_duration, min_duration=s.min_duration, max_duration=s.max_duration,
            source=s.source, transition_in=s.transition_in,
        )
        skipped = _is_skipped_for_cutpoints(seg, assume_unmapped_optional=assume_unmapped_optional)
        slots.append({
            "index": idx,
            "slot_id": s.slot_id,
            "name": s.name,
            "optional": bool(s.optional),
            "active": not skipped,
            "source_hint": getattr(s.source, "hint", None),
        })
    return slots


def label_cut_points(config: ProjectConfig, cut_points: list[float] | None = None, *, assume_unmapped_optional: bool = True) -> dict[str, Any]:
    cfg = config
    pts = [float(x) for x in (cut_points if cut_points is not None else ((cfg.analysis or {}).get("cut_points") or []))]
    slots = active_slots(cfg, assume_unmapped_optional=assume_unmapped_optional)
    active = [s for s in slots if s["active"]]
    rows = []
    prev = 0.0
    for i, s in enumerate(active):
        end = pts[i] if i < len(pts) else None
        dur = (end - prev) if end is not None else None
        next_slot = active[i + 1] if i + 1 < len(active) else None
        rows.append({
            "boundary": i + 1,
            "slot_id": s["slot_id"],
            "slot_name": s["name"],
            "slot_index": s["index"],
            "start": round(prev, 4),
            "end": round(end, 4) if end is not None else None,
            "duration": round(dur, 4) if dur is not None else None,
            "cuts_before": next_slot["slot_id"] if next_slot else "(end)",
            "label": f"{s['name']} → {next_slot['name']}" if next_slot else f"{s['name']} (end)",
        })
        if end is not None:
            prev = end
    warnings = []
    if pts and len(pts) != len(active):
        warnings.append(f"cut_points count ({len(pts)}) != active segment count ({len(active)}); boundaries labeled by order up to available items.")
    return {
        "template": str(cfg.template_path),
        "slots_total": len(slots),
        "active_slots": len(active),
        "skipped_slots": [s["slot_id"] for s in slots if not s["active"]],
        "cut_points": [round(x, 4) for x in pts],
        "boundaries": rows,
        "warnings": warnings,
    }


def detect_onset_pairs(onsets: list[float], *, min_gap: float = 0.8, max_gap: float = 1.4) -> list[dict[str, float]]:
    pts = sorted(float(x) for x in onsets)
    pairs = []
    for i in range(len(pts) - 1):
        gap = pts[i + 1] - pts[i]
        if min_gap <= gap <= max_gap:
            pairs.append({"first": round(pts[i], 4), "second": round(pts[i + 1], 4), "gap": round(gap, 4)})
    return pairs


def suggest_second_of_pair(onsets: list[float], *, target: float | None = None, near: float | None = None, min_gap: float = 0.8, max_gap: float = 1.4) -> dict[str, Any] | None:
    pairs = detect_onset_pairs(onsets, min_gap=min_gap, max_gap=max_gap)
    if not pairs:
        return None
    ref = near if near is not None else target
    if ref is None:
        return pairs[0]
    # Prefer pair bracketing/near ref; bias toward using the 2nd onset as the cut target.
    def score(p: dict[str, float]) -> tuple[float, float, float]:
        # if ref is within/near the pair window, great; otherwise distance to nearest edge
        window = 0.0 if (p["first"] - 0.25) <= ref <= (p["second"] + 0.25) else min(abs(p["first"] - ref), abs(p["second"] - ref))
        return (window, abs(p["second"] - ref), abs(p["first"] - ref))
    return sorted(pairs, key=score)[0]


def nearest_onset(onsets: list[float], near: float) -> float | None:
    pts = [float(x) for x in onsets if x is not None]
    if not pts:
        return None
    return round(min(pts, key=lambda x: abs(x - float(near))), 4)


def nudge_cut_points(cut_points: list[float], *, near: float, to: float | str, onsets: list[float] | None = None, min_gap: float = 0.8, max_gap: float = 1.4) -> dict[str, Any]:
    pts = [float(x) for x in cut_points]
    if not pts:
        raise ValueError("No cut points to nudge")
    idx = min(range(len(pts)), key=lambda i: abs(pts[i] - float(near)))
    old = pts[idx]
    suggestion = None
    if isinstance(to, (int, float)):
        new = float(to)
        reason = "explicit"
    else:
        s = str(to).strip().lower()
        if s in ("second", "second-of-pair", "2nd", "2nd-of-pair", "pair-second"):
            pair = suggest_second_of_pair(onsets or [], near=old, min_gap=min_gap, max_gap=max_gap)
            if not pair:
                raise ValueError(f"No onset pair (gap {min_gap}-{max_gap}s) found near {old:g}s")
            new = float(pair["second"])
            reason = "second-of-pair"
            suggestion = pair
        elif s in ("nearest", "onset", "nearest-onset"):
            n = nearest_onset(onsets or [], old)
            if n is None:
                raise ValueError("No onsets available to snap to")
            new = n
            reason = "nearest-onset"
        else:
            try:
                new = float(s)
                reason = "explicit"
            except ValueError as e:
                raise ValueError(f"Unsupported nudge target: {to!r}") from e
    pts[idx] = round(new, 4)
    pts = sorted(pts)
    return {
        "index": idx,
        "boundary": idx + 1,
        "near": round(float(near), 4),
        "old": round(old, 4),
        "new": round(new, 4),
        "reason": reason,
        "suggestion": suggestion,
        "cut_points": [round(x, 4) for x in pts],
        "requires_confirmation": True,
    }


def suggest_cut_points(config: ProjectConfig, *, onsets: list[float] | None = None, count: int | None = None, use_second_of_pair: bool = False, min_gap: float = 0.8, max_gap: float = 1.4) -> dict[str, Any]:
    labeled = label_cut_points(config)
    n = count if count is not None else int(labeled["active_slots"])
    pts = sorted(float(x) for x in (onsets or []))
    if not pts:
        return {"ok": False, "error": "No onsets/candidates available (run analyze --backend onsets or provide candidates)", "active_slots": n, "suggested_cut_points": []}
    # simple even selection across onset candidates
    if len(pts) <= n:
        chosen = pts[:]
    else:
        chosen = []
        for i in range(n):
            pos = (i + 1) * (len(pts) - 1) / max(1, n)
            j = min(len(pts) - 1, max(0, int(round(pos))))
            chosen.append(pts[j])
        # dedupe while preserving order
        dedup = []
        for v in chosen:
            if not dedup or abs(v - dedup[-1]) > 1e-6:
                dedup.append(v)
        chosen = dedup
    if use_second_of_pair:
        adjusted = []
        for v in chosen:
            pair = suggest_second_of_pair(pts, near=v, min_gap=min_gap, max_gap=max_gap)
            adjusted.append(float(pair["second"]) if pair else v)
        chosen = sorted(set(round(x, 4) for x in adjusted))
    return {
        "ok": True,
        "template_aware_count": n,
        "active_slots": n,
        "skipped_slots": labeled["skipped_slots"],
        "candidate_onsets": len(pts),
        "used_second_of_pair": use_second_of_pair,
        "suggested_cut_points": [round(x, 4) for x in chosen],
        "labeled_preview": label_cut_points(config, chosen)["boundaries"],
        "requires_confirmation": True,
    }
