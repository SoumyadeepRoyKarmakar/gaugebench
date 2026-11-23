"""Answer parsing and scoring.

Numbers: correct iff |answer - key| <= tolerance (half the local smallest dial
division, summed when two readings are combined). We also keep the error in
"tolerance units" so analysis can tell a near miss from a wild guess.
Choices: case/punctuation-insensitive exact match against the allowed options.
"""
from __future__ import annotations

import re

NUM_RE = re.compile(r"[-−+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?|[-−+]?\.\d+")


def _final_segment(text: str) -> str | None:
    hits = re.findall(r"ANSWER\s*[:：]\s*(.+)", text or "", flags=re.IGNORECASE)
    return hits[-1].strip() if hits else None


def parse_number(text: str) -> float | None:
    seg = _final_segment(text)
    if seg is None:
        return None
    m = NUM_RE.search(seg.replace("**", ""))
    if not m:
        return None
    s = m.group(0).replace("−", "-").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def parse_choice(text: str, choices: list[str]) -> str | None:
    seg = _final_segment(text)
    if seg is None:
        return None
    n = _norm(seg)
    exact = [c for c in choices if _norm(c) == n]
    if exact:
        return exact[0]
    contained = [c for c in choices if _norm(c) and _norm(c) in n]
    return contained[0] if len(contained) == 1 else None


def score(task: dict, text: str) -> dict:
    if task["answer_type"] == "number":
        v = parse_number(text)
        if v is None:
            return {"parsed": None, "correct": False, "parse_ok": False, "abs_err": None, "err_tol_units": None}
        err = abs(v - float(task["answer"]))
        tol = float(task["tolerance"])
        return {"parsed": v, "correct": err <= tol + 1e-9, "parse_ok": True, "abs_err": err,
                "err_tol_units": err / tol if tol else None}
    c = parse_choice(text, task["choices"])
    return {"parsed": c, "correct": c == task["answer"], "parse_ok": c is not None,
            "abs_err": None, "err_tol_units": None}
