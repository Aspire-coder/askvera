# Phase 3 Lane 3: contacts, suggestions, personal account

Write scope (per `docs/conversation-quality/phase3/CX_LANES.md`):
`app/response/contact_completion.py` (extended), `app/response/suggestions.py`
(new), `app/response/personal_account.py` (new),
`config/personal_account_vocabulary.py` (new),
`tests/unit/test_cx_contacts_suggestions.py`,
`tests/unit/test_cx_personal_account.py`.

All three entry points are pure functions: no I/O, no model calls, no import
of `app.orchestrator.chat_orchestrator`. The coordinator wires them into
`_secure_and_complete_response` (the same method that already runs
`_apply_support_contact_supplement`); this doc documents the recommended
hook sites, not a code change to that file (single-writer rule).

## APIs

### `contact_escalation` (`app/response/contact_completion.py`)

```python
def contact_escalation(
    outcome: ConversationOutcome,
    *,
    country: str,
    language: str,
    answer_text: str,
    render: Callable[..., str],
) -> str | None
```

Deviates from the brief's literal signature by one keyword argument,
`render`. The brief's own "copy is data" rule requires every user-visible
sentence to come from Lane 4's `render(key, language, **placeholders) -> str`
callable, and this function's whole job is to produce one - the listed
signature `(outcome, *, country, language, answer_text) -> str | None` had
no way to reach Lane 4's copy without either importing
`config/conversation_routes.json` directly (a second reader of Lane 4's
data, against the "Lane 4 is the only writer" rule) or inlining English
text (explicitly forbidden). `render` closes that gap the same way the
brief's own "Copy is data" paragraph describes injecting it.

Renders the `contact_offer` key with `{contact}` filled from
`app.response.quality.contact_for_country(country)` (phone preferred over
website, same order `build_support_contact_supplement` already uses).
Fires only for `evidence_missing`, `personal_account`,
`dependency_unavailable`, `partial_answer` (only when
`outcome.fields_unsupported` is non-empty), and `cross_market_policy`
(using the SESSION country passed in, never a country named in the
question). Returns `None` for every other outcome kind (including
`safety_refusal` and `clarification`), when `country` has no reviewed
public contact at all, or when the contact is already present in
`answer_text` - checked two ways: a literal substring match against every
configured contact value (language-independent - catches a contact the
orchestrator's own `_apply_support_contact_supplement` already appended
earlier this turn, in any language), and the existing
`recommends_contact_in_language` (catches a recommendation sentence with no
literal contact value in it, in the nine languages that function already
covers).

### `suggest_follow_ups` (`app/response/suggestions.py`)

```python
def suggest_follow_ups(
    outcome: ConversationOutcome,
    *,
    language: str,
    country: str,
    topic_supported: Callable[[str, str], bool],
) -> list[str]
```

Same kind of deviation, for the same reason but on the input side: the
brief names the parameter `supported_topics` in the signature line but then
specifies "Determine 'supported' through an injected predicate
`topic_supported(topic, country) -> bool`" - the two are inconsistent, and
this module follows the fully-specified predicate form since it is what
lets the coordinator back "supported" with a real, existing signal instead
of this module inventing one.

