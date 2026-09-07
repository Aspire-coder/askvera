# Fragment-level reviewer - 2026-09-06

Decision: REJECT this candidate for activation. Production unchanged. Existing reviewer modes remain unchanged and this mode requires explicit `--fragment-review --per-claim --structured-output` flags. No deployment, push, threshold adjustment, cache reset or index mutation.

## Hypothesis and implementation

The previous reviewer accepted an answer containing unrequested bonus detail when its two assertions were grouped into one claim. This experiment asked the model to partition each input claim into consecutive verbatim fragments and assess support and necessity independently for each fragment. A local validator requires all original text, punctuation and ordering to be preserved (whitespace may vary). Missing or rewritten fragments fail closed. Dependent requirements and exceptions should remain with the assertion they qualify.

Bedrock guidance informed the bounded, structured Converse request. One model call per valid input, the existing 768-token limit, unchanged model/profile and no repair retry. Strict output schema is retained; unsupported output/configuration combinations fail before invoking the model. Local text coverage does not establish that segmentation or semantic judgments are correct.

## Evaluation

Folder: `fragment-review-extended-01/`. Manifest records prompt, schema, script hashes, source-capture hashes, questions, candidate answer payloads and expected labels. Row files retain raw model output, full cited passages, parsed judgments, usage and timing. Expected labels are not sent to the model.

Eleven controls repeated twice: **20 model calls plus two deterministic wrong-source rejections**. **14/22 controls met expectations**. Two responses failed exact-text coverage. All model responses were parseable JSON; formatting enforcement held but semantic quality did not.

| Control | Repeat 1 | Repeat 2 |
| --- | --- | --- |
| Unasked bonus, bundled claim | Incorrectly accepted | Incorrectly accepted |
| Same answer, separate claims | Incorrectly accepted | Incorrectly accepted |
| Requested bonus, bundled claim | Correctly accepted | Correctly accepted |
| Same requested answer, separate claims | Correctly accepted | Incorrectly rejected |
| Medical claim without support | Correctly rejected | Correctly rejected |
| Corrected wrong-passage control | Locally rejected | Locally rejected |
| Necessary current-month qualification | Correctly accepted | Incorrectly rejected |
| Complete German rule | Correctly accepted | Correctly accepted |
| German rule missing personal-credit condition | Coverage error | Correctly rejected |
| German rule with wrong quantity | Correctly rejected | Correctly rejected |
| English answer supported by German source | Coverage error | Correctly accepted |

The corrected wrong-passage fixture passed preflight: its bonus quote is absent from the cited monthly subsection. It did not call the model. No invalid fixture rows were excluded from this run.

## What failed

- The model correctly separated the two bonus/activity assertions but still justified both necessity flags by quoting source membership. This shows segmentation alone does not resolve the conflation of truth with relevance.
- One requested-bonus answer lost a necessary qualification because the model treated the remaining marketing-plan conditions as unrelated.
- One timing answer had its direct "No" separated and judged unsupported despite the passage specifying credits during the current month. Isolating fragments can lose the context needed for inference.
- One model response inserted the missing German personal-credit condition into its review fragments, although that condition was not in the answer. Another removed punctuation. The local coverage checks rejected both; they are not counted as successful semantic judgments.

The earlier structured per-claim mode rejected separate unasked bonus detail twice; this candidate failed both repeats on that separate-claim control. Do not promote this merely because it decomposes text or produces valid JSON.

## Local checks

- Full local suite: **1,172 passed**, two existing dependency deprecation warnings.
- Focused reviewer/fixture tests: 49 passed.
- Targeted lint and diff whitespace checks: clean.
- Graph update attempted; graphify is unavailable and graph.json is absent.
- Existing user/Claude changes preserved. No runtime code was connected to the experiment.

## Next experiment, not a deployment recommendation

Keep this failed candidate frozen. Test a relevance-only judgment separately from source-support assessment so verbatim quotations cannot substitute for a necessity decision. Preserve the full question and answer context and test required exceptions/qualifications as positives. Use the same grouping-invariance pairs, plus independently authored cases, before another full-chat comparison.

These are exploratory captured-evidence controls, not an end-to-end retrieval benchmark. Fresh multilingual market isolation, global sponsoring authorization, safety, final citation binding, completeness and deployment gates remain pending.
