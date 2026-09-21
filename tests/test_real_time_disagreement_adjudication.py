"""Source/replay evidence for the 2026-09-21 final disagreement labels."""

import hashlib
import json
import math
from pathlib import Path

import pytest

from weird_captcha_gym.shared_scripts.incubator_generators import (
    cursor_lens_reveal as palimpsest,
    elastic_membrane_sorter as membrane,
    reverse_identity_gate as handshake,
    temporal_memory_first_change as first_change,
)
from weird_captcha_gym.shared_runtime.server.incubator_graders import (
    dead_mans_switch as pressure_grader,
    elastic_membrane_sorter as membrane_grader,
    reverse_identity_gate as handshake_grader,
    temporal_memory_first_change as first_change_grader,
    wrong_number as number_grader,
)
from weird_captcha_gym.shared_runtime.server.slot_reel_witness import _frame_at


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
AUDIT = BENCH / "real_time_audits/historical_50_final_adjudication_2026-09-21"


def controls(mechanic):
    return json.loads((BENCH / f"environments/{mechanic}_env/controls.json").read_text())


def task(mechanic, level, mode):
    return {
        "id": f"{mechanic}_seed_0001@0.1",
        "_control_condition": {
            "difficulty": level,
            "interaction": mode,
            "difficulty_parameters": controls(mechanic)["difficulty"][str(level)]["parameters"],
        },
    }


def test_final_labels_cover_exactly_the_48_disagreements():
    data = json.loads((AUDIT / "final_labels.json").read_text())
    combined = json.loads((ROOT / data["comparison"]["path"]).read_text())
    games = {game["game_case_index"]: game for game in combined["games"]}
    key = lambda row: (row["game"], row["difficulty"], row["interaction"])
    expected = {key(row): row for row in combined["label_disagreements"]}
    actual = {key(row): row for row in data["decisions"]}
    assert len(data["decisions"]) == len(actual) == len(expected) == 48
    assert set(actual) == set(expected)
    for identity, row in actual.items():
        old = expected[identity]
        game = games[row["game"]]
        assert row["environment_id"] == game["environment_id"]
        assert row["public_name"] == game["public_name"]
        assert row["configuration_index"] == game["configuration_indices_by_difficulty"][row["interaction"]][row["difficulty"] - 1]
        assert row["historical_label"] == old["old"]
        assert row["reviewer_label"] == old["new"]
        assert row["final_label"] in {"yes", "no"}
        assert row["rationale_id"] in data["rationales"]
        assert row["final_label"] == data["rationales"][row["rationale_id"]]["label"]
        assert row["agrees_with_reviewer"] == (row["final_label"] == row["reviewer_label"])
    assert sum(row["final_label"] == "yes" for row in actual.values()) == 5
    assert sum(row["final_label"] != row["reviewer_label"] for row in actual.values()) == 7
    assert sum(row["final_label"] != row["historical_label"] for row in actual.values()) == 41
    assert data["counts"] == {
        "configurations": 48, "environments": 10,
        "final_labels": {"yes": 5, "no": 43},
        "agree_with_reviewer": 41, "reject_reviewer": 7,
        "changes_from_historical": 41,
    }
    for artifact in [data["comparison"], data["definition"], *data["reports"], *data["source_files"]]:
        assert hashlib.sha256((ROOT / artifact["path"]).read_bytes()).hexdigest() == artifact["sha256"]


def test_palimpsest_l2_entire_motion_envelope_fits_fixed_center():
    p = controls("cursor_lens_reveal")["difficulty"]["2"]["parameters"]
    assert math.hypot(p["motion_radius_x_max"], p["motion_radius_y_max"]) + .02 < p["lock_radius"]
    for seed in range(20):
        state, _ = palimpsest.generate(task("cursor_lens_reveal", 2, "full"), str(seed))
        assert len(state["nodes"]) == 1
        node = state["nodes"][0]
        assert node["base"] == [128, 122]
        for t in range(0, 180001, 137):
            assert math.dist(node["base"], palimpsest._position(node, t)) < p["lock_radius"]


