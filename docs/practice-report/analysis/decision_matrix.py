"""Зважена матриця вибору джерела даних зустрічі (розділ 2.5 звіту).

Оцінки 1..5 — експертні судження автора, обґрунтовані в тексті звіту; це НЕ
виміряні величини. Скрипт лише детерміновано рахує зважені суми та виконує
аналіз чутливості до ваг (Dirichlet-вибірка, фіксований seed).
"""
from __future__ import annotations

import json
import random

CRITERIA = {
    "access": 0.25,       # доступ до живих даних під час зустрічі
    "latency": 0.20,      # очікувана затримка до тексту
    "accuracy": 0.15,     # якість/покриття мови uk (за документацією, не виміряно)
    "permissions": 0.15,  # дозволи, згода, приватність
    "complexity": 0.10,   # складність інтеграції (5 = просто)
    "repro": 0.15,        # відтворюваність (доступність для будь-кого, стабільність)
}

ALTERNATIVES = {
    "A  Meet REST API (артефакти після зустрічі)": [1, 1, 3, 3, 3, 4],
    "B  Meet Media API (WebRTC)":                  [5, 5, 3, 1, 1, 1],
    "C  Meet Add-ons SDK":                         [2, 3, 3, 2, 3, 3],
    "D  Розширення + мікрофон + Web Speech":       [3, 4, 3, 4, 5, 3],
    "E  Розширення + субтитри Meet (DOM)":         [4, 4, 3, 4, 3, 2],
    "F  Розширення + tabCapture + серверний ASR":  [4, 3, 3, 3, 2, 3],
    "G  Гібрид D+E (обране рішення)":              [4, 4, 3, 4, 3, 3],
}

keys = list(CRITERIA)
w = [CRITERIA[k] for k in keys]
assert abs(sum(w) - 1) < 1e-9


def score(vals, weights):
    return sum(v * x for v, x in zip(vals, weights))


base = {n: round(score(v, w), 2) for n, v in ALTERNATIVES.items()}

random.seed(42)
N = 20000
wins = {n: 0 for n in ALTERNATIVES}
top2 = {n: 0 for n in ALTERNATIVES}
for _ in range(N):
    g = [random.gammavariate(1, 1) for _ in keys]
    s = sum(g)
    ww = [x / s for x in g]
    ranked = sorted(ALTERNATIVES, key=lambda n: -score(ALTERNATIVES[n], ww))
    wins[ranked[0]] += 1
    for n in ranked[:2]:
        top2[n] += 1

# однокритеріальне збурення: ±50 % ваги одного критерію з перенормуванням
perturb = {}
for i, k in enumerate(keys):
    for f in (0.5, 1.5):
        ww = w[:]
        ww[i] *= f
        t = sum(ww)
        ww = [x / t for x in ww]
        best = max(ALTERNATIVES, key=lambda n: score(ALTERNATIVES[n], ww))
        perturb[f"{k} x{f}"] = best[:1]

out = {
    "weights": CRITERIA,
    "scores": ALTERNATIVES,
    "weighted": base,
    "mc_samples": N,
    "mc_best_share": {n: round(c / N, 3) for n, c in wins.items()},
    "mc_top2_share": {n: round(c / N, 3) for n, c in top2.items()},
    "perturb_best": perturb,
}
print(json.dumps(out, ensure_ascii=False, indent=2))
