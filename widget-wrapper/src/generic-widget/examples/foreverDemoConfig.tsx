import type { GenericWidgetConfig } from "../types";
import { exampleWidgetConfig } from "../config/exampleWidgetConfig";

export const foreverDemoConfig: GenericWidgetConfig = {
  ...exampleWidgetConfig,
  brandName: "FOREVER",
  welcomeText: (
    <>
      <p>I'm here to help you find clear, useful support for your selected market and language.</p>
      <p>Choose a topic below or ask a question to start a conversation.</p>
    </>
  ),
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
  policyLinks: [
    { id: "privacy", label: "Privacy Notice", href: "/api/privacy?country=US&lang=en" },
    { id: "terms", label: "Terms of Use", href: "/terms" }
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
    { id: "products", label: "What products are right for me?", prompt: "What products are right for me?" },
    { id: "orders", label: "I need help with an order", prompt: "I need help with an order." },
    { id: "account", label: "Help me with my account", prompt: "Help me with my account." },
    { id: "policies", label: "Where can I find policy information?", prompt: "Where can I find policy information?" }
  ],
  contextualTopics: []
};
