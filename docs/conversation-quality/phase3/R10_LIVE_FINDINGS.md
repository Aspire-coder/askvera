# R10 live capture — findings across 75 journeys

Approval `R10-2026-09-22-KRISH`. Candidate `b5bccb9`. Captured on the EC2
application host against the real corpus, with capture isolation active and
metric publication disabled. 75 journeys, zero errors, 1,534 calls
(882 retrieval, 441 embedding, 95 planner/translation, 66 selector,
50 generation, 0 reranker).

These are observations from one run. Expectations for the 75 journeys have not
yet been written by a source-reviewed human, so nothing below is a pass/fail
score; it is what the system did.

## 1. Delivery mix

| Outcome | Journeys |
| --- | ---: |
| answer | 31 |
| evidence_missing | 25 |
| safety_refusal | 8 |
| international_directory | 4 |
| clarification | 4 |
| cross_market_policy | 2 |
| personal_account | 1 |

31 of 75 journeys carried approved evidence. Only 50 journeys reached
generation: the 25 `evidence_missing` journeys were short-circuited before the
model was called, which is the intended behaviour and is why the run was cheap.

All seven fallback states fired at least once against real documents. Two of
them fired less often than the manifest intended (see §4).

## 2. Stability, measured properly

A second full capture of the same 75 journeys was run on the same build
`b5bccb9` under approval `R10B-2026-09-22-KRISH`, changing nothing but the
output file. Comparing the two runs journey by journey:

- **outcome kind changed: 4 of 75 (5%)**
- approved-evidence presence changed: 4
- CX features applied changed: 1

An earlier, weaker comparison in this document put the instability at six of
twelve journeys. That comparison was wrong: it compared the aborted first
capture against the full one, two runs separated by a build change and by a
call-cap abort, on a twelve-journey sample. The like-for-like figure is 5%,
and the system is stable enough to grade journeys against expectations.

### What actually moves (corrected)

The four journeys whose outcome moved are also the four whose recorded
evidence appeared or disappeared. An earlier draft of this section read that
as retrieval driving the outcome. The arrow runs the other way: the capture's
`approved_evidence` field is the final response's `citations`
(`scripts/capture_application_path.py:593`), and a governance fallback carries
no citations. So a refused answer *reads* as "no evidence" even when evidence
was approved and a grounded answer was generated.

The two investigation sessions traced the mechanism independently
(`c0733e5`, `a3a6571`). A grounded answer about the company quotes US Company
Policy 1.01, which reassures prospects by *denying* an income guarantee.
`IncomeClaimPolicy` paired "guarantee" with an earnings word by position alone
and refused the answer. Whether a given run includes that disclaimer sentence
is generation variance, so the same question is answered in one run and
refused in the next. Three of the four moving journeys are this. Only cx-04b
(international directory, Italian) looks like a genuine retrieval flip.

The capture field is misleadingly named and should record the evidence
decision separately from the delivered citations; that is a CX-lane fix.

Run B was slightly the better of the two (32 answers vs 31, 7 refusals vs 8,
5 international-directory vs 4), which is consistent with noise rather than
with either run being privileged.

## 3. The same question behaves differently by language

Eight journey families were asked in two or three languages. Six diverged:

- **Cash payment (1301c)** — English answers with the policy; Spanish returns
  `evidence_missing`.
- **Company identity** — English and German answer; Italian returns the income
  refusal.
- **International sponsoring** — English answers; German and Finnish return
  `evidence_missing`.
- **Foreign-market policy request** — English returns the correct
  `cross_market_policy` copy; French returns `evidence_missing`; Russian
  answers.
- **Minimum order plus payment** — English and Dutch answer; French returns
  `evidence_missing_detail`.
- **Returns and satisfaction guarantee** — English answers; Danish returns the
  income refusal.

The failure direction is consistent: the non-English side loses evidence or
lands on a harsher fallback, rather than producing a wrong answer. That is the
safe direction, but it means non-English customers are materially less well
served on the same question.

Three families were fully consistent across all three languages:
`evidence_missing` copy (cx-01), typo/ambiguity clarification (cx-05) and the
income-claim refusal (cx-07). The clarification lane is the strongest result in
the run — identical behaviour and correct localisation in English, German and
Spanish.

## 4. Where the run did not match the manifest's intent

- **cx-02, dependency unavailable** — all three journeys produced ordinary
  answers. The injected fault did not reach the path it was meant to disable,
  so the dependency fallback is still unproven live.
