# Terra handoff - R03 correction 4

Date: 2026-09-18 14:57 -04:00  
Scope: R03 Finnish location-phrase boundary only, local and offline.  
Next owner: fresh Sol review, then Astra. R04 remains paused.

## Sol finding and reproduction

Sol found that correction 3 only accepted a place immediately after a cue.
Natural Finnish forms with `nyt`, and the strong work-location cue
`työskentelee`, retained Tanzania even when they named a new location.

The new controls were run before the correction:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/evidence_first_v2/test_r03_context_capture.py -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c4-before' -ra
```

Result: **5 failed, 20 passed, exit 1**. Failing controls covered configured
`asuu nyt`, `on nyt`, `työskentelee`, punctuation/case, and unknown location
phrases.

## Bounded correction

`_is_finnish_location_phrase` matches only a terminal inessive token after one
explicit cue, optionally separated by the single safe modifier `nyt`:

- exact configured forms: `on`, `asuu`, or `työskentelee`;
- unknown/unconfigured lowercase forms: only `asuu` or `työskentelee`.

This preserves ordinary nouns after `on`, including `tiimissä`, `johdossa`,
and `verkostossa`, while allowing natural location phrases to either replace
the prior market (configured) or remain standalone (unknown). It does not scan
arbitrary tokens, expand the configured-form cache, add a country list, or
introduce English keyword behavior. R02, previous R03 controls, audit/capture
guard, no-history behavior, frozen content, and unrelated dirty work remain
unchanged.

## Changed paths

- `app/orchestrator/chat_orchestrator.py`
- `tests/evidence_first_v2/test_r03_context_capture.py`
- `docs/evidence_first_v2/CURRENT_STATUS.md`
- this handoff

## Verification

Focused suite:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/evidence_first_v2/test_r03_context_capture.py tests/unit/test_demo_multilingual_followups.py tests/unit/test_demo_followup_resolution.py tests/unit/test_retrieval_canary_delivered_answer.py tests/unit/test_retrieval_rank_list_capture.py -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c4-focused' -ra
```

Result: **443 passed, exit 0**.

Compatibility suite:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/unit/test_chat_orchestrator.py tests/unit/test_evidence_routing.py tests/unit/test_opensearch_sections.py tests/unit/test_retrieval_service.py tests/unit/test_retrieval_rank_list_capture.py tests/evidence_first_v2 -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c4-compatibility' -ra
```

Result: **482 passed, 1 failed, exit 1**. The one failure is the unchanged,
separately queued V2 isolation allowlist mismatch for `capture_provenance` in
`scope_aware_fusion.py`.

Scoped lint:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m flake8 --ignore=E203,E402,E501,C901 app/orchestrator/chat_orchestrator.py scripts/evidence_first_v2/capture_read_only_retrieval.py scripts/evidence_first_v2/finalize_read_only_capture.py tests/evidence_first_v2/test_r03_context_capture.py
```

Result: **exit 0**. `git diff --check`: **exit 0**.

## Stable snapshot and limits

Base HEAD: `5b1d33fe37167e2a1384e47ac0fa1fe08ea3aee7`.

Selected-file snapshot SHA-256:

`989845f580cba99ebe2f8133423d893b58a901f77385c699b08b4b70482c837e`

The digest is SHA-256 over canonical UTF-8 path, LF, each selected file's
lowercase SHA-256, and a final LF. It covers
`app/orchestrator/chat_orchestrator.py`,
`scripts/evidence_first_v2/capture_read_only_retrieval.py`,
`scripts/evidence_first_v2/finalize_read_only_capture.py`, and
`tests/evidence_first_v2/test_r03_context_capture.py` (463-byte manifest).

No AWS, network, OpenSearch, live model, deployment, push, merge, reindex,
installation, or frozen-fixture edit occurred. R03 correction 4 awaits fresh
Sol review. R04 remains paused.
