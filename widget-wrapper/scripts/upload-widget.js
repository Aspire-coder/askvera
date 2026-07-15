import {
  ensureAwsAuthenticated,
  hasFlag,
  loadDeploymentConfig,
  logStep,
  logSuccess,
  printDeploymentPlan,
  requireCommand,
  runCommand,
  runCommandCapture,
  widgetAssets
} from "./utils.js";

const config = loadDeploymentConfig();
const dryRun = hasFlag("--dry-run");

if (dryRun) {
  printDeploymentPlan(config);
  logSuccess("Dry run complete. No S3 uploads were performed.");
  process.exit(0);
}

logStep("Checking AWS deployment access...");
requireCommand("aws", "Install the AWS CLI, then authenticate with an AWS profile or environment credentials.");
ensureAwsAuthenticated(config.region);
logSuccess("AWS authentication verified");

logStep(`Checking immutable release path ${config.versionS3Uri}...`);
const existingRelease = runCommandCapture("aws", ["s3", "ls", config.versionS3Uri, "--region", config.region], {
  allowFailure: true
});
if (existingRelease.ok && existingRelease.stdout.trim()) {
  console.error(`Release ${config.widgetPrefix}/${config.versionAlias}/ already exists.`);
  console.error("Refusing to overwrite immutable release.");
  process.exit(1);
}
logSuccess("Versioned release path is available");

logStep(`Uploading versioned widget assets to ${config.versionS3Uri}...`);
for (const asset of widgetAssets) {
  runCommand("aws", [
    "s3",
    "cp",
    asset.path,
    `${config.versionS3Uri}${asset.fileName}`,
    "--cache-control",
    config.versionCacheControl,
    "--content-type",
    asset.contentType,
    "--region",
    config.region
  ]);
}
logSuccess(`Uploaded version ${config.versionAlias}`);

logStep(`Uploading latest widget assets to ${config.latestS3Uri}...`);
runCommand("aws", ["s3", "rm", config.latestS3Uri, "--recursive", "--region", config.region]);
for (const asset of widgetAssets) {
  runCommand("aws", [
    "s3",
    "cp",
    asset.path,
    `${config.latestS3Uri}${asset.fileName}`,
    "--cache-control",
    config.latestCacheControl,
    "--content-type",
    asset.contentType,
    "--region",
    config.region
  ]);
}
logSuccess(`Uploaded ${config.latestAlias}`);
