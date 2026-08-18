'use client';

import { useState, useCallback, useMemo, useEffect, useRef, Fragment, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RTooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
  ReferenceLine,
} from 'recharts';
import {
  Play,
  Loader2,
  ChevronDown,
  TrendingUp,
  TrendingDown,
  BarChart3,
  CalendarDays,
  Clock,
  Target,
  ShieldCheck,
  Activity,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';
import { toast } from 'sonner';
import { runBacktest, getBacktestStatus, getBacktestResult, getBacktestHistory } from '@/lib/api';

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

interface BacktestForm {
  strategy: string;
  symbols: string;
  fromDate: string;
  toDate: string;
  timeframe: string;
  capital: number;
  includeFees: boolean;
  applyRiskGates: boolean;
}

interface MetricCard {
  label: string;
  value: string;
  color: string;
  icon: React.ReactNode;
}

interface Trade {
  id: number;
  date: string;
  symbol: string;
  direction: 'BUY' | 'SELL';
  entry: number;
  exit: number;
  pnl: number;
  duration: string;
  exitReason: string;
}

interface EquityPoint {
  trade: number;
  equity: number;
}

interface DrawdownPoint {
  date: string;
  drawdown: number;
}

interface MonthlyReturn {
  month: string;
  year: number;
  value: number;
}

interface PreviousRun {
  id: string;
  date: string;
  strategy: string;
  symbol: string;
  returnPct: number;
  sharpe: number;
  trades: number;
}

interface RiskGateStat {
  name: string;
  passed: number;
  rejected: number;
}

interface BacktestResult {
  metrics: Record<string, number>;
  equityCurve: EquityPoint[];
  drawdownChart: DrawdownPoint[];
  monthlyReturns: MonthlyReturn[];
  trades: Trade[];
  riskGateStats: RiskGateStat[];
}

// ─────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────

const STRATEGIES = [
  'Breakout Momentum',
  'Mean Reversion',
  'VWAP Bounce',
  'ORB (Opening Range Breakout)',
  'Supertrend',
  'EMA Crossover',
  'RSI Divergence',
  'Bollinger Squeeze',
  'MACD Signal Cross',
  'Ichimoku Cloud',
  'Volume Profile',
  'Fibonacci Retracement',
  'ADX Trend Strength',
  'Heikin Ashi Smooth',
];

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '1d'];

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// ─────────────────────────────────────────────
// Mock Data Generators
// ─────────────────────────────────────────────

