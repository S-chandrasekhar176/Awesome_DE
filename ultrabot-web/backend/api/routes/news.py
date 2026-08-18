"""Market News & NLP Sentiment Analysis API for UltraBot.

Provides real-time financial news aggregation, entity recognition for NSE symbols,
trade impact scoring, and sentiment classification across major Indian financial portals:
  - Economic Times
  - Moneycontrol
  - LiveMint
  - Business Standard
  - Google Finance & NSE Corporate filings
"""
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, status

from config.settings import settings
from news.news_engine import NewsEngine

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

router = APIRouter(tags=["news"])

_news_engine = NewsEngine(config=settings._raw_config)

def _compute_time_ago(timestamp_str: str) -> str:
    """Convert an RSS/ISO timestamp string into a human-readable 'X mins ago' string."""
    if not timestamp_str:
        return "Just now"
    now = datetime.now(IST)
    try:
        # Try ISO format first
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
    except (ValueError, TypeError):
        try:
            # Try RSS date format: "Sat, 16 Aug 2026 10:30:00 +0530"
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(timestamp_str)
        except Exception:
            return "Just now"

    diff = now - dt.astimezone(IST)
    total_seconds = int(diff.total_seconds())

    if total_seconds < 0:
        return "Just now"
    elif total_seconds < 60:
        return f"{total_seconds}s ago"
    elif total_seconds < 3600:
        mins = total_seconds // 60
        return f"{mins} min{'s' if mins > 1 else ''} ago"
    elif total_seconds < 86400:
        hrs = total_seconds // 3600
        return f"{hrs} hr{'s' if hrs > 1 else ''} ago"
    else:
        days = total_seconds // 86400
        return f"{days} day{'s' if days > 1 else ''} ago"


def _format_news_item(item: Dict[str, Any], idx: int) -> Dict[str, Any]:
    symbols = item.get("relevant_symbols") or item.get("symbols", [])
    sym = symbols[0] if isinstance(symbols, list) and len(symbols) > 0 else (symbols if isinstance(symbols, str) and symbols else "NIFTY")
    sym_list = symbols if isinstance(symbols, list) and symbols else [sym]

    raw_sent = str(item.get("sentiment", "neutral")).lower()
    if "pos" in raw_sent or "bull" in raw_sent or "buy" in raw_sent:
        sentiment = "BUY"
        trade_action = "BUY"
    elif "neg" in raw_sent or "bear" in raw_sent or "sell" in raw_sent:
        sentiment = "SELL"
        trade_action = "SELL"
    else:
        sentiment = "NEUTRAL"
        trade_action = "HOLD"

    src = item.get("source", "Market News")
    src_lower = src.lower()
    if "economic" in src_lower or "et " in src_lower:
        provider_code = "ET"
    elif "ndtv" in src_lower:
        provider_code = "NDTV"
    elif "livemint" in src_lower or "mint" in src_lower:
        provider_code = "LM"
    elif "hindu" in src_lower or "businessline" in src_lower:
        provider_code = "HBL"
    elif "nse" in src_lower:
        provider_code = "NSE"
    elif "result" in src_lower:
        provider_code = "RC"
    else:
        provider_code = "OTHER"

    impact = str(item.get("impact_level", "medium")).upper()
    raw_ts = item.get("timestamp") or item.get("published_at") or ""
    time_ago = _compute_time_ago(raw_ts)

    return {
        "symbol": sym.upper(),
        "symbols": [s.upper() for s in sym_list],
        "price": float(item.get("price", 0.0) or 0.0),
        "changePct": float(item.get("changePct", 0.0) or 0.0),
        "headline": item.get("headline") or item.get("title") or "Live NSE Market Update",
        "summary": item.get("summary", ""),
        "source": src,
        "providerCode": provider_code,
        "category": item.get("category", "Market Action").title(),
        "sentiment": sentiment,
        "impactLevel": impact,
        "tradeAction": trade_action,
        "confidence": int(item.get("confidence", 80)),
        "timeAgo": time_ago,
        "publishedAt": time_ago,
        "publishedTimestamp": int(time.time() * 1000) - (idx * 60000),
        "timestamp": datetime.now(IST).strftime("%H:%M IST"),
        "url": item.get("url", ""),
    }


_news_cache: List[Dict[str, Any]] = []
_news_cache_timestamp: float = 0.0

@router.get("/api/news")
@router.get("/api/live-news")
@router.get("/api/news/sentiment")
async def get_latest_news() -> List[Dict[str, Any]]:
    """Fetch latest real-time analyzed market news with NLP sentiment and trade signals from live scrapers."""
    global _news_cache, _news_cache_timestamp
    now = time.time()

    # Return cached news if fresh (< 60 seconds)
    if _news_cache and (now - _news_cache_timestamp < 60.0):
        return _news_cache

    try:
        raw_items = await _news_engine.run_full_scan()

        if raw_items and len(raw_items) > 0:
            formatted = [_format_news_item(item, idx) for idx, item in enumerate(raw_items)]
            _news_cache = formatted
            _news_cache_timestamp = now
            return formatted

        return _news_cache or []
    except Exception as exc:
        logger.error("Live news scan encountered error: %s", exc, exc_info=True)
        return _news_cache or []


@router.get("/api/news-focus-stocks")
@router.get("/news-focus-stocks")
async def get_news_focus_stocks() -> Dict[str, Any]:
    """Fetch news-driven catalyst focus stocks for the watchlist with sentiment analysis and real-time live prices."""
    import asyncio
    try:
        news_items = await get_latest_news()
        focus_stocks = []
        seen_symbols = set()

        symbols_to_fetch = []
        for item in news_items:
            sym = (item.get("symbol") or "").upper()
            if sym and sym not in ("NIFTY", "BANKNIFTY", "MARKET") and sym not in seen_symbols:
                symbols_to_fetch.append(sym)
                seen_symbols.add(sym)

        live_quotes = {}
        if symbols_to_fetch:
            from api.routes.candles import _fetch_realtime_quotes_sync
            live_quotes = await asyncio.to_thread(_fetch_realtime_quotes_sync, symbols_to_fetch)

        seen_symbols.clear()
        for item in news_items:
            sym = (item.get("symbol") or "").upper()
            if not sym or sym in ("NIFTY", "BANKNIFTY", "MARKET") or sym in seen_symbols:
                continue
            seen_symbols.add(sym)

            raw_sent = item.get("sentiment", "BUY")
            sent = "BUY" if raw_sent in ("BUY", "POSITIVE", "BULLISH") else "SELL" if raw_sent in ("SELL", "NEGATIVE", "BEARISH") else "WATCH"

            q = live_quotes.get(sym, {})
            live_price = float(q.get("price") or 0.0)
            live_change_pct = float(q.get("changePct") or 0.0)

            focus_stocks.append({
                "symbol": sym,
                "name": f"{sym} (NSE)",
                "price": live_price,
                "changePct": live_change_pct,
                "headline": item.get("headline", "Major catalyst reported in market news"),
                "source": item.get("source", "Live News"),
                "sentiment": sent,
                "catalyst": item.get("summary") or item.get("headline") or "Live high-impact news catalyst",
                "url": item.get("url", ""),
                "publishedAt": item.get("publishedAt") or item.get("timeAgo") or "Live",
            })

        return {
            "success": True,
            "count": len(focus_stocks),
            "data": focus_stocks,
        }
    except Exception as exc:
        logger.error("Failed to build news focus stocks: %s", exc, exc_info=True)
        return {
            "success": True,
            "count": 0,
            "data": [],
        }

