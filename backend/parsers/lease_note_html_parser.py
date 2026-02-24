#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
lease_note_html_parser.py

Goal: Extract operating lease liabilities as Senior Secured instruments
so the output matches AAP.html.

Critical fix:
- In the lease table rows, the pattern is often:
    Label | $ | 2,358,693 | ... | $ | 2,423,183 | ...
  Your previous parser was selecting the '$' cell as the value column.
  This version always selects the first numeric immediately after a '$' token.

Output amounts are in $mm with 3 decimals:
  2,358,693 (thousands) => 2,358.693 ($mm)

CLI:
  python lease_note_html_parser.py input/lease_note.html --period-end "December 28, 2024" --out output/lease_note_parsed.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from bs4.element import Tag


# ----------------------------
# Models
# ----------------------------

@dataclass
class LeaseInstrument:
    instrument_name: str
    amount_outstanding_mm: Optional[float]
    amount_available_mm: Optional[float]
    coupon_percent: Optional[str]
    maturity_year: str
    priority: str
    parent_issuer: Optional[str]
    issue_date: Optional[str]
    instrument_type: str
    lien_level: Optional[str]
    provenance: Dict[str, Any]


# ----------------------------
# Helpers
# ----------------------------

def _read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def _clean_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_number(cell: str) -> Optional[float]:
    """
    Parses: 2,358,693  or (461,528) or $ 1,234
    """
    if cell is None:
        return None
    t = _clean_ws(cell)
    if not t or t in {"-", "—"}:
        return None
    t = t.replace("$", "").replace("US$", "").strip()
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg = True
        t = t[1:-1].strip()
    t = t.replace(",", "").replace(" ", "")
    if not re.fullmatch(r"\d+(\.\d+)?", t):
        return None
    v = float(t)
    return -v if neg else v


def _to_mm_from_lease_table(raw: float) -> float:
    """
    Lease tables are typically in thousands.
    Heuristic: if abs(raw) >= 10,000 -> treat as thousands -> /1000 to $mm.
    """
    if abs(raw) >= 10_000:
        return raw / 1000.0
    return raw


def _html_snippet(tag: Tag, max_chars: int = 1200) -> str:
    h = str(tag)
    return h[:max_chars] + ("..." if len(h) > max_chars else "")


def _expand_row(tr: Tag) -> List[str]:
    """
    Expand colspans by duplicating the text to keep indexing stable.
    """
    out: List[str] = []
    for cell in tr.find_all(["th", "td"], recursive=False):
        text = _clean_ws(cell.get_text(" ", strip=True))
        colspan = int(cell.get("colspan") or 1)
        out.extend([text] * max(1, colspan))

    # fallback in case cells are nested strangely
    if not out:
        for cell in tr.find_all(["th", "td"], recursive=True):
            text = _clean_ws(cell.get_text(" ", strip=True))
            colspan = int(cell.get("colspan") or 1)
            out.extend([text] * max(1, colspan))

    return out


def _table_matrix(table: Tag) -> List[List[str]]:
    matrix: List[List[str]] = []
    for tr in table.find_all("tr"):
        row = _expand_row(tr)
        if any(c.strip() for c in row):
            matrix.append(row)
    return matrix


def _first_amount_after_dollar(row: List[str]) -> Tuple[Optional[float], Optional[int]]:
    """
    Returns (value, index) of the FIRST numeric cell immediately after a '$' token.
    This fixes the exact bug you had (picking the '$' cell).
    """
    for i in range(len(row) - 1):
        if _clean_ws(row[i]) == "$":
            v = _parse_number(row[i + 1])
            if v is not None:
                return v, i + 1
    return None, None


# ----------------------------
# Extraction
# ----------------------------

TARGETS: List[Tuple[str, str, str]] = [
    ("total operating lease liabilities", "Total operating lease liabilities", "operating_lease"),
    ("non current operating lease liabilities", "Non-current operating lease liabilities", "operating_lease"),
    ("total finance lease liabilities", "Total finance lease liabilities", "finance_lease"),
    ("non current finance lease liabilities", "Non-current finance lease liabilities", "finance_lease"),
]


def _match_target(row: List[str]) -> Optional[Tuple[str, str, str]]:
    """
    Matches on the first cell label (or first 2 cells joined),
    normalized to handle hyphens/punctuation.
    """
    if not row:
        return None
    c0 = _norm(row[0])
    c1 = _norm(row[1]) if len(row) > 1 else ""
    candidates = [c0, f"{c0} {c1}".strip()]

    for key, pretty, typ in TARGETS:
        for cand in candidates:
            if cand == key:
                return key, pretty, typ
    return None


def parse_lease_note_html(lease_note_html_path: str | Path, period_end_date_text: Optional[str]) -> Dict[str, Any]:
    soup = BeautifulSoup(_read_text(lease_note_html_path), "lxml")
    instruments: List[LeaseInstrument] = []
    notes: List[str] = []

    for ti, table in enumerate(soup.find_all("table")):
        matrix = _table_matrix(table)
        if len(matrix) < 3:
            continue

        joined = " ".join(" ".join(r) for r in matrix).lower()
        if "lease liabilities" not in joined:
            continue

        for row in matrix:
            hit = _match_target(row)
            if not hit:
                continue

            _, pretty, lease_type = hit

            raw, used_idx = _first_amount_after_dollar(row)
            if raw is None:
                # fallback: last numeric in row
                last_num = None
                last_idx = None
                for idx, cell in enumerate(row):
                    v = _parse_number(cell)
                    if v is not None:
                        last_num, last_idx = v, idx
                raw, used_idx = last_num, last_idx

            if raw is None:
                continue

            amount_mm = round(_to_mm_from_lease_table(raw), 3)

            instruments.append(
                LeaseInstrument(
                    instrument_name=pretty,
                    amount_outstanding_mm=amount_mm,
                    amount_available_mm=None,
                    coupon_percent=None,
                    maturity_year="Various",
                    priority="Senior Secured",
                    parent_issuer=None,
                    issue_date=None,
                    instrument_type=lease_type,
                    lien_level=None,
                    provenance={
                        "table_index": ti,
                        "period_end_date_text": period_end_date_text,
                        "value_cell_index": used_idx,
                        "row_text": " | ".join(_clean_ws(c) for c in row),
                        "html_snippet": _html_snippet(table),
                    },
                )
            )

    # Deduplicate repeated iXBRL tables
    deduped: List[LeaseInstrument] = []
    seen = set()
    for ins in instruments:
        key = (ins.instrument_name, ins.amount_outstanding_mm, ins.instrument_type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ins)

    if not deduped:
        notes.append("No lease instruments extracted (pattern may differ in this filing).")

    return {
        "period_end_date_text": period_end_date_text,
        "instruments": [asdict(x) for x in deduped],
        "notes": notes,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse lease_note.html into lease instruments.")
    ap.add_argument("lease_note_html", help="Path to lease_note.html")
    ap.add_argument("--period-end", default=None, help='e.g., "December 28, 2024" (optional, for provenance)')
    ap.add_argument("--out", default=None, help="Write JSON output to this path")
    args = ap.parse_args()

    result = parse_lease_note_html(args.lease_note_html, args.period_end)

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, indent=2), encoding="utf-8")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()