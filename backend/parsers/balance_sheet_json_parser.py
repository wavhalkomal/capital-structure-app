#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
balance_sheet_json_parser.py

Extract ONLY the balance sheet inputs needed for the Capital Structure table:
  - Cash and cash equivalents ($mm)
  - Noncontrolling interests ($mm)

Also returns:
  - company_name, ticker, cik (best-effort from JSON)
  - annual_period from metadata.json
  - selected_period_key and selected_period_end_date (ISO)
  - provenance for cash/NCI rows (concept/label/raw value object)

Key corrections:
  ✅ Robust period selection for the metadata annual_period (prefers FY match, Q4, instant, latest end_date)
  ✅ Converts values to $mm consistently using numeric_value if present, else display_value + scale
  ✅ Preserves precision to 3 decimals (so you match values like 1,869.417)
  ✅ Deterministic, no prints/warnings unless CLI output requested

Usage:
  python balance_sheet_json_parser.py input/balance_sheet.json input/metadata.json
  python balance_sheet_json_parser.py input/balance_sheet.json input/metadata.json --out output/balance_sheet_parsed.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Helpers
# -----------------------------

def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, str):
            t = x.strip().replace(",", "")
            if t in {"", "-", "—"}:
                return None
            return float(t)
        return float(x)
    except Exception:
        return None


def _parse_iso_date(d: Optional[str]) -> Optional[date]:
    if not d:
        return None
    try:
        y, m, dd = d.split("-")
        return date(int(y), int(m), int(dd))
    except Exception:
        return None


def _to_millions(value_obj: Any) -> Optional[float]:
    """
    Convert a balance-sheet value object into $mm.

    Common shape:
      {
        "numeric_value": 1869417000,
        "display_value": "1,869.417",
        "scale": 6
      }

    Rules:
      - If numeric_value exists => absolute dollars => / 1e6
      - Else use display_value * 10^(scale-6)
    """
    if not isinstance(value_obj, dict):
        return None

    nv = _safe_float(value_obj.get("numeric_value"))
    if nv is not None:
        return nv / 1_000_000.0

    dv = _safe_float(value_obj.get("display_value"))
    if dv is None:
        return None

    scale_raw = value_obj.get("scale")
    try:
        scale = int(scale_raw) if scale_raw is not None else 6
    except Exception:
        scale = 6

    # display_value is in 10^scale dollars. Convert to $mm (10^6 dollars).
    return dv * (10 ** (scale - 6))


