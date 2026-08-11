from __future__ import annotations

import json

from weird_captcha_gym.tools.env_step_action_trace import (
    compact_agent_actions,
    parse_input_trace,
)
from weird_captcha_gym.tools.verify_randomized_env_step_matrix import (
    _bound_local_registration_displacement,
    _filter_registration_displacement_outliers,
    _live_timeline_batches,
    _paused_timeline_buckets,
    summarize,
)


def _group(actions: list[dict]) -> list[dict]:
    return [{"index": 0, "actions": actions}]


def test_registration_rejects_repeated_control_grid_jumps() -> None:
    stable = [
        (float(index), float(index * 2), float(index % 3), 24.0 + float(index % 4))
        for index in range(20)
    ]
    wrong_column = (1818.0, 313.0, -133.0, 75.0)
    wrong_row = (1818.0, 313.0, 0.0, 75.0)

    filtered, displacement = _filter_registration_displacement_outliers(
        [*stable, wrong_column, wrong_row]
    )

    assert filtered == stable
    assert abs(displacement["median_dx"] - 1.0) <= 1.0
    assert 24.0 <= displacement["median_dy"] <= 27.0


def test_registration_bounds_a_local_repeated_feature_jump() -> None:
    assert _bound_local_registration_displacement(12.0, 1.0) == 12.0
    assert _bound_local_registration_displacement(31.0, 1.0) == 1.0


def test_compacts_pointer_events_to_public_click_and_drag_actions() -> None:
    groups, diagnostics = compact_agent_actions(_group([
        {"mouse": {"move": [10, 20]}},
        {"mouse": {"buttons": {"left_down": True}}},
        {"mouse": {"buttons": {"left_up": True}}},
        {"mouse": {"move": [30, 40]}},
        {"mouse": {"buttons": {"left_down": True}}},
        {"mouse": {"move": [50, 60]}},
        {"mouse": {"buttons": {"left_up": True}}},
    ]))

    assert groups[0]["actions"] == [
        {"mouse": {"left_click": [10, 20]}},
        {"mouse": {"left_click_drag": [[30, 40], [50, 60]]}},
    ]
    assert diagnostics == {
        "actions_before_compaction": 7,
        "actions_after_compaction": 2,
        "actions_eliminated": 5,
    }


def test_compacts_a_stepped_straight_drag_but_preserves_a_curved_path() -> None:
    straight = [
        {"mouse": {"move": [10, 20]}},
        {"mouse": {"buttons": {"left_down": True}}},
        {"mouse": {"move": [30, 40]}},
        {"mouse": {"move": [50, 60]}},
        {"mouse": {"buttons": {"left_up": True}}},
    ]
    curved = [
        {"mouse": {"move": [10, 20]}},
        {"mouse": {"buttons": {"left_down": True}}},
        {"mouse": {"move": [30, 5]}},
        {"mouse": {"move": [50, 20]}},
        {"mouse": {"buttons": {"left_up": True}}},
    ]

    compacted_straight, _diagnostics = compact_agent_actions(_group(straight))
    compacted_curved, _diagnostics = compact_agent_actions(_group(curved))

    assert compacted_straight[0]["actions"] == [
        {"mouse": {"left_click_drag": [[10, 20], [50, 60]]}},
    ]
    assert compacted_curved[0]["actions"] == curved


def test_compacts_printable_text_and_key_combinations() -> None:
    groups, _diagnostics = compact_agent_actions(_group([
        {"keyboard": {"keys_down": [":"]}},
        {"action": "wait", "time": 0.02},
        {"keyboard": {"keys_up": [":"]}},
        {"keyboard": {"keys_down": ["b"]}},
        {"keyboard": {"keys_up": ["b"]}},
        {"keyboard": {"keys_down": ["n"]}},
        {"keyboard": {"keys_up": ["n"]}},
        {"keyboard": {"keys_down": ["enter"]}},
        {"keyboard": {"keys_up": ["enter"]}},
        {"keyboard": {"keys_down": ["ctrl"]}},
        {"keyboard": {"keys_down": ["c"]}},
        {"keyboard": {"keys_up": ["c"]}},
        {"keyboard": {"keys_up": ["ctrl"]}},
    ]))

    assert groups[0]["actions"] == [
        {"keyboard": {"text": ":bn"}},
        {"keyboard": {"keys": ["enter"]}},
        {"keyboard": {"keys": ["ctrl", "c"]}},
    ]


