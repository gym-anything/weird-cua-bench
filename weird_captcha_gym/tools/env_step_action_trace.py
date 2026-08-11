"""Record visible browser input and translate it to standard Gym actions.

The recorder is deliberately privileged: controlled solvers may inspect the
local challenge state while deciding what to do.  Its output is not accepted
as a solve.  Acceptance comes only when the resulting groups are replayed by
``GymAnythingEnv.step`` in the separate verification tool.
"""
from __future__ import annotations

import math
from typing import Any


RECORDER_SCRIPT = r"""
(() => {
  const trace = [];
  let sequence = 0;
  const recordedDocuments = new WeakSet();
  const frameOffset = () => {
    let current = window;
    let x = 0;
    let y = 0;
    try {
      while (current !== current.top && current.frameElement) {
        const rect = current.frameElement.getBoundingClientRect();
        x += rect.left;
        y += rect.top;
        current = current.parent;
      }
    } catch (_error) {}
    return [x, y];
  };
  const details = (target) => {
    if (!(target instanceof Element)) return {};
    const rect = target.getBoundingClientRect();
    const [offsetX, offsetY] = frameOffset();
    const result = {
      target_tag: target.tagName.toLowerCase(),
      target_id: target.id || "",
      target_type: target.getAttribute("type") || "",
      target_value: "value" in target ? String(target.value ?? "") : "",
      target_rect: [rect.left + offsetX, rect.top + offsetY, rect.width, rect.height],
      viewport_scroll_x: Number(window.scrollX || 0),
      viewport_scroll_y: Number(window.scrollY || 0),
      viewport_width: Number(window.innerWidth || 0),
      viewport_height: Number(window.innerHeight || 0),
    };
    if (target instanceof HTMLInputElement) {
      result.minimum = target.min;
      result.maximum = target.max;
      result.step = target.step;
    }
    if (target instanceof HTMLSelectElement) {
      result.selected_index = target.selectedIndex;
      result.option_count = target.options.length;
    }
    return result;
  };
  const append = (event, extra = {}) => {
    trace.push({
      sequence: ++sequence,
      type: event.type,
      time_ms: Number(event.timeStamp),
      absolute_time_ms: Number(performance.timeOrigin + event.timeStamp),
      trusted: Boolean(event.isTrusted),
      ...details(event.target),
      ...extra,
    });
  };
  const installForCurrentDocument = () => {
    const targetDocument = document;
    if (recordedDocuments.has(targetDocument)) return;
    recordedDocuments.add(targetDocument);
    for (const type of ["pointermove", "pointerdown", "pointerup", "pointercancel"]) {
      targetDocument.addEventListener(type, (event) => {
        if (!event.isTrusted || event.pointerType !== "mouse") return;
        const [offsetX, offsetY] = frameOffset();
        append(event, {
          x: Number(event.clientX) + offsetX, y: Number(event.clientY) + offsetY,
          button: Number(event.button), buttons: Number(event.buttons),
          pointer_id: Number(event.pointerId),
        });
      }, true);
    }
    targetDocument.addEventListener("wheel", (event) => {
      if (!event.isTrusted) return;
      const [offsetX, offsetY] = frameOffset();
      append(event, {
        x: Number(event.clientX) + offsetX, y: Number(event.clientY) + offsetY,
        delta_x: Number(event.deltaX), delta_y: Number(event.deltaY),
      });
    }, true);
    for (const type of ["keydown", "keyup"]) {
      targetDocument.addEventListener(type, (event) => {
        if (!event.isTrusted) return;
        append(event, {
          key: String(event.key), code: String(event.code),
          repeat: Boolean(event.repeat),
        });
      }, true);
    }
    targetDocument.addEventListener("focusin", (event) => append(event), true);
    targetDocument.addEventListener("input", (event) => append(event, {
      data: event.data == null ? null : String(event.data),
      input_type: String(event.inputType || ""),
    }), true);
  };
  window.__weirdEnvStepInputTrace = trace;
  window.__installWeirdEnvStepInputTrace = installForCurrentDocument;
  window.__recordWeirdEnvStepTabFocus = (tabIndex) => {
    const now = performance.now();
    trace.push({
      sequence: ++sequence,
      type: "tabfocus",
      time_ms: now,
      absolute_time_ms: performance.timeOrigin + now,
      trusted: false,
      tab_index: Number(tabIndex),
    });
  };
  window.__resetWeirdEnvStepInputTrace = () => {
    trace.splice(0, trace.length);
    sequence = 0;
  };
  installForCurrentDocument();
})();
"""


