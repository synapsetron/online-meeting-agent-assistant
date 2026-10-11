"""Будує рисунки розділу 2: топології координації, еволюцію гіпотези розпізнавання, складники
затримки, модель життєвого циклу пункту та діаграми матриці вибору.

Дані для рис. 2.2 читаються з decision_matrix_result.json (експертні оцінки, не вимірювання).
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).parent
OUT = HERE.parent / "figures"
OUT.mkdir(exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Serif", "font.size": 11})
INK, GREY, ACCENT = "#222222", "#9a9a9a", "#2f5f8f"


def _box(ax, x, y, w, h, text, fc="white", ec=INK, fs=10, ls="-"):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.04,rounding_size=0.12",
                                fc=fc, ec=ec, lw=1.3, ls=ls))
    ax.text(x, y, text, ha="center", va="center", color=INK, fontsize=fs)


def _arrow(ax, a, b, both=False, ls="-", color=INK):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="<|-|>" if both else "-|>", mutation_scale=12, lw=1.1,
                                 color=color, ls=ls))


def topologies() -> None:
    fig, (a, b) = plt.subplots(1, 2, figsize=(9.2, 3.6))
    for ax in (a, b):
        ax.set_xlim(0, 10); ax.set_ylim(0, 6); ax.axis("off")
    _box(a, 5, 4.6, 3.2, 0.9, "Координатор", fc="#eaf1f8", ec=ACCENT)
    for x, t in ((1.7, "Агент 1"), (5, "Агент 2"), (8.3, "Агент 3")):
        _box(a, x, 1.6, 2.2, 0.9, t)
        _arrow(a, (x, 2.1), (5 + (x - 5) * 0.35, 4.1), both=True)
    _box(a, 5, 0.3, 4.6, 0.5, "спільний стан змінює лише координатор", ec="white", fs=9)
    a.set_title("а", loc="left")
    pts = {"Агент 1": (2, 4.6), "Агент 2": (8, 4.6), "Агент 3": (2, 1.4), "Агент 4": (8, 1.4)}
    for t, (x, y) in pts.items():
        _box(b, x, y, 2.2, 0.9, t)
    _arrow(b, (3.1, 4.6), (6.9, 4.6), both=True); _arrow(b, (3.1, 1.4), (6.9, 1.4), both=True)
    _arrow(b, (2, 4.1), (2, 1.9), both=True); _arrow(b, (8, 4.1), (8, 1.9), both=True)
    _arrow(b, (3.0, 4.15), (7.0, 1.85), both=True); _arrow(b, (7.0, 4.15), (3.0, 1.85), both=True)
    _box(b, 5, 0.3, 4.6, 0.5, "стан узгоджується обміном повідомленнями", ec="white", fs=9)
    b.set_title("б", loc="left")
    fig.tight_layout(); fig.savefig(OUT / "fig-2-1-topologies.png", dpi=200, bbox_inches="tight"); plt.close(fig)


def hypotheses() -> None:
    rows = [(0.6, "перейдемо", False), (1.2, "перейдемо до", False), (1.9, "перейдемо до питання", False),
            (2.6, "перейдемо до питання бюджет", False), (3.3, "Перейдемо до питання бюджету на", False),
            (4.4, "Перейдемо до питання бюджету на тестування.", True)]
    fig, ax = plt.subplots(figsize=(9.2, 3.5))
    ax.set_xlim(0, 11.6); ax.set_ylim(-0.8, len(rows) + 0.3); ax.axis("off")
    ax.annotate("", xy=(5.6, -0.35), xytext=(0.4, -0.35), arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.1))
    ax.text(3.0, -0.72, "час від початку висловлювання, с", ha="center", fontsize=9.5)
    ys = [len(rows) - 1 - i + 0.25 for i in range(len(rows))]
    labels = [ax.text(6.0, y, text, ha="left", va="center", fontsize=9) for y, (_, text, _) in zip(ys, rows)]
    # Ширина рамок береться з найдовшого рядка, щоб текст не виходив за рамку;
    # межі осей після вимірювання не змінюються, інакше ширина тексту в одиницях осі зміниться.
    fig.canvas.draw()
    to_data = ax.transData.inverted()
    right = max(to_data.transform_bbox(lb.get_window_extent()).x1 for lb in labels)
    box_w = right + 0.15 - 5.9
    for y, (t, _, final) in zip(ys, rows):
        ax.plot([0.4 + t, 0.4 + t], [-0.35, y], color=GREY, lw=0.7, ls=":")
        ax.text(0.4 + t, -0.2, f"{t:.1f}".replace(".", ","), ha="center", va="bottom", fontsize=8.5, color=GREY)
        ax.add_patch(FancyBboxPatch((5.9, y - 0.3), box_w, 0.6, boxstyle="round,pad=0.02,rounding_size=0.08",
                                    fc="#eaf1f8" if final else "white", ec=ACCENT if final else GREY, lw=1.2))
        ax.plot([0.4 + t, 5.9], [y, y], color=GREY, lw=0.7)
        ax.text(5.8, y + 0.14, "фінальна" if final else "часткова", ha="right", va="bottom", fontsize=8,
                color=ACCENT if final else GREY)
    fig.savefig(OUT / "fig-2-2-hypotheses.png", dpi=200, bbox_inches="tight"); plt.close(fig)


def latency() -> None:
    parts = [("L_cap", 1.7, "захоплення"), ("L_asr", 2.2, "розпізнавання"), ("L_tr", 2.0, "передавання"),
             ("L_det", 2.4, "детермінований\nаналіз"), ("L_gate", 2.8, "очікування\nвиклику"),
             ("L_llm", 1.8, "відповідь\nмоделі"), ("L_ui", 2.0, "відображення")]
    fig, ax = plt.subplots(figsize=(9.2, 2.6))
    x = 0.0
    shades = ["#d9d9d9", "#bdbdbd", "#d9d9d9", "#9fbbd6", "#f1d3ad", "#e8b87a", "#d9d9d9"]
    for (name, w, label), c in zip(parts, shades):
        ax.barh(1, w, left=x, color=c, edgecolor="white", height=0.5)
        ax.text(x + w / 2, 1, name, ha="center", va="center", fontsize=9.5)
        ax.text(x + w / 2, 0.55, label, ha="center", va="top", fontsize=8.5)
        x += w
    fast = sum(w for _, w, _ in parts[:4])
    ax.annotate("", xy=(fast, 1.42), xytext=(0, 1.42), arrowprops=dict(arrowstyle="<|-|>", color=ACCENT, lw=1.1))
    ax.text(fast / 2, 1.5, "швидкий шлях: оновлення стану плану", ha="center", va="bottom", fontsize=9, color=ACCENT)
    ax.annotate("", xy=(x, 1.75), xytext=(0, 1.75), arrowprops=dict(arrowstyle="<|-|>", color=INK, lw=1.1))
    ax.text(x / 2, 1.83, "повний шлях: семантична підказка", ha="center", va="bottom", fontsize=9)
    ax.set_xlim(0, x); ax.set_ylim(0.05, 2.1); ax.axis("off")
    fig.savefig(OUT / "fig-2-3-latency.png", dpi=200, bbox_inches="tight"); plt.close(fig)


def lifecycle() -> None:
    fig, ax = plt.subplots(figsize=(9.2, 3.4))
    ax.set_xlim(0, 10); ax.set_ylim(0, 4.4); ax.axis("off")
    _box(ax, 1.3, 2.2, 2.0, 0.9, "не розпочато")
    _box(ax, 5.0, 2.2, 2.2, 0.9, "обговорюється", fc="#eaf1f8", ec=ACCENT)
    _box(ax, 8.7, 3.6, 2.0, 0.9, "розглянуто")
    _box(ax, 8.7, 0.8, 2.0, 0.9, "відкладено")
    _box(ax, 1.3, 0.5, 2.0, 0.7, "пропущено", ls="--")
    _arrow(ax, (2.3, 2.2), (3.9, 2.2)); ax.text(3.1, 2.75, "позитивне свідчення:\nрепліки про пункт", ha="center", fontsize=9)
    _arrow(ax, (6.1, 2.5), (7.7, 3.45)); ax.text(6.3, 3.6, "перехід до іншої теми\nза наявності свідчень", ha="center", fontsize=9)
    _arrow(ax, (6.1, 1.9), (7.7, 0.95)); ax.text(7.35, 1.85, "перехід без\nсвідчень", ha="center", fontsize=9)
    ax.add_patch(FancyArrowPatch((7.7, 0.6), (5.2, 1.75), arrowstyle="-|>", mutation_scale=12, lw=1.1, color=INK,
                                 connectionstyle="arc3,rad=-0.25"))
    ax.text(5.7, 0.55, "повернення", ha="center", fontsize=9)
    _arrow(ax, (1.3, 1.75), (1.3, 0.85), ls="--"); ax.text(1.5, 1.3, "рішення ведучого", ha="left", fontsize=9)
    fig.savefig(OUT / "fig-2-4-lifecycle.png", dpi=200, bbox_inches="tight"); plt.close(fig)


def matrix() -> None:
    data = json.loads((HERE / "decision_matrix_result.json").read_text(encoding="utf-8"))
    names = list(data["weighted"])
    labels = [n.split()[0] for n in names]
    fig, (a, b) = plt.subplots(1, 2, figsize=(9.2, 3.6))

    scores = [data["weighted"][n] for n in names]
    bars = a.bar(labels, scores, color=[ACCENT if l == "G" else GREY for l in labels])
    for bar, s in zip(bars, scores):
        a.text(bar.get_x() + bar.get_width() / 2, s + 0.05, f"{s:.2f}".replace(".", ","),
               ha="center", fontsize=9.5)
    a.set_ylim(0, 4.3); a.set_yticks(range(5)); a.set_ylabel("Зважена сума, бали"); a.set_title("а", loc="left")

    x = range(len(labels)); wd = 0.38
    best = [100 * data["mc_best_share"][n] for n in names]
    top2 = [100 * data["mc_top2_share"][n] for n in names]
    b.bar([i - wd / 2 for i in x], best, wd, color=ACCENT, label="найкраща")
    b.bar([i + wd / 2 for i in x], top2, wd, color=GREY, label="серед двох найкращих")
    b.set_xticks(list(x)); b.set_xticklabels(labels)
    b.set_ylim(0, 110); b.set_ylabel("Частка наборів ваг, %"); b.set_title("б", loc="left")
    b.legend(frameon=False, fontsize=9.5, loc="upper left")
    for axis in (a, b):
        axis.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig-2-5-matrix.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    topologies()
    hypotheses()
    latency()
    lifecycle()
    matrix()
    print(OUT)
