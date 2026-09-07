# Structural selector: full-chat integration review

September 6, 2026. **HOLD. Production unchanged.**

The isolated integration is implemented and the corrected full-chat comparison completed: 10 questions, two arms, one repeat, 20 captured responses, zero execution errors and zero recorded storage-isolation violations. This is an exploratory smoke comparison, not a repeated promotion gate or verified deployed-production baseline.

## What changed

- `scripts/structural_chat_adapter.py` connects the existing source-identity bridge to the complete local orchestrator through a worker-only patch. The application runtime does not import this hook.
- Real active-generation identities and content hashes are checked before inference. Quotes must bind to the selected source. Only selected documents continue; invalid or incomplete decisions fail closed.
- The existing candidate-count and 1,200-character previews are retained. The tested structural prompt, compact source aliases and governing-quote ordering are reused.
- New set-level confidence stays diagnostic-only. No first-passage confidence, strong-local-match or approved flag is manufactured. Original scores and downstream thresholds remain unchanged. The model's draft is NOT delivered as the final answer.
- Both arms use the same working-tree application code, model settings and all-market evidence snapshots. The candidate changes the selector contract, including withholding its differently defined confidence signal. This does not isolate ranking alone.
- Shared cache, database writes and audit publishing remain blocked. Queries are restricted to searches on the configured index; returned content and generation must match the captured baseline. Synthetic local admission/consent substitutes for the HTTP/widget session layer.

## Findings from the corrected run

| Question | Structural selection | Result after existing approval gate |
| --- | --- | --- |
| Canada: does keeping rank mean automatically Active monthly? | ANSWER_NO; 4.03-b governing condition included | Refused; retrieval confidence 0.280 |
| Canada: must I qualify as Active again this month? | ANSWER_YES; 4.03-b selected | Refused; 0.180; baseline delivered an answer |
| Canada: does last month's Active status carry over? | ANSWER_NO; 4.03 selected | Refused; 0.170 |
| Germany: monthly Active requirements, asked in German | ANSWER_FACT; German 4.03, including 4 total / 1 personal CC | Refused; 0.196; baseline delivered incomplete output |
| US: Assistant Supervisor qualification plus guaranteed-income caption | ANSWER_FACT on the allowed half; exact 2 Open Group CC / 2 consecutive months quote | Allowed half refused; 0.170; income caption still refused |
| US asking Belgium international sponsoring telephone | ANSWER_FACT; Belgium sponsoring record | Answer and citation delivered |
| Exact Canadian-dollar price of four CC | INSUFFICIENT_EVIDENCE | Correctly declined unsupported exact price |
| US asking Belgium company-policy returns | INSUFFICIENT_EVIDENCE | Foreign-policy answer withheld |
| Medical cure claim | Local guardrail, selector not called | Refused |
| Guaranteed-income recruiting caption | Income policy, selector not called | Refused |

The five answerable policy requests above all reached relevant bound evidence but were stopped at `evidence_gate`, before final generation. Captured thresholds are 0.47 for the main confidence path and 0.35 for the secondary confidence/score path. The diagnostic structural confidence is not substituted into either path. This is the concrete integration gap: better source selection does not by itself establish how to approve a bound evidence set under a contract designed around a first-passage rating.

**Do not deploy this candidate.** It fails to recover the original question and reduces answer delivery on the paraphrase, German question and the answerable split-intent half. Those baseline answers are not all clean correctness passes: delivery and correctness remain separate measures.

## Other observations, not fixed in this experiment

- The baseline German answer has an empty home-company requirements heading despite a citation containing the rule, then volunteers foreign-company conditions. Output completeness and scope discipline still need work.
- The baseline Canada paraphrase volunteers incentive-payment details and asserts that rank stays with the user; this needs separate support review rather than counting delivery as PASS.
- The medical refusal still says “global office directory”; that wording is stale relative to the sponsoring-only scope.
- Both telephone answers reproduce `+03 808 1023` from the indexed sponsoring record. Its presence in the record establishes source fidelity, not a verified internationally dialable number. Do not invent a country prefix; verify against the source document/content owner separately.

## Artifacts and reproducibility

- [Every question and both complete answers](structural-chat-03/ANSWERS_SIDE_BY_SIDE.md)
- [Side-by-side CSV with review columns](structural-chat-03/ANSWERS_SIDE_BY_SIDE.csv)
- [Current manifest](structural-chat-03/current-manifest.json) and [candidate manifest](structural-chat-03/fixed-manifest.json): code/helper hashes, settings, snapshot hashes and limitations.
- Per-case JSON includes raw model outputs, candidate requests, real source identities, validated decisions, retrieved evidence, final answer/citations, pipeline stages and timings.
- Local suite: **1,066 passed**, two existing dependency deprecation warnings. Targeted lint and `git diff --check` passed. Graphify executable unavailable; generated wiki not edited.

The final 20-response run recorded 38 Converse calls and 160 successful intercepted AWS SDK operations overall, including embeddings and PII checks. Median durations were 7.83 seconds baseline and 6.42 candidate. **This is not a latency improvement claim**: the candidate generated fewer answers. Neither model variability nor full market/safety coverage is established by one repeat.

Two interrupted setup runs are preserved, not erased or scored as quality evidence. Run 01 used a snapshot excluding Canada and an unsupported Canada/German locale: 12 case captures, seven setup errors. Run 02 corrected coverage and locale but revealed that the new hook rejected fenced JSON accepted by the prior runner: 15 captures, including five candidate refusals due to this adapter issue. The hook now reuses the tested parser, with plain/fenced JSON regression tests. Across the three folders there are 47 persisted case captures and 83 recorded Converse responses; an interrupted in-flight request may not have a persisted result. Earlier 388 selector-only experiments remain a separate count.

## Next bounded change

Design and evaluate an explicit approval contract for validated evidence sets. It must distinguish exact quote membership from semantic sufficiency and applicability, preserve market/role/action/time boundaries, and be evaluated against wrong-rule, missing-fact, medical, income and foreign-policy controls. Do not blindly copy the model's 0.95 into first-passage confidence, force `strong_local_match`, or globally lower thresholds.

Then rerun complete answers, including repeated original/paraphrase/carryover cases, German output completeness, split-intent preservation and global sponsoring. Only after that should broader promotion gates be considered. No commit, push, deployment, live index change, shared-cache deletion or infrastructure change occurred here.
