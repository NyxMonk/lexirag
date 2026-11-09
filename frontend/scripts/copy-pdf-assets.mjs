// Copies pdf.js character maps and standard fonts into public/ so the viewer
// renders non-Latin and non-embedded-font PDFs fully offline. Runs before dev/build.
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const root = path.dirname(fileURLToPath(new URL("../package.json", import.meta.url)));
const pdfjsDir = path.dirname(require.resolve("pdfjs-dist/package.json", { paths: [root] }));
const target = path.join(root, "public", "pdfjs");

mkdirSync(target, { recursive: true });
for (const dir of ["cmaps", "standard_fonts"]) {
  const src = path.join(pdfjsDir, dir);
  if (existsSync(src)) cpSync(src, path.join(target, dir), { recursive: true });
}
