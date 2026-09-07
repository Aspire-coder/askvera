# Supplied policy sources: first-pass findings and customer questions

Targeted follow-up completed on 2026-09-06: see [Market-specific customer scenarios](./MARKET_POLICY_CUSTOMER_SCENARIOS.md) for returns, sponsor changes, activity and ordering across all eight supplied policies, 40 additional draft cases and unresolved source ambiguities. These cases have not been run against the chatbot; this does not complete the full-source audit or re-label every question in the older draft.

2026-09-06. Read-only source analysis; no application changes, uploads, reindexing or deployment. This is an initial enrollment/qualification and source-identity review, not a completed clause-by-clause audit of all nine PDFs. Questions below are not yet executed or scored.

## Critical correction to earlier evaluation

The supplied US policy, section 1.01(c-d), PDF pages 2-3, states that new FBO sponsoring in the US ceases from May 1, 2026 and that the FBO opportunity and related incentives are unavailable to US residents from that date. Purchasing and customer sales continue, with transitional provisions for existing downlines through the end of 2026.

Consequently, a correct 2CC Assistant Supervisor sentence from 4.01(a) is NOT by itself a complete answer to a new US resident asking how to join. The earlier cleanup tests verified preservation of that sentence, not full applicability of the answer. Qualification, enrollment eligibility, user status and effective date must be evaluated together. The US introduction and pages 3 and 8 were visually inspected to verify this distinction.

Canada is materially different: section 3.03 on PDF page 8 permits a Preferred Customer to opt in as an FBO at any time. Section 3.04 addresses a 2CC pathway to Assistant Supervisor. Do not impose a universal personal 2CC purchase prerequisite on Canadian FBO enrollment. This page was visually inspected.

Italy is also different: section 4.01, PDF page 13, describes the Promoter role and says its 2CC can be reached through Clienti Club orders and/or personal purchases over one or two consecutive months. Section 3, PDF page 12, separately describes the Cliente Privilegiato route. Do not collapse these roles into one universal enrollment rule. Page 13 was visually inspected; regulatory references are reported only as policy content, not independently verified legal guidance.

## Source inventory

All eight policies are located under `C:/Users/KRISH/AppData/Local/Temp/`, with exact filenames below. The directory is at `C:/Users/KRISH/Downloads/International_Sponsoring_Directory (1).pdf`. The observed languages refer to the reviewed portions, not a certification of every page's language.

| Source filename | PDF pages | Observed language / edition evidence | Required caution |
|---|---:|---|---|
| Forever Living Products Belgium Company Policy (1).pdf | 152 | Dutch, French, English; English edition page 106: posted 1 June 2026, effective 1 July 2026 | Earlier 46-page English split used May/June 2025 text. Re-label the old draft against this new source. |
| Forever Living Products Netherlands Company Policy (1).pdf | 152 | Dutch, French, English; English edition page 106: posted 1 June 2026, effective 1 July 2026 | Similar Benelux content, but different file hash. Do not assume byte or clause equivalence. |
| Forever Living Products Canada Company Policy (1).pdf | 62 | Reviewed English; cover effective 1 May 2026, posted 1 April 2026 | Opt-in and Assistant Supervisor qualification are distinct. |
| Forever Living Products Germany Company Policy (1).pdf | 68 | German; published 1 June 2026, effective 1 July 2026; DACH entities on cover | Do not invent an English source or treat the filename alone as the complete market applicability metadata. |
| Forever Living Products Italy Company Policy (1).pdf | 90 | Italian; effective date not established in this first pass | Preserve Promoter/Cliente Club/Cliente Privilegiato/FBO distinctions and inspect annexes before final labels. |
| Forever Living Products Sweden Company Policy (1).pdf | 55 | Reviewed English; Europe/Scandinavia; posted 1 June 2026, effective 1 July 2026 | Do not assume Swedish-language source text from the filename. |
| Forever Living Products U.K. Company Policy (1).pdf | 32 | English; contents spread dated 1 July 2026 | Two printed pages can share one PDF page. Store both page systems. |
| Forever Living Products U.S. Company Policy (1).pdf | 37 | English; US only; effective 1 May 2026 | Dated enrollment restrictions take precedence over a generic interpretation of remaining rank provisions. |
| International_Sponsoring_Directory (1).pdf | 235 | Reviewed English; effective publication date not established in first pass | Global scope permits access, not automatic applicability or precedence over newer local restrictions. |

## Verified source-language differences in common questions

