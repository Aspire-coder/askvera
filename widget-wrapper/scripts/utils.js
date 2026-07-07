import { execFileSync } from "node:child_process";
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

export function logStep(message) {
  console.log(`\n${message}`);
}

export function logSuccess(message) {
  console.log(`✓ ${message}`);
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
      env: { ...process.env, ...(options.env || {}) }
    });
  } catch (error) {
    const status = typeof error?.status === "number" ? ` Exit code: ${error.status}.` : "";
    fail(`${command} ${args.join(" ")} failed.${status}`);
  }
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

function trimSlashes(value) {
  return value.replace(/^\/+|\/+$/g, "");
}
