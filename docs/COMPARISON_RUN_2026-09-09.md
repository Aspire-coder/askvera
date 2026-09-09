# Current versus Candidate — run of 2026-09-09

The first paid comparison of these candidates against delivered answers. Six
cases, one run per arm, on the deployment host.

**The original result is recorded here unchanged.** A revised evaluation using
corrected expectations follows it, separately labelled. The revision does not
replace the original record; the two answer different questions.

## Arms

| | Revision | Expansion flag |
|---|---|---|
| Current | `c5391bb7dbffdbba6e005ec871d824b2fa094a50` | `absent` |
| Candidate | `40932ce87c5579fc90457f963a06fa1ed28834d4` | `true` |

Same harness, same fixture `2bccac2bcfb59d24832f459c5d3b7352fb44a41ee07603c5629000ce023bf62c`,
same index `askvera-policy-sections`, same model
(`global.anthropic.claude-haiku-4-5`), generation pointer on, 28 active
generation rows, semantic cache off.

`c5391bb` is the pre-change candidate baseline, **not production**. `main` is
`bde45fb`, and the branch between them carries work not measured here.

## Original result, as scored on the day

| | Current | Candidate |
|---|---|---|
| correct | 3/6 | 2/6 |
| cited | 4/6 | 2/6 |
| false abstention | 2/6 | 4/6 |
| retrieval hit | 4/6 | 4/6 |
| latency p50 | 7432 ms | 7391 ms |

Per case:

| Case | Current | Candidate |
|---|---|---|
| `reunion-delivery-cost` | refusal, `evidence_gate` | refusal, `evidence_gate` |
| `reunion-delivery-cost-bare-name` | refusal, `evidence_gate` | refusal, `evidence_gate` |
| `france-minimum-order` | answered | answered |
| `algeria-repeat-order-minimum` | answered | refusal, `output_validator` |
| `algeria-existing-fbo-order-minimum-role` | answered, scored FAIL | refusal, `output_validator` |
| `algeria-delivery-cost` (control) | answered | answered |

## What the answers showed

**The score overstated Current.** Two answers it delivered contain claims about
the reader that nothing supports:

> "For context, **your first order as a Preferred Customer** requires 0.200 CC"

> "**Your first order as a Preferred Customer was** 0.200 CC… Once you have
> completed that initial order…"

The reader had said "after my first purchase" and "I am already an FBO".
Neither said they were a Preferred Customer. One of these scored **correct**,
because `must_contain: ["5"]` passes on any answer containing a five.

**The candidate's detection was right and its response was wrong.** It flagged
both, and then refused the entire answer instead of removing the sentence.

**Réunion failed in both arms, and expansion changed nothing.** Identical
sections retrieved by both (`13.01`, `US:13.01`, …) - US company policy, not
the Réunion directory record. Expansion added queries (7→9 and 6→8) and the
retrieved set did not move. `retrieval_hit` false in both.

**France was already correct in both arms**, including the €150 / 72-hour
condition, so candidate C had no gap to close here. It fired
(`directory_order_size_restored`, `directory_role_label_corrected`) and
produced an equivalent answer. Not shown to help; not shown to harm.

**The control held.** `algeria-delivery-cost` answered 900 DZD in both.

## Revised evaluation — a different question, not a replacement

The expectations above could not distinguish a correct answer from one
containing an invented claim. They were tightened to cover the amount, the
currency, the role a rule applies to and the stage it applies at, and to forbid
the phrasings that assert what a reader has done - the last checked from the
answer text, so the benchmark is not relying on the validator it is meant to
be measuring.

Scored offline against the **captured answers**, with no new model calls. The
candidate column is the fixed repair applied to those same answers, which tests
the repair against the exact failures; it is not what the candidate's own
generation would produce.

| Case | Current, as delivered | Fixed repair applied |
|---|---|---|
| `algeria-repeat-order-minimum` | **FAIL** - invented claim, and 0.200 | pass |
| `algeria-existing-fbo-order-minimum-role` | **FAIL** - invented claim, and 0.200 | pass |
| `algeria-delivery-cost` | pass | pass |
| `france-minimum-order` | pass | pass |

Two cases in the fixture are not scorable this way: both Réunion cases refused
in both arms and there is no answer to rescore.

## Réunion: where the record is excluded

Established from the run: the required section `sponsoring-084-r-union-island`
was not retrieved by either arm, and the sections that were retrieved are US
company policy.

Established locally by reading the code, not by running retrieval:

- `_directory_target_country_names` resolves the question to
  `{"Reunion Island", "Reunion Islands"}` - correct, and the same shape as
  Algeria, which works.
- `include_global_documents` is forced true whenever a market is named, so the
  global directory search does run.
- `_record_country_filter` builds its terms through `_normalize_text`, which
  applies NFKC and casefold and **does not strip diacritics**. So
  `"Réunion Island"` normalises to `"réunion island"` while the filter asks for
  `"reunion island"`.

**Hypothesis, not yet confirmed:** the record's indexed
`metadata.record_country` carries the accent, the filter does not, and the
document is excluded before ranking. The section id `sponsoring-084-r-union-island`
is consistent with an accented title but is not proof of the field's value.

If that holds, it means accent handling *is* the problem and query-text
expansion could never have fixed it, because the document never reaches
ranking. It would also mean an accent-folded content index would not have
fixed it either.

**Confirm before changing anything.** One free query, no model calls:

```
cd ~/askvera-cmp-20260908 && /opt/askvera/.venv/bin/python - <<'EOF'
import logging; logging.disable(logging.INFO)
from config import settings
settings.load_ssm_config()
from app.retrieval.opensearch_sections import _client
body = {"size": 5, "query": {"match": {"section_id": "sponsoring-084-r-union-island"}},
        "_source": ["id", "section_id", "metadata.record_country", "country", "access_scope"]}
for hit in _client().search(index=settings.OPENSEARCH_INDEX, body=body)["hits"]["hits"]:
    print(hit["_source"])
EOF
```

Expansion and any index change stay paused until that output is read.

## Confirmation

Nothing merged, nothing deployed. `main` remains `bde45fb`. The candidate
branch is pushed only. Both arms read production retrieval and called Bedrock;
no document, index or database row was written.
