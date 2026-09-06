from __future__ import annotations

import json
from pathlib import Path


MECHANIC_ID = "reflow_vitrine"
NUMERIC = {"gap", "padding", "grow"}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _states(state_dir: Path) -> tuple[dict, dict]:
    return _read(state_dir / "public_state.json"), _read(state_dir / "ground_truth.json")


def _interaction(public: dict) -> str:
    return str((public.get("control_condition") or {}).get("interaction") or "full")


def _select_frame(page, frame_id: str) -> None:
    page.locator(f'[data-frame-select="{frame_id}"]').click()


def _drag_fader(page, frame_id: str, prop: str, current, target, values: list) -> None:
    fader = page.locator(f'[data-fader-frame="{frame_id}"][data-fader-prop="{prop}"]')
    box = fader.bounding_box()
    if box is None:
        raise AssertionError(f"missing visible fader for {frame_id}.{prop}")
    start_ratio = values.index(current) / (len(values) - 1)
    target_ratio = values.index(target) / (len(values) - 1)
    inset = max(2.0, min(6.0, box["width"] * .02))
    usable_width = box["width"] - inset * 2
    start_x = box["x"] + inset + usable_width * start_ratio
    end_x = box["x"] + inset + usable_width * target_ratio
    y = box["y"] + box["height"] * .38
    page.mouse.move(start_x, y)
    page.mouse.down()
    page.mouse.move(end_x, y, steps=10)
    page.mouse.up()


def _property_matches(page, public: dict, frame_id: str, prop: str, target) -> bool:
    if _interaction(public) == "simplified":
        return page.locator(
            f'[data-set-frame="{frame_id}"][data-set-prop="{prop}"][data-set-value="{target}"].is-current'
        ).count() == 1
    if prop in NUMERIC:
        return page.locator(
            f'[data-fader-frame="{frame_id}"][data-fader-prop="{prop}"]'
        ).get_attribute("aria-label") == f"{prop.upper() if prop != 'grow' else 'GROWTH'} {target}"
    return page.locator(
        f'[data-select-frame="{frame_id}"][data-select-prop="{prop}"]'
    ).input_value() == str(target)


def _choose_dropdown(page, public: dict, frame_id: str, prop: str, target) -> None:
    select = page.locator(f'[data-select-frame="{frame_id}"][data-select-prop="{prop}"]')
    select.click()
    page.keyboard.press("Escape")
    page.keyboard.type(str(target))
    page.keyboard.press("Tab")


def _set_property(page, public: dict, frame_id: str, prop: str, current, target) -> None:
    mode = _interaction(public)
    for _attempt in range(3):
        if mode == "simplified":
            page.locator(f'[data-set-frame="{frame_id}"][data-set-prop="{prop}"][data-set-value="{target}"]').click()
        elif prop in NUMERIC:
            _drag_fader(page, frame_id, prop, current, target, public["allowed_values"][prop])
        else:
            _choose_dropdown(page, public, frame_id, prop, target)
        page.wait_for_timeout(45)
        if _property_matches(page, public, frame_id, prop, target):
            return
    raise AssertionError(f"visible property control did not reach {frame_id}.{prop}={target}")


def _reorder_once(page, public: dict, frame_id: str, current: list[str], target: list[str]) -> None:
    mismatch = next((index for index, value in enumerate(target) if current[index] != value), None)
    if mismatch is None:
        return
    source = current.index(target[mismatch])
    if _interaction(public) == "simplified":
        step = -1 if source > mismatch else 1
        while source != mismatch:
            page.locator(f'[data-order-frame="{frame_id}"][data-order-index="{source}"][data-order-delta="{step}"]').click()
            moved = current.pop(source); source += step; current.insert(source, moved)
            page.wait_for_timeout(35)
        return
    expected = list(current)
    moved = expected.pop(source); expected.insert(mismatch, moved)
    for _attempt in range(3):
        source_chip = page.locator(f'[data-order-frame="{frame_id}"][data-order-chip="{target[mismatch]}"]')
        destination_chip = page.locator(f'[data-order-frame="{frame_id}"][data-order-index="{mismatch}"]')
        source_box = source_chip.bounding_box(); destination_box = destination_chip.bounding_box()
        if source_box is None or destination_box is None:
            raise AssertionError("missing visible child-order chip geometry")
        page.mouse.move(source_box["x"] + source_box["width"] / 2, source_box["y"] + source_box["height"] / 2)
        page.mouse.down()
        page.mouse.move(destination_box["x"] + destination_box["width"] / 2, destination_box["y"] + destination_box["height"] / 2, steps=10)
        page.mouse.up()
        page.wait_for_timeout(45)
        visible = page.locator(f'[data-order-frame="{frame_id}"][data-order-chip]').evaluate_all(
            "nodes => nodes.map(node => node.dataset.orderChip)"
        )
        if visible == expected:
            current[:] = expected
            return
    raise AssertionError(f"visible child order did not reach {expected} for {frame_id}")


def _solve_rules(page, public: dict, truth: dict, *, capture_path: Path | None = None) -> None:
    current = json.loads(json.dumps(public["initial_config"]))
    target = truth["target_config"]
    halfway = max(1, len(truth["corruptions"]) // 2)
    edits = 0
    for frame in public["frames"]:
        frame_id = frame["id"]
        _select_frame(page, frame_id)
        for prop in public["mutable_properties"]:
            if prop == "order" or (prop == "grow" and frame_id == "window"):
                continue
            if current[frame_id][prop] != target[frame_id][prop]:
                _set_property(page, public, frame_id, prop, current[frame_id][prop], target[frame_id][prop])
                current[frame_id][prop] = target[frame_id][prop]
                edits += 1
                if capture_path and edits == halfway:
                    page.screenshot(path=str(capture_path))
        while current[frame_id]["order"] != target[frame_id]["order"]:
            _reorder_once(page, public, frame_id, current[frame_id]["order"], target[frame_id]["order"])
            edits += 1
            if capture_path and edits == halfway:
                page.screenshot(path=str(capture_path))


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    public, _truth = _states(state_dir)
    old_challenge = public["challenge_id"]
    page.locator("#rv-certify").click()
    page.locator('.reflow-vitrine[data-fresh-failure="true"] .rv-verdict.is-fail').wait_for(state="visible")
    page.screenshot(path=str(out_dir / "failed-fresh-commission.png"))
    fresh_public, _fresh_truth = _states(state_dir)
    if fresh_public["challenge_id"] == old_challenge:
        raise AssertionError("failed certification did not generate a fresh commission")


def exercise_local_recovery(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    public, _truth = _states(state_dir)
    frame_id = public["frames"][0]["id"]
    prop = next(prop for prop in public["mutable_properties"] if prop not in {"order", "grow"})
    current = public["initial_config"][frame_id][prop]
    wrong = next(value for value in public["allowed_values"][prop] if value != current)
    _select_frame(page, frame_id)
    _set_property(page, public, frame_id, prop, current, wrong)
    page.screenshot(path=str(out_dir / "reversible-wrong-edit.png"))
    page.locator("#rv-revert").click()
    page.screenshot(path=str(out_dir / "reverted-same-commission.png"))


def solve(page, state_dir: Path, out_dir: Path, mechanic: str, *, certify: bool = True) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    public, truth = _states(state_dir)
    _solve_rules(page, public, truth, capture_path=out_dir / "active-reflow.png")
    page.screenshot(path=str(out_dir / "solved-before-certify.png"))
    if certify:
        page.locator("#rv-certify").click()
        page.locator(".rv-verdict.is-pass").wait_for(state="visible")
