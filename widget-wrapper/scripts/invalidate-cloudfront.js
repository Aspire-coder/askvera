import { loadDeploymentConfig, logStep, logSuccess, requireCommand, runCommand } from "./utils.js";

const config = loadDeploymentConfig();

logStep(`Invalidating CloudFront path ${config.latestInvalidationPath}...`);
requireCommand("aws", "Install the AWS CLI, then authenticate with an AWS profile or environment credentials.");
runCommand("aws", [
  "cloudfront",
  "create-invalidation",
  "--distribution-id",
  config.distributionId,
  "--paths",
  config.latestInvalidationPath,
  "--region",
  config.region
]);
logSuccess("CloudFront invalidated");
