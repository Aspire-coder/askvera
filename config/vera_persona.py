"""Central ASK Vera persona and fallback responses."""

ROLE_CONTENT_SCOPES = {
    "new_prospect": (
        "Product information, public company information, published business-plan basics, "
        "rank qualification requirements, bonus definitions, and policy facts that are in "
        "approved public documentation. Do not provide income projections, earnings claims, "
        "guarantees, or personalized financial advice."
    ),
    "active_distributor": "Product information, training, policy, and distributor support content.",
    "compliance_officer": "Full policy, IDS, audit, and compliance reference content.",
}

# Fix B (2026-09-15): enrollment availability moved out of this hardcoded set
# and into config/markets.json's per-market "fboEnrollmentAvailable" field -
# see services/market_config.fbo_enrollment_is_unavailable(), which this
# module's function of the same name now delegates to.

# Fallback copy keeps the same compliance boundaries, but says them in a
# warmer, more helpful voice because these messages often become the whole
# user-facing response.
FALLBACK_RESPONSES = {
    "low_confidence": (
        "I don't have approved information on that specific question yet, so I don't "
        "want to guess. Your upline or Forever Living support can give you an official "
        "answer - want me to point you to how to reach them?"
    ),
    "insufficient_evidence": (
        "The approved policy documents currently available do not contain enough "
        "information to answer this question clearly. Please rephrase the question or "
        "contact Forever Living support for an official answer."
    ),
    "income_claim": (
        "I can't share income projections or guarantees - that's not something I'm "
        "able to speak to. The official Income Disclosure Statement is the right place "
        "for that kind of detail. Individual results may vary. Forever makes no "
        "guarantees on income or success. The Forever Business Owner opportunity and "
        "related incentives are not available to residents of the United States."
    ),
    "medical_claim": (
        "I'm not able to give medical advice or make claims about treating or curing "
        "anything. For anything health-related, a qualified healthcare professional is "
        "really the right person to ask. Forever's products have not been evaluated by "
        "the Food and Drug Administration and are not intended to diagnose, treat, "
        "cure, or prevent any disease."
    ),
    "bedrock_error": (
        "Sorry about that - I'm having a brief technical hiccup reaching the knowledge "
        "base. Mind trying again in a moment?"
    ),
    "off_topic": (
        "I'm sorry, but I can't help with that question. AskVera can help with approved "
        "Forever Living company policies and information from the international sponsoring directory."
    ),
}


def role_scope_for(role: str) -> str:
    """Return the allowed content scope for a user role."""
    return ROLE_CONTENT_SCOPES.get(role, ROLE_CONTENT_SCOPES["new_prospect"])


def fbo_enrollment_is_unavailable(country: str) -> bool:
    """Return whether current approved policy blocks new FBO enrollment.

    Delegates to services.market_config, which reads this from
    config/markets.json's per-market "fboEnrollmentAvailable" field. The
    import is function-local, not at module top, because
    services.market_config's own module-level imports are simple stdlib
    ones today, but this keeps config.vera_persona (loaded very early, by
    app.prompts.builder and app.orchestrator) from ever being able to form
    an import cycle with services.market_config as that module grows.
    """
    from services.market_config import fbo_enrollment_is_unavailable as _config_fbo_enrollment_is_unavailable

    return _config_fbo_enrollment_is_unavailable(country)
