# Isolated selector comparison

Selector decisions and experimental drafts only, not final chatbot answers or a release gate.

Candidate variants: ranking-only, full-ID binding-only, and combined. Captures: 96.

| Version | Decision/evidence checks passed | Attempts | Execution errors |
| --- | ---: | ---: | ---: |
| current | 18 | 24 | 0 |
| ranking | 21 | 24 | 0 |
| binding | 15 | 24 | 0 |
| combined | 17 | 24 | 0 |

Recorded token usage: {'inputTokens': 425910, 'outputTokens': 20855, 'totalTokens': 446765, 'cacheReadInputTokens': 0}.

Results are exploratory on reused cases. A passed check does not certify all generated claims.

## CA-04

Does keeping my sales level mean I'm automatically active every month?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

### Repeat 1: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 6, 10, 18, 19],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.45,
  "reason": "The user asks whether keeping a sales level automatically means being active every month. Candidate 4 directly addresses activity qualification requirements, showing that maintaining a sales level and being active are separate requirements—an FBO must achieve Active status each month (4 Active Case Credits) independent of sales level. Being at a sales level does not automatically confer monthly active status. Candidates 6, 10, 18, and 19 reinforce that specific levels require explicit monthly activity maintenance as a separate obligation. However, Candidate 4 does not explicitly state 'no, sales level alone does not make you automatically active'—it shows the definition of active status as a distinct requirement, which requires inference to answer the user's yes/no question directly."
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
  "reason": "Candidate 1 explains that Activity status requires 4 Active Case Credits each month and that bonuses depend on being Active that month, but it does NOT directly state whether keeping a Sales Level automatically makes one Active. The question conflates Sales Level (a rank achieved through cumulative credits) with Activity status (a monthly qualification requiring current monthly credits). Candidates 4, 11, and 19 show that various Sales Level recipients must separately 'Be Active every month'—indicating these are distinct requirements, not automatic. The policy distinguishes between maintaining a Sales Level and maintaining monthly Active status; the former does not automatically satisfy the latter."
}
```
````

### Repeat 1: binding

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "1f443fe4e4fb28396e527eefbed3aa51ed2340ce3a124b5d30e6cbb6bdec77c0"
  ],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.55,
  "support": [
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "1f443fe4e4fb28396e527eefbed3aa51ed2340ce3a124b5d30e6cbb6bdec77c0",
      "quote": "1) Be Active every month."
    }
  ],
  "reason": "The question asks whether keeping a sales level automatically makes someone active every month. The policy distinguishes between attaining/keeping a sales level and being active—these are separate requirements. Being active requires 4 Case Credits monthly and is a condition for earning bonuses, while a sales level is achieved through cumulative Case Credits. The sources show activity is
````

### Repeat 1: combined

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "941834197a047666473b308a02ba8491754034a0d42082249ffac5f144ead150"
  ],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.55,
  "support": [
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "941834197a047666473b308a02ba8491754034a0d42082249ffac5f144ead150",
      "quote": "Sales Level: any of various levels achieved by the cumulative Case Credits of the FBO and his/her Downline."
    }
  ],
  "reason": "The question conflates two separate concepts: maintaining a sales level (which is based on cumulative Case Credits) and being active each month (which requires 4 Active Case Credits per month). The selected sources clarify that Activity Qualification requires Active status each month to earn bonuses, but Sales Level is achieved through cumulative credits and is distinct
````

### Repeat 2: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 6, 8, 18, 19],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.35,
  "reason": "The user asks whether keeping a sales level automatically makes an FBO active every month. Candidate 4 explains that Activity is a separate qualification requiring 4 Active Case Credits monthly, and that bonuses are forfeited if Active status is not achieved—demonstrating that sales level and activity status are independent requirements. Candidates 6, 8, 18, and 19 reinforce that being Active is a distinct monthly requirement that must be maintained even after achieving a sales level. However, no candidate directly states that sales level alone does NOT automatically confer monthly activity status; the answer must be inferred from the existence of separate activity requirements."
}
```
````

### Repeat 2: ranking

wrong support decision

````text
```json
{
  "selected_ranks": [1, 4, 11],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.35,
  "reason": "Candidate 1 explains that Activity is a separate monthly qualification requirement (4 Active Case Credits required each month) that is distinct from Sales Level achievement. It shows that maintaining a Sales Level does not automatically make an FBO Active each month—Activity must be re-qualified monthly. However, it does not explicitly state 'no, keeping your sales level does not make you automatically active.' Candidates 4 and 11 reinforce that being 'Active every month' is an explicit separate requirement for certain status/incentive programs, further supporting that Activity and Sales Level are independent."
}
```
````

### Repeat 2: binding

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "6b7a33fc1c207f9f3a30cfcc12f29c6a42af7c0d690143d001ebf3e25bf3bb4f"
  ],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.55,
  "support": [
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "6b7a33fc1c207f9f3a30cfcc12f29c6a42af7c0d690143d001ebf3e25bf3bb4f",
      "quote": "A Manager who is not Active in any Operating Company for three consecutive Months loses eligibility to qualify for Leadership Bonus, even if he/she has no downline Managers."
    }
  ],
  "reason": "The question conflates two separate concepts: maintaining a sales level and being active each month. These are distinct requirements. Keeping a sales level is achieved by maintaining cum
