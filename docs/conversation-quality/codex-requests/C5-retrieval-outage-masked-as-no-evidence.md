# Codex interface request: a retrieval outage is reported as missing evidence (task C5)

From: conversation-quality coordinator, 2026-09-18. Drafted by Lane C and
reproduced by the independent reviewer (Fable). Reproduction tightened by
Lane E (Phase 2, dependency distinction task), 2026-09-18.
Affected file: `app/retrieval/opensearch_sections.py`, which Codex owns and
this project has not edited.

**Status: RESOLVED by Codex's own accepted contract, R02.** R02 adds
`RetrievalResult.availability`, a `RetrievalAvailability` enum with
`AVAILABLE`, `DEGRADED` (at least one retrieval channel failed but another
completed), and `UNAVAILABLE` (no channel completed). Codex's orchestrator
hook routes `UNAVAILABLE`, and `DEGRADED` with no usable final evidence
after country-scope reapproval, to `failure_layer=dependency_unavailable`
with the `bedrock_error` copy. That satisfies this request directly and is a
broader, more accurate signal than the two-value flag originally requested
below (it distinguishes a total outage from a partial one, which a boolean
flag cannot).

**Lane E's own `provider_unavailable` metadata-flag design (previously
proposed in this document) is WITHDRAWN**, in favor of R02. Nothing in this
project defines or checks a `provider_unavailable` key any more; the
`app.orchestrator.dependency_contract` module that briefly defined it has
been reduced to exception classification only (see below), and the
orchestrator patch (`docs/conversation-quality/phase2/patches/
laneE-dependency-wiring.patch`) contains no post-retrieval metadata check.
This section of the document is kept below as a historical record of the
reproduction and the withdrawn proposal, not as an open ask.

## What Lane E still needs from integration (not from Codex directly)

At the point the coordinator combines Codex's R02 orchestrator hook with
Lane E's `_dependency_unavailable_response` helper (added by the patch
above), both of R02's two routing sites should call that same helper,
passing a real `retrieval_availability` value ("unavailable" or "degraded")
so that:

- the `DependencyUnavailable` metric
  (`app.metrics.responses.record_dependency_unavailable`) fires with
  `component="retrieval"` and the matching `availability` dimension value,
  instead of only the exception-escape paths firing it, and
- the delivered response's own metadata carries `retrieval_availability`
  for anyone inspecting the answer (not only the metric).

This is an integration note for the coordinator, not a Codex interface
change -- R02 itself needs nothing further from Codex to satisfy the
original ask.

## What happens (historical -- the problem R02 fixes)

`OpenSearchSectionProvider.retrieve` (around line 1638) catches
`OpenSearchException` and returns an ordinary empty result:

```python
except OpenSearchException:
    LOGGER.exception("opensearch_section_retrieval_failed", correlation_id=correlation_id)
    return RetrievalResult(documents=[], citations=[], confidence=0.0, metadata={...})
```

`OpenSearchException` is the base class for opensearchpy's `ConnectionError`,
`ConnectionTimeout`, `SSLError` and `AuthenticationException`. None of these
subclass Python's built-in `ConnectionError`.

Downstream, an unreachable backend and a backend that ran the query and found
nothing look exactly alike:

- The user is told the approved policy documents "do not contain enough
  information" (`failure_layer=evidence_gate`). That is a confident and false
  statement about the corpus.
- `RetrievalService.retrieve` records `success=True`, so the `RetrievalHealth`
  alarm does not see the outage either.

## Reproduction (historical; re-run 2026-09-18, this repository, real code)

Kept as evidence of the bug R02 fixes -- this was run against the code as it
stood before R02's routing existed. It is not a live check of current
behavior; the fix for exactly this scenario is R02, in Codex's worktree.

A faked `opensearchpy` client whose `.search` raises
`opensearchpy.exceptions.ConnectionTimeout`, wired in place of the real
client by monkeypatching `opensearch_sections._client` -- no source file
edited. Run:

```python
from unittest import mock
from opensearchpy.exceptions import ConnectionTimeout
from app.retrieval import opensearch_sections
from app.retrieval.opensearch_sections import OpenSearchSectionProvider
from app.retrieval.service import RetrievalService

class _FakeClientThatTimesOut:
    def search(self, *_args, **_kwargs):
        raise ConnectionTimeout("connection timed out")

with mock.patch.object(opensearch_sections, "_client", return_value=_FakeClientThatTimesOut()):
    service = RetrievalService(provider=OpenSearchSectionProvider())
    result = service.retrieve("What is the minimum order for Kenya?", "KE", "en", "fbo", "c5-repro")
```

