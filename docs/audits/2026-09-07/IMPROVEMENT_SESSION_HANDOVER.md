# Retrieval and quality improvements: session handover

Worked 2026-09-07. Seven branches produced. Four are merged and the code is
deployed as `fc2a7b9`; three remain, gated on one unanswered question below.

## Headline: the selector flapping is fixed, and measured

`BEDROCK_CLASSIFIER_TEMPERATURE=0` eliminated the intermittent ranking failure
recorded in `SELECTOR_DEMOTES_MATCHING_DIRECTORY_RECORD.md`.

| | Failures | Runs | Rate |
|---|---|---|---|
| Temperature unset | 7 | 34 | 20.6% |
| Temperature 0 (`fc2a7b9`) | **0** | **30** | **0%** |

Fisher exact one-tailed **p = 0.0087**. The cause was sampling on the LLM
evidence selector, not the selector prompt. Full detail and the corrections it
forced are in that finding doc, now marked RESOLVED.

This also cancelled two pieces of planned work: the deterministic country-record
guard the finding proposed, and a confidence-threshold fallback suggested by the
data (0.95 when right, 0.75-0.85 when wrong, across all 34 pre-fix runs). Both
compensated for non-determinism that no longer exists.

## The finding that reframed the metrics work

**Five of the fourteen CloudWatch alarms were watching metrics that no code ever
emitted.** `GovernanceHealth`, `RetrievalHealth`, `ValidationHealth`,
`CacheHitRatio` and `AuditQueueDepth` all had recorders on `MetricsCollector`
and alarms in `app/monitoring/alarms.py`, and zero callers anywhere in `app/`,
`api/`, `services/`, `utils/`, `config/`, `scripts/` or `main.py`.

Every one uses `treat_missing_data="notBreaching"`. With no data they sat in OK
indefinitely. **They did not look broken. They looked healthy.**

Adding a fallback-rate metric to a path nothing published would have produced a
sixth silent alarm, so the publishing path had to be wired first.

A latent defect surfaced while wiring it: the collector only ever had
`record_retrieval_failure`, driving `retrieval_health` to 0.0 with nothing to
drive it back up. Governance and validation each had a success recorder;
retrieval did not. Wired as it stood, that alarm would have latched on the first
failure and fired forever.

## Branches

**Merged and deployed as `fc2a7b9`:**

| Branch | What it does |
|--------|--------------|
| `feat/deterministic-classifiers` | Temperature 0 on the six retrieval classifier calls |
| `feat/canary-repeat-runs` | `--repeat N`, flaky detection, observed-only tier, two new cases |
| `feat/config-drift-detection` | Report SSM values the code refused to apply |

Plus `docs/selector-ranking-weakness`, merged as PR #79.

**Remaining, a stack. Merge 1, then 2, then 3, in that order:**

| # | Branch | What it does |
|---|--------|--------------|
| 1 | `feat/fallback-rate-metric` | Fallback rate + alarm; fixes unused `CLOUDWATCH_FLUSH_INTERVAL` |
| 2 | `feat/track-numeric-repairs` | Count grounding repairs, log their evidence |
| 3 | `feat/wire-health-metrics` | Wire all five dead health metrics |

Every branch has the full suite green under `pytest tests`, which is what
`deploy.sh` runs, not just `tests/unit`.

## Review findings, fixed

An external code review of `e73742c` raised five issues. Four were verified
against current `main` and fixed; one was already superseded.

| Branch | Finding |
|--------|---------|
| `fix/canary-single-execution` | The gate ran two retrievals per case and bypassed no caches |
| `fix/preflight-page-coverage` | One scanned page in a readable PDF was silently dropped |
| `fix/evidence-contract-coverage` | The contract checked claims-in-answer but not answer-in-claims |
| `fix/followup-market-continuity` | A market named in a skipped follow-up turn was lost |
| `fix/out-of-corpus-boundary-answer` | A price question was told to rephrase, which cannot help |

**The review's headline finding was stale.** It scored passage selection 5/10
citing "8 out of 10" on the Kyrgyzstan question - that is the pre-fix baseline
from this document, read at a commit predating the temperature merge. Measured
after: 0 failures in 30. Its methodological point stands and is why we measured.

**Its finding about the evidence contract is real but not live.**
`EVIDENCE_GATED_OUTPUT_ENABLED` is false and unset in SSM, so that component
does not run in production. Fixed so it is safer to enable, not because it was
hurting anyone.

The last of those was not in the review. It is the 2026-09-07 deploy finding:
`product-price-out-of-scope-delivered` passed while returning a generic
insufficient-evidence fallback, so a distributor asking a price was told to
rephrase a question no rephrasing can fix. The corpus-boundary prompt rule
never fired because evidence approval rejects first. The boundary is now
stated on the path that actually executes, and the canary case that passed
vacuously now asserts the boundary answer and forbids "rephrase".

**Two of these carry operational consequences worth knowing before merge.**

