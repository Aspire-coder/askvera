# Contact output fixes - local validation

Validated 2026-09-06. Not deployed.

## Changes

- Separate verified inline source metadata from answer prose before phone cleanup and numeric validation. Structured citations remain available. Unrecognized citation metadata and additional claims are not exempted from validation.
- Remove the captured standalone French orders-number sentence when the question requests only the office/reception telephone. Requests for both numbers retain both.
- Preserve the original failing replay; write corrected results to `contact-output-replay-fixed.json`.

## Results

- Full local unit suite: **844 passed**, with three warnings (dependency deprecations and pytest cache directory permissions).
- Python application lint: passed.
- All six saved-output replays retain the requested phone numbers without numeric fallback or page-number substitution. The French office-only case no longer includes the orders number; the explicit both-numbers case retains both.

## Limits

This is a saved-output cleanup/validation replay, not fresh retrieval or a production end-to-end test. Governance and external PII detection are mocked. Source URLs were unavailable in the captured evidence, so all six retain an incomplete-citation warning. The French filter covers the observed sentence pattern, not every language or paraphrase. Numeric thresholds and country-scope rules were not relaxed. Live validation remains necessary before release.
