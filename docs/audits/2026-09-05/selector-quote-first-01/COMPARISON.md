# Isolated selector comparison

Selector decisions and experimental drafts only, not final chatbot answers or a release gate.

Candidate variant: quote-first. Captures: 36.

| Version | Decision/evidence checks passed | Attempts | Execution errors |
| --- | ---: | ---: | ---: |
| current | 12 | 18 | 0 |
| candidate | 12 | 18 | 0 |

Recorded token usage: {'inputTokens': 108366, 'outputTokens': 5713, 'totalTokens': 114079, 'cacheReadInputTokens': 0}.

Results are exploratory on reused cases. A passed check does not certify all generated claims.

## CA-04

Does keeping my sales level mean I'm automatically active every month?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

### Repeat 1: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 26, 6, 18, 19],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.65,
  "reason": "Candidate 4 addresses Activity Qualification and explains that maintaining a Sales Level does NOT automatically make an FBO active each month—being Active requires meeting specific monthly requirements (4 Active Case Credits). The candidate clarifies that FBOs who do not achieve Active status lose bonuses, answering that Sales Level and Activity status are separate requirements. Candidates 26, 6, 18, and 19 provide supporting evidence that Activity must be earned/maintained monthly independent of Sales Level."
}
```
````

### Repeat 1: candidate

wrong support decision

````text
```json
{
  "support": [
    {
      "rank": 1,
      "quote": "Sales Level: any of various levels achieved by the cumulative Case Credits of the FBO and his/her Downline."
    },
    {
      "rank": 4,
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "missing_facts": [
    "The policy defines what a Sales Level is and what it takes to be Active each month, but contains no rule stating that maintaining a Sales Level automatically makes an FBO Active every month. Active status requires generating 4 Active Case Credits each month (Section 4.03(b)), which is a separate ongoing requirement not derived from Sales Level alone."
  ],
  "selected_ranks": [1, 4],
  "answer_supported": false,
  "confidence": 0.15
}
```
````

### Repeat 2: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 6, 2, 18, 10],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.65,
  "reason": "Candidate 4 explains that maintaining a sales level does NOT automatically make you active every month. It details that FBOs must meet separate Activity Qualification requirements (4 Active Case Credits) each month to be considered 'Active,' and that bonuses are forfeited if Active status is not achieved that month—even if the sales level is retained. The question conflates two separate concepts: sales level retention and monthly active status, which are independent requirements."
}
```
````

### Repeat 2: candidate

wrong support decision

````text
```json
{
  "support": [
    {
      "rank": 1,
      "quote": "Sales Level: any of various levels achieved by the cumulative Case Credits of the FBO and his/her Downline."
    },
    {
      "rank": 4,
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "missing_facts": [
    "The policy defines what a Sales Level is (a rank achieved by cumulative Case Credits) and what it means to be Active each month (4 Active Case Credits required). However, the policy does not contain an explicit rule stating whether maintaining a Sales Level automatically makes an FBO active every month. Candidate 4 shows that being Active requires meeting specific Case Credit requirements each month independent of Sales Level status. The documents show Sales Level and Active status are separate qualifying conditions, but contain no rule establishing that holding one automatically grants the other."
  ],
  "selected_ranks": [
    1,
    4
  ],
  "answer_supported": false,
  "confidence": 0.35
}
```
````

### Repeat 3: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 6, 10, 18],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.65,
  "reason": "Candidate 4 establishes that Activity Qualification (being Active each month) is a separate requirement from achieving/maintaining a Sales Level. It shows that keeping a sales level does NOT automatically make you active—an FBO must separately achieve Active status (4 Case Credits) each month to qualify for bonuses. The policy distinguishes between Sales Level (cumulative achievement) and monthly Activity status (separate monthly requirement). Candidates 6, 10, and 18 reinforce that specific levels (Eagle Manager, Recognized Manager, etc.) require being Active every month as an explicit ongoing requirement, not automatically derived from the sales level itself."
}
```
````

### Repeat 3: candidate

wrong support decision

````text
```json
{
  "support": [
    {
      "rank": 1,
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "rank": 2,
      "quote": "Sales Level: any of various levels achieved by the cumulative Case Credits of the FBO and his/her Downline."
    }
  ],
  "missing_facts": [
    "The document defines what constitutes 'Active' status (4 Active Case Credits per month) and defines 'Sales Level' (cumulative Case Credits), but does not contain an explicit rule stating that maintaining a Sales Level automatically makes an FBO active every month. The policy requires Active status to be earned each month independently through Case Credit generation, not automatically retained through Sales Level maintenance alone."
  ],
  "selected_ranks": [
    26,
    1
  ],
  "answer_supported": false,
  "confidence": 0.2
}
```
````

## CA-04-paraphrase

I already earned my sales rank. Do I still need to qualify as Active again this month?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

### Repeat 1: current

governing activity rule not first

````text
```json
{
  "selected_ranks": [
    4,
    3,
    11
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.88,
  "reason": "Candidate 4 (Section 10.01-e) directly states that during the 36-month Earned Incentive period, a Manager receives payment each month that the Month 3 Case Credit requirement is maintained, establishing that ongoing monthly qualification is required even after earning the rank. Candidate 3 (Section 4.03) provides the general Active requirement of 4 Case Credits monthly. Candidate 11 details the maintenance requirements table showing Month 3 thresholds must be met each month during the 36-month period."
}
```
````

### Repeat 1: candidate

wrong support decision

````text
```json
{
  "support": [
    {
      "rank": 4,
      "quote": "An Active Recognized Manager is eligible to participate in the Earned Incentive Program."
    },
    {
      "rank": 4,
      "quote": "During the period of 36 Months immediately following qualification, the Manager will receive the maximum payment amount for the level achieved each Month that the Month 3 Case Credit requirement is maintained."
    },
    {
      "rank": 3,
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    }
  ],
  "missing_facts": [
    "The policy establishes that eligibility for the Earned Incentive Program requires being an 'Active Recognized Manager' and that during the 36-month period, monthly payments depend on maintaining the Month 3 Case Credit requirement. However, the policy does not explicitly state whether achieving the sales rank (Earned Incentive qualification) itself eliminates or reduces the requirement to qualify as Active each subsequent month, or whether Active status must be re-established monthly independent of rank retention. Section 4.03 requires Active status monthly for bonuses generally, but does not clarify whether this overrides the 36-month Earned Incentive structure."
  ],
  "selected_ranks": [
    4,
    3
  ],
  "answer_supported": false,
  "confidence": 0.55
}
```
````

### Repeat 2: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 3, 11],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.65,
  "reason": "Candidate 4 (Section 10.01) states that during the 36-month Earned Incentive period, the Manager receives maximum payment 'each Month that the Month 3 Case Credit requirement is maintained' (section e), and if credits drop below the Month 3 requirement, payment is recalculated (section f). This indicates ongoing monthly maintenance requirements exist, but does not explicitly state whether 'Active' status must be re-qualified each month. Candidate 3 (Section 4.03) establishes the general rule that to qualify for incentives, 'an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued' (4.03a). Candidate 11 shows the maintenance table. Together these suggest Active status is required each month for Earned Incentive receipt, but no candidate directly states whether a previously-earned sales rank itself requires monthly re-qualification versus just monthly maintenance of Active status for payment eligibility."
}
```
````

### Repeat 2: candidate

wrong support decision

````text
```json
{
  "support": [
    {
      "rank": 4,
      "quote": "An Active Recognized Manager is eligible to participate in the Earned Incentive Program."
    },
    {
      "rank": 4,
      "quote": "During the period of 36 Months immediately following qualification, the Manager will receive the maximum payment amount for the level achieved each Month that the Month 3 Case Credit requirement is maintained."
    },
    {
      "rank": 3,
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    }
  ],
  "missing_facts": [
    "The policy does not explicitly state whether Active status qualification is required each month during the 36-Month Earned Incentive payment period, or only the Month 3 Case Credit requirement. Section 10.01(e) requires maintenance of 'the Month 3 Case Credit requirement' each month to receive payments, but does not explicitly state whether Active status must also be maintained each month during the 36-month period."
  ],
  "selected_ranks": [
    4,
    3
  ],
  "answer_supported": false,
  "confidence": 0.55
}
```
````

### Repeat 3: current

governing activity rule not first

````text
```json
{
  "selected_ranks": [4, 3, 1],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "reason": "Candidate 4 (Section 10.01-e) directly states that during the 36-month Earned Incentive period, a Manager receives payment 'each Month that the Month 3 Case Credit requirement is maintained.' This establishes that yes, ongoing monthly qualification/maintenance is required even after earning the rank. Candidate 3 (Section 4.03-a) reinforces that Active status must be achieved each calendar month to qualify for bonuses and incentives. Candidate 1 addresses re-qualification after the 36-month period ends, providing context on longer-term maintenance cycles."
}
```
````

### Repeat 3: candidate

wrong support decision

````text
```json
{
  "support": [
    {
      "rank": 4,
      "quote": "An Active Recognized Manager is eligible to participate in the Earned Incentive Program."
    },
    {
      "rank": 4,
      "quote": "During the period of 36 Months immediately following qualification, the Manager will receive the maximum payment amount for the level achieved each Month that the Month 3 Case Credit requirement is maintained."
    },
    {
      "rank": 4,
      "quote": "If the Manager's Total Case Credits drop below the Month 3 requirement during any Month, that Month's Earned Incentive payment will be calculated at $2.66 times the Manager's Total Case Credits for that Month."
    },
    {
      "rank": 3,
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    }
  ],
  "missing_facts": [
    "The policy establishes that Active status is required each month to receive Earned Incentive payments at the full amount (Section 10.01(e)), and that Case Credit maintenance requirements apply monthly (Section 10.01(f)). However, the question asks whether earning a sales rank makes Active qualification automatic or unnecessary going forward. The documents do not explicitly state whether achievement of an Earned Incentive rank permanently exempts a person from monthly Active qualification requirements, or whether Active status must be re-qualified each month despite having earned the rank. Section 10.01(a) states only that 'An Active Recognized Manager is eligible to participate' but does not clarify whether being a rank-holder automatically confers or maintains Active status monthly."
  ],
  "selected_ranks": [
    4,
    3
  ],
  "answer_supported": false,
  "confidence": 0.55
}
```
````

## missing-activity-rule

Does keeping my sales level mean I'm automatically active every month?

Expected support: False. Governing sections: [].

### Repeat 1: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "The candidate defines 'Sales Level' but does not address the user's question about whether maintaining a sales level automatically establishes monthly activity status. The question asks about the relationship between sales level retention and automatic activity status; the candidate only provides a definitional explanation of what sales levels are. No direct answer to the activity question is present."
}
```
````

### Repeat 1: candidate

correctly withheld unsupported answer

````text
```json
{
  "support": [],
  "missing_facts": [
    "No rule provided establishing that maintaining a sales level automatically confers or maintains active status in any month. The definition of 'Sales Level' only describes it as levels achieved by cumulative Case Credits, without connecting it to automatic monthly active status or any condition for active status."
  ],
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.1
}
```
````

### Repeat 2: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 only defines what a Sales Level is; it does not address whether keeping a sales level means automatic monthly activity status. The question asks about the relationship between maintaining a sales rank and active status, which requires a rule about retention or activity requirements, not a definition."
}
```
````

### Repeat 2: candidate

correctly withheld unsupported answer

````text
```json
{
  "support": [],
  "missing_facts": [
    "The document defines 'Sales Level' as a rank achieved through cumulative Case Credits, but contains no rule establishing whether maintaining a sales level automatically confers monthly active status. A definition of what a sales level is does not answer whether holding that level automatically produces a recurring monthly status. The document would need to explicitly state a condition such as 'maintaining sales level X automatically qualifies as active each month' or 'active status is automatic upon reaching sales level X,' which is absent."
  ],
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.1
}
```
````

### Repeat 3: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 defines what a Sales Level is but does not address the user's question about whether maintaining a sales level automatically establishes monthly activity status. The question asks about the relationship between sales level retention and active status; the candidate only provides a definitional statement about what sales levels are based on Case Credits. No evidence directly answers this question."
}
```
````

### Repeat 3: candidate

correctly withheld unsupported answer

````text
```json
{
  "support": [],
  "missing_facts": [
    "No rule provided defining the relationship between maintaining a sales level and automatic monthly active status. The candidate defines what 'Sales Level' means (achievement levels based on cumulative Case Credits) but does not address whether holding a sales level automatically confers monthly active status or what conditions determine active status."
  ],
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.1
}
```
````

## wrong-termination-trigger

If I do not order anything for one month, is my FBO business automatically terminated?

Expected support: False. Governing sections: [].

### Repeat 1: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 describes voluntary termination by written request, not automatic termination due to inactivity or lack of orders. It does not address the specific scenario of non-ordering for one month or automatic status loss."
}
```
````

