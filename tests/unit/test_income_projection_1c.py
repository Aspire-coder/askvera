"""Unit coverage for step 1c of the income-projection detector.

Step 2 (a separate branch) exempts the verbatim company income disclaimer
("Forever makes no guarantees regarding income or success.") from
IncomeClaimPolicy. Its review found earnings projections that the detector
in app/risk/policies/income_projection.py itself never caught -- on main
they are refused only because the disclaimer's "guarantee" word happens to
be present, so each is ALLOWED today in any answer without the disclaimer.
Step 1c makes the detector catch them (generated answers only, as before):

  P10  an amount with NO currency anchor (no symbol, currency word or code)
       followed directly by a period phrase, in an earner / estimate shape:
       "Most Managers make 5,000 a month", "Active FBOs typically earn 1,500
       per month", "you'll be earning 900 a month within a year", "an average
       of 2 000 per month" -- also 1.500 / 1 500 / 1'500, "5 mil", "k",
       spelled amounts ("two thousand a month", "cinq mille par mois",
       "funftausend pro Monat") and all 12 languages' period phrases.
  P11  a percentage return / yield / interest on money or an investment over
       a period ("Expect a 30% return every month", "ROI of 50% a year",
       "rendement de 30 % par mois"), money that doubles / triples ("double
       your money every year", "Ihr Geld verdoppelt sich alle sechs Monate"),
       or income that grows N% per period ("your income grows 10% every
       month").
  P12  (optional item 3) a certainty-marked promise that people make / earn
       money with no figure ("Everyone on my team makes money", "I promise
       you will earn money", "You will make money with us"; en/fr/es/de/it).

Precision rests on adjacency (a period phrase RIGHT AFTER the figure -- "4
CC a month", "25 orders per month", "2 times a week", "18 months" and
"1.01(d)" never have that), on the existing RULECTX / _PROGRAM / _RULE1B /
report / negation / subordinate guards, and on a return-noun vocabulary that
bonus rates ("Personal Bonus of 5%"), discounts, the retail margin and
product-return / refund rules never use.

tests/fixtures/income_projection_1c_cases.json holds the dev and held-out
projections (each with the rule id the detector returns), the compliant
hard negatives (all 12 languages), the documented step-1 compliance calls
that keep firing on their pre-1c rule, and the two step-2 closure sentences.

Everything here is local; sockets and boto3 clients raise if used.
"""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path

import pytest

from app.risk.models import RiskContext
from app.risk.policies import IncomeClaimPolicy, IncomeProjectionPolicy
from app.risk.policies.income_projection import detect_earnings_projection

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _refuse(*_: object, **__: object):
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


def _load_1c_cases():
    with open(FIXTURES / "income_projection_1c_cases.json", encoding="utf-8") as handle:
        return json.load(handle)


_1C_CASES = _load_1c_cases()
_1C_MUST_REFUSE = _1C_CASES["must_refuse"]
_1C_MUST_NOT_FIRE = _1C_CASES["must_not_fire"]
_1C_STAYS_REFUSED = _1C_CASES["stays_refused"]
_1C_STEP2_CLOSURE = _1C_CASES["step2_closure"]
_DISCLAIMER_PREFIX = _1C_CASES["disclaimer_prefix"]
_LANGS = ["en", "fr", "es", "it", "de", "nl", "sv", "da", "no", "fi", "ru", "sr"]


def _case_id(case: dict) -> str:
    return case.get("id") or case.get("text", "")[:40]


# --- (a) recall: dev + held-out projections, alone and after the disclaimer ------------------------------------

@pytest.mark.parametrize("case", _1C_MUST_REFUSE, ids=[_case_id(c) for c in _1C_MUST_REFUSE])
def test_1c_must_refuse_cases_fire(case: dict) -> None:
    hit = detect_earnings_projection(case["text"], case.get("lang"))
    assert hit is not None, f"expected a match for step-1c case {case.get('id')!r}, got no match"
    assert hit[0] == case["rule"], f"expected rule {case['rule']!r}, got {hit[0]!r} for {case.get('id')!r}"


