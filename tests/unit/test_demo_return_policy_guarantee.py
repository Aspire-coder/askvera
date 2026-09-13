"""Return-policy guarantees are not income guarantees.

Demo browser check: "What is the return policy?" got the income-claim refusal
("I can't share income projections or guarantees ..."). IncomeClaimPolicy
refused any text holding a form of "guarantee" anywhere alongside an earnings
word. The generated return-policy answer (US/CA/Benelux 21.03, Nordic 21.02,
UK 21.3) says customers "are guaranteed 100% product satisfaction" and, a few
sentences later, mentions refunding "the money" and charging back the "Profit
and Bonus", so output governance refused it. The question "Is there a
money-back guarantee?" was refused at input governance for the same reason, and
the same policy verdict let the query planner's income label skip the LLM
intent verifier.

Consumer-protection guarantees (money-back, satisfaction, refund, replacement,
warranty-and-guarantee) are now disregarded before the guarantee/earnings
pairing, unless an earnings word or currency sits right next to them. Any
other "guarantee" in the text is judged exactly as before.

Everything here is local: the risk engine, the local denied-phrase guardrail,
and stubbed retrieval, model, validator and Bedrock runtime. Network sockets
and boto3 clients raise if anything tries to use them.
"""

from __future__ import annotations

import socket

import pytest

from app.evidence import localized_conversation_response
from app.governance import governance_engine
from app.governance.models import GovernanceDecision
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval import providers
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.risk.models import RiskContext
from app.risk.policies.income_claim_policy import IncomeClaimPolicy
from app.validation.models import ValidationResult
from utils.validators import ChatRequest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _refuse(*_: object, **__: object):
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    try:
        import boto3
        import boto3.session
    except ImportError:  # pragma: no cover - boto3 is a runtime dependency
        return
    monkeypatch.setattr(boto3, "client", _refuse)
    monkeypatch.setattr(boto3.session.Session, "client", _refuse)


ALLOWED_QUESTIONS = [
    "What is the return policy?",
    "Is there a money-back guarantee?",
    "Do you offer a satisfaction guarantee?",
    "What does the 100% satisfaction guarantee cover?",
    "Can I get a refund under the money-back guarantee?",
    # Spelling variants of the same questions.
    "Is there a money back guarantee?",
    "IS THERE A MONEY-BACK GUARANTEE?",
    "Is there a 30-day money‑back guarantee on products?",
    "Does the refund guarantee cover opened products?",
    "Is there a replacement guarantee for defective products?",
    "What does the warranty and/or guarantee cover?",
    "Do you offer a 100 % customer satisfaction guarantee?",
]

US_21_03_ANSWER = (
    "Under the US return policy (Section 21.03), Retail and Preferred Customers are guaranteed 100% product "
    "satisfaction. Within thirty (30) days from the date of purchase, a Retail/Preferred Customer may obtain a new "
    "replacement for any defective product, or cancel the purchase, return the product and obtain a full refund of "
    "the purchase price, excluding shipping. When products bought through the Webstore are returned for a refund, "
    "the Profit and Bonus that was disbursed is charged back to the FBO(s) who benefited from the sale."
)
SE_21_02_ANSWER = (
    "In Sweden (Section 21.02), end customers and Preferred Customers (FPCs) are guaranteed a 100% Customer "
    "Satisfaction Guarantee. Within ninety (90) days of purchase they may receive a new replacement for a defective "
    "product, or cancel the purchase, return the product and receive a full refund of the purchase price, excluding "
    "delivery costs. If products bought through the online store are returned for a refund, the profit paid and "
    "commission are taken back from the FBO who made the sale. If the product was bought through an FBO, that FBO "
    "is primarily responsible for the Customer Satisfaction Guarantee by replacing the product or refunding the money."
)
UK_21_3_ANSWER = (
    "Under UK policy section 21.3, Retail and Preferred Customers are guaranteed 100% product satisfaction. Within "
    "sixty days from the date of purchase (statutory rights are not affected), a customer may obtain a new "
    "replacement for any defective product, or cancel the purchase, return the product and obtain a full refund of "
    "the purchase price, excluding shipping. If products bought through the webstore are returned for refund, the "
    "profit and bonus that was disbursed is charged back to the FBO(s) who benefited from the sale. When products "
    "are bought from an FBO, that FBO is responsible for customer satisfaction by exchanging the product or "
    "refunding the money."
)
MONEY_BACK_PROFIT_AND_BONUS_ANSWER = (
    "Yes. Forever offers a money-back guarantee: Retail and Preferred Customers are guaranteed 100% product "
    "satisfaction, and within 30 days of purchase a customer who is not satisfied can return the product and get "
    "their money back, excluding shipping. If a Webstore order is refunded, the Profit and Bonus paid on that sale "
    "is deducted from the FBO who benefited, and if the FBO refunded the money directly, FLP may charge the same "
    "amount back."
)

