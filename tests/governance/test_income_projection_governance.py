"""Governance-level coverage for IncomeProjectionPolicy, exercised through the
real GovernanceEngine + RiskEngine(default_policies()) stack, following the
pattern in tests/governance/test_claim_topic_answer_exemption.py.

IncomeProjectionPolicy is a TIGHTENING for GENERATED answers only: it adds
INCOME_PROJECTION_RISK refusals for earnings-projection language that
IncomeClaimPolicy's guarantee/earnings-phrase matching does not already
catch, and it never changes the input-side pass or IncomeClaimPolicy's own
behaviour.

Everything here is local; sockets and boto3 clients raise if used, and the
BedrockGuardrailsProvider used below is pure regex over DENIED_TOPICS with
no network call, exactly as in test_claim_topic_answer_exemption.py.
"""

from __future__ import annotations

import re
import socket

import pytest

from app.governance.engine import GovernanceEngine
from app.governance.providers.bedrock_guardrails import BedrockGuardrailsProvider
from app.risk.engine import RiskEngine, default_policies
from app.risk.models import RiskContext
from app.risk.policies import IncomeClaimPolicy, IncomeProjectionPolicy
from app.risk.policies.income_projection import detect_earnings_projection


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _refuse(*_: object, **__: object):
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


class FakeRegistry:
    def __init__(self, provider) -> None:
        self.provider = provider

    def get(self, name: str):
        return self.provider


def _engine() -> GovernanceEngine:
    provider = BedrockGuardrailsProvider()
    return GovernanceEngine(
        registry=FakeRegistry(provider),
        default_provider=provider.name,
        risk=RiskEngine(default_policies()),
    )


def _answer(text: str, *, language: str = "en", allow_claim_topics: bool = False):
    return _engine().evaluate(
        text=text, country="US", language=language, correlation_id="cid",
        allow_claim_topics=allow_claim_topics, is_generated_answer=True,
    )


def _user_input(text: str, *, language: str = "en", allow_claim_topics: bool = False):
    return _engine().evaluate(
        text=text, country="US", language=language, correlation_id="cid",
        allow_claim_topics=allow_claim_topics, is_generated_answer=False,
    )


def _risk_context(text: str, *, is_generated_answer: bool, allow_claim_topics: bool = False, language: str = "en") -> RiskContext:
    return RiskContext(
        user_message=text, country="US", language=language, role="new_prospect",
        correlation_id="cid", allow_claim_topics=allow_claim_topics,
        is_generated_answer=is_generated_answer,
    )


# --- the five finding sentences -------------------------------------------------

FINDING_SENTENCES = [
    "Most FBOs earn roughly 900 dollars a month.",
    "Active Supervisors receive around 400 to 800 dollars a month in bonuses.",
    "Typical Supervisors earn $1,500 a month.",
    "Most FBOs who work the plan earn several thousand dollars a month.",
    "You will typically earn $500 a month.",
]


@pytest.mark.parametrize("text", FINDING_SENTENCES)
def test_finding_sentences_refused_as_generated_answers_via_projection_alone(text: str) -> None:
    ctx = _risk_context(text, is_generated_answer=True)
    assert IncomeClaimPolicy().evaluate(ctx) == [], f"expected IncomeClaimPolicy silent for {text!r}"
    issues = IncomeProjectionPolicy().evaluate(ctx)
    assert [issue.code for issue in issues] == ["INCOME_PROJECTION_RISK"]
    decision = _answer(text)
    assert decision.allowed is False


@pytest.mark.parametrize("text", FINDING_SENTENCES)
def test_finding_sentences_allowed_as_user_input(text: str) -> None:
    decision = _user_input(text)
    assert decision.allowed is True


@pytest.mark.parametrize("text", FINDING_SENTENCES)
def test_finding_sentences_still_refused_with_allow_claim_topics(text: str) -> None:
    """is_claim_topic=False proves allow_claim_topics can never forgive this policy."""
    decision = _answer(text, allow_claim_topics=True)
    assert decision.allowed is False