````

### Repeat 2: combined

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "941834197a047666473b308a02ba8491754034a0d42082249ffac5f144ead150"
  ],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.55,
  "support": [
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "941834197a047666473b308a02ba8491754034a0d42082249ffac5f144ead150",
      "quote": "Sales Level: any of various levels achieved by the cumulative Case Credits of the FBO and his/her Downline."
    }
  ],
  "reason": "The question conflates maintaining a sales level with automatic monthly activity status. The policy distinguishes these concepts: sales level is based on cumulative case credits, while Activity is a separate monthly qualification requiring 4 Active Case Credits each month. Maintaining a sales level does not automatically establish Activity each month—Activity must be earned independently each month."
````

### Repeat 3: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 2, 6, 18, 19],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.45,
  "reason": "Candidate 4 explains that Activity status (being Active every month) is a separate, monthly requirement from maintaining a Sales Level. It shows that keeping a Sales Level does NOT automatically make you Active each month—you must meet the 4 Active Case Credits requirement each month independently. The policy distinguishes between Sales Level (cumulative achievement) and monthly Activity status (separate qualification). Candidates 2, 6, 18, and 19 provide context on the monthly Activity requirement and consequences of inactivity, but none directly state whether Sales Level alone guarantees monthly Activity—the answer is no, they are separate requirements."
}
```
````

### Repeat 3: ranking

wrong support decision

````text
```json
{
  "selected_ranks": [1, 4, 11, 19, 20],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.35,
  "reason": "The user asks whether keeping a sales level automatically makes them active every month. Candidate 1 explains Activity Qualification requirements (4 Active Case Credits per month) but does not address the relationship between sales level and automatic activity status. Candidates 4, 11, 19, and 20 establish that Active status must be achieved each month through specific case credit requirements—they are separate from and not automatically conferred by sales level. The policy distinguishes sales level (cumulative CC achievement) from monthly Activity status (4 active case credits required each month), indicating these are independent requirements."
}
```
````

### Repeat 3: binding

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "6b7a33fc1c207f9f3a30cfcc12f29c6a42af7c0d690143d001ebf3e25bf3bb4f"
  ],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.6,
  "support": [
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "6b7a33fc1c207f9f3a30cfcc12f29c6a42af7c0d690143d001ebf3e25bf3bb4f",
      "quote": "A Manager who is not Active in any Operating Company for three consecutive Months loses eligibility to qualify for Leadership Bonus, even if he/she has no downline Managers."
    }
  ],
  "reason": "The question asks whether keeping a sales level automatically makes one active each month. The policy distinguishes between maintaining a sales level and being active each month. Being active requires
````

### Repeat 3: combined

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "941834197a047666473b308a02ba8491754034a0d42082249ffac5f144ead150"
  ],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.6,
  "support": [
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "941834197a047666473b308a02ba8491754034a0d42082249ffac5f144ead150",
      "quote": "Sales Level: any of various levels achieved by the cumulative Case Credits of the FBO and his/her Downline."
    }
  ],
  "reason": "The user asks whether keeping a sales level automatically makes them active every month. The selected sources distinguish between Sales Level (a cumulative achievement) and Active status (a monthly requirement based on generating 4 Active Case Credits each month). These clarify that Sales Level and Active status are separate concepts—holding a sales level does not automatically confer Active
````

## CA-04-paraphrase

I already earned my sales rank. Do I still need to qualify as Active again this month?

Expected support: True. Governing sections: ['4.03', '4.03-b'].

### Repeat 1: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 3, 29],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.65,
  "reason": "Candidate 4 (10.01-e) states that during the 36-Month period following qualification, a Manager receives payment 'each Month that the Month 3 Case Credit requirement is maintained,' implying ongoing monthly maintenance is required. Candidate 3 (4.03) clarifies that to qualify for bonuses and incentives, an FBO must be Active during the calendar month bonuses are accrued. Candidate 29 (10.01-e) reinforces the maintenance requirement. However, none directly state whether 'Active' status must be re-qualified monthly versus merely maintained, so the answer requires inference from the maintenance language rather than explicit 'no re-qualification needed' language."
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
  "top_rank_confidence": 0.92,
  "reason": "Candidate 1 (Section 4.03) directly answers the user's question. It establishes that to qualify for bonuses and incentives, an FBO 'must be Active' each calendar month, regardless of prior rank achievement. The rule applies monthly and is not waived by having already earned a sales rank. Candidate 2 provides the specific definition of what 'Active' means (4 Active Case Credits), making both together a complete answer to whether qualification is required again this month."
}
```
````

