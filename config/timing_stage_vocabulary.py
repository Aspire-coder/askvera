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
Each language's terms are direct, common-register translations of the English
list, covering the verb, the deed noun and (where the language commonly uses
one) the agent/process noun a policy or directory sentence would use for that
stage - e.g. English "deliver / delivered / delivery"; French "livrer / livré /
livraison". They were not extracted from a specific market's live corpus, so
the coverage is deliberately generous rather than exhaustively verified against
every one of Forever Living's per-market documents.

Limits, and the least confident entries
----------------------------------------
- "processing" and "approval" overlap in ordinary usage in every language here
  (an application is "processed" as part of being "approved"); the classifier
  treats a clause naming both as ambiguous (see `_classify_stage`) rather than
  guessing, by design.
- "payment" and "settlement" are the two stages this list is least confident
  about, because a single market document may use one generic verb ("betalen",
  "pay", "zahlen") for both crediting a distributor's bonus and a bank transfer
  clearing. The terms below try to keep "payment" to the bonus/commission being
  paid out and "settlement" to money arriving in a bank account, but a plain
  "paid" / "betaald" / "payé" with no further qualifier is not listed under
  either stage on purpose, because it cannot be told apart from context alone.
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
            "approval", "approve", "approves", "approved", "approving",
            "application", "apply", "applying", "applicant",
            "registration", "register", "registers", "registered", "registering",
            "qualification", "qualify", "qualifies", "qualified", "qualifying",
        ),
        "processing": (
            "processing", "process", "processes", "processed",
            "order processing", "handling", "handled",
        ),
        "payment": (
            "bonus payment", "commission payment", "payment date", "pay date",
            "payout", "paid out", "bonus is paid", "commissions are paid",
            "bonus payment date",
        ),
        "settlement": (
            "bank transfer", "bank settlement", "settle", "settlement",
            "settled", "clearing", "cleared", "arrive in your account",
            "arrives in your account", "credited to your account",
            "funds arrive", "bank account",
        ),
        "waiting_period": (
            "waiting period", "cooling-off", "cooling off period",
            "sponsor change", "change of sponsor", "changing sponsor",
            "re-application", "reapplication", "re-apply", "reapply", "reapplying",
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
            "approbation", "approuver", "approuvé", "approuvée",
            "demande", "candidature", "postuler",
            "inscription", "s'inscrire", "inscrit", "inscrite",
            "qualification", "qualifier", "qualifié", "qualifiée",
        ),
        "processing": (
            "traitement", "traiter", "traité", "traitée",
            "traitement de la commande",
        ),
        "payment": (
            "paiement de la prime", "paiement de la commission",
            "date de paiement", "versement", "versé", "versée",
            "la prime est versée",
        ),
        "settlement": (
            "virement bancaire", "règlement bancaire", "crédité sur votre compte",
            "créditée sur votre compte", "arrivée des fonds", "compte bancaire",
        ),
        "waiting_period": (
            "période d'attente", "délai de carence", "changement de parrain",
            "changement de sponsor", "réinscription", "nouvelle demande",
            "nouvelle candidature",
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
            "genehmigung", "genehmigen", "genehmigt",
            "antrag", "bewerbung", "bewerben",
            "registrierung", "registrieren", "registriert",
            "qualifikation", "qualifizieren", "qualifiziert",
        ),
        "processing": (
            "bearbeitung", "bearbeiten", "bearbeitet",
            "auftragsbearbeitung",
        ),
        "payment": (
            "bonuszahlung", "provisionszahlung", "zahlungsdatum",
            "auszahlung", "ausgezahlt", "wird ausgezahlt",
        ),
        "settlement": (
            "banküberweisung", "gutschrift", "gutgeschrieben",
            "ihrem konto gutgeschrieben", "geldeingang", "bankkonto",
        ),
        "waiting_period": (
            "wartezeit", "sperrfrist", "sponsorwechsel", "sponsorenwechsel",
            "neuantrag", "erneute bewerbung", "erneute registrierung",
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
            "goedkeuring", "goedkeuren", "goedgekeurd",
            "aanvraag", "aanvragen", "aanmelding", "aanmelden",
            "registratie", "registreren", "geregistreerd",
            "kwalificatie", "kwalificeren", "gekwalificeerd",
        ),
        "processing": (
            "verwerking", "verwerken", "verwerkt", "orderverwerking",
        ),
        "payment": (
            "bonusbetaling", "commissiebetaling", "betaaldatum",
            "uitbetaling", "uitbetaald", "wordt uitbetaald",
        ),
        "settlement": (
            "bankoverschrijving", "storting", "bijgeschreven",
            "op uw rekening bijgeschreven", "bankrekening",
        ),
        "waiting_period": (
            "wachttijd", "wachtperiode", "sponsorwissel", "wisselen van sponsor",
            "herregistratie", "opnieuw aanmelden", "nieuwe aanvraag",
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
            "approvazione", "approvare", "approvato", "approvata",
            "domanda", "richiesta", "iscrizione", "iscriversi",
            "registrazione", "registrare", "registrato",
            "qualificazione", "qualificarsi", "qualificato",
        ),
        "processing": (
            "elaborazione", "elaborare", "elaborato", "elaborata",
            "elaborazione dell'ordine",
        ),
        "payment": (
            "pagamento del bonus", "pagamento della commissione",
            "data di pagamento", "versamento", "versato", "versata",
        ),
        "settlement": (
            "bonifico bancario", "accredito", "accreditato", "accreditata",
            "accreditato sul tuo conto", "arrivo dei fondi", "conto bancario",
        ),
        "waiting_period": (
            "periodo di attesa", "periodo di carenza", "cambio di sponsor",
            "nuova domanda", "nuova iscrizione", "nuova registrazione",
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
            "aprovação", "aprovar", "aprovado", "aprovada",
            "candidatura", "inscrição", "inscrever",
            "registo", "registro", "registrar", "registado", "registrado",
            "qualificação", "qualificar", "qualificado", "qualificada",
        ),
        "processing": (
            "processamento", "processar", "processado", "processada",
        ),
        "payment": (
            "pagamento do bónus", "pagamento do bônus", "pagamento da comissão",
            "data de pagamento", "pagamento efetuado", "é pago", "é paga",
        ),
        "settlement": (
            "transferência bancária", "crédito na conta", "creditado na sua conta",
            "creditada na sua conta", "chegada dos fundos", "conta bancária",
        ),
        "waiting_period": (
            "período de espera", "período de carência", "mudança de patrocinador",
            "nova candidatura", "reinscrição", "novo registo", "novo registro",
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
            "aprobación", "aprobar", "aprobado", "aprobada",
            "solicitud", "solicitar", "inscripción", "inscribirse",
            "registro", "registrar", "registrado", "registrada",
            "calificación", "calificar", "calificado", "calificada",
        ),
        "processing": (
            "procesamiento", "procesar", "procesado", "procesada",
        ),
        "payment": (
            "pago del bono", "pago de la comisión", "fecha de pago",
            "desembolso", "se paga", "se abona el bono",
        ),
        "settlement": (
            "transferencia bancaria", "abono", "abonado en su cuenta",
            "abonada en su cuenta", "llegada de los fondos", "cuenta bancaria",
        ),
        "waiting_period": (
            "período de espera", "periodo de espera", "período de carencia",
            "periodo de carencia", "cambio de patrocinador", "nueva solicitud",
            "reinscripción",
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
            "hyväksyminen", "hyväksyä", "hyväksytty",
            "hakemus", "hakea",
            "rekisteröinti", "rekisteröityä", "rekisteröity",
            "pätevyys", "kelpoisuus",
        ),
        "processing": (
            "käsittely", "käsitellä", "käsitelty", "tilauksen käsittely",
        ),
        "payment": (
            "bonusmaksu", "palkkiomaksu", "maksupäivä", "maksettu", "maksetaan",
        ),
        "settlement": (
            "pankkisiirto", "tilillepano", "tilille maksettu",
            "varojen saapuminen", "pankkitili",
        ),
        "waiting_period": (
            "odotusaika", "sponsorin vaihto", "uusi hakemus",
            "uudelleen rekisteröityminen",
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
            "godkjenning", "godkjenne", "godkjent",
            "søknad", "søke",
            "registrering", "registrere", "registrert",
            "kvalifikasjon", "kvalifisere", "kvalifisert",
        ),
        "processing": (
            "behandling", "behandle", "behandlet", "bestillingsbehandling",
        ),
        "payment": (
            "bonusutbetaling", "provisjonsutbetaling", "betalingsdato",
            "utbetalt", "utbetales",
        ),
        "settlement": (
            "bankoverføring", "godskrevet", "innbetalt til kontoen",
            "midlene ankommer", "bankkonto",
        ),
        "waiting_period": (
            "ventetid", "sponsorbytte", "ny søknad", "ny registrering",
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
            "godkjenning", "godkjenne", "godkjent",
            "søknad", "søke",
            "registrering", "registrere", "registrert",
            "kvalifikasjon", "kvalifisere", "kvalifisert",
        ),
        "processing": (
            "behandling", "behandle", "behandlet", "bestillingsbehandling",
        ),
        "payment": (
            "bonusutbetaling", "provisjonsutbetaling", "betalingsdato",
            "utbetalt", "utbetales",
        ),
        "settlement": (
            "bankoverføring", "godskrevet", "innbetalt til kontoen",
            "midlene ankommer", "bankkonto",
        ),
        "waiting_period": (
            "ventetid", "sponsorbytte", "ny søknad", "ny registrering",
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
            "godkännande", "godkänna", "godkänd",
            "ansökan", "ansöka",
            "registrering", "registrera", "registrerad",
            "kvalifikation", "kvalificera", "kvalificerad",
        ),
        "processing": (
            "behandling", "behandla", "behandlad", "orderbehandling",
        ),
        "payment": (
            "bonusutbetalning", "provisionsutbetalning", "betalningsdatum",
            "utbetald", "utbetalas",
        ),
        "settlement": (
            "banköverföring", "insättning", "insatt på ditt konto",
            "medlen anländer", "bankkonto",
        ),
        "waiting_period": (
            "väntetid", "sponsorbyte", "ny ansökan", "ny registrering",
        ),
        "office_hours": (
            "öppettider", "kontorstid",
        ),
    },
}
