import {
  ensureAwsAuthenticated,
  fail,
  hasFlag,
  loadDeploymentConfig,
  logStep,
  logSuccess,
  requireCommand,
  runCommand,
  runCommandCapture,
  widgetAssets
} from "./utils.js";

const config = loadDeploymentConfig();
const dryRun = hasFlag("--dry-run");
const requestedVersion = process.argv.slice(2).find((value) => !value.startsWith("--"));

if (!requestedVersion) {
  fail("Provide an immutable release version, for example: npm run rollback-widget -- v1.0.20");
}

const versionAlias = requestedVersion.startsWith("v") ? requestedVersion : `v${requestedVersion}`;
if (!/^v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(versionAlias)) {
  fail(`Invalid release version: ${requestedVersion}`);
}

const sourceS3Uri = `s3://${config.bucket}/${config.widgetPrefix}/${versionAlias}/`;

console.log("");
console.log("AskVera Widget Rollback Plan");
console.log("----------------------------");
console.log(`Source release: ${config.widgetPrefix}/${versionAlias}/`);
console.log(`Latest path:    ${config.widgetPrefix}/${config.latestAlias}/`);
console.log(`CloudFront:     ${config.distributionId}`);
console.log(`Invalidation:   ${config.latestInvalidationPath}`);

if (dryRun) {
  logSuccess("Dry run complete. No S3 objects were changed.");
  process.exit(0);
}

requireCommand("aws", "Install the AWS CLI, then authenticate with an AWS profile or environment credentials.");
logStep("Checking AWS deployment access...");
ensureAwsAuthenticated(config.region);

logStep(`Verifying immutable release ${sourceS3Uri}...`);
for (const asset of widgetAssets) {
  const result = runCommandCapture(
    "aws",
    ["s3", "ls", `${sourceS3Uri}${asset.fileName}`, "--region", config.region],
    { allowFailure: true }
  );
  if (!result.ok || !result.stdout.trim()) {
    fail(`Release ${versionAlias} is incomplete: ${asset.fileName} was not found.`);
  }
}
logSuccess("Rollback release verified");

logStep(`Promoting ${versionAlias} to ${config.latestAlias}...`);
runCommand("aws", ["s3", "rm", config.latestS3Uri, "--recursive", "--region", config.region]);
for (const asset of widgetAssets) {
  runCommand("aws", [
    "s3",
    "cp",
    `${sourceS3Uri}${asset.fileName}`,
    `${config.latestS3Uri}${asset.fileName}`,
    "--cache-control",
    config.latestCacheControl,
    "--content-type",
    asset.contentType,
    "--metadata-directive",
    "REPLACE",
    "--region",
    config.region
  ]);
}

logStep(`Invalidating CloudFront path ${config.latestInvalidationPath}...`);
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

logSuccess(`Rolled back latest to ${versionAlias}`);
if (invalidation.Id) {
  console.log(`Invalidation ID: ${invalidation.Id}`);
  console.log(`Status: ${invalidation.Status || "Unknown"}`);
}
