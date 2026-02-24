#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
html_renderer.py

Render built_capital_structure.json into HTML formatted exactly like AAP.html.
No extra output.

CLI:
  python html_renderer.py output/built_capital_structure.json --out output/generated_AAP_like.html
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


# ----------------------------
# Styles (match AAP.html)
# ----------------------------

TABLE_STYLE = "border-collapse:collapse; border-left:none; border-right:none;"

HEADER_TH_LEFT = (
    "font-weight:bold; border-top:none; border-bottom:3px solid #000; "
    "border-left:none; border-right:none; padding:6px 8px; text-align:left;"
)
HEADER_TH_RIGHT = (
    "font-weight:bold; border-top:none; border-bottom:3px solid #000; "
    "border-left:none; border-right:none; padding:6px 8px; text-align:right;"
)

ISSUER_TH_LEFT = "border-top:none; border-bottom:1px solid #000; border-left:none; border-right:none; padding:6px 8px; text-align:left;"
ISSUER_TH_RIGHT = "border-top:none; border-bottom:1px solid #000; border-left:none; border-right:none; padding:6px 8px; text-align:right;"

TD_LEFT = "border-top:none; border-bottom:none; border-left:none; border-right:none; padding:6px 8px; text-align:left;"
TD_RIGHT = "border-top:none; border-bottom:none; border-left:none; border-right:none; padding:6px 8px; text-align:right;"

SPACER_LEFT = "border-top:none; border-bottom:none; border-left:none; border-right:none; padding:6px 8px; text-align:left; height:8px; padding:6px 0;"
SPACER_RIGHT = "border-top:none; border-bottom:none; border-left:none; border-right:none; padding:6px 8px; text-align:right; height:8px; padding:6px 0;"

SUBTOTAL_LEFT = "font-weight:bold; border-top:3px solid #000; border-bottom:none; border-left:none; border-right:none; padding:6px 8px; text-align:left;"
SUBTOTAL_RIGHT = "font-weight:bold; border-top:3px solid #000; border-bottom:none; border-left:none; border-right:none; padding:6px 8px; text-align:right;"

NETDEBT_LEFT = "font-weight:bold; border-top:1px solid #000; border-bottom:1px solid #000; background-color:#f5f5f5; border-left:none; border-right:none; padding:6px 8px; text-align:left;"
NETDEBT_RIGHT = "font-weight:bold; border-top:1px solid #000; border-bottom:1px solid #000; background-color:#f5f5f5; border-left:none; border-right:none; padding:6px 8px; text-align:right;"

EV_LEFT = "font-weight:bold; border-top:3px solid #000; border-bottom:3px solid #000; background-color:#f5f5f5; border-left:none; border-right:none; padding:6px 8px; text-align:left;"
EV_RIGHT = "font-weight:bold; border-top:3px solid #000; border-bottom:3px solid #000; background-color:#f5f5f5; border-left:none; border-right:none; padding:6px 8px; text-align:right;"

NOTES_TH = "border-top:none; border-bottom:1px solid #000; border-left:none; border-right:none; padding:6px 8px; text-align:left;"

FINAL_SPACER_LEFT = "border-top:none; border-bottom:1px solid #000; border-left:none; border-right:none; padding:6px 8px; text-align:left; height:8px; padding:6px 0;"
FINAL_SPACER_RIGHT = "border-top:none; border-bottom:1px solid #000; border-left:none; border-right:none; padding:6px 8px; text-align:right; height:8px; padding:6px 0;"


# ----------------------------
# Formatting
# ----------------------------

def esc(x: Any) -> str:
    return "" if x is None else html.escape(str(x))


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


# def fmt_mm(x: Any, *, force_3dp: bool = False, parens_if_negative: bool = False) -> str:
#     if x is None:
#         return ""
#     if not _is_num(x):
#         return str(x)
#
#     v = float(x)
#
#     if parens_if_negative and v < 0:
#         return f"({abs(v):,.3f})"
#
#     if force_3dp:
#         return f"{v:,.3f}"
#
#     # instrument cells in AAP show 3dp frequently; enforce 3dp for numeric
#     return f"{v:,.3f}"

def fmt_mm(x: Any, *, force_3dp: bool = False, parens_if_negative: bool = False) -> str:
    if x is None or x == "":
        return ""
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return str(x)

    v = float(x)

    if parens_if_negative and v < 0:
        return f"({abs(v):,.3f})"

    if force_3dp:
        return f"{v:,.3f}"

    # ✅ instrument values: trim trailing zeros like AAP (299.110 -> 299.11)
    s = f"{v:,.3f}"
    s = s.rstrip("0").rstrip(".")
    return s

# def fmt_coupon(c: Any) -> str:
#     if c is None:
#         return ""
#     t = str(c).strip()
#     if t.lower() == "variable":
#         return "variable"
#     try:
#         v = float(t)
#         s = f"{v:.2f}".rstrip("0").rstrip(".")
#         return s
#     except Exception:
#         return t

