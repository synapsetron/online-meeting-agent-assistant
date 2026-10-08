"""Tests for the offline cost replay harness (WP3). No network, no sleeping."""
from __future__ import annotations

import dataclasses
import re
import socket
import time
import uuid

import pytest

from server.agents import hint_generator as hint_generator_module
from server.agents import orchestrator as orchestrator_module
from server.config import Config
from server.core.cost import PRICES_USD_PER_MTOK
from server.eval import cost_replay
from server.eval.cost_replay import (
    LLMCallRecord,
    build_profiles,
    gating_delays,
    run_matrix,
    run_replay,
)
from server.eval.scenarios import (
    DRIFT_AND_RETURN,
    GAP_PATTERN_S,
    LONG_MEETING,
    NORMAL_FLOW,
    SCENARIOS,
    SKIPPED_ITEM,
)
from server.eval.token_estimate import (
    CALIBRATION,
    estimate_request_input_tokens,
    estimate_text_tokens,
)

PROFILES = {p.key: p for p in build_profiles()}


def _with_config(profile_key: str, **overrides: object) -> cost_replay.Profile:
    profile = PROFILES[profile_key]
    return dataclasses.replace(profile, config=dataclasses.replace(profile.config, **overrides))


# --- scenarios ---------------------------------------------------------------


def test_scenarios_are_synthetic_and_realistically_paced() -> None:
    assert 4 <= len(SCENARIOS) <= 5
    assert LONG_MEETING.duration_s >= 28 * 60
    for scenario in SCENARIOS:
        previous = 0.0
        for index, segment in enumerate(scenario.segments):
            assert 5 <= len(segment.text.split()) <= 25, segment.text
            gap = segment.t_seconds - previous - scenario.pauses.get(index, 0.0)
            assert min(GAP_PATTERN_S) <= gap <= max(GAP_PATTERN_S)
            previous = segment.t_seconds
            assert str(uuid.UUID(segment.id)) == segment.id
        assert len({s.id for s in scenario.segments}) == len(scenario.segments)
        for item in scenario.agenda:
            assert re.fullmatch(r"item-\d{13}-[a-z0-9]{4}", item.id)
        words_per_segment = scenario.total_words / len(scenario.segments)
        assert 8 <= words_per_segment <= 14


# --- token estimator ---------------------------------------------------------


def test_token_estimate_is_monotonic_in_text_length() -> None:
    text = (
        "Перейдемо до плану релізу, item-1791006808101-scy4: що з бюджетом?\n"
        "[0b7e6f52-3c1d-4a8e-9f27-5d1c0a94e6b3] Reply with only a JSON array."
    )
    estimates = [estimate_text_tokens(text[:n]) for n in range(len(text) + 1)]
    assert estimates[0] == 0
    assert estimates == sorted(estimates)
    assert estimates[-1] > 0
    assert estimate_text_tokens(text * 2) > estimate_text_tokens(text)


def test_token_estimate_charges_cyrillic_and_ids_more_than_english() -> None:
    assert estimate_text_tokens("обговорення") > estimate_text_tokens("discussions")
    assert estimate_text_tokens("0b7e6f52-3c1d-4a8e-9f27-5d1c0a94e6b3") > estimate_text_tokens(
        "a" * 36
    )


def test_token_estimate_is_calibrated_against_the_one_real_measurement() -> None:
    assert (CALIBRATION.segments, CALIBRATION.words, CALIBRATION.agenda_items) == (4, 52, 2)
    assert CALIBRATION.measured_input_tokens == 742
    assert abs(CALIBRATION.relative_error) <= 0.05


def test_request_estimate_reads_system_and_all_messages() -> None:
    base = {"system": "Rules.", "messages": [{"role": "user", "content": "Привіт"}]}
    more = {
        "system": [{"type": "text", "text": "Rules."}],
        "messages": [
            {"role": "user", "content": "Привіт"},
            {"role": "user", "content": [{"type": "text", "text": "ще текст"}]},
        ],
    }
    assert estimate_request_input_tokens(more) > estimate_request_input_tokens(base) > 0


# --- replay ------------------------------------------------------------------


def test_replay_is_reproducible() -> None:
    first = run_replay(DRIFT_AND_RETURN, PROFILES["K2"])
    second = run_replay(DRIFT_AND_RETURN, PROFILES["K2"])
    assert first == second
    assert first.calls == second.calls
    assert first.llm_calls > 0


def test_replay_uses_simulated_time_and_restores_the_clock() -> None:
    started = time.perf_counter()
    result = run_replay(LONG_MEETING, PROFILES["K4"])
    assert time.perf_counter() - started < 1.0  # ~30 simulated minutes
    assert result.duration_s >= 28 * 60
    assert orchestrator_module.time is time
    assert hint_generator_module.time is time


def test_gating_makes_strictly_fewer_calls_on_the_long_scenario() -> None:
    k1 = run_replay(LONG_MEETING, PROFILES["K1"])
    k2 = run_replay(LONG_MEETING, PROFILES["K2"])
    assert k1.hint_calls == k1.final_segments  # a call after every final segment
    assert k2.hint_calls < k1.hint_calls
    assert k2.llm_calls < k1.llm_calls
    assert k2.est_cost_usd < k1.est_cost_usd
    assert k1.gating_delay_max_s == 0
    assert k2.gating_delay_max_s is not None and k2.gating_delay_max_s > 0


def test_call_cap_is_respected() -> None:
    capped = run_replay(NORMAL_FLOW, _with_config("K1", llm_max_calls_per_session=3, summary_interval=10**9))
    assert capped.hint_calls == 3
    assert capped.summary_calls == 0
    assert capped.segments_never_sent > 0


