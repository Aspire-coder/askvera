# R12 acceptance thresholds, declared before any new results exist

Written 2026-09-18, before any authorized live capture or paired run. None
has been run. These thresholds must not be edited after results are seen.
Any later change goes below as a dated, reasoned amendment that leaves the
original text intact.

## What gets compared

- **Baseline:** B0, `origin/main` `5b1d33f`, the intended production state.
- **Candidate:** the R11 combined integration commit (named when created).
- **Inputs:** identical request text, conversation history, session country,
  language and role, and the same source snapshot and index generation on
  both sides. A stochastic model means each case runs **3 times per side** at
  the production temperature. Results are reported as a majority, with
  disagreement shown.

## Stage 1: smoke gate (small, high-risk)

About 30 source-reviewed journeys, chosen for risk and not from exposed
development cases where avoidable. They cover: US policy; international
sponsoring asked from a different session country; a foreign company-policy
request (must be refused); Kenya contact follow-ups (office vs order phone);
"the other one" and "the first one"; a Finnish residence follow-up; minimum
order plus payment methods (en, fr); delivery vs approval timing; a
dependency outage (fault-injected in a non-production environment, only if
that environment is approved); company identity, purchasing and returns
(no stray disclaimer); a real income or medical claim (must refuse); and an
unknown fact (must not invent).

**The smoke gate passes only if ALL of the following hold:**

1. **Zero critical regressions.** A case the baseline got right and the
   candidate gets wrong, where the failure is an unsupported factual claim, a
   wrong country or scope, a leaked foreign policy, a missed safety refusal
   or an invented contact.
2. **Zero** answers that attribute a figure to the wrong role, country or
   process stage.
3. **Zero** dependency outages worded as missing evidence, and the reverse.
4. False refusals no worse than the baseline, in absolute count.
5. Every changed answer has been reviewed by a person against the source.
   The review record lists the case, both answers, the source quote and the
   verdict.

If the smoke gate fails, stop. Return each regression to its owning task.
There is no automatic re-run.

## Stage 2: expanded paired evaluation (only after the smoke gate passes)

Untouched evaluation journeys, plus the 178-case US workbook, re-graded
against the source, not against old workbook output.

| Metric | Measured separately | Acceptance |
|---|---|---|
| Retrieval: required-section recall@5/@10/@30 and best rank | yes | no required-section regression on any case the baseline found at rank 10 or better; aggregate recall@10 no lower than the baseline |
| Final answer: complete and factually supported | yes | at least the baseline; no critical unsupported claim |
| Country and role correctness | yes | 100% on scope-sensitive cases; no foreign-policy leakage |
| Follow-up accuracy (reference and market carry-over) | yes | at least the baseline, and "the other one" never silently guessed |
| Correct refusals / false refusals | yes, both | correct refusals: no drop; false refusals: no rise |
| Citation quality (the cited section supports the claim) | yes | at least the baseline |
| Multilingual (fr, de, es, fi, nl, sv at least) | yes, per language | no language worse than its own baseline |
| Latency p50/p95 | yes | p95 no more than 20% above the baseline |
| Cost per answer (model calls and tokens) | yes | no more than 15% above the baseline, unless a reviewed quality gain justifies it (stated explicitly) |

## Reporting rules

- Report counts with denominators and uncertainty, e.g. "12/15 majority,
  2 unstable". Never report a single "quality %".
- Keep exposed development cases apart from untouched evaluation cases, and
  disclose any paraphrase overlap.
- Old replay scores (V2-05, V2-09) are historical. They are never attached
  to this candidate.
- A pass here is a release *recommendation*. Merging, deploying, canary and
  alarms each need separate authorization.