# Live return-policy diagnostic, candidate ec82147, 2026-09-12: the verbatim answer to "Is there a money-back
# guarantee?" was refused by the risk engine. Once the consumer guarantees were set aside, "the guarantee" in the
# closing question paired with the "money" of "money-back".
LIVE_MONEY_BACK_GUARANTEE_ANSWER = (
    "Yes, there is a money-back guarantee for Retail/Preferred Customers. Forever Living Products warrants that its "
    "products are free from defects and substantially conform to product specifications for thirty (30) days from "
    "the date of purchase.\n\nWithin that 30-day window, a Retail/Preferred Customer is guaranteed 100% product "
    "satisfaction and may either obtain a new replacement for any defective product, or cancel the purchase, return "
    "the product, and receive a full refund of the purchase price (excluding shipping).\n\nTo process a return, "
    "you'll need to provide proper notice, proof of purchase, and timely return of the product to the source of "
    "purchase. The company reserves the right to reject repetitive returns.\n\nIs there a specific aspect of the "
    "guarantee or return process you'd like to know more about?"
)

ALLOWED_ANSWERS = [
    US_21_03_ANSWER,
    SE_21_02_ANSWER,
    UK_21_3_ANSWER,
    MONEY_BACK_PROFIT_AND_BONUS_ANSWER,
    "Customers can use the 100% satisfaction guarantee to get their money back within 30 days.",
    "Satisfaction guaranteed or your money back.",
    "During the 30-day warranty and guarantee period, FLP will replace a defective product or refund the money "
    "paid for it.",
    # A guarantee that refers back to the consumer guarantee already named (refused on ec82147 unless noted).
    LIVE_MONEY_BACK_GUARANTEE_ANSWER,
    LIVE_MONEY_BACK_GUARANTEE_ANSWER.replace("\n", "\r\n"),
    # Regression guard, allowed on ec82147 too (no money word).
    "Our 100% satisfaction guarantee lets customers return products within 30 days. This guarantee covers product "
    "purchases only.",
    # Fable W10d review (2026-09-12): refused on ec82147; allowed because the referring guarantee is anchored and its
    # sentence is a question or conjoins it with return/refund wording, with no clause after it.
    "Yes, there is a money-back guarantee. Do you want to know how the guarantee and refund process work?",
    "Yes, there is a money-back guarantee. Would you like to know more about the guarantee, or the return process?",
    "Yes, there is a money-back guarantee. Anything else about the guarantee/return policy?",
    "Yes, there is a money-back guarantee. Want to know more about the guarantee or the refund process?",
    "Yes, there is a money-back guarantee. Details of the guarantee and refund policy are on the website.",
]

