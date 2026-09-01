# AskVera Developer Guide

## 1. Purpose

AskVera is an embedded knowledge assistant for approved Forever Living company-policy documents and the global office directory. It is delivered as a JavaScript widget, backed by a FastAPI service, and managed through an internal operations portal.

The system is designed to:

- answer only from approved knowledge;
- keep country and language policy content isolated;
- make the global office directory available across markets;
- require privacy consent before chat;
- protect personal information and sensitive claims;
- show evidence and source documents with answers;
- collect feedback and support requests for operations teams.

The live retrieval provider is `opensearch_section`. Amazon Bedrock is used for model generation and related AI services where configured; the application is not currently using a Bedrock Knowledge Base as its primary retrieval path.

## 2. Repository Map

| Area | Location | Responsibility |
|---|---|---|
| API entry point | `main.py` | Starts FastAPI and application lifecycle |
| API routes | `api/` | Chat, widget, admin, consent, feedback, support, and health endpoints |
| Orchestration | `app/` | Chat flow, evidence decisions, model providers, monitoring, and response contracts |
| Configuration | `config/` | Settings, markets, locales, glossary, guardrail topics, and conversation routes |
| Services | `services/` | Sessions, consent, legal documents, ingestion, feedback, support, PII, guardrails, and security state |
| Retrieval | `app/retrieval/` | OpenSearch section retrieval, ranking, scope filtering, and retrieval metadata |
| Shared utilities | `utils/` | Validation, redaction, logging, field normalization, and exceptions |
| Customer widget | `widget-wrapper/` | React/TypeScript SDK, UI, localization, storage, API clients, and CDN deployment |
| Operations portal | `admin-portal/` | Insights, live flow, knowledge uploads, widgets, users, support routing, and feedback review |
| Deployment | `deployment/` | EC2, Nginx, SSL, rollback, ingestion infrastructure, and environment templates |
| Database migrations | `migrations/` | PostgreSQL schema changes for sessions, feedback, RBAC, widget configuration, and controlled publication |
| Tests | `tests/` | Unit and integration-style regression tests |

## 3. High-Level Architecture

```text
Customer website
    |
    | embedded widget.js and widget.css from CloudFront/S3
    v
AskVera React widget
    |
    | init, consent, chat, feedback, support, source, health APIs
    v
Nginx on EC2
    |
    v
FastAPI application (systemd: askvera)
    |
    +--> consent and legal-document service
    +--> session and conversation history service
    +--> PII detection/redaction and guardrails
    +--> OpenSearch section retrieval
    +--> Bedrock model provider
    +--> evidence gate and answer validator
    +--> PostgreSQL audit, feedback, and support records
    +--> Valkey/Redis cache and shared security state
    +--> S3 approved documents and source PDFs
    +--> SES support email delivery
    +--> CloudWatch logs, alarms, and notifications
```

## 4. Chat Request Flow

1. The widget loads its public configuration and calls the widget-init endpoint.
2. The API validates the widget ID, approved origin, and widget session token.
3. The user selects a market and language.
4. The widget loads the legal documents for that market and language.
5. The user accepts the privacy terms. Consent is recorded with market, language, legal version, and session ID.
6. The widget sends the question with the session, market, language, and role context.
7. The API validates the request and applies rate limits.
8. PII and unsafe-content checks run before retrieval or model generation.
9. The retrieval layer searches local policy content plus globally scoped directory content.
10. Retrieval applies scope filters, so country policy records cannot leak between markets. Global directory records remain available to all selected markets.
11. Candidate results are ranked and passed through the evidence decision.
12. On an evidence-approved request, the Bedrock model receives the controlled prompt and selected evidence.
13. The answer contract validates citations, grounding, numeric claims, safety, and PII.
14. The API returns the answer, confidence, sources, metadata, and available actions.
15. The widget renders the answer, citations, feedback controls, and support action where appropriate.
16. Audit events, token usage, cache details, and feedback are stored according to the configured retention rules.