@pytest.mark.parametrize("case", _1C_MUST_REFUSE, ids=[_case_id(c) for c in _1C_MUST_REFUSE])
def test_1c_must_refuse_cases_fire_after_the_income_disclaimer(case: dict) -> None:
    """The disclaimer sentence before the projection changes nothing at the detector level (step 2's exemption
    lives in IncomeClaimPolicy, not here)."""
    hit = detect_earnings_projection(_DISCLAIMER_PREFIX + case["text"], case.get("lang"))
    assert hit is not None and hit[0] == case["rule"], f"{case.get('id')!r} after the disclaimer: {hit!r}"


def test_1c_fixture_covers_every_language_for_items_1_and_2() -> None:
    for item in (1, 2):
        langs = {c["lang"] for c in _1C_MUST_REFUSE if c["item"] == item}
        assert set(_LANGS) <= langs, f"item {item} missing languages {set(_LANGS) - langs}"


# --- (b) precision: compliant sentences of the same shapes in all 12 languages ---------------------------------

@pytest.mark.parametrize("case", _1C_MUST_NOT_FIRE, ids=[_case_id(c) for c in _1C_MUST_NOT_FIRE])
def test_1c_hard_negative_cases_do_not_fire(case: dict) -> None:
    hit = detect_earnings_projection(case["text"], case.get("lang"))
    assert hit is None, f"expected no match for step-1c hard-negative case {case.get('id')!r}, got {hit!r}"


@pytest.mark.parametrize("case", _1C_STAYS_REFUSED, ids=[_case_id(c) for c in _1C_STAYS_REFUSED])
def test_1c_known_compliance_calls_stay_refused_on_their_existing_rule(case: dict) -> None:
    """The worked bonus-maths example ("you earn 8% on a $200 order, which is $16") and "Qualifying Managers can
    earn up to $400 per month" are documented step-1 calls: they were refused before 1c (P1) and still are, on the
    same rule -- 1c adds rules after the existing ones, so no existing hit changes its rule id."""
    hit = detect_earnings_projection(case["text"], case.get("lang"))
    assert hit is not None and hit[0] == case["rule"], f"{case.get('id')!r}: {hit!r}"


@pytest.mark.parametrize(
    "text",
    [
        "An active FBO needs 4 CC a month, of which at least 1 CC is personal.",
        "You must place a minimum of 2 active CC per month to qualify for the bonus.",
        "FBOs earn a Personal Bonus of 5% on their own orders.",
        "Preferred Customers get a 5% discount, FBOs a 35% discount off retail.",
        "The Leadership Bonus is 6%, 3% and 2% on the first, second and third generation.",
        "A 5% volume rebate each month is paid on personal orders.",
        "Retail profit is 43% on the suggested retail price.",
        "Returned products are refunded at 100% of the purchase price within 30 days.",
        "The Forever2Drive incentive pays up to $400 per month for a qualifying vehicle.",
        "Managers can earn up to 400 per month under Forever2Drive.",
        "You have up to 18 months to requalify as Manager.",
        "A minimum of 25 orders per month is required for the retail programme.",
        "Most FBOs typically sponsor 2 new people a month.",
        "Orders are shipped 2 times a week and take up to 5 days.",
        "See section 1.01(d) and 4.03(b) of the Company Policy; call 0800 123 4567.",
        "The policy was updated in 2026 and applies from 1 July 2026.",
        "You get 12 monthly bonus statements a year.",
        "FBOs earn money through retail sales and bonuses as described in the Marketing Plan.",
        "You can earn money by selling the products to retail customers.",
        "Forever does not guarantee that you will make money.",
        "Forever makes no guarantees regarding income or success.",
        "FBOs may not claim that Managers make 5,000 a month.",
        "It is prohibited to say that you will see a 30% return every month.",
        "Statements such as \"double your money every year\" are misleading and banned.",
        "If you make 5,000 a month you must file a tax return.",
        "FBOs who make 5,000 a month receive a 1099.",
        "Interest of 2% per month is charged on overdue invoices.",
        "Returns of 30% a month are a classic sign of a fraudulent scheme, and Forever offers nothing of the kind.",
    ],
)
def test_1c_policy_text_shapes_do_not_fire(text: str) -> None:
    """Forever's own rule text: bonus rates, Case-Credit thresholds, discounts, the retail margin, refund rules, the
    Forever2Drive cap, durations, order minimums, counts per period, dates, section and phone numbers, and the
    prohibition / negation / condition forms of the new shapes."""
    assert detect_earnings_projection(text, "en") is None


