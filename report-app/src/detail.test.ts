/**
 * The detail's honest absences: a Hotspot that cannot be placed says why
 * where the chart was expected, and a Run without embedded source still
 * shows where the time goes, line by line.
 */

import { expect, test } from "vitest";
import type { Derived, HotspotEntry, Payload } from "./data";
import { detail } from "./detail";

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

function entry(overrides: Partial<HotspotEntry>): HotspotEntry {
  return {
    name: "main",
    module: "/app/solver",
    source_file: null,
    resolution_level: "line",
    classification: null,
    classification_reason: null,
    relative_error: 0.05,
    share: derived(0.5),
    achieved: derived(null, "no flops_dp raw counter in this Run"),
    attainable: derived(null, "no flops_dp raw counter in this Run"),
    envelope_fraction: derived(null, "no flops_dp raw counter in this Run"),
    dram_intensity: derived(null, "no flops_dp raw counter in this Run"),
    imbalance: derived(1.0),
    source: null,
    lines: [],
    inline_frames: [],
    ...overrides,
  };
}

function payload(hotspot: HotspotEntry): Payload {
  return {
    format: { name: "nunatak-report", schema: 1, generated_by: "nunatak" },
    run: { name: "r", created: "", command: ["./solver"], exit_code: 0 },
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
    coverage: { time_base: "task-clock", samples: 100, seconds: 1, loci: 1 },
    floor_samples: 30,
    hotspots: [hotspot],
    others: null,
  };
}

test("an unplaceable Hotspot says why where the chart was expected", () => {
  const item = entry({
    classification_reason: "no flops_dp raw counter in this Run",
  });
  const html = detail(payload(item), item);
  expect(html).toContain("Off the roofline");
  expect(html).toContain("no flops_dp raw counter in this Run");
  expect(html).not.toContain("<svg");
});

test("an absent quantity is written unavailable, never a blank", () => {
  const item = entry({});
  const html = detail(payload(item), item);
  expect(html).toContain("unavailable");
});

test("without embedded text the line distribution survives", () => {
  const item = entry({
    source_file: "/build/app/reduce.cpp",
    source: {
      file: "/build/app/reduce.cpp",
      resolved_path: null,
      start_line: null,
      end_line: null,
      text: null,
      truncated: false,
      reason: "source text withheld by --no-source",
    },
    lines: [
      { line: 31, share: 0.9 },
      { line: 34, share: 0.1 },
    ],
  });
  const html = detail(payload(item), item);
  expect(html).toContain("Source not shown");
  expect(html).toContain("source text withheld by --no-source");
  expect(html).toContain("···");
  expect(html).toContain(">31<");
  expect(html).toContain("90%");
});

test("embedded source is annotated with per-line shares, hot lines marked", () => {
  const item = entry({
    source_file: "/app/kernel.c",
    source: {
      file: "/app/kernel.c",
      resolved_path: "/app/kernel.c",
      start_line: 10,
      end_line: 12,
      text: "a;\nb;\nc;",
      truncated: false,
      reason: null,
    },
    lines: [
      { line: 11, share: 0.85 },
      { line: 12, share: 0.05 },
    ],
  });
  const html = detail(payload(item), item);
  expect(html).toContain('class="ln hot"');
  expect(html).toContain(">85%<");
  expect(html).toContain(">5%<");
});
