# Isolated selector comparison

Selector decisions and experimental drafts only, not final chatbot answers or a release gate.

Candidate variant: structural. Captures: 28.

| Version | Decision/evidence checks passed | Attempts | Execution errors |
| --- | ---: | ---: | ---: |
| combined | 12 | 14 | 0 |
| structural | 14 | 14 | 0 |

Recorded token usage: {'inputTokens': 113774, 'outputTokens': 4360, 'totalTokens': 118134, 'cacheReadInputTokens': 0}.

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
  "reason": "Keeping sales level is distinct from monthly Activity status; Activity must be earned each month separately."
}
```
````

### Repeat 1: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "Keeping a sales level does not automatically make an FBO active every month; instead, an FBO must have 4 Active Case Credits in their Home Operating Company during that specific month to be considered Active.",
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
  "reason": "Yes, Active status must be re-qualified each month to receive bonuses, regardless of prior rank achievement."
}
```
````

### Repeat 1: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_YES",
  "draft_answer": "Yes, you must still qualify as Active each month. An FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which bonuses are accrued, regardless of prior rank achievement.",
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
  "reason": "No candidate addresses whether keeping sales level requires monthly activity."
}
```
````

### Repeat 1: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Rule establishing whether maintaining a sales level automatically qualifies someone as active each month"
  ],
  "confidence": 0.1
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
  "reason": "No candidate addresses automatic termination for inactivity or non-ordering."
}
```
````

### Repeat 1: structural

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
  "confidence": 0.85
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
  "reason": "No candidate section contains Canadian customer service contact information."
}
```
````

### Repeat 1: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
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
  "reason": "No candidate addresses retention or loss of sales rank upon stopping orders."
}
```
````

### Repeat 1: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": ["Rule governing whether sales rank is retained permanently upon cessation of ordering"],
  "confidence": 0.2
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
  "reason": "Directly states Active qualification requirement: 4 Active Case Credits per month."
}
```
````

### Repeat 1: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_FACT",
  "draft_answer": "To become Active, an FBO must have a total of 4 Active Case Credits in their Home Operating Company during that month, or if qualifying in a Foreign Operating Company, must have been Active in the Home Operating Company during the previous month or have 4 Active Case Credits in that Foreign Operating Company during that month.",
  "support": [
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month. To be considered Active for the Month in a Foreign Operating Company, he/she must have qualified as Active in the Home Operating Company during the previous Month; or have a Total of 4 Active Case Credits in that Foreign Operating Company during that Month."
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
    "s_1f443fe4e4fb2839",
    "s_c427fc88bec3d7ca",
    "s_ee0ca0247984fb7a"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
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
      "source_id": "s_c427fc88bec3d7ca",
      "quote": "1) Be Active every month."
    },
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "reason": "Sources directly state Active status requirement: 4 Active Case Credits minimum per month."
}
```
````

### Repeat 1: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_FACT",
  "draft_answer": "To be active this month, an FBO must have a total of 4 Active Case Credits in the Home Operating Company during that month.",
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

### Repeat 1: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Rule establishing whether Active status in current month results in permanent retention of sales rank, or whether sales rank is subject to loss upon future inactivity or failure to maintain qualifications"
  ],
  "confidence": 0.0
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
  "reason": "Candidate addresses voluntary termination, not automatic termination by inactivity."
}
```
````

### Repeat 1: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "automatic termination rule for inactive FBOs",
    "inactivity period triggering automatic termination",
    "relationship between sales rank retention and termination status"
  ],
  "confidence": 0.1
}
```
````

## fresh-activity-carryover

Can I stay Active this month just because I was Active last month?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

### Repeat 1: combined

wrong support decision

````text
```json
{
  "selected_source_ids": [
    "s_ee0ca0247984fb7a",
    "s_4ae8240855aeff57",
    "s_06338f7b61f82bdb"
  ],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.35,
  "support": [
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_4ae8240855aeff57",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_06338f7b61f82bdb",
      "quote": "Assistant Supervisors who do not achieve Active status will not be paid a Personal Bonus or a Preferred Customer Bonus that month."
    }
  ],
  "reason": "Activity status must be earned each month through case credits; prior month status does not qualify current month."
}
```
````

### Repeat 1: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "No, you cannot stay Active this month just because you were Active last month. To be considered Active for the current month, you must have a Total of 4 Active Case Credits in your Home Operating Company during that month.",
  "support": [
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

## fresh-monthly-condition

What must an FBO do to qualify as Active in their home company for the month?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

### Repeat 1: combined

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "s_4ae8240855aeff57",
    "s_ee0ca0247984fb7a"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.95,
  "support": [
    {
      "source_id": "s_4ae8240855aeff57",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "reason": "Both sources directly state the specific requirement: 4 Active Case Credits in Home Operating Company."
}
```
````

### Repeat 1: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_FACT",
  "draft_answer": "An FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month to qualify as Active in their home company for the month.",
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

## fresh-cc-cash

Exactly how many Canadian dollars will four Active Case Credits cost me?

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
  "reason": "No candidate sources contain pricing information for Active Case Credits in Canadian dollars."
}
```
````

### Repeat 1: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "pricing in Canadian dollars for Active Case Credits",
    "currency conversion or country-specific pricing for Active Case Credits"
  ],
  "confidence": 0.95
}
```
````

## fresh-inactivity-closure

I missed this month's order. Will Forever close my business without my asking?

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
  "reason": "Candidate addresses voluntary termination only, not automatic closure for missed orders."
}
```
````

### Repeat 1: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": ["Rule establishing conditions for automatic/involuntary termination of Forever Business for missed orders"],
  "confidence": 0.3
}
```
````
