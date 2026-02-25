from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
import time
import os

import requests


@dataclass
class MarketCapResult:
    market_cap_mm: float
    currency: str
    as_of_utc: str
    source: str
    details: Dict[str, Any]


# Simple in-memory cache (good enough for your use-case)
_CACHE: Dict[str, Tuple[float, MarketCapResult]] = {}
CACHE_TTL_SECONDS = 60 * 15  # 15 minutes


def _cache_get(ticker: str) -> Optional[MarketCapResult]:
    now = time.time()
    item = _CACHE.get(ticker)
    if not item:
        return None
    expires_at, val = item
    if expires_at <= now:
        _CACHE.pop(ticker, None)
        return None
    return val


def _cache_set(ticker: str, val: MarketCapResult) -> MarketCapResult:
    _CACHE[ticker] = (time.time() + CACHE_TTL_SECONDS, val)
    return val


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_ticker(ticker: str) -> Optional[str]:
    t = (ticker or "").strip().upper()
    return t or None



def _fetch_fmp_profile(ticker: str, api_key: str) -> Optional[MarketCapResult]:
    """
    Preferred provider: Financial Modeling Prep (FMP) profile endpoint.
    https://financialmodelingprep.com/api/v3/profile/AAP?apikey=...
    Usually reliable from cloud hosts. Never raises.
    """
    try:
        api_key = (api_key or "").strip()
        if not api_key:
            return None

        url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}"
        r = requests.get(url, params={"apikey": api_key}, timeout=10)
        if r.status_code != 200:
            return None

        data = r.json()
        # FMP returns a list of profile objects
        if not isinstance(data, list) or not data:
            return None

        row = data[0] or {}
        mc = row.get("mktCap") or row.get("marketCap")  # tolerate naming differences
        currency = row.get("currency") or "USD"

        if mc is None:
            return None

        return MarketCapResult(
            market_cap_mm=float(mc) / 1e6,
            currency=str(currency),
            as_of_utc=_now_iso(),
            source="fmp_profile",
            details={
                "mktCap_raw": mc,
                "companyName": row.get("companyName"),
                "exchange": row.get("exchange") or row.get("exchangeShortName"),
            },
        )
    except Exception:
        return None

def _fetch_yahoo_quote_endpoint(ticker: str) -> Optional[MarketCapResult]:
    """
    Fallback provider: Yahoo quote endpoint
    https://query1.finance.yahoo.com/v7/finance/quote?symbols=AAP
    This often works even when yfinance .info is flaky, but can still be blocked.
    Never raises.
    """
    try:
        url = "https://query1.finance.yahoo.com/v7/finance/quote"
        params = {"symbols": ticker}

        # Headers matter on some cloud hosts
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }

        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code != 200:
            return None

        data = r.json()
        result = (data or {}).get("quoteResponse", {}).get("result", [])
        if not result:
            return None

        row = result[0] or {}
        mc = row.get("marketCap")
        currency = row.get("currency") or "USD"

        if mc is None:
            return None

        return MarketCapResult(
            market_cap_mm=float(mc) / 1e6,
            currency=str(currency),
            as_of_utc=_now_iso(),
            source="yahoo_v7_quote",
            details={
                "marketCap_raw": mc,
                "shortName": row.get("shortName"),
                "exchange": row.get("fullExchangeName") or row.get("exchange"),
            },
        )
    except Exception:
        return None


def _fetch_yfinance_fast(ticker: str) -> Optional[MarketCapResult]:
    """
    Primary provider: yfinance fast_info (lighter & more reliable than .info).
    Never raises.
    """
    try:
        import yfinance as yf  # import inside to keep module import stable

        tkr = yf.Ticker(ticker)

        fi: Dict[str, Any] = {}
        try:
            fi = dict(tkr.fast_info or {})
        except Exception:
            fi = {}

        mc = fi.get("market_cap")
        currency = fi.get("currency") or "USD"

        if mc is None:
            return None

        return MarketCapResult(
            market_cap_mm=float(mc) / 1e6,
            currency=str(currency),
            as_of_utc=_now_iso(),
            source="yfinance_fast_info",
            details={
                "marketCap_raw": mc,
                "fast_info_keys_sample": sorted(list(fi.keys()))[:40],
            },
        )
    except Exception:
        return None


def get_market_cap_mm_yfinance(ticker: str) -> Optional[MarketCapResult]:
    """
    Backward-compatible name (your code calls this).

    Internally we do:
      cache -> FMP (if FMP_API_KEY is set) -> yfinance fast_info -> Yahoo quote endpoint

    Never raises.
    """
    t = _normalize_ticker(ticker)
    if not t:
        return None

    cached = _cache_get(t)
    if cached:
        return cached

    # 1) FMP (recommended for cloud deployments)
    fmp_key = (os.getenv("FMP_API_KEY") or "").strip()
    res = _fetch_fmp_profile(t, fmp_key)
    if res:
        return _cache_set(t, res)

    # 2) yfinance fast_info
    res = _fetch_yfinance_fast(t)
    if res:
        return _cache_set(t, res)

    # 3) fallback: direct Yahoo endpoint
    res = _fetch_yahoo_quote_endpoint(t)
    if res:
        return _cache_set(t, res)

    return None

    cached = _cache_get(t)
    if cached:
        return cached

    # 1) yfinance fast_info
    res = _fetch_yfinance_fast(t)
    if res:
        return _cache_set(t, res)

    # 2) fallback: direct Yahoo endpoint
    res = _fetch_yahoo_quote_endpoint(t)
    if res:
        return _cache_set(t, res)

    return None



