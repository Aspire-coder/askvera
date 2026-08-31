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

If you're interested in Forever Living opportunities in a specific country or region, I'd recommend reaching out to Forever Living's official office or distributor for that area—they'll have the most current details about eligibility, pricing, and rank requirements there.
Is there anything about the Canadian business plan I can help you with instead?

Citations: None

Recall@1/5/10/20: False/False/False/False; selector: None; evidence: True; delivered: False
; expectation met: True

**Candidate answer**

If you're interested in Forever Living opportunities in a specific country or region, I'd recommend reaching out to Forever Living's main office or a local distributor in that area—they can give you accurate details about minimum orders, qualification requirements, and how the business works there.
Is there anything about the Canadian business structure I can help clarify instead?

Citations: None

Recall@1/5/10/20: False/False/False/False; selector: None; evidence: True; delivered: False
; expectation met: True

