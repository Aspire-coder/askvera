"""Offline structural tests for V2-01. No providers or application routes."""

from __future__ import annotations

import unittest

from app.experimental.evidence_first_v2 import (
    EvidenceAccess,
    EvidenceFact,
    EvidenceFirstResult,
    EvidenceReference,
    FactQualifiers,
    ResultStatus,
    ScopeDecision,
    ScopeIntent,
    Turn,
    TurnSpeaker,
    V2Request,
    resolve_scope,
)


def _request(**changes: object) -> V2Request:
    values: dict[str, object] = {
        "request_id": "offline-case-1",
        "message": "What is the policy?",
        "user_market": "us",
        "language": "en-US",
        "role": "FBO",
        "effective_version": "2026.09",
    }
    values.update(changes)
    return V2Request(**values)  # type: ignore[arg-type]


def _local_reference(**changes: object) -> EvidenceReference:
    values: dict[str, object] = {
        "source_id": "US-policy-2026",
        "section_id": "7.03-c",
        "quote": "The qualification applies to active FBOs.",
        "access": EvidenceAccess.LOCAL_POLICY,
        "source_market": "US",
        "language": "en-US",
        "effective_version": "2026.09",
        "role": "FBO",
    }
    values.update(changes)
    return EvidenceReference(**values)  # type: ignore[arg-type]


def _fact() -> EvidenceFact:
    return EvidenceFact("Active FBOs qualify.", _local_reference())


