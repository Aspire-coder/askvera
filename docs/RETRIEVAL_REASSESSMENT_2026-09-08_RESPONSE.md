# Response to the 2026-09-08 reassessment

Date: 2026-09-08 (overnight)
Reviewed against: `aa8d812` (deployed), work branched from `main`

I verified each substantive claim against the code rather than accepting it.
Four branches are pushed and awaiting your approval. Nothing is merged.

## Verification of the review's claims

| Claim | Verdict | Evidence |
|---|---|---|
| Evidence contract accepts "Income is guaranteed." | **Confirmed** | Reproduced: the sentence yields 2 content tokens against a threshold of 4, so coverage skips it. Skipping means accepting. |
| `EVIDENCE_GATED_OUTPUT_ENABLED` still defaults false | **Confirmed, and stronger than stated** | Default is false *and* production does not override it — it is absent from the deployed `config_effective_snapshot`. `_apply_evidence_contract` returns before parsing. The contract is dormant, not merely unhardened. |
| `_page_has_image` misses nested Form XObjects | **Confirmed** | Only `/Subtype == /Image` directly on the page was checked. |
| Resource-tree errors categorise uncertainty as blank | **Confirmed, and consequential** | `except Exception: return False` is indistinguishable from "no image", after which a no-text page is filed as a blank separator and `requires_ocr` stays false. A scanned page behind a malformed resource tree was published with its content missing from the corpus. |
| Benchmark is five abstention-only pilot cases | **Confirmed** | It is labelled as such in the fixture, and its stated job is harness validation and cost measurement. |
| Refusal detection is English-only | **Confirmed** | A correct French refusal scored as a wrong answer. |
| Source scoring is top-title containment | **Confirmed** | One title covers every market in the sponsoring directory. |
| Citation count is not citation correctness | **Confirmed** | Only presence was checked. |
| Skipping restoration can leave the fact missing | **Confirmed as a risk** | Well-formed is not complete. In the deploy that exercised it the answer happened to carry the figure, which was luck. |
| Two numeric exemptions are fixed | **Confirmed** | Matches tonight's canary: 22/22 blocking, no repair firing. |

I found no claim in the review that was wrong. One is understated — see below.

## What I changed (four branches, unmerged)

**1. `fix/preflight-nested-images-and-unknown-pages`** — the most consequential.
Image detection now descends into Form XObjects with a depth cap. Pages whose
image content could not be established are reported in a new
`undetermined_page_numbers`, count towards `has_unextracted_pages`, and require
OCR. They are deliberately *not* folded into `blank_page_numbers`: "we found
nothing" and "we could not look" support opposite decisions, and only one is
safe to publish unread. A genuine blank separator is still blank — pinned by a
test, so the distinction cannot turn every empty page into a suspected scan.
All three new tests fail on the previous code.

**2. `fix/benchmark-scorer-fidelity`** — all three measurement gaps.
Refusal markers are built per locale from the same approved copy the system
delivers. Cases can name `required_sections` and are scored against section IDs
actually retrieved. A case requiring citations now checks the governing sections
are the ones *cited*. A case naming no source is left **unscored** rather than
counted as a hit, and the summary reports the unscored count beside the rate.

**3. `test/pin-evidence-contract-short-claim-gap`** — pinned, not fixed, on
purpose. See the disagreement below.

**4. `chore/sample-algeria-before-promoting`** (from earlier tonight) — the
Algeria case now runs 5× per deploy and stays observed-only.

## Where I disagree, or would sequence differently

**The contract gap should not be fixed yet.** Closing it means either scoring
short sentences strictly — which would reject ordinary replies like "Yes, you
can." — or judging materiality by keyword, which is precisely the special-casing
this review warns against. Both need the false-rejection measurement the review
itself says must come first. I pinned the behaviour in a test so it cannot drift
silently, and left the fix for after measurement. Fixing it now would be doing
the thing the document argues against, in the name of the document.

