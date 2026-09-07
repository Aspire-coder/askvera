# Isolated selector comparison

Selector decisions and experimental drafts only, not final chatbot answers or a release gate.

Candidate variant: structural. Captures: 84.

| Version | Decision/evidence checks passed | Attempts | Execution errors |
| --- | ---: | ---: | ---: |
| combined | 36 | 42 | 0 |
| structural | 42 | 42 | 0 |

Recorded token usage: {'inputTokens': 341322, 'outputTokens': 12415, 'totalTokens': 353737, 'cacheReadInputTokens': 0}.

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
  "reason": "Keeping sales level requires monthly activity; achieving level does not automatically satisfy monthly activity requirement."
}
```
````

### Repeat 1: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "Keeping a sales level does not automatically make you active every month; you must separately qualify as Active each month by obtaining 4 Active Case Credits in your Home Operating Company during that specific month.",
  "support": [
    {
      "source_id": "s_ee0ca0247984fb7a",
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

### Repeat 2: combined

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
  "reason": "Sales level and activity status are separate requirements; maintaining level does not automatically qualify as active monthly."
}
```
````

### Repeat 2: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "Keeping your sales level does not automatically make you Active every month; you must have a total of 4 Active Case Credits in your Home Operating Company during each month to be considered Active.",
  "support": [
    {
      "source_id": "s_ee0ca0247984fb7a",
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

### Repeat 3: combined

wrong support decision

````text
```json
{
  "selected_source_ids": [
    "s_ee0ca0247984fb7a",
    "s_4ae8240855aeff57",
    "s_6b7a33fc1c207f9f"
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
      "source_id": "s_6b7a33fc1c207f9f",
      "quote": "A Manager who is not Active in any Operating Company for three consecutive Months loses eligibility to qualify for Leadership Bonus, even if he/she has no downline Managers."
    }
  ],
  "reason": "Sales Level and Activity Status are separate requirements; maintaining level does not automatically establish monthly activity."
}
```
````

### Repeat 3: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "Keeping a sales level does not automatically make you active every month; you must separately achieve 4 Active Case Credits each month to be considered Active.",
  "support": [
    {
      "source_id": "s_941834197a047666",
      "quote": "Sales Level: any of various levels achieved by the cumulative Case Credits of the FBO and his/her Downline."
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
    "s_0dd044234fa4916f"
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
    },
    {
      "source_id": "s_0dd044234fa4916f",
      "quote": "Active FBO: An FBO who has generated 4 or more Active Case Credits in his/her Home Operating Company during a calendar month, none of which must be personally purchased."
    }
  ],
  "reason": "Activity qualification is required each month to earn bonuses; rank achievement does not exempt from monthly Active status requirements."
}
```
````

### Repeat 1: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_YES",
  "draft_answer": "Yes, you must still qualify as Active this month. Although you have earned your sales rank, qualifying for bonuses and incentives requires being Active each calendar month, which means generating 4 Active Case Credits in your Home Operating Company during that specific month.",
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

### Repeat 2: combined

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
  "reason": "Active status must be re-qualified each month; earning rank does not waive monthly activity requirements."
}
```
````

### Repeat 2: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_YES",
  "draft_answer": "Yes, you must still qualify as Active this month. To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements during the calendar month in which the bonuses were accrued, regardless of prior rank achievement.",
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

### Repeat 3: combined

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "s_ee0ca0247984fb7a",
    "s_4ae8240855aeff57"
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
    }
  ],
  "reason": "Activity qualification required every month regardless of sales rank to receive bonuses."
}
```
````

### Repeat 3: structural

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
  "reason": "No candidate addresses automatic monthly activity from sales level retention."
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
  "missing_facts": ["rule linking sales level maintenance to automatic monthly active status"],
  "confidence": 0.0
}
```
````

### Repeat 2: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate addresses whether maintaining sales level requires monthly activity."
}
```
````

### Repeat 2: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": ["Rule establishing whether maintaining a sales level automatically qualifies someone as active each month"],
  "confidence": 0.1
}
```
````

### Repeat 3: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "Candidate defines Sales Level but does not address activity requirements or automatic status."
}
```
````

### Repeat 3: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Rule establishing whether maintaining a sales level automatically results in monthly active status"
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
  "reason": "Candidate addresses voluntary termination only, not automatic termination for inactivity."
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
  "missing_facts": ["Rule establishing automatic termination of FBO business based on inactivity or failure to order for a specified period"],
  "confidence": 0.3
}
```
````

### Repeat 2: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "Candidate addresses voluntary termination, not automatic termination for inactivity."
}
```
````

### Repeat 2: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": ["rule for automatic termination based on inactivity or failure to order"],
  "confidence": 0.3
}
```
````

