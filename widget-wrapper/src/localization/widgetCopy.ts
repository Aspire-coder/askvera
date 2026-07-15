export type WidgetCopy = {
  greeting: string;
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
};

const copy: Record<string, WidgetCopy> = {
  en: {
    greeting: "Hello, I'm AskVera. How can I help with Forever Living products, policies, or business support?",
    welcomeEyebrow: "Welcome", welcomeTitle: "Hi, I'm AskVera.",
    welcomeBody: "I can help you find approved answers about Forever Living products, policies, and business support.",
    welcomeNext: "Choose your market and language to begin.", privacyTitle: "Privacy and Terms",
    privacyBody: "Review and accept the required legal documents to use AskVera.",
    privacyAcknowledgment: "I have read and agree to the required privacy and terms documents.",
    accept: "I agree", decline: "Not now", inputPlaceholder: "Ask a question", send: "Send message",
    newChat: "New chat", support: "Request support", supportQueued: "Your support request has been created. Reference: {id}",
    supportFailed: "The support request could not be created. Please try again.", supportCreating: "Creating...", supportRequested: "Requested", conversationCleared: "A new chat is ready.",
    footer: "Answers are generated from approved company documentation.", online: "Online", offline: "Offline",
    reconnecting: "Reconnecting", consentRequired: "Accept the privacy agreement to begin.", unavailable: "AskVera is temporarily unavailable. Please try again in a moment.", waiting: "Waiting for the current response to finish.", copy: "Copy", copied: "Copied", helpful: "Helpful", notHelpful: "Not helpful"
  },
  fr: {
    greeting: "Bonjour, je suis AskVera. Comment puis-je vous aider avec les produits, les politiques ou le soutien commercial de Forever Living?",
    welcomeEyebrow: "Bienvenue", welcomeTitle: "Bonjour, je suis AskVera.",
    welcomeBody: "Je peux vous aider a trouver des reponses approuvees sur les produits, les politiques et le soutien commercial de Forever Living.",
    welcomeNext: "Choisissez votre marche et votre langue pour commencer.", privacyTitle: "Confidentialite et conditions",
    privacyBody: "Consultez et acceptez les documents juridiques requis pour utiliser AskVera.",
    privacyAcknowledgment: "J'ai lu et j'accepte les documents requis sur la confidentialite et les conditions.",
    accept: "J'accepte", decline: "Pas maintenant", inputPlaceholder: "Posez une question", send: "Envoyer",
    newChat: "Nouvelle conversation", support: "Demander de l'aide", supportQueued: "Votre demande d'aide a ete creee. Reference : {id}",
    supportFailed: "La demande d'aide n'a pas pu etre creee. Veuillez reessayer.", supportCreating: "Création...", supportRequested: "Demandé", conversationCleared: "Une nouvelle conversation est prete.",
    footer: "Les reponses sont generees a partir de documents approuves.", online: "En ligne", offline: "Hors ligne",
    reconnecting: "Reconnexion", consentRequired: "Acceptez l'accord de confidentialité pour commencer.", unavailable: "AskVera est temporairement indisponible. Veuillez réessayer dans un instant.", waiting: "Attendez la fin de la réponse en cours.", copy: "Copier", copied: "Copie", helpful: "Utile", notHelpful: "Pas utile"
  },
  es: {
    greeting: "Hola, soy AskVera. ¿Como puedo ayudarte con productos, politicas o soporte comercial de Forever Living?",
    welcomeEyebrow: "Bienvenido", welcomeTitle: "Hola, soy AskVera.",
    welcomeBody: "Puedo ayudarte a encontrar respuestas aprobadas sobre productos, politicas y soporte comercial de Forever Living.",
    welcomeNext: "Elige tu mercado e idioma para comenzar.", privacyTitle: "Privacidad y condiciones",
    privacyBody: "Revisa y acepta los documentos legales requeridos para usar AskVera.",
    privacyAcknowledgment: "He leido y acepto los documentos requeridos de privacidad y condiciones.",
    accept: "Acepto", decline: "Ahora no", inputPlaceholder: "Haz una pregunta", send: "Enviar",
    newChat: "Nuevo chat", support: "Solicitar ayuda", supportQueued: "Tu solicitud de ayuda fue creada. Referencia: {id}",
    supportFailed: "No se pudo crear la solicitud de ayuda. Intentalo de nuevo.", supportCreating: "Creando...", supportRequested: "Solicitado", conversationCleared: "Hay un nuevo chat listo.",
    footer: "Las respuestas se generan a partir de documentos aprobados.", online: "En linea", offline: "Sin conexion",
    reconnecting: "Reconectando", consentRequired: "Acepta el acuerdo de privacidad para comenzar.", unavailable: "AskVera no está disponible temporalmente. Inténtalo de nuevo en un momento.", waiting: "Espera a que termine la respuesta actual.", copy: "Copiar", copied: "Copiado", helpful: "Util", notHelpful: "No util"
  },
  de: {
    greeting: "Hallo, ich bin AskVera. Wie kann ich bei Produkten, Richtlinien oder geschaftlichen Fragen zu Forever Living helfen?",
    welcomeEyebrow: "Willkommen", welcomeTitle: "Hallo, ich bin AskVera.",
    welcomeBody: "Ich helfe Ihnen, freigegebene Antworten zu Produkten, Richtlinien und geschaftlichen Themen von Forever Living zu finden.",
    welcomeNext: "Wahlen Sie Ihren Markt und Ihre Sprache aus.", privacyTitle: "Datenschutz und Bedingungen",
    privacyBody: "Prufen und akzeptieren Sie die erforderlichen rechtlichen Dokumente, um AskVera zu verwenden.",
    privacyAcknowledgment: "Ich habe die erforderlichen Datenschutz- und Bedingungsdokumente gelesen und stimme ihnen zu.",
    accept: "Ich stimme zu", decline: "Nicht jetzt", inputPlaceholder: "Frage stellen", send: "Senden",
    newChat: "Neuer Chat", support: "Support anfordern", supportQueued: "Ihre Supportanfrage wurde erstellt. Referenz: {id}",
    supportFailed: "Die Supportanfrage konnte nicht erstellt werden. Bitte versuchen Sie es erneut.", supportCreating: "Wird erstellt...", supportRequested: "Angefordert", conversationCleared: "Ein neuer Chat ist bereit.",
    footer: "Antworten werden aus freigegebenen Unternehmensdokumenten erstellt.", online: "Online", offline: "Offline",
    reconnecting: "Verbindung wird hergestellt", consentRequired: "Akzeptieren Sie die Datenschutzvereinbarung, um zu beginnen.", unavailable: "AskVera ist vorübergehend nicht verfügbar. Versuchen Sie es gleich noch einmal.", waiting: "Warten Sie, bis die aktuelle Antwort abgeschlossen ist.", copy: "Kopieren", copied: "Kopiert", helpful: "Hilfreich", notHelpful: "Nicht hilfreich"
  },
  nl: {
    greeting: "Hallo, ik ben AskVera. Hoe kan ik helpen met producten, beleid of zakelijke ondersteuning van Forever Living?",
    welcomeEyebrow: "Welkom", welcomeTitle: "Hallo, ik ben AskVera.",
    welcomeBody: "Ik help u goedgekeurde antwoorden te vinden over producten, beleid en zakelijke ondersteuning van Forever Living.",
    welcomeNext: "Kies uw markt en taal om te beginnen.", privacyTitle: "Privacy en voorwaarden",
    privacyBody: "Bekijk en accepteer de vereiste juridische documenten om AskVera te gebruiken.",
    privacyAcknowledgment: "Ik heb de vereiste privacy- en voorwaardendocumenten gelezen en ga ermee akkoord.",
    accept: "Ik ga akkoord", decline: "Niet nu", inputPlaceholder: "Stel een vraag", send: "Versturen",
    newChat: "Nieuwe chat", support: "Hulp aanvragen", supportQueued: "Uw hulpverzoek is aangemaakt. Referentie: {id}",
    supportFailed: "Het hulpverzoek kon niet worden aangemaakt. Probeer het opnieuw.", supportCreating: "Aanmaken...", supportRequested: "Aangevraagd", conversationCleared: "Een nieuwe chat staat klaar.",
    footer: "Antwoorden worden gemaakt op basis van goedgekeurde bedrijfsdocumenten.", online: "Online", offline: "Offline",
    reconnecting: "Opnieuw verbinden", consentRequired: "Accepteer de privacyovereenkomst om te beginnen.", unavailable: "AskVera is tijdelijk niet beschikbaar. Probeer het zo opnieuw.", waiting: "Wacht tot het huidige antwoord klaar is.", copy: "Kopieren", copied: "Gekopieerd", helpful: "Nuttig", notHelpful: "Niet nuttig"
  }
};

export function getWidgetCopy(language?: string): WidgetCopy {
  return copy[(language || "en").split("-", 1)[0].toLowerCase()] || copy.en;
}
