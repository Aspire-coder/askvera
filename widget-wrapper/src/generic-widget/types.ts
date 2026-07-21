import type { CSSProperties, ReactNode } from "react";
import type { WidgetEventBus } from "../events";

export type WidgetProviderType = "custom-react" | "script" | "iframe" | "message-feed" | string;

export type WidgetCountryOption = {
  code: string;
  label: string;
  languageCodes?: string[];
  metadata?: Record<string, unknown>;
};

export type WidgetLanguageOption = {
  code: string;
  label: string;
  countryCodes?: string[];
  metadata?: Record<string, unknown>;
};

export type WidgetPolicyLink = {
  id: string;
  label: string;
  href: string;
  target?: "_blank" | "_self" | "_parent" | "_top";
  required?: boolean;
  html?: string;
};

export type WidgetTopic = {
  id: string;
  label: string;
  prompt?: string;
  metadata?: Record<string, unknown>;
};

export type WidgetMessage = {
  id: string;
  role: "assistant" | "user" | "system";
  content: ReactNode;
  timestamp?: string;
  metadata?: Record<string, unknown>;
};

export type WidgetTheme = {
  accentColor?: string;
  accentTextColor?: string;
  secondaryColor?: string;
  surfaceColor?: string;
  panelColor?: string;
  backgroundColor?: string;
  textColor?: string;
  mutedTextColor?: string;
  borderColor?: string;
  launcherColor?: string;
  launcherTextColor?: string;
  successColor?: string;
  warningColor?: string;
  errorColor?: string;
  dangerColor?: string;
  headerBackgroundColor?: string;
  headerTextColor?: string;
  fieldBackgroundColor?: string;
  fieldTextColor?: string;
  focusRingColor?: string;
  shadow?: string;
  radius?: string;
  fontFamily?: string;
  headingWeight?: string;
  bodyWeight?: string;
  fontScale?: string;
  panelWidth?: string;
  panelHeight?: string;
  launcherSize?: string;
  animationDuration?: string;
  animationEasing?: string;
  spacingUnit?: string;
  zIndex?: number;
};

export type WidgetLabels = {
  launcherAriaLabel: string;
  closeAriaLabel: string;
  menuAriaLabel: string;
  countryLabel: string;
  languageLabel: string;
  countryPlaceholder?: string;
  languagePlaceholder?: string;
  continueLabel: string;
  acceptConsentLabel: string;
  rejectConsentLabel: string;
  messageInputLabel: string;
  messageInputPlaceholder: string;
  sendMessageLabel: string;
  suggestedTopicsLabel: string;
  legalLinksLabel: string;
  childrenRegionLabel: string;
  successDismissLabel: string;
  panelAriaLabel?: string;
  onboardingAriaLabel?: string;
  attachFileLabel?: string;
  composerHint?: string;
  userRoleLabel?: string;
  systemRoleLabel?: string;
  messageActionsLabel?: string;
  copyResponseLabel?: string;
  markHelpfulLabel?: string;
  markNotHelpfulLabel?: string;
  responseCopiedLabel?: string;
  legalReviewTitle?: string;
  saveDocumentLabel?: string;
  closeLegalDocumentLabel?: string;
  savingConsentLabel?: string;
};

export type WidgetMenuLabels = {
  settings: string;
  history: string;
  newChat: string;
  newChatConfirmation: string;
  confirmNewChat: string;
  cancelNewChat: string;
  escalate: string;
};

export type SessionResetReason = "new_chat" | "user_ended" | "idle_timeout";
export type SessionResetResult = { sessionId?: string } | void;

export type WidgetConsentConfig = {
  title: string;
  body: ReactNode;
  eyebrow?: ReactNode;
  acknowledgmentLabel?: ReactNode;
  loadingText?: ReactNode;
  declineTitle?: ReactNode;
  declineBody?: ReactNode;
  declineActionLabel?: ReactNode;
  policyVersion: string;
  categories: string[];
  storageKey?: string;
  requireConsentBeforeMessaging?: boolean;
};

export type WidgetLoadingMessages = {
  thinking?: ReactNode;
  searching?: ReactNode;
  generating?: ReactNode;
  reconnecting?: ReactNode;
  slowResponse?: ReactNode;
};

export type WidgetCitationLabels = {
  references: string;
  sourcesUsed: string;
  primarySource: string;
  supportingSource: string;
  source: string;
  section: string;
};