_KEY_NAMES = {
    " ": "space",
    "Alt": "alt",
    "ArrowDown": "down",
    "ArrowLeft": "left",
    "ArrowRight": "right",
    "ArrowUp": "up",
    "Backspace": "backspace",
    "Control": "ctrl",
    "Delete": "delete",
    "End": "end",
    "Enter": "enter",
    "Escape": "escape",
    "Home": "home",
    "Meta": "meta",
    "PageDown": "pagedown",
    "PageUp": "pageup",
    "Shift": "shift",
    "Tab": "tab",
}


def _key_name(value: Any) -> str:
    key = str(value or "")
    # Space is a named key in the Gym action contract, not text insertion.
    # Check the named-key table before the generic printable-character path.
    if key in _KEY_NAMES:
        return _KEY_NAMES[key]
    # Preserve printable text exactly. In particular, punctuation such as
    # ``:`` is later emitted through the public ``keyboard.text`` action;
    # treating it as a raw key name is not portable across keyboard layouts.
    if len(key) == 1:
        return key
    return key.lower()


def _point(event: dict[str, Any]) -> list[int]:
    return [round(float(event.get("x") or 0)), round(float(event.get("y") or 0))]


def _target_point(event: dict[str, Any], *, range_value: bool = False) -> list[int] | None:
    rect = event.get("target_rect")
    if not isinstance(rect, list) or len(rect) != 4:
        return None
    left, top, width, height = (float(value) for value in rect)
    if width <= 0 or height <= 0:
        return None
    ratio = 0.5
    if range_value:
        try:
            minimum = float(event.get("minimum") or 0)
            maximum = float(event.get("maximum") or 100)
            value = float(event.get("target_value"))
            if maximum > minimum:
                ratio = max(0.0, min(1.0, (value - minimum) / (maximum - minimum)))
        except (TypeError, ValueError):
            ratio = 0.5
    return [round(left + width * ratio), round(top + height / 2)]


def _input_actions(event: dict[str, Any]) -> list[dict[str, Any]]:
    input_type = str(event.get("target_type") or "").lower()
    point = _target_point(event, range_value=input_type == "range")
    if point is None:
        return []
    if input_type == "range":
        return [{"mouse": {"left_click": point}}]
    if str(event.get("target_tag")) == "select":
        selected = max(0, int(event.get("selected_index") or 0))
        actions: list[dict[str, Any]] = [
            {"mouse": {"left_click": point}},
            {"keyboard": {"keys": ["home"]}},
        ]
        actions.extend({"keyboard": {"keys": ["down"]}} for _ in range(selected))
        actions.append({"keyboard": {"keys": ["enter"]}})
        return actions
    return [
        {"mouse": {"left_click": point}},
        {"keyboard": {"keys": ["ctrl", "a"]}},
        {"keyboard": {"text": str(event.get("target_value") or "")}},
    ]


def _focus_action(event: dict[str, Any]) -> dict[str, Any] | None:
    if str(event.get("target_type") or "").lower() != "range":
        return None
    point = _target_point(event, range_value=True)
    return {"mouse": {"left_click": point}} if point is not None else None


