# Structured claim-review experiment - 2026-09-06

Status: HOLD for runtime activation. Production unchanged. No deployment, index mutation, cache reset or threshold change.

## Implemented

Added opt-in `--structured-output` (requires `--per-claim`) to the isolated reviewer. The Bedrock Converse request now optionally supplies a stable JSON schema through `outputConfig.textFormat`. Prompt, token budget (768), source text and semantic acceptance checks remain unchanged for the original seven controls. No repair retries or permissive extraction were added. SDK failures propagate; incomplete responses and invalid local judgments fail closed.

The schema requires typed claim judgments and completeness/safety flags, disallows additional fields, and retains local cardinality, index-order and nonempty-reason validation. This is format enforcement, not proof that a judgment is correct. Capture records now include output configuration and elapsed time; manifests include script hashes.

Reference verified for this implementation: [AWS structured output documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html). The schema uses its supported subset. The existing request uses plain text passages, not Anthropic's native citation feature. No SDK dependency upgrade was necessary.

## Measurements

| Run | Evaluations | Actual model calls | Format failures | Result |
| --- | --- | --- | --- | --- |
| structured-claim-controls-01 | 14 | 12 | 0 | 14/14 expected outcomes, including two deterministic source rejections |
| structured-claim-extended-01 | 16 | 16 | 0 | 12/14 valid scored outcomes; two mislabeled fixture rows excluded |

Both runs repeated each case twice. Total actual calls: 28, plus two local binding checks in the first run. The extended run was expected to make 14 calls plus two binding checks, but the defective negative fixture bound successfully and reached the model twice. Those calls are included in the actual count, not hidden or described as local checks.

The first run preserved the original distinction: unasked bonus details rejected twice, explicitly requested bonus details accepted twice. All earlier complete-answer, contradiction, omitted-condition and income-guarantee controls passed.

Expanded controls used captured Canadian and German policy passages:

- Medical claim without medical support: rejected twice.
- Necessary current-month qualification: accepted twice.
- Complete German activity rule: accepted twice.
- German rule missing the personal-credit condition: rejected twice.
- German rule with an altered quantity: rejected twice.
- English answer/question grounded in the German rule: accepted twice.
- One claim combining monthly activity and unasked bonus detail: incorrectly accepted twice.

The last item remains a material semantic failure. Grouping two facts into one input claim changes the review outcome even though the visible answer is the same as the separately segmented control. A strict JSON format does not solve this.

## Fixture correction, not a bot fix

The first `wrong-passage` control pointed the monthly quote at parent section 4.03, which actually contains that quote. Both model acceptances were valid under the source-membership contract. The two rows are invalid negative labels, not retrieval/source-binding failures. Original captures and labels are preserved unchanged for audit; exclude these rows from semantic scoring.

Corrected the control in code to bind the bonus quote to subsection 4.03-b, where that quote is absent. Added preflight validation that every expected binding-negative must actually fail binding before any model calls. Other controls must bind, so a malformed test cannot masquerade as a semantic rejection.

All eight corrected extended fixtures passed the local binding preflight. The corrected fixture was NOT rerun in the cloud; do not combine this local correction with the earlier run to advertise a new model result.

## Local verification

- Full unit suite: 1,159 passed, two existing dependency deprecation warnings.
- Targeted lint and whitespace checks: clean.
- Graph update attempted, but graphify is unavailable and graph.json is absent.
- User/Claude uncommitted changes preserved. No commit or push performed.

Raw manifests, questions, answer payloads, passages and reviewer outputs are in the two run folders named above. These are exploratory reused evidence controls, not a fresh end-to-end retrieval benchmark. No production answer-rate or latency improvement is established.

## Next

Address claim segmentation independently: the review must evaluate each factual assertion, including multiple assertions within one supplied claim. Test the same visible answer with different claim grouping, and include requested-detail positives and necessary qualifications. Do not ban bonus vocabulary or use naive punctuation splitting that could corrupt abbreviations, quantities or source references.

After that semantic test passes, run the isolated end-to-end comparison with both answers captured, followed by fresh multilingual, market-policy isolation and global-sponsoring authorization gates. None of those gates is closed by this experiment.
