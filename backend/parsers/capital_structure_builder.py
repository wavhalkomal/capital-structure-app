#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
capital_structure_builder.py

Build the final built_capital_structure.json used by html_renderer.py.

Key fixes:
- NO manual --period-end required
- Derives period end from balance_sheet + metadata(annual_period)  :contentReference[oaicite:1]{index=1}
- Uses fixed lease parser output (populated $mm values)
- Normalizes issuer display name to match AAP.html ("Advance Auto Parts, Inc.")
- Produces notes exactly like AAP.html

CLI:
  python capital_structure_builder.py \
    --balance input/balance_sheet.json \
    --debt input/debt_note.html \
    --lease input/lease_note.html \
    --metadata input/metadata.json \
    --market-cap-mm 2592 \
    --out output/built_capital_structure.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
# from debt_note_html_parser import extract_debt_instruments_from_debt_note

# Import your existing balance sheet + debt parsers from project.
# NOTE: lease parser is the fixed file you’re adding.
from balance_sheet_json_parser import extract_required_balance_sheet_data
from lease_note_html_parser import parse_lease_note_html
from debt_note_html_parser import extract_debt_instruments_from_debt_note
# ----------------------------
# Helpers
# ----------------------------

_MONTHS = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
]

def iso_to_long_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{_MONTHS[int(m)-1]} {int(d)}, {int(y)}"


def prettify_company_name(name: str) -> str:
    """
    Convert "ADVANCE AUTO PARTS INC" -> "Advance Auto Parts, Inc."
    Only does this if name is all-uppercase and ends with INC / CORP / LLC, etc.
    """
    if not name:
        return name
    n = name.strip()

    if n.upper() != n:
        return n

    parts = n.split()
    if not parts:
        return n

    suffix = parts[-1]
    base = parts[:-1]

    base_title = " ".join(w.capitalize() for w in base) if base else ""
    if suffix in {"INC", "CORP", "CO", "LLC", "LTD"}:
        suffix_map = {"INC": "Inc.", "CORP": "Corp.", "CO": "Co.", "LLC": "LLC", "LTD": "Ltd."}
        if base_title:
            return f"{base_title}, {suffix_map[suffix]}"
        return suffix_map[suffix]

    return " ".join(w.capitalize() for w in parts)


