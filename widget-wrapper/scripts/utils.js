import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

export const widgetRoot = resolve(__dirname, "..");
export const distDir = join(widgetRoot, "dist");
export const widgetJsPath = join(distDir, "widget.js");
export const widgetCssPath = join(distDir, "widget.css");
export const widgetConfigPath = join(widgetRoot, "deployment", "widget.config.json");
export const releaseConfigPath = join(widgetRoot, "deployment", "release.config.json");
export const packageJsonPath = join(widgetRoot, "package.json");
export const widgetAssets = [
  { fileName: "widget.js", path: widgetJsPath, contentType: "application/javascript" },
  { fileName: "widget.css", path: widgetCssPath, contentType: "text/css" }
];

export function logStep(message) {
  console.log(`\n${message}`);
}

export function logSuccess(message) {
  console.log(`OK ${message}`);
}

export function fail(message) {
  console.error(`Deployment failed: ${message}`);
  process.exit(1);
}

export function readJson(path) {
  if (!existsSync(path)) {
    fail(`Missing required file: ${path}`);
  }
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    fail(`Could not parse JSON file ${path}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

export function loadDeploymentConfig() {
  const widgetConfig = readJson(widgetConfigPath);
  const releaseConfig = readJson(releaseConfigPath);
  const packageJson = readJson(packageJsonPath);

  const requiredWidgetFields = ["bucket", "distributionId", "region", "widgetPrefix", "latestAlias"];
  for (const field of requiredWidgetFields) {
    if (!widgetConfig[field]) {
      fail(`widget.config.json must define ${field}.`);
    }
  }

  if (!packageJson.version) {
    fail("package.json must define version.");
  }

  const versionPrefix = releaseConfig.versionPrefix || "v";
  const version = String(packageJson.version);
  const widgetPrefix = trimSlashes(String(widgetConfig.widgetPrefix));
  const latestAlias = trimSlashes(String(widgetConfig.latestAlias));
  const versionAlias = `${versionPrefix}${version}`;

  return {
    bucket: String(widgetConfig.bucket),
    distributionId: String(widgetConfig.distributionId),
    region: String(widgetConfig.region),
    widgetPrefix,
    latestAlias,
    version,
    versionAlias,
    latestCacheControl: String(releaseConfig.latestCacheControl || "public,max-age=300"),
    versionCacheControl: String(releaseConfig.versionCacheControl || "public,max-age=31536000,immutable"),
    latestS3Uri: `s3://${widgetConfig.bucket}/${widgetPrefix}/${latestAlias}/`,
    versionS3Uri: `s3://${widgetConfig.bucket}/${widgetPrefix}/${versionAlias}/`,
    latestInvalidationPath: `/${widgetPrefix}/${latestAlias}/*`
  };
}

export function runCommand(command, args, options = {}) {
  try {
    execFileSync(command, args, {
      stdio: "inherit",
      cwd: options.cwd || widgetRoot,
      shell: options.shell ?? false,
      env: { ...process.env, ...(options.env || {}) }
    });
  } catch (error) {
    const status = typeof error?.status === "number" ? ` Exit code: ${error.status}.` : "";
    fail(`${command} ${args.join(" ")} failed.${status}`);
  }
}

export function runCommandCapture(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd || widgetRoot,
    shell: options.shell ?? false,
    encoding: "utf8",
    env: { ...process.env, ...(options.env || {}) }
  });

  if (result.status !== 0 && !options.allowFailure) {
    const detail = result.stderr?.trim() || result.stdout?.trim() || `Exit code: ${result.status}`;
    fail(`${command} ${args.join(" ")} failed. ${detail}`);
  }

  return {
    ok: result.status === 0,
    stdout: result.stdout || "",
    stderr: result.stderr || "",
    status: result.status ?? 1
  };
}

export function requireCommand(command, hint) {
  try {
    execFileSync(command, ["--version"], { stdio: "ignore" });
  } catch {
    fail(`${command} is not installed or not available on PATH. ${hint}`);
  }
}

export function ensureAwsAuthenticated(region) {
  runCommand("aws", ["sts", "get-caller-identity", "--region", region]);
}

export function hasFlag(name) {
  return process.argv.slice(2).includes(name);
}

export function printDeploymentPlan(config) {
  console.log("");
  console.log("AskVera Widget Deployment Plan");
  console.log("--------------------------------");
  console.log(`Version:        ${config.version}`);
  console.log(`Bucket:         ${config.bucket}`);
  console.log(`Version path:   ${config.widgetPrefix}/${config.versionAlias}/`);
  console.log(`Latest path:    ${config.widgetPrefix}/${config.latestAlias}/`);
  console.log(`CloudFront:     ${config.distributionId}`);
  console.log(`Invalidation:   ${config.latestInvalidationPath}`);
}

export function printDeploymentSummary(config, invalidation) {
  console.log("");
  console.log("AskVera Widget Deployment Complete");
  console.log("----------------------------------");
  console.log(`Version:        ${config.version}`);
  console.log(`Bucket:         ${config.bucket}`);
  console.log(`Version path:   ${config.widgetPrefix}/${config.versionAlias}/`);
  console.log(`Latest path:    ${config.widgetPrefix}/${config.latestAlias}/`);
  console.log(`CloudFront:     ${config.distributionId}`);
  console.log(`Invalidated:    ${config.latestInvalidationPath}`);
  if (invalidation?.id) {
    console.log(`Invalidation ID: ${invalidation.id}`);
    console.log(`Status:          ${invalidation.status || "Unknown"}`);
  }
}

function trimSlashes(value) {
  return value.replace(/^\/+|\/+$/g, "");
}
