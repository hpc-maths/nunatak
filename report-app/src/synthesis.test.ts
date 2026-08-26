/**
 * The ranks block: the run-level balance stated in the synthesis, the
 * table capped instead of flooding, and the unsampled ranks admitted in
 * "what this report does not say" - never extrapolated, always named.
 */

import { expect, test } from "vitest";
import type { Derived, Payload, RankRow } from "./data";
import { synthesis } from "./synthesis";

function derived(value: number | null, reason: string | null = null): Derived {
  return {
    value,
    unit: "u",
    quality: value === null ? "unavailable" : reason ? "estimated" : "measured",
    lineage: [],
    formula: null,
    reason,
  };
}

function row(rank: number, seconds: number, sampled: boolean): RankRow {
  return {
    rank,
    node: `n${rank % 2}`,
    sampled,
    time: derived(seconds * 1e9),
    mpi_time: derived(sampled ? null : seconds * 0.25e9, sampled ? "mpiP was not preloaded" : null),
  };
}

function payload(ranks: Payload["ranks"]): Payload {
  return {
    format: { name: "nunatak-report", schema: 2, generated_by: "nunatak" },
    run: { name: "r", created: "", command: ["mpirun", "-n", "4", "./solver"], exit_code: 0 },
    machine: {
      system: "Linux",
      kernel: "6.14",
      architecture: "x86_64",
      cpu_model: null,
      logical_cores: 1,
      allocation: {
        visible_cores: null,
        affinity_mask: null,
        cpu_quota: null,
        memory_limit_bytes: null,
      },
      ceilings: [],
    },
    provenance: {
      commit: null,
      dirty_tree: null,
      dependencies: {},
      effective_configuration: {},
    },
    passes: [],
    degradations: [],
    coverage: { time_base: "task-clock", samples: 100, seconds: 1, loci: 4 },
    floor_samples: 30,
    hotspots: [],
    others: null,
    ranks,
    inline_view: null,
    explanations: null,
  };
}

test("a run without topology renders no ranks block", () => {
  const html = synthesis(payload(null));
  expect(html).not.toContain("Ranks");
});

test("the ranks block states its numbers and each rank its layer", () => {
  const html = synthesis(
    payload({
      imbalance: derived(1.42),
      mpi_fraction: derived(0.23),
      unsampled: [1],
      rows: [row(0, 2.0, true), row(1, 1.0, false)],
    })
  );
  expect(html).toContain("2 ranks (1 sampled)");
  expect(html).toContain("<strong>1.42x</strong> the mean");
  expect(html).toContain("<strong>23%</strong> of the time");
  expect(html).toContain("sampled");
  expect(html).toContain("counted");
  // The unsampled rank is an admission, by number.
  expect(html).toContain("1 rank was not sampled</strong> (1)");
});

test("an unavailable mpi share says unavailable, never zero", () => {
  const html = synthesis(
    payload({
      imbalance: derived(1.0),
      mpi_fraction: derived(null, "mpiP was not preloaded"),
      unsampled: [],
      rows: [row(0, 1.0, true), row(1, 1.0, true)],
    })
  );
  expect(html).toContain("unavailable");
  expect(html).not.toContain("0%</td>");
});

test("the table is capped and says what it left out", () => {
  const rows = Array.from({ length: 40 }, (_, index) => row(index, 40 - index, false));
  const html = synthesis(
    payload({
      imbalance: derived(1.9),
      mpi_fraction: derived(null, "mpiP was not preloaded"),
      unsampled: [],
      rows,
    })
  );
  expect(html).toContain("... and 8 more ranks, ordered by time.");
  // One header row plus the 32 kept: the busiest, rank 0 first.
  expect((html.match(/<tr>/g) ?? []).length).toBe(33);
  expect(html.indexOf('<td class="r">0</td>')).toBeGreaterThan(-1);
});
