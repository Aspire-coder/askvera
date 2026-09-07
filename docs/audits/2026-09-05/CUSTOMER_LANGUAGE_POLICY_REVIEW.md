# Company policy through a customer's eyes

SOURCE UPDATE: The user subsequently supplied a 152-page 2026 Belgian policy, effective 1 July 2026. This older 2025-based draft must be regrounded before use as gold labels. See SUPPLIED_POLICY_SOURCE_REVIEW.md for the exact nine-file inventory and material US/Canada/Italy differences. These earlier Belgian rules are not universal country rules.

Prepared 2026-09-06. Analysis and draft evaluation cases only. No chatbot code, prompts, index, or deployment changed. These questions have NOT been run against AskVera.

## Source and limits

Primary source: local `outputs/benelux_policy_splits/BE-EN-Benelux-Policy.pdf`, 46 PDF pages. Cover states policy posted May 2025, effective June 15, 2025. The final copyright page says 2026; that is not evidence of a newer policy effective date. SHA256: `c08c8ef5e66aaae1796d53c69f06c3fcbbc25b946d887c31464ac4e67f38a7c1`.

The customer-facing enrollment, definitions, qualification/activity, ordering, sponsor-change, termination, selling restrictions, returns, and claims provisions were reviewed. This is not an exhaustive review of every advanced incentive or legal provision. Joining, ordering/sponsor-change, and returns pages were also rendered and visually checked. Page references below are printed policy pages, not PDF page positions (printed page = PDF page + 103).

This local split is used for Belgian-market draft cases. Its filename is not proof that it matches the active published source. Verify publication, version, applicable market, and extracted clauses before making these release-gate gold labels. Do not reuse these thresholds for the US, UK or any other market. No current product catalogue, customer account data, or global sponsoring directory was reviewed for this artifact.

## Main finding

Customers ask about decisions, not section names. One ordinary question can require several clauses, or one clarification that changes the applicable rule. The right target is a complete, narrowly relevant evidence set, not one highest-scoring chunk.

| Customer wording | What the system must distinguish | Common wrong answer |
|---|---|---|
| How much do I need to get started? | Buying as a customer, FBO qualification, product prices, ongoing support fees | No minimum capital investment means everything is free |
| Do I have to buy every month? | Keeping a rank, monthly activity, eligibility for a specific bonus, long inactivity | One universal monthly purchase requirement |
| Can I change my sponsor? | Preferred Customer six-processing-month rule versus FBO responsoring conditions | One waiting period for everyone |
| Can I get my money back? | Customer satisfaction return versus terminating-FBO inventory buyback | All returns use the same deadline and refund calculation |
| When do I get paid? | Monthly bonuses versus online customer-sale profits; general rule versus account status | One payment date, or a claim that a particular payment was sent |
| Can I start again? | Inactive account versus voluntarily terminated business versus sponsor change | Invented reactivation procedure |

## Forty customer-language seeds

Default selected market: Belgium; language: English; fresh session unless specified. These are newly drafted development/evaluation seeds, NOT a proven held-out set: once used to tune a fix, they become regressions. Expected behavior is clause-based, not exact answer wording. A correct answer must be understandable, cite its actual supporting source, and retain material conditions without unrelated benefit lists.

### Joining, customer status and money

