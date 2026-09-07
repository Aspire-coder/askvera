# Confirmed ranking weakness: the selector demotes a dominant country record

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
