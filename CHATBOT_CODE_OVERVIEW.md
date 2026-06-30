# ASK Vera Chatbot Code Overview

This document describes the current chatbot application code in the `chatbot python` project. It is intended as a clear handoff/reference for the backend API, AWS integrations, storage, safety flow, and reusable frontend widget wrapper.

## Project Location

```text
C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\chatbot python
```

## High-Level Architecture

```text
Website / Widget
  |
  | HTTP API
  v
FastAPI backend
  |
  |-- Config from local defaults + SSM Parameter Store
  |-- RDS PostgreSQL for sessions and consent
  |-- ElastiCache Valkey/Redis for response cache
  |-- Bedrock Knowledge Base for RAG answers
  |-- Bedrock Guardrail for generated response safety
  |-- Amazon Comprehend for PII masking
  |-- Kinesis Firehose for audit events
  |-- SQS for feedback review workflow
```

## Current AWS Values

| Area | Setting | Current Value |
| --- | --- | --- |
| Region | `AWS_REGION` | `us-east-1` |
| RDS | `RDS_DB_IDENTIFIER` | `database-1` |
| RDS | `RDS_SECRET_ARN` | `arn:aws:secretsmanager:us-east-1:615592621509:secret:rds!db-617fcf32-1ae3-4f45-b803-4378b966fcf6-0xz7wN` |
| Redis / Valkey | `REDIS_HOST` | `master.askverachat-cache.iivrdz.use1.cache.amazonaws.com` |
| Redis / Valkey | `REDIS_PORT` | `6379` |
| Redis / Valkey | `REDIS_USER` | `askverachat-app-user` |
| Bedrock KB | `BEDROCK_KB_ID` | `P482AUAHKM` |
| Bedrock KB | `BEDROCK_DATA_SOURCE_ID` | `JSAC3THB67` |
| Bedrock Model | `BEDROCK_MODEL_ARN` | `arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6` |
| Bedrock Guardrail | `BEDROCK_GUARDRAIL_ID` | `idy33rbs9v1i` |
| Bedrock Guardrail | `BEDROCK_GUARDRAIL_VERSION` | `DRAFT` |
| S3 | `S3_BUCKET` | `askverachat-prod-kb` |
| Firehose | `FIREHOSE_STREAM_NAME` | `vera-audit-stream` |
| SQS | `SQS_FEEDBACK_QUEUE_URL` | `https://sqs.us-east-1.amazonaws.com/615592621509/askverachat-feedback` |
| CORS | `ALLOWED_ORIGINS` | `https://chat.vera-api.xyz`, `https://vera-api.xyz`, local demo origins |

## Runtime Startup Flow

Defined in `main.py`.

1. Configure structured logging.
2. Load config overrides from SSM Parameter Store.
3. Validate required config values.
4. Register SIGTERM handler for graceful EC2 shutdown.
5. Initialize reusable AWS clients.
6. Initialize PostgreSQL and create required tables if missing.
7. Initialize Redis/Valkey cache using IAM auth.
8. Mount FastAPI routes and middleware.

Relevant file:

```text
main.py
```

## Configuration Layer

### `config/settings.py`

Holds local/default deploy-time values and SSM loading logic.

Important behavior:

- Defaults are usable for local/dev reference.
- Production can override values from SSM path `/askverachat/prod/`.
- `load_ssm_config()` loads all parameters under that path with decryption enabled.
- `get(key)` returns a config value or raises a clear error.
- SSM strings are coerced into existing setting types when possible.

Expected SSM path:

```text
/askverachat/prod/
```

Important SSM keys:

```text
AWS_REGION
RDS_SECRET_ARN
REDIS_HOST
REDIS_PORT
REDIS_USER
BEDROCK_KB_ID
BEDROCK_DATA_SOURCE_ID / BEDROCK_DATASOURCE_ID
BEDROCK_MODEL_ARN
BEDROCK_GUARDRAIL_ID
BEDROCK_GUARDRAIL_VERSION
FIREHOSE_STREAM_NAME
SQS_FEEDBACK_QUEUE_URL
S3_BUCKET
ALLOWED_ORIGINS
```

### `config/__init__.py`

Exports compatibility helpers:

```python
from config import load_config, get
```

These map to `settings.load_ssm_config()` and `settings.get()`.

### `scripts/validate_config.py`

Validates required startup values:

```text
AWS_REGION
RDS_SECRET_ARN
```

Current validation passes.

## API Layer

### `api/routes.py`