## 5. Knowledge Sources and Metadata

### Country policy documents

Country policy documents are stored in S3 under a country/language path and indexed as section records. Each indexed record should carry at least:

- `country`;
- `language`;
- `document_type=policy`;
- `access_scope=country`;
- source file and S3 URI;
- section ID and title;
- page range;
- extracted content;
- status such as `staging` or `active`;
- ingestion ID and content hash.

### Global directory

The international office directory is a separate globally scoped source. Its records use metadata such as:

- `country=GLOBAL`;
- `language=en` unless a translated source is added;
- `document_type=office_directory`;
- `access_scope=global`;
- record type such as `office` or `staff`;
- structured address, phone, email, website, and contact fields where available.

Global records are merged with, but not confused with, country policy records.

## 6. Document Ingestion

The normal ingestion lifecycle is:

```text
Upload source PDF
    -> validate file and metadata
    -> extract text and page boundaries
    -> detect policy sections or directory records
    -> normalize encoding and fields
    -> write JSONL/CSV artifacts
    -> load records with status=staging
    -> verify counts, locale, source, and content
    -> publish as active
    -> remove/retire the replaced generation
    -> invalidate affected answer-cache entries
```

Policy extraction is implemented in `scripts/ingestion/extract_policy_sections.py`. Loading is handled by `scripts/ingestion/load_policy_sections_to_opensearch.py`. The scripts support staging, active publication, source replacement, document type, and access scope.

A document should not be made active until the staging checks confirm:

- expected record count;
- correct country and language;
- correct document type and access scope;
- no unintended duplicate generation;
- complete source URI metadata;
- bounded chunk sizes;
- acceptable text encoding;
- representative section or directory queries return expected records.

## 7. Chunking and Retrieval

The policy path preserves numbered sections and list structure where possible, then splits oversized sections into bounded parts. This keeps qualification rules, thresholds, exceptions, and page references together while preventing oversized model context.

Retrieval combines lexical and semantic signals and applies hard metadata filters before ranking. The important rule is scope first, relevance second:

```text
Allowed country policy records for selected market/language
        UNION
Global directory records
        -> lexical/semantic candidate search
        -> rank fusion and optional reranking
        -> evidence selection
        -> grounded generation
```

Do not replace `opensearch_section` with a Bedrock Knowledge Base without a separate evaluation. Retrieval changes must be tested for:

- country isolation;
- language isolation;
- global directory access;
- typo and whitespace tolerance;
- numeric threshold completeness;
- source and page accuracy;
- unsupported and safety-sensitive questions;
- follow-up questions using session history.

## 8. Answer Safety and Quality

The answer pipeline is fail-closed. It should not invent an answer when evidence is insufficient.

Key controls include:

- PII detection and redaction before model processing;
- response-side PII scrubbing;
- medical, income, regulatory, and other guardrail topics;
- evidence gate before generation;
- numeric-claim grounding;
- citation and source validation;
- fallback responses when evidence is insufficient;
- support escalation as an application action, not a model-invented promise.

The persona and response wording are configured through `config/vera_persona.py`, `config/guardrail_topics.py`, and localization/configuration files. New languages should extend configuration and localized copy, not add country-specific branches to orchestration code.

## 9. Sessions, Consent, and Storage

The widget maintains a session ID and token lifecycle through `widget-wrapper/src/services/` and `widget-wrapper/src/sdk/auth.ts`. Conversation state is managed through the widget state provider and reducer.

The storage layer is abstracted under `widget-wrapper/src/storage/` so persistence policy can be changed centrally. Consent is required before chat submission. The server remains authoritative for consent, session expiry, and access checks; browser storage must not be treated as proof of authorization.

Sessions, consent events, chat records, feedback, and support records are stored through the backend services and database configuration. Sensitive values must not be copied into logs, cache keys, analytics, or source metadata.

## 10. Caching

The answer cache is a performance and cost optimization only. Every cache hit must still pass current session, market, language, safety, and evidence checks before being returned.