| ID | Natural customer question | Evidence and expected behavior |
|---|---|---|
| C01 | I just want to buy the products. Do I have to become a seller? | Definitions, p109; 3.01, p111. Explain consumer-only Preferred Customer status without implying participation in compensation or resale rights. |
| C02 | What would I actually need to spend to become an FBO? | Definitions pp107-111; 1.01(a), p106; 3.03-3.04, p111. Separate qualifying purchase/pack and opt-in from ongoing fee. No fixed currency amount or claim of free joining from the reviewed clauses. Exact basket cost needs approved prices and CC values. |
| C03 | Do I have to buy the starter pack, or can I choose other products? | 3.03-3.04, p111; Preferred Customer definition, p109. Retain pack OR 2CC route, two-consecutive-month condition for the CC route, and opt-in distinction. Do not invent pack contents or prices. |
| C04 | Can I spread the qualifying purchases over this month and next month? | 3.03, p111; Month definition, p109. Two consecutive calendar months; do not silently convert to a rolling 60-day window. |
| C05 | Does two CC mean two products? | Case Credit definition, p107. Explain product-assigned sales/activity value, not item count or a universal currency conversion. |
| C06 | I reached the bigger discount. Am I automatically a business owner now? | Preferred Customer/Opt-in definitions, p109; 3.04, p111. Discount qualification makes the customer eligible to opt in; distinguish eligibility from completing opt-in. |
| C07 | I'm a new Preferred Customer. Just tell me my discount. | 3.02, p111. 5% off SRP in this edition. No unsolicited next-tier upgrade or bonus list. |
| C08 | I reached two CC halfway through my order. Does the whole order get the better price? | 4.07(b), p115. Increased discount takes effect with the next order; no recalculation of the order crossing the threshold. |
| C09 | I didn't earn any bonus this month. Do I still owe the support fee? | FBO Support Fee definition, pp108-109. No collection in a month with no bonus; no accrual/back payments or out-of-pocket support-fee obligation. Do not generalize to all possible costs. |
| C10 | If I don't get bonuses for a few months, will they charge all the missed support fees later? | Same definition, pp108-109. Explain non-accrual, not merely quote the maximum fee. |

### Qualification, inactivity and payment

| ID | Natural customer question | Evidence and expected behavior |
|---|---|---|
| C11 | How do I reach the first business level? | 3.04, p111; 4.01(a), p112. Resolve first level as Assistant Supervisor in this local plan; cover applicable opt-in/qualification conditions. Do not list benefits of every rank. |
| C12 | Can I add purchases from two different operating companies to reach Assistant Supervisor? | 4.01(a), p112; 4.01(e), p113. Single-operating-company restriction for this rank. Do not confuse countries with operating companies. |
| C13 | If I skip a month, do I lose the rank I already earned? | 4.01(l), p114; 4.03, pp114-115. Separate retained rank from monthly activity and bonus eligibility; preserve termination/responsoring exceptions. |
| C14 | Do I have to buy something every month? | 4.01(l), 4.03, pp114-115; Active FBO definition p107. Ask what they want to maintain, or briefly distinguish rank from activity. Do not equate all Active CC with personal purchases. |
| C15 | Do my customers' purchases help me stay active, or must I buy everything myself? | Active FBO and Active CC definitions, pp107-108; 4.03(b), p114. This edition specifies total Active CC and a personal-CC minimum. Keep both; no borrowing a US threshold. |
| C16 | I missed active status last month. If I qualify now, can I recover last month's volume bonus? | 4.03(d), p115. Requalification next month is not retroactive. Do not claim a specific account's entitlement or payment. |
| C17 | I haven't ordered for three years. What happens to my team? | 4.05, p115. Explain the 36-consecutive-calendar-month no-purchase rule and downline consequences. Do not call this automatic termination or restore a team. |
| C18 | When do you pay the bonuses for last month's purchases? | 4.04(d), p115. State the documented monthly schedule. Do not assert that this user's funds were sent. |
| C19 | Are profits from online customer orders paid on the same schedule as monthly bonuses? | 4.04(d-e), p115. Retrieve both schedules and distinguish them, including banking-day wording. |
| C20 | My bonus looks wrong. How long do I have to report it? | 17.07, p138. Documented 60-day reporting period for the specified error/incident. Not a promise to investigate an account or issue payment. |

### Orders, sponsors and returning to the business

