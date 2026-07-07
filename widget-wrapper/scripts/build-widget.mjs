import { existsSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = resolve(root, "dist");
const viteBin = resolve(root, "node_modules/vite/bin/vite.js");

function run(command, args, options = {}) {
  console.log(`\n> ${command} ${args.join(" ")}`);
  const result = spawnSync(command, args, {
    cwd: root,
    stdio: "inherit",
    shell: options.shell ?? (process.platform === "win32"),
    env: {
      ...process.env,
      ...options.env
    }
  });

  if (result.status !== 0) {
    console.error(`Command failed with exit code ${result.status}: ${command} ${args.join(" ")}`);
    if (result.error) {
      console.error(result.error);
    }
    process.exit(result.status || 1);
  }
}

if (existsSync(dist)) {
  rmSync(dist, { recursive: true, force: true });
}

run("node", [viteBin, "build"], { shell: false, env: { WIDGET_MINIFY: "true" } });