**The dormancy finding is understated.** The review lists
`EVIDENCE_GATED_OUTPUT_ENABLED` under a general caveat about live enablement.
It deserves to be a headline: the entire evidence-contract layer — parsing,
coverage, section binding — does not execute in production. Section 2's
hardening work has no effect on delivered answers until that flag is turned on,
and turning it on is a larger decision than any item in the table. I would
promote "decide whether to enable the contract, with false-rejection data" to
its own P0.

**"Repair event is not automatically damage" (section 4) is right, and the
canary currently gets this wrong.** `answer_must_not_remove_numbers` treats any
removal as failure. Tonight's Algeria run removed four figures and I could not
tell whether they were invented or real, so I shipped `removal_diagnostics` to
report, per figure, whether it appears in the evidence at all. That is the
labelling section 4 asks for, and it should drive the assertion rather than a
blanket "no removals".

## What I did not do, and why

- **No answerable benchmark cases.** They require corpus text that exists only
  in the live index. `scripts/dump_corpus_sections.py` (read-only) is ready;
  authoring cases from memory would produce a benchmark that measures the
  assumption rather than the system, which the loader now refuses.
- **No hybrid/selector experiments, no confidence calibration.** The review
  sequences these last and I agree.
- **No OCR end-to-end verification, no table-fidelity work.** Needs real PDFs
  and a running ingestion path.

## Open question for you

The Algeria answer now delivered reads:

> "the minimum first order size is **0.200 CC** (approximately 7,800 DZD or $60)
> **when signing up as a Preferred Customer**"

The question asked about a new **FBO**. If Algeria's record genuinely says
enrolment begins as a Preferred Customer, this is correct. If not, the bot is
answering a role question with another role's rule — every figure correctly
sourced, and the answer still wrong. No grounding work catches that. It needs
the Algeria record:

```
python scripts/dump_corpus_sections.py --load-ssm --out corpus_dump --country DZ
```

---

# Addendum: corpus shape, measured 2026-09-08

`dump_corpus_sections.py --inventory` against the live index. This changes where
the remaining benchmark cases should go, so it is recorded rather than left in a
chat log.

## The corpus is not shaped like our tests

| Group | Sections | Share | Test coverage |
|---|---:|---:|---|
| Benelux + Nordic policy (BE, NL, FI, SE, DK, NO, LU) | 12,179 | 68.1% | none |
| US policy | 858 | 4.8% | most policy cases |
| UK policy | 728 | 4.1% | none |
| Global sponsoring directory | 113 | 0.6% | most directory cases |
| Others (IT, KG, CA, AT, CH, DE, RS) | 4,018 | 22.4% | none |

Every retrieval case we have — canary and benchmark — targets US policy or the
sponsoring directory. That is **971 of 17,896 sections, 5.4% of the corpus**,
and the directory alone carries almost all of the market-specific work done
this week despite being 0.6% of it.

The inversion is worth stating plainly: the most-tested document is the
smallest, and two thirds of the corpus has never been queried by any test.

## Near-identical documents distinguished only by country

Section counts are exactly equal within each of these groups, which means the
same policy is indexed once per country:

| Group | Documents | Sections each |
|---|---|---:|
| Nordic English | DK-EN, FI-EN, NO-EN, SE-EN | 788 |
| Benelux Dutch | BE-NL, NL-NL | 774 |
| Benelux French | BE-FR, NL-FR | 763 |
| Benelux English | BE-EN, NL-EN | 693 |
| German | AT-DE, CH-DE, DE-DE | 183 |

Retrieval must therefore separate four Nordic copies of the same English text,
and three German copies, **on the country tag alone** — the passages themselves
are the same words. A scope failure here does not produce a visibly wrong
answer: it produces a correct-looking policy statement from the wrong country,
correctly grounded, correctly cited, and wrong for the reader.

No test covers this. The one scope case we have (US session reaching Belgium
sponsoring) exercises the opposite path: a global document that is *supposed*
to cross markets.

## What this changes about the plan

The review's "80-120 cases across key intents" still holds, but the allocation
should follow the corpus rather than our habits:

