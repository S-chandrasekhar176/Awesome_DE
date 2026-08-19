from typing import Any, Dict, List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

from brokers.base import BaseBroker
from fees.nse_fee_calculator import NSEFeeCalculator
from utils.market_utils import get_lot_size

IST = ZoneInfo("Asia/Kolkata")


class PaperBroker(BaseBroker):
    """Paper/simulated broker for backtesting and paper trading.

    Tracks virtual capital, positions, and calculates real NSE fees.
    Uses an external feed (set via .feed attribute) for LTP data.
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        fee_calculator: Optional[NSEFeeCalculator] = None,
        repository=None,
    ):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.fee_calculator = fee_calculator or NSEFeeCalculator()
        self.repository = repository
        self.feed: Any = None  # Injected externally (e.g. FeedManager)
        self.positions: Dict[str, Dict[str, Any]] = {}  # symbol -> position info
        self.orders: Dict[str, Dict[str, Any]] = {}  # order_id -> order info
        self._order_counter = 0

    @staticmethod
    def _ist_now() -> str:
        return datetime.now(IST).isoformat()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(IST)

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"PAPER-{self._order_counter:06d}"

    async def authenticate(self) -> Dict[str, Any]:
        return {"success": True, "message": "Paper broker always authenticated", "broker": "paper"}

    async def get_ltp(self, symbol: str, exchange: str = "NSE") -> float:
        if self.feed is not None:
            try:
                ltp = await self.feed.get_ltp(symbol) if hasattr(self.feed, 'get_ltp') and callable(getattr(self.feed.get_ltp, '__call__', None)) else self.feed.get_ltp(symbol)
                if ltp and ltp > 0:
                    return float(ltp)
            except Exception:
                pass
        return 0.0

    async def get_margin(self) -> Dict[str, float]:
        capital_in_use = 0.0
        for pos in self.positions.values():
            if pos.get("status") == "OPEN":
                capital_in_use += pos.get("invested_amount", 0.0)
        return {
            "total": round(self.capital, 2),
            "available": round(self.capital - capital_in_use, 2),
            "used": round(capital_in_use, 2),
        }

    async def place_order(
        self,
        symbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        price: float,
        order_type: str = "MARKET",
        product: str = "MIS",
        segment: str = "EQ",
    ) -> Dict[str, Any]:
        # Get real LTP from feed for market orders
        if order_type.upper() == "MARKET":
            ltp = await self.get_ltp(symbol, exchange)
            if ltp > 0:
                price = ltp
            # If feed not available, use passed price as is

        order_value = price * quantity
        margin_info = await self.get_margin()
        available = margin_info["available"]

        if transaction_type.upper() == "BUY" and order_value > available:
            return {
                "success": False,
                "order_id": None,
                "message": f"Insufficient margin: need ₹{order_value:.2f}, available ₹{available:.2f}",
            }

        # Calculate fees for the entry leg
        if transaction_type.upper() == "BUY":
            entry_fees = self.fee_calculator.calculate_equity_intraday(
                buy_price=price, sell_price=price, quantity=quantity
            )
        else:
            entry_fees = self.fee_calculator.calculate_equity_intraday(
                buy_price=price, sell_price=price, quantity=quantity
            )

        order_id = self._next_order_id()
        now = self._ist_now()

        order = {
            "order_id": order_id,
            "symbol": symbol,
            "exchange": exchange,
            "transaction_type": transaction_type.upper(),
            "quantity": quantity,
            "price": round(price, 2),
            "order_type": order_type.upper(),
            "product": product,
            "segment": segment,
            "status": "FILLED",
            "filled_qty": quantity,
            "filled_price": round(price, 2),
            "order_time": now,
            "fees": entry_fees["total"],
        }
        self.orders[order_id] = order

        tx_type = transaction_type.upper()
        if tx_type in ("BUY", "SELL"):
            direction = "LONG" if tx_type == "BUY" else "SHORT"
            if symbol in self.positions and self.positions[symbol].get("status") == "OPEN" and self.positions[symbol].get("direction") == direction:
                pos = self.positions[symbol]
                old_qty = pos["quantity"]
                old_avg = pos["entry_price"]
                new_qty = old_qty + quantity
                pos["quantity"] = new_qty
                pos["entry_price"] = round((old_avg * old_qty + price * quantity) / new_qty, 2)
                pos["invested_amount"] = round(pos["entry_price"] * new_qty, 2)
            else:
                pos = {
                    "id": f"pos-{order_id}",
                    "symbol": symbol,
                    "exchange": exchange,
                    "direction": direction,
                    "quantity": quantity,
                    "entry_price": round(price, 2),
                    "current_price": round(price, 2),
                    "invested_amount": round(price * quantity, 2),
                    "status": "OPEN",
                    "entry_time": now,
                    "product": product,
                    "segment": segment,
                    "fees_paid": entry_fees["total"],
                    "unrealized_pnl": 0.0,
                }
                self.positions[symbol] = pos

            if self.repository is not None:
                try:
                    await self.repository.create_position(
                        symbol=symbol,
                        exchange=exchange,
                        direction=direction,
                        quantity=quantity,
                        entry_price=round(price, 2),
                        invested_amount=round(price * quantity, 2),
                        status="OPEN",
                        entry_time=now,
                        product=product,
                        segment=segment,
                        fees_paid=entry_fees["total"],
                    )
                except Exception:
                    pass

        return {
            "success": True,
            "order_id": order_id,
            "message": f"Paper order filled: {transaction_type} {quantity} {symbol} @ ₹{price:.2f}",
            "filled_price": round(price, 2),
        }

    async def close_position(
        self,
        symbol: str,
        qty: Optional[int] = None,
        exit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        if symbol not in self.positions:
            return {"success": False, "message": f"No open position for {symbol}"}

        pos = self.positions[symbol]
        if pos.get("status") != "OPEN":
            return {"success": False, "message": f"Position for {symbol} is not open"}

        close_qty = qty if qty is not None else pos["quantity"]
        if close_qty > pos["quantity"]:
            close_qty = pos["quantity"]

        if exit_price is None:
            exit_price = await self.get_ltp(symbol, pos.get("exchange", "NSE"))
            if exit_price <= 0:
                exit_price = pos["current_price"]

        entry_price = pos["entry_price"]
        direction = pos.get("direction", "LONG")
        segment = pos.get("segment", "EQ")
        lot_size = get_lot_size(symbol) if segment.upper() == "OPT" else 1

        pnl_result = self.fee_calculator.calculate_net_pnl(
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=close_qty,
            direction=direction,
            segment=segment,
            mode="intraday" if pos.get("product") == "MIS" else "delivery",
            lot_size=lot_size,
        )

        net_pnl = pnl_result["net_pnl"]
        self.capital += net_pnl

        remaining_qty = pos["quantity"] - close_qty
        if remaining_qty <= 0:
            pos["status"] = "CLOSED"
            pos["exit_price"] = round(exit_price, 2)
            pos["exit_time"] = self._ist_now()
            pos["realized_pnl"] = net_pnl
            pos["fees_total"] = pnl_result["fees"]
        else:
            pos["quantity"] = remaining_qty
            pos["invested_amount"] = round(pos["entry_price"] * remaining_qty, 2)

        if self.repository is not None:
            try:
                if remaining_qty <= 0:
                    await self.repository.update_position(
                        pos["id"],
                        status="CLOSED",
                        exit_price=round(exit_price, 2),
                        exit_time=self._ist_now(),
                        realized_pnl=net_pnl,
                        fees_total=pnl_result["fees"],
                    )
                else:
                    await self.repository.update_position(
                        pos["id"],
                        quantity=remaining_qty,
                        invested_amount=round(pos["entry_price"] * remaining_qty, 2),
                    )

                await self.repository.create_trade(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    exit_price=round(exit_price, 2),
                    quantity=close_qty,
                    pnl=pnl_result["gross_pnl"],
                    fees=pnl_result["fees"],
                    net_pnl=net_pnl,
                    status="CLOSED",
                    entry_time=pos["entry_time"],
                    exit_time=self._ist_now(),
                    segment=segment,
                    product=pos.get("product", "MIS"),
                )
            except Exception:
                pass

        return {
            "success": True,
            "symbol": symbol,
            "closed_qty": close_qty,
            "remaining_qty": remaining_qty,
            "entry_price": entry_price,
            "exit_price": round(exit_price, 2),
            "gross_pnl": pnl_result["gross_pnl"],
            "fees": pnl_result["fees"],
            "net_pnl": net_pnl,
            "capital_after": round(self.capital, 2),
        }

    async def update_position_prices(self) -> List[Dict[str, Any]]:
        updated = []
        for symbol, pos in self.positions.items():
            if pos.get("status") != "OPEN":
                continue
            ltp = await self.get_ltp(symbol, pos.get("exchange", "NSE"))
            if ltp <= 0:
                continue
            pos["current_price"] = round(ltp, 2)
            direction = pos.get("direction", "LONG")
            if direction == "LONG":
                pos["unrealized_pnl"] = round((ltp - pos["entry_price"]) * pos["quantity"], 2)
            else:
                pos["unrealized_pnl"] = round((pos["entry_price"] - ltp) * pos["quantity"], 2)
            updated.append({
                "symbol": symbol,
                "ltp": round(ltp, 2),
                "unrealized_pnl": pos["unrealized_pnl"],
            })
        return updated

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if order_id not in self.orders:
            return {"success": False, "message": f"Order {order_id} not found"}
        order = self.orders[order_id]
        if order["status"] != "FILLED":
            order["status"] = "CANCELLED"
            return {"success": True, "message": f"Order {order_id} cancelled"}
        return {"success": False, "message": f"Cannot cancel filled order {order_id}"}

    async def get_positions(self) -> List[Dict[str, Any]]:
        return [
            pos for pos in self.positions.values() if pos.get("status") == "OPEN"
        ]

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        if order_id not in self.orders:
            return {"success": False, "message": f"Order {order_id} not found"}
        order = self.orders[order_id]
        return {
            "success": True,
            "order_id": order_id,
            "status": order["status"],
            "symbol": order["symbol"],
            "filled_qty": order["filled_qty"],
            "filled_price": order["filled_price"],
            "transaction_type": order["transaction_type"],
        }

    def get_name(self) -> str:
        return "paper"
