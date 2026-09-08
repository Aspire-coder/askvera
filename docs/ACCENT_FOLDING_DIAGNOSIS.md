# Réunion, and why unaccented spellings retrieve nothing

Read-only diagnosis, 2026-09-08. No model calls, no generation, no writes. The
corpus was not touched.

## The failing layer, isolated

The benchmark case asks *"What is the delivery cost for orders in **Reunion**
Island?"* — unaccented. The corpus writes **Réunion**. Against the live index:

```
content match_phrase "Reunion"  -> 0 hits
content match_phrase "Réunion"  -> 6 hits
```

Layer by layer, deterministically:

| Layer | Behaviour | Contributes? |
|---|---|---|
| Country resolution | `find_market_mentions` returns `RE` for **both** spellings | No |
| Index mapping | `content` is `{"type": "text"}`; the index body has no `settings.analysis` at all | **Yes** |
| Analyser | default `standard`: lowercases, does not fold diacritics | **Yes** |
| Generation-side filters | the record is `country: GLOBAL, access_scope: global`, and the global generation pointer resolved to a real ingestion id in preflight | Not implicated |

Proved with the read-only `_analyze` API:

```
standard analyzer   "Forever Réunion Island" -> ['forever', 'réunion', 'island']
standard analyzer   "Reunion Island"         -> ['reunion', 'island']

with asciifolding   "Forever Réunion Island" -> ['forever', 'reunion', 'island']
with asciifolding   "Reunion Island"         -> ['reunion', 'island']
```

The document token is `réunion`, the query token is `reunion`, and nothing
folds either. With an `asciifolding` filter both sides become `reunion` and
they match.

**Not tested:** whether vector retrieval would have surfaced the record
regardless. Embedding a query is a paid `invoke_model` call and the
investigation was to stay generation-off. The pilot did retrieve zero documents
for this turn, which is consistent with the vector path not rescuing it, but
that is an observation and not an attribution.

**Not tested:** what the LLM query planner emitted for this turn. The capture
does not record generated queries — a gap. Even so, a planner emitting the
user's own spelling fails lexically, which is sufficient to explain the miss.

## This is not one market

Scanning every active section's title:

| | |
|---|---|
| Active sections | 17,799 |
| Titles containing a diacritic | **5,181 (29.1%)** |

| Market | Accented titles | of |
|---|---:|---:|
| CA | 600 | 1,509 |
| SE | 578 | 1,574 |
| NL | 573 | 2,221 |
| BE | 572 | 2,222 |
| FI | 506 | 1,576 |
| LU | 504 | 1,389 |
| NO | 324 | 1,559 |
| KG | 323 | 847 |
| DK | 263 | 1,567 |
| IT | 263 | 983 |
| US | 220 | 852 |
| DE | 117 | 183 |

Among the 113 global sponsoring-directory sections, exactly one has an accented
title — Réunion — which is why this surfaced there first.

**Read this carefully.** It counts titles that *contain* a diacritic, not
queries that fail. A query fails only when a reader types the unaccented form
of an accented term and lexical matching is the deciding path. The correct
statement is that the exposure spans at least twelve markets rather than one,
and Réunion is one confirmed instance.

## The fix is a reindex, not a patch

Folding only the query does not help: the indexed tokens still carry their
diacritics, so both sides must be folded. That means a custom analyser on the
index, and an analyser change applies only to newly indexed documents — the
17,799 existing sections would have to be reindexed to benefit.

So this needs:

1. an index definition with `asciifolding` (a new index, or a mapping with a
   folded subfield),
2. a reindex of the corpus into it,
3. a measured comparison on the same questions before switching retrieval over,
   because folding merges tokens that some languages keep distinct.

None of that is a code change to merge. It is a corpus operation needing its
own authorisation and its own before/after measurement.

## What would confirm it end to end

Re-running `reunion-delivery-cost` against a folded index and seeing it retrieve
`sponsoring-084-r-union-island` and answer 6EUR. Until then the diagnosis is
established at the analyser and the customer outcome is not.
