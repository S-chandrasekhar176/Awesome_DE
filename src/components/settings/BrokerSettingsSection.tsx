'use client';

import { useState, useCallback, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Save,
  TestTube,
  Trash2,
  Shield,
  ShieldCheck,
  Zap,
  Info,
  LogIn,
  Clock,
} from 'lucide-react';
import { useStore, BROKER_LIST, BROKER_FIELDS, type BrokerCredentialFields } from '@/lib/store';
import { theme } from '@/styles/theme';
import {
  saveAngelOneCredentials,
  saveShoonyaCredentials,
  saveDhanCredentials,
  saveFyersCredentials,
  testAngelOneConnection,
  testShoonyaConnection,
  testDhanConnection,
  testFyersConnection,
  getFyersAuthUrl,
  getFyersTokenStatus,
} from '@/lib/api';

/* ─────────────────────────────────────────────
   Stable constants (avoid new refs on every render)
   ───────────────────────────────────────────── */

const EMPTY_CREDENTIALS: BrokerCredentialFields = {};

/* ─────────────────────────────────────────────
   Pure helper — checks if a broker's credentials
   are filled directly from the state snapshot.
   ───────────────────────────────────────────── */

function isBrokerCredsComplete(creds: BrokerCredentialFields | undefined, brokerId: string): boolean {
  if (!creds) return false;
  const fields = BROKER_FIELDS[brokerId];
  if (!fields || fields.length === 0) return true;
  return fields.every((f) => creds[f.key]?.trim() !== '');
}

/* ─────────────────────────────────────────────
   Broker Card Component
   ───────────────────────────────────────────── */

