# Governing-rule and source-binding integration review

September 6, 2026. HOLD: no production activation, deployment, index publication, confidence relaxation, commit or push.

## What changed locally

Integrated the governing-rule helper and source-binding validator into an isolated selector runner, not the live chatbot. Four arms separate Current, ranking-only, binding-only and their combination. The runner saves exact requests, source registries, hashes, model decisions, token usage and failure reasons. It makes bounded Bedrock calls against frozen evidence, without querying or modifying the live index.

Ranking preserves the candidate set and prioritizes the actual monthly activity requirement for a limited English intent family. Binding requires each quote to belong to its claimed source. It does not prove semantic correctness or grant cross-market authorization. Capture identities are not represented as published document-generation identities.

## Repeated comparison: 96 calls

Eight cases, four arms, three repeats, same model and 512-token output limit. No execution errors.

| Arm | Decision/evidence checks passed |
| --- | ---: |
| Current | 18/24 |
| Ranking only | 21/24 |
| Full-ID binding only | 15/24 |
| Combined full-ID binding and ranking | 17/24 |

Ranking recovered the Canada activity paraphrase from 0/3 to 3/3. The original question remained 0/3 in every arm. Four negative controls passed all repeats in every arm. The full-ID protocol introduced output-size failures at the existing token limit; it is rejected for promotion.

Full requests and paired raw model outputs: [96-call comparison](governing-binding-comparison-01/COMPARISON.md).

## Compact-ID follow-up: 32 calls

Kept full content/provenance hashes in the validation registry but exposed compact stable aliases to the model. Alias collisions and unknown aliases fail closed. No increase to the token limit. This is a one-repeat format smoke test, not evidence of repeatability.

| Arm | Decision/evidence checks passed |
| --- | ---: |
| Current | 6/8 |
| Ranking only | 7/8 |
| Compact binding only | 5/8 |
| Combined compact binding and ranking | 7/8 |

The combined format passed the paraphrase, direct Active question, German control and four negative controls, but still refused the original Canada question. Binding alone also incorrectly refused "How do I become Active?" and did not put the governing rule first for the paraphrase. Shorter identifiers therefore do not solve governing-rule interpretation by themselves.

Full questions and outputs: [32-call comparison](governing-binding-compact-01/COMPARISON.md).

## Verification and limits

- 998 unit tests passed; targeted integration-file lint passed. Two existing dependency deprecation warnings remain.
- 128 additional selector calls completed, zero execution errors, zero additional end-to-end chatbot calls. Together with the previous 108 calls, the checkpoint total is 236 selector calls.
- New runs recorded 587,527 tokens total (446,765 repeated comparison; 140,762 smoke test), with zero recorded cache-read tokens. These are usage counts, not estimated monetary costs.
- Cases reuse captured Canada evidence. Added direct-English and German questions are exploratory controls, not an independent market-wide held-out evaluation.
- These scores assess selector decisions and evidence selection, not final chatbot answers, full claim accuracy or overall retrieval improvement. Binding arms apply additional protocol checks.
- Manifests preserve exact requests and adapter/harness hashes; helper-module hashes are not separately recorded. Production integration must use actual published source-generation metadata.
- Existing unrelated working-tree changes were preserved. Graphify is unavailable; no generated wiki was edited.

## Next gate

Do not promote yet. Trace why the original question receives a negative structured support decision even when the reason describes the correct distinction. Do not override that flag using free-text reasoning or lower confidence. Any proposed repair needs independent positive/negative labels, repeated isolated verification, then full final-answer and safety comparisons before live wiring. The compact combination is a candidate for further testing, not a demonstrated complete fix.