def test_space_is_a_standard_key_action_not_text_insertion() -> None:
    groups = parse_input_trace([
        {"sequence": 1, "type": "keydown", "time_ms": 1000, "key": " ", "trusted": True},
        {"sequence": 2, "type": "keyup", "time_ms": 1010, "key": " ", "trusted": True},
        {"sequence": 3, "type": "keydown", "time_ms": 1300, "key": " ", "trusted": True},
        {"sequence": 4, "type": "keyup", "time_ms": 1550, "key": " ", "trusted": True},
    ])
    compacted, _diagnostics = compact_agent_actions(groups)
    actions = [action for group in compacted for action in group["actions"]]

    assert actions == [
        {"keyboard": {"keys": ["space"]}},
        {"keyboard": {"keys_down": ["space"]}},
        {"keyboard": {"keys_up": ["space"]}},
    ]


def test_preserves_a_long_held_pointer_gesture() -> None:
    actions = [
        {"mouse": {"move": [10, 20]}},
        {"mouse": {"buttons": {"left_down": True}}},
        {"action": "wait", "time": 0.25},
        {"mouse": {"move": [30, 40]}},
        {"mouse": {"buttons": {"left_up": True}}},
    ]

    groups, _diagnostics = compact_agent_actions(_group(actions))

    assert groups[0]["actions"] == actions


def test_preserves_a_single_tick_pointer_hold() -> None:
    actions = [
        {"mouse": {"move": [10, 20]}},
        {"mouse": {"buttons": {"left_down": True}}},
        {"action": "wait", "time": 0.04},
        {"mouse": {"buttons": {"left_up": True}}},
    ]

    groups, _diagnostics = compact_agent_actions(_group(actions))

    assert groups[0]["actions"] == actions


def test_compaction_preserves_semantic_action_timestamps_without_private_action_keys() -> None:
    groups, _diagnostics = compact_agent_actions(_group([
        {"mouse": {"move": [10, 20]}, "_trace_time_ms": 0.0},
        {"mouse": {"buttons": {"left_down": True}}, "_trace_time_ms": 4.0},
        {"action": "wait", "time": 0.04, "_trace_time_ms": 4.0},
        {"mouse": {"buttons": {"left_up": True}}, "_trace_time_ms": 44.0},
        {"keyboard": {"keys_down": ["x"]}, "_trace_time_ms": 80.0},
        {"keyboard": {"keys_up": ["x"]}, "_trace_time_ms": 86.0},
    ]))

    assert groups[0]["actions"] == [
        {"mouse": {"move": [10, 20]}},
        {"mouse": {"buttons": {"left_down": True}}},
        {"mouse": {"buttons": {"left_up": True}}},
        {"keyboard": {"text": "x"}},
    ]
    assert groups[0]["action_at_ms"] == [0.0, 4.0, 44.0, 86.0]
    assert all("_trace_time_ms" not in action for action in groups[0]["actions"])


def test_parse_replays_locator_auto_scroll_as_public_wheel_input() -> None:
    target = {
        "target_tag": "button",
        "target_id": "submit",
        "target_type": "button",
        "target_rect": [100, 900, 200, 50],
        "viewport_scroll_x": 0,
        "viewport_scroll_y": 64,
        "frame_index": 0,
        "trusted": True,
    }
    raw_events = [
        {**target, "sequence": 1, "type": "pointermove", "time_ms": 1000, "x": 200, "y": 925},
        {**target, "sequence": 2, "type": "pointerdown", "time_ms": 1004, "x": 200, "y": 925, "button": 0},
        {**target, "sequence": 3, "type": "pointerup", "time_ms": 1010, "x": 200, "y": 925, "button": 0},
    ]

    groups = parse_input_trace(raw_events)
    compacted, _diagnostics = compact_agent_actions(groups)
    actions = [action for group in compacted for action in group["actions"]]

    assert {"mouse": {"scroll": 1}} in actions
    assert {"mouse": {"left_click": [200, 925]}} in actions
    assert all("_trace_time_ms" not in action for action in actions)


def test_parse_preserves_browser_wheel_sign_for_gym_contract() -> None:
    groups = parse_input_trace([
        {
            "sequence": 1,
            "type": "wheel",
            "time_ms": 1000,
            "x": 500,
            "y": 500,
            "delta_y": 200,
            "trusted": True,
        },
        {
            "sequence": 2,
            "type": "wheel",
            "time_ms": 1200,
            "x": 500,
            "y": 500,
            "delta_y": -100,
            "trusted": True,
        },
    ])
    compacted, _diagnostics = compact_agent_actions(groups)
    actions = [action for group in compacted for action in group["actions"]]

    assert {"mouse": {"scroll": 2}} in actions
    assert {"mouse": {"scroll": -1}} in actions


