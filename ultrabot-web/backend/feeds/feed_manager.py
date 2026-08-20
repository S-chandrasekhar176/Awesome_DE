import logging
import time
from typing import Any, Dict, List, Optional

from feeds.base import BaseFeed
from feeds.yahoo_historical import YahooHistoricalFeed

logger = logging.getLogger(__name__)


class FeedManager:
    """Manage primary and backup market data feeds.

    Tries the primary feed first for LTP/candles.
    Falls back to backup if primary fails or returns 0.
    Supports health checking and automatic failover.
    """

    def __init__(
        self,
        primary: Optional[BaseFeed] = None,
        backup: Optional[BaseFeed] = None,
    ):
        self.primary = primary or YahooHistoricalFeed()
        self.backup = backup
        self._using_backup = False
        self._primary_failure_count = 0
        self._max_failures_before_switch = 3
        self._last_health_check: float = 0
        self._primary_healthy = True

    async def get_ltp(self, symbol: str) -> float:
        """Get LTP, trying primary first, then backup."""
        if not self._using_backup:
            try:
                ltp = await self.primary.get_ltp(symbol)
                if ltp > 0:
                    self._primary_failure_count = 0
                    return ltp
                self._primary_failure_count += 1
            except Exception as e:
                logger.warning("Primary feed LTP error for %s: %s", symbol, e)
                self._primary_failure_count += 1

            if self._primary_failure_count >= self._max_failures_before_switch:
                await self.switch_to_backup()

        if self.backup is not None:
            try:
                ltp = await self.backup.get_ltp(symbol)
                if ltp and ltp > 0:
                    return float(ltp)
            except Exception as e:
                logger.warning("Backup feed LTP error for %s: %s", symbol, e)

        return 0.0

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "5m",
        count: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get candles, trying primary first, then backup."""
        if not self._using_backup:
            try:
                candles = await self.primary.get_candles(symbol, timeframe, count)
                if candles:
                    self._primary_failure_count = 0
                    return candles
                self._primary_failure_count += 1
            except Exception as e:
                logger.warning("Primary feed candle error for %s: %s", symbol, e)
                self._primary_failure_count += 1

            if self._primary_failure_count >= self._max_failures_before_switch:
                await self.switch_to_backup()

        if self.backup is not None:
            try:
                candles = await self.backup.get_candles(symbol, timeframe, count)
                if candles:
                    return candles
            except Exception as e:
                logger.warning("Backup feed candle error for %s: %s", symbol, e)

        return []

    async def subscribe(self, symbols: List[str]) -> Dict[str, Any]:
        if not self._using_backup:
            return await self.primary.subscribe(symbols)
        if self.backup is not None:
            return await self.backup.subscribe(symbols)
        return {"success": False, "message": "No active feed"}

    async def unsubscribe(self, symbols: List[str]) -> Dict[str, Any]:
        if not self._using_backup:
            return await self.primary.unsubscribe(symbols)
        if self.backup is not None:
            return await self.backup.unsubscribe(symbols)
        return {"success": False, "message": "No active feed"}

    async def switch_to_backup(self) -> Dict[str, Any]:
        if self.backup is None:
            logger.warning("No backup feed configured, cannot switch")
            return {"success": False, "message": "No backup feed available"}
        self._using_backup = True
        logger.warning("Switched to backup feed: %s", self.backup.get_name())
        return {"success": True, "message": f"Switched to backup: {self.backup.get_name()}", "backup_feed": self.backup.get_name()}

    async def switch_to_primary(self) -> Dict[str, Any]:
        self._using_backup = False
        self._primary_failure_count = 0
        logger.info("Switched back to primary feed: %s", self.primary.get_name())
        return {"success": True, "message": f"Switched to primary: {self.primary.get_name()}", "primary_feed": self.primary.get_name()}

    async def health_check(self) -> Dict[str, Any]:
        """Check if feeds are alive."""
        self._last_health_check = time.time()
        results = {}

        # Check primary
        try:
            primary_ok = self.primary.is_connected()
            if not primary_ok and hasattr(self.primary, 'connect'):
                result = await self.primary.connect()
                primary_ok = result.get("success", False)
            results["primary"] = {
                "name": self.primary.get_name(),
                "connected": primary_ok,
                "failure_count": self._primary_failure_count,
            }
            self._primary_healthy = primary_ok
            if primary_ok:
                await self.switch_to_primary()
        except Exception as e:
            results["primary"] = {"name": self.primary.get_name(), "connected": False, "error": str(e)}
            self._primary_healthy = False

        # Check backup
        if self.backup is not None:
            try:
                backup_ok = self.backup.is_connected()
                results["backup"] = {
                    "name": self.backup.get_name(),
                    "connected": backup_ok,
                }
            except Exception as e:
                results["backup"] = {"name": self.backup.get_name(), "connected": False, "error": str(e)}

        results["using_backup"] = self._using_backup
        return results

    def get_active_feed(self) -> BaseFeed:
        if self._using_backup and self.backup is not None:
            return self.backup
        return self.primary

    def get_status(self) -> Dict[str, Any]:
        return {
            "primary": self.primary.get_name(),
            "backup": self.backup.get_name() if self.backup else None,
            "using_backup": self._using_backup,
            "primary_failures": self._primary_failure_count,
            "primary_healthy": self._primary_healthy,
        }

    async def connect(self) -> Dict[str, Any]:
        result = await self.primary.connect()
        if self.backup is not None:
            backup_result = await self.backup.connect()
            result["backup"] = backup_result
        return result

    async def disconnect(self) -> Dict[str, Any]:
        result = await self.primary.disconnect()
        if self.backup is not None:
            backup_result = await self.backup.disconnect()
            result["backup"] = backup_result
        return result

    async def get_latest_price(self, symbol: str) -> float:
        """Get the latest price (LTP) for a symbol."""
        return await self.get_ltp(symbol)

