# Remaining Canada refusal: attended follow-up

September 6, 2026. **HOLD. The original refusal is not safely fixed. Production is unchanged.**

## Diagnosis and controlled changes

The captured selector chooses the monthly activity requirement and explains it correctly, but sets `directly_answers_top_rank` false. The current prompt also asks for rank-retention clauses when retaining a rank is mentioned. That suggested a background-versus-requested-property ambiguity, not a missing retrieval passage in these frozen inputs.

Two bounded, isolated smoke comparisons tested that hypothesis and a previously explored explicit-decision protocol combined with the newer ranking and stable source binding. Neither candidate was installed in the live provider. No confidence thresholds, live indexes, caches or infrastructure changed.

| Comparison | Existing compact combination | Candidate | Calls |
| --- | ---: | ---: | ---: |
| Replace only retention instruction with target-property instruction | 9/10 | 9/10 | 20 |
| Explicit yes/no/fact/insufficient decision with ranked, bound evidence | 9/10 | 6/10 | 20 |

These are one-repeat selector checks on reused evidence, not independent held-out or end-to-end quality scores. The second comparison changes the decision protocol and uses stricter polarity/draft checks; it is not a single-word prompt ablation or a comparison against production Current.

## What the failures show

1. Target-property wording alone does not fix the original refusal. It still quotes the applicable activity rule, explains that sales level alone does not establish activity, and emits a false support decision. This does not establish the retention instruction as the root cause.
2. Explicit decisions produced this draft for the original question: "Keeping your sales level does not automatically make you active every month; you must have 4 Active Case Credits in your Home Operating Company each month to be considered Active." However, the model put the Sales Level definition before the governing activity rule. The governing-first check rejected it. A plausible draft is not a passing selector contract.
3. The voluntary-termination-only control emitted ANSWER_NO while also listing the automatic-termination rule as missing. This is an unsupported-answer decision, not evidence that automatic termination does not occur. Rejected.
4. The direct English Active question selected two source IDs but quoted only one. The German control duplicated a selected ID. Both were rejected by binding checks. The German draft was also English; the selector checker does not score customer-facing language quality.

The failed checks were not waived, and no false support flag was overridden using free-text reasoning.

## Retained local work

- Experimental `scoped` and `verdict` variants in the isolated adapter, selected only through explicit experiment options. Default four-arm behavior remains available; production is not wired to these variants.
- Tests that the scope variant changes only the intended instruction and preserves evidence, fails if the baseline instruction changes, and cannot override false decisions using prose.
- Tests for explicit verdict polarity, bound quotes, invalid/mixed schemas and malformed abstention.
- Non-yes/no exploratory questions now carry ANSWER_FACT labels instead of inheriting the original question's ANSWER_NO label. Earlier boolean-only scores did not consult that field and are unchanged.
- Full question, exact request and raw response captures remain available below.

## Verification and accounting

**1005 unit tests passed**, targeted changed-file lint passed. Two existing dependency deprecation warnings remain. Graphify update could not run because the executable is unavailable; no graph exists and no generated wiki was edited.

40 additional selector calls, zero execution errors, 151,208 recorded tokens, zero cache-read tokens. Checkpoint total: **276 selector calls; zero additional end-to-end chatbot calls**. One read-only Bedrock model-metadata check confirmed the captured Haiku model is active. No commit, push, deployment or live-data modification.

## Next implementation boundary

Do not add more wording variants to this reused case or promote these candidates. The next structural candidate should avoid redundant independent source-ID lists by deriving selection from validated support entries, preserve the governing-rule priority after selection, and reject any answer that declares missing required facts. Those deterministic checks cannot prove that the proposed conclusion follows from the rule; semantic correctness still needs independently labeled positive/negative cases and repeated evaluation. Do not silently repair incorrect quotes, invent missing sources or turn missing evidence into a negative answer. Only after these checks pass should final chatbot answers and the full safety suite be compared.

## Full outputs

- [Target-property comparison](target-scope-smoke-01/COMPARISON.md)
- [Bound explicit-decision comparison](bound-verdict-smoke-01/COMPARISON.md)
