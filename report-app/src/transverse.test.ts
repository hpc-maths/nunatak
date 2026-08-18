/**
 * The transverse block: rendered from data, absent without data, capped
 * instead of flooding.
 */

import { expect, test } from "vitest";
import type { InlineViewRow, Payload } from "./data";
import { transverse } from "./transverse";

function row(name: string, share: number, sites = 1): InlineViewRow {
  return { function: name, file: "src/kernels.h", line: 12, share, sites };
}

function payload(inline_view: InlineViewRow[] | null): Payload {
  return { inline_view } as unknown as Payload;
}

test("no transverse data, no block", () => {
  expect(transverse(payload(null))).toBe("");
  expect(transverse(payload([]))).toBe("");
});

test("a frame inlined in many hotspots wears its count", () => {
  const html = transverse(payload([row("axpy_element", 0.62, 12), row("main", 0.38)]));
  expect(html).toContain("axpy_element");
  expect(html).toContain("in 12 hotspots");
  expect(html).toContain("62%");
  expect((html.match(/<tr>/g) ?? []).length).toBe(3);
  expect(html).not.toContain("in 1 hotspots");
});

test("the table is capped and the tail admitted", () => {
  const rows = Array.from({ length: 25 }, (_, i) => row(`f${i}`, (25 - i) / 100));
  const html = transverse(payload(rows));
  expect((html.match(/<tr>/g) ?? []).length).toBe(21);
  expect(html).toContain("and 5 more");
});
