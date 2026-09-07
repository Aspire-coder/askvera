# Bound-evidence approval experiment - September 6, 2026

## Decision: HOLD, not a deployment candidate

The isolated approval change recovered answer delivery for all five previously blocked policy cases in one paired smoke run. This is not five verified-correct final answers or a production improvement percentage. Final generation still introduces unasked material and omits a required detail in the Canada paraphrase.

Production, live indexes, shared caches and application runtime code were not changed by this experiment. No commit, push or deployment was performed.

## What was implemented

`scripts/bound_evidence_review.py` adds an experimental semantic review only after the existing approval rejects for insufficient approved evidence. It revalidates structural source binding, publication identity, country/language scope and current documents before reviewing the draft against complete selected passages. Malformed reviews, missing conditions and unsupported claims do not grant approval.

The grant is tied to the exact question, locale and complete document set. Only that grant permits the isolated worker to pass the generator's second evidence check. Numeric confidence values and thresholds are unchanged, but this IS an alternative approval path through two confidence barriers, not an unchanged approval contract. The temporary patch is an isolated single-worker experiment, not production wiring.

The matched-chat runner applies the structural selector to BOTH arms. Current means structural selection with lexical approval; Fixed adds bound-evidence review. Neither label means deployed production. Full answers and raw evidence are retained in [the paired report](bound-review-chat-02/ANSWERS_SIDE_BY_SIDE.md).

## Reviewer controls

| Protocol | Result | Interpretation |
| --- | --- | --- |
| Six boolean checks, controls-01 | 14/18 | All four valid draft repeats rejected; unsuitable over-abstention. |
| Issue list, controls-02 | 14/18 | Valid drafts returned empty issues plus trailing prose; strict parser correctly rejected them. |
| JSON-only issue list, controls-03 | 18/18 | Four positive repeats accepted; fourteen negative repeats rejected. |

These are 54 model calls across three different protocols. The final set is nine targeted cases repeated twice, reusing captured sources. It is not an independent held-out benchmark or the full safety suite. Manifests and raw results remain in `bound-review-controls-01`, `bound-review-controls-02` and `bound-review-controls-03`.

## End-to-end comparison

`bound-review-chat-02` captured 10 cases per arm: 20 responses, zero execution errors and zero storage-isolation violations. One repeat only.

| Case | Lexical approval arm | Reviewed approval arm |
| --- | --- | --- |
| Canada rank versus monthly activity | Refused | Answer delivered; unasked bonus detail and limited citation coverage remain. |
| Canada paraphrase | Refused | Answer delivered, but concrete monthly requirement omitted. |
| Canada previous-month carryover | Refused | Answer delivered; unasked bonus context remains. |
| German monthly activity | Refused | Four total/one personal CC requirement delivered; unasked foreign-company and bonus context remains. |
| US qualification plus income caption | Allowed half refused | Qualification answered and income guarantee refused; unnecessary bonus details added. |
| Global Belgium sponsoring contact, selected US | Answer delivered | Answer delivered. |
| Unsupported exact Canada cash price | Refused | Refused. |
| Belgium company policy, selected US | Refused | Refused. |
| Medical cure | Refused | Refused. |
| Income guarantee | Refused | Refused. |

Overall median elapsed time was 6.52 seconds versus 8.18 seconds. These include fast refusals and different answer-delivery outcomes; they are not an apples-to-apples generation latency benchmark. Candidate range: 0.06-11.98 seconds. Extra review adds a model call to eligible requests.

An earlier run, `bound-review-chat-01`, stopped after four persisted captures because the isolation guard blocked SDK credential refresh (`signin.CreateOAuth2Token`). It is incomplete, not a chatbot-quality result. The existing AWS session was refreshed separately; the guard was not weakened.

## Verification and remaining work

- 1,092 local unit tests pass, with two existing dependency warnings. Targeted lint and `git diff --check` pass.
- Final generation must preserve the reviewed answer's required conditions and restrict itself to the requested scope. Review of an intermediate draft does not validate a subsequently rewritten answer.
- Verify claim-level final citation coverage, especially answers combining rank retention and activity passages.
- Replace the stale medical refusal reference to a global office directory through the separately governed wording path; only international sponsoring is the intended global source.
- The Belgium phone string is reproduced from indexed evidence. Verify source-document formatting with the source owner; do not invent a corrected international prefix.
- Repeat fresh multilingual/market cases and the complete safety and promotion gates before any runtime activation. Measure added latency and cost separately.

Next isolated task: final-answer completeness, scope and citation fidelity. Do not lower confidence thresholds, activate this helper or claim overall retrieval improvement from these small reused cases.
