# AskVera held-out Current vs Candidate comparison

> Cache was bypassed. Both profiles used the same generation model. Retrieval, selection, evidence approval, and final answer delivery are reported separately.

## Summary

- Generation model: `arn:aws:bedrock:us-east-1:615592621509:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0`
- Current index: `askvera-policy-sections`
- Candidate index: `askvera-policy-sections-rank-20260825-92b2020-v3`
- Retrieval repeats: 1
- Current Recall@1: 0.00%
- Candidate Recall@1: 0.00%
- Current expectation gate: 0/1
- Candidate expectation gate: 1/1

## Case-by-case answers

### PARA-ADV-045 - Adversarial - Wrong Country

**Question:** What's the minimum order for becoming a manager in Antarctica?

**Expected behavior:** abstain

**Runtime locale:** CA/en

**Current answer**

If you're interested in Forever Living in a country or region where the company does operate, I'd be happy to help with manager qualification requirements there. You can also contact Forever Living directly to confirm which markets are currently active.

Citations: CA-EN-Company-Policy.pdf - Sec 8.04-definition-2: Manager | 8.04 | CA

Recall@1/5/10/20: False/False/False/False; selector: None; evidence: True; delivered: True
; expectation met: False

**Candidate answer**

I appreciate the question, but I need to clarify a couple of things:
Second, if you're asking about a different country or region, I'd be happy to help with manager qualification requirements once you let me know which market you're interested in.

Citations: None

Recall@1/5/10/20: False/False/False/False; selector: None; evidence: True; delivered: False
; expectation met: True