### Repeat 3: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "Candidate describes voluntary termination only, not automatic termination for inactivity."
}
```
````

### Repeat 3: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Rule establishing automatic termination of FBO business based on inactivity (no orders for one month)"
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
  "reason": "No candidate provided contains Canadian customer service contact information."
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
    "Canadian customer service telephone number"
  ],
  "confidence": 0.95
}
```
````

### Repeat 2: combined

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

### Repeat 2: structural

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
  "confidence": 0.95
}
```
````

### Repeat 3: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate section contains Canadian customer service telephone contact information."
}
```
````

### Repeat 3: structural

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
  "reason": "No candidate addresses retention or loss of sales rank upon cessation of orders."
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
  "missing_facts": ["rule for retention or loss of sales rank upon cessation of ordering"],
  "confidence": 0.1
}
```
````

### Repeat 2: combined

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

### Repeat 2: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": ["Rule governing retention or loss of sales rank upon cessation of ordering"],
  "confidence": 0.1
}
```
````

### Repeat 3: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate addresses retention or loss of sales rank upon cessation of ordering."
}
```
````

### Repeat 3: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": ["rule governing whether sales rank is retained or lost upon cessation of ordering"],
  "confidence": 0.1
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
  "reason": "Directly states Active qualification requirement: 4 Active Case Credits per month in Home or Foreign Operating Company."
}
```
````

### Repeat 1: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_FACT",
  "draft_answer": "To become Active, an FBO must have a total of 4 Active Case Credits in their Home Operating Company during that month, or if qualifying in a Foreign Operating Company, must have qualified as Active in the Home Operating Company during the previous month or have 4 Active Case Credits in that Foreign Operating Company during that month.",
  "support": [
    {
      "source_id": "s_4ae8240855aeff57",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month. To be considered Active for the Month in a Foreign Operating Company, he/she must have qualified as Active in the Home Operating Company during the previous Month; or have a Total of 4 Active Case Credits in that Foreign Operating Company during that Month."
    }
  ],
  "missing_facts": [],
  "confidence": 0.95
}
```
````

### Repeat 2: combined

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
  "reason": "Directly states requirement to become Active: earn 4 Active Case Credits in applicable Operating Company each month."
}
```
````

### Repeat 2: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_FACT",
  "draft_answer": "To become Active, an FBO must have a total of 4 Active Case Credits in their Home Operating Company during that month, or if qualifying in a Foreign Operating Company, must have been Active in their Home Operating Company the previous month or have 4 Active Case Credits in that Foreign Operating Company during that month.",
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

### Repeat 3: combined

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
  "reason": "Directly states Activity Qualification requirements for Home and Foreign Operating Companies."
}
```
````

### Repeat 3: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_FACT",
  "draft_answer": "To become Active, an FBO must have a Total of 4 Active Case Credits in their Home Operating Company during that month, or if in a Foreign Operating Company, must have qualified as Active in the Home Operating Company during the previous month or have 4 Active Case Credits in that Foreign Operating Company during that month.",
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
    "s_c427fc88bec3d7ca"
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
    }
  ],
  "reason": "Sources directly state Active requirement: 4 Active Case Credits monthly in Home Operating Company."
}
```
````

### Repeat 1: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_FACT",
  "draft_answer": "To be active this month, an FBO must have a total of 4 Active Case Credits in their Home Operating Company during that month.",
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

### Repeat 2: combined

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "s_4ae8240855aeff57",
    "s_1f443fe4e4fb2839",
    "s_c427fc88bec3d7ca"
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
    }
  ],
  "reason": "Sources directly specify activity requirement: 4 Active Case Credits per month for Active status."
}
```
````

### Repeat 2: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_FACT",
  "draft_answer": "To be active this month, an FBO must have a total of 4 Active Case Credits in their Home Operating Company during that month, or if in a Foreign Operating Company, must have been active in the Home Operating Company the previous month or have 4 Active Case Credits in that Foreign Operating Company.",
  "support": [
    {
      "source_id": "s_4ae8240855aeff57",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month. To be considered Active for the Month in a Foreign Operating Company, he/she must have qualified as Active in the Home Operating Company during the previous Month; or have a Total of 4 Active Case Credits in that Foreign Operating Company during that Month."
    }
  ],
  "missing_facts": [],
  "confidence": 0.95
}
```
````

### Repeat 3: combined

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
      "quote": "(b) To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_1f443fe4e4fb2839",
      "quote": "1) Be Active every month."
    }
  ],
  "reason": "To be active this month, FBO must have 4 Active Case Credits in Home Operating Company."
}
```
````

### Repeat 3: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_FACT",
  "draft_answer": "To be active this month, an FBO must have a total of 4 Active Case Credits in their Home Operating Company during that month.",
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
  "reason": "No candidate addresses sales rank retention rules or permanence."
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
    "Rule for automatic retention of sales rank based on Active status in current month",
    "Definition of conditions for permanent retention of sales rank"
  ],
  "confidence": 0.1
}
```
````