#
# def fmt_coupon(c: Any) -> str:
#     if c is None or c == "":
#         return ""
#     t = str(c).strip()
#     if t.lower() == "variable":
#         return "variable"
#     try:
#         v = float(t)
#         return f"{v:.2f}%"
#     except Exception:
#         return t

import re

def fmt_coupon(c: Any, instrument_name: str = "") -> str:
    # If explicitly variable
    if isinstance(c, str) and c.strip().lower() == "variable":
        return "variable"

    # If numeric coupon provided
    if c not in (None, ""):
        try:
            return f"{float(c):.2f}%"
        except Exception:
            return str(c)

    # Otherwise, try to extract from instrument name like "5.90 %"
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", instrument_name or "")
    if m:
        return f"{float(m.group(1)):.2f}"

    return ""

def tr(cells: List[str]) -> str:
    return "<tr>" + "".join(cells) + "</tr>"


def th(text: str, style: str) -> str:
    return f'<th style="{style}">{esc(text)}</th>'


def td(text: str, style: str) -> str:
    return f'<td style="{style}">{esc(text)}</td>'


def spacer(final: bool = False) -> str:
    if final:
        return tr([td("", FINAL_SPACER_LEFT)] + [td("", FINAL_SPACER_RIGHT) for _ in range(7)])
    return tr([td("", SPACER_LEFT)] + [td("", SPACER_RIGHT) for _ in range(7)])


# ----------------------------
# Rows (AAP layout)
# ----------------------------

def header_row() -> str:
    return tr([
        th("Instrument Name", HEADER_TH_LEFT),
        th("Amount Outstanding ($mm)", HEADER_TH_RIGHT),
        th("Amount Available ($mm)", HEADER_TH_RIGHT),
        th("Coupon (%)", HEADER_TH_RIGHT),
        th("Maturity", HEADER_TH_RIGHT),
        th("Priority", HEADER_TH_RIGHT),
        th("Parent Issuer", HEADER_TH_RIGHT),
        th("Issue Date", HEADER_TH_RIGHT),
    ])

def fmt_issue_date(iso_date: Optional[str]) -> str:
    from datetime import datetime

    if not iso_date:
        return ""
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d")
        # AAP format: "March 9, 2023" (no leading zero)
        return dt.strftime("%B %d, %Y").replace(" 0", " ")
    except Exception:
        return str(iso_date)


def issuer_row(issuer: str) -> str:
    return tr([th(issuer, ISSUER_TH_LEFT)] + [th("", ISSUER_TH_RIGHT) for _ in range(7)])

#
# def instrument_row(inst: Dict[str, Any]) -> str:
#     return tr([
#         td(inst.get("instrument_name", ""), TD_LEFT),
#         td(fmt_mm(inst.get("amount_outstanding_mm")), TD_RIGHT),
#         # td(fmt_mm(inst.get("amount_outstanding_mm"), force_3dp=False), TD_RIGHT),
#         td(fmt_mm(inst.get("amount_available_mm")), TD_RIGHT),
#         name = inst.get("instrument_name", "") or ""
#         td(fmt_coupon(inst.get("coupon_percent"), name), TD_RIGHT),
#         # td(fmt_coupon(inst.get("coupon_percent")), TD_RIGHT),
#         td(inst.get("maturity_year", "") or "", TD_RIGHT),
#         td(inst.get("priority", "") or "", TD_RIGHT),
#         td(inst.get("parent_issuer", "") or "", TD_RIGHT),
#         td(inst.get("issue_date", "") or "", TD_RIGHT),
#         # td(inst.get("issue_date", "") or "", TD_RIGHT),
#     ])


def instrument_row(inst: Dict[str, Any]) -> str:
    name = inst.get("instrument_name", "") or ""
    return tr([
        td(name, TD_LEFT),
        td(fmt_mm(inst.get("amount_outstanding_mm")), TD_RIGHT),
        td(fmt_mm(inst.get("amount_available_mm")), TD_RIGHT),
        td(fmt_coupon(inst.get("coupon_percent"), name), TD_RIGHT),
        td(inst.get("maturity_year", "") or "", TD_RIGHT),
        td(inst.get("priority", "") or "", TD_RIGHT),
        td(inst.get("parent_issuer", "") or "", TD_RIGHT),
        td(inst.get("issue_date", "") or "", TD_RIGHT),
    ])


# def subtotal_row(title: str, total_mm: float) -> str:
def subtotal_row(title: str, total_debt_mm: float) -> str:
    return tr([
        td(title, SUBTOTAL_LEFT),
        # td(fmt_mm(total_mm, force_3dp=True), SUBTOTAL_RIGHT),
        td(fmt_mm(total_debt_mm, force_3dp=True), SUBTOTAL_RIGHT),
        td("0", SUBTOTAL_RIGHT),
        td("", SUBTOTAL_RIGHT),
        td("", SUBTOTAL_RIGHT),
        td("", SUBTOTAL_RIGHT),
        td("", SUBTOTAL_RIGHT),
        td("", SUBTOTAL_RIGHT),
    ])


