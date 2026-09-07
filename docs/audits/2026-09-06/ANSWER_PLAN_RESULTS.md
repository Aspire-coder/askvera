# Answer-plan comparison results - 2026-09-06

## Decision: HOLD; do not integrate the extra planning call

36 model calls completed: 12 plans and 24 writer outputs across six cases and two repeats. All returned end_turn and parseable JSON. All 12 plans passed structural question-span/source-quote checks. These are not semantic approval checks.

| Measure | Direct writer control | Writer with plan |
|---|---:|---:|
| Displayed text / cited claim binding valid | 1/12 | 5/12 |
| Binding contract failures | 11/12 | 7/12 |
| Median model-call duration per answer | 2.76 seconds | 4.43 seconds including plan |

All 18 failures were displayed-answer/ordered-claim text mismatches, not quote-membership errors. The model often paraphrased the same fact twice in different wording. No output was silently repaired and no failed answer was delivered. The existing strict binding check remains unchanged.

On inspection against the frozen six-case expectations, both arms retained the monthly quantities, German personal-credit condition, requested bonus conditions, and timing. Neither arm volunteered the unasked bonus explanation in the monthly-only case. Thus there is no demonstrated semantic quality advantage from the added planning call on this small reused set. Some answers remain stiff or repetitive. Structural-valid counts above are NOT answer-quality or retrieval percentages.

The control uses the existing scope contract adapted to structured output without a reviewed draft. It is not deployed Current or the previous full-chat writer configuration. The candidate adds only the planning step to this component setup. Full authorized captured passages remain available to both writers. The test does not establish new retrieval, live publication eligibility, global/country authorization, multilingual generalization, medical/income safety, or end-to-end latency.

## Recommended next implementation

Remove duplicated answer generation at the output-contract boundary: request one ordered set of claim-linked response segments, validate them, then assemble the displayed answer mechanically from those exact segments. This is a new explicit contract, not post-hoc repair of these failed captures. Do not simply deliver this run's plan or discard a mismatched answer silently. Test empty/malformed segments, missing or wrong source bindings, omitted conditions, unknown citations and refusal handling. Semantic support and completeness still require evaluation; deterministic assembly only prevents text drift.

Keep the extra planner experimental. Test the simpler single-text contract before spending more calls on additional reviewers. Then run the full matched chatbot comparison, including fresh questions and safety/country/global checks, before promotion.

## Local verification

- 12 new unit tests; full suite 1,199 passed, two existing dependency warnings.
- Targeted lint and git diff --check passed.
- Graph refresh attempted but graphify is not installed; no graph was available.
- No runtime integration, production changes, threshold changes, index changes, cache changes, commits, pushes or deployment.
- Bedrock/Python guidance informed explicit token/time bounds, one attempt, strict structured output and reuse of a single client.

## Reproduction and provenance

Protocol: [ANSWER_PLAN_PROTOCOL.md](ANSWER_PLAN_PROTOCOL.md).
Raw requests, plans, writer output, quotes, IDs, token usage and timing: [manifest](answer-plan-01/manifest.json) and numbered JSON files in answer-plan-01.
Implementation: scripts/answer_plan_experiment.py. Tests: tests/unit/test_answer_plan_experiment.py.

## Every question and both generated answers

These are raw generated drafts, including failed binding contracts, not approved chatbot responses.

### Repeat 1

#### bonus-only

Question: Is being Active required for Volume and Leadership Bonuses and incentives?

Direct writer (binding FAILED):

Yes, being Active is required for Volume and Leadership Bonuses and all Incentives. An FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

Writer with plan (binding FAILED):

Yes, being Active is required for Volume and Leadership Bonuses and all Incentives. An FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

#### DE-complete

Question: Was muss ich diesen Monat tun, um in meiner Home Operating Company aktiv zu sein?

Direct writer (binding FAILED):

Um diesen Monat in Ihrer Home Operating Company aktiv zu sein, müssen Sie insgesamt 4 aktive Case-Credits in der Home Operating Company generieren, von denen mindestens eine eine persönliche Case-Credit sein muss.

Writer with plan (binding FAILED):