### Repeat 1: binding

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "c17384880e31082ada9bab0aab23483c8fc863a52b490a2cf5079f9387e14230",
    "ba98bd7acf7484f2da7b0d7f7913871882d30f47fbc4394da8f6fb8b077b61c4"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "c17384880e31082ada9bab0aab23483c8fc863a52b490a2cf5079f9387e14230",
      "quote": "During the period of 36 Months immediately following qualification, the Manager will receive the maximum payment amount for the level achieved each Month that the Month 3 Case Credit requirement is maintained."
    },
    {
      "source_id": "ba98bd7acf7484f2da7b0d7f7913871882d30f47fbc4394da8f6fb8b077b61c4",
      "quote": "During the period of 36 Months immediately following qualification, the Manager will receive the maximum payment amount for the level achieved each Month that the Month 3 Case Credit requirement is maintained."
    }
  ],
  "reason": "Even after earning a sales rank in the Earned Incentive Program during the 36-month period, the Manager must maintain Active status and the Month 3 Case Credit requirement each month to
````

### Repeat 1: combined

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "reason": "The user asks whether earning a sales rank eliminates the need to re-qualify as Active monthly. Section 4.03(a) directly establishes that Active status must be achieved each calendar month to qualify for bonuses and incentives—earning a sales rank does not exempt an FBO from this monthly Active requirement. Section 4.03(b) specifies the concrete requirement: 4 Active Case Credits must be generated during that month to be considered Active."
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
  "reason": "Candidate 4 (Section 10.01) clarifies that during the 36-month Earned Incentive payment period, a Manager receives payment each month the Month 3 Case Credit requirement is maintained, but does not directly answer whether Active status must be re-qualified monthly. Candidate 3 (Section 4.03) establishes the general monthly Active qualification requirement (4 Active Case Credits), which applies to all FBOs including Managers. Candidate 11 provides the maintenance requirements table showing Month 3 thresholds must be sustained. The question asks about re-qualifying as Active each month after earning a sales rank; the documents show Active status is a separate, ongoing monthly requirement distinct from the initial rank achievement, but no single candidate explicitly states 'yes, you must re-qualify as Active each month' in direct response to this specific scenario."
}
```
````

### Repeat 2: ranking

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [1, 2],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "reason": "Candidate 1 directly answers the question: Activity qualification must be met each calendar month to receive bonuses and incentives. Section 4.03(a) states 'To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active...during the calendar month in which the bonuses were accrued.' This establishes that earning a sales rank in prior months does not eliminate the requirement to qualify as Active in the current month. Candidate 2 provides the supporting operational definition of Active status."
}
```
````

### Repeat 2: binding

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "c17384880e31082ada9bab0aab23483c8fc863a52b490a2cf5079f9387e14230",
    "ba98bd7acf7484f2da7b0d7f7913871882d30f47fbc4394da8f6fb8b077b61c4"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "c17384880e31082ada9bab0aab23483c8fc863a52b490a2cf5079f9387e14230",
      "quote": "During the period of 36 Months immediately following qualification, the Manager will receive the maximum payment amount for the level achieved each Month that the Month 3 Case Credit requirement is maintained."
    },
    {
      "source_id": "ba98bd7acf7484f2da7b0d7f7913871882d30f47fbc4394da8f6fb8b077b61c4",
      "quote": "If the Manager's Total Case Credits drop below the Month 3 requirement during any Month, that Month's Earned Incentive payment will be calculated at $2.66 times the Manager's Total Case Credits for that Month."
    }
  ],
  "reason": "The user asks whether earning a sales rank (Earned Incentive/Manager level) eliminates the need to qualify as Active each month. Section 
````

### Repeat 2: combined

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "06338f7b61f82bdbe2a11373942af659387e8d5101dd1b93b25fc91ae43a3a87"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "06338f7b61f82bdbe2a11373942af659387e8d5101dd1b93b25fc91ae43a3a87",
      "quote": "Supervisors, Assistant Managers and Managers who do not achieve Active Status will not be paid a Volume Bonus that month."
    }
  ],
  "reason": "The policy explicitly states that earning a sales rank (e.g., Manager, Supervisor) does not exempt an FBO from the monthly Activity Qualification requirement. To receive bonuses each month, including those tied to the earned rank, an FBO must generate 4
````

### Repeat 3: current

wrong support decision

````text
```json
{
  "selected_ranks": [4, 3, 11],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.65,
  "reason": "Candidate 4 states that to maintain Earned Incentive payments during the 36-month period, the Manager must maintain the Month 3 Case Credit requirement each month (section 10.01-e), and that if case credits drop below the Month 3 requirement, payment is calculated differently but still requires maintaining 50+ credits to receive any payment (section 10.01-g). This directly addresses maintenance requirements for an earned sales rank (Earned Incentive). However, it does not explicitly state whether 'Active' status itself must be re-qualified monthly—it focuses on Case Credit maintenance. Candidate 3 (4.03) clarifies the general Activity Qualification rule that to qualify for bonuses and incentives, an FBO must be Active each calendar month. Candidate 11 provides the maintenance table showing Month 3 requirements must be maintained throughout the 36-month period."
}
```
````