def test_pressure_l1_center_is_safe_for_every_phase_and_amplitude():
    p = controls("dead_mans_switch")["difficulty"]["1"]["parameters"]
    bound = (p["x_amplitude_milli_max"] / p["hit_x_milli"]) ** 2 + (p["y_amplitude_milli_max"] / p["hit_y_milli"]) ** 2
    assert bound < 1
    motion = {
        "x_amplitude_milli": p["x_amplitude_milli_max"],
        "y_amplitude_milli": p["y_amplitude_milli_max"],
        "hit_x_milli": p["hit_x_milli"],
        "hit_y_milli": p["hit_y_milli"],
        "period_ms": 4800,
    }
    for phase in range(0, 6284, 97):
        motion["phase_milliradians"] = phase
        assert all(pressure_grader._pressure_contains((.5, .5), t, motion) for t in range(0, 9600, 71))


@pytest.mark.parametrize("level", [3, 4, 5])
def test_palimpsest_capture_can_expire_before_automatic_tracking_starts(level):
    p = controls("cursor_lens_reveal")["difficulty"][str(level)]["parameters"]
    delta = 200
    maximum_speed = math.tau / p["motion_period_ms_min"] * math.hypot(p["motion_radius_x_max"], 1.14 * p["motion_radius_y_max"])
    # Any echo capturable after this delay is already inside the current lens.
    assert maximum_speed * delta + p["lock_radius"] < p["lens_radius"]
    state, _ = palimpsest.generate(task("cursor_lens_reveal", level, "simplified"), "capture-expiry")
    node = state["nodes"][0]
    early = palimpsest._position(node, 2000)
    late = palimpsest._position(node, 2100)
    distance = math.dist(early, late)
    assert distance > .25
    lens = [early[i] - (late[i] - early[i]) / distance * (p["lock_radius"] - .25) for i in range(2)]
    assert math.dist(lens, early) < p["lock_radius"]
    assert p["lock_radius"] < math.dist(lens, late) < p["lens_radius"]
    # The current center, still reachable by the coordinate control, succeeds.
    assert math.dist(late, late) <= p["lock_radius"]
    # Unlike L2, the generated support includes paths with no always-safe point.
    extreme = {"base": [128, 122], "motion": {"radius_x": p["motion_radius_x_max"], "radius_y": p["motion_radius_y_max"], "period_ms": p["motion_period_ms_min"], "phase": 0., "ratio": .68}}
    half_cycle = 12.5 * p["motion_period_ms_min"]
    diameter = max(math.dist(palimpsest._position(extreme, t), palimpsest._position(extreme, t + half_cycle)) for t in range(0, int(half_cycle), 100))
    assert diameter > 2 * p["lock_radius"]


