"""Pure request/assessment adapter for a two-factor selector experiment."""

import re
from dataclasses import replace

from app.retrieval.evidence_decision import validate_decision
from app.retrieval.governing_rules import prioritize_activity_rule
from app.retrieval.source_binding import EvidenceSource, validate_support
from scripts.run_selector_fixed_comparison import OLD_SCHEMA, POLARITY_PROMPT, assess, current_prompt, digest


BINDING_SCHEMA = ('{"selected_source_ids":["copy source ID"],"directly_answers_top_rank":true,'
                  '"top_rank_confidence":0.9,"support":[{"source_id":"copy source ID",'
                  '"quote":"short exact source quote"}],"reason":"short reason"}')

RETENTION_INSTRUCTION = (
    "For retaining a sales level or level discount, prefer explicit retention/loss rules; "
    "monthly activity, Leadership Bonus eligibility and incentive payments are separate questions. "
    "Select complementary governing clauses when the question contrasts these concepts. "
)
TARGET_INSTRUCTION = (
    "Distinguish facts supplied as background from the property the user is asking to establish. "
    "Select the governing rule for that requested property, not a rule proving the background fact. "
    "When a user supplies an existing status and asks whether another status follows, evaluate the "
    "explicit requirements for the requested status; do not silently turn this into a question "
    "about retaining the supplied status. If retention or loss itself is asked about, require "
    "an explicit retention/loss rule. Monthly activity, Leadership Bonus eligibility and incentive "
    "payments are distinct properties. Never infer a missing requirement or exception from silence. "
)
VERDICT_SCHEMA = (
    '{"decision":"ANSWER_NO","draft_answer":"short grounded answer",'
    '"selected_source_ids":["copy source ID"],"support":[{"source_id":"copy source ID",'
    '"quote":"short exact source quote"}],"missing_facts":[],"confidence":0.9}'
)
STRUCTURAL_SCHEMA = (
    '{"decision":"ANSWER_NO","draft_answer":"short grounded answer",'
    '"support":[{"source_id":"copy source ID","quote":"short exact source quote"}],'
    '"missing_facts":[],"confidence":0.9}'
)


def structural_system_prompt():
    """Share the tested protocol without frozen source identities or gold labels."""
    system = (POLARITY_PROMPT.replace("selected_ranks", "selected_source_ids")
              .replace("quotes with ranks", "quotes with source_id")
              + " Copy exact Source IDs rather than ordinal ranks. Keep quotes and draft concise.")
    system = system.replace("selected_source_ids must follow that order", "support entries must follow that order")
    return system + (
        " Do not return selected_source_ids or ranks; support is the only source selection. "
        "Every support item contains only source_id and quote. If any required fact is missing, "
        "use INSUFFICIENT_EVIDENCE with an empty draft and support, never ANSWER_NO. "
        "Return exactly decision, draft_answer, support, missing_facts and confidence.")


def structural_decision(payload, case, rows, sources):
    """Validate before ordering, using selected sources only and no gold labels."""
    aliases = alias_registry(sources)
    if not isinstance(payload, dict) or not isinstance(payload.get("support"), list):
        raise ValueError("Invalid support-only decision")
    resolved = []
    for item in payload["support"]:
        if not isinstance(item, dict) or set(item) != {"source_id", "quote"}:
            raise ValueError("Invalid support item")
        if not isinstance(item["source_id"], str) or item["source_id"] not in aliases:
            raise ValueError("Unknown source alias")
        resolved.append({**item, "source_id": aliases[item["source_id"]]})
    decision = validate_decision({**payload, "support": resolved}, sources)
    if len(rows) != len(sources):
        raise ValueError("Source metadata length mismatch")
    metadata = {}
    for row, source in zip(rows, sources):
        if row["content"] != source.content or row["section_id"] != source.section_id:
            raise ValueError("Source metadata mismatch")
        metadata[source.binding_id] = {**row, "binding_id": source.binding_id}
    # A parent section may contain both the requirement and a benefit. Rank the
    # validated quote itself, not unrelated text elsewhere in its parent.
    selected = [{**metadata[quote.source_id], "content": quote.quote, "quote_index": index}
                for index, quote in enumerate(decision.support)]
    ordered = prioritize_activity_rule(case["question"], selected, case.get("language", "en"))
    return replace(decision, support=tuple(decision.support[row["quote_index"]] for row in ordered))


def source_alias(source):
    return "s_" + source.binding_id[:16]


def alias_registry(sources):
    registry = {source_alias(source): source.binding_id for source in sources}
    if len(registry) != len(sources):
        raise ValueError("Ambiguous or duplicate source aliases")
    return registry


def source_rows(case):
    rows = []
    for block in case["blocks"]:
        header, content = block.split("\nText:\n", 1)
        fields = dict(line.split(": ", 1) for line in header.splitlines() if ": " in line)
        rows.append({"block": block, "section_id": fields["Section"], "content": content,
                     "section_title": fields["Title"], "document_type": fields["Document type"],
                     "access_scope": fields["Access scope"]})
    return rows


