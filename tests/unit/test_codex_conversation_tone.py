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
ROUTES_REST_SHA256 = "1e7e6c39bf32b40b77f2293fde4f31e75411a6c6006c56b4940661bd29299003"
TEMPLATE_LATER_SHA256 = "739e46be1d5abece4c3dcadf63c724dd92dbfe6ef806c8bc17ab2af7ea5c5909"
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
