# AskVera Operations

AskVera Operations is a responsive React and TypeScript admin portal with three connected views:

- **Live flow** replays recent requests across the same eight observable stages used by the chatbot backend.
- **Knowledge** uploads and indexes approved PDF, DOCX, text, Markdown, CSV, and HTML content.
- **Insights** shows users, questions, AI token usage, confidence, unanswered rate, feedback, topics, countries, languages, trends, and answer-level diagnostics.

## Run locally

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev
```

The portal opens at `http://127.0.0.1:5176`. Local development can use presentation-ready demo data or an explicitly enabled development API key. Production uses Cognito authorization-code sign-in with PKCE; no shared administrator secret is placed in the browser bundle.

## Build

```powershell
npm ci
npm run typecheck
npm run build
```

Set the `VITE_API_URL` and `VITE_COGNITO_*` values before building for a separate static host. Never put an admin key in a Vite environment variable or in the generated bundle.

## Deploy as a website

The CloudFormation template at `deployment/admin-portal.yaml` creates a private encrypted S3 bucket, CloudFront distribution, Cognito user pool, administrator group, and hosted sign-in domain. Deploy and publish from PowerShell:

```powershell
cd admin-portal
.\scripts\deploy-portal.ps1 `
  -CognitoDomainPrefix "askvera-operations-ACCOUNT" `
  -CertificateArn "arn:aws:acm:us-east-1:ACCOUNT:certificate/CERTIFICATE_ID"
```

Always pass an issued ACM certificate in `us-east-1` when using the custom domain `operations.vera-api.xyz` (or a matching wildcard certificate). Without `-CertificateArn`, CloudFront uses its default `*.cloudfront.net` certificate. If DNS points the custom hostname at that distribution, browsers show `NET::ERR_CERT_COMMON_NAME_INVALID`.

Verify the certificate before deploying and use only a certificate with status `ISSUED`:

```powershell
aws acm list-certificates `
  --region us-east-1 `
  --profile askvera-deploy `
  --query "CertificateSummaryList[?contains(DomainName, 'vera-api.xyz')].[CertificateArn,DomainName,Status]" `
  --output table
```

Set the AWS profile before running the script because the deployment script calls the AWS CLI internally:

```powershell
$env:AWS_PROFILE = "askvera-deploy"
```

After deployment:

1. Add the CloudFront output as the DNS CNAME for `operations.vera-api.xyz`.
2. Wait for the CloudFront distribution and invalidation to complete.
3. Open `https://operations.vera-api.xyz` and confirm the certificate is valid before sharing the URL.
4. Create Cognito users and add approved users to `AskVeraAdmins`.
5. Store the user-pool and client outputs in API SSM configuration.
6. Add `https://operations.vera-api.xyz` to the API's exact CORS origins.

## Supported knowledge documents

The uploader accepts PDF, DOCX, TXT, Markdown, CSV, HTML, and HTM files up to the configured limit. Each upload carries country, language, document type, access scope, version, and optional effective-date metadata. The generic extractor uses headings and overlapping retrieval-sized chunks, so it is not tied to policy formatting and also supports product information, training, FAQs, marketing, legal, and operational material.

Image-only scanned PDFs require an OCR stage before ingestion. The current service detects that no readable text was extracted and marks the job failed rather than indexing an empty or misleading document.
