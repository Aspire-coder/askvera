# Isolated selector comparison

Selector decisions and experimental drafts only, not final chatbot answers or a release gate.

Candidate variant: set-support. Captures: 36.

| Version | Decision/evidence checks passed | Attempts | Execution errors |
| --- | ---: | ---: | ---: |
| current | 12 | 18 | 0 |
| candidate | 6 | 18 | 0 |

Recorded token usage: {'inputTokens': 113568, 'outputTokens': 6063, 'totalTokens': 119631, 'cacheReadInputTokens': 0}.

Results are exploratory on reused cases. A passed check does not certify all generated claims.

## CA-04

Does keeping my sales level mean I'm automatically active every month?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

### Repeat 1: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 2, 6],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.65,
  "reason": "Candidate 4 explains that Active status is a separate monthly requirement (defined by 4 Active Case Credits) that must be achieved each month to qualify for bonuses and incentives - it is NOT automatic from holding a Sales Level. Candidates 2 and 6 reinforce that being Active every month is an independent requirement that must be fulfilled. The question asks whether keeping a sales level automatically makes one active monthly; the answer is no—sales level and monthly active status are distinct requirements."
}
```
````

### Repeat 1: candidate

wrong support decision

````text
```json
{
  "selected_ranks": [2, 4, 6, 18, 19],
  "answer_supported": false,
  "confidence": 0.3,
  "support": [
    {
      "rank": 2,
      "quote": "Be Active every month."
    },
    {
      "rank": 4,
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "rank": 18,
      "quote": "A Manager who is not Active in any Operating Company for three consecutive Months loses eligibility to qualify for Leadership Bonus, even if he/she has no downline Managers."
    },
    {
      "rank": 19,
      "quote": "Leadership Bonus eligibility can be regained by meeting the following requirements in any single Operating Company: 1) Generate a total of 12 Open Group Case Credits each Month for three consecutive Months (even if he/she does not have any downline Managers). 2) Be Active each Month for the same period."
    }
  ],
  "missing_facts": [
    "Whether maintaining a Sales Level automatically carries forward Active status each month",
    "Whether Sales Level retention requires monthly Active qualification or if it is a separate retained status independent of monthly activity"
  ]
}
```
````

### Repeat 2: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 2, 6, 18],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.65,
  "reason": "Candidate 4 explains that Activity Qualification requires being 'Active' each month to receive bonuses, and defines what 'Active' means (4 Active Case Credits). However, it does not directly state whether holding a Sales Level automatically satisfies the monthly Active requirement. Candidates 2, 6, and 18 clarify that 'Be Active every month' is a separate, ongoing requirement—not automatic—that must be fulfilled independently to maintain various statuses and benefits. The policy treats Sales Level and monthly Activity status as distinct requirements."
}
```
````

### Repeat 2: candidate

wrong support decision

````text
```json
{
  "selected_ranks": [4, 2, 18, 19, 6],
  "answer_supported": false,
  "confidence": 0.3,
  "support": [
    {
      "rank": 4,
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "rank": 2,
      "quote": "Be Active every month."
    },
    {
      "rank": 18,
      "quote": "A Manager who is not Active in any Operating Company for three consecutive Months loses eligibility to qualify for Leadership Bonus"
    },
    {
      "rank": 19,
      "quote": "Leadership Bonus eligibility can be regained by meeting the following requirements in any single Operating Company: 1) Generate a total of 12 Open Group Case Credits each Month for three consecutive Months (even if he/she does not have any downline Managers). 2) Be Active each Month for the same period."
    },
    {
      "rank": 6,
      "quote": "Eagle Manager Status: 1) Be Active every month, either in the Home OC or in the Qualifying OC."
    }
  ],
  "missing_facts": [
    "Whether achieving/maintaining a Sales Level automatically qualifies an FBO as Active each month, or whether Active status is a separate monthly requirement independent of Sales Level"
  ]
}
```
````

