"""F&O stock universe, sector mapping, and market utility functions for NSE.
"""
from typing import Dict, List, Optional


# ────────────────────────────────────────────────────────────────
# F&O Stock Universe (major NSE F&O stocks)
# ────────────────────────────────────────────────────────────────

FNO_UNIVERSE: List[Dict[str, str | int]] = [
    {"symbol": "RELIANCE", "name": "Reliance Industries Ltd", "sector": "Energy", "lot_size": 250},
    {"symbol": "TCS", "name": "Tata Consultancy Services Ltd", "sector": "IT", "lot_size": 150},
    {"symbol": "HDFCBANK", "name": "HDFC Bank Ltd", "sector": "Banking", "lot_size": 550},
    {"symbol": "INFY", "name": "Infosys Ltd", "sector": "IT", "lot_size": 300},
    {"symbol": "ICICIBANK", "name": "ICICI Bank Ltd", "sector": "Banking", "lot_size": 700},
    {"symbol": "HINDUNILVR", "name": "Hindustan Unilever Ltd", "sector": "FMCG", "lot_size": 300},
    {"symbol": "SBIN", "name": "State Bank of India", "sector": "Banking", "lot_size": 750},
    {"symbol": "BHARTIARTL", "name": "Bharti Airtel Ltd", "sector": "Telecom", "lot_size": 475},
    {"symbol": "ITC", "name": "ITC Ltd", "sector": "FMCG", "lot_size": 1600},
    {"symbol": "KOTAKBANK", "name": "Kotak Mahindra Bank Ltd", "sector": "Banking", "lot_size": 400},
    {"symbol": "LT", "name": "Larsen & Toubro Ltd", "sector": "Infrastructure", "lot_size": 150},
    {"symbol": "AXISBANK", "name": "Axis Bank Ltd", "sector": "Banking", "lot_size": 900},
    {"symbol": "BAJFINANCE", "name": "Bajaj Finance Ltd", "sector": "Finance", "lot_size": 125},
    {"symbol": "MARUTI", "name": "Maruti Suzuki India Ltd", "sector": "Auto", "lot_size": 50},
    {"symbol": "TITAN", "name": "Titan Company Ltd", "sector": "Consumer", "lot_size": 175},
    {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical Industries Ltd", "sector": "Pharma", "lot_size": 700},
    {"symbol": "TATAMOTORS", "name": "Tata Motors Ltd", "sector": "Auto", "lot_size": 550},
    {"symbol": "WIPRO", "name": "Wipro Ltd", "sector": "IT", "lot_size": 1500},
    {"symbol": "ULTRACEMCO", "name": "UltraTech Cement Ltd", "sector": "Cement", "lot_size": 200},
    {"symbol": "ADANIENT", "name": "Adani Enterprises Ltd", "sector": "Conglomerate", "lot_size": 250},
    {"symbol": "TATASTEEL", "name": "Tata Steel Ltd", "sector": "Metals", "lot_size": 475},
    {"symbol": "POWERGRID", "name": "Power Grid Corporation of India Ltd", "sector": "Power", "lot_size": 1200},
    {"symbol": "NTPC", "name": "NTPC Ltd", "sector": "Power", "lot_size": 1750},
    {"symbol": "HCLTECH", "name": "HCL Technologies Ltd", "sector": "IT", "lot_size": 350},
    {"symbol": "ASIANPAINT", "name": "Asian Paints Ltd", "sector": "Consumer", "lot_size": 200},
    {"symbol": "BAJAJFINSV", "name": "Bajaj Finserv Ltd", "sector": "Finance", "lot_size": 125},
    {"symbol": "DRREDDY", "name": "Dr Reddy's Laboratories Ltd", "sector": "Pharma", "lot_size": 125},
    {"symbol": "CIPLA", "name": "Cipla Ltd", "sector": "Pharma", "lot_size": 500},
    {"symbol": "ONGC", "name": "Oil & Natural Gas Corporation Ltd", "sector": "Energy", "lot_size": 900},
    {"symbol": "COALINDIA", "name": "Coal India Ltd", "sector": "Mining", "lot_size": 1200},
    {"symbol": "JSWSTEEL", "name": "JSW Steel Ltd", "sector": "Metals", "lot_size": 500},
    {"symbol": "INDUSINDBK", "name": "IndusInd Bank Ltd", "sector": "Banking", "lot_size": 300},
    {"symbol": "HINDALCO", "name": "Hindalco Industries Ltd", "sector": "Metals", "lot_size": 1050},
    {"symbol": "GRASIM", "name": "Grasim Industries Ltd", "sector": "Cement", "lot_size": 250},
    {"symbol": "TECHM", "name": "Tech Mahindra Ltd", "sector": "IT", "lot_size": 550},
    {"symbol": "EICHERMOT", "name": "Eicher Motors Ltd", "sector": "Auto", "lot_size": 50},
    {"symbol": "M&M", "name": "Mahindra & Mahindra Ltd", "sector": "Auto", "lot_size": 175},
    {"symbol": "DIVISLAB", "name": "Divi's Laboratories Ltd", "sector": "Pharma", "lot_size": 250},
    {"symbol": "BPCL", "name": "Bharat Petroleum Corporation Ltd", "sector": "Energy", "lot_size": 900},
    {"symbol": "HEROMOTOCO", "name": "Hero Motocorp Ltd", "sector": "Auto", "lot_size": 100},
    {"symbol": "APOLLOHOSP", "name": "Apollo Hospitals Enterprise Ltd", "sector": "Healthcare", "lot_size": 250},
    {"symbol": "BRITANNIA", "name": "Britannia Industries Ltd", "sector": "FMCG", "lot_size": 150},
    {"symbol": "HINDPETRO", "name": "HPCL", "sector": "Energy", "lot_size": 900},
    {"symbol": "SBILIFE", "name": "SBI Life Insurance Company Ltd", "sector": "Insurance", "lot_size": 500},
    {"symbol": "TATACONSUM", "name": "Tata Consumer Products Ltd", "sector": "FMCG", "lot_size": 475},
    {"symbol": "DABUR", "name": "Dabur India Ltd", "sector": "FMCG", "lot_size": 700},
    {"symbol": "PIDILITIND", "name": "Pidilite Industries Ltd", "sector": "Chemicals", "lot_size": 400},
    {"symbol": "VEDL", "name": "Vedanta Ltd", "sector": "Metals", "lot_size": 1215},
    {"symbol": "ADANIPORTS", "name": "Adani Ports & SEZ Ltd", "sector": "Infrastructure", "lot_size": 250},
    {"symbol": "AMBUJACEM", "name": "Ambuja Cements Ltd", "sector": "Cement", "lot_size": 700},
]

# Build lookup dicts
_SYMBOL_MAP: Dict[str, Dict] = {s["symbol"]: s for s in FNO_UNIVERSE}
_SECTOR_MAP: Dict[str, str] = {s["symbol"]: s["sector"] for s in FNO_UNIVERSE}
_LOT_SIZE_MAP: Dict[str, int] = {s["symbol"]: s["lot_size"] for s in FNO_UNIVERSE}
_FNO_SYMBOLS: set = set(_SYMBOL_MAP.keys())


# ────────────────────────────────────────────────────────────────
# Sector grouping
# ────────────────────────────────────────────────────────────────

def get_sectors() -> Dict[str, List[str]]:
    """Return a dict mapping sector name to list of symbols."""
    sectors: Dict[str, List[str]] = {}
    for stock in FNO_UNIVERSE:
        sec = stock["sector"]
        sectors.setdefault(sec, []).append(stock["symbol"])
    return sectors


# ────────────────────────────────────────────────────────────────
# Public helpers
# ────────────────────────────────────────────────────────────────

def is_fno_stock(symbol: str) -> bool:
    """Check if a symbol is part of the F&O universe."""
    return symbol.upper() in _FNO_SYMBOLS


def get_stock_sector(symbol: str) -> str:
    """Get the sector for a stock. Returns 'Unknown' if not found."""
    return _SECTOR_MAP.get(symbol.upper(), "Unknown")


def get_lot_size(symbol: str) -> int:
    """Get the F&O lot size for a stock. Returns 1 if not found."""
    return _LOT_SIZE_MAP.get(symbol.upper(), 1)


def get_stock_info(symbol: str) -> Optional[Dict]:
    """Get full stock info dict for a symbol. Returns None if not found."""
    return _SYMBOL_MAP.get(symbol.upper())


def get_symbols_by_sector(sector: str) -> List[str]:
    """Get all F&O symbols in a given sector."""
    return [s["symbol"] for s in FNO_UNIVERSE if s["sector"] == sector]


def get_all_fno_symbols() -> List[str]:
    """Get all F&O symbols as a sorted list."""
    return sorted(_FNO_SYMBOLS)