### Repeat 3: ranking

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [1, 2],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "reason": "Candidate 1 directly answers that an FBO must be Active each calendar month to qualify for bonuses and incentives, regardless of prior rank achievement. Section 4.03(a) states the requirement applies to the month bonuses are accrued, and 4.03(b) specifies the 4 Active Case Credit requirement applies monthly. This directly addresses that earning a sales rank does not exempt an FBO from monthly Active qualification."
}
```
````

### Repeat 3: binding

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "ba98bd7acf7484f2da7b0d7f7913871882d30f47fbc4394da8f6fb8b077b61c4",
    "c17384880e31082ada9bab0aab23483c8fc863a52b490a2cf5079f9387e14230"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "ba98bd7acf7484f2da7b0d7f7913871882d30f47fbc4394da8f6fb8b077b61c4",
      "quote": "During the period of 36 Months immediately following qualification, the Manager will receive the maximum payment amount for the level achieved each Month that the Month 3 Case Credit requirement is maintained."
    },
    {
      "source_id": "c17384880e31082ada9bab0aab23483c8fc863a52b490a2cf5079f9387e14230",
      "quote": "An Active Recognized Manager is eligible to participate in the Earned Incentive Program."
    }
  ],
  "reason": "The user asks whether earning a sales rank eliminates the need to qualify as Active each month. Section 4.03 directly answers that regardless of rank or incentive earned, an FBO must be Active each month to receive bonuses and incentives. Section 10.01(e) reinfor
````

### Repeat 3: combined

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "06338f7b61f82bdbe2a11373942af659387e8d5101dd1b93b25fc91ae43a3a87"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "06338f7b61f82bdbe2a11373942af659387e8d5101dd1b93b25fc91ae43a3a87",
      "quote": "Supervisors, Assistant Managers and Managers who do not achieve Active Status will not be paid a Volume Bonus that month."
    }
  ],
  "reason": "The policy explicitly states that to qualify for bonuses and incentives, an FBO must be Active each calendar month—earning a sales rank does not exempt FBOs from the monthly Active requirement. Section 4.03 directly addresses this: regardless of prior achievements,
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
  "reason": "Candidate 1 defines what a Sales Level is but does not address whether maintaining that level means automatic monthly activity status. The question asks about the relationship between sales level retention and active status; the candidate only provides a definitional statement about how sales levels are achieved through cumulative Case Credits. No governing clause about activity requirements or automatic status is presented."
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
  "reason": "The candidate defines 'Sales Level' by listing levels and how they are achieved (cumulative Case Credits), but does not address whether maintaining a sales level automatically satisfies monthly activity requirements or establishes automatic active status. The question asks about the relationship between sales level retention and monthly activity status; the candidate only defines what a sales level is, not the activity or retention rules that govern it."
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
  "reason": "The candidate section defines 'Sales Level' as levels achieved by cumulative Case Credits but does not address whether keeping a sales level means automatic monthly activity. The question asks about the relationship between maintaining a sales level and monthly activity status, which this definition does not answer."
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
  "reason": "The candidate section defines what a Sales Level is (a rank achieved through cumulative Case Credits) but does not address the user's question about whether maintaining that level automatically means being active every month. The question asks about the relationship between keeping a sales level and monthly activity status, which requires a rule about activity requirements or level maintenance conditions, not a definition of sales level itself."
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
  "reason": "Candidate 1 defines 'Sales Level' as a rank achieved through cumulative Case Credits, but does not address the relationship between maintaining a sales level and monthly activity requirements. The question asks about automatic activity status, which requires a clause discussing retention rules, activity requirements, or inactivity consequences—none of which are present in this definition."
}
```
````

### Repeat 2: ranking

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 defines what a Sales Level is, but does not address the relationship between keeping a sales level and automatic monthly activity status. The question asks about a causal or automatic relationship between two concepts; the candidate only defines one of them. No candidates provided directly answer whether maintaining a sales level automatically confers active status each month."
}
```
````

### Repeat 2: binding

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "The candidate section defines 'Sales Level' as achievement of cumulative Case Credits but does not address whether maintaining a sales level automatically ensures monthly activity status. The question asks about the relationship between sales level retention and automatic monthly activity, which requires a clause about activity requirements or retention rules, not a definition of what sales levels are."
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
  "reason": "The candidate section defines what a Sales Level is (a rank achieved through cumulative Case Credits) but does not address the relationship between maintaining a sales level and automatic monthly activity status. The question asks about activity requirements tied to level retention, which requires a rule about activity maintenance or level loss conditions, not a definition of the term itself."
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
  "reason": "Candidate 1 defines Sales Level by cumulative Case Credits but does not address whether maintaining a sales level automatically establishes monthly activity status. The question asks about the relationship between sales level retention and automatic monthly activity, which requires a rule about activity requirements or retention conditions, not a definitional statement about what sales levels are."
}
```
````

