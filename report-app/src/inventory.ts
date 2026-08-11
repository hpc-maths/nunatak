/**
 * Level 2: the dense inventory - find a precise Hotspot.
 *
 * Every Hotspot above the statistical floor, sortable and filterable,
 * with Quality and resolution level in their own columns: Quality is
 * color and shape, resolution a neutral text label, and the two never
 * look alike. An empty cell means the quantity is unavailable for that
 * Hotspot, not that it is zero - the table says so under its last row.
 * The below-floor aggregate closes the table as a row of its own.
 */

import type { Derived, HotspotEntry, Payload, Quality } from "./data";
import { esc, percent, qualityBadge, resolutionBadge, sig } from "./format";

export type SortKey = "share" | "achieved" | "dram_intensity" | "imbalance";

export interface InventoryState {
  sort: SortKey;
  filter: string | null; // a classification, "estimated", "no-source", or null for all
}

/** The Quality a row states: the worst among the quantities it shows,
 *  ignoring the unavailable ones - an absent cell already says itself. */
export function rowQuality(entry: HotspotEntry): Quality {
  const shown = [entry.share, entry.achieved, entry.dram_intensity, entry.imbalance];
  const present = shown.filter((quantity) => quantity.value !== null);
  if (present.length === 0) return "unavailable";
  return present.some((quantity) => quantity.quality === "estimated")
    ? "estimated"
    : "measured";
}

/** The distinct downgrade reasons behind a row's estimated Quality. */
function rowReasons(entry: HotspotEntry): string {
  const reasons = new Set<string>();
  for (const quantity of [entry.share, entry.achieved, entry.dram_intensity, entry.imbalance]) {
    if (quantity.quality === "estimated" && quantity.reason) {
      for (const reason of quantity.reason.split("; ")) reasons.add(reason);
    }
  }
  return [...reasons].join("; ");
}

export function matches(entry: HotspotEntry, filter: string | null): boolean {
  if (filter === null) return true;
  if (filter === "estimated") return rowQuality(entry) === "estimated";
  if (filter === "no-source") return entry.source?.text == null;
  return entry.classification === filter;
}

export function sorted(entries: HotspotEntry[], key: SortKey): HotspotEntry[] {
  return [...entries].sort(
    (a, b) => ((b[key] as Derived).value ?? -1) - ((a[key] as Derived).value ?? -1)
  );
}

/** The filter chips this Run deserves: only regimes that actually occur. */
export function filterChips(entries: HotspotEntry[]): [string, string][] {
  const chips: [string, string][] = [["", "all"]];
  const seen = new Set<string>();
  for (const entry of entries) {
    if (entry.classification !== null && !seen.has(entry.classification)) {
      seen.add(entry.classification);
      chips.push([entry.classification, entry.classification]);
    }
  }
  if (entries.some((entry) => rowQuality(entry) === "estimated")) {
    chips.push(["estimated", "estimated quality"]);
  }
  if (entries.some((entry) => entry.source?.text == null)) {
    chips.push(["no-source", "no source"]);
  }
  return chips;
}

function bar(entry: HotspotEntry, largest: number): string {
  const share = entry.share.value;
  if (share === null || largest <= 0) return "";
  const width = Math.round((share / largest) * 100);
  const hatched = entry.share.quality === "estimated" ? " bar-estimated" : "";
  return `<span class="bar"><i class="${hatched.trim()}" style="width:${width}%"></i></span>`;
}

function number_(quantity: Derived): string {
  if (quantity.value === null) return '<span class="muted">-</span>';
  return sig(quantity.value);
}

function gflops(quantity: Derived): string {
  if (quantity.value === null) return '<span class="muted">-</span>';
  return sig(quantity.value / 1e9);
}