### Repeat 3: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 2, 10, 18],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.6,
  "reason": "Candidate 4 establishes that Activity Qualification (being 'Active') is a separate monthly requirement from holding a Sales Level; it requires 4 Active Case Credits monthly and is necessary to receive bonuses. However, it does NOT explicitly state whether keeping a Sales Level automatically satisfies the Activity requirement. Candidates 2, 10, and 18 confirm that 'Be Active every month' is a distinct requirement even for Managers with Sales Levels, implying Sales Level retention does not automatically make one Active. The policy treats these as separate obligations."
}
```
````

### Repeat 3: candidate

wrong support decision

````text
```json
{
  "selected_ranks": [4, 6, 18, 19],
  "answer_supported": false,
  "confidence": 0.35,
  "support": [
    {
      "rank": 4,
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "rank": 6,
      "quote": "Eagle Manager Status: 1) Be Active every month, either in the Home OC or in the Qualifying OC."
    },
    {
      "rank": 18,
      "quote": "A Manager who is not Active in any Operating Company for three consecutive Months loses eligibility to qualify for Leadership Bonus, even if he/she has no downline Managers."
    },
    {
      "rank": 19,
      "quote": "Leadership Bonus eligibility can be regained by meeting the following requirements in any single Operating Company: 2) Be Active each Month for the same period."
    }
  ],
  "missing_facts": [
    "Whether maintaining a sales level automatically qualifies an FBO as active each month, or whether active status must be independently achieved through meeting case credit requirements",
    "Whether sales level retention depends on maintaining active status or whether they are separate requirements"
  ]
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
  "selected_ranks": [4, 3, 2, 11],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.55,
  "reason": "Candidate 4 (10.01) states that an Active Recognized Manager receives Earned Incentive payments each month that the Month 3 Case Credit requirement is maintained, but does not explicitly address whether Active status must be re-qualified every month. Candidate 3 (4.03) clarifies the monthly Active qualification requirement (4 Active Case Credits), and Candidate 11 shows that dropping below Month 3 requirements affects payment. The question asks about monthly re-qualification of Active status after earning a rank, which requires understanding both the Earned Incentive maintenance rules and the general monthly Active requirement. No single candidate directly states 'you must/must not re-qualify as Active each month after earning your rank.'"
}
```
````

### Repeat 1: candidate

governing activity rule not first

````text
```json
{
  "selected_ranks": [
    4,
    3,
    11
  ],
  "answer_supported": true,
  "confidence": 0.92,
  "support": [
    {
      "rank": 4,
      "quote": "An Active Recognized Manager is eligible to participate in the Earned Incentive Program... During the period of 36 Months immediately following qualification, the Manager will receive the maximum payment amount for the level achieved each Month that the Month 3 Case Credit requirement is maintained."
    },
    {
      "rank": 3,
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "rank": 11,
      "quote": "During the period of 36 Months immediately following qualification, the Manager will receive the maximum payment amount for the level achieved each Month that the Month 3 Case Credit requirement is maintained."
    }
  ],
  "missing_facts": []
}
```
````

### Repeat 2: current

governing activity rule not first

````text
```json
{
  "selected_ranks": [4, 3, 10, 2],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "reason": "Candidate 4 (Section 10.01) directly states that during the 36-month Earned Incentive period, a Manager receives payment each month that 'the Month 3 Case Credit requirement is maintained' (subsection e), and if credits drop below Month 3 requirement, payment is reduced but incentive continues (subsection f). This answers that after earning the rank, ongoing monthly maintenance of the Month 3 case credit threshold is required—not full re-qualification from scratch, but continued active qualification each month. Candidate 3 provides the general Active status requirement (4 case credits monthly), and Candidate 10 defines case credits, supporting context."
}
```
````

### Repeat 2: candidate

governing activity rule not first

````text
```json
{
  "selected_ranks": [4, 3, 11, 12],
  "answer_supported": true,
  "confidence": 0.92,
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
      "rank": 11,
      "quote": "If the Manager's Total Case Credits drop below the Month 3 requirement during any Month, that Month's Earned Incentive payment will be calculated at $2.66 times the Manager's Total Case Credits for that Month."
    },
    {
      "rank": 3,
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    }
  ],
  "missing_facts": []
}
```
````

### Repeat 3: current

wrong support decision

````text
```json
{
  "selected_ranks": [
    4,
    3,
    11,
    10
  ],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.62,
  "reason": "Candidate 4 (Section 10.01-e) states that during the 36-month Earned Incentive period, payment is received 'each Month that the Month 3 Case Credit requirement is maintained,' which addresses ongoing maintenance requirements. However, it does not explicitly state whether Active status must be re-qualified each month separately. Candidate 3 (Section 4.03-a) clarifies that Active status must be achieved monthly to receive bonuses, but the Earned Incentive program (Section 10.01) appears to operate under different maintenance rules focused on Case Credit thresholds rather than explicit monthly Active requalification. The question asks about requalification after earning a rank, which conflates general Active status (required monthly for most bonuses) with the specific Earned Incentive maintenance requirement (Month 3 Case Credits). Section 10.01-e is most directly relevant but does not fully and explicitly answer whether separate Active qualification is required each month for Earned Incentive continuation."
}
```
````

### Repeat 3: candidate

governing activity rule not first

````text
```json
{
  "selected_ranks": [4, 3, 11],
  "answer_supported": true,
  "confidence": 0.85,
  "support": [
    {
      "rank": 4,
      "quote": "An Active Recognized Manager is eligible to participate in the Earned Incentive Program."
    },
    {
      "rank": 11,
      "quote": "During the period of 36 Months immediately following qualification, the Manager will receive the maximum payment amount for the level achieved each Month that the Month 3 Case Credit requirement is maintained."
    },
    {
      "rank": 3,
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    }
  ],
  "missing_facts": []
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
  "reason": "The candidate defines what a Sales Level is (a rank achieved through cumulative Case Credits) but does not address whether maintaining that level automatically establishes monthly activity status. The question asks about the relationship between sales level retention and automatic monthly activity—a separate compliance or status concept not covered by this definitional section."
}
```
````

### Repeat 1: candidate

unparseable model output

````text
```json
{
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.05,
  "support": [],
  "missing_facts": [
    "Rule defining whether maintaining a sales level automatically maintains active status each month",
    "Definition of 'active' status and its relationship to sales level retention",
    "Monthly activity requirements or their absence for sales level holders",
    "Automatic vs. conditional status rules for FBOs at various sales levels"
  ]
}
```

The candidate section provided only defines what a Sales Level is (a rank achieved through cumulative Case Credits), not whether holding that level automatically maintains active status monthly. The question requires a governing rule about active status retention or loss conditions, which is absent from the provided candidate.
````

### Repeat 2: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "The candidate defines what a Sales Level is (a rank achieved through cumulative Case Credits) but does not address whether maintaining that level automatically satisfies monthly activity requirements or establishes ongoing active status. The question asks about the relationship between sales level retention and automatic monthly activity—a rules question about status maintenance—while the candidate only provides a definitional statement about how levels are determined."
}
```
````

