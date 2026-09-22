# R06 diagnosis: C3/C4 workbook cases and the five retrieval regressions

Date: 2026-09-18. Read-only diagnosis. No code was changed anywhere; the only
write made by this task is this file.

Inputs read: `askvera-conv-quality` (candidate, HEAD `6fcad4a`) including
`docs/conversation-quality/codex-requests/laneC-c3-c4-diagnosis.md` and
`docs/conversation-quality/HANDOFF.md`; the read-only
`askvera-evidence-first-v2` worktree's `docs/evidence_first_v2/CURRENT_STATUS.md`,
`V2-09-sol-corrected-scope-aware-fusion-handoff.md`,
`TERRA-R03-CONTEXT-TO-CAPTURE-20260918-1400.md`; the saved capture in
`output/evidence-first-v2/` (`V2-REAL-CAPTURE-COMPARISON-20260918.md`,
`retrieval-capture-20260918-r3.json`, `retrieval-comparison-20260918-corrected.json`);
`us_policy.txt` and `us_testing_cases.md` in the scratchpad.

## Summary table

| Case | First failing stage | Confidence | Evidence | Minimal fix candidate / capture request | Owner area |
|---|---|---|---|---|---|
| 1. Tanzania foreign-then-local follow-up | Query formation (capture tool, not proven production) | High that the *saved evidence* is not representative; unknown for real production | `retrieval-capture-20260918-r3.json` case `ho-slp-04...`: `question` field is the standalone final turn only; `text`/`vector` channels return 0 hits; `global_text`/`global_vector` (30 hits each) never include `sponsoring-022-tanzania`, whose content legitimately answers the question ($100 foreign-FBO vs $5 local-FBO bonus threshold). TERRA-R03 independently found the same runner-level defect: it "loops over `case["question"]`... does not read `case["conversation"]`". | Capture request below (new app-path capture with real conversation history for this exact frozen case) | Codex (retrieval capture / R03 promotion) |
| 2. Finland inactivity follow-up (rank 7→17) | Retrieval fusion formula, but **not currently failing production** at the retrieval stage; unresolved beyond that | Medium | `retrieval-comparison-20260918-corrected.json`: `production_positions.FI:4.05-b = 7` (recall@10 = 1.0), `rrf_positions.FI:4.05-b = 17` (recall@10 = 0.0). This is a **V2 plain-RRF regression relative to current production**, not a current-production defect. Also, the underlying query is the standalone Finnish follow-up alone (no manager-role turn attached) — same capture-tool limitation as case 1, and TERRA-R03 separately found a live orchestrator defect where this exact Finnish anaphoric form (`Entä jos hän...`) used to drop the prior turn (now fixed in `AIOrchestrator` per R03, unverified live). | Capture request below | Codex (V2 fusion) + verify R03 Finnish-follow-up fix live |
| 3. Norway former-FBO reapplication/downline (rank 19 under V2) | Retrieval fusion — **current production actively fails this case (not merely "ranked low")** | High | `retrieval-comparison-20260918-corrected.json`: `production_positions.NO:17.08-c = null` (absent from top 30) vs `rrf_positions = 19`. The raw capture's `captured.merged_order` for this case shows current production ranks `GLOBAL sponsoring-081-norway` (the country's global directory record) **first**, with score 10.10, vs the next candidate at 1.40 — an 8x gap. One of the country-policy vector query variants (`vector#0`) independently ranks the correct clause `NO:17.08-c` **first in its own channel**, but current production's global-record boost crowds every country-policy candidate out of the top 30 entirely. | Country-policy question, mentions country name only ("Forever Norge") → current fusion's global-record protection over-fires and evicts the correct policy clause completely. This is the same protection mechanism V2-09 is trying to make scope-aware (only protect global rows for verified `directory`/`international_sponsoring` intent) — Norway is evidence *for*, not against, that correction. | Codex (V2-09/V2-10 scope-aware fusion; Norway should be added as a named regression control alongside Hong Kong/Ghana) |
| 4. Hong Kong delivery fee / Ghana cross-market bonus | Retrieval fusion (plain RRF demotes a correctly-boosted global record) | High | `retrieval-comparison-20260918-corrected.json`: HK `GLOBAL:sponsoring-030-hong-kong` production rank 1 → RRF rank 20; Ghana `GLOBAL:sponsoring-010-ghana` production rank 1 → RRF rank 30. Raw capture shows the global channel returns only the single correct record (`n=1`) for both cases, so under RRF a channel-of-one candidate gets swamped by 30-candidate country-policy channels that are query-irrelevant to these cases. | Already the explicit design target of V2-09's scope-aware fusion (Hong Kong/Ghana are its own named regression controls; do not deploy plain RRF). No new capture needed here — this is already correctly diagnosed and gated. | Codex (V2-09/V2-10) |
| 5a. P001 "What is Forever Living Products?" | Already fixed on candidate | High | `_verified_conversation_intent` in `app/retrieval/providers.py` deterministically downgrades a false-positive `income_claim` label to `knowledge` for this exact string without any model call, pinned by `tests/conversation/test_intent_company_identity_and_purchasing.py` (verified by reading the bypass logic and the test, not by a live run). Workbook's `ACTUAL` (the income-disclaimer text, sourced from 1.01(d)) predates this fix or reflects a different deployment. | None — fixed. Confirm live once B1 four-branch merge + this candidate reach production (per HANDOFF.md §9 approval queue item 2). | N/A (fixed) |
| 5b. P068 "Can I pay cash?" | Unresolved — cannot be attributed to an existing fix | Medium-low | 13.01(c) confirmed in `us_policy.txt`: lists "credit card (Visa, MasterCard, Discover), PayPal, ApplePay..., check, or money order" — cash is absent, so the workbook's `MUST` is correct. The only related regression-canary case, `us-payment-methods-release-gate` in `tests/fixtures/retrieval_canary.json`, tests a *different* phrasing ("What payment methods are accepted...") and does not exercise the negative-inference form ("Can I pay cash?", where the literal word "cash" never appears in the governing section). Neither the typo-normalizer fix nor the evidence-gate fix (both dated 2026-09-16, before the 2026-09-15-dated workbook — see below) is shown by any test to touch this phrasing. | Capture request below | Codex (retrieval — lexical/semantic gap between "cash" and an enumerated list that omits it) + evidence approval (does 13.01(c) clear the confidence bar for this phrasing if retrieved at all) |
| 5c. P078 "If I'm active here am I active everywhere?" | Already fixed on candidate | High | `tests/unit/test_evidence_routing.py::test_selector_relevant_middle_band_approves_active_everywhere_section` uses this exact question string against section 15.01(b)(6) content and asserts `decision.approved is True`, `reason == "approved_selector_relevant"`. This is the shipped `fix/evidence-gate-grounded-low-confidence-20260916` (merge `98e93cd`), confirmed an ancestor of both the candidate's base (`5b1d33f`) and its HEAD (`6fcad4a`). The workbook file (`us_testing_cases.md`, mtime 2026-09-15 01:02) predates that merge (2026-09-16 00:41). | None — fixed, pending live confirmation | N/A (fixed) |
| 5d. P091 "What happens if I go a whole year without qualifying?" | Already fixed on candidate | High | Same fix and same file, `test_selector_relevant_middle_band_approves_forfeiture_section`, uses section 6.05 content and asserts approval. Same before/after-merge dating as P078. | None — fixed, pending live confirmation | N/A (fixed) |
| 5e. P104 "Can I have a stall at a weekend market?" | Already fixed on candidate | High | `tests/unit/test_typo_retrieval.py::test_correctly_spelled_word_is_not_swapped_for_a_policy_lookalike` uses this **exact** question string and documents the root cause directly: the typo normalizer used to swap the correctly-spelled word "stall" for the policy-lookalike "shall" (one edit apart, from planner candidate wording like "...shall be severely dealt with" near 16.02), corrupting the query before it ever reached retrieval. `tests/unit/test_evidence_routing.py::test_selector_no_selection_is_not_rescued_by_middle_band` uses the corrupted string `"a shall at a weekend market"` as its input, showing what the broken query used to look like and that it correctly stays refused. Fixed by `fix/typo-normalizer-corrupts-words-20260916` (merge `4c16435`), also an ancestor of base and HEAD, also after the workbook's mtime. | None — fixed, pending live confirmation | N/A (fixed) |
| 5f. P167/P168/P170 (emotionally-framed 1.01(c)/(d)/(e) variants) | Unresolved — no pinned fix found | Medium-low | Source sections verified word-for-word in `us_policy.txt` (quoted below). No test in the candidate (unit, conversation, or conversation_pack) reproduces these three specific emotionally-framed questions or the corresponding sections; `tests/conversation_pack/cases.json` only mirrors the plain P001-style identity question (`US-POLICY-001`, `needs_live: true`) and a plain P007-style 2027-gap question, neither of which is emotionally framed. The laneC diagnosis's own hypothesis (retrieval/prompt sensitivity to emotional phrasing) is unconfirmed either way by this evidence. | Capture request below | Retrieval (does emotionally-worded phrasing still surface 1.01(c)/(d)/(e)?) and/or prompt-composition (Lane B/C territory) |

