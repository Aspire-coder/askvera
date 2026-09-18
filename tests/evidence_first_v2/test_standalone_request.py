"""Adversarial offline V2-02 tests for bounded, fail-closed interpretation."""
from __future__ import annotations

from dataclasses import replace
import re
import unittest

from app.experimental.evidence_first_v2 import Ambiguity, AmbiguityCode, ContextField, ContextSource, ContextUse, InterpreterOutput, PlaceStatus, ScopeIntent, StandaloneRequest, StandaloneRequestBuilder, StructuredContext, Turn, TurnSpeaker, V2Request, resolve_standalone_scope
from app.experimental.evidence_first_v2.context import MAX_AMBIGUITY_DETAIL_CHARACTERS, MAX_CONTEXT_CHARACTERS, MAX_CONTEXT_TURNS
from app.experimental.evidence_first_v2.standalone import MAX_AMBIGUITIES, MAX_CONTEXT_USES, MAX_REQUEST_CHARACTERS


_DETAILS = {
    AmbiguityCode.UNKNOWN_EXPLICIT_PLACE: "current destination requires clarification",
    AmbiguityCode.UNKNOWN_CURRENT_INTENT: "current request requires clarification",
    AmbiguityCode.COMPOUND_REQUEST: "current request has multiple branches",
    AmbiguityCode.MULTIPLE_CURRENT_PLACES: "current request has multiple destinations",
}


def _aliases() -> dict[str, str | None]:
    return {"Kenya": "KE", "Belgium": "BE", "Belgique": "BE", "Québec": "CA", "Atlantis": None}


def _request(message: str, request_id: str = "request-1", turns: tuple[Turn, ...] = ()) -> V2Request:
    return V2Request(request_id, message, "US", "en-US", "FBO", "2026.09", turns=turns)


def _use(field: ContextField, text: str, value: str, source: ContextSource = ContextSource.CURRENT_REQUEST, turn_index: int | None = None, start: int | None = None) -> ContextUse:
    start = text.index(value) if start is None else start
    return ContextUse(field, source, value, start, start + len(value), turn_index)


def _numbers(message: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in re.finditer(r"[0-9]+(?:[.,][0-9]+)?", message))


def _uses(message: str, *, negated: bool = False, numbers: tuple[str, ...] | None = None) -> tuple[ContextUse, ...]:
    values = _numbers(message) if numbers is None else numbers
    items = [_use(ContextField.INTENT, message, message), _use(ContextField.STANDALONE_MEANING, message, message)]
    for match in re.finditer(r"[0-9]+(?:[.,][0-9]+)?", message):
        items.append(ContextUse(ContextField.NUMBER, ContextSource.CURRENT_REQUEST, match.group(0), match.start(), match.end()))
    if negated:
        value = "not" if "not" in message.lower() else "No"
        items.append(_use(ContextField.NEGATION, message, value))
    assert tuple(item.value for item in items if item.field is ContextField.NUMBER) == values
    return tuple(items)


def _ambiguities(*codes: AmbiguityCode) -> tuple[Ambiguity, ...]:
    return tuple(Ambiguity(code, _DETAILS[code]) for code in codes)


def _output(request: V2Request, intent: ScopeIntent = ScopeIntent.INTERNATIONAL_SPONSORING, *, session: str = "session-1", status: PlaceStatus = PlaceStatus.NONE, explicit: str | None = None, market: str | None = None, negated: bool = False, numbers: tuple[str, ...] | None = None, text: str | None = None, uses: tuple[ContextUse, ...] | None = None, ambiguities: tuple[Ambiguity, ...] = ()) -> InterpreterOutput:
    values = _numbers(request.message) if numbers is None else numbers
    return InterpreterOutput(request.request_id, session, intent, request.message if text is None else text, status, explicit_place=explicit, requested_directory_market=market, negated=negated, number_tokens=values, context_uses=_uses(request.message, negated=negated, numbers=values) if uses is None else uses, ambiguities=ambiguities)


def _builder(output: InterpreterOutput, aliases: dict[str, str | None] | None = None) -> StandaloneRequestBuilder:
    return StandaloneRequestBuilder(lambda _request, _context: output, _aliases() if aliases is None else aliases)


