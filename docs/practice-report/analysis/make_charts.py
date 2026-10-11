"""Графіки розділу 7 з eval_offline_result.json (офлайн-експерименти та пілотні журнали)."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
OUT = HERE.parent / "figures"
R = json.loads((HERE / "eval_offline_result.json").read_text(encoding="utf-8"))
P = json.loads((HERE / "pilot_stats.json").read_text(encoding="utf-8"))
HINT_CALLS = [c for s in P["sessions"] for c in s["hint_call_list"]]
SUMMARY_CALLS = [c for s in P["sessions"] for c in s["summary_call_list"]]
plt.rcParams.update({"font.family": "DejaVu Serif", "font.size": 10})
INK, GREY, ACCENT, WARM = "#222222", "#9a9a9a", "#2f5f8f", "#c9853a"
NAMES = {"normal_flow": "С1", "drift_and_return": "С2", "skipped_item": "С3", "item_overrun": "С4",
         "long_meeting": "С5", "paraphrase": "С6"}


def clean(ax):
    ax.spines[["top", "right"]].set_visible(False)


def save(fig, name):
    fig.tight_layout(); fig.savefig(OUT / name, dpi=200, bbox_inches="tight"); plt.close(fig)


def pct(values, q):
    v = sorted(values); pos = (len(v) - 1) * q; lo = int(pos); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def fig_7_1():
    rows = [r for r in R["accuracy"] if r["variant"] in ("explicit", "paraphrase")]
    labels = [NAMES[r["scenario"]] for r in rows]
    x = range(len(rows)); w = 0.38
    fig, ax = plt.subplots(figsize=(8.6, 3.5))
    a = ax.bar([i - w / 2 for i in x], [100 * r["segment_accuracy"] for r in rows], w, color=ACCENT, label="частка реплік із правильним активним пунктом")
    b = ax.bar([i + w / 2 for i in x], [100 * r["f1"] for r in rows], w, color=GREY, label="F1 виявлення переходів")
    for bars in (a, b):
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5, f"{bar.get_height():.0f}", ha="center", fontsize=8.5)
    ax.set_xticks(list(x)); ax.set_xticklabels(labels); ax.set_ylim(0, 125); ax.set_yticks(range(0, 101, 20))
    ax.set_ylabel("%"); ax.legend(frameon=False, fontsize=9, loc="upper center", ncol=2); clean(ax)
    save(fig, "fig-7-1-accuracy.png")


def fig_7_2():
    n = R["noise"]; x = [100 * r["rate"] for r in n]
    fig, ax = plt.subplots(figsize=(8.6, 3.5))
    for key, color, label, marker in (("segment_accuracy", ACCENT, "частка правильних реплік", "o"), ("f1", WARM, "F1 переходів", "s")):
        mean = [100 * r[key]["mean"] for r in n]; sd = [100 * r[key]["sd"] for r in n]
        ax.errorbar(x, mean, yerr=sd, color=color, marker=marker, capsize=3, lw=1.6, label=label)
    ax.set_xlabel("Частка спотворених слів, %"); ax.set_ylabel("%"); ax.set_ylim(0, 105)
    ax.legend(frameon=False, fontsize=9); clean(ax); ax.grid(axis="y", color="#e5e5e5", lw=0.7)
    save(fig, "fig-7-2-noise.png")


def fig_7_3():
    hist = R["timing"]["hist"]; t = R["timing"]
    lat = [c["latency_ms"] for c in HINT_CALLS]; slat = [c["latency_ms"] for c in SUMMARY_CALLS]
    fig, (a, b) = plt.subplots(1, 2, figsize=(9.0, 3.4))
    a.hist([min(v, 0.3) for v in hist], bins=30, color=ACCENT)
    for q, name in ((t["p50_ms"], "медіана"), (t["p95_ms"], "p95")):
        a.axvline(q, color=INK, lw=1, ls="--"); a.text(q + 0.004, a.get_ylim()[1] * 0.9, name, fontsize=8.5)
    a.set_xlabel("Час детермінованої обробки репліки, мс"); a.set_ylabel("Кількість реплік"); a.set_title("а", loc="left"); clean(a)
    bins = [600 + 100 * i for i in range(20)]
    b.hist([lat, slat], bins=bins, stacked=True, color=[WARM, GREY], label=[f"підказки (n = {len(lat)})", f"підсумок (n = {len(slat)})"])
    b.axvline(statistics.median(lat), color=INK, lw=1, ls="--"); b.text(statistics.median(lat) + 25, b.get_ylim()[1] * 0.9, "медіана", fontsize=8.5)
    b.axvline(pct(lat, 0.95), color=INK, lw=1, ls=":"); b.text(pct(lat, 0.95) + 25, b.get_ylim()[1] * 0.78, "p95", fontsize=8.5)
    b.set_xlabel("Час відповіді моделі, мс"); b.set_ylabel("Кількість викликів"); b.set_title("б", loc="left")
    b.legend(frameon=False, fontsize=8.5, loc="center right"); clean(b)
    save(fig, "fig-7-3-latency.png")


def fig_7_4():
    profiles = R["gating"]["profiles"]; keys = [p["key"] for p in profiles]
    fig, (a, b) = plt.subplots(1, 2, figsize=(9.0, 3.4))
    lo = [p["cost_per_hour_low"] for p in profiles]; hi = [p["cost_per_hour_high"] for p in profiles]
    a.bar(keys, hi, color="#d9d9d9", label="верхнє припущення"); a.bar(keys, lo, color=ACCENT, label="нижнє припущення")
    a.set_yscale("log"); a.set_ylabel("Оцінка вартості, дол. США за годину"); a.set_title("а", loc="left")
    a.legend(frameon=False, fontsize=8.5); clean(a)
    calls = [p["calls_per_hour"] for p in profiles]
    bars = b.bar(keys, calls, color=GREY)
    for bar in bars:
        b.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 8, f"{bar.get_height():.0f}", ha="center", fontsize=8.5)
    b.set_ylabel("Викликів моделі за годину"); b.set_title("б", loc="left"); clean(b)
    save(fig, "fig-7-4-configs.png")


def fig_7_5():
    sweep = R["gating"]["sweep"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(9.0, 3.5))
    for words, color, marker in ((0, GREY, "^"), (25, WARM, "s"), (50, ACCENT, "o")):
        pts = sorted((s for s in sweep if s["min_words"] == words), key=lambda s: s["interval_s"])
        a.plot([s["interval_s"] for s in pts], [s["calls_per_hour"] for s in pts], color=color, marker=marker, lw=1.5, label=f"поріг {words} слів")
        b.plot([s["interval_s"] for s in pts], [s["delay_median_s"] for s in pts], color=color, marker=marker, lw=1.5, label=f"медіана, поріг {words}")
        if words == 50:
            b.plot([s["interval_s"] for s in pts], [s["delay_p95_s"] for s in pts], color=color, marker=marker, lw=1.2, ls="--", label="p95, поріг 50")
    for ax in (a, b):
        ax.axvline(45, color=INK, lw=0.8, ls=":"); ax.set_xlabel("Мінімальний інтервал між викликами, с"); clean(ax)
        ax.grid(axis="y", color="#e5e5e5", lw=0.7)
    a.set_ylabel("Викликів підказок за годину"); a.set_title("а", loc="left"); a.legend(frameon=False, fontsize=8.5)
    b.set_ylabel("Затримка очікування виклику, с"); b.set_title("б", loc="left"); b.legend(frameon=False, fontsize=8.5)
    save(fig, "fig-7-5-tradeoff.png")


def fig_7_6():
    fig, (a, b) = plt.subplots(1, 2, figsize=(9.0, 3.4))
    a.scatter([c["segments"] for c in HINT_CALLS], [c["input_tokens"] for c in HINT_CALLS], color=ACCENT, alpha=0.65, s=22)
    a.set_xlabel("Кількість реплік у вікні"); a.set_ylabel("Вхідні токени виклику"); a.set_ylim(0, 1100)
    a.set_title("а", loc="left"); clean(a); a.grid(axis="y", color="#e5e5e5", lw=0.7)
    with_hint = [c["output_tokens"] for c in HINT_CALLS if c["hints_accepted"]]
    empty = [c["output_tokens"] for c in HINT_CALLS if not c["hints_accepted"]]
    b.hist([empty, with_hint], bins=range(0, 131, 10), stacked=True, color=[GREY, WARM],
           label=[f"без підказки (n = {len(empty)})", f"з підказкою (n = {len(with_hint)})"])
    b.set_xlabel("Вихідні токени виклику"); b.set_ylabel("Кількість викликів"); b.set_title("б", loc="left")
    b.legend(frameon=False, fontsize=8.5); clean(b)
    save(fig, "fig-7-6-tokens.png")


def fig_7_7():
    rows = [r for r in P["sessions"] if r["valid"]]
    fig, ax = plt.subplots(figsize=(8.6, 3.3))
    x = range(1, len(rows) + 1)
    per_hour = [r["cost_usd"] / r["duration_s"] * 3600 for r in rows]
    bars = ax.bar(x, per_hour, color=ACCENT)
    ax.axhline(0.02, color=INK, lw=1, ls="--"); ax.text(len(rows) + 0.45, 0.0206, "проєктна ціль 0,02", ha="right", fontsize=8.5)
    total = P["valid"]["cost_per_hour"]
    ax.axhline(total, color=WARM, lw=1.2, ls=":"); ax.text(0.55, total + 0.0006, "зважене за тривалістю", ha="left", fontsize=8.5, color=WARM)
    for bar, r in zip(bars, rows):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.0005, f"{r['duration_s'] / 60:.1f} хв".replace(".", ","), ha="center", fontsize=7.5)
    ax.set_xticks(list(x)); ax.set_xlabel("Номер пілотної сесії"); ax.set_ylabel("Вартість, дол. США за годину")
    clean(ax)
    save(fig, "fig-7-7-pilot-cost.png")


if __name__ == "__main__":
    for f in (fig_7_1, fig_7_2, fig_7_3, fig_7_4, fig_7_5, fig_7_6, fig_7_7):
        f()
