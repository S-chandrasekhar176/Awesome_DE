'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import Link from 'next/link';
import {
  TrendingUp,
  TrendingDown,
  Activity,
  ShieldAlert,
  Play,
  Square,
  Clock,
  Zap,
  ArrowUpRight,
  ArrowDownRight,
  BarChart3,
  Radio,
  SignalHigh,
  Eye,
  AlertTriangle,
  Power,
  Wifi,
  Timer,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useDashboard, useStrategies } from '@/hooks/useApi';
import { useEngine } from '@/hooks/useEngine';
import { useEngine as useEngineStore, useStore, type MarketRegime, BROKER_LIST } from '@/lib/store';
import StartEngineDialog from '@/components/trading/StartEngineDialog';
import ScanTelemetryCard from '@/components/trading/ScanTelemetryCard';
import {
  getStoredPositions,
  getStoredTradeHistory,
  getConfirmedOppIds,
  getSkippedOppIds,
  updateStoredPositionsWithLivePrices,
  checkAndAutoSquareoffPositions,
  Position as StoredPosition,
  TradeHistoryItem,
} from '@/lib/tradeExecution';

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

interface Position {
  id: string;
  symbol: string;
  direction: 'BUY' | 'SELL';
  entry: number;
  current: number;
  qty: number;
  pnl: number;
  bookedLevels: number[];
}

interface Trade {
  id: string;
  time: string;
  symbol: string;
  direction: 'BUY' | 'SELL';
  pnl: number;
}

interface DashboardData {
  todayPnl: number;
  todayPnlPercent: number;
  activePositions: number;
  longCount: number;
  shortCount: number;
  winRate: number;
  totalTradesCount: number;
  winningTradesCount: number;
  todayWinRate: number;
  todayTradesCount: number;
  todayWinningTradesCount: number;
  hasTradeHistory: boolean;
  riskUsed: number;
  totalCapital: number;
  capitalUsed: number;
  freeCapital: number;
  dayPnl: number;
  totalPnl: number;
  positions: Position[];
  recentTrades: Trade[];
  engineStatus: string;
  engineMode: string;
  regime: MarketRegime;
  regimeConfidence: number;
  activeStrategies: string[];
  signalsGenerated: number;
  signalsConfirmed: number;
  signalsSkipped: number;
}

// ─────────────────────────────────────────────
// Indian Number Formatting
// ─────────────────────────────────────────────

function formatINR(value: number): string {
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  const parts = abs.toFixed(2).split('.');
  const intPart = parts[0];
  const decPart = parts[1];
  let formatted = '';
  if (intPart.length <= 3) {
    formatted = intPart;
  } else {
    const last3 = intPart.slice(-3);
    const rest = intPart.slice(0, -3);
    formatted = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' + last3;
  }
  return `₹${sign}${formatted}.${decPart}`;
}

function formatPercent(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

// ─────────────────────────────────────────────
// Circular Progress (SVG)
// ─────────────────────────────────────────────

function CircularProgress({ value, size = 64, strokeWidth = 5, color = '#00d09c' }: {
  value: number;
  size?: number;
  strokeWidth?: number;
  color?: string;
}) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;

  return (
    <svg width={size} height={size} className="-rotate-90">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="#1e293b"
        strokeWidth={strokeWidth}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        className="transition-all duration-700 ease-out"
      />
      <text
        x={size / 2}
        y={size / 2}
        className="fill-ub-text-primary text-xs font-bold"
        textAnchor="middle"
        dominantBaseline="central"
        transform={`rotate(90, ${size / 2}, ${size / 2})`}
      >
        {value.toFixed(0)}%
      </text>
    </svg>
  );
}

// ─────────────────────────────────────────────
// Risk Bar Color Helper
// ─────────────────────────────────────────────

function getRiskColor(pct: number): string {
  if (pct < 50) return '#22c55e';
  if (pct <= 80) return '#f59e0b';
  return '#ef4444';
}

function getRiskLabel(pct: number): string {
  if (pct < 50) return 'Low';
  if (pct <= 80) return 'Medium';
  return 'High';
}

// ─────────────────────────────────────────────
// Regime Config
// ─────────────────────────────────────────────

const REGIME_CONFIG: Record<MarketRegime, { label: string; colorClass: string; bgClass: string; borderClass: string }> = {
  bull: {
    label: 'Bull',
    colorClass: 'text-ub-bull',
    bgClass: 'bg-ub-bull/15',
    borderClass: 'border-ub-bull/30',
  },
  bear: {
    label: 'Bear',
    colorClass: 'text-ub-bear',
    bgClass: 'bg-ub-bear/15',
    borderClass: 'border-ub-bear/30',
  },
  sideways: {
    label: 'Sideways',
    colorClass: 'text-ub-sideways',
    bgClass: 'bg-ub-sideways/15',
    borderClass: 'border-ub-sideways/30',
  },
  volatile: {
    label: 'Volatile',
    colorClass: 'text-ub-volatile',
    bgClass: 'bg-ub-volatile/15',
    borderClass: 'border-ub-volatile/30',
  },
};

// ─────────────────────────────────────────────
// Uptime Ticker
// ─────────────────────────────────────────────

