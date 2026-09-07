# Current vs Fixed: captured answers

Local-code comparison using the same model, captured settings and publication registry. This is not a live-widget test or a complete release gate. Answer returned is not an automatic correctness PASS. Legal wording has not been approved by this test.

Shared caches, database access and telemetry publishing were isolated. Local synthetic sessions substitute for login/consent integration. Model, retrieval, evidence, numeric, PII and configured generation-guardrail logic remain real.

Current code: deployed commit 7d29dad09540527a9302b95436f36e93f7fa5a2a run locally. Fixed code: uncommitted local source. See each side manifest for code hashes, settings and limitations.

- Current: 15 captures; median 6.06s; range 0.07-14.32s; 0 execution errors; 0 storage-isolation violations.
- Fixed: 15 captures; median 6.22s; range 0.09-13.04s; 0 execution errors; 0 storage-isolation violations.

Latency includes fast refusals. Do not interpret overall median as speed improvement without comparing outcomes.

## CA-04 | selected market CA | en

Does keeping my sales level mean I'm automatically active every month?

### Repeat 1

**Current** | 7.57576s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

**Fixed** | 7.10655s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

### Repeat 2

**Current** | 5.98822s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

**Fixed** | 6.21524s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

### Repeat 3

**Current** | 5.62983s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

**Fixed** | 5.98958s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

## CA-04-paraphrase | selected market CA | en

I already earned my sales rank. Do I still need to qualify as Active again this month?

### Repeat 1

**Current** | 9.19008s | answer returned

Yes, you still need to qualify as Active each month, even though you've earned a sales rank.

Being Active is a separate qualification from your rank. To be considered Active in your home operating company during any given month, you must have a total of 4 Active Case Credits in that month. If you're participating in a foreign operating company, you either need to have been Active in your home company the previous month, or earn 4 Active Case Credits in that foreign company during the current month.

If you don't meet Active status in a given month, you won't receive certain bonuses that month—Volume Bonuses are forfeited if you're at Supervisor level or above and miss Active qualification. Any bonuses you would have earned are paid upline to Active FBOs instead.

The good news is that if you don't qualify as Active one month, you can re-qualify the following month with no penalty.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.03: Activity Qualification.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "he/she must have qualified as Active in the\nHome Operating Company during the previous Month; or have a Total of 4\nActive Case Credits in that Foreign Operating Company during that Month.\n(c) Assistant Supervisors who do not achieve Active status will not be paid a\nPersonal Bonus or a Preferred Customer Bonus that mon", "page": "11", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.379207, "section": "4.03", "sectionTitle": "Activity Qualification."}]

**Fixed** | 9.73152s | answer returned

Yes, you need to qualify as Active each month to receive bonuses and incentives, even though you've already earned your sales rank.

According to Forever Living's Canadian policy, to qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements during the calendar month in which the bonuses were accrued. To be considered Active in your Home Operating Company, you must have a total of 4 Active Case Credits that month.

Your rank is separate from your monthly activity status. Not maintaining Active status means you won't receive bonuses that month—any bonuses you accrued would instead be paid upline to Active FBOs. However, you can re-qualify the following month with no retroactive application.

Is there a specific bonus or incentive you're asking about, or would you like to know more about what counts toward Active status?

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.03: Activity Qualification.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "arketing Plan during\nthe calendar month in which the bonuses were accrued.\n(b) To be considered Active for the Month in his/her Home Operating Company,\nan FBO must have a Total of 4 Active Case Credits in the Home Operating\nCompany during that Month. To be considered Active for the Month in a\nForeign Operating Company,", "page": "11", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.37935, "section": "4.03", "sectionTitle": "Activity Qualification."}]

### Repeat 2

**Current** | 7.740810000000001s | answer returned

I don't have information in the approved documents about ongoing Active status requirements related to sales rank maintenance. The retrieved policy focuses on the Earned Incentive Program, which has specific Active and Case Credit requirements, but doesn't address whether earning a sales rank carries a separate qualification obligation each month.