class ContractsAndScopeTests(unittest.TestCase):
    def test_scope_retains_request_context_and_exposes_compatibility(self) -> None:
        request = _request(requested_directory_market="ke")
        decision = resolve_scope(request, ScopeIntent.COMPANY_POLICY)
        cross_language = _local_reference(language="es-MX")

        self.assertEqual(decision.user_market, "US")
        self.assertIsNone(decision.directory_market)
        self.assertEqual((decision.role, decision.language, decision.effective_version), ("FBO", "en-US", "2026.09"))
        compatibility = decision.compatibility(cross_language)
        self.assertTrue(compatibility.permitted)
        self.assertEqual(compatibility.request_language, "en-US")
        self.assertEqual(compatibility.evidence_language, "es-MX")
        self.assertEqual(compatibility.language_rule, "source_language_retained_translation_not_decided")

    def test_company_policy_is_limited_to_matching_market_role_and_version(self) -> None:
        decision = resolve_scope(_request(requested_directory_market="BE"), ScopeIntent.COMPANY_POLICY)

        self.assertTrue(decision.permits(_local_reference()))
        self.assertFalse(decision.permits(_local_reference(source_market="BE")))
        self.assertFalse(decision.permits(_local_reference(role="Manager")))
        self.assertFalse(decision.permits(_local_reference(effective_version="2025.12")))

    def test_international_sponsoring_can_target_another_market_only_through_global_directory(self) -> None:
        request = _request(requested_directory_market="KE", effective_version="directory-2026")
        decision = resolve_scope(request, ScopeIntent.INTERNATIONAL_SPONSORING)
        kenya_directory = EvidenceReference(
            source_id="global-sponsoring-directory", section_id="KE-office", quote="Kenya office contact.",
            access=EvidenceAccess.GLOBAL_DIRECTORY, source_market="GLOBAL", directory_market="KE",
            language="en", effective_version="directory-2026",
        )

        self.assertEqual(decision.directory_market, "KE")
        self.assertTrue(decision.permits(kenya_directory))
        self.assertFalse(decision.permits(EvidenceReference(
            source_id="global-sponsoring-directory", section_id="BE-office", quote="Belgium office contact.",
            access=EvidenceAccess.GLOBAL_DIRECTORY, source_market="GLOBAL", directory_market="BE",
            language="en", effective_version="directory-2026",
        )))

    def test_enums_and_nested_contracts_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "ScopeIntent"):
            resolve_scope(_request(), "company_policy")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "EvidenceAccess"):
            _local_reference(access="local_policy")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "ResultStatus"):
            EvidenceFirstResult("ready", "scope", facts=(_fact(),))  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "TurnSpeaker"):
            Turn("system", "text")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "EvidenceReference"):
            EvidenceFact("claim", "not-a-reference")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "EvidenceFact"):
            EvidenceFirstResult(ResultStatus.READY, "scope", facts=("not-a-fact",))  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "failure_reason is required"):
            EvidenceFirstResult(ResultStatus.BLOCKED, "scope", failure_reasons=(" ",))

    def test_direct_scope_decision_construction_fails_closed(self) -> None:
        values = ("US", None, "FBO", "en-US", "2026.09", "direct")
        with self.assertRaisesRegex(ValueError, "ScopeIntent"):
            ScopeDecision("company_policy", values[0], values[1], EvidenceAccess.LOCAL_POLICY, *values[2:])  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "EvidenceAccess"):
            ScopeDecision(ScopeIntent.COMPANY_POLICY, values[0], values[1], "local_policy", *values[2:])  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "requires LOCAL_POLICY"):
            ScopeDecision(ScopeIntent.COMPANY_POLICY, values[0], values[1], EvidenceAccess.GLOBAL_DIRECTORY, *values[2:])
        with self.assertRaisesRegex(ValueError, "cannot declare a directory market"):
            ScopeDecision(ScopeIntent.COMPANY_POLICY, values[0], "KE", EvidenceAccess.LOCAL_POLICY, *values[2:])
        with self.assertRaisesRegex(ValueError, "ASCII two-letter"):
            ScopeDecision(ScopeIntent.COMPANY_POLICY, "GLOBAL", values[1], EvidenceAccess.GLOBAL_DIRECTORY, *values[2:])
        with self.assertRaisesRegex(ValueError, "requires a directory market"):
            ScopeDecision(ScopeIntent.INTERNATIONAL_SPONSORING, values[0], None, EvidenceAccess.GLOBAL_DIRECTORY, *values[2:])
        with self.assertRaisesRegex(ValueError, "requires GLOBAL_DIRECTORY"):
            ScopeDecision(ScopeIntent.INTERNATIONAL_SPONSORING, values[0], "KE", EvidenceAccess.LOCAL_POLICY, *values[2:])

    def test_collections_are_defensively_tupled_and_alias_safe(self) -> None:
        turns = [Turn(TurnSpeaker.USER, "hello")]
        exceptions = ["except as stated"]
        facts = [_fact()]
        failures = ["missing evidence"]
        request = _request(turns=turns)
        qualifiers = FactQualifiers(exceptions=exceptions)
        ready = EvidenceFirstResult(ResultStatus.READY, "scope", facts=facts)
        blocked = EvidenceFirstResult(ResultStatus.BLOCKED, "scope", failure_reasons=failures)
        turns.append(Turn(TurnSpeaker.ASSISTANT, "reply"))
        exceptions.append("later")
        facts.clear()
        failures.clear()

        self.assertEqual(len(request.turns), 1)
        self.assertEqual(qualifiers.exceptions, ("except as stated",))
        self.assertEqual(len(ready.facts), 1)
        self.assertEqual(blocked.failure_reasons, ("missing evidence",))
        with self.assertRaisesRegex(ValueError, "Turn values"):
            _request(turns=("not-a-turn",))
        with self.assertRaisesRegex(ValueError, "exception is required"):
            FactQualifiers(exceptions=("",))

    def test_market_and_access_combinations_are_structurally_strict(self) -> None:
        with self.assertRaisesRegex(ValueError, "ASCII two-letter"):
            _request(user_market="ÅA")
        with self.assertRaisesRegex(ValueError, "ASCII two-letter"):
            _request(user_market="ß")
        with self.assertRaisesRegex(ValueError, "ASCII two-letter"):
            _request(user_market="ſs")
        with self.assertRaisesRegex(ValueError, "ASCII two-letter"):
            _local_reference(source_market="ß")
        with self.assertRaisesRegex(ValueError, "ASCII two-letter"):
            _local_reference(source_market="ſs")
        with self.assertRaisesRegex(ValueError, "requires a directory market"):
            EvidenceReference(
                source_id="directory", section_id="KE", quote="contact", access=EvidenceAccess.GLOBAL_DIRECTORY,
                source_market="GLOBAL", language="en", effective_version="v1",
            )
        with self.assertRaisesRegex(ValueError, "cannot use GLOBAL"):
            _local_reference(source_market="GLOBAL")
        with self.assertRaisesRegex(ValueError, "cannot declare a directory market"):
            _local_reference(directory_market="KE")
        with self.assertRaisesRegex(ValueError, "must use GLOBAL"):
            EvidenceReference(
                source_id="directory", section_id="KE", quote="contact", access=EvidenceAccess.GLOBAL_DIRECTORY,
                source_market="KE", directory_market="KE", language="en", effective_version="v1",
            )

    def test_ready_result_requires_actual_source_bound_fact(self) -> None:
        with self.assertRaisesRegex(ValueError, "source-bound facts"):
            EvidenceFirstResult(ResultStatus.READY, "policy_restricted_to_user_market")
