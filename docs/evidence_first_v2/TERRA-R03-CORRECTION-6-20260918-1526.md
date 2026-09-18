# Terra handoff - R03 correction 6

Date: 2026-09-18 15:26 -04:00  
Scope: R03 configured-form boundary and provenance honesty only, local/offline.  
Next owner: fresh Sol review, then Astra. R04 remains paused.

## Astra finding and correction

Sol approved R03 correction 5's ambiguity policy. Astra then reproduced that
the one-modifier/terminal location rule missed exact configured forms in these
natural follow-ups after Tanzania history:

- `Entä jos hän asuu nyt pysyvästi ugandassa?`
- `Entä jos hän asuu edelleen ugandassa?`
- `Entä jos hän asuu ugandassa ja työskentelee siellä?`

Those forms retained Tanzania and were recorded as
`resolved_dependent_follow_up`. The prior R03 docstring also overstated the
unknown-lowercase rule by describing `työskentelee` as a residence cue.

The smallest compatible correction uses the existing configuration-derived
inessive-form map on whole normalized tokens across the already-bounded
Finnish anaphoric follow-up. An exact configured form now wins independent of
modifier count, terminal position, punctuation, or later clause text. No cache
entries, countries, substring matching, or modifier vocabulary were added.

For an unknown lowercase inessive form, only the bounded `asuu` phrase remains
strong enough to make the current request standalone. Ambiguous lowercase
complements after `on` or `työskentelee` retain ordinary conversational context
but now use the existing contract-compatible `unresolved` provenance status,
without a prior-turn ID. `capture_provenance.validate_context_resolution`
already permits exactly that status, and V2 fusion treats only
`resolved_dependent_follow_up` as trusted fallback context. No contract schema
change was necessary.

## Controls

The R03 controls now cover Astra's three exact phrases, arbitrary additional
modifiers, a configured token inside a longer clause, punctuation/case,
all-caps configured form, exact-token substring control, ordinary nouns,
unknown/unconfigured forms, no history, cross-session behavior, and existing
capture/audit guards. The new config matcher never treats `pseudougandassa` as
Uganda.

## Changed paths

- `app/orchestrator/chat_orchestrator.py`
- `tests/evidence_first_v2/test_r03_context_capture.py`
- `docs/evidence_first_v2/CURRENT_STATUS.md`
- this handoff

## Verification

Focused suite:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/evidence_first_v2/test_r03_context_capture.py tests/unit/test_demo_multilingual_followups.py tests/unit/test_demo_followup_resolution.py tests/unit/test_retrieval_canary_delivered_answer.py tests/unit/test_retrieval_rank_list_capture.py -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c6-focused' -ra
```

Result: **455 passed, exit 0**.

Compatibility suite:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/unit/test_chat_orchestrator.py tests/unit/test_evidence_routing.py tests/unit/test_opensearch_sections.py tests/unit/test_retrieval_service.py tests/unit/test_retrieval_rank_list_capture.py tests/evidence_first_v2 -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c6-compatibility' -ra
```

Result: **494 passed, 1 failed, exit 1**. The sole failure is the unchanged,
separately queued V2 isolation allowlist mismatch for `capture_provenance` in
`scope_aware_fusion.py`.

Scoped lint:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m flake8 --ignore=E203,E402,E501,C901 app/orchestrator/chat_orchestrator.py scripts/evidence_first_v2/capture_read_only_retrieval.py scripts/evidence_first_v2/finalize_read_only_capture.py tests/evidence_first_v2/test_r03_context_capture.py
```

Result: **exit 0**. `git diff --check`: **exit 0**.

## Snapshot and limits

Base HEAD: `5b1d33fe37167e2a1384e47ac0fa1fe08ea3aee7`.

Selected-file snapshot SHA-256:

`b4026bdc628ec5c7b64354e79beb606f819fa0ced3aabe55b7cb1232d93f730d`

The digest covers the same four R03 code/test files as the earlier corrections,
using canonical UTF-8 path/hash lines and a final LF (463 bytes). It identifies
the selected dirty worktree state, not a release or production result.

No AWS, network, OpenSearch, live model, deployment, push, merge, reindex,
installation, or frozen-fixture edits occurred. R03 correction 6 awaits fresh
Sol review, then Astra. R04 remains paused.