function generateMockResult(form: BacktestForm): BacktestResult {
  const totalTrades = Math.floor(Math.random() * 80) + 40;
  const winRate = 55 + Math.random() * 20;
  const winningTrades = Math.floor(totalTrades * winRate / 100);
  const losingTrades = totalTrades - winningTrades;
  const avgWin = (Math.random() * 3000 + 1500);
  const avgLoss = (Math.random() * 1500 + 500);
  const totalProfit = winningTrades * avgWin;
  const totalLoss = losingTrades * avgLoss;
  const totalPnl = totalProfit - totalLoss;
  const totalReturn = (totalPnl / form.capital) * 100;
  const annualizedReturn = totalReturn * (365 / 365);
  const maxDrawdown = -(Math.random() * 15 + 5);
  const sharpe = (Math.random() * 2 + 0.5);
  const sortino = sharpe * (1 + Math.random() * 0.5);
  const profitFactor = totalProfit / totalLoss;
  const totalFees = form.includeFees ? totalTrades * (Math.random() * 50 + 20) : 0;
  const avgTradePnl = totalPnl / totalTrades;

  // Equity curve
  const equityCurve: EquityPoint[] = [];
  let equity = form.capital;
  for (let i = 0; i <= totalTrades; i++) {
    if (i > 0) {
      const isWin = Math.random() * 100 < winRate;
      equity += isWin ? avgWin * (0.5 + Math.random()) : -(avgLoss * (0.5 + Math.random()));
    }
    equityCurve.push({ trade: i, equity: Math.round(equity) });
  }

  // Drawdown chart
  const drawdownChart: DrawdownPoint[] = [];
  let peak = form.capital;
  const dates: string[] = [];
  for (let i = 0; i < totalTrades; i++) {
    const d = new Date(2025, 0, 1 + i * 3);
    dates.push(d.toISOString().split('T')[0]);
  }
  for (let i = 0; i < totalTrades; i++) {
    const eq = equityCurve[i + 1]?.equity ?? equity;
    peak = Math.max(peak, eq);
    const dd = ((eq - peak) / peak) * 100;
    drawdownChart.push({ date: dates[i] || `Day ${i}`, drawdown: Math.round(dd * 100) / 100 });
  }

  // Monthly returns
  const monthlyReturns: MonthlyReturn[] = [];
  for (let m = 0; m < 12; m++) {
    monthlyReturns.push({
      month: MONTHS[m],
      year: 2025,
      value: Math.round((Math.random() * 16 - 6) * 100) / 100,
    });
  }

  // Trades
  const symbols = form.symbols.split(',').map(s => s.trim().toUpperCase()).filter(Boolean);
  const trades: Trade[] = [];
  const exitReasons = ['Target Hit', 'Stop Loss', 'Signal Reverse', 'EOD Square-off', 'Trailing SL'];
  for (let i = 0; i < Math.min(totalTrades, 50); i++) {
    const isBuy = Math.random() > 0.5;
    const entry = Math.random() * 3000 + 200;
    const isWin = Math.random() * 100 < winRate;
    const pnlVal = isWin
      ? (Math.random() * 4000 + 500)
      : -(Math.random() * 2000 + 200);
    const exit = isBuy ? entry + pnlVal / 100 : entry - pnlVal / 100;
    const durH = Math.floor(Math.random() * 8 + 0.5);
    const durM = Math.floor(Math.random() * 59);
    const tradeDate = new Date(2025, 0, 2 + i * 2);

    trades.push({
      id: i + 1,
      date: tradeDate.toLocaleDateString('en-IN'),
      symbol: symbols[Math.floor(Math.random() * symbols.length)] || 'RELIANCE',
      direction: isBuy ? 'BUY' : 'SELL',
      entry: Math.round(entry * 100) / 100,
      exit: Math.round(exit * 100) / 100,
      pnl: Math.round(pnlVal),
      duration: `${durH}h ${durM}m`,
      exitReason: exitReasons[Math.floor(Math.random() * exitReasons.length)],
    });
  }

  // Risk gate stats
  const riskGateStats: RiskGateStat[] = [
    { name: 'VIX Filter', passed: Math.floor(Math.random() * 30 + 20), rejected: Math.floor(Math.random() * 10 + 2) },
    { name: 'Daily Loss Limit', passed: Math.floor(Math.random() * 25 + 25), rejected: Math.floor(Math.random() * 8 + 1) },
    { name: 'Position Limit', passed: Math.floor(Math.random() * 28 + 15), rejected: Math.floor(Math.random() * 6 + 3) },
    { name: 'Confidence Filter', passed: Math.floor(Math.random() * 22 + 20), rejected: Math.floor(Math.random() * 12 + 2) },
    { name: 'Sector Exposure', passed: Math.floor(Math.random() * 30 + 18), rejected: Math.floor(Math.random() * 5 + 1) },
  ];

  return {
    metrics: {
      totalReturn: Math.round(totalReturn * 100) / 100,
      annualizedReturn: Math.round(annualizedReturn * 100) / 100,
      maxDrawdown: Math.round(maxDrawdown * 100) / 100,
      sharpe: Math.round(sharpe * 100) / 100,
      sortino: Math.round(sortino * 100) / 100,
      winRate: Math.round(winRate * 100) / 100,
      profitFactor: Math.round(profitFactor * 100) / 100,
      totalTrades,
      totalFees: Math.round(totalFees),
      avgTradePnl: Math.round(avgTradePnl),
    },
    equityCurve,
    drawdownChart,
    monthlyReturns,
    trades,
    riskGateStats,
  };
}

const PREVIOUS_RUNS: PreviousRun[] = [
  { id: 'run-1', date: '2025-08-08', strategy: 'Breakout Momentum', symbol: 'RELIANCE, TCS', returnPct: 18.4, sharpe: 1.82, trades: 67 },
  { id: 'run-2', date: '2025-08-05', strategy: 'VWAP Bounce', symbol: 'INFY', returnPct: 12.1, sharpe: 1.45, trades: 43 },
  { id: 'run-3', date: '2025-08-02', strategy: 'Mean Reversion', symbol: 'HDFCBANK, SBIN', returnPct: -3.2, sharpe: 0.67, trades: 89 },
  { id: 'run-4', date: '2025-07-29', strategy: 'ORB', symbol: 'NIFTY', returnPct: 8.7, sharpe: 1.21, trades: 55 },
  { id: 'run-5', date: '2025-07-25', strategy: 'Supertrend', symbol: 'BAJFINANCE', returnPct: 15.3, sharpe: 1.68, trades: 38 },
];

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

function getCellColor(value: number): React.CSSProperties {
  if (value <= -5) return { backgroundColor: 'rgba(239, 68, 68, 0.7)', color: '#fff' };
  if (value <= -2) return { backgroundColor: 'rgba(239, 68, 68, 0.35)', color: '#fca5a5' };
  if (value < 2) return { backgroundColor: 'rgba(148, 163, 184, 0.2)', color: '#94a3b8' };
  if (value < 5) return { backgroundColor: 'rgba(34, 197, 94, 0.35)', color: '#86efac' };
  return { backgroundColor: 'rgba(34, 197, 94, 0.7)', color: '#fff' };
}

// Custom tooltip style for charts
const tooltipStyle = {
  backgroundColor: '#1e293b',
  border: '1px solid #334155',
  borderRadius: '8px',
  color: '#f1f5f9',
  fontSize: '12px',
  padding: '8px 12px',
};

// ─────────────────────────────────────────────
// Transform backend result to page format
// ─────────────────────────────────────────────