1. **Country discrimination within a duplicate family** — highest value per
   case, and currently zero coverage. Ask the same question as a Dutch FBO and
   a Belgian FBO and require each to cite its own country's section. If the
   rules are identical the case still proves scope; where they differ it proves
   correctness.
2. **Non-English policy** — 17 of 28 documents are not in English (IT-IT, KG-RU,
   FI-FI, SE-SV, DK-DA, NO-NO, CA-FR, BE-NL, NL-NL, BE-FR, NL-FR, LU-FR, US-ES,
   AT-DE, CH-DE, DE-DE, RS-SR). The benchmark is currently entirely English, and
   the refusal-detection fix earlier today only became necessary because of it.
3. **Benelux and Nordic policy facts** — 68% of the corpus, no coverage.
4. Directory cases are now well covered and should not be extended further
   without reason.

## Caveat on what any of this can claim

13 cases is 0.07% of the corpus; even 120 would be 0.7%. That is enough to
detect systematic failures on covered intents and never enough to certify the
corpus. Any published rate must state the denominator and the markets it
covers.

---

# Addendum 2: 55.6% of the corpus carries no effective date

Measured 2026-09-08 with `--inventory` after two wrong versions of the check.
The reported figure is now corroborated by a sampled section in the same output
(`consistent: true`).

## Scale

**15 of 28 documents, 9,951 of 17,896 sections (55.6%), have no effective date.**

| Dated | Undated |
|---|---|
| IT-IT, SE-EN, UK-EN, US-EN, AT-DE, CH-DE, DE-DE, BE-EN/NL/FR, NL-EN/NL/FR | CA-EN, CA-FR, DK-DA, DK-EN, FI-EN, FI-FI, KG-RU, LU-EN, LU-FR, NO-EN, NO-NO, RS-SR, SE-SV, US-ES, International-Sponsoring-Directory |

## Why it matters

`unsupported_requested_years` keys date-scope protection off `effective_date`
and `document_version`, and returns nothing when a document carries neither.
Asked "what was the FBO support fee in 2024?", a market with dates refuses with
*period not covered*; a market without them answers from current documents as
though the current rule had always applied.

So the protection is inert for 55.6% of the corpus, and — worse than being
uniformly off — it is **inconsistent within a single market**:

- **Sweden**: SE-EN dated, SE-SV undated. The same question about a past year
  is refused in English and answered in Swedish.
- **US**: US-EN dated, US-ES undated. Same split between English and Spanish.
- **Benelux**: BE and NL copies dated in all three languages; the Luxembourg
  copies of the *same policy* are undated.

The English/other-language split in Sweden and the US is the sharpest form: a
reader's protection depends on the language they chose, not on anything about
the policy.

**The entire sponsoring directory is undated** (all 113 global sections), so no
directory answer has date scope at all.

## An anomaly worth a look

`CA-EN-Company-Policy.pdf` reports `versioned_sections: 737` and
`dated_sections: 0` — it carries a document version but no effective date. It
is the only document in that state, which suggests a partial metadata write
rather than a whole job missing its dates.

## What this is not

This is not a retrieval bug and nothing here is wrong per document. Undated
sections are still retrieved, still grounded and still cited; the Algeria
directory answers work fine. It is a metadata gap whose only visible symptom is
a market answering a dated question it should arguably decline.

## Suggested handling

The fix is re-ingestion with `effective_date` and `document_version` set, which
is an operational decision rather than a code change. Two things are worth
settling first:

1. **What should an undated document do?** Today it answers any year. Refusing
   every dated question against undated evidence would be consistent but would
   turn a silent gap into 55.6% of the corpus refusing year-qualified
   questions. That is a product decision, not a technical one.
2. **Whether the split is deliberate.** If some documents genuinely have no
   effective date — the sponsoring directory plausibly does not — then the
   right answer is different per document type, and the directory should be
   excluded from the count rather than fixed.

---

# Addendum 3: the index does not fold accents

Measured 2026-09-08 against the live index, with ASCII controls:

