export type WidgetCopy = {
  greeting: string;
  assistantSubtitle: string;
  welcomeEyebrow: string;
  welcomeTitle: string;
  welcomeBody: string;
  welcomeNext: string;
  privacyTitle: string;
  privacyBody: string;
  privacyAcknowledgment: string;
  accept: string;
  decline: string;
  inputPlaceholder: string;
  send: string;
  newChat: string;
  endChat: string;
  confirmEndChat: string;
  cancelEndChat: string;
  support: string;
  supportQueued: string;
  supportFailed: string;
  supportCreating: string;
  supportRequested: string;
  conversationCleared: string;
  footer: string;
  online: string;
  offline: string;
  reconnecting: string;
  consentRequired: string;
  unavailable: string;
  waiting: string;
  copy: string;
  copied: string;
  helpful: string;
  notHelpful: string;
  privacyEyebrow: string;
  reviewDocuments: string;
  privacyLoading: string;
  privacySaving: string;
  privacySaved: string;
  declineTitle: string;
  declineBody: string;
  reviewPrivacy: string;
  market: string;
  language: string;
  selectMarket: string;
  selectLanguage: string;
  openAssistant: string;
  closeAssistant: string;
  openMenu: string;
  composerHint: string;
  thinking: string;
  searching: string;
  generating: string;
  retrying: string;
  slowResponse: string;
  you: string;
  system: string;
  sourcesUsed: string;
  references: string;
  primarySource: string;
  supportingSource: string;
  source: string;
  section: string;
  saveAsPdf: string;
  closeLegal: string;
  retry: string;
};

