"""Generation: one pi invocation per Hotspot, errors surfaced verbatim.

pi is invoked like any collector - through the executor, output parsed -
in its JSON event mode: one event per line, the assistant's final text
in the closing `message_end`. Two measured facts shape the parsing.
pi exits 0 even when every attempt failed, so the exit code witnesses
nothing: the only witness of a provider error is the event stream
itself, `stopReason: "error"` with the provider's message. And pi
retries transient errors internally, so several assistant messages can
close in one run: the last one is the outcome.

Detecting provider errors is not optional: a pipeline that swallows an
authentication, quota or network failure produces a report without
advice and nobody knows why. An error is therefore distinguished from
an honestly empty answer and carried verbatim to the caller.

Calls run in parallel: the observed latency is tens of seconds per
Hotspot, which makes sequential generation unusable from a handful of
Hotspots on. Recording keeps its integrity under that parallelism - the
executors lock their bookkeeping - but a replayed entry matches
invocations in recorded order, so replayed tests keep to one Hotspot.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

from nunatak.collect.execution import Executor
from nunatak.explain.pi import Pi
from nunatak.explain.prompt import SYSTEM_PROMPT, Request
from nunatak.pivot import Hotspot

# Enough to hide the per-call latency behind the slowest call of a
# typical Run's handful of Hotspots, low enough not to trip provider
# rate limits.
PARALLEL_CALLS = 4

# The flags that reduce pi to a bare model call: no session written, no
# tools, nothing discovered from the working directory - the prompt is
# the whole context, by construction and under snapshot test.
_BARE = (
    "-p",
    "--no-session",
    "--mode",
    "json",
    "--no-tools",
    "--no-extensions",
    "--no-skills",
    "--no-context-files",
    "--no-prompt-templates",
)


@dataclass(frozen=True)
class Explanation:
    """One Hotspot's advice, with the model that actually served it."""

    hotspot: Hotspot
    advice: str
    model: str | None
    provider: str | None


@dataclass(frozen=True)
class Failure:
    """One Hotspot whose generation failed, with the verbatim error."""

    hotspot: Hotspot
    error: str


def generate(
    executor: Executor,
    pi: Pi,
    requests: list[Request],
    model: str | None = None,
    on_done: Callable[[Explanation | Failure], None] | None = None,
    on_token: Callable[[str], None] | None = None,
) -> tuple[list[Explanation], list[Failure]]:
    """Ask the model for every request, in parallel.

    Results come back in request order whatever the completion order;
    `on_done` fires as each call completes, for a terminal that shows
    progress. `on_token` receives the answer's text as the model writes
    it - the caller only passes it for a single request, since parallel
    generations would interleave into soup. `model` is passed to pi
    verbatim - nunatak never resolves model patterns itself.
    """
    def one(request: Request) -> Explanation | Failure:
        outcome = _ask(executor, pi, request.prompt, model, on_token)
        if isinstance(outcome, str):
            return Failure(hotspot=request.hotspot, error=outcome)
        text, served_model, served_provider = outcome
        return Explanation(
            hotspot=request.hotspot,
            advice=text,
            model=served_model,
            provider=served_provider,
        )

    slots: list[Explanation | Failure | None] = [None] * len(requests)
    with ThreadPoolExecutor(max_workers=PARALLEL_CALLS) as pool:
        futures = {
            pool.submit(one, request): index
            for index, request in enumerate(requests)
        }
        for future in as_completed(futures):
            outcome = future.result()
            slots[futures[future]] = outcome
            if on_done is not None:
                on_done(outcome)
    explanations = [r for r in slots if isinstance(r, Explanation)]
    failures = [r for r in slots if isinstance(r, Failure)]
    return explanations, failures


def _ask(
    executor: Executor,
    pi: Pi,
    prompt: str,
    model: str | None,
    on_token: Callable[[str], None] | None = None,
) -> tuple[str, str | None, str | None] | str:
    """One model call: (text, model, provider) on success, the error
    sentence on failure."""
    argv = [pi.path, *_BARE, "--system-prompt", SYSTEM_PROMPT]
    if model is not None:
        argv += ["--model", model]
    argv.append(prompt)
    on_line = None
    if on_token is not None:
        on_line = lambda line: _delta(line, on_token)  # noqa: E731
    invocation = executor.run(argv, on_line=on_line)
    if invocation.exit_code != 0:
        detail = (invocation.stderr or invocation.stdout or "").strip()
        return f"pi exited with {invocation.exit_code}: {detail[:500]}"
    return _parse(invocation.stdout or "")


def _delta(line: str, on_token: Callable[[str], None]) -> None:
    """Feed the answer's own text to the callback, as pi emits it.

    Only `text_delta` fragments are the answer; `thinking_delta` is the
    model's reasoning, which the advice never was and the terminal must
    not pass off as it.
    """
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return
    if event.get("type") != "message_update":
        return
    fragment = event.get("assistantMessageEvent", {})
    if fragment.get("type") == "text_delta":
        on_token(fragment.get("delta", ""))


def _parse(stdout: str) -> tuple[str, str | None, str | None] | str:
    """The assistant's final answer among pi's JSON events.

    The last assistant `message_end` is the outcome - pi retries
    internally and every attempt closes a message. Its text blocks are
    the advice; `stopReason: "error"` carries the provider's message
    verbatim. A stream with neither is itself reported: an unreadable
    answer must not pass for an empty one.
    """
    final: dict | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "message_end":
            continue
        message = event.get("message", {})
        if message.get("role") == "assistant":
            final = message
    if final is None:
        return "no assistant answer in pi's output"
    if final.get("stopReason") == "error":
        return f"provider error: {final.get('errorMessage') or 'no message'}"
    text = "\n".join(
        block.get("text", "")
        for block in final.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()
    if not text:
        return "the model answered with no text"
    return text, final.get("model"), final.get("provider")
