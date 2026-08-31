# AskVera held-out Current vs Candidate comparison

> Cache was bypassed. Both profiles used the same generation model. Retrieval, selection, evidence approval, and final answer delivery are reported separately.

## Summary

- Generation model: `arn:aws:bedrock:us-east-1:615592621509:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0`
- Current index: `askvera-policy-sections`
- Candidate index: `askvera-policy-sections-rank-20260825-92b2020-v3`
- Retrieval repeats: 3
- Current Recall@1: 0.00%
- Candidate Recall@1: 0.00%
- Current expectation gate: 0/2
- Candidate expectation gate: 0/2

## Case-by-case answers

### PARA-PC-IT-031 - Multilingual - PC (IT)

**Question:** Voglio solo comprare con lo sconto, non costruire un'attivita. Che opzione e?

**Expected behavior:** answer

**Runtime locale:** IT/it

**Current answer**

I documenti di policy approvati attualmente disponibili non contengono informazioni sufficienti per rispondere chiaramente a questa domanda. Si prega di riformulare la domanda o contattare il supporto Forever Living per una risposta ufficiale.

Citations: None

Recall@1/5/10/20: False/False/False/True; selector: False; evidence: False; delivered: False
; expectation met: False

**Candidate answer**

La tua opzione è diventare un **Cliente Premium**.

Come Cliente Premium acquisti i prodotti Forever sottoscrivendo un ordine di acquisto pari o superiore a 0,5 Case Credit e ricevi subito uno **sconto del 5%**. Non devi intraprendere alcuna attività di vendita: è semplicemente una modalità di acquisto con vantaggio economico.

Se in futuro desiderassi costruire un'attività, potresti evolverla, ma per ora come Cliente Premium puoi tranquillamente acquistare i prodotti con il vantaggio dello sconto senza alcun impegno commerciale.

Citations: IT-IT-Company-Policy.pdf - Sec 2-part-1-definition-5: Cliente Premium** | 2 | IT

Recall@1/5/10/20: False/False/True/True; selector: False; evidence: True; delivered: True
; expectation met: False

### PARA-ADV-045 - Adversarial - Wrong Country

**Question:** What's the minimum order for becoming a manager in Antarctica?

**Expected behavior:** abstain

**Runtime locale:** CA/en

**Current answer**

I appreciate the question, but I need to clarify two things:

Citations: CA-EN-Company-Policy.pdf - Sec 11.01-b: Core Requirements for All Levels. An FBO, after becoming a Recognized | 11.01 | CA

Recall@1/5/10/20: False/False/False/False; selector: None; evidence: True; delivered: True
; expectation met: False

**Candidate answer**

I appreciate the question, but I need to clarify a couple of things:
If you have questions about the Canadian business plan or another country where Forever Living operates, I'm happy to help.

Citations: CA-EN-Company-Policy.pdf - Sec 4.01-d: Manager is achieved as soon as 120 Open Group Case Credits are generated | 4.01 | CA

Recall@1/5/10/20: False/False/False/False; selector: None; evidence: True; delivered: True
; expectation met: False