class StandaloneRequestTests(unittest.TestCase):
    def test_only_exact_positive_followup_can_inherit_prior_user_market(self) -> None:
        history = StructuredContext("session-1", turns=(Turn(TurnSpeaker.USER, "Kenya"),))
        history_market = _use(ContextField.REQUESTED_DIRECTORY_MARKET, "Kenya", "Kenya", ContextSource.HISTORY, 0)
        followup = _request("What about the telephone?")
        positive = _output(followup, status=PlaceStatus.IMPLIED_FROM_HISTORY, market="KE", uses=_uses(followup.message) + (history_market,))
        self.assertEqual(_builder(positive).build(followup, history).requested_directory_market, "KE")
        for message in ("Zanzibar telephone?", "Atlantis telephone?", "Belgique telephone?", "Que\u0301bec telephone?", "Ｋｅｎｙａ telephone?", "xKenya telephone?"):
            request = _request(message)
            bypass = _output(request, status=PlaceStatus.IMPLIED_FROM_HISTORY, market="KE", uses=_uses(message) + (history_market,))
            with self.assertRaises(ValueError):
                _builder(bypass).build(request, history)
            if message == "Belgique telephone?":
                continue
            if message == "Atlantis telephone?":
                clarified = _output(request, status=PlaceStatus.EXPLICIT_UNKNOWN, explicit="Atlantis", uses=_uses(message) + (_use(ContextField.PLACE, message, "Atlantis"),), ambiguities=_ambiguities(AmbiguityCode.UNKNOWN_EXPLICIT_PLACE))
            else:
                clarified = _output(request, status=PlaceStatus.NONE, ambiguities=_ambiguities(AmbiguityCode.UNKNOWN_EXPLICIT_PLACE))
            self.assertTrue(_builder(clarified).build(request, history).requires_clarification)
        registered = _request("Belgique telephone?")
        resolved = _output(registered, status=PlaceStatus.EXPLICIT_RESOLVED, explicit="Belgique", market="BE", uses=_uses(registered.message) + (_use(ContextField.PLACE, registered.message, "Belgique"),))
        self.assertEqual(_builder(resolved).build(registered, history).requested_directory_market, "BE")

    def test_scope_handoff_refuses_every_clarification_and_unvalidated_destination(self) -> None:
        cases = (("Tell me more", ScopeIntent.INTERNATIONAL_SPONSORING, (), PlaceStatus.NONE), ("Zanzibar telephone?", ScopeIntent.INTERNATIONAL_SPONSORING, _ambiguities(AmbiguityCode.UNKNOWN_EXPLICIT_PLACE), PlaceStatus.NONE), ("Kenya and Belgium telephone?", ScopeIntent.INTERNATIONAL_SPONSORING, _ambiguities(AmbiguityCode.MULTIPLE_CURRENT_PLACES), PlaceStatus.NONE), ("Can I sponsor in Kenya and what is the hotline?", ScopeIntent.INTERNATIONAL_SPONSORING, _ambiguities(AmbiguityCode.COMPOUND_REQUEST), PlaceStatus.EXPLICIT_RESOLVED))
        for message, intent, ambiguities, status in cases:
            request = _request(message)
            uses = _uses(message)
            kwargs: dict[str, object] = {"status": status, "ambiguities": ambiguities, "uses": uses}
            if status is PlaceStatus.EXPLICIT_RESOLVED:
                kwargs.update(explicit="Kenya", market="KE", uses=uses + (_use(ContextField.PLACE, message, "Kenya"),))
            if message == "Tell me more":
                kwargs["ambiguities"] = _ambiguities(AmbiguityCode.UNKNOWN_CURRENT_INTENT)
            result = _builder(_output(request, intent, **kwargs)).build(request, StructuredContext("session-1"))
            with self.assertRaisesRegex(ValueError, "clarification"):
                resolve_standalone_scope(result)
        request = _request("Kenya telephone?")
        output = _output(request, status=PlaceStatus.EXPLICIT_RESOLVED, explicit="Kenya", market="KE", uses=_uses(request.message) + (_use(ContextField.PLACE, request.message, "Kenya"),))
        self.assertEqual(resolve_standalone_scope(_builder(output).build(request, StructuredContext("session-1"))).directory_market, "KE")

    def test_interpreter_receives_rebuilt_request_and_contiguous_context_only(self) -> None:
        raw_turns = tuple(Turn(TurnSpeaker.ASSISTANT, str(index)) for index in range(100))
        request = _request("What is the policy?", turns=raw_turns)
        output = _output(request, ScopeIntent.COMPANY_POLICY)
        seen: list[tuple[int, int]] = []
        def spy(interpreter_request: V2Request, context: StructuredContext) -> InterpreterOutput:
            seen.append((len(interpreter_request.turns), len(context.turns)))
            return output
        result = StandaloneRequestBuilder(spy, _aliases()).build(request, StructuredContext("session-1", turns=raw_turns))
        self.assertEqual(seen, [(0, MAX_CONTEXT_TURNS)])
        self.assertTrue(result.context_truncated)
        stale = StructuredContext("session-1", turns=(Turn(TurnSpeaker.USER, "Kenya"), Turn(TurnSpeaker.USER, "Belgium" * (MAX_CONTEXT_CHARACTERS + 1))))
        followup = _request("telephone?")
        kenya = _use(ContextField.REQUESTED_DIRECTORY_MARKET, "Kenya", "Kenya", ContextSource.HISTORY, 0)
        blocked = _output(followup, status=PlaceStatus.IMPLIED_FROM_HISTORY, market="KE", uses=_uses(followup.message) + (kenya,))
        with self.assertRaises(ValueError):
            _builder(blocked).build(followup, stale)

    def test_limits_and_canonical_ambiguities_reject_hidden_output_channels(self) -> None:
        request = _request("What is the policy?")
        with self.assertRaisesRegex(ValueError, "request message"):
            _builder(_output(request, ScopeIntent.COMPANY_POLICY)).build(_request("x" * (MAX_REQUEST_CHARACTERS + 1)), StructuredContext("session-1"))
        with self.assertRaisesRegex(ValueError, "standalone_message"):
            _output(request, ScopeIntent.COMPANY_POLICY, text="x" * (MAX_REQUEST_CHARACTERS + 1))
        with self.assertRaisesRegex(ValueError, "detail"):
            Ambiguity(AmbiguityCode.UNKNOWN_CURRENT_INTENT, "x" * (MAX_AMBIGUITY_DETAIL_CHARACTERS + 1))
        with self.assertRaisesRegex(ValueError, "canonical"):
            _output(request, ScopeIntent.COMPANY_POLICY, ambiguities=(Ambiguity(AmbiguityCode.UNKNOWN_CURRENT_INTENT, "Kenya from another session"),))
        uses = _uses(request.message) * (MAX_CONTEXT_USES + 1)
        with self.assertRaisesRegex(ValueError, "collection limit"):
            _output(request, ScopeIntent.COMPANY_POLICY, uses=uses)
        with self.assertRaisesRegex(ValueError, "collection limit"):
            _output(request, ScopeIntent.COMPANY_POLICY, ambiguities=_ambiguities(*([AmbiguityCode.UNKNOWN_CURRENT_INTENT] * (MAX_AMBIGUITIES + 1))))

    def test_compounds_channels_unknown_branch_and_false_positive_controls(self) -> None:
        for message in ("Am I permitted to sponsor in Kenya, and whom can I email?", "Can I recruit in Kenya; what is the WhatsApp number?", "May I sponsor in Kenya and what is the address?", "Puis-je parrainer au Kenya, and what is the hotline?", "Kenya hotline and explain bonuses"):
            request = _request(message)
            uses = _uses(message) + (_use(ContextField.PLACE, message, "Kenya"),)
            collapsed = _output(request, status=PlaceStatus.EXPLICIT_RESOLVED, explicit="Kenya", market="KE", uses=uses)
            with self.assertRaisesRegex(ValueError, "compound"):
                _builder(collapsed).build(request, StructuredContext("session-1"))
            flagged = _output(request, status=PlaceStatus.EXPLICIT_RESOLVED, explicit="Kenya", market="KE", uses=uses, ambiguities=_ambiguities(AmbiguityCode.COMPOUND_REQUEST))
            self.assertTrue(_builder(flagged).build(request, StructuredContext("session-1")).requires_clarification)
        policy = _request("What is the office policy?")
        self.assertFalse(_builder(_output(policy, ScopeIntent.COMPANY_POLICY)).build(policy, StructuredContext("session-1")).requires_clarification)
        negated = _request("I do not want eligibility advice, only Kenya telephone.")
        directory = _output(negated, status=PlaceStatus.EXPLICIT_RESOLVED, explicit="Kenya", market="KE", negated=True, uses=_uses(negated.message, negated=True) + (_use(ContextField.PLACE, negated.message, "Kenya"),))
        self.assertFalse(_builder(directory).build(negated, StructuredContext("session-1")).requires_clarification)
        hotline = _request("Kenya hotline?")
        output = _output(hotline, status=PlaceStatus.EXPLICIT_RESOLVED, explicit="Kenya", market="KE", uses=_uses(hotline.message) + (_use(ContextField.PLACE, hotline.message, "Kenya"),))
        self.assertFalse(_builder(output).build(hotline, StructuredContext("session-1")).requires_clarification)

    def test_registry_is_immutable_deterministic_and_original_span_safe(self) -> None:
        request = _request("Kenya telephone?")
        output = _output(request, status=PlaceStatus.EXPLICIT_RESOLVED, explicit="Kenya", market="KE", uses=_uses(request.message) + (_use(ContextField.PLACE, request.message, "Kenya"),))
        builder = _builder(output)
        identity = builder.registry_identity
        with self.assertRaises(TypeError):
            builder._place_aliases["kenya"] = "US"  # type: ignore[index]
        with self.assertRaises(AttributeError):
            builder._place_aliases = ()
        self.assertEqual(builder.registry_identity, identity)
        self.assertEqual(builder.build(request, StructuredContext("session-1")).requested_directory_market, "KE")
        for message in ("ßKenya telephone?", "İKenya telephone?", "Kenya2 telephone?", "中Kenya telephone?", "Kenyaع telephone?", "Ｋｅｎｙａ telephone?", "Que\u0301bec telephone?"):
            denied = _request(message)
            fallback = _output(denied, status=PlaceStatus.IMPLIED_FROM_HISTORY, market="KE", uses=_uses(message) + (_use(ContextField.REQUESTED_DIRECTORY_MARKET, "Kenya", "Kenya", ContextSource.HISTORY, 0),))
            with self.assertRaises(ValueError):
                _builder(fallback).build(denied, StructuredContext("session-1", turns=(Turn(TurnSpeaker.USER, "Kenya"),)))
        quebec = _request("Québec telephone?")
        resolved = _output(quebec, status=PlaceStatus.EXPLICIT_RESOLVED, explicit="Québec", market="CA", uses=_uses(quebec.message) + (_use(ContextField.PLACE, quebec.message, "Québec"),))
        self.assertEqual(_builder(resolved).build(quebec, StructuredContext("session-1")).requested_directory_market, "CA")

    def test_multi_place_unknown_history_repeats_and_overlap_are_closed(self) -> None:
        history = StructuredContext("session-1", turns=(Turn(TurnSpeaker.USER, "Kenya"),))
        request = _request("Atlantis and Kenya telephone?")
        for field in ContextField:
            use = _use(field, "Kenya", "Kenya", ContextSource.HISTORY, 0)
            output = _output(request, status=PlaceStatus.NONE, uses=_uses(request.message) + (use,), ambiguities=_ambiguities(AmbiguityCode.UNKNOWN_EXPLICIT_PLACE, AmbiguityCode.MULTIPLE_CURRENT_PLACES))
            with self.assertRaisesRegex(ValueError, "cannot retain history"):
                _builder(output).build(request, history)
        repeated = _request("Kenya, Kenya telephone?")
        output = _output(repeated, status=PlaceStatus.EXPLICIT_RESOLVED, explicit="Kenya", market="KE", uses=_uses(repeated.message) + (_use(ContextField.PLACE, repeated.message, "Kenya"),))
        self.assertFalse(_builder(output).build(repeated, history).requires_clarification)
        overlap = _request("Democratic Republic of Congo telephone?")
        output = _output(overlap, status=PlaceStatus.NONE, ambiguities=_ambiguities(AmbiguityCode.MULTIPLE_CURRENT_PLACES))
        self.assertTrue(_builder(output, {"Congo": "CG", "Democratic Republic of Congo": "CD", "Kenya": "KE"}).build(overlap, history).requires_clarification)

    def test_repeated_numbers_decimal_and_assistant_history_remain_closed(self) -> None:
        repeated = _request("Does policy require 8 plus 8 units?")
        valid = _output(repeated, ScopeIntent.COMPANY_POLICY)
        self.assertEqual(_builder(valid).build(repeated, StructuredContext("session-1")).number_tokens, ("8", "8"))
        single = _uses(repeated.message)[:2] + (_use(ContextField.NUMBER, repeated.message, "8"),)
        with self.assertRaisesRegex(ValueError, "distinct ordered"):
            _builder(_output(repeated, ScopeIntent.COMPANY_POLICY, uses=single)).build(repeated, StructuredContext("session-1"))
        decimal = _request("Does policy require 8.5 units?")
        self.assertEqual(_builder(_output(decimal, ScopeIntent.COMPANY_POLICY)).build(decimal, StructuredContext("session-1")).number_tokens, ("8.5",))
        request = _request("What is the policy?")
        for field in ContextField:
            assistant = Turn(TurnSpeaker.ASSISTANT, "Kenya")
            use = _use(field, assistant.text, "Kenya", ContextSource.HISTORY, 0)
            with self.assertRaisesRegex(ValueError, "assistant turns"):
                _builder(_output(request, ScopeIntent.COMPANY_POLICY, uses=_uses(request.message) + (use,))).build(request, StructuredContext("session-1", turns=(assistant,)))

    def test_bounds_identity_bool_and_one_call_remain_closed(self) -> None:
        request = _request("What is the policy?")
        context = StructuredContext("session-1", turns=tuple(Turn(TurnSpeaker.USER, str(index)) for index in range(MAX_CONTEXT_TURNS + 1)))
        output = _output(request, ScopeIntent.COMPANY_POLICY)
        calls = 0
        def spy(_request: V2Request, _context: StructuredContext) -> InterpreterOutput:
            nonlocal calls
            calls += 1
            return output
        self.assertTrue(StandaloneRequestBuilder(spy, _aliases()).build(request, context).context_truncated)
        self.assertEqual(calls, 1)
        self.assertTrue(StructuredContext("session-1", turns=(Turn(TurnSpeaker.USER, "x" * (MAX_CONTEXT_CHARACTERS + 1)),)).bounded().history_fallback_blocked)
        with self.assertRaisesRegex(ValueError, "turn_index"):
            ContextUse(ContextField.REFERENT, ContextSource.HISTORY, "Kenya", 0, 5, False)
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            _builder(_output(request, ScopeIntent.COMPANY_POLICY, session="other")).build(request, StructuredContext("session-1"))

    def test_scope_handoff_rejects_replace_and_direct_forgery(self) -> None:
        request = _request("Can I sponsor in Kenya and what is the hotline?")
        uses = _uses(request.message) + (_use(ContextField.PLACE, request.message, "Kenya"),)
        output = _output(request, status=PlaceStatus.EXPLICIT_RESOLVED, explicit="Kenya", market="KE", uses=uses, ambiguities=_ambiguities(AmbiguityCode.COMPOUND_REQUEST))
        result = _builder(output).build(request, StructuredContext("session-1"))
        for forged in (replace(result, requires_clarification=False), replace(result, destination_validated=False)):
            with self.assertRaises(ValueError):
                resolve_standalone_scope(forged)
        direct = StandaloneRequest(result.request_id, result.session_id, result.original_message, result.standalone_message, result.intent, result.user_market, result.requested_directory_market, result.role, result.language, result.effective_version, result.negated, result.number_tokens, result.context_uses, result.ambiguities, result.context_truncated, False, True)
        with self.assertRaises(ValueError):
            resolve_standalone_scope(direct)

    def test_followup_uses_only_newest_retained_user_destination(self) -> None:
        request = _request("telephone?")
        for first, first_market, second, second_market in (("Kenya", "KE", "Belgium", "BE"), ("Belgium", "BE", "Kenya", "KE")):
            context = StructuredContext("session-1", turns=(Turn(TurnSpeaker.USER, first), Turn(TurnSpeaker.USER, second)))
            newest = _use(ContextField.REQUESTED_DIRECTORY_MARKET, second, second, ContextSource.HISTORY, 1)
            correct = _output(request, status=PlaceStatus.IMPLIED_FROM_HISTORY, market=second_market, uses=_uses(request.message) + (newest,))
            self.assertEqual(_builder(correct).build(request, context).requested_directory_market, second_market)
            older = _use(ContextField.REQUESTED_DIRECTORY_MARKET, first, first, ContextSource.HISTORY, 0)
            stale = _output(request, status=PlaceStatus.IMPLIED_FROM_HISTORY, market=first_market, uses=_uses(request.message) + (older,))
            with self.assertRaisesRegex(ValueError, "resolution conflicts"):
                _builder(stale).build(request, context)
        unrelated = StructuredContext("session-1", turns=(Turn(TurnSpeaker.USER, "Kenya"), Turn(TurnSpeaker.USER, "hello")))
        kenya = _use(ContextField.REQUESTED_DIRECTORY_MARKET, "Kenya", "Kenya", ContextSource.HISTORY, 0)
        stale = _output(request, status=PlaceStatus.IMPLIED_FROM_HISTORY, market="KE", uses=_uses(request.message) + (kenya,))
        with self.assertRaises(ValueError):
            _builder(stale).build(request, unrelated)

    def test_one_token_or_branches_clarify_but_numeric_units_do_not(self) -> None:
        for message in ("Can I sponsor in Kenya, fax?", "Can I sponsor in Kenya and SMS?", "Can I sponsor in Kenya or fax me?"):
            request = _request(message)
            uses = _uses(message) + (_use(ContextField.PLACE, message, "Kenya"),)
            collapsed = _output(request, status=PlaceStatus.EXPLICIT_RESOLVED, explicit="Kenya", market="KE", uses=uses)
            with self.assertRaisesRegex(ValueError, "compound"):
                _builder(collapsed).build(request, StructuredContext("session-1"))
        numeric = _request("Does policy require 8 and 8.5 units?")
        self.assertFalse(_builder(_output(numeric, ScopeIntent.COMPANY_POLICY)).build(numeric, StructuredContext("session-1")).requires_clarification)

    def test_registry_identity_boundaries_and_case_variants_are_safe(self) -> None:
        request = _request("Kenya telephone?")
        output = _output(request, status=PlaceStatus.EXPLICIT_RESOLVED, explicit="Kenya", market="KE", uses=_uses(request.message) + (_use(ContextField.PLACE, request.message, "Kenya"),))
        self.assertNotEqual(_builder(output, {"A": "US", "B": "CA"}).registry_identity, _builder(output, {"A": "US", "B": "CB"}).registry_identity)
        with self.assertRaises(ValueError):
            _builder(output, {"A\x00US\nB": "CA"})
        history = StructuredContext("session-1", turns=(Turn(TurnSpeaker.USER, "Kenya"),))
        history_use = _use(ContextField.REQUESTED_DIRECTORY_MARKET, "Kenya", "Kenya", ContextSource.HISTORY, 0)
        for message in ("Kenya\u0301 telephone?", "_Kenya telephone?", "Kenya_ telephone?"):
            denied = _request(message)
            bypass = _output(denied, status=PlaceStatus.IMPLIED_FROM_HISTORY, market="KE", uses=_uses(message) + (history_use,))
            with self.assertRaises(ValueError):
                _builder(bypass).build(denied, history)
        for message in ("kenya telephone?", "KENYA telephone?"):
            variant = _request(message)
            place = message.split()[0]
            resolved = _output(variant, status=PlaceStatus.EXPLICIT_RESOLVED, explicit=place, market="KE", uses=_uses(message) + (_use(ContextField.PLACE, message, place),))
            self.assertEqual(_builder(resolved).build(variant, StructuredContext("session-1")).requested_directory_market, "KE")
