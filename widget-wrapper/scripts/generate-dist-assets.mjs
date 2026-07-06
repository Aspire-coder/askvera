import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = resolve(root, "dist");
const packageJson = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));

function getCommit() {
  return process.env.GITHUB_SHA?.slice(0, 7) || process.env.ASKVERA_BUILD_COMMIT || "unknown";
}

mkdirSync(dist, { recursive: true });

const version = {
  name: packageJson.name,
  version: packageJson.version,
  build: "widget-sdk",
  commit: getCommit(),
  date: new Date().toISOString(),
  artifacts: [
    "widget.es.js",
    "widget.js",
    "widget.min.js",
    "widget.css",
    "widget.min.css",
    "types/"
  ]
};

writeFileSync(resolve(dist, "version.json"), `${JSON.stringify(version, null, 2)}\n`);

const readme = `# ASK Vera Widget Distribution

This folder contains the built ASK Vera embeddable widget SDK.

## Browser Script

\`\`\`html
<link rel="stylesheet" href="./widget.css" />
<script src="./widget.min.js"></script>
<script>
  window.AskVera.init({
    apiUrl: "https://api.vera-api.xyz"
  });
</script>
\`\`\`

## ES Module

\`\`\`ts
import { AskVera } from "@askvera/widget";
import "@askvera/widget/styles.css";

await AskVera.init({
  apiUrl: "https://api.vera-api.xyz"
});
\`\`\`

## Included Files

- \`widget.es.js\` - ES module build.
- \`widget.js\` - browser script build.
- \`widget.min.js\` - minified browser script build.
- \`widget.css\` - widget styles.
- \`widget.min.css\` - minified widget styles.
- \`types/\` - TypeScript declarations.
- \`version.json\` - build metadata.
`;

writeFileSync(resolve(dist, "README.md"), readme);

const rootLicense = resolve(root, "LICENSE");
if (existsSync(rootLicense)) {
  copyFileSync(rootLicense, resolve(dist, "LICENSE"));
} else {
  writeFileSync(resolve(dist, "LICENSE"), "ASK Vera Widget - Proprietary. All rights reserved.\n");
}
