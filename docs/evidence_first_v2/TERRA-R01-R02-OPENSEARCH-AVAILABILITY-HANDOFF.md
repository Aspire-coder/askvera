# Terra handoff - R01/R02 OpenSearch availability contract

Date: 2026-09-18  
Scope: local-only Evidence-First V2 R01 and R02.  
Reviewer: Sol. Do not start R03 from this handoff.

## Decision and boundary

R01 reconciled the dirty V2 baseline and marked the historical output status
as non-authoritative for current work. The authoritative summary is
`CURRENT_STATUS.md`; no historical evidence was deleted or rewritten.

R02 implements Claude's existing C5 provider-side request without touching
Claude's worktree. It adds a small typed availability field to retrieval
results, rather than raising a broad new exception or treating every error as
transient:

| State | Meaning | User/health behavior |
| --- | --- | --- |
| `available` | One or more searches completed, including a genuine empty result | Existing evidence-gate behavior; health success. |
| `degraded` | A channel failed but another completed | Preserve usable evidence and record failed channels; health success. |
| `unavailable` | Every attempted OpenSearch channel failed | Return localized technical-dependency copy before evidence gate; health failure. |

`RequestError` and local `_client()` configuration errors remain visible for
diagnosis. Guardrail/configuration exceptions are not caught or converted, and
no retry behavior was added. Embedding exceptions remain on Claude's existing
dependency-error path.

## Exact R02 files changed

- `app/retrieval/models.py`
- `app/retrieval/__init__.py`
- `app/retrieval/service.py`
- `app/retrieval/opensearch_sections.py`
- `app/orchestrator/chat_orchestrator.py`
- `tests/unit/test_opensearch_sections.py`
- `tests/unit/test_retrieval_service.py`
- `tests/unit/test_chat_orchestrator.py`
- `tests/unit/test_retrieval_rank_list_capture.py`

Some listed integration files were already dirty V2 files at R01 start.
Review R02 as focused availability/health hunks only; do not attribute the
separate V2-09/V2-10 work to this milestone.

## Reproduction before the change

With a fake client that raised `opensearchpy.ConnectionTimeout`, the original
provider returned an ordinary empty `RetrievalResult`:

```text
documents=0, confidence=0.0, metadata={provider: opensearch_section}
```

That made a total provider outage indistinguishable from missing evidence;
the retrieval service recorded success and the orchestrator reached the
evidence gate.

## Controls and results

Using the absolute repository Python runtime, task-owned `--basetemp`, and
`-p no:cacheprovider`:

| Command scope | Result |
| --- | --- |
| R02 provider, service, orchestrator, rank-capture and health suites | **290 passed** |
| V2 contracts/fusion/ranking/replay compatibility subset plus rank capture and health | **156 passed** |
| Targeted flake8 | clean |
| `git diff --check` | clean |
| V2 isolation/audit check | **19 passed, 1 known baseline failure**; the pre-existing V2-10 relative-import allowlist mismatch is recorded in `CURRENT_STATUS.md`, untouched by R02. |

Focused controls prove:

1. timeout, connection and authentication failures produce `unavailable`;
2. a completed empty text/vector result remains `available`;
3. a failed vector channel plus successful text result remains `degraded` and
   retains the text evidence;
4. `RequestError` and local client configuration failure are not relabelled;
5. health records `success=False` for `unavailable`; and
6. the orchestrator produces `dependency_unavailable`, never an
   `evidence_gate` missing-evidence response, for `unavailable`.

## Stable review identity

- Base HEAD: `5b1d33fe37167e2a1384e47ac0fa1fe08ea3aee7`
- R02 file-set binary diff SHA-256: `6a3ce5149ce46c10e93129234956e6245da10c1a1b142d1c711509196d12cc44`

Generate the same identity from the nine exact R02 files above, not from the
whole dirty worktree. It is intentionally independent of this handoff and
other pre-existing V2 changes.

## Limitations and non-claims

- No real OpenSearch, Bedrock, AWS or production traffic was used.
- This confirms typed local behavior, not live availability, alarm routing or
  end-user answer quality.
- A partial failure remains a health success because retrieval has usable
  evidence; failed channels are explicitly exposed. Whether that should page
  is an observability policy decision outside R02.
- R03 and all ranking, capture, integration and release milestones remain
  untouched.