export type GenericWidgetConfig = {
  brandName: string;
  assistantName?: string;
  assistantSubtitle?: string;
  logoUrl?: string;
  launcherIconUrl?: string;
  launcherTitle?: string;
  footerText?: ReactNode;
  emptyStateImageUrl?: string;
  statusLabels?: {
    online?: string;
    reconnecting?: string;
    offline?: string;
  };
  onboarding?: {
    eyebrow: string;
    title: string;
    body: string;
    next: string;
  };
  messageActions?: {
    copy: string;
    copied: string;
    helpful: string;
    notHelpful: string;
  };
  citationLabels?: WidgetCitationLabels;
  composerStatus?: {
    consentRequired: string;
    unavailable: string;
    waiting: string;
  };
  welcomeText?: ReactNode;
  loadingText: ReactNode;
  loadingMessages?: WidgetLoadingMessages;
  successText: ReactNode;
  labels: WidgetLabels;
  menu: WidgetMenuLabels;
  provider: { name: string; type: WidgetProviderType };
  consent: WidgetConsentConfig;
  policyLinks: WidgetPolicyLink[];
  countries: WidgetCountryOption[];
  languages: WidgetLanguageOption[];
  starterTopics?: WidgetTopic[];
  contextualTopics?: WidgetTopic[];
  theme?: WidgetTheme;
  defaultCountryCode?: string;
  defaultLanguageCode?: string;
  persistConsent?: boolean;
  sessionIdleTimeoutMinutes?: number;
  sessionStorageKey?: string;
  sessionMetadataStorageKey?: string;
  visitorStorageKey?: string;
};

export type ConsentActionType = "accepted" | "rejected";

export type ConsentEventPayload = {
  visitorId: string;
  sessionId: string;
  timestamp: string;
  selectedCountry: string;
  selectedLanguage: string;
  policyVersion: string;
  acceptedCategories: string[];
  widgetProviderName: string;
  widgetProviderType: WidgetProviderType;
  actionType: ConsentActionType;
  metadata?: Record<string, unknown>;
};

export type MessageEventPayload = {
  visitorId: string;
  sessionId: string;
  message: string;
  selectedCountry: string;
  selectedLanguage: string;
  widgetProviderName: string;
  widgetProviderType: WidgetProviderType;
  metadata?: Record<string, unknown>;
};

export type LocaleChangePayload = {
  visitorId: string;
  sessionId: string;
  selectedCountry: string;
  selectedLanguage: string;
  metadata?: Record<string, unknown>;
};

export type GenericWidgetRenderState = {
  isOpen: boolean;
  selectedCountry: WidgetCountryOption | undefined;
  selectedLanguage: WidgetLanguageOption | undefined;
  consentAccepted: boolean;
  visitorId: string;
  sessionId: string;
};

export type GenericWidgetWrapperProps = {
  config: GenericWidgetConfig;
  children?: ReactNode | ((state: GenericWidgetRenderState) => ReactNode);
  messages?: WidgetMessage[];
  loading?: boolean;
  openByDefault?: boolean;
  initialConsentAccepted?: boolean;
  initialShowSuccess?: boolean;
  consentRequiredSignal?: number;
  openSignal?: number;
  closeSignal?: number;
  resetSignal?: number;
  outboundMessage?: { id: string; text: string };
  showLocaleSelector?: boolean;
  visitorId?: string;
  sessionId?: string;
  className?: string;
  style?: CSSProperties;
  eventBus?: WidgetEventBus;
  debugEvents?: boolean;
  renderMessages?: (messages: WidgetMessage[], state: GenericWidgetRenderState) => ReactNode;
  onHealthCheck?: () => Promise<boolean>;
  onOpen?: () => void;
  onClose?: () => void;
  onAcceptConsent?: (payload: ConsentEventPayload) => void | Promise<void>;
  onRejectConsent?: (payload: ConsentEventPayload) => void;
  onCountryChange?: (payload: LocaleChangePayload) => void;
  onLanguageChange?: (payload: LocaleChangePayload) => void;
  onSendMessage?: (payload: MessageEventPayload) => void;
  onMessageCopied?: (message: WidgetMessage, state: GenericWidgetRenderState) => void | Promise<void>;
  onMessageFeedback?: (message: WidgetMessage, rating: number, state: GenericWidgetRenderState) => void | Promise<void>;
  onRequestSupport?: (message: WidgetMessage, state: GenericWidgetRenderState) => void | Promise<void>;
  onEscalate?: (payload: LocaleChangePayload) => void;
  onNewChat?: (payload: LocaleChangePayload, reason?: SessionResetReason) => SessionResetResult | Promise<SessionResetResult>;
};
