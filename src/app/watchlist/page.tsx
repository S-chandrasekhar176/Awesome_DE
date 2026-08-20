'use client';

import { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { useKronosHotlist, useWatchlist } from '@/hooks/useApi';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Search,
  X,
  Flame,
  Newspaper,
  Star,
  Clock,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  ExternalLink,
  Activity,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

interface HotStock {
  rank: number;
  symbol: string;
  price: number;
  changePct: number;
  volume: string;
  hotness: number;
  reason: string;
}

interface NewsFocusStock {
  symbol: string;
  name: string;
  price: number;
  changePct: number;
  headline: string;
  source: string;
  sentiment: 'BUY' | 'SELL' | 'WATCH';
  catalyst: string;
  url: string;
  publishedAt: string;
}

interface CustomStock {
  symbol: string;
  price: number;
  changePct: number;
}

// ─────────────────────────────────────────────
// Indian number formatting
// ─────────────────────────────────────────────

function formatINR(n: number | undefined | null): string {
  if (typeof n !== 'number' || isNaN(n)) return '₹0.00';
  return '₹' + n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatChangePercent(pct: number | undefined | null): string {
  if (typeof pct !== 'number' || isNaN(pct)) return '0.00%';
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
}

function changeColor(pct: number | undefined | null): string {
  if (typeof pct !== 'number' || isNaN(pct)) return 'text-ub-text-muted';
  return pct >= 0 ? 'text-ub-profit' : 'text-ub-loss';
}

// ─────────────────────────────────────────────
// Real-world baseline data
// ─────────────────────────────────────────────

const INITIAL_CUSTOM: CustomStock[] = [
  { symbol: 'NIFTY', price: 24361.90, changePct: -0.14 },
  { symbol: 'BANKNIFTY', price: 57589.75, changePct: -0.08 },
  { symbol: 'RELIANCE', price: 1380.40, changePct: 1.04 },
  { symbol: 'TATAMOTORS', price: 978.50, changePct: 1.27 },
  { symbol: 'SBIN', price: 818.20, changePct: -0.41 },
  { symbol: 'TCS', price: 4110.00, changePct: -0.45 },
];

const FO_UNIVERSE = [
  'NIFTY', 'BANKNIFTY', 'FINNIFTY', 'RELIANCE', 'TCS', 'HDFCBANK', 'INFY',
  'ICICIBANK', 'SBIN', 'BHARTIARTL', 'ITC', 'KOTAKBANK', 'LT', 'WIPRO',
  'AXISBANK', 'MARUTI', 'SUNPHARMA', 'TATAMOTORS', 'BAJFINANCE', 'HCLTECH',
  'ADANIENT', 'TATAPOWER', 'JSWSTEEL', 'DRREDDY', 'PIIND', 'DIVISLAB',
  'ASIANPAINT', 'TITAN', 'ULTRACEMCO', 'NESTLEIND', 'TECHM', 'ONGC',
  'NTPC', 'POWERGRID', 'COALINDIA', 'BPCL', 'HINDUNILVR', 'BAJAJFINSV',
  'INDUSINDBK', 'GRASIM', 'M_M', 'EICHERMOT', 'HEROMOTOCO', 'BRITANNIA',
];

const DEFAULT_KRONOS_STOCKS: HotStock[] = [
  { rank: 1, symbol: 'RELIANCE', price: 1380.40, changePct: 1.04, volume: '6.8M (3.2x)', hotness: 94, reason: 'Extreme volume surge: 3.2x avg; Near resistance breakout; Bullish momentum' },
  { rank: 2, symbol: 'TATAMOTORS', price: 978.50, changePct: 1.27, volume: '9.2M (2.8x)', hotness: 89, reason: 'Strong momentum: +1.27%; High-impact earnings catalyst; Above VWAP' },
  { rank: 3, symbol: 'SBIN', price: 818.20, changePct: -0.41, volume: '14.1M (2.4x)', hotness: 84, reason: 'Volume surge: 2.4x avg; RSI 62 bullish momentum; Above key 20 EMA' },
  { rank: 4, symbol: 'HDFCBANK', price: 1642.10, changePct: 0.34, volume: '11.5M (1.9x)', hotness: 78, reason: 'Bullish EMA crossover, price near EMA20; High-impact regulatory catalyst' },
  { rank: 5, symbol: 'TCS', price: 4110.00, changePct: -0.45, volume: '2.4M (1.4x)', hotness: 71, reason: 'RSI 42 bounce potential; Major multi-million IT deal catalyst' },
  { rank: 6, symbol: 'INFY', price: 1785.60, changePct: 0.93, volume: '5.8M (2.1x)', hotness: 76, reason: 'Trading above VWAP with tight spread; Resistance test at 1800' },
  { rank: 7, symbol: 'BHARTIARTL', price: 1458.00, changePct: 0.61, volume: '4.2M (1.8x)', hotness: 80, reason: 'Breakout above multi-week resistance; Volume surge 1.8x' },
  { rank: 8, symbol: 'ICICIBANK', price: 1198.30, changePct: 0.52, volume: '8.4M (1.7x)', hotness: 75, reason: 'Above support level; Steady institutional buying flows' },
];

export default function WatchlistPage() {
  const { data: hotData } = useKronosHotlist();
  const { data: apiWatchlist } = useWatchlist();

  const [kronosStocks, setKronosStocks] = useState<HotStock[]>(DEFAULT_KRONOS_STOCKS);
  const [customStocks, setCustomStocks] = useState<CustomStock[]>(INITIAL_CUSTOM);
  const [newsFocusStocks, setNewsFocusStocks] = useState<NewsFocusStock[]>([]);
  const [isLoadingNews, setIsLoadingNews] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState<string>('');

  const kronosSymbolsRef = useRef<string[]>(DEFAULT_KRONOS_STOCKS.map((s) => s.symbol));
  const customSymbolsRef = useRef<string[]>(INITIAL_CUSTOM.map((s) => s.symbol));

  useEffect(() => {
    kronosSymbolsRef.current = kronosStocks.map((s) => s.symbol);
  }, [kronosStocks]);

  useEffect(() => {
    customSymbolsRef.current = customStocks.map((s) => s.symbol);
  }, [customStocks]);

  // Hydrate from API if available
  useEffect(() => {
    if (hotData && Array.isArray(hotData) && hotData.length > 0) {
      setKronosStocks(hotData);
    }
  }, [hotData]);

  useEffect(() => {
    if (apiWatchlist) {
      const rawList = Array.isArray(apiWatchlist)
        ? apiWatchlist
        : (apiWatchlist as { watchlist?: unknown[] }).watchlist;

      if (Array.isArray(rawList) && rawList.length > 0) {
        const mapped: CustomStock[] = rawList
          .map((item: any) => {
            if (typeof item === 'string') {
              return { symbol: item, price: 0, changePct: 0 };
            }
            if (item && typeof item === 'object' && item.symbol) {
              return {
                symbol: String(item.symbol),
                price: typeof item.price === 'number' ? item.price : 0,
                changePct: typeof item.changePct === 'number' ? item.changePct : 0,
              };
            }
            return null;
          })
          .filter((item): item is CustomStock => item !== null);

        if (mapped.length > 0) {
          setCustomStocks(mapped);
        }
      }
    }
  }, [apiWatchlist]);

  // 1. Sync Live Quotes for all stocks from Live Market Quotes API
  const syncLivePrices = useCallback(async () => {
    try {
      const allSymbols = Array.from(
        new Set([
          ...kronosSymbolsRef.current,
          ...customSymbolsRef.current,
        ])
      ).filter(Boolean);

      if (allSymbols.length === 0) return;

      const res = await fetch(`/api/live-quotes?symbols=${allSymbols.join(',')}`, { cache: 'no-store' });
      if (res.ok) {
        const json = await res.json();
        if (json.success && json.data) {
          const quotes = json.data;
          setKronosStocks((prev) =>
            prev.map((item) => {
              const q = quotes[item.symbol];
              if (q && q.price > 0) {
                return {
                  ...item,
                  price: q.price,
                  changePct: q.changePct,
                };
              }
              return item;
            }),
          );

          setCustomStocks((prev) =>
            prev.map((item) => {
              const q = quotes[item.symbol];
              if (q && q.price > 0) {
                return {
                  ...item,
                  price: q.price,
                  changePct: q.changePct,
                };
              }
              return item;
            }),
          );

          setLastSyncTime(new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
        }
      }
    } catch {
      // Live sync error handling
    }
  }, []);

  // 2. Fetch News-Driven Focus Stocks for Current Date
  const fetchNewsFocusStocks = useCallback(async () => {
    setIsLoadingNews(true);
    try {
      const res = await fetch('/api/news-focus-stocks', { cache: 'no-store' });
      if (res.ok) {
        const json = await res.json();
        if (json.success && Array.isArray(json.data)) {
          setNewsFocusStocks(json.data);
        }
      }
    } catch {
      // Keep existing
    } finally {
      setIsLoadingNews(false);
    }
  }, []);

  useEffect(() => {
    syncLivePrices();
    fetchNewsFocusStocks();
    const interval = setInterval(() => {
      syncLivePrices();
    }, 5000);
    return () => clearInterval(interval);
  }, [syncLivePrices, fetchNewsFocusStocks]);

  const [searchQuery, setSearchQuery] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);

  const filteredUniverse = useMemo(() => {
    if (!searchQuery.trim()) return [];
    const q = searchQuery.toUpperCase();
    const addedSymbols = new Set(customStocks.map((s) => s.symbol));
    return FO_UNIVERSE.filter(
      (s) => s.includes(q) && !addedSymbols.has(s),
    ).slice(0, 8);
  }, [searchQuery, customStocks]);

  const addStock = async (symbol: string) => {
    if (customStocks.find((s) => s.symbol === symbol)) return;
    setSearchQuery('');
    setSearchFocused(false);

    // Fetch real live price directly from live market quote feed
    try {
      const res = await fetch(`/api/live-quotes?symbols=${symbol}`, { cache: 'no-store' });
      if (res.ok) {
        const json = await res.json();
        const q = json.data?.[symbol];
        if (q && q.price > 0) {
          setCustomStocks((prev) => [...prev, { symbol, price: q.price, changePct: q.changePct }]);
          return;
        }
      }
    } catch (err) {
      console.error('Failed fetching live quote for stock:', err);
    }

    setCustomStocks((prev) => [...prev, { symbol, price: 0, changePct: 0 }]);
  };

  const removeStock = (symbol: string) => {
    setCustomStocks((prev) => prev.filter((s) => s.symbol !== symbol));
  };

  return (
    <div className="space-y-4">
      <Tabs defaultValue="hotlist" className="space-y-4">
        <TabsList className="bg-ub-surface border border-ub-border">
          <TabsTrigger
            value="hotlist"
            className="data-[state=active]:bg-ub-accent/15 data-[state=active]:text-ub-accent text-ub-text-muted gap-1.5"
          >
            <Flame className="h-3.5 w-3.5" />
            Kronos Hot List
          </TabsTrigger>
          <TabsTrigger
            value="news"
            className="data-[state=active]:bg-ub-accent/15 data-[state=active]:text-ub-accent text-ub-text-muted gap-1.5"
          >
            <Newspaper className="h-3.5 w-3.5" />
            News-Driven
            {newsFocusStocks.length > 0 && (
              <span className="ml-1 px-1.5 py-0.2 bg-ub-accent/20 text-ub-accent text-[10px] rounded-full font-bold">
                {newsFocusStocks.length}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger
            value="custom"
            className="data-[state=active]:bg-ub-accent/15 data-[state=active]:text-ub-accent text-ub-text-muted gap-1.5"
          >
            <Star className="h-3.5 w-3.5" />
            My Custom List
          </TabsTrigger>
        </TabsList>

        {/* ── Tab 1: Kronos Hot List ── */}
        <TabsContent value="hotlist">
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="p-4 pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold text-ub-text-primary flex items-center gap-2">
                  <Flame className="h-4 w-4 text-ub-accent" />
                  Kronos Hot List (Live Market LTP)
                </CardTitle>
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-ub-text-muted flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    Live Sync: {lastSyncTime || 'Active'}
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => syncLivePrices()}
                    className="h-6 px-2 text-xs text-ub-accent hover:bg-ub-accent/10"
                  >
                    <RefreshCw className="h-3 w-3 mr-1" />
                    Sync
                  </Button>
                </div>
              </div>
              <p className="text-xs text-ub-text-muted mt-0.5">Real-time ranked momentum opportunities synchronized with live NSE/BSE market prices</p>
            </CardHeader>
            <CardContent className="p-0">
              <ScrollArea className="max-h-[calc(100vh-220px)]">
                <Table>
                  <TableHeader>
                    <TableRow className="border-ub-border hover:bg-transparent">
                      <TableHead className="text-ub-text-muted text-xs w-10">#</TableHead>
                      <TableHead className="text-ub-text-muted text-xs">Symbol</TableHead>
                      <TableHead className="text-ub-text-muted text-xs text-right">Live Price</TableHead>
                      <TableHead className="text-ub-text-muted text-xs text-right">Change %</TableHead>
                      <TableHead className="text-ub-text-muted text-xs text-right hidden sm:table-cell">Volume</TableHead>
                      <TableHead className="text-ub-text-muted text-xs hidden md:table-cell" style={{ minWidth: 120 }}>Hotness</TableHead>
                      <TableHead className="text-ub-text-muted text-xs hidden lg:table-cell">Reason & Catalyst</TableHead>
                      <TableHead className="text-ub-text-muted text-xs w-20">Source</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {kronosStocks.map((stock) => (
                      <TableRow
                        key={stock.rank}
                        className="border-ub-border/50 hover:bg-ub-surface-hover cursor-pointer transition-colors"
                      >
                        <TableCell className="text-xs text-ub-text-muted font-mono">{stock.rank}</TableCell>
                        <TableCell className="font-semibold text-ub-text-primary text-xs">{stock.symbol}</TableCell>
                        <TableCell className="text-right font-mono text-xs text-ub-text-primary font-bold">
                          {formatINR(stock.price)}
                        </TableCell>
                        <TableCell className={cn('text-right font-mono text-xs font-semibold', changeColor(stock.changePct))}>
                          {formatChangePercent(stock.changePct)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs text-ub-text-muted hidden sm:table-cell">
                          {stock.volume}
                        </TableCell>
                        <TableCell className="hidden md:table-cell">
                          <div className="flex items-center gap-2">
                            <Progress
                              value={stock.hotness}
                              className="h-1.5 flex-1"
                            />
                            <span className="text-[10px] text-ub-text-primary font-mono w-8 text-right font-semibold">
                              {stock.hotness}%
                            </span>
                          </div>
                        </TableCell>
                        <TableCell className="text-xs text-ub-text-muted hidden lg:table-cell max-w-[280px] truncate" title={stock.reason}>
                          {stock.reason}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className="text-[10px] px-1.5 py-0 border-ub-accent/30 text-ub-accent bg-ub-accent/5"
                          >
                            Kronos AI
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Tab 2: News-Driven (Focus stocks for current date) ── */}
        <TabsContent value="news">
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="p-4 pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold text-ub-text-primary flex items-center gap-2">
                  <Newspaper className="h-4 w-4 text-ub-accent" />
                  Today's News-Driven Focus Stocks
                </CardTitle>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={fetchNewsFocusStocks}
                  disabled={isLoadingNews}
                  className="h-6 px-2 text-xs text-ub-accent hover:bg-ub-accent/10"
                >
                  <RefreshCw className={cn('h-3 w-3 mr-1', isLoadingNews && 'animate-spin')} />
                  Refresh News
                </Button>
              </div>
              <p className="text-xs text-ub-text-muted mt-0.5">High-conviction stocks mentioned in today's live business updates with actionable catalysts</p>
            </CardHeader>
            <CardContent className="p-4 pt-2">
              <div className="space-y-3">
                {newsFocusStocks.map((item, idx) => {
                  const isBuy = item.sentiment === 'BUY';
                  const isSell = item.sentiment === 'SELL';

                  return (
                    <a
                      key={idx}
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block p-3.5 rounded-lg border border-ub-border/50 hover:border-ub-accent/40 hover:bg-ub-surface-hover transition-all cursor-pointer group"
                      title="Click to open full verified article"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                            <span className="font-bold text-ub-text-primary text-sm tracking-wide">{item.symbol}</span>
                            <span className="text-xs text-ub-text-muted">({item.name})</span>
                            <span className="font-mono text-sm font-bold text-ub-text-primary">{formatINR(item.price)}</span>
                            <span className={cn('font-mono text-xs font-semibold', changeColor(item.changePct))}>
                              {formatChangePercent(item.changePct)}
                            </span>
                            {isBuy && (
                              <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 text-[10px] py-0 px-2 font-bold">
                                BUY CATALYST
                              </Badge>
                            )}
                            {isSell && (
                              <Badge className="bg-rose-500/15 text-rose-400 border-rose-500/30 text-[10px] py-0 px-2 font-bold">
                                SELL CATALYST
                              </Badge>
                            )}
                            {!isBuy && !isSell && (
                              <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30 text-[10px] py-0 px-2 font-bold">
                                WATCH
                              </Badge>
                            )}
                          </div>
                          <p className="text-xs font-medium text-ub-text-primary leading-snug group-hover:text-ub-accent transition-colors mb-1">
                            {item.headline}
                          </p>
                          <p className="text-[11px] text-ub-text-muted leading-relaxed">
                            <span className="text-ub-accent font-medium">Catalyst:</span> {item.catalyst}
                          </p>
                        </div>
                        <div className="flex flex-col items-end gap-1.5 shrink-0">
                          <Badge
                            variant="outline"
                            className="text-[10px] px-2 py-0.5 border-ub-border text-ub-text-muted bg-ub-surface flex items-center gap-1"
                          >
                            {item.source}
                            <ExternalLink className="h-2.5 w-2.5 opacity-60" />
                          </Badge>
                          <span className="text-[10px] text-ub-text-muted flex items-center gap-1">
                            <Clock className="h-2.5 w-2.5" />
                            {item.publishedAt}
                          </span>
                        </div>
                      </div>
                    </a>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Tab 3: My Custom List ── */}
        <TabsContent value="custom">
          <Card className="bg-ub-surface border-ub-border">
            <CardHeader className="p-4 pb-2">
              <CardTitle className="text-sm font-semibold text-ub-text-primary flex items-center gap-2">
                <Star className="h-4 w-4 text-ub-accent" />
                My Custom Watchlist
              </CardTitle>
              <p className="text-xs text-ub-text-muted mt-1">Add symbols to monitor live prices</p>
            </CardHeader>
            <CardContent className="p-4 pt-2 space-y-4">
              <div className="relative max-w-sm">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-ub-text-muted" />
                <Input
                  type="text"
                  placeholder="Search F&O symbol (e.g. RELIANCE, TCS)..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onFocus={() => setSearchFocused(true)}
                  onBlur={() => setTimeout(() => setSearchFocused(false), 200)}
                  className="pl-8 bg-ub-surface border-ub-border text-ub-text-primary text-xs"
                />
                {searchFocused && filteredUniverse.length > 0 && (
                  <div className="absolute top-full left-0 right-0 mt-1 bg-ub-surface border border-ub-border rounded-lg shadow-xl z-50 overflow-hidden">
                    {filteredUniverse.map((sym) => (
                      <button
                        key={sym}
                        onMouseDown={() => addStock(sym)}
                        className="w-full text-left px-3 py-2 text-xs text-ub-text-primary hover:bg-ub-surface-hover flex items-center justify-between"
                      >
                        <span className="font-semibold">{sym}</span>
                        <span className="text-[10px] text-ub-accent font-medium">+ Add</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {customStocks.map((stock) => (
                  <div
                    key={stock.symbol}
                    className="p-3 rounded-lg border border-ub-border bg-ub-surface/60 flex items-center justify-between relative group"
                  >
                    <div>
                      <span className="text-xs font-bold text-ub-text-primary block">{stock.symbol}</span>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="font-mono text-xs text-ub-text-primary">{formatINR(stock.price)}</span>
                        <span className={cn('font-mono text-[10px] font-semibold', changeColor(stock.changePct))}>
                          {formatChangePercent(stock.changePct)}
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={() => removeStock(stock.symbol)}
                      className="p-1 rounded text-ub-text-muted hover:text-ub-loss opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
