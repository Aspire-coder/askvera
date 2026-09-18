# Terra handoff - R03 correction 1

Date: 2026-09-18 14:21 -04:00  
Scope: R03 correction only, local and offline.  
Next owner: fresh Sol review, then Astra. Do not start R04.

## Review finding and reproduction

Sol returned **NEEDS CORRECTION** on the first R03 snapshot. This correction
preserves accepted R02 work, unrelated dirty V2 work, Claude's worktree, the
frozen fixture, and the known isolation allowlist mismatch.

The pre-fix controls showed four failures:

- `Atlantisissa` and `Berliinissä` after Tanzania history inherited Tanzania.
- `Ugandassa` retained Tanzania rather than replacing it.
- `--audit-generations-only` invoked audit work before the multi-turn guard.

Exact pre-fix command:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/evidence_first_v2/test_r03_context_capture.py -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c1-before' -ra
```

Result: **4 failed, 3 passed, exit 1**.

## Correction

For a Finnish `Entä jos hän/hänen ...` follow-up, the orchestrator now checks
a capitalized current-turn `-ssa/-ssä` location before retaining history.
It resolves only a configured market or configured localized alias with the
exact safe base-plus-`ssa` form and replaces that token with the configured
display name in the retrieval query. Any unknown, unconfigured, ambiguous, or
unsupported inflected place stays standalone. It never substitutes session
country or prior-market context.

This is a narrow Finnish grammar rule based on configured market data, not a
country, role, or topic list. It changes a validated new destination from
Tanzania to Uganda without hardcoding either market. Unsupported Finnish
declensions intentionally remain standalone rather than being guessed. The
valid no-place Manager follow-up and no-history controls still behave as before.

The capture guard now runs immediately after every pack load in `main`, before
validation, audit, or retrieval capture. The older guards in `_capture` and the
checkpoint finalizer remain as defense in depth. A multi-turn pack therefore
fails before configuration, client creation, or audit work; single-turn audit
packs remain eligible.

## Changed paths

- `app/orchestrator/chat_orchestrator.py`
- `scripts/evidence_first_v2/capture_read_only_retrieval.py`
- `scripts/evidence_first_v2/finalize_read_only_capture.py`
- `tests/evidence_first_v2/test_r03_context_capture.py`
- `docs/evidence_first_v2/CURRENT_STATUS.md`
- this handoff

## Verification

Focused behavior command:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/evidence_first_v2/test_r03_context_capture.py tests/unit/test_demo_multilingual_followups.py tests/unit/test_demo_followup_resolution.py tests/unit/test_retrieval_canary_delivered_answer.py tests/unit/test_retrieval_rank_list_capture.py -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c1-focused' -ra
```

Result: **425 passed, exit 0**. Controls cover unknown and unconfigured
Finnish places, configured inflected-market replacement, no history, the valid
Finnish Manager/role follow-up, topic/market changes, cross-session behavior,
and truthful capture fields.

Compatibility command:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/unit/test_chat_orchestrator.py tests/unit/test_evidence_routing.py tests/unit/test_opensearch_sections.py tests/unit/test_retrieval_service.py tests/unit/test_retrieval_rank_list_capture.py tests/evidence_first_v2 -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c1-compatibility' -ra
```

Result: **464 passed, 1 failed, exit 1**. The only failure is the pre-existing,
separately queued `scope_aware_fusion.py` `capture_provenance` allowlist
mismatch. This correction did not edit that package, import, or allowlist.

Standard lint command:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m flake8 app/orchestrator/chat_orchestrator.py scripts/evidence_first_v2/capture_read_only_retrieval.py scripts/evidence_first_v2/finalize_read_only_capture.py tests/evidence_first_v2/test_r03_context_capture.py
```

Result: exit 1 for two legacy-file findings outside this correction: `C901` on
the pre-existing `_capture` complexity and `E402` on pre-existing finalizer
import placement. The selected legacy files also have the established line-
length baseline.

Scoped changed-file lint command, using only established baseline exclusions:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m flake8 --ignore=E203,E402,E501,C901 app/orchestrator/chat_orchestrator.py scripts/evidence_first_v2/capture_read_only_retrieval.py scripts/evidence_first_v2/finalize_read_only_capture.py tests/evidence_first_v2/test_r03_context_capture.py
```

Result: **exit 0**. The raw lint result above is recorded rather than hidden.

```powershell
git diff --check
```

Result: **exit 0**.

## Stable snapshot identity

Base HEAD: `5b1d33fe37167e2a1384e47ac0fa1fe08ea3aee7`

R03 correction 1 selected-file snapshot SHA-256:

`2b6ba4bbc2604e009f19e79472696b0f38f28a6185dbcba6c4e0cf7bfc48b3af`

The digest is SHA-256 over canonical UTF-8 `path`, LF, and each selected file's
lowercase SHA-256, plus one final LF. It covers
`app/orchestrator/chat_orchestrator.py`,
`scripts/evidence_first_v2/capture_read_only_retrieval.py`,
`scripts/evidence_first_v2/finalize_read_only_capture.py`, and
`tests/evidence_first_v2/test_r03_context_capture.py`. The manifest was 463
bytes. It identifies a selected dirty-worktree state, not a commit, release,
or deployment.

## Limits and next review

- No AWS, network, OpenSearch, live model, push, merge, deploy, reindex,
  installation, or frozen-fixture modification occurred.
- Local checks do not prove live ranking, answer quality, or release readiness.
- R03 correction 1 awaits fresh Sol review. Astra review follows only after
  Sol's verdict. R04 remains paused.
