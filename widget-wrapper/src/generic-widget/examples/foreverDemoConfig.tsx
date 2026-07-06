import type { GenericWidgetConfig } from "../types";
import { exampleWidgetConfig } from "../config/exampleWidgetConfig";

export const foreverDemoConfig: GenericWidgetConfig = {
  ...exampleWidgetConfig,
  brandName: "FOREVER",
  assistantName: "ASK Vera",
  assistantSubtitle: "Enterprise Knowledge Assistant",
  statusLabels: {
    online: "Online",
    reconnecting: "Reconnecting",
    offline: "Offline"
  },
  welcomeText: (
    <>
      <p><strong>Welcome to ASK Vera.</strong></p>
      <p>Get trusted answers from approved company documentation for your selected country and language.</p>
      <p>I can help with company policies, international directory information, country-specific documentation, corporate procedures, and compliance information.</p>
    </>
  ),
  loadingText: "Thinking...",
  loadingMessages: {
    thinking: "Thinking...",
    searching: "Searching approved documentation...",
    generating: "Preparing your answer...",
    reconnecting: "Connection interrupted. Retrying...",
    slowResponse: "Still working..."
  },
  successText: "Thank you. Your privacy choices have been saved and chat is ready.",
  labels: {
    ...exampleWidgetConfig.labels,
    countryLabel: "Market",
    languageLabel: "Language",
    acceptConsentLabel: "Accept and continue",
    rejectConsentLabel: "Not now",
    messageInputPlaceholder: "Ask a question"
  },
  consent: {
    ...exampleWidgetConfig.consent,
    title: "Privacy and Terms",
    body: (
      <>
        <p><strong>To use ASK Vera, you must review and accept the legal documents below.</strong></p>
        <p>Your consent will be recorded for this session before you can start chatting.</p>
        <p>Please review the following legal documents before continuing.</p>
      </>
    ),
    categories: ["chat-processing", "market-language-preferences"],
    storageKey: "forever-style-widget-demo-consent"
  },
  persistConsent: false,
  sessionStorageKey: "askvera_session_id",
  sessionMetadataStorageKey: "askvera_session_metadata",
  visitorStorageKey: "askvera_visitor_id",
  policyLinks: [
    { id: "privacy", label: "Privacy Notice", href: "/api/privacy?country=US&lang=en", required: true },
    { id: "privacy-addendum", label: "Privacy Addendum", href: "/api/privacy?country=US&lang=en", required: true },
    {
      id: "arbitration",
      label: "FLP Individual Arbitration and Class Action Waiver Agreement",
      href: "/api/privacy?country=US&lang=en",
      required: true
    }
  ],
  theme: {
    accentColor: "#ffc400",
    accentTextColor: "#000000",
    launcherColor: "#000000",
    launcherTextColor: "#ffc400",
    successColor: "#2f6f4e",
    textColor: "#111111",
    mutedTextColor: "#5f5f5f",
    borderColor: "#dedede",
    surfaceColor: "#ffffff",
    panelColor: "#ffffff",
    shadow: "0 22px 60px rgba(0, 0, 0, 0.18)",
    radius: "8px"
  },
  provider: { name: "ASK Vera API", type: "custom-react" },
  starterTopics: [
    { id: "company-policies", label: "Company Policies", prompt: "What is the travel expense policy?" },
    { id: "international-directory", label: "International Directory", prompt: "How do I contact the Germany office?" },
    { id: "country-documentation", label: "Country Documentation", prompt: "Show me the policies for Canada." }
  ],
  contextualTopics: []
};