def cash_row(cash_mm: float) -> str:
    return tr([
        td("-  Cash and cash equivalents", TD_LEFT),
        td(fmt_mm(-abs(cash_mm), force_3dp=True, parens_if_negative=True), TD_RIGHT),
        td("", TD_RIGHT), td("", TD_RIGHT), td("", TD_RIGHT), td("", TD_RIGHT), td("", TD_RIGHT), td("", TD_RIGHT),
    ])


def net_debt_row(net_debt_mm: float) -> str:
    return tr([
        td("Net Debt", NETDEBT_LEFT),
        td(fmt_mm(net_debt_mm, force_3dp=True), NETDEBT_RIGHT),
        td("", NETDEBT_RIGHT), td("", NETDEBT_RIGHT), td("", NETDEBT_RIGHT),
        td("", NETDEBT_RIGHT), td("", NETDEBT_RIGHT), td("", NETDEBT_RIGHT),
    ])


def plus_line(label: str, value_mm: float) -> str:
    # Market cap is shown without decimals in AAP if it's an integer
    if abs(value_mm - round(value_mm)) < 1e-9:
        vtxt = f"{int(round(value_mm)):,}"
    else:
        vtxt = fmt_mm(value_mm)

    return tr([
        td(f"+  {label}", TD_LEFT),
        td(vtxt, TD_RIGHT),
        td("", TD_RIGHT), td("", TD_RIGHT), td("", TD_RIGHT), td("", TD_RIGHT), td("", TD_RIGHT), td("", TD_RIGHT),
    ])


def enterprise_value_row(ev_mm: float) -> str:
    return tr([
        td("Enterprise Value", EV_LEFT),
        td(fmt_mm(ev_mm, force_3dp=True), EV_RIGHT),
        td("", EV_RIGHT), td("", EV_RIGHT), td("", EV_RIGHT), td("", EV_RIGHT), td("", EV_RIGHT), td("", EV_RIGHT),
    ])


def notes_rows(notes: List[str]) -> List[str]:
    if not notes:
        return []
    rows: List[str] = []
    rows.append(tr([th("Notes:", NOTES_TH)] + [td("", TD_RIGHT) for _ in range(7)]))
    for i, n in enumerate(notes, start=1):
        rows.append(tr([td(f"{i}. {n}", TD_LEFT)] + [td("", TD_RIGHT) for _ in range(7)]))
    rows.append(spacer(final=True))
    return rows


# ----------------------------
# Render
# ----------------------------

def render(doc: Dict[str, Any]) -> str:
    rows: List[str] = [header_row(), spacer()]

    for g in doc.get("issuer_groups", []) or []:
        rows.append(issuer_row(g.get("issuer", "")))
        for pg in g.get("priority_groups", []) or []:
            for inst in pg.get("instruments", []) or []:
                rows.append(instrument_row(inst))
            subtotal = (pg.get("subtotal") or {}).get("subtotal_outstanding_mm") or 0.0
            rows.append(subtotal_row(f"Total {pg.get('priority','')}", float(subtotal)))
            rows.append(spacer())

    total_debt = float(doc.get("total_debt_mm") or 0.0)
    cash = float(doc.get("cash_mm") or 0.0)
    net_debt = float(doc.get("net_debt_mm") or 0.0)
    nci = float(doc.get("noncontrolling_interests_mm") or 0.0)
    mkt = float(doc.get("market_cap_mm") or 0.0)
    ev = float(doc.get("enterprise_value_mm") or 0.0)

    rows.append(subtotal_row("Total Debt", total_debt))
    rows.append(spacer())
    rows.append(cash_row(cash))
    rows.append(net_debt_row(net_debt))
    rows.append(plus_line("Noncontrolling interests", nci))
    rows.append(plus_line("Market capitalization", mkt))
    rows.append(enterprise_value_row(ev))
    rows.append(spacer())

    rows.extend(notes_rows(doc.get("notes", []) or []))

    return f'<table style="{TABLE_STYLE}">' + "".join(rows) + "</table>"



def main() -> None:
    ap = argparse.ArgumentParser(description="Render built_capital_structure.json to AAP.html format.")
    ap.add_argument("built_json", help="Path to built_capital_structure.json")
    ap.add_argument("--out", default=None, help="Output HTML path (optional)")
    args = ap.parse_args()

    doc = json.loads(Path(args.built_json).read_text(encoding="utf-8"))
    out_html = render(doc)

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out_html, encoding="utf-8")
    else:
        print(out_html)


if __name__ == "__main__":
    main()