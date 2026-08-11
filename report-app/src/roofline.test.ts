/**
 * The geometry invariant of the roofline, under unit test because the
 * prototype really shipped its violation and the code read fine: the
 * memory diagonal stops at the ridge, it never crosses the compute peak.
 */

import { expect, test } from "vitest";
import { domain, ridge, segments } from "./roofline";

const PEAK = 1.0e12; // flop/s
const BANDWIDTH = 1.0e11; // byte/s -> ridge at 10 flop/byte

test("the diagonal stops exactly at the ridge, never past it", () => {
  const { diagonal, flat } = segments(PEAK, BANDWIDTH, 0.01, 1000, 1e9);
  expect(diagonal[1].x).toBe(ridge(PEAK, BANDWIDTH));
  expect(diagonal[1].y).toBe(PEAK);
  expect(diagonal[0].y).toBeLessThanOrEqual(PEAK);
  expect(flat[0].x).toBe(diagonal[1].x);
  expect(flat[0].y).toBe(PEAK);
  expect(flat[1].y).toBe(PEAK);
});

test("every point of the envelope is min(peak, bandwidth x intensity)", () => {
  const { diagonal, flat } = segments(PEAK, BANDWIDTH, 0.01, 1000, 1e9);
  for (const point of [...diagonal, ...flat]) {
    expect(point.y).toBeCloseTo(Math.min(PEAK, BANDWIDTH * point.x), 5);
  }
});

test("a plot narrower than the ridge clips the diagonal, not the peak rule", () => {
  const { diagonal } = segments(PEAK, BANDWIDTH, 0.01, 5, 1e9);
  expect(diagonal[1].x).toBe(5);
  expect(diagonal[1].y).toBeLessThan(PEAK);
});

test("the diagonal's low end is clipped at the plot floor", () => {
  const { diagonal } = segments(PEAK, BANDWIDTH, 1e-6, 1000, 1e9);
  expect(diagonal[0].y).toBeGreaterThanOrEqual(1e9);
});

test("the domain covers the ridge and every placed Hotspot in full decades", () => {
  const { x0, x1, y0, y1 } = domain(PEAK, BANDWIDTH, [
    { x: 0.42, y: 1.7e11 },
    { x: 55, y: 9.0e11 },
  ]);
  expect(x0).toBeLessThanOrEqual(0.42);
  expect(x1).toBeGreaterThanOrEqual(55);
  expect(y0).toBeLessThanOrEqual(1.7e11);
  expect(y1).toBeGreaterThanOrEqual(PEAK);
  for (const bound of [x0, x1, y0, y1]) {
    expect(Math.log10(bound) % 1).toBeCloseTo(0);
  }
});
