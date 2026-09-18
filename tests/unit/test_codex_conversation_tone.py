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
# already had a "responses" block (en, fr, es, de, nl, it, fi, no, sr, sv,
# ru) - the localized copy asking which of two or more candidate markets an
# unresolved back-reference ("the other one") meant, with a "{candidates}"
# placeholder the orchestrator fills in. No existing key's value changed, and
# "pt" was left with no locale block, as before, since it never had one.
ROUTES_REST_SHA256 = "0098ec016292865497a7f551b1eab12748f97ff67d84edbf41c3464fa2822165"
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
TEMPLATE_LATER_SHA256 = "a6728cac7378e9889ecca0cd4da8784330129d757610da15a2d5dcd03fd4b90b"
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
