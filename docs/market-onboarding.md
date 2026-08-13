# AskVera market onboarding

The Operations portal now includes **Market readiness**. It is the checklist for adding a country or market without relying on a private deployment command or memory of previous work.

## What is tracked

The checklist reads the existing application configuration and operational registries:

- `config/markets.json`: market code, display name, enabled languages, default language, and consent version.
- `config/policy_locales.json`: languages with published company-policy content.
- Support routing configuration: enabled department and destination email for handoff.
- Active widget configuration: whether a customer-facing widget includes the market.
- Retrieval validation: shown as **Not verified** until the market's retrieval evaluation has been run. The readiness page does not change retrieval or query live documents.

## Onboarding sequence

1. Add the market and its supported languages to the market configuration.
2. Upload each policy document to the approved market and language location.
3. Extract, inspect, and stage the document sections.
4. Verify section counts, pages, encoding, metadata, country, language, and access scope.
5. Publish the validated generation and confirm that staging records are gone.
6. Add the published locale to the policy-locale configuration.
7. Set the current privacy and terms version.
8. Configure an enabled support route with a department and destination email, where handoff is required.
9. Add the market to the intended active widget after the website origin is approved.
10. Run market-specific retrieval tests, including policy, typo, multilingual, safety, and global-directory questions.
11. Refresh **Market readiness** and resolve every required warning before customer use.

## How to read the statuses

- **Ready**: required configuration is present. Retrieval still needs a real evaluation because it is intentionally reported separately.
- **Needs review**: the market is partially configured, for example only some requested languages have published policies.
- **Not configured**: a required onboarding item is missing.
- **Not verified**: the check requires an explicit test or operational verification and is not inferred from configuration.

## Design boundary

This feature is an operational checklist only. It does not select a retrieval provider, alter OpenSearch filters, change chunking, republish documents, or modify answers sent to users. New markets are discovered from configuration rather than hardcoded into the portal UI.
