# Terra handoff - R03 correction 3

Date: 2026-09-18 14:45 -04:00  
Scope: R03 Finnish false-positive correction only, local and offline.  
Next owner: fresh Sol review, then Astra. R04 remains paused.

## Sol finding and reproduction

Sol found that correction 2 still treated every lowercase Finnish `-ssa/-ssä`
noun after `on` as a new unknown place. With Tanzania in stored history,
valid follow-ups containing `tiimissa`, `johdossa`, or `verkostossa` became
standalone rather than retaining the prior context.

The exact negative controls were added before the correction:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/evidence_first_v2/test_r03_context_capture.py -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c3-before' -ra
```

Pre-fix result: **3 failed, 12 passed, exit 1**. Each ordinary noun after `on`
lost Tanzania context.

## Bounded correction

Lowercase inessive handling now has two separate, grammar-bound cases:

- An exact configured market form can canonicalize after `on` or `asuu`.
- An unknown or unconfigured lowercase form is considered a location only after
  the stronger residence cue `asuu`.

Therefore lowercase `asuu ugandassa` and `on ugandassa` resolve to the
configured market, while lowercase `asuu berliinissa` and `asuu atlantisissa`
remain standalone. Ordinary nouns after `on`, including the reviewed examples,
retain valid history. Capitalized inessive behavior and the existing no-place
role/anaphoric control remain unchanged.

The rule uses configured market data plus the already-recognized Finnish
anaphoric grammar shape. It adds no country list, English keyword behavior, or
general noun lexicon. R02, the capture/audit fail-closed guard, frozen content,
and unrelated dirty V2 work were not changed.

## Claude ownership record

The previous Claude ownership text was a historical read-only observation and
cannot establish Claude's current worktree state. `CURRENT_STATUS.md` now says
that ownership must be refreshed read-only at integration time. This correction
did not inspect or edit Claude's worktree.

## Changed paths

- `app/orchestrator/chat_orchestrator.py`
- `tests/evidence_first_v2/test_r03_context_capture.py`
- `docs/evidence_first_v2/CURRENT_STATUS.md`
- this handoff

## Verification

Focused suite:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/evidence_first_v2/test_r03_context_capture.py tests/unit/test_demo_multilingual_followups.py tests/unit/test_demo_followup_resolution.py tests/unit/test_retrieval_canary_delivered_answer.py tests/unit/test_retrieval_rank_list_capture.py -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c3-focused' -ra
```

Result: **433 passed, exit 0**.

Compatibility suite:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/unit/test_chat_orchestrator.py tests/unit/test_evidence_routing.py tests/unit/test_opensearch_sections.py tests/unit/test_retrieval_service.py tests/unit/test_retrieval_rank_list_capture.py tests/evidence_first_v2 -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c3-compatibility' -ra
```

Result: **472 passed, 1 failed, exit 1**. The only failure is the unchanged,
separately queued V2 isolation allowlist mismatch for `capture_provenance` in
`scope_aware_fusion.py`; it was not edited by R03.

Scoped lint:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m flake8 --ignore=E203,E402,E501,C901 app/orchestrator/chat_orchestrator.py scripts/evidence_first_v2/capture_read_only_retrieval.py scripts/evidence_first_v2/finalize_read_only_capture.py tests/evidence_first_v2/test_r03_context_capture.py
```

Result: **exit 0**.

```powershell
git diff --check
```

Result: **exit 0**.

## Stable snapshot and limits

Base HEAD: `5b1d33fe37167e2a1384e47ac0fa1fe08ea3aee7`.

Selected-file snapshot SHA-256:

`0ae71f22d80f85ca406770e2b7f4bc262d29dfdde37e52a9e05c74211e56a573`

The digest is SHA-256 over canonical UTF-8 `path`, LF, each selected file's
lowercase SHA-256, and one final LF. It covers the R03 code/test set:
`app/orchestrator/chat_orchestrator.py`,
`scripts/evidence_first_v2/capture_read_only_retrieval.py`,
`scripts/evidence_first_v2/finalize_read_only_capture.py`, and
`tests/evidence_first_v2/test_r03_context_capture.py`. Manifest: 463 bytes.

No AWS, network, OpenSearch, live model, push, merge, deployment, reindex,
installation, or frozen-fixture edit occurred. This is local evidence only.
R03 correction 3 awaits fresh Sol review; R04 remains paused.
