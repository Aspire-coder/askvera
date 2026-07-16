# Country-agnostic policy ingestion

The policy retrieval pipeline does not require question aliases for each
country. Every approved policy follows the same workflow:

1. Extract numbered sections, list items, and compact numeric table rows.
2. Attach market, language, version, effective-date, and status metadata.
3. Load the resulting JSONL into OpenSearch or PostgreSQL, or create a Bedrock
   section package.
4. Replace the previous active source and rerun the shared retrieval test set.

Example extraction:

```powershell
python scripts/ingestion/extract_policy_sections.py `
  --pdf path/to/policy.pdf `
  --country NL `
  --language nl `
  --document-version 2025-05 `
  --effective-date 2025-06-15 `
  --output-dir outputs/policy_sections `
  --bedrock-dir outputs/bedrock_sections/nl-nl
```

Example OpenSearch load:

```powershell
python scripts/ingestion/load_policy_sections_to_opensearch.py `
  --jsonl outputs/policy_sections/policy.sections.jsonl `
  --source-uri-prefix s3://approved-policy-bucket/policies `
  --status active `
  --replace-source
```

Use the same commands for every market and language. Do not add test-question
answers, expected numbers, or market-specific phrases to retrieval code.
