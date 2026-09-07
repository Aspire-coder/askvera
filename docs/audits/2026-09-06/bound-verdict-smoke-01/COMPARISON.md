# Isolated selector comparison

Selector decisions and experimental drafts only, not final chatbot answers or a release gate.

Candidate variant: bound-verdict. Captures: 20.

| Version | Decision/evidence checks passed | Attempts | Execution errors |
| --- | ---: | ---: | ---: |
| combined | 9 | 10 | 0 |
| verdict | 6 | 10 | 0 |

Recorded token usage: {'inputTokens': 69430, 'outputTokens': 3306, 'totalTokens': 72736, 'cacheReadInputTokens': 0}.

Results are exploratory on reused cases. A passed check does not certify all generated claims.

## CA-04

Does keeping my sales level mean I'm automatically active every month?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

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
  "reason": "Keeping sales level is separate from monthly activity; activity status must be earned each month independently."
}
```
````

### Repeat 1: verdict

governing activity rule not first

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "Keeping your sales level does not automatically make you active every month; you must have 4 Active Case Credits in your Home Operating Company each month to be considered Active.",
  "selected_source_ids": [
    "s_941834197a047666",
    "s_ee0ca0247984fb7a",
    "s_4ae8240855aeff57"
  ],
  "support": [
    {
      "source_id": "s_941834197a047666",
      "quote": "Sales Level: any of various levels achieved by the cumulative Case Credits of the FBO and his/her Downline."
    },
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_4ae8240855aeff57",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "missing_facts": [],
  "confidence": 0.95
}
```
````

## CA-04-paraphrase

I already earned my sales rank. Do I still need to qualify as Active again this month?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

### Repeat 1: combined

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "s_ee0ca0247984fb7a",
    "s_4ae8240855aeff57",
    "s_c8c81eea3339c099"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
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
      "source_id": "s_c8c81eea3339c099",
      "quote": "A Manager who is not Active in any Operating Company for three consecutive Months loses eligibility to qualify for Leadership Bonus, even if he/she has no downline Managers."
    }
  ],
  "reason": "Active qualification is required each month for bonuses; earned rank does not exempt from monthly activity requirement."
}
```
````

### Repeat 1: verdict

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_YES",
  "draft_answer": "Yes, you must still qualify as Active this month. To qualify for any bonuses and incentives, an FBO must be Active and meet all other requirements during the calendar month in which bonuses are accrued, regardless of prior rank achievement.",
  "selected_source_ids": [
    "s_ee0ca0247984fb7a",
    "s_4ae8240855aeff57"
  ],
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
  "missing_facts": [],
  "confidence": 0.95
}
```
````

## missing-activity-rule

Does keeping my sales level mean I'm automatically active every month?

Expected support: False. Governing sections: [].

### Repeat 1: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate addresses automatic activity from maintaining sales level."
}
```
````

### Repeat 1: verdict

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "selected_source_ids": [],
  "support": [],
  "missing_facts": [
    "Rule establishing whether maintaining sales level automatically results in monthly active status"
  ],
  "confidence": 0.0
}
```
````

## wrong-termination-trigger

If I do not order anything for one month, is my FBO business automatically terminated?

Expected support: False. Governing sections: [].

### Repeat 1: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate addresses automatic termination due to inactivity or lack of orders."
}
```
````

### Repeat 1: verdict

wrong answer polarity

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "Automatic termination is not established by the supplied passage; only voluntary termination by written request is addressed.",
  "selected_source_ids": ["s_67eb1c6234e3618c"],
  "support": [
    {
      "source_id": "s_67eb1c6234e3618c",
      "quote": "An FBO may terminate his/her Forever Business by submitting a written request, signed by all named individuals appearing on the current approved Forever Business."
    }
  ],
  "missing_facts": [
    "Rule governing automatic termination for non-ordering during a specified period"
  ],
  "confidence": 0.8
}
```
````

## missing-phone

What is the Canadian customer service telephone number?

Expected support: False. Governing sections: [].

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

### Repeat 1: verdict

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "selected_source_ids": [],
  "support": [],
  "missing_facts": ["Canadian customer service telephone number"],
  "confidence": 0.95
}
```
````

## missing-retention-rule

Do I permanently keep my sales rank if I stop ordering?

Expected support: False. Governing sections: [].

### Repeat 1: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate addresses retention or loss of sales rank through inactivity."
}
```
````

### Repeat 1: verdict

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "selected_source_ids": [],
  "support": [],
  "missing_facts": [
    "rule specifying whether sales rank is retained, lost, or requires continuous ordering to maintain"
  ],
  "confidence": 0.3
}
```
````

## new-active-condition

How do I become Active?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

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
  "reason": "Directly states the requirement to become Active: 4 Active Case Credits in home or foreign operating company."
}
```
````

### Repeat 1: verdict

selection and quoted source order differ

````text
```json
{
  "decision": "ANSWER_FACT",
  "draft_answer": "To become Active, an FBO must have a total of 4 Active Case Credits in their Home Operating Company during that month.",
  "selected_source_ids": [
    "s_ee0ca0247984fb7a",
    "s_4ae8240855aeff57"
  ],
  "support": [
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "missing_facts": [],
  "confidence": 0.95
}
```
````

## de-active-condition

Welche Voraussetzungen muss ich erfuellen, um diesen Monat aktiv zu sein?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

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
      "quote": "Be Active every month."
    }
  ],
  "reason": "Section 4.03(b) directly states the requirement: 4 Active Case Credits in Home Operating Company per month."
}
```
````

### Repeat 1: verdict

unknown or duplicate source ID

````text
```json
{
  "decision": "ANSWER_FACT",
  "draft_answer": "To be active this month, an FBO must have a total of 4 Active Case Credits in the Home Operating Company during that month.",
  "selected_source_ids": [
    "s_4ae8240855aeff57",
    "s_4ae8240855aeff57"
  ],
  "support": [
    {
      "source_id": "s_4ae8240855aeff57",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "missing_facts": [],
  "confidence": 0.95
}
```
````

## activity-background-retention

I am Active this month. Does that mean I keep my sales rank permanently?

Expected support: False. Governing sections: [].

### Repeat 1: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate addresses retention rules for sales rank based on monthly activity."
}
```
````

### Repeat 1: verdict

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "selected_source_ids": [],
  "support": [],
  "missing_facts": [
    "Rule governing whether Active status in a month results in permanent retention of sales rank"
  ],
  "confidence": 0.1
}
```
````

## activity-background-termination

I kept my sales rank but was inactive this month. Is my business automatically terminated?

Expected support: False. Governing sections: [].

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

### Repeat 1: verdict

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "selected_source_ids": [],
  "support": [],
  "missing_facts": ["rule establishing automatic termination based on inactivity"],
  "confidence": 0.3
}
```
````