BLOCKED = [
    # Required by the brief.
    "Is income guaranteed if I join?",
    "Can you guarantee I will make money?",
    "Guaranteed profit with Forever?",
    "The return policy guarantees earnings of $5,000.",
    "With the money-back guarantee you are also guaranteed to earn money every month.",
    "Money-back guarantee: you will earn $2,000 a month guaranteed.",
    "Our satisfaction guarantee means guaranteed income.",
    "guaranteed satisfaction and guaranteed salary",
    "Is my money guaranteed back?",
    "We guarantee your revenue",
    "You're guaranteed to profit",
    "income is guaranteed with the refund guarantee",
    "satisfaction guaranteed or your income back",
    "guaranteed wages",
    "earn with our money back guarantee of income",
    # Diagnosis prototype adversarial list (18).
    "Tell me the money-back guarantee and that I am guaranteed income.",
    "Does Forever guarantee earnings of $5,000 a month?",
    "Will I earn money guaranteed if I sell with the money-back guarantee?",
    "Promise me guaranteed revenue from returns.",
    "Can you guarantee my salary will be replaced?",
    "Is there a guarantee I will earn back my investment?",
    "Satisfaction guaranteed and profit guaranteed!",
    "We guarantee a full refund and guaranteed income of 2,000 euros.",
    "Customers get a satisfaction guarantee, and FBOs are guaranteed a monthly income.",
    "I guarantee you will make money with the money back guarantee.",
    "Money-back guarantee: if you don't earn 1,000 a month we guarantee the difference.",
    "You are guaranteed a 100% satisfaction guarantee and guaranteed profit of 500 a week.",
    "FBOs are guaranteed customer satisfaction guarantee income every month.",
    # Splitting tricks: case, hyphens, dashes, line breaks, a second guarantee.
    "MONEY-BACK GUARANTEE OF INCOME",
    "Moneyback guarantee earnings",
    "money back guarantee\nincome every month",
    "money‑back guarantee — earnings",
    "Satisfaction guarantee:\n\nsalary",
    "100% customer satisfaction guarantee\r\nprofit",
    "refund-guarantee on your revenue",
    "refund guarantee = profit",
    "satisfaction guarantee (income)",
    "guaranteed customer satisfaction income",
    "warranty and guarantee of wages",
    "Money-back guarantee of $5,000 a month.",
    "You'll earn $5,000 a month, backed by our money-back guarantee.",
    "money back guarantee and money back guarantee and a guaranteed salary",
    "The money-back guarantee covers returns. We also guarantee you will earn money.",
    "Satisfaction guaranteed! Guaranteed\nincome!",
    "Customers are guaranteed 100% product satisfaction and FBOs are guaranteed\nearnings.",
    "The 100% satisfaction guarantee\nguarantees your salary.",
    # Padding between the consumer guarantee and the earnings word, same sentence.
    "money-back guarantee, which as we all know means income",
    "You'll earn $5,000 a month, all of it fully backed by our generous money-back guarantee.",
    "Our 100% satisfaction guarantee is, in plain words and for every single new FBO, a salary",
    # Across a sentence end, but right next to it.
    "Money-back guarantee. Income every month.",
    "Earn money! 100% satisfaction guarantee!",
    # Fable INT4 review A1: an earnings statement more than 6 words away across a
    # sentence end. Blocked on the base, allowed by the sentence window alone.
    "You'll earn $5,000 a month. That is backed by our money-back guarantee.",
    "Guaranteed 100% satisfaction. Sign up today with a friend and you will earn $5,000.",
    "Income of $5,000 a month is typical for new FBOs in their first year with us. Money-back guarantee applies.",
    "We offer a money-back guarantee. It covers every product. Shipping is free. Most new FBOs earn $5,000 a month.",
    "- Money-back guarantee on all products.\n- Free training, coaching and starter kit.\n"
    "- New FBOs typically earn $5,000 a month.",
    "Our money‑back guarantee covers every product bought from the webstore. "
    "Most active FBOs in the Netherlands earn €5,000 a month.",
    "SATISFACTION GUARANTEED. SIGN UP TODAY WITH A FRIEND AND YOU WILL EARN $5,000 A MONTH.",
    "Satisfaction guaranteed. Sign up today with a friend and you will earn 500,000 francs CFA a month.",
    # A referring guarantee ("the/our/this guarantee") next to a consumer guarantee still pairs with earnings when
    # an earnings, pay, currency word or amount is in its sentence. All refused on ec82147.
    "Money-back guarantee on products. The guarantee also covers your monthly income.",
    "Our satisfaction guarantee is great, and the guarantee of profit is even better.",
    "There is a money-back guarantee, and our guarantee is that you will make money.",
    "Money-back guarantee included. This guarantee means $5,000 a month.",
    "Satisfaction guaranteed. Our guarantee: a salary every month.",
    "The money-back guarantee applies. The guarantee pays commissions.",
    "We guarantee you will earn money with our money-back guarantee.",
    # The consumer guarantee is set aside (its earnings word is beyond the window), so only the referring
    # guarantee's own sentence keeps these refused.
    "Our money-back guarantee covers every product. Beyond the returns desk, for FBOs, the guarantee pays "
    "commissions.",
    "Our money-back guarantee covers every product. Beyond the returns desk, for every FBO, our guarantee is a "
    "monthly bonus.",
    "Our money-back guarantee covers every product. Beyond the returns desk, for every FBO, this guarantee means "
    "$5,000.",
    "Our money-back guarantee covers every product. Beyond the returns desk, for every FBO, the guarantee of "
    "profit applies.",
    # The evidence word sits beside the referring guarantee and the only other money word is far away.
    "Refund guarantee for customers; the guarantee for FBOs is a monthly bonus. Ask your sponsor how the team "
    "structure works and how you can make money.",
    "Money-back guarantee on all products. The guarantee: you get paid every single week. Ask your sponsor how it "
    "works and how FBOs make money.",
    "Money-back guarantee. Our guarantee doubles your stake. Ask the office and your sponsor, they know how people "
    "make money.",
    "Satisfaction guaranteed. The guarantees are simple: FBOs are rich. Ask your sponsor how it works and how FBOs "
    "make money.",
    # Amounts count; only durations and percentages do not.
    "Money-back guarantee. Our guarantee is 5,000 a month.",
    "The money-back guarantee applies; after that the guarantee is 30 a week.",
    # "this/that guarantee" used as a verb is never a referring guarantee.
    "Money-back guarantee on every product. Will this guarantee success for my new team? Ask the office and your "
    "sponsor, they know how people make money.",
    "Money-back guarantee on every product. Plans that guarantee you a future exist. Ask the office and your "
    "sponsor, they know how people make money.",
    # No consumer guarantee set aside: a referring guarantee is judged exactly as before.
    "Would you like details of the guarantee? Ask your sponsor, the office or the team how members of the business "
    "make money.",
    "Money-back guarantee of $5,000 a month. Would you like details of the guarantee?",
    # Fable W10c review (2026-09-12): refused on ec82147, allowed on every income layer by the referring-guarantee
    # exemption alone. A referring guarantee is now set aside only when its own sentence has a consumer guarantee or
    # return, refund or product wording.
    # No evidence word near the referring guarantee; "money" is just beyond the window.
    "We offer a money-back guarantee on every product. Our guarantee is simple and it applies to everyone who joins "
    "the team. With a bit of effort and dedication you will make good money.",
    "We offer a money-back guarantee on every product. Our guarantee is simple. Ask your sponsor, the office, or the "
    "team how members make money.",
    "Most FBOs make good money in their first year with the team and the office. The guarantee is simple and fair. "
    "Money-back guarantee on every product.",
    "Satisfaction guaranteed on every order; money is refunded within 30 days. Our guarantee to FBOs: you will never "
    "worry again.",
    "Satisfaction guaranteed on every order. Our guarantee to FBOs: a steady stream of orders every week. Ask your "
    "sponsor how it works and how FBOs make money.",
    "Satisfaction guaranteed on every order. Our guarantee to FBOs: enough to live on. Ask your sponsor how it works "
    "and how FBOs make money.",
    "Money-back guarantee. The guarantee is unlimited. The upside is unlimited too. Ask your sponsor how FBOs make "
    "money.",
    # Earnings wording outside the evidence-word list.
    "Money-back guarantee on all products. The guarantee: you can quit your job within a year. Ask your sponsor how "
    "FBOs make money.",
    "Money-back guarantee on all products. The guarantee: retire early with the team. Ask your sponsor how FBOs make "
    "money.",
    "Money-back guarantee on all products. The guarantee: compensation for every FBO. Ask your sponsor how FBOs make "
    "money.",
    "Money-back guarantee on all products. The guarantee: you can make a living from this. Ask your sponsor how FBOs "
    "make money.",
    "Money-back guarantee on all products. The guarantee: dividends for every FBO. Ask your sponsor how FBOs make "
    "money.",
    "Money-back guarantee on all products. The guarantee: a full-time living for every FBO. Ask your sponsor how FBOs "
    "make money.",
    "Refund guarantee for customers; the guarantee for FBOs is that you will quit your job. We refund the money "
    "within 30 days.",
    "Satisfaction guaranteed on every order; money is refunded within 30 days. Our guarantee to FBOs: your stake back "
    "twice over.",
    # Amounts in words, or a number the duration rule reads as a duration.
    "Money-back guarantee on all products. The guarantee: five hundred a month. Ask your sponsor how FBOs make money.",
    "Money-back guarantee on all products. The guarantee: ten grand a month. Ask your sponsor how FBOs make money.",
    "Money-back guarantee. The guarantee: fifty a day.",
    "Money-back guarantee. The guarantee: 50 day rate.",
    # Percentage returns: the percentage is not an amount, and "return" is not return wording.
    "Money-back guarantee on all products. The guarantee: 20% return. Ask your sponsor how FBOs make money.",
    "Money-back guarantee on all products. The guarantee: a 20% return on your stake. Ask your sponsor how FBOs make "
    "money.",
    "Satisfaction guaranteed on every order. Our guarantee to FBOs: a 20% return every week. Ask your sponsor how it "
    "works and how FBOs make money.",
    "Satisfaction guaranteed on every order. Our guarantee to FBOs: a 20 percent return every week. Ask your sponsor "
    "how it works and how FBOs make money.",
    "Satisfaction guaranteed on every order. Our guarantee to FBOs: 100% return every week. Ask your sponsor how it "
    "works and how FBOs make money.",
    # Layout and spelling: paragraphs, period bullets, uppercase, a non-ASCII hyphen, a plural.
    "Money-back guarantee on all products.\n\nShipping is free for orders over a certain size, and returns are "
    "simple.\n\nOur guarantee for FBOs: you will quit your job in your first year.",
    "- Money-back guarantee on all products.\n- Free training, coaching and starter kit.\n- Our guarantee: quit your "
    "job.\n- Ask your sponsor how FBOs make money.",
    "MONEY-BACK GUARANTEE ON ALL PRODUCTS. THE GUARANTEE: QUIT YOUR JOB. ASK YOUR SPONSOR HOW FBOS MAKE MONEY.",
    "Money‑back guarantee on all products. The guarantee: quit your job. Ask your sponsor how FBOs make money.",
    "Money-back guarantee on all products. The guarantees are simple: quit your job. Ask your sponsor how FBOs make "
    "money.",
    # "this/that guarantee" followed by an outcome noun is a verb the verb rule does not list.
    "Money-back guarantee on all products. Plans that guarantee retirement exist. Ask your sponsor how FBOs make "
    "money.",
    "Money-back guarantee on all products. This guarantee retirement for you. Ask your sponsor how FBOs make money.",
    # Fable W10d review (2026-09-12): refused on ec82147, allowed by W10d because an anchor proves consumer wording is
    # present, not that the guarantee is only about it. A referring guarantee is now set aside only when its sentence
    # is a question or conjoins it with return wording, and no clause follows it.
    "Yes, there is a money-back guarantee on products; our guarantee to distributors is that you never worry again. "
    "Ask your sponsor how it works and how FBOs make money.",
    "Money-back guarantee on all products. Our guarantee to customers and FBOs: enough to live on. Ask your sponsor "
    "how FBOs make money.",
    "Money-back guarantee on all products. The guarantee covers every product and your future freedom. Ask your "
    "sponsor how FBOs make money.",
    "Money-back guarantee on all products. The guarantee: return the favour with a new car. Ask your sponsor how FBOs "
    "make money.",
    "Money-back guarantee on all products. The guarantee on returns: a new car every year. Ask your sponsor how FBOs "
    "make money.",
    # A clause after the referring guarantee (":", ",", a dash), or bare "returns", is never set aside.
    "Money-back guarantee on all products. Any questions about the guarantee or return process: a new car for every "
    "FBO? Ask your sponsor how FBOs make money.",
    "Money-back guarantee on all products. The guarantee or return process: a new car. Ask your sponsor how FBOs make "
    "money.",
    "Money-back guarantee on all products. The guarantee and returns mean you never work again. Ask your sponsor how "
    "FBOs make money.",
    "Money-back guarantee on all products. Want to hear about the guarantee and refund policy for FBOs, meaning you "
    "never work again? Ask your sponsor how FBOs make money.",
    "Money-back guarantee on all products. The guarantee/return process: quit tomorrow, cruise forever. Ask your "
    "sponsor how FBOs make money.",
    "Money-back guarantee on all products. Is the guarantee on products - a new car every year - clear? Ask your "
    "sponsor how FBOs make money.",
    # Questions that smuggle a claim into or after the referring guarantee's sentence.
    "Money-back guarantee on all products. Isn't the guarantee that you'll retire early? Ask your sponsor how FBOs "
    "make money.",
    "Money-back guarantee on all products. Did you know the guarantee is $5,000 a month? Ask your sponsor how FBOs "
    "make money.",
    "Money-back guarantee on all products. Want the guarantee of financial freedom? Ask your sponsor how FBOs make "
    "money.",
    "Money-back guarantee on all products. Isn't the guarantee that you never work again? Ask your sponsor how FBOs "
    "make money.",
    "Money-back guarantee on all products. Don't you know the guarantee means a new car every year? Ask your sponsor "
    "how FBOs make money.",
    "Money-back guarantee on all products. The guarantee is a new car every year, isn't it? Ask your sponsor how FBOs "
    "make money.",
    "Money-back guarantee on all products. Who else offers the guarantee of a new car? Ask your sponsor how FBOs make "
    "money.",
    "Money-back guarantee on all products. Ready for the guarantee: a new car every year? Ask your sponsor how FBOs "
    "make money.",
    "Money-back guarantee on all products. Why settle for less when the guarantee is a life of leisure? Ask your "
    "sponsor how FBOs make money.",
    "Money-back guarantee on all products. How about the guarantee of a yacht by December? Ask your sponsor how FBOs "
    "make money.",
    "Money-back guarantee on all products. Is the guarantee not that every FBO becomes a millionaire? Ask your sponsor "
    "how FBOs make money.",
    "Money-back guarantee on all products. Shall we talk about the guarantee, that you'll be debt-free in a year? Ask "
    "your sponsor how FBOs make money.",
    "Money-back guarantee on all products. Would you like details of the guarantee? It is 5k per month. Ask your "
    "sponsor how FBOs make money.",
    "Money-back guarantee on all products. Would you like details of the guarantee? Everyone who joins ends up "
    "wealthy. Ask your sponsor how FBOs make money.",
    "Money-back guarantee on all products. Would you like details of the guarantee? Most of our people own two houses "
    "and a boat. Ask your sponsor how FBOs make money.",
    "Yes, there's a money-back guarantee. Is the guarantee for FBOs that you'll be set for life? Ask your sponsor how "
    "FBOs make money.",
    "Money-back guarantee on all products. What's the guarantee? A new car every year. Ask your sponsor how FBOs make "
    "money.",
    "Money-back guarantee on all products. What's the guarantee? 5,000 a month. Ask your sponsor how FBOs make money.",
    "Money-back guarantee on all products. Do you get the guarantee of a house? Yes: every FBO does. Ask your sponsor "
    "how FBOs make money.",
]