Cache keys should include the effective market/language scope, normalized question, relevant prompt or knowledge version, and safety context. When approved content is replaced, affected cached answers must be invalidated or versioned out. Semantic caching can be introduced behind a feature flag and must be evaluated for cross-market leakage and false matches before enabling it broadly.

## 11. Customer Widget

The widget is built with Vite and TypeScript/React. Important areas include:

- `src/sdk/AskVera.ts`: public SDK entry point;
- `src/sdk/WidgetRuntime.tsx`: runtime lifecycle and screen state;
- `src/generic-widget/`: header, region selector, consent, messages, references, support form, and menu;
- `src/api/`: typed API clients;
- `src/localization/widgetCopy.ts`: UI copy by language;
- `src/renderers/`: Markdown and citation rendering;
- `src/storage/`: session and locale preferences;
- `scripts/build-widget.mjs`: build process;
- `scripts/validate-build.js`: artifact validation;
- `scripts/upload-widget.js`: immutable version and latest CDN release.

The widget is distributed from S3 through CloudFront. Releases are immutable. If a version already exists, increment the package version rather than overwriting it. The deployment process uploads both a versioned path and `widget/latest/`, then invalidates the latest CloudFront path.

## 12. Operations Portal

The portal is a Vite/React application in `admin-portal/`. Its major areas are:

- live flow and answer review;
- knowledge upload and ingestion status;
- feedback and analytics;
- widget registry and embed code;
- support routing;
- user access and RBAC;
- monitoring and operational diagnostics.

Operations users should be able to see staging versus active knowledge, source metadata, feedback, token usage, market/language filters, support routes, and failure diagnostics without receiving unnecessary raw personal data.

## 13. Support Requests

The widget support form collects the minimum required information, including name, email, question, selected market, language, and session/reference context. The backend validates the form, creates a ticket reference, records the request, resolves the market route, and sends the transactional email through SES when enabled.

Support routing is configuration-driven. A market route contains a department, destination email, and active flag. Changing a route should not require a code deployment, but the new destination must be verified and tested before use.

## 14. AWS and Runtime Services

The deployment currently uses or integrates with:

- EC2 for the FastAPI host;
- systemd for the `askvera` service;
- Nginx for HTTPS reverse proxying and origin controls;
- S3 for approved documents and widget assets;
- CloudFront for widget delivery;
- OpenSearch Serverless for section retrieval;
- Bedrock for model generation and configured AI controls;
- PostgreSQL/RDS for application records and session/audit data;
- Valkey/Redis for cache and shared runtime state;
- SES for support email delivery;
- SSM Parameter Store and IAM for runtime configuration and permissions;
- CloudWatch for logs, alarms, and operational monitoring;
- Route 53 or external DNS for API routing.

Exact resource names and environment values belong in deployment configuration, not in application source code.

## 15. Configuration

Configuration is loaded through `config/settings.py` and runtime SSM values. Important groups include:

- environment and security profile;
- retrieval provider and pipeline version;
- knowledge-base version;
- model and prompt versions;
- widget registry and origin allowlists;
- markets, languages, and legal versions;
- support routes and SES settings;
- database, cache, OpenSearch, Bedrock, and monitoring settings.

Production startup validation should run before restart. A configuration dry run should verify required values, ARN formats, origins, provider selection, and security flags before a deployment changes the live process.

## 16. Local Development

Backend prerequisites are listed in `requirements.txt`. The widget and portal have independent `package.json` files.

Typical workflow:

```powershell
cd C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy

# Backend environment and tests
python -m pytest tests/unit -q

# Widget
cd widget-wrapper
npm install
npm run build

# Operations portal
cd ..\admin-portal
npm install
npm run build
```

Use a local `.env` or approved local configuration for development only. Never copy production secrets into the repository or commit them to Git.

## 17. Testing

Tests are organized under `tests/unit/` and include coverage for chat orchestration, retrieval, cache behavior, consent, API protection, admin authentication/RBAC, feedback, alarms, Bedrock providers, and ingestion.

