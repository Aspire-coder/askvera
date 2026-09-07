# Isolated selector comparison

Selector decisions and experimental drafts only, not final chatbot answers or a release gate.

Candidate variant: polarity. Captures: 36.

| Version | Decision/evidence checks passed | Attempts | Execution errors |
| --- | ---: | ---: | ---: |
| current | 12 | 18 | 0 |
| candidate | 13 | 18 | 0 |

Recorded token usage: {'inputTokens': 107880, 'outputTokens': 4974, 'totalTokens': 112854, 'cacheReadInputTokens': 0}.

Results are exploratory on reused cases. A passed check does not certify all generated claims.

## CA-04

Does keeping my sales level mean I'm automatically active every month?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

### Repeat 1: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 18, 6, 10],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.62,
  "reason": "Candidate 4 clarifies that Activity Qualification is separate from Sales Level attainment. It shows that keeping a Sales Level does not automatically make an FBO active each month—instead, an FBO must meet specific Active status requirements (4 Active Case Credits) every month to receive bonuses, and bonuses are forfeited if Active status is not achieved. Candidates 18, 6, and 10 reinforce that being Active every month is an ongoing requirement for various Manager statuses and benefits, independent of the Sales Level already attained."
}
```
````

### Repeat 1: candidate

governing activity rule not first

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "Keeping a sales level does not automatically make you active every month; you must separately achieve 4 Active Case Credits each month to be considered active.",
  "support": [
    {
      "rank": 1,
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "rank": 2,
      "quote": "Sales Level: any of various levels achieved by the cumulative Case Credits of the FBO and his/her Downline. These include Assistant Supervisor, Supervisor, Assistant Manager and Manager."
    }
  ],
  "missing_facts": [],
  "selected_ranks": [1, 2],
  "confidence": 0.95
}
```
````

### Repeat 2: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 18, 10],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.65,
  "reason": "Candidate 4 explains that Activity Qualification (being Active each month) is a separate requirement from achieving/maintaining a Sales Level. It shows that keeping a Sales Level does not automatically make one Active—an FBO must meet the 4 Active Case Credits requirement each month to be Active. Candidates 18 and 10 reinforce that maintaining certain levels and bonuses requires being Active every month as an independent requirement, not an automatic consequence of Sales Level status."
}
```
````

### Repeat 2: candidate

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "Keeping a sales level does not automatically make an FBO active every month; instead, an FBO must have 4 Active Case Credits each month to be considered Active.",
  "support": [
    {
      "rank": 4,
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "rank": 1,
      "quote": "Sales Level: any of various levels achieved by the cumulative Case Credits of the FBO and his/her Downline. These include Assistant Supervisor, Supervisor, Assistant Manager and Manager."
    }
  ],
  "missing_facts": [],
  "selected_ranks": [4, 1],
  "confidence": 0.95
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
  "top_rank_confidence": 0.35,
  "reason": "The question asks whether keeping a sales level automatically makes someone active every month. Candidate 4 (Activity Qualification) explains that Activity is a separate, monthly requirement requiring 4 Active Case Credits—not automatic from holding a sales level. Candidates 6, 10, and 18 show that various sales-level-related statuses (Eagle Manager, Recognized Manager, Leadership Bonus eligibility) all require explicitly 'Be Active every month' as a separate obligation, confirming activity is not automatic. No candidate directly states 'keeping your sales level does NOT automatically make you active,' so top_rank_confidence is low despite the question being answerable from these governance rules."
}
```
````

### Repeat 3: candidate

governing activity rule not first

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "Maintaining a Sales Level does not automatically make an FBO Active each month; Active status requires a separate monthly qualification of 4 Active Case Credits in the relevant Operating Company.",
  "support": [
    {
      "rank": 1,
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "rank": 2,
      "quote": "Sales Level: any of various levels achieved by the cumulative Case Credits of the FBO and his/her Downline. These include Assistant Supervisor, Supervisor, Assistant Manager and Manager."
    },
    {
      "rank": 3,
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    }
  ],
  "missing_facts": [],
  "selected_ranks": [1, 2, 3],
  "confidence": 0.95
}
```
````

## CA-04-paraphrase

I already earned my sales rank. Do I still need to qualify as Active again this month?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

### Repeat 1: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 3, 1],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.55,
  "reason": "Candidate 4 (10.01-e) states that during the 36-month Earned Incentive period, a Manager receives maximum payment 'each Month that the Month 3 Case Credit requirement is maintained,' implying ongoing monthly requirements. However, it does not directly answer whether 'Active' status must be re-qualified monthly—it addresses case credit maintenance, not Active status qualification. Candidate 3 (4.03) clarifies that Active status must be achieved each calendar month (4 Active Case Credits required), establishing that yes, Active qualification is required monthly even after earning a sales rank. Candidate 1 addresses re-qualification only after the 36-month period ends, not during it."
}
```
````

