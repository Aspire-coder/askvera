# Market-policy fixes: local implementation checkpoint

## Implemented

- Policy extraction rejects valid clock times followed by explicit time units as section headings, both inline and at line start. Decimal section numbers remain supported. Tests cover hours/hrs, Uhr, uur, heures, ore, horas and timmar; other time formats are not certified.
- A verified Benelux ordering excerpt now retains discrepancy and minimum-order clauses under 13.01-d and 13.01-f instead of 23.59. This is an offline excerpt test, not a full-document reindex.
- Both evidence selectors now distinguish explicit FBO/Preferred Customer scenarios, delivery discrepancies, satisfaction returns, termination buy-back, rank retention and activity/bonus eligibility.
- Removed the OpenSearch selector's unconditional unopened-product preference for FBO buy-back. Unopened alone does not establish role, termination or salability.
- Generation instructions preserve the question's stated role without granting access or silently substituting the default profile. They separate related benefits and deadline triggers, and distinguish revision from effective dates.
- Evidence-contract instructions require claim applicability, not merely a citation to a nearby rule. This remains a model instruction, not a new deterministic semantic validator.

## Local verification

- 922 unit tests passed, including 35 new parser/prompt-wiring tests.
- Targeted lint passed for the four edited implementation files and two new test files.
- Existing compact-prompt budget retained; no confidence thresholds, models, access filters or live settings changed.
- Full tests required temporary-file access outside the sandbox. Two existing dependency deprecation warnings remain.

## Still open before promotion

1. CA-04 selector/approval diagnosis, including whether the retention clause reaches the selector and whether the 1,200-character candidate preview hides necessary evidence. Relevant raw hits alone do not prove sufficient selection context.
2. Isolated full-document reparse and candidate index validation, preserving source hashes, section ownership and publication isolation. Existing published chunks remain unchanged.
3. Repeated Current/Candidate answer comparisons, with exact questions, answers and citations. Prompt-wiring tests do not demonstrate corrected model behavior. No new live generation was run at this checkpoint.
4. Complete source-grounded scoring, including the US applicability/date flags, plus the full safety and local/global boundary gates.
5. Freeze candidate code and prompt/cache identity before promotion. Existing prompt version has not yet been advanced, so do not deploy this working tree as-is or evaluate it through shared answer caches.

The repository already contained substantial unrelated uncommitted work. It was preserved. No commit, push, deployment, shared-cache deletion or index publication was performed. No improvement percentage or release-ready claim is supported yet.