const copy: Record<string, Partial<WidgetCopy>> = {
  en: {
    greeting: "Hello, I'm AskVera. How can I help with Forever Living products, policies, or business support?",
    assistantSubtitle: "Enterprise Knowledge Assistant",
    welcomeEyebrow: "Welcome", welcomeTitle: "Hi, I'm AskVera.",
    welcomeBody: "I can help you find approved answers about Forever Living products, policies, and business support.",
    welcomeNext: "Choose your market and language to begin.", privacyTitle: "Privacy and Terms",
    privacyBody: "Review and accept the required legal documents to use AskVera.",
    privacyAcknowledgment: "I have read and agree to the required privacy and terms documents.",
    accept: "I agree", decline: "Not now", inputPlaceholder: "Ask a question", send: "Send message",
    newChat: "New chat", endChat: "End chat", confirmEndChat: "End this chat", cancelEndChat: "Cancel", support: "Request support", supportQueued: "Your support request has been created. Reference: {id}",
    supportFailed: "The support request could not be created. Please try again.", supportCreating: "Creating...", supportRequested: "Requested", conversationCleared: "A new chat is ready.",
    footer: "Answers are generated from approved company documentation.", online: "Online", offline: "Offline",
    reconnecting: "Reconnecting", consentRequired: "Accept the privacy agreement to begin.", unavailable: "AskVera is temporarily unavailable. Please try again in a moment.", waiting: "Waiting for the current response to finish.", copy: "Copy", copied: "Copied", helpful: "Helpful", notHelpful: "Not helpful",
    privacyEyebrow: "One quick privacy step", reviewDocuments: "Review required documents",
    privacyLoading: "Loading legal documents before consent can be recorded.", privacySaving: "Saving...",
    privacySaved: "Privacy saved. Chat is ready.", declineTitle: "No problem. AskVera will be here when you are ready.",
    declineBody: "To start chatting, return and accept the privacy and terms when you are ready.", reviewPrivacy: "Review privacy terms",
    market: "Market", language: "Language", selectMarket: "Select a market", selectLanguage: "Select a language",
    openAssistant: "Open AskVera", closeAssistant: "Close AskVera", openMenu: "Open AskVera menu", composerHint: "Enter to send. Shift + Enter for a new line.",
    thinking: "Thinking...", searching: "Searching approved documentation...", generating: "Preparing your answer...", retrying: "Connection interrupted. Retrying...", slowResponse: "Still working...",
    you: "You", system: "System", sourcesUsed: "Sources used for this answer", references: "References", primarySource: "Primary source", supportingSource: "Supporting source", source: "Source", section: "Section",
    saveAsPdf: "Save as PDF", closeLegal: "Close legal document", retry: "Retry"
  },
  fr: {
    greeting: "Bonjour, je suis AskVera. Comment puis-je vous aider avec les produits, les politiques ou le soutien commercial de Forever Living?",
    assistantSubtitle: "Assistant de connaissances d'entreprise",
    welcomeEyebrow: "Bienvenue", welcomeTitle: "Bonjour, je suis AskVera.",
    welcomeBody: "Je peux vous aider à trouver des réponses approuvées sur les produits, les politiques et le soutien commercial de Forever Living.",
    welcomeNext: "Choisissez votre marché et votre langue pour commencer.", privacyTitle: "Confidentialité et conditions",
    privacyBody: "Consultez et acceptez les documents juridiques requis pour utiliser AskVera.",
    privacyAcknowledgment: "J'ai lu et j'accepte les documents requis sur la confidentialité et les conditions.",
    accept: "J'accepte", decline: "Pas maintenant", inputPlaceholder: "Posez une question", send: "Envoyer",
    newChat: "Nouvelle conversation", endChat: "Terminer la conversation", confirmEndChat: "Terminer ce chat", cancelEndChat: "Annuler", support: "Demander de l'aide", supportQueued: "Votre demande d'aide a été créée. Référence : {id}",
    supportFailed: "La demande d'aide n'a pas pu être créée. Veuillez réessayer.", supportCreating: "Création...", supportRequested: "Demandé", conversationCleared: "Une nouvelle conversation est prête.",
    footer: "Les réponses sont générées à partir de documents approuvés.", online: "En ligne", offline: "Hors ligne",
    reconnecting: "Reconnexion", consentRequired: "Acceptez l'accord de confidentialité pour commencer.", unavailable: "AskVera est temporairement indisponible. Veuillez réessayer dans un instant.", waiting: "Attendez la fin de la réponse en cours.", copy: "Copier", copied: "Copié", helpful: "Utile", notHelpful: "Pas utile",
    privacyEyebrow: "Une étape rapide de confidentialité", reviewDocuments: "Consulter les documents requis", privacyLoading: "Chargement des documents juridiques...", privacySaving: "Enregistrement...", privacySaved: "Confidentialité enregistrée. Le chat est prêt.", declineTitle: "Aucun problème. AskVera sera là quand vous serez prêt.", declineBody: "Pour discuter, revenez accepter les conditions de confidentialité.", reviewPrivacy: "Consulter les conditions", market: "Marché", language: "Langue", selectMarket: "Sélectionnez un marché", selectLanguage: "Sélectionnez une langue", openAssistant: "Ouvrir AskVera", closeAssistant: "Fermer AskVera", openMenu: "Ouvrir le menu AskVera", composerHint: "Entrée pour envoyer. Maj + Entrée pour une nouvelle ligne.", thinking: "Réflexion...", searching: "Recherche dans les documents approuvés...", generating: "Préparation de votre réponse...", retrying: "Connexion interrompue. Nouvelle tentative...", slowResponse: "Toujours en cours...", you: "Vous", system: "Système", sourcesUsed: "Sources utilisées pour cette réponse", references: "Références", primarySource: "Source principale", supportingSource: "Source complémentaire", source: "Source", section: "Section", saveAsPdf: "Enregistrer en PDF", closeLegal: "Fermer le document juridique"
  },
  es: {
    greeting: "Hola, soy AskVera. ¿Cómo puedo ayudarte con productos, políticas o soporte comercial de Forever Living?",
    assistantSubtitle: "Asistente de conocimiento empresarial",
    welcomeEyebrow: "Bienvenido", welcomeTitle: "Hola, soy AskVera.",
    welcomeBody: "Puedo ayudarte a encontrar respuestas aprobadas sobre productos, políticas y soporte comercial de Forever Living.",
    welcomeNext: "Elige tu mercado e idioma para comenzar.", privacyTitle: "Privacidad y condiciones",
    privacyBody: "Revisa y acepta los documentos legales requeridos para usar AskVera.",
    privacyAcknowledgment: "He leído y acepto los documentos requeridos de privacidad y condiciones.",
    accept: "Acepto", decline: "Ahora no", inputPlaceholder: "Haz una pregunta", send: "Enviar",
    newChat: "Nuevo chat", endChat: "Finalizar chat", confirmEndChat: "Finalizar este chat", cancelEndChat: "Cancelar", support: "Solicitar ayuda", supportQueued: "Tu solicitud de ayuda fue creada. Referencia: {id}",
    supportFailed: "No se pudo crear la solicitud de ayuda. Inténtalo de nuevo.", supportCreating: "Creando...", supportRequested: "Solicitado", conversationCleared: "Hay un nuevo chat listo.",
    footer: "Las respuestas se generan a partir de documentos aprobados.", online: "En línea", offline: "Sin conexión",
    reconnecting: "Reconectando", consentRequired: "Acepta el acuerdo de privacidad para comenzar.", unavailable: "AskVera no está disponible temporalmente. Inténtalo de nuevo en un momento.", waiting: "Espera a que termine la respuesta actual.", copy: "Copiar", copied: "Copiado", helpful: "Útil", notHelpful: "No útil",
    privacyEyebrow: "Un paso rápido de privacidad", reviewDocuments: "Revisar los documentos requeridos", privacyLoading: "Cargando los documentos legales...", privacySaving: "Guardando...", privacySaved: "Privacidad guardada. El chat está listo.", declineTitle: "No hay problema. AskVera estará aquí cuando estés listo.", declineBody: "Para chatear, vuelve y acepta la privacidad y las condiciones.", reviewPrivacy: "Revisar privacidad y condiciones", market: "Mercado", language: "Idioma", selectMarket: "Selecciona un mercado", selectLanguage: "Selecciona un idioma", openAssistant: "Abrir AskVera", closeAssistant: "Cerrar AskVera", openMenu: "Abrir el menú de AskVera", composerHint: "Enter para enviar. Mayús + Enter para una nueva línea.", thinking: "Pensando...", searching: "Buscando en la documentación aprobada...", generating: "Preparando tu respuesta...", retrying: "Conexión interrumpida. Reintentando...", slowResponse: "Sigo trabajando...", you: "Tú", system: "Sistema", sourcesUsed: "Fuentes utilizadas para esta respuesta", references: "Referencias", primarySource: "Fuente principal", supportingSource: "Fuente complementaria", source: "Fuente", section: "Sección", saveAsPdf: "Guardar como PDF", closeLegal: "Cerrar documento legal"
  },
  de: {
    greeting: "Hallo, ich bin AskVera. Wie kann ich bei Produkten, Richtlinien oder geschäftlichen Fragen zu Forever Living helfen?",
    assistantSubtitle: "Unternehmens-Wissensassistent",
    welcomeEyebrow: "Willkommen", welcomeTitle: "Hallo, ich bin AskVera.",
    welcomeBody: "Ich helfe Ihnen, freigegebene Antworten zu Produkten, Richtlinien und geschäftlichen Themen von Forever Living zu finden.",
    welcomeNext: "Wählen Sie Ihren Markt und Ihre Sprache aus.", privacyTitle: "Datenschutz und Bedingungen",
    privacyBody: "Prüfen und akzeptieren Sie die erforderlichen rechtlichen Dokumente, um AskVera zu verwenden.",
    privacyAcknowledgment: "Ich habe die erforderlichen Datenschutz- und Bedingungsdokumente gelesen und stimme ihnen zu.",
    accept: "Ich stimme zu", decline: "Nicht jetzt", inputPlaceholder: "Frage stellen", send: "Senden",
    newChat: "Neuer Chat", endChat: "Chat beenden", confirmEndChat: "Diesen Chat beenden", cancelEndChat: "Abbrechen", support: "Support anfordern", supportQueued: "Ihre Supportanfrage wurde erstellt. Referenz: {id}",
    supportFailed: "Die Supportanfrage konnte nicht erstellt werden. Bitte versuchen Sie es erneut.", supportCreating: "Wird erstellt...", supportRequested: "Angefordert", conversationCleared: "Ein neuer Chat ist bereit.",
    footer: "Antworten werden aus freigegebenen Unternehmensdokumenten erstellt.", online: "Online", offline: "Offline",
    reconnecting: "Verbindung wird hergestellt", consentRequired: "Akzeptieren Sie die Datenschutzvereinbarung, um zu beginnen.", unavailable: "AskVera ist vorübergehend nicht verfügbar. Versuchen Sie es gleich noch einmal.", waiting: "Warten Sie, bis die aktuelle Antwort abgeschlossen ist.", copy: "Kopieren", copied: "Kopiert", helpful: "Hilfreich", notHelpful: "Nicht hilfreich",
    privacyEyebrow: "Ein kurzer Datenschutzschritt", reviewDocuments: "Erforderliche Dokumente prüfen", privacyLoading: "Rechtliche Dokumente werden geladen...", privacySaving: "Wird gespeichert...", privacySaved: "Datenschutz gespeichert. Der Chat ist bereit.", declineTitle: "Kein Problem. AskVera ist da, wenn Sie bereit sind.", declineBody: "Akzeptieren Sie die Datenschutzbestimmungen, um den Chat zu starten.", reviewPrivacy: "Datenschutz prüfen", market: "Markt", language: "Sprache", selectMarket: "Markt auswählen", selectLanguage: "Sprache auswählen", openAssistant: "AskVera öffnen", closeAssistant: "AskVera schließen", openMenu: "AskVera-Menü öffnen", composerHint: "Eingabetaste zum Senden. Umschalt + Eingabetaste für eine neue Zeile.", thinking: "Denke nach...", searching: "Freigegebene Dokumente werden durchsucht...", generating: "Antwort wird vorbereitet...", retrying: "Verbindung unterbrochen. Neuer Versuch...", slowResponse: "Noch in Bearbeitung...", you: "Sie", system: "System", sourcesUsed: "Quellen für diese Antwort", references: "Referenzen", primarySource: "Primärquelle", supportingSource: "Ergänzende Quelle", source: "Quelle", section: "Abschnitt", saveAsPdf: "Als PDF speichern", closeLegal: "Rechtsdokument schließen"
  },
  nl: {
    greeting: "Hallo, ik ben AskVera. Hoe kan ik helpen met producten, beleid of zakelijke ondersteuning van Forever Living?",
    assistantSubtitle: "Kennisassistent voor bedrijven",
    welcomeEyebrow: "Welkom", welcomeTitle: "Hallo, ik ben AskVera.",
    welcomeBody: "Ik help u goedgekeurde antwoorden te vinden over producten, beleid en zakelijke ondersteuning van Forever Living.",
    welcomeNext: "Kies uw markt en taal om te beginnen.", privacyTitle: "Privacy en voorwaarden",
    privacyBody: "Bekijk en accepteer de vereiste juridische documenten om AskVera te gebruiken.",
    privacyAcknowledgment: "Ik heb de vereiste privacy- en voorwaardendocumenten gelezen en ga ermee akkoord.",
    accept: "Ik ga akkoord", decline: "Niet nu", inputPlaceholder: "Stel een vraag", send: "Versturen",
    newChat: "Nieuwe chat", endChat: "Chat beëindigen", confirmEndChat: "Deze chat beëindigen", cancelEndChat: "Annuleren", support: "Hulp aanvragen", supportQueued: "Uw hulpverzoek is aangemaakt. Referentie: {id}",
    supportFailed: "Het hulpverzoek kon niet worden aangemaakt. Probeer het opnieuw.", supportCreating: "Aanmaken...", supportRequested: "Aangevraagd", conversationCleared: "Een nieuwe chat staat klaar.",
    footer: "Antwoorden worden gemaakt op basis van goedgekeurde bedrijfsdocumenten.", online: "Online", offline: "Offline",
    reconnecting: "Opnieuw verbinden", consentRequired: "Accepteer de privacyovereenkomst om te beginnen.", unavailable: "AskVera is tijdelijk niet beschikbaar. Probeer het zo opnieuw.", waiting: "Wacht tot het huidige antwoord klaar is.", copy: "Kopiëren", copied: "Gekopieerd", helpful: "Nuttig", notHelpful: "Niet nuttig",
    privacyEyebrow: "Een korte privacystap", reviewDocuments: "Vereiste documenten bekijken", privacyLoading: "Juridische documenten worden geladen...", privacySaving: "Opslaan...", privacySaved: "Privacy opgeslagen. De chat is klaar.", declineTitle: "Geen probleem. AskVera is er wanneer u klaar bent.", declineBody: "Accepteer de privacyvoorwaarden om te beginnen.", reviewPrivacy: "Privacyvoorwaarden bekijken", market: "Markt", language: "Taal", selectMarket: "Selecteer een markt", selectLanguage: "Selecteer een taal", openAssistant: "AskVera openen", closeAssistant: "AskVera sluiten", openMenu: "AskVera-menu openen", composerHint: "Enter om te verzenden. Shift + Enter voor een nieuwe regel.", thinking: "Even nadenken...", searching: "Goedgekeurde documentatie doorzoeken...", generating: "Uw antwoord voorbereiden...", retrying: "Verbinding verbroken. Opnieuw proberen...", slowResponse: "Nog bezig...", you: "U", system: "Systeem", sourcesUsed: "Bronnen voor dit antwoord", references: "Referenties", primarySource: "Primaire bron", supportingSource: "Aanvullende bron", source: "Bron", section: "Sectie", saveAsPdf: "Opslaan als PDF", closeLegal: "Juridisch document sluiten"
  },
  it: {
    greeting: "Ciao, sono AskVera. Come posso aiutarti con prodotti, politiche o supporto commerciale Forever Living?",
    assistantSubtitle: "Assistente alla conoscenza aziendale",
    welcomeEyebrow: "Benvenuto", welcomeTitle: "Ciao, sono AskVera.", welcomeBody: "Posso aiutarti a trovare risposte approvate su prodotti, politiche e supporto commerciale Forever Living.", welcomeNext: "Scegli il mercato e la lingua per iniziare.",
    privacyTitle: "Privacy e condizioni", privacyBody: "Consulta e accetta i documenti legali richiesti per usare AskVera.", privacyAcknowledgment: "Ho letto e accetto i documenti richiesti sulla privacy e le condizioni.", accept: "Accetto", decline: "Non ora", inputPlaceholder: "Fai una domanda", send: "Invia",
    newChat: "Nuova chat", endChat: "Termina chat", confirmEndChat: "Termina questa chat", cancelEndChat: "Annulla", support: "Richiedi assistenza", supportQueued: "La richiesta di assistenza è stata creata. Riferimento: {id}", supportFailed: "Impossibile creare la richiesta. Riprova.", supportCreating: "Creazione...", supportRequested: "Richiesta", conversationCleared: "Una nuova chat è pronta.",
    footer: "Le risposte sono generate da documentazione aziendale approvata.", online: "Online", offline: "Offline", reconnecting: "Riconnessione", consentRequired: "Accetta l'informativa sulla privacy per iniziare.", unavailable: "AskVera non è temporaneamente disponibile. Riprova tra poco.", waiting: "Attendi il completamento della risposta corrente.", copy: "Copia", copied: "Copiato", helpful: "Utile", notHelpful: "Non utile",
    privacyEyebrow: "Un rapido passaggio sulla privacy", reviewDocuments: "Consulta i documenti richiesti", privacyLoading: "Caricamento dei documenti legali...", privacySaving: "Salvataggio...", privacySaved: "Privacy salvata. La chat è pronta.", declineTitle: "Nessun problema. AskVera sarà qui quando sarai pronto.", declineBody: "Per iniziare, torna e accetta privacy e condizioni.", reviewPrivacy: "Consulta privacy e condizioni", market: "Mercato", language: "Lingua", selectMarket: "Seleziona un mercato", selectLanguage: "Seleziona una lingua", openAssistant: "Apri AskVera", closeAssistant: "Chiudi AskVera", openMenu: "Apri il menu AskVera", composerHint: "Invio per spedire. Maiusc + Invio per una nuova riga.", thinking: "Sto pensando...", searching: "Ricerca nella documentazione approvata...", generating: "Preparazione della risposta...", retrying: "Connessione interrotta. Nuovo tentativo...", slowResponse: "Sto ancora lavorando...", you: "Tu", system: "Sistema", sourcesUsed: "Fonti utilizzate per questa risposta", references: "Riferimenti", primarySource: "Fonte principale", supportingSource: "Fonte di supporto", source: "Fonte", section: "Sezione", saveAsPdf: "Salva come PDF", closeLegal: "Chiudi il documento legale"
  },
  da: {
    greeting: "Hej, jeg er AskVera. Hvordan kan jeg hjælpe med Forever Living-produkter, politikker eller forretningssupport?",
    assistantSubtitle: "Virksomhedens vidensassistent",
    welcomeEyebrow: "Velkommen", welcomeTitle: "Hej, jeg er AskVera.", welcomeBody: "Jeg kan hjælpe dig med at finde godkendte svar om Forever Living-produkter, politikker og forretningssupport.", welcomeNext: "Vælg marked og sprog for at begynde.",
    privacyTitle: "Privatliv og vilkår", privacyBody: "Gennemgå og accepter de nødvendige juridiske dokumenter for at bruge AskVera.", privacyAcknowledgment: "Jeg har læst og accepterer de nødvendige privatlivs- og vilkårsdokumenter.", accept: "Jeg accepterer", decline: "Ikke nu", inputPlaceholder: "Stil et spørgsmål", send: "Send",
    newChat: "Ny chat", endChat: "Afslut chat", confirmEndChat: "Afslut denne chat", cancelEndChat: "Annuller", support: "Anmod om hjælp", supportQueued: "Din supportanmodning er oprettet. Reference: {id}", supportFailed: "Supportanmodningen kunne ikke oprettes. Prøv igen.", supportCreating: "Opretter...", supportRequested: "Anmodet", conversationCleared: "En ny chat er klar.",
    footer: "Svar genereres fra godkendt virksomhedsdokumentation.", online: "Online", offline: "Offline", reconnecting: "Opretter forbindelse igen", consentRequired: "Accepter privatlivsaftalen for at begynde.", unavailable: "AskVera er midlertidigt utilgængelig. Prøv igen om lidt.", waiting: "Vent på, at det aktuelle svar bliver færdigt.", copy: "Kopiér", copied: "Kopieret", helpful: "Nyttigt", notHelpful: "Ikke nyttigt",
    privacyEyebrow: "Et hurtigt privatlivstrin", reviewDocuments: "Gennemgå nødvendige dokumenter", privacyLoading: "Indlæser juridiske dokumenter...", privacySaving: "Gemmer...", privacySaved: "Privatliv gemt. Chatten er klar.", declineTitle: "Intet problem. AskVera er her, når du er klar.", declineBody: "Vend tilbage og accepter privatliv og vilkår for at begynde.", reviewPrivacy: "Gennemgå privatlivsvilkår", market: "Marked", language: "Sprog", selectMarket: "Vælg et marked", selectLanguage: "Vælg et sprog", openAssistant: "Åbn AskVera", closeAssistant: "Luk AskVera", openMenu: "Åbn AskVera-menu", composerHint: "Enter for at sende. Shift + Enter for en ny linje.", thinking: "Tænker...", searching: "Søger i godkendt dokumentation...", generating: "Forbereder dit svar...", retrying: "Forbindelsen blev afbrudt. Prøver igen...", slowResponse: "Arbejder stadig...", you: "Du", system: "System", sourcesUsed: "Kilder brugt til dette svar", references: "Referencer", primarySource: "Primær kilde", supportingSource: "Supplerende kilde", source: "Kilde", section: "Afsnit", saveAsPdf: "Gem som PDF", closeLegal: "Luk juridisk dokument"
  },
  fi: {
    greeting: "Hei, olen AskVera. Miten voin auttaa Forever Livingin tuotteissa, käytännöissä tai liiketoimintatuessa?",
    assistantSubtitle: "Yrityksen tietoavustaja",
    welcomeEyebrow: "Tervetuloa", welcomeTitle: "Hei, olen AskVera.", welcomeBody: "Autan löytämään hyväksyttyjä vastauksia Forever Livingin tuotteista, käytännöistä ja liiketoimintatuesta.", welcomeNext: "Valitse markkina ja kieli aloittaaksesi.",
    privacyTitle: "Tietosuoja ja ehdot", privacyBody: "Tutustu vaadittuihin oikeudellisiin asiakirjoihin ja hyväksy ne käyttääksesi AskVeraa.", privacyAcknowledgment: "Olen lukenut ja hyväksyn vaaditut tietosuoja- ja ehtodokumentit.", accept: "Hyväksyn", decline: "Ei nyt", inputPlaceholder: "Kysy kysymys", send: "Lähetä",
    newChat: "Uusi keskustelu", endChat: "Lopeta keskustelu", confirmEndChat: "Lopeta tämä keskustelu", cancelEndChat: "Peruuta", support: "Pyydä tukea", supportQueued: "Tukipyyntösi on luotu. Viite: {id}", supportFailed: "Tukipyyntöä ei voitu luoda. Yritä uudelleen.", supportCreating: "Luodaan...", supportRequested: "Pyydetty", conversationCleared: "Uusi keskustelu on valmis.",
    footer: "Vastaukset luodaan hyväksytyistä yritysasiakirjoista.", online: "Online", offline: "Offline", reconnecting: "Yhdistetään uudelleen", consentRequired: "Hyväksy tietosuojasopimus aloittaaksesi.", unavailable: "AskVera ei ole tilapäisesti käytettävissä. Yritä pian uudelleen.", waiting: "Odota nykyisen vastauksen valmistumista.", copy: "Kopioi", copied: "Kopioitu", helpful: "Hyödyllinen", notHelpful: "Ei hyödyllinen",
    privacyEyebrow: "Nopea tietosuojavaihe", reviewDocuments: "Tarkista vaaditut asiakirjat", privacyLoading: "Ladataan oikeudellisia asiakirjoja...", privacySaving: "Tallennetaan...", privacySaved: "Tietosuoja tallennettu. Keskustelu on valmis.", declineTitle: "Ei hätää. AskVera on täällä, kun olet valmis.", declineBody: "Palaa hyväksymään tietosuoja ja ehdot aloittaaksesi.", reviewPrivacy: "Tarkista tietosuojaehdot", market: "Markkina", language: "Kieli", selectMarket: "Valitse markkina", selectLanguage: "Valitse kieli", openAssistant: "Avaa AskVera", closeAssistant: "Sulje AskVera", openMenu: "Avaa AskVera-valikko", composerHint: "Enter lähettää. Shift + Enter lisää uuden rivin.", thinking: "Ajattelen...", searching: "Haetaan hyväksytyistä asiakirjoista...", generating: "Valmistellaan vastausta...", retrying: "Yhteys katkesi. Yritetään uudelleen...", slowResponse: "Työskentelen edelleen...", you: "Sinä", system: "Järjestelmä", sourcesUsed: "Tässä vastauksessa käytetyt lähteet", references: "Viitteet", primarySource: "Ensisijainen lähde", supportingSource: "Tukeva lähde", source: "Lähde", section: "Kohta", saveAsPdf: "Tallenna PDF-muodossa", closeLegal: "Sulje oikeudellinen asiakirja"
  },
  no: {
    greeting: "Hei, jeg er AskVera. Hvordan kan jeg hjelpe med Forever Living-produkter, retningslinjer eller forretningsstøtte?",
    assistantSubtitle: "Kunnskapsassistent for bedriften",
    welcomeEyebrow: "Velkommen", welcomeTitle: "Hei, jeg er AskVera.", welcomeBody: "Jeg kan hjelpe deg med å finne godkjente svar om Forever Living-produkter, retningslinjer og forretningsstøtte.", welcomeNext: "Velg marked og språk for å begynne.",
    privacyTitle: "Personvern og vilkår", privacyBody: "Les og godta de nødvendige juridiske dokumentene for å bruke AskVera.", privacyAcknowledgment: "Jeg har lest og godtar de nødvendige personvern- og vilkårsdokumentene.", accept: "Jeg godtar", decline: "Ikke nå", inputPlaceholder: "Still et spørsmål", send: "Send",
    newChat: "Ny chat", endChat: "Avslutt chat", confirmEndChat: "Avslutt denne chatten", cancelEndChat: "Avbryt", support: "Be om hjelp", supportQueued: "Støtteforespørselen din er opprettet. Referanse: {id}", supportFailed: "Støtteforespørselen kunne ikke opprettes. Prøv igjen.", supportCreating: "Oppretter...", supportRequested: "Forespurt", conversationCleared: "En ny chat er klar.",
    footer: "Svar genereres fra godkjent firmadokumentasjon.", online: "Online", offline: "Offline", reconnecting: "Kobler til igjen", consentRequired: "Godta personvernavtalen for å begynne.", unavailable: "AskVera er midlertidig utilgjengelig. Prøv igjen om litt.", waiting: "Vent til det gjeldende svaret er ferdig.", copy: "Kopier", copied: "Kopiert", helpful: "Nyttig", notHelpful: "Ikke nyttig",
    privacyEyebrow: "Et raskt personvernsteg", reviewDocuments: "Se gjennom nødvendige dokumenter", privacyLoading: "Laster juridiske dokumenter...", privacySaving: "Lagrer...", privacySaved: "Personvern lagret. Chatten er klar.", declineTitle: "Ikke noe problem. AskVera er her når du er klar.", declineBody: "Kom tilbake og godta personvern og vilkår for å begynne.", reviewPrivacy: "Se gjennom personvernvilkår", market: "Marked", language: "Språk", selectMarket: "Velg et marked", selectLanguage: "Velg et språk", openAssistant: "Åpne AskVera", closeAssistant: "Lukk AskVera", openMenu: "Åpne AskVera-meny", composerHint: "Enter for å sende. Shift + Enter for en ny linje.", thinking: "Tenker...", searching: "Søker i godkjent dokumentasjon...", generating: "Forbereder svaret ditt...", retrying: "Forbindelsen ble brutt. Prøver igjen...", slowResponse: "Jobber fortsatt...", you: "Du", system: "System", sourcesUsed: "Kilder brukt til dette svaret", references: "Referanser", primarySource: "Primærkilde", supportingSource: "Støttekilde", source: "Kilde", section: "Avsnitt", saveAsPdf: "Lagre som PDF", closeLegal: "Lukk juridisk dokument"
  },
  sv: {
    greeting: "Hej, jag är AskVera. Hur kan jag hjälpa till med Forever Livings produkter, policyer eller affärssupport?",
    assistantSubtitle: "Företagets kunskapsassistent",
    welcomeEyebrow: "Välkommen", welcomeTitle: "Hej, jag är AskVera.", welcomeBody: "Jag kan hjälpa dig att hitta godkända svar om Forever Livings produkter, policyer och affärssupport.", welcomeNext: "Välj marknad och språk för att börja.",
    privacyTitle: "Integritet och villkor", privacyBody: "Granska och godkänn de juridiska dokument som krävs för att använda AskVera.", privacyAcknowledgment: "Jag har läst och godkänner de obligatoriska integritets- och villkorsdokumenten.", accept: "Jag godkänner", decline: "Inte nu", inputPlaceholder: "Ställ en fråga", send: "Skicka",
    newChat: "Ny chatt", endChat: "Avsluta chatt", confirmEndChat: "Avsluta den här chatten", cancelEndChat: "Avbryt", support: "Begär hjälp", supportQueued: "Din supportbegäran har skapats. Referens: {id}", supportFailed: "Supportbegäran kunde inte skapas. Försök igen.", supportCreating: "Skapar...", supportRequested: "Begärd", conversationCleared: "En ny chatt är klar.",
    footer: "Svaren genereras från godkänd företagsdokumentation.", online: "Online", offline: "Offline", reconnecting: "Ansluter igen", consentRequired: "Godkänn integritetsavtalet för att börja.", unavailable: "AskVera är tillfälligt otillgänglig. Försök igen om en stund.", waiting: "Vänta tills det aktuella svaret är klart.", copy: "Kopiera", copied: "Kopierat", helpful: "Hjälpsamt", notHelpful: "Inte hjälpsamt",
    privacyEyebrow: "Ett snabbt integritetssteg", reviewDocuments: "Granska obligatoriska dokument", privacyLoading: "Läser in juridiska dokument...", privacySaving: "Sparar...", privacySaved: "Integriteten har sparats. Chatten är klar.", declineTitle: "Inga problem. AskVera finns här när du är redo.", declineBody: "Kom tillbaka och godkänn integritet och villkor för att börja.", reviewPrivacy: "Granska integritetsvillkoren", market: "Marknad", language: "Språk", selectMarket: "Välj en marknad", selectLanguage: "Välj ett språk", openAssistant: "Öppna AskVera", closeAssistant: "Stäng AskVera", openMenu: "Öppna AskVera-menyn", composerHint: "Enter för att skicka. Shift + Enter för en ny rad.", thinking: "Tänker...", searching: "Söker i godkänd dokumentation...", generating: "Förbereder ditt svar...", retrying: "Anslutningen avbröts. Försöker igen...", slowResponse: "Arbetar fortfarande...", you: "Du", system: "System", sourcesUsed: "Källor som användes för detta svar", references: "Referenser", primarySource: "Primär källa", supportingSource: "Stödjande källa", source: "Källa", section: "Avsnitt", saveAsPdf: "Spara som PDF", closeLegal: "Stäng juridiskt dokument"
  }
};

export function getWidgetCopy(language?: string): WidgetCopy {
  const english = copy.en as WidgetCopy;
  const languageCode = (language || "en").split("-", 1)[0].toLowerCase();
  const retry = {
    da: "Prøv igen", de: "Erneut versuchen", es: "Reintentar", fi: "Yritä uudelleen",
    fr: "Réessayer", it: "Riprova", nl: "Opnieuw proberen", no: "Prøv igjen", sv: "Försök igen"
  }[languageCode];
  return { ...english, ...(copy[languageCode] || {}), ...(retry ? { retry } : {}) };
}