### Repeat 1: candidate

wrong answer polarity

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "Once you have earned and qualified for the Earned Incentive Program as an Active Recognized Manager, you do not need to re-qualify as Active each month; instead, you must maintain the Month 3 Case Credit requirement each month during the 36-month payment period to continue receiving payments.",
  "support": [
    {
      "rank": 4,
      "quote": "An Active Recognized Manager is eligible to participate in the Earned Incentive Program."
    },
    {
      "rank": 29,
      "quote": "During the period of 36 Months immediately following qualification, the Manager will receive the maximum payment amount for the level achieved each Month that the Month 3 Case Credit requirement is maintained."
    }
  ],
  "missing_facts": [],
  "selected_ranks": [4, 29],
  "confidence": 0.85
}
```
````

### Repeat 2: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 3, 10, 29],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.65,
  "reason": "Candidate 4 (Section 10.01) states that during the 36-Month Earned Incentive period, a Manager receives maximum payment each month that the 'Month 3 Case Credit requirement is maintained.' This indicates ongoing monthly maintenance requirements exist even after earning the rank, but does not explicitly state whether the user must re-qualify as 'Active' monthly. Candidate 3 (Section 4.03) explains that to qualify for incentives, an FBO 'must be Active and meet all other requirements...during the calendar month in which the bonuses were accrued,' supporting that monthly Active status is required. Candidate 10 and 29 reinforce the maintenance requirement language. The answer is related but not a direct, explicit statement that Active status must be re-qualified every month after earning rank."
}
```
````

### Repeat 2: candidate

wrong answer polarity

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "Once a Manager qualifies for the Earned Incentive Program, Active status must be maintained each month during the 36-month payment period to receive payments, as the Month 3 Case Credit requirement must be maintained each month.",
  "support": [
    {
      "rank": 4,
      "quote": "An Active Recognized Manager is eligible to participate in the Earned Incentive Program."
    },
    {
      "rank": 29,
      "quote": "During the period of 36 Months immediately following qualification, the Manager will receive the maximum payment amount for the level achieved each Month that the Month 3 Case Credit requirement is maintained."
    },
    {
      "rank": 5,
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "selected_ranks": [4, 29, 5],
  "missing_facts": [],
  "confidence": 0.85
}
```
````

### Repeat 3: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 2, 3],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.65,
  "reason": "Candidate 4 (Section 10.01) explains the Earned Incentive Program requires 3 consecutive months of qualification and then maintenance of the Month 3 Case Credit requirement each month during the 36-month period to receive payment. This directly addresses the user's question about whether Active status must be maintained monthly after earning a sales rank (Earned Incentive qualification). Candidates 2 and 3 provide supporting detail on qualification requirements and general Active status rules. However, the top candidate does not explicitly state 'yes, you must re-qualify as Active' in direct language—it requires inference that maintenance of Monthly 3 requirements means ongoing monthly qualification is necessary."
}
```
````

### Repeat 3: candidate

wrong answer polarity

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "Once you have earned your sales rank and qualified for the Earned Incentive Program as an Active Recognized Manager, you must maintain the Month 3 Case Credit requirement each month to continue receiving payments, but you do not need to re-qualify for Active status again that month—Active status is a separate monthly requirement independent of rank retention.",
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
      "rank": 5,
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "missing_facts": [
    "Whether Active status determination each month is automatic upon rank achievement or requires separate monthly qualification actions"
  ],
  "selected_ranks": [4, 5],
  "confidence": 0.6
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
  "reason": "Candidate 1 only defines what Sales Level is (a rank achieved by Case Credits), not whether maintaining it requires or creates automatic monthly activity status. The question asks about the relationship between retention of a sales level and automatic monthly active status—a rule about activity requirements or consequences—which this definition does not address."
}
```
````

### Repeat 1: candidate

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Rule establishing whether maintaining a Sales Level automatically confers monthly active status"
  ],
  "selected_ranks": [],
  "confidence": 0.3
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
  "reason": "The candidate only defines what a Sales Level is (the classification system itself), not the relationship between maintaining a sales level and monthly activity requirements. The question asks whether keeping a sales level automatically makes someone active each month—a rule about activity status, not a definition of the level category. No relevant candidate provided."
}
```
````

