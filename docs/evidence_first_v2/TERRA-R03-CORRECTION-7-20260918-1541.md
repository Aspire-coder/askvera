# Terra handoff - R03 correction 7

Date: 2026-09-18 15:41 -04:00  
Scope: R03 Finnish decision order only, local and offline.  
Next owner: fresh Sol review, then Astra. R04 remains paused.

## Review findings and reproduction

Sol found that correction 6 returned as soon as it saw an exact configured
inflection. Astra then required the two related gaps to be corrected together:

- `Entä jos hän asuu ugandassa tai Atlantisissa?` selected Uganda despite a
  competing unknown place.
- `Entä jos hän on Kenya mutta asuu ugandassa?` selected Uganda despite a
  direct Kenya mention.
- Unsupported multi-modifier place-shaped turns retained Tanzania with trusted
  `resolved_dependent_follow_up` provenance.

New controls were added before the correction and reproduced **5 failures,
38 passes, exit 1**: configured-plus-unknown (both orders), direct-plus-
inflected, and unsupported shapes.

## Bounded collected-evidence decision

`_finnish_anaphoric_place_resolution` now collects, before deciding:

1. exact configuration-derived inessive forms on whole normalized tokens;
2. direct market mentions; and
3. capitalized or lower-case inessive unknown-place candidates.

It resolves only one nonconflicting code with no unknown competition. Multiple
configured/direct codes, a configured form plus an unknown place, a capitalized
unknown, or a strong lower-case `asuu` unknown all fail closed as standalone.
The detection is order-independent and does not scan substrings or add market
or modifier lists.

Unsupported lower-case place-shaped forms that are not safely standalone still
retain their ordinary conversational anchor, but `_has_ambiguous_finnish_...
complement` records the existing contract-valid `unresolved` status instead of
claiming a trusted resolved follow-up. Ordinary nouns keep the same retrieval
context, with truthful unresolved provenance. No provenance schema changed.

## Controls and results

Controls cover reversed conflict order, casing/punctuation, configured plus
configured conflict, configured plus unknown, direct plus inflected, unknown
multi-modifier shape, ordinary noun multi-modifier shape, no-history,
cross-session behavior, exact-token substring protection, and the prior
capture/audit guards.

Focused suite:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/evidence_first_v2/test_r03_context_capture.py tests/unit/test_demo_multilingual_followups.py tests/unit/test_demo_followup_resolution.py tests/unit/test_retrieval_canary_delivered_answer.py tests/unit/test_retrieval_rank_list_capture.py -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c7-focused' -ra
```

Result: **461 passed, exit 0**.

Compatibility suite:

```powershell
& 'C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\.codex-py311-venv\Scripts\python.exe' -m pytest tests/unit/test_chat_orchestrator.py tests/unit/test_evidence_routing.py tests/unit/test_opensearch_sections.py tests/unit/test_retrieval_service.py tests/unit/test_retrieval_rank_list_capture.py tests/evidence_first_v2 -p no:cacheprovider --basetemp 'C:\Users\KRISH\AppData\Local\Temp\askvera-r03-c7-compatibility' -ra
```

Result: **500 passed, 1 failed, exit 1**. The only failure is the unchanged,
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

`9101284889a4aa074b5dec681075ae3b4539dbe4b977997b92d5db322c078bd6`

The digest covers the same four R03 code/test files using canonical UTF-8
path/hash lines plus a final LF (463 bytes). It identifies a selected dirty
worktree state, not a release result.

No AWS, network, OpenSearch, live model, deployment, push, merge, reindex,
installation, or frozen-fixture edit occurred. R03 correction 7 awaits fresh
Sol review, then Astra. R04 remains paused.
