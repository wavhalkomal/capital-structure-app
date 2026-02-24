from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import time

# Lazy import so backend still boots even if missing
def _yf():
    import yfinance as yf
    return yf

@dataclass
class MarketCapResult:
    market_cap_mm: float
    currency: str
    as_of_utc: str
    source: str
    details: Dict[str, Any]

# Simple in-memory cache (good enough for challenge)
_CACHE: Dict[str, tuple[float, float, MarketCapResult]] = {}
# key -> (expires_epoch, market_cap_mm, result)
CACHE_TTL_SECONDS = 60 * 15  # 15 minutes

def get_market_cap_mm_yfinance(ticker: str) -> Optional[MarketCapResult]:
    t = (ticker or "").strip().upper()
    if not t:
        return None

    now = time.time()
    cached = _CACHE.get(t)
    if cached and cached[0] > now:
        return cached[2]

    yf = _yf()
    info = yf.Ticker(t).info  # network call

    # yfinance sometimes gives marketCap directly (best case)
    mc = info.get("marketCap")
    currency = info.get("currency") or "USD"

    # If marketCap not present, compute from price * shares
    if mc is None:
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        shares = info.get("sharesOutstanding")
        if price and shares:
            mc = float(price) * float(shares)

    if mc is None:
        return None

    result = MarketCapResult(
        market_cap_mm=float(mc) / 1e6,
        currency=str(currency),
        as_of_utc=datetime.now(timezone.utc).isoformat(),
        source="yfinance",
        details={
            "raw_info_keys": sorted(list(info.keys()))[:40],  # keep it small
            "marketCap": mc,
            "regularMarketPrice": info.get("regularMarketPrice"),
            "sharesOutstanding": info.get("sharesOutstanding"),
        },
    )

    _CACHE[t] = (now + CACHE_TTL_SECONDS, result.market_cap_mm, result)
    return result