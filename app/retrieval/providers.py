"""Retrieval provider implementations."""

import hashlib
import json
import re
from typing import Any, Protocol

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.logging import get_logger

from .models import RetrievedDocument, RetrievalResult

LOGGER = get_logger("app.retrieval.providers")

TOKEN_STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "can",
    "become",
    "becomes",
    "does",
    "for",
    "from",
    "have",
    "how",
    "into",
    "level",
    "levels",
    "many",
    "much",
    "need",
    "qualify",
    "qualification",
    "requirements",
    "requirement",
    "the",
    "this",
    "what",
    "when",
    "where",
    "with",
    "you",
    "your",
}

PHRASE_ANCHOR_TERMS = {
    "bonus",
    "bonuses",
    "case",
    "credit",
    "credits",
    "discount",
    "fbo",
    "leadership",
    "manager",
    "novus",
    "personal",
    "retail",
    "supervisor",
    "wholesale",
}

CAPITALIZED_STOPWORDS = {
    "A",
    "An",
    "And",
    "As",
    "At",
    "For",
    "If",
    "In",
    "On",
    "The",
    "To",
    "When",
    "Where",
    "You",
}

RANK_ANCHOR_TERMS = {"manager", "supervisor"}


class RetrievalProvider(Protocol):
    """Interface boundary for retrieval implementations."""

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        """Return approved source documents for a user question."""
        ...


def _metadata_value(metadata: dict[str, Any], *keys: str) -> str:
    """Read the first available metadata value as a string."""
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _reference_score(ref: dict[str, Any]) -> float | None:
    """Extract a retrieval/reranker score from known Bedrock response shapes."""
    metadata = ref.get("metadata", {}) or {}
    candidates = [
        ref.get("score"),
        ref.get("retrievalScore"),
        ref.get("rerankerScore"),
        metadata.get("score"),
        metadata.get("retrieval_score"),
        metadata.get("retrievalScore"),
        metadata.get("reranker_score"),
        metadata.get("rerankerScore"),
    ]
    for candidate in candidates:
        try:
            if candidate is None:
                continue
            score = float(candidate)
            if 0 <= score <= 1:
                return score
            if 1 < score <= 100:
                return score / 100
        except (TypeError, ValueError):
            continue
    return None


def _tokens(text: str) -> set[str]:
    """Return meaningful lowercase tokens for lightweight local reranking."""
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in TOKEN_STOPWORDS
    }


def _numbers(text: str) -> set[str]:
    """Return numeric values that should stay close to the user's question."""
    return set(re.findall(r"\b\d+(?:\.\d+)?(?:\s*(?:-|to)\s*\d+(?:\.\d+)?)?\b", text.lower()))


def _capitalized_phrases(text: str) -> list[str]:
    """Extract entity-like phrases from the user's original question."""
    phrases = re.findall(
        r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,}))*\b",
        text,
    )
    cleaned: list[str] = []
    for phrase in phrases:
        words = phrase.split()
        while words and words[0] in CAPITALIZED_STOPWORDS:
            words = words[1:]
        if words:
            cleaned.append(" ".join(words).lower())
    return cleaned


def _ordered_tokens(text: str) -> list[str]:
    """Return meaningful lowercase tokens in source order."""
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in TOKEN_STOPWORDS
    ]


def _query_phrases(text: str) -> list[str]:
    """Extract exact business phrases from the query without relying on capitalization."""
    phrases = {phrase for phrase in _capitalized_phrases(text) if len(phrase.split()) > 1}
    phrases.update(
        phrase
        for phrase in _capitalized_phrases(text)
        if len(phrase.split()) == 1 and phrase in PHRASE_ANCHOR_TERMS
    )
    tokens = _ordered_tokens(text)
    for size in (4, 3, 2):
        for index in range(0, max(len(tokens) - size + 1, 0)):
            window = tokens[index : index + size]
            if not any(token in PHRASE_ANCHOR_TERMS for token in window):
                continue
            phrases.add(" ".join(window))
    return sorted(phrases, key=lambda phrase: (len(phrase.split()), len(phrase)), reverse=True)


