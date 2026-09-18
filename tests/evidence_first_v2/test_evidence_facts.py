"""Offline adversarial V2-03 trust-boundary regressions."""
from __future__ import annotations

from dataclasses import replace
import unittest

from app.experimental.evidence_first_v2.contracts import EvidenceAccess, EvidenceFact, FactQualifiers, V2Request
from app.experimental.evidence_first_v2.evidence import (
    AspectSupport, CoverageStatus, FactCandidate, GoverningManifest, GoverningRequirement,
    SourceAnnotation, SourceCatalog, SourceReference, SourceSection, ValidatedFact,
    assess_coverage, build_coverage_branch, canonical_identity, validate_facts,
)
from app.experimental.evidence_first_v2.scope import ScopeIntent, resolve_scope


POLICY = "FBO eligibility requires 18 units before June except waiver."


def ann(text: str, aspect: str, value: str, **kwargs: object) -> SourceAnnotation:
    start = text.index(value)
    return SourceAnnotation(aspect, start, start + len(value), value, **kwargs)


def policy(text: str = POLICY, annotations: tuple[SourceAnnotation, ...] | None = None, **kwargs: object) -> SourceSection:
    annotations = annotations or (ann(text, "role", "FBO"), ann(text, "eligibility", "eligibility"), ann(text, "unit", "18 units"), ann(text, "timing", "before June"), ann(text, "exceptions", "except waiver"))
    values: dict[str, object] = dict(source_id="policy", section_id="eligibility", text=text, access=EvidenceAccess.LOCAL_POLICY, source_market="US", language="en", effective_version="v1", annotations=annotations, role="FBO")
    values.update(kwargs)
    return SourceSection(**values)  # type: ignore[arg-type]


def request(message: str, version: str = "v1") -> V2Request:
    return V2Request("actual-request", message, "US", "en", "FBO", version, requested_directory_market="KE")


def ref(section: SourceSection, quote: str) -> SourceReference:
    start = section.text.index(quote)
    return SourceReference(section.source_id, section.section_id, start, start + len(quote), quote)


def support(section: SourceSection, aspect: str) -> AspectSupport:
    item = next(item for item in section.annotations if item.aspect == aspect)
    return AspectSupport(item.aspect, item.start, item.end, item.value)


def full_candidate(section: SourceSection) -> FactCandidate:
    return FactCandidate(section.text, ref(section, section.text), FactQualifiers(role="FBO", unit="18 units", timing="before June", exceptions=("except waiver",)), tuple(support(section, name) for name in ("role", "eligibility", "unit", "timing", "exceptions")))