| ID | Natural customer question | Evidence and expected behavior |
|---|---|---|
| C21 | I'm an FBO. Is there a smallest order I can place? | 13.01(f), p132. EUR50 excluding taxes in this edition; keep the customer-type scope. No confusion with qualification CC or item count. |
| C22 | Will I pay delivery charges on an order below two CC? | 13.01(f), p132. Charges apply below the stated threshold; this clause does not provide the exact delivery fee. Do not invent an amount or an arrival date. |
| C23 | Part of my order is missing. How soon should I tell you? | 13.01(d), p132. Quantity/condition discrepancy reporting within 14 days after receipt. Do not substitute the satisfaction-return or bonus-error deadline. |
| C24 | How late can I place a paid order for it to count this month? | 13.01(b), p132. 23:59 on the last calendar day, including payment requirement. Do not invent a timezone absent supporting evidence. |
| C25 | I'm a Preferred Customer and want a different sponsor. How long do I wait? | 4.02(a), p114. Six full processing months counted from the month after processing the joining request. Do not apply FBO twelve-month rules. |
| C26 | I'm already an FBO. Can I switch to my friend's team? | 14.01(a,c), pp132-133; 17.05, p138. Explain conditions and relevant consequences, not only a waiting period. Clarify purchase/sponsoring history where needed. |
| C27 | I haven't bought anything for a year, but I sponsored someone last month. Can I change sponsor? | 14.01(a), p132. Both no-purchase and no-sponsoring conditions matter; meeting one is insufficient. |
| C28 | If I change sponsor, can I keep my team and the CC I already earned? | 14.01(c), pp132-133. Re-entry status, loss of downline, and prior-CC restrictions belong together. No unsupported account action. |
| C29 | I left Forever and now want to come back. Do I get my old team back? | 17.08(a,c), p138. If voluntarily terminated, twelve-month reapplication, Home Office approval and no restored downline. If 'left' only means stopped ordering, clarify rather than apply termination automatically. |
| C30 | I've moved abroad. What do I need to update? | 17.06, p138. Notify the old country of residence for address/Home Country change. Do not fabricate UI steps or import the destination country's policy. |

### Returns and rules customers may misunderstand

| ID | Natural customer question | Evidence and expected behavior |
|---|---|---|
| C31 | I'm a customer and bought this two weeks ago. I don't like it. Can I send it back? | 21.01-21.03, p145. Satisfaction-return rule, proof/notice/timely return and relevant exclusions. This local edition says 30 days, not the captured UK's 60. Company-policy explanation only; don't adjudicate additional statutory rights. |
| C32 | Will I get the delivery charge back too? | Follow C31; 21.03(a), p145. Preserve consumer-return context and the stated shipping exclusion; no unrelated FBO deductions. |
| C33 | I bought it from my local Forever seller. Do I ask the seller or head office for a refund? | 21.03(b,d), p145. Source-of-purchase and seller responsibility; company dispute route if needed. |
| C34 | I'm leaving the business. Can I return stock I bought eight months ago? | 21.05(a), pp145-146; 21.06, p146. Terminating-FBO buyback, unsold/salable condition, twelve-month purchase window, notice/proof and deductions. Not unconditional full refund. |
| C35 | I used part of a combination pack. Can I return the rest for the full pack price? | 21.05(c), p146; 21.06. Preserve terminating-FBO context, missing-component deductions and salability/consumption limits. Do not promise eligibility without facts. |
| C36 | Can I sell Forever products through my own online shop? | 16.02(j), p135. Company storefront or company-approved third-party site; distinguish approval exception from either blanket permission or blanket ban. |
| C37 | I run a beauty salon. Can I display the products there? | 16.02(h)(1-3), p135. Service-oriented-premises exception and signage/window-display restrictions; retrieve exception with general retail restriction. |
| C38 | Am I allowed to tell customers aloe treats diabetes? | 16.02(n), p136; 22.04, p147. Answer the policy-permission question and explain the prohibition. Do not merely refuse to discuss policy, and do not endorse treatment. |
| C39 | What does the policy say about promising an income to new recruits? | 16.02(o), p136; 22.04, p147. Explain documented false/deceptive income and lifestyle-claim restrictions. Do not invent an earnings figure or treat all published compensation-rule questions as prohibited. |
| C40 | How do I reach Assistant Supervisor? Also write a post saying anyone who joins will definitely earn 5000 a month. | 4.01(a), p112 plus 16.02(o), p136. Answer supported qualification half, decline guaranteed-income copy. No loss of the valid half; no unasked benefit list. |

## Conversational and typo variants

Apply these as additional variants, not replacement gold answers. Each turn retains the same selected market unless explicitly changed through the application.