def test_implicit_scroll_state_is_isolated_per_browser_page() -> None:
    groups = parse_input_trace([
        {
            "sequence": 1,
            "type": "pointermove",
            "time_ms": 1000,
            "page_index": 0,
            "frame_index": 0,
            "viewport_scroll_y": 100,
            "x": 10,
            "y": 20,
            "trusted": True,
        },
        {
            "sequence": 2,
            "type": "pointermove",
            "time_ms": 1200,
            "page_index": 1,
            "frame_index": 0,
            "viewport_scroll_y": 0,
            "x": 30,
            "y": 40,
            "trusted": True,
        },
    ])
    compacted, _diagnostics = compact_agent_actions(groups)
    scrolls = [
        action["mouse"]["scroll"]
        for group in compacted
        for action in group["actions"]
        if "scroll" in action.get("mouse", {})
    ]

    assert scrolls == [1]


def test_tab_focus_marker_becomes_public_browser_shortcut() -> None:
    groups = parse_input_trace([
        {
            "sequence": 1,
            "type": "tabfocus",
            "time_ms": 125.0,
            "tab_index": 2,
            "page_index": 2,
        },
    ])

    assert groups == [{
        "at_ms": 0.0,
        "end_ms": 0.0,
        "actions": [{
            "keyboard": {"keys": ["ctrl", "3"]},
            "_trace_time_ms": 0.0,
            "_trace_page_index": 2,
        }],
        "sources": ["browser_tab_focus"],
        "index": 0,
        "delay_before_ms": 0.0,
    }]


def test_paused_timeline_uses_only_fixed_observation_windows() -> None:
    actions = [
        {"mouse": {"left_click": [10, 20]}},
        {"keyboard": {"keys_down": ["shift"]}},
        {"mouse": {"left_click": [30, 40]}},
        {"keyboard": {"keys_up": ["shift"]}},
    ]
    groups = [{
        "actions": actions,
        "action_at_ms": [100.0, 490.0, 510.0, 1_100.0],
    }]

    assert _paused_timeline_buckets(
        groups,
        observation_window_ms=500,
        trailing_delay_ms=400,
    ) == [
        actions[:2],
        actions[2:3],
        actions[3:],
    ]
    assert _paused_timeline_buckets(
        groups,
        observation_window_ms=0,
        trailing_delay_ms=10_000,
    ) == [actions]


def test_paused_timeline_keeps_semantic_groups_on_separate_agent_turns() -> None:
    first = {"mouse": {"left_click": [10, 20]}}
    second = {"mouse": {"left_click": [30, 40]}}
    groups = [
        {"actions": [first], "action_at_ms": [100.0]},
        {"actions": [second], "action_at_ms": [200.0]},
    ]

    assert _paused_timeline_buckets(
        groups,
        observation_window_ms=500,
        trailing_delay_ms=0,
    ) == [[first], [second]]
    assert _paused_timeline_buckets(
        groups,
        observation_window_ms=0,
        trailing_delay_ms=0,
    ) == [[first], [second]]


def test_live_timeline_batches_subtract_action_execution_from_cadence() -> None:
    groups = [{
        "actions": [
            {"keyboard": {"keys_down": ["right"]}},
            {"keyboard": {"keys_down": ["space"]}},
            {"keyboard": {"keys_up": ["space"]}},
        ],
        "action_at_ms": [100.0, 350.0, 450.0],
    }, {
        "actions": [{"keyboard": {"keys_up": ["right"]}}],
        "action_at_ms": [1_000.0],
    }]

    batches = _live_timeline_batches(
        groups,
        initial_action_delay_ms=50,
        estimated_action_execution_ms=12,
    )

    assert batches == [{
        "target_start_ms": 150.0,
        "target_end_ms": 500.0,
        "actions": [
            {"keyboard": {"keys_down": ["right"]}},
            {"action": "wait", "time": 0.238},
            {"keyboard": {"keys_down": ["space"]}},
            {"action": "wait", "time": 0.088},
            {"keyboard": {"keys_up": ["space"]}},
        ],
        "semantic_action_count": 3,
        "estimated_action_execution_ms": 12,
    }, {
        "target_start_ms": 1_050.0,
        "target_end_ms": 1_050.0,
        "actions": [
            {"keyboard": {"keys_up": ["right"]}},
        ],
        "semantic_action_count": 1,
        "estimated_action_execution_ms": 12,
    }]


