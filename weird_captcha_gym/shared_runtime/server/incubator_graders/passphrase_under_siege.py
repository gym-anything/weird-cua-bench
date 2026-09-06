from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "passphrase_under_siege"
DEFAULT_SIZE = 18
VOWELS = frozenset("AEIOUaeiou")
EXPECTED_SELECT_SOURCE = {
    "simplified": "endpoint_clicks",
    "full": "range_drag",
}
EXPECTED_FEED_SOURCE = {
    "simplified": "token_click_hatchling",
    "full": "token_drag",
}
EXPECTED_QUENCH_SOURCE = {
    "simplified": "quench_button",
    "full": "ember_click",
}


def _fail(feedback: str, *, highest: int = 0, total: int = 0) -> dict[str, Any]:
    return {
        "graded": True,
        "passed": False,
        "feedback": feedback,
        "highest_rule_index": highest,
        "total_rules": total,
    }


def _digit_sum(value: str) -> int:
    return sum(int(char) for char in value if char.isdigit())


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _inside_ellipse(
    point: tuple[float, float],
    center: tuple[float, float],
    radius_x: float,
    radius_y: float,
) -> bool:
    if radius_x <= 0 or radius_y <= 0:
        return False
    dx = (point[0] - center[0]) / radius_x
    dy = (point[1] - center[1]) / radius_y
    return (dx * dx) + (dy * dy) <= 1


def _one_occurrence(text: str, token: str) -> tuple[int, int] | None:
    if not token or text.count(token) != 1:
        return None
    start = text.index(token)
    return start, start + len(token)


class Glyph:
    def __init__(
        self,
        char: str,
        bold: bool = False,
        italic: bool = False,
        font: str = "mono",
        size: int = DEFAULT_SIZE,
    ) -> None:
        self.char = char
        self.bold = bold
        self.italic = italic
        self.font = font
        self.size = size