# from __future__ import annotations

# from dataclasses import dataclass
# from datetime import datetime, timezone
# from typing import Optional, Dict, Any, Tuple
# import time

# import requests


# @dataclass
# class MarketCapResult:
#     market_cap_mm: float
#     currency: str
#     as_of_utc: str
#     source: str
#     details: Dict[str, Any]


# # Simple in-memory cache (good enough for your use-case)
# _CACHE: Dict[str, Tuple[float, MarketCapResult]] = {}
# CACHE_TTL_SECONDS = 60 * 15  # 15 minutes


# def _cache_get(ticker: str) -> Optional[MarketCapResult]:
#     now = time.time()
#     item = _CACHE.get(ticker)
#     if not item:
#         return None
#     expires_at, val = item
#     if expires_at <= now:
#         _CACHE.pop(ticker, None)
#         return None
#     return val


# def _cache_set(ticker: str, val: MarketCapResult) -> MarketCapResult:
#     _CACHE[ticker] = (time.time() + CACHE_TTL_SECONDS, val)
#     return val


# def _now_iso() -> str:
#     return datetime.now(timezone.utc).isoformat()


# def _normalize_ticker(ticker: str) -> Optional[str]:
#     t = (ticker or "").strip().upper()
#     return t or None


# def _fetch_yahoo_quote_endpoint(ticker: str) -> Optional[MarketCapResult]:
#     """
#     Fallback provider: Yahoo quote endpoint
#     https://query1.finance.yahoo.com/v7/finance/quote?symbols=AAP
#     This often works even when yfinance .info is flaky, but can still be blocked.
#     Never raises.
#     """
#     try:
#         url = "https://query1.finance.yahoo.com/v7/finance/quote"
#         params = {"symbols": ticker}

#         # Headers matter on some cloud hosts
#         headers = {
#             "User-Agent": (
#                 "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
#                 "AppleWebKit/537.36 (KHTML, like Gecko) "
#                 "Chrome/122.0.0.0 Safari/537.36"
#             ),
#             "Accept": "application/json,text/plain,*/*",
#             "Accept-Language": "en-US,en;q=0.9",
#             "Connection": "keep-alive",
#         }

#         r = requests.get(url, params=params, headers=headers, timeout=10)
#         if r.status_code != 200:
#             return None

#         data = r.json()
#         result = (data or {}).get("quoteResponse", {}).get("result", [])
#         if not result:
#             return None

#         row = result[0] or {}
#         mc = row.get("marketCap")
#         currency = row.get("currency") or "USD"

#         if mc is None:
#             return None

#         return MarketCapResult(
#             market_cap_mm=float(mc) / 1e6,
#             currency=str(currency),
#             as_of_utc=_now_iso(),
#             source="yahoo_v7_quote",
#             details={
#                 "marketCap_raw": mc,
#                 "shortName": row.get("shortName"),
#                 "exchange": row.get("fullExchangeName") or row.get("exchange"),
#             },
#         )
#     except Exception:
#         return None


# def _fetch_yfinance_fast(ticker: str) -> Optional[MarketCapResult]:
#     """
#     Primary provider: yfinance fast_info (lighter & more reliable than .info).
#     Never raises.
#     """
#     try:
#         import yfinance as yf  # import inside to keep module import stable

#         tkr = yf.Ticker(ticker)

#         fi: Dict[str, Any] = {}
#         try:
#             fi = dict(tkr.fast_info or {})
#         except Exception:
#             fi = {}

#         mc = fi.get("market_cap")
#         currency = fi.get("currency") or "USD"

#         if mc is None:
#             return None

#         return MarketCapResult(
#             market_cap_mm=float(mc) / 1e6,
#             currency=str(currency),
#             as_of_utc=_now_iso(),
#             source="yfinance_fast_info",
#             details={
#                 "marketCap_raw": mc,
#                 "fast_info_keys_sample": sorted(list(fi.keys()))[:40],
#             },
#         )
#     except Exception:
#         return None


# def get_market_cap_mm_yfinance(ticker: str) -> Optional[MarketCapResult]:
#     """
#     Backward-compatible name (your code calls this).
#     BUT internally we do: cache -> yfinance fast_info -> yahoo quote endpoint.
#     Never raises.
#     """
#     t = _normalize_ticker(ticker)
#     if not t:
#         return None

#     cached = _cache_get(t)
#     if cached:
#         return cached

#     # 1) yfinance fast_info
#     res = _fetch_yfinance_fast(t)
#     if res:
#         return _cache_set(t, res)

#     # 2) fallback: direct Yahoo endpoint
#     res = _fetch_yahoo_quote_endpoint(t)
#     if res:
#         return _cache_set(t, res)

#     return None
