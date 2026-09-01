"""An OpenAI-compatible endpoint on loopback, and the pi home that points
at it: what makes the explanation layer testable live, with no API key,
no network and no model.

pi accepts any provider declared in `models.json`, and treats its models
as usable once a credential exists - so a placeholder key is enough,
which is what pi's own documentation prescribes for keyless local
servers. The base URL is loopback, which is also what makes nunatak call
the provider local and therefore ask for no agreement before sending
source.

What this stands in for is the model, and nothing else: pi itself is the
real binary, spoken to over its real protocol, and every answer nunatak
reads comes back through pi's own event stream.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

# The answer the stub always gives, and the model that makes it fail
# instead: a provider error is a path nunatak must surface rather than
# swallow, and a stub is the only way to ask for one on purpose.
ANSWER = "Line 5 is a streaming triad: three arrays in, one out, no reuse."
ERROR_MODEL = "stub-error"
PROVIDER = "stub"
MODEL = "stub-1"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        """Silence: the test's own log is the assertion."""

    def do_GET(self) -> None:
        """The catalogue pi lists models from, and a health answer."""
        if self.path.rstrip("/").endswith("/models"):
            self._json({"object": "list", "data": [{"id": MODEL, "object": "model"}]})
        else:
            self._json({"status": "ok"})

    def do_POST(self) -> None:
        """One completion: streamed, whole, or refused for ERROR_MODEL."""
        length = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.server.requests.append(body)
        if body.get("model") == ERROR_MODEL:
            self._json({"error": {"message": "the stub refused", "type": "stub_error"}}, 500)
        elif body.get("stream"):
            self._stream(body)
        else:
            self._json(self._completion(body))

    def _stream(self, body: dict) -> None:
        """The answer as server-sent events, in more than one delta."""
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        # Two deltas, so a caller that renders tokens as they arrive is
        # exercised rather than handed one block.
        head, _, tail = ANSWER.partition(": ")
        for delta in ({"role": "assistant"}, {"content": head + ": "}, {"content": tail}):
            self._event({"choices": [{"index": 0, "delta": delta, "finish_reason": None}]}, body)
        self._event(
            {
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 16, "total_tokens": 28},
            },
            body,
        )
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _event(self, payload: dict, body: dict) -> None:
        """One `data:` frame of the event stream."""
        payload = {
            "id": "stub",
            "object": "chat.completion.chunk",
            "model": body.get("model", MODEL),
            **payload,
        }
        self.wfile.write(b"data: " + json.dumps(payload).encode() + b"\n\n")
        self.wfile.flush()

    def _completion(self, body: dict) -> dict:
        """The non-streamed body, for a caller that asks for one."""
        return {
            "id": "stub",
            "object": "chat.completion",
            "model": body.get("model", MODEL),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": ANSWER},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 16, "total_tokens": 28},
        }

    def _json(self, payload: dict, status: int = 200) -> None:
        """`payload` as the whole response, with its length."""
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


@dataclass
class StubProvider:
    """A running endpoint and the pi home that declares it."""

    home: Path
    base_url: str
    requests: list[dict] = field(default_factory=list)

    @property
    def settings(self) -> Path:
        return self.home / ".pi" / "agent" / "settings.json"

    @property
    def models(self) -> Path:
        return self.home / ".pi" / "agent" / "models.json"

    def prompts(self) -> list[str]:
        """The user text of every request the endpoint received."""
        texts = []
        for body in self.requests:
            for message in body.get("messages", []):
                if message.get("role") != "user":
                    continue
                content = message["content"]
                if isinstance(content, str):
                    texts.append(content)
                else:
                    texts += [part["text"] for part in content if part.get("type") == "text"]
        return texts


def _write_home(home: Path, base_url: str) -> None:
    """The three files pi reads: where the models are, which one is the
    default, and a placeholder credential for a server that ignores it."""
    agent = home / ".pi" / "agent"
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "models.json").write_text(
        json.dumps(
            {
                "providers": {
                    PROVIDER: {
                        "name": "Stub",
                        "baseUrl": base_url,
                        "api": "openai-completions",
                        "apiKey": "stub",
                        "models": [{"id": MODEL}, {"id": ERROR_MODEL}],
                    }
                }
            },
            indent=2,
        )
        + "\n"
    )
    (agent / "settings.json").write_text(
        json.dumps(
            {"defaultProvider": PROVIDER, "defaultModel": MODEL, "quietStartup": True},
            indent=2,
        )
        + "\n"
    )
    (agent / "auth.json").write_text(
        json.dumps({PROVIDER: {"type": "api_key", "key": "stub"}}, indent=2) + "\n"
    )


def serve(home: Path) -> Iterator[StubProvider]:
    """Start the endpoint on a free loopback port, with `home` pointing at
    it. A generator, so a pytest fixture is one `yield from` away."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.requests = []
    base_url = f"http://127.0.0.1:{server.server_port}/v1"
    _write_home(home, base_url)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield StubProvider(home=home, base_url=base_url, requests=server.requests)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
