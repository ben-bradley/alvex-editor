# Using Alvex Editor with OpenWebUI (via Docker) + MCP

Alvex Editor's MCP server lets you drive the full workflow (init, plan, render, etc.) from a chat interface. OpenWebUI is a great self-hosted option that works with Ollama or any OpenAI-compatible provider.

> **Note on file access:** When running OpenWebUI in Docker, the MCP server runs inside the container or needs access to your files. The biggest gotcha is path mapping - files you reference (clips, soundtracks, workspace) must be mounted into the container and referenced by the paths the container sees.

## Prerequisites
- Docker installed
- FFmpeg available where the MCP server runs (if running MCP in container, install it there)
- Ollama running locally (optional - only needed for AI features like `align`/`select`)

## Option 1: Run MCP server on host, OpenWebUI in Docker (easier for file access)
This is often simplest because the MCP server can access your host filesystem directly.

1. Install Alvex Editor on host:
```bash
pip install -e ".[agent]"  # or from PyPI when published
```

2. Run OpenWebUI in Docker:
```bash
docker run -d --name openwebui -p 3000:8080 \
  -v openwebui-data:/app/backend/data \
  --add-host=host.docker.internal:host-gateway \
  ghcr.io/open-webui/open-webui:main
```

3. In OpenWebUI: Admin Panel → Settings → Tools → MCP Servers → Add Server
- Type: `stdio`
- Command: `python` (or full path to python from your venv)
- Args: `["-m", "alvex_editor.mcp_server"]`
- Environment: may need `ALVEX_WORKSPACE` if non-default

4. File access: Since MCP runs on host, it can access any path on host. When the agent references files, use host paths as normal. This avoids most Docker volume mapping issues.

## Option 2: Run both in Docker (more isolated)
More complex for file access. You'll need to mount everything.

1. Create a docker-compose setup or mount volumes:
```bash
docker run -d --name openwebui -p 3000:8080 \
  -v openwebui-data:/app/backend/data \
  -v ~/Alvex:/data/Alvex \
  -v /path/to/clips:/data/clips \
  ghcr.io/open-webui/open-webui:main
```

2. Run MCP server in a container with access to those mounts and ffmpeg installed. Configure OpenWebUI to connect to it (stdio over docker exec, or TCP if you expose it).

3. Set `ALVEX_WORKSPACE=/data/Alvex` and use container paths in all commands (e.g., `/data/clips/...`).

**Tips:**
- Core workflow (init/plan/render) doesn't require Ollama. AI features need Ollama reachable from the MCP environment.
- Use `alvex-editor mcp` to print configuration snippets.
- Keep all project assets outside the repo (workspace `~/Alvex` is ideal).
- If ffmpeg isn't found, set `FFMPEG`/`FFPROBE` env vars or ensure it's on PATH in the MCP environment.
