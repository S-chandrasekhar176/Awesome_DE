'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { useDashboard, useStrategies } from '@/hooks/useApi';
import { useEngine } from '@/hooks/useEngine';
import { useEngine as useEngineStore, useStore, type MarketRegime } from '@/lib/store';
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

// Modular Dashboard Components
import { DashboardData, Position, Trade } from '@/components/dashboard/DashboardTypes';
import DashboardStatsBanner from '@/components/dashboard/DashboardStatsBanner';
import CapitalOverviewCard from '@/components/dashboard/CapitalOverviewCard';
import EngineStatusCard from '@/components/dashboard/EngineStatusCard';
import OpenPositionsCard from '@/components/dashboard/OpenPositionsCard';
import MarketRegimeCard from '@/components/dashboard/MarketRegimeCard';
import QuickSignalsCard from '@/components/dashboard/QuickSignalsCard';
import MarketTimerCard from '@/components/dashboard/MarketTimerCard';
import RecentTradesCard from '@/components/dashboard/RecentTradesCard';
import DashboardSkeleton from '@/components/dashboard/DashboardSkeleton';

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
      } catch {}
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
      } catch {}

      fetch('/api/settings')
        .then((r) => r.json())
        .then((d) => {
          if (d?.config?.capital?.virtual_capital) {
            setConfiguredCapital(d.config.capital.virtual_capital);
          }
        })
        .catch(() => {});
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
      engineStore.setNifty(raw.nifty_price, raw.nifty_change || 0.0);
    }
    if (raw.engine?.broker || raw.broker) {
      engineStore.setActiveBroker(raw.engine?.broker || raw.broker);
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

    // 5. Dynamic Win Rate Engine
    const totalTradesCount = storedTrades.length;
    const winningTradesCount = storedTrades.filter((t) => t.pnl > 0).length;
    const allTimeWinRate = totalTradesCount > 0 ? Math.round((winningTradesCount / totalTradesCount) * 100) : 0;

    const todayDateStr = new Date().toDateString();
    const todayTrades = storedTrades.filter((t) => {
      if (!t.exitedAt) return true;
      return new Date(t.exitedAt).toDateString() === todayDateStr;
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
  }, [apiData, stratData, storedPositions, storedTrades, confirmedIds, skippedIds, engineStore.status, engineStore.mode, engineStore.regime, configuredCapital]);

  const engineStatus = (engineStore.status || data.engineStatus || 'stopped') as 'running' | 'stopped' | 'paused' | 'error';
  const engineMode = (engineStore.mode || data.engineMode || 'paper') as 'paper' | 'live';
  const activeBrokerId = engineStore.activeBroker;
  const startedAt = engineStore.startedAt;
  const regime = (engineStore.regime || data.regime || 'sideways') as MarketRegime;
  const regimeConf = data.regimeConfidence;

  const [engineDialogOpen, setEngineDialogOpen] = useState(false);

  // Heartbeat: simulate a pulse every 5s when engine is running
  useEffect(() => {
    if (engineStatus !== 'running') return;
    const interval = setInterval(() => {
      useStore.getState().engine.heartbeat();
    }, 5000);
    return () => clearInterval(interval);
  }, [engineStatus]);

  const handleStopEngine = useCallback(async () => {
    useStore.getState().engine.stop();
    try {
      await engine.stopAsync();
    } catch (err) {
      console.warn('Backend engine stop error:', err);
    }
  }, [engine]);

  const handleEngineStart = useCallback(async (mode: 'paper' | 'live', brokerId: string) => {
    useStore.getState().engine.start(mode, brokerId);
    setEngineDialogOpen(false);
    try {
      await engine.startAsync({ mode, broker: brokerId });
    } catch (err) {
      console.warn('Backend engine start error:', err);
    }
  }, [engine]);

  return (
    <TooltipProvider delayDuration={300}>
      {isLoading ? (
        <DashboardSkeleton />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {/* SECTION 1: TOP STATS ROW */}
          <DashboardStatsBanner data={data} />

          {/* SECTION 2: CAPITAL OVERVIEW (3 cols) & ENGINE STATUS (2 cols on xl) */}
          <CapitalOverviewCard data={data} />

          <EngineStatusCard
            engineStatus={engineStatus}
            engineMode={engineMode}
            activeBrokerId={activeBrokerId}
            startedAt={startedAt}
            errorMessage={engineStore.errorMessage}
            onOpenStartDialog={() => setEngineDialogOpen(true)}
            onStopEngine={handleStopEngine}
          />

          {/* SECTION 3: OPEN POSITIONS TABLE */}
          <OpenPositionsCard positions={data.positions} />

          {/* SECTION 4: MARKET REGIME, QUICK SIGNALS, MARKET TIMER */}
          <MarketRegimeCard
            regime={regime}
            regimeConfidence={regimeConf}
            activeStrategies={data.activeStrategies}
          />

          <QuickSignalsCard
            signalsGenerated={data.signalsGenerated}
            signalsConfirmed={data.signalsConfirmed}
            signalsSkipped={data.signalsSkipped}
          />

          <MarketTimerCard />

          {/* SECTION 5: LIVE SCANNING & STRATEGY TELEMETRY */}
          <div className="md:col-span-2 xl:col-span-4">
            <ScanTelemetryCard engineState={engineStatus} activeBroker={activeBrokerId || 'paper'} />
          </div>

          {/* SECTION 6: RECENT TRADES */}
          <RecentTradesCard trades={data.recentTrades} />
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
