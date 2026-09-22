# Terra handoff - R03 correction 5

Date: 2026-09-18 15:07 -04:00  
Scope: R03 Finnish ambiguity correction only, local and offline.  
Next owner: fresh Sol review, then Astra. R04 remains paused.

## Sol finding, reproduction, and policy

Sol found that a lowercase complement after `työskentelee` is ambiguous: it can
be a place or an ordinary noun. The prior R03 rule asserted a place and dropped
history for both cases.

Before the correction:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/evidence_first_v2/test_r03_context_capture.py -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c5-before' -ra
```

Result: **5 failed, 27 passed, exit 1**. The failures were unknown or ordinary
lowercase complements after `työskentelee` retaining no Tanzania context.

The bounded fail-closed policy is now:

- Exact configuration-derived lowercase market forms can replace context after
  `asuu`, `on`, or `työskentelee`, optionally with `nyt`.
- Unknown lowercase inessive forms can break context only after `asuu`,
  optionally with `nyt`.
- Unknown lowercase complements after `on` or `työskentelee` retain context as
  ambiguous. This is intentional: R03 cannot honestly claim they are places.
- Existing capitalized unknown-place behavior remains separate and unchanged.

This changes no configured-form cache, adds no countries or noun lexicon, and
does not scan unrestricted tokens. R02, the capture/audit guard, frozen content
and unrelated V2 work remain unchanged.

## Changed paths

- `app/orchestrator/chat_orchestrator.py`
- `tests/evidence_first_v2/test_r03_context_capture.py`
- `docs/evidence_first_v2/CURRENT_STATUS.md`
- this handoff

## Verification

Focused suite:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/evidence_first_v2/test_r03_context_capture.py tests/unit/test_demo_multilingual_followups.py tests/unit/test_demo_followup_resolution.py tests/unit/test_retrieval_canary_delivered_answer.py tests/unit/test_retrieval_rank_list_capture.py -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c5-focused' -ra
```

Result: **450 passed, exit 0**.

Compatibility suite:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/unit/test_chat_orchestrator.py tests/unit/test_evidence_routing.py tests/unit/test_opensearch_sections.py tests/unit/test_retrieval_service.py tests/unit/test_retrieval_rank_list_capture.py tests/evidence_first_v2 -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c5-compatibility' -ra
```

Result: **489 passed, 1 failed, exit 1**. The one failure is the unchanged,
separately queued V2 isolation allowlist mismatch for `capture_provenance` in
`scope_aware_fusion.py`.

Scoped lint:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m flake8 --ignore=E203,E402,E501,C901 app/orchestrator/chat_orchestrator.py scripts/evidence_first_v2/capture_read_only_retrieval.py scripts/evidence_first_v2/finalize_read_only_capture.py tests/evidence_first_v2/test_r03_context_capture.py
```

Result: **exit 0**. `git diff --check`: **exit 0**.

## Snapshot and limitations

Base HEAD: `5b1d33fe37167e2a1384e47ac0fa1fe08ea3aee7`.

Selected-file snapshot SHA-256:

`3ce3d7ea7441233dbb69c6babdd16d1c103da7cbd4fbdec9047621515d2d19ec`

The digest covers the same four R03 code/test files as prior corrections using
canonical UTF-8 path/hash lines and a final LF (463 bytes). It is a dirty-
worktree identity, not a release or production claim.

No AWS, network, OpenSearch, live model, deployment, push, merge, reindex,
installation, or frozen-fixture edit occurred. R03 correction 5 awaits fresh
Sol review; R04 remains paused.
