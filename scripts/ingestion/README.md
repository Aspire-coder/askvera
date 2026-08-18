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

## Isolated vNext chunk experiment

The default `current` profile preserves the established extraction behavior.
The opt-in `vnext` profile uses structure-aware chunks of at most 2,000
characters with approximately 200 characters of overlap.

Generate both packages into separate local directories:

```powershell
python scripts/ingestion/extract_policy_sections.py `
  --pdf path/to/policy.pdf `
  --country CA `
  --language en `
  --chunk-profile current `
  --output-dir outputs/chunks/current

python scripts/ingestion/extract_policy_sections.py `
  --pdf path/to/policy.pdf `
  --country CA `
  --language en `
  --chunk-profile vnext `
  --output-dir outputs/chunks/vnext
```

Compare package size and shape before embedding:

```powershell
python scripts/ingestion/compare_chunk_packages.py `
  --current outputs/chunks/current/policy.sections.jsonl `
  --vnext outputs/chunks/vnext/policy.sections.jsonl `
  --json-output outputs/chunks/comparison.json
```

Load vNext only by naming the separate index explicitly:

```powershell
python scripts/ingestion/load_policy_sections_to_opensearch.py `
  --jsonl outputs/chunks/vnext/policy.sections.jsonl `
  --index askvera-policy-sections-vnext `
  --source-uri-prefix s3://approved-policy-bucket/policies `
  --status active
```

The loader rejects a `vnext` package when its target resolves to the current
`OPENSEARCH_INDEX`.

`vnext_r4` is also isolated. It preserves larger parent sections, caps
structured child expansion, and rejects common numeric false headings. The
2026-08-18 benchmark did not meet the promotion gate, so it must not target the
production index. See
`outputs/interaction_quality/VNEXT_R4_RETRIEVAL_FINDINGS.md`.

Before extracting an unfamiliar PDF, run the preflight check:

```bash
python -B scripts/ingestion/preflight_document.py --pdf /path/to/document.pdf
```

It reports image-only pages that require OCR and table-like pages that benefit
from the isolated `vnext` layout-preserving extraction profile. The established
`current` profile remains the default.
