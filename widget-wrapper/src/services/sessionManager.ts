import { createLocalStorageAdapter, type StorageAdapter } from "../storage";

const SESSION_SCHEMA_VERSION = 1;

const createId = (prefix: string) =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? `${prefix}_${crypto.randomUUID()}`
    : `${prefix}_${Math.random().toString(36).slice(2)}_${Date.now().toString(36)}`;

export type WidgetSessionMetadata = {
  schemaVersion: number;
  visitorId: string;
  sessionId: string;
  legalVersion: string;
  country?: string;
  language?: string;
  createdAt: string;
  expiresAt?: string;
  consentAccepted?: boolean;
};

export type SessionStorageKeys = {
  visitorStorageKey?: string;
  sessionStorageKey?: string;
  sessionMetadataStorageKey?: string;
  consentStorageKey?: string;
};

export type SessionManagerOptions = {
  storage?: StorageAdapter;
  keys?: SessionStorageKeys;
  now?: () => Date;
};

export type RestoreSessionOptions = {
  providedVisitorId?: string;
  providedSessionId?: string;
  legalVersion: string;
  country?: string;
  language?: string;
  consentAccepted?: boolean;
};

export type PersistSessionOptions = {
  legalVersion: string;
  country?: string;
  language?: string;
  consentAccepted?: boolean;
  expiresAt?: string;
};

export class SessionManager {
  private storage: StorageAdapter;
  private keys: SessionStorageKeys;
  private now: () => Date;

  constructor(options: SessionManagerOptions = {}) {
    this.storage = options.storage || createLocalStorageAdapter();
    this.keys = options.keys || {};
    this.now = options.now || (() => new Date());
  }

  createVisitorId() {
    return createId("visitor");
  }

  createSessionId() {
    return createId("session");
  }

  restore(options: RestoreSessionOptions): WidgetSessionMetadata {
    const visitorId = options.providedVisitorId || this.readStoredId(this.keys.visitorStorageKey) || this.createVisitorId();
    const sessionId = options.providedSessionId || this.readStoredId(this.keys.sessionStorageKey) || this.createSessionId();
    const stored = this.readMetadata();
    const storedSessionMatches = Boolean(stored && stored.sessionId === sessionId);
    const restored = Boolean(storedSessionMatches && stored && !this.isExpired(stored));
    const createdAt = restored ? stored!.createdAt : this.now().toISOString();

    return {
      schemaVersion: SESSION_SCHEMA_VERSION,
      visitorId,
      sessionId,
      legalVersion: options.legalVersion,
      country: restored ? stored!.country : options.country,
      language: restored ? stored!.language : options.language,
      createdAt,
      expiresAt: restored ? stored!.expiresAt : undefined,
      consentAccepted: restored && stored ? stored.consentAccepted : storedSessionMatches ? options.consentAccepted : false
    };
  }

  save(session: WidgetSessionMetadata) {
    this.writeStoredId(this.keys.visitorStorageKey, session.visitorId);
    this.writeStoredId(this.keys.sessionStorageKey, session.sessionId);
    this.writeMetadata(session);
    if (this.keys.consentStorageKey && session.consentAccepted !== undefined) {
      this.storage.setItem(this.keys.consentStorageKey, session.consentAccepted ? "true" : "false");
    }
  }

  reset(options: RestoreSessionOptions): WidgetSessionMetadata {
    const session = {
      schemaVersion: SESSION_SCHEMA_VERSION,
      visitorId: options.providedVisitorId || this.createVisitorId(),
      sessionId: options.providedSessionId || this.createSessionId(),
      legalVersion: options.legalVersion,
      country: options.country,
      language: options.language,
      createdAt: this.now().toISOString(),
      consentAccepted: false
    };
    this.save(session);
    return session;
  }

  destroy() {
    for (const key of Object.values(this.keys)) {
      if (key) this.storage.removeItem(key);
    }
  }

  reconnect(options: RestoreSessionOptions) {
    return this.restore(options);
  }

  refresh(session: WidgetSessionMetadata) {
    const nextSession = { ...session, createdAt: session.createdAt || this.now().toISOString() };
    this.save(nextSession);
    return nextSession;
  }

  expire(session: WidgetSessionMetadata) {
    const expired = { ...session, expiresAt: this.now().toISOString(), consentAccepted: false };
    this.save(expired);
    return expired;
  }

  validate(session: WidgetSessionMetadata, legalVersion: string) {
    return {
      valid: !this.isExpired(session) && session.legalVersion === legalVersion,
      legalVersionMatches: session.legalVersion === legalVersion,
      expired: this.isExpired(session)
    };
  }

  isExpired(session: WidgetSessionMetadata) {
    return Boolean(session.expiresAt && new Date(session.expiresAt).getTime() <= this.now().getTime());
  }

  updateConsent(session: WidgetSessionMetadata, accepted: boolean, legalVersion = session.legalVersion) {
    const nextSession = { ...session, consentAccepted: accepted, legalVersion };
    this.save(nextSession);
    return nextSession;
  }

  updateLocale(session: WidgetSessionMetadata, country?: string, language?: string) {
    const nextSession = { ...session, country, language };
    this.save(nextSession);
    return nextSession;
  }

  persist(session: WidgetSessionMetadata, options: PersistSessionOptions) {
    const nextSession = {
      ...session,
      legalVersion: options.legalVersion,
      country: options.country,
      language: options.language,
      consentAccepted: options.consentAccepted,
      expiresAt: options.expiresAt
    };
    this.save(nextSession);
    return nextSession;
  }

  readConsentFlag() {
    return Boolean(this.keys.consentStorageKey && this.storage.getItem(this.keys.consentStorageKey) === "true");
  }

  private readStoredId(storageKey?: string) {
    return storageKey ? this.storage.getItem(storageKey) : undefined;
  }

  private writeStoredId(storageKey: string | undefined, value: string) {
    if (!storageKey) return;
    this.storage.setItem(storageKey, value);
  }

  private readMetadata(): WidgetSessionMetadata | undefined {
    if (!this.keys.sessionMetadataStorageKey) return undefined;
    const raw = this.storage.getItem(this.keys.sessionMetadataStorageKey);
    if (!raw) return undefined;

    try {
      const parsed = JSON.parse(raw) as Partial<WidgetSessionMetadata>;
      if (!parsed.sessionId || !parsed.createdAt || !parsed.legalVersion) return undefined;
      return {
        schemaVersion: parsed.schemaVersion || SESSION_SCHEMA_VERSION,
        visitorId: parsed.visitorId || this.readStoredId(this.keys.visitorStorageKey) || this.createVisitorId(),
        sessionId: parsed.sessionId,
        legalVersion: parsed.legalVersion,
        country: parsed.country,
        language: parsed.language,
        createdAt: parsed.createdAt,
        expiresAt: parsed.expiresAt,
        consentAccepted: parsed.consentAccepted
      };
    } catch {
      return undefined;
    }
  }

  private writeMetadata(metadata: WidgetSessionMetadata) {
    if (!this.keys.sessionMetadataStorageKey) return;
    this.storage.setItem(this.keys.sessionMetadataStorageKey, JSON.stringify(metadata));
  }
}

export function createSessionManager(options?: SessionManagerOptions) {
  return new SessionManager(options);
}
