/**
 * The rendered page from the frozen milestone pivot, held as snapshots:
 * any change to what the user sees becomes a diff read in review - the
 * same discipline the payload already obeys on the Python side. The
 * interactive walkthrough covers what the test strategy names: the
 * substitution of views and the provenance drawer.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeAll, expect, test } from "vitest";

// vitest runs from report-app/; the frozen pivot payload lives in the
// Python test suite and is shared by both sides on purpose.
const PAYLOAD = resolve(
  process.cwd(),
  "..",
  "tests",
  "snapshots",
  "report-payload-workload-c-roofline.json"
);

function click(selector: string): void {
  const element = document.querySelector<HTMLElement>(selector);
  if (!element) throw new Error(`no element matches ${selector}`);
  element.click();
}

beforeAll(async () => {
  const island = document.createElement("script");
  island.type = "application/json";
  island.id = "nunatak-payload";
  island.textContent = readFileSync(PAYLOAD, "utf-8");
  document.body.append(island);
  const root = document.createElement("div");
  root.id = "nunatak-report";
  document.body.append(root);
  await import("./main");
});

test("the page renders the milestone Run", () => {
  expect(document.title).toContain("nunatak");
  expect(document.getElementById("nunatak-report")!.innerHTML).toMatchSnapshot();
});

test("opening a finding substitutes the inventory with the detail", () => {
  expect(document.querySelector(".inv")).not.toBeNull();
  click('[data-go="0"]');
  expect(document.querySelector(".inv")).toBeNull();
  const zone = document.querySelector(".det");
  expect(zone).not.toBeNull();
  expect(zone!.innerHTML).toMatchSnapshot();
});

test("Escape substitutes the inventory back", () => {
  dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  expect(document.querySelector(".det")).toBeNull();
  expect(document.querySelector(".inv")).not.toBeNull();
});

test("the provenance drawer unfolds from the header and folds back", () => {
  expect(document.querySelector(".provpanel")).toBeNull();
  click("[data-prov]");
  const panel = document.querySelector(".provpanel");
  expect(panel).not.toBeNull();
  expect(panel!.innerHTML).toMatchSnapshot();
  click("[data-prov]");
  expect(document.querySelector(".provpanel")).toBeNull();
});
