// Bundle the report mini-app into the Python package's asset directory.
// The output is two files, report.js and report.css, that html.py inlines
// into a single self-contained page: no request ever leaves the report.
import { build } from "esbuild";

await build({
  entryPoints: [{ in: "src/main.ts", out: "report" }],
  bundle: true,
  minify: true,
  format: "iife",
  target: ["es2020"],
  outdir: "../nunatak/report/assets",
  legalComments: "none",
});