# Known residual leaks (Fable W10d review, FINAL design): each is refused on ec82147 but allowed on every income layer,
# because its referring guarantee is anchored and sits in a question or is conjoined with return/refund wording, with
# the claim outside the referring guarantee's own clause. Documented only; not asserted.
#   "Interested in the guarantee or refund policy? FBOs never worry about bills again."
#   "Is the guarantee or return process really a new car every year?"
#   "Is the guarantee for FBOs a new car every year plus free product?"
#   "Is the guarantee or refund policy why every FBO drives a new car?"
# (Fable W16 review, Fix B: "The guarantee and refund policy for FBOs mean you never work again." is now refused and
# moved to FABLE_W16_LIFESTYLE_BLOCKED below.)

# Conservative: refused as on ec82147. W10c allowed this closing offer, but its referring guarantee has no return,
# refund or product wording in its own sentence; the same exemption let "Our guarantee is simple. Ask your sponsor,
# the office, or the team how members make money." through (Fable W10c review). It keeps the base verdict.
# The two declaratives were allowed by W10c/W10d (anchored); Fable W10d review: declarative "the guarantee ..."
# statements are never set aside, so they keep the base verdict too.
CONSERVATIVE_REFUSED_AS_ON_EC82147 = [
    "Yes, there is a money-back guarantee. Would you like details of the guarantee?",
    "The money-back guarantee applies for 30 days; after that the guarantee no longer applies.",
    "Yes, there's a money-back guarantee. Under the guarantee, you can return the product and get your money back "
    "within 30 days.",
]