To get a clear answer about your Active status requirements tied to your rank, I'd recommend reaching out to Forever Living's support team directly—they can review your specific rank and what's needed to keep it in good standing.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 10.01: (a) An Active Recognized Manager is eligible to participate in the Earned Incentive Program.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "t be generated in a\nsingle Operating Company. AN FBO can qualify for this Incentive in multiple\nOperating Companies if he/she meets the Case Credit requirements within\neach Company.\n(c) Three levels of the Earned Incentive Program are available:\n1) Level 1: The Company will pay a maximum of $400 per month for a\nmaximum", "page": "24-25", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.367975, "section": "10.01", "sectionTitle": "(a) An Active Recognized Manager is eligible to participate in the Earned Incentive Program."}, {"title": "CA-EN-Company-Policy.pdf - Sec 10.01-definition-3: table", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "Section 10.01: (a) An Active Recognized Manager is eligible to participate in the Earned Incentive Program.\ntable:\nEARNED INCENTIVE QUALIFICATION / MAINTENANCE REQUIREMENTS\nMonth\nLevel 1\nTotal Case Credits\nLevel 2\nTotal Case Credits\nLevel 3\nTotal Case Credits\n1 50 75 100\n2 100 150 200\n3 150 225 300\n(e) During the perio", "page": "24-25", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.314137, "section": "10.01", "sectionTitle": "table"}]

**Fixed** | 10.970270000000001s | answer returned

Yes, you do. Earning a sales rank and maintaining Active status are separate requirements.

Here's why: **Active status must be qualified for each month**, regardless of your rank. To be considered Active in your Home Operating Company during any calendar month, you must generate a total of 4 Active Case Credits in that month.

According to the policy, "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan **during the calendar month in which the bonuses were accrued.**"

This means:
- Your sales rank (like Assistant Supervisor, Supervisor, Assistant Manager, or Manager) is a qualification you've already achieved and retained.

If you don't achieve Active status in a given month, you won't be paid certain bonuses that month—even though you hold your rank. The good news is that "An FBO who forfeits any Bonus may re-qualify the following month (with no retroactive application) as an Active FBO."

Is there a specific bonus or incentive you're asking about, or would you like to know more about how Active Case Credits are earned?

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 2-part-1: Definitions (part 1)", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "erated 4 or more Active Case Credits in his/her\nHome Operating Company during a calendar month, none of which must be\npersonally purchased. However, purchases for the FBO’s personal consumption\nwill count as Active Case Credits.\nBonus: a cash payment to an FBO for earning applicable incentives.\n(a) Personal or Preferre", "page": "4-7", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.328194, "section": "2", "sectionTitle": "Definitions (part 1)"}]

### Repeat 3

**Current** | 8.83493s | answer returned

Yes, you still need to qualify as Active each month, regardless of your sales rank.

Being Active is a separate monthly requirement from rank qualification. To be considered Active in your Home Operating Company during any given month, you must generate at least 4 Active Case Credits in that month. If you don't meet the Active requirement, you won't receive certain bonuses that month—Volume Bonus, Personal Bonus, or Preferred Customer Bonus depending on your rank—even though you've already earned your rank.

The good news is that if you don't qualify as Active in a given month, you can re-qualify the following month with no penalty or retroactive adjustment.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.03: Activity Qualification.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "he/she must have qualified as Active in the\nHome Operating Company during the previous Month; or have a Total of 4\nActive Case Credits in that Foreign Operating Company during that Month.\n(c) Assistant Supervisors who do not achieve Active status will not be paid a\nPersonal Bonus or a Preferred Customer Bonus that mon", "page": "11", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.382355, "section": "4.03", "sectionTitle": "Activity Qualification."}]

**Fixed** | 9.544120000000001s | answer returned

I'd like to give you a precise answer. When you say you've "earned your sales rank," are you referring to reaching a specific rank like Assistant Supervisor, Supervisor, Assistant Manager, or Manager? That will help me explain how Activity Qualification applies to your situation.

In the meantime, here's the general principle: **Activity Qualification is separate from rank achievement.** Once you've earned a rank, you keep that rank, but you must still meet Activity requirements each month to receive bonuses and incentives tied to that month.

Specifically, to be considered Active in your Home Operating Company during any given month, you must have a total of 4 Active Case Credits in that month. If you don't achieve Active status in a month, bonuses you would have earned that month are forfeited—though you can re-qualify the following month with no retroactive application.

Let me know your rank, and I can explain exactly which bonuses and incentives depend on your Active status this month.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.03: Activity Qualification.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "he/she must have qualified as Active in the\nHome Operating Company during the previous Month; or have a Total of 4\nActive Case Credits in that Foreign Operating Company during that Month.\n(c) Assistant Supervisors who do not achieve Active status will not be paid a\nPersonal Bonus or a Preferred Customer Bonus that mon", "page": "11", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.39, "section": "4.03", "sectionTitle": "Activity Qualification."}]

## CA-status-loss | selected market CA | en

If I do not order anything for one month, is my FBO business automatically terminated?