Defines the HTTP API.

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/chat` | `POST` | Main RAG chat endpoint |
| `/api/config` | `GET` | Returns country/language config and privacy version |
| `/api/privacy` | `GET` | Returns privacy notice HTML |
| `/api/consent` | `POST` | Records consent to PostgreSQL |
| `/api/feedback` | `POST` | Sends feedback to SQS |
| `/health` | `GET` | Fast health check without AWS calls |

### `/api/chat` Flow

```text
1. Read correlation ID
2. Run local guardrail pre-check
3. Scrub user input with Comprehend PII detection
4. Build Redis cache key
5. Return cached result if found
6. Load session history from PostgreSQL
7. Call Bedrock Knowledge Base RetrieveAndGenerate
8. Scrub generated response with Comprehend
9. Run local guardrail post-check
10. Append chat turn to PostgreSQL
11. Write audit event to Firehose
12. Cache response in Redis
13. Return standard response envelope
```

### `api/middleware.py`

Adds a correlation ID to every request and response.

Behavior:

- Reads `x-correlation-id` header if supplied.
- Generates a UUID when no header exists.
- Stores it on `request.state.correlation_id`.
- Adds it to the response header.
- Logs request method, path, status, and duration.

## Request And Response Models

Defined in `utils/validators.py`.

### Standard Envelope

All main API responses use:

```text
success
data
error
correlationId
timestamp
```

### Chat Request

```text
message
sessionId
country
language
role
```

### Consent Request

```text
sessionId
country
lang
timestamp
version
```

### Feedback Request

```text
sessionId
messageId
rating
comment
```

## AWS Client Container

### `services/aws_clients.py`

Creates boto3 clients once using the EC2 instance role.

Clients:

```text
bedrock-agent-runtime
bedrock-runtime
comprehend
firehose
secretsmanager
sqs
```

No access keys are stored in code.

## Database Layer

### `services/db.py`

Uses Secrets Manager to fetch the RDS PostgreSQL credentials from `RDS_SECRET_ARN`.

Builds a SQLAlchemy engine:

```text
postgresql+psycopg://username:password@host:port/dbname
```

Connection options:

```text
pool_size = 5
max_overflow = 10
pool_pre_ping = True
```

Creates tables if they do not exist.

### PostgreSQL Tables

#### `chat_sessions`

```sql
session_id TEXT PRIMARY KEY
messages JSONB NOT NULL DEFAULT '[]'::jsonb
expires_at TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

#### `consent_log`

