# AskVera held-out Current vs Candidate comparison

> Cache was bypassed. Both profiles used the same generation model. Retrieval, selection, evidence approval, and final answer delivery are reported separately.

## Summary

- Generation model: `arn:aws:bedrock:us-east-1:615592621509:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0`
- Current index: `askvera-policy-sections`
- Candidate index: `askvera-policy-sections-rank-20260825-92b2020-v3`
- Retrieval repeats: 3
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

If you're interested in becoming a Manager in a particular country or region where Forever Living operates, I'd be happy to help with those details. Could you let me know which market you're asking about?
For the most current information about availability in your area, you can also reach out to [Forever Living's official contact channels in your country].

Citations: None

Recall@1/5/10/20: False/False/False/False; selector: None; evidence: True; delivered: False
; expectation met: True

**Candidate answer**

I appreciate the question, but I need to clarify a couple of things:
If you're asking about a different country or region, I'd be happy to help. Just let me know which market you're interested in, and I can look up the Manager qualification requirements for you.

Citations: None

Recall@1/5/10/20: False/False/False/False; selector: None; evidence: True; delivered: False
; expectation met: True

