'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Activity,
  ShieldCheck,
  ShieldAlert,
  Radio,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Cpu,
  Layers,
  Search,
  Filter,
} from 'lucide-react';
import { getEngineScanTelemetry, type ScanTelemetryData, type ScanTelemetryEvent } from '@/lib/api';
import { theme } from '@/styles/theme';

import { useEngine as useEngineStore, useStore } from '@/lib/store';

interface ScanTelemetryCardProps {
  engineState?: string;
  activeBroker?: string;
}

export default function ScanTelemetryCard({ engineState = 'stopped', activeBroker = 'paper' }: ScanTelemetryCardProps) {
  const storeTelemetry = useStore((s) => s.engine.scanTelemetry);
  const storeActiveBroker = useStore((s) => s.engine.activeBroker);
  const [telemetry, setTelemetry] = useState<ScanTelemetryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<'ALL' | 'PASSED' | 'REJECTED' | 'NO_SETUP'>('ALL');
  const [lastUpdated, setLastUpdated] = useState<string>('—');
  const [isWsLive, setIsWsLive] = useState(false);

  // Sync with store when new WebSocket event arrives
  useEffect(() => {
    if (storeTelemetry) {
      setTelemetry((prev) => ({
        ...(prev || {}),
        ...storeTelemetry,
      }));
      setLastUpdated(new Date().toLocaleTimeString('en-IN', { hour12: false }));
      setIsWsLive(true);
    }
  }, [storeTelemetry]);

  const fetchTelemetry = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getEngineScanTelemetry();
      if (data) {
        setTelemetry(data);
        setLastUpdated(new Date().toLocaleTimeString('en-IN', { hour12: false }));
      }
    } catch {
      // Fallback or offline state handled gracefully
    } finally {
      setLoading(false);
    }
  }, []);

  // Poll every 5 seconds while engine is active as a fallback, 15s otherwise
  useEffect(() => {
    fetchTelemetry();
    const intervalMs = engineState === 'running' || engineState === 'scanning' ? 5000 : 15000;
    const timer = setInterval(fetchTelemetry, intervalMs);
    return () => clearInterval(timer);
  }, [fetchTelemetry, engineState]);

  const recentEvents = telemetry?.recent_events || [];
  const filteredEvents = recentEvents.filter((ev) => {
    if (filter === 'ALL') return true;
    return ev.status === filter;
  });

  const gateRejections = telemetry?.rejections_by_gate || {};
  const gateEntries = Object.entries(gateRejections);

  const isEngineActive = engineState === 'running' || engineState === 'scanning';

  return (
    <Card className="bg-ub-surface border-ub-border overflow-hidden">
      <CardHeader className="pb-3 border-b border-ub-border/60">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-ub-accent/10 border border-ub-accent/20 flex items-center justify-center text-ub-accent">
              <Cpu size={16} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <CardTitle className="text-base font-semibold text-ub-text-primary">
                  Live Strategy &amp; Scan Telemetry
                </CardTitle>
                <Badge
                  variant="outline"
                  className={`text-[10px] font-semibold flex items-center gap-1 ${
                    isEngineActive
                      ? 'border-ub-profit/40 text-ub-profit bg-ub-profit/10 animate-pulse'
                      : 'border-ub-text-disabled/40 text-ub-text-disabled bg-ub-text-disabled/10'
                  }`}
                >
                  <Radio size={10} />
                  {isEngineActive ? 'SCANNING ACTIVE' : 'ENGINE IDLE'}
                </Badge>
              </div>
              <p className="text-[11px] text-ub-text-muted mt-0.5">
                Active Broker: <span className="text-ub-accent font-medium capitalize">{telemetry?.broker || storeActiveBroker || activeBroker}</span> • Mode: <span className="uppercase text-ub-text-primary font-medium">{telemetry?.mode || 'paper'}</span> • Updated: {lastUpdated} {isWsLive && <span className="text-ub-profit ml-1.5 font-bold">● WS LIVE</span>}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={fetchTelemetry}
              disabled={loading}
              className="h-8 px-2.5 text-xs border-ub-border text-ub-text-muted hover:text-ub-text-primary hover:bg-ub-surface-active"
            >
              <RefreshCw size={12} className={`mr-1.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-4 space-y-4">
        {/* Metric Summary Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="p-3 rounded-lg bg-ub-background border border-ub-border/80">
            <div className="flex items-center justify-between text-ub-text-muted text-xs mb-1">
              <span>Symbols Scanned</span>
              <Search size={13} className="text-ub-accent" />
            </div>
            <div className="text-xl font-bold text-ub-text-primary">
              {telemetry?.symbols_scanned || 0}
            </div>
            <div className="text-[10px] text-ub-text-disabled mt-0.5">
              Across {telemetry?.total_scans || 0} scan iterations
            </div>
          </div>

          <div className="p-3 rounded-lg bg-ub-background border border-ub-border/80">
            <div className="flex items-center justify-between text-ub-text-muted text-xs mb-1">
              <span>Signals Generated</span>
              <Layers size={13} className="text-blue-400" />
            </div>
            <div className="text-xl font-bold text-ub-text-primary">
              {telemetry?.signals_generated || 0}
            </div>
            <div className="text-[10px] text-ub-text-disabled mt-0.5">
              Active strategies: {telemetry?.active_strategies?.length || 0}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-ub-background border border-ub-profit/30 bg-ub-profit/5">
            <div className="flex items-center justify-between text-ub-profit text-xs mb-1">
              <span className="font-medium">Passed Risk Gates</span>
              <ShieldCheck size={14} className="text-ub-profit" />
            </div>
            <div className="text-xl font-bold text-ub-profit">
              {telemetry?.signals_passed || 0}
            </div>
            <div className="text-[10px] text-ub-profit/80 mt-0.5">
              Converted to pending opportunities
            </div>
          </div>

          <div className="p-3 rounded-lg bg-ub-background border border-ub-loss/30 bg-ub-loss/5">
            <div className="flex items-center justify-between text-ub-loss text-xs mb-1">
              <span className="font-medium">Blocked by Gates</span>
              <ShieldAlert size={14} className="text-ub-loss" />
            </div>
            <div className="text-xl font-bold text-ub-loss">
              {telemetry?.signals_rejected || 0}
            </div>
            <div className="text-[10px] text-ub-loss/80 mt-0.5">
              Filtered safely by Risk Engine
            </div>
          </div>
        </div>

        {/* Risk Gate Rejections Breakdown */}
        {gateEntries.length > 0 && (
          <div className="p-3 rounded-lg bg-ub-background/80 border border-ub-border">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-ub-text-primary mb-2">
              <Filter size={13} className="text-ub-warning" />
              <span>Risk Gate Blockage Breakdown (Why Signals Were Blocked):</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {gateEntries.map(([gateName, count]) => (
                <div
                  key={gateName}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-ub-surface border border-ub-warning/30 text-xs text-ub-text-primary"
                >
                  <span className="font-mono text-ub-warning font-medium">{gateName}</span>
                  <Badge className="bg-ub-warning/20 text-ub-warning border-none px-1.5 py-0 text-[10px] font-bold">
                    {count}
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Live Scan Feed Header & Filter Tabs */}
        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Activity size={14} className="text-ub-accent" />
              <span className="text-xs font-semibold text-ub-text-primary">
                Live Scan Activity Stream (Last 50 Events)
              </span>
            </div>

            <div className="flex items-center gap-1 bg-ub-background p-0.5 rounded-md border border-ub-border">
              {(['ALL', 'PASSED', 'REJECTED', 'NO_SETUP'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setFilter(tab)}
                  className={`text-[11px] px-2 py-0.5 rounded transition-all ${
                    filter === tab
                      ? 'bg-ub-accent/15 text-ub-accent font-semibold'
                      : 'text-ub-text-muted hover:text-ub-text-primary'
                  }`}
                >
                  {tab === 'NO_SETUP' ? 'NO TRIGGER' : tab}
                </button>
              ))}
            </div>
          </div>

          {/* Activity Feed Table / List */}
          <ScrollArea className="h-64 rounded-lg border border-ub-border bg-ub-background">
            {filteredEvents.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-center p-4">
                <Search size={24} className="text-ub-text-disabled mb-2" />
                <p className="text-xs text-ub-text-muted">
                  {isEngineActive
                    ? 'No matching scan activity recorded yet in this cycle. Scanning in progress...'
                    : 'Start the engine to see real-time strategy scan evaluations, gate passes, and rejection logs.'}
                </p>
              </div>
            ) : (
              <div className="divide-y divide-ub-border/50">
                {filteredEvents.map((ev, idx) => {
                  const isPassed = ev.status === 'PASSED';
                  const isRejected = ev.status === 'REJECTED';
                  const isBuy = ev.direction === 'BUY';

                  return (
                    <div
                      key={`${ev.time}-${ev.symbol}-${ev.strategy}-${idx}`}
                      className="p-2.5 hover:bg-ub-surface/60 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs"
                    >
                      <div className="flex items-start sm:items-center gap-2.5">
                        <span className="font-mono text-[11px] text-ub-text-disabled shrink-0 pt-0.5 sm:pt-0">
                          {ev.time}
                        </span>

                        {isPassed ? (
                          <CheckCircle2 size={15} className="text-ub-profit shrink-0 mt-0.5 sm:mt-0" />
                        ) : isRejected ? (
                          <XCircle size={15} className="text-ub-loss shrink-0 mt-0.5 sm:mt-0" />
                        ) : (
                          <AlertCircle size={15} className="text-ub-text-disabled shrink-0 mt-0.5 sm:mt-0" />
                        )}

                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="font-semibold text-ub-text-primary">{ev.symbol}</span>
                          <Badge
                            variant="outline"
                            className="text-[10px] font-mono px-1.5 py-0 bg-ub-surface border-ub-border text-ub-text-primary"
                          >
                            {ev.strategy}
                          </Badge>
                          {ev.direction && ev.direction !== '—' && (
                            <Badge
                              className={`text-[9px] px-1.5 py-0 font-bold border-none ${
                                isBuy ? 'bg-ub-profit/15 text-ub-profit' : 'bg-ub-loss/15 text-ub-loss'
                              }`}
                            >
                              {ev.direction}
                            </Badge>
                          )}
                          {ev.price && ev.price > 0 && (
                            <span className="text-[11px] text-ub-text-muted">₹{ev.price}</span>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 pl-7 sm:pl-0">
                        {ev.gate && ev.gate !== '—' && (
                          <Badge
                            variant="outline"
                            className={`text-[10px] font-mono px-1.5 py-0 ${
                              isPassed
                                ? 'border-ub-profit/30 text-ub-profit bg-ub-profit/5'
                                : 'border-ub-loss/30 text-ub-loss bg-ub-loss/5'
                            }`}
                          >
                            {ev.gate}
                          </Badge>
                        )}
                        <span
                          className={`text-[11px] truncate max-w-xs ${
                            isPassed
                              ? 'text-ub-profit font-medium'
                              : isRejected
                              ? 'text-ub-loss'
                              : 'text-ub-text-disabled'
                          }`}
                          title={ev.reason}
                        >
                          {ev.reason || (isPassed ? 'Passed all risk gates' : 'Conditions not met')}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </ScrollArea>
        </div>
      </CardContent>
    </Card>
  );
}
