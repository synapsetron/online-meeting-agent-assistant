"""Схеми для розділів 3–5 (архітектура, варіанти використання, послідовність, блок-схеми)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

OUT = Path(__file__).parent.parent / "figures"
OUT.mkdir(exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Serif", "font.size": 9.5})
INK, GREY, ACCENT, FILL, LLM = "#222222", "#8a8a8a", "#2f5f8f", "#eaf1f8", "#fbefe0"


def canvas(w: float, h: float, xmax: float = 100, ymax: float = 60):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, xmax); ax.set_ylim(0, ymax); ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, text, fc="white", ec=INK, fs=9.5, bold=False, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.8",
                                fc=fc, ec=ec, lw=1.2, ls=ls))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            color=INK, fontweight="bold" if bold else "normal")


def group(ax, x, y, w, h, title):
    ax.add_patch(Rectangle((x, y), w, h, fc="#f7f7f7", ec=GREY, lw=1.0, ls="--"))
    ax.text(x + 1, y + h - 1.2, title, ha="left", va="top", fontsize=9, color=GREY, style="italic")


def arrow(ax, a, b, text="", dx=0, dy=1.2, both=False, ls="-", fs=8.5, ha="center", color=INK):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="<|-|>" if both else "-|>", mutation_scale=11,
                                 lw=1.1, color=color, ls=ls, shrinkA=0, shrinkB=0))
    if text:
        ax.text((a[0] + b[0]) / 2 + dx, (a[1] + b[1]) / 2 + dy, text, ha=ha, va="center", fontsize=fs, color=INK)


def diamond(ax, cx, cy, w, h, text, fs=8.5):
    ax.add_patch(Polygon([(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)],
                         closed=True, fc="white", ec=INK, lw=1.2))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs)


def save(fig, name):
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_3_1():
    fig, ax = canvas(11.5, 6.2, xmax=136, ymax=71)
    fs, ls_ = 9.5, 8.8
    box(ax, 2, 62, 30, 8, "Сторінка Google Meet:\nсубтитри з іменами мовців", fs=fs, ls="--")
    group(ax, 1, 3, 32, 54, "Браузер")
    box(ax, 2, 38, 30, 13, "Content script:\nчитання субтитрів,\nвиділення нового тексту,\nоверлей", fs=fs)
    box(ax, 2, 21, 30, 11, "Service worker:\nстан сесії клієнта,\nWebSocket-клієнт", fs=fs)
    box(ax, 2, 6, 30, 8, "Popup, сторінка\nналаштувань", fs=fs)
    arrow(ax, (17, 62), (17, 51), "зміни DOM", dx=1.5, dy=3.1, ls="--", fs=ls_, ha="left")
    arrow(ax, (17, 38), (17, 32), "сегменти", dx=1.5, dy=0, both=True, fs=ls_, ha="left")
    arrow(ax, (17, 14), (17, 21), "адженда", dx=1.5, dy=0, fs=ls_, ha="left")
    group(ax, 48, 3, 68, 54, "Сервер (FastAPI): окремий контекст на сесію")
    box(ax, 50, 21, 15, 11, "WebSocket-\nшлюз", fs=fs)
    box(ax, 70, 21, 19, 11, "Оркестратор\n(координатор)", fc=FILL, ec=ACCENT, bold=True, fs=fs)
    box(ax, 94, 42, 21, 8, "Аналізатор\nтранскрипту", fs=fs)
    box(ax, 94, 31, 21, 8, "Трекер\nадженди", fs=fs)
    box(ax, 94, 18, 21, 9, "Генератор\nпідказок (LLM)", fc=LLM, fs=fs)
    box(ax, 94, 6, 21, 9, "Агент\nпідсумку (LLM)", fc=LLM, fs=fs)
    box(ax, 69, 41, 20, 8, "Сховище стану\nсесії", fs=fs)
    box(ax, 67, 6, 22, 8, "Лічильник токенів\nі вартості", fs=fs)
    arrow(ax, (32, 26.5), (50, 26.5), "WebSocket", dy=1.8, both=True, fs=ls_)
    arrow(ax, (65, 26.5), (70, 26.5), both=True)
    arrow(ax, (89, 30), (94, 45)); arrow(ax, (89, 28.5), (94, 35)); arrow(ax, (89, 25), (94, 22.5))
    arrow(ax, (89, 23), (94, 11))
    arrow(ax, (79.5, 32), (79.5, 41), "дельта", dx=-1.5, dy=0, fs=ls_, ha="right")
    arrow(ax, (94, 19), (89, 12), "", ls=":")
    box(ax, 121, 12, 14, 12, "Anthropic\nMessages\nAPI", fc=LLM, fs=fs)
    arrow(ax, (115, 22), (121, 20), both=True); arrow(ax, (115, 11), (121, 16), both=True)
    save(fig, "fig-3-1-architecture.png")


def fig_3_2():
    fig, ax = canvas(9.2, 5.6, ymax=64)
    ax.add_patch(Rectangle((22, 2), 58, 60, fc="#fafafa", ec=GREY, lw=1.0))
    ax.text(51, 59.5, "Асистент супроводу зустрічі", ha="center", va="center", fontsize=9.5, style="italic")

    def actor(x, y, label):
        ax.add_patch(Ellipse((x, y + 7), 3, 3.6, fc="white", ec=INK, lw=1.2))
        ax.plot([x, x], [y + 5.2, y], color=INK, lw=1.2)
        ax.plot([x - 3, x + 3], [y + 3.5, y + 3.5], color=INK, lw=1.2)
        ax.plot([x, x - 2.5], [y, y - 4], color=INK, lw=1.2); ax.plot([x, x + 2.5], [y, y - 4], color=INK, lw=1.2)
        ax.text(x, y - 7, label, ha="center", va="center", fontsize=8.5)

    actor(9, 30, "Ведучий\nзустрічі")
    actor(92, 44, "Google Meet\n(субтитри)")
    actor(92, 16, "Служба\nLLM")
    left = [(54, "Задати адженду"), (46.5, "Запустити або зупинити запис"), (39, "Переглянути стан адженди"),
            (31.5, "Переглянути транскрипт"), (24, "Отримати підказку"), (16.5, "Відхилити підказку"),
            (9, "Отримати підсумок зустрічі"), ]
    for y, t in left:
        ax.add_patch(Ellipse((38, y), 27, 6.2, fc="white", ec=INK, lw=1.1))
        ax.text(38, y, t, ha="center", va="center", fontsize=8)
        ax.plot([12.5, 24.5], [32, y], color=INK, lw=0.9)
    right = [(46.5, "Отримати текст реплік"), (24, "Згенерувати підказку"), (9, "Сформувати звіт")]
    for y, t in right:
        ax.add_patch(Ellipse((67, y), 22, 6.2, fc="white", ec=INK, lw=1.1))
        ax.text(67, y, t, ha="center", va="center", fontsize=8)
        arrow(ax, (51.5, y), (56, y), "", ls="--")
    ax.text(53.7, 49.2, "«include»", ha="center", fontsize=7.2); ax.text(53.7, 26.7, "«include»", ha="center", fontsize=7.2)
    ax.text(53.7, 11.7, "«include»", ha="center", fontsize=7.2)
    ax.plot([78, 88.5], [46.5, 47], color=INK, lw=0.9)
    ax.plot([78, 88.5], [24, 20], color=INK, lw=0.9); ax.plot([78, 88.5], [9, 18], color=INK, lw=0.9)
    save(fig, "fig-3-2-usecase.png")


def fig_3_3():
    fig, ax = canvas(12.5, 7.0, xmax=153, ymax=88)
    names = ["Content\nscript", "Service\nworker", "WebSocket-\nшлюз", "Оркестратор", "Детерміновані\nагенти",
             "Генератор\nпідказок", "LLM API"]
    xs = [10, 32, 54, 76, 98, 120, 142]
    for x, n in zip(xs, names):
        box(ax, x - 9.5, 80, 19, 7, n, fs=9.5, fc=FILL if n == "Оркестратор" else "white")
        ax.plot([x, x], [80, 0.5], color=GREY, lw=0.9, ls="--")

    def msg(i, j, y, text, ls="-", side=1.4, fs=8.8):
        arrow(ax, (xs[i], y), (xs[j], y), text, dy=side, ls=ls, fs=fs)

    msg(0, 1, 74, "TRANSCRIPT_SEGMENT", fs=8)
    msg(1, 2, 70, "TRANSCRIPT")
    msg(2, 3, 66, "process_segment()")
    msg(3, 4, 62, "analyze(), track()")
    msg(4, 3, 58, "AgendaDelta", ls="--")
    ax.text(xs[3] + 2, 53.2, "застосувати дельту,\nперевірити час пункту", fontsize=8.5, ha="left", va="center",
            bbox=dict(fc="white", ec=GREY, lw=0.7, pad=3))
    msg(3, 2, 48, "результат", ls="--")
    msg(2, 1, 42.5, "NEW_TRANSCRIPT,\nAGENDA_UPDATE", side=2.4)
    msg(1, 0, 38, "оновлення оверлею")
    ax.add_patch(Rectangle((xs[3] - 10, 2), xs[6] - xs[3] + 20, 32, fc="none", ec=GREY, lw=0.9))
    ax.text(xs[3] - 9, 32.4, "opt  [умови запуску LLM виконано] — фонове завдання", fontsize=8.8, ha="left",
            va="center")
    msg(3, 5, 27.5, "generate(адженда, вікно)")
    msg(5, 6, 23.5, "messages.create")
    msg(6, 5, 19.5, "JSON-об’єкт", ls="--")
    msg(5, 3, 15.5, "підказки, пропозиція пункту", ls="--")
    msg(3, 2, 11.5, "hint sink")
    msg(2, 1, 7.5, "NEW_HINT")
    msg(1, 0, 3.5, "картка підказки")
    save(fig, "fig-3-3-sequence.png")


def fig_3_4():
    fig, ax = canvas(9.2, 4.8, ymax=54)
    group(ax, 1, 20, 42, 32, "Вкладка meet.google.com")
    box(ax, 3, 36, 16, 9, "Сторінка Meet\n(DOM, субтитри)", fs=8)
    box(ax, 25, 36, 16, 9, "Content script\n(ізольований світ)", fc=FILL, ec=ACCENT, fs=8)
    box(ax, 25, 23, 16, 8, "Оверлей\n(Shadow DOM)", fs=8)
    arrow(ax, (19, 40.5), (25, 40.5), both=True)
    arrow(ax, (33, 36), (33, 31))
    ax.plot([22, 22], [21, 49], color="#b03030", lw=1.2, ls=":")
    ax.text(12, 22.5, "межа довіри", color="#b03030", fontsize=8, ha="center", va="center")
    group(ax, 52, 20, 28, 32, "Контексти розширення")
    box(ax, 54, 36, 24, 9, "Service worker\n(стан сесії, WebSocket)", fc=FILL, ec=ACCENT, fs=8)
    box(ax, 54, 23, 11, 8, "Popup,\nOptions", fs=8)
    box(ax, 67, 23, 11, 8, "Offscreen\ndocument", fs=8, ls="--")
    arrow(ax, (41, 40.5), (54, 40.5), both=True)
    ax.text(47.5, 43.2, "runtime", ha="center", fontsize=7.5); ax.text(47.5, 37.8, "messaging", ha="center", fontsize=7.5)
    arrow(ax, (59.5, 31), (59.5, 36), both=True); arrow(ax, (72.5, 31), (72.5, 36), both=True, ls="--")
    box(ax, 88, 36, 11, 9, "Сервер\n(FastAPI)", fs=8)
    arrow(ax, (78, 40.5), (88, 40.5), both=True)
    ax.text(83, 43.2, "Web-", ha="center", fontsize=7.5); ax.text(83, 37.8, "Socket", ha="center", fontsize=7.5)
    box(ax, 54, 6, 24, 8, "chrome.storage.local\n(адженда, налаштування)", fs=8)
    arrow(ax, (66, 14), (66, 20), both=True)
    box(ax, 2, 6, 44, 8, "Дозволи: storage, activeTab, tabCapture, offscreen;\ncontent script лише для https://meet.google.com/*", fs=7.8, ec=GREY)
    box(ax, 84, 6, 15, 8, "Субтитри →\nMutationObserver", fs=7.8, ec=GREY)
    save(fig, "fig-3-4-integration.png")


def fig_4_0():
    fig, ax = canvas(9.2, 4.6, ymax=50)
    pos = {"pending": (12, 26), "active": (48, 26), "covered": (86, 40), "deferred": (86, 10), "skipped": (12, 6)}
    lab = {"pending": "pending\n(очікує)", "active": "active\n(обговорюється)", "covered": "covered\n(розглянуто)",
           "deferred": "deferred\n(відкладено)", "skipped": "skipped\n(пропущено)"}
    for k, (x, y) in pos.items():
        box(ax, x - 10, y - 4.5, 20, 9, lab[k], fc=FILL if k == "active" else "white", ec=ACCENT if k == "active" else INK,
            ls="--" if k == "skipped" else "-")
    arrow(ax, (22, 26), (38, 26))
    ax.text(30, 36, "згадка пункту (правило 2)\nабо пропозиція моделі\nз упевненістю ≥ 0,7", ha="center", va="center", fontsize=8)
    arrow(ax, (58, 29), (76, 39))
    ax.text(62, 40, "активовано інший пункт,\nє ≥ 1 доказ", ha="center", va="center", fontsize=8)
    arrow(ax, (58, 23.5), (76, 12.5))
    ax.text(72, 21.5, "активовано інший,\nдоказів немає", ha="center", va="center", fontsize=8)
    ax.add_patch(FancyArrowPatch((76, 8), (50, 21.5), arrowstyle="-|>", mutation_scale=11, lw=1.1, color=INK,
                                 connectionstyle="arc3,rad=-0.25"))
    ax.text(55, 8, "повернення до пункту", ha="center", va="center", fontsize=8)
    arrow(ax, (12, 21.5), (12, 10.5), ls="--")
    ax.text(14, 16, "дозволено моделлю станів;\nавтоматично не виконується", ha="left", va="center", fontsize=7.8)
    save(fig, "fig-4-0-states.png")


def fig_4_1():
    fig, ax = canvas(7.6, 9.4, xmax=80, ymax=100)
    cx = 30
    box(ax, cx - 13, 94, 26, 5, "Сегмент транскрипту", fc=FILL, ec=ACCENT)
    diamond(ax, cx, 86, 24, 7, "is_final?")
    box(ax, 55, 83.5, 22, 5, "Лише показати в UI", fs=8.5)
    box(ax, cx - 15, 74, 30, 5.5, "Нормалізація тексту,\nперевірка довжини (≥ 3 слів)", fs=8.5)
    box(ax, cx - 15, 65, 30, 5.5, "Пошук фрази переходу\nта згадок пунктів адженди", fs=8.5)
    box(ax, cx - 15, 56, 30, 5.5, "Додати сегмент до доказів\nзгаданих пунктів", fs=8.5)
    diamond(ax, cx, 47, 44, 10.5, "Є згадка пункту і (фраза\nпереходу, або немає активного,\nабо мова про інший пункт)?", fs=7.4)
    box(ax, 55, 41.5, 24.5, 11, "Попередній активний →\ncovered (є докази) або\ndeferred; згаданий → active", fs=7.8)
    box(ax, cx - 15, 32, 30, 5, "Оновити час активного пункту", fs=8.5)
    diamond(ax, cx, 23, 30, 8, "час > 1,5 · T\nі минуло 300 с?", fs=8)
    box(ax, 55, 20.5, 22, 5, "Підказка time_warning", fs=8.5)
    box(ax, cx - 15, 9, 30, 5.5, "Застосувати дельту до стану;\nперевірити умови запуску LLM", fs=8.5)
    box(ax, cx - 13, 1, 26, 4.5, "AGENDA_UPDATE клієнту", fc=FILL, ec=ACCENT, fs=8.5)
    arrow(ax, (cx, 94), (cx, 89.5))
    arrow(ax, (cx + 12, 86), (55, 86), "ні", dy=1.2)
    arrow(ax, (cx, 82.5), (cx, 79.5), "так", dx=2.5, dy=0)
    arrow(ax, (cx, 74), (cx, 70.5)); arrow(ax, (cx, 65), (cx, 61.5)); arrow(ax, (cx, 56), (cx, 52.2))
    arrow(ax, (cx + 22, 47), (55, 47), "", dy=1.2); ax.text(53.4, 48.6, "так", fontsize=8.5, ha="center")
    arrow(ax, (cx, 41.8), (cx, 37), "ні", dx=2.5, dy=0)
    ax.plot([67, 67], [41.5, 34.5], color=INK, lw=1.1); arrow(ax, (67, 34.5), (cx + 15, 34.5))
    arrow(ax, (cx, 32), (cx, 27))
    arrow(ax, (cx + 15, 23), (55, 23), "так", dy=1.2)
    arrow(ax, (cx, 19), (cx, 14.5), "ні", dx=2.5, dy=0)
    ax.plot([66, 66], [20.5, 11.5], color=INK, lw=1.1); arrow(ax, (66, 11.5), (cx + 15, 11.5))
    arrow(ax, (cx, 9), (cx, 5.5))
    save(fig, "fig-4-1-flow.png")


def fig_4_2():
    fig, ax = canvas(7.6, 8.4, xmax=80, ymax=90)
    cx = 28
    box(ax, cx - 14, 84, 28, 5, "Новий фінальний сегмент\nу черзі очікування", fc=FILL, ec=ACCENT, fs=8.5)
    checks = [(75, "Виклик уже\nвиконується?", "call_in_flight"), (63, "Досягнуто ліміту\nвикликів (200)?", "call_cap_reached"),
              (51, "Досягнуто ліміту\nвартості (0,05 $)?", "cost_cap_reached"), (39, "Минуло менше 45 с\nвід останнього?", "min_interval"),
              (27, "Нових слів\nменше 50?", "too_few_new_words")]
    prev = 84
    for y, text, reason in checks:
        diamond(ax, cx, y, 30, 8.6, text, fs=8)
        arrow(ax, (cx, prev), (cx, y + 4.3), "ні" if prev != 84 else "", dx=2.5, dy=0)
        arrow(ax, (cx + 15, y), (52, y), "так", dy=1.2)
        box(ax, 52, y - 2.5, 26, 5, f"пропуск: {reason}", fs=8)
        prev = y - 4.3
    arrow(ax, (cx, prev), (cx, 16), "ні", dx=2.5, dy=0)
    box(ax, cx - 16, 9, 32, 7, "Зафіксувати вікно (8 реплік),\nзапустити фоновий виклик,\nочистити чергу", fc=LLM, fs=8.5)
    box(ax, 48, 6, 31, 9, "Таймер паузи: через 20 с тиші\nповторити перевірку з порогом\n12 слів (ліміти ті самі)", fs=8, ls="--")
    ax.plot([78.5, 79.5, 79.5], [27, 27, 15], color=GREY, lw=1.0, ls="--")
    ax.plot([78.5, 79.5], [39, 39], color=GREY, lw=1.0, ls="--"); ax.plot([79.5, 79.5], [39, 27], color=GREY, lw=1.0, ls="--")
    arrow(ax, (48, 10.5), (44, 12), "", ls="--", color=GREY)
    box(ax, cx - 16, 0.5, 32, 5, "Підказки → перевірка → NEW_HINT", fs=8.5)
    arrow(ax, (cx, 9), (cx, 5.5))
    save(fig, "fig-4-2-gate.png")


def fig_5_1():
    fig, ax = canvas(9.2, 4.2, ymax=46)
    f = 7.4
    box(ax, 0.5, 34, 20, 8, "Адженда: псевдоніми\na1…aN, статуси, час", fs=f)
    box(ax, 0.5, 22, 20, 8, "Вікно: до 8 реплік s1…s8,\nкожна ≤ 300 символів", fs=f)
    box(ax, 0.5, 10, 20, 8, "Нещодавно показані\nпідказки (тип, пункт)", fs=f)
    box(ax, 24.5, 17, 17, 18, "Запит:\nsystem — правила;\nuser — дані та блок\n<transcript>", fc=FILL, ec=ACCENT, fs=f)
    for y in (38, 26, 14):
        arrow(ax, (20.5, y), (24.5, 26 + (y - 26) * 0.4))
    box(ax, 45.5, 18, 15.5, 16, "Модель\nclaude-haiku-5-5,\nбез міркувань,\n≤ 250 токенів", fc=LLM, fs=f)
    arrow(ax, (41.5, 26), (45.5, 26))
    box(ax, 65, 17, 17.5, 18, "Розбір JSON:\nтип із 5 значень,\nпсевдонім пункту,\n≥ 1 доказ, ≤ 2 підказки;\nпропозиція пункту", fs=f)
    arrow(ax, (61, 26), (65, 26))
    box(ax, 86.5, 18, 13, 16, "Повтори\n(120 с) →\nNEW_HINT;\nпункт → трекер", fs=f)
    arrow(ax, (82.5, 26), (86.5, 26))
    box(ax, 65, 2, 17.5, 8, "Відкинуто:\nзапис у журнал", fs=f, ec=GREY)
    arrow(ax, (73.7, 17), (73.7, 10), ls="--", color=GREY)
    box(ax, 44.5, 2, 17.5, 8, "Помилка, таймаут 10 с\n→ вимикач", fs=f, ec=GREY)
    arrow(ax, (53.2, 18), (53.2, 10), ls="--", color=GREY)
    box(ax, 24.5, 2, 17, 8, "Лічильник токенів\nі вартості сесії", fs=f, ec=GREY)
    arrow(ax, (46, 18.5), (41.5, 9.5), ls=":", color=GREY)
    save(fig, "fig-5-1-llm-exchange.png")


def fig_5_2():
    fig, ax = canvas(9.0, 3.3, ymax=36)
    box(ax, 1, 14, 25, 9, "Замкнено\n(виклики дозволено)", fc=FILL, ec=ACCENT, fs=8.2)
    box(ax, 37.5, 14, 25, 9, "Розімкнено\n(виклики відхиляються)", fs=8.2)
    box(ax, 74, 14, 25, 9, "Напіввідкрито\n(один пробний виклик)", fs=8.2)
    arrow(ax, (26, 18.5), (37.5, 18.5), "3 помилки", dy=1.5, fs=7.5)
    ax.text(31.7, 16.6, "поспіль", ha="center", fontsize=7.5)
    arrow(ax, (62.5, 18.5), (74, 18.5), "минуло", dy=1.5, fs=7.5)
    ax.text(68.2, 16.6, "60 с", ha="center", fontsize=7.5)
    ax.add_patch(FancyArrowPatch((86, 14), (50, 14), arrowstyle="-|>", mutation_scale=11, lw=1.1, color=INK,
                                 connectionstyle="arc3,rad=-0.35"))
    ax.text(68, 6.0, "пробний виклик невдалий", ha="center", fontsize=8)
    ax.add_patch(FancyArrowPatch((86, 23), (13.5, 23), arrowstyle="-|>", mutation_scale=11, lw=1.1, color=INK,
                                 connectionstyle="arc3,rad=0.28"))
    ax.text(50, 34.2, "пробний виклик успішний", ha="center", fontsize=8)
    save(fig, "fig-5-2-breaker.png")


if __name__ == "__main__":
    for f in (fig_3_1, fig_3_2, fig_3_3, fig_3_4, fig_4_0, fig_4_1, fig_4_2, fig_5_1, fig_5_2):
        f()
    print(sorted(p.name for p in OUT.glob("fig-[345]-*.png")))