def _expanded_retrieval_query(message: str) -> str:
    """Add policy-style terms to improve matching without changing the user's question."""
    queries = _retrieval_queries(message)
    if len(queries) == 1:
        return message
    return message + "\n\nRelevant policy terms: " + "; ".join(queries[1:9])


def _retrieval_queries(message: str) -> list[str]:
    """Return focused retrieval queries for Bedrock KB search."""
    additions: list[str] = []
    priority_additions: list[str] = []
    message_terms = _tokens(message)
    phrases = _query_phrases(message)

    for phrase in phrases:
        if phrase not in additions:
            additions.append(phrase)

    if {"case", "credit", "credits"} & message_terms:
        for phrase in phrases:
            if len(phrase.split()) == 1 and phrase in {"manager", "supervisor"}:
                priority_additions.append(f"{phrase} is achieved by generating open group case credits")
            if len(phrase.split()) > 1 and any(term in phrase.split() for term in {"manager", "supervisor"}):
                priority_additions.append(f"{phrase} is achieved by generating open group case credits")

    if {"bonus", "bonuses"} & message_terms:
        additions.extend(
            phrase
            for phrase in phrases
            if any(term in phrase.split() for term in {"bonus", "retail", "personal", "wholesale", "novus", "leadership"})
        )

    unique_additions = []
    for addition in [*priority_additions, *additions]:
        cleaned = " ".join(addition.split())
        if cleaned and cleaned not in unique_additions:
            unique_additions.append(cleaned)

    if not unique_additions:
        return [message]
    return [message, *unique_additions[:4]]


def _phrase_score(message: str, document_text: str) -> float:
    """Reward chunks that contain the exact named thing the user asked about."""
    phrases = _query_phrases(message)
    if not phrases:
        return 0.0
    document_lower = document_text.lower()
    matches = sum(1 for phrase in phrases if phrase in document_lower)
    return min(matches / len(phrases), 1.0)


def _policy_term_score(message: str, document_text: str) -> float:
    """Reward source windows with the same policy concepts as the question."""
    query_terms = _tokens(message)
    if not query_terms:
        return 0.0

    document_lower = document_text.lower()
    windows = [
        document_lower[index : index + 420]
        for index in range(0, max(len(document_lower), 1), 210)
    ] or [document_lower]
    best_overlap = 0.0
    for window in windows:
        window_terms = _tokens(window)
        if not window_terms:
            continue
        best_overlap = max(best_overlap, len(query_terms & window_terms) / len(query_terms))
    return best_overlap


def _requirement_heading_score(message: str, document_text: str) -> float:
    """Reward chunks whose requirement heading matches the exact item asked about."""
    message_terms = _tokens(message)
    if not ({"case", "credit", "credits"} & message_terms or {"qualify", "qualification"} & message_terms):
        return 0.0

    document_lower = document_text.lower()
    anchors = [
        phrase
        for phrase in _query_phrases(message)
        if set(phrase.split()) & RANK_ANCHOR_TERMS
    ]
    anchors = sorted(set(anchors), key=lambda phrase: (len(phrase.split()), len(phrase)), reverse=True)
    for anchor in anchors:
        if len(anchor.split()) == 1:
            # Do not treat "Assistant Supervisor" as an exact match for "Supervisor".
            exact_anchor = rf"(?<![a-z]\s)\b{re.escape(anchor)}\b"
        else:
            exact_anchor = rf"\b{re.escape(anchor)}\b"
        exact_patterns = [
            rf"{exact_anchor}\s+is\s+achieved\b",
            rf"{exact_anchor}\s+is\s+earned\b",
            rf"{exact_anchor}\s+requires\b",
            rf"\breaches\s+the\s+level\s+of\s+{re.escape(anchor)}\b",
            rf"\bqualif(?:y|ies|ied)\s+as\s+{re.escape(anchor)}\b",
        ]
        if any(re.search(pattern, document_lower) for pattern in exact_patterns):
            return 1.0

        if len(anchor.split()) == 1:
            qualified_heading = rf"\b[a-z]+(?:\s+[a-z]+){{0,2}}\s+{re.escape(anchor)}\s+is\s+achieved\b"
            if re.search(qualified_heading, document_lower):
                return -1.0
    return 0.0


