# AskVera Full Project Context for Claude Code

Snapshot date: 2026-09-01 (America/Toronto)

This is the orientation document for a new Claude Code session. Read it before editing the repository. The full Markdown export that contains this document also embeds every included text source file, configuration contract, migration, script, test, and project document.

## Security boundary

- This handoff intentionally contains no passwords, access keys, private keys, OAuth codes, MFA codes, database credentials, secret values, or decrypted SecureString values.
- AWS credentials are short-lived and must be obtained through the approved AWS sign-in flow.
- Production configuration names and non-secret resource identifiers are documented. Secret values remain in AWS Secrets Manager or protected runtime configuration and must be resolved only at runtime.
- Do not call `secretsmanager get-secret-value` or `batch-get-secret-value` during ordinary debugging or documentation work.
- Never paste credentials, login callback URLs, authorization codes, or secret values into Claude Code, GitHub, logs, or documentation.

## Authoritative locations

### Active repository

| Purpose | Path |
|---|---|
| Authoritative local repository and export source | `C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy` |
| Parent workspace and archive root | `C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot` |
| Production EC2 checkout | `/opt/askvera` |
| Production service user | `askvera` |
| Production systemd unit | `askvera.service` |

The parent workspace contains many historical clones, temporary folders, dependency caches, and GitHub Desktop recovery folders. Do not treat those as authoritative. Confirm `git rev-parse --show-toplevel` returns the `askvera-deploy` path before editing.

### Active Git worktrees

| Local path | Branch | Snapshot commit | Purpose/status |
|---|---|---|---|
| `...\askvera-deploy` | `fix/global-directory-market-catalog` | `156650d` | Primary checkout. Clean. Its tree exactly matches `origin/main` at this snapshot. |
| `...\release-knowledge-live-data` | `fix/retrieval-release-gate-v4` | `dc69823` | Retrieval release documentation/worktree. |
| `...\release-market-selector` | `feat/market-readiness-selector` | `91461d8` | Open PR #3 worktree. |
| `...\release-production-chat-timeout` | `perf/retrieval-search-concurrency` | `886d82e` | Retrieval latency experiment worktree. |
| `...\release-retrieval-measurement-only` | `feat/retrieval-authority-stack` | `7d448a4` | Isolated authority/retrieval evaluation worktree. |
| `...\release-retrieval-profile-control` | `feat/retrieval-shadow-quality` | `2c37f41` | Shadow quality/profile evaluation worktree. |
| `...\release-support-selector` | `feat/support-routing-selector` | `0b8b0de` | Support routing selector worktree. |

Use `git worktree list --porcelain` to re-verify these before making changes. Do not delete or move worktrees without first checking branch ownership and uncommitted changes.

## Git and GitHub state

| Item | Value |
|---|---|
| GitHub repository | `https://github.com/Aspire-coder/askvera` |
| Visibility | Public |
| Default branch | `main` |
| Remote | `origin` -> `https://github.com/Aspire-coder/askvera.git` |
| Current remote main commit | `8136d848dcc17fce6fa13ebb40f5713a692cb2fa` |
| Current checkout commit | `156650d3cd95584475dc6b2b81edc97d0e3c48af` |
| Tree parity | Current checkout tree equals `origin/main` tree `be0ace8e53c9188605fa0bcd9ef88aa67bd1da52` |
| Working tree | Clean at snapshot time |
| Latest main CI | Passed, run `33469870675` |
| CI URL | `https://github.com/Aspire-coder/askvera/actions/runs/33469870675` |
| Open pull requests | PR #3 only |
| Standalone GitHub issues | None |

### Pull requests

