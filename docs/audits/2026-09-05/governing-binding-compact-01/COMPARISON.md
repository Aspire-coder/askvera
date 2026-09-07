# Isolated selector comparison

Selector decisions and experimental drafts only, not final chatbot answers or a release gate.

Candidate variant: see manifest requests. Captures: 32.

| Version | Decision/evidence checks passed | Attempts | Execution errors |
| --- | ---: | ---: | ---: |
| current | 6 | 8 | 0 |
| ranking | 7 | 8 | 0 |
| binding | 5 | 8 | 0 |
| combined | 7 | 8 | 0 |

Recorded token usage: {'inputTokens': 135676, 'outputTokens': 5086, 'totalTokens': 140762, 'cacheReadInputTokens': 0}.

Results are exploratory on reused cases. A passed check does not certify all generated claims.

## CA-04

Does keeping my sales level mean I'm automatically active every month?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

### Repeat 1: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 2, 6, 18, 19],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.45,
  "reason": "Candidate 4 explains that Activity status is a separate monthly requirement (4 Active Case Credits) distinct from Sales Level achievement. It shows that keeping a Sales Level does NOT automatically make someone Active each month—Activity must be achieved independently every month. However, it addresses bonus qualification consequences rather than directly stating whether Sales Level maintenance itself requires monthly activity. Candidates 2, 6, 18, and 19 reinforce that being Active every month is a separate, ongoing requirement for various benefits and level maintenance, not automatic from Sales Level alone."
}
```
````

### Repeat 1: ranking

wrong support decision

````text
```json
{
  "selected_ranks": [1, 4, 11, 19],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.45,
  "reason": "Candidate 1 explains that Activity status is determined monthly by earning 4 Active Case Credits—it is NOT automatic based on Sales Level. The policy distinguishes between keeping a Sales Level (which is cumulative) and being Active each month (which requires monthly qualification). Candidates 4, 11, and 19 reinforce that Active status must be achieved 'every month' and that inactivity for three consecutive months results in loss of Leadership Bonus eligibility, confirming Activity is not automatic. The answer is 'no'—Sales Level and monthly Activity are separate requirements."
}
```
````

### Repeat 1: binding

wrong support decision

````text
```json
{
  "selected_source_ids": [
    "s_4ae8240855aeff57",
    "s_1f443fe4e4fb2839",
    "s_6b7a33fc1c207f9f"
  ],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.35,
  "support": [
    {
      "source_id": "s_4ae8240855aeff57",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_1f443fe4e4fb2839",
      "quote": "1) Be Active every month."
    },
    {
      "source_id": "s_6b7a33fc1c207f9f",
      "quote": "A Manager who is not Active in any Operating Company for three consecutive Months loses eligibility to qualify for Leadership Bonus, even if he/she has no downline Managers."
    }
  ],
  "reason": "Sales Level retention requires separate monthly Activity qualification; holding a level does not automatically satisfy monthly Activity requirements."
}
```
````

### Repeat 1: combined

wrong support decision

````text
```json
{
  "selected_source_ids": [
    "s_ee0ca0247984fb7a",
    "s_4ae8240855aeff57",
    "s_941834197a047666"
  ],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.45,
  "support": [
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "s_4ae8240855aeff57",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_941834197a047666",
      "quote": "Sales Level: any of various levels achieved by the cumulative Case Credits of the FBO and his/her Downline."
    }
  ],
  "reason": "Sales Level and Activity Status are separate requirements; keeping level does not ensure automatic monthly activity."
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
  "selected_ranks": [4, 3, 11],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.65,
  "reason": "Candidate 4 states that during the 36-month Earned Incentive period, a Manager receives payment 'each Month that the Month 3 Case Credit requirement is maintained' (section 10.01-e), and section 10.01-f clarifies that if credits drop below the Month 3 requirement, payment is recalculated rather than forfeited. However, the policy does not explicitly state whether earning a sales rank eliminates the need for monthly Activity qualification. Candidates 3 and 11 clarify that Active status requires 4 Case Credits monthly for bonuses and incentives, and that Earned Incentive payments depend on maintaining Month 3 Case Credit thresholds, suggesting ongoing monthly qualification is required even after initial Earned Incentive qualification."
}
```
````

### Repeat 1: ranking

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [1, 2, 12],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "reason": "Candidate 1 (4.03(a)) directly answers the question: to qualify for bonuses and incentives, an FBO must be Active each month, regardless of having earned a rank previously. This is monthly recurring requirement independent of rank achievement. Candidate 2 reinforces the monthly Active qualification requirement. Candidate 12 clarifies that loss of Active status for three consecutive months has consequences, further confirming Active status must be re-qualified monthly."
}
```
````

### Repeat 1: binding

governing activity rule not first

````text
```json
{
  "selected_source_ids": [
    "s_58c042bf07cf2d3c",
    "s_ba98bd7acf7484f2",
    "s_ee0ca0247984fb7a"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "s_58c042bf07cf2d3c",
      "quote": "During the period of 36 Months immediately following qualification, the Manager will receive the maximum payment amount for the level achieved each Month that the Month 3 Case Credit requirement is maintained."
    },
    {
      "source_id": "s_ba98bd7acf7484f2",
      "quote": "During the period of 36 Months immediately following qualification, the Manager will receive the maximum payment amount for the level achieved each Month that the Month 3 Case Credit requirement is maintained."
    },
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    }
  ],
  "reason": "Earned Incentive requires maintaining Month 3 Case Credit requirement monthly, not just initial qualification."
}
```
````

