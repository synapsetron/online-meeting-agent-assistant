"""Офлайн-експерименти для розділу 7 (без жодного звернення до LLM API).

Запуск із кореня репозиторію:
    server/.venv/bin/python docs/practice-report/analysis/eval_offline.py

Що вимірюється насправді (на синтетичних сценаріях server/eval/scenarios.py):
  E1  точність детермінованого шару (аналізатор + трекер) щодо еталонних міток,
      які випливають із побудови сценаріїв;
  E2  те саме на ускладнених варіантах (без явної фрази відкриття пункту);
  E3  стійкість до імітованих помилок розпізнавання (випадкові заміни/пропуски/вставки слів);
  E4  час детермінованої обробки одного фінального сегмента на цій машині;
  E5  параметри обмеження викликів LLM: кількість викликів і затримка гейтингу
      (симульований час, заглушка замість моделі; вартість — ОЦІНКА);
  E6  зведення пілотних викликів реальної моделі з logs/backend.jsonl (якщо файл є).
Якість підказок LLM, WER і наскрізна затримка тут НЕ вимірюються.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import platform
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from server.agents.orchestrator import Orchestrator  # noqa: E402
from server.config import Config  # noqa: E402
from server.core.state_store import MeetingStateStore  # noqa: E402
from server.eval import cost_replay as cr  # noqa: E402
from server.eval import scenarios as sc  # noqa: E402
from server.models import AgendaItem, HintType, TranscriptSegment  # noqa: E402

logging.disable(logging.CRITICAL)

POOL_TITLE = {
    sc._SPRINT: "Статус спринту",
    sc._BLOCKERS: "Блокери розробки",
    sc._RELEASE: "План релізу",
    sc._BUDGET: "Бюджет тестування",
}
TOLERANCE = 2  # сегментів: перехід вважається виявленим, якщо зафіксований не пізніше


def _core(text: str) -> str:
    return text[1:45]


_CORE_TO_TITLE = {_core(u): title for pool, title in POOL_TITLE.items() for u in pool}


def truth_labels(scenario: sc.Scenario) -> list[str | None]:
    """Еталонний активний пункт після кожного сегмента. Під час відхилення від
    теми активним лишається попередній пункт (його ніхто не закривав)."""
    title_to_id = {a.title: a.id for a in scenario.agenda}
    labels: list[str | None] = []
    current: str | None = None
    for seg in scenario.segments:
        if not seg.off_agenda:
            for core, title in _CORE_TO_TITLE.items():
                if core in seg.text:
                    current = title_to_id[title]
                    break
        labels.append(current)
    return labels


def implicit_variant(scenario: sc.Scenario) -> sc.Scenario:
    """Ускладнений варіант: з кожного блоку прибрано першу репліку, яка називає
    пункт і містить фразу переходу («тиха» зміна теми)."""
    openers = {pool[0] for pool in POOL_TITLE}
    kept, labels = [], truth_labels(scenario)
    for seg in scenario.segments:
        if seg.text not in openers:
            kept.append(seg)
    return dataclasses.replace(scenario, key=scenario.key + "_implicit", segments=tuple(kept))


PARAPHRASE = (
    ("Статус спринту", (
        "Почнімо з того, що команда встигла зробити за останні два тижні.",
        "Із п'ятнадцяти запланованих задач дванадцять уже закрито.",
        "Ще три в роботі, дві з них майже готові до перевірки.",
        "Темп трохи впав, бо двоє людей були на навчанні.",
        "Загалом ітерація йде за графіком, відставань я не бачу.",
    )),
    ("Блокери розробки", (
        "Тепер про те, що нам зараз заважає рухатися вперед.",
        "Тестове середовище падає щодня, і ми втрачаємо на цьому години.",
        "Доступу до нової бази даних досі немає, заявку не погодили.",
        "У мене стоїть робота, бо немає макетів екрана налаштувань.",
        "Я подивлюся конфігурацію контейнерів одразу після зустрічі.",
    )),
    ("План релізу", (
        "Гаразд, а коли ми реально зможемо випустити наступну версію?",
        "За графіком це наступна середа, але є ризики.",
        "Код треба заморозити в п'ятницю ввечері, далі лише виправлення помилок.",
        "Сповіщення я б відклав до наступного випуску, вони ще сирі.",
        "Хто напише інструкцію з розгортання і сценарій відкату?",
    )),
    ("Бюджет тестування", (
        "Залишилося питання грошей на перевірку якості в наступному кварталі.",
        "Зараз закладено години лише на ручну перевірку.",
        "Пропоную частину коштів перенести на автоматизацію регресії.",
        "Ліцензія на інструмент коштує як два дні роботи одного фахівця на місяць.",
        "Резерв у десять відсотків виглядає розумним, більше нам не погодять.",
    )),
)


def paraphrase_scenario() -> tuple[sc.Scenario, list[str | None]]:
    """Ручний сценарій: пункти обговорюються без слів із їхніх назв (перефразування)."""
    agenda = sc._agenda(*sc._FULL_AGENDA)
    ids = {a.title: a.id for a in agenda}
    segments, truth, t = [], [], 0.0
    for title, lines in PARAPHRASE:
        for line in lines:
            t += 8.0
            segments.append(sc.SegmentSpec(id=f"para-{len(segments)}", t_seconds=t, speaker="Учасник", text=line))
            truth.append(ids[title])
    scenario = sc.Scenario(key="paraphrase", title="Перефразування", description="", agenda=agenda,
                           segments=tuple(segments))
    return scenario, truth


def add_noise(text: str, rate: float, rng: random.Random, vocab: list[str]) -> str:
    out: list[str] = []
    for word in text.split():
        if rng.random() < rate:
            kind = rng.random()
            if kind < 0.60:
                out.append(rng.choice(vocab))  # заміна
            elif kind < 0.85:
                continue  # пропуск
            else:
                out.extend([word, rng.choice(vocab)])  # вставка
        else:
            out.append(word)
    return " ".join(out) or text


async def run_deterministic(scenario: sc.Scenario, texts: list[str] | None = None) -> dict:
    # Ліміт 0 викликів: LLM не запускається, працює лише детермінований шар.
    config = Config(anthropic_api_key="offline", llm_max_calls_per_session=0, llm_flush_idle_seconds=0)
    orch = Orchestrator(config)
    state = MeetingStateStore(
        meeting_id=f"eval-{scenario.key}",
        agenda_items=[
            AgendaItem(id=a.id, title=a.title, estimated_minutes=a.estimated_minutes, order=i)
            for i, a in enumerate(scenario.agenda)
        ],
        window_size=config.transcript_window_size,
    )
    predicted: list[str | None] = []
    durations_ms: list[float] = []
    warnings: list[tuple[int, float, str]] = []
    for i, seg in enumerate(scenario.segments):
        segment = TranscriptSegment(
            id=seg.id, meeting_id=state.meeting.id, speaker_id=seg.speaker,
            text=texts[i] if texts else seg.text, timestamp=seg.t_seconds, is_final=True,
        )
        started = time.perf_counter()
        result = await orch.process_segment(segment, state)
        durations_ms.append((time.perf_counter() - started) * 1000)
        predicted.append(state.agenda.active_item_id)
        for hint in result.time_warnings:
            if hint.type == HintType.TIME_WARNING:
                warnings.append((i, seg.t_seconds, hint.agenda_item_id))
    statuses = {item.id: item.status.value for item in state.agenda.items}
    evidence = {item.id: len(item.evidence) for item in state.agenda.items}
    await orch.aclose()
    return {"predicted": predicted, "durations_ms": durations_ms, "warnings": warnings,
            "statuses": statuses, "evidence": evidence}


def transitions(labels: list[str | None]) -> list[tuple[int, str]]:
    out, prev = [], None
    for i, lab in enumerate(labels):
        if lab is not None and lab != prev:
            out.append((i, lab))
        prev = lab if lab is not None else prev
    return out


def score(truth: list[str | None], predicted: list[str | None]) -> dict:
    n = len(truth)
    correct = sum(1 for t, p in zip(truth, predicted) if t == p)
    gt, pr = transitions(truth), transitions(predicted)
    used: set[int] = set()
    tp, delays = 0, []
    for gi, gid in gt:
        for k, (pi, pid) in enumerate(pr):
            if k not in used and pid == gid and 0 <= pi - gi <= TOLERANCE:
                used.add(k); tp += 1; delays.append(pi - gi)
                break
    fp, fn = len(pr) - tp, len(gt) - tp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"segments": n, "segment_accuracy": correct / n, "gt_transitions": len(gt),
            "pred_transitions": len(pr), "tp": tp, "fp": fp, "fn": fn,
            "precision": precision, "recall": recall, "f1": f1,
            "mean_delay_segments": statistics.mean(delays) if delays else None}


def expected_statuses(scenario: sc.Scenario, truth: list[str | None]) -> dict[str, str]:
    order = [gid for _, gid in transitions(truth)]
    exp = {a.id: "pending" for a in scenario.agenda}
    for gid in order:
        exp[gid] = "covered"
    if order:
        exp[order[-1]] = "active"
    return exp


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def e1_e2_e4() -> tuple[list[dict], dict]:
    rows, all_durations = [], []
    for base in sc.SCENARIOS:
        for scenario in (base, implicit_variant(base)):
            truth = truth_labels(scenario)
            run = asyncio.run(run_deterministic(scenario))
            row = {"scenario": scenario.key, "variant": "implicit" if scenario is not base else "explicit",
                   **score(truth, run["predicted"])}
            exp = expected_statuses(scenario, truth)
            row["status_correct"] = sum(1 for k in exp if exp[k] == run["statuses"][k])
            row["status_total"] = len(exp)
            row["status_detail"] = {"expected": list(exp.values()), "got": [run["statuses"][k] for k in exp]}
            row["time_warnings"] = len(run["warnings"])
            if run["warnings"]:
                idx, t, item_id = run["warnings"][0]
                spec = next(a for a in scenario.agenda if a.id == item_id)
                start_t = next(s.t_seconds for s, lab in zip(scenario.segments, run["predicted"]) if lab == item_id)
                row["first_warning_s_after_limit"] = round(t - start_t - spec.estimated_minutes * 60 * 1.5, 1)
            row["off_agenda_segments"] = sum(1 for s in scenario.segments if s.off_agenda)
            rows.append(row)
            if scenario is base:
                all_durations.extend(run["durations_ms"])
    scenario, truth = paraphrase_scenario()
    run = asyncio.run(run_deterministic(scenario))
    row = {"scenario": scenario.key, "variant": "paraphrase", **score(truth, run["predicted"])}
    exp = expected_statuses(scenario, truth)
    row["status_correct"] = sum(1 for k in exp if exp[k] == run["statuses"][k])
    row["status_total"] = len(exp)
    row["status_detail"] = {"expected": list(exp.values()), "got": [run["statuses"][k] for k in exp]}
    row["time_warnings"] = len(run["warnings"]); row["off_agenda_segments"] = 0
    row["predicted_titles"] = [next((a.title for a in scenario.agenda if a.id == p), None) for p in run["predicted"]]
    rows.append(row)
    # повторні прогони для стабільнішої оцінки часу
    for _ in range(4):
        for base in sc.SCENARIOS:
            all_durations.extend(asyncio.run(run_deterministic(base))["durations_ms"])
    timing = {"n": len(all_durations), "p50_ms": percentile(all_durations, 0.5),
              "p95_ms": percentile(all_durations, 0.95), "p99_ms": percentile(all_durations, 0.99),
              "max_ms": max(all_durations), "mean_ms": statistics.mean(all_durations),
              "hist": all_durations}
    return rows, timing


def e3(rates=(0.0, 0.05, 0.10, 0.20, 0.30, 0.40), repeats: int = 20) -> list[dict]:
    vocab = sorted({w for s in sc.SCENARIOS for seg in s.segments for w in seg.text.split()})
    out = []
    for rate in rates:
        accs, f1s, recalls, precisions = [], [], [], []
        for rep in range(repeats if rate else 1):
            rng = random.Random(1000 * rep + int(rate * 100))
            tot_n = tot_ok = tp = fp = fn = 0
            for scenario in sc.SCENARIOS:
                truth = truth_labels(scenario)
                texts = [add_noise(s.text, rate, rng, vocab) for s in scenario.segments]
                s = score(truth, asyncio.run(run_deterministic(scenario, texts))["predicted"])
                tot_n += s["segments"]; tot_ok += round(s["segment_accuracy"] * s["segments"])
                tp += s["tp"]; fp += s["fp"]; fn += s["fn"]
            p = tp / (tp + fp) if tp + fp else 0.0
            r = tp / (tp + fn) if tp + fn else 0.0
            accs.append(tot_ok / tot_n); precisions.append(p); recalls.append(r)
            f1s.append(2 * p * r / (p + r) if p + r else 0.0)
        def ms(v):
            return {"mean": statistics.mean(v), "sd": statistics.pstdev(v) if len(v) > 1 else 0.0,
                    "min": min(v), "max": max(v)}
        out.append({"rate": rate, "repeats": len(accs), "segment_accuracy": ms(accs),
                    "precision": ms(precisions), "recall": ms(recalls), "f1": ms(f1s)})
    return out


def e5() -> dict:
    profiles = {p.key: p for p in cr.build_profiles()}
    k4 = profiles["K4"]
    by_profile = []
    for p in profiles.values():
        calls = dur = 0
        lo = hi = 0.0
        delays_med, delays_max, never = [], [], 0
        for scenario in sc.SCENARIOS:
            a = cr.run_replay(scenario, p, "low")
            b = cr.run_replay(scenario, p, "high")
            calls += a.llm_calls; dur += a.duration_s
            lo += a.est_cost_usd; hi += b.est_cost_usd
            delays_med.append(a.gating_delay_median_s or 0.0)
            delays_max.append(a.gating_delay_max_s or 0.0)
            never += a.segments_never_sent
        by_profile.append({"key": p.key, "label": p.label, "calls": calls,
                           "calls_per_hour": calls / dur * 3600,
                           "cost_per_hour_low": lo / dur * 3600, "cost_per_hour_high": hi / dur * 3600,
                           "gating_delay_median_s": statistics.median(delays_med),
                           "gating_delay_max_s": max(delays_max), "segments_never_sent": never})
    sweep = []
    for interval in (0, 10, 20, 30, 45, 60, 90, 120):
        for words in (0, 25, 50, 100):
            cfg = dataclasses.replace(k4.config, llm_debounce_seconds=float(interval), llm_min_new_words=words)
            prof = dataclasses.replace(k4, key=f"S{interval}-{words}", config=cfg)
            calls = dur = 0
            lo = hi = 0.0
            all_delays: list[float] = []
            never = 0
            for scenario in sc.SCENARIOS:
                a = cr.run_replay(scenario, prof, "low")
                b = cr.run_replay(scenario, prof, "high")
                d, nv = cr.gating_delays(scenario, [c for c in a.calls if getattr(c, "kind", "hint") == "hint"],
                                         cfg.transcript_window_size)
                all_delays.extend(d); never += nv
                calls += a.hint_calls; dur += a.duration_s
                lo += a.est_cost_usd; hi += b.est_cost_usd
            sweep.append({"interval_s": interval, "min_words": words, "hint_calls": calls,
                          "calls_per_hour": calls / dur * 3600,
                          "cost_per_hour_low": lo / dur * 3600, "cost_per_hour_high": hi / dur * 3600,
                          "delay_median_s": statistics.median(all_delays) if all_delays else None,
                          "delay_p95_s": percentile(all_delays, 0.95) if all_delays else None,
                          "delay_max_s": max(all_delays) if all_delays else None,
                          "segments_never_sent": never})
    return {"profiles": by_profile, "sweep": sweep}


def e6() -> dict | None:
    path = ROOT / "logs" / "backend.jsonl"
    if not path.exists():
        return None
    calls, seg_ms, sessions = [], [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = event.get("event")
        if name == "llm_call":
            calls.append({k: event.get(k) for k in ("kind", "model", "segments", "input_tokens",
                                                     "output_tokens", "latency_ms", "hints_accepted", "stop_reason")})
        elif name == "segment_processed" and event.get("final"):
            seg_ms.append(event.get("duration_ms"))
        elif name == "session_closed":
            sessions.append({k: event.get(k) for k in ("duration_s", "llm_calls", "input_tokens",
                                                        "output_tokens", "est_cost_usd", "hints_total")})
    return {"llm_calls": calls, "segment_duration_ms": seg_ms, "sessions": sessions}


def main() -> None:
    rows, timing = e1_e2_e4()
    result = {
        "date": time.strftime("%Y-%m-%d"),
        "machine": {"cpu": platform.processor() or platform.machine(), "python": platform.python_version(),
                    "system": f"{platform.system()} {platform.release()}"},
        "tolerance_segments": TOLERANCE,
        "accuracy": rows,
        "timing": timing,
        "noise": e3(),
        "gating": e5(),
        "pilot": e6(),
    }
    out = Path(__file__).with_name("eval_offline_result.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    brief = {k: v for k, v in result.items() if k not in ("timing", "pilot", "gating")}
    brief["timing"] = {k: v for k, v in timing.items() if k != "hist"}
    print(json.dumps(rows[-1], ensure_ascii=False))
    print(json.dumps(brief["timing"]))
    print(json.dumps([(n["rate"], round(n["segment_accuracy"]["mean"], 3), round(n["f1"]["mean"], 3)) for n in result["noise"]]))
    print(json.dumps(result["gating"], ensure_ascii=False))


if __name__ == "__main__":
    main()
