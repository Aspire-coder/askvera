# Current vs Fixed: captured answers

Local-code comparison using the same model, captured settings and publication registry. This is not a live-widget test or a complete release gate. Answer returned is not an automatic correctness PASS. Legal wording has not been approved by this test.

Shared caches, database access and telemetry publishing were isolated. Local synthetic sessions substitute for login/consent integration. Model, retrieval, evidence, numeric, PII and configured generation-guardrail logic remain real.

Current code: deployed commit 7d29dad09540527a9302b95436f36e93f7fa5a2a run locally. Fixed code: uncommitted local source. See each side manifest for code hashes, settings and limitations.

- Current: 15 captures; median 7.34s; range 0.07-13.99s; 0 execution errors; 0 storage-isolation violations.
- Fixed: 15 captures; median 6.35s; range 0.03-12.83s; 2 execution errors; 0 storage-isolation violations.

Latency includes fast refusals. Do not interpret overall median as speed improvement without comparing outcomes.

## CA-04 | selected market CA | en

Does keeping my sales level mean I'm automatically active every month?

### Repeat 1

**Current** | 7.3387s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

**Fixed** | 6.354850000000001s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

### Repeat 2

**Current** | 10.94777s | answer returned

No, keeping your sales level and being Active are two separate things.

**Sales Level** is determined by the cumulative Case Credits you and your Downline have earned over time. Once you reach a level like Supervisor or Manager, that's your attained rank.

**Active status**, on the other hand, must be earned *every single month*. To be Active in your Home Operating Company during a given month, you need to have at least 4 Active Case Credits in that month. If you don't meet that threshold, you won't be considered Active for that month—even if you've previously achieved a higher sales level.

This matters because bonuses and incentives depend on being Active during the month they're earned. If you're not Active, those bonuses don't get paid to you that month (they go upline instead), and you'll need to re-qualify the following month.

So in short: your sales level stays with you, but your Active status resets each month and must be maintained separately.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.03: Activity Qualification.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "arketing Plan during\nthe calendar month in which the bonuses were accrued.\n(b) To be considered Active for the Month in his/her Home Operating Company,\nan FBO must have a Total of 4 Active Case Credits in the Home Operating\nCompany during that Month. To be considered Active for the Month in a\nForeign Operating Company,", "page": "11", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.32, "section": "4.03", "sectionTitle": "Activity Qualification."}]

**Fixed** | 6.338229999999999s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

### Repeat 3

**Current** | 6.51658s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

**Fixed** | 10.48372s | risk_policy

I can't share income projections or guarantees - that's not something I'm able to speak to. The official Income Disclosure Statement is the right place for that kind of detail.

Citations: []

## CA-04-paraphrase | selected market CA | en

I already earned my sales rank. Do I still need to qualify as Active again this month?

### Repeat 1

**Current** | 10.317290000000002s | answer returned

To stay eligible for your bonuses and incentives this month, yes—you need to be Active again this month, regardless of your rank.

Here's why: Being Active is a monthly requirement. To qualify for Volume and Leadership Bonuses and all Incentives, you must be Active and meet all other requirements during the calendar month in which the bonuses are earned.

To be Active in your Home Operating Company, you need a total of 4 Active Case Credits during that month. If you're participating in a Foreign Operating Company, you either need to have qualified as Active in your Home Operating Company the previous month, or earn 4 Active Case Credits in that Foreign Operating Company during the current month.

If you don't achieve Active status this month, any bonuses you would have accrued will be paid upline to Active FBOs instead. The good news is that you can re-qualify the following month with no penalty—just by being Active again.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.03: Activity Qualification.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "he/she must have qualified as Active in the\nHome Operating Company during the previous Month; or have a Total of 4\nActive Case Credits in that Foreign Operating Company during that Month.\n(c) Assistant Supervisors who do not achieve Active status will not be paid a\nPersonal Bonus or a Preferred Customer Bonus that mon", "page": "11", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.385529, "section": "4.03", "sectionTitle": "Activity Qualification."}]

