# R04: one reference-resolution interface

Status: **implemented as a reconciliation, not a third resolver**. Verified on
the combined candidate `integ/combined-20260918` (4618b67). The final Fable
review is pending.

## Decision

There is no new planner field and no new model call. The Codex request that
proposed a planner `unresolved_reference` flag
(`codex-requests/A7-unresolved-reference.md`) is **withdrawn**. A7 was solved
deterministically for the 10 configured reference languages, so a model
boolean would add cost and a trust question (a model's country guess must
never become authorization) with no benefit to show for it.

The two existing resolvers cover disjoint inputs, and they write into one
provenance contract.

## The four concerns, kept separate

| Concern | Where | Rule |
|---|---|---|
| **Retaining conversation text** | `_build_retrieval_query_with_provenance` (the anchor from the session's USER turns only) | Assistant text is never an anchor and never evidence |
| **Resolving a reference** | Lane A `reference_resolution.resolve_reference` (contrastive and ordinal, 10 languages), run in `_handle_chat`; V2 `_finnish_anaphoric_trust_decision` (Finnish "hän … -ssa" residence follow-ups), run inside query construction | Both are deterministic. Trust is earned: exactly one candidate, supported form, no conflicting residue |
| **Authorizing a market** | `approve_evidence` plus the scope reapproval in `_route_or_approve_evidence`; `_authorized_policy_market` | Always the session country for company policy. A resolved reference can only choose a *directory target*; it never widens policy eligibility |
| **Producing the standalone retrieval query** | query construction | Consumes the resolution result; it does not recompute trust (R03 C9/C10 fixed the one place that re-evaluated it) |

## States (the single provenance contract, V2-10 `capture_provenance`)

| State | Meaning | Prior-turn id | Effect |
|---|---|---|---|
| `not_dependent` | the message stands alone (no history, a topic change, an explicit market, or a conflict that fails closed) | none | retrieval uses the message only |
| `resolved_dependent_follow_up` | the follow-up depends on a prior user turn and is resolved | **required**: the turn the target came from | may activate V2 trusted follow-up ordering |
| `unresolved` | context is retained for retrieval but not trusted (an ambiguous place-shaped complement) | **forbidden** | V2 trusted ordering stays off |
| *(clarification)* | Lane A contrastive with 2 or more candidates | n/a: no retrieval runs | the user gets one concise question naming the candidates |

`capture_provenance.validate_context_resolution` enforces the id rules.
`scope_aware_fusion._trusted_follow_up` trusts only `resolved_dependent_follow_up`
with a non-empty id.

## Verified behaviour (coordinator probes on the combined code)

- Kenya then Uganda: "And the other one?" → clarification (Kenya, Uganda), no
  retrieval. "What about the first one?" → message resolved to Kenya;
  provenance `resolved_dependent_follow_up` with the id of the turn that named
  Kenya.
- Ordinary words: "minimum first order", "last day to order", "any other
  fee", "One second" → unchanged.
- An unknown place: "Entä jos hän on narniassa?" → `unresolved`, no id; it
  never becomes a trusted Tanzania follow-up (R03 C10).
- Absent history → `not_dependent`. Cross-session → a different
  prior_user_turn_id (opaque, session-scoped).
- Topic change ("What is the return policy?") → standalone.

## Disjointness of the two resolvers

Lane A acts only on a *pure* reference: after removing function words, the
reference word and an optional prop-word, nothing may remain. V2's Finnish
path needs "hän" plus a place-shaped complement. So a message cannot trigger
both. One cross-over: Lane A's ordinal rewrite appends an English display
name ("… Kenya") to a Finnish message. V2 then sees an explicit market and
records `not_dependent` or resolved correctly. Nothing is guessed. The final
review is asked to probe Finnish ordinals after two markets.

## Remaining gaps (not claimed)

- Roles and figures as referents ("that amount", "the second requirement")
  are not resolved by either resolver; retrieval anchoring handles them. They
  are not clarified.
- Languages without reference vocabulary (29 of 39 configured) → unchanged,
  never guessed.
- Multilingual model behaviour on real traffic is unmeasured until R10/R12.