# --- (c) step-2 closure: the reviewer's two sentences, detector and policy level --------------------------------

def _context(message: str, *, is_generated_answer: bool, allow_claim_topics: bool = False, language: str = "en") -> RiskContext:
    return RiskContext(
        user_message=message,
        country="US",
        language=language,
        role="new_prospect",
        correlation_id="test-correlation",
        allow_claim_topics=allow_claim_topics,
        is_generated_answer=is_generated_answer,
    )


@pytest.mark.parametrize("case", _1C_STEP2_CLOSURE, ids=[_case_id(c) for c in _1C_STEP2_CLOSURE])
def test_step2_closure_sentences_are_detected_alone_and_after_the_disclaimer(case: dict) -> None:
    alone = detect_earnings_projection(case["text"], case["lang"])
    after = detect_earnings_projection(_DISCLAIMER_PREFIX + case["text"], case["lang"])
    assert alone is not None and alone[0] == case["rule"], alone
    assert after is not None and after[0] == case["rule"], after


@pytest.mark.parametrize("case", _1C_STEP2_CLOSURE, ids=[_case_id(c) for c in _1C_STEP2_CLOSURE])
def test_step2_closure_sentences_are_refused_by_income_projection_policy(case: dict) -> None:
    """Alone: IncomeClaimPolicy does not refuse the sentence (no guarantee word), so the refusal is this policy's own.
    After the disclaimer: on this branch IncomeClaimPolicy still refuses the disclaimer's "guarantee" word, so the
    projection policy defers when allow_claim_topics is False (no duplicate finding) and runs its own detector when
    allow_claim_topics is True -- and then refuses on the projection itself, which is what step 2 needs."""
    policy = IncomeProjectionPolicy()
    alone = _context(case["text"], is_generated_answer=True)
    assert IncomeClaimPolicy().evaluate(alone) == []
    assert [i.code for i in policy.evaluate(alone)] == ["INCOME_PROJECTION_RISK"]
    with_disclaimer = _context(_DISCLAIMER_PREFIX + case["text"], is_generated_answer=True)
    if IncomeClaimPolicy().evaluate(with_disclaimer):
        assert policy.evaluate(with_disclaimer) == []  # deferral, exactly as before 1c
    else:
        assert [i.code for i in policy.evaluate(with_disclaimer)] == ["INCOME_PROJECTION_RISK"]
    forgiven = _context(_DISCLAIMER_PREFIX + case["text"], is_generated_answer=True, allow_claim_topics=True)
    assert [i.code for i in policy.evaluate(forgiven)] == ["INCOME_PROJECTION_RISK"]


@pytest.mark.parametrize("case", _1C_STEP2_CLOSURE + _1C_MUST_REFUSE[:12], ids=[_case_id(c) for c in _1C_STEP2_CLOSURE + _1C_MUST_REFUSE[:12]])
def test_1c_shapes_never_touch_the_user_input_pass(case: dict) -> None:
    """The detector only runs when is_generated_answer is True: a user typing any of these is not refused."""
    assert IncomeProjectionPolicy().evaluate(_context(case["text"], is_generated_answer=False, language=case["lang"])) == []


# --- (e) step-1c review fixes (R1/R2/A1/A2/A4/A5) ------------------------------------------------------------

