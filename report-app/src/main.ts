/**
 * Entry point: read the embedded payload, render the report.
 *
 * The synthesis opens the page; the zone below holds the inventory or
 * the detail of one Hotspot - the two substitute each other, they never
 * cohabit. The way back is an explicit button and the Escape key.
 */

import "./style.css";
import { readPayload } from "./data";
import { detail } from "./detail";
import { esc } from "./format";
import { inventory } from "./inventory";
import { synthesis } from "./synthesis";
import type { InventoryState, SortKey } from "./inventory";
import type { Payload } from "./data";

function duration(payload: Payload): string | null {
  const pass = payload.passes[0];
  if (!pass || !pass.start || !pass.end) return null;
  const seconds = (new Date(pass.end).getTime() - new Date(pass.start).getTime()) / 1000;
  if (!Number.isFinite(seconds) || seconds < 0) return null;
  if (seconds >= 3600) return `${Math.floor(seconds / 3600)} h ${Math.round((seconds % 3600) / 60)} min`;
  if (seconds >= 60) return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
  if (seconds < 1) return "< 1 s";
  return `${Math.round(seconds)} s`;
}

function topbar(payload: Payload): string {
  const machine = payload.machine;
  const cores =
    machine.allocation.visible_cores ?? machine.logical_cores;
  const meta = [
    payload.run.name,
    payload.run.command.join(" "),
    [machine.cpu_model, cores !== null ? `${cores} cores` : null]
      .filter((part) => part !== null)
      .join(", ") || `${machine.architecture}`,
    duration(payload),
  ]
    .filter((part) => part !== null && part !== "")
    .map((part) => esc(String(part)))
    .join(" &nbsp;·&nbsp; ");
  return `
  <div class="topbar">
    <div class="topbar-in">
      <svg viewBox="0 0 96 96" aria-label="nunatak">
        <path d="M4 86 L36 14 H62 L70 44 L78 31 L92 86 Z" fill="var(--rock)"/>
        <rect x="0" y="70" width="96" height="16" fill="var(--ice)"/>
        <circle cx="36" cy="14" r="5" fill="var(--ember)"/>
      </svg>
      <span class="brand">nunatak</span>
      <span class="vsep"></span>
      <span class="runmeta">${meta}</span>
    </div>
  </div>`;
}

function footer(payload: Payload): string {
  return `
  <div class="shell foot muted small">
    ${esc(payload.format.generated_by)} · self-contained report, no request leaves this page
  </div>`;
}

const state: InventoryState = { sort: "share", filter: null };
// The zone below the synthesis holds one content at a time: the
// inventory, or the detail of the Hotspot at this index.
let view: number | null = null;

function open(payload: Payload, index: number): void {
  view = index;
  render(payload);
  document.querySelector(".inv, .det")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function back(payload: Payload): void {
  view = null;
  render(payload);
  document.querySelector(".inv, .det")?.scrollIntoView({ block: "start" });
}

function bind(payload: Payload): void {
  for (const chip of document.querySelectorAll<HTMLButtonElement>("[data-filter]")) {
    chip.onclick = () => {
      state.filter = chip.dataset.filter || null;
      render(payload);
    };
  }
  for (const header of document.querySelectorAll<HTMLTableCellElement>("[data-sort]")) {
    header.onclick = () => {
      state.sort = header.dataset.sort as SortKey;
      render(payload);
    };
  }
  for (const opener of document.querySelectorAll<HTMLElement>("[data-row], [data-go]")) {
    opener.onclick = () => {
      open(payload, Number(opener.dataset.row ?? opener.dataset.go));
    };
  }
  for (const button of document.querySelectorAll<HTMLButtonElement>("[data-back]")) {
    button.onclick = () => back(payload);
  }
}

function zone(payload: Payload): string {
  const entry = view !== null ? payload.hotspots[view] : undefined;
  if (entry !== undefined) {
    return `<div class="det">${detail(payload, entry)}</div>`;
  }
  return inventory(payload, state);
}

function render(payload: Payload): void {
  const root = document.getElementById("nunatak-report");
  if (!root) throw new Error("nunatak-report element missing from the page");
  document.title = `nunatak - ${payload.run.name}`;
  root.innerHTML =
    `${topbar(payload)}<div class="shell">${synthesis(payload)}</div>` +
    `${zone(payload)}${footer(payload)}`;
  bind(payload);
}

const payload = readPayload();
addEventListener("keydown", (event) => {
  if (event.key === "Escape" && view !== null) back(payload);
});
render(payload);