| PR | State | Title |
|---:|---|---|
| 21 | Merged | Resolve global countries from full market catalog |
| 20 | Merged | Handle adjacent transposition in country names |
| 19 | Merged | Accept transposition typos in market names |
| 18 | Merged | Recognize sponsoring as global directory intent |
| 17 | Merged | Filter global retrieval by requested country |
| 16 | Merged | Use unauthenticated readiness check for deploy |
| 15 | Merged | Restore global translation runtime setting |
| 14 | Merged | Define bounded AWS client timeout settings |
| 13 | Merged | Fix ingestion schema migrations |
| 12 | Merged | Add safe retrieval shadow control |
| 11 | Merged | Calibrate selected retrieval evidence |
| 10 | Merged | Legal QA remediation |
| 9 | Merged | Match follow-up code to production Python |
| 8 | Merged | Restore follow-up and global directory answers |
| 7 | Merged | Preserve database certificate access |
| 6 | Merged | Allow GuardDuty bucket ownership validation |
| 5 | Merged | Harden operations portal deployment |
| 4 | Merged | Remove demo document activity from production |
| 3 | **Open** | Add market selector to readiness |
| 2 | Merged | Paginate and filter insight reviews |
| 1 | Merged | Add ingestion job schema migrations |

Open PR: `https://github.com/Aspire-coder/askvera/pull/3`.

### Releases and versions

| Item | Value |
|---|---|
| GitHub release | `v1.0.0-beta` |
| QA baseline tag | `v1.0.0-qa-baseline` |
| QA baseline production commit | `38922cfcdce2584aa879604ac1a870629c981f76` |
| QA baseline widget release | `v1.1.17` |
| Current source widget package version | `1.1.20` |
| Admin portal package version | `0.1.0` |

Do not infer that a package version is deployed merely because it exists in source. Confirm the immutable S3 release and current `latest` pointer before claiming deployment.

## Current production status and known open items

### Public checks performed for this snapshot

| Endpoint | Result |
|---|---|
| `https://api.vera-api.xyz/health` | HTTP 200 from Nginx |
| `https://operations.vera-api.xyz` | HTTP 200 from S3/CloudFront-backed portal |
| `https://d1wzljalfbhsv7.cloudfront.net/widget/latest/widget.js` | HTTP 200 |
| `https://d1wzljalfbhsv7.cloudfront.net/widget/latest/widget.css` | HTTP 200 |
| `https://chat.vera-api.xyz` | **TLS hostname/certificate mismatch observed** (`SEC_E_WRONG_PRINCIPAL`) |

The widget CDN assets are available, but the custom `chat.vera-api.xyz` hostname needs its DNS/CloudFront alternate-domain and ACM certificate configuration checked before it should be presented as healthy.

### Deployment/retrieval state

- GitHub `main` is green at `8136d84`.
- The latest production promotion attempt passed configuration validation, migrations, automated tests, local health, and public health, but the blocking retrieval canary returned **10/15**.
- The deployment script correctly rolled the service back to the previous working revision `27f6a30`.
- The five failing canary areas were Belgium minimum order, Mexico sponsoring, Thailand minimum order, Kyrgyzstan foreign-FBO bonus, and Uruguay telephone.
- The current diagnosis is that code-level country/global routing fixes did not change production candidate evidence. The active global-document/index generation and metadata need to be traced before another deploy.
- Do not bypass the retrieval canary or deploy with `--skip-tests` to force this release through.
- Verify the actual EC2 revision and runtime profile again after AWS login because the status above is the last observed deployment state, not a secret-backed live query made by this export.

### Engineering work that is implemented but not automatically production-ready

- Authority/entity/question-type classification and authority-aware retrieval experiments exist on isolated branches/worktrees.
- Parent-child retrieval and signal-based confidence work must remain isolated until measured against Current and all promotion gates pass.
- Semantic cache is designed to remain shadow-only until held-out quality and safety gates prove it safe. Exact cache behavior is versioned by evidence and runtime versions.
- PR #3 remains open and must be reviewed independently.

## Product and architecture summary

AskVera is a governed enterprise knowledge assistant. It answers from approved Forever Living policy documents for the selected market/language and from approved global documents such as the worldwide office/sponsoring directory. It must refuse unsupported medical, income, external-data, and policy claims rather than inventing an answer.

