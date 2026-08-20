import { create } from 'zustand';

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

export type EngineStatus = 'running' | 'stopped' | 'paused' | 'error';
export type EngineMode = 'paper' | 'live';
export type MarketRegime = 'bull' | 'bear' | 'sideways' | 'volatile';

export interface Opportunity {
  id: string;
  symbol: string;
  type: string;
  direction: 'BUY' | 'SELL';
  entry: number;
  target: number;
  stopLoss: number;
  riskReward: number;
  confidence: number;
  strategy: string;
  timestamp: string;
}

export interface LivePrice {
  symbol: string;
  ltp: number;
  change: number;
  changePercent: number;
  high: number;
  low: number;
  open: number;
  volume: number;
}

// ─────────────────────────────────────────────
// Broker Types
// ─────────────────────────────────────────────

export const BROKER_LIST = [
  { id: 'paper', name: 'Paper Broker', needsCredentials: false, category: 'paper' as const },
  { id: 'yahoofinance', name: 'Yahoo Finance', needsCredentials: false, category: 'paper' as const },
  { id: 'zerodha', name: 'Zerodha', needsCredentials: true, category: 'live' as const },
  { id: 'angel_one', name: 'Angel One', needsCredentials: true, category: 'live' as const },
  { id: 'dhan', name: 'Dhan', needsCredentials: true, category: 'live' as const },
  { id: 'fyers', name: 'Fyers', needsCredentials: true, category: 'live' as const },
  { id: 'shoonya', name: 'Shoonya', needsCredentials: true, category: 'live' as const },
] as const;

export type BrokerId = (typeof BROKER_LIST)[number]['id'] | 'angelone';

export interface BrokerCredentialFields {
  [key: string]: string;
}

// Credential field definitions per broker
export const BROKER_FIELDS: Record<string, { key: string; label: string; placeholder: string; type?: 'password' }[]> = {
  zerodha: [
    { key: 'apiKey', label: 'API Key', placeholder: 'Your Zerodha API key' },
    { key: 'apiSecret', label: 'API Secret', placeholder: 'Your Zerodha API secret', type: 'password' },
    { key: 'userId', label: 'User ID / PAN', placeholder: 'e.g. AB1234' },
    { key: 'totpSecret', label: 'TOTP Secret', placeholder: 'For auto-login (optional)', type: 'password' },
  ],
  angel_one: [
    { key: 'apiKey', label: 'SmartAPI Key', placeholder: 'Your Angel One API key' },
    { key: 'clientCode', label: 'Client Code', placeholder: 'Your client code' },
    { key: 'pin', label: 'PIN', placeholder: 'Your PIN', type: 'password' },
    { key: 'totpSecret', label: 'TOTP Secret', placeholder: 'For auto-login (optional)', type: 'password' },
  ],
  angelone: [
    { key: 'apiKey', label: 'SmartAPI Key', placeholder: 'Your Angel One API key' },
    { key: 'clientCode', label: 'Client Code', placeholder: 'Your client code' },
    { key: 'pin', label: 'PIN', placeholder: 'Your PIN', type: 'password' },
    { key: 'totpSecret', label: 'TOTP Secret', placeholder: 'For auto-login (optional)', type: 'password' },
  ],
  dhan: [
    { key: 'clientId', label: 'Client ID', placeholder: 'Your Dhan Client ID (e.g. 1000000123)' },
    { key: 'accessToken', label: 'Access Token (JWT)', placeholder: 'Paste your Dhan JWT Access Token', type: 'password' },
  ],
  fyers: [
    { key: 'appId', label: 'App ID / Client ID', placeholder: 'Your Fyers App ID (e.g. XC12345-100)' },
    { key: 'secretKey', label: 'Secret Key', placeholder: 'Your Fyers App Secret Key', type: 'password' },
    { key: 'redirectUri', label: 'Redirect URI', placeholder: 'Must match the URI registered in your Fyers app (e.g. http://127.0.0.1:8000/api/brokers/fyers/callback)' },
    { key: 'accessToken', label: 'Access Token (auto-filled after Connect)', placeholder: 'Click "Connect / Re-authenticate" below instead of pasting this manually', type: 'password' },
    { key: 'pin', label: 'User PIN', placeholder: 'Your Fyers PIN (optional)', type: 'password' },
  ],
  shoonya: [
    { key: 'userId', label: 'User ID', placeholder: 'Your Shoonya User ID' },
    { key: 'password', label: 'Password', placeholder: 'Your Shoonya Password', type: 'password' },
    { key: 'vendorCode', label: 'Vendor Code', placeholder: 'Your Shoonya Vendor Code (e.g. FA12345_U)' },
    { key: 'appKey', label: 'API / App Key', placeholder: 'Your Shoonya API App Key', type: 'password' },
    { key: 'totpSecret', label: 'TOTP Secret', placeholder: 'Your TOTP Secret Key', type: 'password' },
  ],
  yahoofinance: [
    { key: 'symbols', label: 'Symbol List', placeholder: 'e.g. ^NSEI, ^NSEBANK, RELIANCE.NS' },
  ],
  paper: [],
};