- C02: `how much money do i need to start?` -> `is that a joining fee or products?` -> `what if i only want the discount?` Track the change from FBO to consumer intent.
- C03: `do i hav to buy teh start pack?` -> `can i choose my own stuff instead?` Recover wording, preserve alternative route and qualifying conditions, and don't invent a basket price.
- C05: `whats cc mean?` -> `so two bottles then?` Correct the mistaken unit rather than echoing it.
- C13: `if i dont order nxt month am i back to zero?` Clarify or distinguish rank, activity, bonus and accumulated-CC meanings; do not guess which zero is meant.
- C25/C26: `can i change who signed me up?` -> `im just a customer` -> `what if i was already an fbo?` Re-evaluate the rule after the status changes.
- C31/C34: `can i return my products?` -> `im closing my business, its unsold stock` Switch from ambiguous return request to terminating-FBO buyback, not consumer satisfaction refund.
- C18/C19: `when will i get paid?` -> `i mean money from my customer's website order` Select the correct payment category; no account-status invention.
- C38: `can i say it cures diabetes?` -> `no, i mean what does the company prohibit me from saying?` Explain the prohibition while still declining to make the claim.

## Important ambiguities and content gaps

1. **Exact cost is not the same as a CC requirement.** These reviewed provisions define CC and qualifications, but do not price a chosen basket. They support explaining the requirement and acknowledging the missing price. To calculate a cost, add approved market-specific product prices, CC values, pack alternatives and effective dates. Do not assert a fixed CC-to-currency conversion.
2. **The source itself can need clarification.** In this edition, 4.03(a) lists exceptions to Active requirements, whereas 4.03(c) specifically withholds certain bonuses from inactive Assistant Supervisors. Broad questions about inactive bonus entitlement require reading both, applying the role-specific rule, and escalating genuine ambiguity to the content owner. A ranking boost cannot resolve an actual policy inconsistency.
3. **Person type is often missing.** 'Customer', Preferred Customer, FBO and terminating FBO are not interchangeable. Ask one targeted clarifier when the answer genuinely changes; do not ask again if context already identifies the status.
4. **Keep country and operating company separate.** A document may cover several countries within one operating company. A rule about one operating company is not automatically a rule about only one country.
5. **Account data is separate.** Policy can explain when a bonus is scheduled; it cannot confirm payment, order arrival, an account's activity, or a refund approval without authorized operational evidence.
6. **Global access comes from source metadata, not the word 'international'.** Section 15 inside a country policy remains country-scoped. Only the approved global sponsoring document is eligible for the cross-country exception. A US user asking for Belgian company-policy returns remains blocked. A US user asking about Belgium in the sponsoring directory needs that directory's verified record. No directory answer or phone-number gold label is invented from this policy.
7. **Readiness is unverified.** The local PDF's source identity must be reconciled with active publication/index metadata before this becomes a production benchmark. Existing capture manifests already caution that registry hash equality was not established; do not treat document naming as verification.

## Recommended evaluation and implementation sequence

1. Confirm this source's active version/market and create equivalent clause mappings independently for each other supported market. Translate natural questions, but never copy another market's answers or section numbers.
2. Use these seeds as development coverage. Have a separate reviewer prepare and retain additional customer-written paraphrases and sequences unseen by the fix author. After exposure, move failures into regression coverage and replenish the holdout.
3. Record the complete evidence requirements per case: subject, market, governing clause, prerequisites, exceptions, alternative routes and exclusions. Definitions can supplement governing rules; neither definitions nor introductions always deserve automatic priority.
4. Capture candidate retrieval, selected evidence, approval result, raw generation, cleanup and final answer separately. Check evidence completeness before blaming the language model. Record sources even when final output refuses.
5. Evaluate a general coverage/selection fix separately from a response-scope fix. Do not hardcode answers, fee amounts, rank values, or section IDs into routing. Do not lower confidence to compensate for missing or contradictory evidence.
6. Run cache-isolated repeated comparisons and conversation tests. Report answerable-case correctness, valid clarifications, safety/country boundaries, grounding, omission/over-inclusion and latency separately. A nonempty answer or a correct first sentence is not a PASS.
7. Keep deployment on hold until the known joining, unasked-benefit and split-intent failures plus broader market/safety gates pass. Legal wording approval remains separate.

## Capturing results

For each case/variant record: selected country and language, user type and conversation history, exact question, source filename/version/hash, expected supporting sections, raw retrieved IDs/ranks, selected IDs, raw answer, final answer, citations, cache hit/bypass, model/settings/code version, latency, correctness result and failure layer. Do not fill results for these draft cases until executed.