@pytest.mark.parametrize("level", [1, 2])
@pytest.mark.parametrize("mode", ["full", "simplified"])
@pytest.mark.parametrize("well", [0, 1])
def test_membrane_fixed_pre_run_tension_passes_two_of_three_courses(level, mode, well):
    for seed in range(100):
        state, truth = membrane.generate(task("elastic_membrane_sorter", level, mode), str(seed))
        if state["rounds"][0]["target_well"] == well:
            break
    else:
        raise AssertionError("generated lateral course not found")
    current = state["rounds"][0]
    p = state["physics"]
    heights = [.08, .68, .32, .92] if well == 0 else [.68, .08, .92, .32]
    source = "membrane_post_drag" if mode == "full" else "tension_slider"
    events = []

    def emit(kind, tick, **values):
        events.append({"seq": len(events) + 1, "type": kind, "tick": tick, "round_id": current["id"], **values})

    for index, value in enumerate(heights):
        emit("post", 0, post=index, before=current["post_heights"][index], after=value, input_source=source)
    emit("release", 0, heights=heights)
    ball = {"x": 450., "y": 230., "vx": 0., "vy": 0.}
    ax, ay = membrane_grader._force(heights, p["slope_accel"])
    checkpoint = 0
    for tick in range(1, p["max_ticks"] + 1):
        ball["vx"] = (ball["vx"] + ax) * p["drag"]
        ball["vy"] = (ball["vy"] + ay) * p["drag"]
        ball["x"] += ball["vx"]
        ball["y"] += ball["vy"]
        assert 28 <= ball["x"] <= 872 and 28 <= ball["y"] <= 452
        point = [ball["x"], ball["y"]]
        if checkpoint < len(current["checkpoints"]) and math.dist(point, current["checkpoints"][checkpoint]) <= p["checkpoint_radius"]:
            emit("checkpoint", tick, index=checkpoint, ball=dict(ball))
            checkpoint += 1
        speed = math.hypot(ball["vx"], ball["vy"])
        if checkpoint == len(current["checkpoints"]) and math.dist(point, current["wells"][well]) < p["well_radius"] and speed <= p["capture_speed"]:
            emit("capture", tick, well=well, checkpoints=checkpoint, ball=dict(ball), speed=speed)
            break
    assert events[-1]["type"] == "capture"
    payload = {k: state[k] for k in ("mechanic_id", "task_id", "challenge_id")}
    payload.update(events=events, completed=True)
    assert membrane_grader.grade(payload, truth, state)["passed"]
    assert all(event["tick"] == 0 for event in events if event["type"] in {"post", "release"})


@pytest.mark.parametrize("level", [1, 2, 3])
def test_wrong_number_can_leave_tuning_fixed_through_whole_trial(level):
    p = controls("wrong_number")["difficulty"][str(level)]["parameters"]
    for drift in p["drift_milli_values"]:
        line = {"phase_offset_steps": 0, "skew_offset_steps": 0, "distortion_milli": 0, "drift_milli_steps_per_second": drift}
        phase = 0 if level < 3 else (-1 if drift > 0 else 1) % p["phase_steps"]
        # Include the next sampling interval beyond the declared trial length.
        samples = [number_grader._alignment(line, phase, 0, t, p)[1] for t in range(0, p["trial_ms"] + p["sample_ms"] + 1, 10)]
        assert all(samples)


@pytest.mark.parametrize("level", range(1, 6))
def test_first_change_full_accepts_all_required_evidence_in_frozen_review(level):
    state, truth = first_change.generate(task("temporal_memory_first_change", level, "full"), "review-only")
    timeline = truth["timeline"]
    target = truth["target_object_id"]
    item = next(item for item in timeline["objects"] if item["id"] == target)
    first = min(timeline["events"], key=lambda event: event["at_ms"])
    events = [{"sequence": 1, "kind": "arm"}]
    for hits, when in [(timeline["proof"]["minimum_pre_hits"], first["at_ms"] - 80), (timeline["proof"]["minimum_change_hits"], first["at_ms"] + 80)]:
        # The slider advances in 40-ms increments and may remain stationary.
        at_ms = round(when / 40) * 40
        for _ in range(hits):
            events.append({"sequence": len(events) + 1, "kind": "observe", "mode": "review", "timeline_ms": at_ms, "cursor": list(first_change_grader._moving_position(item, at_ms)), "input_source": "canvas_pointer"})
    events.append({"sequence": len(events) + 1, "kind": "return_settled"})
    events.append({"sequence": len(events) + 1, "kind": "select", "selected_object_id": target, "point": list(first_change_grader._settled_position(timeline, target)), "input_source": "canvas_pointer"})
    payload = {k: state[k] for k in ("mechanic_id", "task_id", "challenge_id")}
    payload.update(events=events, interaction_mode="full", selected_object_id=target)
    assert first_change_grader.grade(payload, truth, state)["passed"]