### Repeat 3: ranking

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "The candidate defines what a Sales Level is (a rank achieved by cumulative Case Credits) but does not address the relationship between maintaining a sales level and automatic monthly activity status. The question asks about activity requirements or automatic status, while the candidate only defines the term itself. No relevant evidence provided."
}
```
````

### Repeat 3: binding

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "The candidate section defines 'Sales Level' as levels achieved through cumulative Case Credits but does not address whether maintaining a sales level automatically qualifies someone as active each month. The question asks about the relationship between sales level retention and monthly activity status, which this definition does not answer."
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
  "reason": "The candidate section defines 'Sales Level' as achievement levels based on cumulative Case Credits, but does not address the relationship between maintaining a sales level and automatic monthly activity status. The question asks about activity requirements or automatic qualification, which this definition does not cover."
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
  "reason": "Candidate 1 describes VOLUNTARY termination by written request, not automatic termination due to inactivity or lack of orders. The question asks about automatic termination for non-ordering, which this candidate does not address."
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
  "reason": "Candidate 1 describes voluntary termination by written request, not automatic termination due to inactivity or failure to order. The question asks about automatic termination triggered by one month without orders; this candidate addresses a different trigger (voluntary action). No candidate provided addresses the specific scenario of automatic termination for inactivity."
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
  "reason": "The candidate section addresses voluntary termination initiated by the FBO through a written request. The user's question asks whether automatic termination occurs due to inactivity (no orders for one month), which is a different scenario. The candidate does not address automatic termination triggered by inactivity or lack of orders."
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
  "reason": "The candidate section addresses voluntary termination by written request, not automatic termination due to inactivity or lack of orders. The user's question asks whether failure to order for one month automatically terminates FBO status, which requires a policy section on inactivity-based or automatic termination. The provided candidate does not address automatic termination triggered by non-ordering."
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
  "reason": "Candidate 1 addresses voluntary termination by written request, not automatic termination due to inactivity or lack of orders. The question asks about automatic termination for non-ordering, which is a different scenario. No candidate directly addresses the specific rule about whether one month of no orders triggers automatic FBO termination."
}
```
````

### Repeat 2: ranking

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 addresses voluntary termination by written request, not automatic termination due to inactivity or lack of orders. The question asks about automatic termination for non-ordering, which is a different scenario. No candidate provided directly answers the specific question about automatic FBO termination from one month of inactivity."
}
```
````

### Repeat 2: binding

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "The candidate section addresses voluntary termination by written request, not automatic termination due to inactivity or lack of orders. It does not answer whether an FBO business is automatically terminated for not ordering for one month. No relevant sources were found in the provided candidates."
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
  "reason": "The candidate source addresses voluntary termination by written request, not automatic termination due to inactivity or lack of orders. The user's question asks about automatic termination for non-ordering during one month, which is a different scenario. No source provided addresses the specific trigger of inactivity or order requirements for automatic FBO status termination."
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
  "reason": "Candidate 1 addresses voluntary termination by written request, not automatic termination due to inactivity or lack of orders. The question asks about automatic termination from non-ordering, which is a different scenario. No candidate provided directly answers the specific question about automatic FBO termination for one month of no orders."
}
```
````

### Repeat 3: ranking

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 addresses voluntary termination by written request, not automatic termination due to inactivity or failure to order. The user's question asks whether non-ordering for one month triggers automatic termination, which is a different scenario involving involuntary status loss. No candidate directly answers the specific question about automatic termination for lack of orders."
}
```
````

### Repeat 3: binding

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "The candidate section addresses voluntary termination by written request, not automatic termination for inactivity or lack of orders. The user's question asks about automatic termination due to one month without orders, which is a different scenario. No candidate section directly addresses the automatic termination rule based on inactivity or ordering requirements."
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
  "reason": "The candidate section addresses voluntary termination by written request, not automatic termination due to inactivity or lack of orders. The question asks about automatic termination from one month without ordering, which is a different scenario than the voluntary termination described in the candidate. No source provided directly answers whether non-ordering results in automatic FBO termination."
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
  "reason": "Candidate 1 is about Sales Level definitions and is not related to customer service contact information. No candidates provided contain Canadian customer service telephone number information."
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
  "reason": "Candidate 1 is about sales level definitions and does not contain any customer service telephone number information. No candidate sections provided contain contact information for Canadian customer service."
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
  "reason": "The candidate section provided defines 'Sales Level' and contains no customer service telephone number or contact information for Canada. No sources directly answer the user's question about Canadian customer service contact details."
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
  "reason": "The candidate section provided is a policy definition of 'Sales Level' and does not contain any customer service telephone number information for Canada or any other location. No office directory or contact information is present in the provided candidate."
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
  "reason": "No candidate provides Canadian customer service telephone number. Candidate 1 defines Sales Level, which is unrelated to contact information."
}
```
````

### Repeat 2: ranking

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "No candidate provided contains customer service contact information for Canada. Candidate 1 is a policy definition section unrelated to customer service telephone numbers."
}
```
````

### Repeat 2: binding

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "The candidate section provided defines 'Sales Level' and is not related to Canadian customer service contact information. No relevant source was found to answer the user's question about a Canadian customer service telephone number."
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
  "reason": "The candidate section provided is a policy definition of 'Sales Level' and does not contain any customer service contact information or telephone numbers for Canada. No relevant sources are available to answer this question."
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
  "reason": "No candidates provided contain Canadian customer service telephone number information. Candidate 1 is a policy definition section about sales levels, which is unrelated to customer service contact information."
}
```
````

