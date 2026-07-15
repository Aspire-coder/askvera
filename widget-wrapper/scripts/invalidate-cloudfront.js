import { hasFlag, loadDeploymentConfig, logStep, logSuccess, printDeploymentPlan, requireCommand, runCommandCapture } from "./utils.js";

const config = loadDeploymentConfig();
const dryRun = hasFlag("--dry-run");

if (dryRun) {
  printDeploymentPlan(config);
  logSuccess("Dry run complete. No CloudFront invalidation was created.");
  process.exit(0);
}

logStep(`Invalidating CloudFront path ${config.latestInvalidationPath}...`);
requireCommand("aws", "Install the AWS CLI, then authenticate with an AWS profile or environment credentials.");
const result = runCommandCapture("aws", [
  "cloudfront",
  "create-invalidation",
  "--distribution-id",
  config.distributionId,
  "--paths",
  config.latestInvalidationPath,
  "--region",
  config.region,
  "--output",
  "json"
]);

let invalidation = {};
try {
  invalidation = JSON.parse(result.stdout).Invalidation || {};
} catch {
  invalidation = {};
}

logSuccess("CloudFront invalidation requested");
if (invalidation.Id) {
  console.log(`Invalidation ID: ${invalidation.Id}`);
  console.log(`Status: ${invalidation.Status || "Unknown"}`);
}