class Replay:
    def __init__(
        self,
        truth: dict[str, Any],
        public: dict[str, Any],
        interaction: str,
    ) -> None:
        self.truth = truth
        self.public = public
        self.interaction = interaction
        self.glyphs: list[Glyph] = []
        self.cursor = 0
        self.selection: tuple[int, int] | None = None
        self.selection_source: str | None = None
        self.hazard_started_ms: int | None = None
        self.hunger_deadline_ms: int | None = None
        self.next_feed_ready_ms: int | None = None
        self.feed_count = 0
        self.used_grains: set[str] = set()
        self.quenched: set[str] = set()
        self.damaged: set[str] = set()
        self.starved = False
        self.confirmation_started = False
        self.confirmation_expected = ""
        self.confirmation = ""
        self.submitted = False
        self.highest_rule_index = 0
        self.last_ms = -1

    @property
    def contract(self) -> dict[str, Any]:
        return self.truth["contract"]

    @property
    def clues(self) -> dict[str, Any]:
        return self.truth["clues"]

    @property
    def text(self) -> str:
        return "".join(glyph.char for glyph in self.glyphs)

    @property
    def rule_ids(self) -> list[str]:
        return [str(item) for item in self.truth["rule_ids"]]

    def _style_exactly(self, start: int, end: int, attribute: str, value: Any) -> bool:
        if not (0 <= start < end <= len(self.glyphs)):
            return False
        for index, glyph in enumerate(self.glyphs):
            expected = value if start <= index < end else (
                False if attribute in {"bold", "italic"} else "mono" if attribute == "font" else DEFAULT_SIZE
            )
            if getattr(glyph, attribute) != expected:
                return False
        return True

    def _font_ranges_exactly(self, required: tuple[int, int], allowed: tuple[int, int] | None = None) -> bool:
        start, end = required
        if not 0 <= start < end <= len(self.glyphs):
            return False
        for index, glyph in enumerate(self.glyphs):
            if start <= index < end:
                if glyph.font != "serif":
                    return False
            elif allowed is not None and allowed[0] <= index < allowed[1]:
                if glyph.font not in {"mono", "serif"}:
                    return False
            elif glyph.font != "mono":
                return False
        return True

    def _rule(self, rule_id: str) -> bool:
        text = self.text
        stamp = str(self.clues.get("stamp") or "")
        color = str(self.clues.get("color") or "")
        gauge = str(self.clues.get("gauge_token") or "")
        stamp_range = _one_occurrence(text, stamp)
        color_range = _one_occurrence(text, color) if color else None
        gauge_range = _one_occurrence(text, gauge) if gauge else None
        if rule_id == "minimum_length":
            return len(text) >= int(self.contract["minimum_length"])
        if rule_id == "uppercase":
            return any(char.isupper() for char in text)
        if rule_id == "special_mark":
            return "!" in text
        if rule_id == "digit_sum":
            return _digit_sum(text) == int(self.contract["digit_sum_target"])
        if rule_id == "stamp":
            return stamp_range is not None
        if rule_id == "color":
            return color_range is not None
        if rule_id == "gauge":
            return gauge_range is not None
        if rule_id == "clue_order":
            if stamp_range is None:
                return False
            starts = [stamp_range[0]]
            if color:
                if color_range is None:
                    return False
                starts.append(color_range[0])
            if gauge:
                if gauge_range is None:
                    return False
                starts.append(gauge_range[0])
            return starts == sorted(starts) and len(set(starts)) == len(starts)
        if rule_id == "exact_length":
            return len(text) == int(self.contract["exact_length"])
        if rule_id == "bold_vowels":
            return bool(self.glyphs) and all(glyph.bold == (glyph.char in VOWELS) for glyph in self.glyphs)
        if rule_id == "stamp_bold":
            return stamp_range is not None and self._style_exactly(*stamp_range, "bold", True)
        if rule_id == "stamp_italic":
            return stamp_range is not None and self._style_exactly(*stamp_range, "italic", True)
        if rule_id == "stamp_font":
            return stamp_range is not None and self._font_ranges_exactly(
                stamp_range,
                color_range if self.contract["color_font"] else None,
            )
        if rule_id == "gauge_size":
            if gauge_range is None:
                return False
            start, end = gauge_range
            digit_indices = [index for index in range(start, end) if self.glyphs[index].char.isdigit()]
            if not digit_indices:
                return False
            required = int(self.contract["gauge_size_px"])
            return all(
                glyph.size == (required if index in digit_indices else DEFAULT_SIZE)
                for index, glyph in enumerate(self.glyphs)
            )
        if rule_id == "color_font":
            return color_range is not None and self._font_ranges_exactly(color_range, stamp_range)
        if rule_id == "hatchling":
            return not self.starved and self.feed_count >= int(self.contract["feed_required"])
        if rule_id == "embers":
            expected = {str(item["id"]) for item in self.truth.get("embers") or []}
            return not self.damaged and self.quenched == expected
        raise ValueError(f"unknown siege rule {rule_id}")

    def results(self) -> list[bool]:
        return [self._rule(rule_id) for rule_id in self.rule_ids]

    def _update_progress(self, now_ms: int) -> None:
        results = self.results()
        prefix = 0
        for passed in results:
            if not passed:
                break
            prefix += 1
        self.highest_rule_index = max(self.highest_rule_index, prefix)
        static_ids = [rule_id for rule_id in self.rule_ids if rule_id not in {"hatchling", "embers"}]
        if (
            self.hazard_started_ms is None
            and (self.truth.get("embers") or int(self.contract["feed_required"]))
            and all(self._rule(rule_id) for rule_id in static_ids)
        ):
            self.hazard_started_ms = now_ms
            if int(self.contract["feed_required"]):
                self.hunger_deadline_ms = now_ms + int(self.contract["hunger_ms"])
                self.next_feed_ready_ms = now_ms

    def process_time(self, now_ms: int) -> None:
        if self.hazard_started_ms is None:
            return
        for ember in self.truth.get("embers") or []:
            ember_id = str(ember["id"])
            expires = self.hazard_started_ms + int(ember["spawn_offset_ms"]) + int(ember["ttl_ms"])
            if now_ms >= expires and ember_id not in self.quenched and ember_id not in self.damaged:
                self.damaged.add(ember_id)
                if self.glyphs:
                    index = int(ember["damage_slot"]) % len(self.glyphs)
                    self.glyphs.pop(index)
                    self.cursor = min(self.cursor, len(self.glyphs))
                    self.selection = None
                    self.selection_source = None
        if self.hunger_deadline_ms is not None and now_ms >= self.hunger_deadline_ms:
            self.starved = True
        self._update_progress(now_ms)

    def apply(self, event: dict[str, Any]) -> str | None:
        if self.submitted:
            return "events appear after terminal submission"
        kind = str(event.get("kind") or "")
        now_ms = event.get("t_ms")
        if isinstance(now_ms, bool) or not isinstance(now_ms, int) or now_ms < self.last_ms or now_ms > 600_000:
            return "event task time is invalid"
        self.process_time(now_ms)
        self.last_ms = now_ms

        if kind == "type":
            if self.confirmation_started:
                return "editor typing occurred after the ledger was sealed"
            char = event.get("text")
            if not isinstance(char, str) or len(char) != 1 or not 32 <= ord(char) <= 126:
                return "typed character is invalid"
            if event.get("input_source") != "physical_keyboard":
                return "typing uses the wrong input surface"
            if event.get("index") != self.cursor:
                return "typing cursor does not match replay state"
            if self.selection is not None:
                start, end = self.selection
                del self.glyphs[start:end]
                self.cursor = start
            self.glyphs.insert(self.cursor, Glyph(char))
            self.cursor += 1
            self.selection = None
            self.selection_source = None
        elif kind == "backspace":
            if self.confirmation_started or event.get("input_source") != "physical_keyboard":
                return "editor backspace uses the wrong phase or input surface"
            if self.selection is not None:
                start, end = self.selection
                del self.glyphs[start:end]
                self.cursor = start
            elif self.cursor:
                self.glyphs.pop(self.cursor - 1)
                self.cursor -= 1
            self.selection = None
            self.selection_source = None
        elif kind == "select":
            if self.confirmation_started:
                return "selection occurred after the ledger was sealed"
            expected_source = EXPECTED_SELECT_SOURCE[self.interaction]
            actual_source = event.get("input_source")
            if actual_source not in {expected_source, "keyboard_select_all"}:
                return "selection uses the wrong interaction input"
            start, end = event.get("start"), event.get("end")
            if (
                isinstance(start, bool)
                or isinstance(end, bool)
                or not isinstance(start, int)
                or not isinstance(end, int)
                or not 0 <= start < end <= len(self.glyphs)
            ):
                return "selected range is invalid"
            if actual_source == "keyboard_select_all" and (start != 0 or end != len(self.glyphs)):
                return "keyboard select-all did not select the whole visible document"
            self.selection = (start, end)
            self.selection_source = actual_source
            self.cursor = end
        elif kind == "format":
            if self.confirmation_started or self.selection is None:
                return "formatting occurred without an active editable selection"
            if event.get("input_source") != "toolbar_button":
                return "formatting uses the wrong input surface"
            start, end = self.selection
            if event.get("start") != start or event.get("end") != end:
                return "formatting range does not match the visible selection"
            if event.get("selection_source") != self.selection_source:
                return "formatting is not bound to the selected interaction mode"
            style = str(event.get("style") or "")
            value = event.get("value")
            if style in {"bold", "italic"}:
                if not isinstance(value, bool):
                    return "boolean formatting value is invalid"
            elif style == "font":
                if value not in {"mono", "serif"}:
                    return "font formatting value is invalid"
            elif style == "size":
                if isinstance(value, bool) or value not in {DEFAULT_SIZE, 24, 28, 32}:
                    return "font-size formatting value is invalid"
            else:
                return "unknown formatting operation"
            for glyph in self.glyphs[start:end]:
                setattr(glyph, style, value)
        elif kind == "feed":
            if self.confirmation_started or self.hazard_started_ms is None or self.starved:
                return "feeding occurred outside the live hatchling phase"
            if event.get("input_source") != EXPECTED_FEED_SOURCE[self.interaction]:
                return "feeding uses the wrong interaction input"
            token_id = str(event.get("token_id") or "")
            valid_tokens = [str(item) for item in self.truth["hatchling"]["grain_tokens"]]
            if token_id not in valid_tokens or token_id in self.used_grains:
                return "grain token is invalid or reused"
            required = int(self.contract["feed_required"])
            if self.feed_count >= required or token_id != valid_tokens[self.feed_count]:
                return "grain token is out of delivery order"
            if self.next_feed_ready_ms is None or now_ms < self.next_feed_ready_ms:
                return "next grain is not ready"
            x_norm, y_norm = event.get("x_norm"), event.get("y_norm")
            if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in (x_norm, y_norm)):
                return "feeding coordinate is invalid"
            target = (
                float(self.truth["hatchling"]["x_norm"]),
                float(self.truth["hatchling"]["y_norm"]),
            )
            if not _inside_ellipse(
                (float(x_norm), float(y_norm)),
                target,
                float(self.truth["hatchling"]["radius_x_norm"]),
                float(self.truth["hatchling"]["radius_y_norm"]),
            ):
                return "grain did not land on the rendered hatchling"
            self.used_grains.add(token_id)
            self.feed_count += 1
            self.next_feed_ready_ms = (
                now_ms + int(self.contract["feed_interval_ms"])
                if self.feed_count < required
                else None
            )
            self.hunger_deadline_ms = now_ms + int(self.contract["hunger_ms"])
        elif kind == "quench":
            if self.confirmation_started or self.hazard_started_ms is None:
                return "ember quench occurred outside the defense phase"
            if event.get("input_source") != EXPECTED_QUENCH_SOURCE[self.interaction]:
                return "ember quench uses the wrong interaction input"
            ember_id = str(event.get("ember_id") or "")
            ember = next((item for item in self.truth.get("embers") or [] if str(item["id"]) == ember_id), None)
            if ember is None or ember_id in self.quenched or ember_id in self.damaged:
                return "ember identity is invalid, repeated, or already destructive"
            local_ms = now_ms - self.hazard_started_ms - int(ember["spawn_offset_ms"])
            if not 0 <= local_ms < int(ember["ttl_ms"]):
                return "ember was quenched outside its visible lifetime"
            if self.interaction == "full":
                x_norm, y_norm = event.get("x_norm"), event.get("y_norm")
                if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in (x_norm, y_norm)):
                    return "ember click coordinate is invalid"
                phase = local_ms / int(ember["ttl_ms"])
                expected = (
                    float(ember["start"][0]) + (float(ember["end"][0]) - float(ember["start"][0])) * phase,
                    float(ember["start"][1]) + (float(ember["end"][1]) - float(ember["start"][1])) * phase,
                )
                if _distance((float(x_norm), float(y_norm)), expected) > 0.065:
                    return "ember click missed the rendered moving target"
            self.quenched.add(ember_id)
        elif kind == "begin_confirmation":
            if self.confirmation_started or not all(self.results()):
                return "ledger was sealed before every rule was green"
            if event.get("input_source") != "seal_button":
                return "ledger sealing uses the wrong input surface"
            self.confirmation_started = True
            self.confirmation_expected = self.text
            self.selection = None
            self.selection_source = None
        elif kind == "confirm_type":
            char = event.get("text")
            if (
                not self.confirmation_started
                or not isinstance(char, str)
                or len(char) != 1
                or not 32 <= ord(char) <= 126
                or event.get("input_source") != "physical_keyboard"
            ):
                return "confirmation typing is invalid"
            self.confirmation += char
        elif kind == "confirm_backspace":
            if not self.confirmation_started or event.get("input_source") != "physical_keyboard":
                return "confirmation backspace is invalid"
            self.confirmation = self.confirmation[:-1]
        elif kind == "submit":
            if event.get("input_source") != "certify_button":
                return "submission uses the wrong input surface"
            self.submitted = True
        else:
            return f"unknown siege event {kind}"

        self._update_progress(now_ms)
        return None