Before merging a retrieval or widget change, run:

1. Python compilation and lint checks.
2. The complete Python test suite in a clean environment.
3. Widget typecheck/build and artifact validation.
4. Country/language isolation tests.
5. Global directory tests.
6. PII and safety-response tests.
7. Consent, session, feedback, and support-request tests.
8. Mobile and desktop widget smoke tests.
9. Staging ingestion and publication verification for any new documents.

If the full suite cannot run because dependencies are missing or inaccessible, report the result as unverified. Syntax checks are not a substitute for the complete test suite.

## 18. Deployment and Rollback

### Backend

```text
commit and push to main
    -> pull on EC2 as askvera
    -> install only approved dependencies if required
    -> validate runtime configuration
    -> restart askvera
    -> check systemd status and /health
    -> review recent journal logs
    -> run a small authenticated smoke test
```

### Widget

```text
npm run build
    -> validate dist/widget.js and dist/widget.css
    -> increment immutable release version
    -> upload versioned S3 path
    -> upload widget/latest
    -> invalidate CloudFront
    -> test with a hard refresh and network cache disabled
```

Rollback must use the deployment rollback scripts or a previously published immutable widget version. Do not overwrite an immutable release path.

## 19. Adding a Country or Language

1. Confirm the approved policy document and language.
2. Add the market and language to configuration.
3. Add the legal-document mapping and localized widget copy.
4. Upload the source document to the correct S3 prefix.
5. Extract and inspect sections or directory records.
6. Load as `staging` with country, language, document type, and scope metadata.
7. Verify record counts and representative queries.
8. Publish the verified generation as `active`.
9. Confirm no records from another market are returned.
10. Test consent, greeting, fallback, feedback, support, and source links in that language.

Do not add country-specific retrieval rules or hardcoded question answers. Use metadata, structured fields, localized copy, and shared pipeline behavior.

## 20. Troubleshooting Guide

| Symptom | First checks |
|---|---|
| Widget shows offline | DNS target, EC2 public address/Elastic IP, Nginx, systemd status, `/health`, CloudFront cache |
| Legal documents keep loading | Widget config, market/language mapping, legal API response, browser network request, cache state |
| Answer has no source | retrieval provider, metadata filters, evidence gate, source URI, active generation |
| Correct source but malformed directory answer | structured directory fields, record type, source renderer, field completeness |
| Support says submitted but no email | SES sending status, verified sender, destination route, suppression list, journal logs, spam folder |
| Feedback missing in portal | widget feedback request, API response, database write, selected time/market/language filters |
| Widget looks old | immutable release version, `latest` upload, CloudFront invalidation, browser/service-worker cache |
| CI fails during collection | dependency lockfile and test dependencies, especially HTTP test-client packages |

## 21. Safe Change Rules

- Preserve `opensearch_section` unless a measured replacement passes the retrieval evaluation.
- Keep country policy and global directory scope filters separate.
- Avoid hardcoding countries, languages, business rules, and test answers in orchestration code.
- Make new behavior feature-flagged when it changes retrieval, caching, safety, or persistence.
- Add a regression test before changing a previously working behavior.
- Never log raw PII, credentials, tokens, or full sensitive support submissions.
- Validate configuration before restarting production services.
- Keep UAT and production widget IDs, origins, documents, and registries separate.

## 22. Ownership Handoff Checklist

The DevOps or platform team taking over should receive:

- repository and branch strategy;
- AWS account and region details through approved access procedures;
- deployment and rollback procedure;
- SSM parameter ownership;
- IAM role and least-privilege policy ownership;
- EC2/systemd/Nginx ownership;
- S3, CloudFront, DNS, and certificate ownership;
- OpenSearch collection and index ownership;
- database, cache, SES, and monitoring ownership;
- document-ingestion approval process;
- test pack and acceptance criteria;
- incident and support escalation contacts.

This guide describes the current application behavior. Before production handoff, verify every environment-specific value against the live deployment and keep secrets outside this document.
