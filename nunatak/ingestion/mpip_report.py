"""Parser for the mpiP report - the counting layer's view of MPI.

One aggregated text report per run, written by mpiP's collector rank at
`MPI_Finalize`. Three sections feed the pivot: the task assignment
(rank to node - the report brings its own Locus map), the per-task MPI
time table, and the per-task sent-bytes statistics. Everything becomes
Locus-level Measurements: `app_time` and `mpi_time` are mpiP's own
wall-clock view of each rank (distinct from the counting layer's
task-clock, which is CPU time), `mpi_sent_bytes` the volume each rank
pushed into the network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from nunatak.pivot import Degradation, Locus, Measurement, Quality

REPORT_SUFFIX = ".mpiP"

_VERSION = re.compile(r"^@ Version\s*:\s*(\S+)")
_ASSIGNMENT = re.compile(r"^@ MPI Task Assignment\s*:\s*(\d+)\s+(\S+)")
_SECTION = re.compile(r"^@---\s*(.+?)\s*-*$")
_TIME_ROW = re.compile(r"^\s*(\d+)\s+([\d.e+-]+)\s+([\d.e+-]+)\s+[\d.e+-]+\s*$")
_SENT_ROW = re.compile(
    r"^\S+\s+\d+\s+(\d+)\s+\d+\s+[\d.e+-]+\s+[\d.e+-]+\s+[\d.e+-]+\s+([\d.e+-]+)\s*$"
)


@dataclass
class MpipReport:
    """What one mpiP report says, before it becomes Measurements."""

    version: str
    nodes: dict[int, str] = field(default_factory=dict)
    app_time: dict[int, float] = field(default_factory=dict)
    mpi_time: dict[int, float] = field(default_factory=dict)
    sent_bytes: dict[int, float] = field(default_factory=dict)


def supports(version: str) -> bool:
    """Whether this parser recognizes the report format of `version`.

    The section layout parsed here is mpiP 3.x's; a different major
    declares itself instead of being parsed at random.
    """
    return version.split(".")[0] == "3"


def parse(text: str) -> MpipReport | None:
    """Parse one mpiP report; None when the text is not one."""
    if not text.startswith("@ mpiP"):
        return None
    report = MpipReport(version="")
    section = ""
    for line in text.splitlines():
        match = _VERSION.match(line)
        if match:
            report.version = match.group(1)
            continue
        match = _ASSIGNMENT.match(line)
        if match:
            report.nodes[int(match.group(1))] = match.group(2)
            continue
        match = _SECTION.match(line)
        if match:
            section = match.group(1)
            continue
        if section.startswith("MPI Time"):
            match = _TIME_ROW.match(line)
            if match:
                rank = int(match.group(1))
                report.app_time[rank] = float(match.group(2))
                report.mpi_time[rank] = float(match.group(3))
        elif section.startswith("Callsite Message Sent"):
            match = _SENT_ROW.match(line)
            if match:
                rank = int(match.group(1))
                report.sent_bytes[rank] = report.sent_bytes.get(rank, 0.0) + float(
                    match.group(2)
                )
    return report


def _measurement(counter: str, value: float, unit: str, rank: int, node: str) -> Measurement:
    """One Locus-level Measurement of the MPI counting layer."""
    return Measurement(
        hotspot=None,
        locus=Locus(node=node, rank=rank),
        counter=counter,
        value=value,
        unit=unit,
        quality=Quality.MEASURED,
    )


def ingest_mpip(
    directory: Path, expected: bool
) -> tuple[list[Measurement], list[Degradation], str | None]:
    """Turn the mpiP reports under `directory` into Measurements.

    Returns (measurements, degradations, mpiP version). `expected` says
    a library was preloaded: then a missing report is declared - the
    application may not have reached `MPI_Finalize` - while a run that
    never preloaded mpiP simply has no MPI layer, which the doctor
    already announced.
    """
    reports = sorted(Path(directory).glob(f"*{REPORT_SUFFIX}"))
    if not reports:
        if expected:
            return [], [
                Degradation(
                    name="mpi-report-missing",
                    message="mpiP was preloaded but produced no report",
                    remedy="the application may not have reached MPI_Finalize; "
                    "its own logs say more",
                )
            ], None
        return [], [], None

    measurements: list[Measurement] = []
    degradations: list[Degradation] = []
    version = None
    for path in reports:
        report = parse(path.read_text())
        if report is None or not supports(report.version):
            found = report.version if report else "unreadable"
            degradations.append(
                Degradation(
                    name="ingestion-unsupported",
                    message=f"no parser for mpiP {found}; raw report kept in the Run",
                    remedy="upgrade nunatak, or use mpiP 3.x",
                )
            )
            continue
        version = report.version
        for rank, seconds in sorted(report.app_time.items()):
            node = report.nodes.get(rank, "unknown")
            measurements.append(
                _measurement("app_time", seconds * 1e9, "ns", rank, node)
            )
        for rank, seconds in sorted(report.mpi_time.items()):
            node = report.nodes.get(rank, "unknown")
            measurements.append(
                _measurement("mpi_time", seconds * 1e9, "ns", rank, node)
            )
        for rank, total in sorted(report.sent_bytes.items()):
            node = report.nodes.get(rank, "unknown")
            measurements.append(
                _measurement("mpi_sent_bytes", total, "bytes", rank, node)
            )
    return measurements, degradations, version
