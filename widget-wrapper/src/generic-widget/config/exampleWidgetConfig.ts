import type { GenericWidgetConfig } from "../types";

export const exampleWidgetConfig: GenericWidgetConfig = {
  brandName: "Demo Assistant",
  assistantName: "Demo Assistant",
  assistantSubtitle: "Enterprise Knowledge Assistant",
  launcherTitle: "Open Demo Assistant",
  footerText: "Powered by approved company documentation.",
  welcomeText: "Get trusted answers from approved company documentation for your selected region and language.",
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
    { id: "company-policies", label: "Company Policies", prompt: "What is the travel expense policy?" },
    { id: "international-directory", label: "International Directory", prompt: "How do I contact the Germany office?" },
    { id: "country-documentation", label: "Country Documentation", prompt: "Show me the policies for Canada." }
  ],
  contextualTopics: []
};