def test_live_timeline_batches_recover_uncompacted_trace_timestamps() -> None:
    groups = [{
        "at_ms": 100.0,
        "actions": [
            {"mouse": {"move": [10, 20]}, "_trace_time_ms": 100.0},
            {"mouse": {"buttons": {"left_down": True}}, "_trace_time_ms": 120.0},
            {"mouse": {"move": [20, 30]}, "_trace_time_ms": 170.0},
            {"mouse": {"buttons": {"left_up": True}}, "_trace_time_ms": 200.0},
        ],
    }]

    assert _live_timeline_batches(
        groups,
        initial_action_delay_ms=0,
        estimated_action_execution_ms=12,
    ) == [{
        "target_start_ms": 100.0,
        "target_end_ms": 200.0,
        "actions": [
            {"mouse": {"move": [10, 20]}},
            {"action": "wait", "time": .008},
            {"mouse": {"buttons": {"left_down": True}}},
            {"action": "wait", "time": .038},
            {"mouse": {"move": [20, 30]}},
            {"action": "wait", "time": .018},
            {"mouse": {"buttons": {"left_up": True}}},
        ],
        "semantic_action_count": 4,
        "estimated_action_execution_ms": 12,
    }]

def test_summary_can_be_limited_to_one_result_campaign(tmp_path) -> None:
    manifest = {
        "matrix_seed": 7,
        "entries": [{"index": index, "mechanic": f"m{index}"} for index in range(75)],
    }
    (tmp_path / "verify-shard-old-00.json").write_text(
        json.dumps({"records": [{
            "index": 0,
            "mechanic": "m0",
            "status": "verifier_failed",
        }]}),
        encoding="utf-8",
    )
    (tmp_path / "verify-shard-final-v1-00.json").write_text(
        json.dumps({"records": [{
            "index": 0,
            "mechanic": "m0",
            "status": "passed",
        }]}),
        encoding="utf-8",
    )

    assert summarize(manifest, tmp_path, result_prefix="final-") == 1
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["records"][0]["status"] == "passed"
    assert summary["result_prefix"] == "final-"
    assert len(summary["result_files"]) == 1


def test_summary_preserves_an_exact_accepted_pass_after_a_failed_rerun(tmp_path) -> None:
    manifest = {
        "matrix_seed": 7,
        "entries": [{"index": index, "mechanic": f"m{index}"} for index in range(75)],
    }
    (tmp_path / "verify-shard-01-pass.json").write_text(json.dumps({"records": [{
        "index": 0,
        "mechanic": "m0",
        "status": "passed",
        "same_oracle_world": True,
        "action_api": "GymAnythingEnv.step only",
    }]}), encoding="utf-8")
    (tmp_path / "verify-shard-02-failure.json").write_text(json.dumps({"records": [{
        "index": 0,
        "mechanic": "m0",
        "status": "verifier_failed",
        "same_oracle_world": True,
        "action_api": "GymAnythingEnv.step only",
    }]}), encoding="utf-8")

    assert summarize(manifest, tmp_path) == 1
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["accepted_pass_count"] == 1
    assert summary["records"][0]["status"] == "passed"
    assert summary["attempt_status_counts"] == {"passed": 1, "verifier_failed": 1}


def test_summary_rejects_a_pass_from_a_different_time_condition(tmp_path) -> None:
    manifest = {
        "matrix_seed": 7,
        "entries": [
            {
                "index": index,
                "mechanic": f"m{index}",
                "difficulty": 3,
                "interaction": "full",
                "time_mode": "paused",
                "challenge_seed": 1000 + index,
            }
            for index in range(75)
        ],
    }
    (tmp_path / "verify-shard-live-pass.json").write_text(
        json.dumps({"records": [{
            "index": 0,
            "mechanic": "m0",
            "difficulty": 3,
            "interaction": "full",
            "time_mode": "live",
            "challenge_seed": 1000,
            "status": "passed",
            "same_oracle_world": True,
            "action_api": "GymAnythingEnv.step only",
        }]}),
        encoding="utf-8",
    )

    assert summarize(manifest, tmp_path) == 1
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["accepted_pass_count"] == 0
    assert summary["records"][0]["status"] == "missing"
    assert summary["attempt_status_counts"] == {}
    assert summary["ignored_condition_mismatch_count"] == 1
