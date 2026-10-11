"""Зведення пілотних живих сесій із logs/backend.jsonl для розділу 7.

Запуск із кореня репозиторію:
    server/.venv/bin/python docs/practice-report/analysis/pilot_stats.py

Журнал містить лише лічильники (без тексту транскрипту). Сесії, у яких темп
«мовлення» перевищує MAX_WORDS_PER_MIN, вважаються зіпсованими дублюванням
субтитрів (до виправлення caption-growth) і виключаються з оцінок вартості.
Час відповіді моделі від дублювання не залежить, тому береться з усіх викликів.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LOG = ROOT / "logs" / "backend.jsonl"
OUT = Path(__file__).with_name("pilot_stats.json")
MAX_WORDS_PER_MIN = 250
# Сесія на збірці до виправлення дублювання субтитрів (зафіксовано в CLAUDE.md).
KNOWN_INFLATED = {"7c755822"}
PRICE_IN, PRICE_OUT = 0.10 / 1e6, 0.50 / 1e6  # claude-haiku-5-5, дол. США за токен


def pct(values: list[float], q: float) -> float:
    v = sorted(values)
    pos = (len(v) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def dist(values: list[float]) -> dict:
    return {"n": len(values), "min": min(values), "median": statistics.median(values),
            "mean": round(statistics.mean(values), 1), "p95": round(pct(values, 0.95), 1), "max": max(values)}


def main() -> None:
    sessions: dict[str, dict] = defaultdict(lambda: {
        "words": 0, "final_segments": 0, "seg_ms": [], "hint_calls": [], "summary_calls": [],
        "hints_llm": 0, "hints_time": 0, "suppressed": 0, "switched": [], "switch_skipped": [],
        "flush": 0, "skips": defaultdict(int), "dismissed": 0})
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = e.get("session")
        if not sid:
            continue
        s = sessions[sid]
        name = e.get("event")
        if name == "session_started":
            s["start"] = e["ts"]
        elif name == "segment_processed" and e.get("final"):
            s["words"] += e.get("words", 0)
            s["final_segments"] += 1
            s["seg_ms"].append(e.get("duration_ms", 0))
        elif name == "llm_call":
            rec = {k: e.get(k) for k in ("segments", "input_tokens", "output_tokens", "latency_ms",
                                          "hints_accepted", "agenda_proposal", "stop_reason")}
            (s["hint_calls"] if e.get("kind") == "hint" else s["summary_calls"]).append(rec)
        elif name == "hint_pushed":
            s["hints_llm" if e.get("source") == "llm" else "hints_time"] += 1
        elif name == "hint_suppressed_repeat":
            s["suppressed"] += 1
        elif name == "hint_dismissed":
            s["dismissed"] += 1
        elif name == "agenda_switched":
            s["switched"].append(e.get("confidence"))
        elif name == "agenda_switch_skipped":
            s["switch_skipped"].append(e.get("reason"))
        elif name == "llm_flush":
            s["flush"] += 1
        elif name == "llm_skipped":
            s["skips"][e.get("reason")] += 1
        elif name == "session_closed":
            s["duration_s"] = e.get("duration_s")
            s["est_cost_usd"] = e.get("est_cost_usd")

    rows = []
    for sid, s in sessions.items():
        calls = s["hint_calls"] + s["summary_calls"]
        if not calls or not s.get("duration_s"):
            continue
        wpm = s["words"] / s["duration_s"] * 60
        tin = sum(c["input_tokens"] for c in calls)
        tout = sum(c["output_tokens"] for c in calls)
        rows.append({
            "session": sid[:8], "start": s.get("start"), "duration_s": s["duration_s"],
            "final_segments": s["final_segments"], "words": s["words"], "words_per_min": round(wpm),
            "valid": wpm <= MAX_WORDS_PER_MIN and sid[:8] not in KNOWN_INFLATED,
            "hint_calls": len(s["hint_calls"]), "summary_calls": len(s["summary_calls"]),
            "input_tokens": tin, "output_tokens": tout,
            "cost_usd": round(tin * PRICE_IN + tout * PRICE_OUT, 6),
            "hints_llm": s["hints_llm"], "hints_time": s["hints_time"], "suppressed": s["suppressed"],
            "dismissed": s["dismissed"], "switched": s["switched"], "switch_skipped": s["switch_skipped"],
            "flush": s["flush"], "skips": dict(s["skips"]),
            "hint_call_list": s["hint_calls"], "summary_call_list": s["summary_calls"], "seg_ms": s["seg_ms"],
        })
    rows.sort(key=lambda r: r["start"] or "")

    hint = [c for r in rows for c in r["hint_call_list"]]
    summ = [c for r in rows for c in r["summary_call_list"]]
    valid = [r for r in rows if r["valid"]]
    seg_ms = [v for r in rows for v in r["seg_ms"]]
    dur = sum(r["duration_s"] for r in valid)
    cost = sum(r["cost_usd"] for r in valid)
    with_hint = [c for c in hint if c["hints_accepted"]]
    empty = [c for c in hint if not c["hints_accepted"]]
    result = {
        "max_words_per_min": MAX_WORDS_PER_MIN,
        "sessions": rows,
        "hint_latency_ms": dist([c["latency_ms"] for c in hint]),
        "summary_latency_ms": dist([c["latency_ms"] for c in summ]) if summ else None,
        "hint_input_tokens": dist([c["input_tokens"] for c in hint]),
        "hint_output_tokens_with_hint": dist([c["output_tokens"] for c in with_hint]),
        "hint_output_tokens_empty": dist([c["output_tokens"] for c in empty]) if empty else None,
        "summary_input_tokens": dist([c["input_tokens"] for c in summ]) if summ else None,
        "summary_output_tokens": dist([c["output_tokens"] for c in summ]) if summ else None,
        "segment_ms": dist(seg_ms),
        "stop_reasons": sorted({c["stop_reason"] for c in hint + summ}),
        "valid": {"sessions": len(valid), "duration_s": round(dur, 1), "cost_usd": round(cost, 6),
                  "cost_per_hour": round(cost / dur * 3600, 4),
                  "hint_calls": sum(r["hint_calls"] for r in valid),
                  "hint_calls_per_hour": round(sum(r["hint_calls"] for r in valid) / dur * 3600, 1),
                  "hints_shown": sum(r["hints_llm"] + r["hints_time"] for r in valid),
                  "words": sum(r["words"] for r in valid),
                  "final_segments": sum(r["final_segments"] for r in valid),
                  "summary_calls": sum(r["summary_calls"] for r in valid),
                  "suppressed": sum(r["suppressed"] for r in valid),
                  "calls_with_hint": sum(1 for r in valid for c in r["hint_call_list"] if c["hints_accepted"]),
                  "switched": sum(len(r["switched"]) for r in valid),
                  "switch_skipped": [x for r in valid for x in r["switch_skipped"]],
                  "flush": sum(r["flush"] for r in valid)},
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rows:
        print({k: v for k, v in r.items() if not k.endswith("_list") and k != "seg_ms"})
    print({k: v for k, v in result.items() if k != "sessions"})


if __name__ == "__main__":
    main()