### Repeat 1: candidate

correctly withheld unsupported answer

````text
```json
{
  "support": [],
  "missing_facts": [
    "The supplied document defines voluntary termination by written request (Section 17.08-a) but contains no rule establishing automatic termination based on inactivity (no orders for one month). A definition of voluntary termination does not establish the conditions or triggers for involuntary or automatic termination."
  ],
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.15
}
```
````

### Repeat 2: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 addresses voluntary termination by written request, not automatic termination due to inactivity or failure to order. The question asks about automatic termination from one month of no orders, which is a different scenario. No candidate provided addresses the specific inactivity/ordering rule asked about."
}
```
````

### Repeat 2: candidate

correctly withheld unsupported answer

````text
```json
{
  "support": [],
  "missing_facts": [
    "The document does not contain any rule establishing automatic termination of an FBO business based on failure to order for one month or any specified period of inactivity. Candidate 1 addresses only voluntary termination by written request, which is a different mechanism. No automatic termination condition tied to ordering frequency or inactivity duration is present in the supplied evidence."
  ],
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.1
}
```
````

### Repeat 3: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 addresses voluntary termination by written request, not automatic termination due to inactivity or lack of orders. The question asks about automatic termination from non-ordering for one month, which requires a policy section on inactivity-based termination rules. This candidate does not address that scenario."
}
```
````