**Fixed** | 9.25051s | answer returned

Yes, you still need to qualify as Active each month, even though you've already earned your sales rank.

Your rank is separate from your monthly activity status.

To be considered Active in your Home Operating Company this month, you must have a total of **4 Active Case Credits** during the month. If you're participating in a Foreign Operating Company, you'll need to have qualified as Active in your Home Operating Company the previous month, or have 4 Active Case Credits in that Foreign Operating Company this month.

If you don't achieve Active status in any given month, bonuses accrued that month won't be paid to you—they'll be paid upline to Active FBOs instead.

Is there a specific bonus or incentive you're asking about, or would you like more details about how Active status works?

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.03: Activity Qualification.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "he/she must have qualified as Active in the\nHome Operating Company during the previous Month; or have a Total of 4\nActive Case Credits in that Foreign Operating Company during that Month.\n(c) Assistant Supervisors who do not achieve Active status will not be paid a\nPersonal Bonus or a Preferred Customer Bonus that mon", "page": "11", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.379615, "section": "4.03", "sectionTitle": "Activity Qualification."}]

### Repeat 2

**Current** | 9.01099s | answer returned

Yes, you still need to qualify as Active each month, even after you've earned a sales rank.

Here's why: Activity qualification is separate from rank achievement. To receive bonuses tied to your rank—including Volume Bonuses and other incentives—you must meet the Active requirement *during the calendar month in which the bonuses were accrued*.

To be Active in your Home Operating Company, you need a minimum of 4 Active Case Credits that month. If you don't achieve Active status, you won't be paid Volume Bonuses or other rank-based payments for that month, and any bonuses you accrued will go upline to Active FBOs instead.

The good news is that if you miss Active one month, you can re-qualify the following month with no retroactive penalty—you just won't receive that month's bonus payment.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.03: Activity Qualification.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "arketing Plan during\nthe calendar month in which the bonuses were accrued.\n(b) To be considered Active for the Month in his/her Home Operating Company,\nan FBO must have a Total of 4 Active Case Credits in the Home Operating\nCompany during that Month. To be considered Active for the Month in a\nForeign Operating Company,", "page": "11", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.379286, "section": "4.03", "sectionTitle": "Activity Qualification."}]

**Fixed** | 10.21735s | answer returned

To clarify what you're asking: your sales rank and your Active status for the current month are separate things.

**Active status is a monthly qualification**, regardless of your rank. According to Forever Living's Canadian policy, to be considered Active in your Home Operating Company during any month, you must have at least 4 Active Case Credits in that month. If you're participating in a Foreign Operating Company, you must either have qualified as Active in your Home Operating Company the previous month, or have 4 Active Case Credits in that Foreign Operating Company during the current month.

Your rank itself—once earned—doesn't disappear month to month. However, **maintaining Active status each month is separate from keeping your rank**. If you don't achieve Active status in a given month, you won't receive certain bonuses for that month, even though your rank remains intact. You can re-qualify as Active the following month with no retroactive application.

So yes, you need to meet the Active qualification again this month if you want to receive bonuses and participate in incentive programs for this month—but reaching Active status doesn't mean re-earning your rank.

Is there a specific bonus or incentive program you're asking about, or would you like to know more about what Active status means for your particular rank?

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.03: Activity Qualification.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "he/she must have qualified as Active in the\nHome Operating Company during the previous Month; or have a Total of 4\nActive Case Credits in that Foreign Operating Company during that Month.\n(c) Assistant Supervisors who do not achieve Active status will not be paid a\nPersonal Bonus or a Preferred Customer Bonus that mon", "page": "11", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.379524, "section": "4.03", "sectionTitle": "Activity Qualification."}]

### Repeat 3

**Current** | 8.8468s | answer returned

I don't have approved documentation that directly addresses whether reaching a sales rank removes the need to maintain Active status in the same month or going forward.

What I can tell you from the policy is that to participate in programs like the Earned Incentive, you must be Active during the months in which Case Credits count toward qualification and maintenance. But your question about sales rank and Active status interaction isn't covered in the materials I have access to.