function UptimeTicker({ startedAt }: { startedAt: number | null }) {
  const [uptime, setUptime] = useState('00:00:00');

  useEffect(() => {
    if (!startedAt) { setUptime('00:00:00'); return; }
    const tick = () => {
      const diff = Math.floor((Date.now() - startedAt) / 1000);
      const h = String(Math.floor(diff / 3600)).padStart(2, '0');
      const m = String(Math.floor((diff % 3600) / 60)).padStart(2, '0');
      const s = String(diff % 60).padStart(2, '0');
      setUptime(`${h}:${m}:${s}`);
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [startedAt]);

  return (
    <span className="font-mono text-xs" style={{ color: '#00D09C' }}>
      {uptime}
    </span>
  );
}

// ─────────────────────────────────────────────
// Skeleton Loaders
// ─────────────────────────────────────────────

function StatsRowSkeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <Card key={i} className="bg-ub-surface border-ub-border rounded-lg">
          <CardContent className="p-4 space-y-3">
            <Skeleton className="h-4 w-28 bg-ub-border" />
            <Skeleton className="h-8 w-32 bg-ub-border" />
            <Skeleton className="h-3 w-20 bg-ub-border" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function MainContentSkeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
      <div className="lg:col-span-3 space-y-4">
        <Card className="bg-ub-surface border-ub-border rounded-lg">
          <CardContent className="p-4 space-y-3">
            <Skeleton className="h-5 w-32 bg-ub-border" />
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-4 w-full bg-ub-border" />
            ))}
          </CardContent>
        </Card>
        <Card className="bg-ub-surface border-ub-border rounded-lg">
          <CardContent className="p-4 space-y-3">
            <Skeleton className="h-5 w-36 bg-ub-border" />
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full bg-ub-border" />
            ))}
          </CardContent>
        </Card>
      </div>
      <div className="lg:col-span-2 space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="bg-ub-surface border-ub-border rounded-lg">
            <CardContent className="p-4 space-y-3">
              <Skeleton className="h-5 w-28 bg-ub-border" />
              <Skeleton className="h-4 w-20 bg-ub-border" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Market Timer Component
// ─────────────────────────────────────────────

function MarketTimer() {
  const [now, setNow] = useState(() => new Date());
  const engine = useEngineStore();

  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 1_000);
    return () => clearInterval(interval);
  }, []);

  const istString = now.toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  let marketCloseSeconds = engine.marketCloseSeconds;
  if (!marketCloseSeconds) {
    const istNow = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
    const isWeekday = istNow.getDay() >= 1 && istNow.getDay() <= 5;
    const sec = istNow.getHours() * 3600 + istNow.getMinutes() * 60 + istNow.getSeconds();
    const openSec = 9 * 3600 + 15 * 60; // 09:15
    const closeSec = 15 * 3600 + 30 * 60; // 15:30
    if (isWeekday && sec >= openSec && sec < closeSec) {
      marketCloseSeconds = closeSec - sec;
    }
  }

  const hours = Math.floor(marketCloseSeconds / 3600);
  const minutes = Math.floor((marketCloseSeconds % 3600) / 60);
  const seconds = Math.floor(marketCloseSeconds % 60);
  const pad = (n: number) => String(n).padStart(2, '0');
  const timeToClose = marketCloseSeconds > 0
    ? `Closes in ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`
    : 'Market Closed';

  const isUrgent = marketCloseSeconds > 0 && marketCloseSeconds < 1800;

  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="flex items-center gap-1.5 font-mono">
        <Clock className="h-3.5 w-3.5 text-ub-text-muted" />
        <span className="font-bold text-ub-text-primary tracking-wide">
          {istString}
        </span>
        <Badge variant="outline" className="text-[9px] font-semibold border-ub-border/80 text-ub-text-muted px-1.5 py-0 h-4 leading-none">
          IST
        </Badge>
      </div>
      <span className="text-ub-border/60">•</span>
      <span className={`text-[11px] font-medium ${
        marketCloseSeconds > 0
          ? isUrgent
            ? 'text-ub-warning font-mono font-semibold'
            : 'text-ub-text-muted font-mono'
          : 'text-ub-text-disabled'
      }`}>
        {timeToClose}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────
// Stat Card Component
// ─────────────────────────────────────────────

function StatCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="bg-ub-surface border-ub-border rounded-lg">
      <CardContent className="p-4">
        <p className="text-xs font-medium text-ub-text-muted uppercase tracking-wider mb-2">
          {title}
        </p>
        {children}
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────
// Dashboard Section Card
// ─────────────────────────────────────────────