// ─────────────────────────────────────────────
// Auth Slice
// ─────────────────────────────────────────────

export interface AuthSlice {
  token: string | null;
  username: string | null;
  isAuthenticated: boolean;
  login: (token: string, username: string) => void;
  logout: () => void;
  hydrate: () => void;
}

// ─────────────────────────────────────────────
// Engine Slice
// ─────────────────────────────────────────────

export interface EngineSlice {
  status: EngineStatus;
  mode: EngineMode;
  regime: MarketRegime;
  vix: number;
  niftyValue: number;
  niftyChange: number;
  marketCloseSeconds: number;
  activeBroker: string | null;
  startedAt: number | null;
  errorMessage: string | null;
  lastHeartbeat: number | null;
  scanTelemetry: any | null;
  setEngineStatus: (status: EngineStatus) => void;
  setMode: (mode: EngineMode) => void;
  setRegime: (regime: MarketRegime) => void;
  setVix: (vix: number) => void;
  setNifty: (value: number, change: number) => void;
  setMarketCloseSeconds: (seconds: number) => void;
  setActiveBroker: (broker: string | null) => void;
  setErrorMessage: (msg: string | null) => void;
  setScanTelemetry: (telemetry: any) => void;
  addTelemetryEvent: (event: any) => void;
  start: (mode: EngineMode, brokerId: string) => void;
  stop: () => void;
  heartbeat: () => void;
  hydrateEngine: () => void;
}

// ─────────────────────────────────────────────
// Realtime Slice
// ─────────────────────────────────────────────

export interface RealtimeSlice {
  livePrices: Record<string, LivePrice>;
  opportunities: Opportunity[];
  updatePrice: (price: LivePrice) => void;
  updatePrices: (prices: LivePrice[]) => void;
  addOpportunity: (opportunity: Opportunity) => void;
  setOpportunities: (opportunities: Opportunity[]) => void;
  clearOpportunities: () => void;
}

// ─────────────────────────────────────────────
// Sidebar Slice
// ─────────────────────────────────────────────

export interface SidebarSlice {
  collapsed: boolean;
  mobileOpen: boolean;
  toggle: () => void;
  setCollapsed: (collapsed: boolean) => void;
  setMobileOpen: (open: boolean) => void;
}

// ─────────────────────────────────────────────
// Brokers Slice
// ─────────────────────────────────────────────

export interface BrokersSlice {
  credentials: Record<string, BrokerCredentialFields>;
  saveBrokerCredentials: (brokerId: string, fields: BrokerCredentialFields) => void;
  clearBrokerCredentials: (brokerId: string) => void;
  isBrokerConfigured: (brokerId: string) => boolean;
  hydrateBrokers: () => void;
}

// ─────────────────────────────────────────────
// Combined Store
// ─────────────────────────────────────────────

interface StoreState {
  auth: AuthSlice;
  engine: EngineSlice;
  realtime: RealtimeSlice;
  sidebar: SidebarSlice;
  brokers: BrokersSlice;
}

// ─────────────────────────────────────────────
// Store — actions inside each slice
// ─────────────────────────────────────────────

const LS_BROKERS_KEY = 'ultrabot_broker_creds';

