'use client';

export interface Position {
  id: string;
  symbol: string;
  direction: 'BUY' | 'SELL';
  entry: number;
  current: number;
  quantity: number;
  remainingQty: number;
  stopLoss: number;
  target: number;
  unrealizedPnl: number;
  unrealizedPnlPct: number;
  strategy: string;
  sector: string;
  type: string;
  margin: number;
  enteredAt: string;
  bookedLevels: { level: number; achieved: boolean }[];
}

export type StoredPosition = Position;

export interface TradeHistoryItem {
  id: string;
  symbol: string;
  direction: 'BUY' | 'SELL';
  entryPrice: number;
  exitPrice: number;
  quantity: number;
  pnl: number;
  pnlPercent: number;
  strategy: string;
  exitReason: 'TARGET' | 'STOP_LOSS' | 'MANUAL' | 'SQUAREOFF';
  enteredAt: string;
  exitedAt: string;
}

const POSITIONS_KEY = 'ultrabot_open_positions';
const TRADES_HISTORY_KEY = 'ultrabot_trade_history';
const CONFIRMED_OPPS_KEY = 'ultrabot_confirmed_opportunities';

export function getStoredPositions(): Position[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(POSITIONS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveStoredPositions(positions: Position[]) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(POSITIONS_KEY, JSON.stringify(positions));
    window.dispatchEvent(new Event('ultrabot_positions_updated'));
  } catch { }
}

export function getStoredTradeHistory(): TradeHistoryItem[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(TRADES_HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveStoredTradeHistory(trades: TradeHistoryItem[]) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(TRADES_HISTORY_KEY, JSON.stringify(trades));
    window.dispatchEvent(new Event('ultrabot_trades_updated'));
  } catch { }
}

