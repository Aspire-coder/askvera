"""Final chat response assembly."""

from __future__ import annotations

import re
import unicodedata
from time import perf_counter
from typing import TYPE_CHECKING, Any

from app.metrics import STAGE_RESPONSE_BUILD
from app.metrics.pipeline import record_pipeline_metric
from utils.logging import get_logger

from .models import ChatResponse

if TYPE_CHECKING:
    from app.models.responses import ModelResponse
    from app.retrieval.models import RetrievedDocument, RetrievalResult

LOGGER = get_logger("app.response")

REFERENCE_STOPWORDS = {
    "about",
    "also",
    "and",
    "answer",
    "are",
    "can",
    "does",
    "for",
    "from",
    "have",
    "into",
    "need",
    "that",
    "the",
    "this",
    "with",
    "you",
    "your",
}

# Words that can sit next to a figure without saying what it counts. A figure
# is matched to a source only through its unit or a content word, never through
# one of these: "since 2024 the", "18 or fewer", "€18 per order".
_FIGURE_FUNCTION_WORDS = frozenset({
    # en
    "a", "about", "after", "also", "an", "and", "are", "as", "at", "be", "been", "before", "between", "by",
    "each", "every", "fewer", "for", "from", "have", "in", "into", "is", "least", "less", "more", "most", "must",
    "of", "on", "only", "or", "over", "per", "same", "shall", "should", "since", "than", "that", "the", "then",
    "there", "these", "this", "those", "to", "under", "until", "when", "where", "which", "while", "will", "with",
    "within", "would",
    # fr
    "à", "après", "au", "aux", "avant", "avec", "cette", "comme", "dans", "de", "depuis", "des", "du", "en",
    "entre", "et", "jusqu", "la", "le", "les", "leur", "leurs", "mais", "moins", "nous", "ou", "par", "pendant",
    "plus", "pour", "sans", "selon", "sont", "sous", "un", "une", "vers", "vous",
    # it
    "anche", "come", "con", "da", "dalla", "degli", "della", "delle", "dello", "di", "dopo", "e", "entro", "gli",
    "il", "lo", "meno", "nella", "nelle", "o", "ogni", "oltre", "prima", "questa", "questo", "sono", "su",
    # nl
    "binnen", "deze", "een", "het", "meer", "met", "minder", "naar", "niet", "onder", "sinds", "tussen", "van",
    "vanaf", "voor", "zijn", "zoals", "zonder",
    # no / da / sv
    "att", "av", "bare", "blir", "bliver", "deras", "deres", "denne", "dette", "disse", "efter", "eller", "er",
    "etter", "fler", "flere", "hvis", "i", "ikke", "inden", "innan", "innen", "inom", "inte", "med", "mellan",
    "mellem", "mellom", "mere", "mindre", "minst", "och", "også", "också", "og", "på", "samt", "sedan", "siden",
    "skal", "som", "til", "utan", "uten", "vara", "være",
    # fi
    "aikana", "alle", "enintään", "ennen", "että", "ja", "jälkeen", "kanssa", "kuin", "mutta", "myös", "olla",
    "ovat", "sekä", "sisällä", "tai", "vähintään", "yli",
    # de
    "auch", "bis", "das", "dass", "der", "die", "diese", "dieser", "ein", "eine", "einem", "einen", "einer",
    "gegen", "höchstens", "innerhalb", "je", "mehr", "mindestens", "nach", "nicht", "oder", "ohne", "pro",
    "seit", "sind", "sowie", "über", "und", "unter", "weniger", "werden", "wird", "zwischen",
})

# Units too short to pass as content words. Longer units ("months", "mois",
# "kuukautta", "jaar") qualify as content words on their own.
_FIGURE_SHORT_UNITS = frozenset({
    "%", "an", "ans", "år", "års", "cc", "chf", "czk", "dag", "dkk", "eur", "gbp", "h", "huf", "kg", "km", "kr",
    "l", "md", "mdr", "min", "ml", "mnd", "mån", "nok", "pln", "pv", "ron", "sek", "uke", "usd",
})
_FIGURE_CURRENCY_ALIASES = {"€": "eur", "euro": "eur", "euros": "eur", "$": "usd", "£": "gbp",
                            "kroner": "kr", "kronor": "kr"}

_MONTH_NAMES = frozenset({
    # en
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    # fr
    "janvier", "février", "fevrier", "mars", "avril", "mai", "juin", "juillet", "août", "aout", "septembre",
    "octobre", "novembre", "décembre", "decembre",
    # it
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
    "dicembre",
    # nl
    "januari", "februari", "maart", "mei", "juni", "juli", "augustus", "oktober",
    # no / da / sv / de
    "januar", "jänner", "februar", "märz", "marts", "maj", "augusti", "desember", "dezember",
})
_FINNISH_MONTH = re.compile(r"(?:tammi|helmi|maalis|huhti|touko|kesä|heinä|elo|syys|loka|marras|joulu)kuu\w*")

# Words an answer shares with almost any retrieved passage or directory record.
# Sharing one of them does not show that a passage is about the question asked.
_GENERIC_TOPIC_WORDS = frozenset({
    "business", "bureau", "company", "contact", "contacter", "email", "fbos", "forever", "hours", "kontakt",
    "kontakta", "kontakte", "kontoret", "living", "mail", "office", "opening", "owner", "phone", "policy",
    "politique", "post", "products", "section", "site", "telefon", "telephone", "téléphone", "website",
    "åbningstider", "åpningstider", "öppettider", "horaires", "orari", "openingstijden", "öffnungszeiten",
})
_PERIOD_WORDS = frozenset({
    "année", "années", "anni", "dage", "dagar", "dagen", "dager", "days", "euro", "euros", "giorni", "heures",
    "hours", "jaar", "jahr", "jahre", "jahren", "jaren", "jours", "kronor", "kroner", "kuukauden", "kuukautta",
    "kuukauteen", "maand", "maanden", "måned", "måneder", "månader", "mesi", "mois", "monat", "monate",
    "monaten", "month", "months", "päivää", "percent", "pourcent", "procent", "prosent", "semaines",
    "settimane", "tage", "tagen", "uger", "uker", "veckor", "viikkoa", "vuoden", "vuotta", "week", "weeks",
    "weken", "wochen", "year", "years",
})
# Inflections that leave a topic word the same word ("trip"/"trips").
_TOPIC_SUFFIXES = ("s", "es", "x", "e", "n", "en", "er", "ne", "ar")

# Phone numbers with a country prefix, and unprefixed numbers in three or more
# short groups ("22 33 44 55") but not thousands written with separators
# ("10 000 000"), which the second pattern's caller filters out.
_PREFIXED_PHONE = r"\+\s?\d[\d\s().\-/]{4,}\d"
_GROUPED_DIGITS = r"(?<![\d.,])\d{2,4}(?:[ \-]\d{2,4}){2,}(?![\d.,])"


def _is_month(word: str) -> bool:
    return word in _MONTH_NAMES or bool(_FINNISH_MONTH.fullmatch(word))


class ResponseBuilder:
    """Assemble canonical chat responses without calling external services."""

    def build(
        self,
        *,
        model_response: ModelResponse,
        retrieval_result: RetrievalResult,
        correlation_id: str,
        session_metadata: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """Build the final internal chat response."""
        started = perf_counter()
        success = False
        try:
            guardrail_intervened = model_response.finish_reason == "guardrail_intervened"
            failure_layer = (
                "aws_guardrail"
                if guardrail_intervened
                else (model_response.metadata or {}).get("failure_layer")
            )
            chat_response = ChatResponse(
                answer=model_response.text,
                # A guardrail response is safety copy, not an answer grounded in the
                # retrieved policy sections. Never present unrelated retrieval as its source.
                citations=[] if guardrail_intervened else self._supporting_citations(
                    model_response.text,
                    retrieval_result,
                    session_country=str((session_metadata or {}).get("country") or ""),
                ),
                suggestions=[],
                cards=[],
                confidence=model_response.confidence,
                correlation_id=correlation_id,
                metadata={
                    "provider": model_response.provider,
                    "model_name": model_response.model_name,
                    "latency_ms": model_response.latency_ms,
                    "token_usage": model_response.token_usage,
                    "finish_reason": model_response.finish_reason,
                    "failure_layer": failure_layer,
                    "response_source": "guardrail" if guardrail_intervened else "model",
                    "retrieval_confidence": retrieval_result.confidence,
                    "retrieved_document_count": len(retrieval_result.documents),
                    "correlation_id": correlation_id,
                    **(model_response.metadata or {}),
                    **(session_metadata or {}),
                },
            )
            LOGGER.info(
                "response_builder_chat_response_built",
                correlation_id=correlation_id,
                provider=model_response.provider,
                model_name=model_response.model_name,
                confidence=model_response.confidence,
                source_count=len(model_response.citations),
                response_source=chat_response.metadata.get("cache", "model"),
                finish_reason=chat_response.metadata.get("finish_reason"),
                failure_layer=chat_response.metadata.get("failure_layer"),
            )
            success = True
            return chat_response
        finally:
            record_pipeline_metric(
                stage=STAGE_RESPONSE_BUILD,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=success,
                correlation_id=correlation_id,
                metadata={
                    "responseSource": chat_response.metadata.get("cache", "model") if success else "error",
                    "citationCount": len(chat_response.citations) if success else 0,
                    "confidence": round(float(chat_response.confidence or 0.0), 3) if success else 0.0,
                },
            )

    def from_cached(self, cached: dict[str, Any], correlation_id: str) -> ChatResponse:
        """Build a canonical response from the existing cache shape."""
        original_usage = dict(cached.get("token_usage") or {})
        saved_input_tokens = int(original_usage.get("inputTokens", original_usage.get("input_tokens", 0)) or 0)
        saved_output_tokens = int(original_usage.get("outputTokens", original_usage.get("output_tokens", 0)) or 0)
        chat_response = ChatResponse(
            answer=str(cached.get("response", "")),
            citations=list(cached.get("sources", [])),
            suggestions=[],
            cards=[],
            confidence=float(cached.get("confidence", 0.0) or 0.0),
            correlation_id=correlation_id,
            metadata={
                "cache": "hit",
                "correlation_id": correlation_id,
                "provider": "cache",
                "model_name": str(cached.get("model_name") or "cached response"),
                "token_usage": {"inputTokens": 0, "outputTokens": 0},
                "cache_token_savings": saved_input_tokens + saved_output_tokens,
                "cached_input_tokens": saved_input_tokens,
                "cached_output_tokens": saved_output_tokens,
            },
        )
        LOGGER.info(
            "response_builder_chat_response_built",
            correlation_id=correlation_id,
            provider="cache",
            model_name="cache",
            confidence=chat_response.confidence,
            source_count=len(chat_response.citations),
            response_source="cache",
        )
        return chat_response

    def fallback(
        self,
        answer: str,
        correlation_id: str,
        metadata: dict[str, Any] | None = None,
        cards: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        """Build a canonical low-confidence fallback response."""
        chat_response = ChatResponse(
            answer=answer,
            citations=[],
            suggestions=[],
            cards=list(cards or []),
            confidence=0.0,
            correlation_id=correlation_id,
            metadata={"fallback": True, "correlation_id": correlation_id, **(metadata or {})},
        )
        LOGGER.info(
            "response_builder_chat_response_built",
            correlation_id=correlation_id,
            provider="fallback",
            model_name="fallback",
            confidence=chat_response.confidence,
            source_count=0,
            response_source="fallback",
            failure_layer=chat_response.metadata.get("failure_layer"),
        )
        return chat_response

    def _supporting_citations(
        self,
        answer: str,
        retrieval_result: RetrievalResult,
        *,
        session_country: str = "",
    ) -> list[dict[str, Any]]:
        """Return only the retrieved citations that best support the answer."""
        return [
            self._source_for_answer(document, answer)
            for document in self._supporting_documents(answer, retrieval_result, session_country=session_country)
        ]

    def reconcile_citations(
        self,
        *,
        built_answer: str,
        delivered_answer: str,
        citations: list[dict[str, Any]],
        retrieval_result: RetrievalResult,
        session_country: str = "",
    ) -> list[dict[str, Any]]:
        """Return citations for the answer the reader receives after post-generation edits.

        `build` chooses citations from the model's text. Numeric repair later
        deletes sentences from that text, and directory restoration appends
        contact lines to it, but the citations chosen before either edit were
        delivered unchanged. A policy passage cited for a figure that repair
        deleted stayed on an answer that no longer states it, and its excerpt
        still quoted the deleted claim.

        Citations are therefore chosen again, by the same rules as `build`,
        from the part of the model's text that reaches the reader. Appended
        directory lines are not model text and are never scored: they are
        copied from an approved directory record, and letting their digits
        into the score is what diluted governing passages below the gate.

        - Nothing changed (or only lines were appended): citations unchanged.
        - Nothing the model wrote survives (a refusal replaced it): none.
        - An original citation is kept, in its original order, while the
          surviving text still selects it, or, for a directory record, while
          the delivered answer still quotes one of its emails or phone numbers.
          Another step may have rewritten a sentence rather than deleted it
          ("must be taken" became "have to be taken"), so an original policy
          citation is also kept while the delivered text up to its last
          sentence the model wrote still clears the `build` support gate. It is
          never kept for another market's local policy.
        - A citation not chosen before is added only for a known reader market,
          never from another market's local policy, and never beyond two
          citations. Invented figures that repair deleted can dilute every
          passage below the gate, so an answer built with no citation may gain
          one once only its grounded sentences remain.

        Safety copy is unaffected: text that no edit changed returns the
        citations it was built with, which for a guardrail response is none.
        """
        if (delivered_answer or "").strip() == (built_answer or "").strip():
            return list(citations)
        identifiers = [document.id for document in retrieval_result.documents]
        surviving, complete = self._surviving_text(built_answer, delivered_answer, identifiers)
        if complete:
            return list(citations)
        if not self._comparable_text(surviving, identifiers):
            return []

        documents_by_key: dict[tuple[str, ...], RetrievedDocument] = {}
        for document in retrieval_result.documents:
            documents_by_key.setdefault(self._citation_key(document.to_source()), document)
        recomputed = self._supporting_documents(surviving, retrieval_result, session_country=session_country)
        recomputed_keys = {self._citation_key(document.to_source()) for document in recomputed}

        allowed_markets = self._document_markets(session_country)
        delivered_model_text = self._delivered_model_text(built_answer, delivered_answer, identifiers)
        selected: list[tuple[RetrievedDocument, str]] = []
        seen: set[tuple[str, ...]] = set()
        for citation in citations:
            key = self._citation_key(citation)
            document = documents_by_key.get(key)
            if document is None or key in seen:
                continue
            if key in recomputed_keys:
                selected.append((document, surviving))
                seen.add(key)
            elif self._is_directory_document(document):
                if self._quotes_directory_contact(delivered_answer, document):
                    selected.append((document, delivered_answer))
                    seen.add(key)
            elif not (allowed_markets and self._is_foreign_policy(document, allowed_markets)) and self._still_supports(
                delivered_model_text, document
            ):
                selected.append((document, delivered_model_text))
                seen.add(key)

        if allowed_markets:
            for document in recomputed:
                key = self._citation_key(document.to_source())
                if len(selected) >= 2:
                    break
                if key in seen or self._is_foreign_policy(document, allowed_markets):
                    continue
                selected.append((document, surviving))
                seen.add(key)
        return [self._source_for_answer(document, text) for document, text in selected]

    @staticmethod
    def _citation_key(source: dict[str, Any]) -> tuple[str, ...]:
        """What a reader can tell apart about a citation; excerpt and score are presentation."""
        return tuple(
            str(source.get(field) or "")
            for field in ("title", "uri", "section", "country", "language", "page", "documentVersion")
        )

    @staticmethod
    def _comparable_text(text: str, identifiers: list[str]) -> str:
        """Casefolded words of a text, without inline source markers the orchestrator strips."""
        normalized = unicodedata.normalize("NFKC", text or "").casefold()
        for identifier in identifiers:
            if identifier:
                normalized = normalized.replace(f"[{identifier.casefold()}]", " ")
        normalized = re.sub(r"\[(?:source\s+)?\d+\](?:\([^\s()]*\))?", " ", normalized)
        return " ".join(re.findall(r"[^\W_]+", normalized))

    def _surviving_text(self, built_answer: str, delivered_answer: str, identifiers: list[str]) -> tuple[str, bool]:
        """The model's sentences that the delivered answer still contains, and whether all of them are."""
        delivered = f" {self._comparable_text(delivered_answer, identifiers)} "
        kept: list[str] = []
        complete = True
        for unit in re.split(r"(?<=[.!?])\s+|\n", built_answer or ""):
            comparable = self._comparable_text(unit, identifiers)
            # A line made only of source markers is presentation the orchestrator
            # removes on purpose; losing it removes no claim.
            if not re.sub(r"\b(?:sources?|pages?|pp|section)\b", "", comparable).strip():
                kept.append(unit)
                continue
            if f" {comparable} " in delivered:
                kept.append(unit)
            else:
                complete = False
        return "\n".join(kept), complete

    def _delivered_model_text(self, built_answer: str, delivered_answer: str, identifiers: list[str]) -> str:
        """The delivered answer without lines appended after the model's text.

        Restoration steps append directory lines at the end, so everything after
        the last delivered sentence that also appears in the model's text is
        excluded. A sentence rewritten in place stays in, because a sentence
        the model wrote still follows it.
        """
        built = f" {self._comparable_text(built_answer, identifiers)} "
        units = [unit for unit in re.split(r"(?<=[.!?])\s+|\n", delivered_answer or "") if unit.strip()]
        last = -1
        for index, unit in enumerate(units):
            comparable = self._comparable_text(unit, identifiers)
            if comparable and f" {comparable} " in built:
                last = index
        return "\n".join(units[: last + 1])

    def _still_supports(self, answer: str, document: RetrievedDocument) -> bool:
        """The `build` support gate: the same threshold and, for a numeric answer, a shared figure."""
        if not (answer or "").strip():
            return False
        source = document.content or document.excerpt
        numbers = self._numbers(answer)
        return self._support_score(answer, source) >= self._minimum_support_score(answer) and (
            not numbers or bool(numbers & self._numbers(source))
        )

    @staticmethod
    def _is_directory_document(document: RetrievedDocument) -> bool:
        metadata = document.metadata or {}
        return str(document.country or "").strip().upper() == "GLOBAL" and bool(
            metadata.get("directory_kind") or metadata.get("directory_section")
        )

    def _quotes_directory_contact(self, answer: str, document: RetrievedDocument) -> bool:
        """Whether the answer repeats an email address or phone number of a directory record."""
        source = (document.content or document.excerpt or "").lower()
        lowered = (answer or "").lower()
        emails = re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", source)
        if any(email in lowered for email in emails):
            return True
        source_numbers = self._phone_digits(source)
        return bool(source_numbers and source_numbers & self._phone_digits(lowered))

    @staticmethod
    def _phone_spans(lowered: str) -> list[tuple[int, int]]:
        spans = []
        for pattern in (_PREFIXED_PHONE, _GROUPED_DIGITS):
            for match in re.finditer(pattern, lowered):
                groups = re.split(r"[ \-]", match.group(0))
                if pattern == _GROUPED_DIGITS and all(len(group) == 3 for group in groups[1:]):
                    continue
                spans.append((match.start(), match.end()))
        return spans

    def _phone_digits(self, lowered: str) -> set[str]:
        numbers = {re.sub(r"\D", "", lowered[start:end]) for start, end in self._phone_spans(lowered)}
        return {number for number in numbers if len(number) >= 6}

    def _supporting_documents(
        self,
        answer: str,
        retrieval_result: RetrievalResult,
        *,
        session_country: str = "",
    ) -> list[RetrievedDocument]:
        """Return the retrieved documents that best support the answer."""
        documents = retrieval_result.documents
        if not documents:
            return []

        evidence_contract = (retrieval_result.metadata or {}).get("evidence_contract", {})
        if isinstance(evidence_contract, dict) and evidence_contract.get("status") == "accepted":
            evidence_ids = {str(identifier) for identifier in evidence_contract.get("evidence_ids", [])}
            verified = [document for document in documents if not evidence_ids or document.id in evidence_ids]
            # These documents already passed the claim-level evidence contract.
            # A second lexical check can incorrectly discard citations when the
            # answer and source use different languages.
            #
            # None is discarded, but the first is shown as the primary source,
            # and the model's listed IDs arrive in retrieval order. Sweden's
            # buy-back answer (section 21.05) led with section 1.01, the company
            # introduction, because it ranked first. Order by support; the sort
            # is stable, so equally scored passages keep their original order.
            verified.sort(key=lambda document: self._support_score(answer, document.content or document.excerpt), reverse=True)
            return verified[:3]

        # Preserve explicit references to approved passages, including a
        # non-numeric rule alongside a numeric requirement. This is citation
        # presentation, not a claim-entailment or evidence-approval override.
        approval = (retrieval_result.metadata or {}).get("evidence_decision", {})
        if isinstance(approval, dict) and approval.get("approved") is True:
            indices = {int(match) for match in re.findall(r"\[(?:Source\s+)?(\d+)\](?!\()", answer)}
            explicit = [document for index, document in enumerate(documents, 1)
                        if index in indices or re.search(r"\[" + re.escape(document.id) + r"\](?!\()", answer)]
            if explicit:
                return explicit

        # Local policy is only ever the reader's own market's. A global directory
        # record stays eligible: it is how another country's sponsoring facts
        # are answered.
        allowed_markets = self._document_markets(session_country)
        if allowed_markets:
            documents = [document for document in documents if not self._is_foreign_policy(document, allowed_markets)]
            if not documents:
                return []

        answer_numbers = self._numbers(answer)
        ranked = sorted(
            documents,
            key=lambda document: (
                self._support_score(answer, document.content or document.excerpt),
                float(document.score or 0.0),
            ),
            reverse=True,
        )
        supported = [
            document
            for document in ranked
            if self._support_score(answer, document.content or document.excerpt) >= self._minimum_support_score(answer)
            and (not answer_numbers or bool(answer_numbers & self._numbers(document.content or document.excerpt)))
        ]
        return (
            self._numeric_citations(
                answer_numbers, supported, documents, answer=answer, add_governing=bool(allowed_markets)
            )
            if answer_numbers
            else supported[:2]
        )

    @staticmethod
    def _document_markets(session_country: str) -> set[str]:
        """Document country codes that hold the session market's own policy."""
        country = (session_country or "").strip().upper()
        if not country or country == "GLOBAL":
            return set()
        from services.market_config import get_document_country_codes

        return {code.upper() for code in get_document_country_codes(country)}

    @staticmethod
    def _is_foreign_policy(document: RetrievedDocument, allowed_markets: set[str]) -> bool:
        country = str(document.country or "").strip().upper()
        return bool(country) and country != "GLOBAL" and country not in allowed_markets

    def _numeric_citations(
        self,
        answer_numbers: set[str],
        supported: list[RetrievedDocument],
        documents: list[RetrievedDocument],
        *,
        answer: str = "",
        add_governing: bool = False,
    ) -> list[RetrievedDocument]:
        """Cite the best-supported source, plus one more only for figures it lacks.

        A numeric answer used to keep exactly one citation. Ranking counts every
        digit group of a phone number as its own figure ("+352 2 786 1452" is
        four), so an answer stating a policy deadline and a directory contact
        cited the directory and dropped the policy passage carrying the
        deadline. The second source is added only when it carries an answer
        figure the first does not, and never when retrieval holds local policy
        from more than one market, so another market's policy cannot be cited.
        """
        if not supported:
            return []
        selected = [supported[0]]
        local_markets = {
            str(document.country or "").upper()
            for document in documents
            if str(document.country or "").strip() and str(document.country).upper() != "GLOBAL"
        }
        if len(local_markets) > 1:
            return selected
        # Only a known reader market has had foreign policy filtered out above.
        governing = self._governing_policy_citation(answer, selected[0], documents) if add_governing else None
        if governing is not None:
            return [*selected, governing]
        uncovered = answer_numbers - self._numbers(selected[0].content or selected[0].excerpt)
        for document in supported[1:]:
            if uncovered & self._numbers(document.content or document.excerpt):
                selected.append(document)
                break
        return selected

    def _governing_policy_citation(
        self,
        answer: str,
        first: RetrievedDocument,
        documents: list[RetrievedDocument],
    ) -> RetrievedDocument | None:
        """Return the local policy passage stating a figure the first citation does not.

        Contact details decided the numeric citation. Every digit group of a
        phone number counts as an answer figure, so a directory record that
        matches "+352 2 786 1452" outranks the policy passage stating the
        requested deadline, and the four extra figures dilute that passage's
        score below the support threshold. A figure-set comparison also treats
        the directory as covering an age limit of 18 because it charges a
        delivery fee of 18 - the same digits in an unrelated sentence.

        So only figures outside contact details count here, and a source covers
        one only where it states it with the same unit or content word ("18 år",
        "24 mois"). Years, days of the month and function words ("18 or",
        "€18 per") never make a match.

        Sharing a figure and its unit is still not sharing a fact: Norway's
        termination clause also says "over 18 år". The passage must therefore
        share a topic word with the answer beyond the figure, its unit and
        generic brand or contact words. It must also pass the same support gate
        as any other citation, scored against the same full answer text. This is
        deliberately no easier than fb22f38: contact digits still dilute that
        score, so a governing passage below the gate is not added.

        The first citation is kept. This adds at most one retrieved local-policy
        passage, which the caller has already restricted to the reader's own
        market.

        A passage below the full-answer gate is never added. Scoring only the
        sentence around the figure was measured on 2026-09-11 against every
        NO/LU/FI/IT/CA/NL extraction row and still cited unrelated clauses that
        restate most of a short answer sentence with a different subject ("the
        FBO can purchase at up to 5% discount" cited to the preferred-customer
        clause), so it is not used (handoff 2026-09-11_1625_ovn-w4-citation).
        """
        figures = [figure for figure in self._figure_occurrences(answer, skip_contacts=True) if figure[1] or figure[2]]
        first_figures = self._figure_occurrences(first.content or first.excerpt)
        uncovered = [figure for figure in figures if not self._covers_figure(first_figures, figure)]
        if not uncovered:
            return None
        topic = self._topic_words(answer, figures)
        if not topic:
            return None
        minimum = self._minimum_support_score(answer)
        candidates = []
        for document in documents:
            country = str(document.country or "").strip().upper()
            if document is first or not country or country == "GLOBAL":
                continue
            text = document.content or document.excerpt
            source_figures = self._figure_occurrences(text)
            if not any(self._covers_figure(source_figures, figure) for figure in uncovered):
                continue
            if not self._shares_topic_word(topic, self._tokens(text)):
                continue
            score = self._support_score(answer, text)
            if score >= minimum:
                candidates.append((score, float(document.score or 0.0), document))
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: (candidate[0], candidate[1]))[2]

    @staticmethod
    def _contact_spans(lowered: str) -> list[tuple[int, int]]:
        """Character spans of phone numbers, emails, web addresses and clock times."""
        from app.validation.validators.numeric_grounding_validator import _time_occurrences

        spans = [(start, end) for start, end, _keys in _time_occurrences(lowered)]
        for pattern in (r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", r"(?:https?://|www\.)\S+"):
            spans.extend((match.start(), match.end()) for match in re.finditer(pattern, lowered))
        spans.extend(ResponseBuilder._phone_spans(lowered))
        return spans

    def _without_contact_details(self, answer: str) -> str:
        """Answer text with contact details blanked, for scoring a stated fact."""
        lowered = (answer or "").lower()
        if len(lowered) != len(answer or ""):
            text = lowered
        else:
            text = answer or ""
        characters = list(text)
        for start, end in self._contact_spans(lowered):
            characters[start:end] = " " * (end - start)
        return "".join(characters)

    def _figure_occurrences(self, text: str, *, skip_contacts: bool = False) -> list[tuple[set[str], str, str]]:
        """Each plain figure with its notation variants, its unit and the content word before it.

        The unit or word is "" when the figure has none that can identify it.
        Years ("2024") and days of the month ("1 January", "1. januar") are
        left out: they date a rule, they are not the figure it sets.
        """
        from app.validation.validators.numeric_grounding_validator import (
            _number_variants,
            _time_occurrences,
        )

        lowered = (text or "").lower()
        skipped = (
            self._contact_spans(lowered)
            if skip_contacts
            else [(start, end) for start, end, _keys in _time_occurrences(lowered)]
        )
        occurrences = []
        for match in re.finditer(r"\b\d+(?:[.,]\d+)?\b", lowered):
            if any(start <= match.start() < end for start, end in skipped):
                continue
            number = match.group(0)
            if re.fullmatch(r"(?:19|20)\d{2}", number):
                continue
            before = lowered[max(0, match.start() - 40):match.start()]
            after = lowered[match.end():match.end() + 24]
            preceding = re.search(r"([^\W\d_]+)[\s *]{0,3}$", before)
            preceding_word = preceding.group(1) if preceding else ""
            if number.isdigit() and 1 <= int(number) <= 31 and (
                _is_month(preceding_word) or any(_is_month(word) for word in re.findall(r"[^\W\d_]+", after[:14])[:2])
            ):
                continue
            following = re.match(r"[\s *\-–]{0,3}([^\W\d_]+|[%€$£])", after)
            unit = self._figure_unit(following.group(1) if following else "")
            currency = re.search(r"([€$£])[\s ]?$", before)
            if not unit and currency:
                unit = _FIGURE_CURRENCY_ALIASES[currency.group(1)]
            occurrences.append((_number_variants(number), unit, self._figure_content_word(preceding_word)))
        return occurrences

    @classmethod
    def _figure_unit(cls, word: str) -> str:
        """The word as the figure's unit, or "" when it cannot say what the figure counts."""
        word = _FIGURE_CURRENCY_ALIASES.get(word, word)
        return word if word in _FIGURE_SHORT_UNITS else cls._figure_content_word(word)

    @staticmethod
    def _figure_content_word(word: str) -> str:
        if len(word) < 4 or word in _FIGURE_FUNCTION_WORDS or _is_month(word):
            return ""
        return word

    @staticmethod
    def _covers_figure(source_figures: list[tuple[set[str], str, str]], figure: tuple[set[str], str, str]) -> bool:
        """Whether a source states the figure with the same unit or content word as the answer."""
        def same_word(left: str, right: str) -> bool:
            if not left or not right:
                return False
            return left == right or (len(left) >= 4 and len(right) >= 4 and left[:4] == right[:4])

        variants, unit, preceding = figure
        return any(
            variants & source_variants and (same_word(unit, source_unit) or same_word(preceding, source_preceding))
            for source_variants, source_unit, source_preceding in source_figures
        )

    def _topic_words(self, answer: str, figures: list[tuple[set[str], str, str]]) -> set[str]:
        """Content words of the answer outside contact details, figure units and generic words."""
        units = {unit for _variants, unit, _preceding in figures}
        return {
            token
            for token in self._tokens(self._without_contact_details(answer))
            if token not in units
            and token not in _FIGURE_FUNCTION_WORDS
            and token not in _GENERIC_TOPIC_WORDS
            and token not in _PERIOD_WORDS
            and not _is_month(token)
        }

    @staticmethod
    def _shares_topic_word(topic: set[str], source_tokens: set[str]) -> bool:
        """Whether the source uses a topic word, allowing only a plain inflection ("trip"/"trips")."""
        for word in topic:
            if word in source_tokens or any(word + suffix in source_tokens for suffix in _TOPIC_SUFFIXES):
                return True
            if any(
                word.endswith(suffix) and len(word) - len(suffix) >= 4 and word[: -len(suffix)] in source_tokens
                for suffix in _TOPIC_SUFFIXES
            ):
                return True
        return False

    def _support_score(self, answer: str, source_text: str) -> float:
        """Score how well a source text supports the final answer text."""
        answer_tokens = self._tokens(answer)
        source_tokens = self._tokens(source_text)
        if not answer_tokens or not source_tokens:
            return 0.0

        overlap = len(answer_tokens & source_tokens) / len(answer_tokens)
        answer_numbers = self._numbers(answer)
        source_numbers = self._numbers(source_text)
        number_overlap = len(answer_numbers & source_numbers) / len(answer_numbers) if answer_numbers else 0.0
        phrase_overlap = self._phrase_overlap(answer, source_text)
        return round(overlap + (number_overlap * 0.55) + (phrase_overlap * 0.25), 6)

    def _minimum_support_score(self, answer: str) -> float:
        """Require stronger source support when the answer contains measurable values."""
        return 0.35 if self._numbers(answer) else 0.12

    def _tokens(self, text: str) -> set[str]:
        """Return Unicode terms useful for citation support matching."""
        normalized = unicodedata.normalize("NFKC", text or "").casefold()
        return {
            token
            for token in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
            if len(token) > 3 and token not in REFERENCE_STOPWORDS
        }

    def _numbers(self, text: str) -> set[str]:
        """Return comparable numeric keys for answer/source support matching.

        This has to recognise the same value written two ways, because a
        directory record and an answer routinely differ in notation. Measured
        on 2026-09-08: the Algeria record writes office hours as
        "09.30 am - 17.30 pm", a model wrote "9:30 AM to 5:30 PM", and the two
        sets shared nothing at all - so a correct, retrieved, grounded answer
        was delivered to the reader with no citation on it.

        The keys come from the numeric grounding validator rather than a fourth
        private notion of sameness. Clock times are keyed by that module's
        meridiem-aware logic, and plain figures carry their notation variants,
        so "7.5" and "7.50" compare equal here exactly as they do there.
        """
        from app.validation.validators.numeric_grounding_validator import (
            _number_variants,
            _time_occurrences,
        )

        lowered = (text or "").lower()
        keys: set[str] = set()
        time_spans: list[tuple[int, int]] = []
        for start, end, time_keys in _time_occurrences(lowered):
            time_spans.append((start, end))
            keys |= time_keys

        for match in re.finditer(r"\b\d+(?:[.,]\d+)?\b", lowered):
            # A figure inside a clock time is already represented by its time
            # key; counting "30" separately would match any source mentioning
            # thirty of anything.
            if any(start <= match.start() < end for start, end in time_spans):
                continue
            keys |= _number_variants(match.group(0))
        return keys

    def _phrase_overlap(self, answer: str, source_text: str) -> float:
        """Reward sources that contain named concepts from the answer."""
        answer_phrases = [
            phrase.lower()
            for phrase in re.findall(
                r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,}))*\b",
                answer,
            )
            if len(phrase.split()) > 1
        ]
        if not answer_phrases:
            return 0.0
        source_lower = source_text.lower()
        return min(sum(1 for phrase in answer_phrases if phrase in source_lower) / len(answer_phrases), 1.0)

    def _source_for_answer(self, document: RetrievedDocument, answer: str) -> dict[str, Any]:
        """Build a source dictionary with an answer-focused excerpt."""
        source = document.to_source()
        source["excerpt"] = self._best_excerpt(answer, document.content or document.excerpt)
        return source

    def _best_excerpt(self, answer: str, source_text: str, length: int = 320) -> str:
        """Choose an excerpt near the strongest answer/source overlap."""
        if not source_text:
            return ""

        windows = [
            source_text[index : index + length]
            for index in range(0, max(len(source_text), 1), max(length // 2, 1))
        ] or [source_text]
        best_window = max(windows, key=lambda window: self._support_score(answer, window))
        if self._support_score(answer, best_window) <= 0:
            return source_text[:length].strip()

        return best_window.strip()


response_builder = ResponseBuilder()
