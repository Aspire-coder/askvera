# Retrieval Profile Control

## Purpose

The Operations portal can safely turn isolated retrieval comparison on or off without deploying code. This first release intentionally supports only two modes:

- **Current only**: the established retrieval and parsing profile serves customer answers. No candidate lookup runs.
- **Shadow comparison**: Current still serves every customer answer. A configurable sample of requests is also evaluated against the isolated candidate index in the background. Only privacy-safe comparison telemetry is stored.

There is no portal option that allows the candidate to serve customers.

## Safety boundaries

- The candidate provider must be `opensearch_section`.
- The candidate index must be configured, exist in OpenSearch, and differ from the Current index.
- Only a Super Admin can change mode.
- Every change requires a reason and an exact confirmation phrase.
- Every change is recorded in the administrator audit log with pipeline and index identifiers.
- Shadow work is asynchronous and exceptions cannot fail or replace the Current response.
- If runtime-control storage is unavailable, retrieval falls back to the deployment configuration.
- Question text and document content are not written to the control audit event.

## Parsing is separate

The switch does not upload, parse, rechunk, re-embed, publish, roll back or delete documents. The portal displays both chunk profiles and index names so administrators can verify which prepared corpus each retrieval profile uses.

Building or refreshing a candidate parsing profile remains an ingestion and indexing operation. It must complete before Shadow can be enabled.

## Data and API

Migration `20260825_01_retrieval_runtime_control.sql` creates the singleton control record.

- `GET /api/admin/operations/retrieval-profile` returns the active control, Current profile, candidate readiness and parsing profiles.
- `PUT /api/admin/operations/retrieval-profile` changes Current/Shadow mode for a Super Admin.

Confirmation phrases:

- `ENABLE SHADOW`
- `USE CURRENT`

Shadow sample rates offered by the portal are 5%, 10%, 25% and 100%.

## Rollback

Select **Current only**, provide the reason, type `USE CURRENT`, and apply the mode. The API writes the control immediately; application processes refresh it within five seconds. No deployment or index mutation is required.

## Promotion boundary

Shadow results must be evaluated with the frozen retrieval and response-quality gates. Adding a future Candidate/Canary serving mode requires a separate reviewed implementation, rollback contract and release approval. It is not part of this control.

