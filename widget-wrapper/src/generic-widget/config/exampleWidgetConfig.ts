import type { GenericWidgetConfig } from "../types";

export const exampleWidgetConfig: GenericWidgetConfig = {
  brandName: "Demo Assistant",
  welcomeText: "Choose your region and review the consent notice to begin.",
  loadingText: "Loading response...",
  loadingMessages: {
    thinking: "Thinking...",
    searching: "Searching documentation...",
    generating: "Preparing your answer...",
    reconnecting: "Connection interrupted. Retrying...",
    slowResponse: "Still working..."
  },
  successText: "Consent saved. You can now continue.",
  provider: { name: "Demo provider", type: "custom-react" },
  labels: {
    launcherAriaLabel: "Open assistant",
    closeAriaLabel: "Close assistant",
    menuAriaLabel: "Open assistant menu",
    countryLabel: "Region",
    languageLabel: "Language",
    countryPlaceholder: "Select a region",
    languagePlaceholder: "Select a language",
    continueLabel: "Continue",
    acceptConsentLabel: "Accept",
    rejectConsentLabel: "Decline",
    messageInputLabel: "Message",
    messageInputPlaceholder: "Type a message",
    sendMessageLabel: "Send message",
    suggestedTopicsLabel: "Suggested topics",
    legalLinksLabel: "Legal links",
    childrenRegionLabel: "Embedded assistant",
    successDismissLabel: "Dismiss confirmation"
  },
  menu: {
    settings: "Settings",
    history: "History",
    newChat: "New chat",
    escalate: "Contact support"
  },
  consent: {
    title: "Consent",
    body: "This assistant may process your messages according to the linked policies. Accept to continue.",
    policyVersion: "2026-01",
    categories: ["chat-processing", "support"],
    storageKey: "generic-widget-consent-demo",
    requireConsentBeforeMessaging: true
  },
  policyLinks: [
    { id: "privacy", label: "Privacy policy", href: "/privacy" },
    { id: "terms", label: "Terms of use", href: "/terms" }
  ],
  countries: [
    { code: "US", label: "United States", languageCodes: ["en", "es"] },
    { code: "CA", label: "Canada", languageCodes: ["en", "fr"] },
    { code: "GB", label: "United Kingdom", languageCodes: ["en"] }
  ],
  languages: [
    { code: "en", label: "English", countryCodes: ["US", "CA", "GB"] },
    { code: "es", label: "Spanish", countryCodes: ["US"] },
    { code: "fr", label: "French", countryCodes: ["CA"] }
  ],
  starterTopics: [
    { id: "orders", label: "Orders", prompt: "I need help with an order." },
    { id: "account", label: "Account", prompt: "I need help with my account." }
  ],
  contextualTopics: [{ id: "support", label: "Support", prompt: "Connect me with support." }]
};
