# Single-text response experiment results

Date: 2026-09-06

## Decision

Keep as an experimental candidate; do not deploy yet. The segments-only writer passed source-binding and exact displayed-text assembly on 12/12 outputs. The experimental dual-text control passed 0/12: every output differed from its separately generated claim text. This is a structural improvement, not a retrieval, overall correctness, or safety pass rate. The control is an experimental writer, not deployed Current.

## Protocol and results

Six reused cases, two repetitions per arm, 24 completed model calls. No planner, repair call, or threshold change. Full requests, source passages, responses, and manifest are retained in `segments-only-01`. See `SEGMENTS_PROTOCOL.md` for the pre-run protocol.

| Measure | Dual-text control | Segments-only candidate |
| --- | --- | --- |
| Structurally valid | 0/12 | 12/12 |
| Model-call median, seconds | 2.80 | 2.62 |

Timing measures these component calls only, not end-to-end chatbot latency. Small reused sample; no general performance claim.

## Answer inspection

Candidate outputs preserved current-month and home-company conditions; the German-policy outputs retained the personal Case Credit requirement. Bonus eligibility was included when requested and not volunteered for the monthly-only question. These are qualitative observations on six reused cases, not independent legal approval or a held-out semantic grade. German register varied between formal and informal across repeats, so tone consistency remains a review item.

## Local verification

- 1,222 unit tests passed (two existing warnings).
- Targeted lint and whitespace checks passed.
- Graph update unavailable because graphify is not installed.
- Production, deployed configuration, indexes, and caches unchanged.

## Follow-up testing remains open

The prepared fixture contains seven sequences and 21 turns. The existing full-chat comparison runner currently creates a new session for each question, so running it unchanged would not test follow-up memory. Next: connect the isolated conversation recorder to the full-chat runner with separate per-arm, per-sequence sessions and actual delivered-answer history; then run both arms and preserve every question, answer, source, and failure. Do not treat the fixture or local mock tests as completed live follow-up verification.

Country-policy isolation, global sponsoring access, language and country changes, clarification loops, split intent, safety, and cache/session separation remain promotion gates. No runtime integration or release approval is implied by this component experiment.

## All questions and both model outputs

Control text below is the raw rejected draft, never an approved delivered answer. Candidate text is assembled directly from validated segments. Machine-readable files retain the individual segments and support quotes.

### bonus-only — repeat 1

Question: Is being Active required for Volume and Leadership Bonuses and incentives?

Control draft (rejected: Displayed answer differs from ordered claims):

Yes, being Active is required for Volume and Leadership Bonuses and all Incentives. An FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

Candidate (structurally accepted):

Yes, being Active is required for Volume and Leadership Bonuses and all Incentives. To qualify for these bonuses and incentives, an FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

### DE-complete — repeat 1

Question: Was muss ich diesen Monat tun, um in meiner Home Operating Company aktiv zu sein?

Control draft (rejected: Displayed answer differs from ordered claims):

Um in diesem Monat in Ihrer Home Operating Company aktiv zu sein, müssen Sie insgesamt 4 aktive Case-Credits in der Home Operating Company generieren, von denen mindestens eine eine persönliche Case-Credit sein muss.

Candidate (structurally accepted):

Um in diesem Monat in Ihrer Home Operating Company aktiv zu sein, müssen Sie insgesamt 4 aktive Case-Credits in der Home Operating Company generieren, von denen mindestens eine eine persönliche Case-Credit sein muss.

### DE-English-question — repeat 1

Question: What must I do to be Active this month in my Home Operating Company?

Control draft (rejected: Displayed answer differs from ordered claims):

To be Active this month in your Home Operating Company, you must generate a total of 4 active Case-Credits in your Home Operating Company during this month, of which at least one must be a personal Case-Credit.

Candidate (structurally accepted):

To be Active this month in your Home Operating Company, you must generate a total of 4 active Case-Credits in your Home Operating Company during this month, of which at least one must be a personal Case-Credit.

### mixed-claim — repeat 1

Question: What must I do to be Active this month in my Home Operating Company?

Control draft (rejected: Displayed answer differs from ordered claims):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month.

