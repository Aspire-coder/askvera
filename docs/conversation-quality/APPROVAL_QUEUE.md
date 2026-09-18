# Approval queue

Nothing here has been done. Each item needs your explicit approval.

| # | Requested action | Why | Estimated cost | Expected output | Raised |
|---|---|---|---|---|---|
| 1 | Accept that dependency outages become HTTP 200 fallbacks, with monitoring moved to a dedicated metric (see Phase 2 Lane E) instead of HighErrorRate | C5 honesty to users; an outage must not look like missing evidence | none | decision | Phase 1 |
| 2 | Live paired run, baseline B0 against the candidate, on the pack's needs-live cases and the 178-case US workbook | the only way to measure prompt-only rules and model prose | about 200-400 Haiku generations plus retrieval; low (single-digit USD) | per-case transcripts and pass/fail | Phase 1 |
| 3 | Merge the four B1 branches, then this candidate | release | none | PRs | Phase 1 |
| 4 | Deploy | release | - | only after #2 passes and Codex's retrieval work is combined and re-validated | Phase 1 |
| 5 | Decide which pipeline owns answer composition long term: the production path (this project) or Evidence-First V2 | V2 has its own standalone-request, composition and validation stages covering this scope | none | decision | Phase 1 |
| 6 | Product decision: when the user writes in a language other than the widget selection, should the answer follow the message (option B, answer only) or the selector (option A)? Source eligibility never changes | Prompt instructions conflict today; see `phase2/X1_LANGUAGE_SWITCH_DECISION.md` | none | decision; implementation follows | Programme |
| 7 | Language coverage decision: 39 language codes are configured across enabled markets, but the conversation vocabularies cover about 10 and route copy covers 12 (da, de, en, es, fi, fr, it, nl, no, ru, sr, sv). Arabic (10 markets), Portuguese (3), Albanian (3) and 24 others fall back to English-only matching and translated copy | Coverage is currently "fail conservatively", not multilingual | none locally; native review of vocabulary for any added language | a prioritized language list for native-speaker vocabulary review | Programme |
