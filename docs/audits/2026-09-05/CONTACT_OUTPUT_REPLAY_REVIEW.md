# Contact output replay findings

Replayed six saved live model answers through the existing
_secure_and_complete_response and _validate_response helpers. No new model calls.
Full before/after text and metadata: contact-output-replay.json.

Isolation: output governance mocked to allow, external PII detection mocked to no
entities. Local regex PII processing, contact restoration, field selection and
validators remained real. Source URI/version were unavailable and left empty,
causing expected CITATIONS_INCOMPLETE warnings. This is not a complete chat,
live safety or publication test. Confidence is a fixture value.

## Confirmed in this replay

1. In three Belgium answers (BE_EN, BE_FR, BE_BOTH), cleanup transformed the source
   page range 111-112 into (888) 440-ALOE (2563). Metadata reports phone_replaced.
   Later numeric repair removed the erroneous numeric content, but left damaged
   inline source text. A location-specific contact must not replace citation metadata.
2. BE_FR_SHORT lost its valid phone answer entirely: [Source 1] was treated as an
   unsupported number and final validation returned the insufficient-evidence
   fallback. The selected language remained English, as in the original component
   setup, so the fallback was English despite the question requesting French.
3. BE_FR retained its unrequested orders telephone through field cleanup. The
   current selector relies on English question keywords and colon-labelled fields;
   this French narrative answer does not match that path.
4. US_TYPO retained its phone but numeric repair truncated its inline source label
   at the filename's period. BE_RECEPTION remained intact, apart from the expected
   missing-URI warning.

Five answers retain requested phone content; one falls back. That is not a 5/6
quality pass: damaged citations and unrequested fields remain failures.

## Required follow-up

- Separate/validate citation metadata before contact redaction and numeric checking.
  Do not exempt arbitrary source-looking prose or remove all numbers near a citation.
- Restore contacts only from authorized relevant evidence, never from a selected-
  market fallback merely because a numeric token was classified as a phone.
- Use explicit field intent and structured source fields for multilingual contact
  scope, preserving requests for multiple fields and required role/location labels.
- Freeze these saved-output failures as regressions, including spoofed citations,
  changed phone digits and multi-field requests. Verify the actual full chat path
  separately before attributing the same behavior to production.

No production code, settings, deployment, database or shared cache was changed.
Only local replay tooling and this report were added during this check.