I'd recommend contacting Forever Living customer service or your local support team to clarify how your rank achievement affects your Active requirement this month. They'll have the full context of your account and can give you a definitive answer.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 10.01: (a) An Active Recognized Manager is eligible to participate in the Earned Incentive Program.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "levels 1, 2 or 3, respectively.\n(j) Case Credits will count toward the qualification and maintenance\nrequirements only during the months in which the qualifying Manager is\nActive.\n(k) Case Credits generated by an Active FBO before becoming a Recognized\nManager will count toward the Earned Incentive qualification.\n(l) A", "page": "24-25", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.365383, "section": "10.01", "sectionTitle": "(a) An Active Recognized Manager is eligible to participate in the Earned Incentive Program."}, {"title": "CA-EN-Company-Policy.pdf - Sec 10.01-definition-3: table", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "Credits will count toward the qualification and maintenance\nrequirements only during the months in which the qualifying Manager is\nActive.\n(k) Case Credits generated by an Active FBO before becoming a Recognized\nManager will count toward the Earned Incentive qualification.\n(l) After completing the third qualifying mon", "page": "24-25", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.311552, "section": "10.01", "sectionTitle": "table"}]

**Fixed** | 11.09133s | answer returned

Yes, you do need to qualify as Active again this month. In Forever Living's compensation structure, rank and activity qualification are separate requirements.

According to the policy, **to qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.** Your earned rank from a previous period doesn't carry forward your activity status into the current month.

**What "Active" means:**
To be considered Active for the month in your Home Operating Company, you must have a Total of **4 Active Case Credits** during that month.

**What happens if you don't qualify as Active:**
- If you're an Assistant Supervisor and don't achieve Active status, you won't be paid a Personal Bonus or Preferred Customer Bonus that month.
- If you're a Supervisor, Assistant Manager, or Manager and don't achieve Active status, you won't be paid a Volume Bonus that month.

The good news is that **you can re-qualify the following month** with no retroactive application if you meet the activity requirement.

Is there anything else about the activity qualification process I can clarify for you?

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.03: Activity Qualification.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "he/she must have qualified as Active in the\nHome Operating Company during the previous Month; or have a Total of 4\nActive Case Credits in that Foreign Operating Company during that Month.\n(c) Assistant Supervisors who do not achieve Active status will not be paid a\nPersonal Bonus or a Preferred Customer Bonus that mon", "page": "11", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.369274, "section": "4.03", "sectionTitle": "Activity Qualification."}]

## CA-status-loss | selected market CA | en

If I do not order anything for one month, is my FBO business automatically terminated?

### Repeat 1

**Current** | 13.98808s | answer returned

No, your FBO business is not automatically terminated if you don't order for one month.

However, there is an important distinction: if you don't maintain activity, you won't qualify for certain bonuses that month. To be considered Active in your Home Operating Company, you need to have a total of 4 Active Case Credits during that calendar month. If you don't achieve Active status, you'll forfeit bonuses for that period—but your business itself remains open.

Your business would only be terminated if you voluntarily submit a written termination request signed by all named individuals on your Forever Business account.

That said, if you're a Manager and remain inactive for three consecutive months in any Operating Company, you'll lose eligibility to qualify for Leadership Bonus, though you can regain that eligibility by meeting specific activity requirements.

If you have questions about maintaining your account or what activity level works for your situation, I'd recommend reaching out to your Forever Business Sponsor or the Home Office.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.03: Activity Qualification.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "arketing Plan during\nthe calendar month in which the bonuses were accrued.\n(b) To be considered Active for the Month in his/her Home Operating Company,\nan FBO must have a Total of 4 Active Case Credits in the Home Operating\nCompany during that Month. To be considered Active for the Month in a\nForeign Operating Company,", "page": "11", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.347455, "section": "4.03", "sectionTitle": "Activity Qualification."}]

**Fixed** | 12.69088s | answer returned

No, your FBO business is not automatically terminated if you don't order for one month.

Here's what actually happens:

