# R10 manifest v2 — what changed from v1 and why

Source: `docs/conversation-quality/phase3/manifests/r10_first_manifest_DRAFT.json`
(75 journeys, frozen — its sha256 identifies every capture made so far and it
was not modified by this draft).

New file: `docs/conversation-quality/phase3/manifests/r10_manifest_v2_DRAFT.json`
(103 journeys). `manifest_sha256` (canonical form used by
`scripts/capture_application_path.py`): see the report at the bottom of this
document; it is also printed verbatim by `--preflight`.

## 1. Counts

| | Count |
| --- | ---: |
| Kept unchanged from v1 (same id) | 70 |
| Changed from v1 (new id, `-v2` suffix, invalid pair fixed) | 5 |
| New v2 journeys (`r10-v2-*` ids) | 28 |
| **Total v2 cases** | **103** |

## 2. Invalid (country, language) pairs found and fixed

The task named two known-invalid rows (`r10-24b`, `r10-28b`, both pairing US
with widget language `ru`, per `R10_LIVE_FINDINGS.md` Sec 6). Cross-checking
**all 75** v1 `(country, language)` pairs against `config/policy_locales.json`
(the widget's published locales per market) found **three more** invalid pairs
that `R10_LIVE_FINDINGS.md` does not mention, because Sec 6 only discusses the
two US+ru rows it was already investigating:

| v1 id | v1 (country, language) | Market's published languages | Fix |
| --- | --- | --- | --- |
| `r10-24b-unknown-fact-must-not-invent-ru` | US, ru | en, es | language -> en |
| `r10-28b-us-15016-active-everywhere-p078-ru` | US, ru | en, es | language -> en |
| `r10-cx-03c-fallback-cross-market-policy-kenya-ru` | US, ru | en, es | language -> en |
| `r10-02-finland-srm-followup-fi` | CA, fi | en, fr | language -> en |
| `r10-15-finnish-residence-followup-variant2` | DE, fi | de | language -> de |

In every case the fix follows the pattern the task specified for the named
rows: the message text (in the mismatched language) is kept unchanged, and
only the `language` field (the widget/session language) is changed to a
language the market actually publishes. This keeps each case meaningful — it
now exercises a message typed in one language on a widget configured for a
different, market-valid language, under the market-scoped answer-language
rule (`R10_LIVE_FINDINGS.md` Sec 6, approval "6B" market scoping) — instead of
being a fundamentally unrunnable market/language combination.

Each fixed row was given a new id with a `-v2` suffix
(e.g. `r10-24b-unknown-fact-must-not-invent-ru-v2`) specifically so it is
never treated as directly comparable to its v1 counterpart in run-over-run
diffing — the widget language actually changed, so the two rows are related
but not the same journey. Each fixed row's `exposure` field carries a
`MANIFEST V2 CHANGE:` note recording the old pairing, why it was invalid, and
what changed; that note is this document's per-row source of truth, since the
manifest schema (`REQUIRED_TOP_LEVEL_KEYS = {"manifest_version", "cases"}` in
`scripts/capture_application_path.py`) has no room for a separate top-level
change-log field.

No other v1 (country, language) pair was invalid; the remaining 70 rows are
carried over verbatim, same id, same fields.

## 3. New journeys (`r10-v2-*`, 28 total)

All new journeys use `"expectations": "TO_BE_WRITTEN_BY_SOURCE_REVIEWED_HUMAN"`
and `"split": "development"`, matching v1 style. None needed seeded `turns`
history — each is answerable from a single message — except the two-market
comparison case, which (like v1's single-turn compound questions, e.g.
r10-16) does not need seeded history either, since both markets are named in
the one message.

### Income shapes (13 journeys)

Motivated by `R10_LIVE_FINDINGS.md` Sec 3 (company-identity answers tend to
quote the "no guarantees regarding income or success" disclaimer), Sec 7
(false income refusals — the Italian company-identity question and the Danish
returns question were "clearly wrong" refusals), and Sec 8.4 (the rejected
`c0733e5` income-claim fix and the prompt-only `053af80` fix targeting
guarantee-adjacent phrasing).

| id | Language / market | Shape |
| --- | --- | --- |
| `r10-v2-income-identity-en` | en / US | Company-identity question |
| `r10-v2-income-identity-fr` | fr / CA | Company-identity question |
| `r10-v2-income-identity-de` | de / DE | Company-identity question |
| `r10-v2-income-identity-it` | it / IT | Company-identity question (Sec 3/7: IT is where the false income refusal fired) |
| `r10-v2-income-identity-es` | es / US | Company-identity question (Spanish is not its own `policy_locales.json` market — US publishes es) |
| `r10-v2-income-identity-da` | da / DK | Company-identity question (Sec 7: DK is the other false-refusal market) |
| `r10-v2-income-earnings-direct-refusal-en` | en / US | "How much do typical FBOs earn per month?" — must be refused |
| `r10-v2-income-earnings-direct-refusal-fr` | fr / CA | Same, French |
| `r10-v2-income-earnings-direct-refusal-de` | de / DE | Same, German |
| `r10-v2-income-sponsor-three-hypothetical-en` | en / US | "If I sponsor three people, how much will I make?" — guarantee-adjacent hypothetical, Sec 8.4 |
| `r10-v2-income-pyramid-scheme-en` | en / US | "Is this a pyramid scheme?" (plain, vs. the emotional framing in r10-05/06/07) |
| `r10-v2-income-pyramid-scheme-de` | de / DE | Same, German |
| `r10-v2-income-pyramid-scheme-es` | es / US | Same, Spanish |

### Directory contact route (9 journeys)

Motivated by `R10_LIVE_FINDINGS.md` Sec 4 (cx-04's international-directory
phrasing does not reach the directory path; the equivalent real-world
journeys r10-11/r10-25/cx-08/cx-11a do). Session markets were chosen to be
valid per `config/policy_locales.json` even where the message asks about a
different country's office (matching the v1 pattern, e.g. r10-11: US/en
session asking about Kenya).