### Repeat 3: candidate

correctly withheld unsupported answer

````text
```json
{
  "support": [],
  "missing_facts": [
    "The provided candidate section addresses only VOLUNTARY termination (requiring written request by the FBO). The question asks whether automatic termination occurs upon inaction (no orders for one month). No rule governing automatic termination based on inactivity period is present in the supplied evidence."
  ],
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.15
}
```
````

## missing-phone

What is the Canadian customer service telephone number?

Expected support: False. Governing sections: [].

### Repeat 1: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "The candidate section discusses Sales Level definitions and is completely unrelated to customer service contact information for Canada. No office directory, contact information, or customer service details are present in the provided candidate."
}
```
````

### Repeat 1: candidate

correctly withheld unsupported answer

````text
```json
{
  "support": [],
  "missing_facts": ["The source material does not contain a Canadian customer service telephone number. The provided candidate section defines 'Sales Level' in a business compensation or organizational context and is unrelated to customer service contact information."],
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.0
}
```
````

### Repeat 2: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 is a policy definition section about sales levels and has no contact information. It does not address the user's question about Canadian customer service telephone number. No candidates provided contain office directory or contact information for Canada."
}
```
````

### Repeat 2: candidate

correctly withheld unsupported answer

````text
```json
{
  "support": [],
  "missing_facts": [
    "The source document does not contain any customer service telephone numbers. The candidate section provided defines 'Sales Level' in a policy document and is unrelated to customer service contact information. No telephone number for Canadian customer service is present in the supplied evidence."
  ],
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.0
}
```
````