function BrokerCredentialCard({
  brokerId,
  isActiveEngineBroker = false,
}: {
  brokerId: string;
  isActiveEngineBroker?: boolean;
}) {
  const credentials = useStore((s) => s.brokers.credentials[brokerId] ?? EMPTY_CREDENTIALS);
  const isConfigured = useStore((s) => isBrokerCredsComplete(s.brokers.credentials[brokerId], brokerId));
  const saveCreds = useStore((s) => s.brokers.saveBrokerCredentials);
  const clearCreds = useStore((s) => s.brokers.clearBrokerCredentials);

  const brokerMeta = BROKER_LIST.find((b) => b.id === brokerId);
  const fields = BROKER_FIELDS[brokerId] || [];
  const needsCreds = brokerMeta?.needsCredentials ?? true;

  const [localCreds, setLocalCreds] = useState<BrokerCredentialFields>(credentials);
  const [testing, setTesting] = useState(false);
  const hasChanges = JSON.stringify(localCreds) !== JSON.stringify(credentials);

  // Sync local credentials when the store completes hydration
  useEffect(() => {
    if (credentials && Object.keys(credentials).length > 0) {
      setLocalCreds(credentials);
    }
  }, [credentials]);

  const handleSave = useCallback(async () => {
    // 1. Save to local Zustand store / localStorage
    saveCreds(brokerId, localCreds);

    // 2. Sync to backend API
    if (brokerId === 'angelone') {
      try {
        await saveAngelOneCredentials({
          client_id: localCreds.clientCode || '',
          client_secret: localCreds.apiSecret || localCreds.apiKey || '',
          api_key: localCreds.apiKey || '',
          pin: localCreds.pin || '',
          totp_secret: localCreds.totpSecret || '',
          account_type: 'live',
        });
        toast.success(`Angel One credentials synced to backend`);
      } catch (err: any) {
        toast.error(`Failed to sync to backend: ${err.response?.data?.detail || err.message || err}`);
      }
    } else if (brokerId === 'shoonya') {
      try {
        await saveShoonyaCredentials({
          client_id: localCreds.userId || '',
          client_secret: localCreds.password || '',
          totp_secret: localCreds.totpSecret || '',
          account_type: 'live',
        });
        toast.success(`Shoonya credentials synced to backend`);
      } catch (err: any) {
        toast.error(`Failed to sync to backend: ${err.response?.data?.detail || err.message || err}`);
      }
    } else if (brokerId === 'dhan') {
      try {
        await saveDhanCredentials({
          client_id: localCreds.clientId || '',
          access_token: localCreds.accessToken || '',
          account_type: 'live',
        });
        toast.success(`Dhan credentials synced to backend`);
      } catch (err: any) {
        toast.error(`Failed to sync to backend: ${err.response?.data?.detail || err.message || err}`);
      }
    } else if (brokerId === 'fyers') {
      try {
        await saveFyersCredentials({
          app_id: localCreds.appId || '',
          access_token: localCreds.accessToken || '',
          secret_key: localCreds.secretKey || '',
          redirect_uri: localCreds.redirectUri || '',
          pin: localCreds.pin || '',
          account_type: 'live',
        });
        toast.success(`Fyers credentials synced to backend`);
      } catch (err: any) {
        toast.error(`Failed to sync to backend: ${err.response?.data?.detail || err.message || err}`);
      }
    } else {
      toast.success(`${brokerMeta?.name || brokerId} credentials saved`);
    }
  }, [brokerId, localCreds, saveCreds, brokerMeta?.name]);

  const handleClear = useCallback(() => {
    clearCreds(brokerId);
    setLocalCreds({});
    toast.info(`${brokerMeta?.name || brokerId} credentials cleared`);
  }, [brokerId, clearCreds, brokerMeta?.name]);

  const handleTest = useCallback(async () => {
    setTesting(true);
    try {
      if (Object.keys(localCreds).length > 0) {
        await handleSave();
      }
      let res: any;
      if (brokerId === 'angelone') res = await testAngelOneConnection();
      else if (brokerId === 'shoonya') res = await testShoonyaConnection();
      else if (brokerId === 'dhan') res = await testDhanConnection();
      else if (brokerId === 'fyers') res = await testFyersConnection();

      if (res?.connected) {
        toast.success(`${brokerMeta?.name || brokerId}: Connection verified successfully!`);
      } else {
        toast.error(`${brokerMeta?.name || brokerId}: ${res?.message || 'Connection test failed'}`);
      }
    } catch (err: any) {
      toast.error(`${brokerMeta?.name || brokerId} test failed: ${err.message || err}`);
    } finally {
      setTesting(false);
    }
  }, [brokerId, brokerMeta?.name, localCreds, handleSave]);

  const [fyersStatus, setFyersStatus] = useState<{ connected: boolean; seconds_until_expiry: number } | null>(null);
  const [connecting, setConnecting] = useState(false);
  const searchParams = useSearchParams();

  const checkFyersStatus = useCallback(async () => {
    if (brokerId !== 'fyers') return;
    try {
      const res = await getFyersTokenStatus();
      setFyersStatus(res);
    } catch {
      setFyersStatus({ connected: false, seconds_until_expiry: 0 });
    }
  }, [brokerId]);

  useEffect(() => {
    if (brokerId === 'fyers') {
      checkFyersStatus();
      if (searchParams.get('fyers_auth') === 'success') {
        toast.success('Fyers login successful! Access token is valid.');
      } else if (searchParams.get('fyers_auth') === 'error') {
        toast.error(`Fyers login failed: ${searchParams.get('msg') || 'Unknown error'}`);
      }
    }
  }, [brokerId, checkFyersStatus, searchParams]);

  const handleFyersConnect = useCallback(async () => {
    setConnecting(true);
    try {
      const res = await getFyersAuthUrl();
      if (res?.auth_url) {
        window.location.href = res.auth_url;
      } else {
        toast.error('Failed to generate Fyers login URL. Verify App ID and Secret Key.');
      }
    } catch (err: any) {
      toast.error(`Fyers connect error: ${err.message || err}`);
    } finally {
      setConnecting(false);
    }
  }, []);

  const formatExpiry = (seconds: number) => {
    if (seconds <= 0) return 'Expired';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m remaining`;
  };

  const updateField = (key: string, val: string) => {
    setLocalCreds((prev) => ({ ...prev, [key]: val }));
  };

  // No credentials needed (Paper Broker / Yahoo Finance)
  if (!needsCreds) {
    return (
      <Card
        className={`bg-ub-surface transition-all ${
          isActiveEngineBroker
            ? 'border-ub-profit/60 shadow-[0_0_15px_rgba(0,208,156,0.12)] bg-ub-profit/[0.02]'
            : 'border-ub-border'
        }`}
      >
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div
                className="h-9 w-9 rounded-lg flex items-center justify-center font-bold text-sm"
                style={{ backgroundColor: theme.colors.profit + '15', color: theme.colors.profit, border: '1px solid ' + theme.colors.profit + '30' }}
              >
                {brokerMeta?.name?.[0] || '?'}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base font-semibold text-ub-text-primary">
                    {brokerMeta?.name || brokerId}
                  </CardTitle>
                  {isActiveEngineBroker && (
                    <Badge className="bg-ub-profit text-ub-background font-bold text-[9px] px-1.5 py-0 border-none flex items-center gap-1">
                      <Zap size={9} className="fill-current" /> ACTIVE IN ENGINE
                    </Badge>
                  )}
                </div>
                <p className="text-[11px] text-ub-text-disabled mt-0.5">
                  {brokerId === 'paper'
                    ? 'Built-in simulator — no configuration needed. Uses virtual money with simulated or real data.'
                    : 'Free market data from Yahoo Finance. No API key required.'}
                </p>
              </div>
            </div>
            <Badge
              variant="outline"
              className="border-ub-profit/40 text-ub-profit bg-ub-profit/10 text-[10px] font-semibold"
            >
              <CheckCircle2 size={11} className="mr-1" />
              Always Ready
            </Badge>
          </div>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card
      className={`bg-ub-surface transition-all ${
        isActiveEngineBroker
          ? 'border-ub-profit/60 shadow-[0_0_15px_rgba(0,208,156,0.12)] bg-ub-profit/[0.02]'
          : 'border-ub-border'
      }`}
    >
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div
              className="h-9 w-9 rounded-lg flex items-center justify-center font-bold text-sm"
              style={{
                backgroundColor: isConfigured ? theme.colors.profit + '15' : theme.colors.surfaceActive,
                color: isConfigured ? theme.colors.profit : theme.colors.textMuted,
                border: '1px solid ' + (isConfigured ? theme.colors.profit + '30' : theme.colors.border),
              }}
            >
              {brokerMeta?.name?.[0] || '?'}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <CardTitle className="text-base font-semibold text-ub-text-primary">
                  {brokerMeta?.name || brokerId}
                </CardTitle>
                {isActiveEngineBroker && (
                  <Badge className="bg-ub-profit text-ub-background font-bold text-[9px] px-1.5 py-0 border-none flex items-center gap-1">
                    <Zap size={9} className="fill-current" /> ACTIVE IN ENGINE
                  </Badge>
                )}
              </div>
              <p className="text-[11px] text-ub-text-disabled mt-0.5">
                Fill in your API credentials below. They are saved locally on your device.
              </p>
            </div>
          </div>
          <Badge
            variant="outline"
            className={`text-[10px] font-semibold ${
              isConfigured
                ? 'border-ub-profit/40 text-ub-profit bg-ub-profit/10'
                : 'border-ub-text-disabled/40 text-ub-text-disabled bg-ub-text-disabled/10'
            }`}
          >
            {isConfigured ? (
              <><CheckCircle2 size={11} className="mr-1" /> Configured</>
            ) : (
              <><XCircle size={11} className="mr-1" /> Not Configured</>
            )}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {fields.map((field) => (
            <div key={field.key} className="space-y-2">
              <Label className="text-ub-text-muted text-sm">{field.label}</Label>
              <Input
                type={field.type || 'text'}
                value={localCreds[field.key] || ''}
                onChange={(e) => updateField(field.key, e.target.value)}
                placeholder={field.placeholder}
                className="bg-ub-background border-ub-border text-ub-text-primary"
              />
            </div>
          ))}
        </div>
        {brokerId === 'fyers' && (
          <div
            className="flex items-center justify-between px-3 py-2 rounded-lg"
            style={{ backgroundColor: theme.colors.info + '08', border: '1px solid ' + theme.colors.info + '20' }}
          >
            <div className="flex items-center gap-2">
              <Clock size={13} style={{ color: theme.colors.textMuted }} />
              <span className="text-[11px] text-ub-text-muted">
                {fyersStatus === null
                  ? 'Checking connection status…'
                  : fyersStatus.connected
                  ? `Connected — token valid for ${formatExpiry(fyersStatus.seconds_until_expiry)}`
                  : 'Not connected — daily login required before live/paper trading with Fyers'}
              </span>
            </div>
            <Button
              onClick={handleFyersConnect}
              disabled={connecting}
              size="sm"
              className="bg-ub-accent hover:bg-ub-accent-hover text-ub-background font-semibold text-xs"
            >
              {connecting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
              ) : (
                <LogIn className="h-3.5 w-3.5 mr-1.5" />
              )}
              {fyersStatus?.connected ? 'Re-authenticate' : 'Connect'}
            </Button>
          </div>
        )}
        <div className="flex items-center justify-between">
          <Button
            onClick={handleClear}
            variant="ghost"
            className="text-ub-text-disabled hover:text-ub-loss hover:bg-ub-loss/10 text-xs"
          >
            <Trash2 className="h-3.5 w-3.5 mr-1.5" />
            Clear
          </Button>
          <div className="flex gap-2">
            <Button
              onClick={handleTest}
              disabled={testing || !isConfigured}
              variant="outline"
              className="border-ub-accent/40 text-ub-accent hover:bg-ub-accent/10 hover:text-ub-accent text-xs"
            >
              {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <TestTube className="h-3.5 w-3.5 mr-1.5" />}
              Test
            </Button>
            <Button
              onClick={handleSave}
              disabled={!hasChanges}
              className="bg-ub-accent hover:bg-ub-accent-hover text-ub-background font-semibold text-xs"
            >
              <Save className="h-3.5 w-3.5 mr-1.5" />
              Save
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* ─────────────────────────────────────────────
   Main Section
   ───────────────────────────────────────────── */

export default function BrokerSettingsSection() {
  const engineState = useStore((s) => s.engine.status);
  const activeBrokerId = useStore((s) => s.engine.activeBroker);
  const engineMode = useStore((s) => s.engine.mode);
  const isEngineRunning = engineState === 'running' || engineState === 'paused';

  const currentBrokerId = activeBrokerId || (engineMode === 'live' ? 'fyers' : 'paper');
  const activeBrokerMeta = BROKER_LIST.find((b) => b.id === currentBrokerId);

  const paperBrokers = BROKER_LIST.filter((b) => b.category === 'paper');
  const liveBrokers = BROKER_LIST.filter((b) => b.category === 'live');

  return (
    <div className="space-y-6">
      {/* Active Engine Broker Status Banner */}
      <div
        className="p-4 rounded-xl border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 transition-all"
        style={{
          backgroundColor: isEngineRunning ? 'rgba(0, 208, 156, 0.06)' : 'rgba(255, 255, 255, 0.02)',
          borderColor: isEngineRunning ? 'rgba(0, 208, 156, 0.3)' : 'rgba(255, 255, 255, 0.1)',
        }}
      >
        <div className="flex items-center gap-3">
          <div
            className={`h-11 w-11 rounded-xl flex items-center justify-center shrink-0 ${
              isEngineRunning ? 'bg-ub-profit/15 text-ub-profit' : 'bg-ub-accent/10 text-ub-accent'
            }`}
          >
            <ShieldCheck size={22} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-ub-text-muted">
                Active Execution Broker in Engine
              </span>
              <Badge
                className={`text-[10px] font-bold ${
                  isEngineRunning
                    ? 'bg-ub-profit text-ub-background animate-pulse'
                    : 'bg-ub-text-disabled/20 text-ub-text-muted'
                }`}
              >
                {isEngineRunning ? '● RUNNING IN ENGINE' : '○ ENGINE IDLE'}
              </Badge>
            </div>
            <p className="text-base font-bold text-ub-text-primary mt-0.5">
              {activeBrokerMeta?.name || currentBrokerId}
              <span className="text-xs font-normal text-ub-text-muted ml-2">
                ({engineMode.toUpperCase()} Mode)
              </span>
            </p>
            <p className="text-[11px] text-ub-text-disabled mt-0.5">
              {isEngineRunning
                ? 'All incoming strategy opportunities and risk-managed orders are active through this broker.'
                : 'Configure credentials below. When you start the engine, select which broker to trade with.'}
            </p>
          </div>
        </div>
      </div>

      {/* Info banner */}
      <div
        className="flex items-start gap-3 px-4 py-3 rounded-lg"
        style={{ backgroundColor: theme.colors.info + '08', border: '1px solid ' + theme.colors.info + '20' }}
      >
        <Info size={16} className="shrink-0 mt-0.5" style={{ color: theme.colors.info }} />
        <div>
          <p className="text-xs font-semibold" style={{ color: theme.colors.textPrimary }}>
            Broker Credentials &amp; API Integration
          </p>
          <p className="text-[11px] mt-0.5 leading-relaxed" style={{ color: theme.colors.textMuted }}>
            Your API credentials are stored locally on your device (encrypted in production). Configure at least one broker to use with the trading engine. Paper Broker and Yahoo Finance work without any credentials.
          </p>
        </div>
      </div>

      {/* Paper Mode Data Sources */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Shield size={15} style={{ color: theme.colors.profit }} />
          <h3 className="text-sm font-semibold text-ub-text-primary">Paper Trade Data Sources</h3>
          <Badge className="text-[9px] px-1.5 py-0 bg-ub-profit/10 text-ub-profit border-ub-profit/20 font-medium">
            No credentials needed
          </Badge>
        </div>
        <div className="space-y-3">
          {paperBrokers.map((b) => (
            <BrokerCredentialCard
              key={b.id}
              brokerId={b.id}
              isActiveEngineBroker={isEngineRunning && currentBrokerId === b.id}
            />
          ))}
        </div>
      </div>

      <Separator className="bg-ub-border" />

      {/* Live Brokers */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Zap size={15} style={{ color: theme.colors.loss }} />
          <h3 className="text-sm font-semibold text-ub-text-primary">Live Trade Brokers</h3>
          <Badge className="text-[9px] px-1.5 py-0 bg-ub-loss/10 text-ub-loss border-ub-loss/20 font-medium">
            Credentials required
          </Badge>
        </div>
        <div className="space-y-3">
          {liveBrokers.map((b) => (
            <BrokerCredentialCard
              key={b.id}
              brokerId={b.id}
              isActiveEngineBroker={isEngineRunning && currentBrokerId === b.id}
            />
          ))}
        </div>
      </div>
    </div>
  );
}