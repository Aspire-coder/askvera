// Print a reproducible country-name catalog using Node's bundled Unicode CLDR data.
// This supplies names only, never policy eligibility or market availability.
import { readFileSync } from "node:fs";
const root = new URL("../", import.meta.url);
const markets = JSON.parse(readFileSync(new URL("config/markets.json", root), "utf8")).markets;
const supplemental = JSON.parse(readFileSync(new URL("config/global_directory_markets.json", root), "utf8")).markets;
const languages = [...new Set(markets.flatMap(m => m.languages.filter(l => l.enabled).map(l => l.code)))].sort();
// Custom business regions (e.g. BALTICS) retain their configured names.
const codes = [...new Set([...markets, ...supplemental].map(m => m.code))].filter(code => /^[A-Z]{2}$/.test(code)).sort();
const names = Object.fromEntries(codes.map(code => [code, [...new Set(languages.map(language => {
  return new Intl.DisplayNames([language], { type: "region", fallback: "none" }).of(code);
}).filter(name => name && name !== code))].sort()]));
console.log(JSON.stringify({ source: "Node Intl.DisplayNames / Unicode CLDR", icu: process.versions.icu, languages, names }, null, 2));