@pytest.mark.parametrize(
    "lang, text",
    [
        # R1: an estimate next to a bare figure with nobody earning it (rent, costs, spending) is not a projection
        ("en", "The rent for a small office is about 1,000 a month."),
        ("en", "Electricity for the shop runs roughly 150 a month."),
        ("en", "Insurance is approximately 500 a year for a home-based business."),
        ("en", "Approximately 2,000 per year is spent on samples by an average Manager."),
        ("en", "Managers' annual training budget is about 1,500 a year."),
        ("en", "Around 1,000 a month goes on advertising for most small businesses."),
        ("de", "Die Miete beträgt etwa 1.000 im Monat."),
        ("de", "Ich gebe etwa 100 im Monat für Produkte aus."),
        ("de", "Ein Manager gibt ungefähr 500 im Monat für Muster aus."),
        ("fr", "Le loyer est d'environ 1 000 par mois."),
        ("es", "El alquiler es de unos 1.000 al mes."),
        ("it", "L'affitto è di circa 1.000 al mese."),
        ("nl", "Ik geef ongeveer 100 per maand uit aan producten."),
        ("sv", "Jag lägger ungefär 1 000 i månaden på produkter."),
        ("da", "Jeg bruger cirka 1.000 om måneden på produkter."),
        ("no", "Jeg bruker omtrent 1 000 i måneden på produkter."),
        ("fi", "Käytän noin 100 kuukaudessa tuotteisiin."),
        ("ru", "Я трачу около 10 000 в месяц на продукты."),
        ("sr", "Kirija je oko 50.000 mesečno."),
        # R2: "every FBO / everyone earns money (from sales)" explains the Marketing Plan; no team scope = no promise
        ("en", "Every FBO earns money."),
        ("en", "Every FBO earns money from product sales and from bonuses."),
        ("en", "Every FBO earns money only from actual product sales."),
        ("en", "Everyone earns money from sales."),
        ("en", "All of our FBOs earn money from their own sales, not from recruiting."),
        ("en", "Everyone who joins earns money only from what they sell."),
        ("fr", "Tout le monde chez Forever gagne de l'argent uniquement grâce aux ventes."),
        ("es", "Todos los FBO ganan dinero únicamente con las ventas al detalle."),
        ("de", "Jeder FBO verdient Geld ausschließlich durch Produktverkäufe."),
        ("it", "Tutti gli FBO guadagnano soldi soltanto dalle vendite."),
        # A1: interest / yield that is a late-payment, statutory, bank, savings, deposit or bond rate
        ("en", "Statutory interest of 2% a month applies to overdue balances."),
        ("en", "Interest at 2% per month applies to late payments."),
        ("en", "Overdue invoices bear interest of 1.5% a month."),
        ("en", "Compare this with a bank account paying 2% interest per year."),
        ("en", "A bank deposit yields about 2% a year; Forever pays no interest."),
        ("en", "Bank savings return 3% a year at best."),
        ("en", "Government bonds yield 4% per year."),
        ("fr", "Les intérêts de retard sont de 1,5 % par mois."),
        ("es", "Los intereses de demora son del 1,5 % mensual."),
        ("it", "Sulle fatture scadute si applicano interessi dell'1,5% al mese."),
        ("de", "Verzugszinsen von 1,5 % pro Monat fallen auf überfällige Rechnungen an."),
        ("nl", "Rente op een spaarrekening is 2% per jaar; Forever is geen belegging."),
        ("sv", "Dröjsmålsränta på 1,5 % per månad tillkommer på förfallna fakturor."),
        ("da", "Renter på 1,5 % om måneden tillægges forfaldne fakturaer."),
        ("no", "Renter på 1,5 % per måned påløper forfalte fakturaer."),
        ("fi", "Erääntyneille laskuille lisätään 1,5 % korko kuukaudessa."),
        ("sr", "Zatezna kamata iznosi 1,5% mesečno."),
        # A2: income TAX is not income
        ("en", "Income tax increases 2% each year."),
        ("en", "Income tax rates rise 2% every year in some countries."),
        ("en", "Income tax is 20% a year."),
        # A4: a quoted promise named as a prohibited claim is reported, not made
        ("en", "\"You will make money\" is a prohibited earnings claim under 16.03."),
        ("en", "The statement \"you will make money\" is an income claim and must not be used."),
        ("en", "Saying \"I promise you will make money\" breaks the Company Policy."),
        ("en", "\"Everyone on my team makes money\" is a prohibited claim under 16.03."),
        ("fr", "Dire \"vous allez gagner de l'argent\" est une allégation de revenus interdite."),
    ],
)
def test_1c_review_compliant_sentences_do_not_fire(lang: str, text: str) -> None:
    assert detect_earnings_projection(text, lang) is None


