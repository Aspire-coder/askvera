# ASK Vera AWS Cleanup Tracker

This file tracks temporary AWS resources and test artifacts created while debugging retrieval.

Production retrieval now uses the OpenSearch section index. The resources in
the cleanup table are no longer part of the active production path, but should
still be checked against SSM configuration before deletion.

## Ready For Cleanup

| Item | Location / ID | Why it exists | Cleanup timing |
| --- | --- | --- | --- |
| Section test Knowledge Base | `48MZUCJGAT` / `askvera-section-test-ca-en` | Managed Bedrock KB created to test section-sized policy chunks. | Confirm it is absent from SSM, then delete it. |
| Section test data source | `5H3QAO9ATD` | Data source attached to the section test KB. | Delete with the section test KB. |
| Section chunk S3 test prefix | `s3://askverachat-prod-content/bedrock-kb-test/section-chunks/CA/en/company-policy/` | Temporary one-file-per-section test package. | Confirm it is not referenced, then delete it. |
| Older section chunk S3 prefix | `s3://askverachat-prod-content/bedrock-kb-test/section-chunks/CA/en/company/` | Earlier test prefix used during section KB trials. | Delete if it still exists. |
| Uploaded test spreadsheets | `s3://askverachat-prod-content/tmp/ASK_Vera_Canada_Test_Scenarios*.xlsx` | Temporary transfer path for EC2 retrieval evaluation. | Delete after test harness reports are archived locally. |

## EC2 Temporary Files

These are local EC2 files under `/tmp`. They are safe to delete after reports are copied or no longer needed.

| Item | Location | Why it exists |
| --- | --- | --- |
| Retrieval reports | `/tmp/retrieval_eval_*` | CSV/JSON output from retrieval harness runs. |
| Canada test workbook | `/tmp/ASK_Vera_Canada_Test_Scenarios*.xlsx` | Input workbook for retrieval evaluation. |
| Canada policy PDF copy | `/tmp/CA-EN-Company-Policy.pdf` | Temporary copy used by section extraction. |
| Section extraction output | `/tmp/askvera-policy-sections-*` | JSONL/CSV output from PDF section extraction. |
| Bedrock section package output | `/tmp/askvera-section-package-*` | Generated one-file-per-section package for KB tests. |

## Production Resources To Keep

| Item | Location / ID | Why it stays |
| --- | --- | --- |
| Production approved KB bucket | `s3://askverachat-prod-kb/approved/` | Source of approved company documents. |
| Production content bucket | `s3://askverachat-prod-content/` | Legal docs, widget assets, and approved support files. |
| OpenSearch Serverless collection | `p6ytwsfpt0la5h2hth4` / `bedrock-knowledge-base-6w5myh` | Hosts the active section retrieval index. |
| OpenSearch section index | `askvera-policy-sections` | Active production retrieval index. |
| DynamoDB widget registry | `AskVeraWidgets` | Runtime widget/customer configuration. |
| RDS database | `database-1` | Sessions and consent records; also retains the rollback section index. |
| RDS managed secret | `rds!db-617fcf32-1ae3-4f45-b803-4378b966fcf6-0xz7wN` | Active RDS credentials managed by AWS. |

## Notes

- The section index work should not require hand-written answer JSON.
- The section index stores generated sections from approved PDFs so retrieval can be tested and controlled more precisely.
- Before deleting any AWS resource, confirm production is not reading from it through SSM Parameter Store.
