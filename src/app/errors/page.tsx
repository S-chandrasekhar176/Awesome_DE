'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
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
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RTooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import {
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle2,
  XCircle,
  Loader2,
  RotateCcw,
  ArrowRight,
  Clock,
  Bug,
  ShieldAlert,
  ChevronLeft,
  ChevronRight,
  Activity,
  Zap,
  X,
} from 'lucide-react';
import { toast } from 'sonner';

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

type Severity = 'Critical' | 'Warning' | 'Info';
type RecoveryStatus = 'Attempting...' | 'Success' | 'Failed' | 'Not Available';

interface ActiveError {
  id: string;
  code: string;
  severity: Severity;
  description: string;
  rootCause: string;
  action: string;
  recoveryStatus: RecoveryStatus;
  timestamp: string;
}

interface ErrorHistoryEntry {
  id: string;
  time: string;
  code: string;
  type: string;
  severity: Severity;
  message: string;
  resolved: boolean;
}

interface ErrorTypeDistribution {
  name: string;
  value: number;
  color: string;
}

interface SeverityDistribution {
  name: string;
  count: number;
  color: string;
}

// ─────────────────────────────────────────────
// Mock Data
// ─────────────────────────────────────────────

const ACTIVE_ERRORS: ActiveError[] = [
  {
    id: 'active-1',
    code: 'ERR-2025-0810-0001',
    severity: 'Critical',
    description: 'WebSocket connection to broker API lost. All real-time price feeds are currently unavailable.',
    rootCause: 'Network timeout after 3 failed reconnection attempts to ws://broker-api:8080.',
    action: 'Check network connectivity. Restart broker gateway service. Verify API credentials have not expired.',
    recoveryStatus: 'Attempting...',
    timestamp: '2025-08-10 14:32:05',
  },
  {
    id: 'active-2',
    code: 'ERR-2025-0810-0002',
    severity: 'Critical',
    description: 'Order placement failed for RELIANCE BUY order. Order was rejected by the exchange.',
    rootCause: 'Insufficient margin available. Required: ₹1,25,000 | Available: ₹87,000.',
    action: 'Free up margin by closing positions or increase virtual capital allocation.',
    recoveryStatus: 'Failed',
    timestamp: '2025-08-10 13:15:42',
  },
  {
    id: 'active-3',
    code: 'ERR-2025-0810-0003',
    severity: 'Warning',
    description: 'Daily loss limit approaching threshold. Current loss: 2.4% of capital (limit: 3%).',
    rootCause: 'Three consecutive losing trades in BANKNIFTY options.',
    action: 'Review open positions. Consider tightening stop losses. Cool-off period may activate.',
    recoveryStatus: 'Not Available',
    timestamp: '2025-08-10 12:48:20',
  },
  {
    id: 'active-4',
    code: 'ERR-2025-0810-0004',
    severity: 'Warning',
    description: 'Signal confidence below minimum threshold for INFY. Signal score: 0.52 (minimum: 0.65).',
    rootCause: 'VIX spike causing high uncertainty. Strategy indicators conflicted on direction.',
    action: 'No action needed. Signal was correctly filtered out by risk gates.',
    recoveryStatus: 'Not Available',
    timestamp: '2025-08-10 11:22:17',
  },
  {
    id: 'active-5',
    code: 'ERR-2025-0810-0005',
    severity: 'Info',
    description: 'Engine auto-paused due to pre-market session. Scanning will resume at market open.',
    rootCause: 'Scheduled pause — engine is configured to pause during pre-market window (09:00–09:15).',
    action: 'None required. Engine will auto-resume at 09:15 IST.',
    recoveryStatus: 'Success',
    timestamp: '2025-08-10 09:00:00',
  },
];

