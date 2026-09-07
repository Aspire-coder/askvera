# Cleanup recheck - HOLD

## Scope

Thirty new synthetic Fixed captures (10 questions, three repeats). Current is reused from matched-full-01, not a concurrent control. Final citation/decimal/abbreviation cleanup is included in this Fixed code hash. Confidence thresholds and safety settings were not changed. No deployment or shared cache/storage writes were performed.

The recorder now stores generation-time evidence, in source order with enriched metadata, before generation. Refused answers therefore retain evidence even when response metadata drops it. This recording change does not alter the chatbot's answer path.

## Observed failures

- UK joining: first two repeats still infer no joining/upfront fee from no minimum capital investment. All three omit a consistent complete alternative/opt-in pathway. Not a correctness pass.
- Rank qualification: all three retain the qualification sentence, but all three add unasked benefits.
- Split intent: repeat 1 refuses the supported qualification half; repeat 2 answers narrowly and declines the income request; repeat 3 answers but adds unasked benefits. Not a stable pass.
- Discount-only: repeats 1 and 3 stay within scope; repeat 2 adds the unasked upgrade path.
- Medical refusal still mentions the obsolete global office directory. Wording cleanup remains open.

## Replay and tests

The new offline replay uses exact generation inputs when available, or recorded approved IDs matched to captured hits in order for older runs. Missing/ambiguous evidence is skipped, never replaced with all retrieved hits.

- Older joining-evidence-07: 17 replayed, 13 skipped for unavailable approved evidence.
- This run: all 18 generated answers replayable; 12 pre-generation responses have no generation evidence and are skipped.
- Replay covers citation cleanup and numeric sentence repair only, not the whole orchestrator or semantic correctness. In split repeat 1, removing one unsupported sentence changes the context for another numeric claim, so repair still leaves an unsupported claim and full validation refuses. Do not loosen validation to hide this.
- Full unit suite: 887 passed. Two dependency deprecations and a non-failing pytest cache permission warning. Initial sandbox run had fixture setup permission errors; rerun outside sandbox completed successfully.
- Focused tests: 57 passed. New replay helper/tests lint passed. Graphify unavailable.

## Next implementation boundary

Keep these failures frozen. Fix evidence completeness and generation scope as separate candidates; do not globally lower confidence or blindly trim after the first sentence. Preserve mandatory conditions and permitted split-intent answers. The joining and scope issues are unresolved, so there is no promotion or release-readiness claim.

Full questions, both code-profile answers, citations and timings are in ANSWERS_SIDE_BY_SIDE.md and its CSV. SELECTED_EVIDENCE_REPLAY.json contains raw generation and intermediate cleanup outputs; it is not a quality scorecard.
