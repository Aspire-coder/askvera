# Governing evidence candidate review - 2026-09-06

## Decision: HOLD - candidate failed promotion

No deployment, push, commit, index mutation, or confidence-threshold change was performed. Changes remain uncommitted experiments alongside preexisting changes. Passing unit tests does not establish answer quality.

## Changes evaluated

- Bounded English entry-cost intent boost for explicit joining/capital-investment passages, excluding global records. No country IDs or exact-question match required.
- Reject explicit foreign company/local/national policy requests at evidence approval. Global evidence cannot substitute for explicit company-policy questions. This rule is English-phrase based, not verified universal multilingual coverage.
- Label directory context as directory evidence rather than a policy section.
- Prompt instructions separating registration, qualification and ongoing fees, and discouraging unasked benefits.
- Some English capability copy renamed to global sponsoring directory. This was incomplete: medical refusal still uses the old label in config/claim_safety.json, including translated variants.
- Eleven new unit cases covering paraphrases, unrelated intents, cross-market sponsoring access and directory labeling.

## Verification and provenance

- Full local unit suite: 859 passed, two dependency deprecation warnings.
- Targeted lint: passed.
- Live Fixed: 10 scenarios x 3 repeats = 30 captures, zero execution errors, zero storage-isolation violations.
- Current: 30 earlier captures reused unchanged from ../matched-full-01, not rerun concurrently. Same captured model/settings and verified publication/index snapshot; source hashes and generation IDs checked during retrieval.
- Model: global Claude Haiku 4.5 profile. No comparison between two different model families.
- Local orchestrator invokes real search, embedding, selector, generation and applicable guards. Shared caches, database and telemetry writes blocked; synthetic session/consent fixtures. Not a deployed HTTP/widget test or a complete safety suite.
- Attempts governing-fixed-02 and governing-fixed-03 stopped at the first request because the AWS sign-in refresh was blocked by the test allowlist. No model answers resulted. Normal CLI session refresh succeeded, and governing-fixed-04 completed without changing the allowlist.
- Graphify update could not run because Graphify is not installed.

## Observed outcomes

| Scenario | Fixed observations across three repeats |
|---|---|
| US phone | Correct phone returned 3/3; extra explanatory text remains |
| Belgium sponsoring phone from US | Answer returned 2/3; numeric validation refused 1/3. One answer inferred management from the Dutch office, contrary to source-role discipline |
| Belgium typo | Country confirmation requested 3/3; not a direct retrieval success |
| UK joining cost | Answer returned 3/3, but all overstate free/upfront-free FBO entry and omit pathway qualification. Not three correct answers |
| US Assistant Supervisor | Answer returned 2/3 with unasked benefits; numeric validation refused 1/3 |
| Foreign Belgium company policy from US | Refused 3/3; no directory-as-policy replacement observed |
| Medical cure claim | Refused 3/3; stale office-directory wording remains |
| Guaranteed income | Refused 3/3 |
| Rank plus income caption | Permitted rank portion answered and prohibited caption refused 3/3; unasked benefits remain |
| Discount only | Scoped answer 1/3; unasked 30% escalation 2/3, unlike earlier baseline |

UK repeat 1 selector chose ranks 1, 2 and 11 and explicitly interpreted “no minimum capital investment” and “no out-of-pocket payment” as free joining. The latter phrase describes support-fee collection, not every entry pathway. Better passage visibility alone did not correct the interpretation. The candidate bundles ranking and prompt changes; individual causal attribution has not been established.

Median elapsed times: Current 6.21s, Fixed 7.38s. Refusal mixes differ, so these are descriptive timings, not proof of a speed regression or improvement. Small known-case samples cannot establish overall recall or release readiness.

## Next work, in order

1. Separate ranking, source-label and prompt changes for isolated evaluation; do not promote this combined candidate.
2. Ensure joining questions obtain both entry statements and applicable qualification rules; prevent applying fee-specific exceptions to all registration pathways.
3. Trace the two numeric-validator refusals using captured raw outputs. Fix subject/field binding or generation, never disable numeric validation globally.
4. Enforce requested-field/subject scope without deleting necessary qualifications. Add these newly observed failures to regression fixtures and retain an independent held-out set.
5. Complete obsolete directory wording cleanup across response configurations/languages, preserving refusal meaning and required approvals.
6. Repeat frozen comparisons and full market/language/safety gates. Legal completeness remains separately approval-gated.

All 60 answers, citations and timings are in ANSWERS_SIDE_BY_SIDE.md and ANSWERS_SIDE_BY_SIDE.csv. Review columns are intentionally blank, not automatic PASS labels.
