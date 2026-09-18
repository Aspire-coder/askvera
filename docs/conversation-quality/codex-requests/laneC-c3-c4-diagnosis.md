# C3/C4 diagnosis from the graded US workbook (diagnosis only, time-boxed)

**Source:** `us_testing_cases.md` (178 graded cases, all `RESULT: None` -
ungraded by a human yet). Read-only input; not modified.
**Scope note:** `app/evidence.py` (the evidence gate) is a shared boundary
with Codex's evidence selection and was NOT edited. This document is
diagnosis and a request, not a patch.

## C4: supported fact refused - a clear, repeated pattern (5+ cases)

Every case below names a SPECIFIC, numbered policy section in the workbook's
own "sec" column, i.e. the grader believes the fact is directly supported,
and every one got the exact same generic fallback:

> "The approved policy documents currently available do not contain enough
> information to answer this question clearly. Please rephrase the question
> or contact Forever Living support for an official answer."

| Case | Question | Supported by | Most likely failure layer |
|---|---|---|---|
| P001 | "What is Forever Living Products?" | sec 1.01(a) - basic company description | Evidence gate / query formation. Note: got the income_claim disclaimer text verbatim, not the generic fallback - see below. |
| P068 | "Can I pay cash?" | sec 13.01(c) - lists accepted payment forms (cash absent) | Evidence gate / retrieval - a negative inference over a listed set |
| P078 | "If I'm active here am I active everywhere?" | sec 15.01(b)(6) - Home-Country Active status propagation | Retrieval - specific, less-common cross-reference rule |
| P091 | "What happens if I go a whole year without qualifying?" | sec 6.05(a),(b) - Manager forfeiture / Inherited Managers | Retrieval - specific, less-common rule |
| P104 | "Can I have a stall at a weekend market?" | sec 16.02(e)(1) - temporary-exhibition carve-out | Retrieval - specific, less-common rule |
| P167/P168/P170 | Emotionally-framed variants of the same May-2026-change facts already answered correctly elsewhere in the same workbook (e.g. P003) | sec 1.01(c)/(d)/(e) | Retrieval or prompt sensitivity to emotional phrasing of an otherwise-covered topic |

**Most likely failure layer, overall:** retrieval not surfacing the specific
section for a differently-phrased or less-common query, OR the evidence
approval gate (`app/evidence.py::approve_evidence`, Codex/shared boundary)
scoring the retrieved section below its approval threshold even when it was
returned. Both are outside Lane C's file boundary (`app/retrieval/**` is
Codex-owned; `app/evidence.py` is explicitly called out as shared and not to
be edited here).

**P001 is the sharpest case and deserves its own line:** this exact question
- "What is Forever Living Products?" - is also the C1 (company-identity
income disclaimer) example on the conversation-quality task board. Lane C
verified on this worktree's B1 baseline that the deterministic
`_verified_conversation_intent` bypass in `app/retrieval/providers.py`
already catches a false-positive `income_claim` label for this exact string
without a model call (see
`tests/conversation/test_intent_company_identity_and_purchasing.py`,
committed earlier this round). The workbook's `ACTUAL` for P001 is the
income_claim disclaimer verbatim, which the current B1 code should not
produce. Two explanations are consistent with everything observed:
1. The workbook was captured against a deployment that predates the
   income-bypass fix (the task board itself records "production uncertainty"
   - B0 was requested for deployment 2026-09-17 but never confirmed live,
   and B1 is ahead of production by four locally-merged branches including
   this exact fix).
2. Something about the LIVE semantic classifier's confidence or the live
   session's exact `country`/`role`/`language` values differs from what was
   tested offline, keeping the bypass from firing in production even though
   it fires in this offline harness.

**Not reproducible purely offline for P068/P078/P091/P104/P167/P168/P170:**
these depend on the real retrieval ranking and evidence-approval scoring
against the real ingested US Company Policy document, which requires a live
or fixture-backed OpenSearch index this worktree does not have. P001 IS
reproducible offline (and was reproduced, in Lane C's favor) via the
`_verified_conversation_intent` bypass.

## C3: unsupported fact answered confidently - no clear case found

A systematic scan of the workbook (regex over every case whose `MUST NOT`
forbids an invented number/date/name/figure, checking whether `ACTUAL`
contains one anyway) found exactly one candidate, and it is disputed by the
workbook's own author:

**P144** - "What's the minimum order in the UK?" - graded category "N. Not
in the document", `MUST`: "This document covers the United States only."
`ACTUAL` answered with a specific UK figure (£75) drawn from the directory
record. The workbook's own `NOTES` column already flags this: *"can be
answered as this si [sic] from global sponsor document"* - i.e. the grader
believes the `MUST` expectation itself is wrong, because the UK figure
legitimately comes from the International Sponsoring Directory (a different,
valid approved document), not from the US Company Policy the rest of the
workbook is graesed against. This looks like a correctly-answered
cross-document case, not a hallucination, and is not put forward as a C3
defect.

No other case in the 178 examined showed a confident invented figure, date,
name or policy detail where none was supported. Every other "N. Not in the
document" case correctly declined (P140, P141, P145, P146, P148-P151, etc.).

**Conclusion:** within this workbook, C3 (unsupported fact invented) does
not have a clear reproducible example; C4 (supported fact refused) has a
strong, repeated, systemic pattern whose root cause sits in Codex-owned
retrieval/evidence-approval territory. Recommend Codex investigate why
retrieval scoring for less-common, precisely-worded policy cross-references
(15.01(b)(6), 6.05(a)/(b), 16.02(e)(1), 13.01(c), 1.01(a)) falls below
approval even though the workbook's own section citations show the answer
is present in the ingested document.