# --- R10E texts: allowed once the approved-disclaimer exemption is applied ----
# (fix/income-disclaimer-exemption-20260925, app/risk/policies/income_disclaimer.py).
# These three real generated answers quote the company's own mandatory US-EN
# income disclaimer (Company Policy 1.01(d)) and were previously refused only
# because IncomeClaimPolicy's guarantee/earnings pairing is not sentence-scoped
# and fired on the disclaimer's own wording. IncomeProjectionPolicy correctly
# never fired on these texts either before or after the fix -- they contain no
# earnings-projection figure -- so that half of this test is unchanged.

R10E_TEXTS = {
    "r10-05": (
        "I understand your concern—it's smart to ask directly. Here's what Forever Living says about itself:\n\n"
        "Forever Living Products (FLP) is \"an international family of companies that produce and market exclusive "
        "health and beauty products throughout the world through its unique concept that encourages and supports "
        "the use and retail sales of its products through independent Forever Business Owners (FBO).\"\n\n"
        "The company emphasizes that **\"the fundamental goal of the FLP marketing plan is to promote the sale and "
        "use of high-quality products to consumers.\"**\n\n"
        "On earnings and success, Forever is explicit: **\"FLP has a long history of success, but does not "
        "represent that an FBO will achieve financial success. Compensation in FLP is based upon the sale of its "
        "products. Individual results may vary. Forever makes no guarantees regarding income or success.\"**\n\n"
        "**Important timing note:** As of May 1, 2026, the U.S. business structure changed significantly. The "
        "company stopped sponsoring new Forever Business Owners in the United States, and new FBOs can no longer "
        "join the U.S. program. Existing downline purchasing will continue generating earnings through the end of "
        "2026, but the sponsoring-based incentive structure has ended.\n\n"
        "If you have specific questions about the business model, product focus, or current eligibility, I'm happy "
        "to help clarify further. You can also reach the company directly at **1-888-440-ALOE (2563)** or through "
        "a Regional Sales Director or Area Sales Manager for detailed discussion."
    ),
    "r10-06": (
        "I understand your family's concern. Here's what Forever Living is, plainly:\n\n"
        "**What Forever Living Products (FLP) is:**\n\n"
        "Forever Living Products is an international company that produces and sells health and beauty products. "
        "The fundamental goal of the FLP marketing plan is to promote the sale and use of high-quality products to "
        "consumers.\n\n"
        "**How it operates:**\n\n"
        "The company has historically sold through independent Forever Business Owners (FBOs)—people who "
        "purchase products and can earn money by selling them to customers and by recruiting others to do the "
        "same. FLP provides products, support staff, and a marketing plan to FBOs.\n\n"
        "**Important context for the US right now:**\n\n"
        "As of May 1, 2026, Forever Living made significant changes to its U.S. business structure. The company "
        "decided to narrow its U.S. operations and focus on a model centered on product sales and long-term "
        "compliance, due to regulatory concerns. **The Forever Business Owner opportunity and related incentives "
        "are not available to residents of the United States beginning on May 1, 2026.** This means:\n\n"
        "- Sponsoring new FBOs in the U.S. has stopped.\n"
        "- Incentives tied to sponsoring or organizational expansion have ended.\n\n"
        "**On earnings:**\n\n"
        "FLP does not represent that an FBO will achieve financial success. Compensation is based upon the sale of "
        "its products. Individual results may vary, and Forever makes no guarantees regarding income or success.\n\n"
        "If you have specific questions about how the business works or what's being offered to you or your family "
        "member, contact Forever Living Customer Care at 1-888-440-ALOE (2563)."
    ),
    "r10-07": (
        "Forever Living Products (FLP) is an international family of companies that produces and market exclusive "
        "health and beauty products throughout the world through its unique concept that encourages and supports "
        "the use and retail sales of its products through independent Forever Business Owners (FBOs). FLP provides "
        "each FBO with the best quality products, support staff and marketing plan in the industry.\n\n"
        "The fundamental goal of the FLP marketing plan is to promote the sale and use of high-quality products to "
        "consumers.\n\n"
        "It's important to understand that FLP has a long history of success, but does not represent that an FBO "
        "will achieve financial success. Compensation in FLP is based upon the sale of its products. Individual "
        "results may vary. Forever makes no guarantees regarding income or success.\n\n"
        "**Important note for U.S. residents:** The Forever Business Owner opportunity and related incentives are "
        "not available to residents of the United States beginning on May 1, 2026. As of that date, the company "
        "narrowed the U.S. structure to focus on a model centered on product sales and long-term compliance. "
        "Sponsoring new Forever Business Owners in the United States has ceased, and qualification for incentives "
        "tied to sponsoring or organizational expansion has ended.\n\n"
        "If you have specific questions about the company's policies or structure, you can contact the Regional "
        "Sales Director/Area Sales Manager or call Customer Care at 1-888-440-ALOE (2563)."
    ),
}
_DISCLAIMER_RE = re.compile(r"[^.\n]*no guarantees regarding income or success\.?\"?\**")