### Repeat 2: candidate

unparseable model output

````text
```json
{
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.95,
  "support": [],
  "missing_facts": [
    "Rule defining whether maintaining a sales level automatically requires monthly activity",
    "Rule distinguishing between sales level retention and monthly active status requirements",
    "Conditions or triggers that establish or maintain 'active' status independent of sales level"
  ]
}
```

The candidate section defines what a Sales Level is but does not address the relationship between maintaining a sales level and automatic monthly activity status. The question asks whether one status (keeping sales level) automatically guarantees another status (being active monthly). The provided definition does not contain a governing rule about this relationship, so the evidence cannot support a conclusion either way.
````

### Repeat 3: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "The candidate defines what a Sales Level is but does not address whether maintaining a sales level automatically confers monthly active status. The question asks about the relationship between sales level retention and automatic monthly activity—a distinct policy rule that is not answered by a definitional section."
}
```
````

### Repeat 3: candidate

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.1,
  "support": [],
  "missing_facts": [
    "Rule governing automatic monthly activity status based on sales level retention",
    "Definition of 'active' status and its relationship to sales level maintenance",
    "Whether sales level retention requires ongoing monthly activity or is independent",
    "Conditions that trigger loss of active status despite maintaining sales level"
  ]
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
  "reason": "Candidate 1 addresses voluntary termination by written request, not automatic termination due to inactivity or lack of orders. The user question asks about automatic termination for non-ordering, which is a different trigger than the voluntary action described in this section. No candidate provided directly answers the specific question about whether one month of no orders triggers automatic FBO termination."
}
```
````

### Repeat 1: candidate

unparseable model output

````text
```json
{
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.95,
  "support": [],
  "missing_facts": [
    "Policy section explicitly addressing automatic termination due to inactivity or lack of orders for one month",
    "Rule distinguishing between voluntary termination and automatic termination based on order activity"
  ]
}
```

**Explanation:** The provided candidate section (17.08-a) addresses only *voluntary* termination—an action initiated by the FBO through a written request. It does not establish an automatic termination rule triggered by one month of no orders. To answer whether inactivity automatically terminates FBO status, a section governing automatic termination conditions (such as inactivity thresholds or minimum order requirements) would be required. The absence of such a governing rule in the provided candidates means the answer cannot be supported.
````

