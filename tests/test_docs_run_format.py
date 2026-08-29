"""The Run directory is a format nunatak promises to keep readable, so
its reference is held against the writer rather than reviewed by eye.

The pivot's schemas are declared once in `persistence`, which makes the
comparison exact: a column added there and not documented fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

from nunatak.pivot import persistence

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs" / "reference" / "run-directory.md"


def _schemas() -> dict[str, list[str]]:
    """{path: column names}, from the schemas the writer uses."""
    return {
        path: [field.name for field in getattr(persistence, f"_{name.upper()}")]
        for name, path in persistence._FILES.items()
    }


def _documented_columns() -> dict[str, list[str]]:
    """{path: column names}, from the tables of the reference page.

    A heading names a file and the table under it names its columns.
    """
    text = REFERENCE.read_text()
    documented: dict[str, list[str]] = {}
    pending: list[str] = []
    for line in text.splitlines():
        if line.startswith("### "):
            pending = re.findall(r"`(pivot/[a-z-]+\.parquet)`", line)
            continue
        row = re.match(r"^\| `([a-z_]+)` \| \w+ \|", line)
        if row and pending:
            documented.setdefault(pending[0], []).append(row.group(1))
    return documented


def test_every_pivot_table_is_documented():
    assert set(_documented_columns()) == set(_schemas())


def test_every_pivot_column_is_documented_in_order():
    schemas = _schemas()
    documented = _documented_columns()
    wrong = {
        path: (documented.get(path), columns)
        for path, columns in schemas.items()
        if documented.get(path) != columns
    }
    assert not wrong, f"documented columns, real columns: {wrong}"


def test_the_manifest_keys_are_documented():
    documented = set(re.findall(r"^\| `(\w+)` \| ", REFERENCE.read_text(), re.MULTILINE))
    keys = set(persistence.manifest(_bare_run()))
    assert keys <= documented, f"undocumented manifest keys: {sorted(keys - documented)}"


def test_the_documented_schema_number_is_the_real_one():
    stated = re.search(r"The schema number is `(\d+)`", REFERENCE.read_text())
    assert stated is not None, "the page does not state the schema number"
    assert int(stated.group(1)) == persistence.SCHEMA


def _bare_run():
    from nunatak.pivot.model import Allocation, Machine, Provenance, Run

    machine = Machine(
        system="Linux", kernel="6.8", architecture="x86_64", cpu_model="test",
        logical_cores=1, allocation=Allocation(visible_cores=1),
    )
    return Run(
        name="test", created="2026-01-01T00:00:00+00:00", command=["true"],
        exit_code=0, machine=machine, provenance=Provenance(),
    )