@pytest.mark.parametrize("case_id,text", list(R10E_TEXTS.items()))
def test_r10e_texts_allowed_via_disclaimer_exemption_and_never_hit_projection(case_id: str, text: str) -> None:
    ctx = _risk_context(text, is_generated_answer=True)
    claim_issues = IncomeClaimPolicy().evaluate(ctx)
    assert claim_issues == [], f"{case_id}: the approved-disclaimer exemption should clear INCOME_CLAIM_RISK"
    projection_issues = IncomeProjectionPolicy().evaluate(ctx)
    assert projection_issues == [], f"{case_id}: INCOME_PROJECTION_RISK must not fire on these disclaimer-only texts"
    decision = _answer(text)
    assert decision.allowed is True, case_id


@pytest.mark.parametrize("case_id,text", list(R10E_TEXTS.items()))
def test_r10e_texts_allowed_once_disclaimer_sentence_removed(case_id: str, text: str) -> None:
    stripped = _DISCLAIMER_RE.sub("", text)
    decision = _answer(stripped)
    assert decision.allowed is True, case_id
    ctx = _risk_context(stripped, is_generated_answer=True)
    assert IncomeProjectionPolicy().evaluate(ctx) == [], f"{case_id}: the new detector must not fire on the non-disclaimer text"


# --- the disclaimer+figure pair, in all 12 languages ----------------------------

STEP2_PAIR_BY_LANGUAGE = {
    "en": "Forever makes no guarantees regarding income or success. Most FBOs earn roughly 900 dollars a month.",
    "fr": "Forever ne garantit ni revenu ni succès. La plupart des FBO gagnent environ 900 € par mois.",
    "es": "Forever no garantiza ingresos ni éxito. La mayoría de los FBO gana aproximadamente 900 dólares al mes.",
    "de": "Forever gibt keine Garantie für Einkommen oder Erfolg. Die meisten FBOs verdienen etwa 900 € im Monat.",
    "nl": "Forever geeft geen garanties over inkomen of succes. De meeste FBO's verdienen ongeveer € 900 per maand.",
    "it": "Forever non garantisce reddito o successo. La maggior parte degli FBO guadagna circa 900 € al mese.",
    "da": "Forever giver ingen garantier for indkomst eller succes. De fleste FBO’er tjener omkring 6.000 kr. om måneden.",
    "no": "Forever gir ingen garantier om inntekt eller suksess. De fleste FBO-er tjener rundt 9 000 kr i måneden.",
    "sv": "Forever ger inga garantier för inkomst eller framgång. De flesta FBO:er tjänar ungefär 9 000 kronor i månaden.",
    "fi": "Forever ei takaa tuloja tai menestystä. Useimmat FBO:t ansaitsevat noin 900 euroa kuukaudessa.",
    "ru": "Forever не гарантирует доход или успех. Большинство FBO зарабатывают около 900 долларов в месяц.",
    "sr": "Forever ne garantuje prihod ni uspeh. Većina FBO zarađuje oko 900 evra mesečno.",
}


@pytest.mark.parametrize("language,text", list(STEP2_PAIR_BY_LANGUAGE.items()))
def test_disclaimer_and_projection_pair_refused_in_every_language(language: str, text: str) -> None:
    """Refused as a generated answer today via IncomeClaimPolicy's own disclaimer match --
    AND the detector itself fires on the projection sentence in every language.

    The first assertion alone is vacuous on the base code: IncomeClaimPolicy already
    refuses on the disclaimer sentence regardless of whether income_projection.py exists
    at all. The second assertion is what actually pins the property step 2 will depend on
    (the detector, not just IncomeClaimPolicy, recognising the projection sentence in
    every one of the 12 languages -- P1 fires on all 12 here).
    """
    decision = _answer(text, language=language)
    assert decision.allowed is False, language
    assert detect_earnings_projection(text, language) is not None, (
        f"expected the projection detector itself to fire on the {language!r} pair, not just IncomeClaimPolicy"
    )


