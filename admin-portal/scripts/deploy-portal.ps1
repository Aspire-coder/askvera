param(
  [string]$StackName = "askvera-operations",
  [string]$Region = "us-east-1",
  [string]$PortalDomain = "operations.vera-api.xyz",
  [string]$CertificateArn = "",
  [string]$ApiOrigin = "https://api.vera-api.xyz",
  [Parameter(Mandatory = $true)][string]$CognitoDomainPrefix
)

$ErrorActionPreference = "Stop"
$portalRoot = Split-Path -Parent $PSScriptRoot
$repositoryRoot = Split-Path -Parent $portalRoot
$template = Join-Path $repositoryRoot "deployment\admin-portal.yaml"

function Assert-NativeCommandSucceeded([string]$Operation) {
  if ($LASTEXITCODE -ne 0) {
    throw "$Operation failed with exit code $LASTEXITCODE."
  }
}

aws cloudformation deploy `
  --template-file $template `
  --stack-name $StackName `
  --region $Region `
  --parameter-overrides `
    "PortalDomainName=$PortalDomain" `
    "CertificateArn=$CertificateArn" `
    "ApiOrigin=$ApiOrigin" `
    "CognitoDomainPrefix=$CognitoDomainPrefix" `
  --no-fail-on-empty-changeset
Assert-NativeCommandSucceeded "CloudFormation deployment"

function Get-StackOutput([string]$Key) {
  return aws cloudformation describe-stacks `
    --stack-name $StackName `
    --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='$Key'].OutputValue | [0]" `
    --output text
}

$bucket = Get-StackOutput "PortalBucketName"
$distribution = Get-StackOutput "PortalDistributionId"
$cognitoDomain = Get-StackOutput "CognitoDomain"
$clientId = Get-StackOutput "CognitoClientId"
$userPoolId = Get-StackOutput "CognitoUserPoolId"
$portalUrl = Get-StackOutput "PortalUrl"

$env:VITE_API_URL = $ApiOrigin
$env:VITE_COGNITO_DOMAIN = $cognitoDomain
$env:VITE_COGNITO_CLIENT_ID = $clientId
$env:VITE_COGNITO_REDIRECT_URI = "$portalUrl/"
$env:VITE_COGNITO_LOGOUT_URI = "$portalUrl/"
$env:VITE_ALLOW_DEMO = "false"

Push-Location $portalRoot
try {
  npm ci
  Assert-NativeCommandSucceeded "Dependency installation"
  npm run build
  Assert-NativeCommandSucceeded "Portal build"
  aws s3 sync dist "s3://$bucket/" --delete --region $Region
  Assert-NativeCommandSucceeded "Portal upload"
  aws cloudfront create-invalidation --distribution-id $distribution --paths "/*"
  Assert-NativeCommandSucceeded "CloudFront invalidation"
} finally {
  Pop-Location
}

Write-Host "AskVera Operations deployed to $portalUrl"
Write-Host "Cognito user pool: $userPoolId"
Write-Host "Cognito client: $clientId"
Write-Host "Next: create an administrator, add the user to AskVeraAdmins, update API SSM values, and add the CloudFront DNS target."
