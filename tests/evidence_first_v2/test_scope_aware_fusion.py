"""Adversarial controls for isolated, scope-aware Evidence-First V2 fusion."""

from __future__ import annotations

import unittest
from copy import deepcopy
from types import SimpleNamespace

from app.experimental.evidence_first_v2.scope_aware_fusion import fuse
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval.providers import _runtime_scope_intent
from scripts import offline_retrieval_replay as replay


def hit(
    identifier: str,
    *,
    country: str = "US",
    scope: str = "country",
    record_country: str = "",
    version: str = "v1",
    content_hash: str = "hash-1",
    section: str = "1.01",
) -> dict[str, object]:
    return {
        "_id": identifier,
        "_source": {
            "id": identifier,
            "country": country,
            "access_scope": scope,
            "source_file": "source.pdf",
            "document_version": version,
            "section_id": section,
            "metadata": {"record_country": record_country, "content_hash": content_hash},
        },
    }


class ScopeAwareFusionTests(unittest.TestCase):
    def test_runtime_scope_boundary_keeps_country_named_policy_ambiguous_without_a_directory_route(self) -> None:
        policy = _runtime_scope_intent(
            "What is Canada's return policy?",
            include_global_documents=True,
            named_markets={"CA"},
            shared_office_markets=set(),
            deterministic_directory_route=False,
        )
        directory = _runtime_scope_intent(
            "What is the Canada office phone number?",
            include_global_documents=True,
            named_markets={"CA"},
            shared_office_markets=set(),
            deterministic_directory_route=True,
        )
        named_policy_without_route = _runtime_scope_intent(
            "What are manager qualifications in Canada?",
            include_global_documents=True,
            named_markets={"CA"},
            shared_office_markets=set(),
            deterministic_directory_route=False,
        )
        self.assertEqual(policy, {
            "provenance": "runtime", "intent": "policy", "decision_source": "deterministic_policy_route",
        })
        self.assertEqual(directory, {
            "provenance": "runtime", "intent": "directory", "decision_source": "deterministic_directory_route",
        })
        self.assertEqual(named_policy_without_route, {
            "provenance": "runtime", "intent": "ambiguous", "decision_source": "planner_global_scope_only",
        })

    def test_orchestrator_marks_only_resolved_follow_up_with_an_opaque_prior_turn_id(self) -> None:
        orchestrator = AIOrchestrator()
        standalone, standalone_context = orchestrator._build_retrieval_query_with_provenance(
            "What is the return policy?", "", "cid", session_id="session-1",
        )
        follow_up, follow_up_context = orchestrator._build_retrieval_query_with_provenance(
            "Tell me more.", "user: What is the return policy?\nvera: A summary.", "cid", session_id="session-1",
        )
        self.assertEqual(standalone, "What is the return policy?")
        self.assertEqual(standalone_context, {"provenance": "runtime", "status": "not_dependent"})
        self.assertIn("Follow-up request: Tell me more.", follow_up)
        self.assertEqual(follow_up_context["status"], "resolved_dependent_follow_up")
        self.assertTrue(follow_up_context["prior_user_turn_id"].startswith("history-user-1-"))

    def test_compatible_directory_intent_protects_one_matching_global_record(self) -> None:
        result = fuse(
            [{"hits": [hit("policy"), hit("directory-a", country="GLOBAL", scope="global", record_country="Hong Kong"), hit("directory-b", country="GLOBAL", scope="global", record_country="Hong Kong")]}],
            ("policy", "directory-b", "directory-a"),
            target_country_names=("Hong Kong",),
            runtime_scope_intent={
                "provenance": "runtime", "intent": "international_sponsoring",
                "decision_source": "deterministic_sponsoring_route",
            },
            authorized_policy_market="US",
        )

        self.assertEqual(result.order[0], "directory-b")
        self.assertEqual(result.protected_global_ids, ("directory-b",))
        self.assertEqual(result.scope_intent_status, "directory_compatible")

    def test_policy_question_naming_another_country_cannot_protect_or_admit_foreign_policy(self) -> None:
        result = fuse(
            [{"hits": [hit("foreign-policy", country="CA"), hit("directory", country="GLOBAL", scope="global", record_country="Canada"), hit("us-policy", country="US")]}],
            ("foreign-policy", "directory", "us-policy"),
            target_country_names=("Canada",),
            runtime_scope_intent={
                "provenance": "runtime", "intent": "policy", "decision_source": "deterministic_policy_route",
            },
            authorized_policy_market="US",
        )

        self.assertEqual(result.protected_global_ids, ())
        self.assertNotIn("foreign-policy", result.order)
        self.assertEqual(result.rejected_policy_ids, ("foreign-policy",))

    def test_missing_or_ambiguous_scope_intent_never_protects_a_global_record(self) -> None:
        searches = [{"hits": [hit("policy"), hit("directory", country="GLOBAL", scope="global", record_country="Réunion Island")]}]
        for scope_intent in (
            None,
            {"provenance": "runtime", "intent": "ambiguous", "decision_source": "planner_global_scope_only"},
        ):
            result = fuse(searches, ("policy", "directory"), target_country_names=("Reunion Island",), runtime_scope_intent=scope_intent, authorized_policy_market="US")
            self.assertEqual(result.protected_global_ids, ())

    def test_direct_fusion_rejects_malformed_or_mismatched_provenance(self) -> None:
        searches = [{"hits": [hit("policy"), hit("directory", country="GLOBAL", scope="global", record_country="Canada")]}]
        invalid_scope_records = (
            {"provenance": "runtime", "intent": "directory", "decision_source": "planner_global_scope_only"},
            {"provenance": "runtime", "intent": "policy", "decision_source": "deterministic_directory_route"},
            {"provenance": "runtime", "intent": "directory", "decision_source": "deterministic_directory_route", "extra": True},
        )
        for scope in invalid_scope_records:
            with self.assertRaisesRegex(ValueError, "runtime_scope_intent"):
                fuse(searches, (), runtime_scope_intent=scope, authorized_policy_market="US")
        for context in (
            {"provenance": "runtime", "status": "resolved_dependent_follow_up", "prior_user_turn_id": "raw prior question"},
            {"provenance": "runtime", "status": "not_dependent", "prior_user_turn_id": "history-user-1-0123456789abcdef"},
            {"provenance": "runtime", "status": "unresolved", "extra": "no"},
        ):
            with self.assertRaisesRegex(ValueError, "context_resolution"):
                fuse(searches, (), context_resolution=context, authorized_policy_market="US")

    def test_conflicting_versions_or_sections_for_one_public_id_fail_closed(self) -> None:
        for conflicting in (hit("same", version="v2"), hit("same", section="2.01"), hit("same", content_hash="hash-2")):
            with self.assertRaisesRegex(ValueError, "conflicting identities"):
                fuse([{"hits": [hit("same"), conflicting]}], (), authorized_policy_market="US")

    def test_current_order_is_eligible_then_stably_deduplicated(self) -> None:
        result = fuse(
            [{"hits": [hit("foreign", country="CA"), hit("stable"), hit("new")]}, {"hits": [hit("new"), hit("stable")]}],
            ("foreign", "stable", "stable", "new", "stable"),
            authorized_policy_market="US",
            current_order_weight=8.0,
        )

        self.assertEqual(result.order, tuple(dict.fromkeys(result.order)))
        self.assertNotIn("foreign", result.order)
        self.assertEqual(result.order[0], "stable")

    def test_trusted_follow_up_fallback_never_returns_duplicates_or_ineligible_policy(self) -> None:
        result = fuse(
            [{"hits": [hit("foreign", country="CA"), hit("stable"), hit("new")]}, {"hits": [hit("new"), hit("stable")]}],
            ("foreign", "stable", "stable", "new"),
            authorized_policy_market="US",
            context_resolution={"provenance": "runtime", "status": "resolved_dependent_follow_up", "prior_user_turn_id": "history-user-9-0123456789abcdef"},
        )

        self.assertTrue(result.used_follow_up_fallback)
        self.assertEqual(result.order, ("stable", "new"))

    def test_replay_rejects_conflicting_merged_versions_instead_of_last_write_wins(self) -> None:
        first = dict(hit("same")["_source"])
        second = dict(first)
        second["document_version"] = "v2"

        with self.assertRaisesRegex(ValueError, "conflicting merged identities"):
            replay._strict_row_index([(first, 2.0), (second, 1.0)])

    def test_replay_reports_pre_and_post_selector_eviction(self) -> None:
        class Provider:
            def _merge_hits(self, text_hits, vector_hits, *_args, **_kwargs):
                return [(dict(item["_source"]), float(item["_score"])) for item in [*text_hits, *vector_hits]]

        def selector(rows, _limit):
            return [rows[0], rows[-1]]

        settings = SimpleNamespace(OPENSEARCH_RESULT_COUNT=2, OPENSEARCH_EVIDENCE_SELECTOR_CANDIDATE_COUNT=2)
        sections = SimpleNamespace(OpenSearchSectionProvider=Provider, _selector_candidates=selector)
        capture = {
            "schema": replay.CAPTURE_SCHEMA,
            "cases": [
                {
                    "case_id": "synthetic-observability",
                    "question": "policy request",
                    "country": "US",
                    "runtime_scope_intent": {
                        "provenance": "runtime", "intent": "policy", "decision_source": "deterministic_policy_route",
                    },
                    "authorized_policy_market": "US",
                    "required_sections": ["US:2.01"],
                    "searches": [
                        {
                            "kind": "text",
                            "weight": 1.0,
                            "hits": [
                                {"_id": "first", "_score": 3.0, "_source": hit("first")["_source"]},
                                {"_id": "required", "_score": 2.0, "_source": hit("required", section="2.01")["_source"]},
                                {"_id": "global", "_score": 1.0, "_source": hit("global", country="GLOBAL", scope="global")["_source"]},
                            ],
                        }
                    ],
                }
            ],
        }

        report = replay.compare_capture({"settings": settings, "sections": sections}, capture)
        case = report["cases"][0]
        selector_effect = case["scope_aware"]["selector"]
        self.assertEqual(case["scope_aware_pre_selector_positions"], {"US:2.01": 2})
        self.assertEqual(case["scope_aware_post_selector_positions"], {"US:2.01": None})
        self.assertEqual(selector_effect["evicted_ids"], ["required"])
        self.assertEqual(selector_effect["quota_added_ids"], ["global"])
        malformed = deepcopy(capture)
        malformed["cases"][0]["runtime_scope_intent"]["extra"] = "not accepted"
        with self.assertRaisesRegex(ValueError, "runtime_scope_intent"):
            replay.compare_capture({"settings": settings, "sections": sections}, malformed)

    def test_malformed_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            fuse([], (), rrf_k=0)
        with self.assertRaises(ValueError):
            fuse([], (), current_order_weight=-1)
        with self.assertRaises(ValueError):
            fuse([], (), authorized_policy_market="USA")
        with self.assertRaises(ValueError):
            fuse([{"weight": -1, "hits": []}], ())
        with self.assertRaises(ValueError):
            fuse([{"hits": "not-a-list"}], ())