- **cx-04, international directory** — all three journeys returned
  `evidence_missing_detail` for a phone-number request, while the equivalent
  real-world journeys (r10-11, r10-25, cx-08, cx-11a) did produce
  `international_directory`. The manifest's cx-04 phrasing does not reach the
  directory path.

## 5. Outcome classification under-reports refusals

Three journeys delivered refusal or limit copy while the typed outcome recorded
`answer`:

- r10-22 delivered the income refusal, typed `answer`.
- cx-06a and cx-06b delivered the personal-account limit, typed `answer`
  (the CX feature `personal_account_limit` did apply, so the customer-visible
  text is right).

Because CX composition keys off the typed outcome, an under-classified turn can
miss the composition it should have received. cx-06c, the Finnish sibling, was
typed `personal_account` correctly — so this is inconsistent derivation, not a
missing rule.

## 6. Answer language (corrected after source review)

An earlier draft of this document listed two wrong-language answers as CX
defects. Reading `config/policy_locales.json` shows that neither is one.

- **cx-13a — French message, US widget, English answer: correct.** The US
  market's published locales are `["en", "es"]`. Answer language follows the
  message language only within the session market's enabled languages
  (approval 6B market scoping), so French is not an available answer language
  for a US session and English is the right fallback. Its Spanish sibling
  cx-13b did switch, because Spanish *is* a US locale. The rule worked in
  both directions.
- **r10-24b — Russian message, US widget, English answer: a manifest defect,
  not a code defect.** Russian is not a US locale at all, so the journey pairs
  a market and a widget language that the product does not offer. Its sibling
  r10-28b has the same invalid pairing and answered in Russian, which makes
  this one more instance of the run-to-run instability in §2 rather than a
  language finding.

Every journey whose market genuinely enables its language answered in that
language: German, Italian, Dutch, Norwegian, Danish, Finnish, Spanish and
Serbian. r10-26b is the best of them — a Serbian customer asking about Ghana
was told, in Serbian, that their country selection is Serbia.

Action: fix the two invalid US+ru journeys in the manifest before the next
capture. No CX-layer change.

## 7. False income refusals

Down from 4 of 12 in the first capture to 8 of 75 here, and two of the eight are
clearly wrong: the Italian company-identity question and the Danish returns
question are not income questions. The pattern that the investigation session is
chasing is real, but it is entangled with the instability in §2 — the same
prompt refused in one run and answered in the next.

## 8. What was done about it (to 2026-09-24)

Each finding, and where it stands. Nothing below is merged to `main`.

1. **Outcome under-classification (§5)** — fixed in the CX lane, `a50e5a4`:
   route-delivered refusals are typed `safety_refusal`, and the order-status
   question types the same way in every market and language.
2. **Misleading capture field (§2)** — fixed, `e45c062`: each case now
   records the evidence gate's own decision in `evidence_decision`, separately
   from the delivered citations in `approved_evidence`.
3. **Cross-language evidence loss, cash payment (§3)** — fixed in retrieval,
   `bd95ba1`: a market's English-only editions are now also searched with an
   English rendering of the question. Taken unchanged from `a3a6571`.
4. **False income refusals (§2, §7)** — two code fixes were written and
   reviewed. `c0733e5` was rejected: an adversarial review found 46 real
   income claims it newly allowed, including "Forever doesn't guarantee
   income but I guarantee you'll earn $2,000 a month". The governance half of
   `a3a6571` also leaked, and a hardened version was blocked by the local
   permission policy as a security weakening. The owner chose the prompt-only
   route instead, as the 2026-09-12 reviews did for the same problem:
   `053af80` tells the model not to quote "guarantee", even from a source.
   The refusal code is unchanged. Whether the model follows the rule is
   verifiable only live.
5. **Invalid US + Russian journeys (§6)** — not yet corrected in the
   manifest; deliberately left until the next manifest is cut, because the
   manifest's hash identifies all captures made so far.

The combined verification build is `9bb03f9` on
`verify/r10d-income-and-cx-20260924` (income fixes, CX lane and capture
isolation together, because `main` lacks the metrics isolation). Its live
capture is approved as `R10D-2026-09-24-KRISH`.

Still owed: the result of that capture, human-written expectations for the
75 journeys, native-speaker review of the non-English copy, and the paired
baseline run, which waits on confirming which build is actually deployed.