def _document_relevance(message: str, document: RetrievedDocument) -> float:
    """Score a retrieved document against the user question before prompting."""
    query_tokens = _tokens(message)
    document_text = " ".join([document.title, document.content, document.excerpt])
    document_tokens = _tokens(document_text)
    if not query_tokens or not document_tokens:
        return float(document.score or 0.0)

    overlap = len(query_tokens & document_tokens) / len(query_tokens)
    number_overlap = 0.0
    query_numbers = _numbers(message)
    if query_numbers:
        document_numbers = _numbers(document_text)
        number_overlap = len(query_numbers & document_numbers) / len(query_numbers)

    source_score = float(document.score or 0.0)
    phrase_score = _phrase_score(message, document_text)
    policy_score = _policy_term_score(message, document_text)
    requirement_score = _requirement_heading_score(message, document.content)
    return round(
        (source_score * 0.25)
        + (overlap * 0.15)
        + (policy_score * 0.15)
        + (phrase_score * 0.25)
        + (number_overlap * 0.10)
        + (requirement_score * 0.10),
        6,
    )


def _rerank_documents(message: str, documents: list[RetrievedDocument]) -> list[RetrievedDocument]:
    """Prefer documents whose text best matches the exact user question."""
    return sorted(
        documents,
        key=lambda document: (
            _requirement_heading_score(message, document.content),
            _document_relevance(message, document),
            float(document.score or 0.0),
        ),
        reverse=True,
    )


def _selector_candidate_text(document: RetrievedDocument, index: int) -> str:
    """Format one retrieval candidate for the evidence selector."""
    content = re.sub(r"\s+", " ", document.content or document.excerpt).strip()
    if len(content) > 900:
        content = content[:900].rsplit(" ", 1)[0] + "..."
    return (
        f"[{index}] title: {document.title}\n"
        f"score: {document.score if document.score is not None else 'unknown'}\n"
        f"section text: {content}"
    )


def _parse_selector_ranks(text: str) -> list[int]:
    """Parse selected candidate ranks from a compact JSON model response."""
    stripped = text.strip()
    json_match = re.search(r"\{.*\}", stripped, flags=re.S)
    payload = json.loads(json_match.group(0) if json_match else stripped)
    ranks = payload.get("selected_ranks", [])
    parsed: list[int] = []
    for rank in ranks:
        try:
            value = int(rank)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in parsed:
            parsed.append(value)
    return parsed


