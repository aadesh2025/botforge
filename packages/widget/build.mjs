// Zero-dependency "build": the widget is already vanilla JS, so we lightly strip the
// license banner's leading whitespace and copy it to dist/ and to the web app's public/
// dir (served at /widget.js). If esbuild is installed, we minify; otherwise we plain-copy.
import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const srcJs = resolve(here, "src/widget.js");
const srcCss = resolve(here, "src/widget.css");
const distDir = resolve(here, "dist");
const webPublic = resolve(here, "../../apps/web/public");

mkdirSync(distDir, { recursive: true });
mkdirSync(webPublic, { recursive: true });

let js = readFileSync(srcJs, "utf8");
try {
  const esbuild = await import("esbuild");
  js = (await esbuild.transform(js, { minify: true, loader: "js" })).code;
  console.log("[widget] minified with esbuild");
} catch {
  console.log("[widget] esbuild not found — shipping unminified");
}

writeFileSync(resolve(distDir, "widget.js"), js);
writeFileSync(resolve(webPublic, "widget.js"), js);
copyFileSync(srcCss, resolve(distDir, "widget.css"));
copyFileSync(srcCss, resolve(webPublic, "widget.css"));
console.log("[widget] wrote dist/ and apps/web/public/{widget.js,widget.css}");