### Repeat 2: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 addresses voluntary termination by written request, not automatic termination due to inactivity/non-ordering. The question asks about automatic termination from one month of no orders, which is a different scenario. No candidate provided directly answers the specific question about automatic FBO termination for inactivity."
}
```
````

### Repeat 2: candidate

unparseable model output

````text
```json
{
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.05,
  "support": [],
  "missing_facts": [
    "Rule governing automatic FBO termination for inactivity or non-ordering",
    "Definition of what constitutes automatic (non-voluntary) termination triggers",
    "Specific inactivity period or order requirement that triggers automatic termination"
  ]
}
```

The candidate section addresses only *voluntary* termination (requiring a written request), not automatic termination. To answer whether non-ordering for one month automatically terminates FBO status requires a different governing rule that specifies automatic termination conditions or inactivity thresholds. The provided candidate does not contain that rule.
````

### Repeat 3: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 addresses voluntary termination by written request, not automatic termination due to inactivity or lack of orders. The question asks about automatic termination triggered by one month without orders, which is a different scenario. No candidate provided directly answers the specific question about automatic termination for inactivity."
}
```
````

### Repeat 3: candidate

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.1,
  "support": [],
  "missing_facts": [
    "Policy rule governing automatic FBO termination due to inactivity or lack of orders for one month",
    "Distinction between voluntary termination and automatic termination triggers",
    "Specific inactivity requirements or order frequency requirements for FBO status retention"
  ]
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
  "reason": "No candidates provided contain Canadian customer service contact information. Candidate 1 is a policy definition unrelated to customer service telephone numbers."
}
```
````

### Repeat 1: candidate

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.0,
  "support": [],
  "missing_facts": [
    "Canadian customer service telephone number",
    "Office directory or contact information for Canada"
  ]
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
  "reason": "Candidate 1 defines 'Sales Level' and is unrelated to customer service contact information. No candidates provided contain Canadian customer service telephone numbers or office directory information."
}
```
````

### Repeat 2: candidate

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.0,
  "support": [],
  "missing_facts": [
    "Canadian customer service telephone number",
    "office_directory record for Canada with contact information"
  ]
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
  "reason": "No candidate provided contains customer service contact information. Candidate 1 is a policy definition of Sales Level, which is unrelated to Canadian customer service telephone numbers. An office_directory record with Record country Canada would be needed to answer this question."
}
```
````

### Repeat 3: candidate

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.0,
  "support": [],
  "missing_facts": [
    "Canadian customer service telephone number",
    "Office directory or contact information for Canada"
  ]
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
  "reason": "Candidate 1 only defines what a Sales Level is, not the retention or loss rule for inactive ordering. The question asks about permanence of rank when stopping orders, which requires a retention/loss policy clause, not a definitional section."
}
```
````

### Repeat 1: candidate

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.1,
  "support": [],
  "missing_facts": [
    "Rule governing retention or loss of sales rank upon cessation of ordering",
    "Whether sales rank is maintained automatically or requires continued activity",
    "Conditions that trigger rank demotion or loss",
    "Definition of 'stopping ordering' and its effect on rank status"
  ]
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
  "reason": "Candidate 1 only defines what a Sales Level is; it does not address retention rules, inactivity consequences, or whether sales ranks are permanently kept when ordering stops. The question asks about a retention/loss rule, not a definition."
}
```
````

### Repeat 2: candidate

unparseable model output

````text
```json
{
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.1,
  "support": [],
  "missing_facts": [
    "Explicit rule regarding retention or loss of sales rank upon cessation of ordering",
    "Definition of conditions that trigger rank loss (inactivity period, minimum ordering requirements, etc.)",
    "Whether rank retention is automatic, conditional, or subject to ongoing activity requirements"
  ]
}
```

The candidate section provided only defines what a Sales Level is (a rank achieved through cumulative Case Credits), but does not address the governance rule for whether a rank is permanently retained if ordering stops. To answer this question, evidence is needed that explicitly addresses rank retention/loss conditions, activity requirements, or inactivity consequences.
````

### Repeat 3: current

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "The candidate section defines what Sales Level is but does not address whether sales rank is retained when ordering stops. It contains no information about rank retention rules, inactivity consequences, or ordering requirements for maintaining rank. A direct answer would require a section explicitly stating retention or loss conditions based on ordering activity."
}
```
````

### Repeat 3: candidate

unparseable model output

````text
```json
{
  "selected_ranks": [],
  "answer_supported": false,
  "confidence": 0.1,
  "support": [],
  "missing_facts": [
    "Explicit rule governing whether sales rank is retained when an FBO stops ordering",
    "Definition of 'permanent' retention or loss conditions for sales levels",
    "Automatic inactivity rules that would affect rank status",
    "Minimum ordering or activity requirements to maintain achieved rank"
  ]
}
```

The candidate section only defines what a Sales Level is (cumulative Case Credits achievement), not the retention or loss rules when ordering stops. To answer whether rank is permanently kept after stopping orders requires governance clauses addressing rank maintenance conditions, inactivity consequences, or explicit retention/loss rules—none of which are provided in the candidate text.
````
