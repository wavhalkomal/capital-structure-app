# backend/app/bonus.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _round2(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    return float(f"{x:.3f}")  # keep a few decimals (your outputs often have 3)


def _get_in(d: Dict[str, Any], path: List[str], default=None):
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def build_citations(built: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Build a citations list from provenance already present in built_capital_structure.json.
    NO changes to parsers required.

    Output format is UI-friendly (cards).
    """
    citations: List[Dict[str, Any]] = []

    # --- Cash + NCI citations from balance sheet provenance (already present)
    bs_prov = _get_in(built, ["provenance", "balance_sheet"], {}) or {}

    cash = bs_prov.get("cash_and_cash_equivalents", {})
    if isinstance(cash, dict) and cash:
        citations.append(
            {
                "label": "Cash and cash equivalents",
                "file": "balance_sheet.json",
                "kind": "json",
                "where": cash.get("source_label") or cash.get("match_label") or "balance_sheet.json",
                "snippet": str(cash)[:400],
                "confidence": 0.99,
            }
        )

    nci = bs_prov.get("noncontrolling_interests", {})
    if isinstance(nci, dict) and nci:
        citations.append(
            {
                "label": "Noncontrolling interests",
                "file": "balance_sheet.json",
                "kind": "json",
                "where": nci.get("source_label") or nci.get("match_label") or "balance_sheet.json",
                "snippet": str(nci)[:400],
                "confidence": 0.95,
            }
        )

    # --- Instrument citations (debt + leases)
    instruments = built.get("instruments") or []
    if isinstance(instruments, list):
        for idx, inst in enumerate(instruments, start=1):
            if not isinstance(inst, dict):
                continue

            name = inst.get("instrument_name") or inst.get("name") or f"Instrument {idx}"
            prov = inst.get("provenance") or {}
            if not isinstance(prov, dict) or not prov:
                continue

            src = prov.get("source_file") or prov.get("file") or "unknown"
            table_index = prov.get("table_index")
            row_text = prov.get("row_text") or ""
            html_snip = prov.get("html_snippet") or ""

            where = []
            if table_index is not None:
                where.append(f"table_index={table_index}")
            if prov.get("row_index") is not None:
                where.append(f"row_index={prov.get('row_index')}")
            where = ", ".join(where) if where else "—"

            snippet = (html_snip or row_text or str(prov))[:400]

            citations.append(
                {
                    "label": name,
                    "file": src,
                    "kind": "html" if str(src).endswith(".html") else "json",
                    "where": where,
                    "snippet": snippet,
                    "confidence": prov.get("confidence", 0.75),
                }
            )

    return citations


def _sum_instrument_outstanding(built: Dict[str, Any]) -> float:
    total = 0.0
    instruments = built.get("instruments") or []
    for inst in instruments:
        if not isinstance(inst, dict):
            continue
        amt = _safe_float(inst.get("amount_outstanding_mm"))
        if amt is None:
            amt = _safe_float(inst.get("amount_outstanding"))  # just in case
        if amt is None:
            continue
        total += amt
    return total


def _find_value(built: Dict[str, Any], keys: List[str]) -> Optional[float]:
    for k in keys:
        v = _safe_float(built.get(k))
        if v is not None:
            return v
    return None


def run_self_assessment(built: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute correctness checks + a score from built_capital_structure.json.
    NO changes to the working pipeline required.
    """
    checks: List[Dict[str, Any]] = []

    total_debt = _find_value(built, ["total_debt_mm", "total_debt"])
    cash = _find_value(built, ["cash_and_cash_equivalents_mm", "cash_mm", "cash_and_cash_equivalents"])
    nci = _find_value(built, ["noncontrolling_interests_mm", "nci_mm", "noncontrolling_interests"])
    market_cap = _find_value(built, ["market_cap_mm", "market_cap"])
    net_debt = _find_value(built, ["net_debt_mm", "net_debt"])
    ev = _find_value(built, ["enterprise_value_mm", "enterprise_value"])

    sum_inst = _sum_instrument_outstanding(built)

    def add_check(cid: str, status: str, message: str, **extra):
        obj = {"id": cid, "status": status, "message": message}
        obj.update(extra)
        checks.append(obj)

    # --- Check: total debt vs sum of instruments
    if total_debt is not None:
        delta = abs(total_debt - sum_inst)
        if delta <= 0.05:
            add_check("arith_total_debt", "pass", f"Total Debt matches sum of instruments (Δ={_round2(delta)}).", delta=_round2(delta))
        elif delta <= 0.5:
            add_check("arith_total_debt", "warn", f"Total Debt slightly differs from sum of instruments (Δ={_round2(delta)}).", delta=_round2(delta))
        else:
            add_check("arith_total_debt", "fail", f"Total Debt differs from sum of instruments (Δ={_round2(delta)}).", delta=_round2(delta))
    else:
        add_check("arith_total_debt", "warn", "Total Debt not found in built output.")

    # --- Check: net debt
    if total_debt is not None and cash is not None and net_debt is not None:
        expected = total_debt - cash
        delta = abs(net_debt - expected)
        if delta <= 0.05:
            add_check("arith_net_debt", "pass", f"Net Debt matches Total Debt - Cash (Δ={_round2(delta)}).", delta=_round2(delta))
        elif delta <= 0.5:
            add_check("arith_net_debt", "warn", f"Net Debt slightly differs (Δ={_round2(delta)}).", delta=_round2(delta))
        else:
            add_check("arith_net_debt", "fail", f"Net Debt differs (Δ={_round2(delta)}).", delta=_round2(delta))
    else:
        add_check("arith_net_debt", "warn", "Net Debt check skipped (missing Total Debt/Cash/Net Debt).")

    # --- Check: enterprise value
    if ev is not None and net_debt is not None and nci is not None and market_cap is not None:
        expected = net_debt + nci + market_cap
        delta = abs(ev - expected)
        if delta <= 0.05:
            add_check("arith_enterprise_value", "pass", f"EV matches Net Debt + NCI + Market Cap (Δ={_round2(delta)}).", delta=_round2(delta))
        elif delta <= 0.5:
            add_check("arith_enterprise_value", "warn", f"EV slightly differs (Δ={_round2(delta)}).", delta=_round2(delta))
        else:
            add_check("arith_enterprise_value", "fail", f"EV differs (Δ={_round2(delta)}).", delta=_round2(delta))
    else:
        add_check("arith_enterprise_value", "warn", "EV check skipped (missing EV/Net Debt/NCI/Market Cap).")

    # --- Sanity checks on instruments
    instruments = built.get("instruments") or []
    missing_fields = 0
    neg_amounts = 0
    for inst in instruments:
        if not isinstance(inst, dict):
            continue
        name = inst.get("instrument_name")
        amt = _safe_float(inst.get("amount_outstanding_mm"))
        priority = inst.get("priority")
        maturity = inst.get("maturity")
        coupon = inst.get("coupon")

        if not name or priority is None:
            missing_fields += 1
        if amt is not None and amt < -1e-6:
            neg_amounts += 1
        # maturity sanity (if numeric)
        try:
            if maturity not in (None, "", "—"):
                y = int(str(maturity))
                if y < 1990 or y > 2100:
                    add_check("sanity_maturity", "warn", f"Suspicious maturity year: {y} for {name}.")
                    break
        except Exception:
            pass

    if missing_fields == 0:
        add_check("completeness", "pass", "All instruments have basic required fields (name/priority).")
    else:
        add_check("completeness", "warn", f"{missing_fields} instrument(s) missing name/priority.")

    if neg_amounts == 0:
        add_check("sanity_negative_amounts", "pass", "No negative outstanding amounts detected.")
    else:
        add_check("sanity_negative_amounts", "fail", f"{neg_amounts} instrument(s) have negative outstanding amounts.")

    # --- Score
    score = 100
    for c in checks:
        if c["status"] == "fail":
            score -= 20
        elif c["status"] == "warn":
            score -= 5
    score = max(0, min(100, score))

    return {"score": score, "checks": checks}