Candidate (structurally accepted):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month.

### mixed-requested — repeat 1

Question: What must I do to be Active this month in my Home Operating Company? Is being Active also required for Volume and Leadership Bonuses and incentives?

Control draft (rejected: Displayed answer differs from ordered claims):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month. Yes, being Active is also required for Volume and Leadership Bonuses and all Incentives—you must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

Candidate (structurally accepted):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month. Yes, being Active is required for Volume and Leadership Bonuses and all Incentives. You must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

### necessary-timing — repeat 1

Question: Are 4 Active Case Credits from last month enough to be Active this month in my Home Operating Company?

Control draft (rejected: Displayed answer differs from ordered claims):

No. To be considered Active this month in your Home Operating Company, you must have a total of 4 Active Case Credits in your Home Operating Company during this month. Active Case Credits from last month do not carry forward to qualify you as Active this month.

Candidate (structurally accepted):

No, 4 Active Case Credits from last month are not enough to be Active this month in your Home Operating Company. To be considered Active for the month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that current month.

### bonus-only — repeat 2

Question: Is being Active required for Volume and Leadership Bonuses and incentives?

Control draft (rejected: Displayed answer differs from ordered claims):

Yes, being Active is required for Volume and Leadership Bonuses and all Incentives. An FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

Candidate (structurally accepted):

Yes, being Active is required for Volume and Leadership Bonuses and all Incentives. An FBO must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

### DE-complete — repeat 2

Question: Was muss ich diesen Monat tun, um in meiner Home Operating Company aktiv zu sein?

Control draft (rejected: Displayed answer differs from ordered claims):

Um diesen Monat in Ihrer Home Operating Company als aktiv zu gelten, müssen Sie insgesamt 4 aktive Case-Credits in der Home Operating Company generieren, von denen mindestens einer eine persönliche Case-Credit sein muss.

Candidate (structurally accepted):

Um diesen Monat in deiner Home Operating Company aktiv zu sein, musst du insgesamt 4 aktive Case-Credits in der Home Operating Company generieren, von denen mindestens eine eine persönliche Case-Credit sein muss.

### DE-English-question — repeat 2

Question: What must I do to be Active this month in my Home Operating Company?

Control draft (rejected: Displayed answer differs from ordered claims):

To be Active this month in your Home Operating Company, you must generate a total of 4 active Case-Credits in your Home Operating Company during this month, of which at least one must be a personal Case-Credit.

Candidate (structurally accepted):

To be Active this month in your Home Operating Company, you must generate a total of 4 active Case-Credits in your Home Operating Company during this month, of which at least one must be a personal Case-Credit.

### mixed-claim — repeat 2

Question: What must I do to be Active this month in my Home Operating Company?

Control draft (rejected: Displayed answer differs from ordered claims):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month.

Candidate (structurally accepted):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month.

### mixed-requested — repeat 2

Question: What must I do to be Active this month in my Home Operating Company? Is being Active also required for Volume and Leadership Bonuses and incentives?

Control draft (rejected: Displayed answer differs from ordered claims):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month. Yes, being Active is required for Volume and Leadership Bonuses and all Incentives—you must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

Candidate (structurally accepted):

To be Active this month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that month. Yes, being Active is required for Volume and Leadership Bonuses and all Incentives. To qualify for these bonuses and incentives, you must be Active and meet all other requirements of the Marketing Plan during the calendar month in which the bonuses were accrued.

### necessary-timing — repeat 2

Question: Are 4 Active Case Credits from last month enough to be Active this month in my Home Operating Company?

Control draft (rejected: Displayed answer differs from ordered claims):

No, 4 Active Case Credits from last month are not enough to be Active this month in your Home Operating Company. To be considered Active for the current month in your Home Operating Company, you must have a total of 4 Active Case Credits in the Home Operating Company during that current month.

Candidate (structurally accepted):

No, 4 Active Case Credits from last month are not enough to be Active this month in your Home Operating Company. To be considered Active for the current month in your Home Operating Company, you must have a Total of 4 Active Case Credits in the Home Operating Company during that current month.

