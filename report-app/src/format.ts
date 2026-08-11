/**
 * Formatting and the visual vocabulary of uncertainty.
 *
 * Two registers, two channels, never confused: Quality is carried by
 * color and shape, the resolution level by a neutral text label. The
 * wording matches the terminal summary - both derive from the same
 * Diagnostics. The synthesis states downgrades in prose; the hatched
 * and dotted Quality marks arrive with the inventory and the roofline.
 */

import type { Derived } from "./data";

const PREFIXES: [number, string][] = [
  [1e15, "P"],
  [1e12, "T"],
  [1e9, "G"],
  [1e6, "M"],
  [1e3, "k"],
];

export function esc(text: string): string {
  return text.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
}

/** A flop/s value with its natural SI prefix, three significant digits. */
export function flops(value: number): string {
  for (const [scale, prefix] of PREFIXES) {
    if (value >= scale) {
      return `${(value / scale).toPrecision(3).replace(/\.?0+$/, "")} ${prefix}FLOP/s`;
    }
  }
  return `${value.toPrecision(3).replace(/\.?0+$/, "")} FLOP/s`;
}

/** A fraction as a percentage, one decimal below 1%. */
export function percent(value: number): string {
  if (value === 0) return "0%";
  if (value < 0.01) return `${(value * 100).toFixed(1)}%`;
  return `${Math.round(value * 100)}%`;
}

/**
 * The distinct downgrade reasons among the quantities a finding shows.
 * Derived metrics join the reasons of their inputs with `;`, and two
 * metrics often share an input: deduplication works on the individual
 * reasons, not on the joined strings.
 */
export function downgrades(...quantities: Derived[]): string[] {
  const reasons = new Set<string>();
  for (const quantity of quantities) {
    if (quantity.quality === "estimated" && quantity.reason) {
      for (const reason of quantity.reason.split("; ")) reasons.add(reason);
    }
  }
  return [...reasons];
}

/** Resolution level: a neutral text label, never a color - identity, not uncertainty. */
export function resolutionBadge(level: string): string {
  const extra = level === "unresolved" ? " res-unresolved" : "";
  return `<span class="res${extra}">${esc(level)}</span>`;
}
