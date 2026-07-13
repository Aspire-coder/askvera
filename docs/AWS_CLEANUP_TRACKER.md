# ASK Vera AWS Cleanup Tracker

This file tracks temporary AWS resources and test artifacts created while debugging retrieval.

Do not delete these until the replacement retrieval path has been validated and production has been switched intentionally.

## Keep For Now

| Item | Location / ID | Why it exists | Cleanup timing |
| --- | --- | --- | --- |
| Section test Knowledge Base | `48MZUCJGAT` / `askvera-section-test-ca-en` | Managed Bedrock KB created to test section-sized policy chunks. | Delete after the PostgreSQL section index or final retrieval approach is validated. |
| Section test data source | `5H3QAO9ATD` | Data source attached to the section test KB. | Delete with the section test KB. |
| Section chunk S3 test prefix | `s3://askverachat-prod-content/bedrock-kb-test/section-chunks/CA/en/company-policy/` | Temporary one-file-per-section test package. | Delete after the section test KB is no longer needed. |
| Older section chunk S3 prefix | `s3://askverachat-prod-content/bedrock-kb-test/section-chunks/CA/en/company/` | Earlier test prefix used during section KB trials. | Check if it exists, then delete after validation. |
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
| DynamoDB widget registry | `AskVeraWidgets` | Runtime widget/customer configuration. |
| RDS database | `database-1` | Sessions, consent log, and future controlled section index. |
| RDS managed secret | `rds!db-617fcf32-1ae3-4f45-b803-4378b966fcf6-0xz7wN` | Active RDS credentials managed by AWS. |

## Notes

- The section index work should not require hand-written answer JSON.
- The section index stores generated sections from approved PDFs so retrieval can be tested and controlled more precisely.
- Before deleting any AWS resource, confirm production is not reading from it through SSM Parameter Store.