### Repeat 2: candidate

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": ["rule establishing automatic monthly active status based on sales level maintenance"],
  "selected_ranks": [],
  "confidence": 0.2
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
  "reason": "The candidate defines 'Sales Level' as a rank achieved through cumulative Case Credits, but does not address whether maintaining a sales level automatically qualifies as monthly activity or active status. The question asks about the relationship between sales level retention and monthly activity requirements, which is not covered by this definitional section."
}
```
````

### Repeat 3: candidate

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Rule establishing whether maintaining a Sales Level automatically results in monthly active status"
  ],
  "selected_ranks": [],
  "confidence": 0.3
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
  "reason": "Candidate 1 addresses voluntary termination by written request, not automatic termination due to inactivity or lack of orders. The question asks about automatic termination triggered by one month without orders, which is a different scenario than what this candidate covers."
}
```
````

### Repeat 1: candidate

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Rule establishing automatic termination of FBO business based on inactivity or failure to order for a specified period"
  ],
  "selected_ranks": [],
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
  "reason": "Candidate 1 addresses voluntary termination by written request, not automatic termination due to inactivity. The user's question asks about automatic termination from one month without orders, which is a different trigger and scenario. No candidate directly answers the question about inactivity-based automatic termination."
}
```
````

### Repeat 2: candidate

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Rule establishing automatic termination of FBO business based on one month without orders"
  ],
  "selected_ranks": [],
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
  "reason": "Candidate 1 addresses voluntary termination by written request, not automatic termination due to inactivity or lack of orders. The user's question asks whether FBO status is automatically terminated for non-ordering, which requires a clause about involuntary termination or inactivity consequences. This candidate does not address that scenario."
}
```
````

### Repeat 3: candidate

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Rule establishing automatic termination of FBO business based on failure to order for one month"
  ],
  "selected_ranks": [],
  "confidence": 0.0
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
  "reason": "No candidates provided contain Canadian customer service contact information. Candidate 1 is about sales level definitions and is not relevant to the user's question about a telephone number."
}
```
````

### Repeat 1: candidate

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Canadian customer service telephone number"
  ],
  "selected_ranks": [],
  "confidence": 0.95
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
  "reason": "No candidates provided address Canadian customer service contact information. The single candidate discusses sales level definitions and is completely unrelated to customer service telephone numbers."
}
```
````

### Repeat 2: candidate

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Canadian customer service telephone number"
  ],
  "selected_ranks": [],
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
  "reason": "No candidates provided contain Canadian customer service contact information. Candidate 1 is about sales level definitions and is not relevant to the question about a telephone number."
}
```
````

### Repeat 3: candidate

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Canadian customer service telephone number"
  ],
  "selected_ranks": [],
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
  "reason": "The candidate defines what a Sales Level is, but does not address retention rules, inactivity consequences, or whether stopping orders affects rank permanence. A definition alone does not answer the retention/loss policy question."
}
```
````

### Repeat 1: candidate

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Rule specifying whether sales rank is retained, lost, or automatically terminated upon cessation of ordering"
  ],
  "selected_ranks": [],
  "confidence": 0.3
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
  "reason": "The candidate defines what a Sales Level is but does not address retention, loss, or the effect of stopping orders on rank status. The question asks about permanence of rank given inactivity; this candidate only defines the term, not the rule governing its retention."
}
```
````

### Repeat 2: candidate

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": ["Rule specifying whether sales rank is retained, lost, or automatically terminated upon cessation of ordering"],
  "selected_ranks": [],
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
  "reason": "Candidate 1 only defines what a Sales Level is; it does not address retention rules, inactivity consequences, or whether stopping orders affects rank retention. The question asks about a specific rule governing rank loss through inactivity, which this definitional section does not contain."
}
```
````

### Repeat 3: candidate

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Rule establishing whether sales rank is retained, lost, or automatically terminated upon cessation of ordering"
  ],
  "selected_ranks": [],
  "confidence": 0.0
}
```
````