# W16b (2026-09-12): a product warranty is a consumer guarantee. Refused on ec82147 and on W10e+W16, because
# "guarantee" paired with the refunded "money" (the first three are the orchestrator's measured texts).
WARRANTY_REFUND_ALLOWED = [
    "The guarantee covers defects; the money is refunded within 30 days.",
    "The guarantee covers defective products and the money is refunded within 30 days.",
    "Products are guaranteed free from defects for 30 days, and your money is refunded if you return them.",
    "The product guarantee covers manufacturing defects. The money is paid back within 30 days.",
    "Our guarantee applies to defective products; your money is reimbursed if you return them.",
    "The guarantee covers repair or replacement of defective products, and the money is refunded if a repair is not "
    "possible.",
    "All products are guaranteed against defects in materials and workmanship for 90 days; we refund the money if a "
    "product fails.",
    "Does the guarantee cover defects? Yes, the guarantee covers defects and the money is refunded within 30 days.",
]

# W16b adversarial, refused before and after: a warranty next to an earnings word, refunded money that recurs, is
# multiplied or earns interest, a second guarantee, a claim after a colon, or an object that is not a defect.
WARRANTY_REFUND_BLOCKED = [
    "The guarantee covers defects and your income; the money is refunded within 30 days.",
    "The guarantee covers your income; the money is refunded within 30 days.",
    "The guarantee covers defects; the money is returned to you every month as profit.",
    "The guarantee covers defects; your money is returned every month.",
    "The guarantee covers defects; your money is paid back twice over.",
    "The guarantee covers defects; the money is refunded with interest.",
    "Every month the guarantee covers defects and your money is returned.",
    "The guarantee covers defective products and guaranteed money back and income.",
    "The guarantee covers defects. We also guarantee you will make money.",
    "The guarantee covers defects; the money is refunded and FBOs make a profit.",
    "The guarantee covers defects: a new car every year and your money back.",
    "The guarantee covers defects and commissions; the money is refunded.",
    "The guarantee covers defects; the money is refunded, plus $5,000 a month.",
    "Warranty on your earnings: the guarantee covers defects and the money is refunded.",
    "The guarantee covers faulty investments; the money is refunded within 30 days.",
    "Products are guaranteed free from defects, and your money is doubled every month.",
    "The guarantee covers defects; the money is returned tenfold.",
    "The guarantee covers defects and your future; you will make money.",
    "The guarantee covers damage to your bank balance; the money is refunded.",
    "Guaranteed money: the guarantee covers defects and the money is refunded within 30 days.",
    "The guarantee covers defects; the money is refunded. Our guarantee to FBOs: you will never worry again.",
    "The guarantee covers defects; the money is refunded. The guarantee for FBOs is that you make money.",
    "The guarantee covers defects and the money is refunded; FBOs earn $5,000 a month.",
    "THE GUARANTEE COVERS DEFECTS; THE MONEY IS RETURNED EVERY MONTH.",
]

