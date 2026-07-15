import {
  hasFlag,
  loadDeploymentConfig,
  logStep,
  logSuccess,
  printDeploymentPlan,
  printDeploymentSummary,
  runCommand,
  runCommandCapture,
  widgetRoot
} from "./utils.js";

const dryRun = hasFlag("--dry-run");
const config = loadDeploymentConfig();
const nodeCommand = process.execPath;

console.log("");
console.log("AskVera Widget Deployment");
console.log("-------------------------");
if (dryRun) {
  console.log("Mode: dry run");
  printDeploymentPlan(config);
}

logStep("Building widget...");
runCommand(nodeCommand, ["scripts/build-widget.mjs"], { cwd: widgetRoot });
logSuccess("Build complete");

logStep("Validating build...");
runCommand(nodeCommand, ["scripts/validate-build.js"], { cwd: widgetRoot });

if (dryRun) {
  logSuccess("Dry run complete. No upload or invalidation was performed.");
  printDeploymentSummary(config);
  process.exit(0);
}

logStep("Uploading widget assets...");
runCommand(nodeCommand, ["scripts/upload-widget.js"], { cwd: widgetRoot });

logStep("Invalidating latest CloudFront alias...");
const result = runCommandCapture(nodeCommand, ["scripts/invalidate-cloudfront.js"], { cwd: widgetRoot });
const idMatch = result.stdout.match(/Invalidation ID:\s*(.+)/);
const statusMatch = result.stdout.match(/Status:\s*(.+)/);
printDeploymentSummary(config, {
  id: idMatch?.[1]?.trim(),
  status: statusMatch?.[1]?.trim()
});
