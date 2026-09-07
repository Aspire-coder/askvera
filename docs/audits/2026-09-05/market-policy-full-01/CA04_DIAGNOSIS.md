# CA-04: selector and approval diagnosis

Question: Does keeping my sales level mean I'm automatically active every month?

## Confirmed from the frozen Current capture

- Selector chose ranks 5, 6, 8, 4. Its explanation identifies candidate 5 as Section 4.03 and describes the monthly four-Active-Case-Credit requirement.
- The same structured response sets `directly_answers_top_rank: false` and confidence 0.65. This is inconsistent with its prose explanation describing a direct answer; the prose is not independent proof of entailment.
- The provider only accepts selector confidence when the direct-answer flag is true. Consequently 0.65 must not be reported as the effective retrieval confidence.
- Approval reports `insufficient_approved_evidence`, top score 1.25963 and no approved evidence. No generation was attempted.
- Raw 4.03 text contains monthly activity requirements near its beginning, before the 1,200-character preview boundary. Complete absence of retrieval is not the explanation supported by this capture.

## Limits

The original capture stores a prompt hash, search hits and model output, but not the actual selector input. Candidate ordering, all preview contents and coverage of the rank-retention clause cannot be independently reconstructed from the final search-hit list alone. Do not assert preview truncation caused this case, or that the selector explanation proves the answer was complete.

## Action taken

The local comparison harness now captures Converse text inputs alongside outputs. It allowlists system/message text, excluding other SDK parameters and nontext payloads. This is synthetic evaluation instrumentation, not production logging. No confidence flags are overridden, thresholds lowered, or extra model retries introduced.

The preceding local prompt changes already ask selectors to distinguish rank retention from monthly activity and select complementary clauses. Their effectiveness remains unverified by a new live run.

## Next verification

Run matched cache-bypassed Current/Candidate comparisons with this capture enabled, repeating CA-04 and its paraphrases. Inspect exact candidate text, selected IDs, structured direct-answer signal, approval, and generated claims together. Include negative controls about automatic status loss and unsupported bonus conditions. If the needed clause is absent or truncated, correct candidate coverage as a separate experiment rather than weakening approval. No deployment or index publication at this checkpoint.