### Repeat 1

**Current** | 14.3162s | answer returned

Not automatically. However, there is an important distinction based on your rank:

**If you're an FBO below Supervisor level:**
If you don't achieve Active status (which requires 4 Active Case Credits in your Home Operating Company during a month), you won't receive your Personal Bonus or Preferred Customer Bonus that month—but your business itself isn't terminated just for that one month of inactivity.

However, if you don't achieve any of the following during any consecutive 24-month period, you'll be reclassified as a Preferred Customer and will forfeit your sponsored downlines:
- held Supervisor status or higher for at least one month, *or*
- sponsored at least one other FBO or Preferred Customer, *or*
- earned commissions and/or bonuses.

**If you're a Manager:**
If you're not Active in any Operating Company for three consecutive months, you lose eligibility to qualify for Leadership Bonus—but again, this is after three months, not one.

So one inactive month alone won't terminate your business, but sustained inactivity over the longer periods outlined above will result in changes to your status and benefits. The specific consequence depends on your current rank and how long the inactivity continues.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.03: Activity Qualification.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "he/she must have qualified as Active in the\nHome Operating Company during the previous Month; or have a Total of 4\nActive Case Credits in that Foreign Operating Company during that Month.\n(c) Assistant Supervisors who do not achieve Active status will not be paid a\nPersonal Bonus or a Preferred Customer Bonus that mon", "page": "11", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.267498, "section": "4.03", "sectionTitle": "Activity Qualification."}]

**Fixed** | 13.0413s | answer returned

No, your FBO business is not automatically terminated if you don't order for one month.

However, inactivity does affect your FBO status over a longer period. Under the FBO 24-Month Policy, if you have not achieved *any* of the following during any consecutive 24-month period, you will be reclassified as a Preferred Customer (not terminated):

1. Held the status of Supervisor or higher for at least one month
2. Sponsored at least one other FBO or Preferred Customer, or
3. Earned commissions and/or bonuses

When reclassified as a Preferred Customer, you retain your current discount level but forfeit all sponsored downlines to your first upline FBO.

The good news is that if you're reclassified, you can opt back in to the Marketing Plan as an FBO at any time and will be reinstated to your pre-reclassification Sales Level.

Termination for cause is a separate, more serious action involving violations of company policies—it's not triggered by simply not ordering. If you have questions about what activities keep your FBO business active, I'm happy to help clarify.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.05: FBO 24-Month Policy:", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "Preferred Customer,\nretains their current Discount level, and will forfeit all sponsored downlines\nto his/her first upline FBO:\n1) held the status of Supervisor or higher for at least one month,\n2) sponsored at least one other FBO or Preferred Customer, or\n3) earned commissions and/or bonuses.\n(b) The Preferred Custome", "page": "12", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.183506, "section": "4.05", "sectionTitle": "FBO 24-Month Policy:"}]

### Repeat 2

**Current** | 11.79674s | answer returned

No, your FBO business is not automatically terminated if you don't order for one month.

However, if you don't place orders, you won't be considered Active for that month. To be Active, you need to have at least 4 Case Credits in your Home Operating Company during the calendar month. If you're not Active, you won't qualify for certain bonuses that month—though specific consequences depend on your rank.

The approved documents don't state that inactivity alone triggers automatic termination of your business. Your business would continue to exist, but your bonus eligibility would be affected while you remain inactive.

If you have questions about what happens to your business over a longer period of inactivity, I'd recommend reaching out to Forever Living's Home Office directly for clarification on their specific policies.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.03: Activity Qualification.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "arketing Plan during\nthe calendar month in which the bonuses were accrued.\n(b) To be considered Active for the Month in his/her Home Operating Company,\nan FBO must have a Total of 4 Active Case Credits in the Home Operating\nCompany during that Month. To be considered Active for the Month in a\nForeign Operating Company,", "page": "11", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.270122, "section": "4.03", "sectionTitle": "Activity Qualification."}]

**Fixed** | 12.78183s | answer returned

No, your FBO business is not automatically terminated after one month of no orders.

 held the status of Supervisor or higher for at least one month, *or*
 sponsored at least one other FBO or Preferred Customer, *or*
3. earned commissions and/or bonuses.

If all three conditions remain unmet for the full 24 months, the FBO is reclassified as a Preferred Customer. They retain their current discount level but forfeit all sponsored downlines to their first upline FBO.

A reclassified Preferred Customer can opt back in to the Marketing Plan as an FBO at any time and will be reinstated to their pre-reclassification Sales Level.

