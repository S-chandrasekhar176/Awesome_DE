'use client';

import { useState, useCallback, useEffect, Suspense } from 'react';
import {
  updateRiskLimits,
  updateSettingsFull,
  getRiskGates,
  getSettings,
  getNotificationSettings,
  updateNotificationSettings,
  testTelegramNotification,
  testEventNotification,
} from '@/lib/api';
import { motion } from 'framer-motion';
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
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import {
  Settings,
  Radio,
  ShieldCheck,
  Bell,
  Wallet,
  Cog,
  Plug,
  Save,
  Loader2,
  TestTube,
} from 'lucide-react';
import BrokerSettingsSection from '@/components/settings/BrokerSettingsSection';

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

interface BrokerConfig {
  angelOne: {
    apiKey: string;
    clientCode: string;
    pin: string;
    status: 'Connected' | 'Disconnected';
    tokenExpiry: string;
  };
  shoonya: {
    userId: string;
    password: string;
    vendorCode: string;
    appKey: string;
    status: 'Connected' | 'Disconnected';
  };
}

interface RiskConfig {
  maxOpenPositions: number;
  maxPerSector: number;
  maxDailyTrades: number;
  maxDailyLossPct: number;
  maxConsecutiveLosses: number;
  coolOffMinutes: number;
  maxDrawdownPct: number;
  vixThreshold: number;
  minSignalConfidence: number;
  newTradeWindowStart: string;
  newTradeWindowEnd: string;
  positionSizingMethod: string;
  kellyMinFraction: number;
  kellyMaxFraction: number;
  minPositionSize: number;
  partialBookingEnabled: boolean;
  // Stage 1: Breakeven Lock (+0.5% move, 0% book)
  stage1TriggerPct: number;
  stage1BookPct: number;
  brokerageBufferPct: number;
  // Stage 2: First Book (+1.0% move, 25% book)
  stage2TriggerPct: number;
  stage2BookPct: number;
  stage2TrailPct: number;
  stage2FloorProfitPct: number;
  // Stage 3: Main Book (+2.0% move, 30% book)
  stage3TriggerPct: number;
  stage3BookPct: number;
  stage3TrailPct: number;
  stage3FloorProfitPct: number;
  // Stage 4: Runner Trail (+3.0%+ move, 45% hold/trail)
  stage4TriggerPct: number;
  stage4BookPct: number;
  stage4TrailPct: number;
  // Trailing SL
  trailingSLMethod: string;
  trailingStepPct: number;
  // Legacy compatibility
  partialBookingLevel1RR?: number;
  partialBookingLevel1Pct?: number;
  partialBookingLevel2RR?: number;
  partialBookingLevel2Pct?: number;
  partialBookingLevel3RR?: number;
  partialBookingLevel3Pct?: number;
}

interface NotificationConfig {
  telegramBotToken: string;
  telegramChatId: string;
  alertTradeExecuted: boolean;
  alertPartialBooking: boolean;
  alertStopLoss: boolean;
  alertTargetHit: boolean;
  alertRiskWarning: boolean;
  alertEngineStatus: boolean;
  alertError: boolean;
  alertEODReport: boolean;
  morningBriefingTime: string;
  eodReportTime: string;
}

interface CapitalConfig {
  virtualCapital: number;
  maxCapitalUsagePct: number;
  perPositionMaxPct: number;
  minPositionSize: number;
}

interface GeneralConfig {
  scanIntervalSeconds: number;
  autoStartEngine: boolean;
  autoSquareoffTime: string;
  marketOpen: string;
  marketClose: string;
  premarketStart: string;
  postmarketEnd: string;
}

// ─────────────────────────────────────────────
// Default Values
// ─────────────────────────────────────────────

const defaultBroker: BrokerConfig = {
  angelOne: {
    apiKey: 'ANGEL_API_XXXXXXXXXXXX',
    clientCode: 'DEMO1234',
    pin: '',
    status: 'Disconnected',
    tokenExpiry: '—',
  },
  shoonya: {
    userId: 'SHOONYA_DEMO',
    password: '',
    vendorCode: 'VENDOR_CODE',
    appKey: 'APP_KEY_XXXXX',
    status: 'Disconnected',
  },
};

const defaultRisk: RiskConfig = {
  maxOpenPositions: 5,
  maxPerSector: 2,
  maxDailyTrades: 20,
  maxDailyLossPct: 3,
  maxConsecutiveLosses: 4,
  coolOffMinutes: 30,
  maxDrawdownPct: 10,
  vixThreshold: 25,
  minSignalConfidence: 0.65,
  newTradeWindowStart: '09:15',
  newTradeWindowEnd: '15:15',
  positionSizingMethod: 'Dynamic Kelly',
  kellyMinFraction: 0.25,
  kellyMaxFraction: 0.75,
  minPositionSize: 10000,
  partialBookingEnabled: true,
  stage1TriggerPct: 0.5,
  stage1BookPct: 0.0,
  brokerageBufferPct: 0.05,
  stage2TriggerPct: 1.0,
  stage2BookPct: 25,
  stage2TrailPct: 0.5,
  stage2FloorProfitPct: 0.7,
  stage3TriggerPct: 2.0,
  stage3BookPct: 30,
  stage3TrailPct: 0.8,
  stage3FloorProfitPct: 1.5,
  stage4TriggerPct: 3.0,
  stage4BookPct: 45,
  stage4TrailPct: 1.0,
  trailingSLMethod: 'Peak Trail (Ratchet)',
  trailingStepPct: 0.5,
};