### Request path

1. Browser loads the React widget from CloudFront.
2. Widget validates its public instance ID, approved origin, market, language, privacy version, and consent.
3. FastAPI applies input governance, PII handling, session checks, and deterministic safety/conversation routing.
4. Retrieval uses OpenSearch section evidence with strict country/language isolation for policy content.
5. Global documents may answer a named foreign country even when the user's selected market differs, provided the record carries the approved global access scope.
6. Bedrock generates only from approved retrieved evidence.
7. Citation, numeric grounding, output integrity, safety, and evidence checks gate the response.
8. Eligible responses may use exact/versioned cache behavior; semantic reuse remains shadow-only unless separately promoted.
9. Analytics, audit, feedback, and optional support routing are persisted or queued.

### Main source ownership

| Path | Responsibility |
|---|---|
| `main.py` | FastAPI startup and route wiring |
| `api/` | Public and administrator HTTP routes |
| `app/orchestrator/chat_orchestrator.py` | End-to-end chat turn orchestration |
| `app/retrieval/` | Query planning, OpenSearch retrieval, ranking, reranking, vNext/shadow logic |
| `app/models/` | Bedrock model provider and model routing |
| `app/validation/` | Numeric, citation, grounding, and output-integrity validation |
| `services/` | AWS clients, sessions, RDS, cache, ingestion, analytics, auth, support, localization |
| `config/` | Runtime settings, markets, multilingual controlled responses, glossary and safety config |
| `migrations/` | Ordered additive PostgreSQL migrations |
| `scripts/` | Deployment, ingestion, release gates, traces, repair, export and operations tools |
| `tests/` | Unit, regression, safety, retrieval and contract tests |
| `widget-wrapper/` | Customer-facing React/TypeScript widget and immutable CDN deployment tooling |
| `admin-portal/` | React/TypeScript operations portal |
| `deployment/` | EC2, Nginx, systemd, CloudFormation, SSM and delivery assets |
| `.github/workflows/` | CI and widget release workflows |

Snapshot repository counts: 544 tracked files, 283 Python files, 104 TypeScript/TSX files, 48 Markdown documents, and 90 files under `tests/`.

## AWS account and production inventory

### Identity and region

| Item | Last verified/documented value |
|---|---|
| AWS account | `615592621509` |
| Primary region | `us-east-1` |
| Local CLI profile previously used | `askvera-prod` (not present in the current CLI session at snapshot time) |
| Previously observed caller | `arn:aws:iam::615592621509:user/pavan410` |

Treat identity and resource state as stale until re-verified with `aws sts get-caller-identity` after an approved `aws login`.

### Core AWS resources