## Source/document issues for the user

None found. Every governing passage checked against `us_policy.txt` (1.01(a),
1.01(c), 1.01(d), 1.01(e), 6.05(a), 6.05(b), 13.01(c), 15.01(b)(6),
16.02(e)(1)) is present, intact, and matches the workbook's description of
it. The Tanzania global-directory record (`sponsoring-022-tanzania`) is also
present and intact in the source bundle, with a specific, legitimate
foreign-vs-local bonus-threshold distinction ($100 vs $5) that answers the
frozen case's question. No extraction, OCR, or page-structure defect was
found in any of the eight sections examined.

## Case detail

### 1. Tanzania foreign-then-local follow-up

The frozen case's final turn is "And what about FBOs who live there?" after
a first turn about foreign-resident FBO bonuses. In the saved capture
(`retrieval-capture-20260918-r3.json`), the `question` field recorded for
this case is that final turn alone — no country name, no "bonus", nothing
that a lexical/vector search could latch onto. Its `text`/`vector` search
channels (which should carry the country-scoped query) both returned zero
hits; the `global_text`/`global_vector` channels returned 30 hits each but
never include `sponsoring-022-tanzania` anywhere in either list (checked
against every hit's `_id`). This is the exact defect TERRA-R03 already
diagnosed and fixed at the application layer: the old retrieval-only capture
runner "loops over `case["question"]`... does not read
`case["conversation"]`, construct session history, invoke the orchestrator,
or attach runtime context provenance," while the real `AIOrchestrator` path
"already reads the session history, creates a contextual query." That
application-layer fix has not yet been exercised against this frozen case
with a real capture — R03 fixed the mechanism, but no fresh multi-turn
capture for Tanzania has been run since. **This case cannot be marked a
current production defect from the saved evidence; it can only be marked as
proof that the capture used to measure it was not representative.**

### 2. Finland inactivity follow-up

Two separate things are true and must not be conflated. First,
`retrieval-comparison-20260918-corrected.json` shows current production
ranks the required section `FI:4.05-b` at 7 (recall@10 = 1.0) while V2 plain
RRF ranks it at 17 (recall@10 = 0.0) — this is a **regression that V2 would
introduce**, not a defect in what is running today. Second, the query
underlying even the rank-7 production measurement is, per the same
capture-tool limitation as Tanzania, the standalone Finnish follow-up
sentence alone (`"Entä jos hän on Sponsored Recognized Manager..."`), not a
context-carrying reconstruction of the full three-turn conversation
(inactivity → manager-role question). TERRA-R03 separately found and fixed a
live defect where this exact configured Finnish anaphoric form used to be
misread as a brand-new long question, dropping the prior inactivity turn
entirely; that fix is local-only and unverified live. Both of these mean the
"rank 7" figure itself should not be trusted as a description of current
real-world behavior for this exact multi-turn case.

### 3. Norway former-FBO reapplication and downline

This is the strongest and most actionable current-production finding in
this diagnosis. The raw capture's `captured.merged_order` for this case (in
`retrieval-capture-20260918-r3.json`) shows the top-ranked candidate under
**current production fusion** is `GLOBAL|en|International-Sponsoring-Directory.pdf|sponsoring-081-norway`
with score `10.097727` — roughly 8x the next-best candidate's score of
`1.403168` — while the correct country-policy clause `NO:17.08-c` does not
appear anywhere in the top 30 merged results. Yet looked at per-channel, one
of the vector query variants (`vector#0`) independently ranks `NO:17.08-c`
**first** in its own list. The only plausible explanation consistent with
both facts is that current production's global-directory boost/pin
mechanism — the same mechanism responsible for correctly keeping Hong Kong
and Ghana at rank 1 (case 4) — fires here too, because the question names
the country ("Forever Norge"), and once fired it dominates the merge so
completely that every country-policy candidate, including a channel-leading
one, is pushed out of the top 30 entirely. Under V2 plain RRF (which removes
that boost), the same clause resurfaces at rank 19 — worse than ideal, but a
recovery from total absence. This case should be treated as affirmative
evidence *for* the V2-09/V2-10 scope-aware correction (which already commits
to only protecting a global row for verified `directory`/
`international_sponsoring` intent) rather than as a separate bug: Norway
should be added to that work's named regression list alongside Hong Kong and
Ghana, as a case where the *unscoped* global boost is actively harmful.