# Fable W16 review, Fix A (2026-09-12): refused on W10e and W10e+W16, allowed on every income layer by W16b, because
# refunded money next to a prize, premium, payout, lifestyle word, an addition or a large amount was still masked as a
# refund and the warranty was set aside. Refund wording is now masked only when its clause has none of these.
FABLE_W16_REFUND_PRIZE_BLOCKED = [
    'The guarantee covers defects; your money is returned in full, plus a new car.',
    'The guarantee covers defects; the money is refunded, plus a free holiday.',
    'The guarantee covers defects; the money is refunded, plus a house in Marbella.',
    'The guarantee covers defects; your money is returned with a 20% premium.',
    'The guarantee covers defects; the money is refunded with a 20 percent uplift.',
    'The guarantee covers defects; the money is refunded, plus five thousand for you.',
    'The guarantee covers defects; the money is refunded plus 500 francs.',
    'The guarantee covers defects; the money is refunded plus 500 rand.',
    'THE GUARANTEE COVERS DEFECTS; THE MONEY IS REFUNDED, PLUS A NEW CAR.',
    'Guaranteed free from defects; the money is refunded and you become a millionaire.',
    'The guarantee covers defects; the money is refunded, and returned again, and again.',
    'The guarantee covers defects; the money is refunded with extra.',
    'The guarantee covers defects; the money is refunded and multiplied.',
    'The guarantee covers defects; the money is refunded x10.',
    'The guarantee covers defects; the money is refunded plus a lifetime of residual payments.',
    'Guaranteed against defects. Join and the money is refunded plus a new Mercedes every quarter.',
    'The guarantee covers defects; the money is refunded, plus a passive stream for life.',
    'The guarantee covers defects; the money is refunded plus your recruitment rewards.',
    'The guarantee covers defects; the money is refunded and then some.',
    'The guarantee covers defects; the money is refunded, plus a Rolex.',
    'The guarantee covers defects; the money is refunded, plus a luxury cruise.',
    'The guarantee covers defects; the money is refunded, plus a Tesla and a villa.',
    'The guarantee covers defects; the money is repaid with a 15% premium on top.',
    'The guarantee covers defects; the money is given back plus a prize.',
    'The guarantee covers defects; the money is refunded and the rest is pure upside.',
    'The guarantee covers defects; the money is refunded, plus ten grand.',
    'The guarantee covers defects; the money is refunded, plus 10,000.',
    'The guarantee covers defects; the money is refunded, plus 10k.',
    'The guarantee covers defects; refund of the money plus a jackpot.',
    'The guarantee covers defects; we repay the money and pay you a premium.',
    'The guarantee covers defects; we reimburse the money and pay you for life.',
    'The guarantee covers defects and the money is refunded — a paycheck for life.',
    'The guarantee covers defects; the money is refunded, plus royalties.',
    'The guarantee covers defects; the money is refunded, plus residuals.',
    'The guarantee covers defects; the money is refunded in full plus 50% more.',
    'The guarantee covers defects; the money is refunded and you receive a wealth-building package.',
    "The guarantee covers defects; the money is refunded — and you'll be wealthy.",
    'The guarantee covers defects; the money is refunded, plus a new car.\nThe guarantee covers defects; the money is '
    'refunded, plus a yacht.',
    'The guarantee covers defects; money back plus a new car.',
    'Guaranteed free from defects; money back, plus a new car.',
    'Our guarantee covers all defects for two years; the money is repaid, plus a lifestyle you deserve.',
    'The guarantee covers defects; the money is refunded plus a 5,000 signing gift.',
]

