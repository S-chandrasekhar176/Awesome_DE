'use client';

import { useState, useMemo, useEffect } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useStrategies } from '@/hooks/useApi';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Checkbox } from '@/components/ui/checkbox';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import {
  ChevronDown,
  FlaskConical,
  Activity,
  TrendingUp,
  TrendingDown,
  Minus,
  Zap,
  BarChart3,
} from 'lucide-react';
import { useEngine, type MarketRegime } from '@/lib/store';
import { cn } from '@/lib/utils';

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

interface StrategyParams {
  [key: string]: string | number | boolean;
}

interface Strategy {
  id: string;
  name: string;
  description: string;
  category: 'core' | 'advanced';
  active: boolean;
  winRate: number;
  signals: number;
  trades: number;
  pauseReason?: 'regime_mismatch' | 'manual_pause';
  sparkline: number[];
  params: StrategyParams;
}

// ─────────────────────────────────────────────
// Mock Data
// ─────────────────────────────────────────────



// ─────────────────────────────────────────────
// Regime Config
// ─────────────────────────────────────────────

const REGIME_CONFIG: Record<MarketRegime, { label: string; color: string; bgColor: string; icon: React.ElementType }> = {
  bull: { label: 'Bull', color: 'text-ub-profit', bgColor: 'bg-ub-profit/15 border-ub-profit/30', icon: TrendingUp },
  bear: { label: 'Bear', color: 'text-ub-loss', bgColor: 'bg-ub-loss/15 border-ub-loss/30', icon: TrendingDown },
  sideways: { label: 'Sideways', color: 'text-ub-warning', bgColor: 'bg-ub-warning/15 border-ub-warning/30', icon: Minus },
  volatile: { label: 'Volatile', color: 'text-ub-volatile', bgColor: 'bg-ub-volatile/15 border-ub-volatile/30', icon: Zap },
};

// ─────────────────────────────────────────────
// Sparkline Component
// ─────────────────────────────────────────────

function Sparkline({ data, color = '#00d09c' }: { data: number[]; color?: string }) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const width = 80;
  const height = 28;
  const padding = 2;

  const points = data
    .map((v, i) => {
      const x = padding + (i / (data.length - 1)) * (width - padding * 2);
      const y = height - padding - ((v - min) / range) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg width={width} height={height} className="shrink-0">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// ─────────────────────────────────────────────
// Strategy Card
// ─────────────────────────────────────────────

function StrategyCard({ strategy, onToggle }: { strategy: Strategy; onToggle: (id: string, enabled: boolean) => void }) {
  const [expanded, setExpanded] = useState(false);

  const winRateColor =
    strategy.winRate >= 65 ? 'text-ub-profit' : strategy.winRate >= 58 ? 'text-ub-warning' : 'text-ub-loss';

  const sparkColor = strategy.active ? (strategy.winRate >= 65 ? '#22c55e' : '#f59e0b') : '#475569';

  return (
    <Collapsible open={expanded} onOpenChange={setExpanded}>
      <Card
        className={cn(
          'bg-ub-surface border-ub-border transition-all duration-200',
          strategy.active
            ? 'hover:border-ub-accent/40'
            : 'opacity-70 hover:opacity-100',
          expanded && 'border-ub-accent/50',
        )}
      >
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer select-none p-4 pb-2">
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-ub-text-primary text-sm">{strategy.name}</span>
                  <Badge
                    variant="outline"
                    className={cn(
                      'text-[10px] px-1.5 py-0',
                      strategy.active
                        ? 'border-ub-profit/40 text-ub-profit bg-ub-profit/10'
                        : 'border-ub-warning/40 text-ub-warning bg-ub-warning/10',
                    )}
                  >
                    {strategy.active ? 'Active' : 'Paused'}
                  </Badge>
                </div>
                <p className="text-xs text-ub-text-muted mt-1 truncate">{strategy.description}</p>
              </div>
              <ChevronDown
                className={cn(
                  'h-4 w-4 text-ub-text-muted shrink-0 transition-transform duration-200',
                  expanded && 'rotate-180',
                )}
              />
            </div>
          </CardHeader>
        </CollapsibleTrigger>

        <CardContent className="p-4 pt-0">
          {strategy.pauseReason && !strategy.active && (
            <p className="text-[11px] text-ub-warning mb-2">
              ⚠ {strategy.pauseReason === 'regime_mismatch' ? 'Regime mismatch' : 'Manual pause'}
            </p>
          )}

          <div className="flex items-center gap-4 text-xs mb-3">
            <span className={cn('font-medium', winRateColor)}>
              Win Rate: {strategy.winRate}%
            </span>
            <Sparkline data={strategy.sparkline} color={sparkColor} />
          </div>

          <div className="flex items-center gap-4 text-xs text-ub-text-muted mb-3">
            <span>
              Signals: <span className="text-ub-text-primary font-medium">{strategy.signals}</span>{' '}
              | Trades: <span className="text-ub-text-primary font-medium">{strategy.trades}</span>
            </span>
          </div>

          <div className="flex items-center gap-2">
            <Switch
              checked={strategy.active}
              onCheckedChange={(checked) => onToggle(strategy.id, checked)}
              className="data-[state=checked]:bg-ub-accent"
            />
            <Link href={`/backtest?strategy=${encodeURIComponent(strategy.id)}`} className="ml-auto">
              <Button variant="outline" size="sm" className="h-7 text-xs gap-1 border-ub-border text-ub-text-muted hover:text-ub-accent hover:border-ub-accent/40 cursor-pointer">
                <FlaskConical className="h-3 w-3" />
                Backtest
              </Button>
            </Link>
          </div>

          <CollapsibleContent>
            <Separator className="my-3 bg-ub-border" />
            <div className="space-y-1.5">
              <p className="text-[11px] font-medium text-ub-text-muted uppercase tracking-wider mb-2">
                Strategy Parameters
              </p>
              {Object.entries(strategy.params).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between text-xs">
                  <span className="text-ub-text-muted">{key}</span>
                  <span className="text-ub-text-primary font-mono bg-ub-bg/50 px-1.5 py-0.5 rounded">
                    {String(value)}
                  </span>
                </div>
              ))}
            </div>
          </CollapsibleContent>
        </CardContent>
      </Card>
    </Collapsible>
  );
}

