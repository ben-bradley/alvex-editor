from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from .timeline import AudioEffect, Overlay, Segment, SourceRef, Transition


@dataclass
class TemplateSection:
    heading: str
    level: int
    content: str


@dataclass
class VideoTemplate:
    path: Path
    title: str = ""
    sections: list[TemplateSection] = field(default_factory=list)
    edit_slots: list[Segment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "title": self.title,
            "sections": [{"heading": s.heading, "level": s.level, "content": s.content} for s in self.sections],
            "edit_slots": [s.to_dict() for s in self.edit_slots],
        }


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
EDIT_ITEM_RE = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*[-–—:]\s*(.*)$")
DURATION_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-–to]+\s*(\d+(?:\.\d+)?)\s*second", re.I)
DURATION_SINGLE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*second", re.I)
FADE_IN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*second\s+fade\s*in", re.I)
FADE_OUT_END_RE = re.compile(r"(?:fade(?:s)?\s+to\s+black|fade\s*out|music(?:\s+volume)?\s+also\s+fades).*?starting\s+at\s+(\d+(?:\.\d+)?)\s*seconds?\s+before\s+the\s+end", re.I)
FADE_BLACK_END_RE = re.compile(r"(?:slow\s+)?fade\s+to\s+black.*?starting\s+at\s+(\d+(?:\.\d+)?)\s*seconds?\s+before\s+the\s+end", re.I)
MUSIC_FADE_END_RE = re.compile(r"music(?:\s+volume)?\s+also\s+fades.*?starting\s+at\s+(\d+(?:\.\d+)?)\s*seconds?\s+before\s+the\s+end", re.I)
TITLE_VISIBLE_RE = re.compile(r"title\s+is\s+visible\s+after\s+(?:the\s+)?(?:(first)\s+second|(\d+(?:\.\d+)?)\s*seconds?)\s+of\s+the\s+fade\s*in\s+and\s+is\s+visible\s+for\s+(\d+(?:\.\d+)?)\s*seconds?", re.I)
TITLE_ADDRESS_RE = re.compile(r"title\s+(?:that\s+is\s+)?(?:the\s+)?address", re.I)
TITLE_END_RE = re.compile(r"title(?:\s+overlay)?\s+fades\s+in.*?(\d+(?:\.\d+)?)\s*seconds?\s+before\s+the\s+end", re.I)
TAKEN_FROM_RE = re.compile(r"taken\s+from\s+the\s+\*\*(.+?)\*\*\s+recording", re.I)
HINT_FROM_RE = re.compile(r"clip\s+is\s+taken\s+from\s+the\s+\*\*(.+?)\*\*", re.I)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "slot"


def parse_sections(text: str) -> list[TemplateSection]:
    lines = text.splitlines()
    sections: list[TemplateSection] = []
    current_heading = "__preamble__"
    current_level = 0
    buf: list[str] = []
    for line in lines:
        m = HEADING_RE.match(line)
        if m:
            if buf or current_heading != "__preamble__":
                sections.append(TemplateSection(current_heading, current_level, "\n".join(buf).strip()))
            current_level = len(m.group(1))
            current_heading = m.group(2).strip()
            buf = []
        else:
            buf.append(line)
    if buf or current_heading != "__preamble__":
        sections.append(TemplateSection(current_heading, current_level, "\n".join(buf).strip()))
    return sections


def _find_section(sections: list[TemplateSection], name: str) -> TemplateSection | None:
    want = name.strip().lower()
    for s in sections:
        if s.heading.strip().lower() == want:
            return s
    for s in sections:
        if want in s.heading.strip().lower():
            return s
    return None


def _extract_durations(text: str) -> tuple[float | None, float | None, float | None]:
    m = DURATION_RANGE_RE.search(text)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (lo + hi) / 2, lo, hi
    # Avoid grabbing "5 second fade in" as the whole clip duration when it's clearly an effect;
    # prefer ranges for clip duration. Single values are used cautiously.
    return None, None, None


def _extract_source_hint(name: str, text: str) -> str | None:
    for rx in (TAKEN_FROM_RE, HINT_FROM_RE):
        m = rx.search(text)
        if m:
            return m.group(1).strip()
    # Heuristic mappings from the sample template's naming.
    low = (name + " " + text).lower()
    if "mid orbit front" in low:
        return "Mid Orbit"
    if "mid orbit back" in low:
        return "Mid Orbit"
    if "high orbit front" in low or "high orbit back" in low:
        return "High Orbit"
    if "pan front" in low:
        return "Pan Front"
    if "pan back" in low:
        return "Pan Back"
    if "approach door" in low:
        return "Approach Door"
    if "rise up" in low:
        return "Rise Up"
    if "departure" in low:
        return "Departure"
    if "high approach front" in low:
        return "High Approach Front"
    if "feature" in low:
        return "Features"
    return name