| AWS service | Known resource/value | Purpose and access |
|---|---|---|
| EC2 | Instance `i-01d8dc208e2e4fa7f`, Name `askvera-prod` | Runs Nginx and FastAPI. Prefer Systems Manager Session Manager/Run Command, not SSH. |
| EC2 networking | Last observed public IP `52.87.10.58`, private IP `10.0.5.247` | Re-verify before use; public addressing may change unless elastic. |
| IAM | Instance profile/role `ChatbotAppRole` | Application uses role credentials; never put AWS keys on the server. |
| Systems Manager | Parameter path `/askverachat/prod/`; EC2 previously online as managed node | Runtime configuration and secure shell-less operations. |
| S3 approved knowledge | Documented production bucket `askverachat-prod-kb`; older content/test references include `askverachat-prod-content` | Approved source documents, ingestion objects, and controlled publication. Verify active `S3_BUCKET` parameter. |
| S3 widget | `askvera-widget-assets` | Immutable widget releases and `widget/latest` alias. |
| CloudFront widget | Distribution ID `E11MOVF0JGC9EM`; domain `d1wzljalfbhsv7.cloudfront.net` | Serves widget JS/CSS. Custom `chat.vera-api.xyz` TLS currently needs correction. |
| CloudFormation portal | Stack name `askvera-operations` | Creates portal S3, CloudFront, Cognito and related controls. Query stack outputs for exact live IDs. |
| Cognito portal | Domain pattern `askvera-operations.auth.us-east-1.amazoncognito.com` | Operations portal login, users and groups. Client ID is runtime/deployment config and is not copied here. |
| OpenSearch Serverless | Active index default `askvera-policy-sections`; experimental index default `askvera-policy-sections-vnext` | Primary section retrieval and isolated candidate evaluation. Endpoint comes from protected runtime config. |
| Bedrock | Guardrail `askverachat-guardrail`, ID `idy33rbs9v1i`, published version `1` | Generation, embeddings, optional evidence selection/reranking and guardrails. Model IDs come from runtime config. |
| RDS PostgreSQL | Identifier and secret reference stored under SSM (`RDS_DB_IDENTIFIER`, `RDS_SECRET_ARN`) | Sessions, consent, analytics, operations, feedback and ingestion state. Credentials stay in Secrets Manager. |
| ElastiCache/Valkey | Endpoint/user/cache name stored in SSM (`REDIS_HOST`, `REDIS_USER`, `REDIS_CACHE_NAME`) | Exact cache, optional semantic shadow cache and shared runtime state using IAM auth. |
| Kinesis Firehose | Stream default `askvera-audit` | Durable audit delivery when enabled. |
| SQS | Feedback queue and optional ingestion queue/DLQ configured through SSM/CloudFormation | Async feedback and durable ingestion commands. |
| CloudWatch | Namespace `ASKVera`; alarm prefix `AskVera` | Logs, latency/error/cache/retrieval/governance metrics and alarms. |
| SNS | Topic default `askvera-alerts` when enabled | Alarm notifications. |
| SES | Runtime-configured support sender/routes | Sends support requests when enabled. Internal recipient addresses are not included. |
| GuardDuty malware protection | `deployment/ingestion-malware-protection.yaml` with knowledge bucket integration | Scans uploaded knowledge before publication when deployed. |
| ACM/DNS | Certificates must be in `us-east-1` for CloudFront custom domains | Verify certificates and aliases for `operations.vera-api.xyz` and `chat.vera-api.xyz`. |

### Production URLs

| Component | URL |
|---|---|
| API | `https://api.vera-api.xyz` |
| Health | `https://api.vera-api.xyz/health` |
| Operations portal | `https://operations.vera-api.xyz` |
| Widget JS | `https://d1wzljalfbhsv7.cloudfront.net/widget/latest/widget.js` |
| Widget CSS | `https://d1wzljalfbhsv7.cloudfront.net/widget/latest/widget.css` |
| Widget custom hostname | `https://chat.vera-api.xyz` (TLS issue at snapshot time) |

## AWS configuration contract

The complete key list and defaults are in `config/settings.py` and `deployment/production.env.example`. Production loads parameters under `/askverachat/prod/` when `SSM_CONFIG_ENABLED` is active.

Important categories include:

- Foundation: `AWS_REGION`, `ENVIRONMENT`, `APP_VERSION`, `SSM_CONFIG_ENABLED`, `SSM_CONFIG_PATH`.
- Database: `RDS_DB_IDENTIFIER`, `RDS_HOST`, `RDS_PORT`, `RDS_DB_NAME`, `RDS_SECRET_ARN`, TLS settings.
- Cache: `REDIS_HOST`, `REDIS_PORT`, `REDIS_USER`, `REDIS_CACHE_NAME`, exact/semantic cache flags and versions.
- Knowledge: `S3_BUCKET`, legal/knowledge upload buckets, active knowledge/pipeline version values.
- Retrieval: `RETRIEVAL_PROVIDER`, `OPENSEARCH_ENDPOINT`, `OPENSEARCH_INDEX`, `OPENSEARCH_VNEXT_INDEX`, result counts, selector/reranker/authority/parent-child flags and weights.
- Bedrock: knowledge base/data source IDs, model IDs, guardrail ID/version, confidence and timeout settings.
- Admin: Cognito pool/client/domain/group, RBAC/user-management and widget-management flags.
- Delivery: Firehose stream, SQS URLs, SES support routing, CloudWatch/SNS settings.
- Web: exact CORS origins, widget registry/config, CDN loader/style URLs and legal version.

