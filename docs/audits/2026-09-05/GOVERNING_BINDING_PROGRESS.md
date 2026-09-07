# Governing selection and source binding: local experiment

Latest: isolated model integration and 128 additional selector calls are now complete. **998 unit tests pass**. Ranking recovered one paraphrase across three repeats, but the original refusal remains unresolved. See [integration review](GOVERNING_BINDING_INTEGRATION_REVIEW.md). The no-cloud-call statement below describes the earlier offline step only. Production remains unchanged.

September 6, 2026. No production wiring, deployment, cloud calls, index writes or confidence changes in this step. Existing dirty changes were preserved.

## Implemented

- `app/retrieval/source_binding.py`: immutable source descriptors with full SHA-256 identity over document, generation, section, country and exact content. Support quotes must match their claimed already-authorized source, allowing only whitespace wrapping differences. Wrong identifiers, wrong source versions, missing provenance, modified numbers, duplicate sources and incorrect quote membership raise errors. Quotes are never automatically relocated to a different source.
- `app/retrieval/governing_rules.py`: conservative English activity-qualification prioritization. The exact definition/qualification clause precedes benefits and incentives. Other targets, compound requests and unsupported languages preserve order. It neither grants access nor approves an answer, and it does not change scores or confidence.
- `scripts/probe_governing_binding.py`: offline probe using previously captured inputs. Capture hashes are explicitly capture identities, not invented published document-generation IDs.

## Measured offline result

| Captured question | Before | After |
| --- | --- | --- |
| Does keeping my sales level mean I'm automatically active every month? | Sales Level definition first; activity rule fourth | Activity rule 4.03 first, 4.03-b second |
| I already earned my sales rank. Do I still need to qualify as Active again this month? | Earned Incentive passages first; activity rule third | Activity rule 4.03 first, 4.03-b second |
| If I do not order anything for one month, is my FBO business automatically terminated? | Existing termination-related order | Unchanged |

Candidate sets are identical before/after. Valid source bindings survive order changes; wrong bindings are rejected in all three probes. Full evidence: `governing-binding-offline-01.json`.

## Tests and limitations

**990 unit tests passed**, including 30 added binding/target regression cases; targeted lint passed. Two existing dependency deprecation warnings remain. Graphify refresh could not run because its executable is unavailable; no graph currently exists.

This is not a model-output or end-to-end improvement claim. The helpers are NOT called by the live provider. Source binding proves text membership, not semantic correctness. The activity classifier is deliberately English-only, supports a limited request family and does not claim typo/multilingual/compound completeness. Global sponsoring authorization still belongs upstream; passing an unauthorized source to the binding helper does not authorize it.

## Next gate

Integrate the two components into an isolated selector experiment using stable source IDs (not ordinal rank positions), real published generation metadata when supplied by the provider, and unmodified approval/safety gates. Test governing ranking and binding separately before the combination, include additional independently labeled questions and multilingual no-change controls, and compare both final answers. Do not deploy or infer safety from the unit count. The original Canada production refusal remains unresolved until that evidence exists.