| Market | Customer wording | Reviewed evidence | Expected distinction |
|---|---|---|---|
| US | I'm new. How much must I buy to become an FBO now? | 1.01(c-d), PDF 2-3; 4.01(a), PDF 8 | Lead with dated availability restriction for a US resident, not 2CC shopping instructions. Selected market is not conclusive proof of residency. |
| Canada | Can I join before I have two CC? | 3.03-3.04, PDF 8 | Opt-in at any time versus qualification at Assistant Supervisor; do not infer a free monetary cost from these clauses. |
| Belgium | Do I need the starter pack, or can I choose products? | 3.03-3.04, PDF 113 English; PDF 12 Dutch; PDF 64 French | Pack or 2CC alternative and opt-in eligibility; preserve time window. |
| Netherlands | Moet ik een startpakket kopen of kan ik zelf producten kiezen? | 3.03-3.04, PDF 12 | Same question grounded independently in this file's Dutch clauses. |
| UK | If I get the bigger discount, am I automatically an FBO? | 3.3-3.4, PDF 6, printed 10-11 | Eligibility to opt in is not automatic opt-in. |
| Germany | Muss ich erst zwei Case Credits kaufen, um FBO zu werden? | 3.03-3.04, PDF 9 | Explain the reviewed purchase/registration conditions; do not import another country's starter-pack option without German evidence. |
| Sweden | Can I choose products instead of a Start Your Journey Pack? | 3.03-3.04, PDF 8 | Reviewed English source has alternative route and opt-in distinction. A Swedish answer would be cross-language generation, not proof of a Swedish PDF. |
| Italy | Sono Promoter: contano anche gli ordini dei miei Clienti Club per i due CC? | 4.01(3), PDF 13 | Client orders and/or personal purchases for the stated Promoter route. Do not say all qualifying volume must be bought personally. |

Exact product-basket cost requires approved market-specific prices and CC values, not a generic conversion from CC to currency. This first pass has not established a current price catalogue or a complete monetary-cost answer for each country.

## Twenty-seven additional natural-language evaluation seeds

Each group uses its own selected policy market. Directory cases explicitly identify global source scope. These are proposed development cases, not a pristine held-out benchmark once used for fixes.

### United States - PDF pages 2-3 and 8

1. "I live in the US and want to sign up as a new FBO today. What do I need to do?" Include current dated restriction; don't supply a new-enrollment pathway.
2. "If I buy two CC, can I become an FBO even with the new US rules?" Do not let qualification text override enrollment availability.
3. "I've been an FBO for years. Does the May change mean I can't buy or sell products anymore?" Distinguish continued product/customer sales and existing-business transition from the new-applicant restriction; no guaranteed personal earnings.

### Canada - PDF page 8

4. "Do I have to wait until I reach two CC before opting in?" Retrieve 3.03 as well as 3.04.
5. "What's the difference between becoming an FBO and becoming Assistant Supervisor?" Explain both statuses without unasked bonus lists.
6. "I haven't bought anything yet. Does that paragraph prove joining costs nothing?" Do not turn permission to opt in into unsupported zero-price wording.

### Belgium - PDF pages 12, 64 and 113

7. "Kan ik gewoon klant blijven zonder te verkopen?" Ground consumer status in 3.01 and applicable definitions; don't turn shopping into compulsory business enrollment.
8. "Dois-je acheter le pack de démarrage ou puis-je choisir mes produits ?" Use French 3.03 and preserve alternatives.
9. "I qualified for the discount. Can I sell now, or is there another step?" Read opt-in eligibility with consumer/FBO rights; don't equate discount status with completion of enrollment.

### Netherlands - PDF page 12

10. "Kan ik de aankopen over deze en volgende maand spreiden?" Preserve two consecutive months; don't substitute a rolling day count.
11. "Ik wil alleen korting, geen eigen bedrijf. Kan dat?" Consumer route, no unwanted upsell.
12. "Welke korting krijg ik als nieuwe Preferred Customer? Alleen het percentage graag." Preserve 'up to' wording in this edition; no unsolicited upgrade path.

### Germany - PDF page 9

13. "Kann ich mich schon als FBO registrieren, bevor ich die zwei CC erreicht habe?" Use German conditions, not Canada's at-any-time rule.
14. "Kann ich die zwei CC auf zwei aufeinanderfolgende Monate verteilen?" Retain the qualifying time window.
15. "Ist ein Startpaket zwingend vorgeschrieben?" Don't import the UK/Benelux pack alternative or infer a universal prohibition from its absence in these reviewed clauses. Inspect additional German enrollment provisions before final gold scoring.

### Italy - PDF pages 12-14

