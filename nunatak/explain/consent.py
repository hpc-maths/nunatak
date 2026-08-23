"""Consent: source code leaves the machine only with an explicit yes.

Two distinct switches guard two distinct risks: `--no-source` keeps
text out of the report, and this module asks - bluntly, once per
project and provider - before any source is sent to a remote model.
A provider proven local (its endpoint on this machine) asks nothing:
that is the clean exit for a site that can let nothing out.

The agreement is memorized in the global cache, which only ever holds
what is recomputable or re-askable - losing it costs one question,
never an information. It is keyed by project and by who would receive
the source: switching providers asks again, an unknown provider or a
bare model pattern is keyed as itself and treated as remote.

There is no way to consent without a terminal: a batch job that finds
no memorized agreement withholds the explanation and says how to grant
it from a login node, because a silent default in either direction
would be a decision nunatak has no right to make.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path

from nunatak.console import Console
from nunatak.explain.pi import Identity


def directory() -> Path:
    """Where agreements live: `$XDG_CACHE_HOME/nunatak/consents`."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "nunatak" / "consents"


def recipient(identity: Identity, model_flag: str | None = None) -> str:
    """Who would receive the source, as the consent key.

    The provider name when pi's configuration names one; the raw model
    flag when the user asked for a pattern nunatak cannot resolve to a
    provider - pi's fuzzy matching is pi's - and pi's built-in default
    otherwise.
    """
    if identity.provider is not None:
        return identity.provider
    if model_flag:
        return model_flag
    return "pi's built-in default provider"


def granted(project: str, who: str) -> bool:
    """Whether this project already agreed to send source to `who`."""
    record = directory() / f"{_safe(project)}.json"
    try:
        agreements = json.loads(record.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return who in agreements.get("recipients", {})


def record(project: str, who: str) -> None:
    """Memorize the agreement, next to the project's earlier ones."""
    directory().mkdir(parents=True, exist_ok=True)
    path = directory() / f"{_safe(project)}.json"
    try:
        agreements = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        agreements = {"recipients": {}}
    agreements["recipients"][who] = {
        "agreed": datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    }
    path.write_text(json.dumps(agreements, indent=2) + "\n")


def obtain(
    identity: Identity,
    project: str,
    console: Console,
    model_flag: str | None = None,
    ask=input,
) -> tuple[bool, str | None]:
    """Whether source may be sent, and the sentence to show when not.

    Local provider: yes, silently. Memorized agreement for this project
    and recipient: yes. A terminal: the question, without detour, and a
    yes is memorized. Anything else - a job log, a declined answer -
    withholds, with the exact way to grant consent later.
    """
    if not identity.remote:
        return True, None
    who = recipient(identity, model_flag)
    if granted(project, who):
        return True, None
    if not console.is_terminal:
        return False, (
            "no consent recorded for this project and no terminal "
            "to ask on: no source was sent"
        )
    what = f"{who}" + (f" (model {identity.model})" if identity.model else "")
    console.info(
        f"Explanations send source code of this project to {what}, "
        "a remote service."
    )
    try:
        answer = ask("Send source there, now and for this project? [y/N] ")
    except EOFError:
        answer = ""
    if answer.strip().lower() in ("y", "yes"):
        record(project, who)
        return True, None
    return False, "consent declined: no source was sent"


def _safe(project: str) -> str:
    """A filesystem-safe file stem for the project name."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", project) or "project"
