# AskVera - wording review packet for Legal and market translators

Date: 2026-09-07. Prepared for a single combined review.

**Status: merged to `main` (PR #57) but NOT yet deployed.** Users still see the
current wording from `7d29dad`. Nothing in Ask A reaches a user until the next
backend deploy, so it can still be changed or reverted before release.

There are two asks. Ask A is a factual correction already implemented and
awaiting sign-off. Ask B is blocked and needs Legal to supply wording.

---

## Ask A - confirm the corrected source name (12 locales)

### Why

The refusal and capability copy named the **global office directory**. That
document is retired and is no longer an active publication. The only approved
global source is the **International Sponsoring Directory**
(`International-Sponsoring-Directory.pdf`). The copy therefore pointed users at
a document that no longer exists.

Three different names were in use across shipped copy: `global office
directory` (retired, 11 locales), `global sponsoring directory` (English only)
and `international sponsoring directory`. All now use the last, which matches
the actual document title.

### What did NOT change

- The refusal itself, its tone, and the medical/health advice it gives.
- Phrases about reaching *an office* - sponsoring records still carry office
  contact details, so "how to reach an office" remains correct.
- Any internal identifier. Only user-visible prose changed.

### What Legal/translators are asked to confirm

1. That naming the International Sponsoring Directory in a medical refusal is
   acceptable, and that pointing to a retired document was the defect.
2. That each translated document name is idiomatic and grammatically agrees
   with the sentence around it. These were produced by the engineering change,
   **not by a native speaker or certified translator.**

### A1. Medical-claim refusal (`config/claim_safety.json`)

Full strings, since the document name has to agree with the sentence.

#### English (`en`)

- **Current (live today):** I'm sorry, but I can't confirm that a Forever Living product treats or cures a disease. AskVera can help with approved Forever Living company policies and information from the global office directory. For a medical question, please speak with a qualified healthcare professional.
- **Proposed (on main):** I'm sorry, but I can't confirm that a Forever Living product treats or cures a disease. AskVera can help with approved Forever Living company policies and information from the international sponsoring directory. For a medical question, please speak with a qualified healthcare professional.
- **Back-translation of the new name:** the international sponsoring directory

#### French (`fr`)

- **Current (live today):** Je suis désolée, mais je ne peux pas confirmer qu'un produit Forever Living traite ou guérit une maladie. AskVera peut vous aider avec les politiques approuvées de Forever Living et les informations du répertoire mondial des bureaux. Pour une question médicale, consultez un professionnel de santé qualifié.
- **Proposed (on main):** Je suis désolée, mais je ne peux pas confirmer qu'un produit Forever Living traite ou guérit une maladie. AskVera peut vous aider avec les politiques approuvées de Forever Living et les informations de l'annuaire international de parrainage. Pour une question médicale, consultez un professionnel de santé qualifié.
- **Back-translation of the new name:** the international sponsoring directory (annuaire = directory, parrainage = sponsoring)

#### Spanish (`es`)

- **Current (live today):** Lo siento, pero no puedo confirmar que un producto de Forever Living trate o cure una enfermedad. AskVera puede ayudarle con las políticas aprobadas de Forever Living y la información del directorio mundial de oficinas. Para una pregunta médica, consulte a un profesional de la salud cualificado.
- **Proposed (on main):** Lo siento, pero no puedo confirmar que un producto de Forever Living trate o cure una enfermedad. AskVera puede ayudarle con las políticas aprobadas de Forever Living y la información del directorio internacional de patrocinio. Para una pregunta médica, consulte a un profesional de la salud cualificado.
- **Back-translation of the new name:** the international sponsoring directory (patrocinio = sponsoring)

#### German (`de`)

- **Current (live today):** Es tut mir leid, aber ich kann nicht bestätigen, dass ein Produkt von Forever Living eine Krankheit behandelt oder heilt. AskVera kann bei genehmigten Unternehmensrichtlinien von Forever Living und Informationen aus dem weltweiten Büroverzeichnis helfen. Bei medizinischen Fragen wenden Sie sich bitte an qualifiziertes medizinisches Fachpersonal.
- **Proposed (on main):** Es tut mir leid, aber ich kann nicht bestätigen, dass ein Produkt von Forever Living eine Krankheit behandelt oder heilt. AskVera kann bei genehmigten Unternehmensrichtlinien von Forever Living und Informationen aus dem internationalen Sponsoring-Verzeichnis helfen. Bei medizinischen Fragen wenden Sie sich bitte an qualifiziertes medizinisches Fachpersonal.
- **Back-translation of the new name:** the international sponsoring directory (Verzeichnis = directory)

#### Dutch (`nl`)

- **Current (live today):** Het spijt me, maar ik kan niet bevestigen dat een product van Forever Living een ziekte behandelt of geneest. AskVera kan u helpen met goedgekeurd bedrijfsbeleid van Forever Living en informatie uit de wereldwijde kantoordirectory. Raadpleeg voor medische vragen een gekwalificeerde zorgprofessional.
- **Proposed (on main):** Het spijt me, maar ik kan niet bevestigen dat een product van Forever Living een ziekte behandelt of geneest. AskVera kan u helpen met goedgekeurd bedrijfsbeleid van Forever Living en informatie uit de internationale sponsordirectory. Raadpleeg voor medische vragen een gekwalificeerde zorgprofessional.
- **Back-translation of the new name:** the international sponsor directory

#### Italian (`it`)

- **Current (live today):** Mi dispiace, ma non posso confermare che un prodotto Forever Living tratti o curi una malattia. AskVera può aiutarti con le politiche aziendali approvate di Forever Living e con le informazioni dell'elenco globale degli uffici. Per una domanda medica, consulta un professionista sanitario qualificato.
- **Proposed (on main):** Mi dispiace, ma non posso confermare che un prodotto Forever Living tratti o curi una malattia. AskVera può aiutarti con le politiche aziendali approvate di Forever Living e con le informazioni dell'elenco internazionale di sponsorizzazione. Per una domanda medica, consulta un professionista sanitario qualificato.
- **Back-translation of the new name:** the international sponsorship list/directory (elenco = list)

#### Danish (`da`)

- **Current (live today):** Jeg er ked af det, men jeg kan ikke bekræfte, at et Forever Living-produkt behandler eller helbreder en sygdom. AskVera kan hjælpe med godkendte virksomhedspolitikker fra Forever Living og oplysninger fra det globale kontorkatalog. Ved medicinske spørgsmål bør du tale med en kvalificeret sundhedsfaglig person.
- **Proposed (on main):** Jeg er ked af det, men jeg kan ikke bekræfte, at et Forever Living-produkt behandler eller helbreder en sygdom. AskVera kan hjælpe med godkendte virksomhedspolitikker fra Forever Living og oplysninger fra det internationale sponsorkatalog. Ved medicinske spørgsmål bør du tale med en kvalificeret sundhedsfaglig person.
- **Back-translation of the new name:** the international sponsor catalogue

#### Finnish (`fi`)

- **Current (live today):** Olen pahoillani, mutta en voi vahvistaa, että Forever Living -tuote hoitaa tai parantaa sairautta. AskVera voi auttaa Forever Livingin hyväksytyissä yrityskäytännöissä ja maailmanlaajuisen toimistohakemiston tiedoissa. Käänny lääketieteellisissä kysymyksissä pätevän terveydenhuollon ammattilaisen puoleen.
- **Proposed (on main):** Olen pahoillani, mutta en voi vahvistaa, että Forever Living -tuote hoitaa tai parantaa sairautta. AskVera voi auttaa Forever Livingin hyväksytyissä yrityskäytännöissä ja kansainvälisen sponsorointihakemiston tiedoissa. Käänny lääketieteellisissä kysymyksissä pätevän terveydenhuollon ammattilaisen puoleen.
- **Back-translation of the new name:** the international sponsoring directory (hakemisto = directory)

#### Norwegian (`no`)

- **Current (live today):** Beklager, men jeg kan ikke bekrefte at et Forever Living-produkt behandler eller kurerer en sykdom. AskVera kan hjelpe med godkjente selskapspolicyer fra Forever Living og informasjon fra den globale kontorkatalogen. Ved medisinske spørsmål bør du snakke med kvalifisert helsepersonell.
- **Proposed (on main):** Beklager, men jeg kan ikke bekrefte at et Forever Living-produkt behandler eller kurerer en sykdom. AskVera kan hjelpe med godkjente selskapspolicyer fra Forever Living og informasjon fra den internasjonale sponsorkatalogen. Ved medisinske spørsmål bør du snakke med kvalifisert helsepersonell.
- **Back-translation of the new name:** the international sponsor catalogue

#### Serbian (`sr`)

- **Current (live today):** Žao mi je, ali ne mogu da potvrdim da proizvod kompanije Forever Living leči ili izlečuje bolest. AskVera može da pomogne sa odobrenim pravilima kompanije Forever Living i informacijama iz globalnog imenika kancelarija. Za medicinska pitanja obratite se kvalifikovanom zdravstvenom radniku.
- **Proposed (on main):** Žao mi je, ali ne mogu da potvrdim da proizvod kompanije Forever Living leči ili izlečuje bolest. AskVera može da pomogne sa odobrenim pravilima kompanije Forever Living i informacijama iz međunarodnog imenika sponzorstva. Za medicinska pitanja obratite se kvalifikovanom zdravstvenom radniku.
- **Back-translation of the new name:** the international sponsorship directory (imenik = directory)

#### Swedish (`sv`)

- **Current (live today):** Jag är ledsen, men jag kan inte bekräfta att en Forever Living-produkt behandlar eller botar en sjukdom. AskVera kan hjälpa till med godkända företagspolicyer från Forever Living och information från den globala kontorskatalogen. Vid medicinska frågor bör du prata med kvalificerad vårdpersonal.
- **Proposed (on main):** Jag är ledsen, men jag kan inte bekräfta att en Forever Living-produkt behandlar eller botar en sjukdom. AskVera kan hjälpa till med godkända företagspolicyer från Forever Living och information från den internationella sponsorkatalogen. Vid medicinska frågor bör du prata med kvalificerad vårdpersonal.
- **Back-translation of the new name:** the international sponsor catalogue

#### Russian (`ru`)

- **Current (live today):** Мне жаль, но я не могу подтвердить, что продукт Forever Living лечит или излечивает заболевание. AskVera может помочь с утверждёнными политиками компании Forever Living и информацией из глобального справочника офисов. По медицинским вопросам обратитесь к квалифицированному медицинскому специалисту.
- **Proposed (on main):** Мне жаль, но я не могу подтвердить, что продукт Forever Living лечит или излечивает заболевание. AskVera может помочь с утверждёнными политиками компании Forever Living и информацией из международного справочника спонсорства. По медицинским вопросам обратитесь к квалифицированному медицинскому специалисту.
- **Back-translation of the new name:** the international sponsorship reference/directory (справочник = reference book)

### A2. Capability and off-topic copy (`config/conversation_routes.json`)

Same change, same 12 locales, in the 'what can you help with' and off-topic
replies. Full English shown; the other locales change only the document name
in the identical position.

**English `capability`**

- Current: I'm AskVera, your guide to Forever Living's official policies and the global office directory. Ask me about qualification rules, bonuses, compliance questions, or how to reach an office, and I'll find the approved answer for you.
- Proposed: I'm AskVera, your guide to Forever Living's official policies and the international sponsoring directory. Ask me about qualification rules, bonuses, compliance questions, or how to reach an office, and I'll find the approved answer for you.

**English `off_topic`**

- Current: I'm sorry, but I can't help with that question. AskVera can help with approved Forever Living company policies and information from the global office directory. Please ask me about one of those areas, and I'll be happy to help.
- Proposed: I'm sorry, but I can't help with that question. AskVera can help with approved Forever Living company policies and information from the international sponsoring directory. Please ask me about one of those areas, and I'll be happy to help.

| Locale | Current name | Proposed name | Back-translation |
| --- | --- | --- | --- |
| English (`en`) | the global office directory | the international sponsoring directory | the international sponsoring directory |
| French (`fr`) | du répertoire mondial des bureaux | de l'annuaire international de parrainage | the international sponsoring directory (annuaire = directory, parrainage = sponsoring) |
| Spanish (`es`) | del directorio mundial de oficinas | del directorio internacional de patrocinio | the international sponsoring directory (patrocinio = sponsoring) |
| German (`de`) | aus dem weltweiten Büroverzeichnis | aus dem internationalen Sponsoring-Verzeichnis | the international sponsoring directory (Verzeichnis = directory) |
| Dutch (`nl`) | uit de wereldwijde kantorengids | uit de internationale sponsordirectory | the international sponsor directory |
| Italian (`it`) | dell’elenco globale degli uffici | dell’elenco internazionale di sponsorizzazione | the international sponsorship list/directory (elenco = list) |
| Danish (`da`) | fra den globale kontoroversigt | fra det internationale sponsorkatalog | the international sponsor catalogue |
| Finnish (`fi`) | maailmanlaajuisen toimistohakemiston | kansainvälisen sponsorointihakemiston | the international sponsoring directory (hakemisto = directory) |
| Norwegian (`no`) | fra den globale kontoroversikten | fra den internasjonale sponsorkatalogen | the international sponsor catalogue |
| Serbian (`sr`) | iz globalnog imenika kancelarija | iz međunarodnog imenika sponzorstva | the international sponsorship directory (imenik = directory) |
| Swedish (`sv`) | från den globala kontorskatalogen | från den internationella sponsorkatalogen | the international sponsor catalogue |
| Russian (`ru`) | из глобального справочника офисов | из международного справочника спонсорства | the international sponsorship reference/directory (справочник = reference book) |

---

## Ask B - medical-claim wording (BLOCKED, needs Legal to supply text)

This has been open since before the September 5 review and is unchanged on
`main`. It is the last item blocking consistent medical-claim handling.

### Problem 1: two different answers for the same kind of request

A medical request gets one of two different replies depending on how it is
phrased:

- If it names **both** a product **and** a disease claim (e.g. "Does Aloe Vera
  Gel cure diabetes?"), the user gets the reviewed refusal in
  `config/claim_safety.json` shown in Ask A above.
- Any other medical request (e.g. "What helps a sunburn?") falls through to a
  different, shorter string in `config/conversation_routes.json`:

  > I'm not able to give medical advice or make claims about treating or curing anything. For anything health-related, a qualified healthcare professional is really the right person to ask.

Legal previously flagged this inconsistency. The fix is to remove the fork
(`services/claim_safety.py:56`) so every medical request gets one approved
answer. **Legal needs to say which wording is the approved one**, in English,
for translation into the other 11 locales.

### Problem 2: medical claims are logged but never blocked

`app/risk/policies/medical_claim_policy.py` is set to `PolicyAction.WARN`: it
records a medical-claim risk but does not stop the request. The equivalent
income policy is `REFUSE` and does block. The recommendation is to make the
medical policy `REFUSE` to match, and to extend the denied-phrase list, which
currently lacks common ailment terms (sunburn, headache, rash, acne, pain).

Note the trade-off, which is why this needs a decision rather than just a
code change: a broader denied list with a REFUSE action will also refuse more
**legitimate** questions. A related over-refusal was just fixed - "Does company
policy prohibit medical claims?" was being refused as if it were itself a
medical claim - and that protection currently covers only a narrow set of
exact English phrasings.

### What is needed from Legal

1. The exact approved English wording for a medical-claim refusal.
2. Confirmation that this single wording replaces both current variants.
3. A decision on blocking (`REFUSE`) versus logging (`WARN`).
4. If blocking: confirmation that refusing more borderline health questions is
   acceptable, accepting some legitimate questions will be refused too.

---

## Decision checklist

- [ ] Ask A: source-name correction approved for release
- [ ] Ask A: translations confirmed by a native speaker per market
- [ ] Ask B: approved English medical-claim wording supplied
- [ ] Ask B: single wording confirmed to replace both variants
- [ ] Ask B: REFUSE vs WARN decided

Until Ask A is confirmed it stays merged but undeployed, and Ask B stays
unimplemented. Neither is a code blocker; both are wording decisions.