### Repeat 2: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate directly addresses sales rank retention rules or permanence."
}
```
````

### Repeat 2: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": ["rule establishing whether Active status in the current month results in permanent retention of sales rank"],
  "confidence": 0.1
}
```
````

### Repeat 3: combined

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

### Repeat 3: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": ["rule for permanent retention of sales rank based on active status in current month"],
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
  "reason": "Candidate addresses voluntary termination only, not automatic termination by inactivity."
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
  "missing_facts": ["automatic termination rule based on inactivity"],
  "confidence": 0.2
}
```
````

### Repeat 2: combined

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

### Repeat 2: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": ["automatic termination rule for inactive sales participants"],
  "confidence": 0.3
}
```
````

### Repeat 3: combined

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

### Repeat 3: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": ["rule establishing automatic termination based on inactivity"],
  "confidence": 0.3
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
    "s_4ae8240855aeff57"
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
    }
  ],
  "reason": "Activity requires monthly 4 Case Credits, not prior-month status. Prior month activity alone is insufficient."
}
```
````

### Repeat 1: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "No, being Active last month does not automatically make you Active this month. Active status must be earned each month by meeting the current month's requirements: having 4 Active Case Credits in your Home Operating Company during that specific month.",
  "support": [
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    }
  ],
  "missing_facts": [],
  "confidence": 0.95
}
```
````

### Repeat 2: combined

wrong support decision

````text
```json
{
  "selected_source_ids": [
    "s_ee0ca0247984fb7a",
    "s_4ae8240855aeff57"
  ],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.3,
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
  "reason": "Activity is determined monthly by case credits, not prior month status alone."
}
```
````

### Repeat 2: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "No, staying Active last month does not automatically make you Active this month; you must have a Total of 4 Active Case Credits in your Home Operating Company during the current month to be considered Active.",
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

### Repeat 3: combined

wrong support decision

````text
```json
{
  "selected_source_ids": [
    "s_ee0ca0247984fb7a",
    "s_4ae8240855aeff57"
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
    }
  ],
  "reason": "Activity is determined by monthly case credit requirements, not prior month status."
}
```
````

### Repeat 3: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_NO",
  "draft_answer": "No, prior month Active status does not carry forward to the current month; an FBO must have 4 Active Case Credits in the current month to be considered Active that month.",
  "support": [
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "s_ee0ca0247984fb7a",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
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
  "reason": "Directly states the specific requirement: 4 Active Case Credits in home company."
}
```
````

### Repeat 1: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_FACT",
  "draft_answer": "To qualify as Active in their home company for the month, an FBO must have a total of 4 Active Case Credits in the Home Operating Company during that month.",
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

### Repeat 2: combined

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
  "reason": "Both sources directly state the specific requirement: 4 Active Case Credits in home company."
}
```
````

### Repeat 2: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_FACT",
  "draft_answer": "To qualify as Active in their home company for the month, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that month.",
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

### Repeat 3: combined

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
  "reason": "Directly states the specific Active qualification requirement for FBOs in home company."
}
```
````

### Repeat 3: structural

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "decision": "ANSWER_FACT",
  "draft_answer": "An FBO must have a Total of 4 Active Case Credits in their Home Operating Company during that month to qualify as Active in their home company for the month.",
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
  "reason": "No candidate documents contain pricing information for Active Case Credits in Canadian dollars."
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
  "missing_facts": ["pricing in Canadian dollars for Active Case Credits"],
  "confidence": 0.1
}
```
````

### Repeat 2: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate contains pricing information for Active Case Credits in Canadian dollars."
}
```
````

### Repeat 2: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "The cost in Canadian dollars for four Active Case Credits is not stated in the provided documents. While the documents reference Active Case Credits as a requirement for activity qualification, they do not contain pricing information in Canadian dollars for this product or service."
  ],
  "confidence": 0.95
}
```
````

### Repeat 3: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate contains pricing information for Active Case Credits in Canadian dollars."
}
```
````

### Repeat 3: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": ["pricing in Canadian dollars for Active Case Credits"],
  "confidence": 0.1
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
  "reason": "Candidate only covers voluntary termination, not automatic closure for missed orders."
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
  "missing_facts": ["automatic termination rule for missed orders"],
  "confidence": 0.3
}
```
````

### Repeat 2: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate addresses automatic termination for missed orders."
}
```
````

### Repeat 2: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": ["rule governing automatic/involuntary termination of Forever Business for missed orders"],
  "confidence": 0.2
}
```
````

### Repeat 3: combined

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate addresses automatic termination for missed orders."
}
```
````

### Repeat 3: structural

correctly withheld unsupported answer

````text
```json
{
  "decision": "INSUFFICIENT_EVIDENCE",
  "draft_answer": "",
  "support": [],
  "missing_facts": [
    "Rule governing automatic/involuntary termination of Forever Business for missed orders or inactivity"
  ],
  "confidence": 0.3
}
```
````