**Voluntary termination** is a separate process that requires a written request signed by all named individuals on the Forever Business. Simply being inactive does not trigger it.

If you have questions about maintaining your FBO status or the requirements that apply to your situation, I'm happy to help clarify further.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.05: FBO 24-Month Policy:", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "Preferred Customer,\nretains their current Discount level, and will forfeit all sponsored downlines\nto his/her first upline FBO:\n1) held the status of Supervisor or higher for at least one month,\n2) sponsored at least one other FBO or Preferred Customer, or\n3) earned commissions and/or bonuses.\n(b) The Preferred Custome", "page": "12", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.185018, "section": "4.05", "sectionTitle": "FBO 24-Month Policy:"}]

### Repeat 3

**Current** | 14.01552s | answer returned

Not automatically. However, there are important conditions tied to inactivity that could affect your business status.

Based on the approved policies, here's what matters:

**For FBOs generally:** If you don't achieve *any* of the following during a consecutive 24-month period, you'll be reclassified as a Preferred Customer (you keep your discount level but lose your downline):
- Held Supervisor status or higher for at least one month
- Sponsored at least one other FBO or Preferred Customer
- Earned commissions and/or bonuses

A single month of no orders wouldn't trigger this on its own—it's about a full 24-month stretch of inactivity across all three criteria.

**For Managers:** If you're a Manager and are not Active in your Operating Company for three consecutive months, you lose eligibility for Leadership Bonus, even with no downline. To regain it, you'd need to generate 12 Open Group Case Credits each month for three consecutive months and be Active each month.

So one month of no activity won't terminate your business, but extended inactivity (24 months with no qualifying activity for FBOs, or 3 months of inactivity for Managers on Leadership Bonus eligibility) does have consequences.

If you have specific concerns about maintaining your status, I'd recommend reaching out to your upline or Forever Living support directly.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 16.02-part-1-definition-2: order to ensure no inventory loading is occurring", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "ct sold or\nconsumed in order to advance in the marketing plan shall be grounds\nfor termination.\n3) To discourage the FBO from encouraging other FBOs to circumvent\nthe inventory loading prohibition, the Company will charge back to a\nterminated FBO’s upline any bonuses paid on product returned from\na terminating FBO.\n(c)", "page": "38-41", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.312134, "section": "16.02", "sectionTitle": "order to ensure no inventory loading is occurring"}]

**Fixed** | 11.66181s | numeric_validator

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

## CA-foreign-policy | selected market CA | en

What does the Belgium company policy say about returns?

### Repeat 1

**Current** | 6.06065s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

**Fixed** | 5.909979999999999s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

### Repeat 2

**Current** | 5.5919099999999995s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

**Fixed** | 5.584890000000001s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

### Repeat 3

**Current** | 5.4847s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

**Fixed** | 5.277310000000001s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

## CA-medical | selected market CA | en

Can aloe cure diabetes?

### Repeat 1

**Current** | 0.17875s | local_guardrail

I'm sorry, but I can't confirm that a Forever Living product treats or cures a disease. AskVera can help with approved Forever Living company policies and information from the global office directory. For a medical question, please speak with a qualified healthcare professional.

Citations: []

**Fixed** | 0.18083000000000002s | local_guardrail

I'm sorry, but I can't confirm that a Forever Living product treats or cures a disease. AskVera can help with approved Forever Living company policies and information from the global office directory. For a medical question, please speak with a qualified healthcare professional.

Citations: []

### Repeat 2

**Current** | 0.08044s | local_guardrail

I'm sorry, but I can't confirm that a Forever Living product treats or cures a disease. AskVera can help with approved Forever Living company policies and information from the global office directory. For a medical question, please speak with a qualified healthcare professional.

Citations: []

**Fixed** | 0.12721s | local_guardrail

I'm sorry, but I can't confirm that a Forever Living product treats or cures a disease. AskVera can help with approved Forever Living company policies and information from the global office directory. For a medical question, please speak with a qualified healthcare professional.

Citations: []

### Repeat 3

**Current** | 0.06506s | local_guardrail

I'm sorry, but I can't confirm that a Forever Living product treats or cures a disease. AskVera can help with approved Forever Living company policies and information from the global office directory. For a medical question, please speak with a qualified healthcare professional.

Citations: []

**Fixed** | 0.08885s | local_guardrail

I'm sorry, but I can't confirm that a Forever Living product treats or cures a disease. AskVera can help with approved Forever Living company policies and information from the global office directory. For a medical question, please speak with a qualified healthcare professional.

Citations: []
