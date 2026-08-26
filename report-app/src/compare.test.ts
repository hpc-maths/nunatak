/**
 * The comparison view: verdicts visible at every level, non-comparable
 * declared above the diff, direction colored only when significant.
 */

import { expect, test } from "vitest";
import type { CompareDelta, ComparePayload, CompareSide } from "./compare-data";
import { compareDetail, compareInventory, compareSynthesis } from "./compare";

function sideOf(value: number, samples = 10000): CompareSide {
  return { value, samples, error: value / Math.sqrt(samples) };
}

function delta(
  before: CompareSide | null,
  after: CompareSide | null,
  overrides: Partial<CompareDelta> = {}
): CompareDelta {
  const change = before !== null && after !== null ? after.value - before.value : null;
  const combined =
    before !== null && after !== null ? Math.hypot(before.error, after.error) : null;
  return {
    function: "axpy",
    file: "/src/app.c",
    before,
    after,
    change,
    change_fraction:
      change !== null && before!.value > 0 ? change / before!.value : null,
    combined_error: combined,
    significant: change !== null && combined !== null && Math.abs(change) > combined,
    ...overrides,
  };
}

function payload(deltas: CompareDelta[], overrides: Partial<ComparePayload> = {}): ComparePayload {
  return {
    format: { name: "nunatak-compare", schema: 1, generated_by: "nunatak" },
    before: { run: "/runs/a", name: "before" },
    after: { run: "/runs/b", name: "after" },
    unit: "ns",
    findings: [],
    total: delta(sideOf(2e9), sideOf(1e9)),
    deltas,
    ...overrides,
  };
}

test("the synthesis totals with a verdict and counts the movements", () => {
  const html = compareSynthesis(
    payload([delta(sideOf(2e9), sideOf(1e9)), delta(sideOf(1e9), sideOf(1.01e9))])
  );
  expect(html).toContain("2 s");
  expect(html).toContain("a significant difference");
  expect(html).toContain("1 improved");
  expect(html).toContain("1 unchanged within their error");
});

test("findings are declared above the diff, never masked", () => {
  const html = compareSynthesis(
    payload([], {
      findings: [{ name: "different-machines", message: "measured on different Machines" }],
    })
  );
  expect(html).toContain("Declared not directly comparable");
  expect(html).toContain("measured on different Machines");
});

test("direction is color only when significant", () => {
  const significant = delta(sideOf(2e9), sideOf(1e9));
  const within = delta(sideOf(2e9, 100), sideOf(1.94e9, 100));
  const html = compareInventory(payload([significant, within]));
  expect(html).toContain("cmp-down");
  expect(html).toContain("not a difference");
  expect(html).not.toContain("cmp-up");
});

test("one-sided entities say appeared or vanished", () => {
  const html = compareInventory(payload([delta(null, sideOf(1e9)), delta(sideOf(1e9), null)]));
  expect(html).toContain("appeared at 1 s");
  expect(html).toContain("vanished (was 1 s)");
});

test("the detail spells out the arithmetic of the verdict", () => {
  const within = delta(sideOf(2e9, 100), sideOf(1.94e9, 100));
  const html = compareDetail(payload([within]), within);
  expect(html).toContain("smaller than the combined sampling error");
  expect(html).toContain("not a difference");
  expect(html).toContain("100 samples");
});

test("a vanished entity is attributed to inlining, not to magic", () => {
  const gone = delta(sideOf(1e9), null);
  const html = compareDetail(payload([gone]), gone);
  expect(html).toContain("vanished, which inlining alone can cause");
});