# Fable W16 review, Fix B: wealth and lifestyle outcomes are earnings words. The first four were allowed on every
# base (a pre-existing gap); the next three were refused on W10e and allowed by W16b.
FABLE_W16_LIFESTYLE_BLOCKED = [
    "Guaranteed free from defects, and guaranteed to make you rich.",
    "Money-back guarantee, and you will become a millionaire.",
    "Satisfaction guaranteed. Retire early with us.",
    "Our guarantee: you will never have to work again.",
    "The guarantee covers defects; the money is refunded. You will retire early on us.",
    "The guarantee covers defects; the money is refunded. You never need to work again.",
    "The guarantee covers defects; the money is refunded. Quit your job within a year.",
    # Moved from the documented residual leaks above (Fable W10d review): intentionally changed by Fable W16 review
    # Fix B, allowed before it. The second is the same sentence as measured in Fable's 126-text set (new.txt).
    "The guarantee and refund policy for FBOs mean you never work again.",
    "Money-back guarantee on all products. The guarantee and refund policy for FBOs mean you never work again. Ask "
    "your sponsor how FBOs make money.",
]

# Fable W16 review controls, allowed before and after: ordinary refund timing, payment method and shipping wording, and
# "rich"/"wealth" that are not an outcome for the reader.
FABLE_W16_CONTROLS_ALLOWED = [
    "Money-back guarantee; the money is refunded to the original payment method within 5-10 business days.",
    "The guarantee covers defects; the money is refunded to the original payment method within 5-10 business days.",
    "The guarantee covers defects; the money is refunded in full plus the return shipping.",
    "Money-back guarantee; the money is refunded plus shipping costs.",
    "Money-back guarantee; the money is refunded within 2 to 3 weeks.",
    "Money-back guarantee; the money is refunded 100%.",
    "Money-back guarantee; the money is refunded again if the replacement also fails.",
    "Money-back guarantee on the holiday gift set; the money is refunded within 30 days.",
    "Aloe vera gel is rich in nutrients; we guarantee the quality.",
    "A wealth of information about our guarantee is on the website.",
    "We guarantee a wealth of choice in the catalogue.",
]


def _context(text: str) -> RiskContext:
    return RiskContext(user_message=text, country="US", language="en", role="new_prospect", correlation_id="cid")


def _evaluate(text: str, *, answer: bool) -> GovernanceDecision:
    return governance_engine.evaluate(
        text=text, country="US", language="en", correlation_id="cid", is_generated_answer=answer,
    )


@pytest.mark.parametrize("text", ALLOWED_QUESTIONS + ALLOWED_ANSWERS)
def test_consumer_guarantees_are_not_income_claims_for_the_policy(text) -> None:
    assert IncomeClaimPolicy().evaluate(_context(text)) == []


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("text", ALLOWED_QUESTIONS + ALLOWED_ANSWERS)
def test_consumer_guarantees_pass_governance(text, answer) -> None:
    decision = _evaluate(text, answer=answer)
    assert decision.allowed is True, decision


@pytest.mark.parametrize("text", BLOCKED)
def test_income_guarantees_are_still_flagged_by_the_policy(text) -> None:
    issues = IncomeClaimPolicy().evaluate(_context(text))
    assert [issue.code for issue in issues] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("text", BLOCKED)
def test_income_guarantees_are_still_refused_by_governance(text, answer) -> None:
    decision = _evaluate(text, answer=answer)
    assert decision.allowed is False
    assert decision.provider == "risk_engine"
    assert [issue["code"] for issue in decision.metadata["risk"]["issues"]] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("text", CONSERVATIVE_REFUSED_AS_ON_EC82147)
def test_unanchored_referring_guarantee_is_refused_as_on_ec82147(text, answer) -> None:
    issues = IncomeClaimPolicy().evaluate(_context(text))
    assert [issue.code for issue in issues] == ["INCOME_CLAIM_RISK"]
    decision = _evaluate(text, answer=answer)
    assert decision.allowed is False
    assert decision.provider == "risk_engine"
    assert [issue["code"] for issue in decision.metadata["risk"]["issues"]] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("text", WARRANTY_REFUND_ALLOWED)
def test_warranty_with_refunded_money_is_not_an_income_claim(text) -> None:
    assert IncomeClaimPolicy().evaluate(_context(text)) == []


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("text", WARRANTY_REFUND_ALLOWED)
def test_warranty_with_refunded_money_passes_governance(text, answer) -> None:
    decision = _evaluate(text, answer=answer)
    assert decision.allowed is True, decision


@pytest.mark.parametrize("text", WARRANTY_REFUND_BLOCKED)
def test_warranty_next_to_an_income_claim_is_still_flagged_by_the_policy(text) -> None:
    issues = IncomeClaimPolicy().evaluate(_context(text))
    assert [issue.code for issue in issues] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("text", WARRANTY_REFUND_BLOCKED)
def test_warranty_next_to_an_income_claim_is_still_refused_by_governance(text, answer) -> None:
    decision = _evaluate(text, answer=answer)
    assert decision.allowed is False
    assert decision.provider == "risk_engine"
    assert [issue["code"] for issue in decision.metadata["risk"]["issues"]] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("text", FABLE_W16_REFUND_PRIZE_BLOCKED + FABLE_W16_LIFESTYLE_BLOCKED)