function row(entry: HotspotEntry, index: number, largest: number): string {
  const quality = rowQuality(entry);
  const reasons = quality === "estimated" ? ` title="${esc(rowReasons(entry))}"` : "";
  const module = entry.module.split("/").pop() ?? entry.module;
  const shareCell =
    entry.share.value !== null ? percent(entry.share.value) : '<span class="muted">-</span>';
  const imbalance =
    entry.imbalance.value !== null
      ? `x ${sig(entry.imbalance.value, 2)}`
      : '<span class="muted">-</span>';
  return `
    <tr class="row" data-row="${index}">
      <td><span class="fn">${esc(entry.name)}</span><span class="mod">${esc(module)}</span></td>
      <td class="barcell">${bar(entry, largest)}</td>
      <td class="r num">${shareCell}</td>
      <td class="r num">${gflops(entry.achieved)}</td>
      <td class="r num">${number_(entry.dram_intensity)}</td>
      <td class="r num">${imbalance}</td>
      <td${reasons}>${qualityBadge(quality)}</td>
      <td>${resolutionBadge(entry.resolution_level)}</td>
    </tr>`;
}

function othersRow(payload: Payload): string {
  if (payload.others === null) return "";
  const count = payload.others.count === 1 ? "1 Hotspot" : `${payload.others.count} Hotspots`;
  const share =
    payload.others.share !== null ? percent(payload.others.share) : '<span class="muted">-</span>';
  return `
    <tr class="agg">
      <td><span class="fn">others (${count})</span><span class="mod">below the statistical floor of ${payload.floor_samples} samples</span></td>
      <td class="barcell"></td>
      <td class="r num">${share}</td>
      <td class="r num"><span class="muted">-</span></td>
      <td class="r num"><span class="muted">-</span></td>
      <td class="r num"><span class="muted">-</span></td>
      <td>${qualityBadge("estimated")}</td>
      <td><span class="muted small">-</span></td>
    </tr>`;
}

/** The full level-2 section, as HTML. */
export function inventory(payload: Payload, state: InventoryState): string {
  const total = payload.hotspots.length + (payload.others?.count ?? 0);
  const chips = filterChips(payload.hotspots)
    .map(
      ([key, label]) =>
        `<button class="chip" data-filter="${esc(key)}" aria-pressed="${
          (state.filter ?? "") === key
        }">${esc(label)}</button>`
    )
    .join("");
  const entries = sorted(
    payload.hotspots.filter((entry) => matches(entry, state.filter)),
    state.sort
  );
  const largest = payload.hotspots.reduce(
    (top, entry) => Math.max(top, entry.share.value ?? 0),
    0
  );
  const rows = entries
    .map((entry) => row(entry, payload.hotspots.indexOf(entry), largest))
    .join("");
  const headers: { label: string; sort?: SortKey; right?: boolean }[] = [
    { label: "Hotspot" },
    { label: "Share", sort: "share" },
    { label: "%", sort: "share", right: true },
    { label: "GFLOP/s", sort: "achieved", right: true },
    { label: "DRAM intensity", sort: "dram_intensity", right: true },
    { label: "Imbalance", sort: "imbalance", right: true },
    { label: "Quality" },
    { label: "Resolution" },
  ];
  const head = headers
    .map((header) => {
      const classes = [
        header.right ? "r" : "",
        header.sort === state.sort ? "sorted" : "",
        header.sort ? "" : "unsortable",
      ]
        .filter(Boolean)
        .join(" ");
      const sort = header.sort ? ` data-sort="${header.sort}"` : "";
      return `<th class="${classes}"${sort}>${header.label}</th>`;
    })
    .join("");
  return `
  <div class="inv">
    <div class="filters">
      <span class="eyebrow">Inventory · ${total} Hotspot${total === 1 ? "" : "s"}</span>
      ${chips}
    </div>
    <table class="tab">
      <thead><tr>${head}</tr></thead>
      <tbody>${rows}${othersRow(payload)}</tbody>
    </table>
    <div class="tabfoot small muted">
      <span>An empty cell means the quantity is unavailable for that Hotspot, not that it is zero.</span>
    </div>
  </div>`;
}
