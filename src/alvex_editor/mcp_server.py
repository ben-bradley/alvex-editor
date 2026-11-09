"""MCP server exposing Alvex Editor as tools for AI agents.

Run (after installing the optional extra): `alvex-editor-mcp`
Or: `python -m alvex_editor.mcp_server`

Install: `pip install "alvex-editor[agent]"`

Tools wrap `alvex_editor.api` and preserve human-confirmation gates:
- suggest_* tools write suggested manifests and set requires_confirmation; pass apply=True only with explicit user confirmation.
- render_video defaults to dry_run/preview-friendly use; only execute a real render when explicitly requested.
"""

from __future__ import annotations

from typing import Any


def _load_server_class():
    # Support MCP Python SDK v2 (MCPServer) and v1 (FastMCP).
    try:
        from mcp.server.mcpserver import MCPServer  # type: ignore

        return MCPServer
    except Exception:
        pass
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore

        return FastMCP
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "The MCP SDK is required for the Alvex MCP server. Install with: pip install 'alvex-editor[agent]' (mcp>=1.0)"
        ) from e


def build_server():
    from . import api

    Server = _load_server_class()
    mcp = Server("alvex-editor")

    @mcp.tool()
    def workspace_info(workspace: str | None = None, save: bool = False) -> dict[str, Any]:
        """Show the visible Alvex workspace (outside repo): ~/Alvex with templates/, soundtracks/, projects/. At chat start, confirm these locations with the user. save=true writes config and ensures dirs (explicit intent)."""
        return api.workspace_info(workspace=workspace, save=save)

    @mcp.tool()
    def list_templates(workspace: str | None = None) -> dict[str, Any]:
        """List available templates from the bundled repo example and the user template registry (~/Alvex/templates/)."""
        return api.templates_list(workspace=workspace)

    @mcp.tool()
    def list_soundtracks(workspace: str | None = None) -> dict[str, Any]:
        """List the soundtrack registry (~/Alvex/soundtracks/), including whether each has curated, reusable cut points."""
        return api.soundtracks_list(workspace=workspace)

    @mcp.tool()
    def init_project(
        template: str = "standard real estate template",
        soundtrack: str | None = None,
        clips_dir: str | None = None,
        address: str | None = None,
        name: str | None = None,
        project_id: str | None = None,
        workspace: str | None = None,
        on_exists: str = "fail",
        register_soundtrack: bool = False,
        soundtrack_title: str | None = None,
    ) -> dict[str, Any]:
        """Create a new project under ~/Alvex/projects/<slug>/ (outside repo) from resolved inputs. Resolves template aliases and soundtrack registry (reuses curated cut points if present). Confirm resolved inputs with the user. If the project exists, on_exists='fail' returns requires_resolution+options (ask the user, then retry with overwrite|suffix)."""
        variables = {"address": address} if address else None
        return api.init_project(workspace=workspace, name=name, address=address, template=template, soundtrack=soundtrack, clips_dir=clips_dir, project_id=project_id, variables=variables, on_exists=on_exists, register_soundtrack=register_soundtrack, soundtrack_title=soundtrack_title)

    @mcp.tool()
    def import_soundtrack(source: str, workspace: str | None = None, track_id: str | None = None, title: str | None = None) -> dict[str, Any]:
        """Copy/import an MP3 into the soundtrack registry (~/Alvex/soundtracks/<id>/) so it is self-contained and reusable."""
        return api.soundtrack_import(source=source, workspace=workspace, track_id=track_id, title=title)

    @mcp.tool()
    def save_soundtrack_cut_points(soundtrack: str, cut_points: list[float] | None = None, bpm: float | None = None, offset: float | None = None, notes: list[str] | None = None, workspace: str | None = None) -> dict[str, Any]:
        """Save curated, human-confirmed cut points for a registered soundtrack (map once, reuse). Call only after reviewing/confirming the cut points with the user."""
        return api.soundtrack_set_cut_points(soundtrack=soundtrack, workspace=workspace, cut_points=cut_points, bpm=bpm, offset=offset, notes=notes, method="curated")

    @mcp.tool()
    def project_status(project: str) -> dict[str, Any]:
        """Inspect an Alvex project: config, template/soundtrack/clips presence, timeline/analysis cache, sources manifest, resolved ffmpeg/ffprobe info, and ollama availability."""
        return api.project_status(project=project)

    @mcp.tool()
    def doctor(project: str | None = None) -> dict[str, Any]:
        """Diagnose environment and optional project readiness: resolved ffmpeg/ffprobe paths (PATH/env/WinGet hints), platform, and project issues/notes (stale timeline soundtrack, missing manifest, etc.)."""
        return api.doctor(project=project)

    @mcp.tool()
    def template_info(project: str) -> dict[str, Any]:
        """Parse and return a project's template (slots, order, constraints)."""
        return api.template_info(project=project)

    @mcp.tool()
    def analyze_soundtrack(project: str, backend: str = "auto", refresh: bool = False, output: str | None = None) -> dict[str, Any]:
        """Analyze a project's soundtrack into a beat/cut-point grid. backend: auto|onsets|librosa|library. Uses/rebuilds the song cut-point library (hash-cached) unless refresh. Explicit config cut_points/bpm/beat_times may take precedence per config rules."""
        return api.analyze(project=project, backend=backend, refresh=refresh, output=output, write_cache=True)

    @mcp.tool()
    def plan_timeline(project: str, map_clips: bool = False, run_analyze: bool = True, output: str | None = None) -> dict[str, Any]:
        """Build/resolve timeline.json from the template (+ optional analysis and filename-based clip mapping)."""
        return api.plan(project=project, output=output, map_clips=map_clips, run_analyze=run_analyze)

    @mcp.tool()
    def suggest_clip_mapping(project: str, clips: str | None = None, timeline: str | None = None, vision: bool = False, host: str | None = None, model: str | None = None, vision_model: str | None = None, output: str | None = None, manifest: str | None = None, apply: bool = False) -> dict[str, Any]:
        """Suggest clip-to-slot mappings (Ollama). Writes a suggested manifest for review. IMPORTANT: requires_confirmation unless apply=True; set apply=True ONLY with explicit user confirmation."""
        return api.suggest_mapping(project=project, timeline=timeline, clips=clips, host=host, model=model, vision_model=vision_model, vision=vision, output=output, manifest=manifest, apply=apply)

    @mcp.tool()
    def suggest_inpoints(project: str, timeline: str | None = None, manifest: str | None = None, vision: bool = False, candidates: int = 5, slots: list[str] | None = None, host: str | None = None, model: str | None = None, vision_model: str | None = None, output: str | None = None, apply: bool = False) -> dict[str, Any]:
        """Suggest in-points (segment selection) for mapped clips. Writes a suggested manifest for review. IMPORTANT: requires_confirmation unless apply=True; set apply=True ONLY with explicit user confirmation."""
        return api.suggest_inpoints(project=project, timeline=timeline, manifest=manifest, host=host, model=model, vision_model=vision_model, vision=vision, candidates=candidates, slots=slots, output=output, apply=apply)

    @mcp.tool()
    def apply_manifest(project: str | None = None, suggested: str = "", target: str | None = None) -> dict[str, Any]:
        """Apply a reviewed suggested manifest to a target manifest. Explicit confirmation action (call only after the user has reviewed/approved the suggestion)."""
        if not suggested:
            return {"ok": False, "command": "apply_manifest", "error": "suggested manifest path is required"}
        return api.apply_manifest_file(project=project, suggested=suggested, target=target)

    @mcp.tool()
    def cuts_show(project: str, cut_points: list[float] | None = None) -> dict[str, Any]:
        """Show slot-labeled cut-point boundaries for a project (Features/optional-skipped aware). cut_points overrides config when provided."""
        return api.cuts_show(project=project, cut_points=cut_points)

    @mcp.tool()
    def cuts_suggest(project: str, count: int | None = None, use_second_of_pair: bool = False, near: float | None = None) -> dict[str, Any]:
        """Suggest template-aware cut points from cached onset/analysis candidates. Not applied (requires_confirmation). use_second_of_pair snaps to the 2nd onset in detected pairs."""
        return api.cuts_suggest(project=project, count=count, use_second_of_pair=use_second_of_pair, near=near)

    @mcp.tool()
    def cuts_nudge(project: str, near: float, to: float | str, cut_points: list[float] | None = None) -> dict[str, Any]:
        """Suggest nudging the cut point nearest `near` seconds to a value or pattern ("second-of-pair"/"nearest-onset"). Not applied (requires_confirmation)."""
        return api.cuts_nudge(project=project, near=near, to=to, cut_points=cut_points)

    @mcp.tool()
    def cuts_apply(project: str, cut_points: list[float], save_config: bool = True) -> dict[str, Any]:
        """Apply cut points to the project config (explicit action). Writes config outside the repo when save_config=true."""
        return api.cuts_apply(project=project, cut_points=cut_points, save_config=save_config)

    @mcp.tool()
    def cuts_preview(project: str, cut_points: list[float] | None = None, save_config: bool = False) -> dict[str, Any]:
        """One-step explicit iteration: re-plan from current config and render a preview (uses project render config/fresh timeline). Optionally set cut points; persists to config only when save_config=true (explicit)."""
        return api.cuts_preview(project=project, cut_points=cut_points, save_config=save_config)

    @mcp.tool()
    def render_video(project: str | None = None, timeline: str | None = None, manifest: str | None = None, output: str | None = None, soundtrack: str | None = None, preview: bool = True, dry_run: bool = False, print_filter: bool = False, allow_unmapped: bool = False, no_plan: bool = False, no_probe: bool = False, strict_duration: bool = False) -> dict[str, Any]:
        """Render a resolved timeline with FFmpeg. Defaults to preview=True. Use dry_run=True to inspect the command/filter without executing. Set preview=False and dry_run=False only for an intentional final render. When project is provided and timeline is omitted, re-plans from current config (timing/cut-points/render/soundtrack/manifest) unless no_plan=true."""
        return api.render(project=project, timeline=timeline, manifest=manifest, output=output, soundtrack=soundtrack, preview=preview, dry_run=dry_run, print_filter=print_filter, allow_unmapped=allow_unmapped, no_plan=no_plan, no_probe=no_probe, strict_duration=strict_duration)

    return mcp


def main() -> None:
    mcp = build_server()
    mcp.run()


if __name__ == "__main__":
    main()