class EvidenceFactsTests(unittest.TestCase):
    def test_canonical_identities_are_tuple_safe_and_replay_cannot_cross_catalogs(self) -> None:
        self.assertNotEqual(canonical_identity(("x,eligibility",)), canonical_identity(("x", "eligibility")))
        self.assertNotEqual(canonical_identity(("x|y", "\x00")), canonical_identity(("x", "y\x00")))
        section = policy()
        annotation = next(item for item in section.annotations if item.aspect == "unit")
        requirement = GoverningRequirement(section.source_id, section.section_id, annotation.aspect, annotation.start, annotation.end, annotation.value, "eligibility")
        catalog_a = SourceCatalog.admit((section,), GoverningManifest((requirement,)))
        catalog_b = SourceCatalog.admit((section,), GoverningManifest())
        actual = request("eligibility")
        scope = resolve_scope(actual, ScopeIntent.COMPANY_POLICY)
        fact = validate_facts((full_candidate(catalog_a.sections[0]),), catalog_a, scope)[0]
        branch = build_coverage_branch(actual, scope, catalog_b)
        self.assertNotEqual(catalog_a.identity, catalog_b.identity)
        with self.assertRaisesRegex(ValueError, "does not match current"):
            assess_coverage(actual, (branch,), catalog_b, (fact,))

    def test_actual_request_revalidation_rejects_builder_minted_substitution_and_omission(self) -> None:
        catalog = SourceCatalog.admit((policy(),))
        actual = request("eligibility unit")
        actual_scope = resolve_scope(actual, ScopeIntent.COMPANY_POLICY)
        facts = validate_facts((full_candidate(catalog.sections[0]),), catalog, actual_scope)
        self.assertEqual(assess_coverage(actual, (build_coverage_branch(actual, actual_scope, catalog),), catalog, facts).status, CoverageStatus.COMPLETE)
        substituted = request("unit")
        omitted = request("eligibility")
        with self.assertRaisesRegex(ValueError, "externally held actual"):
            assess_coverage(actual, (build_coverage_branch(substituted, resolve_scope(substituted, ScopeIntent.COMPANY_POLICY), catalog),), catalog, facts)
        with self.assertRaisesRegex(ValueError, "externally held actual"):
            assess_coverage(actual, (build_coverage_branch(omitted, resolve_scope(omitted, ScopeIntent.COMPANY_POLICY), catalog),), catalog, facts)

    def test_document_requirement_metadata_cannot_weaken_defaults(self) -> None:
        source = policy()
        weakened = tuple(replace(item, required_for=("other",)) if item.aspect in {"unit", "timing", "exceptions"} else item for item in source.annotations)
        with self.assertRaisesRegex(ValueError, "cannot set governing"):
            SourceCatalog.admit((replace(source, annotations=weakened),))
        catalog = SourceCatalog.admit((source,))
        section = catalog.sections[0]
        narrow = FactCandidate("FBO eligibility", ref(section, "FBO eligibility"), FactQualifiers(role="FBO"), (support(section, "role"), support(section, "eligibility")))
        actual = request("eligibility")
        scope = resolve_scope(actual, ScopeIntent.COMPANY_POLICY)
        self.assertEqual(assess_coverage(actual, (build_coverage_branch(actual, scope, catalog),), catalog, validate_facts((narrow,), catalog, scope)).status, CoverageStatus.UNCERTAIN)

    def test_cross_section_alternative_requires_trusted_manifest_authorization(self) -> None:
        one_text, two_text = "eligibility one", "eligibility two"
        one = SourceSection("one", "one", one_text, EvidenceAccess.LOCAL_POLICY, "US", "en", "v1", (ann(one_text, "eligibility", "eligibility"),), role_neutral=True)
        two = SourceSection("two", "two", two_text, EvidenceAccess.LOCAL_POLICY, "US", "en", "v1", (ann(two_text, "eligibility", "eligibility"),), role_neutral=True)
        requirements = tuple(GoverningRequirement(section.source_id, section.section_id, "eligibility", 0, 11, "eligibility", "eligibility", "either") for section in (one, two))
        with self.assertRaisesRegex(ValueError, "section-local"):
            SourceCatalog.admit((one, two), GoverningManifest(requirements))
        trusted = SourceCatalog.admit((one, two), GoverningManifest(requirements, frozenset(("either",))))
        self.assertNotEqual(trusted.identity, SourceCatalog.admit((one, two)).identity)

    def test_manifest_rejects_ghost_duplicate_conflicting_and_ambiguous_groups(self) -> None:
        source = policy()
        unit = next(item for item in source.annotations if item.aspect == "unit")
        timing = next(item for item in source.annotations if item.aspect == "timing")
        rule = GoverningRequirement("policy", "eligibility", "unit", unit.start, unit.end, unit.value, "eligibility", "local")
        with self.assertRaisesRegex(ValueError, "known spanning"):
            SourceCatalog.admit((source,), GoverningManifest((), frozenset(("ghost",))))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            SourceCatalog.admit((source,), GoverningManifest((rule, rule)))
        for rules in ((rule, replace(rule, alternative_group="other")), (replace(rule, alternative_group="other"), rule)):
            with self.assertRaisesRegex(ValueError, "conflicting"):
                SourceCatalog.admit((source,), GoverningManifest(rules))
        ambiguous = GoverningManifest((rule, GoverningRequirement("policy", "eligibility", "timing", timing.start, timing.end, timing.value, "unit", "local")))
        with self.assertRaisesRegex(ValueError, "one target"):
            SourceCatalog.admit((source,), ambiguous)
        self.assertIsInstance(SourceCatalog.admit((source,), GoverningManifest((rule,))), SourceCatalog)

    def test_unicode_boundaries_reject_fragments_and_accept_full_multilingual_token(self) -> None:
        for text, value in (("FBO 8\u0301", "8"), ("FBO 8\u203f", "8"), ("FBO ineligible", "eligible")):
            section = policy(text, (ann(text, "role", "FBO"), ann(text, "eligibility", value)))
            with self.assertRaisesRegex(ValueError, "Unicode token"):
                SourceCatalog.admit((section,))
        multilingual = "FBO éligibilité"
        safe = policy(multilingual, (ann(multilingual, "role", "FBO"), ann(multilingual, "éligibilité", "éligibilité")))
        self.assertEqual(SourceCatalog.admit((safe,)).sections[0].annotations[-1].value, "éligibilité")

    def test_adjacent_sign_separator_and_punctuated_negation_contexts_fail_closed(self) -> None:
        for text in ("FBO -8", "FBO +8", "FBO −8", "FBO 8/10", "FBO 8-10", "FBO 8:10", "FBO 8.5", "FBO 8,5"):
            section = policy(text, (ann(text, "role", "FBO"), ann(text, "eligibility", "8")))
            with self.assertRaisesRegex(ValueError, "sign or numeric context"):
                SourceCatalog.admit((section,))
        for text in ("FBO not-eligible", "FBO not: eligible", "FBO never/eligible"):
            section = policy(text, (ann(text, "role", "FBO"), ann(text, "eligibility", "eligible")))
            with self.assertRaisesRegex(ValueError, "explicit negation"):
                SourceCatalog.admit((section,))
        for text in ("FBO value 8 units", "FBO (8)"):
            section = policy(text, (ann(text, "role", "FBO"), ann(text, "eligibility", "8")))
            self.assertIsInstance(SourceCatalog.admit((section,)), SourceCatalog)

    def test_mandatory_sections_annotations_and_explicit_manifest_alternative(self) -> None:
        first_text, second_text = "FBO eligibility first.", "FBO eligibility second."
        first = policy(first_text, (ann(first_text, "role", "FBO"), ann(first_text, "eligibility", "eligibility")), section_id="one")
        second = policy(second_text, (ann(second_text, "role", "FBO"), ann(second_text, "eligibility", "eligibility")), section_id="two")
        catalog = SourceCatalog.admit((first, second))
        actual = request("eligibility")
        scope = resolve_scope(actual, ScopeIntent.COMPANY_POLICY)
        first_admitted = next(item for item in catalog.sections if item.section_id == "one")
        fact = FactCandidate(first_admitted.text, ref(first_admitted, first_admitted.text), FactQualifiers(role="FBO"), (support(first_admitted, "role"), support(first_admitted, "eligibility")))
        self.assertEqual(assess_coverage(actual, (build_coverage_branch(actual, scope, catalog),), catalog, validate_facts((fact,), catalog, scope)).status, CoverageStatus.UNCERTAIN)
        base = policy()
        route_start = POLICY.index("waiver")
        route = SourceAnnotation("route", route_start, route_start + len("waiver"), "waiver")
        configured = replace(base, annotations=base.annotations + (route,))
        rule = GoverningRequirement("policy", "eligibility", "route", route.start, route.end, "waiver", "eligibility", "route")
        alt_catalog = SourceCatalog.admit((configured,), GoverningManifest((rule,)))
        self.assertNotEqual(alt_catalog.identity, SourceCatalog.admit((configured,)).identity)

    def test_existing_fact_wrapper_and_scope_isolation_gates_remain_closed(self) -> None:
        catalog = SourceCatalog.admit((policy(),))
        actual = request("eligibility")
        scope = resolve_scope(actual, ScopeIntent.COMPANY_POLICY)
        genuine = validate_facts((full_candidate(catalog.sections[0]),), catalog, scope)[0]
        forged = ValidatedFact(EvidenceFact("FBO", catalog.sections[0].reference(0, 3), FactQualifiers(role="FBO")), genuine.candidate, genuine.catalog_identity, genuine.scope_identity, genuine.fact_identity)
        branch = build_coverage_branch(actual, scope, catalog)
        with self.assertRaisesRegex(ValueError, "does not match current"):
            assess_coverage(actual, (branch,), catalog, (forged,))
        with self.assertRaisesRegex(ValueError, "does not match current"):
            assess_coverage(actual, (branch,), catalog, (replace(genuine, catalog_identity="forged"),))
