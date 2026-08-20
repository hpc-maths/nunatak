"""Report payload: everything the report shows, as plain JSON data.

The payload is the contract between the Python core and the report's
TypeScript mini-app: the app renders it, it never computes it. Like the
Diagnostic it embeds, the payload is recomputed on demand and never
persisted - the Run directory stays measured data only.

It carries data, not prose: values keep their unit, their Quality and
their downgrade reason, absent quantities stay null next to the reason,
and the app owns the wording - in the same vocabulary as the terminal
summary, which derives from the same Diagnostics.
"""

from __future__ import annotations

import json
import math

from nunatak import analysis
from nunatak.analysis import Derived, Diagnostic
from nunatak.pivot import AddressDetail, Hotspot, Run, hotspot_level, manifest

# Version of the payload contract, bumped on any breaking change so a
# mini-app never renders a shape it does not understand. Schema 2 added
# the `ranks` section - the run-level balance of an MPI run; schema 3
# the `inline_view` section - time by inline frame, all Hotspots
# combined; schema 4 the `callers` and `inclusive` fields of each
# Hotspot, consumed from the recorded call paths.
SCHEMA = 4


def _derived(quantity: Derived) -> dict:
    """The plain-JSON form of a derived metric, lineage included."""
    return {
        "value": quantity.value,
        "unit": quantity.unit,
        "quality": quantity.quality.value,
        "lineage": list(quantity.lineage),
        "formula": quantity.formula,
        "reason": quantity.reason,
    }


def _coverage(run: Run, time_base: str | None) -> dict:
    """What the report's numbers stand on: samples, seconds, Loci.

    `seconds` is cumulative time over Loci - Loci run concurrently, so it
    is not wall time - and stays null when the time base is not a clock
    in nanoseconds.
    """
    sampled = analysis.sampled_view(run)
    clocked = [m for m in sampled if m.counter == time_base]
    seconds = None
    if clocked and all(m.unit == "ns" for m in clocked):
        seconds = sum(m.value for m in clocked if m.value is not None) / 1e9
    return {
        "time_base": time_base,
        "samples": sum(m.sample_count or 0 for m in clocked),
        "seconds": seconds,
        "loci": len({m.locus for m in sampled}),
    }


def _details_of(run: Run, hotspot: Hotspot, time_base: str | None) -> list[AddressDetail]:
    """The address details of one Hotspot, on a single counter.

    The time base is the counter of record for a distribution of time;
    when the details never sampled it, the first counter they did sample
    keeps the view alive rather than empty.
    """
    details = [d for d in run.address_details if d.hotspot == hotspot and d.frames]
    counters = [d.counter for d in details]
    counter = time_base if time_base in counters else next(iter(counters), None)
    return [d for d in details if d.counter == counter]


def _lines(details: list[AddressDetail]) -> list[dict]:
    """The distribution of samples over the physical function's lines.

    This is what survives `--no-source`: where the time goes, line by
    line, without a line of code. Addresses whose line the debug
    information does not give are left out - absent is not line zero.
    """
    per_line: dict[int, float] = {}
    total = 0.0
    for detail in details:
        total += detail.value
        line = detail.frames[-1].line
        if line is not None:
            per_line[line] = per_line.get(line, 0.0) + detail.value
    if total <= 0:
        return []
    return [
        {"line": line, "share": value / total}
        for line, value in sorted(per_line.items())
    ]


def _inline_frames(details: list[AddressDetail]) -> list[dict]:
    """The ventilation of a Hotspot by innermost inline frame.

    Every sampled address lands in exactly one innermost frame - the
    physical function itself where nothing was inlined - so the shares
    sum to one and the "rest" needs no special row.
    """
    per_frame: dict[tuple, float] = {}
    total = 0.0
    for detail in details:
        total += detail.value
        innermost = detail.frames[0]
        key = (innermost.function, innermost.file, innermost.declaration_line)
        per_frame[key] = per_frame.get(key, 0.0) + detail.value
    if total <= 0:
        return []
    return [
        {"function": function, "file": file, "line": line, "share": value / total}
        for (function, file, line), value in sorted(
            per_frame.items(), key=lambda item: -item[1]
        )
    ]


