# backend/app/market_cap.py
from __future__ import annotations

import os
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import requests

# yfinance is optional; we only import if fallback is enabled.
# (Railway/Yahoo often blocks, so default is disabled.)
try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None  # type: ignore


@dataclass
class MarketCapResult:
    market_cap_mm: float
    source: str
    currency: str
    as_of_utc: str
    details: str


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return default


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _fetch_fmp_stable_profile(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Calls:
      https://financialmodelingprep.com/stable/profile?symbol=AAP&apikey=...
    Returns first object dict or None.
    """
    api_key = (os.getenv("FMP_API_KEY") or "").strip()
    if not api_key:
        return None

    symbol = (ticker or "").strip().upper()
    if not symbol:
        return None

    url = "https://financialmodelingprep.com/stable/profile"
    params = {"symbol": symbol, "apikey": api_key}

    try:
        r = requests.get(url, params=params, timeout=12)
        if r.status_code != 200:
            # Don't raise -> don't crash the app
            return None

        data = r.json()
        if not isinstance(data, list) or not data:
            return None

        obj = data[0]
        if not isinstance(obj, dict):
            return None

        return obj
    except Exception:
        return None


def get_market_cap_mm_fmp(ticker: str) -> Optional[MarketCapResult]:
    """
    FMP Stable (recommended on cloud):
      - Uses stable/profile and reads marketCap (or mktCap if present)
      - Returns MarketCapResult in MILLIONS, or None
    """
    obj = _fetch_fmp_stable_profile(ticker)
    if not obj:
        return None

    # FMP stable typically uses "marketCap"
    raw = obj.get("marketCap", None)
    if raw is None:
        raw = obj.get("mktCap", None)

    mc = _safe_float(raw)
    if mc is None or mc <= 0:
        return None

    currency = str(obj.get("currency") or "USD")

    return MarketCapResult(
        market_cap_mm=mc / 1_000_000.0,
        source="fmp_stable_profile",
        currency=currency,
        as_of_utc=_now_utc_iso(),
        details="stable/profile: marketCap",
    )


def _get_market_cap_mm_yfinance_internal(ticker: str) -> Optional[MarketCapResult]:
    """
    Yahoo/yfinance fallback (NOT reliable on Railway).
    Always wrapped so it never crashes the API.
    """
    if yf is None:
        return None

    symbol = (ticker or "").strip().upper()
    if not symbol:
        return None

    try:
        t = yf.Ticker(symbol)
        info = t.info or {}

        mc = _safe_float(info.get("marketCap"))
        if mc is None or mc <= 0:
            return None

        currency = str(info.get("currency") or "USD")

        return MarketCapResult(
            market_cap_mm=mc / 1_000_000.0,
            source="yfinance",
            currency=currency,
            as_of_utc=_now_utc_iso(),
            details="ticker.info.marketCap",
        )
    except (json.JSONDecodeError, ValueError, KeyError):
        return None
    except Exception:
        return None


def get_market_cap_mm_yfinance(ticker: str) -> Optional[MarketCapResult]:
    """
    IMPORTANT: We keep this function name because your main.py already calls it.

    Behavior:
      1) Try FMP Stable FIRST (recommended, reliable on Railway)
      2) Optionally fall back to yfinance if enabled via env var:
           ALLOW_YFINANCE_FALLBACK=true
         Default: disabled (prevents 429 / blocks / 500s)

    Returns:
      MarketCapResult or None (never raises)
    """
    # 1) FMP first
    res = get_market_cap_mm_fmp(ticker)
    if res is not None:
        return res

    # 2) Optional yfinance fallback
    if _env_bool("ALLOW_YFINANCE_FALLBACK", default=False):
        return _get_market_cap_mm_yfinance_internal(ticker)

    return None
