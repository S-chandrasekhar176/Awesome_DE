import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from api.dependencies import get_current_user, get_repository
from db.repository import Repository
from models.watchlist_item import WatchlistItemCreate, WatchlistItemResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

# Known F&O stocks (Nifty 50 + major F&O stocks)
_FNO_UNIVERSE = [
    ("RELIANCE", "Reliance Industries Ltd"), ("TCS", "Tata Consultancy Services"),
    ("HDFCBANK", "HDFC Bank Ltd"), ("INFY", "Infosys Ltd"),
    ("ICICIBANK", "ICICI Bank Ltd"), ("HINDUNILVR", "Hindustan Unilever Ltd"),
    ("ITC", "ITC Ltd"), ("SBIN", "State Bank of India"),
    ("BHARTIARTL", "Bharti Airtel Ltd"), ("KOTAKBANK", "Kotak Mahindra Bank"),
    ("LT", "Larsen & Toubro Ltd"), ("AXISBANK", "Axis Bank Ltd"),
    ("BAJFINANCE", "Bajaj Finance Ltd"), ("MARUTI", "Maruti Suzuki India"),
    ("SUNPHARMA", "Sun Pharmaceutical Industries"), ("TATAMOTORS", "Tata Motors Ltd"),
    ("WIPRO", "Wipro Ltd"), ("ULTRACEMCO", "UltraTech Cement Ltd"),
    ("TITAN", "Titan Company Ltd"), ("NESTLEIND", "Nestle India Ltd"),
    ("NTPC", "NTPC Ltd"), ("POWERGRID", "Power Grid Corporation"),
    ("ONGC", "Oil & Natural Gas Corp"), ("TATASTEEL", "Tata Steel Ltd"),
    ("HCLTECH", "HCL Technologies"), ("COALINDIA", "Coal India Ltd"),
    ("BAJAJFINSV", "Bajaj Finserv Ltd"), ("INDUSINDBK", "IndusInd Bank Ltd"),
    ("ADANIENT", "Adani Enterprises Ltd"), ("TECHM", "Tech Mahindra Ltd"),
    ("GRASIM", "Grasim Industries Ltd"), ("ASIANPAINT", "Asian Paints Ltd"),
    ("M_M", "Mahindra & Mahindra Ltd"), ("HEROMOTOCO", "Hero MotoCorp Ltd"),
    ("DRREDDY", "Dr Reddy's Laboratories"), ("DIVISLAB", "Divi's Laboratories"),
    ("CIPLA", "Cipla Ltd"), ("EICHERMOT", "Eicher Motors Ltd"),
    ("BPCL", "Bharat Petroleum Corp"), ("HINDALCO", "Hindalco Industries"),
    ("APOLLOHOSP", "Apollo Hospitals Enterprise"), ("JSWSTEEL", "JSW Steel Ltd"),
    ("TATACONSUM", "Tata Consumer Products"), ("BRITANNIA", "Britannia Industries"),
    ("DABUR", "Dabur India Ltd"), ("PIDILITIND", "Pidilite Industries"),
    ("MARICO", "Marico Ltd"), ("HAL", "Hindustan Aeronautics Ltd"),
    ("BEL", "Bharat Electronics Ltd"), ("ADANIPORTS", "Adani Ports & SEZ"),
    ("SHRIRAMFIN", "Shriram Finance Ltd"), ("LICI", "Life Insurance Corp"),
    ("HDBANK", "HDFC Bank Ltd"), ("ADANIGREEN", "Adani Green Energy"),
    ("TRENT", "Trent Ltd"), ("VEDL", "Vedanta Ltd"),
    ("WELSPUNLIV", "Welspun Living Ltd"), ("SBILIFE", "SBI Life Insurance"),
    ("BERGEPAINT", "Berger Paints India"), ("AMBUJACEM", "Ambuja Cements"),
    ("HINDPETRO", "Hindustan Petroleum Corp"), ("SIEMENS", "Siemens Ltd"),
    ("ABBOTINDIA", "Abbott India Ltd"), ("DLF", "DLF Ltd"),
    ("PNB", "Punjab National Bank"), ("CANBK", "Canara Bank"),
    ("BANKBARODA", "Bank of Baroda"), ("IDFCFIRSTB", "IDFC First Bank"),
    ("MUTHOOTFIN", "Muthoot Finance Ltd"), ("YESBANK", "Yes Bank Ltd"),
    ("INDIGO", "IndiGo Airlines"), ("ZOMATO", "Zomato Ltd"),
    ("IRFC", "IRFC Ltd"), ("RVNL", "RVNL"),
    ("IRCTC", "IRCTC Ltd"), ("TATAPOWER", "Tata Power Company"),
    ("SUZLON", "Suzlon Energy Ltd"), ("NHPC", "NHPC Ltd"),
    ("NTPC", "NTPC Ltd"), ("JPPOWER", "Jaiprakash Power Ventures"),
    ("ADANIPOWER", "Adani Power Ltd"), ("TATAELXSI", "Tata Elxsi Ltd"),
    ("MCDOWELL-N", "United Spirits Ltd"), ("BATAINDIA", "Bata India Ltd"),
    ("VBL", "Varun Beverages Ltd"), ("LAURUSLABS", "Laurus Labs Ltd"),
    ("BALRAMCHIN", "Balrampur Chini Mills"), ("TRIDENT", "Trident Ltd"),
    ("IGL", "Indraprastha Gas Ltd"), ("MGL", "Mahanagar Gas Ltd"),
    ("GAIL", "GAIL (India) Ltd"), ("PETRONET", "Petronet LNG Ltd"),
    ("POWERGRID", "Power Grid Corp"), ("NATIONALUM", "National Aluminium"),
    ("NMDC", "NMDC Ltd"), ("SAIL", "Steel Authority of India"),
    ("HINDCOPPER", "Hindustan Copper Ltd"), ("TATAMETALI", "Tata Metaliks"),
    ("JINDALSTEL", "Jindal Steel & Power"),
]


