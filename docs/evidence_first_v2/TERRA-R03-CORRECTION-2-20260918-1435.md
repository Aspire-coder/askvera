# Terra handoff - R03 correction 2

Date: 2026-09-18 14:35 -04:00  
Scope: R03 lowercase Finnish place correction only, local and offline.  
Next owner: fresh Sol review, then Astra. R04 remains paused.

## Sol finding and reproduction

Sol found that R03 correction 1 considered only capitalized Finnish inessive
place tokens. With Tanzania in the stored history, lowercase `ugandassa`,
`berliinissa`, and `atlantisissa` therefore retained Tanzania.

Lowercase controls were added before the code correction:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/evidence_first_v2/test_r03_context_capture.py -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c2-before' -ra
```

Pre-fix result: **3 failed, 8 passed, exit 1**. The failures showed both
lowercase unknown/unconfigured places borrowing Tanzania and a configured
lowercase inessive form failing to replace it.

## Bounded correction

`_finnish_anaphoric_place_resolution` now considers a lowercase inessive form
only in the existing Finnish anaphoric grammar shape when it is the terminal
term after Finnish `on` or `asuu`. Capitalized inessive handling is unchanged.
The configured, exact base-plus-`ssa` map remains the only way to resolve and
canonicalize a lowercase market. A lowercase unconfigured or unknown inessive
candidate returns unresolved and stays standalone. A lowercase role/anaphoric
follow-up without a location candidate keeps its stored context.

This is configuration-derived and Finnish-grammar-bound. It adds no country
list, English keyword rule, or session-country substitution. R02, the R03
capture/audit guard, capitalized controls, no-history behavior, cross-session
isolation, frozen content, and unrelated dirty work remain unchanged.

## Changed paths

- `app/orchestrator/chat_orchestrator.py`
- `tests/evidence_first_v2/test_r03_context_capture.py`
- `docs/evidence_first_v2/CURRENT_STATUS.md`
- this handoff

## Verification

Focused suite:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/evidence_first_v2/test_r03_context_capture.py tests/unit/test_demo_multilingual_followups.py tests/unit/test_demo_followup_resolution.py tests/unit/test_retrieval_canary_delivered_answer.py tests/unit/test_retrieval_rank_list_capture.py -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c2-focused' -ra
```

Result: **429 passed, exit 0**.

Compatibility suite:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/unit/test_chat_orchestrator.py tests/unit/test_evidence_routing.py tests/unit/test_opensearch_sections.py tests/unit/test_retrieval_service.py tests/unit/test_retrieval_rank_list_capture.py tests/evidence_first_v2 -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c2-compatibility' -ra
```

Result: **468 passed, 1 failed, exit 1**. The sole failure is the pre-existing,
separately queued V2 isolation allowlist mismatch for `capture_provenance` in
`scope_aware_fusion.py`; it was not edited here.

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

`c473e9b659de67a529546d902621848f0d6e7848a29fc8136e4166e99cf30ce8`

The digest is SHA-256 over canonical UTF-8 `path`, LF, each selected file's
lowercase SHA-256, and one final LF. It covers the R03 code/test set from
correction 1: `app/orchestrator/chat_orchestrator.py`,
`scripts/evidence_first_v2/capture_read_only_retrieval.py`,
`scripts/evidence_first_v2/finalize_read_only_capture.py`, and
`tests/evidence_first_v2/test_r03_context_capture.py`. Manifest: 463 bytes.

No AWS, network, OpenSearch, live model, push, merge, deployment, reindex,
installation, or frozen-fixture edit occurred. This local correction is not
release evidence. R03 correction 2 now awaits a fresh Sol review.
