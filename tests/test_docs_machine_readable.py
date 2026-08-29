"""What a machine reads has to be documented exactly, so the reference is
held against the payloads themselves.

The two contracts are built here from a bare Run. The four convenience
payloads are literal dictionaries at their `json.dumps` call site, and
their keys are read from the source rather than by running a verb, which
would need a machine.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from nunatak.cli.compare import _payload as comparison_payload
from nunatak.compare import compare
from nunatak.pivot.model import Allocation, Machine, Provenance, Run
from nunatak.report import payload

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs" / "reference" / "machine-readable.md"


def _run() -> Run:
    machine = Machine(
        system="Linux", kernel="6.8", architecture="x86_64", cpu_model="test",
        logical_cores=1, allocation=Allocation(visible_cores=1),
    )
    return Run(
        name="test", created="2026-01-01T00:00:00+00:00", command=["true"],
        exit_code=0, machine=machine, provenance=Provenance(),
    )


def _documented(heading: str) -> list[str]:
    """The keys of the table under a heading, in order."""
    text = REFERENCE.read_text()
    section = text.split(f"\n## {heading}\n", 1)[1]
    section = section.split("\n## ", 1)[0]
    keys: list[str] = []
    for line in section.splitlines():
        row = re.match(r"^\| (`[^|]+`) \| ", line)
        if row:
            keys.extend(re.findall(r"`([a-z_]+)`", row.group(1)))
    return keys


def _emitted_keys(module: str, verb: str) -> list[str]:
    """The keys of the dictionary a verb hands to `json.dumps`."""
    tree = ast.parse((ROOT / "nunatak" / "cli" / f"{module}.py").read_text())
    literals = {
        node.targets[0].id: node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Dict)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "dumps"
        ):
            continue
        argument = node.args[0]
        if isinstance(argument, ast.Name):
            argument = literals.get(argument.id)
        if isinstance(argument, ast.Dict):
            return [k.value for k in argument.keys if isinstance(k, ast.Constant)]
    raise AssertionError(f"{verb} hands no literal dictionary to json.dumps")


def test_the_report_payload_is_documented():
    built = payload.build(_run(), [])
    assert _documented("The report payload")[:1] == ["format"]
    documented = set(_documented("The report payload"))
    assert set(built) <= documented, f"undocumented: {sorted(set(built) - documented)}"
    assert documented <= set(built), f"invented: {sorted(documented - set(built))}"


def test_the_comparison_payload_is_documented():
    built = comparison_payload(compare(_run(), _run()), "before", "after")
    documented = set(_documented("`compare --json`"))
    assert set(built) <= documented, f"undocumented: {sorted(set(built) - documented)}"


def test_the_documented_schema_numbers_are_the_real_ones():
    built = comparison_payload(compare(_run(), _run()), "before", "after")
    stated = dict(re.findall(r"^\| `(nunatak-[a-z]+)` \| (\d+) \|", REFERENCE.read_text(), re.M))
    assert int(stated["nunatak-report"]) == payload.SCHEMA
    assert int(stated["nunatak-compare"]) == built["format"]["schema"]


def test_every_convenience_payload_is_documented():
    for module, heading in (
        ("run", "`run --json`"),
        ("doctor", "`doctor --json`"),
        ("report", "`report --json`"),
        ("calibrate", "`calibrate --json`"),
    ):
        emitted = _emitted_keys(module, heading)
        documented = _documented(heading)
        assert emitted == documented, f"{heading}: emits {emitted}, documents {documented}"