Um in einem bestimmten Monat in Ihrer Home Operating Company als aktiv zu gelten, müssen Sie in diesem Monat insgesamt 4 aktive Case-Credits in der Home Operating Company generieren, von denen mindestens einer eine persönliche Case-Credit ist.

#### DE-English-question

Question: What must I do to be Active this month in my Home Operating Company?

Direct writer (binding valid):

To be Active this month in your Home Operating Company, you must generate a total of 4 active Case-Credits in your Home Operating Company during this month, of which at least one must be a personal Case-Credit.

Writer with plan (binding valid):

To be Active this month in your Home Operating Company, you must generate a total of 4 active Case-Credits in your Home Operating Company during this month, of which at least one must be a personal Case-Credit.

#### mixed-claim

Question: What must I do to be Active this month in my Home Operating Company?

Direct writer (binding FAILED):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month.

Writer with plan (binding valid):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month.

#### mixed-requested

Question: What must I do to be Active this month in my Home Operating Company? Is being Active also required for Volume and Leadership Bonuses and incentives?

Direct writer (binding FAILED):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month. Yes, being Active is required for Volume and Leadership Bonuses and all Incentives—you must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

Writer with plan (binding FAILED):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month. Yes, being Active is required for Volume and Leadership Bonuses and all Incentives. To qualify for these bonuses and incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

#### necessary-timing

Question: Are 4 Active Case Credits from last month enough to be Active this month in my Home Operating Company?

Direct writer (binding FAILED):

No, 4 Active Case Credits from last month are not enough to be Active this month in your Home Operating Company. To be considered Active for the current month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that current month.

Writer with plan (binding FAILED):

No. To be Active in your Home Operating Company in the current month, you must have 4 Active Case Credits accumulated during that current month, not from the previous month.

### Repeat 2

#### bonus-only

Question: Is being Active required for Volume and Leadership Bonuses and incentives?

Direct writer (binding FAILED):

Yes, being Active is required for Volume and Leadership Bonuses and all Incentives. An FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

Writer with plan (binding FAILED):

Yes, being Active is required to qualify for Volume and Leadership Bonuses and all Incentives. An FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

#### DE-complete

Question: Was muss ich diesen Monat tun, um in meiner Home Operating Company aktiv zu sein?

Direct writer (binding FAILED):

Um in diesem Monat in Ihrer Home Operating Company aktiv zu sein, müssen Sie insgesamt 4 aktive Case-Credits in der Home Operating Company generieren, von denen mindestens einer eine persönliche Case-Credit sein muss.

Writer with plan (binding valid):

Um in einem bestimmten Monat in der Home Operating Company als aktiv zu gelten, muss ein FBO in diesem Monat insgesamt 4 aktive Case-Credits in der Home Operating Company generiert haben, von denen mindestens eine eine persönliche Case-Credit ist.

#### DE-English-question

Question: What must I do to be Active this month in my Home Operating Company?

Direct writer (binding FAILED):

To be Active this month in your Home Operating Company, you must generate a total of 4 active Case-Credits in your Home Operating Company during this month, of which at least one must be a personal Case-Credit.

Writer with plan (binding valid):

To be considered active in your Home Operating Company during a specific month, you must generate a total of 4 active Case-Credits in your Home Operating Company during that month, of which at least one must be a personal Case-Credit.

#### mixed-claim

Question: What must I do to be Active this month in my Home Operating Company?

Direct writer (binding FAILED):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month.

Writer with plan (binding valid):

To be considered Active for the month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month.

#### mixed-requested

Question: What must I do to be Active this month in my Home Operating Company? Is being Active also required for Volume and Leadership Bonuses and incentives?

Direct writer (binding FAILED):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month. Yes, being Active is required for Volume and Leadership Bonuses and all Incentives—you must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

Writer with plan (binding FAILED):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month. Yes, being Active is required for Volume and Leadership Bonuses and all Incentives. To qualify for these bonuses and incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

#### necessary-timing

Question: Are 4 Active Case Credits from last month enough to be Active this month in my Home Operating Company?

Direct writer (binding FAILED):

No, 4 Active Case Credits from last month are not enough to be Active this month in your Home Operating Company. You must have a total of 4 Active Case Credits in your Home Operating Company during the current month to be considered Active for that month.

Writer with plan (binding FAILED):

No. To be considered Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during this current month, not from the previous month.