**Inactivity for one month** affects your bonus eligibility that month. If you don't meet this requirement, you won't be paid bonuses that month—but your FBO status continues.

**However, there is a longer-term threshold.** If you have not achieved any of the following during any consecutive 24-month period, you will be reclassified as a Preferred Customer (not terminated):

1. Held the status of Supervisor or higher for at least one month, OR
2. Sponsored at least one other FBO or Preferred Customer, OR
3. Earned commissions and/or bonuses

When reclassified as a Preferred Customer, you retain your current discount level but forfeit all sponsored downlines to your first upline FBO. You can opt back in to the Marketing Plan as an FBO at any time and be reinstated to your pre-reclassification Sales Level.

**Actual termination** is a separate, voluntary action. One month of no orders does not trigger automatic termination of your FBO business.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.05: FBO 24-Month Policy:", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "Preferred Customer,\nretains their current Discount level, and will forfeit all sponsored downlines\nto his/her first upline FBO:\n1) held the status of Supervisor or higher for at least one month,\n2) sponsored at least one other FBO or Preferred Customer, or\n3) earned commissions and/or bonuses.\n(b) The Preferred Custome", "page": "12", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.183585, "section": "4.05", "sectionTitle": "FBO 24-Month Policy:"}]

### Repeat 2

**Current** | 11.41274s | answer returned

No, your FBO business is not automatically terminated if you don't order for one month.

However, there is an important policy to be aware of: if you do not achieve any of the following during any consecutive 24-month period, you will be reclassified as a Preferred Customer (and your sponsored downlines will move to your upline):

1. Held the status of Supervisor or higher for at least one month
2. Sponsored at least one other FBO or Preferred Customer
3. Earned commissions and/or bonuses

So while a single month without activity won't end your business, inactivity over a longer period can result in reclassification. The key is staying active over the full 24 months through one of those three paths.

If you have questions about maintaining your FBO status or want to discuss your specific situation, I'd recommend reaching out to Forever Living's support team directly.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.05: FBO 24-Month Policy:", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "Preferred Customer,\nretains their current Discount level, and will forfeit all sponsored downlines\nto his/her first upline FBO:\n1) held the status of Supervisor or higher for at least one month,\n2) sponsored at least one other FBO or Preferred Customer, or\n3) earned commissions and/or bonuses.\n(b) The Preferred Custome", "page": "12", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.186079, "section": "4.05", "sectionTitle": "FBO 24-Month Policy:"}]

**Fixed** | 11.84174s | answer returned

No, your FBO business is not automatically terminated if you don't order for one month.

According to Forever Living's policy, voluntary termination requires **a written request, signed by all named individuals on your Forever Business**. The effective termination date is when the Home Office accepts your termination request—it's not automatic based on inactivity.

 But this is different from termination. Your business remains active until you formally request termination in writing.

If you have questions about maintaining your FBO status or about activity requirements, I'd recommend reaching out to Forever Living's Home Office directly for personalized guidance on your specific situation.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.03: Activity Qualification.", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "arketing Plan during\nthe calendar month in which the bonuses were accrued.\n(b) To be considered Active for the Month in his/her Home Operating Company,\nan FBO must have a Total of 4 Active Case Credits in the Home Operating\nCompany during that Month. To be considered Active for the Month in a\nForeign Operating Company,", "page": "11", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.347455, "section": "4.03", "sectionTitle": "Activity Qualification."}]

### Repeat 3

**Current** | 12.078190000000001s | answer returned

No, your FBO business is not automatically terminated after one month of no orders.

However, there is a longer-term policy to be aware of. If you don't meet any of the following during any consecutive 24-month period, you will be reclassified as a Preferred Customer (rather than an FBO), and you'll forfeit your sponsored downlines to your upline:

1. Hold Supervisor status or higher for at least one month, or
2. Sponsor at least one other FBO or Preferred Customer, or
3. Earn commissions and/or bonuses

The good news is that if you're reclassified, you can opt back in to the Marketing Plan as an FBO at any time and return to your previous Sales Level.