Do not copy live parameter values into this export. To inventory safely, list parameter metadata with `ssm describe-parameters`; retrieve only explicitly approved non-secret settings. Never decrypt SecureString values for documentation.

## How to access everything safely

### Local development

Use Python 3.11 to match CI and production, Node 22 for frontend builds, and Git from GitHub Desktop or the bundled runtime.

```powershell
cd "C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy"
git fetch origin --prune
git status
git switch main
git pull --ff-only origin main
```

If `git` is not on PATH, GitHub Desktop includes Git, or the Codex runtime Git path can be added for that terminal session. Do not make a second clone merely to work around PATH.

Backend checks:

```powershell
python -m pip install -r requirements.txt
python -m pytest tests/unit -q
python scripts/run_retrieval_canary.py --validate-only
python scripts/validate_config.py
```

Widget:

```powershell
cd widget-wrapper
npm ci
npm run typecheck
npm run build
npm run validate-widget
npm run dev
```

Operations portal:

```powershell
cd admin-portal
npm ci
npm run build
npm run validate-production-build
npm run dev
```

### AWS sign-in

The approved local flow is AWS CLI v2 `aws login`, which provides short-lived credentials. Verify the account immediately afterward.

```powershell
aws --version
aws login --profile askvera-prod
aws sts get-caller-identity --profile askvera-prod --region us-east-1
$env:AWS_PROFILE = "askvera-prod"
$env:AWS_REGION = "us-east-1"
```

Do not use long-lived access keys. If the profile name differs, use the profile that the login command creates and record only the profile name, account and non-secret ARN.

### EC2 access through Systems Manager

Prefer Session Manager:

```powershell
aws ssm start-session --target i-01d8dc208e2e4fa7f --profile askvera-prod --region us-east-1
```

On the instance:

```bash
cd /opt/askvera
sudo systemctl status askvera
sudo journalctl -u askvera -n 200 --no-pager
curl -fsS http://127.0.0.1:8000/health
sudo -u askvera git status
sudo -u askvera git rev-parse HEAD
```

Use Run Command for auditable noninteractive checks. Never paste secret-bearing command output into issue trackers or AI chats.

### Deployment

The production deploy script performs a fetch/fast-forward, dependency install, compile, production config validation, ordered migrations, tests, runtime config sync, restart, local/public health checks, and the blocking retrieval canary. Any failure rolls back to the prior revision.

```bash
cd /opt/askvera
sudo BRANCH=main ./deployment/deploy.sh
```

Before deploying:

1. Confirm `origin/main` is the intended reviewed commit.
2. Confirm GitHub CI is green.
3. Confirm no unreviewed local server changes.
4. Validate production configuration before restart.
5. Keep tests and retrieval canary enabled.
6. Record previous and target commits.
7. Confirm health and retrieval gates after restart.

### Widget release

Widget releases are immutable and versioned from `widget-wrapper/package.json`. The current source version is `1.1.20`. Publishing creates `widget/v<version>/` and promotes files to `widget/latest/`; existing immutable versions must never be overwritten.

GitHub Actions uses OIDC and repository secrets `AWS_DEPLOY_ROLE_ARN` and `AWS_REGION`. Do not add AWS access keys to GitHub.

### Operations portal deployment

Use `admin-portal/scripts/deploy-portal.ps1` and the `askvera-operations` CloudFormation stack. Query stack outputs for the current bucket, distribution, user pool, and client IDs. Ensure the ACM certificate is in `us-east-1` and covers the custom hostname before changing DNS.

