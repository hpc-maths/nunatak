/**
 * The roofline - level 3 only, where the device is implicit.
 *
 * A global roofline would mix CPU and GPU Ceilings or impose a device
 * selector; contextualized on one Hotspot, the chart is correct by
 * construction. It shows the envelope Ceilings, the selected Hotspot in
 * evidence, and the other placeable Hotspots as pale points for scale.
 *
 * The geometry is kept in pure functions because the one bug the
 * prototype actually shipped - the memory diagonal crossing the compute
 * peak instead of stopping at the ridge - was invisible in the code and
 * only appeared at render time. `segments` is under unit test for it.
 */

import type { HotspotEntry, Payload } from "./data";
import { esc, flops, percent, sig } from "./format";

export interface Point {
  x: number;
  y: number;
}

/** The break point of the envelope: where the diagonal meets the peak. */
export function ridge(peak: number, bandwidth: number): number {
  return peak / bandwidth;
}

/**
 * The two strokes of the envelope `min(peak, bandwidth x intensity)` in
 * data coordinates: the memory diagonal stops exactly at the ridge - it
 * never crosses the peak - and the flat roof starts there.
 * `xMin`/`xMax` bound the plot; `yMin` clips the diagonal's low end.
 */
export function segments(
  peak: number,
  bandwidth: number,
  xMin: number,
  xMax: number,
  yMin: number
): { diagonal: [Point, Point]; flat: [Point, Point] } {
  const breakpoint = Math.min(ridge(peak, bandwidth), xMax);
  const xStart = Math.max(xMin, yMin / bandwidth);
  return {
    diagonal: [
      { x: xStart, y: bandwidth * xStart },
      { x: breakpoint, y: bandwidth * breakpoint },
    ],
    flat: [
      { x: breakpoint, y: peak },
      { x: xMax, y: peak },
    ],
  };
}

/** The plot domain: decades covering the ridge and every placed Hotspot. */
export function domain(
  peak: number,
  bandwidth: number,
  points: Point[]
): { x0: number; x1: number; y0: number; y1: number } {
  const xs = [ridge(peak, bandwidth), ...points.map((p) => p.x)];
  const ys = [peak, ...points.map((p) => p.y)];
  const x0 = Math.pow(10, Math.floor(Math.log10(Math.min(...xs))) - 1);
  const x1 = Math.pow(10, Math.ceil(Math.log10(Math.max(...xs))) + 1);
  const y0 = Math.pow(10, Math.floor(Math.log10(Math.min(...ys))) - 1);
  const y1 = Math.pow(10, Math.ceil(Math.log10(peak)));
  return { x0, x1, y0, y1 };
}

const W = 520;
const H = 300;
const M = { left: 56, right: 14, top: 16, bottom: 40 };

function placed(entry: HotspotEntry): Point | null {
  if (entry.dram_intensity.value === null || entry.achieved.value === null) return null;
  return { x: entry.dram_intensity.value, y: entry.achieved.value };
}