function SectionCard({ title, icon: Icon, headerRight, children, className = '' }: {
  title: string;
  icon: React.ElementType;
  headerRight?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={`bg-ub-surface border-ub-border rounded-lg ${className}`}>
      <CardHeader className="pb-3 pt-4 px-4 flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-sm font-semibold text-ub-text-primary flex items-center gap-2">
          <Icon className="h-4 w-4 text-ub-accent" />
          {title}
        </CardTitle>
        {headerRight}
      </CardHeader>
      <CardContent className="px-4 pb-4 pt-0">
        {children}
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────
// MAIN DASHBOARD
// ─────────────────────────────────────────────

export default function DashboardPage() {
  const { data: apiData, isLoading } = useDashboard();
  const { data: stratData } = useStrategies();
  const engine = useEngine();
  const engineStore = useEngineStore();

  const [storedPositions, setStoredPositions] = useState<StoredPosition[]>([]);
  const [storedTrades, setStoredTrades] = useState<TradeHistoryItem[]>([]);
  const [confirmedIds, setConfirmedIds] = useState<string[]>([]);
  const [skippedIds, setSkippedIds] = useState<string[]>([]);

  // Load client-side paper positions, trades, and opportunities
  const refreshStorage = useCallback(() => {
    checkAndAutoSquareoffPositions();
    setStoredPositions(getStoredPositions());
    setStoredTrades(getStoredTradeHistory());
    setConfirmedIds(getConfirmedOppIds());
    setSkippedIds(getSkippedOppIds());
  }, []);

  useEffect(() => {
    refreshStorage();
    window.addEventListener('ultrabot_positions_updated', refreshStorage);
    window.addEventListener('ultrabot_trades_updated', refreshStorage);
    window.addEventListener('ultrabot_opportunities_updated', refreshStorage);
    return () => {
      window.removeEventListener('ultrabot_positions_updated', refreshStorage);
      window.removeEventListener('ultrabot_trades_updated', refreshStorage);
      window.removeEventListener('ultrabot_opportunities_updated', refreshStorage);
    };
  }, [refreshStorage]);

  // Live quotes polling for open positions
  useEffect(() => {
    const pollQuotes = async () => {
      checkAndAutoSquareoffPositions();
      const positions = getStoredPositions();
      if (positions.length === 0) {
        setStoredPositions([]);
        return;
      }
      const symbols = Array.from(new Set(positions.map((p) => p.symbol)));
      try {
        const res = await fetch(`/api/live-quotes?symbols=${symbols.join(',')}`);
        if (res.ok) {
          const json = await res.json();
          if (json.success && json.data) {
            const updated = updateStoredPositionsWithLivePrices(json.data);
            setStoredPositions(updated);
          }
        }
      } catch { }
    };

    pollQuotes();
    const interval = setInterval(pollQuotes, 4000);
    return () => clearInterval(interval);
  }, []);

  const [configuredCapital, setConfiguredCapital] = useState<number>(0);

  useEffect(() => {
    const loadCapital = () => {
      try {
        if (typeof window !== 'undefined') {
          const saved = localStorage.getItem('ultrabot_settings_capital');
          if (saved) {
            const parsed = JSON.parse(saved);
            if (typeof parsed.virtualCapital === 'number' && parsed.virtualCapital > 0) {
              setConfiguredCapital(parsed.virtualCapital);
              return;
            }
          }
        }
      } catch { }

      fetch('/api/settings')
        .then((r) => r.json())
        .then((d) => {
          if (d?.config?.capital?.virtual_capital) {
            setConfiguredCapital(d.config.capital.virtual_capital);
          }
        })
        .catch(() => { });
    };

    loadCapital();
    if (typeof window !== 'undefined') {
      window.addEventListener('storage', loadCapital);
      return () => window.removeEventListener('storage', loadCapital);
    }
  }, []);

  useEffect(() => {
    if (!apiData) return;
    const raw = apiData as Record<string, any>;
    if (typeof raw.vix === 'number' && raw.vix > 0) engineStore.setVix(raw.vix);
    if (typeof raw.nifty_price === 'number' && raw.nifty_price > 0) {
      engineStore.setNifty(raw.nifty_price, raw.nifty_change || -0.29);
    }
    if (raw.regime) engineStore.setRegime((raw.regime as string).toLowerCase() as MarketRegime);
    if (raw.market && typeof raw.market.time_to_close_seconds === 'number') {
      engineStore.setMarketCloseSeconds(raw.market.time_to_close_seconds);
    }
  }, [apiData]);

  // Merge API data with live stored positions and trade history
  const data: DashboardData = useMemo(() => {
    const raw = apiData as Record<string, any> | undefined;

    // 1. Positions (prefer stored paper positions if present)
    const positionsList: Position[] = (storedPositions.length > 0
      ? storedPositions.map((p) => ({
        id: p.id,
        symbol: p.symbol,
        direction: p.direction,
        entry: p.entry,
        current: p.current || p.entry,
        qty: p.remainingQty || p.quantity,
        pnl: p.unrealizedPnl || 0,
        bookedLevels: p.bookedLevels ? p.bookedLevels.filter((b) => b.achieved).map((b) => b.level) : [],
      }))
      : (Array.isArray(raw?.positions) ? raw.positions : [])) as Position[];

    // 2. Trades
    const tradesList: Trade[] = (storedTrades.length > 0
      ? storedTrades.map((t) => ({
        id: t.id,
        time: t.exitedAt ? new Date(t.exitedAt).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : 'Today',
        symbol: t.symbol,
        direction: t.direction,
        pnl: t.pnl,
      }))
      : (Array.isArray(raw?.recentTrades) ? raw.recentTrades : [])) as Trade[];

    // 3. Active Positions Counts & P&L
    const activePositions = positionsList.length;
    const longCount = positionsList.filter((p) => p.direction === 'BUY').length;
    const shortCount = positionsList.filter((p) => p.direction === 'SELL').length;

    const unrealizedPnl = positionsList.reduce((sum, p) => sum + p.pnl, 0);
    const realizedPnl = tradesList.reduce((sum, t) => sum + t.pnl, 0);
    const todayPnl = +(unrealizedPnl + realizedPnl).toFixed(2);

    // 4. Capital Calculations
    const totalCapital = configuredCapital > 0
      ? configuredCapital
      : typeof raw?.total_capital === 'number' && raw.total_capital > 0
        ? raw.total_capital
        : typeof raw?.totalCapital === 'number' && raw.totalCapital > 0
          ? raw.totalCapital
          : 1000000.0;

    const capitalUsed = +(positionsList.reduce((sum, p) => sum + (p.entry * p.qty * 0.2), 0)).toFixed(2);
    const freeCapital = +(totalCapital - capitalUsed + todayPnl).toFixed(2);
    const todayPnlPercent = totalCapital > 0 ? +((todayPnl / totalCapital) * 100).toFixed(2) : 0;

    // 5. Dynamic Win Rate Engine (Evaluates every trade on every day)
    const totalTradesCount = storedTrades.length;
    const winningTradesCount = storedTrades.filter((t) => t.pnl > 0).length;
    const allTimeWinRate = totalTradesCount > 0 ? Math.round((winningTradesCount / totalTradesCount) * 100) : 0;

    const istDateFormatter = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' });
    const todayDateStr = istDateFormatter.format(new Date());
    const todayTrades = storedTrades.filter((t) => {
      if (!t.exitedAt) return true;
      try {
        return istDateFormatter.format(new Date(t.exitedAt)) === todayDateStr;
      } catch {
        return false;
      }
    });
    const todayTradesCount = todayTrades.length;
    const todayWinningTradesCount = todayTrades.filter((t) => t.pnl > 0).length;
    const todayWinRate = todayTradesCount > 0 ? Math.round((todayWinningTradesCount / todayTradesCount) * 100) : allTimeWinRate;

    const hasExecutedTrades = totalTradesCount > 0;
    const hasOpenPositions = positionsList.length > 0;
    const hasTradeHistory = hasExecutedTrades || hasOpenPositions;

    let winRate = allTimeWinRate;
    if (totalTradesCount === 0 && hasOpenPositions) {
      const positive = positionsList.filter((p) => p.pnl > 0).length;
      winRate = Math.round((positive / positionsList.length) * 100);
    }

    // 6. Risk Used
    const riskUsed = capitalUsed > 0 ? Math.min(100, Math.max(8, Math.round((capitalUsed / totalCapital) * 100 * 2.5))) : 0;

    // 7. Signals counts
    const signalsConfirmed = confirmedIds.length || (raw?.signalsConfirmed as number) || (raw?.signals_confirmed as number) || 0;
    const signalsSkipped = skippedIds.length || (raw?.signalsSkipped as number) || (raw?.signals_skipped as number) || 0;
    const signalsGenerated = typeof raw?.signalsGenerated === 'number'
      ? raw.signalsGenerated
      : typeof raw?.signals_generated === 'number'
        ? raw.signals_generated
        : (signalsConfirmed + signalsSkipped);

    const activeStrats = (raw?.active_strategies || raw?.activeStrategies) as string[] | undefined;
    const stratNamesFromApi = Array.isArray(stratData)
      ? stratData.filter((s: any) => s.is_active || s.active || s.enabled).map((s: any) => s.name || s.id)
      : [];
    const activeStrategies = (Array.isArray(activeStrats) && activeStrats.length > 0)
      ? activeStrats
      : stratNamesFromApi.length > 0
        ? stratNamesFromApi
        : (Array.isArray(stratData) ? stratData.map((s: any) => s.name || s.id).slice(0, 4) : []);

    const regConf = (raw?.regime_confidence || raw?.regimeConfidence || (typeof raw?.confidence === 'number' ? Math.round(raw.confidence * 100) : 0)) as number;

    return {
      todayPnl,
      todayPnlPercent,
      activePositions,
      longCount,
      shortCount,
      winRate,
      totalTradesCount,
      winningTradesCount,
      todayWinRate,
      todayTradesCount,
      todayWinningTradesCount,
      hasTradeHistory,
      riskUsed,
      totalCapital,
      capitalUsed,
      freeCapital,
      dayPnl: todayPnl,
      totalPnl: todayPnl,
      positions: positionsList,
      recentTrades: tradesList,
      engineStatus: (raw?.engine_status as string) ?? (raw?.engineStatus as string) ?? engineStore.status ?? 'running',
      engineMode: (raw?.engine_mode as string) ?? (raw?.engineMode as string) ?? engineStore.mode ?? 'paper',
      regime: (raw?.regime as MarketRegime) ?? engineStore.regime ?? 'sideways',
      regimeConfidence: regConf,
      activeStrategies: activeStrategies as string[],
      signalsGenerated,
      signalsConfirmed,
      signalsSkipped,
    };
  }, [apiData, stratData, storedPositions, storedTrades, confirmedIds, skippedIds, engineStore.status, engineStore.mode, engineStore.regime]);

  const pnlIsPositive = data.todayPnl >= 0;
  const pnlColor = data.todayPnl > 0 ? 'text-ub-profit' : data.todayPnl < 0 ? 'text-ub-loss' : 'text-ub-text-muted';
  const riskColor = getRiskColor(data.riskUsed);
  const capitalUsedPct = data.totalCapital > 0 ? (data.capitalUsed / data.totalCapital) * 100 : 0;

  const engineStatus = (engineStore.status || data.engineStatus || 'stopped') as 'running' | 'stopped' | 'paused' | 'error';
  const engineMode = (engineStore.mode || data.engineMode || 'paper') as 'paper' | 'live';
  const activeBrokerId = engineStore.activeBroker;
  const activeBrokerName = activeBrokerId ? (BROKER_LIST.find((b) => b.id === activeBrokerId)?.name ?? activeBrokerId) : null;
  const startedAt = engineStore.startedAt;
  const regime = (engineStore.regime || data.regime || 'sideways') as MarketRegime;
  const regimeConf = data.regimeConfidence;
  const regimeCfg = REGIME_CONFIG[regime];

  const [engineDialogOpen, setEngineDialogOpen] = useState(false);

  // Heartbeat: simulate a pulse every 5s when engine is running
  useEffect(() => {
    if (engineStatus !== 'running') return;
    const interval = setInterval(() => {
      useStore.getState().engine.heartbeat();
    }, 5000);
    return () => clearInterval(interval);
  }, [engineStatus]);

  const handleStartStop = useCallback(async () => {
    if (engineStatus === 'running' || engineStatus === 'paused') {
      useStore.getState().engine.stop();
      try {
        await engine.stopAsync();
      } catch (err) {
        console.error('Failed to stop backend engine:', err);
      }
    } else {
      setEngineDialogOpen(true);
    }
  }, [engineStatus, engine]);

  const handleEngineStart = useCallback(async (mode: 'paper' | 'live', brokerId: string) => {
    useStore.getState().engine.start(mode, brokerId);
    setEngineDialogOpen(false);
    try {
      await engine.startAsync({ mode, broker: brokerId });
    } catch (err) {
      console.error('Failed to start backend engine:', err);
      useStore.getState().engine.stop();
    }
  }, [engine]);

  return (
    <TooltipProvider delayDuration={300}>
      {isLoading ? (
        <div className="space-y-4">
          <StatsRowSkeleton />
          <MainContentSkeleton />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {/* ────────────────────────────────────────
                SECTION 1: TOP STATS ROW
            ──────────────────────────────────────── */}

          {/* Card 1: Today's P&L */}
          <StatCard title="Today's P&L">
            <div className="flex items-center gap-3">
              <div className={`h-10 w-10 rounded-lg flex items-center justify-center ${pnlIsPositive ? 'bg-ub-profit/10' : 'bg-ub-loss/10'}`}>
                {pnlIsPositive ? (
                  <TrendingUp className="h-5 w-5 text-ub-profit" />
                ) : (
                  <TrendingDown className="h-5 w-5 text-ub-loss" />
                )}
              </div>
              <div>
                <p className={`text-xl font-bold font-mono ${pnlColor}`}>
                  {formatINR(data.todayPnl)}
                </p>
                <p className={`text-xs font-medium ${pnlColor}`}>
                  {formatPercent(data.todayPnlPercent)}
                </p>
              </div>
            </div>
          </StatCard>

          {/* Card 2: Active Positions */}
          <StatCard title="Active Positions">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-ub-accent/10 flex items-center justify-center">
                <Activity className="h-5 w-5 text-ub-accent" />
              </div>
              <div>
                <p className="text-xl font-bold text-ub-text-primary font-mono">
                  {data.activePositions}
                </p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-xs text-ub-profit font-medium">
                    {data.longCount} Long
                  </span>
                  <span className="text-ub-border">|</span>
                  <span className="text-xs text-ub-loss font-medium">
                    {data.shortCount} Short
                  </span>
                </div>
              </div>
            </div>
          </StatCard>

          {/* Card 3: Dynamic Win Rate */}
          <StatCard title="Win Rate">
            <div className="flex items-center gap-4">
              <CircularProgress
                value={data.hasTradeHistory ? data.winRate : 0}
                size={68}
                strokeWidth={5}
                color={!data.hasTradeHistory ? '#64748b' : data.winRate >= 60 ? '#22c55e' : data.winRate >= 40 ? '#f59e0b' : '#ef4444'}
              />
              <div className="flex flex-col">
                <span className="text-xs text-ub-text-muted">
                  {data.hasTradeHistory
                    ? `${data.winningTradesCount}/${data.totalTradesCount} Won (All-Time)`
                    : 'Trades Won'}
                </span>
                <span
                  className={`text-sm font-semibold ${!data.hasTradeHistory
                      ? 'text-ub-text-muted'
                      : data.winRate >= 60
                        ? 'text-ub-profit'
                        : data.winRate >= 40
                          ? 'text-ub-warning'
                          : 'text-ub-loss'
                    }`}
                >
                  {!data.hasTradeHistory
                    ? 'No Trades Yet'
                    : data.winRate >= 60
                      ? 'Good'
                      : data.winRate >= 40
                        ? 'Moderate'
                        : 'Needs Tuning'}
                </span>
                {data.todayTradesCount > 0 && (
                  <span className="text-[10px] text-cyan-400 font-mono mt-0.5">
                    Today: {data.todayWinningTradesCount}/{data.todayTradesCount} ({data.todayWinRate}%)
                  </span>
                )}
              </div>
            </div>
          </StatCard>

          {/* Card 4: Risk Used */}
          <StatCard title="Risk Used">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ShieldAlert className={`h-5 w-5`} style={{ color: riskColor }} />
                  <span className="text-xl font-bold font-mono" style={{ color: riskColor }}>
                    {data.riskUsed}%
                  </span>
                </div>
                <Badge
                  variant="outline"
                  className="text-[10px] font-semibold"
                  style={{
                    color: riskColor,
                    borderColor: riskColor + '40',
                    backgroundColor: riskColor + '15',
                  }}
                >
                  {getRiskLabel(data.riskUsed)}
                </Badge>
              </div>
              <div className="h-2 w-full rounded-full bg-ub-border overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${Math.min(data.riskUsed, 100)}%`,
                    backgroundColor: riskColor,
                  }}
                />
              </div>
              <p className="text-[11px] text-ub-text-muted">
                {data.riskUsed < 50
                  ? 'Healthy risk utilization'
                  : data.riskUsed <= 80
                    ? 'Approaching limit — exercise caution'
                    : 'High risk — consider reducing exposure'}
              </p>
            </div>
          </StatCard>

          {/* ────────────────────────────────────────
                SECTION 2: MAIN CONTENT — LEFT (3/5)
            ──────────────────────────────────────── */}

          {/* Capital Panel */}
          <SectionCard
            title="Capital Overview"
            icon={BarChart3}
            headerRight={<MarketTimer />}
            className="md:col-span-1 xl:col-span-3"
          >
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
              <div>
                <p className="text-[11px] text-ub-text-muted uppercase tracking-wider">Total Capital</p>
                <p className="text-sm font-bold text-ub-text-primary font-mono mt-0.5">
                  {formatINR(data.totalCapital)}
                </p>
              </div>
              <div>
                <p className="text-[11px] text-ub-text-muted uppercase tracking-wider">Capital Used</p>
                <p className="text-sm font-bold text-ub-warning font-mono mt-0.5">
                  {formatINR(data.capitalUsed)}
                </p>
              </div>
              <div>
                <p className="text-[11px] text-ub-text-muted uppercase tracking-wider">Free Capital</p>
                <p className="text-sm font-bold text-ub-profit font-mono mt-0.5">
                  {formatINR(data.freeCapital)}
                </p>
              </div>
              <div>
                <p className="text-[11px] text-ub-text-muted uppercase tracking-wider">Day P&L</p>
                <p className={`text-sm font-bold font-mono mt-0.5 ${data.dayPnl >= 0 ? 'text-ub-profit' : 'text-ub-loss'}`}>
                  {formatINR(data.dayPnl)}
                </p>
              </div>
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-ub-text-muted">Capital Utilization</span>
                <span className="text-ub-text-primary font-medium font-mono">{capitalUsedPct.toFixed(1)}%</span>
              </div>
              <Progress
                value={capitalUsedPct}
                className="h-2 bg-ub-border [&>div]:bg-ub-accent"
              />
            </div>
            <Separator className="my-3 bg-ub-border" />
            <div className="flex items-center justify-between">
              <span className="text-xs text-ub-text-muted">Total P&L (All Time)</span>
              <span className={`text-base font-bold font-mono ${data.totalPnl >= 0 ? 'text-ub-profit' : 'text-ub-loss'}`}>
                {formatINR(data.totalPnl)}
              </span>
            </div>
          </SectionCard>

          {/* ────────────────────────────────────────
                SECTION 2: MAIN CONTENT — RIGHT (2/5)
            ──────────────────────────────────────── */}

          {/* Engine Status */}
          <SectionCard title="Engine Status" icon={Zap} className="xl:col-span-2">
            <div className="space-y-3">
              {/* Top row: Status + Mode + Broker */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className={`h-2.5 w-2.5 rounded-full ${engineStatus === 'running'
                        ? 'bg-ub-profit animate-pulse'
                        : engineStatus === 'error'
                          ? 'bg-ub-loss animate-pulse'
                          : engineStatus === 'paused'
                            ? 'bg-ub-warning'
                            : 'bg-ub-text-disabled'
                      }`}
                  />
                  <Badge
                    variant="outline"
                    className={`text-xs font-semibold ${engineStatus === 'running'
                        ? 'border-ub-profit/30 text-ub-profit bg-ub-profit/10'
                        : engineStatus === 'error'
                          ? 'border-ub-loss/30 text-ub-loss bg-ub-loss/10'
                          : engineStatus === 'paused'
                            ? 'border-ub-warning/30 text-ub-warning bg-ub-warning/10'
                            : 'border-ub-text-disabled/30 text-ub-text-disabled bg-ub-text-disabled/10'
                      }`}
                  >
                    {engineStatus.charAt(0).toUpperCase() + engineStatus.slice(1)}
                  </Badge>
                </div>
                <Badge
                  variant="outline"
                  className={`text-[10px] font-semibold ${engineMode === 'live'
                      ? 'border-ub-loss/30 text-ub-loss bg-ub-loss/10'
                      : 'border-ub-accent/30 text-ub-accent bg-ub-accent/10'
                    }`}
                >
                  {engineMode === 'live' ? '🔴 ' : '🟢 '}
                  {engineMode.charAt(0).toUpperCase() + engineMode.slice(1)}
                </Badge>
              </div>

              {/* Active broker + uptime (shown when running) */}
              {engineStatus === 'running' && (
                <div className="flex items-center justify-between px-3 py-2 rounded-md" style={{ backgroundColor: 'rgba(0, 208, 156, 0.06)', border: '1px solid rgba(0, 208, 156, 0.12)' }}>
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5">
                      <Wifi size={13} className="text-ub-profit" />
                      <span className="text-[11px] text-ub-text-muted">Connected via</span>
                    </div>
                    <span className="text-xs font-semibold text-ub-text-primary">
                      {activeBrokerName || (engineMode === 'live' ? 'Live Broker' : 'Paper Broker')}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Timer size={13} className="text-ub-text-disabled" />
                    <span className="text-[11px] text-ub-text-muted">Uptime</span>
                    <UptimeTicker startedAt={startedAt} />
                  </div>
                </div>
              )}

              {/* Error message */}
              {engineStatus === 'error' && engineStore.errorMessage && (
                <div className="flex items-start gap-2 px-3 py-2.5 rounded-md" style={{ backgroundColor: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
                  <AlertTriangle size={14} className="shrink-0 mt-0.5 text-ub-loss" />
                  <p className="text-[11px] text-ub-loss leading-relaxed">{engineStore.errorMessage}</p>
                </div>
              )}

              {/* Stopped: show reason if available */}
              {engineStatus === 'stopped' && !activeBrokerId && (
                <p className="text-[11px] text-ub-text-disabled">Engine is idle. Select a mode and broker to start trading.</p>
              )}

              <div className="flex gap-2">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={engineStatus === 'running'}
                      onClick={() => setEngineDialogOpen(true)}
                      className={`flex-1 h-9 text-xs font-semibold border-ub-border ${engineStatus !== 'running'
                          ? 'hover:bg-ub-profit/15 hover:text-ub-profit hover:border-ub-profit/40 text-ub-text-muted'
                          : 'opacity-40 cursor-not-allowed'
                        }`}
                    >
                      <Power className="h-3.5 w-3.5 mr-1.5" />
                      Start Engine
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent className="bg-ub-surface border-ub-border text-ub-text-primary text-xs">
                    Choose mode & broker to start
                  </TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={engineStatus === 'stopped'}
                      onClick={() => useStore.getState().engine.stop()}
                      className={`flex-1 h-9 text-xs font-semibold border-ub-border ${engineStatus !== 'stopped'
                          ? 'hover:bg-ub-loss/15 hover:text-ub-loss hover:border-ub-loss/40 text-ub-text-muted'
                          : 'opacity-40 cursor-not-allowed'
                        }`}
                    >
                      <Square className="h-3.5 w-3.5 mr-1.5" />
                      Stop
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent className="bg-ub-surface border-ub-border text-ub-text-primary text-xs">
                    Stop the trading engine
                  </TooltipContent>
                </Tooltip>
              </div>
            </div>
          </SectionCard>

          {/* Open Positions Table */}
          <SectionCard title="Open Positions" icon={Activity} className="md:col-span-1 xl:col-span-3">
            <ScrollArea className="max-h-[300px]">
              <Table>
                <TableHeader>
                  <TableRow className="border-ub-border hover:bg-transparent">
                    <TableHead className="text-[11px] text-ub-text-muted font-semibold uppercase tracking-wider h-8">Symbol</TableHead>
                    <TableHead className="text-[11px] text-ub-text-muted font-semibold uppercase tracking-wider h-8 text-center">Dir</TableHead>
                    <TableHead className="text-[11px] text-ub-text-muted font-semibold uppercase tracking-wider h-8 text-right">Entry</TableHead>
                    <TableHead className="text-[11px] text-ub-text-muted font-semibold uppercase tracking-wider h-8 text-right">Current</TableHead>
                    <TableHead className="text-[11px] text-ub-text-muted font-semibold uppercase tracking-wider h-8 text-center">Qty</TableHead>
                    <TableHead className="text-[11px] text-ub-text-muted font-semibold uppercase tracking-wider h-8 text-right">P&L</TableHead>
                    <TableHead className="text-[11px] text-ub-text-muted font-semibold uppercase tracking-wider h-8 text-center hidden sm:table-cell">Booked</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.positions.map((pos) => {
                    const pnlPositive = pos.pnl >= 0;
                    return (
                      <TableRow key={pos.id} className="border-ub-border hover:bg-ub-surface-hover transition-colors">
                        <TableCell className="text-xs font-semibold text-ub-text-primary py-2.5">
                          {pos.symbol}
                        </TableCell>
                        <TableCell className="py-2.5 text-center">
                          <Badge
                            variant="outline"
                            className={`text-[10px] font-bold ${pos.direction === 'BUY'
                                ? 'border-ub-profit/30 text-ub-profit bg-ub-profit/10'
                                : 'border-ub-loss/30 text-ub-loss bg-ub-loss/10'
                              }`}
                          >
                            {pos.direction === 'BUY' ? (
                              <ArrowUpRight className="h-3 w-3 mr-0.5" />
                            ) : (
                              <ArrowDownRight className="h-3 w-3 mr-0.5" />
                            )}
                            {pos.direction}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs font-mono text-ub-text-muted py-2.5 text-right">
                          {pos.entry.toFixed(2)}
                        </TableCell>
                        <TableCell className="text-xs font-mono text-ub-text-primary py-2.5 text-right">
                          {pos.current.toFixed(2)}
                        </TableCell>
                        <TableCell className="text-xs font-mono text-ub-text-primary py-2.5 text-center">
                          {pos.qty}
                        </TableCell>
                        <TableCell className={`text-xs font-mono font-semibold py-2.5 text-right ${pnlPositive ? 'text-ub-profit' : 'text-ub-loss'
                          }`}>
                          {pnlPositive ? '+' : ''}{formatINR(pos.pnl)}
                        </TableCell>
                        <TableCell className="py-2.5 text-center hidden sm:table-cell">
                          {pos.bookedLevels.length > 0 ? (
                            <div className="flex flex-wrap gap-1 justify-center">
                              {pos.bookedLevels.map((level, idx) => (
                                <Badge
                                  key={idx}
                                  variant="outline"
                                  className="text-[9px] font-mono border-ub-accent/30 text-ub-accent bg-ub-accent/5"
                                >
                                  {level.toFixed(1)}
                                </Badge>
                              ))}
                            </div>
                          ) : (
                            <span className="text-[11px] text-ub-text-muted">—</span>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </ScrollArea>
            {data.positions.length === 0 && (
              <div className="flex flex-col items-center justify-center py-8 text-ub-text-muted">
                <Activity className="h-8 w-8 mb-2 opacity-30" />
                <p className="text-xs">No open positions</p>
              </div>
            )}
          </SectionCard>

          {/* Market Regime */}
          <SectionCard title="Market Regime" icon={Radio} className="xl:col-span-2">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Badge
                  variant="outline"
                  className={`text-xs font-bold px-3 py-1 ${regimeCfg.colorClass} ${regimeCfg.bgClass} ${regimeCfg.borderClass}`}
                >
                  {regime === 'bull' && <TrendingUp className="h-3.5 w-3.5 mr-1" />}
                  {regime === 'bear' && <TrendingDown className="h-3.5 w-3.5 mr-1" />}
                  {regime === 'sideways' && <BarChart3 className="h-3.5 w-3.5 mr-1" />}
                  {regime === 'volatile' && <AlertTriangle className="h-3.5 w-3.5 mr-1" />}
                  {regimeCfg.label} Market
                </Badge>
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] text-ub-text-muted">Confidence</span>
                  <span className="text-xs font-mono font-bold text-ub-text-primary">{regimeConf}%</span>
                </div>
              </div>
              <Progress
                value={regimeConf}
                className="h-1.5 bg-ub-border"
                style={{ '--progress-color': regimeCfg.colorClass.includes('profit') ? '#22c55e' : regimeCfg.colorClass.includes('loss') ? '#ef4444' : regimeCfg.colorClass.includes('volatile') ? '#a855f7' : '#f59e0b' } as React.CSSProperties}
              />
              <Separator className="bg-ub-border" />
              <div>
                <p className="text-[11px] text-ub-text-muted mb-2">Active Strategies</p>
                <div className="flex flex-wrap gap-1.5">
                  {data.activeStrategies.map((strategy, idx) => (
                    <Badge
                      key={idx}
                      variant="outline"
                      className="text-[10px] font-medium border-ub-accent/20 text-ub-accent bg-ub-accent/5"
                    >
                      {strategy}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          </SectionCard>

          {/* Quick Signals */}
          <SectionCard title="Quick Signals" icon={SignalHigh} className="xl:col-span-2">
            <div className="grid grid-cols-3 gap-3">
              <div className="text-center p-2 rounded-lg bg-ub-background/50">
                <p className="text-lg font-bold font-mono text-ub-accent">{data.signalsGenerated}</p>
                <p className="text-[10px] text-ub-text-muted mt-0.5">Generated</p>
              </div>
              <div className="text-center p-2 rounded-lg bg-ub-background/50">
                <p className="text-lg font-bold font-mono text-ub-profit">{data.signalsConfirmed}</p>
                <p className="text-[10px] text-ub-text-muted mt-0.5">Confirmed</p>
              </div>
              <div className="text-center p-2 rounded-lg bg-ub-background/50">
                <p className="text-lg font-bold font-mono text-ub-warning">{data.signalsSkipped}</p>
                <p className="text-[10px] text-ub-text-muted mt-0.5">Skipped</p>
              </div>
            </div>
            <div className="mt-3 flex items-center gap-1.5 text-[11px] text-ub-text-muted">
              <SignalHigh className="h-3 w-3" />
              <span>
                {data.signalsGenerated > 0
                  ? `${((data.signalsConfirmed / data.signalsGenerated) * 100).toFixed(0)}% confirmation rate`
                  : 'No signals today'}
              </span>
            </div>
          </SectionCard>

          {/* Live Strategy & Scan Telemetry Feed - Full Width */}
          <ScanTelemetryCard
            engineState={engineStatus}
            activeBroker={activeBrokerName}
            className="md:col-span-2 xl:col-span-4"
          />

          {/* ────────────────────────────────────────
                SECTION 3: RECENT TRADES
            ──────────────────────────────────────── */}

          {/* Recent Trades - spans full width */}
          <SectionCard title="Recent Trades" icon={Eye} className="md:col-span-2 xl:col-span-4">
            <Table>
              <TableHeader>
                <TableRow className="border-ub-border hover:bg-transparent">
                  <TableHead className="text-[11px] text-ub-text-muted font-semibold uppercase tracking-wider h-8">Time</TableHead>
                  <TableHead className="text-[11px] text-ub-text-muted font-semibold uppercase tracking-wider h-8">Symbol</TableHead>
                  <TableHead className="text-[11px] text-ub-text-muted font-semibold uppercase tracking-wider h-8 text-center">Direction</TableHead>
                  <TableHead className="text-[11px] text-ub-text-muted font-semibold uppercase tracking-wider h-8 text-right">P&L</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.recentTrades.slice(0, 5).map((trade) => {
                  const isProfit = trade.pnl >= 0;
                  return (
                    <TableRow key={trade.id} className="border-ub-border hover:bg-ub-surface-hover transition-colors">
                      <TableCell className="text-xs font-mono text-ub-text-muted py-2.5">
                        {trade.time}
                      </TableCell>
                      <TableCell className="text-xs font-semibold text-ub-text-primary py-2.5">
                        {trade.symbol}
                      </TableCell>
                      <TableCell className="py-2.5 text-center">
                        <Badge
                          variant="outline"
                          className={`text-[10px] font-bold ${trade.direction === 'BUY'
                              ? 'border-ub-profit/30 text-ub-profit bg-ub-profit/10'
                              : 'border-ub-loss/30 text-ub-loss bg-ub-loss/10'
                            }`}
                        >
                          {trade.direction}
                        </Badge>
                      </TableCell>
                      <TableCell className={`text-xs font-mono font-semibold py-2.5 text-right ${isProfit ? 'text-ub-profit' : 'text-ub-loss'
                        }`}>
                        {isProfit ? '+' : ''}{formatINR(trade.pnl)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            {data.recentTrades.length === 0 && (
              <div className="flex flex-col items-center justify-center py-6 text-ub-text-muted">
                <Eye className="h-8 w-8 mb-2 opacity-30" />
                <p className="text-xs">No trades today</p>
              </div>
            )}
            <div className="mt-3 flex justify-end">
              <Link href="/trades">
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs text-ub-accent hover:text-ub-accent-hover hover:bg-ub-accent/10 h-7 cursor-pointer"
                >
                  View All Trades
                  <ArrowUpRight className="h-3 w-3 ml-1" />
                </Button>
              </Link>
            </div>
          </SectionCard>
        </div>
      )}

      <StartEngineDialog
        open={engineDialogOpen}
        onOpenChange={setEngineDialogOpen}
        onStart={handleEngineStart}
        isStarting={engine.isStarting}
      />
    </TooltipProvider>
  );
}