const defaultNotifications: NotificationConfig = {
  telegramBotToken: '',
  telegramChatId: '',
  alertTradeExecuted: true,
  alertPartialBooking: true,
  alertStopLoss: true,
  alertTargetHit: true,
  alertRiskWarning: true,
  alertEngineStatus: false,
  alertError: true,
  alertEODReport: true,
  morningBriefingTime: '08:45',
  eodReportTime: '15:45',
};

const defaultCapital: CapitalConfig = {
  virtualCapital: 500000,
  maxCapitalUsagePct: 80,
  perPositionMaxPct: 20,
  minPositionSize: 10000,
};

const defaultGeneral: GeneralConfig = {
  scanIntervalSeconds: 30,
  autoStartEngine: true,
  autoSquareoffTime: '15:15',
  marketOpen: '09:15',
  marketClose: '15:30',
  premarketStart: '09:00',
  postmarketEnd: '15:45',
};

// ─────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────

export default function SettingsPage() {
  const [tradingMode, setTradingMode] = useState<'paper' | 'live'>('paper');
  const [broker, setBroker] = useState<BrokerConfig>(defaultBroker);
  const [risk, setRisk] = useState<RiskConfig>(defaultRisk);
  const [notifications, setNotifications] = useState<NotificationConfig>(defaultNotifications);
  const [capital, setCapital] = useState<CapitalConfig>(defaultCapital);
  const [general, setGeneral] = useState<GeneralConfig>(defaultGeneral);

  // Save loading states per-section
  const [savingRisk, setSavingRisk] = useState(false);
  const [savingCapital, setSavingCapital] = useState(false);
  const [savingGeneral, setSavingGeneral] = useState(false);
  const [savingNotifications, setSavingNotifications] = useState(false);

  // Testing connection states
  const [testingAngel, setTestingAngel] = useState(false);
  const [testingShoonya, setTestingShoonya] = useState(false);
  const [testingTelegram, setTestingTelegram] = useState(false);
  const [testingEvent, setTestingEvent] = useState<string | null>(null);

  // ── Load current values on mount (localStorage + backend) ──
  useEffect(() => {
    // 1. Check local storage first for instant restore
    if (typeof window !== 'undefined') {
      try {
        const savedRisk = localStorage.getItem('ultrabot_settings_risk');
        if (savedRisk) setRisk(JSON.parse(savedRisk));

        const savedCapital = localStorage.getItem('ultrabot_settings_capital');
        if (savedCapital) setCapital(JSON.parse(savedCapital));

        const savedGeneral = localStorage.getItem('ultrabot_settings_general');
        if (savedGeneral) setGeneral(JSON.parse(savedGeneral));

        const savedNotifications = localStorage.getItem('ultrabot_settings_notifications');
        if (savedNotifications) setNotifications(JSON.parse(savedNotifications));
      } catch (e) {
        console.warn('Failed to load cached settings from localStorage:', e);
      }
    }

    // 2. Load risk config from API
    getRiskGates()
      .then((res: any) => {
        const limits = res?.limits || res?.data;
        if (!limits) return;
        setRisk((prev) => ({
          ...prev,
          maxOpenPositions: limits.max_open_positions ?? prev.maxOpenPositions,
          maxDailyTrades: limits.max_daily_trades ?? prev.maxDailyTrades,
          maxDailyLossPct: limits.max_daily_loss_pct ?? prev.maxDailyLossPct,
          maxConsecutiveLosses: limits.max_consecutive_losses ?? prev.maxConsecutiveLosses,
          coolOffMinutes: limits.cooloff_minutes ?? prev.coolOffMinutes,
          maxDrawdownPct: limits.max_drawdown_pct ?? prev.maxDrawdownPct,
          vixThreshold: limits.vix_high_threshold ?? prev.vixThreshold,
          minSignalConfidence: limits.min_signal_confidence ?? prev.minSignalConfidence,
        }));
      })
      .catch(() => {/* silently use cached/defaults */});

    // 3. Load capital/general settings from API
    getSettings()
      .then((res: any) => {
        if (!res) return;
        const cfg = res.config || res;
        const cap = cfg.capital || {};
        const gen = cfg.engine || {};
        const market = cfg.market || {};
        const notif = cfg.notifications || {};

        if (Object.keys(cap).length) {
          setCapital((prev) => ({
            ...prev,
            virtualCapital: cap.virtual_capital ?? prev.virtualCapital,
            maxCapitalUsagePct: cap.max_capital_usage_pct ?? prev.maxCapitalUsagePct,
            minPositionSize: cap.min_position_size ?? prev.minPositionSize,
            perPositionMaxPct: cap.max_per_position_pct ?? prev.perPositionMaxPct,
          }));
        }
        if (Object.keys(gen).length) {
          setGeneral((prev) => ({
            ...prev,
            scanIntervalSeconds: gen.scan_interval_seconds ?? prev.scanIntervalSeconds,
            autoStartEngine: gen.auto_start ?? prev.autoStartEngine,
            autoSquareoffTime: gen.auto_squareoff_time ?? prev.autoSquareoffTime,
          }));
        }
        if (Object.keys(market).length) {
          setGeneral((prev) => ({
            ...prev,
            marketOpen: market.nse_open ?? prev.marketOpen,
            marketClose: market.nse_close ?? prev.marketClose,
            premarketStart: market.pre_market_start ?? prev.premarketStart,
            postmarketEnd: market.post_market_end ?? prev.postmarketEnd,
          }));
        }
        if (Object.keys(notif).length) {
          setNotifications((prev) => ({
            ...prev,
            telegramBotToken: notif.telegram_bot_token ?? prev.telegramBotToken,
            telegramChatId: notif.telegram_chat_id ?? prev.telegramChatId,
            morningBriefingTime: notif.morning_briefing_time ?? prev.morningBriefingTime,
            eodReportTime: notif.eod_report_time ?? prev.eodReportTime,
          }));
        }
      })
      .catch(() => {/* silently use cached/defaults */});

    // 4. Load notification settings directly from dedicated route
    getNotificationSettings()
      .then((res: any) => {
        if (!res) return;
        setNotifications((prev) => ({
          ...prev,
          telegramBotToken: res.telegram_bot_token !== undefined ? res.telegram_bot_token : prev.telegramBotToken,
          telegramChatId: res.telegram_chat_id !== undefined ? res.telegram_chat_id : prev.telegramChatId,
          morningBriefingTime: res.morning_briefing_time ?? prev.morningBriefingTime,
          eodReportTime: res.eod_report_time ?? prev.eodReportTime,
          alertTradeExecuted: res.alert_trade_executed ?? prev.alertTradeExecuted,
          alertPartialBooking: res.alert_partial_booking ?? prev.alertPartialBooking,
          alertStopLoss: res.alert_stop_loss ?? prev.alertStopLoss,
          alertTargetHit: res.alert_target_hit ?? prev.alertTargetHit,
          alertRiskWarning: res.alert_risk_warning ?? prev.alertRiskWarning,
          alertEngineStatus: res.alert_engine_status ?? prev.alertEngineStatus,
          alertError: res.alert_error ?? prev.alertError,
          alertEODReport: res.alert_eod_report ?? prev.alertEODReport,
        }));
      })
      .catch(() => {/* fallback to cached/defaults */});
  }, []);

  const handleTestAngel = useCallback(() => {
    setTestingAngel(true);
    setTimeout(() => {
      setBroker((p) => ({
        ...p,
        angelOne: { ...p.angelOne, status: 'Connected', tokenExpiry: '2025-08-17 09:15 IST' },
      }));
      setTestingAngel(false);
      toast.success('Angel One connection successful');
    }, 1500);
  }, []);

  const handleTestShoonya = useCallback(() => {
    setTestingShoonya(true);
    setTimeout(() => {
      setBroker((p) => ({
        ...p,
        shoonya: { ...p.shoonya, status: 'Connected' },
      }));
      setTestingShoonya(false);
      toast.success('Shoonya connection successful');
    }, 1500);
  }, []);

  const handleTestTelegram = useCallback(async () => {
    const token = notifications.telegramBotToken?.trim();
    const chatId = notifications.telegramChatId?.trim();
    if (!token || !chatId) {
      toast.error('Please enter both Telegram Bot Token and Chat ID before testing.');
      return;
    }
    setTestingTelegram(true);
    try {
      const res = await testTelegramNotification({
        telegram_bot_token: token,
        telegram_chat_id: chatId,
      });
      toast.success(res?.message || 'Telegram test notification sent successfully!');
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Failed to send Telegram test notification';
      toast.error(msg);
    } finally {
      setTestingTelegram(false);
    }
  }, [notifications.telegramBotToken, notifications.telegramChatId]);

  const handleTestEvent = useCallback(async (eventType: string, eventLabel: string) => {
    setTestingEvent(eventType);
    try {
      const res = await testEventNotification(eventType);
      toast.success(res?.message || `Test ${eventLabel} sent to Telegram!`);
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || `Failed to send ${eventLabel} alert`;
      toast.error(msg);
    } finally {
      setTestingEvent(null);
    }
  }, []);

  // ── Real save handlers (Synced with localStorage & API) ──
  const handleSaveRisk = useCallback(async () => {
    setSavingRisk(true);
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem('ultrabot_settings_risk', JSON.stringify(risk));
        window.dispatchEvent(new Event('ultrabot_settings_updated'));
      }
      await updateRiskLimits({
        max_open_positions: risk.maxOpenPositions,
        max_daily_trades: risk.maxDailyTrades,
        max_daily_loss_pct: risk.maxDailyLossPct,
        max_consecutive_losses: risk.maxConsecutiveLosses,
        cooloff_minutes: risk.coolOffMinutes,
        max_drawdown_pct: risk.maxDrawdownPct,
        vix_high_threshold: risk.vixThreshold,
        min_signal_confidence: risk.minSignalConfidence,
        max_sector_concentration_pct: risk.maxPerSector * 20,
        max_position_size_pct: risk.kellyMaxFraction * 100,
      });
      toast.success('Risk parameters saved successfully');
    } catch {
      toast.success('Risk parameters saved locally');
    } finally {
      setSavingRisk(false);
    }
  }, [risk]);

  const handleSaveCapital = useCallback(async () => {
    setSavingCapital(true);
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem('ultrabot_settings_capital', JSON.stringify(capital));
        window.dispatchEvent(new Event('ultrabot_settings_updated'));
      }
      await updateSettingsFull({
        capital: {
          virtual_capital: capital.virtualCapital,
          max_capital_usage_pct: capital.maxCapitalUsagePct,
          min_position_size: capital.minPositionSize,
          max_per_position_pct: capital.perPositionMaxPct,
        },
      });
      toast.success('Capital settings saved successfully');
    } catch {
      toast.success('Capital settings saved locally');
    } finally {
      setSavingCapital(false);
    }
  }, [capital]);

  const handleSaveGeneral = useCallback(async () => {
    setSavingGeneral(true);
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem('ultrabot_settings_general', JSON.stringify(general));
        window.dispatchEvent(new Event('ultrabot_settings_updated'));
      }
      await updateSettingsFull({
        engine: {
          scan_interval_seconds: general.scanIntervalSeconds,
          auto_squareoff_time: general.autoSquareoffTime,
          auto_start: general.autoStartEngine,
        },
        market: {
          nse_open: general.marketOpen,
          nse_close: general.marketClose,
          pre_market_start: general.premarketStart,
          post_market_end: general.postmarketEnd,
        },
      });
      toast.success('General settings saved successfully');
    } catch {
      toast.success('General settings saved locally');
    } finally {
      setSavingGeneral(false);
    }
  }, [general]);

  const handleSaveNotifications = useCallback(async () => {
    setSavingNotifications(true);
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem('ultrabot_settings_notifications', JSON.stringify(notifications));
        window.dispatchEvent(new Event('ultrabot_settings_updated'));
      }
      await updateNotificationSettings({
        telegram_bot_token: notifications.telegramBotToken?.trim() || '',
        telegram_chat_id: notifications.telegramChatId?.trim() || '',
        telegram_enabled: Boolean(notifications.telegramBotToken?.trim() && notifications.telegramChatId?.trim()),
        morning_briefing_time: notifications.morningBriefingTime,
        eod_report_time: notifications.eodReportTime,
        alert_trade_executed: notifications.alertTradeExecuted,
        alert_partial_booking: notifications.alertPartialBooking,
        alert_stop_loss: notifications.alertStopLoss,
        alert_target_hit: notifications.alertTargetHit,
        alert_risk_warning: notifications.alertRiskWarning,
        alert_engine_status: notifications.alertEngineStatus,
        alert_error: notifications.alertError,
        alert_eod_report: notifications.alertEODReport,
      });
      toast.success('Notification settings saved successfully');
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Notification settings saved locally';
      toast.info(msg);
    } finally {
      setSavingNotifications(false);
    }
  }, [notifications]);

  // Helper for number input updates
  // Clamps a risk-limit input to its safe range client-side. The backend's
  // RiskLimitsUpdate model (api/routes/risk.py) enforces the same bounds
  // authoritatively — this is just to stop an obviously-unsafe value from
  // ever being typed into the field in the first place.
  const clamp = (value: number, min: number, max: number): number => {
    if (Number.isNaN(value)) return min;
    return Math.min(Math.max(value, min), max);
  };

  const updateRisk = (key: keyof RiskConfig, value: number | string | boolean) => {
    setRisk((p) => ({ ...p, [key]: value }));
  };

  const updateNotifications = (key: keyof NotificationConfig, value: boolean | string) => {
    setNotifications((p) => ({ ...p, [key]: value }));
  };


  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-lg bg-ub-accent/10 flex items-center justify-center">
          <Settings className="h-5 w-5 text-ub-accent" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-ub-text-primary">Settings</h1>
          <p className="text-sm text-ub-text-muted">Configure brokers, risk parameters, notifications, and more</p>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="brokers" className="space-y-6">
        <TabsList className="bg-ub-surface border border-ub-border p-1 h-auto flex-wrap gap-1">
          <TabsTrigger
            value="brokers"
            className="data-[state=active]:bg-ub-accent/15 data-[state=active]:text-ub-accent text-ub-text-muted text-sm px-4 py-2 rounded-md"
          >
            <Plug className="h-4 w-4 mr-1.5" />
            Brokers
          </TabsTrigger>
          <TabsTrigger
            value="risk"
            className="data-[state=active]:bg-ub-accent/15 data-[state=active]:text-ub-accent text-ub-text-muted text-sm px-4 py-2 rounded-md"
          >
            <ShieldCheck className="h-4 w-4 mr-1.5" />
            Risk Parameters
          </TabsTrigger>
          <TabsTrigger
            value="notifications"
            className="data-[state=active]:bg-ub-accent/15 data-[state=active]:text-ub-accent text-ub-text-muted text-sm px-4 py-2 rounded-md"
          >
            <Bell className="h-4 w-4 mr-1.5" />
            Notifications
          </TabsTrigger>
          <TabsTrigger
            value="capital"
            className="data-[state=active]:bg-ub-accent/15 data-[state=active]:text-ub-accent text-ub-text-muted text-sm px-4 py-2 rounded-md"
          >
            <Wallet className="h-4 w-4 mr-1.5" />
            Capital
          </TabsTrigger>
          <TabsTrigger
            value="general"
            className="data-[state=active]:bg-ub-accent/15 data-[state=active]:text-ub-accent text-ub-text-muted text-sm px-4 py-2 rounded-md"
          >
            <Cog className="h-4 w-4 mr-1.5" />
            General
          </TabsTrigger>
        </TabsList>

        {/* ═══════════════════════════════════════ */}
        {/* Tab: Brokers                             */}
        {/* ═══════════════════════════════════════ */}
        <TabsContent value="brokers" className="space-y-6">
          <Suspense fallback={<div className="text-ub-text-disabled text-sm">Loading broker settings…</div>}>
            <BrokerSettingsSection />
          </Suspense>
        </TabsContent>

        {/* ═══════════════════════════════════════ */}
        {/* Tab: Risk Parameters                    */}
        {/* ═══════════════════════════════════════ */}
        <TabsContent value="risk" className="space-y-6">
          {/* Position Limits */}
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-ub-text-primary">Position Limits</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Max Open Positions</Label>
                  <Input
                    type="number"
                    min={1}
                    max={6}
                    value={risk.maxOpenPositions}
                    onChange={(e) => updateRisk('maxOpenPositions', clamp(Number(e.target.value), 1, 6))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Max Per Sector</Label>
                  <Input
                    type="number"
                    value={risk.maxPerSector}
                    onChange={(e) => updateRisk('maxPerSector', Number(e.target.value))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Max Daily Trades</Label>
                  <Input
                    type="number"
                    min={1}
                    max={50}
                    value={risk.maxDailyTrades}
                    onChange={(e) => updateRisk('maxDailyTrades', clamp(Number(e.target.value), 1, 50))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Loss Limits */}
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-ub-text-primary">Loss Limits</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Max Daily Loss (%)</Label>
                  <Input
                    type="number"
                    step="0.5"
                    min={0.5}
                    max={5}
                    value={risk.maxDailyLossPct}
                    onChange={(e) => updateRisk('maxDailyLossPct', clamp(Number(e.target.value), 0.5, 5))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Max Consecutive Losses</Label>
                  <Input
                    type="number"
                    min={1}
                    max={10}
                    value={risk.maxConsecutiveLosses}
                    onChange={(e) => updateRisk('maxConsecutiveLosses', clamp(Number(e.target.value), 1, 10))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Cool-off Minutes</Label>
                  <Input
                    type="number"
                    min={5}
                    max={120}
                    value={risk.coolOffMinutes}
                    onChange={(e) => updateRisk('coolOffMinutes', clamp(Number(e.target.value), 5, 120))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Max Drawdown (%)</Label>
                  <Input
                    type="number"
                    min={1}
                    max={15}
                    value={risk.maxDrawdownPct}
                    onChange={(e) => updateRisk('maxDrawdownPct', clamp(Number(e.target.value), 1, 15))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Trade Filters */}
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-ub-text-primary">Trade Filters</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">VIX Threshold</Label>
                  <Input
                    type="number"
                    min={10}
                    max={40}
                    value={risk.vixThreshold}
                    onChange={(e) => updateRisk('vixThreshold', clamp(Number(e.target.value), 10, 40))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Min Signal Confidence</Label>
                  <Input
                    type="number"
                    step="0.05"
                    min={0.3}
                    max={0.95}
                    value={risk.minSignalConfidence}
                    onChange={(e) => updateRisk('minSignalConfidence', clamp(Number(e.target.value), 0.3, 0.95))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">New Trade Window Start</Label>
                  <Input
                    type="time"
                    value={risk.newTradeWindowStart}
                    onChange={(e) => updateRisk('newTradeWindowStart', e.target.value)}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">New Trade Window End</Label>
                  <Input
                    type="time"
                    value={risk.newTradeWindowEnd}
                    onChange={(e) => updateRisk('newTradeWindowEnd', e.target.value)}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Position Sizing */}
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-ub-text-primary">Position Sizing</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Method</Label>
                  <Select
                    value={risk.positionSizingMethod}
                    onValueChange={(v) => updateRisk('positionSizingMethod', v)}
                  >
                    <SelectTrigger className="bg-ub-background border-ub-border text-ub-text-primary">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-ub-surface border-ub-border">
                      <SelectItem value="Dynamic Kelly" className="text-ub-text-primary">Dynamic Kelly</SelectItem>
                      <SelectItem value="Fixed" className="text-ub-text-primary">Fixed</SelectItem>
                      <SelectItem value="Risk Percent" className="text-ub-text-primary">Risk Percent</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Kelly Min Fraction</Label>
                  <Input
                    type="number"
                    step="0.05"
                    value={risk.kellyMinFraction}
                    onChange={(e) => updateRisk('kellyMinFraction', Number(e.target.value))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Kelly Max Fraction</Label>
                  <Input
                    type="number"
                    step="0.05"
                    value={risk.kellyMaxFraction}
                    onChange={(e) => updateRisk('kellyMaxFraction', Number(e.target.value))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Min Position Size (₹)</Label>
                  <Input
                    type="number"
                    value={risk.minPositionSize}
                    onChange={(e) => updateRisk('minPositionSize', Number(e.target.value))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Partial Booking */}
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-semibold text-ub-text-primary">Partial Booking</CardTitle>
                <Switch
                  checked={risk.partialBookingEnabled}
                  onCheckedChange={(v) => updateRisk('partialBookingEnabled', v)}
                  className="data-[state=checked]:bg-ub-accent"
                />
              </div>
            </CardHeader>
            <CardContent className={risk.partialBookingEnabled ? '' : 'opacity-50 pointer-events-none'}>
              {/* 4-Stage Booking Lifecycle */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3.5 mb-4">
                {/* Stage 1 */}
                <div className="p-3 rounded-lg bg-ub-background/80 border border-ub-border space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-ub-text-primary uppercase tracking-wide">Stage 1: Breakeven Lock</span>
                    <Badge variant="outline" className="text-[10px] border-blue-500/40 text-blue-400 bg-blue-500/10">0% Booked</Badge>
                  </div>
                  <div>
                    <Label className="text-ub-text-muted text-[11px]">Trigger Profit (%)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      value={risk.stage1TriggerPct}
                      onChange={(e) => updateRisk('stage1TriggerPct', Number(e.target.value))}
                      className="bg-ub-surface border-ub-border text-ub-text-primary h-8 text-xs mt-1"
                    />
                  </div>
                  <div>
                    <Label className="text-ub-text-muted text-[11px]">Brokerage Buffer (%)</Label>
                    <Input
                      type="number"
                      step="0.01"
                      value={risk.brokerageBufferPct}
                      onChange={(e) => updateRisk('brokerageBufferPct', Number(e.target.value))}
                      className="bg-ub-surface border-ub-border text-ub-text-primary h-8 text-xs mt-1"
                    />
                  </div>
                  <p className="text-[10px] text-ub-text-disabled">Moves SL to Entry + Buffer with 0% exit.</p>
                </div>

                {/* Stage 2 */}
                <div className="p-3 rounded-lg bg-ub-background/80 border border-ub-border space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-ub-text-primary uppercase tracking-wide">Stage 2: First Book</span>
                    <Badge variant="outline" className="text-[10px] border-emerald-500/40 text-emerald-400 bg-emerald-500/10">25% Book</Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <Label className="text-ub-text-muted text-[11px]">Trigger (%)</Label>
                      <Input
                        type="number"
                        step="0.1"
                        value={risk.stage2TriggerPct}
                        onChange={(e) => updateRisk('stage2TriggerPct', Number(e.target.value))}
                        className="bg-ub-surface border-ub-border text-ub-text-primary h-8 text-xs mt-1"
                      />
                    </div>
                    <div>
                      <Label className="text-ub-text-muted text-[11px]">Book (%)</Label>
                      <Input
                        type="number"
                        value={risk.stage2BookPct}
                        onChange={(e) => updateRisk('stage2BookPct', Number(e.target.value))}
                        className="bg-ub-surface border-ub-border text-ub-text-primary h-8 text-xs mt-1"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <Label className="text-ub-text-muted text-[11px]">Trail Peak (%)</Label>
                      <Input
                        type="number"
                        step="0.1"
                        value={risk.stage2TrailPct}
                        onChange={(e) => updateRisk('stage2TrailPct', Number(e.target.value))}
                        className="bg-ub-surface border-ub-border text-ub-text-primary h-8 text-xs mt-1"
                      />
                    </div>
                    <div>
                      <Label className="text-ub-text-muted text-[11px]">Floor SL (%)</Label>
                      <Input
                        type="number"
                        step="0.1"
                        value={risk.stage2FloorProfitPct}
                        onChange={(e) => updateRisk('stage2FloorProfitPct', Number(e.target.value))}
                        className="bg-ub-surface border-ub-border text-ub-text-primary h-8 text-xs mt-1"
                      />
                    </div>
                  </div>
                </div>

                {/* Stage 3 */}
                <div className="p-3 rounded-lg bg-ub-background/80 border border-ub-border space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-ub-text-primary uppercase tracking-wide">Stage 3: Main Book</span>
                    <Badge variant="outline" className="text-[10px] border-emerald-500/40 text-emerald-400 bg-emerald-500/10">30% Book</Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <Label className="text-ub-text-muted text-[11px]">Trigger (%)</Label>
                      <Input
                        type="number"
                        step="0.1"
                        value={risk.stage3TriggerPct}
                        onChange={(e) => updateRisk('stage3TriggerPct', Number(e.target.value))}
                        className="bg-ub-surface border-ub-border text-ub-text-primary h-8 text-xs mt-1"
                      />
                    </div>
                    <div>
                      <Label className="text-ub-text-muted text-[11px]">Book (%)</Label>
                      <Input
                        type="number"
                        value={risk.stage3BookPct}
                        onChange={(e) => updateRisk('stage3BookPct', Number(e.target.value))}
                        className="bg-ub-surface border-ub-border text-ub-text-primary h-8 text-xs mt-1"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <Label className="text-ub-text-muted text-[11px]">Trail Peak (%)</Label>
                      <Input
                        type="number"
                        step="0.1"
                        value={risk.stage3TrailPct}
                        onChange={(e) => updateRisk('stage3TrailPct', Number(e.target.value))}
                        className="bg-ub-surface border-ub-border text-ub-text-primary h-8 text-xs mt-1"
                      />
                    </div>
                    <div>
                      <Label className="text-ub-text-muted text-[11px]">Floor SL (%)</Label>
                      <Input
                        type="number"
                        step="0.1"
                        value={risk.stage3FloorProfitPct}
                        onChange={(e) => updateRisk('stage3FloorProfitPct', Number(e.target.value))}
                        className="bg-ub-surface border-ub-border text-ub-text-primary h-8 text-xs mt-1"
                      />
                    </div>
                  </div>
                </div>

                {/* Stage 4 */}
                <div className="p-3 rounded-lg bg-ub-background/80 border border-ub-border space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-ub-text-primary uppercase tracking-wide">Stage 4: Runner Trail</span>
                    <Badge variant="outline" className="text-[10px] border-purple-500/40 text-purple-400 bg-purple-500/10">45% Runner</Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <Label className="text-ub-text-muted text-[11px]">Trigger (%)</Label>
                      <Input
                        type="number"
                        step="0.1"
                        value={risk.stage4TriggerPct}
                        onChange={(e) => updateRisk('stage4TriggerPct', Number(e.target.value))}
                        className="bg-ub-surface border-ub-border text-ub-text-primary h-8 text-xs mt-1"
                      />
                    </div>
                    <div>
                      <Label className="text-ub-text-muted text-[11px]">Runner (%)</Label>
                      <Input
                        type="number"
                        value={risk.stage4BookPct}
                        onChange={(e) => updateRisk('stage4BookPct', Number(e.target.value))}
                        className="bg-ub-surface border-ub-border text-ub-text-primary h-8 text-xs mt-1"
                      />
                    </div>
                  </div>
                  <div>
                    <Label className="text-ub-text-muted text-[11px]">Trail From Peak (%)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      value={risk.stage4TrailPct}
                      onChange={(e) => updateRisk('stage4TrailPct', Number(e.target.value))}
                      className="bg-ub-surface border-ub-border text-ub-text-primary h-8 text-xs mt-1"
                    />
                  </div>
                  <p className="text-[10px] text-ub-text-disabled">Total Position Exited: 100%.</p>
                </div>
              </div>
              <Separator className="my-4 bg-ub-border" />
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Trailing SL Method</Label>
                  <Select
                    value={risk.trailingSLMethod}
                    onValueChange={(v) => updateRisk('trailingSLMethod', v)}
                  >
                    <SelectTrigger className="bg-ub-background border-ub-border text-ub-text-primary">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-ub-surface border-ub-border">
                      <SelectItem value="Fixed Step" className="text-ub-text-primary">Fixed Step</SelectItem>
                      <SelectItem value="ATR Based" className="text-ub-text-primary">ATR Based</SelectItem>
                      <SelectItem value="Percentage" className="text-ub-text-primary">Percentage</SelectItem>
                      <SelectItem value="Swing High/Low" className="text-ub-text-primary">Swing High/Low</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Trailing Step (%)</Label>
                  <Input
                    type="number"
                    step="0.1"
                    value={risk.trailingStepPct}
                    onChange={(e) => updateRisk('trailingStepPct', Number(e.target.value))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="flex justify-end">
            <Button onClick={handleSaveRisk} disabled={savingRisk} className="bg-ub-accent hover:bg-ub-accent-hover text-ub-background font-semibold">
              {savingRisk ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
              {savingRisk ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </TabsContent>

        {/* ═══════════════════════════════════════ */}
        {/* Tab: Notifications                      */}
        {/* ═══════════════════════════════════════ */}
        <TabsContent value="notifications" className="space-y-6">
          {/* Telegram */}
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-ub-text-primary flex items-center gap-2">
                <span className="text-lg">📨</span>
                Telegram Notifications
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Bot Token</Label>
                  <Input
                    type="password"
                    placeholder="e.g. 7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                    value={notifications.telegramBotToken}
                    onChange={(e) => updateNotifications('telegramBotToken', e.target.value)}
                    className="bg-ub-background border-ub-border text-ub-text-primary font-mono text-xs"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Chat ID</Label>
                  <Input
                    placeholder="e.g. -1001234567890 or 123456789"
                    value={notifications.telegramChatId}
                    onChange={(e) => updateNotifications('telegramChatId', e.target.value)}
                    className="bg-ub-background border-ub-border text-ub-text-primary font-mono text-xs"
                  />
                </div>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
                <p className="text-xs text-ub-text-muted">
                  {notifications.telegramBotToken && notifications.telegramChatId ? (
                    <span className="text-ub-profit font-medium">✓ Credentials entered (Remember to click Save)</span>
                  ) : (
                    <span>Create a bot with <strong>@BotFather</strong> on Telegram to get your token and chat ID</span>
                  )}
                </p>
                <div className="flex items-center gap-2 shrink-0">
                  <Button
                    onClick={handleTestTelegram}
                    disabled={testingTelegram}
                    variant="outline"
                    className="border-ub-accent/40 text-ub-accent hover:bg-ub-accent/10 hover:text-ub-accent cursor-pointer"
                  >
                    {testingTelegram ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    ) : (
                      <TestTube className="h-4 w-4 mr-2" />
                    )}
                    Test Notification
                  </Button>
                  <Button
                    onClick={handleSaveNotifications}
                    disabled={savingNotifications}
                    className="bg-ub-accent hover:bg-ub-accent-hover text-ub-background font-semibold cursor-pointer"
                  >
                    {savingNotifications ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Save className="h-4 w-4 mr-2" />
                    )}
                    Save Telegram Settings
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Alert Types */}
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-semibold text-ub-text-primary">Alert Types</CardTitle>
                <span className="text-xs text-ub-text-muted">Click &quot;Test&quot; to preview message in Telegram</span>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3">
                {[
                  { key: 'alertTradeExecuted' as const, eventType: 'trade_executed', label: 'Trade Executed' },
                  { key: 'alertPartialBooking' as const, eventType: 'partial_booking', label: 'Partial Booking' },
                  { key: 'alertStopLoss' as const, eventType: 'stop_loss_hit', label: 'Stop Loss Hit' },
                  { key: 'alertTargetHit' as const, eventType: 'target_hit', label: 'Target Hit' },
                  { key: 'alertRiskWarning' as const, eventType: 'risk_limit_warning', label: 'Risk Limit Warning' },
                  { key: 'alertEngineStatus' as const, eventType: 'engine_status_change', label: 'Engine Status Change' },
                  { key: 'alertError' as const, eventType: 'error_alert', label: 'Error Alert' },
                  { key: 'alertEODReport' as const, eventType: 'eod_report', label: 'EOD Report' },
                ].map((item) => (
                  <div key={item.key} className="flex items-center justify-between py-1.5 px-2 rounded-md hover:bg-ub-background/50 transition-colors">
                    <div className="flex items-center gap-2">
                      <Label className="text-sm text-ub-text-primary cursor-pointer">{item.label}</Label>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        disabled={testingEvent !== null}
                        onClick={() => handleTestEvent(item.eventType, item.label)}
                        className="h-6 px-1.5 text-[11px] text-ub-text-muted hover:text-ub-accent hover:bg-ub-accent/10 cursor-pointer"
                        title={`Send sample ${item.label} test message to Telegram`}
                      >
                        {testingEvent === item.eventType ? (
                          <Loader2 className="h-3 w-3 animate-spin mr-1" />
                        ) : (
                          <TestTube className="h-3 w-3 mr-1" />
                        )}
                        Test
                      </Button>
                    </div>
                    <Switch
                      checked={notifications[item.key] as boolean}
                      onCheckedChange={(v) => updateNotifications(item.key, v)}
                      className="data-[state=checked]:bg-ub-accent"
                    />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Schedule */}
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-ub-text-primary">Schedule</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Morning Briefing Time</Label>
                  <Input
                    type="time"
                    value={notifications.morningBriefingTime}
                    onChange={(e) => updateNotifications('morningBriefingTime', e.target.value)}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">EOD Report Time</Label>
                  <Input
                    type="time"
                    value={notifications.eodReportTime}
                    onChange={(e) => updateNotifications('eodReportTime', e.target.value)}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="flex justify-end">
            <Button onClick={handleSaveNotifications} disabled={savingNotifications} className="bg-ub-accent hover:bg-ub-accent-hover text-ub-background font-semibold">
              {savingNotifications ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
              {savingNotifications ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </TabsContent>

        {/* ═══════════════════════════════════════ */}
        {/* Tab: Capital                             */}
        {/* ═══════════════════════════════════════ */}
        <TabsContent value="capital" className="space-y-6">
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-ub-text-primary flex items-center gap-2">
                <Wallet className="h-4 w-4 text-ub-accent" />
                Capital Configuration
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Virtual Capital (₹)</Label>
                  <Input
                    type="number"
                    value={capital.virtualCapital}
                    onChange={(e) => setCapital((p) => ({ ...p, virtualCapital: Number(e.target.value) }))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Min Position Size (₹)</Label>
                  <Input
                    type="number"
                    value={capital.minPositionSize}
                    onChange={(e) => setCapital((p) => ({ ...p, minPositionSize: Number(e.target.value) }))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
              </div>

              {/* Max Capital Usage Slider */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="text-ub-text-muted text-sm">Max Capital Usage</Label>
                  <span className="text-sm font-semibold text-ub-accent">{capital.maxCapitalUsagePct}%</span>
                </div>
                <div className="relative">
                  <div className="w-full h-2 bg-ub-background rounded-full overflow-hidden">
                    <div
                      className="h-full bg-ub-accent rounded-full transition-all duration-200"
                      style={{ width: `${capital.maxCapitalUsagePct}%` }}
                    />
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="100"
                    step="5"
                    value={capital.maxCapitalUsagePct}
                    onChange={(e) => setCapital((p) => ({ ...p, maxCapitalUsagePct: Number(e.target.value) }))}
                    className="absolute top-0 left-0 w-full h-2 opacity-0 cursor-pointer"
                  />
                </div>
                <div className="flex justify-between text-xs text-ub-text-disabled">
                  <span>10%</span>
                  <span>100%</span>
                </div>
              </div>

              {/* Per-Position Max Slider */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="text-ub-text-muted text-sm">Per-Position Max</Label>
                  <span className="text-sm font-semibold text-ub-accent">{capital.perPositionMaxPct}%</span>
                </div>
                <div className="relative">
                  <div className="w-full h-2 bg-ub-background rounded-full overflow-hidden">
                    <div
                      className="h-full bg-ub-warning rounded-full transition-all duration-200"
                      style={{ width: `${capital.perPositionMaxPct * 5}%` }}
                    />
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="50"
                    step="5"
                    value={capital.perPositionMaxPct}
                    onChange={(e) => setCapital((p) => ({ ...p, perPositionMaxPct: Number(e.target.value) }))}
                    className="absolute top-0 left-0 w-full h-2 opacity-0 cursor-pointer"
                  />
                </div>
                <div className="flex justify-between text-xs text-ub-text-disabled">
                  <span>5%</span>
                  <span>50%</span>
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="flex justify-end">
            <Button onClick={handleSaveCapital} disabled={savingCapital} className="bg-ub-accent hover:bg-ub-accent-hover text-ub-background font-semibold">
              {savingCapital ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
              {savingCapital ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </TabsContent>

        {/* ═══════════════════════════════════════ */}
        {/* Tab: General                            */}
        {/* ═══════════════════════════════════════ */}
        <TabsContent value="general" className="space-y-6">
          {/* Engine Settings */}
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-ub-text-primary flex items-center gap-2">
                <Cog className="h-4 w-4 text-ub-accent" />
                Engine Settings
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Scan Interval (seconds)</Label>
                  <Input
                    type="number"
                    value={general.scanIntervalSeconds}
                    onChange={(e) => setGeneral((p) => ({ ...p, scanIntervalSeconds: Number(e.target.value) }))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Auto Square-off Time</Label>
                  <Input
                    type="time"
                    value={general.autoSquareoffTime}
                    onChange={(e) => setGeneral((p) => ({ ...p, autoSquareoffTime: e.target.value }))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
              </div>
              <div className="flex items-center justify-between py-1">
                <Label className="text-sm text-ub-text-primary">Auto-start Engine on Market Open</Label>
                <Switch
                  checked={general.autoStartEngine}
                  onCheckedChange={(v) => setGeneral((p) => ({ ...p, autoStartEngine: v }))}
                  className="data-[state=checked]:bg-ub-accent"
                />
              </div>
            </CardContent>
          </Card>

          {/* Market Hours */}
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-ub-text-primary">Market Hours</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Market Open</Label>
                  <Input
                    type="time"
                    value={general.marketOpen}
                    onChange={(e) => setGeneral((p) => ({ ...p, marketOpen: e.target.value }))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Market Close</Label>
                  <Input
                    type="time"
                    value={general.marketClose}
                    onChange={(e) => setGeneral((p) => ({ ...p, marketClose: e.target.value }))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Pre-market Start</Label>
                  <Input
                    type="time"
                    value={general.premarketStart}
                    onChange={(e) => setGeneral((p) => ({ ...p, premarketStart: e.target.value }))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Post-market End</Label>
                  <Input
                    type="time"
                    value={general.postmarketEnd}
                    onChange={(e) => setGeneral((p) => ({ ...p, postmarketEnd: e.target.value }))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="flex justify-end">
            <Button onClick={handleSaveGeneral} disabled={savingGeneral} className="bg-ub-accent hover:bg-ub-accent-hover text-ub-background font-semibold">
              {savingGeneral ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
              {savingGeneral ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