def parse_input_trace(
    raw_events: list[dict[str, Any]],
    *,
    split_gap_ms: float = 120.0,
) -> list[dict[str, Any]]:
    """Convert trusted browser events to action groups.

    Events separated only by normal input dispatch latency are batched into a
    single step. A real wait splits the stream, allowing a paused replay to
    spend its declared observation window between the two groups.
    """
    events = sorted(raw_events, key=lambda item: int(item.get("sequence") or 0))
    groups: list[dict[str, Any]] = []
    active_pointer: dict[str, Any] | None = None
    pending_move: dict[str, Any] | None = None
    keyboard_group: dict[str, Any] | None = None
    pending_focus: dict[str, Any] | None = None
    last_physical_time = float("-inf")
    scroll_positions: dict[tuple[int, int], tuple[float, float]] = {}
    current_page_index = 0

    def timed(action: dict[str, Any], timestamp: float) -> dict[str, Any]:
        return {
            **action,
            "_trace_time_ms": timestamp,
            "_trace_page_index": current_page_index,
        }

    def append_with_input_delay(group: dict[str, Any], action: dict[str, Any], timestamp: float) -> None:
        gap = timestamp - float(group["end_ms"])
        if 20 <= gap < split_gap_ms:
            group["actions"].append({
                "action": "wait",
                "time": gap / 1000,
                "_trace_time_ms": float(group["end_ms"]),
            })
        group["actions"].append(timed(action, timestamp))
        group["end_ms"] = timestamp

    def add_group(actions: list[dict[str, Any]], start: float, end: float, source: str) -> None:
        if not actions:
            return
        if groups and start - float(groups[-1]["end_ms"]) < split_gap_ms:
            groups[-1]["actions"].extend(actions)
            groups[-1]["end_ms"] = max(float(groups[-1]["end_ms"]), end)
            groups[-1]["sources"].append(source)
            return
        groups.append({
            "at_ms": start,
            "end_ms": end,
            "actions": actions,
            "sources": [source],
        })

    def flush_keyboard() -> None:
        nonlocal keyboard_group
        if keyboard_group is None:
            return
        add_group(
            keyboard_group["actions"],
            keyboard_group["at_ms"],
            keyboard_group["end_ms"],
            "keyboard",
        )
        keyboard_group = None

    def flush_move() -> None:
        nonlocal pending_move
        if pending_move is None:
            return
        add_group(
            pending_move["actions"],
            pending_move["at_ms"],
            pending_move["end_ms"],
            "pointer_move",
        )
        pending_move = None

    def flush_pointer() -> None:
        nonlocal active_pointer
        if active_pointer is None:
            return
        add_group(
            active_pointer["actions"],
            active_pointer["at_ms"],
            active_pointer["end_ms"],
            "pointer_gesture",
        )
        active_pointer = None

    for event in events:
        kind = str(event.get("type") or "")
        timestamp = float(event.get("time_ms") or 0)
        current_page_index = int(event.get("page_index") or 0)
        frame_index = int(event.get("frame_index") or 0)
        document_key = (current_page_index, frame_index)
        scroll_x = float(event.get("viewport_scroll_x") or 0)
        scroll_y = float(event.get("viewport_scroll_y") or 0)
        previous_scroll_x, previous_scroll_y = scroll_positions.get(document_key, (0.0, 0.0))
        scroll_positions[document_key] = (scroll_x, scroll_y)
        scroll_delta_y = scroll_y - previous_scroll_y
        if abs(scroll_delta_y) >= 1 and kind not in {"focusin", "input"}:
            # Playwright locators may scroll a visible control into the
            # viewport before dispatching trusted pointer input. Reproduce
            # that movement with the public wheel action instead of silently
            # relying on locator auto-scroll during accepted replay. One X11
            # wheel notch is roughly three browser text lines.
            flush_keyboard()
            flush_move()
            flush_pointer()
            wheel_notches = max(1, round(abs(scroll_delta_y) / 100))
            # The Gym mouse contract used by the benchmark is positive down,
            # matching browser scrollY and WheelEvent.deltaY.
            if scroll_delta_y < 0:
                wheel_notches = -wheel_notches
            point = _point(event)
            add_group(
                [
                    timed({"mouse": {"move": point}}, timestamp),
                    timed({"mouse": {"scroll": wheel_notches}}, timestamp),
                ],
                timestamp,
                timestamp,
                "implicit_visible_scroll",
            )
        if kind == "tabfocus":
            flush_keyboard()
            flush_move()
            flush_pointer()
            tab_index = int(event.get("tab_index") or 0)
            if not 0 <= tab_index <= 7:
                raise ValueError(f"cannot replay browser tab index {tab_index}")
            add_group(
                [timed({"keyboard": {"keys": ["ctrl", str(tab_index + 1)]}}, timestamp)],
                timestamp,
                timestamp,
                "browser_tab_focus",
            )
            continue
        if kind == "focusin":
            pending_focus = event
            continue
        if kind == "input":
            # Native pointer/keyboard input already has an exact action record.
            if timestamp - last_physical_time <= split_gap_ms:
                continue
            flush_keyboard()
            flush_move()
            flush_pointer()
            actions = [timed(action, timestamp) for action in _input_actions(event)]
            add_group(actions, timestamp, timestamp, "programmatic_input")
            pending_focus = None
            continue
        if kind in {"keydown", "keyup"}:
            flush_move()
            flush_pointer()
            if pending_focus is not None:
                focus = _focus_action(pending_focus)
                if focus is not None:
                    add_group([timed(focus, timestamp)], timestamp, timestamp, "programmatic_focus")
                pending_focus = None
            key = _key_name(event.get("key"))
            if not key or key == "unidentified":
                continue
            action = timed({
                "keyboard": {
                    "keys_down" if kind == "keydown" else "keys_up": [key]
                }
            }, timestamp)
            if keyboard_group is None or timestamp - float(keyboard_group["end_ms"]) >= split_gap_ms:
                flush_keyboard()
                keyboard_group = {"at_ms": timestamp, "end_ms": timestamp, "actions": []}
            append_with_input_delay(keyboard_group, action, timestamp)
            last_physical_time = timestamp
            continue
        flush_keyboard()
        if kind == "pointermove":
            action = timed({"mouse": {"move": _point(event)}}, timestamp)
            if active_pointer is not None:
                if timestamp - float(active_pointer["end_ms"]) >= split_gap_ms:
                    flush_pointer()
                    active_pointer = {"at_ms": timestamp, "end_ms": timestamp, "actions": []}
                append_with_input_delay(active_pointer, action, timestamp)
            elif pending_move is None or timestamp - float(pending_move["end_ms"]) >= split_gap_ms:
                flush_move()
                pending_move = {"at_ms": timestamp, "end_ms": timestamp, "actions": [action]}
            else:
                append_with_input_delay(pending_move, action, timestamp)
            last_physical_time = timestamp
            continue
        if kind == "pointerdown":
            if pending_move is not None and timestamp - float(pending_move["end_ms"]) < split_gap_ms:
                initial = pending_move
                pending_move = None
                active_pointer = {
                    "at_ms": initial["at_ms"],
                    "end_ms": timestamp,
                    "actions": list(initial["actions"]),
                }
            else:
                flush_move()
                active_pointer = {
                    "at_ms": timestamp,
                    "end_ms": timestamp,
                    "actions": [timed({"mouse": {"move": _point(event)}}, timestamp)],
                }
            button = "right" if int(event.get("button") or 0) == 2 else "left"
            append_with_input_delay(
                active_pointer,
                {"mouse": {"buttons": {f"{button}_down": True}}},
                timestamp,
            )
            last_physical_time = timestamp
            continue
        if kind in {"pointerup", "pointercancel"}:
            flush_move()
            if active_pointer is None:
                active_pointer = {
                    "at_ms": timestamp,
                    "end_ms": timestamp,
                    "actions": [timed({"mouse": {"move": _point(event)}}, timestamp)],
                }
            elif timestamp - float(active_pointer["end_ms"]) >= split_gap_ms:
                flush_pointer()
                active_pointer = {
                    "at_ms": timestamp,
                    "end_ms": timestamp,
                    "actions": [timed({"mouse": {"move": _point(event)}}, timestamp)],
                }
            button = "right" if int(event.get("button") or 0) == 2 else "left"
            append_with_input_delay(
                active_pointer,
                {"mouse": {"buttons": {f"{button}_up": True}}},
                timestamp,
            )
            flush_pointer()
            last_physical_time = timestamp
            continue
        if kind == "wheel":
            flush_move()
            flush_pointer()
            wheel_notches = max(1, round(abs(float(event.get("delta_y") or 0)) / 100))
            if float(event.get("delta_y") or 0) < 0:
                wheel_notches = -wheel_notches
            actions = [
                timed({"mouse": {"move": _point(event)}}, timestamp),
                timed({"mouse": {"scroll": wheel_notches}}, timestamp),
            ]
            add_group(actions, timestamp, timestamp, "wheel")
            last_physical_time = timestamp

    flush_keyboard()
    flush_move()
    flush_pointer()
    if not groups:
        return []
    origin = float(groups[0]["at_ms"])
    previous_end = origin
    for index, group in enumerate(groups):
        group["index"] = index
        group["delay_before_ms"] = max(0.0, float(group["at_ms"]) - previous_end)
        group["at_ms"] = round(float(group["at_ms"]) - origin, 3)
        group["end_ms"] = round(float(group["end_ms"]) - origin, 3)
        group["delay_before_ms"] = round(float(group["delay_before_ms"]), 3)
        for action in group["actions"]:
            if "_trace_time_ms" in action:
                action["_trace_time_ms"] = round(
                    float(action["_trace_time_ms"]) - origin,
                    3,
                )
        previous_end = origin + float(group["end_ms"])
    return groups


