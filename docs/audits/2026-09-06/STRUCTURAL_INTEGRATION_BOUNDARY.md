# Structural selector: source integration boundary

September 6, 2026. Local bridge implemented; full answer-pipeline integration remains pending. Production unchanged.

Update: the isolated full-chat integration and 20-response smoke comparison are now complete. The candidate is held because bound policy evidence still fails the existing confidence gate. See [the full-chat review](STRUCTURAL_CHAT_REVIEW.md). The text below records the earlier bridge-only checkpoint.

## Implemented and verified

`app/retrieval/structural_selection.py` converts versioned RetrievedDocument objects into evidence identities, validates support-only decisions, and returns only selected documents in validated quote order. No model draft is delivered as a final answer.

Required provenance: active status, a caller-supplied authorized active ingestion ID, section ID, exact SHA-256 content hash, and stable document identity. The previously captured Canada search rows have ingestion IDs and hashes but no logical_document_id. A canonical S3 URI is therefore accepted as the actual document identity when a logical ID is absent. No capture hash is presented as a publication generation; temporary/query-bearing or fabricated OpenSearch addresses are rejected as fallback identities.

Market defenses: foreign country policies are rejected even when the global option is enabled. Cross-market global documents require both explicit upstream authorization and the international_sponsoring directory kind. The generic global office directory is not accepted. Publication, expiry, language and query-intent controls still belong upstream; this bridge supplements, not replaces, them.

The bridge preserves document scores and existing validation signals. It does not transfer whole-decision confidence onto the first document, set an approved flag, remove an existing rejection, or bypass the evidence/governance engine. Abstention yields no selected documents. Invalid quotes, missing provenance, duplicate identities and stale generations fail closed.

## Important integration finding

The current OpenSearch provider uses selector confidence as a rating of the first passage and blends it with lexical confidence before the evidence-approval gate. The experimental structural confidence describes a proposed answer supported by a set of quotes. These are not interchangeable. The bridge deliberately does not silently map the new value to `evidence_selector_confidence` or overwrite `evidence_selector_directly_answers`.

## Verification

- 20 new boundary tests, including country/global sponsoring behavior, stale identity, missing hashes, abstention, and score preservation.
- Full suite: **1,053 passed**, two pre-existing dependency deprecation warnings.
- Targeted lint passed. Graphify unavailable; generated wiki unchanged.
- Zero AWS calls or additional model tests this step. Prior totals remain 388 selector calls and zero additional end-to-end chatbot calls.
- No deployment, live-provider wiring, commits, pushes or live index changes. Existing unrelated work preserved.

## Remaining work

Connect this bridge only in the isolated comparison worker using an authoritative active-generation snapshot. Make the confidence semantics explicit at the retrieval-result boundary, preserve all existing approval thresholds, and capture that effective configuration. Then run complete final-answer comparisons against an accurately identified Current baseline, including country policy isolation, cross-country sponsoring, medical/income refusal, split intent, citations, scope, language and latency. A successful local bridge does not complete that gate and is not a deployment recommendation.
