from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Self

from .policy import ensure_not_inside_repo


@dataclass
class TimeRange:
    start: float | None = None
    end: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}


@dataclass
class SourceRef:
    # Path or identifier of the media source; None when unmapped.
    path: str | None = None
    # Recording/slot hint used for mapping (e.g., "Mid Orbit").
    hint: str | None = None
    in_point: float | None = None
    out_point: float | None = None
    status: str = "unmapped"  # unmapped | mapped | missing

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SourceRef":
        data = data or {}
        return cls(path=data.get("path"), hint=data.get("hint"), in_point=data.get("in_point"), out_point=data.get("out_point"), status=data.get("status") or "unmapped")


@dataclass
class Overlay:
    type: str  # title, text, image
    text: str | None = None
    asset: str | None = None
    # float seconds from segment start, or a string ref like "end-5" (seconds before segment end).
    start: float | str | None = None
    end: float | str | None = None
    fade_in: float | None = None
    fade_out: float | None = None
    position: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Overlay":
        return cls(type=data.get("type", "text"), text=data.get("text"), asset=data.get("asset"), start=data.get("start"), end=data.get("end"), fade_in=data.get("fade_in"), fade_out=data.get("fade_out"), position=data.get("position"))


@dataclass
class AudioEffect:
    fade_in: float | None = None
    fade_out: float | None = None
    fade_out_end_before: float | None = None  # seconds before segment end when fade-out completes
    gain: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AudioEffect":
        data = data or {}
        return cls(
            fade_in=data.get("fade_in"),
            fade_out=data.get("fade_out"),
            fade_out_end_before=data.get("fade_out_end_before"),
            gain=data.get("gain"),
        )


@dataclass
class Transition:
    type: str = "cut"  # cut, fade, etc.
    duration: float | None = None
    align: str | None = None  # on-beat, fixed

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Transition":
        data = data or {}
        return cls(type=data.get("type") or "cut", duration=data.get("duration"), align=data.get("align"))


@dataclass
class Segment:
    slot_id: str
    name: str
    description: str = ""
    optional: bool = False
    target_duration: float | None = None
    min_duration: float | None = None
    max_duration: float | None = None
    resolved_duration: float | None = None
    timeline_in: float | None = None
    timeline_out: float | None = None
    source: SourceRef = field(default_factory=SourceRef)
    transition_in: Transition = field(default_factory=Transition)
    overlays: list[Overlay] = field(default_factory=list)
    video_effects: list[dict[str, Any]] = field(default_factory=list)
    audio: AudioEffect = field(default_factory=AudioEffect)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "slot_id": self.slot_id,
            "name": self.name,
            "description": self.description,
            "optional": self.optional,
            "target_duration": self.target_duration,
            "min_duration": self.min_duration,
            "max_duration": self.max_duration,
            "resolved_duration": self.resolved_duration,
            "timeline_in": self.timeline_in,
            "timeline_out": self.timeline_out,
            "source": self.source.to_dict(),
            "transition_in": self.transition_in.to_dict(),
            "overlays": [o.to_dict() for o in self.overlays],
            "video_effects": self.video_effects,
            "audio": self.audio.to_dict(),
            "notes": self.notes,
        }
        return {k: v for k, v in data.items() if v not in (None, "", [], {}) or k in ("slot_id", "name", "optional", "source", "transition_in")}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Segment":
        return cls(
            slot_id=data["slot_id"],
            name=data.get("name") or data["slot_id"],
            description=data.get("description") or "",
            optional=bool(data.get("optional")),
            target_duration=data.get("target_duration"),
            min_duration=data.get("min_duration"),
            max_duration=data.get("max_duration"),
            resolved_duration=data.get("resolved_duration"),
            timeline_in=data.get("timeline_in"),
            timeline_out=data.get("timeline_out"),
            source=SourceRef.from_dict(data.get("source")),
            transition_in=Transition.from_dict(data.get("transition_in")),
            overlays=[Overlay.from_dict(o) for o in (data.get("overlays") or [])],
            video_effects=list(data.get("video_effects") or []),
            audio=AudioEffect.from_dict(data.get("audio")),
            notes=list(data.get("notes") or []),
        )


@dataclass
class Timeline:
    version: int = 1
    project: str | None = None
    template: str | None = None
    soundtrack: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    variables: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    segments: list[Segment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "version": self.version,
            "project": self.project,
            "template": self.template,
            "soundtrack": self.soundtrack,
            "created_at": self.created_at,
            "variables": self.variables,
            "analysis": self.analysis,
            "segments": [s.to_dict() for s in self.segments],
        }
        return {k: v for k, v in data.items() if v not in (None, {}, []) or k in ("version", "variables", "segments")}

    def write(self, path: str | Path) -> Path:
        path = Path(path)
        ensure_not_inside_repo(path, kind="timeline/edit plan")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Timeline":
        return cls(
            version=int(data.get("version") or 1),
            project=data.get("project"),
            template=data.get("template"),
            soundtrack=data.get("soundtrack"),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            variables=dict(data.get("variables") or {}),
            analysis=dict(data.get("analysis") or {}),
            segments=[Segment.from_dict(s) for s in (data.get("segments") or [])],
        )


def load_timeline(path: str | Path) -> Timeline:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return Timeline.from_dict(data)
