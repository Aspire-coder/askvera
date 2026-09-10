# Unaccented spellings retrieve nothing — diagnosis and candidate remedies

Read-only, 2026-09-08. No model calls, no generation, no writes. The corpus was
not touched.

## Bookkeeping correction, first

An earlier version of this document reported 17,799 active sections against the
pilot's 17,896. **The corpus did not change and nothing was filtered — the scan
was wrong.**

`section_id` is not unique: 17,896 active documents share **3,770** distinct
section ids, because markets hold identical sections under the same id.
`search_after` paging sorted only on `section_id` silently skips documents when
the sort key repeats. Re-paged with `(section_id, _id)`, the scan returns
exactly 17,896 — matching the `count` API.

Every figure below is recomputed on the complete set.

## What is established

The benchmark case asks *"delivery cost for orders in **Reunion** Island"*;
the corpus writes **Réunion**.

| Layer | Behaviour | Contributes? |
|---|---|---|
| Country resolution | `find_market_mentions` returns `RE` for both spellings | No |
| Index mapping | `content` is plain `{"type": "text"}`; no `settings.analysis` at all | Yes |
| Analyser | default `standard`: lowercases, does not fold diacritics | Yes |
| Generation filters | record is `GLOBAL`/`global`; the global pointer resolved normally | Not implicated |

Proved with the read-only `_analyze` API: the document tokenises to `réunion`,
the question to `reunion`; with `asciifolding` both become `reunion`.

**This establishes an accent-sensitive lexical mismatch. It does not fully
explain the pilot's zero documents.** Two links remain unverified: what the LLM
query planner emitted (the capture does not record generated queries — a gap),
and whether vector retrieval would have surfaced the record anyway (embedding is
a paid call and this stayed generation-off).

## Exposure, not a failure rate

Of **17,896** active sections, **5,212 (29.1%)** have a diacritic in the title:

| Market | Accented | of | |
|---|---:|---:|---:|
| CA | 602 | 1,520 | 40% |
| SE | 583 | 1,584 | 37% |
| NL | 576 | 2,230 | 26% |
| BE | 576 | 2,230 | 26% |
| LU | 507 | 1,398 | 36% |
| FI | 507 | 1,587 | 32% |
| NO | 326 | 1,572 | 21% |
| KG | 323 | 847 | 38% |
| DK | 265 | 1,578 | 17% |
| IT | 263 | 985 | 27% |
| US | 223 | 858 | 26% |
| AT / DE | 117 each | 183 each | 64% |

**This is exposure, not a 29.1% retrieval failure rate.** A query fails only
when a reader types the unaccented form of an accented term and lexical
matching decides the outcome. Réunion is one confirmed instance.

## Remedy A — country-name expansion, no index change

The catalogue already carries approved spelling variants. `RE` holds
`Reunion`, `Reunion Island`, `Reunion Islands`, `Réunion`, `La Réunion`,
`Reunión`, `Riunione` and more; every market has equivalents in
`market_name_aliases.json`. Nothing needs hard-coding.

Tested against the live index, global scope, `status: active`:

```
question wording only ("Reunion Island")     -> 0 hits
expanded with approved catalogue names       -> sponsoring-084-r-union-island (4.12)
                                                sponsoring-063-france         (2.77)
```

The governing record is retrieved, top-ranked, **with no reindex**. The France
record also matches, which is plausible — the French office covers Réunion —
but any implementation should confirm expansion does not dilute ranking.

**Country-boundary safety**, checked:

```
"Guinea"            -> GN        "Equatorial Guinea" -> GQ
"Reunion"           -> RE        "La Reunion"        -> RE
```

Longest-name matching holds. One observation to check separately:
`"Democratic Republic of the Congo"` resolves to `CG`, not `CD` — possibly
because `CD` is not a configured market, but it should be confirmed rather than
assumed.

This addresses **country names only**. It does nothing for accented words in
ordinary policy text.

## Remedy B — a folded field alongside the original, not instead of it

Blanket accent-stripping is **not safe**, and the live corpus shows why:

| Language | Accented | Count | Unaccented | Count |
|---|---|---:|---|---:|
| French | `à` | 1,312 | `a` | 9,122 |
| Danish | `så` | 75 | `sa` | 348 |
| Norwegian | `får` | 202 | `far` | 11 |

These are distinct words in their own languages — Norwegian *får* (gets/sheep)
against *far* (father) — and folding merges them. Replacing the live analyser
would trade one class of miss for another.

So: a **separate folded subfield searched alongside** the original, letting an
exact-accent match keep its higher weight. That still requires an isolated
candidate index, a reindex into it, and a measured comparison across the
affected languages before any switch — and approval before creating or
populating it.

## Recommended order

1. **Remedy A** — country-name expansion, using the catalogue. Tested feasible
   above; not yet wired into retrieval.
2. **Remedy B** — candidate index, on approval, with language-pair tests
   including the merging pairs above and country-boundary cases.
3. A small end-to-end comparison confirming the delivery answer and its
   citation, not merely that a section is retrieved.

Kept separate, deliberately: decimal interpretation, minimum-order
completeness, and the invented purchase history.