Returns at most 2 keys from the closed set `suggest_topic_delivery_cost`,
`suggest_topic_payment_methods`, `suggest_topic_contact`,
`suggest_topic_returns`, in that fixed priority order (see
`suggestions.py`'s `_SUGGEST_TOPICS` for the rationale). Never returns the
topic the reader just asked about (matched against
`outcome.fields_requested` via `_TOPIC_FIELD_ALIASES`, using the same
canonical directory-field keys `app/response/outcome.py` /
`utils/directory_fields.py` already use - `phone`, `order_phone`, `email`,
`website`, `address`, `business_hours`, `fax` for `contact`;
`delivery_cost`/`delivery_time` for `delivery_cost`;
`payment_methods` for `payment_methods`; `returns` has no canonical
directory-field key, so it is never excluded this way). Never suggests for
`safety_refusal` or `dependency_unavailable`. `language` is accepted for
signature symmetry but unused today.

### `detect_personal_account_request` (`app/response/personal_account.py`)

```python
def detect_personal_account_request(question: str, language: str) -> bool
```

Delegates to the new closed vocabulary in
`config/personal_account_vocabulary.py` (12 languages: da, de, en, es, fi,
fr, it, nl, no, ru, sr, sv - the CX route-copy set). Matches five narrow
lookup shapes (location/status, completed-event confirmation, current-value
lookup, earned-amount lookup, identifier reference), each requiring BOTH a
first-person possessive and a concrete account-object noun. Deliberately
does NOT match a calculation question ("How is my bonus calculated?"), a
future-timing policy question ("When will my commission be paid?"), a
capability question ("Can I return my order?"), or a general fact question
using "my" ("What are the payment methods for my order?") - see
`config/personal_account_vocabulary.py`'s module docstring for the full
positive/negative shape table and the per-language confidence notes.

**This is not a refusal.** A question matching this shape still gets the
normal policy/evidence answer when the pipeline has one; this function is
never consulted by retrieval, evidence approval or the prompt. The
coordinator ADDS the `personal_account_limit` note (rendered via Lane 4's
`render`) plus a `contact_escalation` call with
`OutcomeKind.PERSONAL_ACCOUNT` alongside whatever answer already exists -
never in place of it.

## Recommended hook sites (coordinator wiring, not made here)

In `AIOrchestrator._secure_and_complete_response`
(`app/orchestrator/chat_orchestrator.py`), after the existing
`_apply_support_contact_supplement` step and after `derive_outcome` (Lane 1)
has produced this turn's `ConversationOutcome`:

1. Call `detect_personal_account_request(user_question, language)`. When
   `True` and `outcome.kind` is not already `personal_account`, treat the
   outcome the same way `personal_account` is otherwise derived (or simply
   OR this signal into the derivation Lane 1 already performs before
   `contact_escalation` runs) - Lane 1 owns exactly how `OutcomeKind` values
   are finalized; this lane only supplies the detector.
2. Call `contact_escalation(outcome, country=session_country, language=language, answer_text=chat_response.answer, render=cx_render.render)`.
   When it returns a string, append it to the answer the same way the
   existing support-contact supplement is appended (blank line separator),
   or attach it as a distinct metadata field for the UI to render as a
   separate element - either is compatible with this function's contract,
   since it already returns fully-rendered text, not a raw block to merge
   field-by-field.
3. Call `suggest_follow_ups(outcome, language=language, country=session_country, topic_supported=<signal>)`
   and attach the returned keys to `ChatResponse.suggestions` (rendered
   through Lane 4's `render` the same way any other key is, at the point
   the response is finalized for the client).

## Recommended `topic_supported` signal

`config/markets.json` was investigated first (it is the obvious existing
per-market config) and rejected: it carries market/language enablement and
UI feature flags (`defaultFeatures`: `feedback`, `sources`, `productCards`),
not per-topic evidence coverage - no field there distinguishes a market
with an approved delivery-cost policy from one without.

The recommended signal instead is **approved directory-record field
presence for the market**, the same mechanism `build_support_contact_supplement`
and `_label_canonical_field` (`utils/directory_fields.py`) already use to
decide whether a record backs a phone/email/website claim: for
`payment_methods` and `delivery_cost`, check whether the market's approved
directory record (the same "selected applicable record" the coordinator
already resolves for `_apply_support_contact_supplement`) carries a
non-empty value under `_label_canonical_field(label) in
("payment_methods", "delivery_cost")`. For `contact`, reuse the same check
`_apply_support_contact_supplement` already performs to decide whether a
support-contact block exists at all (a non-`None`
`build_support_contact_supplement` result). For `returns`, no directory
field exists in this repository today - the coordinator should treat
`returns` as supported only where a market-scoped returns-policy document
is confirmed present in the corpus (a corpus/config signal Lane 3 does not
own and has not invented one for), or otherwise pass a predicate that
always returns `False` for `returns` until that signal exists, which
`suggest_follow_ups` already handles safely (it simply never suggests a
topic the predicate declines).

## Test summary

- `tests/unit/test_cx_contacts_suggestions.py`: 26 tests -
  `contact_escalation` positive/negative outcome-kind coverage, the
  partial-answer "only with a real gap" rule, dedup against both a literal
  contact substring and a multilingual recommendation sentence, the
  cross-market "session contact, not the named market's" rule, a missing-
  contact market returning `None`, phone-then-website fallback; plus
  `suggest_follow_ups` priority ordering, the "never the topic just asked"
  rule (directory-field and contact-field cases), unsupported-topic
  filtering, excluded-kind filtering, predicate argument-passing, and
  determinism.
- `tests/unit/test_cx_personal_account.py`: 190 tests - one positive per
  lookup shape in English, positives in all 11 non-English route
  languages, the four negative shapes named in the brief across en/es/fr/de
  plus a no-possessive Russian negative, an unrecognised-language negative,
  empty/`None` input, region-tagged language-code normalization (`fr-FR`),
  the S1/F2/F3 rate-and-need and time-marker probes, and Fable's F2-A/F2-B
  re-review probes below.

Fable's re-review of the F2/F3 fix (2026-09-19, both low priority) found
two more gaps, now fixed and covered by
`test_fable_f2a_extended_veto_probes_are_not_personal_account` and
`test_fable_f2b_for_the_month_or_week_is_a_time_marker_not_purpose`:

- **F2-A** - the veto word list was missing "quota"/"to keep", and the F3
  time-marker shape had no veto at all, so a trailing role/conditional/
  general/policy/calculated clause ("if I reach Manager", "as a Supervisor
  in general", "under the policy", "how is it calculated") still triggered
  the note. Fixed by extending the veto list identically on both shapes,
  in all languages where each shape exists, and by confining every veto
  lookahead to `[^.!?]{0,40}?` (clause-bounded, not sentence-unbounded) so
  a second sentence in a multi-sentence message can no longer leak a veto
  word into an earlier, unrelated lookup.
- **F2-B** - the "for the ..." veto (and its es/fr/it/nl/de generic-
  preposition equivalents) was too broad and wrongly vetoed a genuine
  time-scoped lookup, "What is my volume for the month?". Fixed with a
  negative lookahead excluding "month"/"week" (and per-language
  equivalents) immediately after "for the"/"para la"/"pour la"/"per
  la"/"voor de"/"für die"; the other six languages use a rule-specific
  phrase and never had this clash.

An independent review (2026-09-22, medium) found that the F2-A veto list
itself had been written as bare conjunctions/relative pronouns in several
languages instead of specific phrases: English `if\s+i` (with no verb
requirement), Spanish `si|como`, Italian `se|come`, German/Dutch `als`,
Swedish/Danish/Norwegian `som`, Finnish `jos`, Russian `как|если\s+я`,
Serbian `ако`/`као`. Each of these is an ordinary word in everyday use --
Nordic `som` is the everyday relative pronoun ("that/which"), Spanish
`como`/Italian `come`/Russian `как` are the everyday word for "how" -- so
any genuine account lookup that happened to contain one of them anywhere
in the sentence lost the personal-account note. Reproduced (and fixed) in
all 12 languages, covered by
`test_bare_conjunction_veto_no_longer_swallows_genuine_lookups`:

| language | lost the note before the fix |
| --- | --- |
| sv | "Vad är mitt saldo som jag har nu?" |
| da | "Hvad er min saldo som jeg har nu?" |
| no | "Hva er min saldo som jeg har nå?" |
| ru | "Какой мой баланс, как я могу его проверить?" |
| es | "¿Cuál es mi saldo y como puedo verlo?" |
| it | "Qual è il mio saldo e come posso vederlo?" |
| nl | "Wat is mijn saldo als ik nu inlog?" |
| en | "What is my commission this month, if I may ask?" |
| de | "Wie hoch ist mein Kontostand, wenn ich mich einlogge?" |
| fr | "Quel est mon solde si je le vérifie maintenant?" |
| fi | "Mikä on saldoni, jos kirjaudun sisään?" |
| sr | "Колико је моје стање, као што сад имам?" |

Fix: every conditional/role veto now requires a specific phrase ending in
an actual rank word, drawn from a small closed per-language rank-title
list (manager, supervisor, assistant supervisor, senior supervisor,
director, and their per-language equivalents -- no existing rank
vocabulary was found elsewhere in the repository to reuse, so this list is
closed and inlined per language, matching this module's existing
discipline): English "if I reach/qualify/become/hit/am `<rank>`" and "as
a/an `<rank>`"; German "wenn ich `<rank>` werde" and "als `<rank>`";
Spanish "si llego a/si alcanzo `<rank>`" and "como `<rank>`"; Italian "se
divento `<rank>`" and "come `<rank>`"; Dutch "als ik `<rank>` word" and
"als `<rank>`"; Swedish "om jag blir `<rank>`" and "som `<rank>`";
Danish/Norwegian "hvis jeg bliver/blir `<rank>`" and "som `<rank>`";
Finnish "jos minusta tulee `<rank>`"; Russian "если я стан(у/ет) `<rank>`"
and "как (это) рассчитывается" (the bare "как" veto was folded into this
specific "how is it calculated" phrase, alongside the pre-existing
standalone "рассчитывается" veto, kept unchanged); Serbian "ако
постан(ем/е) `<rank>`" and "као `<rank>`". French's `si\s+je`/`en\s+tant\s+que`
vetoes were tightened the same way ("si je deviens/atteins `<rank>`", "en
tant que `<rank>`") even though French was not one of the languages the
reviewer reproduced the defect in, since every fix in this module must
generalize across languages rather than patch only the reported ones.
Every existing F2-A role/conditional negative (e.g. "What is my commission
this month if I reach Manager?", "Wie hoch ist mein Bonus als
Supervisor?") stays vetoed after the narrowing -- see
`test_bare_conjunction_fix_keeps_existing_policy_negatives` and the
pre-existing `test_fable_f2a_extended_veto_probes_are_not_personal_account`.

Fable's re-review of the bare-conjunction fix (2026-09-22) found the new
rank-word requirement itself too NARROW: 36/48 role/conditional probes
wrongly kept the note because the rank word or its surrounding verb form
wasn't covered. Three causes, all fixed and covered by
`test_fable_re_review_role_conditional_probes_are_not_personal_account`
(38 probes across all three causes, all 12 languages) and
`test_fable_re_review_keeps_restored_lookups_matching` (the 12 restored
lookups, re-asserted):

1. **Missing brand rank names.** The local rank lists never included the
   brand's own English rank names (Manager, Supervisor, Soaring Manager,
   Sapphire Manager, Diamond Manager, Diamond Sapphire Manager, Double/
   Triple Diamond, Diamond Director, Senior Diamond Director, Crown, Crown
   Ambassador), which route-language markets use untranslated too ("Vad
   är min provision denna månad om jag blir Manager?", "Hvad er min
   provision … som Manager?"). No existing rank vocabulary was found
   elsewhere in the repository to reuse, so one shared closed fragment (a
   repeatable prefix-modifier group -- assistant/senior/soaring/sapphire/
   diamond/double/triple -- before a closed core-noun group -- manager/
   supervisor/director/diamond/crown -- with an optional trailing
   "ambassador") was added to every language's rank alternation instead of
   a separate per-language brand-rank list.
2. **Only one verb/copula form per language.** en covered `reach|qualify|
   become|hit|am` but missed "qualify AS", "get promoted to", "reach THE
   ... LEVEL", and "were"; de missed the copula "bin" ("wenn ich Manager
   bin"); es missed "soy"/"me convierto en"; fi missed "pääsen ...iksi";
   ru missed "буду" and the bare "как <rank>" role marker; sr missed
   "буде". Fixed by adding the missing forms per language.
3. **No feminine/inflected rank forms.** "als Managerin", "come
   Supervisora", "en tant que Superviseure" fell outside every exact-string
   rank alternative. Fixed by appending `\w*` to every rank stem (Italian's
   and Spanish's "supervisor" stems were shortened to their common root so
   the suffix covers both masculine and feminine forms).

A rank word inside the OBJECT noun phrase ("Has my Manager bonus been
paid?") is unaffected either way -- that shape requires the object noun
immediately after the possessive, so a rank word between them already
fails to match the shape at all, independent of this veto (verified
unchanged before/after: both `False`, for the pre-existing, unrelated
reason, not a regression from this fix).

| set | before (fable4) | after (fable5) |
| --- | --- | --- |
| Fable-style role/conditional probes (38, must be vetoed) | 11/38 | 38/38 |
| Restored genuine lookups (12, must keep the note) | 12/12 | 12/12 |
| Rank-in-object-noun probes (3, unaffected either way) | 0/3 | 0/3 |

## Run results

- `tests/unit/test_cx_personal_account.py`: 246 passed
- `tests/unit/test_cx_*.py` + `tests/conversation` + `tests/conversation_pack/cx` (full run): 1067 passed, 9 xfailed
- `flake8` on `config/personal_account_vocabulary.py` and
  `tests/unit/test_cx_personal_account.py`: clean
- `git diff --check`: clean
