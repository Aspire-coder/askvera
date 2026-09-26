"""Bounded phase1 tone invariants for the Codex conversation-style patch.

User decision on 2026-09-12: the language-instruction bullet's clause requiring
headings and support guidance to stay in the user's language was retained
(dropped by the Codex patch); only the tone wording (short paragraphs, no
headings for short answers, no stock phrases/repeated introductions) was
adopted from Codex's rewrite.
"""

import json
import hashlib
from pathlib import Path

from app.evidence import assistant_meta_response, classify_intent
from app.prompts import PromptBuilder
from app.retrieval import RetrievalResult, RetrievedDocument


ROOT = Path(__file__).parents[2]
ROUTES = ROOT / "config" / "conversation_routes.json"
TEMPLATES = ROOT / "app" / "prompts" / "templates.py"
# Updated 2026-09-14 for the Legal-supplied medical/income disclaimer sentences
# (docs/legal/2026-09-07-WORDING_REVIEW_PACKET.md Ask B): every locale's
# medical_claim and income_claim response gained an appended disclaimer
# sentence. That is an intended, reviewed change to "the rest" of this file,
# so the baseline digest below reflects it; anything else changing still
# fails this test. Recomputed a second time the same day after fixing a
# casing typo in the Russian income disclaimer ("Сша" -> "США").
# Updated 2026-09-14: the prompt now forbids raw field trailers and requires
# explicit handling of conflicting directory and policy sources.
# Updated 2026-09-16: the US test plan requires that a declined question also
# offers Customer Care contact. insufficient_evidence gained an appended
# sentence carrying the existing [PHONE] placeholder token (en, fr, es, de,
# nl - the locales that already carry reviewed copy for this key); the
# remaining configured locales continue to translate the English source on
# demand and pick up the new sentence automatically.
# Updated 2026-09-18 (Phase 2, Lane A, task A7): added one new key,
# "reference_clarification", to the "responses" object of every locale that
# already had a "responses" block (en, fr, es, de, nl, it, fi, no, sv) - the
# localized copy asking which of two or more candidate markets an
# unresolved back-reference ("the other one") meant, with a "{candidates}"
# placeholder the orchestrator fills in. No existing key's value changed, and
# "pt" was left with no locale block, as before, since it never had one.
# (Fable review, 2026-09-18, finding T1: this comment previously also named
# "sr" and "ru", but config/conversation_routes.json never gained a
# "reference_clarification" key for either locale; corrected the comment
# only - the hash below and the config file are unchanged.)
# Updated 2026-09-18 (Phase 3, Lane 4, CX localization/rendering task): every
# locale gained the CX_LANES.md message-key set (evidence_missing_detail,
# dependency_unavailable, cross_market_policy_scope,
# international_directory_note, personal_account_limit, partial_answer_gap,
# clarify_field, clarify_country, clarify_role, repair_ack, contact_offer,
# suggest_intro, the four suggest_topic_* keys) plus ten field_label_<field>
# keys for the canonical directory fields (utils/directory_fields.py /
# config/directory_field_vocabulary.py). it/da/fi/no/sr/sv/ru also gained a
# "bedrock_error" entry (none of these seven locales had one before), since
# "dependency_unavailable" reuses that same string per locale. No existing
# key's value changed anywhere. This is purely additive; the new non-English
# copy is Lane 4's own translation and needs native review (see
# docs/conversation-quality/phase3/CX_LANE4_LOCALIZATION.md).
# Updated 2026-09-19 (Fable CX review finding S5): "insufficient_evidence"
# was reviewed copy for only 5 of the 12 route locales (en fr es de nl); the
# other 7 (it da fi no sr sv ru) had none at all, so app/response/cx_render.py's
# render() floored to English for them while the base orchestrator path
# (app.evidence.localized_conversation_response) translated at runtime via
# Bedrock - a mismatch that could deliver a bilingual answer (translated base
# text with an appended English CX sentence) and that always defeated
# app/response/cx_compose.py's generic-copy recognition (evidence_missing_detail
# and the personal-account note never applied) for those 7 locales. Added
# "insufficient_evidence" for it/da/fi/no/sr/sv/ru, matching the exact
# two-paragraph shape (generic sentence; then a "[PHONE]"-placeholder contact
# line) the existing en/fr/es/de/nl entries already use. No existing key's
# value changed anywhere. This new copy is Lane 4's own translation and needs
# native review (see docs/conversation-quality/phase3/CX_LANE4_LOCALIZATION.md).
ROUTES_REST_SHA256 = "3ec04c67e6959926bfca3f738d6517c629854593bc4719225bc5d8110d952213"
# Updated 2026-09-18 (conversation-quality project): four rules edited in
# place, all additive in meaning, with the rendered prompt held under the
# existing 4392-character budget (4247 -> 4381), so no budget assertion moved.
# "role" joined the no-transfer list (FBO vs Preferred Customer figures); the
# qualifications rule now asks for mandatory qualifications, amounts, periods,
# exceptions and alternative routes stated concretely, and for a named contact
# rather than leaving it unnamed; the compound-request rule now also names a part
# the evidence does not establish, keeping "prohibited or unavailable parts". PROMPT_VERSION was bumped with it, because
# both caches key on it. These are instructions only: whether live answers
# improve is unverified without a live run.
# Updated 2026-09-22 (owner-approved, R10 income-disclaimer quoting): the
# compensation rule gained ", even quoted" so the model stops quoting
# "guarantee" from policy 1.01(d), which the unchanged income policy refuses,
# and "Explain bans on medical or income
# claims" was reworded to "Explain medical or income claim bans" (same
# meaning) so the rule stays within the existing 4392-character budget
# without moving any budget assertion. Previous hash:
# a6728cac7378e9889ecca0cd4da8784330129d757610da15a2d5dcd03fd4b90b
# Updated 2026-09-25 (owner decision "Prompt + widen to 1.01(d)", rework of
# income step 2): the compensation rule gained one sentence telling the model
# that the only permitted "guarantee" wording, in English answers, is the
# standalone sentence "Forever makes no guarantees regarding income or
# success." (not after a colon, joined to a clause or reworded; the R10F run
# phrased it differently every time and every answer was refused). Fitted to
# the existing 4392-character budget (4390 -> 4381) by meaning-preserving
# trims only: "state the limitation" -> "say so"; "are not necessarily" ->
# "need not be"; "when necessary" -> "if needed"; "placeholders such as [AGE]
# and [VALUE]" -> "[AGE]/[VALUE] placeholders"; "describe ... as" -> "call";
# "require support" -> "need support"; the COMPLIANCE_PROMPT sentence "Explain
# sourced claims policies and bonus/discount rules without promising earnings
# or projected, average or personalised outcomes." dropped as a duplicate of
# the compensation rule's own "guaranteed, projected, average or personalised
# earnings are not"; and one Oxford comma + line join in the (unhashed) first
# rule. No budget assertion moved. PROMPT_VERSION bumped with it. Previous
# hash: 454c713329759149f748fecc2cd4d8d6687a2595c4b71fd3574d8ab16e997307
# 2026-09-26 review nit: the exception's dash framing became parentheses so the
# model cannot read it as a bullet (same length, 4381). Previous hash:
# 7b6c5e06c376c8d3001de6b68b55d2ec7a3c1b026aad93f52b8ef47795e2fc91
TEMPLATE_LATER_SHA256 = "ca9167a60d5fec652262445fc6a2a8b123a2f9fe4d32e866d5953d151426826a"
EXPECTED = {
    "greeting": "Hi! What can I help you with?",
    "wellbeing": "Thanks for asking! I'm here to help. What's on your mind?",
    "thanks": "You're welcome!",
    "farewell": "Take care!",
    "capability": "I'm AskVera, an AI guide to Forever Living's official policies and international sponsoring directory. I can help explain policy rules or find office contact details in the approved documents.",
    "casual": "Jokes aren't my specialty, but I can help untangle a Forever Living policy question.",
}