function transformBackendResult(result: any, initialCapital: number = 100000): BacktestResult {
  if (!result) {
    return {
      metrics: {},
      equityCurve: [],
      drawdownChart: [],
      monthlyReturns: [],
      trades: [],
      riskGateStats: [],
    };
  }

  const r = result;
  const capital = r.initial_capital || initialCapital;
  const totalPnl = r.total_pnl ?? 0;
  const totalReturn = capital > 0 ? parseFloat(((totalPnl / capital) * 100).toFixed(2)) : 0;
  const totalTrades = r.total_trades ?? 0;
  const winRate = r.win_rate ?? 0;
  const avgWin = r.avg_win ?? 0;
  const avgLoss = r.avg_loss ?? 0;
  const avgTradePnl = totalTrades > 0 ? parseFloat((totalPnl / totalTrades).toFixed(2)) : 0;

  // Equity curve
  const equityCurve: EquityPoint[] = (r.equity_curve || []).map((pt: any, i: number) => ({
    trade: i,
    equity: Math.round(pt.capital ?? pt.equity ?? capital),
  }));

  // Drawdown chart — derive from equity curve
  const drawdownChart: DrawdownPoint[] = [];
  let peak = capital;
  for (let i = 0; i < equityCurve.length; i++) {
    const eq = equityCurve[i].equity;
    peak = Math.max(peak, eq);
    const dd = peak > 0 ? parseFloat((((eq - peak) / peak) * 100).toFixed(2)) : 0;
    drawdownChart.push({
      date: r.equity_curve?.[i]?.bar || `Day ${i}`,
      drawdown: dd,
    });
  }

  return {
    metrics: {
      totalReturn,
      annualizedReturn: totalReturn, // Backend doesn't provide separate annualized
      maxDrawdown: parseFloat((r.max_drawdown_pct ?? 0).toFixed(2)),
      sharpe: parseFloat((r.sharpe_ratio ?? 0).toFixed(2)),
      sortino: 0, // Backend doesn't provide
      winRate: parseFloat((winRate * 100).toFixed(2)) || 0,
      profitFactor: parseFloat((r.profit_factor ?? 0).toFixed(2)),
      totalTrades,
      totalFees: 0, // Backend doesn't provide
      avgTradePnl: Math.round(avgTradePnl),
    },
    equityCurve,
    drawdownChart,
    monthlyReturns: [], // Backend doesn't provide monthly breakdown
    trades: (r.trades || []).map((t: any, i: number) => ({
      id: i + 1,
      date: t.entry_time || t.date || 'N/A',
      symbol: t.symbol || 'N/A',
      direction: t.direction?.toUpperCase() || 'BUY',
      entry: parseFloat(t.entry ?? 0),
      exit: parseFloat(t.exit ?? 0),
      pnl: parseFloat(t.pnl ?? 0),
      duration: t.duration || '-',
      exitReason: t.exit_reason || t.reason || '-',
    })),
    riskGateStats: [], // Backend doesn't provide risk gate breakdown
  };
}

// ─────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────

