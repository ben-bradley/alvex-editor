from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .structured import find_project_config, load_structured
from .validation import merge_preset, validate_config


@dataclass
class ProjectConfig:
    # Paths are resolved relative to the config file's directory.
    config_path: Path
    project_dir: Path
    template: str
    soundtrack: str | None = None
    clips_dir: str | None = None
    overlays_dir: str | None = None
    branding_dir: str | None = None
    output_dir: str = "output"
    timeline_path: str = "timeline.json"
    analysis_path: str = "analysis.json"
    sources_manifest: str | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    timing: dict[str, Any] = field(default_factory=dict)
    ollama: dict[str, Any] = field(default_factory=dict)
    name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    segment_overrides: dict[str, Any] = field(default_factory=dict)

    def resolve(self, value: str | None) -> Path | None:
        if value is None:
            return None
        p = Path(value).expanduser()
        if not p.is_absolute():
            p = (self.project_dir / p).resolve()
        return p

    @property
    def template_path(self) -> Path:
        path = self.resolve(self.template)
        assert path is not None
        return path

    @property
    def soundtrack_path(self) -> Path | None:
        return self.resolve(self.soundtrack)

    @property
    def clips_path(self) -> Path | None:
        return self.resolve(self.clips_dir)

    @property
    def output_path(self) -> Path:
        path = self.resolve(self.output_dir)
        assert path is not None
        return path

    @property
    def resolved_timeline_path(self) -> Path:
        path = self.resolve(self.timeline_path)
        assert path is not None
        return path

    @property
    def resolved_analysis_path(self) -> Path:
        path = self.resolve(self.analysis_path)
        assert path is not None
        return path

    @property
    def resolved_sources_manifest(self) -> Path | None:
        return self.resolve(self.sources_manifest)


REQUIRED_FIELDS = {"template"}


def _load_preset(data: dict[str, Any], *, project_dir: Path) -> dict[str, Any] | None:
    ref = data.get("preset") or data.get("style_preset")
    if not ref or not isinstance(ref, str):
        return None
    # project-local preset file
    for base in [project_dir, project_dir / "presets"]:
        name = ref if ref.endswith(".json") else f"{ref}.json"
        p = (base / name)
        if p.exists():
            d = load_structured(p)
            return d if isinstance(d, dict) else None
    # workspace presets
    try:
        from .workspace import load_workspace
        ws = load_workspace(start=project_dir)
        p = (ws.root / "presets" / (ref if ref.endswith(".json") else f"{ref}.json"))
        if p.exists():
            d = load_structured(p)
            return d if isinstance(d, dict) else None
    except Exception:
        pass
    # inline presets map
    presets = data.get("presets")
    if isinstance(presets, dict) and isinstance(presets.get(ref), dict):
        return presets[ref]
    return None


def load_config(path: str | Path, *, validate: bool = True) -> ProjectConfig:
    config_path = find_project_config(path)
    config_path = Path(config_path).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Project config not found: {config_path} (expected alvex.json)")
    raw_data = load_structured(config_path) or {}
    if not isinstance(raw_data, dict):
        raise ValueError(f"Project config must be a JSON object: {config_path}")
    project_dir = config_path.parent
    preset = _load_preset(raw_data, project_dir=project_dir)
    data = merge_preset(raw_data, preset)
    validation_warnings: list[str] = []
    if validate:
        vr = validate_config(data)
        if not vr.ok:
            raise ValueError("Invalid project config: " + "; ".join(vr.errors))
        validation_warnings = vr.warnings
    missing = REQUIRED_FIELDS - set(data)
    if missing:
        raise ValueError(f"Project config missing required field(s): {', '.join(sorted(missing))}")
    analysis = data.get("analysis") or {}
    # Convenience shorthands.
    if "soundtrack_bpm" in data and "bpm" not in analysis:
        analysis = {**analysis, "bpm": data["soundtrack_bpm"]}
    if "beat_offset" in data and "offset" not in analysis:
        analysis = {**analysis, "offset": data["beat_offset"]}
    seg_ov = data.get("segment_overrides") or data.get("slot_overrides") or {}
    if not isinstance(seg_ov, dict):
        seg_ov = {}
    return ProjectConfig(
        config_path=config_path,
        project_dir=project_dir,
        template=str(data["template"]),
        soundtrack=data.get("soundtrack"),
        clips_dir=data.get("clips_dir"),
        overlays_dir=data.get("overlays_dir"),
        branding_dir=data.get("branding_dir"),
        output_dir=str(data.get("output_dir", "output")),
        timeline_path=str(data.get("timeline_path", "timeline.json")),
        analysis_path=str(data.get("analysis_path", "analysis.json")),
        sources_manifest=data.get("sources_manifest") or data.get("manifest"),
        variables=data.get("variables") or {},
        analysis=analysis,
        timing=data.get("timing") or {},
        ollama=data.get("ollama") or {},
        name=data.get("name"),
        raw=raw_data,
        warnings=validation_warnings,
        segment_overrides=seg_ov,
    )