@pytest.mark.parametrize(
    "lang, text, rule",
    [
        # "Nobody can promise ..." is NOT a hedge (round 3): main refuses these on P1 and so does 1c -- a
        # "nobody/no one can promise" hedge tried in round 2 un-refused the genuine promises below it
        ("en", "Nobody can promise that you will earn $1,500 a month.", "P1"),
        ("sv", "Ingen kan lova att du tjänar 15 000 kr i månaden.", "P1"),
        ("da", "Ingen kan love, at du tjener 15.000 kr. om måneden.", "P1"),
        ("no", "Ingen kan love at du tjener 15 000 kr i måneden.", "P1"),
        ("en", "Although nobody can promise it, you will earn $1,500 a month.", "P1"),
        ("en", "No one can guarantee you'll earn less than $2,000 a month.", "P1"),
        ("en", "Nobody can promise that you will earn $1,500 a month — most earn more.", "P1"),
        ("en", "Nobody can predict the weather, and you will make $5,000 a month.", "P1"),
        ("en", "Nobody can promise that you will earn $1,500 a month, but you will.", "P1"),
        ("en", "Nobody can promise it, yet most of our Managers earn $3,000 a month.", "P1"),
        ("en", "Nobody can guarantee results. You will earn $1,500 a month.", "P1"),
        ("en", "Nobody can promise; Managers make $5,000 a month.", "P1"),
        ("en", "Nobody can promise that you will earn $1,500 a month; typical Managers earn 3,000 a month.", "P1"),
        ("en", "People who say nobody can promise are wrong: you will earn $5,000 a month.", "P1"),
        ("en", "Nobody can promise it, but you will earn $1,500 a month.", "P1"),
        ("en", "Nobody can promise it; you will earn $1,500 a month.", "P1"),
        ("en", "Nobody can promise it. You will earn $1,500 a month.", "P1"),
        ("en", "Nobody can guarantee it, but most of my team make $3,000 a month.", "P1"),
        ("en", "I cannot promise it, but you will earn $1,500 a month.", "P1"),
        ("fr", "Personne ne peut le garantir, mais la plupart gagnent 3 000 € par mois.", "P1"),
        ("fr", "Bien que personne ne puisse le promettre, vous gagnerez 1 500 € par mois.", "P1"),
        ("es", "Nadie puede prometer nada, pero ganarás 1.500 € al mes.", "P1"),
        ("es", "Aunque nadie puede prometerlo, ganarás 1.500 € al mes.", "P1"),
        ("de", "Niemand kann es versprechen, aber Sie werden 1.500 € im Monat verdienen.", "P1"),
        ("de", "Obwohl niemand es versprechen kann, werden Sie 1.500 € im Monat verdienen.", "P1"),
        ("it", "Nessuno può prometterlo, ma guadagnerai 1.500 € al mese.", "P1"),
        ("it", "Anche se nessuno può prometterlo, guadagnerai 1.500 € al mese.", "P1"),
        ("nl", "Niemand kan het beloven, maar je verdient 1.500 € per maand.", "P1"),
        ("nl", "Hoewel niemand het kan beloven, verdien je 1.500 € per maand.", "P1"),
        ("sv", "Ingen kan lova något, men du tjänar 15 000 kr i månaden.", "P1"),
        ("sv", "Även om ingen kan lova det tjänar du 15 000 kr i månaden.", "P1"),
        ("da", "Ingen kan love noget, men du tjener 15.000 kr. om måneden.", "P1"),
        ("da", "Selvom ingen kan love det, tjener du 15.000 kr. om måneden.", "P1"),
        ("no", "Ingen kan love noe, men du tjener 15 000 kr i måneden.", "P1"),
        ("no", "Selv om ingen kan love det, tjener du 15 000 kr i måneden.", "P1"),
        ("fi", "Kukaan ei voi luvata mitään, mutta ansaitset 1 500 € kuukaudessa.", "P1"),
        ("sr", "Niko ne može obećati, ali zarađivaćete 150.000 dinara mesečno.", "P1"),
        # the bare-figure twins fire P10 (same verdict as main gives the currency form)
        ("en", "Nobody can promise that you will earn 1,500 a month.", "P10"),
        ("en", "Nobody can promise it, yet most of our Managers earn 3,000 a month.", "P10"),
        ("en", "Nobody can guarantee results. You will earn 1,500 a month.", "P10"),
        ("en", "Nobody can promise anything; still, Managers make 5,000 a month.", "P10"),
        ("en", "Nobody can promise it, but most Managers make 5,000 a month.", "P10"),
        ("fr", "Personne ne peut promettre de résultats. Vous gagnerez 1 500 par mois.", "P10"),
        ("de", "Niemand kann versprechen, dass Sie 1.500 im Monat verdienen.", "P10"),
        ("sv", "Ingen kan lova att du tjänar 15 000 i månaden.", "P10"),
        ("da", "Ingen kan love, at du tjener 15.000 om måneden.", "P10"),
        ("no", "Ingen kan love at du tjener 15 000 i måneden.", "P10"),
    ],
)
def test_1c_nobody_can_promise_is_not_a_hedge(lang: str, text: str, rule: str) -> None:
    """Round 3 of the step-1c review: the "nobody / no one can promise|guarantee|predict" hedge was DROPPED in all
    12 languages, because it un-refused genuine promises ("Although nobody can promise it, you will earn $1,500 a
    month", "No one can guarantee you'll earn less than $2,000 a month" ...). These verdicts now match main
    exactly (P1 on the currency forms) and the bare-figure twins fire P10."""
    hit = detect_earnings_projection(text, lang)
    assert hit is not None and hit[0] == rule, hit