def test_refund_with_a_prize_or_a_lifestyle_promise_is_flagged_by_the_policy(text) -> None:
    issues = IncomeClaimPolicy().evaluate(_context(text))
    assert [issue.code for issue in issues] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("text", FABLE_W16_REFUND_PRIZE_BLOCKED + FABLE_W16_LIFESTYLE_BLOCKED)
def test_refund_with_a_prize_or_a_lifestyle_promise_is_refused_by_governance(text, answer) -> None:
    decision = _evaluate(text, answer=answer)
    assert decision.allowed is False
    assert decision.provider == "risk_engine"
    assert [issue["code"] for issue in decision.metadata["risk"]["issues"]] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("text", FABLE_W16_CONTROLS_ALLOWED)
def test_ordinary_refund_and_rich_wording_is_not_an_income_claim(text, answer) -> None:
    assert IncomeClaimPolicy().evaluate(_context(text)) == []
    decision = _evaluate(text, answer=answer)
    assert decision.allowed is True, decision


def test_gain_or_prize_words_in_the_refund_clause() -> None:
    """Fable W16 Fix A samples: what keeps refunded money counting, and what does not."""
    from app.risk.policies.income_claim_policy import _GAIN_OR_PRIZE_RE

    for text in ("returned every month", "plus a new car", "plus 10,000", "plus ten grand", "with a 20% premium",
                 "returned again and again", "plus a house in Marbella", "pay you a premium"):
        assert _GAIN_OR_PRIZE_RE.search(text), text
    for text in ("within 30 days", "within thirty (30) days", "in 5-10 business days", "refunded 100%",
                 "for the 2 items", "to the original payment method", "plus the return shipping", "plus shipping costs",
                 "again if the replacement also fails", "within 2 to 3 weeks"):
        assert not _GAIN_OR_PRIZE_RE.search(text), text


# --- Orchestrator: the reported question with a stubbed 21.03 answer ------------------


class _Validator:
    def validate(self, *_: object, **__: object) -> ValidationResult:
        return ValidationResult()


class _ReturnPolicyRetriever:
    def retrieve(self, *_: object, **__: object) -> RetrievalResult:
        document = RetrievedDocument(
            id="US:21.03", title="US Company Policy - Sec 21.03",
            content=(
                "21.03 (a) Retail/Preferred Customers are guaranteed 100% product satisfaction. Within thirty (30) "
                "days from the date of purchase, a Retail/Preferred Customer may obtain a new replacement for any "
                "defective product, or cancel the purchase, return the product, and obtain a full refund of the "
                "purchase price, excluding shipping. (c) When FLP products are acquired through the Company's "
                "Webstore and subsequently returned for refund, the Profit and Bonus which was disbursed will be "
                "charged back to the FBO(s) who benefited from the sale."
            ),
            source="s3://approved/us-company-policy.pdf", country="US", language="en", score=0.9,
        )
        return RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.9,
                               metadata={"conversation_intent": "knowledge"})


class _ReturnPolicyRouter:
    def generate(self, *_: object, **__: object) -> ModelResponse:
        return ModelResponse(text=US_21_03_ANSWER, citations=[], confidence=0.9, provider="stub", model_name="stub")


def test_return_policy_answer_is_delivered_not_refused_as_income(monkeypatch) -> None:
    orchestrator = AIOrchestrator(retriever=_ReturnPolicyRetriever(), router=_ReturnPolicyRouter(),
                                  validator=_Validator())
    for name, value in {
        "validate_and_touch_session": lambda *_: None, "has_valid_consent": lambda *_: True,
        "scrub_pii": lambda text, *_, **__: text, "get_session_history": lambda *_: "",
        "get_cache_value": lambda *_: None, "set_cache_value": lambda *_: None,
        "append_session_turn": lambda *_: None, "write_audit_event": lambda *_: None,
    }.items():
        monkeypatch.setattr(chat_orchestrator, name, value)

    response = orchestrator.handle_chat(
        ChatRequest(message="What is the return policy?", sessionId="s", country="US", language="en"), "cid",
    )

    assert response.answer != localized_conversation_response("income_claim", "en")
    assert response.metadata.get("governance_provider") != "risk_engine"
    assert "guaranteed 100% product satisfaction" in response.answer
    assert "refund" in response.answer


# --- Query planner: an income label is verified, not rubber-stamped -------------------


class _VerifierRuntime:
    def __init__(self) -> None:
        self.calls = 0

    def converse(self, **_: object) -> dict:
        self.calls += 1
        return {"output": {"message": {"content": [{"text": '{"income_claim":false}'}]}}}


def test_money_back_guarantee_question_reaches_the_intent_verifier() -> None:
    runtime = _VerifierRuntime()

    intent = providers._verified_conversation_intent(
        "income_claim", "Is there a money-back guarantee?", "US", "en", "cid", runtime,
    )

    assert runtime.calls == 1
    assert intent == ("knowledge", True)


def test_real_income_guarantee_still_skips_the_verifier_as_income() -> None:
    runtime = _VerifierRuntime()

    intent = providers._verified_conversation_intent(
        "income_claim", "Can you guarantee I will make money with the money-back guarantee?", "US", "en", "cid",
        runtime,
    )

    assert runtime.calls == 0
    assert intent == ("income_claim", False)