### Repeat 3: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 defines 'Sales Level' and is unrelated to Canadian customer service contact information. No candidates provided contain customer service telephone numbers or office directory information for Canada."
}
```
````

### Repeat 3: candidate

correctly withheld unsupported answer

````text
```json
{
  "support": [],
  "missing_facts": ["The document does not contain a Canadian customer service telephone number. The provided candidate section defines 'Sales Level' in a compensation or organizational context and is unrelated to customer service contact information."],
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.0
}
```
````

## missing-retention-rule

Do I permanently keep my sales rank if I stop ordering?

Expected support: False. Governing sections: [].

### Repeat 1: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "The candidate defines what a Sales Level is, but does not address whether sales ranks are retained or lost when ordering stops. The question asks about retention rules upon inactivity, not the definition of rank categories."
}
```
````

### Repeat 1: candidate

correctly withheld unsupported answer

````text
```json
{
  "support": [],
  "missing_facts": [
    "The document defines what Sales Level is (achievement based on cumulative Case Credits) but does not contain any rule addressing whether Sales Levels are retained, lost, or made permanent upon cessation of ordering. No retention condition, permanence clause, or consequence of stopping orders is stated."
  ],
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.15
}
```
````

### Repeat 2: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 defines what a Sales Level is but does not address retention, loss, or the effect of stopping orders on rank status. The question asks about permanent retention when ordering stops; the candidate only provides a definitional explanation without any retention or inactivity rules."
}
```
````

### Repeat 2: candidate

correctly withheld unsupported answer

````text
```json
{
  "support": [],
  "missing_facts": [
    "The document defines what Sales Level is (achieved through cumulative Case Credits) but does not state whether Sales Levels are permanently retained or lost upon cessation of ordering. No rule is provided governing rank retention or loss based on order activity."
  ],
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.0
}
```
````

### Repeat 3: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 only defines what a Sales Level is; it does not address whether sales rank is retained when ordering stops. The question asks about retention rules upon inactivity, which requires a clause about retention/loss conditions, not a definition."
}
```
````

### Repeat 3: candidate

correctly withheld unsupported answer

````text
```json
{
  "support": [],
  "missing_facts": [
    "The document defines what Sales Level is (achievement based on cumulative Case Credits) but does not specify whether sales rank is permanently retained upon cessation of ordering, or whether ongoing ordering is required to maintain rank status."
  ],
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.1
}
```
````