# --- the FBO Support Fee worked example: a rule-context near-miss, all 12 languages --

FEE_EXAMPLE_BY_LANGUAGE = {
    "en": "For example, if an FBO earns €20 in bonus in a month, €3 will be deducted as the FBO Support Fee.",
    "fr": "Par exemple, si un FBO gagne 20 € de bonus dans le mois, 3 € seront déduits au titre des frais de soutien FBO.",
    "es": "Por ejemplo, si un FBO gana 20 dólares en bonos en un mes, se deducirán 3 dólares como cuota de soporte FBO.",
    "de": "Wenn ein FBO in einem Monat 20 € Bonus verdient, werden 3 € als FBO-Supportgebühr abgezogen.",
    "nl": "Als een FBO in een maand € 20 aan bonus verdient, wordt € 3 ingehouden als FBO-ondersteuningsvergoeding.",
    "it": "Ad esempio, se un FBO guadagna 20 € di bonus in un mese, verranno detratti 3 € come quota di supporto FBO.",
    "da": "Hvis en FBO tjener 20 € i kommission i løbet af en måned, fratrækkes 3 € som bonusgebyr.",
    "no": "Hvis en FBO tjener 20 € i bonus i løpet av en måned, trekkes 3 € som FBO-støttegebyr.",
    "sv": "Om en FBO tjänar 20 € i bonus under en månad dras 3 € av som FBO-supportavgift.",
    "fi": "Jos FBO ansaitsee kuukaudessa 20 euroa bonusta, 3 euroa vähennetään FBO-tukimaksuna.",
    "ru": "Например, если FBO зарабатывает 20 долларов бонуса в месяц, 3 доллара удерживаются в качестве сбора поддержки FBO.",
    "sr": "Ako FBO zaradi 20 evra bonusa u toku meseca, 3 evra se odbijaju kao naknada za podršku FBO.",
}


@pytest.mark.parametrize("language,text", list(FEE_EXAMPLE_BY_LANGUAGE.items()))
def test_fee_worked_example_does_not_fire_in_any_language(language: str, text: str) -> None:
    """The new detector must never fire on this rule-context near-miss, in any language.

    Note (Fable review): the FULL engine already refuses the "fi" and "ru" fee
    examples on the base code (before this port existed), via IncomeClaimPolicy's
    translated income-claim phrase list -- a pre-existing false positive, not
    caused by this port. This test asserts only IncomeProjectionPolicy's own
    verdict, which is None in every language including "fi" and "ru"; it makes
    no claim about the full GovernanceEngine's decision for those two.
    """
    ctx = _risk_context(text, is_generated_answer=True, language=language)
    assert IncomeProjectionPolicy().evaluate(ctx) == [], language


# --- known residual miss "sr-fin_freedom": covered elsewhere by the full engine --

def test_sr_financial_freedom_residual_miss_is_still_refused_by_the_full_engine() -> None:
    """income_projection.py does not catch this (see tests/unit's _KNOWN_RESIDUAL_MISSES:
    "financial freedom" is deliberately excluded from P4, and the sr "pasivan prihod"
    adjectival form does not match the "pasivn\\w*" vocabulary stem). The full
    GovernanceEngine must still refuse it -- via IncomeClaimPolicy's translated
    income-claim phrase list -- proving the gap is covered elsewhere, not left open.
    """
    text = "Forever vam pruža finansijsku slobodu i pasivan prihod."
    ctx = _risk_context(text, is_generated_answer=True, language="sr")
    assert IncomeProjectionPolicy().evaluate(ctx) == [], "the ported detector is not expected to catch this"
    claim_issues = IncomeClaimPolicy().evaluate(ctx)
    assert [issue.code for issue in claim_issues] == ["INCOME_CLAIM_RISK"], (
        "expected the translated income-claim phrase list to cover this residual miss"
    )
    decision = _answer(text, language="sr")
    assert decision.allowed is False, "expected the full engine to refuse this residual-miss text"
