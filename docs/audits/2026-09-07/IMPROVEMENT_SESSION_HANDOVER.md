# Retrieval and quality improvements: session handover

Worked 2026-09-07 against `main` at `7ad2d10`. Six code branches are pushed and
unmerged. Nothing was deployed and nothing was run against the production box.

## The finding that reframed the work

**Five of the fourteen CloudWatch alarms were watching metrics that no code ever
emitted.** `GovernanceHealth`, `RetrievalHealth`, `ValidationHealth`,
`CacheHitRatio` and `AuditQueueDepth` all had recorders on `MetricsCollector`
and alarms in `app/monitoring/alarms.py`, and zero callers anywhere in `app/`,
`api/`, `services/`, `utils/`, `config/`, `scripts/` or `main.py`.

Every one of those alarms uses `treat_missing_data="notBreaching"`. With no data
they sat in OK indefinitely. **They did not look broken. They looked healthy.**

This changed the shape of task 1. Adding a fallback-rate metric to a metrics
path that nothing published would have produced another silent alarm. The
publishing path had to be wired first.

A latent defect surfaced while wiring it: the collector only ever had
`record_retrieval_failure`, which drives `retrieval_health` to 0.0 with nothing
to drive it back up. Governance and validation each had a success recorder;
retrieval did not. Wired as it stood, `RetrievalHealth` would have latched at
0.0 on the first failure and fired forever — no more useful than the silence.

## Branches, in merge order

The first three are independent. The last three are a stack.

| # | Branch | What it does |
|---|--------|--------------|
| 1 | `feat/deterministic-classifiers` | `temperature: 0` on the six retrieval classifier calls |
| 2 | `feat/canary-repeat-runs` | `--repeat N`, flaky detection, observed-only tier, two new cases |
| 3 | `feat/config-drift-detection` | Report SSM values the code refused to apply |
| 4 | `feat/fallback-rate-metric` | Fallback rate + alarm; fixes unused `CLOUDWATCH_FLUSH_INTERVAL` |
| 5 | `feat/track-numeric-repairs` | *stacked on 4* — count grounding repairs |
| 6 | `feat/wire-health-metrics` | *stacked on 5* — wire all five dead health metrics |

**Merge 4 → 5 → 6 in that order.** 1, 2 and 3 can go any time.

Every branch has the full suite green (`pytest tests`, which is what `deploy.sh`
runs — not just `tests/unit`).

## Before you assume any of this is live

None of the metrics work reaches CloudWatch unless both of these are true in
SSM. Their code defaults are `null` and `false`:

```bash
aws ssm get-parameters-by-path --path /askverachat/prod/ --recursive \
  --query "Parameters[?contains(Name,'METRICS') || contains(Name,'CLOUDWATCH')].[Name,Value]" \
  --output table
```

If `METRICS_PROVIDER` is not `cloudwatch` or `ENABLE_CLOUDWATCH_METRICS` is not
`true`, then **request metrics are not reaching CloudWatch today either**, and
the six alarms that do have producers are as blind as the five that do not. I
could not check this myself.

## Verifying the temperature change — do this, don't assume

Branch 1 is a hypothesis with a measurement attached, not a proven fix. The
selector weakness in `SELECTOR_DEMOTES_MATCHING_DIRECTORY_RECORD.md` recorded
~4 failures in 14 runs, with the record scoring 9.406 buried at position four.
Non-zero sampling is the obvious mechanism, but that is an inference.

Measure it before and after, using the mechanism branch 2 adds:

```bash
cd /opt/askvera && sudo -u askvera .venv/bin/python scripts/run_retrieval_canary.py \
  --load-ssm --repeat 10 --case-id kyrgyzstan-foreign-fbo-bonus-release-gate
```

Read `passed_runs` and `flaky` in the output. If the pre-change run flaps and
the post-change run is 10/10, the fix is real. If it still flaps at temperature
0, the selector prompt itself is the problem and the finding doc's next steps
apply.

I deliberately did **not** quarantine that case. It is currently the only signal
that would tell you whether the temperature change worked.

## Two things I did not do, and why

**Held-out evaluation on the US$25 budget.** Prepared but not run. It spends
real money and needs the box, both of which are yours to trigger. The discipline
from `RETRIEVAL_STATUS_AND_PLAN.md` §6 still holds and matters more than the
mechanics: **agree the thresholds before seeing any results, and never reuse a
question that was used to tune a fix.** Branch 2 gives you `--repeat` so a
held-out number can be a distribution rather than a single sample.

**Backing up the 8 GB of captures to S3.** Not done. It is an outward-facing
upload of ~600 Bedrock calls of evaluation data, it costs money, and the
destination bucket and retention are decisions I should not make for you. The
captures still exist only on one laptop, which remains the single largest
unrecoverable risk in the project — larger than anything in this session.

## Open risks

- **The 35% fallback threshold is a guess.** Nobody has measured the normal
  rate. It is set to catch a step change, not to express a quality target.
  Tighten it once a fortnight of `FallbackResponses` data gives a real baseline.
- **The two new canary cases are unverified.** That is why they are
  observed-only. Promote them to blocking once a deploy shows them passing.
- **`starlette` is unpinned**, arriving via `fastapi==0.141.1`. That is why the
  `httpx2` deprecation appeared with no change on our side. Pinning it, and
  doing the `httpx2` migration deliberately, is the real fix for the third
  deploy message.
- **There is no deploy log.** `/var/log/askvera-deploy.log` does not exist, so
  deploy output — canary scores, health timings, rollbacks — lives only in shell
  scrollback. A `tee` into a timestamped file would make the fallback-rate work
  much easier to reason about after the fact.
- **`_high_error_rate_alarm` uses per-host dimensions** while the new fallback
  alarm uses aggregate ones. Correct for a single-instance deployment, worth
  revisiting before a second instance exists.

## Corrections to things I said earlier

- I claimed no `temperature` was set anywhere. Wrong:
  `services/controlled_copy.py` already pinned it to 0. That is the precedent
  branch 1 follows.
- I predicted both the curl and nginx deploy messages would disappear on the
  next deploy. Only nginx did. `deploy.sh` parses its functions before
  `git pull` replaces the file, so the curl fix lands one deploy later.
- I stated a test count of 1004 in a commit message without having read it. The
  actual figure was 987. Amended.
- I added `latest_system_metric` to the collector when `system_snapshot` already
  did the same thing. Removed.