The preflight fix converts silent page loss into a rejected upload.
`ADMIN_TEXTRACT_OCR_ENABLED` is false in production, so a PDF containing even
one scanned page will now be refused where it previously published minus that
page. Failing loudly is the right trade for an assistant whose answers
distributors act on, but it will block uploads that used to succeed.

The canary fix changes what `--repeat` measures. It was partly measuring the
cache; it now measures the pipeline every run. Expect delivered-answer cases to
cost more and to be less uniformly green than before, because they were
previously being answered from cache after the first run.

## Blocking question for the remaining three

None of that work reaches CloudWatch unless SSM sets both of these. The code
defaults are `null` and `false`:

```bash
aws ssm get-parameters-by-path --path /askverachat/prod/ --recursive \
  --query "Parameters[?contains(Name,'METRICS') || contains(Name,'CLOUDWATCH')].[Name,Value]" \
  --output table
```

The `config_effective_snapshot` log confirms SSM sets `METRICS_PROVIDER`,
`ENABLE_CLOUDWATCH_METRICS` and `ENABLE_CLOUDWATCH_ALARMS`, but not to what
values. If `METRICS_PROVIDER` is not `cloudwatch`, then request metrics are not
reaching CloudWatch today either, the six alarms that do have producers are as
blind as the five that do not, and fixing that comes before deploying these
three branches.

## What the first deploy of this work found

**Config drift, immediately.** SSM held
`RETRIEVAL_PIPELINE_VERSION = 2026-07-17-reviewed-results-v1`, seven weeks
stale, while production ran `2026-08-23-selector-calibration-v4`. Harmless at
runtime, since the code ignores it, but it would mislead anyone reading SSM to
find out what production runs. Deleted from the console; the application's own
role correctly lacks `ssm:DeleteParameter`. The next deploy should report
`ignored_code_owned_count: 0`.

**A canary case that passes for the wrong reason.**
`product-price-out-of-scope-delivered` passed, but the answer was a generic
fallback telling the reader the documents do not contain enough information and
to rephrase. Evidence approval rejected first
(`insufficient_approved_evidence`), so the corpus-boundary prompt rule never
ran. The assertion, absence of two bad phrases, passed because the response
contained nothing at all. A distributor asking a price is told to rephrase
rather than that the documents do not cover pricing. **The case needs a stronger
assertion and the behaviour needs fixing.** Keep it observed-only until then.

**Numeric repair firing on a directory contact answer.**
`uruguay-phone-delivered-answer` triggered `NUMERIC_CLAIM_UNGROUNDED`, and
repair removed the figures 10 and 8. The phone numbers survived and the case
passed, but something was deleted, plausibly office hours. This is the same
validator that removed a correct figure earlier in the day, on exactly the class
of answer where three phone numbers went missing this week. Worth reading the
full answer before and after repair.

**`uruguay-phone-delivered-answer` is ready to promote** to blocking. It
delivered the correct number with a citation.

## Two things deliberately not done

**Held-out evaluation on the US$25 budget.** Not run. It spends real money and
needs the box. The discipline from `RETRIEVAL_STATUS_AND_PLAN.md` section 6
matters more than the mechanics: **agree thresholds before seeing results, and
never reuse a question used to tune a fix.** `--repeat` now makes a held-out
number a distribution rather than a single sample.

**Backing up the 8 GB of captures to S3.** Not done. It is an outward-facing
upload whose destination bucket and retention are not mine to choose. Those
captures still exist on one laptop only, which remains the single largest
unrecoverable risk in the project.

## Open risks

- **The 35% fallback threshold is a guess.** Nobody has measured the normal
  rate. Set to catch a step change, not to express a target. Tighten it once a
  fortnight of `FallbackResponses` data gives a baseline.
- **`starlette` is unpinned**, arriving via `fastapi==0.141.1`, which is why the
  `httpx2` deprecation appeared with no change on our side. Pinning it and doing
  the migration deliberately is the real fix for that deploy message.
- **There is no deploy log.** `/var/log/askvera-deploy.log` does not exist, so
  canary scores, health timings and rollbacks live only in shell scrollback.
- **`_high_error_rate_alarm` uses per-host dimensions** while the new fallback
  alarm uses aggregate ones. Correct for one instance; revisit before a second.
- **The 0% post-fix rate is not proof of zero.** Rule of three puts the 95%
  upper bound at 10%. Decisively better than 20.6%, not perfect.

## Corrections made during the session

- I claimed no temperature was set anywhere. Wrong:
  `services/controlled_copy.py` already pinned it to 0.
- I predicted both the curl and nginx deploy messages would clear on the same
  deploy. Only nginx did. `deploy.sh` parses its functions before `git pull`
  replaces the file, so the curl fix landed one deploy later.
- I stated a test count of 1004 in a commit message without having read it. The
  actual figure was 987. Amended.
- I added `latest_system_metric` to the collector when `system_snapshot` already
  did the same thing. Removed.
- I read a 9/10 probe as a near-clean result before verifying the change was
  deployed. It was not. The box was still on `7ad2d10`, so that run was a second
  baseline rather than an after-measurement.
