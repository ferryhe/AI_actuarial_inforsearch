"""Real loopback AsyncOpenAI/HTTPX cancellation; no external provider access."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import openai
import pytest

from ai_actuarial import article_interpretations as articles
from tests.test_article_interpretations import Generator, Resolver, response, seed, service
from tests.test_article_interpretations import storage as storage


class _ChunkedHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def do_POST(self):
        state, lock = self.server.fixture_state, self.server.fixture_lock
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with lock:
            index = len(state["requests"]) + 1
            state["requests"].append(payload)
            state["active_server"] += 1
            state["max_server"] = max(state["max_server"], state["active_server"])
            state["events"].append(("server_start", index, time.monotonic()))
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            if index == 1:
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                # Each read succeeds before the SDK read timeout; only the total
                # article deadline can stop this six-second trickle early.
                for _ in range(3000):
                    self.wfile.write(b"1\r\n \r\n")
                    self.wfile.flush()
                    time.sleep(0.002)
                self.wfile.write(b"0\r\n\r\n")
            else:
                content = json.dumps(
                    {
                        "id": "loopback",
                        "object": "chat.completion",
                        "created": 0,
                        "model": payload["model"],
                        "choices": [
                            {
                                "index": 0,
                                "finish_reason": "stop",
                                "message": {
                                    "role": "assistant",
                                    "content": response(payload["messages"]),
                                },
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 100,
                            "completion_tokens": 100,
                            "total_tokens": 200,
                        },
                    }
                ).encode()
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            state["disconnect"] = True
        finally:
            with lock:
                state["active_server"] -= 1
                state["events"].append(("server_end", index, time.monotonic()))


@pytest.fixture
def chunked_server():
    state = {"requests": [], "events": [], "active_server": 0, "max_server": 0, "disconnect": False}
    lock = threading.Lock()

    server = ThreadingHTTPServer(("127.0.0.1", 0), _ChunkedHandler)
    server.fixture_state, server.fixture_lock = state, lock
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", state
    finally:
        server.shutdown()
        server.server_close()  # Reap every local handler, not daemon abandonment.
        thread.join(2)
        assert not thread.is_alive()
        assert state["active_server"] == 0


def test_real_chunked_transport_is_cancelled_closed_and_serial_before_next_source(
    storage, monkeypatch, chunked_server
):
    base_url, observed = chunked_server
    seed(storage, "a")
    seed(storage, "b")
    monkeypatch.setattr(articles, "MAX_CALL_SECONDS", 2.0)
    real_sdk = openai.AsyncOpenAI
    owned = {"active": 0, "max_active": 0, "events": [], "clients": []}

    class TrackedClient(real_sdk):
        def __init__(self, **kwargs):
            # Real AsyncHTTPTransport over localhost; avoid inherited proxy settings.
            super().__init__(**kwargs, http_client=httpx.AsyncClient(trust_env=False))
            self.index = len(owned["clients"]) + 1
            owned["clients"].append(self)
            owned["active"] += 1
            owned["max_active"] = max(owned["max_active"], owned["active"])
            owned["events"].append(("client_start", self.index, time.monotonic()))

        async def close(self):
            if self.is_closed():
                return
            await super().close()
            owned["active"] -= 1
            owned["events"].append(("client_closed", self.index, time.monotonic()))

    monkeypatch.setattr(articles.openai, "AsyncOpenAI", TrackedClient)
    runtime = SimpleNamespace(
        provider="deepseek",
        model="deepseek-fixture",
        api_key="local-fixture-only",
        base_url=base_url,
        stable_credential_id="loopback-fixture",
        raw_config={},
        configured=True,
    )
    adapter = articles.ChatArticleGenerator(runtime, 6000)
    started = time.monotonic()
    receipt = service(storage, generator=adapter).run(round_key="real-async-cancel")
    elapsed = time.monotonic() - started
    drafts = {d["source_key"]: d for d in articles.read_interpretations(storage.database)}
    first, second = drafts["a"]["attempts"][0], drafts["b"]["attempts"][0]
    assert [s["status"] for s in receipt["slots"]] == ["failed", "ready", "skipped"]
    assert receipt["provider_calls"] == 2 and len(first["calls"]) == len(second["calls"]) == 1
    assert first["calls"][0]["cancelled"] and first["calls"][0]["owned_client_closed"]
    assert first["calls"][0]["error_type"] == "TimeoutError"
    assert first["provider_seconds"] == pytest.approx(
        first["calls"][0]["timeout_seconds"], abs=0.002
    )
    assert first["calls"][0]["charged_provider_seconds"] >= first["calls"][0]["elapsed_seconds"]
    assert second["calls"][0]["finish_reason"] == "stop"
    assert second["calls"][0]["completion_tokens"] == 100
    assert all(c.is_closed() for c in owned["clients"])
    assert owned["active"] == 0 and owned["max_active"] == 1
    close_one = next(e[2] for e in owned["events"] if e[:2] == ("client_closed", 1))
    start_two = next(e[2] for e in owned["events"] if e[:2] == ("client_start", 2))
    assert close_one < start_two
    assert observed["disconnect"] and observed["active_server"] == 0
    assert len(observed["requests"]) == 2 and elapsed < 3.5
    assert observed["max_server"] == 1
    print(
        json.dumps(
            {
                "fixture_only": True,
                "provider_calls": 0,
                "loopback_requests": 2,
                "openai_version": importlib.metadata.version("openai"),
                "httpx_version": httpx.__version__,
                "max_active_owned_operations": owned["max_active"],
                "max_active_server_handlers": observed["max_server"],
                "active_on_return": owned["active"],
                "server_active_on_return": observed["active_server"],
                "elapsed_seconds": elapsed,
                "client_events": owned["events"],
                "server_events": observed["events"],
                "first_call": first["calls"][0],
                "second_call": second["calls"][0],
                "round_provider_calls": receipt["provider_calls"],
            },
            ensure_ascii=False,
        )
    )


def test_cooperative_async_cleanup_finishes_before_next_source(storage, monkeypatch):
    seed(storage, "a")
    seed(storage, "b")
    monkeypatch.setattr(articles, "MAX_CALL_SECONDS", 0.1)
    events = []
    active = [0, 0]

    class Cooperative(Generator):
        async def generate(self, messages, *, deadline):
            index = len(self.calls) + 1
            self.calls.append({"deadline": deadline})
            active[0] += 1
            active[1] = max(active[1], active[0])
            events.append(("start", index))
            try:
                if index == 1:
                    await asyncio.sleep(1)
                return response(messages)
            finally:
                await asyncio.sleep(0.002)
                active[0] -= 1
                events.append(("end", index))

    generator = Cooperative()
    result = service(storage, generator=generator, resolver=Resolver()).run(
        round_key="async-cleanup"
    )
    assert result["status"] == "complete" and result["provider_calls"] == 2
    assert active == [0, 1] and events == [("start", 1), ("end", 1), ("start", 2), ("end", 2)]
