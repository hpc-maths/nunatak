// esbuild bundles the imported stylesheet into report.css; TypeScript
// only needs to know the import is legal.
declare module "*.css";
