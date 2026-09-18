# DependencyUnavailable alarm spec (Lane E, Phase 2, task C5/monitoring)

Status: proposal only. Nothing here has been deployed. This document exists
so a human can approve or reject a specific CloudWatch alarm; Lane E's code
changes (`app/metrics/**`, the orchestrator patch) do not create it.
`app/monitoring/alarms.py` (Codex/coordinator-touched territory in prior
phases, and out of Lane E's file-ownership list for this phase) is
deliberately left unmodified -- adding the `AlarmDefinition` below would
create a real AWS alarm on the next `CloudWatchAlarmManager.put_alarms()` run
wherever that is wired into deploy, which this project must not do without
separate sign-off.

## Why this alarm, distinct from HighErrorRate and HighFallbackRate

Phase 1 (`C5`) made two dependency failures that used to reach the API as
HTTP error envelopes (BedrockTimeoutError/BedrockServiceError from
`generate()`, and AwsServiceError/BotoCoreError/ClientError/ConnectionError/
TimeoutError/OSError escaping `retrieve()`) into ordinary HTTP 200 chat
fallbacks under `failure_layer=dependency_unavailable`. That was the right
fix for the user (an honest "technical hiccup" answer instead of a raw error
response or, worse, a crash), but it has a monitoring cost that Phase 1
disclosed and left pending: **a Bedrock or embedding outage now counts
toward `HighFallbackRate`, not `HighErrorRate`**, because the request itself
succeeds.

Neither existing alarm is a good substitute for watching this directly:

- **HighErrorRate** (`app/monitoring/alarms.py:_high_error_rate_alarm`) never
  sees these events at all now -- that is precisely the behavior change C5
  made, and reverting it would bring back error envelopes and un-persisted
  turns.
- **HighFallbackRate** (`_high_fallback_rate_alarm`) sees them, but only
  mixed into every other fallback reason: missing evidence, a policy-country
  restriction, an ambiguous market, off-topic refusals, and low confidence.
  On a real Bedrock/OpenSearch outage, `FallbackResponsesByLayer` with
  `FailureLayer=dependency_unavailable` would show the spike, but only if an
  operator remembers to filter by that dimension while `HighFallbackRate`
  itself is silent or noisy with unrelated fallback reasons. A single
  dedicated metric removes that manual step and lets the alarm fire on the
  outage specifically, at a much lower volume/threshold than a 35%-of-all-
  fallbacks trigger would tolerate.

`DependencyUnavailable` (emitted by
`app.metrics.responses.record_dependency_unavailable`, metric name
`DependencyUnavailable`, dimensions `Component`
(`retrieval`/`embedding`/`generation`) and `Availability`
(`unavailable`/`degraded`/`exception`)) is a `Count`, not a ratio,
specifically so it can be summed directly rather than needing a
fallback-rate-style ratio calculation, and so a handful of dependency
outages in a short window shows up as a small number rather than being
diluted into the fallback denominator.

## What each related metric actually means (read this before alarming on any of them)

Three metrics can all be touched by the same underlying retrieval outage,
and they do not agree with each other by construction -- each answers a
different question, measured at a different point in the pipeline:

- **RetrievalHealth** (`app.metrics.health.record_retrieval_outcome`,
  written from `RetrievalService.retrieve`'s `finally` block in
  `app/retrieval/service.py`) answers "did the provider call return without
  raising?" It is measured *before* the evidence gate and *before* Codex's
  R02 availability routing ever runs. Once R02 lands, a `DEGRADED` result
  that still carries some usable evidence is a normal return value, not a
  raised exception -- so `RetrievalService` can legitimately record
  `success=True` for it even on a request whose *delivered answer* later
  fails final evidence approval and gets routed to
  `dependency_unavailable`. RetrievalHealth dropping is necessary evidence
  of a retrieval problem; RetrievalHealth staying healthy is NOT sufficient
  evidence that no dependency failure reached the user on that request.
- **FallbackResponsesByLayer{FailureLayer=dependency_unavailable}**
  (`app.metrics.responses.record_delivered_response`) answers "how many
  delivered answers were fallbacks for this reason?" It is measured at the
  end of the pipeline, once a `ChatResponse` exists, and is a percentage's
  numerator (paired with `DeliveredResponses` for `HighFallbackRate`). It
  cannot be alarmed on alone without either accepting every other fallback
  layer's noise (if watching plain `FallbackResponses`) or manually
  filtering by dimension on every review (if watching the by-layer metric).
- **DependencyUnavailable** (this document's subject) answers "how many
  times did the orchestrator decide, right then, that a dependency was the
  reason it could not deliver a real answer?" It is emitted at the same
  moment as the `dependency_unavailable` fallback response is built (inside
  `_dependency_unavailable_response`), so it is a subset, by construction,
  of `FallbackResponsesByLayer{FailureLayer=dependency_unavailable}`, sliced
  by which dependency (`Component`) and how (`Availability`). It is the
  metric this alarm should watch, precisely because it is not diluted by
  every other fallback reason and does not depend on RetrievalHealth having
  also dropped.

In short: a real outage can show up in `DependencyUnavailable` and
`FallbackResponsesByLayer` while `RetrievalHealth` stays green (a degraded-
but-technically-successful provider call whose result still failed
downstream), so an operator diagnosing an incident should not treat
`RetrievalHealth` as the single source of truth for "is retrieval okay" --
it answers a narrower question than its name suggests.

## Proposed alarm

Following the existing conventions in `app/monitoring/alarms.py`
(`AlarmDefinition`, `_metric_query`, `_aggregate_dimensions`,
`_description`):

| Field | Value |
|---|---|
| Alarm name | `{CLOUDWATCH_ALARM_PREFIX}-HighDependencyUnavailable` (follows the existing `ALARM_NAMES`/`_ALARM_SUFFIXES` pattern; add `"high_dependency_unavailable": "HighDependencyUnavailable"` to `_ALARM_SUFFIXES` at implementation time) |
| Metric name | `DependencyUnavailable` (`app.metrics.names.DEPENDENCY_UNAVAILABLE_METRIC`) |
| Namespace | `settings.CLOUDWATCH_NAMESPACE` (`APP_NAMESPACE` in `alarms.py`, default `"ASKVera"`) -- same namespace every other application metric in this module uses |
| Dimensions | `_aggregate_dimensions()`: `{"Environment": environment_label(), "Version": version_label()}` -- matching `HighFallbackRate`/`RetrievalHealth`/etc, not the per-host `_app_dimensions()` set, because a dependency outage is a fleet-wide signal, not a single-host one. Deliberately **not** filtered by `Component` or `Availability` at the alarm level, so any dependency (retrieval, embedding, or generation) trips it; those two dimensions exist on the metric for post-incident triage (`GetMetricData`/dashboard breakdown), not for narrowing the alarm itself. |
| Statistic | `Sum` |
| Period | 300 seconds (5 minutes) -- shorter than `HighFallbackRate`'s 900s, because a dependency outage is more urgent to page on than a fallback-rate drift and the false-positive risk from a low-traffic period is bounded by the threshold below, not by a long period |
| Evaluation periods | 2 (10 minutes total), `datapoints_to_alarm=2` (no "M of N" leniency) -- consistent, sustained failures, not one blip |
| Threshold / comparison | `GreaterThanThreshold`, threshold `5` (five dependency-unavailable events in a 5-minute period, sustained for two consecutive periods). This is a `Sum` of raw counts, not a percentage, so it needs its own settings constant (e.g. `DEPENDENCY_UNAVAILABLE_THRESHOLD`) rather than reusing `ERROR_RATE_THRESHOLD` or `FALLBACK_RATE_THRESHOLD`, both of which are percentages over a different denominator. Five is a starting point for approval, not a measured value -- see "Open question" below. |
| Unit | `Count` |
| Treat missing data | `notBreaching` (matches every other health/count alarm in this module: no traffic in a period must not itself page) |

Definition sketch (for whoever implements this once approved -- not
authored into `alarms.py` by this patch):

```python
def _high_dependency_unavailable_alarm(dimensions: dict[str, str]) -> AlarmDefinition:
    return AlarmDefinition(
        name=ALARM_NAMES["high_dependency_unavailable"],
        description=_description(
            f"More than {DEPENDENCY_UNAVAILABLE_THRESHOLD:.0f} dependency-unavailable "
            "responses in 5 minutes, sustained for two periods.",
            "Retrieval, embedding, or Bedrock generation is failing; users are getting "
            "a technical-hiccup fallback instead of a real answer.",
            "Check FallbackResponsesByLayer{FailureLayer=dependency_unavailable} broken "
            "down by DependencyUnavailable{Component,Availability} to see which dependency "
            "(retrieval/embedding/generation) and which exception type, then that "
            "dependency's own health/latency dashboard (Bedrock, OpenSearch, embeddings).",
        ),
        metric_name=DEPENDENCY_UNAVAILABLE_METRIC,
        namespace=APP_NAMESPACE,
        statistic="Sum",
        threshold=DEPENDENCY_UNAVAILABLE_THRESHOLD,
        comparison_operator="GreaterThanThreshold",
        dimensions=dimensions,
        period=300,
        evaluation_periods=2,
        datapoints_to_alarm=2,
        treat_missing_data="notBreaching",
        unit="Count",
    )
```

## Approval needed

1. **Create the alarm at all.** This is a new CloudWatch alarm, which is a
   billed AWS resource and a new page-able condition. Someone with
   operational ownership needs to say yes before it is added to
   `app/monitoring/alarms.py` and deployed.
2. **The threshold (`5` per 5 minutes, 2 consecutive periods).** Picked to be
   low enough to catch a real outage quickly and high enough that a couple
   of transient Bedrock throttles in a quiet period don't page. This
   worktree has no production traffic data to validate that number against;
   it should be revisited against real `DependencyUnavailable` volume after
   a burn-in period, the same way `FALLBACK_RATE_THRESHOLD` and
   `FALLBACK_RATE_MIN_SAMPLE` were tuned from observed fallback rates rather
   than picked cold.
3. **Whether this should page the same on-call rotation as HighErrorRate**,
   given it is monitoring exactly the class of failure that used to trip
   that alarm before C5 changed its HTTP status.
4. **Notification wiring** (`AlarmNotificationActions`) -- not addressed
   here; follows whatever the coordinator decides for the other Phase 1/2
   alarm-behavior changes already on the approval queue in
   `docs/conversation-quality/HANDOFF.md` section 9.

## What this spec deliberately does not do

- It does not modify `app/monitoring/alarms.py`, `_ALARM_SUFFIXES`,
  `ALARM_NAMES`, or `config/settings.py` to add
  `DEPENDENCY_UNAVAILABLE_THRESHOLD`. Those are one small, reviewable diff
  once approved; writing them now would be adding an alarm on deploy without
  the sign-off this document exists to request.
- It does not change `HighFallbackRate`'s threshold or sample floor. The
  monitoring trade-off Phase 1 already disclosed (Bedrock/embedding outages
  moved from error-rate to fallback-rate) still stands; this alarm is an
  addition, not a fix to that trade-off, which remains item 1 on the
  existing approval queue in `docs/conversation-quality/HANDOFF.md`.
