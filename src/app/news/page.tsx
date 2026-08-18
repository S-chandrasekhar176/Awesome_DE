'use client';

import { useState, useMemo } from 'react';
import { useNews } from '@/hooks/useApi';
import {
  Newspaper,
  TrendingUp,
  TrendingDown,
  Clock,
  ExternalLink,
  Tag,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Search,
  Filter,
  ArrowUpDown,
  Calendar,
  Sparkles,
  RefreshCw,
  SlidersHorizontal,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

type SortOption = 'latest' | 'oldest' | 'stocks_asc' | 'stocks_desc' | 'confidence' | 'bullish' | 'bearish';

export default function NewsPage() {
  const { data: newsItems, isLoading, isError, refetch } = useNews();
  const [filterSentiment, setFilterSentiment] = useState<'ALL' | 'BUY' | 'SELL' | 'NEUTRAL'>('ALL');
  const [filterProvider, setFilterProvider] = useState<string>('ALL');
  const [sortOption, setSortOption] = useState<SortOption>('latest');
  const [searchQuery, setSearchQuery] = useState('');

  // Compute live provider counts across all received news items
  const providerCounts = useMemo(() => {
    if (!Array.isArray(newsItems)) {
      return { total: 0, et: 0, ndtv: 0, lm: 0, hbl: 0, other: 0 };
    }
    let et = 0;
    let ndtv = 0;
    let lm = 0;
    let hbl = 0;
    let other = 0;

    for (const item of newsItems) {
      const src = (item.source || '').toLowerCase();
      const code = item.providerCode;

      if (code === 'ET' || src.includes('economic') || src.includes('et ')) et++;
      else if (code === 'NDTV' || src.includes('ndtv')) ndtv++;
      else if (code === 'LM' || src.includes('livemint') || src.includes('mint')) lm++;
      else if (code === 'HBL' || src.includes('hindu') || src.includes('businessline')) hbl++;
      else other++;
    }

    return { total: newsItems.length, et, ndtv, lm, hbl, other };
  }, [newsItems]);

  const filteredAndSortedItems = useMemo(() => {
    if (!Array.isArray(newsItems)) return [];

    // 1. Filter
    const filtered = newsItems.filter((item: any) => {
      const sentiment = (item.sentiment || item.tradeAction || 'NEUTRAL').toUpperCase();
      const matchesSentiment =
        filterSentiment === 'ALL' ||
        (filterSentiment === 'BUY' && (sentiment === 'BUY' || sentiment === 'BULLISH')) ||
        (filterSentiment === 'SELL' && (sentiment === 'SELL' || sentiment === 'BEARISH')) ||
        (filterSentiment === 'NEUTRAL' && sentiment === 'NEUTRAL');

      const src = (item.source || '').toLowerCase();
      const code = item.providerCode;
      let matchesProvider = true;

      if (filterProvider === 'ET') {
        matchesProvider = code === 'ET' || src.includes('economic') || src.includes('et ');
      } else if (filterProvider === 'NDTV') {
        matchesProvider = code === 'NDTV' || src.includes('ndtv');
      } else if (filterProvider === 'LM') {
        matchesProvider = code === 'LM' || src.includes('livemint') || src.includes('mint');
      } else if (filterProvider === 'HBL') {
        matchesProvider = code === 'HBL' || src.includes('hindu') || src.includes('businessline');
      } else if (filterProvider === 'OTHER') {
        matchesProvider =
          code === 'OTHER' ||
          (!src.includes('economic') &&
            !src.includes('ndtv') &&
            !src.includes('mint') &&
            !src.includes('hindu') &&
            !src.includes('businessline'));
      }

      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        (item.symbol || '').toLowerCase().includes(q) ||
        (item.headline || '').toLowerCase().includes(q) ||
        (item.summary || '').toLowerCase().includes(q) ||
        (item.source || '').toLowerCase().includes(q) ||
        (item.symbols || []).some((s: string) => s.toLowerCase().includes(q));

      return matchesSentiment && matchesProvider && matchesSearch;
    });

    // 2. Sort
    return filtered.sort((a: any, b: any) => {
      if (sortOption === 'latest') {
        const timeA = a.publishedTimestamp || 0;
        const timeB = b.publishedTimestamp || 0;
        return timeB - timeA;
      }
      if (sortOption === 'oldest') {
        const timeA = a.publishedTimestamp || 0;
        const timeB = b.publishedTimestamp || 0;
        return timeA - timeB;
      }
      if (sortOption === 'stocks_asc') {
        const symA = (a.symbol || 'ZZZ').toUpperCase();
        const symB = (b.symbol || 'ZZZ').toUpperCase();
        return symA.localeCompare(symB);
      }
      if (sortOption === 'stocks_desc') {
        const symA = (a.symbol || 'AAA').toUpperCase();
        const symB = (b.symbol || 'AAA').toUpperCase();
        return symB.localeCompare(symA);
      }
      if (sortOption === 'confidence') {
        return (b.confidence || 0) - (a.confidence || 0);
      }
      if (sortOption === 'bullish') {
        const isBuyA = a.sentiment === 'BUY' ? 1 : 0;
        const isBuyB = b.sentiment === 'BUY' ? 1 : 0;
        return isBuyB - isBuyA;
      }
      if (sortOption === 'bearish') {
        const isSellA = a.sentiment === 'SELL' ? 1 : 0;
        const isSellB = b.sentiment === 'SELL' ? 1 : 0;
        return isSellB - isSellA;
      }
      return 0;
    });
  }, [newsItems, filterSentiment, filterProvider, sortOption, searchQuery]);

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-ub-accent/15 border border-ub-accent/20">
            <Newspaper className="w-5 h-5 text-ub-accent" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-ub-text-primary flex items-center gap-2">
              Real-time Market News & Sentiment
              <Badge variant="outline" className="text-[11px] font-mono text-ub-accent border-ub-accent/40 bg-ub-accent/10">
                Live Feed
              </Badge>
            </h1>
            <p className="text-sm text-ub-text-muted">
              Live automated financial news aggregation, NLP sentiment analysis & trade impact signals for Indian markets
            </p>
          </div>
        </div>

        {/* Filter & Search actions */}
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative w-48 sm:w-60">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ub-text-muted" />
            <Input
              placeholder="Search ticker or news..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 h-8 text-xs bg-ub-surface border-ub-border text-ub-text-primary placeholder:text-ub-text-muted/60"
            />
          </div>

          {/* Sentiment Filter */}
          <div className="flex items-center bg-ub-surface border border-ub-border rounded-lg p-0.5">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setFilterSentiment('ALL')}
              className={`h-7 px-2.5 text-xs font-medium rounded-md ${
                filterSentiment === 'ALL'
                  ? 'bg-ub-accent/15 text-ub-accent'
                  : 'text-ub-text-muted hover:text-ub-text-primary'
              }`}
            >
              All
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setFilterSentiment('BUY')}
              className={`h-7 px-2.5 text-xs font-medium rounded-md ${
                filterSentiment === 'BUY'
                  ? 'bg-ub-profit/15 text-ub-profit font-semibold'
                  : 'text-ub-text-muted hover:text-ub-text-primary'
              }`}
            >
              Bullish
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setFilterSentiment('SELL')}
              className={`h-7 px-2.5 text-xs font-medium rounded-md ${
                filterSentiment === 'SELL'
                  ? 'bg-ub-loss/15 text-ub-loss font-semibold'
                  : 'text-ub-text-muted hover:text-ub-text-primary'
              }`}
            >
              Bearish
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setFilterSentiment('NEUTRAL')}
              className={`h-7 px-2.5 text-xs font-medium rounded-md ${
                filterSentiment === 'NEUTRAL'
                  ? 'bg-ub-surface-active text-ub-text-primary'
                  : 'text-ub-text-muted hover:text-ub-text-primary'
              }`}
            >
              Neutral
            </Button>
          </div>

          <Button
            variant="outline"
            size="icon"
            onClick={() => refetch()}
            className="h-8 w-8 border-ub-border text-ub-text-muted hover:text-ub-text-primary hover:border-ub-accent/40"
            title="Refresh news feed"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Provider Switcher Bar & Sort Control */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pt-1 border-y border-ub-border/60 py-3">
        {/* Source Provider Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 max-w-full">
          <button
            onClick={() => setFilterProvider('ALL')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all shrink-0 ${
              filterProvider === 'ALL'
                ? 'bg-ub-accent/15 border-ub-accent text-ub-accent shadow-sm'
                : 'bg-ub-surface border-ub-border text-ub-text-muted hover:border-ub-border/80 hover:text-ub-text-primary'
            }`}
          >
            <span>🌐</span> All Sources ({providerCounts.total})
          </button>
          <button
            onClick={() => setFilterProvider('ET')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all shrink-0 ${
              filterProvider === 'ET'
                ? 'bg-emerald-500/15 border-emerald-500 text-emerald-400 shadow-sm'
                : 'bg-ub-surface border-ub-border text-ub-text-muted hover:border-ub-border/80 hover:text-ub-text-primary'
            }`}
          >
            <span>📰</span> Economic Times ({providerCounts.et})
          </button>
          <button
            onClick={() => setFilterProvider('NDTV')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all shrink-0 ${
              filterProvider === 'NDTV'
                ? 'bg-blue-500/15 border-blue-500 text-blue-400 shadow-sm'
                : 'bg-ub-surface border-ub-border text-ub-text-muted hover:border-ub-border/80 hover:text-ub-text-primary'
            }`}
          >
            <span>📺</span> NDTV Profit ({providerCounts.ndtv})
          </button>
          <button
            onClick={() => setFilterProvider('LM')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all shrink-0 ${
              filterProvider === 'LM'
                ? 'bg-orange-500/15 border-orange-500 text-orange-400 shadow-sm'
                : 'bg-ub-surface border-ub-border text-ub-text-muted hover:border-ub-border/80 hover:text-ub-text-primary'
            }`}
          >
            <span>⚡</span> LiveMint ({providerCounts.lm})
          </button>
          <button
            onClick={() => setFilterProvider('HBL')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all shrink-0 ${
              filterProvider === 'HBL'
                ? 'bg-cyan-500/15 border-cyan-500 text-cyan-400 shadow-sm'
                : 'bg-ub-surface border-ub-border text-ub-text-muted hover:border-ub-border/80 hover:text-ub-text-primary'
            }`}
          >
            <span>📈</span> Hindu BusinessLine ({providerCounts.hbl})
          </button>
          <button
            onClick={() => setFilterProvider('OTHER')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all shrink-0 ${
              filterProvider === 'OTHER'
                ? 'bg-purple-500/15 border-purple-500 text-purple-400 shadow-sm'
                : 'bg-ub-surface border-ub-border text-ub-text-muted hover:border-ub-border/80 hover:text-ub-text-primary'
            }`}
          >
            <span>🔍</span> NSE Corporate / Others ({providerCounts.other})
          </button>
        </div>

        {/* Sort Filter Options Bar */}
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-ub-text-muted flex items-center gap-1 font-medium">
            <ArrowUpDown className="h-3.5 w-3.5 text-ub-accent" /> Sort By:
          </span>
          <select
            value={sortOption}
            onChange={(e) => setSortOption(e.target.value as SortOption)}
            className="h-8 px-2.5 text-xs bg-ub-surface border border-ub-border rounded-lg text-ub-text-primary focus:outline-none focus:border-ub-accent cursor-pointer font-medium"
          >
            <option value="latest">🕒 Latest First (Newest Date)</option>
            <option value="oldest">⏳ Oldest First</option>
            <option value="stocks_asc">🔤 Stock Ticker (A → Z)</option>
            <option value="stocks_desc">🔤 Stock Ticker (Z → A)</option>
            <option value="confidence">🎯 Highest AI Confidence</option>
            <option value="bullish">📈 Bullish / Buy Signals First</option>
            <option value="bearish">📉 Bearish / Sell Signals First</option>
          </select>
        </div>
      </div>

      {/* Content Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Card key={i} className="bg-ub-surface border-ub-border">
              <CardContent className="p-5 space-y-3">
                <div className="flex justify-between items-center">
                  <Skeleton className="h-5 w-24 rounded bg-ub-surface-active" />
                  <Skeleton className="h-5 w-16 rounded bg-ub-surface-active" />
                </div>
                <Skeleton className="h-12 w-full rounded bg-ub-surface-active" />
                <div className="flex justify-between items-center pt-2">
                  <Skeleton className="h-4 w-20 rounded bg-ub-surface-active" />
                  <Skeleton className="h-4 w-28 rounded bg-ub-surface-active" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : isError ? (
        <Card className="border-ub-loss/30 bg-ub-loss/5 p-8 text-center space-y-3">
          <p className="text-ub-loss font-medium">Failed to load live news feed.</p>
          <Button
            size="sm"
            onClick={() => refetch()}
            className="bg-ub-accent hover:bg-ub-accent-hover text-ub-background text-xs font-semibold"
          >
            Retry News Feed
          </Button>
        </Card>
      ) : filteredAndSortedItems && filteredAndSortedItems.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredAndSortedItems.map((item: any, idx: number) => {
            const sentiment = (item.sentiment || item.tradeAction || 'NEUTRAL').toUpperCase();
            const isBuy = sentiment === 'BUY' || sentiment === 'BULLISH';
            const isSell = sentiment === 'SELL' || sentiment === 'BEARISH';
            const relatedSymbols: string[] = item.symbols || (item.symbol ? [item.symbol] : []);

            return (
              <Card
                key={item.id || idx}
                className="bg-ub-surface border-ub-border hover:border-ub-accent/40 transition-all duration-200 shadow-sm flex flex-col justify-between"
              >
                <CardContent className="p-5 flex flex-col h-full space-y-3">
                  {/* Top Bar: Primary Symbol & Trade Sentiment Signal */}
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <Badge
                        variant="outline"
                        className="font-bold text-xs px-2 py-0.5 border-ub-accent/30 text-ub-accent bg-ub-accent/10 font-mono"
                      >
                        {item.symbol || 'NIFTY'}
                      </Badge>
                      {item.category && (
                        <span className="text-[11px] text-ub-text-muted px-1.5 py-0.5 rounded bg-ub-surface-hover border border-ub-border/50">
                          {item.category}
                        </span>
                      )}
                    </div>

                    {/* Trade Signal Badge */}
                    <div className="flex items-center gap-1">
                      {isBuy ? (
                        <Badge className="bg-ub-profit/15 hover:bg-ub-profit/20 text-ub-profit border border-ub-profit/30 font-semibold text-[11px] px-2 py-0.5 flex items-center gap-1">
                          <ArrowUpRight className="h-3 w-3" />
                          BUY SIGNAL
                        </Badge>
                      ) : isSell ? (
                        <Badge className="bg-ub-loss/15 hover:bg-ub-loss/20 text-ub-loss border border-ub-loss/30 font-semibold text-[11px] px-2 py-0.5 flex items-center gap-1">
                          <ArrowDownRight className="h-3 w-3" />
                          SELL SIGNAL
                        </Badge>
                      ) : (
                        <Badge className="bg-ub-text-muted/15 text-ub-text-muted border border-ub-border font-medium text-[11px] px-2 py-0.5 flex items-center gap-1">
                          <Minus className="h-3 w-3" />
                          NEUTRAL
                        </Badge>
                      )}
                    </div>
                  </div>

                  {/* News Headline with Direct Source Link */}
                  {(() => {
                    const isGenericUrl =
                      !item.url ||
                      item.url.endsWith('/markets') ||
                      item.url.endsWith('/markets/') ||
                      item.url.endsWith('/stocks/') ||
                      item.url.endsWith('corporate-filings-announcements') ||
                      item.url.endsWith('/news') ||
                      item.url.endsWith('/finance/') ||
                      item.url.split('/').length <= 4;

                    const articleUrl = !isGenericUrl
                      ? item.url
                      : `https://news.google.com/search?q=${encodeURIComponent(
                          (item.symbol ? item.symbol + ' ' : '') + item.headline
                        )}`;

                    return (
                      <>
                        <a
                          href={articleUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm font-semibold text-ub-text-primary leading-snug line-clamp-3 hover:text-ub-accent transition-colors flex items-start gap-1 group"
                          title="Click to open full live article directly"
                        >
                          <span className="flex-1">{item.headline}</span>
                          <ExternalLink className="h-3.5 w-3.5 opacity-50 group-hover:opacity-100 group-hover:text-ub-accent shrink-0 mt-0.5" />
                        </a>

                        {/* Summary / Impact Note if available */}
                        {item.summary && (
                          <p className="text-xs text-ub-text-muted line-clamp-2 leading-relaxed">
                            {item.summary}
                          </p>
                        )}

                        {/* Related Symbols / Tags */}
                        {relatedSymbols.length > 1 && (
                          <div className="flex items-center gap-1.5 flex-wrap pt-1">
                            <span className="text-[10px] text-ub-text-muted flex items-center gap-0.5">
                              <Tag className="h-2.5 w-2.5" /> Related:
                            </span>
                            {relatedSymbols.slice(0, 4).map((sym: string) => (
                              <span
                                key={sym}
                                className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-ub-surface-hover border border-ub-border text-ub-text-primary"
                              >
                                {sym}
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Bottom Metadata: Direct Article Verification Link & Published Time */}
                        <div className="flex items-center justify-between pt-3 mt-auto border-t border-ub-border text-xs gap-2">
                          <a
                            href={articleUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1.5 font-medium text-xs text-ub-accent hover:text-ub-accent-hover hover:underline bg-ub-accent/10 px-2 py-1 rounded-md transition-colors"
                            title="Read exact article on original publisher"
                          >
                            <span>{item.source || 'Live Source'}</span>
                            <ExternalLink className="h-3 w-3" />
                          </a>

                          <div className="flex items-center gap-2 text-[11px] text-ub-text-muted shrink-0">
                            {item.confidence && (
                              <span className="text-emerald-400 font-semibold text-[10px] bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded">
                                {item.confidence}% Conf.
                              </span>
                            )}
                            <div className="flex items-center gap-1">
                              <Clock className="h-3 w-3 text-ub-accent" />
                              <span>{item.publishedAt || item.timeAgo || 'Recently'}</span>
                            </div>
                          </div>
                        </div>
                      </>
                    );
                  })()}
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : (
        <Card className="bg-ub-surface border-ub-border p-12 text-center">
          <Newspaper className="w-12 h-12 mx-auto mb-4 opacity-20 text-ub-text-muted" />
          <h3 className="text-base font-semibold text-ub-text-primary mb-1">
            No matching news found
          </h3>
          <p className="text-xs text-ub-text-muted max-w-sm mx-auto mb-4">
            No news articles match your current provider filter ({filterProvider}), sentiment ({filterSentiment}), or search query.
          </p>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setFilterProvider('ALL');
              setFilterSentiment('ALL');
              setSearchQuery('');
            }}
            className="border-ub-border text-xs"
          >
            Reset Filters
          </Button>
        </Card>
      )}
    </div>
  );
}