@pytest.mark.parametrize(
    "text",
    [
        'I promise "you will make money".',
        'As I always say: "everyone on my team makes money".',
        'Trust me: "you will make money" — every single one of my recruits does.',
        '"Everyone on my team makes money" - and that\'s a fact.',
        'Everyone on my team makes "real" money.',
        '"You will make money with us," I tell every recruit, and it\'s true.',
        'My sponsor said "you will make money" and she was right: you will make money.',
        'Everyone on my team makes money, "guaranteed".',
        # optional team-scope recall (round 3)
        "Everyone I sponsored makes money.",
        "Everyone who joins under me makes money.",
        "All the people in my group are making money.",
        "Join my team: everyone makes money.",
        "Everyone in my Forever team makes money.",
        "All my recruits make money.",
        "Each and every member of my team makes money.",
    ],
)
def test_1c_own_quoted_or_scoped_promises_fire(text: str) -> None:
    """A4 (round 3): a quoted promise is reported only when the quote opens the sentence and is judged by it
    ("... is a prohibited claim"), or a non-first-person say/report word precedes it. "I promise '...'", "As I
    always say: '...'" and a quote followed by "- and that's a fact" are the answer's own promise."""
    hit = detect_earnings_projection(text, "en")
    assert hit is not None and hit[0] == "P12", hit


@pytest.mark.parametrize(
    "lang, text, rule",
    [
        ("en", "Unlike a bond, this pays a 10% return every month.", "P11"),
        ("en", "Your investment yields 30% a month, far more than any deposit.", "P11"),
        ("en", "Forget the bank: your money doubles every year with Forever.", "P11"),
        ("en", "A bank pays 2% a year; with us expect a 30% return every month.", "P11"),
        ("en", "Better than a savings account: expect a 5% return every month.", "P11"),
    ],
)
def test_1c_return_exclusion_stops_at_a_contrast_word(lang: str, text: str, rule: str) -> None:
    """Round 3: a bank/bond/deposit word on the far side of a contrast or comparison word (unlike, than, forget,
    ...) does not cancel the return promised to the reader; late-payment interest and "Compare this with a bank
    account paying 2% interest per year" stay clean (see test_1c_review_compliant_sentences_do_not_fire)."""
    hit = detect_earnings_projection(text, lang)
    assert hit is not None and hit[0] == rule, hit


def test_a_25000_digit_run_evaluates_well_under_one_second() -> None:
    """R3 (review): `_SPELLED_BARE_GATE` carried a "\\w*cient[oa]s" alternative that rescanned a long digit run from
    every position -- 15.9 s for 25,000 digits against 0.2 s on main. The Spanish hundreds are now spelled out and a
    digit may not precede the magnitude word."""
    result, elapsed = _timed("1" * 25000)
    assert result is None
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


# --- (d) performance: the new regexes must stay linear -------------------------------------------------------
#
# Measured locally (median, this machine) before the bounds below were in place: "two thousand and " * N with no
# period phrase took 2.6 s / 10 s / 40 s at N = 500 / 1,000 / 2,000 (quadratic) through the 1c spelled-bare rewrite,
# and the SAME chained-number-word shape ending in a currency word took 1.3 s / 12 s / 45 s on the PRE-1c detector
# through 1b's _SPELLED_RE. Both rewrites now bound the number-word run to 8 joined tokens (_SPELLED_NUM_BOUNDED);
# after it: ~0.14 s / ~0.24 s at N = 2,000. Every other 1c path is windowed like P1/P2/P6/P8 (verb scan bounded to
# WIN_BEFORE before the amount, clause slice to +-400 chars, _ClauseIndex lookups O(log n)).