def test_cost_cap_is_respected() -> None:
    cap = 0.01
    profile = _with_config("K0", llm_max_session_cost_usd=cap, summary_interval=10**9)
    capped = run_replay(NORMAL_FLOW, profile, "high")
    uncapped = run_replay(NORMAL_FLOW, _with_config("K0", summary_interval=10**9), "high")
    assert 0 < capped.hint_calls < uncapped.hint_calls
    price_in, price_out = PRICES_USD_PER_MTOK[profile.config.anthropic_model]
    last = capped.calls[-1]
    last_cost = (last.est_input_tokens * price_in + last.est_output_tokens * price_out) / 1e6
    # No call starts once the estimated spend has reached the cap.
    assert capped.est_cost_usd - last_cost < cap <= capped.est_cost_usd


def test_usage_meter_agrees_with_recorded_fake_calls() -> None:
    result = run_replay(SKIPPED_ITEM, PROFILES["K0"], "high")
    assert result.summary_calls > 0
    assert result.usage_meter_calls == result.llm_calls == len(result.calls)
    assert result.usage_meter_cost_usd == pytest.approx(result.est_cost_usd)
    assert all(c.est_output_tokens == c.max_tokens for c in result.calls)  # "high" = max_tokens
    assert all(c.model == "claude-sonnet-5-5" for c in result.calls)


def test_model_change_alone_scales_cost_by_the_price_ratio() -> None:
    k0 = run_replay(SKIPPED_ITEM, PROFILES["K0"])
    k1 = run_replay(SKIPPED_ITEM, PROFILES["K1"])
    assert (k0.llm_calls, k0.est_input_tokens, k0.est_output_tokens) == (
        k1.llm_calls, k1.est_input_tokens, k1.est_output_tokens,
    )
    assert k1.est_cost_usd < k0.est_cost_usd


def test_no_network_and_no_real_anthropic_call(monkeypatch: pytest.MonkeyPatch) -> None:
    forbidden: list[str] = []

    def deny(name: str):
        def _deny(*args: object, **kwargs: object) -> None:
            forbidden.append(name)
            raise AssertionError(f"{name} must not be used by the offline replay")
        return _deny

    monkeypatch.setattr(socket.socket, "connect", deny("socket.connect"))
    monkeypatch.setattr(socket, "create_connection", deny("socket.create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", deny("socket.getaddrinfo"))
    try:
        from anthropic.resources.messages import AsyncMessages
    except ImportError:  # anthropic not installed: nothing real to call
        AsyncMessages = None  # type: ignore[assignment,misc]
    if AsyncMessages is not None:
        monkeypatch.setattr(AsyncMessages, "create", deny("anthropic.AsyncMessages.create"))

    result = run_replay(NORMAL_FLOW, PROFILES["K4"])

    assert forbidden == []
    assert result.hint_calls > 0
    assert result.usage_meter_calls == len(result.calls)  # every call went to the fake


def test_canned_drift_hint_exercises_the_hint_path() -> None:
    result = run_replay(DRIFT_AND_RETURN, PROFILES["K1"])
    canned = sum(1 for call in result.calls if call.canned_hint)
    assert canned > 0
    assert 1 <= result.hints_accepted <= canned


def test_idle_flush_runs_in_simulated_time_when_the_orchestrator_has_one() -> None:
    if not hasattr(Config(anthropic_api_key="offline"), "llm_flush_idle_seconds"):
        pytest.skip("orchestrator without idle flush")
    result = run_replay(DRIFT_AND_RETURN, PROFILES["K3"])
    arrivals = {segment.t_seconds for segment in DRIFT_AND_RETURN.segments}
    flushed = [c for c in result.calls if c.kind == "hint" and c.sim_time_s not in arrivals]
    assert flushed, "expected a call fired by the idle-flush timer during the scripted pause"
    assert all(c.sim_time_s <= DRIFT_AND_RETURN.duration_s for c in result.calls)


def test_gating_delays_window_arithmetic() -> None:
    def call(t: float, finals: int) -> LLMCallRecord:
        return LLMCallRecord("hint", t, finals, "m", 10, 1, 1)

    scenario = dataclasses.replace(NORMAL_FLOW, segments=NORMAL_FLOW.segments[:6])
    times = [s.t_seconds for s in scenario.segments]
    # One call right after segment 4 (window 3 -> segments 2..4), one 5 s after segment 6.
    delays, never = gating_delays(scenario, [call(times[3], 4), call(times[5] + 5, 6)], window=3)
    assert never == 1  # segment 1 slid out of the window
    assert delays == [
        times[3] - times[1], times[3] - times[2], 0.0,
        times[5] + 5 - times[4], 5.0,
    ]
    assert gating_delays(scenario, [], window=3) == ([], 6)


def test_matrix_and_markdown_label_everything_as_estimates() -> None:
    report = run_matrix(scenarios=[SKIPPED_ITEM])
    assert [a.profile_key for a in report.aggregates] == ["K0", "K1", "K2", "K3", "K4"]
    k0, k4 = report.aggregate("K0"), report.aggregate("K4")
    assert k0.cost_ratio_vs_k0 == (1.0, 1.0)
    assert k0.est_cost_usd[0] <= k0.est_cost_usd[1]
    assert k4.est_cost_usd[1] < k0.est_cost_usd[0]
    markdown = cost_replay.render_markdown(report, "test-command")
    assert "оцінка" in markdown and "Обмеження" in markdown
    assert "test-command" in markdown
    assert "підтверджено" not in markdown.replace("не підтверджено", "")