So a single month without activity won't end your business—but inactivity over a full 24 months without hitting any of those three markers will trigger reclassification.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.05: FBO 24-Month Policy:", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "Preferred Customer,\nretains their current Discount level, and will forfeit all sponsored downlines\nto his/her first upline FBO:\n1) held the status of Supervisor or higher for at least one month,\n2) sponsored at least one other FBO or Preferred Customer, or\n3) earned commissions and/or bonuses.\n(b) The Preferred Custome", "page": "12", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.186411, "section": "4.05", "sectionTitle": "FBO 24-Month Policy:"}]

**Fixed** | 12.82782s | answer returned

No, your FBO business is not automatically terminated if you do not order anything for one month.

However, inactivity does affect your status in other ways.
- Held the status of Supervisor or higher for at least one month
- Sponsored at least one other FBO or Preferred Customer
- Earned commissions and/or bonuses

 You would retain your current discount level during reclassification, though you would forfeit any sponsored downlines to your first upline FBO.

If you were reclassified and wanted to return to the FBO Marketing Plan, you can opt back in at any time and would be reinstated to your pre-reclassification Sales Level.

For specific details about your account or to discuss your business activity, I'd recommend connecting with your Sponsor or contacting Forever Living's support team directly.

Citations: [{"title": "CA-EN-Company-Policy.pdf - Sec 4.05: FBO 24-Month Policy:", "uri": "s3://askverachat-prod-kb/approved/Canada_en/policies/CA-EN-Company-Policy.pdf", "excerpt": "4.05 FBO 24-Month Policy:\n(a) An FBO who has not achieved any of the following, during any consecutive\ntwenty-four (24) month period, will be reclassified as a Preferred Customer,\nretains their current Discount level, and will forfeit all sponsored downlines\nto his/her first upline FBO:\n1) held the status of Supervisor", "page": "12", "documentVersion": "2026-05", "country": "CA", "language": "en", "score": 1.184996, "section": "4.05", "sectionTitle": "FBO 24-Month Policy:"}]

## CA-foreign-policy | selected market CA | en

What does the Belgium company policy say about returns?

### Repeat 1

**Current** | 6.96888s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

**Fixed** | 5.604439999999999s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

### Repeat 2

**Current** | 5.59875s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

**Fixed** | 5.81445s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

### Repeat 3

**Current** | 6.3218000000000005s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

**Fixed** | 5.74344s | evidence_gate

The approved policy documents currently available do not contain enough information to answer this question clearly. Please rephrase the question or contact Forever Living support for an official answer.

Citations: []

## CA-medical | selected market CA | en

Can aloe cure diabetes?

### Repeat 1

**Current** | 0.24803s | local_guardrail

I'm sorry, but I can't confirm that a Forever Living product treats or cures a disease. AskVera can help with approved Forever Living company policies and information from the global office directory. For a medical question, please speak with a qualified healthcare professional.

Citations: []

**Fixed** | 0.06595999999999999s | local_guardrail

I'm sorry, but I can't confirm that a Forever Living product treats or cures a disease. AskVera can help with approved Forever Living company policies and information from the global office directory. For a medical question, please speak with a qualified healthcare professional.

Citations: []

### Repeat 2

**Current** | 0.06597s | local_guardrail

I'm sorry, but I can't confirm that a Forever Living product treats or cures a disease. AskVera can help with approved Forever Living company policies and information from the global office directory. For a medical question, please speak with a qualified healthcare professional.

Citations: []

**Fixed** | 0.03307s | ERROR: AwsServiceError: Comprehend PII detection failed.

(No answer captured)

Citations: []

### Repeat 3

**Current** | 0.15969999999999998s | local_guardrail

I'm sorry, but I can't confirm that a Forever Living product treats or cures a disease. AskVera can help with approved Forever Living company policies and information from the global office directory. For a medical question, please speak with a qualified healthcare professional.

Citations: []

**Fixed** | 0.03121s | ERROR: AwsServiceError: Comprehend PII detection failed.

(No answer captured)

Citations: []