### 4. Hong Kong delivery fee and Ghana cross-market bonus

Confirmed exactly as already diagnosed by V2-09: both required records are
correctly ranked 1 under current production and demoted to rank 20 (Hong
Kong) and rank 30 (Ghana) under V2 plain RRF. The raw capture shows the
`global_text`/`global_vector` channels return only a single hit for each of
these two cases — the correct record and nothing else — so a formula that
fuses purely by rank position across channels of very different sizes will
always crowd out a channel-of-one candidate once enough country-policy
candidates (which are irrelevant here) are added to the union. This is
already correctly gated: V2-09's handoff explicitly states "do not deploy
plain reciprocal rank fusion yet" and lists both cases as named regression
controls for the scope-aware fusion work. No further diagnosis is needed
here; this diagnosis simply corroborates the existing finding against the
raw per-channel data.

### 5. US workbook leads

Source-verified sections (brief quotes, page numbers from `us_policy.txt`):

- 1.01(a), p.2: "Forever Living Products (FLP) is an international family
  of companies that produce and market exclusive health and beauty products
  ... through independent Forever Business Owners (FBO)."
- 1.01(c), p.2 (part of the May 2026 change summary): "Existing downline
  purchasing will continue generating earnings under the current structure
  until the end of 2026."
- 1.01(d), p.2–3: "Forever makes no guarantees regarding income or success
  ... not available to residents of the United States beginning on May 1,
  2026."