### Repeat 3: ranking

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 is about Sales Level definitions and does not contain any customer service telephone number information for Canada or any other location."
}
```
````

### Repeat 3: binding

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "The candidate section is a policy definition of 'Sales Level' and does not contain any customer service telephone number or Canada-specific contact information. No sources from the provided candidates address the user's question about Canadian customer service contact details."
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
  "reason": "The candidate section provided defines 'Sales Level' and is unrelated to Canadian customer service contact information. No office_directory or contact information source was provided to answer this question about a Canadian telephone number."
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
  "reason": "The candidate only defines what a Sales Level is; it does not address whether sales rank is retained or lost when ordering stops. A retention or loss rule is needed to answer this question."
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
  "reason": "The candidate defines 'Sales Level' but does not address retention, loss, or the effect of stopping orders on rank maintenance. The question asks about a retention rule; this candidate only provides a definition of what sales levels are."
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
  "reason": "The candidate section defines 'Sales Level' but does not address retention rules, inactivity consequences, or whether sales rank is permanently kept if ordering stops. A direct answer would require a policy section explicitly stating retention or loss conditions based on ordering activity."
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
  "reason": "The provided candidate section defines 'Sales Level' but does not address whether sales rank is retained permanently when ordering stops. The question asks about retention rules upon cessation of ordering activity, which requires a clause about rank maintenance, loss conditions, or activity requirements—not a definition of what sales levels are. No relevant governance section was provided."
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
  "reason": "The candidate defines 'Sales Level' but does not address retention, loss, or the effect of stopping orders on rank maintenance. It is only tangentially related to the question about permanently keeping sales rank."
}
```
````

### Repeat 2: ranking

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "Candidate 1 only defines what a Sales Level is; it does not address retention rules, inactivity consequences, or whether stopping orders affects rank status. The question asks about permanent retention upon stopping orders, which requires a rule about rank loss or retention conditions, not a definition."
}
```
````

### Repeat 2: binding

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "The candidate section defines 'Sales Level' but does not address retention, loss, or permanence of rank upon cessation of ordering. A rule about what happens when an FBO stops ordering is needed to answer this question, and this definition alone does not provide that governing clause."
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
  "reason": "The candidate section defines 'Sales Level' but does not address retention, loss, or permanence of rank when ordering stops. A definition alone does not answer the question about whether stopping orders affects rank retention. Additional policy sections governing rank retention or loss through inactivity would be needed to answer this question."
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
  "reason": "Candidate 1 only defines what a Sales Level is; it does not address whether sales rank is retained or lost when an FBO stops ordering. The question asks about retention rules upon inactivity, which requires a clause about maintenance requirements or loss conditions, not a definition."
}
```
````

### Repeat 3: ranking

correctly withheld unsupported answer

````text
```json
{
  "selected_ranks": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "reason": "The candidate section only defines what a Sales Level is (a rank achieved through cumulative Case Credits), but does not address whether sales ranks are retained or lost when ordering stops. The question asks about retention rules upon inactivity, which requires a clause about retention/loss conditions, not a definition of the rank itself."
}
```
````

### Repeat 3: binding

correctly withheld unsupported answer

````text
```json
{
  "selected_source_ids": [],
  "directly_answers_top_rank": false,
  "top_rank_confidence": 0.0,
  "support": [],
  "reason": "The candidate source defines 'Sales Level' but does not address whether sales rank is retained when ordering stops. The question asks about retention rules upon inactivity, which requires a clause about maintenance requirements, loss conditions, or retention policies - not a definitional section."
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
  "reason": "The candidate section defines 'Sales Level' but does not address retention, loss, or what happens when ordering stops. The question asks about permanent retention of rank upon cessation of ordering, which requires a rule about retention or loss conditions - not a definition of the rank itself."
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
  "top_rank_confidence": 0.95,
  "reason": "Candidate 4 directly states the requirement to be Active: an FBO must have a Total of 4 Active Case Credits in their Home Operating Company during that Month. Candidate 26 repeats this core definition. Candidate 2 mentions the ongoing requirement to 'Be Active every month' but does not explain how to initially become Active."
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
  "reason": "Candidate 1 directly answers the question 'How do I become Active?' by explicitly stating the requirement: an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month to be considered Active. Candidate 2 provides the same core requirement with additional context for Foreign Operating Companies."
}
```
````

### Repeat 1: binding

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "reason": "The user asks how to become Active. Section 4.03(b) directly specifies the requirement: an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month to be considered Active. This is the foundational rule for achieving Active status."
}
```
````

### Repeat 1: combined

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.95,
  "support": [
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in a Foreign Operating Company, he/she must have qualified as Active in the Home Operating Company during the previous Month; or have a Total of 4 Active Case Credits in that Foreign Operating Company during that Month."
    }
  ],
  "reason": "The user asks how to become Active. Section 4.03 directly states the specific requirement: accumulate a total of 4 Active Case Credits in the Home Operating Company during a calendar month. The selected sources provide the complete rule for both home and foreign operating companies."
}
```
````

