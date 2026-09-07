# Live comparison preflight - 2026-09-05

Status: AWS authentication and SSM reads verified. Matched Current/Candidate answer comparison NOT RUN.

## EC2 inspection follow-up

Read-only SSM command 926ee3f1-7c7f-4cb4-8d67-162d9cf9508b completed successfully.

- askvera service: active/running; user askvera; working directory /opt/askvera.
- Deployed revision: 7d29dad09540527a9302b95436f36e93f7fa5a2a.
- Tracked worktree status output was empty; untracked files were not inspected.
- Host memory at inspection: 912 MB total, 282 MB available; no swap.
- No psql or asm-exec executable was found on the command's PATH; this is not an
  exhaustive filesystem inventory. aws-secrets-manager-agent.service was inactive.
- Script inventory contains the existing retrieval-only evaluators and the response
  capture script already reviewed. It does not establish an isolated answer harness.
- Do not start a second full chatbot process on this small production host without
  measured resource headroom and isolation. Do not run migration/backfill/cleanup
  scripts as evaluation setup, or invoke the existing direct secret-fetch startup.
- The proposed EC2 route has not resolved secure credential access. Prefer the
  local test runtime plus a supported read-only metadata access path. No model
  invocations or database queries were performed by this EC2 inspection.

## Follow-up: tunnel verified, credential-wrapper incompatibility found

- Installed official Amazon-signed Session Manager plugin 1.2.835.0 successfully.
- Existing instance is Online with SSM agent 3.3.4624.0.
- Temporary remote-host tunnel bound to 127.0.0.1:15432; PostgreSQL accepted an
  SSL negotiation probe. No database authentication or query occurred.
- Approved asm-exec runtime reference failed to resolve the RDS credential.
- Isolated nonsecret diagnostics verified signing credentials are available and
  AWS MCP initialization succeeds. Tool discovery does not expose aws___call_aws,
  the tool hardcoded in the installed wrapper; it exposes aws___run_script instead.
- This is an identified wrapper/API compatibility gap, not evidence that the
  database credential is invalid or that Secrets Manager permission is denied.
- No direct secret retrieval fallback was attempted. The wrapper needs a supported
  compatible release/backend before this credential-dependent snapshot can proceed.
- Full answer comparison remains NOT RUN; no quality improvement is claimed.

## Verified configuration (SSM, not process-level attestation)

- Profile: askvera-review; account 615592621509; IAM user pavan410.
- Region: us-east-1.
- Retrieval provider: opensearch_section.
- OpenSearch index: askvera-policy-sections.
- Configured chat model: us.anthropic.claude-sonnet-4-5-20250929-v1:0.
- Model routing mode: shadow. Actual per-request model selection still needs traces.
- SSM prompt version: 2026-07-17.1; local default: 2026-09-05-context-boundaries-v2.
  PROMPT_VERSION is not in the code-owned SSM exclusion list. A normal SSM load
  can override the local version label. This alone does not establish which prompt
  text the production process uses.
- KB version label: 2026-07-30-policy-refresh. This is not a corpus hash.
- Active generation pointer enabled: true.

## Isolation findings

- No AWS MCP tools were exposed; read-only AWS CLI fallback was used.
- Parameter metadata and ten explicitly allowlisted nonsecret values were read;
  no SecureString values were decrypted and no Secrets Manager values were read.
- A TCP connection to the configured RDS host on port 5432 did not complete
  within five seconds. This is a connectivity observation, not proof of its cause.
- Retrieval publication checks require knowledge_active_generations from RDS.
  Do not disable them or substitute all indexed documents for an active snapshot.
- services/db.py initializes its connection through direct secret retrieval.
  Do not execute that path for this agent-run test; use the approved asm-exec
  runtime-reference mechanism for any necessary credentials.
- scripts/fill_bot_actual_responses.py automatically records consent using a
  fixed version. It is not suitable unchanged for this production comparison.
- Normal app startup is not an isolated harness: database, cache and audit
  integrations must be controlled before use.

## Next required work

1. Establish an approved SSM port-forwarding session through the existing instance,
   or another authorized private-network path. Do not open RDS publicly.
2. Read only the publication metadata needed for an immutable local source snapshot,
   using a read-only database transaction and runtime-resolved credentials.
3. Build a bounded local answer harness with local session state, disabled shared
   writes and isolated cache. Preserve retrieval/publication/output safeguards.
4. Freeze deployed revision, actual source generations, source hashes, settings and
   model selection. Distinguish local-code Current from live production Current.
5. Capture each question and both full answers, citations and timings. Repeat the
   small controlled set before interpreting differences. Do not claim improvement
   percentages from this preflight or from local unit tests.

No deployment, cloud configuration mutation, production cache clear, commit or push
was performed during this preflight. CLI login created the separately approved
short-lived local profile in the preceding step.
