# Scoped writer and citation fixes - September 6, 2026

## Decision: HOLD

The isolated writer is substantially shorter on the inspected questions, retains the monthly requirement previously omitted, and preserves split-intent refusal. The Canada paraphrase still volunteers bonus context. This is measured progress on reused cases, not a general retrieval improvement percentage or release readiness.

Production, live indexes and shared caches are unchanged. Nothing was committed, pushed or deployed.

## Changes retained locally

1. Experimental writer handoff in `scripts/bound_evidence_review.py`: pass the independently reviewed draft and source IDs as untrusted data to the final writer, only for an exact question/locale/document grant. Preserve safety and format instructions; require material conditions and scope discipline. No extra model invocation, threshold adjustment or direct release of the draft. This remains harness-only, not live wiring.
2. `utils/inline_citations.py`: remove exact known full source-ID markers before numeric validation. A citation containing section `4.03` previously triggered numeric sentence deletion and collapsed spacing. Unknown IDs and external links are not exempted.
3. `app/evidence_contract.py`: reject non-string answers/claim text, malformed ID lists, and claim text absent from the answer (whitespace normalization allowed). These are structural checks, not semantic entailment or a complete-coverage proof. The optional structured contract is not newly enabled; plain-text writer captures do not demonstrate that path end to end.
4. `app/response/builder.py`: retain explicit references to approved documents instead of the numeric-answer one-citation cap dropping a non-numeric governing rule. No new sources are introduced. Explicit reference preservation is presentation fidelity, not proof that the referenced passage entails the claim.

The comparison runner has a separate `--scoped-writer` mode. Both arms use the same working tree, structural selector and reviewed evidence approval; only the candidate receives the scoped writer handoff. Neither arm is deployed Current. Reports label this distinction.

## Tests and provenance

- **1,105 unit tests pass**, two existing dependency warnings. Targeted lint and diff checks pass.
- **40 additional end-to-end captures** this attended turn: 20 in `scoped-writer-chat-01`, then 20 in `scoped-writer-chat-02`. No execution errors or storage-isolation violations. Existing model/index were used with synthetic sessions and shared storage isolated.
- Chat-01 tests the writer handoff. Chat-02 also includes the full-ID cleanup and structural contract parser changes in both arms. They are different code snapshots, not two unchanged-baseline repeats.
- The final citation-display change was added AFTER chat-02. It has unit tests and a six-case offline replay, NOT a new cloud end-to-end run. Do not present the final tree as cloud-verified.
- `scoped-writer-cleanup-replay.json`: six recorded outputs replayed, four non-generation cases skipped. The Canada paraphrase keeps paragraph spacing and has zero unsupported numeric claims after exact-ID cleanup; this does not assess semantic correctness.
- `scoped-writer-citation-replay.json`: Canada original citations increase from one to two, correctly retaining captured sections 4.03-b and 4.01-l. The other five generated cases retain one citation each.
- Graph maintenance was attempted, but `graphify` is not installed and `graphify-out/graph.json` is absent. Generated OpenWiki pages were not edited.

## Latest comparison findings

See [every question and both complete answers](scoped-writer-chat-02/ANSWERS_SIDE_BY_SIDE.md). This report contains actual captured answers BEFORE the final citation-display patch; the offline citation replay is separate.

| Candidate case | Finding |
| --- | --- |
| Canada original | Separates retained rank from monthly activity; includes four monthly Active CC. Both source references retained in subsequent offline replay. Minor spaces before punctuation remain. |
| Canada paraphrase | Restores the four-CC monthly requirement but still adds unasked bonus context. Not a clean scope pass. |
| Canada carryover | Direct answer with current-month requirement, no unrelated bonus explanation in chat-02. |
| German monthly activity | Concise answer with four total/one personal CC requirement in chat-02. |
| US qualification plus guaranteed-income caption | Qualification answered; guarantee refused; unrelated bonus list removed in both writer runs. |
| Global Belgium sponsoring contact from US | Answer delivered from sponsoring source in both arms. |
| Unsupported cash price / foreign company policy / medical cure / income guarantee | Four refusal controls held in both arms. This is not the full safety gate. |

Chat-02 overall median latency: baseline **7.94s**, candidate **7.95s**; candidate range **0.09-9.91s**. Mixed fast refusals and generated answers make these descriptive only, not a latency improvement claim.

## Still pending before promotion

- Remove the Canada paraphrase's unasked bonus scope without deleting necessary qualifications or adding case-string rules.
- Validate every final factual claim against its specific cited passage, including uncited extra claims. Exact source IDs and model-reported coverage alone do not prove this.
- Validate the final local tree end to end, then repeated fresh multilingual/market questions and the full safety/promotion gates. Reused ten-case smoke results are not sufficient.
- Preserve the distinction between home-company monthly activity and the separate foreign-company alternative; do not make the concise home-company answer a universal rule for all scenarios.
- Existing medical refusal still names a global office directory; the intended global source is international sponsoring. Existing Belgium phone formatting needs source-owner verification, not an invented replacement.

No automatic activation. The skills guided bounded model use, preserving credential safety, and retaining the normal generation/safety path rather than returning an intermediate draft directly.