def _binding_error(
    payload: dict[str, Any],
    truth: dict[str, Any],
    public: dict[str, Any],
) -> str | None:
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID:
        return "payload mechanic mismatch"
    if str(truth.get("mechanic_id") or "") != MECHANIC_ID:
        return "ground-truth mechanic mismatch"
    if str(public.get("mechanic_id") or "") != MECHANIC_ID:
        return "public-state mechanic mismatch"
    challenge_id = str(truth.get("challenge_id") or "")
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id:
        return "stale challenge"
    if str(public.get("challenge_id") or "") != challenge_id:
        return "public-state challenge mismatch"
    task_id = str(truth.get("task_id") or "")
    if not task_id or str(payload.get("task_id") or "") != task_id:
        return "payload task mismatch"
    if str(public.get("task_id") or "") != task_id:
        return "public-state task mismatch"
    return None


def grade(
    payload: dict[str, Any],
    ground_truth: dict[str, Any],
    public_state: dict[str, Any],
) -> dict[str, Any]:
    if error := _binding_error(payload, ground_truth, public_state):
        return _fail(error)
    condition = ground_truth.get("control_condition")
    if condition != public_state.get("control_condition"):
        return _fail("public control condition differs from siege contract")
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in EXPECTED_SELECT_SOURCE:
        return _fail("siege interaction condition is invalid")
    if str(payload.get("interaction_mode") or "") != interaction:
        return _fail("siege transcript uses the wrong interaction mode")
    if ground_truth.get("contract") != public_state.get("contract"):
        return _fail("public difficulty contract differs from hidden contract")
    if ground_truth.get("clues") != public_state.get("clues"):
        return _fail("public visual clues differ from hidden contract")
    if ground_truth.get("embers") != public_state.get("embers"):
        return _fail("public ember paths differ from hidden contract")
    public_rule_ids = [str(rule.get("id") or "") for rule in public_state.get("rules") or []]
    truth_rule_ids = [str(item) for item in ground_truth.get("rule_ids") or []]
    if not truth_rule_ids or public_rule_ids != truth_rule_ids:
        return _fail("public rule stack differs from hidden contract")
    if ground_truth.get("hatchling") != public_state.get("hatchling"):
        return _fail("public hatchling geometry differs from hidden contract")

    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 600:
        return _fail("siege transcript is missing or outside limits", total=len(truth_rule_ids))
    replay = Replay(ground_truth, public_state, interaction)
    replay._update_progress(0)
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(
                f"event {sequence} sequence mismatch",
                highest=replay.highest_rule_index,
                total=len(truth_rule_ids),
            )
        if error := replay.apply(event):
            return _fail(
                f"event {sequence}: {error}",
                highest=replay.highest_rule_index,
                total=len(truth_rule_ids),
            )
    replay.process_time(replay.last_ms)
    all_green = all(replay.results())
    passed = (
        replay.submitted
        and replay.confirmation_started
        and replay.confirmation == replay.confirmation_expected
        and replay.confirmation_expected == replay.text
        and all_green
        and not replay.starved
        and not replay.damaged
    )
    if not replay.submitted:
        feedback = "attempt was never certified"
    elif not replay.confirmation_started:
        feedback = "confirmation phase was never reached"
    elif replay.confirmation != replay.confirmation_expected:
        feedback = "sealed confirmation does not match the authored passphrase"
    elif replay.starved:
        feedback = "the hatchling starved before certification"
    elif replay.damaged:
        feedback = "an ember destroyed the authored text"
    elif not all_green:
        feedback = "one or more live constraint cards are red"
    else:
        feedback = (
            f"all {len(truth_rule_ids)} constraints replay green; "
            f"{len(replay.quenched)} ember(s) quenched; {replay.feed_count} feed(s); exact confirmation"
        )
    return {
        "graded": True,
        "passed": passed,
        "feedback": feedback,
        "highest_rule_index": replay.highest_rule_index,
        "total_rules": len(truth_rule_ids),
        "document_length": len(replay.glyphs),
        "digit_sum": _digit_sum(replay.text),
        "feed_count": replay.feed_count,
        "quenched_embers": len(replay.quenched),
    }
