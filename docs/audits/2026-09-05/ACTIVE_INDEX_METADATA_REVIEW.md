# Read-only active-index verification - 2026-09-06

Evidence: `active-index-metadata-v2.json`, compared with `active-source-metadata.json`.

| Document | Sections in published generation | Result |
| --- | ---: | --- |
| UK English policy | 728 | Present, active, country UK, version 2026-07 |
| US English policy | 435 | Present, active, country US, version 2026-05 |
| April 2026 international office directory | 0 | No match for active ingestion ID; filename lookup across generations also returned zero |
| International sponsoring directory | 113 | Present, active, global scope; version absent |

All four generation queries returned exact totals with no timeout or failed shards. No truncation occurred. These checks cover the configured `askvera-policy-sections` index, not every possible AWS index or renamed copy.

## Interpretation

- The April office-directory publication entry points to no sections in this index. This is a confirmed publication/index coverage gap. It cannot supply evidence through that active ingestion ID. Whether the document should be restored or retired requires verifying the actual approved source and replacement intent.
- UK versus GB is not by itself proof of a retrieval defect: the current local `config/policy_locales.json` explicitly maps public GB to indexed UK. The indexed UK sections and active-generation country agree. Registry normalization still warrants review, but blind country-code replacement is not justified.
- US, UK and sponsoring sections lack logical-document IDs at both top level and nested metadata. They do have ingestion IDs, allowing the existing generation filter to select them. This metadata gap alone does not establish failed answer delivery.
- Sponsoring sections have no document version at either level, despite the registry's 2026-08 label. Do not silently synthesize this version in a baseline.
- Indexed `content_hash` is a chunk-content hash in the ingestion writer. Registry hash semantics vary by registration path: PDF bytes, processed JSONL section lines, or a source-URI/ETag reference. Comparing those values directly would be invalid. Source file bytes and chunk text were not verified by this metadata-only check.

## Next

Verify the approved S3 source objects and hashes, especially the April directory, without modifying publication or index data. Establish whether the absent directory was superseded. Then prepare the same frozen evidence/configuration inputs for Current and Candidate. Full answers, citations, safety, and latency remain untested by this check.

## Execution

Read-only SSM configuration and OpenSearch searches only. No model calls, index writes, database writes, cache changes or deployment. Installed the installed botocore version's required `awscrt==0.36.0` support package in the isolated local test environment to use the existing AWS login profile. Application requirements and deployed dependencies were not changed. Diagnostic script compiled successfully; Graphify unavailable.