def _select_evidence_documents(
    message: str,
    documents: list[RetrievedDocument],
    correlation_id: str,
) -> list[RetrievedDocument]:
    """Use a focused model pass to pick exact evidence sections from candidates."""
    if not settings.BEDROCK_EVIDENCE_SELECTOR_ENABLED or len(documents) <= settings.BEDROCK_RETRIEVAL_RESULT_COUNT:
        return documents

    candidate_limit = max(settings.BEDROCK_RETRIEVAL_RESULT_COUNT, settings.BEDROCK_EVIDENCE_SELECTOR_CANDIDATE_COUNT)
    candidates = documents[:candidate_limit]
    candidate_text = "\n\n".join(_selector_candidate_text(document, index) for index, document in enumerate(candidates, 1))
    system_prompt = (
        "You select evidence for ASK Vera. Your job is not to answer the question; your job is to pick "
        "the candidate sections that most directly support the answer. Prefer the section that governs, "
        "defines, or gives the requirement for the exact topic in the user's question. A section that only "
        "mentions the same words is weaker than a section whose title or first paragraph is about the exact "
        "topic. Do not choose neighboring sections, glossary-only sections, inherited/related-status sections, "
        "or later exception sections when a direct rule/definition/requirement section is available. If the "
        "question asks how to become, qualify, earn, use, file, change, terminate, or whether something is "
        "allowed, prefer procedural or rule sections over general background sections. If the question includes "
        "typos or another language, infer the intended business topic and still choose the direct section. "
        "Return only JSON."
    )
    user_prompt = (
        f"Question:\n{message}\n\n"
        f"Candidate sections:\n{candidate_text}\n\n"
        "Choose sections that directly answer the exact question, even if they are not the highest-scored "
        "candidates. Return JSON exactly like this: {\"selected_ranks\":[1,2,3],\"reason\":\"short reason\"}. "
        f"Choose at most {settings.BEDROCK_RETRIEVAL_RESULT_COUNT} ranks."
    )
    try:
        response = get_aws_clients().bedrock_runtime.converse(
            modelId=settings.BEDROCK_MODEL_ARN,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
        )
        text = response["output"]["message"]["content"][0].get("text", "")
        ranks = _parse_selector_ranks(text)
    except (BotoCoreError, ClientError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        LOGGER.exception("evidence_selector_failed", correlation_id=correlation_id)
        return documents

    selected: list[RetrievedDocument] = []
    for rank in ranks[: settings.BEDROCK_RETRIEVAL_RESULT_COUNT]:
        if 1 <= rank <= len(candidates):
            selected.append(candidates[rank - 1])
    if not selected:
        return documents

    selected_ids = {id(document) for document in selected}
    reordered = [*selected, *[document for document in documents if id(document) not in selected_ids]]
    LOGGER.info(
        "evidence_selector_success",
        correlation_id=correlation_id,
        selected_ranks=ranks[: settings.BEDROCK_RETRIEVAL_RESULT_COUNT],
        candidate_count=len(candidates),
    )
    return reordered


def confidence_from_sources(sources: list[dict[str, Any]]) -> float:
    """Compute answer confidence from scores, source count, and citation quality."""
    if not sources:
        return 0.0
    scores = [float(source["score"]) for source in sources if source.get("score") is not None]
    if scores:
        top_score = max(scores)
        average_score = sum(scores) / len(scores)
        score_confidence = (top_score * 0.7) + (average_score * 0.3)
    else:
        source_count_confidence = min(len(sources), settings.BEDROCK_RETRIEVAL_RESULT_COUNT) * settings.BEDROCK_FALLBACK_SOURCE_WEIGHT
        citation_quality_count = sum(1 for source in sources if source.get("uri") and source.get("excerpt"))
        citation_quality = min(citation_quality_count, 3) * settings.BEDROCK_FALLBACK_CITATION_WEIGHT
        score_confidence = 0.45 + source_count_confidence + citation_quality
    return round(min(score_confidence, 0.99), 3)


def score_summary(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise source scores for retrieval quality logging."""
    scores: list[float] = []
    for source in sources:
        if source.get("score") is None:
            continue
        try:
            scores.append(float(source["score"]))
        except (TypeError, ValueError):
            continue
    return {
        "top_score": round(max(scores), 3) if scores else None,
        "average_score": round(sum(scores) / len(scores), 3) if scores else None,
        "source_count": len(sources),
    }


def source_log_summary(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return compact source details that are useful in production logs."""
    return [
        {
            "title": source.get("title", ""),
            "page": source.get("page", ""),
            "score": source.get("score"),
            "country": source.get("country", ""),
            "language": source.get("language", ""),
        }
        for source in sources[: settings.BEDROCK_RETRIEVAL_RESULT_COUNT]
    ]


def _retrieval_configuration(*, country: str, language: str, managed: bool) -> dict[str, Any]:
    if managed:
        return {
            "managedSearchConfiguration": {
                "numberOfResults": settings.BEDROCK_RETRIEVAL_CANDIDATE_COUNT,
            }
        }
    return {
        "vectorSearchConfiguration": {
            "numberOfResults": settings.BEDROCK_RETRIEVAL_CANDIDATE_COUNT,
            "overrideSearchType": "HYBRID",
            "filter": {
                "andAll": [
                    {"equals": {"key": "country_code", "value": country}},
                    {"equals": {"key": "language", "value": language}},
                    {"equals": {"key": "status", "value": "active"}},
                ]
            },
        }
    }


def _is_managed_kb_configuration_error(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    message = error.get("Message", "")
    return error.get("Code") == "ValidationException" and "managedSearchConfiguration" in message


class BedrockRetrievalProvider:
    """Retrieve approved source documents from Bedrock Knowledge Bases."""

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        """Call the standalone Retrieve API for reliable source scores."""
        retrieval_queries = _retrieval_queries(message)
        retrieval_results: list[dict[str, Any]] = []
        use_managed_search = settings.BEDROCK_RETRIEVAL_CONFIGURATION == "managed"
        try:
            client = get_aws_clients().bedrock_agent_runtime
            for retrieval_query in retrieval_queries:
                try:
                    response = client.retrieve(
                        knowledgeBaseId=settings.BEDROCK_KB_ID,
                        retrievalQuery={"text": retrieval_query},
                        retrievalConfiguration=_retrieval_configuration(
                            country=country,
                            language=language,
                            managed=use_managed_search,
                        ),
                    )
                except ClientError as exc:
                    if use_managed_search or not _is_managed_kb_configuration_error(exc):
                        raise
                    use_managed_search = True
                    LOGGER.info(
                        "retrieval_switching_to_managed_search",
                        correlation_id=correlation_id,
                        knowledge_base_id=settings.BEDROCK_KB_ID,
                    )
                    response = client.retrieve(
                        knowledgeBaseId=settings.BEDROCK_KB_ID,
                        retrievalQuery={"text": retrieval_query},
                        retrievalConfiguration=_retrieval_configuration(
                            country=country,
                            language=language,
                            managed=True,
                        ),
                    )
                retrieval_results.extend(response.get("retrievalResults", []))
        except (BotoCoreError, ClientError):
            LOGGER.exception("retrieval_failed", correlation_id=correlation_id, country=country, language=language, role=role)
            return RetrievalResult(documents=[], citations=[], confidence=0.0, metadata={"provider": "bedrock"})

        documents = [self._document_from_retrieve_result(result) for result in retrieval_results]
        documents = [document for document in documents if document.source]
        documents = self._dedupe_documents(documents)
        documents = _rerank_documents(message, documents)
        documents = _select_evidence_documents(message, documents, correlation_id)
        max_local_relevance = _document_relevance(message, documents[0]) if documents else 0.0
        selected_documents = documents[: settings.BEDROCK_RETRIEVAL_RESULT_COUNT]
        result = self._result(
            selected_documents,
            provider="bedrock",
            candidate_count=len(documents),
            candidate_sources=[document.to_source() for document in documents],
            query_count=len(retrieval_queries),
            max_local_relevance=max_local_relevance,
            strong_local_match=max_local_relevance >= settings.BEDROCK_STRONG_LOCAL_MATCH_THRESHOLD,
        )
        LOGGER.info(
            "retrieval_success",
            correlation_id=correlation_id,
            country=country,
            language=language,
            role=role,
            max_local_relevance=round(max_local_relevance, 3),
            strong_local_match=result.metadata.get("strong_local_match", False),
            **score_summary(result.sources),
            sources=source_log_summary(result.sources),
        )
        return result

    def _dedupe_documents(self, documents: list[RetrievedDocument]) -> list[RetrievedDocument]:
        """Merge duplicate retrieve results while keeping the strongest score."""
        deduped: dict[str, RetrievedDocument] = {}
        for document in documents:
            content_hash = hashlib.sha256(document.content.encode("utf-8")).hexdigest()
            key = "|".join([document.source, document.page, content_hash])
            existing = deduped.get(key)
            if existing is None or float(document.score or 0.0) > float(existing.score or 0.0):
                deduped[key] = document
        return list(deduped.values())

    def _result(self, documents: list[RetrievedDocument], **metadata: Any) -> RetrievalResult:
        sources = [document.to_source() for document in documents]
        return RetrievalResult(documents=documents, citations=sources, confidence=confidence_from_sources(sources), metadata=metadata)

    def _document_from_retrieve_result(self, result: dict[str, Any]) -> RetrievedDocument:
        location = result.get("location", {})
        uri = location.get("s3Location", {}).get("uri", "")
        metadata = result.get("metadata", {}) or {}
        content = result.get("content", {}).get("text", "")
        return RetrievedDocument(
            id=_metadata_value(metadata, "id", "document_id") or uri,
            title=_metadata_value(metadata, "title", "document_title") or uri.rsplit("/", 1)[-1],
            content=content,
            source=uri,
            excerpt=content[:240],
            page=_metadata_value(metadata, "page", "page_number", "x-amz-bedrock-kb-document-page-number"),
            document_version=_metadata_value(metadata, "document_version", "version", "policy_version"),
            country=_metadata_value(metadata, "country_code", "countrycode", "country"),
            language=_metadata_value(metadata, "language", "lang"),
            score=_reference_score(result),
            metadata=metadata,
        )
