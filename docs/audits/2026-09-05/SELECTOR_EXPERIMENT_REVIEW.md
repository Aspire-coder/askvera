# Selector experiments - hold, no production change

Three bounded experiments completed September 6, 2026: 108 Bedrock Converse calls, zero recorded execution errors, no search/index/SSM/database/production operations in the runners. Recorded usage totals 346,564 tokens, including 16,750 output tokens. These are selector-only experiments, not end-to-end customer answer tests.

| Candidate design | Current checks | Candidate checks | Decision |
| --- | ---: | ---: | --- |
| Selected-set support | 12/18 | 6/18 | Reject |
| Quote-first support | 12/18 | 12/18 | Reject: no answerable-case recovery |
| Yes/no/insufficient decision | 12/18 | 13/18 | Reject: unstable and wrong paraphrase |

Each includes two answerable questions and four deliberately evidence-ablated negative controls, repeated three times per version. The score checks decision, first governing section and (for candidate positives) exact quote binding. Candidate and Current schemas have different validation requirements, so these numbers are NOT interchangeable answer-quality percentages. All cases are exploratory/reused, not held-out generalization evidence. The four negative controls are NOT the full medical/income/country safety suite.

## What the captured source actually establishes

Canada 4.03(b) explicitly defines monthly Active qualification using 4 Active Case Credits in the Home Operating Company during that month, with a separate foreign-company condition. This supports explaining that retained rank alone does not make monthly qualification automatic. It does not by itself establish a universal permanent rank-retention rule or all termination conditions.

The original CA-04 fixed input includes 4.03 and 4.03-b, but does NOT include 4.01-l. Do not repeat an earlier assumption that both those particular clauses were in every selector input. Exact inputs are frozen in each manifest.

For the ablated controls, only a sales-level definition or a voluntary-termination clause is provided. Expected abstention means insufficient evidence IN THAT INPUT, not absence of a rule anywhere in Canada's policy.

## Failures worth preserving

1. Current selects the activity rule and explains a negative answer, yet marks direct support false. Both first candidate designs still fail to recover the original question consistently.
2. The paraphrase is misread as Earned Incentive participation instead of general Active qualification. In the polarity experiment, the model says monthly Active requalification is unnecessary, with 0.85 confidence, citing incentive rules. That answer is unsafe to promote.
3. Polarity repeat 1 gives a broadly appropriate answer for the original question but cites rank 1 for a quote actually in candidate 4. Exact source binding rejects it. Repeat 2 passes the decision/evidence check; repeat 3 does not. One success is not stability.
4. The first experiment adds prose after JSON in six unsupported cases. Those captures fail the strict parser, not because the model necessarily recommended an unsupported answer. Reports distinguish the reason.

## Retained changes and verification

Only isolated evaluation tooling and its tests were added in this work. No production selector prompt/schema, confidence threshold or risk gate was changed. The production code was already dirty; prior changes were preserved.

- Full unit suite: **960 passed**, two existing dependency warnings.
- Lint passes for the new comparison, reporting and test files.
- Original captured source and model inputs are preserved. Manifests record prompts, case evidence, model, token configuration, fixture/script hashes and repeats.
- The model and region stay fixed between each pair, output cap is 512, no SDK invocation retries, order alternates by repeat. Managed model output remains nondeterministic. No cache points are used; recorded cache-read tokens are zero.
- Hardening is off in these experiments. The Current baseline prompt is extracted from the local provider, not the older rejected prompt embedded in capture history.

## Next implementation decision

Do not wire any of the three candidates into production. The next work should isolate governing-rule selection from decision formatting: classify the requested property separately from mentioned rank/benefit terms, bind support to stable source identifiers, and validate quotes against those exact sources. Evaluate using additional independently labeled questions and deliberately wrong governing passages before changing approval behavior. Do not override a rejected decision from prose or loosen global thresholds.

The final narrow income fix still needs end-to-end verification. Offline parser repairs still need an isolated index comparison. These experiments do not close either item.

## Full outputs

- `selector-set-support-01/COMPARISON.md`
- `selector-quote-first-01/COMPARISON.md`
- `selector-polarity-01/COMPARISON.md`

These contain each question and both raw model decisions/drafts for all repeats. Drafts are explicitly experimental and must not be presented as approved chatbot answers.
