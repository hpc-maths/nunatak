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
    callers: [],
    inclusive: null,
    loop: null,
    advice: null,
    ...overrides,
  };
}

function payload(hotspot: HotspotEntry): Payload {
  return {
    format: { name: "nunatak-report", schema: 2, generated_by: "nunatak" },
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
    ranks: null,
    inline_view: null,
    explanations: null,
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

test("a library leaf names its callers with their shares", () => {
  const item = entry({
    name: "dgemm_kernel",
    module: "/usr/lib/libopenblas.so",
    callers: [
      { name: "assemble_matrix", share: 0.7 },
      { name: "solve_pressure", share: 0.3 },
    ],
  });
  const html = detail(payload(item), item);
  expect(html).toContain("Called from");
  expect(html).toContain("assemble_matrix");
  expect(html).toContain("70%");
});

test("without recorded paths there is no callers block and inclusive says so", () => {
  const item = entry({});
  const html = detail(payload(item), item);
  expect(html).not.toContain("Called from");
  expect(html).toContain("no recorded paths");
});

test("the inclusive share joins the metrics when paths were recorded", () => {
  const item = entry({ inclusive: 0.85, callers: [{ name: "main", share: 1 }] });
  const html = detail(payload(item), item);
  expect(html).toContain("Inclusive");
  expect(html).toContain("85%");
});

test("the hot loop states its facts and its bounds", () => {
  const item = entry({
    loop: {
      start_offset: 0x1420,
      end_offset: 0x1437,
      instructions: 5,
      flops_per_iteration: 8,
      vector_fp: 1,
      scalar_fp: 0,
      vector_ratio: 1,
      vector_width_bits: 256,
      loaded_bytes: 64,
      stored_bytes: 32,
      gathers: 0,
      l1_intensity: derived(8 / 96, "static analysis"),
      cycle_bounds: {
        ports: 1.3,
        steady_state: 1.41,
        quality: "estimated",
        reason: "scheduling model znver2",
      },
      bounds_reason: null,
    },
  });
  const html = detail(payload(item), item);
  expect(html).toContain("Hot loop, from the machine code");
  expect(html).toContain("100% at 256 bits");
  expect(html).toContain("64 loaded, 32 stored");
  expect(html).toContain("znver2");
  expect(html).not.toContain("Indirect accesses");
});

test("a composite loop fact stays whole in its own column", () => {
  // The frame lists align a percentage in a narrow column; a fact whose
  // value is a phrase must not be squeezed into it.
  const item = entry({
    loop: {
      start_offset: 0x10,
      end_offset: 0x20,
      instructions: 11,
      flops_per_iteration: 0,
      vector_fp: 0,
      scalar_fp: 0,
      vector_ratio: null,
      vector_width_bits: null,
      loaded_bytes: 8,
      stored_bytes: 0,
      gathers: 0,
      l1_intensity: derived(0, "static analysis"),
      cycle_bounds: null,
      bounds_reason: "unknown microarchitecture",
    },
  });
  const html = detail(payload(item), item);
  expect(html).toContain(
    '<span class="num fact-value">8 loaded, 0 stored</span>'
  );
  expect(html).not.toContain('<span class="num pc-right">8 loaded');
});

test("absent bounds say why and a scalar loop wears its zero", () => {
  const item = entry({
    loop: {
      start_offset: 0x1380,
      end_offset: 0x139a,
      instructions: 7,
      flops_per_iteration: 2,
      vector_fp: 0,
      scalar_fp: 2,
      vector_ratio: 0,
      vector_width_bits: null,
      loaded_bytes: 16,
      stored_bytes: 8,
      gathers: 0,
      l1_intensity: null,
      cycle_bounds: null,
      bounds_reason: "LLVM 17 does not know znver4; install LLVM 19 or newer",
    },
  });
  const html = detail(payload(item), item);
  expect(html).toContain("0%");
  expect(html).toContain("No cycle bounds: LLVM 17 does not know znver4");
});

test("no loop analysis, no block", () => {
  const item = entry({});
  expect(detail(payload(item), item)).not.toContain("Hot loop");
});

test("advice arrives labeled, with the model that wrote it", () => {
  const item = entry({
    advice: {
      text: "Fuse the loops; expect roughly 2x.",
      model: "some-model",
      provider: "somewhere",
      withheld: null,
    },
  });
  const html = detail(payload(item), item);
  expect(html).toContain("Advice - some-model via somewhere");
  expect(html).toContain("Fuse the loops");
  expect(html).toContain("never a measurement");
});

test("withheld advice shows its reason where the advice was expected", () => {
  const item = entry({
    advice: {
      text: null,
      model: null,
      provider: null,
      withheld: "no source available for this Hotspot in the Run",
    },
  });
  const html = detail(payload(item), item);
  expect(html).toContain("No advice: no source available");
  expect(html).not.toContain("advice-text");
});

test("advice never generated nudges toward the verb", () => {
  const item = entry({});
  const html = detail(payload(item), item);
  expect(html).toContain("nunatak explain");
});