const ERROR_HISTORY: ErrorHistoryEntry[] = [
  { id: 'h1', time: '2025-08-10 14:32:05', code: 'ERR-2025-0810-0001', type: 'Connection', severity: 'Critical', message: 'WebSocket connection to broker API lost', resolved: false },
  { id: 'h2', time: '2025-08-10 13:15:42', code: 'ERR-2025-0810-0002', type: 'Order', severity: 'Critical', message: 'Order placement failed — insufficient margin', resolved: false },
  { id: 'h3', time: '2025-08-10 12:48:20', code: 'ERR-2025-0810-0003', type: 'Risk', severity: 'Warning', message: 'Daily loss limit approaching threshold (2.4%)', resolved: false },
  { id: 'h4', time: '2025-08-10 11:22:17', code: 'ERR-2025-0810-0004', type: 'Signal', severity: 'Warning', message: 'Signal confidence below minimum threshold', resolved: false },
  { id: 'h5', time: '2025-08-10 09:00:00', code: 'ERR-2025-0810-0005', type: 'Engine', severity: 'Info', message: 'Engine auto-paused for pre-market session', resolved: true },
  { id: 'h6', time: '2025-08-09 15:30:12', code: 'ERR-2025-0809-0001', type: 'Connection', severity: 'Critical', message: 'API rate limit exceeded (429 Too Many Requests)', resolved: true },
  { id: 'h7', time: '2025-08-09 14:18:45', code: 'ERR-2025-0809-0002', type: 'Order', severity: 'Warning', message: 'Partial fill — 50 of 100 qty executed', resolved: true },
  { id: 'h8', time: '2025-08-09 11:45:33', code: 'ERR-2025-0809-0003', type: 'Signal', severity: 'Info', message: 'Strategy Mean Reversion signal expired', resolved: true },
  { id: 'h9', time: '2025-08-09 10:22:10', code: 'ERR-2025-0809-0004', type: 'Risk', severity: 'Warning', message: 'Max consecutive losses (3) reached — cool-off active', resolved: true },
  { id: 'h10', time: '2025-08-08 15:28:00', code: 'ERR-2025-0808-0001', type: 'Engine', severity: 'Critical', message: 'Engine process killed — OOM (1.8GB used)', resolved: true },
  { id: 'h11', time: '2025-08-08 14:55:30', code: 'ERR-2025-0808-0002', type: 'Connection', severity: 'Warning', message: 'Slow API response (>5s) detected', resolved: true },
  { id: 'h12', time: '2025-08-08 09:02:15', code: 'ERR-2025-0808-0003', type: 'Engine', severity: 'Info', message: 'Engine started successfully in paper mode', resolved: true },
  { id: 'h13', time: '2025-08-07 13:40:50', code: 'ERR-2025-0807-0001', type: 'Order', severity: 'Critical', message: 'Invalid order params — lot size mismatch', resolved: true },
  { id: 'h14', time: '2025-08-07 10:15:22', code: 'ERR-2025-0807-0002', type: 'Signal', severity: 'Warning', message: 'Duplicate signal suppressed — ORB on NIFTY', resolved: true },
  { id: 'h15', time: '2025-08-06 15:45:00', code: 'ERR-2025-0806-0001', type: 'Risk', severity: 'Critical', message: 'Max drawdown exceeded — auto square-off triggered', resolved: true },
];

const ERROR_TYPE_COLORS: Record<string, string> = {
  Connection: '#ef4444',
  Order: '#f59e0b',
  Signal: '#3b82f6',
  Risk: '#a855f7',
  Engine: '#22c55e',
};

const SEVERITY_BADGE_STYLES: Record<Severity, string> = {
  Critical: 'bg-ub-loss/15 text-ub-loss border-ub-loss/30',
  Warning: 'bg-ub-warning/15 text-ub-warning border-ub-warning/30',
  Info: 'bg-ub-accent/15 text-ub-accent border-ub-accent/30',
};

const RECOVERY_BADGE_STYLES: Record<RecoveryStatus, string> = {
  'Attempting...': 'bg-ub-warning/15 text-ub-warning border-ub-warning/30',
  Success: 'bg-ub-profit/15 text-ub-profit border-ub-profit/30',
  Failed: 'bg-ub-loss/15 text-ub-loss border-ub-loss/30',
  'Not Available': 'bg-ub-text-muted/15 text-ub-text-muted border-ub-text-muted/30',
};

const SEVERITY_ICONS: Record<Severity, React.ReactNode> = {
  Critical: <AlertCircle className="h-4 w-4" />,
  Warning: <AlertTriangle className="h-4 w-4" />,
  Info: <Info className="h-4 w-4" />,
};

