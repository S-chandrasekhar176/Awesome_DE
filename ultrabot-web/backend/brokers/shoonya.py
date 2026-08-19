import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
import pyotp

import httpx

from brokers.base import BaseBroker
from brokers.token_manager import TokenManager
from errors.error_types import BrokerError, ConnectionLostError, TokenExpiredError

logger = logging.getLogger(__name__)

# Shoonya Noren REST API endpoints
_BASE_URL = "https://api.shoonya.com/NorenWClientTP"
_LOGIN_URL = f"{_BASE_URL}/QuickAuth"
_QUOTE_URL = f"{_BASE_URL}/GetQuotes"
_MARGIN_URL = f"{_BASE_URL}/Limits"
_ORDER_URL = f"{_BASE_URL}/PlaceOrder"
_CANCEL_URL = f"{_BASE_URL}/CancelOrder"
_ORDER_STATUS_URL = f"{_BASE_URL}/OrderBook"
_POSITIONS_URL = f"{_BASE_URL}/PositionBook"
_HOLDINGS_URL = f"{_BASE_URL}/Holdings"

# Standard NSE symbol token mapping for Shoonya (Noren API)
_TOKEN_MAP: Dict[str, str] = {
    "RELIANCE": "2885",
    "TCS": "11536",
    "INFY": "1594",
    "HDFCBANK": "1333",
    "ICICIBANK": "4963",
    "SBIN": "3045",
    "BHARTIARTL": "10604",
    "ITC": "1660",
    "TATAMOTORS": "3456",
    "LT": "11483",
    "BAJFINANCE": "317",
    "MARUTI": "10999",
    "SUNPHARMA": "3351",
    "WIPRO": "3787",
    "AXISBANK": "5900",
    "KOTAKBANK": "1922",
    "HCLTECH": "7229",
    "TATASTEEL": "3499",
    "TITAN": "3506",
    "ASIANPAINT": "236",
    "HINDUNILVR": "1394",
    "ADANIENT": "25",
    "ADANIPORTS": "15083",
    "BAJAJFINSV": "16675",
    "BAJAJ-AUTO": "16669",
    "BPCL": "526",
    "CIPLA": "694",
    "COALINDIA": "20374",
    "DRREDDY": "881",
    "EICHERMOT": "910",
    "GRASIM": "1232",
    "HEROMOTOCO": "1348",
    "HINDALCO": "1363",
    "INDUSINDBK": "5258",
    "JSWSTEEL": "11723",
    "M&M": "2031",
    "NESTLEIND": "17963",
    "NTPC": "11630",
    "ONGC": "2475",
    "POWERGRID": "14977",
    "TECHM": "13538",
    "ULTRACEMCO": "11532",
    "APOLLOHOSP": "157",
    "BRITANNIA": "547",
    "DIVISLAB": "10940",
    "HDFCLIFE": "467",
    "SBILIFE": "21808",
    "LTIM": "17818",
    "SHRIRAMFIN": "4306",
    "TRENT": "1964",
    "BEL": "383",
    "NIFTY": "26000",
    "BANKNIFTY": "26009",
    "FINNIFTY": "26037",
    "MIDCPNIFTY": "26074",
}