/** The roofline SVG for `entry`, or null when it cannot be placed. */
export function roofline(payload: Payload, entry: HotspotEntry): string | null {
  const ceilings = new Map(payload.machine.ceilings.map((c) => [c.name, c]));
  const peak = ceilings.get("flops_dp");
  const bandwidth = ceilings.get("dram_bandwidth");
  const point = placed(entry);
  if (!peak || !bandwidth || !point) return null;

  const ghosts = payload.hotspots
    .filter((other) => other !== entry)
    .map(placed)
    .filter((p): p is Point => p !== null);
  const { x0, x1, y0, y1 } = domain(peak.value, bandwidth.value, [point, ...ghosts]);
  const px = (v: number) =>
    M.left + ((Math.log10(v) - Math.log10(x0)) / (Math.log10(x1) - Math.log10(x0))) * (W - M.left - M.right);
  const py = (v: number) =>
    H - M.bottom - ((Math.log10(v) - Math.log10(y0)) / (Math.log10(y1) - Math.log10(y0))) * (H - M.top - M.bottom);

  let svg = `<svg class="rf" viewBox="0 0 ${W} ${H}" role="img" aria-label="Roofline of ${esc(entry.name)}">
    <style>.rf text{paint-order:stroke fill}.rf .halo{stroke:var(--surface);stroke-width:3.4;stroke-linejoin:round}</style>`;

  // Decade grid. Labels cross lines by necessity in a log-log plane: a
  // halo of the background color keeps them readable without moving them.
  for (let e = Math.ceil(Math.log10(x0)); e <= Math.floor(Math.log10(x1)); e++) {
    const x = px(10 ** e);
    const label = e >= 0 ? String(10 ** e) : `10⁻${-e}`;
    svg += `<line x1="${x}" y1="${M.top}" x2="${x}" y2="${H - M.bottom}" stroke="var(--line-soft)"/>
      <text x="${x}" y="${H - M.bottom + 16}" fill="var(--faint)" font-size="10" text-anchor="middle">${label}</text>`;
  }
  for (let e = Math.ceil(Math.log10(y0)); e <= Math.floor(Math.log10(y1)); e++) {
    const y = py(10 ** e);
    svg += `<line x1="${M.left}" y1="${y}" x2="${W - M.right}" y2="${y}" stroke="var(--line-soft)"/>
      <text x="${M.left - 7}" y="${y + 3.5}" fill="var(--faint)" font-size="10" text-anchor="end">1e${e}</text>`;
  }
  svg += `<text x="${M.left + (W - M.left - M.right) / 2}" y="${H - 5}" fill="var(--muted)" font-size="10.5" text-anchor="middle">DRAM arithmetic intensity (flop/byte)</text>
    <text x="12" y="${M.top + 2}" fill="var(--muted)" font-size="10.5" transform="rotate(-90 12 ${M.top + 2})" text-anchor="end">FLOP/s</text>`;

  // The envelope: diagonal to the ridge, flat roof past it.
  const { diagonal, flat } = segments(peak.value, bandwidth.value, x0, x1, y0);
  const dashIf = (estimated: boolean) => (estimated ? ' stroke-dasharray="5 4"' : "");
  svg += `<path d="M ${px(diagonal[0].x)} ${py(diagonal[0].y)} L ${px(diagonal[1].x)} ${py(diagonal[1].y)}"
      fill="none" stroke="var(--melt)" stroke-width="1.6"${dashIf(bandwidth.quality === "estimated")}/>`;
  svg += `<line x1="${px(flat[0].x)}" y1="${py(peak.value)}" x2="${px(flat[1].x)}" y2="${py(peak.value)}"
      stroke="var(--rock)" stroke-width="1.8"${dashIf(peak.quality === "estimated")}/>`;

  const peakLabel = `${flops(peak.value)} peak${peak.quality === "estimated" ? " · estimated" : ""}`;
  const bwLabel = `DRAM ${sig(bandwidth.value / 1e9)} GB/s${bandwidth.quality === "estimated" ? " · estimated" : ""}`;
  // Label the diagonal along its own on-screen direction, at its
  // geometric middle (the middle in log space).
  const mid = {
    x: Math.sqrt(diagonal[0].x * diagonal[1].x),
    y: Math.sqrt(diagonal[0].y * diagonal[1].y),
  };
  const slopeDegrees =
    (Math.atan2(py(mid.y * 10) - py(mid.y), px(mid.x * 10) - px(mid.x)) * 180) / Math.PI;
  svg += `<text class="halo" x="${px(flat[0].x) + 5}" y="${py(peak.value) - 7}" fill="var(--rock)" font-size="10">${esc(peakLabel)}</text>`;
  svg += `<text class="halo" x="${px(mid.x)}" y="${py(mid.y) - 8}" fill="var(--melt)" font-size="10"
      transform="rotate(${sig(slopeDegrees)} ${px(mid.x)} ${py(mid.y) - 8})">${esc(bwLabel)}</text>`;

  // Pale points: the other placeable Hotspots, for scale.
  for (const ghost of ghosts) {
    svg += `<circle cx="${px(ghost.x)}" cy="${py(ghost.y)}" r="4.5" fill="var(--faint)" fill-opacity=".38"/>`;
  }

  // The selected Hotspot: the same Quality encoding as everywhere else -
  // a full disc when measured, a dashed outline when estimated.
  const estimated =
    entry.dram_intensity.quality === "estimated" || entry.achieved.quality === "estimated";
  const cx = px(point.x);
  const cy = py(point.y);
  svg += estimated
    ? `<circle cx="${cx}" cy="${cy}" r="9" fill="none" stroke="var(--warn)" stroke-width="2.4" stroke-dasharray="3 2.5"/>`
    : `<circle cx="${cx}" cy="${cy}" r="9" fill="var(--ember)" stroke="var(--surface)" stroke-width="2"/>`;
  const share = entry.share.value !== null ? ` · ${percent(entry.share.value)}` : "";
  svg += `<text class="halo" x="${cx}" y="${cy + 25}" fill="var(--ink)" font-size="11" text-anchor="middle">${esc(entry.name)}${share}</text>`;
  return svg + "</svg>";
}