const tooltipStyle = {
  backgroundColor: '#1e293b',
  border: '1px solid #334155',
  borderRadius: '8px',
  color: '#f1f5f9',
  fontSize: '12px',
  padding: '8px 12px',
};

const ITEMS_PER_PAGE = 8;

// ─────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────

export default function ErrorsPage() {
  const { data: apiErrors } = useErrors();
  const rawErrors = (apiErrors as any) || {};

  const [activeErrors, setActiveErrors] = useState<ActiveError[]>([]);

  useEffect(() => {
    if (Array.isArray(rawErrors.active)) {
      setActiveErrors(rawErrors.active);
    }
  }, [rawErrors.active]);

  const ERROR_HISTORY: ErrorHistoryEntry[] = Array.isArray(rawErrors.history) ? rawErrors.history : [];

  const [filterSeverity, setFilterSeverity] = useState<string>('all');
  const [filterType, setFilterType] = useState<string>('all');
  const [filterDateFrom, setFilterDateFrom] = useState<string>('');
  const [filterDateTo, setFilterDateTo] = useState<string>('');
  const [currentPage, setCurrentPage] = useState(1);

  // Derived data for charts
  const errorTypeDistribution: ErrorTypeDistribution[] = useMemo(() => {
    const counts: Record<string, number> = {};
    ERROR_HISTORY.forEach((e) => {
      counts[e.type] = (counts[e.type] || 0) + 1;
    });
    return Object.entries(counts)
      .map(([name, value]) => ({
        name,
        value,
        color: ERROR_TYPE_COLORS[name] || '#94a3b8',
      }))
      .sort((a, b) => b.value - a.value);
  }, []);

  const severityDistribution: SeverityDistribution[] = useMemo(() => {
    const counts: Record<string, number> = { Critical: 0, Warning: 0, Info: 0 };
    ERROR_HISTORY.forEach((e) => {
      counts[e.severity]++;
    });
    const colors: Record<string, string> = { Critical: '#ef4444', Warning: '#f59e0b', Info: '#3b82f6' };
    return Object.entries(counts).map(([name, count]) => ({
      name,
      count,
      color: colors[name] || '#94a3b8',
    }));
  }, []);

  // Stats
  const stats = useMemo(() => {
    const total = ERROR_HISTORY.length;
    const unresolved = ERROR_HISTORY.filter((e) => !e.resolved).length + activeErrors.length;
    const recovered = ERROR_HISTORY.filter((e) => e.resolved).length;
    const recoveryRate = total > 0 ? Math.round((recovered / total) * 100) : 100;
    const typeCounts: Record<string, number> = {};
    ERROR_HISTORY.forEach((e) => {
      typeCounts[e.type] = (typeCounts[e.type] || 0) + 1;
    });
    const mostCommon = Object.entries(typeCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || 'System Normal';
    return { total: total + activeErrors.length, unresolved, recoveryRate, mostCommon };
  }, [ERROR_HISTORY, activeErrors]);

  // Filtered history
  const filteredHistory = useMemo(() => {
    return ERROR_HISTORY.filter((e) => {
      if (filterSeverity !== 'all' && e.severity !== filterSeverity) return false;
      if (filterType !== 'all' && e.type !== filterType) return false;
      if (filterDateFrom && e.time < filterDateFrom) return false;
      if (filterDateTo && e.time > filterDateTo + 'T23:59:59') return false;
      return true;
    });
  }, [filterSeverity, filterType, filterDateFrom, filterDateTo]);

  const totalPages = Math.max(1, Math.ceil(filteredHistory.length / ITEMS_PER_PAGE));
  const paginatedHistory = filteredHistory.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE,
  );

  const handleMarkResolved = useCallback((id: string) => {
    setActiveErrors((prev) => prev.filter((e) => e.id !== id));
    toast.success('Error marked as resolved');
  }, []);

  // Reset page on filter change
  const handleFilterChange = useCallback((setter: React.Dispatch<React.SetStateAction<string>>) => (value: string) => {
    setter(value);
    setCurrentPage(1);
  }, []);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-lg bg-ub-warning/10 flex items-center justify-center">
          <AlertTriangle className="h-5 w-5 text-ub-warning" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-ub-text-primary">Error Console</h1>
          <p className="text-sm text-ub-text-muted">Monitor and manage errors, auto-recovery, and system health</p>
        </div>
      </div>

      {/* ── Error Stats ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="bg-ub-surface border-ub-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-ub-text-muted uppercase tracking-wider">Total Errors</span>
              <Activity className="h-4 w-4 text-ub-accent" />
            </div>
            <p className="text-2xl font-bold text-ub-text-primary">{stats.total}</p>
          </CardContent>
        </Card>
        <Card className="bg-ub-surface border-ub-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-ub-text-muted uppercase tracking-wider">Active / Unresolved</span>
              <AlertCircle className="h-4 w-4 text-ub-loss" />
            </div>
            <p className="text-2xl font-bold text-ub-loss">{stats.unresolved}</p>
          </CardContent>
        </Card>
        <Card className="bg-ub-surface border-ub-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-ub-text-muted uppercase tracking-wider">Auto-Recovery Rate</span>
              <RotateCcw className="h-4 w-4 text-ub-profit" />
            </div>
            <p className="text-2xl font-bold text-ub-profit">{stats.recoveryRate}%</p>
          </CardContent>
        </Card>
        <Card className="bg-ub-surface border-ub-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-ub-text-muted uppercase tracking-wider">Most Common Type</span>
              <Bug className="h-4 w-4 text-ub-volatile" />
            </div>
            <p className="text-lg font-bold text-ub-volatile">{stats.mostCommon}</p>
          </CardContent>
        </Card>
      </div>

      {/* ── Active Errors ── */}
      <div>
        <h2 className="text-lg font-semibold text-ub-text-primary mb-4 flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-ub-loss" />
          Active Errors
          {activeErrors.length > 0 && (
            <Badge variant="outline" className="bg-ub-loss/15 text-ub-loss border-ub-loss/30 text-[10px] font-semibold">
              {activeErrors.length}
            </Badge>
          )}
        </h2>

        <div className="space-y-4">
          {activeErrors.length === 0 ? (
            <Card className="bg-ub-surface border-ub-border">
              <CardContent className="p-8 text-center">
                <CheckCircle2 className="h-10 w-10 text-ub-profit mx-auto mb-3" />
                <p className="text-sm text-ub-text-muted">No active errors. All systems operational.</p>
              </CardContent>
            </Card>
          ) : (
            activeErrors.map((error) => (
              <motion.div
                key={error.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3 }}
              >
                <Card className={`bg-ub-surface border ${
                  error.severity === 'Critical' ? 'border-ub-loss/40' : error.severity === 'Warning' ? 'border-ub-warning/40' : 'border-ub-border'
                }`}>
                  <CardContent className="p-4 space-y-3">
                    {/* Header */}
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant="outline" className={`text-[10px] font-semibold ${SEVERITY_BADGE_STYLES[error.severity]}`}>
                          {SEVERITY_ICONS[error.severity]}
                          <span className="ml-1">{error.severity}</span>
                        </Badge>
                        <span className="text-xs font-mono text-ub-text-muted">{error.code}</span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <Badge variant="outline" className={`text-[10px] font-semibold ${RECOVERY_BADGE_STYLES[error.recoveryStatus]}`}>
                          {error.recoveryStatus === 'Attempting...' && <Loader2 className="h-3 w-3 animate-spin mr-1" />}
                          {error.recoveryStatus === 'Success' && <CheckCircle2 className="h-3 w-3 mr-1" />}
                          {error.recoveryStatus === 'Failed' && <XCircle className="h-3 w-3 mr-1" />}
                          {error.recoveryStatus}
                        </Badge>
                      </div>
                    </div>

                    {/* What happened */}
                    <div className="space-y-1">
                      <div className="flex items-start gap-2">
                        <span className="text-xs font-semibold text-ub-warning mt-0.5 shrink-0">What:</span>
                        <p className="text-sm text-ub-text-primary">{error.description}</p>
                      </div>
                    </div>

                    {/* Why it happened */}
                    <div className="flex items-start gap-2">
                      <span className="text-xs font-semibold text-ub-loss mt-0.5 shrink-0">Why:</span>
                      <p className="text-sm text-ub-text-muted">{error.rootCause}</p>
                    </div>

                    {/* How to fix */}
                    <div className="flex items-start gap-2">
                      <span className="text-xs font-semibold text-ub-profit mt-0.5 shrink-0">Fix:</span>
                      <p className="text-sm text-ub-text-primary">{error.action}</p>
                    </div>

                    {/* Footer */}
                    <div className="flex items-center justify-between pt-2 border-t border-ub-border">
                      <div className="flex items-center gap-1.5 text-ub-text-disabled text-xs">
                        <Clock className="h-3 w-3" />
                        {error.timestamp}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-ub-accent hover:text-ub-accent-hover hover:bg-ub-accent/10 text-xs h-7 px-3"
                        onClick={() => handleMarkResolved(error.id)}
                      >
                        <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
                        Mark Resolved
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ))
          )}
        </div>
      </div>

      {/* ── Error History + Breakdown ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Error History Table */}
        <div className="lg:col-span-2 space-y-4">
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-ub-text-primary flex items-center gap-2">
                <Clock className="h-4 w-4 text-ub-accent" />
                Error History
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Filters */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-ub-text-muted text-xs">Severity</Label>
                  <Select value={filterSeverity} onValueChange={handleFilterChange(setFilterSeverity)}>
                    <SelectTrigger className="bg-ub-background border-ub-border text-ub-text-primary text-xs h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-ub-surface border-ub-border">
                      <SelectItem value="all" className="text-ub-text-primary">All</SelectItem>
                      <SelectItem value="Critical" className="text-ub-text-primary">Critical</SelectItem>
                      <SelectItem value="Warning" className="text-ub-text-primary">Warning</SelectItem>
                      <SelectItem value="Info" className="text-ub-text-primary">Info</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-ub-text-muted text-xs">Type</Label>
                  <Select value={filterType} onValueChange={handleFilterChange(setFilterType)}>
                    <SelectTrigger className="bg-ub-background border-ub-border text-ub-text-primary text-xs h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-ub-surface border-ub-border">
                      <SelectItem value="all" className="text-ub-text-primary">All</SelectItem>
                      <SelectItem value="Connection" className="text-ub-text-primary">Connection</SelectItem>
                      <SelectItem value="Order" className="text-ub-text-primary">Order</SelectItem>
                      <SelectItem value="Signal" className="text-ub-text-primary">Signal</SelectItem>
                      <SelectItem value="Risk" className="text-ub-text-primary">Risk</SelectItem>
                      <SelectItem value="Engine" className="text-ub-text-primary">Engine</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-ub-text-muted text-xs">From</Label>
                  <Input
                    type="date"
                    value={filterDateFrom}
                    onChange={(e) => handleFilterChange(setFilterDateFrom)(e.target.value)}
                    className="bg-ub-background border-ub-border text-ub-text-primary text-xs h-9"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-ub-text-muted text-xs">To</Label>
                  <Input
                    type="date"
                    value={filterDateTo}
                    onChange={(e) => handleFilterChange(setFilterDateTo)(e.target.value)}
                    className="bg-ub-background border-ub-border text-ub-text-primary text-xs h-9"
                  />
                </div>
              </div>

              {/* Table */}
              <ScrollArea className="max-h-96">
                <Table>
                  <TableHeader>
                    <TableRow className="border-ub-border hover:bg-transparent">
                      <TableHead className="text-ub-text-muted text-xs">Time</TableHead>
                      <TableHead className="text-ub-text-muted text-xs">Code</TableHead>
                      <TableHead className="text-ub-text-muted text-xs">Type</TableHead>
                      <TableHead className="text-ub-text-muted text-xs">Severity</TableHead>
                      <TableHead className="text-ub-text-muted text-xs">Message</TableHead>
                      <TableHead className="text-ub-text-muted text-xs text-right">Resolved?</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedHistory.length === 0 ? (
                      <TableRow className="border-ub-border">
                        <TableCell colSpan={6} className="text-center text-ub-text-muted text-sm py-8">
                          No errors match the current filters.
                        </TableCell>
                      </TableRow>
                    ) : (
                      paginatedHistory.map((entry) => (
                        <TableRow key={entry.id} className="border-ub-border hover:bg-ub-surface-hover">
                          <TableCell className="text-ub-text-muted text-xs whitespace-nowrap">{entry.time}</TableCell>
                          <TableCell className="text-ub-text-primary text-xs font-mono whitespace-nowrap">{entry.code}</TableCell>
                          <TableCell>
                            <Badge
                              variant="outline"
                              className="text-[10px] font-semibold"
                              style={{
                                borderColor: `${ERROR_TYPE_COLORS[entry.type] || '#94a3b8'}40`,
                                color: ERROR_TYPE_COLORS[entry.type] || '#94a3b8',
                                backgroundColor: `${ERROR_TYPE_COLORS[entry.type] || '#94a3b8'}15`,
                              }}
                            >
                              {entry.type}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className={`text-[10px] font-semibold ${SEVERITY_BADGE_STYLES[entry.severity]}`}>
                              {entry.severity}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-ub-text-primary text-xs max-w-[200px] truncate">{entry.message}</TableCell>
                          <TableCell className="text-right">
                            <Badge
                              variant="outline"
                              className={`text-[10px] font-semibold ${
                                entry.resolved
                                  ? 'border-ub-profit/40 text-ub-profit bg-ub-profit/10'
                                  : 'border-ub-loss/40 text-ub-loss bg-ub-loss/10'
                              }`}
                            >
                              {entry.resolved ? (
                                <>
                                  <CheckCircle2 className="h-3 w-3 mr-0.5" />
                                  Yes
                                </>
                              ) : (
                                <>
                                  <XCircle className="h-3 w-3 mr-0.5" />
                                  No
                                </>
                              )}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </ScrollArea>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between pt-3 border-t border-ub-border">
                  <span className="text-xs text-ub-text-muted">
                    Showing {(currentPage - 1) * ITEMS_PER_PAGE + 1}–{Math.min(currentPage * ITEMS_PER_PAGE, filteredHistory.length)} of {filteredHistory.length}
                  </span>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 text-ub-text-muted hover:bg-ub-surface-hover"
                      disabled={currentPage === 1}
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </Button>
                    {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
                      <Button
                        key={page}
                        variant={page === currentPage ? 'default' : 'ghost'}
                        size="sm"
                        className={`h-7 w-7 p-0 text-xs ${
                          page === currentPage
                            ? 'bg-ub-accent text-ub-background font-semibold'
                            : 'text-ub-text-muted hover:bg-ub-surface-hover'
                        }`}
                        onClick={() => setCurrentPage(page)}
                      >
                        {page}
                      </Button>
                    ))}
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 text-ub-text-muted hover:bg-ub-surface-hover"
                      disabled={currentPage === totalPages}
                      onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    >
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Error Breakdown */}
        <div className="space-y-4">
          {/* By Type (PieChart) */}
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-ub-text-primary">By Type</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-[200px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={errorTypeDistribution}
                      cx="50%"
                      cy="50%"
                      innerRadius={45}
                      outerRadius={75}
                      paddingAngle={3}
                      dataKey="value"
                      stroke="none"
                    >
                      {errorTypeDistribution.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <RTooltip
                      contentStyle={tooltipStyle}
                      formatter={((value: number, name: string) => [`${value} errors`, name]) as never}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              {/* Legend */}
              <div className="flex flex-wrap gap-3 mt-2 justify-center">
                {errorTypeDistribution.map((item) => (
                  <div key={item.name} className="flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                    <span className="text-xs text-ub-text-muted">{item.name}</span>
                    <span className="text-xs font-semibold text-ub-text-primary">{item.value}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* By Severity (Horizontal Bars) */}
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-ub-text-primary">By Severity</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {severityDistribution.map((item) => {
                  const maxCount = Math.max(...severityDistribution.map((s) => s.count));
                  const pct = Math.round((item.count / maxCount) * 100);
                  return (
                    <div key={item.name} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-ub-text-muted text-xs">{item.name}</span>
                        <span className="text-ub-text-primary text-xs font-semibold">{item.count}</span>
                      </div>
                      <div className="flex h-2 w-full overflow-hidden rounded-full bg-ub-background">
                        <div
                          className="rounded-full transition-all duration-500"
                          style={{ width: `${pct}%`, backgroundColor: item.color }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}import { useErrors } from '@/hooks/useApi';

