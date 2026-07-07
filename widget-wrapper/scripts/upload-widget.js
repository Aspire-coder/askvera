import { distDir, ensureAwsAuthenticated, loadDeploymentConfig, logStep, logSuccess, requireCommand, runCommand } from "./utils.js";

const config = loadDeploymentConfig();

logStep("Checking AWS deployment access...");
requireCommand("aws", "Install the AWS CLI, then authenticate with an AWS profile or environment credentials.");
ensureAwsAuthenticated(config.region);
logSuccess("AWS authentication verified");

logStep(`Uploading versioned widget assets to ${config.versionS3Uri}...`);
runCommand("aws", [
  "s3",
  "sync",
  distDir,
  config.versionS3Uri,
  "--delete",
  "--cache-control",
  config.versionCacheControl,
  "--region",
  config.region
]);
logSuccess(`Uploaded version ${config.versionAlias}`);

logStep(`Uploading latest widget assets to ${config.latestS3Uri}...`);
runCommand("aws", [
  "s3",
  "sync",
  distDir,
  config.latestS3Uri,
  "--delete",
  "--cache-control",
  config.latestCacheControl,
  "--region",
  config.region
]);
logSuccess(`Uploaded ${config.latestAlias}`);
