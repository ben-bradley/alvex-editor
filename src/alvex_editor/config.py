from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


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


def load_config(path: str | Path) -> ProjectConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Project config not found: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Project config must be a YAML mapping: {config_path}")
    missing = REQUIRED_FIELDS - set(data)
    if missing:
        raise ValueError(f"Project config missing required field(s): {', '.join(sorted(missing))}")
    project_dir = config_path.parent
    analysis = data.get("analysis") or {}
    # Convenience shorthands.
    if "soundtrack_bpm" in data and "bpm" not in analysis:
        analysis = {**analysis, "bpm": data["soundtrack_bpm"]}
    if "beat_offset" in data and "offset" not in analysis:
        analysis = {**analysis, "offset": data["beat_offset"]}
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
        raw=data,
    )
