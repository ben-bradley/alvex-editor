from __future__ import annotations

from dataclasses import dataclass
import base64
import json
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request


@dataclass
class OllamaConfig:
    host: str = "http://127.0.0.1:11434"
    model: str | None = None
    vision_model: str | None = None
    timeout: float = 120.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, *, fallback_host: str | None = None) -> "OllamaConfig":
        data = data or {}
        host = data.get("host") or data.get("base_url") or data.get("endpoint") or fallback_host or "http://127.0.0.1:11434"
        host = str(host).rstrip("/")
        if "://" not in host:
            host = "http://" + host
        return cls(
            host=host,
            model=data.get("model"),
            vision_model=data.get("vision_model") or data.get("model"),
            timeout=float(data.get("timeout") or 120.0),
        )


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, config: OllamaConfig):
        self.config = config

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self.config.host + path
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise OllamaError(f"Ollama {path} failed ({e.code}): {detail}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise OllamaError(f"Ollama {path} failed: {e}") from e

    def _get(self, path: str) -> dict[str, Any]:
        url = self.config.host + path
        try:
            with urllib.request.urlopen(url, timeout=min(self.config.timeout, 15.0)) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise OllamaError(f"Ollama {path} failed: {e}") from e

    def version(self) -> dict[str, Any]:
        return self._get("/api/version")

    def tags(self) -> dict[str, Any]:
        return self._get("/api/tags")

    def chat(self, *, model: str, messages: list[dict[str, Any]], format: Any = None, options: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if format is not None:
            payload["format"] = format
        if options:
            payload["options"] = options
        data = self._post("/api/chat", payload)
        msg = data.get("message") or {}
        content = msg.get("content")
        if content is None:
            raise OllamaError(f"Ollama chat returned no content: {json.dumps(data)[:500]}")
        return str(content)

    def chat_vision(self, *, model: str, prompt: str, images: list[Path | bytes | str], system: str | None = None, format: Any = None) -> str:
        encoded: list[str] = []
        for img in images:
            if isinstance(img, (bytes, bytearray)):
                encoded.append(base64.b64encode(img).decode("ascii"))
            elif isinstance(img, Path) or (isinstance(img, str) and Path(img).exists()):
                encoded.append(base64.b64encode(Path(img).read_bytes()).decode("ascii"))
            else:
                # assume already base64
                encoded.append(str(img))
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt, "images": encoded})
        return self.chat(model=model, messages=messages, format=format)


def extract_json_object(text: str) -> Any:
    text = text.strip()
    # strip fenced blocks
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{") or part.startswith("["):
                text = part
                break
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min([i for i in [text.find("{"), text.find("[")] if i >= 0], default=-1)
        end_obj = text.rfind("}")
        end_arr = text.rfind("]")
        end = max(end_obj, end_arr)
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise
