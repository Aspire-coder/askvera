"""Cue-term vocabulary for classifying which process stage a timing figure belongs to.

Forever Living's policy and directory text states several different clocks that
share the same shape ("3 working days", "48 hours", "within 2 months"): how long
delivery takes, how long an application/registration/qualification takes to be
approved, how long an order takes to process, when a bonus or commission is
paid, how long a bank transfer/settlement takes to arrive, and how long a
waiting period (a sponsor change, a re-application, a cooling-off period) or a
set of office/business hours lasts. A model answer that borrows a number stated
for one of these stages and reports it for another - "your bonus is paid within
3 working days" when the source states 3 working days for *delivery* - is wrong
in a way that ordinary numeric grounding (does this number appear in the
source at all) cannot catch, because the number itself is genuinely present in
the source.

This module holds ONE auditable mapping, language code -> stage name -> a tuple
of cue terms (words and short phrases) that the numeric grounding validator
uses to classify the stage of the clause or sentence a timing number sits in,
in the answer and in the retrieved source text. It intentionally holds no
regex, no market names and no benchmark case IDs: only the words themselves.
`app/validation/validators/numeric_grounding_validator.py` builds the matching
patterns from this table alone.

How the terms were chosen
--------------------------
Each stage's cues name the PROCESS EVENT or period itself - a verb, its
participle, or the stage's own generic noun ("approval", "processing",
"payment date", "settlement", "waiting period") - never the TOPIC a sentence
happens to be about. This distinction is deliberate and was tightened after an
integration review found the first draft mixing the two: a term such as
"sponsor change" or "application" names WHAT is being approved, processed or
waited out, not the stage itself, and a wrong answer naturally states its
topic correctly while getting the stage wrong ("Your sponsor change will be
processed within 6 months" - topic "sponsor change" is right, stage should be
"waiting period", not "processing"). Keeping a topic word as a cue for one
stage let that stage's own vocabulary appear, by coincidence, in a sentence
about a completely different (and wrong) stage, which made the classifier see
two different stages and back off as unclassifiable - silently letting the
exact substitution this module exists to catch through. Each language's terms
are direct, common-register translations of the English list; they were not
extracted from a specific market's live corpus, so the coverage is
deliberately generous rather than exhaustively verified against every one of
Forever Living's per-market documents.

Limits, and the least confident entries
----------------------------------------
- "processing" and "approval" still name closely related events (an
  application is commonly "processed" as part of being "approved"), but with
  topic nouns removed, only a clause that actually uses BOTH process verbs
  ("processed" and "approved" together) is now ambiguous; a clause naming a
  topic plus one process verb no longer is.
- "payment" and "settlement" are the two stages this list is least confident
  about, because a single market document may use one generic verb ("betalen",
  "pay", "zahlen") for both crediting a distributor's bonus and a bank transfer
  clearing. The terms below try to keep "payment" to the date/act of paying out
  and "settlement" to money being credited or arriving in a bank account, but a
  plain "paid" / "betaald" / "payé" with no further qualifier is not listed
  under either stage on purpose, because it cannot be told apart from context
  alone. Delivery's bare "arrive"/"arrival" (a parcel arriving) and
  settlement's "arrive in your account" (funds arriving) share the same verb
  by design; a sentence using the fuller settlement phrase still matches both
  and is treated as unclassifiable rather than guessed, which is the safe
  direction.
- Finnish, Norwegian and Swedish terms for "payment", "settlement" and
  "waiting_period" are translated from English rather than sourced from a
  native policy document, so they are the entries most likely to need a native
  reviewer's correction.
- "office_hours" is deliberately narrow (phrases such as "office hours",
  "business hours", "opening hours"), never a bare "hours" word, so that an
  ordinary duration ("within 48 hours") is not misread as an office-hours
  statement just because the word for "hour" appears nearby.
- This list does not attempt every synonym; a clause using an uncovered word
  classifies as unknown for that stage, which is the safe direction (the
  validator only tightens grounding when BOTH sides classify to a stage, and
  never when either side is unclassifiable).
"""

from __future__ import annotations

TIMING_STAGE_VOCABULARY: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "delivery": (
            "delivery", "deliver", "delivers", "delivered", "delivering",
            "shipping", "shipment", "shipped", "dispatch", "dispatched",
            "arrive", "arrives", "arrival", "courier",
        ),
        "approval": (
            "approved", "approval", "approve", "approves", "approving",
            "accepted", "confirmed as approved",
        ),
        "processing": (
            "processing", "process", "processes", "processed", "handling", "handled",
        ),
        "payment": (
            "payment date", "pay date", "paid out", "payout", "paid", "pays", "paying",
        ),
        "settlement": (
            "settlement", "settle", "settles", "settled", "credited", "credit",
            "clear", "clears", "cleared", "clearing", "arrive in your account",
            "arrives in your account", "funds arrive",
        ),
        "waiting_period": (
            "waiting period", "wait", "waits", "waited", "waiting", "must wait",
            "cooling-off", "cooling off period", "not eligible until",
            "not permitted until", "before you may",
        ),
        "office_hours": (
            "office hours", "business hours", "opening hours", "opening times",
            "working hours",
        ),
    },
    "fr": {
        "delivery": (
            "livraison", "livrer", "livré", "livrée", "livrés", "livrées",
            "expédition", "expédié", "expédiée", "arrivée", "arriver",
        ),
        "approval": (
            "approuvé", "approuvée", "approuvés", "approuvées", "approbation",
            "approuver", "accepté", "acceptée", "confirmé comme approuvé",
        ),
        "processing": (
            "traitement", "traiter", "traité", "traitée",
        ),
        "payment": (
            "date de paiement", "date de versement", "versement", "versé", "versée",
            "payé", "payée",
        ),
        "settlement": (
            "règlement", "réglé", "réglée", "crédité", "créditée",
            "créditée sur votre compte", "créditée à votre compte",
            "arrivée des fonds", "les fonds arrivent",
        ),
        "waiting_period": (
            "période d'attente", "attendre", "doit attendre", "délai de carence",
            "pas éligible avant", "avant de pouvoir",
        ),
        "office_hours": (
            "heures d'ouverture", "heures de bureau", "horaires d'ouverture",
            "horaires de bureau",
        ),
    },
    "de": {
        "delivery": (
            "lieferung", "liefern", "geliefert", "versand", "versendet",
            "ankunft", "ankommen", "ankommt",
        ),
        "approval": (
            "genehmigt", "genehmigung", "genehmigen", "akzeptiert",
            "bestätigt als genehmigt",
        ),
        "processing": (
            "bearbeitung", "bearbeiten", "bearbeitet",
        ),
        "payment": (
            "zahlungsdatum", "auszahlung", "ausgezahlt", "wird ausgezahlt",
            "bezahlt",
        ),
        "settlement": (
            "abrechnung", "abgerechnet", "gutschrift", "gutgeschrieben",
            "ihrem konto gutgeschrieben", "geldeingang",
        ),
        "waiting_period": (
            "wartezeit", "warten", "muss warten", "sperrfrist",
            "nicht berechtigt bis", "bevor sie können",
        ),
        "office_hours": (
            "öffnungszeiten", "geschäftszeiten", "bürozeiten",
        ),
    },
    "nl": {
        "delivery": (
            "levering", "leveren", "geleverd", "verzending", "verzonden",
            "aankomst", "aankomen",
        ),
        "approval": (
            "goedgekeurd", "goedkeuring", "goedkeuren", "geaccepteerd",
            "bevestigd als goedgekeurd",
        ),
        "processing": (
            "verwerking", "verwerken", "verwerkt",
        ),
        "payment": (
            "betaaldatum", "uitbetaling", "uitbetaald", "wordt uitbetaald",
            "betaald",
        ),
        "settlement": (
            "verrekening", "verrekend", "bijgeschreven", "storting",
            "op uw rekening bijgeschreven",
        ),
        "waiting_period": (
            "wachttijd", "wachten", "moet wachten", "wachtperiode",
            "niet gerechtigd tot", "voordat u kunt",
        ),
        "office_hours": (
            "openingstijden", "kantooruren", "werktijden",
        ),
    },
    "it": {
        "delivery": (
            "consegna", "consegnare", "consegnato", "consegnata",
            "spedizione", "spedito", "spedita", "arrivo", "arrivare",
        ),
        "approval": (
            "approvato", "approvata", "approvazione", "approvare", "accettato",
            "confermato come approvato",
        ),
        "processing": (
            "elaborazione", "elaborare", "elaborato", "elaborata",
        ),
        "payment": (
            "data di pagamento", "versamento", "versato", "versata", "pagato",
        ),
        "settlement": (
            "saldo", "saldato", "accredito", "accreditato", "accreditata",
            "accreditato sul tuo conto", "arrivo dei fondi",
        ),
        "waiting_period": (
            "periodo di attesa", "attendere", "deve attendere",
            "periodo di carenza", "non ammissibile fino a", "prima di poter",
        ),
        "office_hours": (
            "orario di apertura", "orari di ufficio", "orario di lavoro",
        ),
    },
    "pt": {
        "delivery": (
            "entrega", "entregar", "entregue", "entregues",
            "envio", "enviado", "enviada", "chegada", "chegar",
        ),
        "approval": (
            "aprovado", "aprovada", "aprovação", "aprovar", "aceite", "aceito",
            "confirmado como aprovado",
        ),
        "processing": (
            "processamento", "processar", "processado", "processada",
        ),
        "payment": (
            "data de pagamento", "pagamento efetuado", "é pago", "é paga", "pago",
        ),
        "settlement": (
            "liquidação", "liquidado", "crédito na conta", "creditado",
            "creditado na sua conta", "creditada na sua conta", "chegada dos fundos",
        ),
        "waiting_period": (
            "período de espera", "esperar", "deve esperar", "período de carência",
            "não elegível até", "antes de poder",
        ),
        "office_hours": (
            "horário de funcionamento", "horário de expediente",
            "horário de atendimento",
        ),
    },
    "es": {
        "delivery": (
            "entrega", "entregar", "entregado", "entregada",
            "envío", "enviado", "enviada", "llegada", "llegar",
        ),
        "approval": (
            "aprobado", "aprobada", "aprobación", "aprobar", "aceptado",
            "confirmado como aprobado",
        ),
        "processing": (
            "procesamiento", "procesar", "procesado", "procesada",
        ),
        "payment": (
            "fecha de pago", "desembolso", "se paga", "pagado",
        ),
        "settlement": (
            "liquidación", "liquidado", "abono", "abonado", "abonado en su cuenta",
            "abonada en su cuenta", "llegada de los fondos",
        ),
        "waiting_period": (
            "período de espera", "periodo de espera", "esperar", "debe esperar",
            "no elegible hasta", "antes de poder",
        ),
        "office_hours": (
            "horario de oficina", "horario de atención", "horas de apertura",
        ),
    },
    "fi": {
        "delivery": (
            "toimitus", "toimittaa", "toimitettu", "lähetys", "lähetetty",
            "saapuminen", "saapua",
        ),
        "approval": (
            "hyväksytty", "hyväksyminen", "hyväksyä", "hyväksytään",
        ),
        "processing": (
            "käsittely", "käsitellä", "käsitelty",
        ),
        "payment": (
            "maksupäivä", "maksettu", "maksetaan",
        ),
        "settlement": (
            "hyvitys", "hyvitetty", "tilille maksettu", "varojen saapuminen",
        ),
        "waiting_period": (
            "odotusaika", "odottaa", "on odotettava", "ei oikeutettu ennen",
            "ennen kuin voi",
        ),
        "office_hours": (
            "aukioloajat", "toimistoaika",
        ),
    },
    "no": {
        "delivery": (
            "levering", "levere", "levert", "forsendelse", "sendt",
            "ankomst", "ankomme",
        ),
        "approval": (
            "godkjent", "godkjenning", "godkjenne", "akseptert",
            "bekreftet som godkjent",
        ),
        "processing": (
            "behandling", "behandle", "behandlet",
        ),
        "payment": (
            "betalingsdato", "utbetalt", "utbetales",
        ),
        "settlement": (
            "oppgjør", "oppgjort", "godskrevet", "innbetalt til kontoen",
            "midlene ankommer",
        ),
        "waiting_period": (
            "ventetid", "vente", "må vente", "ikke berettiget før", "før du kan",
        ),
        "office_hours": (
            "åpningstider", "kontortid",
        ),
    },
    "nb": {
        "delivery": (
            "levering", "levere", "levert", "forsendelse", "sendt",
            "ankomst", "ankomme",
        ),
        "approval": (
            "godkjent", "godkjenning", "godkjenne", "akseptert",
            "bekreftet som godkjent",
        ),
        "processing": (
            "behandling", "behandle", "behandlet",
        ),
        "payment": (
            "betalingsdato", "utbetalt", "utbetales",
        ),
        "settlement": (
            "oppgjør", "oppgjort", "godskrevet", "innbetalt til kontoen",
            "midlene ankommer",
        ),
        "waiting_period": (
            "ventetid", "vente", "må vente", "ikke berettiget før", "før du kan",
        ),
        "office_hours": (
            "åpningstider", "kontortid",
        ),
    },
    "sv": {
        "delivery": (
            "leverans", "leverera", "levererad", "frakt", "skickad",
            "ankomst", "anlända",
        ),
        "approval": (
            "godkänd", "godkännande", "godkänna", "accepterad",
            "bekräftad som godkänd",
        ),
        "processing": (
            "behandling", "behandla", "behandlad",
        ),
        "payment": (
            "betalningsdatum", "utbetald", "utbetalas",
        ),
        "settlement": (
            "avräkning", "avräknad", "krediterad", "insatt på ditt konto",
            "medlen anländer",
        ),
        "waiting_period": (
            "väntetid", "vänta", "måste vänta", "inte berättigad förrän",
            "innan du kan",
        ),
        "office_hours": (
            "öppettider", "kontorstid",
        ),
    },
}