### Repeat 2: current

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [4, 26, 2],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "reason": "Candidate 4 directly answers how to become Active by stating the specific requirement: an FBO must have a Total of 4 Active Case Credits in their Home Operating Company during that month. Candidate 26 provides the same core definition. Candidate 2 reinforces that being Active is a monthly requirement."
}
```
````

### Repeat 2: ranking

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [1, 2],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.95,
  "reason": "Candidate 1 directly states the requirement to become Active: an FBO must have a Total of 4 Active Case Credits in their Home Operating Company during that month. Candidate 2 provides the same specific requirement as a supporting reference."
}
```
````

### Repeat 2: binding

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "reason": "The question asks how to become Active. Section 4.03(b) directly states the requirement: an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month to be considered Active. This is the governing definition of Active status."
}
```
````

### Repeat 2: combined

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in a Foreign Operating Company, he/she must have qualified as Active in the Home Operating Company during the previous Month; or have a Total of 4 Active Case Credits in that Foreign Operating Company during that Month."
    }
  ],
  "reason": "The user asks how to become Active. Section 4.03 directly states the requirement: an FBO must have a total of 4 Active Case Credits in their Home Operating Company during the month to be considered Active. The second source clarifies the requirement for Foreign Operating Companies as well."
}
```
````

### Repeat 3: current

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [4, 26, 2],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "reason": "Candidate 4 directly states the requirement to become Active: an FBO must have a Total of 4 Active Case Credits in their Home Operating Company during that month. Candidate 26 reinforces this definition. Candidate 2 states the ongoing requirement to 'Be Active every month' but does not define how to initially become Active."
}
```
````

### Repeat 3: ranking

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [1, 2],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.95,
  "reason": "Candidate 1 directly states the requirement to become Active: an FBO must have a Total of 4 Active Case Credits in their Home Operating Company during that month. Candidate 2 provides the same core requirement in more focused form."
}
```
````

### Repeat 3: binding

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    }
  ],
  "reason": "The user asks how to become Active. Section 4.03(b) directly states the requirement: an FBO must have a total of 4 Active Case Credits in their Home Operating Company during that month to be considered Active for the month. This is the primary qualification rule for achieving Active status."
}
```
````

### Repeat 3: combined

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.95,
  "support": [
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in a Foreign Operating Company, he/she must have qualified as Active in the Home Operating Company during the previous Month; or have a Total of 4 Active Case Credits in that Foreign Operating Company during that Month."
    }
  ],
  "reason": "The question asks how to become Active. Section 4.03(b) directly states the specific requirement: an FBO must have a Total of 4 Active Case Credits in their Home Operating Company during that Month to be considered Active. The second source provides the complementary requirement for Foreign Operating Companies."
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
  "top_rank_confidence": 0.95,
  "reason": "Candidate 4 (Section 4.03) directly states the specific requirement to be Active this month: an FBO must have a Total of 4 Active Case Credits in their Home Operating Company during that Month. Candidate 26 provides the same defining rule. Candidate 2 confirms the general requirement to 'Be Active every month' but lacks the specific qualification detail."
}
```
````

### Repeat 1: ranking

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [4, 2, 26],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.95,
  "reason": "Candidate 4 (Section 4.03) directly answers the question by specifying the exact requirement to be Active for a month: an FBO must have a total of 4 Active Case Credits in their Home Operating Company during that month. Candidate 2 confirms the general requirement to 'Be Active every month.' Candidate 26 provides the same specific definition of Active status (4 Active Case Credits). These candidates directly state the prerequisites for monthly activity."
}
```
````

### Repeat 1: binding

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "1f443fe4e4fb28396e527eefbed3aa51ed2340ce3a124b5d30e6cbb6bdec77c0"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.95,
  "support": [
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "1f443fe4e4fb28396e527eefbed3aa51ed2340ce3a124b5d30e6cbb6bdec77c0",
      "quote": "1) Be Active every month."
    }
  ],
  "reason": "The user asks in German what requirements they must fulfill to be active this month. Section 4.03(b) directly answers this with the specific requirement: an FBO must have a total of 4 Active Case Credits in their Home Operating Company during that month. Section 1f443fe clarifies the general requirement to be active every month."
}
```
````

### Repeat 1: combined

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "1f443fe4e4fb28396e527eefbed3aa51ed2340ce3a124b5d30e6cbb6bdec77c0"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.95,
  "support": [
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "1f443fe4e4fb28396e527eefbed3aa51ed2340ce3a124b5d30e6cbb6bdec77c0",
      "quote": "Be Active every month."
    }
  ],
  "reason": "The user asks in German what requirements must be fulfilled to be active this month (Welche Voraussetzungen muss ich erfuellen, um diesen Monat aktiv zu sein?). Section 4.03(b) directly states the specific requirement: an FBO must have a total of 4 Active Case Credits in their