def _parse_effects(name: str, text: str, index: int, total: int) -> tuple[list[Overlay], list[dict[str, Any]], AudioEffect, list[str]]:
    overlays: list[Overlay] = []
    video_effects: list[dict[str, Any]] = []
    audio = AudioEffect()
    notes: list[str] = []
    low = text.lower()
    is_intro = index == 1 or "intro clip" in low
    is_outro = index == total or "closing clip" in low or name.strip().lower() == "departure"

    fade_in = FADE_IN_RE.search(text)
    if fade_in and (is_intro or "fade in" in low):
        dur = float(fade_in.group(1))
        video_effects.append({"type": "fade_in", "duration": dur})
        if "music" in low and "fades in" in low:
            audio.fade_in = dur
        notes.append(f"video fade-in {dur}s")
        if audio.fade_in:
            notes.append(f"music fade-in {dur}s")

    def _fmt_num(n: float) -> str:
        return f"{n:g}"

    if TITLE_ADDRESS_RE.search(text) or ("address" in low and "title" in low):
        vis = TITLE_VISIBLE_RE.search(text)
        if vis:
            after = 1.0 if vis.group(1) else float(vis.group(2))
            visible_for = float(vis.group(3))
            overlays.append(Overlay(type="title", text="${address}", start=after, end=after + visible_for))
            notes.append(f"title ${{address}} {_fmt_num(after)}s-{_fmt_num(after + visible_for)}s")
        elif is_outro:
            end_m = TITLE_END_RE.search(text)
            if end_m:
                before = float(end_m.group(1))
                overlays.append(Overlay(type="title", text="${address}", start=f"end-{_fmt_num(before)}", end="end", fade_in=1.0))
                notes.append(f"title ${{address}} last {_fmt_num(before)}s")
        else:
            overlays.append(Overlay(type="title", text="${address}"))
            notes.append("title ${address}")

    if is_outro:
        black = FADE_BLACK_END_RE.search(text)
        if black:
            before = float(black.group(1))
            video_effects.append({"type": "fade_out", "duration": before, "anchor": "end"})
            notes.append(f"fade to black last {_fmt_num(before)}s")
        music = MUSIC_FADE_END_RE.search(text)
        if music:
            audio.fade_out = float(music.group(1))
            notes.append(f"music fade-out last {_fmt_num(audio.fade_out)}s")
        end_t = TITLE_END_RE.search(text)
        if end_t and not any(o.text == "${address}" for o in overlays):
            before = float(end_t.group(1))
            overlays.append(Overlay(type="title", text="${address}", start=f"end-{_fmt_num(before)}", end="end", fade_in=1.0))
            notes.append(f"title ${{address}} last {_fmt_num(before)}s")

    if "cut" in low and "beat" in low:
        notes.append("cut on beat")
    return overlays, video_effects, audio, notes


def parse_edit_sequence(section: TemplateSection) -> list[Segment]:
    segments: list[Segment] = []
    items: list[tuple[int, str, str]] = []
    for line in section.content.splitlines():
        m = EDIT_ITEM_RE.match(line.strip())
        if m:
            items.append((int(m.group(1)), m.group(2).strip(), m.group(3).strip()))
    total = len(items)
    for idx, name, desc in items:
        target, lo, hi = _extract_durations(desc)
        optional = bool(re.search(r"\boptional\b", desc, re.I) or re.search(r"\boptional\b", name, re.I))
        # Features slot in the sample is optional even if phrasing varies slightly.
        if slugify(name) == "features":
            optional = True
        overlays, video_effects, audio, notes = _parse_effects(name, desc, idx, total)
        source_hint = _extract_source_hint(name, desc)
        transition = Transition(type="cut", align="on-beat" if "beat" in desc.lower() or "beat" in section.content.lower() else None)
        segments.append(
            Segment(
                slot_id=slugify(name),
                name=name,
                description=desc,
                optional=optional,
                target_duration=target,
                min_duration=lo,
                max_duration=hi,
                source=SourceRef(hint=source_hint, status="unmapped"),
                transition_in=transition,
                overlays=overlays,
                video_effects=video_effects,
                audio=audio,
                notes=notes,
            )
        )
    return segments


def load_template(path: str | Path) -> VideoTemplate:
    path = Path(path).expanduser().resolve()
    text = path.read_text(encoding="utf-8")
    sections = parse_sections(text)
    title = ""
    for s in sections:
        if s.level == 1 and s.heading != "__preamble__":
            title = s.heading
            break
    edit_section = _find_section(sections, "Clip Edit Sequence")
    edit_slots = parse_edit_sequence(edit_section) if edit_section else []
    return VideoTemplate(path=path, title=title, sections=sections, edit_slots=edit_slots)
