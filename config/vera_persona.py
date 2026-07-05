"""Central ASK Vera persona and fallback responses."""

ROLE_CONTENT_SCOPES = {
    "new_prospect": "Product information and public company information only.",
    "active_distributor": "Product information, training, policy, and distributor support content.",
    "compliance_officer": "Full policy, IDS, audit, and compliance reference content.",
}

FALLBACK_RESPONSES = {
    "low_confidence": "I could not find sufficient approved information for this question. Please contact your upline or Forever Living support if you require an official interpretation.",
    "income_claim": "I cannot provide income projections or guarantees. Please refer to the official Income Disclosure Statement for approved information.",
    "medical_claim": "I cannot provide medical advice or make medical claims. Please speak with a qualified healthcare professional.",
    "bedrock_error": "I am having a brief technical issue reaching the knowledge base. Please try again in a moment.",
    "off_topic": "I can help with Forever Living products, policies, ordering, business support, and approved company information.",
}


def role_scope_for(role: str) -> str:
    """Return the allowed content scope for a user role."""
    return ROLE_CONTENT_SCOPES.get(role, ROLE_CONTENT_SCOPES["new_prospect"])