class ShoonyaBroker(BaseBroker):
    """Shoonya (Noren) broker integration.

    Uses httpx for HTTP calls to Shoonya's Noren REST API.
    Requires user_id, password, vendor_code, app_key, and TOTP secret for authentication.
    """

    def __init__(
        self,
        user_id: str = "",
        password: str = "",
        vendor_code: str = "",
        app_key: str = "",
        totp_secret: str = "",
        factor2_pin: str = "",
        token_manager: Optional[TokenManager] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(config)
        self.user_id = user_id or self.config.get("user_id", "")
        self.password = password or self.config.get("password", "")
        self.vendor_code = vendor_code or self.config.get("vendor_code", "")
        self.app_key = app_key or self.config.get("app_key", "")
        self.totp_secret = totp_secret or self.config.get("totp_secret", "")
        self.factor2_pin = factor2_pin or self.config.get("factor2_pin", "")
        self.token_manager = token_manager or TokenManager()
        self._client: Optional[httpx.AsyncClient] = None
        self._authenticated = False
        self._session_token: str = ""

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=_BASE_URL,
                timeout=30.0,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
        return self._client

    def _auth_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._session_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @staticmethod
    def _sha256(data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    async def authenticate(self) -> Dict[str, Any]:
        try:
            client = self._get_client()
            password_hash = self._sha256(self.password)
            
            # Generate TOTP 2FA if secret provided, else pin or fallback
            factor2 = self.factor2_pin.strip()
            if self.totp_secret and self.totp_secret.strip():
                try:
                    cleaned_totp = self.totp_secret.replace(" ", "").upper()
                    factor2 = pyotp.TOTP(cleaned_totp).now()
                except Exception as e:
                    logger.warning("Failed to generate TOTP for Shoonya: %s", e)
            if not factor2:
                factor2 = password_hash

            app_key_hash = self._sha256(f"{self.user_id}|{self.app_key}") if self.app_key else ""

            payload = {
                "uid": self.user_id,
                "pwd": password_hash,
                "factor2": factor2,
                "vc": self.vendor_code,
                "appkey": app_key_hash or self.app_key,
                "deviceType": "WEB",
            }

            # Shoonya uses form-encoded data
            response = await client.post(_LOGIN_URL, data=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("stat") == "Ok":
                self._session_token = data.get("susertoken", "")
                self._authenticated = True

                self.token_manager.store_token(
                    broker_name="shoonya",
                    access_token=self._session_token,
                    refresh_token="",
                    extra={
                        "actid": data.get("actid", self.user_id),
                        "ls": data.get("ls", ""),
                    },
                )

                logger.info("Shoonya authentication successful for user %s", self.user_id)
                return {"success": True, "message": "Authenticated with Shoonya"}
            else:
                msg = data.get("emsg", "Login failed")
                logger.error("Shoonya auth failed: %s", msg)
                return {"success": False, "message": msg}

        except httpx.HTTPStatusError as e:
            logger.error("Shoonya auth HTTP error: %s", e)
            return {"success": False, "message": f"HTTP error {e.response.status_code}"}
        except httpx.RequestError as e:
            logger.error("Shoonya connection error: %s", e)
            return {"success": False, "message": f"Connection error: {str(e)}"}
        except Exception as e:
            logger.error("Shoonya auth unexpected error: %s", e)
            return {"success": False, "message": str(e)}

    async def _refresh_if_needed(self) -> bool:
        if self.token_manager.is_expired("shoonya"):
            result = await self.authenticate()
            return result.get("success", False)
        return False

    async def get_ltp(self, symbol: str, exchange: str = "NSE") -> float:
        await self._refresh_if_needed()
        token_id = _TOKEN_MAP.get(symbol.upper())
        if token_id and self._authenticated and self._session_token:
            try:
                client = self._get_client()
                payload = {
                    "uid": self.user_id,
                    "exch": exchange,
                    "token": token_id,
                }
                response = await client.post(_QUOTE_URL, data=payload, headers=self._auth_headers())
                if response.status_code == 200:
                    data = response.json()
                    if data.get("stat") == "Ok":
                        lp_str = data.get("lp", "0")
                        if lp_str and float(lp_str) > 0:
                            return float(lp_str)
            except TokenExpiredError:
                raise
            except Exception as e:
                logger.warning("Failed to get Shoonya direct LTP for %s: %s", symbol, e)

        # Real-time fallback to market feed / Yahoo
        try:
            from feeds.feed_manager import FeedManager
            feed = FeedManager()
            price = await feed.get_latest_price(symbol)
            if price and price > 0:
                return float(price)
        except Exception:
            pass
        return 0.0

    async def get_margin(self) -> Dict[str, float]:
        await self._refresh_if_needed()
        try:
            client = self._get_client()
            payload = {"uid": self.user_id}
            response = await client.post(_MARGIN_URL, data=payload, headers=self._auth_headers())
            response.raise_for_status()
            data = response.json()

            if data.get("stat") == "Ok":
                return {
                    "total": float(data.get("eqmargin", {}).get("net", 0)),
                    "available": float(data.get("eqmargin", {}).get("availablecash", 0)),
                    "used": float(data.get("eqmargin", {}).get("utilisedmargin", 0)),
                }
            return {"total": 0.0, "available": 0.0, "used": 0.0}
        except Exception as e:
            logger.error("Failed to get margin: %s", e)
            return {"total": 0.0, "available": 0.0, "used": 0.0}

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
        await self._refresh_if_needed()
        try:
            client = self._get_client()

            # Shoonya transaction type codes
            tx_type = "B" if transaction_type.upper() == "BUY" else "S"
            prctyp = "MKT" if order_type.upper() == "MARKET" else "LMT"

            # Shoonya product codes
            shoonya_product = {"MIS": "I", "CNC": "C", "NRML": "M"}
            prod_code = shoonya_product.get(product, "I")

            payload = {
                "uid": self.user_id,
                "actid": self.user_id,
                "exch": exchange,
                "tsym": symbol,
                "qty": str(quantity),
                "prc": "0" if order_type.upper() == "MARKET" else str(price),
                "prctyp": prctyp,
                "ret": "DAY",
                "trantype": tx_type,
                "prd": prod_code,
            }

            response = await client.post(_ORDER_URL, data=payload, headers=self._auth_headers())
            response.raise_for_status()
            data = response.json()

            if data.get("stat") == "Ok":
                order_id = data.get("norenordno", "")
                return {
                    "success": True,
                    "order_id": order_id,
                    "message": f"Order placed: {transaction_type} {quantity} {symbol}",
                }
            else:
                return {
                    "success": False,
                    "order_id": None,
                    "message": data.get("emsg", "Order placement failed"),
                }
        except Exception as e:
            logger.error("Failed to place order for %s: %s", symbol, e)
            return {"success": False, "order_id": None, "message": str(e)}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        await self._refresh_if_needed()
        try:
            client = self._get_client()
            payload = {
                "uid": self.user_id,
                "norenordno": order_id,
            }
            response = await client.post(_CANCEL_URL, data=payload, headers=self._auth_headers())
            response.raise_for_status()
            data = response.json()

            if data.get("stat") == "Ok":
                return {"success": True, "message": f"Order {order_id} cancelled"}
            return {"success": False, "message": data.get("emsg", "Cancel failed")}
        except Exception as e:
            logger.error("Failed to cancel order %s: %s", order_id, e)
            return {"success": False, "message": str(e)}

    async def get_positions(self) -> List[Dict[str, Any]]:
        await self._refresh_if_needed()
        try:
            client = self._get_client()
            payload = {"uid": self.user_id, "actid": self.user_id}
            response = await client.post(_POSITIONS_URL, data=payload, headers=self._auth_headers())
            response.raise_for_status()
            data = response.json()

            if data.get("stat") == "Ok":
                positions = []
                for item in data.get("poslist", []):
                    net_qty = int(item.get("netqty", "0"))
                    if net_qty == 0:
                        continue
                    positions.append({
                        "symbol": item.get("tsym", ""),
                        "exchange": item.get("exch", ""),
                        "quantity": abs(net_qty),
                        "avg_price": float(item.get("avgprc", 0)),
                        "pnl": float(item.get("pnl", 0)),
                        "side": "LONG" if net_qty > 0 else "SHORT",
                    })
                return positions
            return []
        except Exception as e:
            logger.error("Failed to get positions: %s", e)
            return []

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        await self._refresh_if_needed()
        try:
            client = self._get_client()
            payload = {"uid": self.user_id, "norenordno": order_id}
            response = await client.post(_ORDER_STATUS_URL, data=payload, headers=self._auth_headers())
            response.raise_for_status()
            data = response.json()

            if data.get("stat") == "Ok":
                orders = data.get("ordlist", [])
                if orders:
                    order = orders[0]
                    return {
                        "success": True,
                        "order_id": order_id,
                        "status": order.get("status", "UNKNOWN"),
                        "filled_qty": int(order.get("fillshares", "0")),
                        "filled_price": float(order.get("avgprc", "0")),
                        "symbol": order.get("tsym", ""),
                        "transaction_type": "BUY" if order.get("trantype", "") == "B" else "SELL",
                    }
            return {"success": False, "message": "Order not found"}
        except Exception as e:
            logger.error("Failed to get order status for %s: %s", order_id, e)
            return {"success": False, "message": str(e)}

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def get_name(self) -> str:
        return "shoonya"