def _inline_view(run: Run, time_base: str | None) -> list[dict] | None:
    """Time by innermost inline frame, all Hotspots combined.

    This is the transverse view: it catches the header routine inlined
    into twelve Hotspots - invisible in each of them, dominant across
    them - and it is the only view stable across a recompilation, since
    a frame is keyed by `(function, file)` and never by the compiler's
    inlining choices. Each sampled address lands in exactly one
    innermost frame, so the shares sum to one over the sampled total.

    None when no chain goes deeper than the physical function itself -
    the view would restate the Hotspot list - or without a time base:
    a transverse sum across Hotspots needs one counter for its rows to
    be comparable at all.
    """
    if time_base is None:
        return None
    details = [
        d for d in run.address_details if d.counter == time_base and d.frames
    ]
    if not any(len(d.frames) >= 2 for d in details):
        return None
    total = sum(d.value for d in details)
    if total <= 0:
        return None
    rows: dict[tuple, dict] = {}
    for detail in details:
        innermost = detail.frames[0]
        entry = rows.setdefault(
            (innermost.function, innermost.file),
            {
                "function": innermost.function,
                "file": innermost.file,
                "line": innermost.declaration_line,
                "value": 0.0,
                "hotspots": set(),
            },
        )
        entry["value"] += detail.value
        entry["hotspots"].add(detail.hotspot)
    return [
        {
            "function": entry["function"],
            "file": entry["file"],
            "line": entry["line"],
            "share": entry["value"] / total,
            "sites": len(entry["hotspots"]),
        }
        for entry in sorted(rows.values(), key=lambda e: -e["value"])
    ]


def _hotspot_stacks(run: Run, hotspot: Hotspot, time_base: str | None) -> list:
    """The recorded call paths whose executing leaf is this Hotspot,
    matched by logical identity - the same join the display uses."""
    if time_base is None or hotspot.logical_identity.name is None:
        return []
    return [
        s
        for s in run.stacks
        if s.counter == time_base
        and s.frames
        and s.frames[0].module == hotspot.logical_identity.module
        and s.frames[0].function == hotspot.logical_identity.name
    ]


def _callers(run: Run, hotspot: Hotspot, time_base: str | None) -> list[dict]:
    """The ventilation of a Hotspot's stacked time by immediate caller.

    This is what attaches a library leaf to user code: a hot `dgemm`
    inside OpenBLAS names the solver functions that called it, with
    their shares. Shares are over the paths that recorded a caller; an
    unnamed caller keeps its honest `module+0x...` display.
    """
    stacked = [s for s in _hotspot_stacks(run, hotspot, time_base) if len(s.frames) >= 2]
    total = sum(s.value for s in stacked)
    if total <= 0:
        return []
    per_caller: dict[str, float] = {}
    for stack in stacked:
        caller = stack.frames[1].display_name
        per_caller[caller] = per_caller.get(caller, 0.0) + stack.value
    return [
        {"name": name, "share": value / total}
        for name, value in sorted(per_caller.items(), key=lambda item: -item[1])
    ]


def _inclusive(run: Run, hotspot: Hotspot, time_base: str | None) -> float | None:
    """The share of the sampled time where this Hotspot's function
    appears anywhere in the recorded path - executing, or somewhere up
    the callers. A recursive function counts once per path. None when
    the Run recorded no paths: unknown is not zero.
    """
    if time_base is None or hotspot.logical_identity.name is None:
        return None
    timed = [s for s in run.stacks if s.counter == time_base and s.frames]
    total = sum(s.value for s in timed)
    if total <= 0:
        return None
    module = hotspot.logical_identity.module
    name = hotspot.logical_identity.name
    covered = sum(
        s.value
        for s in timed
        if any(f.module == module and f.function == name for f in s.frames)
    )
    return covered / total


def _source(run: Run, hotspot: Hotspot) -> dict | None:
    """The embedded source extract of one Hotspot, reason included.

    None when the Run carries no extract for it - a Hotspot without
    line-level attribution, or a pre-extraction Run.
    """
    for extract in run.source_extracts:
        if extract.hotspot == hotspot:
            return {
                "file": extract.file,
                "resolved_path": extract.resolved_path,
                "start_line": extract.start_line,
                "end_line": extract.end_line,
                "text": extract.text,
                "truncated": extract.truncated,
                "reason": extract.reason,
            }
    return None


def _relative_error(run: Run, hotspot: Hotspot, time_base: str | None) -> float | None:
    """Sampling error on the Hotspot's share, decreasing in 1/sqrt(n)."""
    samples = sum(
        m.sample_count or 0
        for m in analysis.sampled_view(run)
        if m.hotspot == hotspot and m.counter == time_base
    )
    return 1.0 / math.sqrt(samples) if samples > 0 else None


