"""pi, the gateway to the language model: located and read, never wrapped.

Everything nunatak knows about the model comes from pi's own state:
`settings.json` names the default provider and model, `models.json`
declares user-defined providers with their endpoint. Reading those files
is not duplicating the configuration - it is treating it as the single
source, the same way perf's version banner is read rather than assumed.

The reads cross the execution boundary because decisions hang on them:
whether source code is about to leave the machine depends on the
provider's endpoint, and a replayed Run must reach the same verdict the
recording did, whatever the replaying host has in its home directory.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from nunatak.collect.execution import Executor
from nunatak.config import Config

# pi keeps its state under ~/.pi/agent. Both files belong to pi: nunatak
# reads them as facts and never writes them.
SETTINGS = Path.home() / ".pi" / "agent" / "settings.json"
MODELS = Path.home() / ".pi" / "agent" / "models.json"

# `pi --version` prints a bare version number and nothing else. Anything
# different answered at that name - a shell that ignores the flag, some
# other `pi` on PATH - is not the tool, and pretending otherwise would
# surface as a cryptic failure at explanation time.
_VERSION = re.compile(r"\d+(\.\d+)+")


@dataclass(frozen=True)
class Pi:
    """One usable pi: the invoked path and the version that answered."""

    path: str
    version: str


@dataclass(frozen=True)
class Identity:
    """Who would serve an explanation: pi's default provider and model.

    `remote` is what the consent decision hangs on. It is True unless
    the provider's endpoint in pi's `models.json` provably points at
    this machine: a provider nunatak cannot prove local is treated as
    remote - over-asking for consent costs a keystroke, under-asking
    leaks source code.
    """

    provider: str | None
    model: str | None
    remote: bool


def locate(executor: Executor, config: Config) -> Pi | None:
    """The usable pi, or None.

    `tools.pi` in nunatak.toml replaces the default entirely, like the
    other tool overrides; the bare name otherwise resolves on the
    executor's PATH - npm installs land in too many prefixes for a fixed
    path to exist. A broken Node underneath fails the probe the same way
    an absent pi does, which is the honest answer: neither can serve.
    """
    path = config.tools.get("pi", "pi")
    invocation = executor.run([path, "--version"])
    if invocation.exit_code != 0 or not invocation.stdout:
        return None
    banner = invocation.stdout.strip().splitlines()
    if not banner or not _VERSION.fullmatch(banner[0].strip()):
        return None
    return Pi(path=path, version=banner[0].strip())


def identity(executor: Executor) -> Identity:
    """The provider and model pi would serve an explanation with.

    An empty or unreadable `settings.json` leaves both None: pi then
    falls back to its own built-in default, which is a hosted service -
    the Identity stays remote, and the consent path stays on.
    """
    settings = _read_json(executor, SETTINGS)
    provider = settings.get("defaultProvider")
    model = settings.get("defaultModel")
    remote = True
    if isinstance(provider, str):
        providers = _read_json(executor, MODELS).get("providers", {})
        declared = providers.get(provider) if isinstance(providers, dict) else None
        if isinstance(declared, dict) and _loopback(declared.get("baseUrl", "")):
            remote = False
    return Identity(
        provider=provider if isinstance(provider, str) else None,
        model=model if isinstance(model, str) else None,
        remote=remote,
    )


def readiness(executor: Executor, pi: Pi, provider: str) -> str | None:
    """What pi says about the provider's credentials, or None.

    `pi auth check` answers without touching the network when asked not
    to refresh; its verdict is displayed verbatim - nunatak does not
    grade credential states it does not own.
    """
    invocation = executor.run(
        [pi.path, "auth", "check", "--provider", provider, "--json", "--no-refresh"]
    )
    if not invocation.stdout:
        return None
    try:
        verdict = json.loads(invocation.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        return None
    status = verdict.get("status")
    if not isinstance(status, str):
        return None
    kind = verdict.get("authType")
    return f"credentials {status} ({kind})" if isinstance(kind, str) else f"credentials {status}"


def _loopback(base_url: str) -> bool:
    """Whether `base_url` provably points at this machine."""
    host = urlsplit(base_url).hostname
    if host is None:
        return False
    return host in ("localhost", "::1") or host.startswith("127.")


def _read_json(executor: Executor, path: Path) -> dict:
    """One of pi's JSON files as a mapping, {} when absent or unreadable.

    {} is the safe failure: no provider can be proven local from a file
    that did not parse, so consent stays on.
    """
    invocation = executor.run(["/bin/cat", str(path)])
    if invocation.exit_code != 0 or not invocation.stdout:
        return {}
    try:
        parsed = _lenient(invocation.stdout)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _lenient(text: str):
    """Parse pi's JSON5-flavored files.

    pi accepts `//` and `/* */` comments and trailing commas; the
    standard parser does not. Both liberties are stripped outside string
    literals only - a baseUrl carries `//` that a naive scrub would
    amputate - and a comma is trailing even when a comment sits between
    it and the closing bracket.
    """
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        character = text[i]
        if in_string:
            out.append(character)
            if character == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if character == '"':
                in_string = False
            i += 1
            continue
        if character == '"':
            in_string = True
            out.append(character)
            i += 1
            continue
        if text.startswith("//", i) or text.startswith("/*", i):
            i = _past_comment(text, i)
            continue
        if character == ",":
            j = i + 1
            while j < n:
                if text[j].isspace():
                    j += 1
                elif text.startswith("//", j) or text.startswith("/*", j):
                    j = _past_comment(text, j)
                else:
                    break
            if j < n and text[j] in "}]":
                i += 1
                continue
        out.append(character)
        i += 1
    return json.loads("".join(out))


def _past_comment(text: str, start: int) -> int:
    """The index right after the comment beginning at `start`."""
    if text.startswith("//", start):
        end = text.find("\n", start)
        return len(text) if end < 0 else end
    end = text.find("*/", start + 2)
    return len(text) if end < 0 else end + 2