16. "Sono Promoter. Devo comprare personalmente tutti i prodotti per arrivare a due CC?" Include the Clienti Club route in 4.01(3).
17. "Sono Cliente Privilegiato: dopo i due CC divento automaticamente FBO?" Keep opt-in distinct and use 3.03-3.04.
18. "Promoter e FBO sono la stessa cosa?" Explain the role distinction in 4.01 without dumping all commissions.

### Sweden - reviewed English PDF page 8

19. "Do I need a pack or can I reach two CC with products?" Preserve both documented alternatives.
20. "If I qualify for the discount, do I have to join the business?" Eligibility/choice, not an automatic obligation.
21. "Kan jag välja produkter i stället för ett startpaket?" Swedish-language answer grounded in the supplied English clauses. Score separately as cross-language; do not claim a Swedish source edition.

### United Kingdom - PDF page 6, printed pages 10-11

22. "Can I split my qualifying purchases between this month and next?" Preserve the stated two-consecutive-month route.
23. "I only want cheaper products. Do I have to recruit anyone?" Distinguish Preferred Customer consumer rights from FBO participation; don't import rank/income material.
24. "I got the 30% discount. Does that mean I've already opted in?" Qualification is eligibility, not evidence of an account action.

### Global sponsoring directory - PDF pages 1 and 111-112

25. "I'm in the US. What is the Belgium office reception number in the sponsoring directory?" Global record is accessible; preserve Netherlands reception label and distinguish Belgium order phone. A directory lookup does not establish eligibility to join from the US.
26. "Does the Belgium directory say I have to place an order while registering as a Preferred Customer?" PDF 112 explicitly answers no. This is customer registration, not proof of a no-purchase FBO qualification pathway.
27. "The directory says I can sponsor internationally. Does that override the restrictions for US residents?" Do not use global scope as a bypass for the selected US policy's dated restriction. Cross-source applicability must be evaluated; do not invent conflict resolution based only on rank score.

Follow-up variants: "what about next month?", "I'm only a customer", "I mean the office, not orders", "so it's free?", and typos such as "do i need to buy 2cc frst?" must preserve status, source, market and date context. Re-evaluate when the user changes any of these facts.

## Source identity versus deployed state

The supplied US, UK and sponsoring-directory file SHA256 values match the downloaded-file hashes recorded in `comparison-source-file-hashes.json`. This is byte identity with that earlier captured S3 object, not a fresh verification of active publication, index completeness, registry hash semantics or current deployment. The other six files have not been matched to live AWS sources in this pass.

| File key | SHA256 |
|---|---|
| Belgium | 0af6b6c3eec0206d4beea9a2122b58575fe14d49ea1fedb464b6fbc132409542 |
| Canada | 5d8030aa685d2d6fd6e2edd3706a8bb4cedcbb2a748e10baccc77a3eb4972b9a |
| Germany | 3a81ccf687bc34a7ee971a6fdd389de6b432de8bf968195e5e62dfb3371ef88f |
| Italy | 03471a236aa95c100491563b6429f77f69c944badef07bcb71c2597fd40f69a6 |
| Netherlands | 37795b77c1f91f760ba06bb1a04c92785c37d129ca72419e9a025e9083eeb6a5 |
| Sweden | f50bd72710b75c2b69f8c377cc07ced8317a0ced81f900ee7546c8580896eb7c |
| UK | f46158cce2b19755c17a4e3ed8c7d18233338018d143d9b1f16a91ebc053e98f |
| US | a12c4a65f8211c58825a547eba68618c7dea3c17b919499433440438274c8bde |
| Global | cb39504dc711b42b69f1598aaef5b1a85253a3e2ba71dfc5738b90c7d298bdb0 |

## Next priorities

1. Correct evaluation expectations before more tuning: new US applicant, existing US FBO, Canadian opt-in, Italian Promoter and UK/Benelux customer-to-FBO routes are distinct cases.
2. Map governing restrictions, effective dates, definitions, prerequisites, alternatives and exceptions as a required evidence set. Do not blanket-boost introductions or definitions: the applicable rule depends on the question.
3. Reground the older 40-question customer review in the supplied 2026 editions. The old Belgian draft says a fixed 5% where the newly supplied English 3.02 says 'up to' 5%, demonstrating why this is necessary. Its section/page/threshold labels must not be promoted unchanged.
4. Expand into returns, activity, sponsor changes, payments and local ordering rules independently per edition and language. This remains pending, not completed by the enrollment-focused pass.
5. Verify deployed publication/index identity, then run isolated repeated tests, recording full questions, answers and exact selected evidence. Include unsupported prices, prohibited claims, genuine policy-permission questions, mixed intents and global/local source conflicts.
6. No deployment or claim of overall quality improvement based on this analysis alone. Do not lower confidence to compensate for missing governing restrictions.
