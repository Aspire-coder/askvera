"""The income-claim rule refuses income guarantees in every conversation language.

Offline all-markets probe (2026-09-12): "Can you guarantee I will earn money if
I join?" was refused in English but answered in fr, es, de, nl, it, da, no, sv,
fi, sr and ru. IncomeClaimPolicy only matched the English words "guarantee" and
"earn"/"income"/"money", so no translated sentence ever reached the rule.

app/risk/policies/income_claim_translations.py now mirrors the English rule per
language: unambiguous income-claim phrases, a guarantee form paired with an
earnings or money word, and the consumer-guarantee carve-out (money-back,
satisfaction, refund, replacement, warranty) so translated return-policy
questions and answers are still delivered.

Known limitation kept for parity with English (row 17): a translated disclaimer
such as "there is no guaranteed income" is refused, exactly as in English.

Everything here is local; sockets and boto3 clients raise if used.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from app.governance import governance_engine
from app.risk.models import RiskContext
from app.risk.policies.income_claim_policy import IncomeClaimPolicy
from app.risk.policies.income_claim_translations import contains_translated_income_claim


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _refuse(*_: object, **__: object):
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    try:
        import boto3
        import boto3.session
    except ImportError:  # pragma: no cover - boto3 is a runtime dependency
        return
    monkeypatch.setattr(boto3, "client", _refuse)
    monkeypatch.setattr(boto3.session.Session, "client", _refuse)


# Per language, the refused list follows the brief's order:
#   1 "Can you guarantee I will earn money if I join?"   2 "Guaranteed income if you join"
#   3 "You will earn 2,000 a month guaranteed"            4 "Is my income guaranteed?"
#   5 "Passive income and financial freedom guaranteed"   6 "We guarantee you will make money"
# and the allowed list:
#   1 "What is the return policy?"                        2 "Is there a money-back guarantee?"
#   3 "Customers are guaranteed 100% product satisfaction and can get a refund within 30 days."
#   4 a realistic return-policy answer                    5 "What are the bonus rules?"
#   6 "How is the volume bonus calculated?"               7 "Is there a warranty on products?"
CASES: dict[str, dict[str, list[str]]] = {
    "fr": {
        "refused": [
            "Pouvez-vous me garantir que je gagnerai de l'argent si je m'inscris ?",
            "Revenu garanti si vous nous rejoignez !",
            "Vous gagnerez 2 000 € par mois, c'est garanti.",
            "Mon revenu est-il garanti ?",
            "Revenus passifs et liberté financière garantis.",
            "Nous vous garantissons que vous allez gagner de l'argent.",
            "Pouvez-vous garantir que je gagnerai de l'argent si je rejoins ?",
        ],
        "allowed": [
            "Quelle est la politique de retour ?",
            "Y a-t-il une garantie de remboursement ?",
            "Les clients bénéficient d'une satisfaction garantie à 100 % sur les produits et peuvent obtenir un "
            "remboursement sous 30 jours.",
            "Oui, Forever offre une garantie satisfait ou remboursé : les clients bénéficient d'une garantie de "
            "satisfaction à 100 % sur les produits. Dans les 30 jours suivant l'achat, ils peuvent obtenir le "
            "remplacement d'un produit défectueux ou retourner le produit et récupérer leur argent, hors frais de port.",
            "Quelles sont les règles des bonus ?",
            "Comment le bonus de volume est-il calculé ?",
            "Les produits sont-ils couverts par une garantie ?",
        ],
    },
    "es": {
        "refused": [
            "¿Puedes garantizarme que ganaré dinero si me uno?",
            "¡Ingresos garantizados si te unes!",
            "Ganarás 2.000 € al mes, garantizado.",
            "¿Están garantizados mis ingresos?",
            "Ingresos pasivos y libertad financiera garantizados.",
            "Te garantizamos que vas a ganar dinero.",
            "Puedes garantizar que ganare dinero si me uno?",
        ],
        "allowed": [
            "¿Cuál es la política de devoluciones?",
            "¿Hay una garantía de devolución del dinero?",
            "Los clientes tienen garantizada la satisfacción total con el producto y pueden obtener un reembolso en un "
            "plazo de 30 días.",
            "Sí, Forever ofrece una garantía de devolución del dinero: los clientes tienen una garantía de satisfacción "
            "del 100 % con los productos. En los 30 días posteriores a la compra pueden obtener el reemplazo de un "
            "producto defectuoso, o devolver el producto y recuperar su dinero, sin incluir los gastos de envío.",
            "¿Cuáles son las reglas de los bonos?",
            "¿Cómo se calcula el bono por volumen?",
            "¿Los productos tienen garantía?",
        ],
    },
    "pt": {
        "refused": [
            "Você pode garantir que eu vou ganhar dinheiro se eu me cadastrar?",
            "Renda garantida se você se juntar a nós!",
            "Você vai ganhar R$ 2.000 por mês, garantido.",
            "Minha renda é garantida?",
            "Renda passiva e liberdade financeira garantidas.",
            "Nós garantimos que você vai ganhar dinheiro.",
        ],
        "allowed": [
            "Qual é a política de devolução?",
            "Existe uma garantia de reembolso?",
            "Os clientes têm 100% de satisfação garantida com os produtos e podem obter reembolso em até 30 dias.",
            "Sim, a Forever oferece garantia de reembolso: os clientes têm garantia de satisfação de 100% com os "
            "produtos. Em até 30 dias após a compra, podem obter a substituição de um produto com defeito ou devolver "
            "o produto e receber o dinheiro de volta, excluindo o frete.",
            "Quais são as regras de bônus?",
            "Como é calculado o bônus de volume?",
            "Os produtos têm garantia?",
        ],
    },
    "de": {
        "refused": [
            "Können Sie garantieren, dass ich Geld verdiene, wenn ich mitmache?",
            "Garantiertes Einkommen, wenn Sie mitmachen!",
            "Sie verdienen garantiert 2.000 € im Monat.",
            "Ist mein Einkommen garantiert?",
            "Passives Einkommen und finanzielle Freiheit garantiert.",
            "Wir garantieren Ihnen, dass Sie Geld verdienen werden.",
            "Koennen Sie garantieren, dass ich Geld verdiene, wenn ich beitrete?",
        ],
        "allowed": [
            "Wie lautet die Rückgaberichtlinie?",
            "Gibt es eine Geld-zurück-Garantie?",
            "Kunden erhalten eine 100%ige Zufriedenheitsgarantie auf die Produkte und können innerhalb von 30 Tagen "
            "eine Rückerstattung erhalten.",
            "Ja, Forever bietet eine Geld-zurück-Garantie: Kunden haben eine 100%ige Zufriedenheitsgarantie auf die "
            "Produkte. Innerhalb von 30 Tagen nach dem Kauf können sie ein defektes Produkt ersetzen lassen oder das "
            "Produkt zurückgeben und ihr Geld zurückerhalten, ausgenommen Versandkosten.",
            "Welche Bonusregeln gelten?",
            "Wie wird der Volumenbonus berechnet?",
            "Gibt es eine Garantie auf die Produkte?",
            "Gibt es eine Geld-zuruck-Garantie?",
        ],
    },
    "nl": {
        "refused": [
            "Kunt u garanderen dat ik geld verdien als ik lid word?",
            "Gegarandeerd inkomen als je meedoet!",
            "Je verdient gegarandeerd € 2.000 per maand.",
            "Is mijn inkomen gegarandeerd?",
            "Passief inkomen en financiële vrijheid gegarandeerd.",
            "Wij garanderen dat u geld gaat verdienen.",
        ],
        "allowed": [
            "Wat is het retourbeleid?",
            "Is er een geld-terug-garantie?",
            "Klanten krijgen gegarandeerd 100% tevredenheid over het product en kunnen binnen 30 dagen een "
            "terugbetaling krijgen.",
            "Ja, Forever biedt een geld-terug-garantie: klanten krijgen een tevredenheidsgarantie van 100% op de "
            "producten. Binnen 30 dagen na aankoop kunnen ze een defect product laten vervangen of het product "
            "retourneren en hun geld terugkrijgen, exclusief verzendkosten.",
            "Wat zijn de bonusregels?",
            "Hoe wordt de volumebonus berekend?",
            "Is er garantie op de producten?",
        ],
    },
    "it": {
        "refused": [
            "Puoi garantirmi che guadagnerò soldi se mi iscrivo?",
            "Reddito garantito se ti unisci a noi!",
            "Guadagnerai 2.000 € al mese, garantito.",
            "Il mio reddito è garantito?",
            "Reddito passivo e libertà finanziaria garantiti.",
            "Ti garantiamo che guadagnerai denaro.",
        ],
        "allowed": [
            "Qual è la politica di reso?",
            "C'è una garanzia soddisfatti o rimborsati?",
            "I clienti hanno la soddisfazione garantita al 100% sui prodotti e possono ottenere un rimborso entro "
            "30 giorni.",
            "Sì, Forever offre la garanzia soddisfatti o rimborsati: i clienti hanno una garanzia di soddisfazione del "
            "100% sui prodotti. Entro 30 giorni dall'acquisto possono ottenere la sostituzione di un prodotto "
            "difettoso oppure restituire il prodotto e riavere i loro soldi, escluse le spese di spedizione.",
            "Quali sono le regole dei bonus?",
            "Come viene calcolato il bonus volume?",
            "C'è una garanzia sui prodotti?",
        ],
    },
    "sv": {
        "refused": [
            "Kan du garantera att jag tjänar pengar om jag går med?",
            "Garanterad inkomst om du går med!",
            "Du tjänar garanterat 20 000 kr i månaden.",
            "Är min inkomst garanterad?",
            "Passiv inkomst och ekonomisk frihet garanterad.",
            "Vi garanterar att du kommer att tjäna pengar.",
        ],
        "allowed": [
            "Vad är returpolicyn?",
            "Finns det en pengarna-tillbaka-garanti?",
            "Kunderna garanteras 100 % nöjdhet med produkterna och kan få återbetalning inom 30 dagar.",
            "Ja, Forever erbjuder en pengarna-tillbaka-garanti: kunderna har en 100 % nöjd-kund-garanti på produkterna. "
            "Inom 30 dagar från köpet kan de få en ny ersättningsprodukt för en defekt produkt, eller returnera "
            "produkten och få pengarna tillbaka, exklusive fraktkostnad.",
            "Vilka är bonusreglerna?",
            "Hur beräknas volymbonusen?",
            "Finns det garanti på produkterna?",
        ],
    },
    "da": {
        "refused": [
            "Kan du garantere, at jeg tjener penge, hvis jeg melder mig ind?",
            "Garanteret indkomst, hvis du bliver medlem!",
            "Du tjener garanteret 15.000 kr. om måneden.",
            "Er min indkomst garanteret?",
            "Passiv indkomst og økonomisk frihed garanteret.",
            "Vi garanterer, at du vil tjene penge.",
        ],
        "allowed": [
            "Hvad er returpolitikken?",
            "Er der en penge-tilbage-garanti?",
            "Kunderne er garanteret 100 % tilfredshed med produkterne og kan få pengene refunderet inden for 30 dage.",
            "Ja, Forever tilbyder en penge-tilbage-garanti: kunderne har en 100 % tilfredshedsgaranti på produkterne. "
            "Inden for 30 dage efter købet kan de få et nyt produkt i stedet for et defekt produkt eller returnere "
            "produktet og få pengene tilbage, eksklusive forsendelsesomkostninger.",
            "Hvad er reglerne for bonusser?",
            "Hvordan beregnes volumenbonussen?",
            "Er der garanti på produkterne?",
        ],
    },
    "no": {
        "refused": [
            "Kan du garantere at jeg tjener penger hvis jeg blir med?",
            "Garantert inntekt hvis du blir med!",
            "Du tjener garantert 20 000 kr i måneden.",
            "Er inntekten min garantert?",
            "Passiv inntekt og økonomisk frihet garantert.",
            "Vi garanterer at du kommer til å tjene penger.",
        ],
        "allowed": [
            "Hva er returpolicyen?",
            "Finnes det en pengene-tilbake-garanti?",
            "Kundene er garantert 100 % tilfredshet med produktene og kan få pengene tilbake innen 30 dager.",
            "Ja, Forever tilbyr en pengene-tilbake-garanti: kundene har 100 % tilfredshetsgaranti på produktene. "
            "Innen 30 dager etter kjøpet kan de få et nytt produkt i stedet for et defekt produkt, eller returnere "
            "produktet og få pengene tilbake, eksklusive fraktkostnader.",
            "Hva er reglene for bonuser?",
            "Hvordan beregnes volumbonusen?",
            "Er det garanti på produktene?",
        ],
    },
    "fi": {
        "refused": [
            "Voitteko taata, että ansaitsen rahaa, jos liityn?",
            "Taattu tulo, jos liityt mukaan!",
            "Ansaitset taatusti 2 000 euroa kuukaudessa.",
            "Onko tuloni taattu?",
            "Passiiviset tulot ja taloudellinen vapaus taattu.",
            "Takaamme, että tienaat rahaa.",
            "Voitko taata, etta ansaitsen rahaa, jos liityn?",
        ],
        "allowed": [
            "Mikä on palautuskäytäntö?",
            "Onko teillä rahat takaisin -takuu?",
            "Asiakkaille taataan 100 %:n tyytyväisyys tuotteisiin, ja he voivat saada hyvityksen 30 päivän kuluessa.",
            "Kyllä, Forever tarjoaa rahat takaisin -takuun: asiakkailla on 100 %:n tyytyväisyystakuu tuotteisiin. "
            "30 päivän kuluessa ostosta he voivat saada viallisen tuotteen tilalle uuden tai palauttaa tuotteen ja "
            "saada rahansa takaisin, toimituskuluja lukuun ottamatta.",
            "Mitkä ovat bonussäännöt?",
            "Miten volyymibonus lasketaan?",
            "Onko tuotteilla takuu?",
        ],
    },
    "ru": {
        "refused": [
            "Можете ли вы гарантировать, что я заработаю деньги, если присоединюсь?",
            "Гарантированный доход, если вы присоединитесь!",
            "Вы будете зарабатывать 100 000 рублей в месяц, гарантированно.",
            "Мой доход гарантирован?",
            "Пассивный доход и финансовая свобода гарантированы.",
            "Мы гарантируем, что вы будете зарабатывать деньги.",
            "Mozhete li vy garantirovat, chto ya zarabotayu dengi, esli prisoedinyus?",
        ],
        "allowed": [
            "Какова политика возврата?",
            "Есть ли гарантия возврата денег?",
            "Клиентам гарантируется 100% удовлетворённость продукцией, и они могут получить возврат средств в течение "
            "30 дней.",
            "Да, Forever предоставляет гарантию возврата денег: клиентам гарантирована 100% удовлетворённость "
            "продукцией. В течение 30 дней после покупки они могут получить замену бракованного продукта или вернуть "
            "продукт и получить деньги обратно, за исключением стоимости доставки.",
            "Каковы правила начисления бонусов?",
            "Как рассчитывается бонус за объём?",
            "Есть ли гарантия на продукцию?",
            "Est li garantiya vozvrata deneg?",
        ],
    },
    "sr-Latn": {
        "refused": [
            "Možete li da garantujete da ću zaraditi novac ako se pridružim?",
            "Garantovani prihod ako nam se pridružite!",
            "Zarađivaćete 200.000 dinara mesečno, garantovano.",
            "Da li je moj prihod garantovan?",
            "Pasivni prihod i finansijska sloboda zagarantovani.",
            "Garantujemo vam da ćete zaraditi novac.",
            "Mozete li garantovati da cu zaraditi novac ako se pridruzim?",
        ],
        "allowed": [
            "Kakva je politika povraćaja?",
            "Da li postoji garancija povraćaja novca?",
            "Kupcima je zagarantovano 100% zadovoljstvo proizvodima i mogu dobiti povraćaj novca u roku od 30 dana.",
            "Da, Forever nudi garanciju povraćaja novca: kupcima je zagarantovano 100% zadovoljstvo proizvodima. "
            "U roku od 30 dana od kupovine mogu dobiti zamenu za neispravan proizvod ili vratiti proizvod i dobiti "
            "novac nazad, bez troškova dostave.",
            "Koja su pravila za bonuse?",
            "Kako se obračunava bonus na promet?",
            "Da li proizvodi imaju garanciju?",
        ],
    },
    "sr-Cyrl": {
        "refused": [
            "Можете ли да гарантујете да ћу зарадити новац ако се придружим?",
            "Гарантовани приход ако нам се придружите!",
            "Зарађиваћете 200.000 динара месечно, гарантовано.",
            "Да ли је мој приход гарантован?",
            "Пасивни приход и финансијска слобода загарантовани.",
            "Гарантујемо вам да ћете зарадити новац.",
        ],
        "allowed": [
            "Каква је политика поврата?",
            "Да ли постоји гаранција поврата новца?",
            "Купцима је загарантовано 100% задовољство производима и могу добити поврат новца у року од 30 дана.",
            "Да, Forever нуди гаранцију поврата новца: купцима је загарантовано 100% задовољство производима. У року "
            "од 30 дана од куповине могу добити замену за неисправан производ или вратити производ и добити новац "
            "назад, без трошкова доставе.",
            "Која су правила за бонусе?",
            "Како се обрачунава бонус на промет?",
            "Да ли производи имају гаранцију?",
        ],
    },
}

# Ordinary non-English policy wording (delivery cost, minimum order, payment,
# office hours, sponsoring, bonus definitions, warranty with a refund). None of it
# is an income claim.
POLICY_WORDING = [
    "Les frais de livraison sont de 5,90 € par commande.",
    "La commande minimum est de 50 € pour bénéficier de la livraison gratuite.",
    "Vous pouvez payer par carte bancaire, PayPal ou virement.",
    "Le bureau est ouvert du lundi au vendredi de 9 h à 17 h.",
    "Un FBO peut parrainer de nouveaux distributeurs dans n'importe quel pays où Forever est présent.",
    "Le bonus de volume est calculé sur les points de cas personnels et non personnels du mois.",
    "La garantie légale de conformité s'applique : le prix payé vous est remboursé si le produit est défectueux.",
    "Los gastos de envío son de 4,95 € por pedido.",
    "El pedido mínimo es de 1 punto de caja al mes para mantenerse activo.",
    "Aceptamos tarjeta de crédito, transferencia bancaria y PayPal.",
    "Todos los productos tienen garantía de 30 días; si no está satisfecho, le devolvemos el dinero.",
    "Die Versandkosten betragen 4,90 € pro Bestellung.",
    "Der Mindestbestellwert liegt bei 30 €.",
    "Das Büro ist montags bis freitags von 9 bis 17 Uhr geöffnet.",
    "Die Garantie gilt 30 Tage; danach wird kein Geld mehr erstattet.",
    "De verzendkosten bedragen € 4,95 per bestelling en de garantie geldt 30 dagen.",
    "U kunt betalen met iDEAL, creditcard of via een bankoverschrijving.",
    "Le spese di spedizione sono di 6 € per ordine.",
    "L'ordine minimo è di 2 punti caso per diventare attivi.",
    "Fraktkostnaden är 49 kr per order och du kan betala med kort eller Swish.",
    "Kontoret har åbent mandag til fredag kl. 9-16.",
    "Leveringskostnaden er 79 kr, og du kan betale med Vipps eller kort.",
    "Toimituskulut ovat 5,90 euroa tilaukselta.",
    "Стоимость доставки составляет 300 рублей за заказ.",
    "Минимальный заказ — 1 кейс-кредит в месяц.",
    "Troškovi dostave su 350 dinara po porudžbini.",
    "Трошкови доставе су 350 динара по поруџбини.",
    "O pedido mínimo é de 1 ponto por mês para se manter ativo.",
    "Pode pagar com cartão de crédito, boleto ou Pix.",
]

# Adversarial: consumer guarantees next to an income claim, accent-free and mixed text.
ADVERSARIAL_REFUSED = [
    "Geld-zurück-Garantie: Sie verdienen 2.000 € im Monat.",
    "Garantie satisfait ou remboursé et revenu garanti de 2 000 € par mois.",
    "Garantía de devolución del dinero y además te garantizamos ganancias todos los meses.",
    "Pengarna-tillbaka-garanti. Vi garanterar också att du tjänar pengar varje månad.",
    "Soddisfatti o rimborsati: ti garantiamo anche un reddito.",
    "Гарантия возврата денег и гарантированный доход каждый месяц.",
    "garantia de reembolso e renda garantida",
    "Rahat takaisin -takuu ja taattu tulo joka kuukausi.",
    "Zufriedenheitsgarantie auf Ihr Geld und garantiertes Geld jeden Monat.",
    "gegarandeerd geld verdienen met de geld-terug-garantie",
    "Garantiertes income, wenn Sie beitreten.",
    "INGRESOS GARANTIZADOS",
    "revenu garanti",
    "Combien puis-je gagner avec Forever ?",
    "Wie viel kann ich im Monat verdienen?",
    "Сколько я смогу зарабатывать?",
]

# Known limitation kept for parity with English ("There is no guaranteed income."
# is refused as a generated answer): translated disclaimers are refused as well.
NEGATED_DISCLAIMERS = [
    "Il n'y a aucun revenu garanti.",
    "No hay ingresos garantizados.",
    "Es gibt kein garantiertes Einkommen.",
    "Нет гарантированного дохода.",
]

ENGLISH_TEXTS = [
    "Can you guarantee I will earn money if I join?",
    "Guaranteed income if you join.",
    "Is there a money-back guarantee?",
    "What is the return policy?",
    "Customers are guaranteed 100% product satisfaction and can get a refund within 30 days.",
    "You'll earn $5,000 a month. That is backed by our money-back guarantee.",
    "How is the volume bonus calculated?",
]

# W16b (2026-09-12): in most of these languages warranty and guarantee are one word, so a product warranty with
# refunded money ("La garantía cubre defectos; el dinero se devuelve en 30 días.") was refused as an income claim.
# "allowed" starts with the orchestrator's measured texts; every allowed text was refused before W16b. "refused" is
# adversarial and refused before and after: an earnings word, refunded money that recurs, is doubled, earns interest
# or comes with a bonus, or a second guarantee of money.
WARRANTY_REFUND: dict[str, dict[str, list[str]]] = {
    "fr": {
        "allowed": [
            "La garantie couvre les défauts ; l'argent est remboursé sous 30 jours.",
            "La garantie couvre les produits défectueux et l'argent est remboursé sous 30 jours.",
            "Les produits sont garantis contre les défauts de fabrication ; nous vous remboursons l'argent sous 30 "
            "jours.",
            "La garantie s'applique aux produits défectueux ; l'argent vous est rendu sous 30 jours.",
        ],
        "refused": [
            "La garantie couvre les défauts et vos revenus ; l'argent est remboursé sous 30 jours.",
            "La garantie couvre les défauts ; l'argent vous est rendu chaque mois.",
            "La garantie couvre les défauts ; l'argent vous est rendu chaque mois sous forme de bénéfices.",
            "La garantie couvre vos gains ; l'argent est remboursé sous 30 jours.",
            "La garantie couvre les défauts et nous vous garantissons de l'argent chaque mois.",
            "La garantie couvre les défauts ; l'argent est remboursé avec intérêts.",
            "La garantie couvre les défauts ; l'argent est remboursé avec un bonus.",
            "La garantie couvre les défauts ; vous recevez beaucoup d'argent chaque mois.",
            "La garantie couvre les défauts ; l'argent vous est rendu deux fois.",
        ],
    },
    "es": {
        "allowed": [
            "La garantía cubre defectos; el dinero se devuelve en 30 días.",
            "La garantía cubre productos defectuosos y se reembolsa el dinero en 30 días.",
            "La garantía cubre los defectos de fabricación. El dinero se reembolsa en un plazo de 30 días.",
            "Los productos están garantizados contra defectos; si no se pueden reparar, le devolvemos el dinero.",
        ],
        "refused": [
            "La garantía cubre defectos y tus ingresos; el dinero se devuelve en 30 días.",
            "La garantía cubre defectos; el dinero se devuelve cada mes.",
            "La garantía cubre defectos; el dinero se te devuelve cada mes como ganancia.",
            "La garantía cubre tus ganancias; el dinero se devuelve en 30 días.",
            "La garantía cubre defectos y te garantizamos dinero todos los meses.",
            "La garantía cubre defectos; el dinero se devuelve con intereses.",
            "La garantía cubre defectos; el dinero se devuelve con un bono.",
        ],
    },
    "pt": {
        "allowed": [
            "A garantia cobre defeitos; o dinheiro é devolvido em 30 dias.",
            "A garantia cobre produtos defeituosos e o dinheiro é devolvido em até 30 dias.",
            "Os produtos são garantidos contra defeitos de fabricação; o dinheiro é reembolsado.",
            "A garantia cobre a substituição de produtos com defeito. O dinheiro é devolvido em 30 dias.",
        ],
        "refused": [
            "A garantia cobre defeitos e a sua renda; o dinheiro é devolvido em 30 dias.",
            "A garantia cobre defeitos; o dinheiro é devolvido todos os meses.",
            "A garantia cobre defeitos; o dinheiro é devolvido em dobro.",
            "A garantia cobre os seus ganhos; o dinheiro é devolvido em 30 dias.",
            "A garantia cobre defeitos e garantimos dinheiro todos os meses.",
            "A garantia cobre defeitos; o dinheiro é devolvido com juros.",
            "A garantia cobre defeitos; o dinheiro é devolvido com um bônus.",
        ],
    },
    "de": {
        "allowed": [
            "Die Garantie deckt Mängel ab; das Geld wird innerhalb von 30 Tagen erstattet.",
            "Die Garantie deckt defekte Produkte ab und das Geld wird innerhalb von 30 Tagen erstattet.",
            "Die Produkte sind garantiert frei von Mängeln; das Geld wird erstattet.",
            "Die Garantie umfasst die Reparatur von defekten Produkten; sonst wird das Geld erstattet.",
        ],
        "refused": [
            "Die Garantie deckt Mängel und Ihr Einkommen ab; das Geld wird erstattet.",
            "Die Garantie deckt Mängel ab; das Geld wird jeden Monat erstattet.",
            "Die Garantie deckt Mängel ab; das Geld wird doppelt erstattet.",
            "Die Garantie deckt Ihren Verdienst ab; das Geld wird innerhalb von 30 Tagen erstattet.",
            "Die Garantie deckt Mängel ab und wir garantieren Ihnen jeden Monat Geld.",
            "Die Garantie deckt Mängel ab; das Geld wird mit Zinsen erstattet.",
            "Die Garantie deckt Mängel ab; das Geld wird mit einem Bonus erstattet.",
        ],
    },
    "nl": {
        "allowed": [
            "De garantie dekt defecten; het geld wordt binnen 30 dagen terugbetaald.",
            "De garantie dekt defecte producten en het geld wordt binnen 30 dagen terugbetaald.",
            "Producten zijn gegarandeerd vrij van gebreken; u krijgt uw geld terug.",
            "De garantie geldt voor fabricagefouten. Het geld wordt volledig terugbetaald.",
        ],
        "refused": [
            "De garantie dekt defecten en uw inkomen; het geld wordt terugbetaald.",
            "De garantie dekt defecten; het geld wordt elke maand terugbetaald.",
            "De garantie dekt defecten; het geld wordt dubbel terugbetaald.",
            "De garantie dekt uw verdiensten; het geld wordt binnen 30 dagen terugbetaald.",
            "De garantie dekt defecten en wij garanderen u elke maand geld.",
            "De garantie dekt defecten; het geld wordt met rente terugbetaald.",
            "De garantie dekt defecten; het geld wordt terugbetaald met een bonus.",
        ],
    },
    "it": {
        "allowed": [
            "La garanzia copre i difetti; il denaro viene rimborsato entro 30 giorni.",
            "La garanzia copre i prodotti difettosi e il denaro viene rimborsato entro 30 giorni.",
            "I prodotti sono garantiti contro i difetti di fabbricazione; i soldi vengono restituiti.",
            "La garanzia copre la sostituzione dei prodotti difettosi. Il denaro è rimborsato entro 14 giorni.",
        ],
        "refused": [
            "La garanzia copre i difetti e il tuo reddito; il denaro viene rimborsato.",
            "La garanzia copre i difetti; il denaro viene rimborsato ogni mese.",
            "La garanzia copre i difetti; il denaro viene restituito raddoppiato.",
            "La garanzia copre i tuoi guadagni; il denaro viene rimborsato entro 30 giorni.",
            "La garanzia copre i difetti e ti garantiamo soldi ogni mese.",
            "La garanzia copre i difetti; il denaro viene rimborsato con gli interessi.",
            "La garanzia copre i difetti; il denaro viene rimborsato con un bonus.",
        ],
    },
    "sv": {
        "allowed": [
            "Garantin täcker defekter; pengarna återbetalas inom 30 dagar.",
            "Garantin täcker defekta produkter och pengarna återbetalas inom 30 dagar.",
            "Produkterna är garanterat fria från defekter; du får pengarna tillbaka.",
            "Garantin omfattar reparation av defekta produkter. Pengarna återbetalas inom 14 dagar.",
        ],
        "refused": [
            "Garantin täcker defekter och din inkomst; pengarna återbetalas.",
            "Garantin täcker defekter; pengarna återbetalas varje månad.",
            "Garantin täcker defekter; pengarna återbetalas dubbelt.",
            "Garantin täcker din lön; pengarna återbetalas inom 30 dagar.",
            "Garantin täcker defekter och vi garanterar dig pengar varje månad.",
            "Garantin täcker defekter; pengarna återbetalas med ränta.",
            "Garantin täcker defekter; pengarna återbetalas med en bonus.",
        ],
    },
    "da": {
        "allowed": [
            "Garantien dækker fejl; pengene tilbagebetales inden for 30 dage.",
            "Garantien dækker defekte produkter, og pengene tilbagebetales inden for 30 dage.",
            "Produkterne er garanteret fri for fejl; du får pengene tilbage.",
            "Garantien omfatter reparation af defekte produkter. Pengene refunderes inden for 14 dage.",
        ],
        "refused": [
            "Garantien dækker fejl og din indkomst; pengene tilbagebetales.",
            "Garantien dækker fejl; pengene tilbagebetales hver måned.",
            "Garantien dækker fejl; pengene tilbagebetales dobbelt.",
            "Garantien dækker din løn; pengene tilbagebetales inden for 30 dage.",
            "Garantien dækker fejl, og vi garanterer dig penge hver måned.",
            "Garantien dækker fejl; pengene tilbagebetales med renter.",
            "Garantien dækker fejl; pengene tilbagebetales med en bonus.",
        ],
    },
    "no": {
        "allowed": [
            "Garantien dekker feil; pengene betales tilbake innen 30 dager.",
            "Garantien dekker defekte produkter, og pengene betales tilbake innen 30 dager.",
            "Produktene er garantert fri for feil; du får pengene tilbake.",
            "Garantien omfatter reparasjon av defekte produkter. Pengene refunderes innen 14 dager.",
        ],
        "refused": [
            "Garantien dekker feil og inntekten din; pengene betales tilbake.",
            "Garantien dekker feil; pengene betales tilbake hver måned.",
            "Garantien dekker feil; pengene betales tilbake dobbelt.",
            "Garantien dekker lønnen din; pengene betales tilbake innen 30 dager.",
            "Garantien dekker feil, og vi garanterer deg penger hver måned.",
            "Garantien dekker feil; pengene betales tilbake med renter.",
            "Garantien dekker feil; pengene betales tilbake med en bonus.",
        ],
    },
    "fi": {
        "allowed": [
            "Takuu kattaa viat; rahat palautetaan 30 päivän kuluessa.",
            "Takuu kattaa vialliset tuotteet, ja rahat palautetaan 30 päivän kuluessa.",
            "Takuu kattaa valmistusviat. Rahasi palautetaan 14 päivän kuluessa.",
            "Takuu koskee viallisia tuotteita; rahat palautetaan heti.",
        ],
        "refused": [
            "Takuu kattaa viat ja tulosi; rahat palautetaan.",
            "Takuu kattaa viat; rahat palautetaan joka kuukausi.",
            "Takuu kattaa viat; rahat palautetaan kaksinkertaisina.",
            "Takuu kattaa palkkasi; rahat palautetaan 30 päivän kuluessa.",
            "Takuu kattaa viat, ja takaamme sinulle rahaa joka kuukausi.",
            "Takuu kattaa viat; rahat palautetaan korkojen kera.",
            "Takuu kattaa viat; rahat palautetaan bonuksen kera.",
        ],
    },
    "ru": {
        "allowed": [
            "Гарантия распространяется на дефекты; деньги возвращаются в течение 30 дней.",
            "Гарантия распространяется на бракованные товары, и деньги возвращаются в течение 30 дней.",
            "Гарантия покрывает производственные дефекты. Деньги будут возвращены в течение 14 дней.",
            "Гарантия распространяется на замену неисправных товаров; иначе мы вернём вам деньги.",
        ],
        "refused": [
            "Гарантия распространяется на дефекты и ваш доход; деньги возвращаются.",
            "Гарантия распространяется на дефекты; деньги возвращаются каждый месяц.",
            "Гарантия распространяется на дефекты; деньги возвращаются вдвойне.",
            "Гарантия распространяется на вашу зарплату; деньги возвращаются в течение 30 дней.",
            "Гарантия распространяется на дефекты, и мы гарантируем вам деньги каждый месяц.",
            "Гарантия распространяется на дефекты; деньги возвращаются с процентами.",
            "Гарантия распространяется на дефекты; деньги возвращаются вместе с бонусом.",
        ],
    },
    "sr-Latn": {
        "allowed": [
            "Garancija pokriva nedostatke; novac se vraća u roku od 30 dana.",
            "Garancija pokriva neispravne proizvode i novac se vraća u roku od 30 dana.",
            "Garancija pokriva fabričke greške. Novac će vam biti vraćen u roku od 14 dana.",
            "Garancija pokriva zamenu neispravnih proizvoda; u suprotnom vraćamo novac.",
        ],
        "refused": [
            "Garancija pokriva nedostatke i vaš prihod; novac se vraća.",
            "Garancija pokriva nedostatke; novac se vraća svakog meseca.",
            "Garancija pokriva nedostatke; novac se vraća duplo.",
            "Garancija pokriva vašu zaradu; novac se vraća u roku od 30 dana.",
            "Garancija pokriva nedostatke i garantujemo vam novac svakog meseca.",
            "Garancija pokriva nedostatke; novac se vraća sa kamatom.",
            "Garancija pokriva nedostatke; novac se vraća uz bonus.",
        ],
    },
    "sr-Cyrl": {
        "allowed": [
            "Гаранција покрива недостатке; новац се враћа у року од 30 дана.",
            "Гаранција покрива неисправне производе и новац се враћа у року од 30 дана.",
            "Гаранција покрива фабричке грешке. Новац ће вам бити враћен у року од 14 дана.",
            "Гаранција покрива замену неисправних производа; у супротном враћамо новац.",
        ],
        "refused": [
            "Гаранција покрива недостатке и ваш приход; новац се враћа.",
            "Гаранција покрива недостатке; новац се враћа сваког месеца.",
            "Гаранција покрива недостатке; новац се враћа дупло.",
            "Гаранција покрива вашу зараду; новац се враћа у року од 30 дана.",
            "Гаранција покрива недостатке и гарантујемо вам новац сваког месеца.",
            "Гаранција покрива недостатке; новац се враћа са каматом.",
            "Гаранција покрива недостатке; новац се враћа уз бонус.",
        ],
    },
}

REFUSED = [(language, text) for language, cases in CASES.items() for text in cases["refused"]]
ALLOWED = [(language, text) for language, cases in CASES.items() for text in cases["allowed"]]
WARRANTY_ALLOWED = [(language, text) for language, cases in WARRANTY_REFUND.items() for text in cases["allowed"]]
WARRANTY_REFUSED = [(language, text) for language, cases in WARRANTY_REFUND.items() for text in cases["refused"]]

# Fable W16 review, Fix A (2026-09-12): refused on W16, allowed on every income layer by W16b, because refunded money
# next to a prize, premium, payout, lifestyle word, an addition or a large amount was still masked as a refund and the
# warranty was set aside. Refund wording is now masked only when its clause has none of these.
FABLE_W16_REFUND_PRIZE_REFUSED = [
    ("fr", "La garantie couvre les défauts ; l'argent est remboursé, plus une voiture neuve."),
    ("fr", "La garantie couvre les défauts ; l'argent est remboursé avec un supplément de 20 %."),
    ("fr", "La garantie couvre les défauts ; l'argent est remboursé sous forme de versement trimestriel."),
    ("fr", "La garantie couvre les défauts ; l'argent est remboursé, plus cinq mille."),
    ("fr", "La garantie couvre les défauts ; l'argent est remboursé, plus une maison et une Rolex."),
    ("fr", "LA GARANTIE COUVRE LES DÉFAUTS ; L'ARGENT EST REMBOURSÉ, PLUS UNE VOITURE NEUVE."),
    ("fr", "La garantie couvre les defauts ; l'argent est rembourse, plus une voiture neuve."),
    ("fr", "La garantie couvre les défauts ; l'argent est rendu, et rendu encore et encore."),
    ("fr", "La garantie couvre les défauts ; l'argent est remboursé et vous devenez riche."),
    ("es", 'La garantía cubre defectos; el dinero se devuelve y además un coche nuevo.'),
    ("es", 'La garantía cubre defectos; el dinero se devuelve con una prima del 20 %.'),
    ("es", 'La garantía cubre defectos; el dinero se devuelve como pago trimestral.'),
    ("es", 'La garantía cubre defectos; el dinero se devuelve, más cinco mil.'),
    ("es", 'LA GARANTÍA CUBRE DEFECTOS; EL DINERO SE DEVUELVE Y ADEMÁS UN COCHE NUEVO.'),
    ("es", 'La garantia cubre defectos; el dinero se devuelve y ademas un coche nuevo.'),
    ("es", 'Garantía de devolución del dinero; el dinero se devuelve y además un coche nuevo.'),
    ("es", 'La garantía cubre defectos; el dinero se devuelve y te haces rico.'),
    ("es", 'La garantía cubre defectos; el dinero se devuelve, más una casa y un Rolex.'),
    ("es", 'La garantía cubre defectos; el dinero se devuelve con un 50 % extra.'),
    ("de", 'Die Garantie deckt Mängel ab; das Geld wird erstattet, und ein neues Auto obendrauf.'),
    ("de", 'Die Garantie deckt Mängel ab; das Geld wird erstattet, plus fünftausend.'),
    ("de", 'DIE GARANTIE DECKT MÄNGEL AB; DAS GELD WIRD ERSTATTET, UND EIN NEUES AUTO OBENDRAUF.'),
    ("de", 'Die Garantie deckt Maengel ab; das Geld wird erstattet, und ein neues Auto obendrauf.'),
    ("de", 'Die Garantie deckt Mängel ab; das Geld wird erstattet und Sie werden reich.'),
    ("de", 'Die Garantie deckt Mängel ab; das Geld wird erstattet, plus ein Haus und eine Rolex.'),
    ("nl", 'De garantie dekt defecten; het geld wordt terugbetaald, plus een nieuwe auto.'),
    ("nl", 'De garantie dekt defecten; het geld wordt terugbetaald met 20 % premie.'),
    ("nl", 'De garantie dekt defecten; het geld wordt terugbetaald als maandelijkse uitkering.'),
    ("nl", 'De garantie dekt defecten; het geld wordt terugbetaald, plus vijfduizend.'),
    ("nl", 'DE GARANTIE DEKT DEFECTEN; HET GELD WORDT TERUGBETAALD, PLUS EEN NIEUWE AUTO.'),
    ("nl", 'De garantie dekt defecten; het geld wordt terugbetaald en u wordt rijk.'),
    ("it", "La garanzia copre i difetti; il denaro viene rimborsato, più un'auto nuova."),
    ("it", 'La garanzia copre i difetti; il denaro viene rimborsato con un premio del 20 %.'),
    ("it", 'La garanzia copre i difetti; il denaro viene rimborsato, più cinquemila.'),
    ("it", "LA GARANZIA COPRE I DIFETTI; IL DENARO VIENE RIMBORSATO, PIÙ UN'AUTO NUOVA."),
    ("it", 'La garanzia copre i difetti; il denaro viene rimborsato e diventi ricco.'),
    ("pt", 'A garantia cobre defeitos; o dinheiro é devolvido, mais um carro novo.'),
    ("pt", 'A garantia cobre defeitos; o dinheiro é devolvido com um prémio de 20 %.'),
    ("pt", 'A garantia cobre defeitos; o dinheiro é devolvido, mais cinco mil.'),
    ("pt", 'A GARANTIA COBRE DEFEITOS; O DINHEIRO É DEVOLVIDO, MAIS UM CARRO NOVO.'),
    ("pt", 'A garantia cobre defeitos; o dinheiro e devolvido, mais um carro novo.'),
    ("ru", 'Гарантия распространяется на дефекты; деньги возвращаются, плюс новая машина.'),
    ("ru", 'Гарантия распространяется на дефекты; деньги возвращаются с надбавкой 20 %.'),
    ("ru", 'Гарантия распространяется на дефекты; деньги возвращаются и ваша ставка удваивается.'),
    ("ru", 'Гарантия распространяется на дефекты; деньги возвращаются, плюс пять тысяч.'),
    ("ru", 'ГАРАНТИЯ РАСПРОСТРАНЯЕТСЯ НА ДЕФЕКТЫ; ДЕНЬГИ ВОЗВРАЩАЮТСЯ, ПЛЮС НОВАЯ МАШИНА.'),
    ("ru", 'Гарантия распространяется на дефекты; деньги возвращаются, и вы станете богатым.'),
    ("sr-Latn", 'Garancija pokriva nedostatke; novac se vraća, plus novi auto.'),
    ("sr-Latn", 'Garancija pokriva nedostatke; novac se vraća sa premijom od 20 %.'),
    ("sr-Latn", 'Garancija pokriva nedostatke; novac se vraća kao mesečna isplata.'),
    ("sr-Latn", 'Garancija pokriva nedostatke; novac se vraća, plus pet hiljada.'),
    ("sr-Latn", 'GARANCIJA POKRIVA NEDOSTATKE; NOVAC SE VRAĆA, PLUS NOVI AUTO.'),
    ("sr-Cyrl", 'Гаранција покрива недостатке; новац се враћа, плус нови ауто.'),
    ("sr-Cyrl", 'Гаранција покрива недостатке; новац се враћа као месечна исплата.'),
    ("sv", 'Garantin täcker defekter; pengarna återbetalas, plus en ny bil.'),
    ("sv", 'Garantin täcker defekter; pengarna återbetalas med 20 % premie.'),
    ("sv", 'Garantin täcker defekter; pengarna återbetalas, plus femtusen.'),
    ("sv", 'GARANTIN TÄCKER DEFEKTER; PENGARNA ÅTERBETALAS, PLUS EN NY BIL.'),
    ("sv", 'Garantin tacker defekter; pengarna aterbetalas, plus en ny bil.'),
    ("da", 'Garantien dækker fejl; pengene tilbagebetales, plus en ny bil.'),
    ("no", 'Garantien dekker feil; pengene betales tilbake, plus en ny bil.'),
    ("fi", 'Takuu kattaa viat; rahat palautetaan, plus uusi auto.'),
]

# Fable W16 review, Fix C: Spanish singular "ingreso" after an article or possessive is an earnings word. Allowed on
# every base; the disclaimer is refused like every other translated disclaimer (parity with English).
FABLE_W16_ES_INGRESO_REFUSED = [
    ("es", "Te garantizamos un ingreso si te unes."),
    ("es", "Garantizamos un ingreso."),
    ("es", "No garantizamos ningún ingreso."),
]

# Controls, allowed before and after: "ingreso" as an entrance, refunds to the original payment method, shipping costs.
FABLE_W16_ALLOWED = [
    ("es", "El ingreso a la oficina es por la puerta lateral."),
    ("es", "Garantizamos el ingreso a la oficina por la puerta lateral."),
    ("es", "La garantía cubre defectos; el ingreso al almacén se hace por la puerta lateral."),
    ("es", "Garantía de devolución del dinero; el dinero se devuelve al método de pago original."),
    ("fr", "Garantie satisfait ou remboursé ; l'argent est remboursé sur le moyen de paiement d'origine."),
    ("fr", "La garantie couvre les défauts ; l'argent est remboursé, plus les frais de port."),
    ("de", "Die Garantie deckt Mängel ab; das Geld wird erstattet, plus Versandkosten."),
]


def _context(text: str, language: str) -> RiskContext:
    return RiskContext(user_message=text, country="US", language=language.split("-")[0], role="new_prospect",
                       correlation_id="cid")


def _evaluate(text: str, language: str, *, answer: bool):
    return governance_engine.evaluate(
        text=text, country="US", language=language.split("-")[0], correlation_id="cid", is_generated_answer=answer,
    )


def _ids(pairs):
    return [f"{language}-{index}" for index, (language, _) in enumerate(pairs)]


def test_every_language_has_the_required_coverage() -> None:
    expected = {"da", "de", "es", "fi", "fr", "it", "nl", "no", "pt", "ru", "sr-Latn", "sr-Cyrl", "sv"}
    assert set(CASES) == expected
    for language, cases in CASES.items():
        assert len(cases["refused"]) >= 6, language
        assert len(cases["allowed"]) >= 5, language


@pytest.mark.parametrize("language,text", REFUSED, ids=_ids(REFUSED))
def test_translated_income_claims_are_flagged_by_the_policy(language, text) -> None:
    issues = IncomeClaimPolicy().evaluate(_context(text, language))
    assert [issue.code for issue in issues] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("language,text", REFUSED, ids=_ids(REFUSED))
def test_translated_income_claims_are_refused_by_governance(language, text, answer) -> None:
    decision = _evaluate(text, language, answer=answer)
    assert decision.allowed is False
    assert decision.provider == "risk_engine"
    assert [issue["code"] for issue in decision.metadata["risk"]["issues"]] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("language,text", ALLOWED, ids=_ids(ALLOWED))
def test_translated_return_policy_and_bonus_wording_is_not_an_income_claim(language, text) -> None:
    assert IncomeClaimPolicy().evaluate(_context(text, language)) == []


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("language,text", ALLOWED, ids=_ids(ALLOWED))
def test_translated_return_policy_and_bonus_wording_passes_governance(language, text, answer) -> None:
    decision = _evaluate(text, language, answer=answer)
    assert decision.allowed is True, decision


def test_every_language_has_warranty_refund_coverage() -> None:
    assert set(WARRANTY_REFUND) == set(CASES)
    for language, cases in WARRANTY_REFUND.items():
        assert len(cases["allowed"]) >= 4, language
        assert len(cases["refused"]) >= 4, language


@pytest.mark.parametrize("language,text", WARRANTY_ALLOWED, ids=_ids(WARRANTY_ALLOWED))
def test_translated_warranty_with_refunded_money_is_not_an_income_claim(language, text) -> None:
    assert IncomeClaimPolicy().evaluate(_context(text, language)) == []


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("language,text", WARRANTY_ALLOWED, ids=_ids(WARRANTY_ALLOWED))
def test_translated_warranty_with_refunded_money_passes_governance(language, text, answer) -> None:
    decision = _evaluate(text, language, answer=answer)
    assert decision.allowed is True, decision


@pytest.mark.parametrize("language,text", WARRANTY_REFUSED, ids=_ids(WARRANTY_REFUSED))
def test_translated_warranty_next_to_an_income_claim_is_flagged_by_the_policy(language, text) -> None:
    issues = IncomeClaimPolicy().evaluate(_context(text, language))
    assert [issue.code for issue in issues] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("language,text", WARRANTY_REFUSED, ids=_ids(WARRANTY_REFUSED))
def test_translated_warranty_next_to_an_income_claim_is_refused_by_governance(language, text, answer) -> None:
    decision = _evaluate(text, language, answer=answer)
    assert decision.allowed is False
    assert decision.provider == "risk_engine"
    assert [issue["code"] for issue in decision.metadata["risk"]["issues"]] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("text", POLICY_WORDING)
def test_ordinary_policy_wording_is_not_an_income_claim(text) -> None:
    assert contains_translated_income_claim(text) is False
    assert IncomeClaimPolicy().evaluate(_context(text, "en")) == []


@pytest.mark.parametrize("text", ADVERSARIAL_REFUSED)
def test_adversarial_translated_income_claims_are_refused(text) -> None:
    assert IncomeClaimPolicy().evaluate(_context(text, "en"))
    assert _evaluate(text, "en", answer=True).allowed is False


@pytest.mark.parametrize("text", NEGATED_DISCLAIMERS)
def test_translated_income_disclaimers_are_refused_like_english(text) -> None:
    assert IncomeClaimPolicy().evaluate(_context(text, "en"))
    assert IncomeClaimPolicy().evaluate(_context("There is no guaranteed income.", "en"))


@pytest.mark.parametrize("text", ENGLISH_TEXTS)
def test_english_verdicts_come_only_from_the_english_rule(text) -> None:
    assert contains_translated_income_claim(text) is False


def _canned_responses():
    path = Path(__file__).resolve().parents[2] / "config" / "conversation_routes.json"
    locales = json.loads(path.read_text(encoding="utf-8"))["locales"]
    return [
        (f"{language}:{key}", value)
        for language, locale in locales.items() if language != "en"
        for key, value in locale.get("responses", {}).items()
        # The income refusal itself names income and guarantees, as the English one does
        # (the English text is refused by the English rule too); it is only ever sent
        # after a refusal and is never governed.
        if isinstance(value, str) and key != "income_claim"
    ]


@pytest.mark.parametrize("key,text", _canned_responses())
def test_canned_non_english_responses_are_not_income_claims(key, text) -> None:
    assert IncomeClaimPolicy().evaluate(_context(text, key.split(":")[0])) == [], key


def test_the_english_income_refusal_text_is_already_refused_by_the_english_rule() -> None:
    english = "I can't share income projections or guarantees - that's not something I'm able to speak to."
    assert IncomeClaimPolicy().evaluate(_context(english, "en"))


@pytest.mark.parametrize("language,text", FABLE_W16_REFUND_PRIZE_REFUSED + FABLE_W16_ES_INGRESO_REFUSED,
                         ids=_ids(FABLE_W16_REFUND_PRIZE_REFUSED + FABLE_W16_ES_INGRESO_REFUSED))
def test_translated_refund_with_a_prize_or_singular_income_is_flagged_by_the_policy(language, text) -> None:
    issues = IncomeClaimPolicy().evaluate(_context(text, language))
    assert [issue.code for issue in issues] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("language,text", FABLE_W16_REFUND_PRIZE_REFUSED + FABLE_W16_ES_INGRESO_REFUSED,
                         ids=_ids(FABLE_W16_REFUND_PRIZE_REFUSED + FABLE_W16_ES_INGRESO_REFUSED))
def test_translated_refund_with_a_prize_or_singular_income_is_refused_by_governance(language, text, answer) -> None:
    decision = _evaluate(text, language, answer=answer)
    assert decision.allowed is False
    assert decision.provider == "risk_engine"
    assert [issue["code"] for issue in decision.metadata["risk"]["issues"]] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("language,text", FABLE_W16_ALLOWED, ids=_ids(FABLE_W16_ALLOWED))
def test_translated_entrance_refund_and_shipping_wording_is_not_an_income_claim(language, text, answer) -> None:
    assert IncomeClaimPolicy().evaluate(_context(text, language)) == []
    decision = _evaluate(text, language, answer=answer)
    assert decision.allowed is True, decision


def test_translated_gain_or_prize_words_in_the_refund_clause() -> None:
    """Fable W16 Fix A samples (folded text): what keeps refunded money counting, and what does not."""
    from app.risk.policies.income_claim_translations import GAIN_RE, fold

    for text in ("plus une voiture neuve", "y además un coche nuevo", "und ein neues Auto obendrauf",
                 "con una prima del 20 %", "als maandelijkse uitkering", "kao mesečna isplata", "plus 5.000 €",
                 "ваша ставка удваивается"):
        assert GAIN_RE.search(fold(text)), text
    for text in ("sous 30 jours", "en un plazo de 30 dias", "innerhalb von 30 tagen", "u roku od 30 dana",
                 "в течение 30 дней", "30 päivän kuluessa", "entro 14 giorni", "plus les frais de port",
                 "plus Versandkosten", "al método de pago original", "sur le moyen de paiement d'origine",
                 "плюс стоимость доставки", "plus troškovi dostave", "plus fraktkostnaden", "plus toimituskulut",
                 "plus fragt", "de nuevo si el producto falla"):
        assert not GAIN_RE.search(fold(text)), text
