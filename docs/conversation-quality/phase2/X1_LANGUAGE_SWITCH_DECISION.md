# X1: what happens when the user writes in a language the widget isn't set to

Status: **needs a product decision**. APPROVAL_QUEUE item 6. Nothing is
implemented.

## Today (verified in code)

- The widget sends `language`. The user picks it, and it can change mid-session.
- `body.language` drives four things at once:
  1. the answer language in the prompt ("User language: …");
  2. the deterministic copy (refusals, the outage message, clarifications);
  3. the language-aware post-processing (Phase 2 A, B, C and F vocabularies);
  4. retrieval: the document-language preference and the same-country
     English fallback (`OPENSEARCH_GLOBAL_DOCUMENT_LANGUAGE`).
- Nothing detects the language of the message itself. Suppose a French user
  types French while the widget says "en". The prompt says "User language: en",
  yet its first rule also says "Keep the complete response in that language".
  Those two instructions conflict, so the model may answer in either language.
  The deterministic copy and vocabularies stay English.

## The distinction that must not blur

**Answer language** and **source eligibility** are different things:

- Answer language is presentation. Following the user's actual language is
  harmless for authorization.
- Source eligibility (which country's policy, which document language, the
  global-sponsoring exemption) is authorization. It must stay bound to the
  session country and the configured locale rules. A message typed in German
  must never make German-market policy eligible for a US session.

## Options

| Option | Behaviour | Risk |
|---|---|---|
| **A. Selector is authoritative (today, made explicit)** | Answer in `body.language`. Fix only the prompt conflict, so it says "answer in User language" unambiguously | A French question gets an English answer. Predictable. No new failure mode |
| **B. Follow the message, answer-only (recommended)** | Detect the message language deterministically: count function words from the vocabularies already in the repo, and switch only on a strong, unambiguous signal in a language that has route copy. Use it for items 1-3 only. Retrieval (item 4) keeps `body.language` | A short or mixed message may be misdetected; mitigated by switching only on a strong signal and never for single-word messages. Covers only about 12 of the 39 configured languages (those with route copy); the rest stay on the selector |
| C. Follow the message everywhere | Also switch retrieval language | Changes which documents are eligible. **Not recommended**, and it would need a separate eligibility review |

## Recommendation

**B, answer-only.** Keep authorization untouched and switch presentation
only. It adds no dependency and no model call. If the product owner prefers
predictability over accommodation, choose **A**; it's also the smaller
change.

## What implementation would need (after a decision)

- A deterministic detector in a new module, built from the existing
  vocabularies, with a documented threshold.
- An `answer_language` threaded to the prompt, the localized copy and the
  post-processing vocabularies. Retrieval keeps `body.language`. This is a
  shared `chat_orchestrator.py` change and must be sequenced after Lane E and
  R11.
- A `PROMPT_VERSION` bump only if the prompt text changes (option A's wording
  fix would change it).
- Tests: language switched and unswitched; mixed-language messages; single
  words; a retrieval-eligibility invariant (the country and document-language
  filters are identical with and without a switch); cross-session isolation.