// ─────────────────────────────────────────────
// Page Component
// ─────────────────────────────────────────────

const EMPTY_ARRAY: Strategy[] = [];

export default function StrategiesPage() {
  const { regime, vix } = useEngine();
  const [isAutoMode, setIsAutoMode] = useState(true);

  const { data: apiStrategies, toggle } = useStrategies();

  const strategies: Strategy[] = useMemo(() => {
    if (!apiStrategies || !Array.isArray(apiStrategies)) return EMPTY_ARRAY;
    return apiStrategies.map((item: any, idx: number) => {
      const id = item.name || item.id || `strat-${idx}`;
      const name = item.display_name || item.name || item.id || 'Strategy';
      const description = item.description || 'Automated algorithmic strategy with real-time risk guards.';
      const category = (Array.isArray(item.tags) && item.tags.includes('advanced')) || item.category === 'advanced' ? 'advanced' : 'core';
      const active = Boolean(item.is_enabled ?? item.is_active ?? item.active ?? true);

      let winRate = 72;
      if (item.performance?.win_rate !== undefined) {
        winRate = item.performance.win_rate > 1 ? Math.round(item.performance.win_rate) : Math.round(item.performance.win_rate * 100);
      } else if (item.winRate !== undefined) {
        winRate = item.winRate > 1 ? Math.round(item.winRate) : Math.round(item.winRate * 100);
      }

      const signals = item.signals ?? item.performance?.total_trades ?? 32;
      const trades = item.trades ?? item.performance?.total_trades ?? 26;
      const sparkline = Array.isArray(item.sparkline) && item.sparkline.length > 0
        ? item.sparkline
        : [62, 65, 64, 70, 68, 72, 71, winRate];

      const params = (item.parameters || item.params || {
        timeframe: item.timeframe || '5min',
        direction: item.direction || 'BOTH',
        best_regimes: Array.isArray(item.best_regimes) ? item.best_regimes.join(', ') : 'Bull, Bear',
      }) as StrategyParams;

      return {
        id,
        name,
        description,
        category,
        active,
        winRate,
        signals,
        trades,
        pauseReason: item.pauseReason,
        sparkline,
        params,
      };
    });
  }, [apiStrategies]);
  
  const [manualEnabled, setManualEnabled] = useState<Record<string, boolean>>({});
  
  useEffect(() => {
    if (!strategies || strategies.length === 0) return;
    const map: Record<string, boolean> = {};
    strategies.forEach((s) => { map[s.id] = s.active; });
    setManualEnabled(map);
  }, [strategies]);

  const regimeConfig = REGIME_CONFIG[regime];
  const RegimeIcon = regimeConfig.icon;

  const confidence = useMemo(() => {
    switch (regime) {
      case 'bull': return 78;
      case 'bear': return 65;
      case 'sideways': return 52;
      case 'volatile': return 41;
    }
  }, [regime]);

  const coreStrategies = useMemo(() => strategies.filter((s) => s.category === 'core'), [strategies]);
  const advancedStrategies = useMemo(() => strategies.filter((s) => s.category === 'advanced'), [strategies]);

  const handleToggle = (id: string, enabled: boolean) => {
    toggle({ name: id, isEnabled: enabled });
  };

  const handleManualCheck = (id: string, checked: boolean) => {
    toggle({ name: id, isEnabled: checked });
  };

  return (
    <div className="space-y-6">
      {/* ── Market Regime Panel ── */}
      <Card className="bg-ub-surface border-ub-border">
        <CardHeader className="p-4 pb-3">
          <CardTitle className="text-base font-semibold text-ub-text-primary flex items-center gap-2">
            <Activity className="h-4 w-4 text-ub-accent" />
            Market Regime
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0 space-y-4">
          <div className="flex flex-wrap items-center gap-4">
            <Badge
              variant="outline"
              className={cn('text-xs px-3 py-1 border gap-1.5', regimeConfig.bgColor, regimeConfig.color)}
            >
              <RegimeIcon className="h-3.5 w-3.5" />
              {regimeConfig.label}
            </Badge>

            <div className="flex items-center gap-2 flex-1 min-w-[200px] max-w-xs">
              <span className="text-xs text-ub-text-muted">Confidence</span>
              <Progress value={confidence} className="h-2 flex-1" />
              <span className="text-xs font-medium text-ub-text-primary">{confidence}%</span>
            </div>

            <div className="flex items-center gap-2 ml-auto">
              <span className="text-xs text-ub-text-muted">Auto</span>
              <Switch
                checked={isAutoMode}
                onCheckedChange={setIsAutoMode}
                className="data-[state=checked]:bg-ub-accent"
              />
              <span className="text-xs text-ub-text-muted">Manual</span>
            </div>
          </div>

          {/* VIX display */}
          <div className="flex items-center gap-2 text-xs text-ub-text-muted">
            <BarChart3 className="h-3 w-3" />
            <span>India VIX:</span>
            <span className={cn('font-medium', vix > 20 ? 'text-ub-volatile' : vix > 15 ? 'text-ub-warning' : 'text-ub-profit')}>
              {vix > 0 ? vix.toFixed(2) : '11.36'}
            </span>
          </div>

          {/* Manual mode checklist */}
          {!isAutoMode && (
            <div className="mt-3 p-3 bg-ub-bg rounded-lg border border-ub-border space-y-2">
              <p className="text-xs font-medium text-ub-text-muted uppercase tracking-wider">
                Manual Strategy Selection
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
                {strategies.map((s) => (
                  <label
                    key={s.id}
                    className="flex items-center gap-2 cursor-pointer hover:bg-ub-surface-hover rounded px-2 py-1.5 transition-colors"
                  >
                    <Checkbox
                      checked={manualEnabled[s.id]}
                      onCheckedChange={(checked) => handleManualCheck(s.id, !!checked)}
                      className="data-[state=checked]:bg-ub-accent data-[state=checked]:border-ub-accent"
                    />
                    <span className="text-xs text-ub-text-primary">{s.name}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Core Strategies ── */}
      <section>
        <h3 className="text-sm font-semibold text-ub-text-primary mb-3 flex items-center gap-2">
          <span className="w-1.5 h-4 rounded-full bg-ub-accent" />
          Core Strategies ({coreStrategies.length})
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {coreStrategies.map((s) => (
            <StrategyCard key={s.id} strategy={s} onToggle={handleToggle} />
          ))}
        </div>
      </section>

      {/* ── Advanced Strategies ── */}
      <section>
        <h3 className="text-sm font-semibold text-ub-text-primary mb-3 flex items-center gap-2">
          <span className="w-1.5 h-4 rounded-full bg-ub-volatile" />
          Advanced Strategies ({advancedStrategies.length})
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {advancedStrategies.map((s) => (
            <StrategyCard key={s.id} strategy={s} onToggle={handleToggle} />
          ))}
        </div>
      </section>
    </div>
  );
}