- 1.01(e), p.3: names the Regional Sales Director/Area Sales Manager and
  Customer Care as the contact for questions.
- 6.05(a)/(b), p.15–16: forfeiture of downline Manager lines after 12
  months without LBQ, becoming an Inherited Manager to the first Leadership
  Eligible Manager upline.
- 13.01(c), p.[38223 offset]: acceptable payment forms are "credit card
  (Visa, MasterCard, Discover), PayPal, ApplePay (for North America ONLY),
  check, or money order" — cash is not listed.
- 15.01(b)(6), p.[39333 offset]: Active status achieved in the Home Country
  extends to all other countries the following month, "regardless of the
  Sales Level."
- 16.02(e)(1), p.[42681 offset]: "exhibitions for a period of less than one
  week in a twelve-month period at the same venue are considered temporary
  and are therefore permitted."

All eight match the workbook's stated `sec` citation and `MUST` content
exactly. None of them show an extraction defect.

**P001, P078, P091, P104 are already fixed on the candidate**, each
confirmed by reading the exact mechanism and a pinned test that uses the
identical question string (P001, P078, P091) or documents the identical
root cause (P104's "stall"→"shall" typo corruption). `us_testing_cases.md`'s
file modification time (2026-09-15 01:02) is earlier than the merge commits
for the evidence-gate fix (`98e93cd`, 2026-09-16 00:41) and the
typo-normalizer fix (`4c16435`, 2026-09-16 00:59), both of which are
confirmed ancestors of the candidate's base commit `5b1d33f` and its HEAD
`6fcad4a` via `git merge-base --is-ancestor`. This is consistent with (but
does not by itself prove) the workbook having been captured against a
pre-fix deployment.

**P068 and P167/P168/P170 remain unresolved.** For P068, the only related
canary (`us-payment-methods-release-gate`) tests a different, positively-
phrased question and does not establish whether "Can I pay cash?" — where
the answer word "cash" never appears in the governing section — is
retrieved and approved correctly. For P167/P168/P170, the governing
sections are all confirmed present and correct, but no test in the
candidate reproduces the emotionally-framed phrasing itself, so the laneC
diagnosis's "retrieval or prompt sensitivity to emotional phrasing"
hypothesis is neither confirmed nor refuted by anything in this candidate
or the saved capture.

## Capture requests for R09/R10

Each of the following needs a **live or fixture-backed capture through the
real application path** (not the old retrieval-only runner), because the
saved evidence stops short of the needed stage or was built on a
non-representative query:

1. **Tanzania (case 1).** Replay the exact frozen case
   `ho-slp-04-tanzania-foreign-then-local-bonus-follow-up-en` through the
   `AIOrchestrator` path with its full two-turn `conversation` (the original
   foreign-resident-bonus turn plus "And what about FBOs who live there?"),
   country `TZ`, language `en`. Record: the contextual query the
   orchestrator actually builds, the resulting text/vector/global search hit
   lists (all channels), the selector's decision, and `approve_evidence`'s
   decision/reason. This is the only way to know whether R03's
   context-to-capture fix actually recovers `GLOBAL:sponsoring-022-tanzania`
   for this case.

2. **Finland (case 2).** Same treatment for
   `ho-slp-17-finland-36-month-inactivity-then-managers-follow-up-fi` with
   its full three-turn conversation (inactivity question → answer → "Entä
   jos hän on Sponsored Recognized Manager..."), language `fi`. Record the
   same fields as above, plus whether the fixed Finnish anaphoric-form
   recognizer in `AIOrchestrator` (per TERRA-R03) actually retains the prior
   turn in a live run.

3. **Norway (case 3).** A capture recording, per query variant, both the
   raw per-channel score list (already available) **and** which channel(s)
   the global-record boost/pin logic consults to decide whether to protect
   `sponsoring-081-norway`, plus what runtime scope-intent field (if any) is
   available at capture time. This is exactly the "trusted runtime-produced
   scope decision and authorized policy market per request" gate that
   V2-09/V2-10 already requires before promotion — Norway should be one of
   its held-out cases, not a separate ask.

4. **P068 (cash payment).** A live or fixture-backed capture of "Can I pay
   cash?" for `country=US, language=en, role=new_prospect`, recording the
   text/vector hit list (does 13.01(c) even appear in the candidate set for
   this exact phrasing?), the selector's decision, and `approve_evidence`'s
   decision/reason. If 13.01(c) is retrieved but not approved, the
   evidence-gate fix's selector-relevant middle band should be reviewed
   against this phrasing specifically, the same way it already was for
   P078/P091.

5. **P167/P168/P170 (emotional framing).** Live or fixture-backed captures
   of the three exact workbook questions for `country=US, language=en`,
   recording retrieval hit lists for sections 1.01(c)/(d)/(e) and the
   selector/approval decision. If retrieval and approval both succeed, the
   defect (if any) is in generation/prompt composition, not retrieval — in
   which case this should route back to Lane B/C's prompt work rather than
   Codex retrieval.

None of these five captures requires any change to frozen evaluation
content, the isolation allowlist, or any AWS/production configuration; each
is a bounded, held-out replay of an existing frozen case or workbook
question through the already-fixed application path.

## Handoff

Five findings, in order of actionability: (1) Norway is a genuine current-
production miss caused by an unscoped global-directory boost — strong
evidence to add as a named regression control for the V2-09/V2-10
scope-aware fusion work, alongside Hong Kong and Ghana, which are already
correctly diagnosed and gated as-is. (2) Tanzania and Finland's headline
numbers (absent / rank-7-vs-17) were measured on a capture tool that TERRA-
R03 already found and fixed at the application layer, so neither number
describes current or even fixed-application behavior — both need a fresh
capture through the real orchestrator path before any fusion change is
scored against them. (3) On the US workbook, P001, P078, P091, and P104 are
already fixed on this candidate (confirmed via code + pinned tests using
the exact question strings/root cause), most likely because the 178-case
workbook predates those September 16 merges. (4) P068 (cash) and
P167/P168/P170 (emotional framing) remain genuinely open — all source
sections are verified intact and correct, but no existing fix or test
covers either the negative-inference "is X absent from a listed set"
pattern or emotionally-worded phrasing of an otherwise-covered topic, and
five capture requests above spell out exactly what a live run would need to
record to close each gap.
