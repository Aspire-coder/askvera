# Contact scope v3 - candidate, not promotion-ready

Added narrow multilingual contact-field instructions to SYSTEM_PROMPT, preserving
the existing mandatory-qualification rules. Local prompt version is now
2026-09-05-contact-scope-v3. Production SSM/configuration was not changed.

The initial draft exceeded the 4250-character prompt test. It was shortened rather
than increasing the limit. Final local suite: 841 passed, three existing warnings.
Application-source flake8 passed. Graphify refresh was attempted but unavailable.

## Live supplied-evidence observations

Six initial-draft calls and six final compact-prompt calls were made, with the same
model, guardrail, excerpts and component-test limitations as the preceding report.
Initial results: contact-scope-v3-results.json. Final results:
contact-scope-v3-compact-results.json. Final system-prompt SHA256:
a694362162dbb8389199e2d1325ba5d50237b72371771ffefff5dce76e25b447.

- All six final answers included the requested phone numbers and location labels.
- Four of five single-field answers omitted the unrequested order number; the
  original French question still produced both phones. Scope compliance is not
  reliable enough to call the issue fixed.
- The explicitly requested two-number case retained both phones and labels.
- Five of six raw answers were flagged by the standalone numeric checker after
  adding source markers/page or section numbers. The model supplied citation
  metadata is not handled as separate metadata by this component check. This is
  not proof the complete response pipeline fails the same way; test that boundary
  before changing numeric safeguards. Do not broadly exempt numbers near citations.
- Decorative source blocks/separators still appear; prompt wording is not a
  deterministic output-format guarantee.

These are one-off generated observations with manually supplied evidence, not
fresh-index retrieval measurements. No full pipeline, source publication, or
production parity claim is made. The changes remain local and uncommitted.

Next: verify the existing directory field selection and citation normalization
paths against these saved raw answers before adding any new mechanism. The prompt
candidate must not be deployed based solely on its passing unit suite.
