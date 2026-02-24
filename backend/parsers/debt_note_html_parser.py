#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
debt_note_html_parser_fixed.py

Generic Debt Note HTML parser to extract debt instruments (bonds/notes, credit facilities, term loans)
from XBRL-rendered HTML debt footnotes.

Design goals
- Works across many filing styles:
  * schedule tables listing instruments and carrying amounts
  * narrative sections that contain the *issue date* ("were issued <date>")
  * credit agreement / revolving credit facility descriptions ("On <date>, entered into ... credit agreement...")
- Keeps table-based extraction as the primary source of instrument rows (because it's the most consistent).
- Adds a second pass that:
  * back-fills issue dates for table rows from narrative text, keyed by the "due <Month Day, Year>" maturity date
  * adds missing credit facility instruments that are mentioned only in narrative (common!)

Output JSON schema (compatible with your pipeline):
{
  "parent_company_name": str|None,
  "period_end_date_text": str|None,
  "instruments": [
      {
        "instrument_name": str,
        "amount_outstanding_mm": float|None,
        "amount_available_mm": float|None,
        "coupon_percent": float|str|None,   # allow "variable"
        "maturity_year": int|None,
        "priority": str|None,
        "parent_issuer": str|None,
        "issue_date": "YYYY-MM-DD"|None,
        "instrument_type": str|None,        # "bond", "credit_facility", "term_loan", ...
        "lien_level": str|None,
        "provenance": {...}
      }, ...
  ],
  "notes": [str, ...]
}

CLI:
  python debt_note_html_parser_fixed.py --html input/debt_note.html --period-end "December 28, 2024" --out debt_parsed.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup


MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _to_mm_if_thousands(v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    # Heuristic consistent with your lease parser:
    # Big integers like 299,110 are thousands → 299.110 ($mm)
    return (v / 1000.0) if abs(v) >= 10_000 else v


def _clean_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _lower(s: str) -> str:
    return (s or "").lower()


def _parse_us_date(text: str) -> Optional[_dt.date]:
    """
    Parse dates like "March 9, 2026" (month name) or "03/09/2026" (mm/dd/yyyy).
    """
    t = _clean_space(text)
    if not t:
        return None

    # mm/dd/yyyy
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
    if m:
        mm, dd, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return _dt.date(yy, mm, dd)
        except ValueError:
            return None

    # Month d, yyyy
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", t)
    if m:
        mon = MONTHS.get(m.group(1).lower())
        if not mon:
            return None
        dd, yy = int(m.group(2)), int(m.group(3))
        try:
            return _dt.date(yy, mon, dd)
        except ValueError:
            return None

    return None


def _date_to_iso(d: Optional[_dt.date]) -> Optional[str]:
    return d.isoformat() if d else None


def _extract_due_date_text_from_name(name: str) -> Optional[str]:
    """
    Extracts "March 9, 2026" from "... due March 9, 2026" (case-insensitive).
    """
    m = re.search(r"\bdue\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})\b", name, flags=re.IGNORECASE)
    if not m:
        return None
    return _clean_space(m.group(1))


def _extract_maturity_year_from_name(name: str) -> Optional[int]:
    due = _extract_due_date_text_from_name(name)
    if not due:
        return None
    d = _parse_us_date(due)
    return d.year if d else None


def _safe_float_from_text(t: str) -> Optional[float]:
    """
    Robust numeric extraction for table cells, returning *millions* if the table is in millions.
    We do NOT scale here; your pipeline already expects MM numbers. This function just parses.
    """
    s = _clean_space(t)
    if not s or s in {"—", "-", "–", "—-", "— —"}:
        return None
    # remove currency / commas / parentheses
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace("$", "").replace(",", "")
    # allow em dash
    if s in {"—", "-", "–"}:
        return None
    # sometimes "0.0" etc
    try:
        v = float(s)
        return -v if neg else v
    except Exception:
        # last resort: find a number substring
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        if not m:
            return None
        v = float(m.group(0))
        return -v if neg else v


def _classify_instrument_type(name_text: str) -> str:
    t = _lower(name_text)
    if any(k in t for k in ["revolver", "revolving", "credit facility", "rcf", "line of credit", "credit agreement"]):
        return "credit_facility"
    if "term loan" in t:
        return "term_loan"
    if any(k in t for k in ["note", "notes", "debenture", "senior notes"]):
        return "bond"
    return "other_debt"


def _extract_parent_issuer(text: str) -> Optional[str]:
    # Best-effort: "issued by X" or "the Company issued"
    # In most filings this isn't clean; keep None by default.
    m = re.search(r"\bissued by\s+([A-Z][A-Za-z0-9&\-\., ]+)\b", text)
    if m:
        return _clean_space(m.group(1))
    return None


def _soup_text(soup: BeautifulSoup) -> str:
    # Use a separator to avoid accidental concatenation of words
    return _clean_space(soup.get_text(" "))


def _build_issue_date_map_from_narrative(full_text: str) -> Dict[str, str]:
    """
    Build a mapping:
      due_date_text ("March 9, 2026") -> issue_date_iso ("2023-03-09")
    from patterns like:
      "... % senior unsecured notes due March 9, 2026 ... were issued March 9, 2023 ..."
    This is the *most reliable generic* pattern across issuers.
    """
    t = full_text

    # capture due date + issued date
    # allow various punctuation / parentheses between them
    pat = re.compile(
        r"senior\s+unsecured\s+notes\s+due\s+([A-Za-z]+\s+\d{1,2},\s*\d{4}).{0,250}?were\s+issued\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})",
        flags=re.IGNORECASE | re.DOTALL,
    )

    out: Dict[str, str] = {}
    for m in pat.finditer(t):
        due_txt = _clean_space(m.group(1))
        iss_txt = _clean_space(m.group(2))
        due_d = _parse_us_date(due_txt)
        iss_d = _parse_us_date(iss_txt)
        if not due_d or not iss_d:
            continue
        out[due_txt] = iss_d.isoformat()
    return out


def _extract_credit_facilities_from_narrative(full_text: str) -> List[Dict[str, Any]]:
    """
    Extract credit facility / credit agreement instruments mentioned only in narrative, e.g.:
      "On November 9, 2021, the Company entered into a credit agreement that provided a ... unsecured revolving credit facility (the “2021 Credit Agreement”) ..."
    Also try to find the latest maturity date mentioned for that agreement, e.g.:
      "... extended the maturity date ... to November 9, 2027."
    """
    t = full_text

    # 1) Find "On <date> ... (unsecured|secured) revolving credit facility ... (the “<NAME> Credit Agreement”)"
    # Capture agreement label so we can later find maturity changes.
    start_pat = re.compile(
        r"\bOn\s+([A-Za-z]+\s+\d{1,2},\s*\d{4}),\s+.*?\b(?:(secured|unsecured)\s+)?revolving\s+credit\s+facility\b.*?\(\s*the\s+[“\"']([^”\"']*?Credit Agreement)[”\"']\s*\)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 2) Maturity date mentions, keyed by agreement name
    maturity_pat = re.compile(
        r"\bmaturity\s+date\b.*?(?:the\s+)?([A-Za-z0-9][A-Za-z0-9\s\-]{0,60}?Credit Agreement)\b.*?\bto\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})",
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Collect maturity updates per agreement
    maturities: Dict[str, List[_dt.date]] = {}
    for m in maturity_pat.finditer(t):
        agreement = _clean_space(m.group(1))
        agreement = re.sub(r"^(?:of\s+)?(?:the\s+)?", "", agreement, flags=re.IGNORECASE)
        d = _parse_us_date(_clean_space(m.group(2)))
        if not agreement or not d:
            continue
        maturities.setdefault(agreement, []).append(d)

    out: List[Dict[str, Any]] = []
    for m in start_pat.finditer(t):
        issue_txt = _clean_space(m.group(1))
        sec_unsec = _clean_space(m.group(2)) if m.group(2) else "unsecured"
        agreement = _clean_space(m.group(3))
        agreement = re.sub(r"^(?:of\s+)?(?:the\s+)?", "", agreement, flags=re.IGNORECASE)

        issue_d = _parse_us_date(issue_txt)
        if not issue_d or not agreement:
            continue

        # Choose latest maturity date we can find for that agreement; else None
        mats = maturities.get(agreement, [])
        maturity_year: Optional[int] = max(mats).year if mats else None

        # Normalize name to match expected style in outputs
        name = f"{sec_unsec.title()} Revolving Credit Facility ({agreement})"

        out.append(
            {
                "instrument_name": name,
                "amount_outstanding_mm": 0.0,
                "amount_available_mm": None,
                "coupon_percent": "variable",
                "maturity_year": maturity_year,
                "priority": sec_unsec.title(),
                "parent_issuer": None,
                "issue_date": issue_d.isoformat(),
                "instrument_type": "credit_facility",
                "lien_level": None,
                "provenance": {"source": "narrative", "agreement_name": agreement},
            }
        )
    return out


def _extract_instruments_from_primary_table(soup: BeautifulSoup) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Extract instruments from the main debt schedule table (usually the first big table in the debt note).
    Heuristic:
      - pick the table with the most occurrences of "due <Month> <d>, <yyyy>"
      - instrument name is the first text cell of each data row containing 'due'
      - amount is the next numeric-ish cell
      - coupon is the next numeric-ish cell (or "variable")
    """
    notes: List[str] = []
    tables = soup.find_all("table")
    if not tables:
        return [], notes

    def score_table(tab) -> int:
        txt = tab.get_text(" ", strip=True)
        return len(re.findall(r"\bdue\s+[A-Za-z]+\s+\d{1,2},\s*\d{4}\b", txt, flags=re.IGNORECASE))

    scored = [(score_table(t), i, t) for i, t in enumerate(tables)]
    scored.sort(reverse=True, key=lambda x: x[0])
    best_score, best_idx, best = scored[0]
    if best_score == 0:
        return [], notes

    notes.append(f"Selected table #{best_idx} as primary debt schedule (score={best_score}).")

    instruments: List[Dict[str, Any]] = []

    rows = best.find_all("tr")
    for r in rows:
        cells = r.find_all(["td", "th"])
        if not cells:
            continue
        cell_texts = [_clean_space(c.get_text(" ", strip=True)) for c in cells]
        row_text = " | ".join(cell_texts)

        # Find the cell that contains 'due <date>' - treat that as instrument name cell
        name_idx = None
        for j, ct in enumerate(cell_texts):
            if re.search(r"\bdue\s+[A-Za-z]+\s+\d{1,2},\s*\d{4}\b", ct, flags=re.IGNORECASE):
                name_idx = j
                break
        if name_idx is None:
            continue

        name = cell_texts[name_idx]
        if not name:
            continue

        # Simple forward scan for amount + coupon
        amount: Optional[float] = None
        coupon: Optional[Any] = None

        for k in range(name_idx + 1, len(cell_texts)):
            if amount is None:
                amount = _safe_float_from_text(cell_texts[k])
                if amount is not None:
                    continue
            if coupon is None:
                t = _clean_space(cell_texts[k])
                if not t:
                    continue
                if t.lower() == "variable":
                    coupon = "variable"
                    break
                # coupon percent like 5.90
                f = _safe_float_from_text(t)
                if f is not None and 0 < f < 100:
                    coupon = f
                    break

        maturity_year = _extract_maturity_year_from_name(name)
        priority = "Unsecured" if "unsecured" in _lower(name) else None
        amount_mm = _to_mm_if_thousands(amount)

        instruments.append(
            {
                "instrument_name": name,
                "amount_outstanding_mm": amount_mm,
                "amount_available_mm": None,
                "coupon_percent": coupon,
                "maturity_year": maturity_year,
                "priority": priority,
                "parent_issuer": None,
                "issue_date": None,  # back-filled later
                "instrument_type": _classify_instrument_type(name),
                "lien_level": None,
                "provenance": {"source": "table", "table_index": best_idx, "row_text": row_text[:500]},
            }
        )

        # instruments.append(
        #     {
        #         "instrument_name": name,
        #         "amount_outstanding_mm": amount,
        #         "amount_available_mm": None,
        #         "coupon_percent": coupon,
        #         "maturity_year": maturity_year,
        #         "priority": priority,
        #         "parent_issuer": None,
        #         "issue_date": None,  # back-filled later
        #         "instrument_type": _classify_instrument_type(name),
        #         "lien_level": None,
        #         "provenance": {"source": "table", "table_index": best_idx, "row_text": row_text[:500]},
        #     }
        # )

    return instruments, notes


def parse_debt_note_html(html_path: str, period_end_date_text: Optional[str] = None, parent_company_name: Optional[str] = None) -> Dict[str, Any]:
    raw = Path(html_path).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")

    full_text = _soup_text(soup)

    instruments, notes = _extract_instruments_from_primary_table(soup)

    # Back-fill issue dates for note/bond rows from narrative map
    due_to_issue = _build_issue_date_map_from_narrative(full_text)
    if due_to_issue:
        notes.append(f"Built issue-date map from narrative with {len(due_to_issue)} entries.")

    for ins in instruments:
        due_txt = _extract_due_date_text_from_name(ins["instrument_name"])
        if due_txt and due_txt in due_to_issue:
            ins["issue_date"] = due_to_issue[due_txt]

    # Add credit facilities found only in narrative (if not already present)
    narrative_facilities = _extract_credit_facilities_from_narrative(full_text)
    if narrative_facilities:
        notes.append(f"Extracted {len(narrative_facilities)} credit facility instrument(s) from narrative.")

    existing_names = {_lower(i["instrument_name"]) for i in instruments}
    for cf in narrative_facilities:
        if _lower(cf["instrument_name"]) not in existing_names:
            instruments.append(cf)

    # Fill in instrument_type, parent_issuer best-effort
    parent_issuer = _extract_parent_issuer(full_text)
    for ins in instruments:
        if not ins.get("instrument_type"):
            ins["instrument_type"] = _classify_instrument_type(ins["instrument_name"])
        if parent_issuer and not ins.get("parent_issuer"):
            ins["parent_issuer"] = parent_issuer

    # Sort to match expected human outputs: maturity_year then name
    def sort_key(i: Dict[str, Any]) -> Tuple[int, str]:
        y = i.get("maturity_year")
        y_key = int(y) if isinstance(y, int) else 9999
        return (y_key, i.get("instrument_name", ""))

    instruments.sort(key=sort_key)

    return {
        "parent_company_name": parent_company_name,
        "period_end_date_text": period_end_date_text,
        "instruments": instruments,
        "notes": notes,
    }


def _cli() -> int:
    ap = argparse.ArgumentParser(description="Parse a debt_note HTML and extract debt instruments.")
    ap.add_argument("--html", required=True, help="Path to debt_note.html")
    ap.add_argument("--period-end", dest="period_end", default=None, help='Period end date text, e.g. "December 28, 2024"')
    ap.add_argument("--parent-company", dest="parent_company", default=None, help="Optional parent company display name")
    ap.add_argument("--out", default=None, help="Output JSON path (prints to stdout if omitted)")
    args = ap.parse_args()

    result = parse_debt_note_html(
        args.html,
        period_end_date_text=args.period_end,
        parent_company_name=args.parent_company,
    )

    out_json = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out_json, encoding="utf-8")
    else:
        print(out_json)
    return 0

def extract_debt_instruments_from_debt_note(
    html_path: str,
    period_end_date_text: Optional[str] = None,
    parent_company_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Backwards-compatible wrapper expected by capital_structure_builder.py
    """
    return parse_debt_note_html(
        html_path,
        period_end_date_text=period_end_date_text,
        parent_company_name=parent_company_name,
    )

if __name__ == "__main__":
    raise SystemExit(_cli())
