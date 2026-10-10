"""Затримка очікування виклику моделі в пілотних сесіях (розділ 7).

Запуск із кореня репозиторію після pilot_stats.py:
    server/.venv/bin/python docs/practice-report/analysis/pilot_gating_delay.py

Для кожного фінального сегмента придатної сесії береться інтервал від його обробки
сервером до запуску найближчого наступного виклику підказок (момент запуску =
позначка події llm_call мінус latency_ms). Це складник L_gate; чи потрапив сегмент
у вікно з 8 реплік цього виклику, журнал не фіксує.
"""
from __future__ import annotations

import collections
import json
import statistics
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[2]


def pct(v: list[float], q: float) -> float:
    pos = (len(v) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def main() -> None:
    pilot = json.loads((HERE / "pilot_stats.json").read_text(encoding="utf-8"))
    valid = {r["session"] for r in pilot["sessions"] if r["valid"]}
    segs, calls = collections.defaultdict(list), collections.defaultdict(list)
    types: collections.Counter[str] = collections.Counter()
    for line in (ROOT / "logs" / "backend.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = (e.get("session") or "")[:8]
        if sid not in valid:
            continue
        ts = datetime.fromisoformat(e["ts"]).timestamp()
        name = e.get("event")
        if name == "segment_processed" and e.get("final"):
            segs[sid].append(ts)
        elif name == "llm_call" and e.get("kind") == "hint":
            calls[sid].append(ts - e["latency_ms"] / 1000)
        elif name == "hint_pushed":
            types[e.get("hint_type")] += 1
    delays, never, total = [], 0, 0
    for sid in valid:
        starts = sorted(calls[sid])
        for t in segs[sid]:
            total += 1
            later = [c for c in starts if c >= t - 0.05]
            if later:
                delays.append(max(0.0, later[0] - t))
            else:
                never += 1
    delays.sort()
    result = {"n": len(delays), "segments": total, "never": never, "median": statistics.median(delays),
              "p95": pct(delays, 0.95), "max": max(delays), "hint_types": dict(types)}
    (HERE / "pilot_gating_delay.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