export function getConfirmedOppIds(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(CONFIRMED_OPPS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function addConfirmedOppId(id: string) {
  if (typeof window === 'undefined') return;
  try {
    const ids = getConfirmedOppIds();
    if (!ids.includes(id)) {
      ids.push(id);
      localStorage.setItem(CONFIRMED_OPPS_KEY, JSON.stringify(ids));
      window.dispatchEvent(new Event('ultrabot_opportunities_updated'));
    }
  } catch { }
}

const SKIPPED_OPPS_KEY = 'ultrabot_skipped_opportunities';

export function getSkippedOppIds(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(SKIPPED_OPPS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function addSkippedOppId(id: string) {
  if (typeof window === 'undefined') return;
  try {
    const ids = getSkippedOppIds();
    if (!ids.includes(id)) {
      ids.push(id);
      localStorage.setItem(SKIPPED_OPPS_KEY, JSON.stringify(ids));
      window.dispatchEvent(new Event('ultrabot_opportunities_updated'));
    }
  } catch { }
}

export function executeOpportunityTrade(opp: {
  id: string;
  symbol: string;
  direction: 'BUY' | 'SELL';
  entry: number;
  stopLoss: number;
  target: number;
  quantity: number;
  strategy: string;
  sector?: string;
  type?: string;
  margin?: number;
}): Position {
  const existing = getStoredPositions();

  const newPos: Position = {
    id: `pos-${Date.now()}-${opp.symbol}`,
    symbol: opp.symbol,
    direction: opp.direction,
    entry: opp.entry,
    current: opp.entry,
    quantity: opp.quantity || 50,
    remainingQty: opp.quantity || 50,
    stopLoss: opp.stopLoss,
    target: opp.target,
    unrealizedPnl: 0,
    unrealizedPnlPct: 0,
    strategy: opp.strategy || 'Breakout',
    sector: opp.sector || 'Equities',
    type: opp.type || 'EQ',
    margin: opp.margin || +(opp.entry * (opp.quantity || 50) * 0.2).toFixed(2),
    enteredAt: new Date().toISOString(),
    bookedLevels: [
      { level: 1, achieved: false },
      { level: 2, achieved: false },
      { level: 3, achieved: false },
    ],
  };

  const updated = [newPos, ...existing.filter((p) => p.symbol !== opp.symbol)];
  saveStoredPositions(updated);
  addConfirmedOppId(opp.id);

  return newPos;
}

export function modifyStoredPosition(
  id: string,
  updates: { stopLoss?: number; target?: number; remainingQty?: number }
): boolean {
  const positions = getStoredPositions();
  const index = positions.findIndex((p) => p.id === id);
  if (index === -1) return false;

  const currentPos = positions[index];
  positions[index] = {
    ...currentPos,
    stopLoss: updates.stopLoss !== undefined ? updates.stopLoss : currentPos.stopLoss,
    target: updates.target !== undefined ? updates.target : currentPos.target,
    remainingQty: updates.remainingQty !== undefined ? updates.remainingQty : currentPos.remainingQty,
  };

  saveStoredPositions(positions);
  return true;
}

export function updateStoredPositionsWithLivePrices(quotes: Record<string, { price: number }>): Position[] {
  const positions = getStoredPositions();
  if (positions.length === 0) return positions;

  let changed = false;
  const updated = positions.map((pos) => {
    const quote = quotes[pos.symbol];
    if (quote && quote.price > 0 && quote.price !== pos.current) {
      changed = true;
      const currentPrice = quote.price;
      const pnl = pos.direction === 'BUY'
        ? (currentPrice - pos.entry) * pos.remainingQty
        : (pos.entry - currentPrice) * pos.remainingQty;
      const pnlPct = +(((currentPrice - pos.entry) / pos.entry) * 100 * (pos.direction === 'BUY' ? 1 : -1)).toFixed(2);

      // Auto check booked levels
      const bookedLevels = pos.bookedLevels.map((lvl) => {
        const targetDiff = Math.abs(pos.target - pos.entry);
        const levelPrice = pos.direction === 'BUY'
          ? pos.entry + (targetDiff * (lvl.level / 3))
          : pos.entry - (targetDiff * (lvl.level / 3));
        const achieved = pos.direction === 'BUY' ? currentPrice >= levelPrice : currentPrice <= levelPrice;
        return { ...lvl, achieved: lvl.achieved || achieved };
      });

      return {
        ...pos,
        current: currentPrice,
        unrealizedPnl: +pnl.toFixed(2),
        unrealizedPnlPct: pnlPct,
        bookedLevels,
      };
    }
    return pos;
  });

  if (changed) {
    saveStoredPositions(updated);
  }
  return updated;
}

export function closeStoredPosition(
  id: string,
  exitPrice?: number,
  exitReason: 'MANUAL' | 'TARGET' | 'STOP_LOSS' | 'SQUAREOFF' = 'MANUAL'
): boolean {
  const positions = getStoredPositions();
  const targetPos = positions.find((p) => p.id === id);
  if (!targetPos) return false;

  const currentPrice = exitPrice ?? targetPos.current;
  const pnl = targetPos.direction === 'BUY'
    ? (currentPrice - targetPos.entry) * targetPos.remainingQty
    : (targetPos.entry - currentPrice) * targetPos.remainingQty;
  const pnlPct = +(((currentPrice - targetPos.entry) / targetPos.entry) * 100 * (targetPos.direction === 'BUY' ? 1 : -1)).toFixed(2);

  const historyItem: TradeHistoryItem = {
    id: `trade-${Date.now()}`,
    symbol: targetPos.symbol,
    direction: targetPos.direction,
    entryPrice: targetPos.entry,
    exitPrice: currentPrice,
    quantity: targetPos.remainingQty,
    pnl: +pnl.toFixed(2),
    pnlPercent: pnlPct,
    strategy: targetPos.strategy,
    exitReason,
    enteredAt: targetPos.enteredAt,
    exitedAt: new Date().toISOString(),
  };

  const history = getStoredTradeHistory();
  saveStoredTradeHistory([historyItem, ...history]);

  const remainingPositions = positions.filter((p) => p.id !== id);
  saveStoredPositions(remainingPositions);

  return true;
}

export function isSafeSquareoffTime(autoSquareoffTimeStr: string = '15:15'): boolean {
  try {
    const now = new Date();
    const istNow = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
    const day = istNow.getDay(); // 0 is Sun, 6 is Sat
    if (day === 0 || day === 6) return true; // Weekend

    const parts = autoSquareoffTimeStr.split(':').map(Number);
    const sqHour = !isNaN(parts[0]) ? parts[0] : 15;
    const sqMin = !isNaN(parts[1]) ? parts[1] : 15;

    const currentMins = istNow.getHours() * 60 + istNow.getMinutes();
    const squareoffMins = sqHour * 60 + sqMin;
    const marketOpenMins = 9 * 60 + 15;

    // If past safe square-off time (15:15) or before market open (closed)
    if (currentMins >= squareoffMins || currentMins < marketOpenMins) {
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

export function checkAndAutoSquareoffPositions(autoSquareoffTimeStr: string = '15:15'): Position[] {
  if (!isSafeSquareoffTime(autoSquareoffTimeStr)) {
    return getStoredPositions();
  }

  const positions = getStoredPositions();
  if (positions.length === 0) return [];

  const history = getStoredTradeHistory();
  const newTrades: TradeHistoryItem[] = positions.map((pos) => {
    const currentPrice = pos.current || pos.entry;
    const pnl = pos.direction === 'BUY'
      ? (currentPrice - pos.entry) * pos.remainingQty
      : (pos.entry - currentPrice) * pos.remainingQty;
    const pnlPct = +(((currentPrice - pos.entry) / pos.entry) * 100 * (pos.direction === 'BUY' ? 1 : -1)).toFixed(2);

    return {
      id: `trade-${Date.now()}-${pos.symbol}`,
      symbol: pos.symbol,
      direction: pos.direction,
      entryPrice: pos.entry,
      exitPrice: currentPrice,
      quantity: pos.remainingQty,
      pnl: +pnl.toFixed(2),
      pnlPercent: pnlPct,
      strategy: pos.strategy,
      exitReason: 'SQUAREOFF',
      enteredAt: pos.enteredAt,
      exitedAt: new Date().toISOString(),
    };
  });

  saveStoredTradeHistory([...newTrades, ...history]);
  saveStoredPositions([]);
  return [];
}

export function clearAllPaperData() {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(POSITIONS_KEY);
    localStorage.removeItem(TRADES_HISTORY_KEY);
    localStorage.removeItem(CONFIRMED_OPPS_KEY);
    localStorage.removeItem(SKIPPED_OPPS_KEY);
    window.dispatchEvent(new Event('ultrabot_positions_updated'));
    window.dispatchEvent(new Event('ultrabot_trades_updated'));
    window.dispatchEvent(new Event('ultrabot_opportunities_updated'));
  } catch { }
}
