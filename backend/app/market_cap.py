from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import time


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


_CACHE: Dict[str, tuple[float, MarketCapResult]] = {}
CACHE_TTL_SECONDS = 60 * 15  # 15 minutes


def get_market_cap_mm_yfinance(ticker: str) -> Optional[MarketCapResult]:
    """
    Fetch market cap in $mm using yfinance.
    Returns None if fetch fails.
    Never raises.
    """

    try:
        t = (ticker or "").strip().upper()
        if not t:
            return None

        now = time.time()

        # Cache check
        cached = _CACHE.get(t)
        if cached and cached[0] > now:
            return cached[1]

        yf = _yf()
        ticker_obj = yf.Ticker(t)

        fi: Dict[str, Any] = {}
        info: Dict[str, Any] = {}

        # ---------------------------
        # Try fast_info first (preferred)
        # ---------------------------
        try:
            fi = dict(ticker_obj.fast_info or {})
        except Exception:
            fi = {}

        mc = fi.get("market_cap")
        currency = fi.get("currency") or "USD"

        # ---------------------------
        # Fallback to .info only if needed
        # ---------------------------
        if mc is None:
            try:
                info = dict(ticker_obj.info or {})
                mc = info.get("marketCap")
                currency = info.get("currency") or currency
            except Exception:
                info = {}

        # ---------------------------
        # Final fallback: price * shares
        # ---------------------------
        if mc is None:
            price = (
                fi.get("last_price")
                or fi.get("regular_market_price")
                or info.get("regularMarketPrice")
                or info.get("currentPrice")
            )
            shares = (
                fi.get("shares_outstanding")
                or info.get("sharesOutstanding")
            )

            if price and shares:
                try:
                    mc = float(price) * float(shares)
                except Exception:
                    mc = None

        if mc is None:
            return None

        result = MarketCapResult(
            market_cap_mm=float(mc) / 1e6,
            currency=str(currency),
            as_of_utc=datetime.now(timezone.utc).isoformat(),
            source="yfinance_fast_info",
            details={
                "marketCap_raw": mc,
                "fast_info_keys": sorted(list(fi.keys()))[:30],
            },
        )

        _CACHE[t] = (now + CACHE_TTL_SECONDS, result)
        return result

    except Exception:
        # Absolute safety net — never crash job creation
        return None

# from __future__ import annotations
# from dataclasses import dataclass
# from datetime import datetime, timezone
# from typing import Optional, Dict, Any
# import time

# def _yf():
#     import yfinance as yf
#     return yf

# @dataclass
# class MarketCapResult:
#     market_cap_mm: float
#     currency: str
#     as_of_utc: str
#     source: str
#     details: Dict[str, Any]

# _CACHE: Dict[str, tuple[float, float, MarketCapResult]] = {}
# CACHE_TTL_SECONDS = 60 * 15  # 15 minutes

# def get_market_cap_mm_yfinance(ticker: str) -> Optional[MarketCapResult]:
#     t = (ticker or "").strip().upper()
#     if not t:
#         return None

#     now = time.time()
#     cached = _CACHE.get(t)
#     if cached and cached[0] > now:
#         return cached[2]

#     yf = _yf()
#     ticker_obj = yf.Ticker(t)

#     info: Dict[str, Any] = {}      # <-- ALWAYS defined
#     fi: Dict[str, Any] = {}        # <-- ALWAYS defined

#     # Prefer fast_info (lighter / more reliable)
#     try:
#         fi = dict(ticker_obj.fast_info or {})
#     except Exception:
#         fi = {}

#     mc = fi.get("market_cap")
#     currency = fi.get("currency") or "USD"

#     # Fallback to .info only if needed (can be blocked in cloud)
#     if mc is None:
#         try:
#             info = dict(ticker_obj.info or {})
#             mc = info.get("marketCap")
#             currency = info.get("currency") or currency
#         except Exception:
#             info = {}

#     # If still missing, try compute market cap from price * shares
#     if mc is None:
#         price = (
#             fi.get("last_price")
#             or fi.get("regular_market_price")
#             or info.get("regularMarketPrice")
#             or info.get("currentPrice")
#         )
#         shares = fi.get("shares_outstanding") or info.get("sharesOutstanding")
#         if price and shares:
#             try:
#                 mc = float(price) * float(shares)
#             except Exception:
#                 mc = None

#     if mc is None:
#         return None

#     # Build safe details without assuming info exists
#     details = {
#         "marketCap": mc,
#         "currency": currency,
#         "fast_info_keys": sorted(list(fi.keys()))[:40],
#     }
#     if info:
#         details.update({
#             "raw_info_keys": sorted(list(info.keys()))[:40],
#             "regularMarketPrice": info.get("regularMarketPrice"),
#             "sharesOutstanding": info.get("sharesOutstanding"),
#         })

#     result = MarketCapResult(
#         market_cap_mm=float(mc) / 1e6,
#         currency=str(currency),
#         as_of_utc=datetime.now(timezone.utc).isoformat(),
#         source="yfinance_fast_info",
#         details=details,
#     )

#     _CACHE[t] = (now + CACHE_TTL_SECONDS, result.market_cap_mm, result)
#     return result
