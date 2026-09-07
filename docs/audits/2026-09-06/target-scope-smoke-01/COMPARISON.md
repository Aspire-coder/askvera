# Isolated selector comparison

Selector decisions and experimental drafts only, not final chatbot answers or a release gate.

Candidate variant: target-scope. Captures: 20.

| Version | Decision/evidence checks passed | Attempts | Execution errors |
| --- | ---: | ---: | ---: |
| combined | 9 | 10 | 0 |
| scoped | 9 | 10 | 0 |

Recorded token usage: {'inputTokens': 75200, 'outputTokens': 3272, 'totalTokens': 78472, 'cacheReadInputTokens': 0}.

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
  "reason": "Sales Level and Activity status are separate requirements; keeping level does not auto-qualify monthly activity."
}
```
````

### Repeat 1: scoped

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
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
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
  "reason": "Activity requires monthly 4 Active Case Credits; Sales Level alone does not establish monthly activity."
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
    "s_06338f7b61f82bdb"
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
      "source_id": "s_06338f7b61f82bdb",
      "quote": "Supervisors, Assistant Managers and Managers who do not achieve Active Status will not be paid a Volume Bonus that month."
    }
  ],
  "reason": "Active status must be re-qualified each month; earned rank does not carry forward activity requirements."
}
```
````

### Repeat 1: scoped

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
  "reason": "Active status must be re-qualified monthly; earning rank does not exempt from monthly activity requirement."
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
  "reason": "No candidate addresses the relationship between keeping sales level and monthly activity requirements."
}
```
````

### Repeat 1: scoped

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate directly addresses monthly activity requirements or automatic status maintenance."
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

### Repeat 1: scoped

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
  "reason": "No candidate sections contain Canadian customer service contact information."
}
```
````

### Repeat 1: scoped

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
  "reason": "No candidate addresses sales rank retention after stopping orders."
}
```
````

### Repeat 1: scoped

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
  "reason": "Directly states the requirement to become Active: 4 Active Case Credits per month in Home or Foreign OC."
}
```
````

### Repeat 1: scoped

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
      "quote": "To be considered Active for the Month in a Foreign Operating Company, he/she must have qualified as Active in the Home Operating Company during the previous Month; or have a Total of 4 Active Case Credits in that Foreign Operating Company during that Month."
    }
  ],
  "reason": "Directly states the requirement to become Active: accumulate 4 Active Case Credits in Home or Foreign Operating Company."
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
      "quote": "1) Be Active every month."
    }
  ],
  "reason": "Policy directly specifies 4 Active Case Credits monthly requirement for Active status."
}
```
````

### Repeat 1: scoped

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
  "reason": "Source directly states the requirement: 4 Active Case Credits needed for monthly activity status."
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
  "reason": "No candidate addresses retention rules or permanence of sales rank."
}
```
````

### Repeat 1: scoped

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "No candidate directly addresses whether active status maintains sales rank permanently."
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

### Repeat 1: scoped

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