| Phrase searched | Sections matched |
|---|---:|
| `Reunion` | **0** |
| `Réunion` | 6 |
| `Algeria` (control) | 9 |
| `Belgium` (control) | 3 |

An unaccented query cannot match accented document text. The controls rule out
a broken test.

## How it was found

`reunion-delivery-cost` was the only benchmark case to fail on retrieval rather
than on a later layer: `governing sections not retrieved`, with a top score of
1.398 against 9.5 for comparable directory questions. Market detection was
never the problem - `Reunion` is a configured alias and resolves to RE
correctly - so the failure had to be in matching the document text.

## Why it is wider than one market

Only one configured market name carries an accent (Saint-Barthélemy), which
makes this look small. It is not, for two reasons.

**The config and the corpus disagree.** `global_directory_markets.json` calls it
"Reunion Island"; the record in the index is titled "Forever Réunion Island".
The ingestion pipeline mangled the accent when generating the section id, which
reads `sponsoring-084-r-union-island` - the `é` was dropped rather than folded,
so the damage is already visible in the identifier.

**Fifteen of twenty-eight documents are not in English.** Italian, Finnish,
Swedish, Danish, Norwegian, French, Spanish, German, Serbian and Russian policy
documents carry accented and non-Latin text throughout, and 1,871 accented
alias spellings are configured across the markets. Readers routinely type
without diacritics. Every one of those queries is currently matching less text
than it should on the lexical channel.

This does not mean those questions fail outright: hybrid retrieval still has a
vector channel, which is presumably why the corpus has worked as well as it
has. It means the lexical half is silently degraded for a large part of the
corpus, and nothing measures that today.

## Options

Corrected on review. An earlier version of this section recommended reindexing
outright. That was too fast: one failing question does not establish that every
accented-language problem has the same cause or the same fix, and changing an
index analyser is not reversible in the way a code change is.

**First, inspect rather than change.** Read the active analyser on
`askvera-policy-sections` and confirm what it does with diacritics on both the
indexing and the query side. The counts above show a symptom; they do not show
which analyser stage produces it, and a query-side normaliser could be
responsible rather than the mapping.

**Then measure on a candidate, not on the active index.** Build a candidate
index with an asciifolding filter, replay a fixed set of questions with and
without diacritics against both, and compare retrieved section IDs. That is a
metamorphic property - the same question in two spellings should retrieve the
same sections - and it is what would establish that folding fixes the general
case rather than this one record.

**Preserve distinctions that matter.** Folding is not free in every language.
Where a diacritic distinguishes two different words, folding merges them, and
the corpus spans French, Spanish, German, the Nordics, Serbian and Russian.
Whether that trade is acceptable per language is a decision for someone who
reads those languages, not a default.

Query-side alias expansion remains a poor substitute for the general fix: it
would make one benchmark case pass while accented content words stayed
unmatched. It may still be worth having as a narrow mitigation for market names
once the analyser question is settled, but not as a way of closing this.

## What to measure once it is settled

Recall on the same question with and without diacritics should be equal, per
language. That is cheap to test and belongs in the generated suite rather than
as a one-off case.

---

# Addendum 4: two claims corrected

Both were mine, both were asserted rather than established, and both were
challenged in review on 2026-09-08.

**"Dynamic translation is right."** I wrote that a reader needs an answer in
their language either way, and treated that as settling the question. The first
half is true; the conclusion is a product and governance judgement, not a
technical finding. Seven locales - Italian, Danish, Finnish, Norwegian,
Serbian, Swedish, Russian - receive a live model translation of English refusal
copy, constrained to add no facts, numbers or contacts, but not reviewed and
not necessarily identical between two requests. Whether that is acceptable for
copy a reader is told is approved policy communication is a decision for
whoever owns that wording. It stands as an open quality gap, not a resolved
design choice.

**"Recommended: reindex."** Corrected in the Options section above. Inspect the
analyser, measure a candidate index, and decide per language whether folding
loses a distinction that matters, before changing anything.