Today's outcome, observed directly (not inferred):

```
documents: []
confidence: 0.0
metadata: {'provider': 'opensearch_section'}
record_retrieval_outcome(success=...) calls: [True]
```

1. `RetrievalService.retrieve` returns zero documents **without raising**
   (confirmed: `except OpenSearchException` at
   `app/retrieval/opensearch_sections.py:1638` catches
   `ConnectionTimeout`, a subclass, and returns an ordinary empty
   `RetrievalResult` with no `provider_unavailable` key at all).
2. `record_retrieval_outcome(success=True)` is recorded (confirmed: the
   `finally` block in `RetrievalService.retrieve`,
   `app/retrieval/service.py:53-70`, only sees whether `provider.retrieve`
   raised past it, which it did not).
3. Downstream, `retrieval_dependency_unavailable(result)` (see the contract
   below) returns `False` for this result, so the orchestrator's evidence
   gate treats it exactly like a query that ran and matched nothing, and
   the user is told the documents "do not contain enough information" --
   a false statement about the corpus.

## What the conversation side does now, updated 2026-09-18 (post-R02)

`AIOrchestrator._handle_scrubbed_chat` catches any dependency failure that
*escapes* the retriever (`AwsServiceError` from the embedding path,
`BotoCoreError`, `ClientError`, built-in `ConnectionError`/`TimeoutError`/`OSError`)
or the generator (`BedrockTimeoutError`/`BedrockServiceError`). It answers
with the localized `bedrock_error` copy under
`failure_layer=dependency_unavailable`, and emits a dedicated
`DependencyUnavailable` CloudWatch metric
(`app.metrics.responses.record_dependency_unavailable`; dimensions
`component` = `retrieval`/`embedding`/`generation` and `availability` =
`unavailable`/`degraded`/`exception` -- see
`docs/conversation-quality/phase2/DEPENDENCY_ALARM_SPEC.md` for the proposed
alarm on it). The reproduced failure above never escapes the provider, so
that catch alone still cannot help with it -- which is exactly the gap R02
closes, on Codex's side, via `RetrievalResult.availability` rather than via
anything in this project's `app/orchestrator/dependency_contract.py`.

This is delivered as a reviewable patch
(`docs/conversation-quality/phase2/patches/laneE-dependency-wiring.patch`,
pending coordinator integration because `chat_orchestrator.py` is a
single-writer file) plus tests
(`tests/conversation/test_dependency_orchestrator_wiring.py`, three cases
`xfail(strict=True)` on the Lane E branch precisely because the patch is not
yet integrated) and deterministic exception-classification tests
(`tests/conversation/test_dependency_contract.py`).

`app/orchestrator/dependency_contract.py` now only classifies an exception
caught at the `retrieve()`/`generate()` call sites into a bounded
`component` label for the metric (`AwsServiceError` -> `"embedding"`,
everything else in the recognized set -> `"retrieval"`). It defines no
`RetrievalResult` predicate and imports nothing from `app/retrieval/**`, so
it cannot compete with or duplicate R02.

## Acceptance (satisfied by R02; recorded for closure)

- With `client.search` raising `ConnectionTimeout` (or any
  `OpenSearchException` subclass caught for a transport/timeout/auth
  reason), the delivered answer carries `failure_layer=dependency_unavailable`
  and the technical-problem copy, never the missing-evidence copy: satisfied
  by R02's `UNAVAILABLE` routing.
- Retrieval health (`record_retrieval_outcome`) records the failure, not the
  `success=True` shown in the reproduction above: satisfied by R02 (Codex's
  side; not re-verified in this document).
- A query that runs and genuinely matches nothing is unchanged: it still
  gets `evidence_gate` and the missing-evidence copy. R02's `AVAILABLE`
  value (or `DEGRADED` with usable final evidence) must not route to
  `dependency_unavailable` -- this is Codex's own contract to keep, not
  re-defined here.
- The `DependencyUnavailable` metric fires exactly once per such outage once
  both the orchestrator patch above AND Codex's R02 routing call the shared
  `_dependency_unavailable_response` helper with a real
  `retrieval_availability` value (see "What Lane E still needs from
  integration" above) -- not zero times, and not more than once per
  request.
