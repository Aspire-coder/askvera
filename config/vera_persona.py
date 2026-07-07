"""Central ASK Vera persona and fallback responses."""

ROLE_CONTENT_SCOPES = {
    "new_prospect": "Product information and public company information only.",
    "active_distributor": "Product information, training, policy, and distributor support content.",
    "compliance_officer": "Full policy, IDS, audit, and compliance reference content.",
}

# Fallback copy keeps the same compliance boundaries, but says them in a
# warmer, more helpful voice because these messages often become the whole
# user-facing response.
FALLBACK_RESPONSES = {
    "low_confidence": (
        "I don't have approved information on that specific question yet, so I don't "
        "want to guess. Your upline or Forever Living support can give you an official "
        "answer - want me to point you to how to reach them?"
    ),
    "income_claim": (
        "I can't share income projections or guarantees - that's not something I'm "
        "able to speak to. The official Income Disclosure Statement is the right place "
        "for that kind of detail."
    ),
    "medical_claim": (
        "I'm not able to give medical advice or make claims about treating or curing "
        "anything. For anything health-related, a qualified healthcare professional is "
        "really the right person to ask."
    ),
    "bedrock_error": (
        "Sorry about that - I'm having a brief technical hiccup reaching the knowledge "
        "base. Mind trying again in a moment?"
    ),
    "off_topic": (
        "That's a bit outside my lane. I'm here to help with Forever Living products, "
        "ordering, policies, and business support - happy to dig into any of those with you."
    ),
}


def role_scope_for(role: str) -> str:
    """Return the allowed content scope for a user role."""
    return ROLE_CONTENT_SCOPES.get(role, ROLE_CONTENT_SCOPES["new_prospect"])