def round3(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(float(x), 3)


def sum_amounts(instruments: List[Dict[str, Any]]) -> float:
    s = 0.0
    for ins in instruments:
        v = ins.get("amount_outstanding_mm")
        if v is None:
            continue
        s += float(v)
    return round(s, 3)


def group_by_priority(instruments: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for ins in instruments:
        p = ins.get("priority") or "Unsecured"
        out.setdefault(p, []).append(ins)
    return out


def normalize_instrument_amounts(instruments: List[Dict[str, Any]]) -> None:
    for ins in instruments:
        ins["amount_outstanding_mm"] = round3(ins.get("amount_outstanding_mm"))
        ins["amount_available_mm"] = round3(ins.get("amount_available_mm"))


def unsecured_sort_key(inst):
    name = inst.get("instrument_name", "")

    # 1️⃣ Put Revolver first
    if "Revolving Credit Facility" in name:
        return (0, 0)

    # 2️⃣ Then sort remaining by maturity ascending
    maturity = inst.get("maturity_year")
    if isinstance(maturity, int):
        return (1, maturity)

    return (1, 9999)

# ----------------------------
# Builder
# ----------------------------

def build_capital_structure(
    balance_path: str,
    debt_path: str,
    lease_path: str,
    metadata_path: str,
    market_cap_mm: float,
) -> Dict[str, Any]:
    # Balance sheet extract (cash + NCI + selected period ISO end date)
    bs = extract_required_balance_sheet_data(balance_path, metadata_path)
    iso_end = bs.get("selected_period_end_date")
    if not iso_end:
        raise ValueError("Could not derive selected_period_end_date from balance sheet.")

    period_end_text = iso_to_long_date(iso_end)

    company_name_raw = bs.get("company_name") or "Company"
    company_name_display = prettify_company_name(str(company_name_raw))

    # Debt parse (your debt parser already expects period-end text)
    debt_parsed = extract_debt_instruments_from_debt_note(
        debt_path,
        period_end_date_text=period_end_text,
        parent_company_name=company_name_display,
    )
    debt_instruments = debt_parsed.get("instruments") or []
    normalize_instrument_amounts(debt_instruments)

    # Lease parse (fixed)
    lease_parsed = parse_lease_note_html(lease_path, period_end_text)
    lease_instruments = lease_parsed.get("instruments") or []
    normalize_instrument_amounts(lease_instruments)

    # Combine
    all_instruments = lease_instruments + debt_instruments

    # Single issuer group (AAP style)
    issuer = company_name_display

    # Force expected priorities (AAP style)
    for ins in lease_instruments:
        ins["priority"] = "Senior Secured"
    # debt parser should already label unsecured; keep as-is.

    pri_groups_map = group_by_priority(all_instruments)

    priority_groups: List[Dict[str, Any]] = []
    # for priority in ["Senior Secured", "Unsecured", "Subordinated"]:
    #     if priority not in pri_groups_map:
    #         continue
    #     insts = pri_groups_map[priority]
    #
    #     # Keep original order as extracted to match AAP.html row order
    #     subtotal = round(sum_amounts(insts), 3)

    for priority in ["Senior Secured", "Unsecured", "Subordinated"]:
        if priority not in pri_groups_map:
            continue

        insts = pri_groups_map[priority]

        # ✅ SORT ONLY UNSECURED
        if priority == "Unsecured":
            insts = sorted(insts, key=unsecured_sort_key)

        subtotal = round(sum_amounts(insts), 3)


        priority_groups.append(
            {
                "priority": priority,
                "instruments": insts,
                "subtotal": {"subtotal_outstanding_mm": subtotal},
            }
        )

    issuer_groups = [
        {"issuer": issuer, "priority_groups": priority_groups}
    ]

    total_debt_mm = round(sum_amounts(all_instruments), 3)

    cash_mm = round3(bs.get("cash_and_cash_equivalents_mm")) or 0.0
    nci_mm = round3(bs.get("noncontrolling_interests_mm")) or 0.0

    net_debt_mm = round(total_debt_mm - cash_mm, 3)
    enterprise_value_mm = round(net_debt_mm + nci_mm + float(market_cap_mm), 3)

    # Notes EXACTLY like AAP.html
    notes = [
        "Market Cap and most recent FY EBITDA come from Seeking Alpha",
        "All debt amounts come from the most recent 10-K filing",
        "Following amounts are hardcoded: price, yield",
    ]

    return {
        "company_name": str(company_name_raw),
        "company_name_display": issuer,
        "ticker": bs.get("ticker"),
        "cik": bs.get("cik"),
        "annual_period": bs.get("annual_period"),
        "period_end_date_text": period_end_text,
        "selected_period_end_date": iso_end,

        "issuer_groups": issuer_groups,

        "total_debt_mm": total_debt_mm,
        "cash_mm": cash_mm,
        "net_debt_mm": net_debt_mm,
        "noncontrolling_interests_mm": nci_mm,
        "market_cap_mm": round3(market_cap_mm) if market_cap_mm is not None else 0.0,
        "enterprise_value_mm": enterprise_value_mm,

        "notes": notes,

        # provenance (optional, helps debug but does not affect rendering)
        "provenance": {
            "balance_sheet": bs.get("provenance"),
            "debt_notes": debt_parsed.get("notes"),
            "lease_notes": lease_parsed.get("notes"),
        },
    }


# ----------------------------
# CLI
# ----------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Build capital structure JSON for renderer.")
    ap.add_argument("--balance", required=True, help="Path to balance_sheet.json")
    ap.add_argument("--debt", required=True, help="Path to debt_note.html")
    ap.add_argument("--lease", required=True, help="Path to lease_note.html")
    ap.add_argument("--metadata", required=True, help="Path to metadata.json")
    ap.add_argument("--market-cap-mm", required=True, type=float, help="Market cap in $mm (e.g., 2592)")
    ap.add_argument("--out", required=True, help="Output path for built_capital_structure.json")
    args = ap.parse_args()

    built = build_capital_structure(
        balance_path=args.balance,
        debt_path=args.debt,
        lease_path=args.lease,
        metadata_path=args.metadata,
        market_cap_mm=args.market_cap_mm,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(built, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()