def make_request(case, variant, snapshot_id):
    if variant not in {"current", "ranking", "binding", "combined", "scoped", "verdict", "structural"}:
        raise ValueError("Unknown experiment variant")
    rows = source_rows(case)
    if variant in {"ranking", "combined", "scoped", "verdict", "structural"}:
        rows = prioritize_activity_rule(case["question"], rows, case.get("language", "en"))
    # Explicitly bind frozen evidence snapshots, not fabricated live provenance.
    sources = [EvidenceSource("frozen-capture:" + snapshot_id, snapshot_id,
                              row["section_id"], case.get("country", "CA"), row["content"]) for row in rows]
    bound = variant in {"binding", "combined", "scoped", "verdict", "structural"}
    alias_registry(sources)
    blocks = []
    for index, (row, source) in enumerate(zip(rows, sources), 1):
        heading = f"Source ID: {source_alias(source)}" if bound else f"Candidate {index}"
        blocks.append(re.sub(r"^Candidate \d+", heading, row["block"]))
    system = current_prompt()
    if variant == "scoped":
        if system.count(RETENTION_INSTRUCTION) != 1:
            raise ValueError("Baseline retention instruction changed; review experiment")
        system = system.replace(RETENTION_INSTRUCTION, TARGET_INSTRUCTION)
    schema = OLD_SCHEMA
    if bound:
        system = system.replace("selected_ranks", "selected_source_ids")
        system += (" Select by the exact Source ID, never ordinal positions. For every selected source "
                   "include one short verbatim quote in support using that same source_id. "
                   "Do not shorten IDs, relocate quotes, combine sentences or use ellipses. "
                   "If you select no sources, support must be empty. Keep reason under 15 words. "
                   "Return only the JSON object.")
        schema = BINDING_SCHEMA
    if variant in {"verdict", "structural"}:
        # Reuse the recorded polarity protocol, now with ranked evidence and stable binding.
        system = (POLARITY_PROMPT.replace("selected_ranks", "selected_source_ids")
                  .replace("quotes with ranks", "quotes with source_id")
                  + " Copy exact Source IDs rather than ordinal ranks. Keep quotes and draft concise.")
        schema = VERDICT_SCHEMA
        if variant == "structural":
            system = structural_system_prompt()
            schema = STRUCTURAL_SCHEMA
    user = (f'User question:\n{case["question"]}\n\nCandidate sections:\n'
            + "\n\n".join(blocks) + f"\n\nSelect up to 5 sources. Return JSON exactly like this: {schema}.")
    return {"system": [{"text": system}], "messages": [{"role": "user", "content": [{"text": user}]}]}, rows, sources


def assess_bound(payload, case, rows, sources):
    flag = payload.get("directly_answers_top_rank")
    ids = payload.get("selected_source_ids")
    if type(flag) is not bool or not isinstance(ids, list) or len(ids) > 5:
        return False, "invalid bound decision"
    aliases = alias_registry(sources)
    lookup = {source_alias(source): index + 1 for index, source in enumerate(sources)}
    if any(not isinstance(key, str) or key not in lookup for key in ids) or len(set(ids)) != len(ids):
        return False, "unknown or duplicate source ID"
    support = payload.get("support")
    if ids:
        try:
            resolved = [{**item, "source_id": aliases[item["source_id"]]} for item in support]
            bound = validate_support(resolved, sources)
        except (ValueError, KeyError, TypeError) as exc:
            return False, str(exc)
        if tuple(aliases[key] for key in ids) != bound:
            return False, "selection and quoted source order differ"
    elif support != []:
        return False, "support without selection"
    translated = {**payload, "selected_ranks": [lookup[key] for key in ids]}
    return assess(translated, {**case, "blocks": [row["block"] for row in rows]}, "current")


def assessment(payload, case, variant, rows, sources):
    if variant == "structural":
        try:
            decision = structural_decision(payload, case, rows, sources)
        except (ValueError, KeyError, TypeError) as exc:
            return False, str(exc)
        supported = decision.decision != "INSUFFICIENT_EVIDENCE"
        if supported and decision.decision != case.get("polarity"):
            return False, "wrong answer polarity"
        ranks = {source.binding_id: index + 1 for index, source in enumerate(sources)}
        return assess({"directly_answers_top_rank": supported,
                       "selected_ranks": [ranks[key] for key in decision.source_ids]},
                      {**case, "blocks": [row["block"] for row in rows]}, "current")
    if variant == "verdict":
        if "directly_answers_top_rank" in payload or "answer_supported" in payload:
            return False, "mixed decision schemas"
        verdict = payload.get("decision")
        if verdict not in {"ANSWER_YES", "ANSWER_NO", "ANSWER_FACT", "INSUFFICIENT_EVIDENCE"}:
            return False, "invalid verdict"
        supported = verdict != "INSUFFICIENT_EVIDENCE"
        if supported:
            if verdict != case.get("polarity"):
                return False, "wrong answer polarity"
            if payload.get("missing_facts") != [] or not isinstance(payload.get("draft_answer"), str) or not payload["draft_answer"].strip():
                return False, "missing draft or incomplete evidence"
        elif (payload.get("draft_answer") not in ("", None) or payload.get("selected_source_ids") != []
              or payload.get("support") != [] or not isinstance(payload.get("missing_facts"), list)
              or not payload["missing_facts"]):
            return False, "invalid abstention"
        return assess_bound({**payload, "directly_answers_top_rank": supported}, case, rows, sources)
    if variant in {"binding", "combined", "scoped"}:
        return assess_bound(payload, case, rows, sources)
    return assess(payload, {**case, "blocks": [row["block"] for row in rows]}, "current")


def prepare_requests(cases, snapshot_id, variants=("current", "ranking", "binding", "combined")):
    requests = []
    for case in cases:
        for variant in variants:
            request, rows, sources = make_request(case, variant, snapshot_id)
            requests.append({"case": case, "variant": variant, "request": request,
                             "request_sha256": digest(request), "rows": rows,
                             "sources": [source.__dict__ for source in sources]})
    return requests