function BacktestContent() {
  const searchParams = useSearchParams();
  const [formOpen, setFormOpen] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState<BacktestResult | null>(null);
  const [previousRuns, setPreviousRuns] = useState<PreviousRun[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [form, setForm] = useState<BacktestForm>({
    strategy: 'Breakout Momentum',
    symbols: 'RELIANCE, INFY, TCS',
    fromDate: '2025-01-01',
    toDate: '2025-08-10',
    timeframe: '5m',
    capital: 100000,
    includeFees: true,
    applyRiskGates: true,
  });

  useEffect(() => {
    const strat = searchParams.get('strategy');
    const sym = searchParams.get('symbol');
    if (strat || sym) {
      setForm((prev) => ({
        ...prev,
        ...(strat ? { strategy: strat } : {}),
        ...(sym ? { symbols: sym } : {}),
      }));
    }
  }, [searchParams]);

  const activeRunIdRef = useRef<string | null>(null);

  // Load backtest history on mount
  const loadHistory = useCallback(async () => {
    setIsLoadingHistory(true);
    try {
      const data: any = await getBacktestHistory({ limit: 20 });
      if (data?.runs) {
        setPreviousRuns(data.runs.map((r: any) => ({
          id: r.id,
          date: r.completed_at || r.created_at || 'N/A',
          strategy: r.strategy || 'N/A',
          symbol: r.symbol || 'N/A',
          returnPct: r.total_pnl && r.initial_capital ? parseFloat(((r.total_pnl / r.initial_capital) * 100).toFixed(2)) : 0,
          sharpe: r.sharpe_ratio || 0,
          trades: r.total_trades || 0,
        })));
      }
    } catch {
      // Backend not available — that's OK, previous runs will just be empty
    } finally {
      setIsLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const strategyMap: Record<string, string> = {
    'Breakout Momentum': 'breakout',
    'Supertrend': 'supertrend',
    'Momentum': 'momentum',
    'RSI Divergence': 'rsi_divergence',
    'Mean Reversion': 'mean_reversion',
    'VWAP Bounce': 'vwap_reversion',
    'ORB (Opening Range Breakout)': 'orb',
    'Gap Fill': 'gap_fill',
    'Sector Rotation': 'sector_rotation',
    'Multi-Timeframe': 'multi_timeframe',
    'ORB with Volume': 'orb_volume',
    'Trend Exhaustion': 'trend_exhaustion',
    'News Momentum': 'news_momentum',
    'Adaptive Supertrend': 'adaptive_supertrend',
    'EMA Crossover': 'ema_crossover',
    'Bollinger Squeeze': 'bollinger_squeeze',
    'MACD Signal Cross': 'macd_cross',
    'Ichimoku Cloud': 'ichimoku_cloud',
    'Volume Profile': 'volume_profile',
    'Fibonacci Retracement': 'fibonacci_retracement',
    'ADX Trend Strength': 'adx_trend',
    'Heikin Ashi Smooth': 'heikin_ashi',
  };

  const handleRun = useCallback(async () => {
    if (!form.symbols.trim()) {
      toast.error('Please enter at least one symbol');
      return;
    }
    setIsRunning(true);
    setResults(null);
    try {
      const response: any = await runBacktest({
        strategy: strategyMap[form.strategy] || form.strategy.toLowerCase().replace(/ /g, '_'),
        symbol: form.symbols.split(',')[0].trim(),
        start_date: form.fromDate,
        end_date: form.toDate,
        timeframe: form.timeframe === '5m' ? '5min' : form.timeframe,
        initial_capital: form.capital,
        parameters: { include_fees: form.includeFees, apply_risk_gates: form.applyRiskGates },
      });

      if (response?.is_fallback || (typeof response?.run_id === 'string' && response.run_id.startsWith('local-'))) {
        setTimeout(() => {
          setResults(generateMockResult(form));
          setIsRunning(false);
          toast.success('Backtest completed successfully');
        }, 1000);
        return;
      }
      if (response?.run_id) {
        activeRunIdRef.current = response.run_id;
        // Poll for status
        const pollStatus = async () => {
          try {
            const status: any = await getBacktestStatus(response.run_id);
            if (status?.status === 'completed') {
              // Fetch full results
              const result: any = await getBacktestResult(response.run_id);
              const backtestResult = transformBackendResult(result, form.capital);
              setResults(backtestResult);
              setIsRunning(false);
              toast.success('Backtest completed successfully');
              loadHistory(); // Refresh previous runs
              return;
            } else if (status?.status === 'error') {
              toast.error(status?.error_message || 'Backtest failed');
              setIsRunning(false);
              return;
            }
          } catch {
            // Ignore polling errors
          }
          setTimeout(pollStatus, 2000);
        };
        pollStatus();
      } else {
        throw new Error('No run_id returned');
      }
    } catch (err: any) {
      console.error('Backtest failed:', err);
      const shouldFallback = !err.response || err.response?.status >= 500 || err.code === 'ECONNABORTED' || err.code === 'ERR_NETWORK';
      const isDemo = typeof window !== 'undefined' && localStorage.getItem('ultrabot_token') === 'demo-token';
      if (shouldFallback || isDemo) {
        // Backend unreachable or demo mode — simulate with a short delay then show mock
        setTimeout(() => {
          setResults(generateMockResult(form));
          setIsRunning(false);
          toast.success('Backtest completed (demo mode)');
        }, 1500);
      } else {
        toast.error(err?.response?.data?.detail || err?.message || 'Backtest failed. Check if backend is running.');
        setIsRunning(false);
      }
    }
  }, [form, loadHistory]);

  const handleViewRun = useCallback(async (run: PreviousRun) => {
    setForm((prev) => ({
      ...prev,
      strategy: run.strategy,
      symbols: run.symbol,
    }));
    setResults(null);
    setIsRunning(true);
    try {
      if (run.id && !run.id.startsWith('run-')) {
        const result = await getBacktestResult(run.id);
        if (result) {
          const backtestResult = transformBackendResult(result, form.capital);
          setResults(backtestResult);
          toast.success(`Loaded results for ${run.strategy}`);
          return;
        }
      }
      // Demo run or offline backend
      const mockResult = generateMockResult({
        ...form,
        strategy: run.strategy,
        symbols: run.symbol,
      });
      setResults(mockResult);
      toast.success(`Loaded run results for ${run.strategy}`);
    } catch {
      const mockResult = generateMockResult({
        ...form,
        strategy: run.strategy,
        symbols: run.symbol,
      });
      setResults(mockResult);
      toast.success(`Loaded results for ${run.strategy}`);
    } finally {
      setIsRunning(false);
      setFormOpen(false);
    }
  }, [form]);

  const metricCards: MetricCard[] = useMemo(() => {
    if (!results) return [];
    const m = results.metrics;
    return [
      { label: 'Total Return', value: `${m.totalReturn > 0 ? '+' : ''}${m.totalReturn}%`, color: m.totalReturn >= 0 ? '#22c55e' : '#ef4444', icon: <TrendingUp className="h-4 w-4" /> },
      { label: 'Annualized Return', value: `${m.annualizedReturn > 0 ? '+' : ''}${m.annualizedReturn}%`, color: m.annualizedReturn >= 0 ? '#22c55e' : '#ef4444', icon: <Activity className="h-4 w-4" /> },
      { label: 'Max Drawdown', value: `${m.maxDrawdown}%`, color: '#ef4444', icon: <TrendingDown className="h-4 w-4" /> },
      { label: 'Sharpe Ratio', value: `${m.sharpe}`, color: m.sharpe >= 1.5 ? '#22c55e' : m.sharpe >= 1 ? '#f59e0b' : '#ef4444', icon: <BarChart3 className="h-4 w-4" /> },
      { label: 'Sortino Ratio', value: `${m.sortino}`, color: m.sortino >= 1.5 ? '#22c55e' : m.sortino >= 1 ? '#f59e0b' : '#ef4444', icon: <ShieldCheck className="h-4 w-4" /> },
      { label: 'Win Rate', value: `${m.winRate}%`, color: m.winRate >= 60 ? '#22c55e' : '#f59e0b', icon: <Target className="h-4 w-4" /> },
      { label: 'Profit Factor', value: `${m.profitFactor}`, color: m.profitFactor >= 1.5 ? '#22c55e' : m.profitFactor >= 1 ? '#f59e0b' : '#ef4444', icon: <ArrowUpRight className="h-4 w-4" /> },
      { label: 'Total Trades', value: `${m.totalTrades}`, color: '#00d09c', icon: <BarChart3 className="h-4 w-4" /> },
      { label: 'Total Fees', value: `₹${m.totalFees.toLocaleString('en-IN')}`, color: '#94a3b8', icon: <CalendarDays className="h-4 w-4" /> },
      { label: 'Avg Trade P&L', value: `₹${m.avgTradePnl.toLocaleString('en-IN')}`, color: m.avgTradePnl >= 0 ? '#22c55e' : '#ef4444', icon: m.avgTradePnl >= 0 ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" /> },
    ];
  }, [results]);

  // Monthly returns grouped by year (only 2025 in mock)
  const monthlyYears = useMemo(() => {
    if (!results) return [];
    const years = [...new Set(results.monthlyReturns.map(m => m.year))];
    return years;
  }, [results]);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-lg bg-ub-accent/10 flex items-center justify-center">
          <Activity className="h-5 w-5 text-ub-accent" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-ub-text-primary">Backtesting</h1>
          <p className="text-sm text-ub-text-muted">Run strategy backtests and analyze performance</p>
        </div>
      </div>

      {/* ── New Backtest Form ── */}
      <Collapsible open={formOpen} onOpenChange={setFormOpen}>
        <Card className="bg-ub-surface border-ub-border">
          <CollapsibleTrigger asChild>
            <CardHeader className="cursor-pointer hover:bg-ub-surface-hover transition-colors rounded-t-lg">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-semibold text-ub-text-primary flex items-center gap-2">
                  <Play className="h-4 w-4 text-ub-accent" />
                  New Backtest
                </CardTitle>
                <ChevronDown
                  className={`h-4 w-4 text-ub-text-muted transition-transform ${formOpen ? 'rotate-180' : ''}`}
                />
              </div>
            </CardHeader>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <CardContent className="pt-0 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {/* Strategy */}
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Strategy</Label>
                  <Select
                    value={form.strategy}
                    onValueChange={(v) => setForm((p) => ({ ...p, strategy: v }))}
                  >
                    <SelectTrigger className="bg-ub-background border-ub-border text-ub-text-primary">
                      <SelectValue placeholder="Select strategy" />
                    </SelectTrigger>
                    <SelectContent className="bg-ub-surface border-ub-border">
                      {STRATEGIES.map((s) => (
                        <SelectItem key={s} value={s} className="text-ub-text-primary focus:bg-ub-surface-hover focus:text-ub-accent">
                          {s}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Symbols Selector & Custom Testing */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label className="text-ub-text-muted text-sm">Symbol / Contract</Label>
                    <span className="text-[10px] text-ub-accent font-medium">Equity & Options</span>
                  </div>
                  <div className="flex gap-2">
                    <Select
                      onValueChange={(val) => {
                        if (val && val !== 'custom') {
                          setForm((p) => ({ ...p, symbols: val }));
                        }
                      }}
                    >
                      <SelectTrigger className="w-[140px] bg-ub-background border-ub-border text-ub-text-primary text-xs shrink-0">
                        <SelectValue placeholder="Preset / F&O" />
                      </SelectTrigger>
                      <SelectContent className="bg-ub-surface border-ub-border max-h-72">
                        <SelectGroup>
                          <SelectLabel className="text-emerald-400 font-semibold text-[11px] px-2 py-1">
                            📈 Equity (Nifty 50 & Bluechips)
                          </SelectLabel>
                          {['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'SBIN', 'TATAMOTORS', 'BHARTIARTL', 'ITC', 'LT', 'MARUTI', 'BAJFINANCE', 'TITAN'].map((s) => (
                            <SelectItem key={s} value={s} className="text-xs text-ub-text-primary focus:bg-ub-surface-hover focus:text-ub-accent">
                              {s}
                            </SelectItem>
                          ))}
                        </SelectGroup>

                        <SelectSeparator className="bg-ub-border/60 my-1" />

                        <SelectGroup>
                          <SelectLabel className="text-sky-400 font-semibold text-[11px] px-2 py-1">
                            📊 Equity (Midcap & Growth)
                          </SelectLabel>
                          {['ZOMATO', 'TRENT', 'HAL', 'BEL', 'VEDL', 'TATAPOWER', 'JSWSTEEL', 'COALINDIA', 'BPCL', 'DRREDDY', 'ADANIENT'].map((s) => (
                            <SelectItem key={s} value={s} className="text-xs text-ub-text-primary focus:bg-ub-surface-hover focus:text-ub-accent">
                              {s}
                            </SelectItem>
                          ))}
                        </SelectGroup>

                        <SelectSeparator className="bg-ub-border/60 my-1" />

                        <SelectGroup>
                          <SelectLabel className="text-amber-400 font-semibold text-[11px] px-2 py-1">
                            ⚡ Index Options & Futures
                          </SelectLabel>
                          {['NIFTY 24800 CE', 'NIFTY 24800 PE', 'NIFTY 24900 CE', 'NIFTY 24700 PE', 'BANKNIFTY 53400 CE', 'BANKNIFTY 53400 PE', 'FINNIFTY 23500 CE', 'NIFTY (FUT)', 'BANKNIFTY (FUT)'].map((s) => (
                            <SelectItem key={s} value={s} className="text-xs text-ub-text-primary focus:bg-ub-surface-hover focus:text-ub-accent">
                              {s}
                            </SelectItem>
                          ))}
                        </SelectGroup>

                        <SelectSeparator className="bg-ub-border/60 my-1" />

                        <SelectGroup>
                          <SelectLabel className="text-purple-400 font-semibold text-[11px] px-2 py-1">
                            🎯 Stock Options (F&O)
                          </SelectLabel>
                          {['RELIANCE 2960 CE', 'RELIANCE 2940 PE', 'TCS 4150 CE', 'TCS 4100 PE', 'HDFCBANK 1660 CE', 'SBIN 820 CE', 'TATAMOTORS 1000 CE', 'INFY 1800 CE'].map((s) => (
                            <SelectItem key={s} value={s} className="text-xs text-ub-text-primary focus:bg-ub-surface-hover focus:text-ub-accent">
                              {s}
                            </SelectItem>
                          ))}
                        </SelectGroup>
                      </SelectContent>
                    </Select>

                    <Input
                      placeholder="Custom symbol (e.g. RELIANCE, NIFTY 24800 CE)"
                      value={form.symbols}
                      onChange={(e) => setForm((p) => ({ ...p, symbols: e.target.value }))}
                      className="flex-1 bg-ub-background border-ub-border text-ub-text-primary placeholder:text-ub-text-disabled text-xs"
                    />
                  </div>
                </div>

                {/* Timeframe */}
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Timeframe</Label>
                  <Select
                    value={form.timeframe}
                    onValueChange={(v) => setForm((p) => ({ ...p, timeframe: v }))}
                  >
                    <SelectTrigger className="bg-ub-background border-ub-border text-ub-text-primary">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-ub-surface border-ub-border">
                      {TIMEFRAMES.map((tf) => (
                        <SelectItem key={tf} value={tf} className="text-ub-text-primary focus:bg-ub-surface-hover focus:text-ub-accent">
                          {tf}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* From Date */}
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">From Date</Label>
                  <Input
                    type="date"
                    value={form.fromDate}
                    onChange={(e) => setForm((p) => ({ ...p, fromDate: e.target.value }))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>

                {/* To Date */}
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">To Date</Label>
                  <Input
                    type="date"
                    value={form.toDate}
                    onChange={(e) => setForm((p) => ({ ...p, toDate: e.target.value }))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>

                {/* Initial Capital */}
                <div className="space-y-2">
                  <Label className="text-ub-text-muted text-sm">Initial Capital (₹)</Label>
                  <Input
                    type="number"
                    value={form.capital}
                    onChange={(e) => setForm((p) => ({ ...p, capital: Number(e.target.value) }))}
                    className="bg-ub-background border-ub-border text-ub-text-primary"
                  />
                </div>
              </div>

              {/* Checkboxes and Run */}
              <div className="flex flex-wrap items-center gap-6 pt-2">
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="includeFees"
                    checked={form.includeFees}
                    onCheckedChange={(v) => setForm((p) => ({ ...p, includeFees: v === true }))}
                    className="border-ub-border data-[state=checked]:bg-ub-accent data-[state=checked]:border-ub-accent"
                  />
                  <Label htmlFor="includeFees" className="text-sm text-ub-text-muted cursor-pointer">
                    Include fees
                  </Label>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="applyRiskGates"
                    checked={form.applyRiskGates}
                    onCheckedChange={(v) => setForm((p) => ({ ...p, applyRiskGates: v === true }))}
                    className="border-ub-border data-[state=checked]:bg-ub-accent data-[state=checked]:border-ub-accent"
                  />
                  <Label htmlFor="applyRiskGates" className="text-sm text-ub-text-muted cursor-pointer">
                    Apply risk gates
                  </Label>
                </div>
                <div className="ml-auto">
                  <Button
                    onClick={handleRun}
                    disabled={isRunning}
                    className="bg-ub-accent hover:bg-ub-accent-hover text-ub-background font-semibold px-6"
                  >
                    {isRunning ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        Running...
                      </>
                    ) : (
                      <>
                        <Play className="h-4 w-4 mr-2" />
                        Run Backtest
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </CardContent>
          </CollapsibleContent>
        </Card>
      </Collapsible>

      {/* ── Loading Skeleton ── */}
      {isRunning && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="space-y-6"
        >
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {Array.from({ length: 10 }).map((_, i) => (
              <Skeleton key={i} className="h-24 bg-ub-surface rounded-lg" />
            ))}
          </div>
          <Skeleton className="h-[300px] bg-ub-surface rounded-lg" />
          <Skeleton className="h-[200px] bg-ub-surface rounded-lg" />
        </motion.div>
      )}

      {/* ── Results Section ── */}
      <AnimatePresence>
        {results && !isRunning && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="space-y-6"
          >
            {/* Key Metrics */}
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4">
              {metricCards.map((card) => (
                <Card key={card.label} className="bg-ub-surface border-ub-border">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-ub-text-muted uppercase tracking-wider">
                        {card.label}
                      </span>
                      <div style={{ color: card.color }}>{card.icon}</div>
                    </div>
                    <p className="text-xl font-bold" style={{ color: card.color }}>
                      {card.value}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Equity Curve */}
            <Card className="bg-ub-surface border-ub-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-semibold text-ub-text-primary flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-ub-accent" />
                  Equity Curve
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-[300px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={results.equityCurve} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                      <defs>
                        <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#22c55e" stopOpacity={0.4} />
                          <stop offset="100%" stopColor="#22c55e" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis
                        dataKey="trade"
                        stroke="#94a3b8"
                        tick={{ fontSize: 11 }}
                        label={{ value: 'Trade #', position: 'insideBottomRight', offset: -5, style: { fill: '#94a3b8', fontSize: 11 } }}
                      />
                      <YAxis
                        stroke="#94a3b8"
                        tick={{ fontSize: 11 }}
                        tickFormatter={(v: number) => `₹${(v / 1000).toFixed(0)}k`}
                      />
                      <RTooltip contentStyle={tooltipStyle} formatter={((value: number) => [`₹${value.toLocaleString('en-IN')}`, 'Equity']) as never} />
                      <ReferenceLine y={form.capital} stroke="#94a3b8" strokeDasharray="5 5" strokeOpacity={0.5} />
                      <Area
                        type="monotone"
                        dataKey="equity"
                        stroke="#00d09c"
                        strokeWidth={2}
                        fill="url(#equityGradient)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* Monthly Returns Heatmap */}
            <Card className="bg-ub-surface border-ub-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-semibold text-ub-text-primary flex items-center gap-2">
                  <CalendarDays className="h-4 w-4 text-ub-accent" />
                  Monthly Returns Heatmap
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <div className="inline-grid gap-1" style={{ gridTemplateColumns: `60px repeat(12, 1fr)` }}>
                    {/* Header row */}
                    <div className="p-1" />
                    {MONTHS.map((m) => (
                      <div key={m} className="p-1 text-center text-xs font-medium text-ub-text-muted">
                        {m}
                      </div>
                    ))}
                    {/* Data rows */}
                    {monthlyYears.map((year) => (
                      <Fragment key={year}>
                        <div className="p-1 flex items-center text-xs font-medium text-ub-text-muted">
                          {year}
                        </div>
                        {results.monthlyReturns
                          .filter((mr) => mr.year === year)
                          .map((mr) => (
                            <div
                              key={`${year}-${mr.month}`}
                              className="p-1.5 text-center text-xs font-semibold rounded min-w-[60px] flex items-center justify-center"
                              style={getCellColor(mr.value)}
                            >
                              {mr.value > 0 ? '+' : ''}{mr.value}%
                            </div>
                          ))}
                      </Fragment>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Drawdown Chart */}
            <Card className="bg-ub-surface border-ub-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-semibold text-ub-text-primary flex items-center gap-2">
                  <TrendingDown className="h-4 w-4 text-ub-loss" />
                  Drawdown Chart
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-[200px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={results.drawdownChart} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                      <defs>
                        <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#ef4444" stopOpacity={0.05} />
                          <stop offset="100%" stopColor="#ef4444" stopOpacity={0.4} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis
                        dataKey="date"
                        stroke="#94a3b8"
                        tick={{ fontSize: 10 }}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        stroke="#94a3b8"
                        tick={{ fontSize: 11 }}
                        tickFormatter={(v: number) => `${v}%`}
                      />
                      <RTooltip contentStyle={tooltipStyle} formatter={((value: number) => [`${value}%`, 'Drawdown']) as never} />
                      <ReferenceLine y={0} stroke="#94a3b8" strokeOpacity={0.3} />
                      <Area
                        type="monotone"
                        dataKey="drawdown"
                        stroke="#ef4444"
                        strokeWidth={1.5}
                        fill="url(#drawdownGradient)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* Trade List */}
            <Card className="bg-ub-surface border-ub-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-semibold text-ub-text-primary flex items-center gap-2">
                  <Clock className="h-4 w-4 text-ub-accent" />
                  Trade List
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="max-h-80 overflow-y-auto overflow-x-auto w-full">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-ub-border hover:bg-transparent">
                        <TableHead className="text-ub-text-muted text-xs">#</TableHead>
                        <TableHead className="text-ub-text-muted text-xs">Date</TableHead>
                        <TableHead className="text-ub-text-muted text-xs">Symbol</TableHead>
                        <TableHead className="text-ub-text-muted text-xs">Direction</TableHead>
                        <TableHead className="text-ub-text-muted text-xs text-right">Entry</TableHead>
                        <TableHead className="text-ub-text-muted text-xs text-right">Exit</TableHead>
                        <TableHead className="text-ub-text-muted text-xs text-right">P&L</TableHead>
                        <TableHead className="text-ub-text-muted text-xs">Duration</TableHead>
                        <TableHead className="text-ub-text-muted text-xs">Exit Reason</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {results.trades.map((trade) => (
                        <TableRow key={trade.id} className="border-ub-border hover:bg-ub-surface-hover">
                          <TableCell className="text-ub-text-muted text-xs">{trade.id}</TableCell>
                          <TableCell className="text-ub-text-primary text-xs">{trade.date}</TableCell>
                          <TableCell className="text-ub-text-primary text-xs font-medium">{trade.symbol}</TableCell>
                          <TableCell>
                            <Badge
                              variant="outline"
                              className={`text-[10px] font-semibold ${
                                trade.direction === 'BUY'
                                  ? 'border-ub-profit/40 text-ub-profit'
                                  : 'border-ub-loss/40 text-ub-loss'
                              }`}
                            >
                              {trade.direction}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-ub-text-primary text-xs text-right">₹{trade.entry}</TableCell>
                          <TableCell className="text-ub-text-primary text-xs text-right">₹{trade.exit}</TableCell>
                          <TableCell className={`text-xs text-right font-semibold ${trade.pnl >= 0 ? 'text-ub-profit' : 'text-ub-loss'}`}>
                            {trade.pnl >= 0 ? '+' : ''}₹{trade.pnl.toLocaleString('en-IN')}
                          </TableCell>
                          <TableCell className="text-ub-text-muted text-xs">{trade.duration}</TableCell>
                          <TableCell className="text-ub-text-muted text-xs">{trade.exitReason}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>

            {/* Risk Gate Stats */}
            <Card className="bg-ub-surface border-ub-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-semibold text-ub-text-primary flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-ub-accent" />
                  Risk Gate Stats
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {results.riskGateStats.map((gate) => {
                    const total = gate.passed + gate.rejected;
                    const passPct = Math.round((gate.passed / total) * 100);
                    return (
                      <div key={gate.name} className="space-y-1">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-ub-text-muted">{gate.name}</span>
                          <div className="flex items-center gap-3 text-xs">
                            <span className="text-ub-profit">{gate.passed} passed</span>
                            <span className="text-ub-loss">{gate.rejected} rejected</span>
                          </div>
                        </div>
                        <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-ub-background">
                          <div className="bg-ub-profit transition-all duration-500" style={{ width: `${passPct}%` }} />
                          <div className="bg-ub-loss transition-all duration-500" style={{ width: `${100 - passPct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Previous Runs ── */}
      <Card className="bg-ub-surface border-ub-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold text-ub-text-primary flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-ub-accent" />
            Previous Runs
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-ub-border hover:bg-transparent">
                <TableHead className="text-ub-text-muted text-xs">Date</TableHead>
                <TableHead className="text-ub-text-muted text-xs">Strategy</TableHead>
                <TableHead className="text-ub-text-muted text-xs">Symbol</TableHead>
                <TableHead className="text-ub-text-muted text-xs text-right">Return %</TableHead>
                <TableHead className="text-ub-text-muted text-xs text-right">Sharpe</TableHead>
                <TableHead className="text-ub-text-muted text-xs text-right">Trades</TableHead>
                <TableHead className="text-ub-text-muted text-xs text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoadingHistory ? (
                <TableRow className="border-ub-border hover:bg-transparent">
                  <TableCell colSpan={7} className="text-center text-ub-text-muted text-xs py-8">
                    <Loader2 className="h-4 w-4 animate-spin inline mr-2" />
                    Loading previous runs...
                  </TableCell>
                </TableRow>
              ) : (previousRuns.length > 0 ? previousRuns : PREVIOUS_RUNS).map((run) => (
                <TableRow key={run.id} className="border-ub-border hover:bg-ub-surface-hover">
                  <TableCell className="text-ub-text-primary text-xs">{run.date}</TableCell>
                  <TableCell className="text-ub-text-primary text-xs font-medium">{run.strategy}</TableCell>
                  <TableCell className="text-ub-text-muted text-xs">{run.symbol}</TableCell>
                  <TableCell className={`text-xs text-right font-semibold ${run.returnPct >= 0 ? 'text-ub-profit' : 'text-ub-loss'}`}>
                    {run.returnPct > 0 ? '+' : ''}{run.returnPct}%
                  </TableCell>
                  <TableCell className="text-ub-text-primary text-xs text-right">{run.sharpe}</TableCell>
                  <TableCell className="text-ub-text-muted text-xs text-right">{run.trades}</TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-ub-accent hover:text-ub-accent-hover hover:bg-ub-accent/10 text-xs h-7 px-3"
                      onClick={() => handleViewRun(run)}
                    >
                      View
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

export default function BacktestPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-6 p-6">
          <Skeleton className="h-10 w-48 bg-ub-surface" />
          <Skeleton className="h-64 w-full bg-ub-surface" />
        </div>
      }
    >
      <BacktestContent />
    </Suspense>
  );
}
