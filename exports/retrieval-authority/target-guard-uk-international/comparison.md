# AskVera held-out Current vs Candidate comparison

> Cache was bypassed. Both profiles used the same generation model. Retrieval, selection, evidence approval, and final answer delivery are reported separately.

## Summary

- Generation model: `arn:aws:bedrock:us-east-1:615592621509:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0`
- Current index: `askvera-policy-sections`
- Candidate index: `askvera-policy-sections-rank-20260825-92b2020-v3`
- Retrieval repeats: 1
- Current Recall@1: 100.00%
- Candidate Recall@1: 0.00%
- Current expectation gate: 0/1
- Candidate expectation gate: 1/1

## Case-by-case answers

### PARA-INTL-UK-026 - International Sponsoring

**Question:** From the UK, how would I go about signing someone up in another country?

**Expected behavior:** answer

**Runtime locale:** GB/en

**Current answer**

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: None

Recall@1/5/10/20: True/True/True/True; selector: True; evidence: False; delivered: False
; expectation met: False

**Candidate answer**

To sponsor someone internationally from the UK, here's the process:

**The main steps are:**

1. **Contact the Head Office** – Reach out to either the UK Head Office or the Head Office of the country where you want to sponsor them.

2. **Request international sponsoring** – Tell them you want to internationally sponsor someone into that country.

3. **They'll use your original ID number** – The person you sponsor will keep your ID number across all countries they're sponsored into.

4. **Your sponsorship carries over** – You remain their sponsor (as shown on their first accepted application form), unless there's a re-sponsorship or a Preferred Customer 6-month sponsor change.

5. **They start at your current sales level** – The new FBO automatically begins at whatever sales level you've currently attained.

For the **UK office contact details**:
- **Email:** businessownersupport-uk@flp.ltd
- **Phone:** +44 1926 626 629

They can guide you through the specific requirements for the country you're targeting and help with any paperwork needed.

Office & Product Center Address: Longbridge Manor Longbridge

Citations: UK-EN-Company-Policy.pdf - Sec 15: International Sponsoring Policies | 15 | UK

Recall@1/5/10/20: False/True/True/True; selector: True; evidence: True; delivered: True
; expectation met: True