def _timed(text: str):
    started = time.perf_counter()
    result = detect_earnings_projection(text, "en")
    return result, time.perf_counter() - started


def test_a_sentence_with_2000_chained_number_words_and_no_period_evaluates_well_under_one_second() -> None:
    result, elapsed = _timed("two thousand and " * 2000 + "end.")
    assert result is None
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


def test_a_sentence_with_2000_chained_number_words_and_a_currency_evaluates_well_under_one_second() -> None:
    """Pins the bound on 1b's _SPELLED_RE too (pre-existing quadratic path, found while measuring 1c)."""
    result, elapsed = _timed("two thousand and " * 2000 + "x y dollars.")
    assert result is None  # no earn verb / earner / estimate anywhere
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


def test_a_sentence_with_2000_bare_amounts_per_period_evaluates_well_under_one_second() -> None:
    result, elapsed = _timed("5,000 a month and " * 2000 + "end.")
    assert result is None  # no verb, earner, rank or estimate anywhere
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


def test_a_sentence_with_2000_negated_verb_bare_amounts_evaluates_well_under_one_second() -> None:
    result, elapsed = _timed("you never earn 5,000 a month and " * 2000 + "end.")
    assert result is None  # "never earn" is negated on every repetition
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


def test_a_sentence_with_2000_percentage_returns_in_rule_context_evaluates_well_under_one_second() -> None:
    result, elapsed = _timed("30% return every month on the order and " * 2000 + "end.")
    assert result is None  # "order" is rule context on every repetition
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


def test_a_sentence_with_2000_reported_double_your_money_evaluates_well_under_one_second() -> None:
    result, elapsed = _timed("prohibited to double your money every year and " * 2000 + "end.")
    assert result is None
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


def test_a_200kb_policy_like_answer_grows_linearly_from_50kb() -> None:
    """Linearity check on a realistic mix of the shapes the new guards reject (Case Credits per month, an "up to"
    cap, durations, order minimums, a bonus rate): 200 KB must cost no more than ~6x the 50 KB run (linear = 4x)."""
    unit = "The Personal Bonus is 5% on 4 CC per month; up to 18 months to requalify; 25 orders minimum. "
    small = (unit * (50_000 // len(unit) + 1))[:50_000]
    large = (unit * (200_000 // len(unit) + 1))[:200_000]
    # best of three: a 200 KB run allocates millions of match objects, and its wall time swings ~2x with the
    # heap state the earlier (2,000-item) timing tests leave behind -- the detector itself is linear (measured
    # 225 ms -> 910 ms at 50 -> 200 KB in a fresh process, and 4.0x on main's own detector), so the min filters
    # the allocator noise and the bound is 8x (linear = 4x) rather than a knife-edge.
    results = [(_timed(small), _timed(large)) for _ in range(3)]
    assert all(rs is None and rl is None for (rs, _), (rl, _) in results)
    t_small = min(ts for (_, ts), _ in results)
    t_large = min(tl for _, (_, tl) in results)
    assert t_large < 6.0, f"200 KB took {t_large:.2f}s"
    assert t_large <= 8 * max(t_small, 0.05), f"50 KB {t_small:.3f}s -> 200 KB {t_large:.3f}s (super-linear growth)"


# Final review round: a quote followed by an affirming copula is not a report, and French/Spanish
# "never say" instructions are reports.
@pytest.mark.parametrize(
    "text",
    [
        '"You will make money" is a fact.',
        '"You will make money" is true.',
        '"You will make money" is not an exaggeration.',
        '"You will make money" is our motto and it holds.',
        '"You will make money," is what I guarantee.',
    ],
)
def test_1c_quote_with_affirming_copula_still_fires(text: str) -> None:
    assert detect_earnings_projection(text, "en")


@pytest.mark.parametrize(
    "text,lang",
    [
        ("Ne dites jamais « vous allez gagner de l'argent ».", "fr"),
        ("Nunca digas « vas a ganar dinero ».", "es"),
        ('Never say "you will make money".', "en"),
    ],
)
def test_1c_never_say_instruction_is_a_report(text: str, lang: str) -> None:
    assert not detect_earnings_projection(text, lang)