def _pointer_path_is_straight(
    points: list[list[float]],
    *,
    maximum_deviation_px: float = 3.0,
    maximum_path_ratio: float = 1.03,
) -> bool:
    """Return whether an observed pointer path is safely reducible to endpoints."""
    if len(points) <= 2:
        return True
    start_x, start_y = map(float, points[0])
    end_x, end_y = map(float, points[-1])
    direct = math.hypot(end_x - start_x, end_y - start_y)
    path_length = sum(
        math.hypot(float(second[0]) - float(first[0]), float(second[1]) - float(first[1]))
        for first, second in zip(points, points[1:])
    )
    if direct <= 1e-6:
        return path_length <= maximum_deviation_px
    if path_length / direct > maximum_path_ratio:
        return False
    for x, y in points[1:-1]:
        cross = abs(
            (end_y - start_y) * (float(x) - start_x)
            - (end_x - start_x) * (float(y) - start_y)
        )
        if cross / direct > maximum_deviation_px:
            return False
    return True


def compact_agent_actions(
    groups: list[dict[str, Any]],
    *,
    maximum_incidental_gesture_wait: float = 0.0,
    maximum_incidental_key_wait: float = 0.18,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Recover the atomic public actions that produced a trusted DOM trace.

    Replaying every produced pointer/key event as a separate public action
    misrepresents the agent API and adds one transport round trip per event.
    Held gestures remain expanded because their duration is meaningful. Only
    down/up pairs with no recorded wait are folded into an atomic action;
    browser dispatch gaps shorter than 20 ms never become waits in the parser,
    so ordinary clicks and drags still compact without erasing a control hold.
    """

    before = sum(len(group.get("actions") or []) for group in groups)
    compacted_groups: list[dict[str, Any]] = []

    def mouse_value(action: dict[str, Any], key: str):
        mouse = action.get("mouse")
        return mouse.get(key) if isinstance(mouse, dict) else None

    def button_value(action: dict[str, Any], key: str) -> bool:
        mouse = action.get("mouse")
        buttons = mouse.get("buttons") if isinstance(mouse, dict) else None
        return bool(buttons.get(key)) if isinstance(buttons, dict) else False

    def keyboard_value(action: dict[str, Any], key: str) -> list[str] | None:
        keyboard = action.get("keyboard")
        value = keyboard.get(key) if isinstance(keyboard, dict) else None
        if value is None:
            return None
        return [str(value)] if isinstance(value, str) else [str(item) for item in value]

    for source_group in groups:
        source = list(source_group.get("actions") or [])
        output: list[dict[str, Any]] = []
        output_times: list[float | None] = []
        output_pages: list[int | None] = []
        index = 0
        text_buffer = ""
        text_time: float | None = None
        text_page: int | None = None

        def trace_time(action: dict[str, Any]) -> float | None:
            value = action.get("_trace_time_ms")
            return float(value) if value is not None else None

        def trace_page(action: dict[str, Any]) -> int | None:
            value = action.get("_trace_page_index")
            return int(value) if value is not None else None

        def append_output(
            action: dict[str, Any],
            timestamp: float | None,
            page_index: int | None,
        ) -> None:
            clean = dict(action)
            clean.pop("_trace_time_ms", None)
            clean.pop("_trace_page_index", None)
            output.append(clean)
            output_times.append(timestamp)
            output_pages.append(page_index)

        def flush_text() -> None:
            nonlocal text_buffer, text_time, text_page
            if text_buffer:
                append_output({"keyboard": {"text": text_buffer}}, text_time, text_page)
                text_buffer = ""
                text_time = None
                text_page = None

        while index < len(source):
            action = source[index]
            start = mouse_value(action, "move")
            if isinstance(start, list) and len(start) == 2 and index + 1 < len(source):
                button = None
                if button_value(source[index + 1], "left_down"):
                    button = "left"
                elif button_value(source[index + 1], "right_down"):
                    button = "right"
                if button is not None:
                    cursor = index + 2
                    endpoint = list(start)
                    path = [list(start)]
                    moved = False
                    wait_seconds = 0.0
                    valid = False
                    while cursor < len(source):
                        candidate = source[cursor]
                        if button_value(candidate, f"{button}_up"):
                            valid = True
                            break
                        move = mouse_value(candidate, "move")
                        if isinstance(move, list) and len(move) == 2:
                            endpoint = list(move)
                            path.append(endpoint)
                            moved = moved or endpoint != list(start)
                            cursor += 1
                            continue
                        if candidate.get("action") == "wait":
                            wait_seconds += max(0.0, float(candidate.get("time") or 0))
                            cursor += 1
                            continue
                        break
                    if (
                        valid
                        and wait_seconds <= maximum_incidental_gesture_wait
                        and (not moved or _pointer_path_is_straight(path))
                    ):
                        flush_text()
                        mouse_key = f"{button}_click_drag" if moved else f"{button}_click"
                        mouse_payload = [list(start), endpoint] if moved else list(start)
                        append_output(
                            {"mouse": {mouse_key: mouse_payload}},
                            trace_time(source[cursor]),
                            trace_page(source[cursor]),
                        )
                        index = cursor + 1
                        continue

            # Recover one public key-combination action from its down/up
            # events. This covers both a simple key tap and Ctrl+C-style
            # combinations without inventing a runner-specific shape.
            downs = keyboard_value(action, "keys_down")
            if downs:
                cursor = index
                pressed: list[str] = []
                released: list[str] = []
                wait_seconds = 0.0
                while cursor < len(source):
                    candidate = source[cursor]
                    candidate_downs = keyboard_value(candidate, "keys_down")
                    candidate_ups = keyboard_value(candidate, "keys_up")
                    if candidate_downs and not released:
                        pressed.extend(candidate_downs)
                        cursor += 1
                        continue
                    if candidate_ups:
                        released.extend(candidate_ups)
                        cursor += 1
                        if len(released) >= len(pressed):
                            break
                        continue
                    if candidate.get("action") == "wait" and not released:
                        wait_seconds += max(0.0, float(candidate.get("time") or 0))
                        cursor += 1
                        continue
                    break
                if (
                    pressed
                    and released == list(reversed(pressed))
                    and wait_seconds <= maximum_incidental_key_wait
                ):
                    printable = len(pressed) == 1 and len(pressed[0]) == 1
                    if printable:
                        text_buffer += pressed[0]
                        text_time = trace_time(source[cursor - 1])
                        text_page = trace_page(source[cursor - 1])
                    else:
                        flush_text()
                        append_output(
                            {"keyboard": {"keys": pressed}},
                            trace_time(source[cursor - 1]),
                            trace_page(source[cursor - 1]),
                        )
                    index = cursor
                    continue

            flush_text()
            if action.get("action") == "wait" and trace_time(action) is not None:
                # Recorded waits describe spacing between trusted events. The
                # live replay scheduler reconstructs that spacing from the
                # timestamps; paused replay intentionally keeps task time
                # frozen while an action itself is injected.
                index += 1
                continue
            append_output(action, trace_time(action), trace_page(action))
            index += 1
        flush_text()
        group = dict(source_group)
        group["actions"] = output
        if output_times and all(timestamp is not None for timestamp in output_times):
            group["action_at_ms"] = [round(float(timestamp), 3) for timestamp in output_times]
        if output_pages and all(page_index is not None for page_index in output_pages):
            group["action_page_indices"] = [int(page_index) for page_index in output_pages]
        compacted_groups.append(group)

    after = sum(len(group.get("actions") or []) for group in compacted_groups)
    return compacted_groups, {
        "actions_before_compaction": before,
        "actions_after_compaction": after,
        "actions_eliminated": before - after,
    }