def _hotspot(run: Run, diagnostic: Diagnostic, time_base: str | None) -> dict:
    """One Hotspot as the report sees it: identity, Diagnostic, detail."""
    hotspot = diagnostic.hotspot
    details = _details_of(run, hotspot, time_base)
    return {
        "name": hotspot.display_name,
        "module": hotspot.logical_identity.module,
        "source_file": hotspot.logical_identity.source_file,
        "resolution_level": hotspot.resolution_level.value,
        "classification": diagnostic.classification,
        "classification_reason": diagnostic.classification_reason,
        "relative_error": _relative_error(run, hotspot, time_base),
        "share": _derived(diagnostic.share),
        "achieved": _derived(diagnostic.achieved),
        "attainable": _derived(diagnostic.attainable),
        "envelope_fraction": _derived(diagnostic.envelope_fraction),
        "dram_intensity": _derived(diagnostic.dram_intensity),
        "imbalance": _derived(diagnostic.imbalance),
        "source": _source(run, hotspot),
        "lines": _lines(details),
        "inline_frames": _inline_frames(details),
        "callers": _callers(run, hotspot, time_base),
        "inclusive": _inclusive(run, hotspot, time_base),
    }


def _others(run: Run, diagnostics: list[Diagnostic], time_base: str | None) -> dict | None:
    """The below-floor aggregate: Hotspots the Diagnostic skipped.

    Their Measurements are in the pivot but not in `diagnostics`, so the
    app cannot derive this admission itself. `share` stays null without a
    time base - unknown is not zero.
    """
    diagnosed = {diagnostic.hotspot for diagnostic in diagnostics}
    skipped = {m.hotspot for m in analysis.sampled_view(run)} - diagnosed
    if not skipped:
        return None
    share = None
    if time_base is not None:
        share = max(0.0, 1.0 - sum(d.share.value or 0.0 for d in diagnostics))
    return {"count": len(skipped), "share": share}


def _ranks(run: Run) -> dict | None:
    """The run-level balance, null for a Run without rank topology.

    Straight from `analysis.balance`: rows carry each rank's time with
    its source in the formula, the imbalance factor and the MPI
    fraction arrive as derived metrics with their lineage, and
    `unsampled` names the ranks whose Hotspot-level Measurements are
    unavailable by design.
    """
    verdict = analysis.balance(run)
    if verdict is None:
        return None
    return {
        "imbalance": _derived(verdict.imbalance),
        "mpi_fraction": _derived(verdict.mpi_fraction),
        "unsampled": list(verdict.unsampled),
        "rows": [
            {
                "rank": entry.rank,
                "node": entry.node,
                "sampled": entry.sampled,
                "time": _derived(entry.time),
                "mpi_time": _derived(entry.mpi_time),
            }
            for entry in verdict.ranks
        ],
    }


def build(
    run: Run,
    diagnostics: list[Diagnostic],
    floor_samples: int = analysis.STATISTICAL_FLOOR_SAMPLES,
) -> dict:
    """The complete report payload for one Run.

    `diagnostics` is the output of `analysis.diagnose(run)`, already
    ordered by decreasing share; `floor_samples` must be the floor that
    produced it, so the report names the threshold actually applied.
    Returns a JSON-serializable dict; its trunk is the Run manifest, so
    the report and the Run directory never drift apart.
    """
    trunk = manifest(run)
    time_base = analysis.time_base(run)
    return {
        "format": {
            "name": "nunatak-report",
            "schema": SCHEMA,
            "generated_by": trunk["format"]["generated_by"],
        },
        "run": trunk["run"],
        "machine": trunk["machine"],
        "provenance": trunk["provenance"],
        "passes": trunk["passes"],
        "degradations": trunk["degradations"],
        "coverage": _coverage(run, time_base),
        "floor_samples": floor_samples,
        "hotspots": [_hotspot(run, d, time_base) for d in diagnostics],
        "others": _others(run, diagnostics, time_base),
        "ranks": _ranks(run),
        "inline_view": _inline_view(run, time_base),
    }


WITHHELD = "source text withheld by --no-source"


def without_source(payload: dict) -> dict:
    """The `--no-source` variant of a payload: the code text is withheld,
    the line numbers and the sample distribution stay.

    A page-side toggle would be a trap: the text would remain embedded in
    the file it claims to hide. The variant is produced here, before the
    page exists, so what leaves the machine never contained a line of
    code. Returns a new payload; the input is not modified.
    """
    stripped = json.loads(json.dumps(payload))
    for entry in stripped["hotspots"]:
        if entry["source"] is not None:
            entry["source"]["text"] = None
            entry["source"]["truncated"] = False
            entry["source"]["reason"] = WITHHELD
    return stripped
