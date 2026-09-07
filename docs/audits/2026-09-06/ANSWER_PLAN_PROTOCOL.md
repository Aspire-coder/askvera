# Answer-plan component protocol

Frozen before calls. Six reused/exploratory cases, two repeats, two writer arms.
Control: existing scope contract adapted to a structured source-bound writer.
Candidate: identical writer plus a separate question-linked, source-bound plan.
Neither arm is the deployed Current or the exact previous full-chat runtime.
No previous answer draft is included. Both arms see identical full passages.
Source capture: scoped-writer-chat-02. No live search or shared storage changes.

Maximum 36 calls: 12 direct writer calls, 12 planner calls, up to 12 planned
writer calls. Failed or empty plans stop their writer. No repairs or retries.
Control/candidate order reverses on repeat two. All prompts, plans and answers
are saved; final answers require human semantic review, not reviewer-model votes.

## Expected semantic outcomes

- mixed-claim: four Active CC in the home company during the current month;
  no unasked bonus eligibility or foreign-company alternative.
- mixed-requested: same monthly requirement PLUS Active and other marketing-plan
  requirements for bonuses/incentives during the accrual month. Do not imply
  Active status alone guarantees payment.
- necessary-timing: previous month's four credits alone do not establish current
  home-company Active status; retain current-month four-CC requirement.
- DE-complete: German answer with four total active CC, at least one personal,
  during the month in the home company. No unrelated bonus discussion.
- DE-English-question: same DE rule in English, including personal-credit condition.
- bonus-only: Active plus other plan conditions and relevant calendar month;
  do not volunteer a separate tutorial on obtaining Active status.

All factual claims must cite a passage containing the support quote and actually
supporting the interpretation. Structural binding is scored separately from
completeness, scope, and meaning. Raw quote membership cannot certify correctness.

This does not test all markets, safety, authorization, fresh retrieval, cache, or
full response validation. Any success is a component result, not release readiness.
Measure the extra planning latency; do not recommend an extra production call
without proving sufficient benefit and testing a lower-latency integration.