@router.get("")
async def get_watchlist(
    username: str = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
) -> List[Dict[str, Any]]:
    """Get all active watchlist items."""
    try:
        items = await repo.get_active_watchlist()
        return [
            {
                "id": item.id,
                "symbol": item.symbol,
                "name": item.name,
                "sector": item.sector,
                "lot_size": item.lot_size,
                "is_fno": item.is_fno,
                "is_active": item.is_active,
                "added_at": item.added_at,
                "last_scanned_at": item.last_scanned_at,
                "last_signal_at": item.last_signal_at,
            }
            for item in items
        ]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get watchlist: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch watchlist: {str(exc)}",
        )


@router.post("/add")
async def add_to_watchlist(
    body: WatchlistItemCreate,
    username: str = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
) -> Dict[str, Any]:
    """Manually add a stock to the watchlist."""
    try:
        # Check if already exists
        existing = await repo.get_watchlist_item_by_symbol(body.symbol)
        if existing is not None:
            # Re-activate if inactive
            if not existing.is_active:
                await repo.update_watchlist_item(existing.id, is_active=True)
                return {
                    "message": f"'{body.symbol}' re-activated in watchlist",
                    "id": existing.id,
                    "symbol": body.symbol,
                }
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"'{body.symbol}' already exists in watchlist",
            )

        item = await repo.add_watchlist_item(
            symbol=body.symbol,
            name=body.name,
            sector=body.sector,
            lot_size=body.lot_size,
            is_fno=body.is_fno,
            is_active=body.is_active,
            extra=body.extra,
        )

        return {
            "message": f"'{body.symbol}' added to watchlist",
            "id": item.id,
            "symbol": item.symbol,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to add watchlist item: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add watchlist item: {str(exc)}",
        )


@router.delete("/{symbol}")
async def remove_from_watchlist(
    symbol: str,
    username: str = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
) -> Dict[str, Any]:
    """Remove a stock from the watchlist (deactivate it)."""
    try:
        # Find by symbol
        item = await repo.get_watchlist_item_by_symbol(symbol)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{symbol}' not found in watchlist",
            )

        # Deactivate rather than delete
        await repo.update_watchlist_item(item.id, is_active=False)

        return {
            "message": f"'{symbol}' removed from watchlist",
            "id": item.id,
            "symbol": symbol,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to remove watchlist item: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove watchlist item: {str(exc)}",
        )


@router.get("/universe")
async def get_fno_universe(
    username: str = Depends(get_current_user),
) -> List[Dict[str, str]]:
    """Return all known F&O stocks."""
    return [
        {"symbol": sym, "name": name}
        for sym, name in _FNO_UNIVERSE
    ]