export const useStore = create<StoreState>((set, get) => ({
  auth: {
    token: null,
    username: null,
    isAuthenticated: false,

    login(token: string, username: string) {
      if (typeof window !== 'undefined') {
        localStorage.setItem('ultrabot_token', token);
        localStorage.setItem('ultrabot_username', username);
      }
      set({ auth: { ...get().auth, token, username, isAuthenticated: true } });
    },

    logout() {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('ultrabot_token');
        localStorage.removeItem('ultrabot_username');
      }
      set({ auth: { ...get().auth, token: null, username: null, isAuthenticated: false } });
    },

    hydrate() {
      if (typeof window === 'undefined') return;
      const token = localStorage.getItem('ultrabot_token');
      const username = localStorage.getItem('ultrabot_username');
      set({ auth: { ...get().auth, token, username, isAuthenticated: !!token } });
    },
  },

  engine: {
    status: 'stopped',
    mode: 'paper',
    regime: 'sideways',
    vix: 0,
    niftyValue: 0,
    niftyChange: 0,
    marketCloseSeconds: 0,
    activeBroker: null,
    startedAt: null,
    errorMessage: null,
    lastHeartbeat: null,

    hydrateEngine() {
      if (typeof window === 'undefined') return;
      const saved = localStorage.getItem('ultrabot_engine_state');
      const savedMode = (localStorage.getItem('ultrabot_engine_mode') as EngineMode) || 'paper';
      const savedBroker = localStorage.getItem('ultrabot_active_broker');
      const savedStartedAt = localStorage.getItem('ultrabot_started_at');

      if (saved && (saved === 'running' || saved === 'stopped' || saved === 'paused')) {
        set({
          engine: {
            ...get().engine,
            status: saved as EngineStatus,
            mode: savedMode,
            activeBroker: saved === 'running' ? (savedBroker || 'paper') : null,
            startedAt: saved === 'running' && savedStartedAt ? Number(savedStartedAt) : null,
          },
        });
      }
    },

    scanTelemetry: null,

    setEngineStatus(status) {
      if (typeof window !== 'undefined') {
        localStorage.setItem('ultrabot_engine_state', status);
      }
      set({ engine: { ...get().engine, status } });
    },
    setMode(mode) { set({ engine: { ...get().engine, mode } }); },
    setRegime(regime) { set({ engine: { ...get().engine, regime } }); },
    setVix(vix) { set({ engine: { ...get().engine, vix } }); },
    setNifty(value, change) { set({ engine: { ...get().engine, niftyValue: value, niftyChange: change } }); },
    setMarketCloseSeconds(seconds) { set({ engine: { ...get().engine, marketCloseSeconds: seconds } }); },
    setActiveBroker(broker) {
      if (typeof window !== 'undefined' && broker) {
        localStorage.setItem('ultrabot_active_broker', broker);
      }
      set({ engine: { ...get().engine, activeBroker: broker } });
    },
    setErrorMessage(msg) { set({ engine: { ...get().engine, errorMessage: msg } }); },
    setScanTelemetry(telemetry) { set({ engine: { ...get().engine, scanTelemetry: telemetry } }); },
    addTelemetryEvent(event) {
      const current = get().engine.scanTelemetry || { recent_events: [], rejections_by_gate: {}, signals_generated: 0, signals_passed: 0, signals_rejected: 0 };
      const recent = [event, ...(current.recent_events || [])].slice(0, 50);
      const isPassed = event.status === 'PASSED';
      const isRejected = event.status === 'REJECTED';
      const gateMap = { ...(current.rejections_by_gate || {}) };
      if (isRejected && event.gate && event.gate !== '—') {
        gateMap[event.gate] = (gateMap[event.gate] || 0) + 1;
      }
      set({
        engine: {
          ...get().engine,
          scanTelemetry: {
            ...current,
            signals_generated: (current.signals_generated || 0) + (isPassed || isRejected ? 1 : 0),
            signals_passed: (current.signals_passed || 0) + (isPassed ? 1 : 0),
            signals_rejected: (current.signals_rejected || 0) + (isRejected ? 1 : 0),
            rejections_by_gate: gateMap,
            recent_events: recent,
          }
        }
      });
    },

    start(mode, brokerId) {
      const now = Date.now();
      if (typeof window !== 'undefined') {
        localStorage.setItem('ultrabot_engine_state', 'running');
        localStorage.setItem('ultrabot_engine_mode', mode);
        localStorage.setItem('ultrabot_active_broker', brokerId);
        localStorage.setItem('ultrabot_started_at', String(now));
      }
      set({
        engine: {
          ...get().engine,
          status: 'running',
          mode,
          activeBroker: brokerId,
          startedAt: now,
          errorMessage: null,
          lastHeartbeat: now,
        },
      });
    },

    stop() {
      if (typeof window !== 'undefined') {
        localStorage.setItem('ultrabot_engine_state', 'stopped');
        localStorage.removeItem('ultrabot_active_broker');
        localStorage.removeItem('ultrabot_started_at');
      }
      set({
        engine: {
          ...get().engine,
          status: 'stopped',
          activeBroker: null,
          startedAt: null,
          errorMessage: null,
          lastHeartbeat: null,
        },
      });
    },

    heartbeat() {
      set({ engine: { ...get().engine, lastHeartbeat: Date.now() } });
    },
  },

  realtime: {
    livePrices: {},
    opportunities: [],

    updatePrice(price) {
      set({
        realtime: {
          ...get().realtime,
          livePrices: { ...get().realtime.livePrices, [price.symbol]: price },
        },
      });
    },
    updatePrices(prices) {
      const updated = { ...get().realtime.livePrices };
      for (const p of prices) { updated[p.symbol] = p; }
      set({ realtime: { ...get().realtime, livePrices: updated } });
    },
    addOpportunity(opportunity) {
      set({
        realtime: {
          ...get().realtime,
          opportunities: [opportunity, ...get().realtime.opportunities],
        },
      });
    },
    setOpportunities(opportunities) {
      set({ realtime: { ...get().realtime, opportunities } });
    },
    clearOpportunities() {
      set({ realtime: { ...get().realtime, opportunities: [] } });
    },
  },

  sidebar: {
    collapsed: false,
    mobileOpen: false,

    toggle() { set({ sidebar: { ...get().sidebar, collapsed: !get().sidebar.collapsed } }); },
    setCollapsed(collapsed) { set({ sidebar: { ...get().sidebar, collapsed } }); },
    setMobileOpen(mobileOpen) { set({ sidebar: { ...get().sidebar, mobileOpen } }); },
  },

  brokers: {
    credentials: {},

    saveBrokerCredentials(brokerId, fields) {
      const updated = { ...get().brokers.credentials, [brokerId]: fields };
      if (typeof window !== 'undefined') {
        localStorage.setItem(LS_BROKERS_KEY, JSON.stringify(updated));
      }
      set({ brokers: { ...get().brokers, credentials: updated } });
    },

    clearBrokerCredentials(brokerId) {
      const updated = { ...get().brokers.credentials };
      delete updated[brokerId];
      if (typeof window !== 'undefined') {
        localStorage.setItem(LS_BROKERS_KEY, JSON.stringify(updated));
      }
      set({ brokers: { ...get().brokers, credentials: updated } });
    },

    isBrokerConfigured(brokerId) {
      const creds = get().brokers.credentials[brokerId];
      if (!creds) return false;
      // Check that at least one non-empty value exists
      return Object.values(creds).some((v) => v.trim() !== '');
    },

    hydrateBrokers() {
      if (typeof window === 'undefined') return;
      try {
        const raw = localStorage.getItem(LS_BROKERS_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          set({ brokers: { ...get().brokers, credentials: parsed } });
        }
      } catch {
        // ignore corrupt data
      }
    },
  },
}));

// ─────────────────────────────────────────────
// Selectors — simple, stable references
// ─────────────────────────────────────────────

export const useAuth = () => useStore((s) => s.auth);
export const useEngine = () => useStore((s) => s.engine);
export const useRealtime = () => useStore((s) => s.realtime);
export const useSidebar = () => useStore((s) => s.sidebar);
export const useBrokers = () => useStore((s) => s.brokers);