@pytest.mark.parametrize("mode", ["full", "simplified"])
def test_handshake_l1_constant_drive_and_contact_replay_all_initial_offsets(mode):
    for offset in range(360):
        for direction in (-1, 1):
            state, truth = handshake.generate(task("reverse_identity_gate", 1, mode), str(offset))
            # Every offset and either direction is in the authored L1 support.
            stage = truth["stages"][0]
            stage.update(pulse_start_deg=0, receiver_initial_deg=offset, pulse_speed_deg_per_tick=direction)
            state["stages"] = truth["stages"]
            station = stage["station"]
            events = []

            def emit(kind, **values):
                events.append({"seq": len(events) + 1, "type": kind, **values})

            emit("deploy", station=station, deployed_count=1)
            emit("key", stage=0, station=station, before=0, after=direction, input_source="keyboard" if mode == "full" else "direction_button")
            emit("contact", stage=0, station=station, before=False, after=True, input_source="pointer_hold" if mode == "full" else "contact_toggle")
            pulse, receiver, charge = 0, offset, 0
            for tick in range(1, 61):
                pulse = (pulse + direction) % 360
                receiver = (receiver + direction * 8) % 360
                error = abs((receiver - pulse + 180) % 360 - 180)
                locked = error <= 30
                if locked:
                    receiver, error, charge = pulse, 0, charge + 1
                else:
                    charge = max(0, charge - 1)
                emit("tick", stage=0, station=station, tick=tick, state={"pulse_deg": pulse, "receiver_deg": receiver, "error_deg": error, "charge": charge, "locked": locked, "direction": direction, "contact": True})
                if charge == 8:
                    emit("relay", stage=0, station=station, tick=tick, charge=charge, next_station=None)
                    break
            assert charge == 8
            emit("verify", completed_stages=1, deployed=[station])
            payload = {k: state[k] for k in ("mechanic_id", "task_id", "challenge_id")}
            payload.update(events=events, completed=True)
            assert handshake_grader.grade(payload, truth, state)["passed"]


def test_slot_l5_thirty_ms_prediction_never_requires_an_unseen_next_symbol():
    p = controls("slot_reel_capture")["difficulty"]["5"]["parameters"]
    ratio = p["capture_window_ratio"]
    delta = 30
    assert delta < (1 - ratio) / 2 * min(p["interval_ms_values"])
    for interval in p["interval_ms_values"]:
        reel = {"target": "K", "tokens": ["◆", "K", "●", "✦", "♢", "▰", "✶", "✹", "⬟"], "interval_ms": interval, "phase": 0}
        for t in range(9 * interval):
            token, _ = _frame_at(reel, t, ratio)
            future_token, ready = _frame_at(reel, t + delta, ratio)
            if future_token == "K" and ready:
                assert token == "K"
        # The configured 160-ms spacing identifies all four possible speeds
        # from displacement modulo the 92-px wrap, without memorizing tokens.
        rates = {round((160 / speed) % 1, 8) for speed in p["interval_ms_values"]}
        assert len(rates) == len(p["interval_ms_values"])
        expiry = interval * (1 + (1 + ratio) / 2)
        assert _frame_at(reel, expiry - 10, ratio) == ("K", True)
        assert _frame_at(reel, expiry + 10, ratio) == ("K", False)


def test_clutch_l2_cannot_recover_by_an_extra_revolution_inside_tick_budget():
    p = controls("clockwork_clutch_safe")["difficulty"]["2"]["parameters"]
    first_possible_final_release = p["release_tick_ranges"][1][0]
    work_per_tick = p["drive_deg_per_tick"] * p["load_numerator"]
    # The ratio bank has minimum magnitude 1 and maximum magnitude 1.5.
    extra_turn_work = 360 / 1.5
    maximum_tolerance_work = 2 * p["phase_tolerance_deg"] / 1
    earliest_extra_turn = first_possible_final_release + (extra_turn_work - maximum_tolerance_work) / work_per_tick
    assert earliest_extra_turn > p["max_ticks"]
