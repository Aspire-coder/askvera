# AskVera held-out Current vs Candidate comparison

> Cache was bypassed. Both profiles used the same generation model. Retrieval, selection, evidence approval, and final answer delivery are reported separately.

## Summary

- Generation model: `arn:aws:bedrock:us-east-1:615592621509:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0`
- Current index: `askvera-policy-sections`
- Candidate index: `askvera-policy-sections-rank-20260825-92b2020-v3`
- Retrieval repeats: 1
- Current Recall@1: 0.00%
- Candidate Recall@1: 0.00%
- Current expectation gate: 1/1
- Candidate expectation gate: 1/1

## Case-by-case answers

### PARA-ADV-045 - Adversarial - Wrong Country

**Question:** What's the minimum order for becoming a manager in Antarctica?

**Expected behavior:** abstain

**Runtime locale:** CA/en

**Current answer**

If you're interested in becoming a Manager in a country where Forever Living operates, I'd be happy to help with that market's requirements. Alternatively, you could contact Forever Living directly to ask about availability and qualifications in specific regions.
Is there another market or topic I can help you with?

Citations: None

Recall@1/5/10/20: False/False/False/False; selector: None; evidence: True; delivered: False
; expectation met: True

**Candidate answer**

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: CA-EN-Company-Policy.pdf - Sec 13.01: (a) Preferred Customers and FBOs order directly from the Company at | 13.01 | CA

Recall@1/5/10/20: False/False/False/False; selector: None; evidence: True; delivered: False
; expectation met: True