````

### Repeat 2: current

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [4, 26, 2],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.95,
  "reason": "Candidate 4 directly states the requirement to be Active: an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month. Candidate 26 provides the same core definition. Candidate 2 confirms the general requirement to 'Be Active every month.' Together, these establish the specific prerequisite for monthly activity status."
}
```
````

### Repeat 2: ranking

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [4, 26, 2],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "reason": "Candidate 4 section 4.03(b) directly specifies the requirement to be Active: an FBO must have a total of 4 Active Case Credits in their Home Operating Company during that month. Candidate 26 provides the same rule in simpler form. Candidate 2 states the general requirement to 'Be Active every month' but lacks the specific 4 Case Credits detail."
}
```
````

### Repeat 2: binding

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "1f443fe4e4fb28396e527eefbed3aa51ed2340ce3a124b5d30e6cbb6bdec77c0"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.95,
  "support": [
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "1f443fe4e4fb28396e527eefbed3aa51ed2340ce3a124b5d30e6cbb6bdec77c0",
      "quote": "1) Be Active every month."
    }
  ],
  "reason": "The user asks in German what requirements must be fulfilled to be active this month ('um diesen Monat aktiv zu sein'). Section 4.03(b) directly specifies the quantitative requirement: 4 Active Case Credits in the Home Operating Company. Section 4.03(a) establishes that being Active is required
````

### Repeat 2: combined

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_source_ids": [
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "1f443fe4e4fb28396e527eefbed3aa51ed2340ce3a124b5d30e6cbb6bdec77c0"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "1f443fe4e4fb28396e527eefbed3aa51ed2340ce3a124b5d30e6cbb6bdec77c0",
      "quote": "1) Be Active every month."
    }
  ],
  "reason": "The user asks in German for the requirements to be active this month. Section 4.03(b) directly states the specific requirement: an FBO must have 4 Active Case Credits in the home operating company during that month to be considered Active. This is the core qualifying requirement for monthly activity status."
}
```
````

### Repeat 3: current

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [4, 26, 2],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "reason": "Candidate 4 directly states the requirement to be Active: an FBO must have a Total of 4 Active Case Credits in their Home Operating Company during that Month (section 4.03-b). Candidate 26 provides the same core rule. Candidate 2 confirms the general requirement to 'Be Active every month' but lacks the specific Case Credit detail."
}
```
````

### Repeat 3: ranking

decision and governing evidence match; semantic quote review still required

````text
```json
{
  "selected_ranks": [4, 2, 26],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.95,
  "reason": "Candidate 4 directly states the Activity Qualification requirements: an FBO must have 4 Active Case Credits in their Home Operating Company during the month to be considered Active. Candidate 2 reiterates the general requirement to 'Be Active every month.' Candidate 26 provides the specific definition of what constitutes Active status (4 Active Case Credits). Together these directly answer the user's question about the prerequisites to be active this month."
}
```
````

### Repeat 3: binding

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "1f443fe4e4fb28396e527eefbed3aa51ed2340ce3a124b5d30e6cbb6bdec77c0"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "1f443fe4e4fb28396e527eefbed3aa51ed2340ce3a124b5d30e6cbb6bdec77c0",
      "quote": "1) Be Active every month."
    }
  ],
  "reason": "The user asks in German what requirements must be fulfilled to be active this month. Section 4.03(b) directly specifies the core requirement: 4 Active Case Credits in the Home Operating Company. Section 4.03(a) confirms activity qualification is necessary for bonuses, and Section 11.01 reiterates the
````

### Repeat 3: combined

incomplete model response

````text
```json
{
  "selected_source_ids": [
    "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
    "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
    "1f443fe4e4fb28396e527eefbed3aa51ed2340ce3a124b5d30e6cbb6bdec77c0"
  ],
  "directly_answers_top_rank": true,
  "top_rank_confidence": 0.92,
  "support": [
    {
      "source_id": "4ae8240855aeff57bdd3adf8fe15db9397b1ee2f5f757b9d7619ee991290c5af",
      "quote": "To be considered Active for the Month in his/her Home Operating Company, an FBO must have a Total of 4 Active Case Credits in the Home Operating Company during that Month."
    },
    {
      "source_id": "ee0ca0247984fb7aa6b388ec80132662aa195dffa0246ff919d6469c7432266c",
      "quote": "To qualify for Volume and Leadership Bonuses and all Incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued."
    },
    {
      "source_id": "1f443fe4e4fb28396e527eefbed3aa51ed2340ce3a124b5d30e6cbb6bdec77c0",
      "quote": "1) Be Active every month."
    }
  ],
  "reason": "The user asks in German what requirements must be fulfilled to be active this month. Section 4.03(b) directly states the specific requirement: an FBO must have 4 Active Case Credits in the Home Operating Company during that month. Section 4.03(a) confirms Active status is required for bonuses and incentives. Section
````