```sql
id BIGSERIAL PRIMARY KEY
session_id TEXT NOT NULL
country TEXT NOT NULL
lang TEXT NOT NULL
accepted_at TIMESTAMPTZ NOT NULL
version TEXT NOT NULL
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `services/session.py`

Handles chat session history.

Functions:

```text
get_session_history()
append_session_turn()
```

Session behavior:

- Stores the latest turns in PostgreSQL.
- Keeps the last 10 message entries.
- Uses `SESSION_TTL_SECONDS = 7200`.

### `services/consent.py`

Writes user privacy consent events to `consent_log`.

## Redis / Valkey Cache

### `services/cache.py`

Uses ElastiCache Valkey/Redis over TLS with IAM authentication.

Current config:

```text
REDIS_HOST = master.askverachat-cache.iivrdz.use1.cache.amazonaws.com
REDIS_PORT = 6379
REDIS_USER = askverachat-app-user
TLS = true
```

Important behavior:

- `RedisIamCredentialProvider` generates a fresh IAM token for new Redis connections.
- Token signing uses SigV4 for the `elasticache` service.
- Response cache key includes message, country, language, and role.
- Cached values are JSON.
- Cache TTL is `CACHE_TTL_SECONDS = 7200`.

Functions:

```text
generate_iam_auth_token()
init_cache()
build_cache_key()
get_cache_value()
set_cache_value()
```

## Bedrock Knowledge Base

### `services/bedrock.py`

Calls Bedrock `retrieve_and_generate`.

Current KB config:

```text
Knowledge Base ID: P482AUAHKM
Data Source ID: JSAC3THB67
Model ARN: arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6
Guardrail ID: idy33rbs9v1i
Guardrail version: DRAFT
```

Metadata filter now matches the uploaded `.metadata.json` sidecar files:

```json
{
  "andAll": [
    { "equals": { "key": "country_code", "value": "<country>" } },
    { "equals": { "key": "language", "value": "<language>" } },
    { "equals": { "key": "status", "value": "active" } }
  ]
}
```

Generation config:

- Uses custom prompt template from `config/vera_persona.py`.
- Applies Bedrock guardrail config.
- Requests 5 hybrid search results.
- Extracts citations from retrieved references.

Current confidence behavior:

```text
0.85 if sources exist
0.4 if no sources exist
```

This is marked as a future improvement because it is not yet using a real reranker score.

## Safety And Compliance

### `services/pii.py`

Uses Amazon Comprehend `detect_pii_entities`.

Behavior:

- Scrubs user input before Bedrock.
- Scrubs model output before returning to user.
- Replaces detected entities with labels like `[EMAIL]` or `[PHONE]`.
- Limits Comprehend input to 5000 characters.

### `services/guardrails.py`

Local rule-based guardrail before and after generation.

Checks:

```text
income_claim
medical_claim
off_topic
```

Rules are defined in:

```text
config/guardrail_topics.py
```

### `config/vera_persona.py`

Defines:

- System prompt template.
- Role-specific content scope.
- Fallback responses for low confidence, blocked content, and Bedrock errors.

## Audit And Feedback

### `services/audit.py`

Writes audit events to Firehose.

Current stream:

```text
vera-audit-stream
```

Payload includes:

```text
timestamp
correlationId
event fields
```

### `services/feedback.py`

Sends feedback to SQS.

Current queue:

```text
https://sqs.us-east-1.amazonaws.com/615592621509/askverachat-feedback
```

Payload includes:

```text
correlationId
sessionId
messageId
rating
comment
```

## Error Handling

Defined in `utils/exceptions.py`.

Stable error types:

| Exception | Error Code | HTTP Status |
| --- | --- | --- |
| `ConfigurationError` | `CONFIGURATION_ERROR` | `500` |
| `BedrockTimeoutError` | `BEDROCK_TIMEOUT` | `504` |
| `BedrockServiceError` | `BEDROCK_ERROR` | `502` |
| `CacheConnectionError` | `CACHE_CONNECTION_ERROR` | `503` |
| `GuardrailBlockedError` | `GUARDRAIL_BLOCKED` | `400` |
| `LowConfidenceError` | `LOW_CONFIDENCE` | `200` |
| `AwsServiceError` | `AWS_SERVICE_ERROR` | `502` |

## Logging

Defined in:

```text
utils/logging.py
```

The app uses structured logs with correlation IDs across API, service, and AWS call paths.

## Frontend Widget Wrapper

Location:

```text
widget-wrapper/
```

This is a reusable React + TypeScript widget shell. It is intentionally generic and can wrap:

- Chatwoot
- iframe widgets
- third-party script widgets
- custom React chat apps
- plain message feeds

### Main Export

```text
GenericWidgetWrapper
```

Defined in:

```text
widget-wrapper/src/generic-widget/GenericWidgetWrapper.tsx
```

### Widget Features

- Floating launcher.
- Header with menu and close actions.
- Country/language selector.
- Consent panel.
- Legal links.
- Success confirmation banner.
- Suggested topic pills.
- Message feed.
- Loading state.
- Composer.
- Child slot for any provider/widget.
- Callback hooks for open, close, consent, locale changes, message send, escalation, and new chat.

### Widget Config

Defined in:

```text
widget-wrapper/src/generic-widget/types.ts
```

Important config sections:

```text
brandName
welcomeText
loadingText
successText
provider
labels
menu
consent
policyLinks
countries
languages
starterTopics
contextualTopics
theme
```

### Chatwoot Adapter

Defined in:

```text
widget-wrapper/src/generic-widget/integrations/ChatwootWidgetAdapter.tsx
```

Behavior:

- Loads the Chatwoot SDK script.
- Accepts `baseUrl` and `websiteToken`.
- Can hide Chatwoot's default bubble.
- Opens/closes Chatwoot when wrapper opens/closes.
- Passes wrapper context to Chatwoot custom attributes:
  - visitor ID
  - session ID
  - selected country
  - selected language
  - consent status

### Local Demo

Location:

```text
widget-wrapper/demo/
```

Run with:

```bash
cd "chatbot python/widget-wrapper"
npm run demo
```

Current local demo:

- Uses Forever-style black/white/yellow visual direction.
- Shows country/language selector.
- Requires privacy acceptance before chat unlocks.
- Uses simulated local provider until real Chatwoot values are provided.

## Tests

Current test files:

```text
tests/unit/test_bedrock.py
tests/unit/test_cache.py
tests/unit/test_guardrails.py
tests/unit/test_pii.py
tests/integration/test_chat_flow.py
```

Current lightweight checks that have passed:

```bash
python scripts/validate_config.py
python -m compileall config services main.py
npm run build:demo
```

Full `pytest` execution still depends on installing project test dependencies in the active environment.

## Generated / Support Artifacts

These are project artifacts, not main application code:

```text
output/pdf/
graphify-out/
tmp/
__pycache__/
```

They should be reviewed before final handoff or commit.

## Current Pending Items

The current tracking file is:

```text
PENDING_ITEMS.md
```

Important remaining items:

- Publish Bedrock guardrail version when ready instead of using `DRAFT`.
- Decide local/offline startup mode.
- Move privacy copy out of the hardcoded API route.
- Confirm Comprehend permissions.
- Improve confidence scoring with real retrieval/reranker metadata.
- Decide wrapper deployment path and final Chatwoot values.
