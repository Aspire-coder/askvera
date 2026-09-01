# AskVera Code Maintenance Notes

## Scope of this cleanup

This pass is intentionally conservative. The existing widget, OpenSearch section
retrieval, country and language isolation, safety routing, and answer validation
remain the active behavior. No production provider, index, prompt, or cache
setting is changed by cleanup alone.

## Changes made

- The unfinished WhatsApp adapter, settings, message catalog, and unit tests
  were removed from the active application path. Legacy schema cleanup is
  intentionally kept out of this application commit because it drops tables
  and requires a separate production data-retention approval.
- The retrieval evaluation CLI is isolated in
  `scripts/evaluate_retrieval_shadow.py`; it does not run in the user answer
  path.

## Safe cleanup rules for future work

1. Keep transport concerns at the API boundary.
2. Keep retrieval decisions in the retrieval provider, not in channel routes.
3. Keep localized copy in catalog/config files, not scattered string literals.
4. Remove a helper only after repository-wide reference and test searches show
   that it is unused.
5. Do not delete old ingestion or retrieval paths until a measured replacement
   has passed the locale, citation, safety, latency, and cost gates.
6. Keep experimental retrieval flags disabled until shadow evaluation proves
   that the candidate improves quality without regressing isolation.

## Verification

The full backend unit suite and lint checks are the required local checks for
this cleanup. The production database migration is intentionally not applied
as part of local verification.
