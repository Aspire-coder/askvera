import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const dist = resolve(process.cwd(), "dist");
const html = await readFile(resolve(dist, "index.html"), "utf8");
const asset = html.match(/assets\/index-[^\"']+\.js/);

if (!asset) throw new Error("Production build does not reference an application bundle.");

const bundle = await readFile(resolve(dist, asset[0]), "utf8");
for (const [feature, marker] of [["market selector", "Select market"], ["support routing selector", "Select support market"]]) {
  if (!bundle.includes(marker)) throw new Error(`Production build is missing the ${feature} feature.`);
}

console.log(`Validated production build: ${asset[0]}`);