def test_only_six_english_response_values_changed_from_head() -> None:
    current = json.loads(ROUTES.read_text(encoding="utf-8"))
    current_responses = current["locales"]["en"]["responses"]
    for key, value in EXPECTED.items():
        assert current_responses[key] == value
    rest = json.loads(json.dumps(current))
    for key in EXPECTED:
        rest["locales"]["en"]["responses"].pop(key)
    digest = hashlib.sha256(json.dumps(rest, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    assert digest == ROUTES_REST_SHA256


def test_prompt_later_rules_match_head_and_rendered_budget_holds() -> None:
    current = TEMPLATES.read_text(encoding="utf-8")
    marker = "- Use only the retrieved authorised chunks"
    assert hashlib.sha256(current[current.index(marker):].encode()).hexdigest() == TEMPLATE_LATER_SHA256
    prompt = PromptBuilder().build(
        user_question="What office contact details are listed for Mexico?",
        conversation="",
        country="CA",
        language="en",
        role="new_prospect",
        retrieval_result=RetrievalResult(
            documents=[RetrievedDocument(
                id="directory-mexico",
                title="Global directory - Mexico",
                content="Mexico office contact details",
                source="s3://kb/global-directory.pdf",
                country="GLOBAL",
                language="en",
                score=0.9,
                metadata={"access_scope": "global", "directory_kind": "international_sponsoring"},
            )],
            citations=[],
            confidence=0.95,
        ),
    )
    assert len(prompt.system_prompt) <= 4392
    assert "complete response in that language" in prompt.system_prompt
    assert "headings and support guidance" in prompt.system_prompt


def test_zero_model_social_routing_keeps_mixed_policy_question_grounded() -> None:
    assert classify_intent("Hi", "en") == "assistant_meta"
    assert assistant_meta_response("Hi", "en") == EXPECTED["greeting"]
    assert classify_intent("Hi, what's the policy for becoming a Manager?", "en") == "policy_fact"