### Repeat 1: combined

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "s_ee0ca0247984fb7a",
    "s_4ae8240855aeff57"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.95,
  "support": [
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "s_4ae8240855aeff57",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "reason": "Activity qualification is required each month regardless of prior sales rank achievement."
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
  "reason": "The candidate defines 'Sales Level' but does not address the relationship between maintaining a sales level and automatic monthly activity status. The question asks about an activity rule or requirement, while the candidate only provides a definitional explanation of what sales levels are."
}
```
````

### Repeat 1: ranking

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "The candidate section defines 'Sales Level' as ranks achieved through cumulative Case Credits, but does not address the relationship between maintaining a sales level and automatic monthly activity status. The question asks about activity requirements or automatic status, which is not covered by this definitional section."
}
```
````

### Repeat 1: binding

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "Candidate defines Sales Level but does not address automatic activity status."
}
```
````

### Repeat 1: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate addresses automatic monthly activity from maintaining sales level."
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
  "reason": "Candidate 1 addresses voluntary termination by written request, not automatic termination for inactivity. The user question asks about automatic termination due to one month without orders, which is a different scenario. No candidate provided directly answers the question about inactivity-based automatic termination."
}
```
````

### Repeat 1: ranking

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 addresses voluntary termination by written request, not automatic termination due to inactivity or failure to order. The question asks about automatic termination triggered by one month without orders; this candidate does not address that scenario."
}
```
````

### Repeat 1: binding

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate addresses automatic termination for inactivity or non-ordering."
}
```
````

### Repeat 1: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "Candidate addresses voluntary termination only, not automatic termination for inactivity."
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
  "reason": "Candidate 1 is a policy definition section about Sales Levels and is not related to customer service contact information. No candidates provided contain Canadian customer service telephone numbers or office directory information."
}
```
````

### Repeat 1: ranking

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 is about sales level definitions and does not contain customer service contact information. No relevant candidates provided for the user's question about Canadian customer service telephone number."
}
```
````

### Repeat 1: binding

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate provides Canadian customer service telephone number."
}
```
````

### Repeat 1: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate section contains Canadian customer service telephone number."
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
  "reason": "The candidate defines 'Sales Level' but does not address retention rules, inactivity consequences, or whether rank is permanently kept when ordering stops. A definition alone does not answer a question about rank retention policy."
}
```
````

### Repeat 1: ranking

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "The candidate section only defines what a Sales Level is (based on cumulative Case Credits), but does not address retention, loss, or what happens when ordering stops. The question asks about a retention rule; this candidate merely defines the term without stating any rule about permanence or loss of rank."
}
```
````

### Repeat 1: binding

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate directly addresses sales rank retention upon stopping orders."
}
```
````

### Repeat 1: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate addresses retention or loss of sales rank through ordering cessation."
}
```
````

## new-active-condition

How do I become Active?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

### Repeat 1: current

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [4, 26, 2],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "reason": "Candidate 4 directly states the requirement to become Active: an FBO must have a Total of 4 Active Case Credits in their Home Operating Company during that Month. Candidate 26 reinforces this same rule. Candidate 2 mentions the ongoing requirement to 'Be Active every month' but does not explain how to initially achieve Active status."
}
```
````

### Repeat 1: ranking

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [1, 2],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.95,
  "reason": "Candidate 1 (Section 4.03) directly answers how to become Active by stating the specific requirement: an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month. Candidate 2 provides the same requirement in concentrated form for clarity."
}
```
````

### Repeat 1: binding

wrong support decision

````text
```json
{
  "selected_source_ids": [
    "s_4ae8240855aeff57",
    "s_1f443fe4e4fb2839",
    "s_ee0ca0247984fb7a"
  ],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.45,
  "support": [
    {
      "source_id": "s_4ae8240855aeff57",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_1f443fe4e4fb2839",
      "quote": "1) Be Active every month."
    },
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "reason": "Sources explain how to achieve and maintain Active status through Case Credits monthly, not initial activation steps."
}
```
````

### Repeat 1: combined

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "s_ee0ca0247984fb7a",
    "s_4ae8240855aeff57"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.95,
  "support": [
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_4ae8240855aeff57",
      "quote": "To be considered Active for the Month in a Foreign Operating Company, he/she must have qualified as Active in the Home Operating Company during the previous Month; or have a Total of 4 Active Case Credits in that Foreign Operating Company during that Month."
    }
  ],
  "reason": "Directly states Active qualification requirement: 4 Active Case Credits per month."
}
```
````

## de-active-condition

Welche Voraussetzungen muss ich erfuellen, um diesen Monat aktiv zu sein?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

### Repeat 1: current

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [4, 26, 2],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "reason": "Candidate 4 directly states the requirement to be Active: an FBO must have a Total of 4 Active Case Credits in their Home Operating Company during that month. Candidate 26 provides the same core definition. Candidate 2 confirms the general requirement to be Active every month."
}
```
````

### Repeat 1: ranking

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [4, 26, 2],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "reason": "Candidate 4 section 4.03(b) directly answers the question by specifying the requirement to be Active this month: an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month. Candidate 26 provides the same rule with identical content. Candidate 2 mentions being Active every month as a general requirement."
}
```
````

### Repeat 1: binding

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "s_4ae8240855aeff57",
    "s_ee0ca0247984fb7a",
    "s_1f443fe4e4fb2839"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "s_4ae8240855aeff57",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_1f443fe4e4fb2839",
      "quote": "Be Active every month."
    }
  ],
  "reason": "Policy explicitly defines Activity requirement as 4 Active Case Credits monthly."
}
```
````

### Repeat 1: combined

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "s_4ae8240855aeff57",
    "s_ee0ca0247984fb7a",
    "s_1f443fe4e4fb2839"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "s_4ae8240855aeff57",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_1f443fe4e4fb2839",
      "quote": "1) Be Active every month."
    }
  ],
  "reason": "Source specifies exact requirement: 4 Active Case Credits in Home Operating Company to be active this month."
}
```
````
