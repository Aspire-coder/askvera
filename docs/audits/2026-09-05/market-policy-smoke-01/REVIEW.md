# Market policy smoke test: blocked before answer capture

2026-09-06. Two attempted cases: BE-01 and BE-02. Zero valid answer captures. The remaining 38 cases were not attempted.

Both attempts stopped with `RuntimeError: Search returned evidence outside verified baseline`. Recorded storage violations are empty. This is an evaluation infrastructure error, not a chatbot correctness failure. Do not calculate a recall or answer-quality percentage from this run.

Root cause found in the existing snapshot exporter: `scripts/audit_active_index_metadata.py` filters exported generations to US, UK/GB and GLOBAL English. The recorder requires every returned hit to exist in that snapshot. Belgian evidence cannot pass that check. This error alone does not establish that the live index changed.

Prepared `market-policy-cases.json` with 40 unique reviewed questions, expected behavior kept out of prompts, German/Italian request languages and GB normalization. Extended the existing local-code recorder with fixture and Current-only options. Python compilation passed. No application source or deployment was changed.

Provenance: this invokes a local archive of deployed commit 7d29dad09540527a9302b95436f36e93f7fa5a2a against AWS, not the HTTP/widget. Fresh nonsecret SSM settings were captured. Publication registry and index baseline are older snapshots, so this is not yet a verified current-source baseline. Shared cache reads/writes are bypassed, session/consent fixtures are synthetic, and database/shared audit access remains isolated.

Required before continuing: obtain a fresh publication registry; export all eight markets and applicable languages plus the approved global sponsoring generation; check source versions against supplied PDFs; then repeat the two-case capture check. Do not simply remove the evidence-identity guard or relabel old snapshots as current. Questions whose source edition differs must be recorded as source-version mismatches, not automatically retrieval defects.
