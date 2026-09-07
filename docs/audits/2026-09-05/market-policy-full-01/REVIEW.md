# Market-policy Current run: findings and limits

2026-09-06. Evaluation only; no chatbot fixes, publication changes, index changes or deployment.

Completed: **40/40 captures, zero capture exceptions, zero recorded storage-isolation violations**. Median local-pipeline duration: **9.88 seconds**; maximum: **15.50 seconds**. These are not browser/production latency measurements or a 40/40 correctness result.

## What was refreshed

- A fresh document registry was exported through a temporary loopback Systems Manager tunnel using the approved asm-exec credential wrapper. The SQL transaction was explicitly repeatable-read and read-only with a 15-second statement timeout. Only document metadata was selected. Helper and tunnel were stopped after export.
- OpenSearch metadata was captured for all 28 published registry generations, including the eight requested markets/languages and the International Sponsoring Directory. All 28 reads reported complete results. Other published markets were included to make the identity guard complete; they were not added to the 40-case questionnaire.
- The original US/UK/global-only snapshot was retained. The runner now accepts explicit registry/index snapshot paths and rejects incomplete snapshots. It still rejects any returned hit absent from the frozen identity/content-hash baseline.
- Seven S3 source objects are byte-identical to the supplied PDFs: CA, DE, IT, SE, UK, US and global sponsoring. BE/NL are 47-page English splits of the supplied multilingual documents. Their extracted pages 11,29,43 match supplied pages 116,134,148 respectively after whitespace normalization. This is a targeted content check, not certification of every page.

Artifacts alongside this folder: `market-policy-active-source-metadata.json`, `market-policy-active-index-metadata.json`, `market-policy-source-hashes.json`, `market-policy-benelux-source-text.json`, `market-policy-cases.json`.

## Evaluation meaning

The runner executes a local archive of server-verified deployed commit `7d29dad09540527a9302b95436f36e93f7fa5a2a` against AWS services using freshly read nonsecret SSM settings. It is NOT a request to the deployed HTTP/widget, and therefore is not production latency, browser behavior, consent integration or session persistence verification.

Shared caches are bypassed, not deleted. Storage entry points are blocked or replaced with synthetic in-memory fixtures. Effective settings and overrides are in `current-manifest.json`. All requests start in fresh synthetic sessions, with the default `new_prospect` profile and explicit role wording in questions; this does not test stored role/profile variation. Expected-answer notes never enter model prompts.

One sample per question is a baseline, not a stability or promotion gate. There is no new Candidate in this run, so no improvement percentage can be computed. Successful capture is not a correctness pass. See `capture-summary.json` for completed counts and measured local-pipeline durations, and `ANSWERS.md` for every question, expected behavior, full answer and citations.

Registry, source-object and index reads are sequential, not one atomic snapshot. S3 reads were guarded with ETag/version identity; returned search hits were checked against the index snapshot. This does not prove that every indexed clause faithfully represents its PDF.

## Confirmed problems to prioritize

| Case | Actual behavior | Evidence from this run | Failure attribution |
|---|---|---|---|
| BE-04 | Monthly activity/rank question answered with Earned Incentive Month 3/50CC/36-month payment rules. | Raw search results include 4.03-family hits; generation evidence instead includes 6.04,10.01,10.01-f and definition fragments. | Wrong governing evidence selected; answer drifts to another program. Do not call this complete absence of retrieval. |
| BE-05 | Says no specific minimum order value is available and substitutes the 75% inventory rule. | S3 source page 29 / original page 134 has EUR 50 excluding taxes. Raw search results contain the text under **23.59-f** and **23.59**, while generation evidence omits it. | Parser treats a time as a section identifier; evidence selection also fails to retain the answer-bearing text. |
| NL-05 | Says missing items, defects and returns all share a 30-day-from-purchase deadline. | S3 source ordering clause specifies 14 days from receipt. The correct text occurs in raw hits under **23.59-d**/**23.59**; generation evidence favors 21.03 customer satisfaction. | Mis-sectioned ordering evidence plus wrong procedure selected and an overgeneralized final answer. |
| DE-03 | Explicit FBO asking about six inactive months is told yes under the Preferred Customer rule. | Correct FBO 14.01 is first in recorded generation evidence and explicitly requires the preceding 12 months with no purchases/sponsoring. 4.02 PC rule is also present. | Role/applicability failure in generation despite correct governing evidence being supplied. Retrieval-only changes cannot establish a fix. |
| CA-04 | Refuses rank-versus-monthly-activity question. | Raw search results contain 4.03; response reports `failure_layer=evidence_gate`, and no generation input was recorded. | Evidence approval failure with relevant candidates present; inspect selector inputs and rank-retention clause coverage before changing confidence. |
| SE-04 | Says level discount depends on remaining active, then says its fate is unspecified. | Supplied/S3-identical policy 4.01(l), page 11, explicitly preserves achieved level discount unless sponsor change/termination; 4.03 separately addresses monthly activity/commissions. | Incorrect/incomplete answer. Trace selection of the retention clause before assigning exact upstream cause. |
| DE-04 | Initially says inactivity does not lose rank, but later conditions rank retention on not being inactive for three months. | 4.03 activity and 6.04 Leadership Bonus eligibility differ from sales-level retention. | Conflates rank with Leadership Bonus requalification; final explanation contradicts its opening. |

These are observed defects, not an exhaustive scored list. Do not label every other case a pass by subtraction. In particular, UK termination answers may rely on additional section 17 provisions not included in the initial targeted gold; review those before marking extra timing or refund conditions fabricated.

Additional US review flags: US-03 describes a Preferred Customer-to-FBO conversion within a six-month window as a sponsor-change exception, despite the reviewed deletion/applicability issues. US-04 correctly gives the domestic 2CC number but attributes it to April 1 rather than distinguishing the supplied policy's posted date and May 1 effective date. These require explicit applicability/version checks before a clean-pass label. US-02 abstains on the ambiguous buyback-termination question; this is not automatically a recall failure because the source has an unresolved termination cross-reference.

## Examples of useful behavior

BE-01 correctly gives the 30-day customer return route with shipping excluded and proof/notice/return conditions. CA-02 correctly avoids inventing a fixed 10% deduction. CA-05 uses order-placement rather than delivery as its deadline anchor. DE-05 excludes promotional material from the minimum-order product value. IT-01 distinguishes delivery-based withdrawal and return within 14 days of notice. IT-04 recognizes Clienti Club purchases as a source of Personal CC. These observations do not certify every sentence or the complete safety suite.

## Recommended next steps, not implemented here

1. Freeze the concrete time-as-section parsing failure with real page snippets and sibling-clause coverage tests. Preserve 13.01 ownership across 23.59 text. Reindex only an isolated candidate generation after verification.
2. Test evidence selection on rank versus activity, ordering discrepancy versus dissatisfaction, and minimum order versus inventory rules. Keep answer-bearing requirements and their qualifiers together.
3. Test role-aware generation with both FBO and PC evidence present. Explicit user role must not be replaced with an inferred role from inactivity duration. Include multilingual variants.
4. Diagnose CA-04 at selector/approval stages without lowering the global safety threshold.
5. Complete case-by-case scoring against all applicable source clauses; repeat the failure cases and retain the full safety, local/global isolation and conversation tests before promotion.

No clean-pass percentage or release-ready claim is made from this first capture run.