## Promotion gates for retrieval changes

A retrieval change is not release-ready merely because unit tests or a small canary pass. Keep these independently reported:

1. Frozen manifest and environment parity.
2. In-scope recall on frozen and held-out questions.
3. Safety boundary and compound/split-intent behavior.
4. Legal/disclaimer completeness.
5. Response integrity: no empty labels, heading-only output, truncation, invented terminology, or missing citations.
6. Cross-market isolation for country policy documents.
7. Cross-market availability for approved global documents when a foreign country is named.
8. Repeated cache-free runs to measure managed-model variance.
9. Latency and cost checks.
10. Full regression suite, then production parity after deploy.

Confidence thresholds are the last tuning lever because they trade answer rate against safe abstention. Do not lower global thresholds to repair one failed question. Fix retrieval representation, intent decomposition, authority selection, or output integrity at the actual failing layer.

## Database migrations

Ordered migrations currently include:

- `20260728_01_feedback_expected_answer.sql`
- `20260728_02_admin_rbac.sql`
- `20260728_03_widget_configs.sql`
- `20260729_01_operations_admin.sql`
- `20260730_01_runtime_hardening.sql`
- `20260730_02_controlled_knowledge_publication.sql`
- `20260814_01_ingestion_upload_uri.sql`
- `20260814_02_ingestion_job_metadata.sql`
- `20260817_01_operations_roadmap.sql`
- `20260819_01_model_routing_analytics.sql`
- `20260825_01_retrieval_runtime_control.sql`

Apply them only through `scripts/run_db_migrations.py --load-ssm --apply`. Do not manually modify production schema or rewrite an already-applied migration.

## Cleanup and historical folders

The parent archive contains many folders prefixed with `GITHUB_DESKTOP_`, AWS configuration exports, `.release-*`, caches, analysis outputs, and older clones. They are retained for recovery/history and are not the source of truth. The tracked cleanup list is `docs/AWS_CLEANUP_TRACKER.md`. Do not delete AWS prefixes or local recovery folders merely because they look old; verify references and create a recoverable backup first.

Known temporary AWS cleanup candidates include old `bedrock-kb-test/section-chunks/` prefixes and transferred QA spreadsheets under temporary S3 paths. The active approved knowledge bucket/index/generation must never be removed during cleanup.

## First actions for Claude Code

1. Read `AGENTS.md`, `CLAUDE.md`, `README.md`, this context document, and `docs/ASKVERA_COMPLETE_PROJECT_HANDOFF.md`.
2. Confirm repository root, branch, clean status, `origin/main`, and worktrees.
3. Do not assume production equals GitHub main; verify EC2 commit and release gates.
4. Inspect the exact modules and tests related to the requested change before editing.
5. Preserve country policy isolation and global-document cross-market behavior.
6. Preserve safe refusal behavior and citation/evidence contracts.
7. Use feature flags, isolated indexes, and shadow evaluation for retrieval experiments.
8. Run focused tests, full CI-compatible tests, retrieval gates and build validation.
9. Do not deploy, publish knowledge, rotate cache/knowledge versions, change AWS configuration, or delete resources without explicit authorization.
10. Never reveal secrets or credentials in output.

## Verification notes for this snapshot

- Git remote metadata refreshed from GitHub on 2026-09-01.
- GitHub repository, PR, release and Actions state queried from the public GitHub API.
- Public production URLs checked without privileged access.
- Live AWS resource inventory could not be re-queried because no AWS CLI profile/credentials were active in this Windows session. Known resource IDs above come from previously verified deployment work and tracked project documentation and are marked accordingly.
- Re-run the AWS inventory after approved `aws login` before treating mutable IPs, deployment commit, SSM state, index generation, Cognito IDs, CloudFormation outputs, alarms, queues or database/cache endpoints as current.

