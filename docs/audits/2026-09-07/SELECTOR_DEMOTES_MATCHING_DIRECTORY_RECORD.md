# Confirmed ranking weakness: the selector demotes a dominant country record

> **RESOLVED 2026-09-07.** Cause was non-zero sampling on the LLM evidence
> selector, not the selector prompt. Fixed by `BEDROCK_CLASSIFIER_TEMPERATURE=0`
> in `feat/deterministic-classifiers`, deployed as `fc2a7b9`. Measured 0
> failures in 30 runs against 7 in 34 before (Fisher exact p = 0.0087). See
> **Resolution** at the end. The analysis below is kept as written, including
> the parts it got wrong.

Investigated 2026-09-07 against deployed `544c1f6`. **The canary fixture is
correct. The selector is wrong roughly a third of the time.**

Next session should start here.

## The case

`kyrgyzstan-foreign-fbo-bonus-release-gate`, question:

> How are foreign FBOs paid their bonus in Kyrgyzstan?

Fixture expects the top document to be the Forever Kyrgyzstan record from the
International Sponsoring Directory. It failed roughly 4 times in 14 deploy runs
today, each time recoverable by retrying the deploy unchanged.

## Why the fixture is right

The Kyrgyzstan record, 3,184 characters, carries a dedicated section:

> **BONUS PAYMENT** - To local FBO's: If FBO gets his/her registration at Tax
> office and submits his registration certificate his/her bonuses are subject for
> bank transfer without tax and social payment deductions. If FBO prefers to get
> his/her bonuses without getting registration at tax Office he/she gets bonus...

It distinguishes local from foreign FBOs and states the actual payment mechanism.
Term counts in that record: bonus 6, payment 6, bank 5, transfer 4.

The section the selector prefers instead, US-EN-Company-Policy 4.04-f, reads in
full:

> Any 3rd-party charges or fees accrued on payments made to an FBO outside the
> Country in which the Profits/Bonuses are earned will be the responsibility of
> the FBO.

That assigns responsibility for charges. It never says how anyone is paid. It is
also a US policy section answering a question about Kyrgyzstan.

## Why this is the selector, not retrieval or scoring

Lexical and vector scoring get it right every time. In one probe the Kyrgyzstan
record scored **9.406** against 4.375 for the next candidate, and it was first in
the returned order on 6 of 6 consecutive runs at confidence 0.95.

The failing deploy runs show the same record present but reordered. Canary output
from a failed run:

    "document_scores": [0.912, 0.997, 1.066, 9.406, 4.376]
    "top_title": "US-EN-Company-Policy.pdf - Sec 4.04-f: Any 3rd-party charges..."
    "confidence": 0.78

The 9.406 record is fourth. The LLM evidence selector reorders candidates after
scoring, and intermittently buries an exact-country match that scores more than
twice its nearest rival and literally contains the heading BONUS PAYMENT.

Selector confidence tracks the error: 0.95 when it picks the record, 0.75-0.85
when it picks the policy section. The selector is measurably less sure when wrong.

## Reproduce

    cd /opt/askvera && sudo -u askvera .venv/bin/python - <<'PY'
    import os
    os.environ.setdefault("APP_ENV", "production")
    from config import settings
    settings.load_ssm_config()
    from app.retrieval.service import RetrievalService
    svc = RetrievalService()
    for i in range(10):
        r = svc.retrieve("How are foreign FBOs paid their bonus in Kyrgyzstan?",
                         "US", "en", "new_prospect", "probe-%d" % i)
        print(i, round(r.confidence, 2), r.documents[0].title[:70])
    PY

Expect the Kyrgyzstan record most runs, and a US policy section on a minority.
Ten runs is the minimum useful sample at a roughly 30% rate.

## Suggested direction, not a decision

A deterministic guard is preferable to a selector prompt change. On 2026-09-07 a
selector prompt rewrite regressed three release-gate cases and forced a rollback;
prompt edits to this component are demonstrably high risk.

The shape to consider: when the question names a country, a global sponsoring
record for that country is among the candidates, and its score dominates, the
selector should not be able to demote it below unrelated local policy sections.
`_directory_target_country_names` and `_directory_record_country_score` in
`app/retrieval/opensearch_sections.py` already identify the record; the gap is
that the LLM reorders afterwards.

Validation must account for the failure rate. A single green canary proves
nothing at roughly 30% - require several consecutive clean runs, and prefer the
standalone probe above for iteration since it needs no deploy.

## Do not

Relax the fixture. The expectation is correct, and loosening it would hide a
selector that discards the best available evidence for a country-specific
question. That is the class of failure this gate exists to catch.


## Resolution (2026-09-07)

**The cause was sampling, not the prompt.** Every Bedrock `converse` call in
`app/retrieval/providers.py` and `app/retrieval/opensearch_sections.py` ran at
the model's default temperature. The evidence selector is a classifier that
returns JSON, so sampling variety bought nothing and cost reproducibility: the
same question could be given the same candidates and reorder them differently.

`feat/deterministic-classifiers` sets `temperature` explicitly on the six
classifier calls -- query planner, both evidence selectors, the support and
income-claim routers, query translation -- and leaves the three prose-writing
calls at the model default. Deployed as `fc2a7b9`.

### Measurement

Same standalone probe, same question, same index.

| | Failures | Runs | Rate |
|---|---|---|---|
| Temperature unset | 7 | 34 | 20.6% |
| Temperature 0 (`fc2a7b9`) | **0** | **30** | **0%** |

Fisher exact, one-tailed: **p = 0.0087**. Probability of 30 consecutive clean
runs at the old rate: **0.001**.

The 30 post-fix runs all returned confidence 0.95, the value that previously
accompanied every correct result. No run returned 0.75 or 0.85.

Rule of three puts the 95% upper bound on the new failure rate at 10%, so this
is not evidence the rate is exactly zero -- only that it is decisively lower
than 20.6%.

### What this closes, and what it does not

The deterministic guard proposed above is **not needed**. Neither is the
confidence-threshold fallback that suggested itself from the data (0.95 when
right, 0.75-0.85 when wrong, across all 34 pre-fix runs). Both were designed to
compensate for a non-determinism that no longer exists. Building either now
would add a branch that never fires.

`kyrgyzstan-foreign-fbo-bonus-release-gate` stays blocking and is now a genuine
regression guard rather than a known-flaky case. If it fails again, that is new
information, not the old flapping.

The advice above about validation still holds and generalises: a single green
canary run proves nothing about an intermittent failure. `--repeat N`, added in
`feat/canary-repeat-runs`, exists for this.

### Correction to the analysis above

The section arguing a prompt change was the likely fix, and that a deterministic
guard was preferable to touching the prompt, was reasoning from the wrong cause.
The prompt was never the problem. The observation that prompt edits to this
component are high risk remains true and was what made a deterministic
alternative attractive -- but the actual fix touched no prompt at all.
