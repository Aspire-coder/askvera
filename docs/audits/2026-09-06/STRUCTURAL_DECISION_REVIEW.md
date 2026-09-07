# Structural evidence decision candidate

September 6, 2026. Local opt-in experiment only. No deployment, live-provider wiring, index publication, shared-cache clearing, threshold changes, commit or push.

## Implemented

- `app/retrieval/evidence_decision.py` accepts one support-only contract. Citations are derived from validated quotes, not an independent model-generated source list. Multiple valid quotes from one source retain their text while sharing a citation identity.
- Supported decisions must have a nonempty draft, valid bound evidence, no missing required facts, and finite numeric confidence in [0, 1]. No confidence threshold is lowered. Boolean, nonnumeric and nonfinite confidence values are rejected.
- Abstention must have an empty draft/support and named missing facts. A proposed ANSWER_NO with missing required facts is rejected, never converted into a supported answer.
- The isolated adapter resolves short source aliases to full content/version-bound identities before validation. It orders only validated, selected quotes. It never adds an omitted source or moves an incorrect quote to another source.
- Governing order uses the quoted text, not merely the parent section. A benefit quote does not inherit authority from a different sentence elsewhere in its source. Existing conservative English activity-rule detection is reused; unsupported languages and intent families preserve order.
- The pure validator and ordering helper do not read expected-answer labels. Evaluation labels remain outside the decision path. Raw model output and normalized decisions are separately captured, with helper hashes in the manifest.

## Test scope

14 captured-evidence cases: ten existing exploratory cases/controls and four fresh wordings declared before invocation. New questions cover activity carryover, monthly qualification, unsupported CC-to-currency conversion and automatic closure versus voluntary termination. Sources remain captured Canada evidence, not a fresh retrieval run or independent multi-market benchmark.

The smoke comparison passed 14/14 structural checks versus 12/14 for the earlier compact combination. Manual review identified parent-section versus quoted-rule ordering, which was corrected before the repeated comparison. The smoke artifacts remain unchanged and contain the earlier helper hash.

## Verification

The repeated comparison completed all **84 calls**, with **42/42** structural decision/evidence checks versus **36/42** for the earlier compact combination. This comparator is an experimental candidate, not production Current. The original Canada question and fresh activity-carryover question each improved from 0/3 to 3/3. All eight missing-evidence/negative controls passed all three repeats (24/24) on both sides. No execution errors occurred.

Manual review of all three original-question drafts found the monthly requirement and the matching governing quote. One draft shortened the Home Operating Company qualification; complete customer-facing scope wording still needs validation. All three remained ANSWER_NO, not a forced conversion from a false support flag.

This turn used **112 selector calls** (28 smoke plus 84 repeated), 471,871 recorded tokens and zero cache-read tokens. Cumulative checkpoint total is **388 selector calls; zero additional end-to-end chatbot calls**. This is a repeatable local selector result, not a demonstrated production improvement. The candidate changes both output contract and deterministic normalization relative to the comparator; no single-factor attribution is claimed.

1,033 unit tests passed; targeted changed-file lint passed. Two existing dependency deprecation warnings remain. Graphify is not installed/on PATH and no graph exists; generated wiki files were not edited. Extensive unrelated existing changes were preserved.

## Promotion limits

Text membership and correct source ordering do not prove every generated claim. Drafts are selector outputs, not final chatbot answers. The German control can pass evidence checks while its draft is English; language quality is not certified by this metric. The generic Active question can include foreign-company conditions, so scope and concision still require final-answer review.

Live integration must supply actual published source-generation metadata and enforce country/global sponsoring authorization upstream. Captured snapshot identities are not live document-generation IDs. Broad multilingual support, end-to-end latency, final safety and all-market quality remain unverified for this candidate. Do not deploy based on this component score.

## Artifacts

- [Smoke questions and raw outputs](structural-smoke-01/COMPARISON.md)
- [Repeated questions, raw outputs and scores](structural-repeated-01/COMPARISON.md). Each JSON capture additionally includes the validated, ordered decision; the manifest records source registries and hashes.

## Next

The structural candidate is ready for an isolated end-to-end integration review, not deployment. Supply actual source-generation metadata, connect validated decisions to the existing final-answer pipeline without bypassing safety or authorization, and compare full final answers with production Current across the broader market suite. Keep language, answer completeness, citations, safety and latency as separate gates.
