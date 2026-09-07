# Session summary - 2026-09-07

Baseline at start: `7d29dad`. Deployed at end: `544c1f6`. Sixteen pull requests
merged (#57-#72), each deployed and canary-gated individually.

## Verified live

Re-tested through the widget against the deployed build, not asserted from unit
tests. Baseline for comparison: `docs/audits/2026-09-05/PRODUCTION_UI_BASELINE.md`.

| Defect | Evidence |
| --- | --- |
| Phone number omitted from answers (baseline cases 3, 9, 10) | Belgium orders and reception numbers both delivered with role labels; `1-888-440-ALOE (2563)` delivered |
| Safe half of a mixed request lost (case 8) | FBO definition answered with a source, income caption refused |
| Legitimate policy question refused as a medical claim (case 5) | Answers citing Section 16.02(j); the appended-instruction variant still refuses |
| Retired directory named in user-facing copy | "international sponsoring directory" in 12 locales, backend and widget |
| Safe follow-up inheriting an earlier refusal | "How much would those products cost?" answers after a refused caption request; the caption request still refuses |
| Rank questions abstaining or losing figures | 0 abstentions in 12 runs across four core questions |

## Fixed but not independently re-verified

- Response language decoupled from the selected market. `DE`+English is accepted
  where it was rejected outright; document authority is unchanged and still
  governed by the selected market. Not exercised through the widget.
- Product pricing now declines plainly instead of promising a lookup that cannot
  happen. Verified on the box, seen once in the widget.

## Root causes worth remembering

Four separate defects lived in the numeric grounding validator, three introduced
by this session's own phone fix:

1. Phrase extraction discarded line breaks, merging a heading into the sentence
   below it and producing a subject that matched no source.
2. Token spans covered only suffixes, so a trailing word in a heading left no
   span present in the source.
3. Repair deleted a sentence and orphaned a bracket, which the integrity check
   then read as truncation.
4. The subject was read from a 220-character window reaching back across the
   answer's heading.

A fifth defect was pre-existing: bracket balance was tested for equality, so
"a) b) c)" enumerations were read as truncated answers. Policy answers enumerate
requirements constantly, so any such answer could be discarded.

Two failure modes, and the quieter one is worse. An abstention tells the user
nothing is available. A repair that removes a sentence delivers a fluent,
confident answer with the governing figure silently missing.

## Open

- **Legal packet** - `docs/legal/2026-09-07-WORDING_REVIEW_PACKET.md`. Three
  items. Note that moving the medical policy from WARN to REFUSE would undo the
  case 5 fix, because the risk engine runs before the guardrail provider.
- **Residual numeric flagging** - the validator removed a number in 3 of 12 runs,
  then 0 of 8. Whether those were genuine catches or remaining false rejections
  is not established.
- **Flaky canary case** - `kyrgyzstan-foreign-fbo-bonus` failed 3 of roughly 10
  runs, each time recoverable on retry. Left as-is by decision.
- **In-message language requests** - a French request in an English session is
  answered in English. Market/language coupling is fixed; this is separate.
- **Track B** - preserved on `experimental/track-b-retrieval-work`. The raw
  model-call captures, about 8 GB, are deliberately not in git and exist only on
  the local disk.
- **`$25` cloud test budget** - unspent. The two matched comparisons, segments
  writer and follow-up context, have not been run.

## Recommendation

The release canary scores retrieval: which document was selected, and whether
evidence was approved. Every defect found today after the selector regression was
downstream of that - in governance, in output validation, in repair. The canary
passed 15/15 while a core question was failing in production, and it could not
have caught any of them.

Add at least one case that asserts a delivered answer: ask a rank-qualification
question, require the governing figure to appear in the final text with a
citation. That single check would have caught four of today's defects.

Nothing here establishes general answer quality. These are targeted fixes to
specific reported failures, verified against those failures.