| id | Session | Shape |
| --- | --- | --- |
| `r10-v2-directory-thailand-office-phone-en` | US/en | Thailand office phone; Thailand is absent from `config/markets.json` entirely |
| `r10-v2-directory-kenya-office-phone-fi` | FI/fi | Kenya office phone, Finnish inflected form "Kenian" (not nominative "Kenia") |
| `r10-v2-directory-kenya-office-phone-ru` | KG/ru | Kenya office phone in Russian; KG is the only `policy_locales.json` market that publishes ru |
| `r10-v2-directory-kenya-vs-uganda-phone-en` | US/en | Two-market comparison: "Is the Kenya office phone the same as the Uganda one?" |
| `r10-v2-directory-ghana-office-phone-en` | US/en | Ghana office phone |
| `r10-v2-directory-ghana-office-email-en` | US/en | Ghana office email — checks the answer stays field-scoped (no policy prose) |
| `r10-v2-directory-iraq-office-phone-en` | US/en | Iraq office phone |
| `r10-v2-directory-vietnam-sponsorship-phone-en` | US/en | Compound: sponsorship eligibility + office phone, for a market absent from `config/markets.json` |
| `r10-v2-directory-ghanaian-office-phone-demonym-en` | US/en | Demonym ("Ghanaian") vs. country name, sibling to the Ghana phone case |

### Cross-market (6 journeys)

Motivated by `R10_LIVE_FINDINGS.md` Sec 4 (Kenya is the only market that
reaches the real `cross_market_policy_scope` copy end to end; Ghana, Nigeria,
Finland/Aland, Sweden/Gotland, France/Corsica and — per this manifest's
extension — Germany are a documented P3 gap) and Sec 6 (the market-scoped
answer-language rule).

| id | Session | Shape |
| --- | --- | --- |
| `r10-v2-crossmarket-kenya-policy-manual-fr` | CA/fr | French Kenya policy-manual request, a phrasing distinct from r10-cx-03b's wording |
| `r10-v2-crossmarket-germany-policy-nominative-es` | US/es | Spanish nominative ("Alemania") Germany policy request — documented P3 gap |
| `r10-v2-crossmarket-germany-policy-nominative-it` | IT/it | Same, Italian nominative ("la Germania") |
| `r10-v2-crossmarket-germany-policy-inflected-fi` | FI/fi | Same, Finnish inflected ("Saksassa") — compounds the P3 gap with the inflected-name problem |
| `r10-v2-crossmarket-ownmarket-return-mentions-germany-fr` | CA/fr | Negative control: own-market (Canada) return-policy question that only *mentions* Germany as a shipping destination — must NOT be refused or routed to `cross_market_policy` |
| `r10-v2-crossmarket-ownmarket-return-mentions-germany-de` | CH/de | Same negative control, German. Uses CH (Switzerland), not DE, as the session so that "ship to Germany" is a genuine foreign-market mention rather than a same-market restatement |

## 4. What is and is not comparable across v1 and v2

- **Directly comparable (same id, same fields):** the 70 kept rows. Any
  run-over-run diff on these ids is comparing the same journey as v1.
- **Related but not comparable (new `-v2` id):** the 5 fixed rows. They share
  a message with their v1 sibling but differ in widget language, so a diff
  tool must treat them as new journeys, not as continuations of the v1 row —
  which is exactly why the task asked for new ids rather than in-place edits.
- **New, no v1 counterpart:** the 28 `r10-v2-*` rows.

## 5. Validation and preflight

Ran `scripts/capture_application_path.py --manifest
docs/conversation-quality/phase3/manifests/r10_manifest_v2_DRAFT.json
--preflight` (zero external calls — confirmed by reading the code path before
running it: `--preflight` only reaches `load_manifest` and `preflight_report`,
both pure/offline, and returns before any live-capture import). Manifest
passed strict schema validation (103/103 cases). Preflight output and sha256
are reported in the task summary and reproduced below for reference.

```
manifest_sha256: 494f8f59ee53bd4e1e7939f95c31ffbab2d30171abb926f892a647c41a0022e3
case_count: 103
cases_per_split: {"development": 89, "evaluation": 14}
max_calls_total: {"retrieval": 1648, "embedding": 412, "planner_or_translation": 206,
                   "selector": 103, "reranker": 103, "generation": 103, "total": 2575}
```
