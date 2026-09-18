# Codex interface request: a retrieval outage is reported as missing evidence (task C5)

From: conversation-quality coordinator, 2026-09-18. Drafted by Lane C and
reproduced by the independent reviewer (Fable).
Affected file: `app/retrieval/opensearch_sections.py`, which Codex owns and
this project has not edited.
Status: open. This blocks the retrieval half of C5 only.

## What happens

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

## Reproduction

Run offline with a faked client (independent reviewer, scratchpad
`p1_outage.py`): make `client.search` raise
`opensearchpy.ConnectionTimeout`. Then:

1. `RetrievalService.retrieve` returns zero documents without raising.
2. `record_retrieval_outcome(success=True)` is recorded.
3. The orchestrator delivers `failure_layer=evidence_gate` with the
   missing-evidence copy.

## What the conversation side already does

`AIOrchestrator._handle_scrubbed_chat` catches any dependency failure that
*escapes* the retriever (`AwsServiceError` from the embedding path,
`BotoCoreError`, `ClientError`, built-in `ConnectionError`/`TimeoutError`/`OSError`).
It answers with the localized `bedrock_error` copy under
`failure_layer=dependency_unavailable`. The failure described above never
escapes the provider, so that catch cannot help with it.

## Requested interface (Codex decides the exact shape)

Pick one:

1. **Flag it.** When a transport, timeout or auth error is caught (as opposed
   to a query that ran and matched nothing), set
   `metadata["provider_unavailable"] = True` on the returned result, and record
   `success=False` for retrieval health. The orchestrator will then route the
   flag to `dependency_unavailable` before the evidence gate. That wiring is
   about five lines on this side, plus a test.
2. **Raise it.** Re-raise as `AwsServiceError` (or a new
   `RetrievalUnavailableError(AskVeraError)`). The existing orchestrator catch
   handles `AwsServiceError` already, with no further change.

Option 2 needs no change on this side. Option 1 keeps any partial-failure
behaviour Codex relies on.

## Acceptance

- With `client.search` raising `ConnectionTimeout`, the delivered answer
  carries `failure_layer=dependency_unavailable` and the technical-problem
  copy, never the missing-evidence copy.
- Retrieval health records the failure.
- A query that runs and genuinely matches nothing is unchanged: it still gets
  `evidence_gate` and the missing-evidence copy.