def _norm_label(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _iter_rows(balance_sheet: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = balance_sheet.get("rows") or []
    return [r for r in rows if isinstance(r, dict)]


# -----------------------------
# Period selection
# -----------------------------

@dataclass(frozen=True)
class PeriodMeta:
    key: str
    fiscal_year: Optional[int]
    fiscal_quarter: Optional[int]
    period_type: Optional[str]
    end_date: Optional[str]


def _load_periods(balance_sheet: Dict[str, Any]) -> List[PeriodMeta]:
    cols = balance_sheet.get("columns") or []
    out: List[PeriodMeta] = []
    for c in cols:
        if not isinstance(c, dict):
            continue
        key = str(c.get("key") or "")
        if not key:
            continue
        fy = c.get("fiscal_year")
        fq = c.get("fiscal_quarter")
        out.append(
            PeriodMeta(
                key=key,
                fiscal_year=int(fy) if fy is not None else None,
                fiscal_quarter=int(fq) if fq is not None else None,
                period_type=(c.get("period_type") or None),
                end_date=(c.get("end_date") or None),
            )
        )
    return out


def select_period_key_for_annual_period(balance_sheet: Dict[str, Any], annual_period: int) -> Tuple[str, Optional[str]]:
    """
    Choose the best period key for the annual_period from metadata.

    Preference order:
      1) fiscal_year == annual_period
      2) fiscal_quarter == 4
      3) period_type == "instant"
      4) latest end_date
    """
    periods = _load_periods(balance_sheet)

    candidates = [p for p in periods if p.fiscal_year == annual_period]
    if not candidates:
        # fallback: first columns entry
        if periods:
            return periods[0].key, periods[0].end_date
        # fallback: first row.values key
        for r in _iter_rows(balance_sheet):
            vals = r.get("values")
            if isinstance(vals, dict) and vals:
                k = next(iter(vals.keys()))
                return str(k), None
        return "UNKNOWN", None

    def score(p: PeriodMeta) -> Tuple[int, int, date]:
        q4 = 1 if p.fiscal_quarter == 4 else 0
        inst = 1 if (p.period_type or "").lower() == "instant" else 0
        ed = _parse_iso_date(p.end_date) or date(1900, 1, 1)
        return (q4, inst, ed)

    best = sorted(candidates, key=score, reverse=True)[0]
    return best.key, best.end_date


# -----------------------------
# Row finding
# -----------------------------
def find_row(balance_sheet: dict, concepts: list[str], label_any_keywords: list[str] | None = None) -> dict | None:
    """
    Finds the first matching balance sheet row by:
      1) concept in `concepts` (priority order)
      2) OR label containing any keywords (optional)

    Expects balance_sheet rows in balance_sheet["rows"] OR balance_sheet["line_items"].
    Adjust the row list key if your JSON uses a different key.
    """
    rows = balance_sheet.get("rows") or balance_sheet.get("line_items") or []
    if not isinstance(rows, list):
        return None

    # Normalize keywords
    kws = [k.lower() for k in (label_any_keywords or [])]

    # 1) concept match in priority order
    for concept in concepts:
        for r in rows:
            c = (r.get("concept") or r.get("tag") or "").strip()
            if c == concept:
                return r

    # 2) label keyword match
    if kws:
        for r in rows:
            label = (r.get("label") or r.get("name") or r.get("title") or "").lower()
            if any(k in label for k in kws):
                return r

    return None


def find_row_by_concept_or_label(
    balance_sheet: Dict[str, Any],
    *,
    concept_candidates: List[str],
    label_keywords_any: List[str],
) -> Optional[Dict[str, Any]]:
    concept_set = {c for c in concept_candidates if c}
    keywords = [_norm_label(k) for k in label_keywords_any if k and k.strip()]

    # 1) concept match
    if concept_set:
        for r in _iter_rows(balance_sheet):
            concept = str(r.get("concept") or "")
            if concept in concept_set:
                return r

    # 2) label keyword match
    if keywords:
        for r in _iter_rows(balance_sheet):
            label = _norm_label(str(r.get("label") or ""))
            if any(k in label for k in keywords):
                return r

    return None


def extract_row_value_mm(row: Dict[str, Any], period_key: str) -> Optional[float]:
    vals = row.get("values")
    if not isinstance(vals, dict):
        return None
    value_obj = vals.get(period_key)
    mm = _to_millions(value_obj)
    return mm


def build_provenance(row: Optional[Dict[str, Any]], period_key: str) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    vals = row.get("values") if isinstance(row.get("values"), dict) else {}
    return {
        "concept": row.get("concept"),
        "label": row.get("label"),
        "period_key": period_key,
        "raw_value_obj": vals.get(period_key),
    }


# -----------------------------
# Output schema
# -----------------------------

@dataclass
class BalanceSheetExtract:
    annual_period: int
    selected_period_key: str
    selected_period_end_date: Optional[str]

    company_name: str
    ticker: Optional[str]
    cik: Optional[str]

    cash_and_cash_equivalents_mm: Optional[float]
    noncontrolling_interests_mm: float

    provenance: Dict[str, Any]


# -----------------------------
# Main extraction
# -----------------------------

def extract_required_balance_sheet_data(balance_sheet_json_path: str | Path, metadata_json_path: str | Path) -> Dict[str, Any]:
    bs = json.loads(Path(balance_sheet_json_path).read_text(encoding="utf-8"))
    md = json.loads(Path(metadata_json_path).read_text(encoding="utf-8"))

    annual_period_raw = md.get("annual_period")
    if annual_period_raw is None:
        raise ValueError("metadata.json missing required field: annual_period")
    annual_period = int(annual_period_raw)

    period_key, end_date = select_period_key_for_annual_period(bs, annual_period)

    company_name = (
        bs.get("company_name")
        or bs.get("entity_name")
        or (md.get("company_name") if isinstance(md, dict) else None)
        or "Company"
    )
    ticker = bs.get("ticker") or md.get("ticker")
    cik = bs.get("cik") or md.get("cik")

    # Cash row
    # cash_row = find_row_by_concept_or_label(
    #     bs,
    #     concept_candidates=[
    #         "us-gaap:CashAndCashEquivalentsAtCarryingValue",
    #         "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    #         "us-gaap:Cash",
    #     ],
    #     label_keywords_any=[
    #         "cash and cash equivalents",
    #         "cash & cash equivalents",
    #         "cash",
    #     ],
    # )

    # --- CASH (required for Net Debt) ---
    cash_row = find_row(
        balance_sheet=bs,
        concepts=[
            # ✅ prefer combined cash FIRST (this is what AAP.html uses)
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "CashAndCashEquivalentsAtCarryingValue",
            "CashAndCashEquivalents",
        ],
        label_any_keywords=[
            "cash and cash equivalents",
            "restricted cash",
            "cash, cash equivalents and restricted cash",
            "cash cash equivalents restricted cash and restricted cash equivalents",
        ],
    )

    cash_mm = extract_row_value_mm(cash_row, period_key) if cash_row else None

    # Noncontrolling interests row (default 0 if missing)
    nci_row = find_row_by_concept_or_label(
        bs,
        concept_candidates=[
            "us-gaap:MinorityInterest",
            "us-gaap:NoncontrollingInterest",
            "us-gaap:NoncontrollingInterests",
            "us-gaap:NoncontrollingInterestEquity",
        ],
        label_keywords_any=[
            "noncontrolling interests",
            "non controlling interests",
            "minority interest",
        ],
    )
    nci_mm = extract_row_value_mm(nci_row, period_key) if nci_row else None

    # Precision handling: keep 3 decimals
    cash_mm_3 = round(cash_mm, 3) if cash_mm is not None else None
    nci_mm_3 = round(nci_mm, 3) if nci_mm is not None else 0.0

    out = BalanceSheetExtract(
        annual_period=annual_period,
        selected_period_key=period_key,
        selected_period_end_date=end_date,
        company_name=str(company_name),
        ticker=str(ticker) if ticker is not None else None,
        cik=str(cik) if cik is not None else None,
        cash_and_cash_equivalents_mm=cash_mm_3,
        noncontrolling_interests_mm=nci_mm_3,
        provenance={
            "cash": build_provenance(cash_row, period_key),
            "noncontrolling_interests": build_provenance(nci_row, period_key),
        },
    )

    return asdict(out)


# -----------------------------
# CLI
# -----------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract cash + noncontrolling interests from balance_sheet.json")
    parser.add_argument("balance_sheet_json", help="Path to balance_sheet.json")
    parser.add_argument("metadata_json", help="Path to metadata.json")
    parser.add_argument("--out", default=None, help="Optional output JSON path")
    args = parser.parse_args()

    result = extract_required_balance_sheet_data(args.balance_sheet_json, args.metadata_json)

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, indent=2), encoding="utf-8")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()