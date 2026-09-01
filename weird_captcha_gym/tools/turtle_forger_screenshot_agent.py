from __future__ import annotations

import hashlib
import io
import itertools
import json
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps


@dataclass
class VisibleCard:
    family: str
    value: int | str | None
    centre: tuple[int, int]
    text: str
    icon_mask: np.ndarray


@dataclass
class VisibleStroke:
    index: int
    total: int
    line: tuple[float, float, float]
    endpoints: tuple[tuple[float, float], tuple[float, float]]
    pixel_length: float
    colour_name: str
    colour_rgb: tuple[int, int, int]
    frame_path: str
    frame_sha256: str


def _normalise(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _click_actions(x: float, y: float) -> list[dict[str, Any]]:
    return [{"mouse": {"left_click": [round(x), round(y)]}}]


def _drag_actions(
    start: tuple[int, int],
    end: tuple[int, int],
) -> list[dict[str, Any]]:
    start_x, start_y = start
    end_x, end_y = end
    actions: list[dict[str, Any]] = [
        {"mouse": {"move": [start_x, start_y]}},
        {"mouse": {"buttons": {"left_down": True}}},
    ]
    for fraction in (0.2, 0.4, 0.6, 0.8, 1.0):
        actions.append(
            {
                "mouse": {
                    "move": [
                        round(start_x + (end_x - start_x) * fraction),
                        round(start_y + (end_y - start_y) * fraction),
                    ]
                }
            }
        )
    actions.append({"mouse": {"buttons": {"left_up": True}}})
    return actions


class TurtleForgerScreenshotAgent:
    """Task-specific screenshot policy for a complete authoritative solve.

    The policy receives only evaluator-delivered PNG observations. It OCRs the
    visible card drawer and scan counter, measures the rendered transient
    strokes, reconstructs the two closed turtle subprograms and their pen-up
    relocation, then returns native pointer actions. It never receives task
    state, generated truth, a URL, DOM access, or a browser handle.
    """

    autonomous = False

    def __init__(
        self,
        *,
        agent_args: dict[str, Any],
        verbose: bool = False,
        debug: bool = False,
    ) -> None:
        self.agent_args = dict(agent_args)
        self.verbose = verbose
        self.debug = debug
        self.done = False
        self.turn = 0
        self.phase = "start_scan"
        self.display_resolution = (1920, 1080)
        self.save_path: Path | None = None
        self.task_description = ""
        self.cards: list[VisibleCard] = []
        self.strokes: dict[int, VisibleStroke] = {}
        self.expected_strokes: int | None = None
        self.program: list[VisibleCard] = []
        self.program_description: list[str] = []
        self.program_cursor = 0

    def init(
        self,
        task_description: str,
        display_resolution: tuple[int, int],
        save_path: str,
    ) -> None:
        self.task_description = task_description
        self.display_resolution = tuple(display_resolution)
        self.save_path = Path(save_path)
        self.manifest_path = self.save_path / "screenshot_policy_manifest.jsonl"

    def _record(self, row: dict[str, Any]) -> None:
        with self.manifest_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    def _tesseract(self, image: Image.Image, *, psm: int) -> str:
        payload = io.BytesIO()
        image.save(payload, format="PNG")
        completed = subprocess.run(
            [
                str(self.agent_args.get("tesseract_binary", "tesseract")),
                "stdin",
                "stdout",
                "--psm",
                str(psm),
            ],
            input=payload.getvalue(),
            check=True,
            capture_output=True,
            timeout=float(self.agent_args.get("inference_timeout_seconds", 30)),
        )
        return completed.stdout.decode("utf-8", errors="replace")

    def _card_text(self, crop: Image.Image) -> str:
        label_crop = crop.crop((30, 2, crop.width - 4, min(crop.height, 31)))
        rgb_label = label_crop.resize(
            (label_crop.width * 8, label_crop.height * 8)
        )
        gray_label = ImageOps.grayscale(label_crop).resize(
            (label_crop.width * 8, label_crop.height * 8)
        )
        parts = [
            self._tesseract(rgb_label, psm=7),
            self._tesseract(gray_label, psm=7),
        ]
        return _normalise(" ".join(parts))

    @staticmethod
    def _card_from_text(
        text: str,
        centre: tuple[int, int],
        icon_mask: np.ndarray,
    ) -> VisibleCard | None:
        if "close" in text and "loop" in text:
            return VisibleCard("close", None, centre, text, icon_mask)
        if "lift" in text and "pen" in text:
            return VisibleCard("pen_up", None, centre, text, icon_mask)
        if "lower" in text and "pen" in text:
            return VisibleCard("pen_down", None, centre, text, icon_mask)
        if "ink" in text:
            for colour in ("vermilion", "cyan", "jade"):
                if colour in text:
                    return VisibleCard("ink", colour, centre, text, icon_mask)
        loop_match = re.search(r"loop\s*x\s*(\d{1,2})", text)
        if loop_match is not None:
            return VisibleCard("repeat", int(loop_match.group(1)), centre, text, icon_mask)
        advance_match = re.search(r"advance\s*(\d{1,4})", text)
        if advance_match is not None:
            value = int(advance_match.group(1))
            # At this rendered weight Tesseract sometimes treats the trailing
            # edge of a final zero as an extra 6 ("100" -> "1006").
            if value >= 1000 and value % 10 == 6:
                value //= 10
            return VisibleCard("advance", value, centre, text, icon_mask)
        turn_match = re.search(r"turn\s*[a-z]*\s*(\d{1,3})", text)
        if turn_match is not None:
            value = int(turn_match.group(1))
            # The visible degree sign is consistently joined to a final zero
            # as a 6 by Tesseract (90° -> 96°, 120° -> 126°).
            if value % 10 == 6:
                value = (value // 10) * 10
            return VisibleCard("turn", value, centre, text, icon_mask)
        return None

    def _read_cards(self, image: Image.Image) -> list[VisibleCard]:
        width, height = image.size
        lefts = [round(width * 0.7365), round(width * 0.8604)]
        rights = [round(width * 0.8568), round(width * 0.9807)]
        first_top = round(height * 0.1435)
        card_height = round(height * 0.0455)
        cards: list[VisibleCard] = []
        unparsed: list[str] = []
        for row in range(9):
            top = round(first_top + row * height * 0.0495)
            for column, (left, right) in enumerate(zip(lefts, rights)):
                crop = image.crop((left, top, right, top + card_height)).convert("RGB")
                # A blank part of the drawer is dark; card stock is visibly pale.
                if float(np.asarray(crop, dtype=np.float32).mean()) < 95:
                    continue
                text = self._card_text(crop)
                grayscale = np.asarray(ImageOps.grayscale(crop), dtype=np.uint8)
                icon_mask = grayscale[:, : min(40, grayscale.shape[1])] < 145
                centre = (round((left + right) / 2), round(top + card_height / 2))
                card = self._card_from_text(text, centre, icon_mask)
                if card is None:
                    unparsed.append(f"r{row}c{column}:{text}")
                else:
                    cards.append(card)
        required_families = {"close", "pen_up", "pen_down", "ink", "repeat", "advance", "turn"}
        present = {card.family for card in cards}
        if not required_families.issubset(present):
            raise RuntimeError(
                "visible drawer OCR missed required card families; "
                f"present={sorted(present)} unparsed={unparsed}"
            )
        return cards

    def _counter(self, image: Image.Image) -> tuple[int, int, str] | None:
        width, height = image.size
        crop = image.crop(
            (
                round(width * 0.014),
                round(height * 0.730),
                round(width * 0.245),
                round(height * 0.766),
            )
        ).resize((round(width * 0.92), round(height * 0.144)))
        text = _normalise(self._tesseract(crop, psm=7))
        def clean_counter_digit(value: int) -> int:
            # The condensed counter font makes a leading zero look like 6 to
            # Tesseract ("01 / 08" -> "61 68"). Baseline stroke counts are
            # below 30, so the rendered 60-series readings are unambiguous.
            return value - 60 if 60 <= value <= 69 else value

        match = re.search(r"stroke\s*0*(\d+)\s*0*(\d+)\b", text)
        if match is None:
            digits = [int(value) for value in re.findall(r"\b\d{1,2}\b", text)]
            if len(digits) >= 2 and "stroke" in text:
                return clean_counter_digit(digits[-2]), clean_counter_digit(digits[-1]), text
            return None
        return (
            clean_counter_digit(int(match.group(1))),
            clean_counter_digit(int(match.group(2))),
            text,
        )

    def _proof_score(self, image: Image.Image) -> tuple[float | None, str]:
        width, height = image.size
        crop = image.crop(
            (
                round(width * 0.372),
                round(height * 0.737),
                round(width * 0.420),
                round(height * 0.758),
            )
        ).resize((round(width * 0.48), round(height * 0.21)))
        raw = self._tesseract(crop, psm=7).strip()
        # In this condensed score face Tesseract consistently reads zero as 6.
        normalised = raw.replace("6", "0")
        match = re.search(r"(\d{1,3})\s*[.]\s*(\d{2})", normalised)
        if match is None:
            return None, raw
        return float(f"{match.group(1)}.{match.group(2)}"), raw

    def _pass_text(self, image: Image.Image) -> str:
        width, height = image.size
        crop = image.crop(
            (
                round(width * 0.373),
                round(height * 0.137),
                round(width * 0.726),
                round(height * 0.732),
            )
        ).resize((round(width * 0.706), round(height * 1.19)))
        return _normalise(self._tesseract(crop, psm=3))

    @staticmethod
    def _colour_name(rgb: tuple[int, int, int]) -> str:
        red, green, blue = rgb
        if red > green + 35 and red > blue + 35:
            return "vermilion"
        if blue >= green * 0.93 and blue > red * 1.35:
            return "cyan"
        return "jade"

    def _visible_stroke(
        self,
        image: Image.Image,
        *,
        index: int,
        total: int,
        frame_path: Path,
    ) -> VisibleStroke | None:
        width, height = image.size
        left = round(width * 0.0145)
        right = round(width * 0.368)
        top = round(height * 0.137)
        bottom = round(height * 0.730)
        crop = np.asarray(image.convert("RGB"))[top:bottom, left:right]
        red = crop[:, :, 0]
        green = crop[:, :, 1]
        blue = crop[:, :, 2]
        vermilion = (red > 165) & (green < 155) & (blue < 150)
        cyan = (red < 125) & (green > 125) & (blue > 145)
        jade = (red < 140) & (green > 135) & (blue < 180) & (green > blue * 1.08)
        mask = (vermilion | cyan | jade).astype(np.uint8) * 255
        lines = cv2.HoughLinesP(
            mask,
            1,
            np.pi / 1440,
            threshold=20,
            minLineLength=20,
            maxLineGap=18,
        )
        if lines is None:
            return None
        candidates: list[tuple[float, float, tuple[int, int, int, int]]] = []
        for raw in lines[:, 0]:
            row = tuple(int(value) for value in raw)
            x1, y1, x2, y2 = row
            length = math.hypot(x2 - x1, y2 - y1)
            angle = math.atan2(y2 - y1, x2 - x1) % math.pi
            candidates.append((length, angle, row))
        pixel_length = max(item[0] for item in candidates)
        if pixel_length < 24:
            return None
        long_lines = [item for item in candidates if item[0] > pixel_length * 0.60]
        doubled_sine = sum(
            length * math.sin(2 * angle) for length, angle, _row in long_lines
        )
        doubled_cosine = sum(
            length * math.cos(2 * angle) for length, angle, _row in long_lines
        )
        angle = (0.5 * math.atan2(doubled_sine, doubled_cosine)) % math.pi
        direction_x, direction_y = math.cos(angle), math.sin(angle)
        a, b = direction_y, -direction_x
        coloured_y, coloured_x = np.nonzero(mask)
        c = float(np.median(a * coloured_x + b * coloured_y))
        coloured = crop[mask.astype(bool)]
        median = tuple(int(value) for value in np.median(coloured, axis=0))
        return VisibleStroke(
            index=index,
            total=total,
            line=(a, b, c + a * left + b * top),
            endpoints=((0.0, 0.0), (0.0, 0.0)),
            pixel_length=pixel_length,
            colour_name=self._colour_name(median),
            colour_rgb=median,
            frame_path=str(frame_path),
            frame_sha256=hashlib.sha256(frame_path.read_bytes()).hexdigest(),
        )

    def _ingest_frames(self, obs: dict[str, Any]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for frame in list(obs.get("frames") or []):
            frame_path = Path(str(frame.get("path") or ""))
            if not frame_path.is_file():
                raise RuntimeError("screenshot policy received a missing chronological frame")
            with Image.open(frame_path) as opened:
                image = opened.convert("RGB")
            counter = self._counter(image)
            record: dict[str, Any] = {
                "frame_path": str(frame_path),
                "frame_sha256": hashlib.sha256(frame_path.read_bytes()).hexdigest(),
                "counter": None,
            }
            if counter is not None:
                index, total, counter_text = counter
                record["counter"] = {
                    "index": index,
                    "total": total,
                    "ocr": counter_text,
                }
                self.expected_strokes = total
                stroke = self._visible_stroke(
                    image,
                    index=index,
                    total=total,
                    frame_path=frame_path,
                )
                if stroke is not None:
                    current = self.strokes.get(index)
                    if current is None or stroke.pixel_length > current.pixel_length:
                        self.strokes[index] = stroke
                    record["measured_stroke"] = {
                        "index": stroke.index,
                        "pixel_length": round(stroke.pixel_length, 3),
                        "colour_name": stroke.colour_name,
                        "colour_rgb": list(stroke.colour_rgb),
                        "line": [round(value, 6) for value in stroke.line],
                    }
            records.append(record)
        return records

    @staticmethod
    def _intersection(
        first: tuple[float, float, float],
        second: tuple[float, float, float],
    ) -> tuple[float, float]:
        a, b, c = first
        d, e, f = second
        determinant = a * e - b * d
        if abs(determinant) < 1e-5:
            raise RuntimeError("consecutive visible strokes were unexpectedly parallel")
        return ((c * e - b * f) / determinant, (a * f - c * d) / determinant)

    @staticmethod
    def _turn_between(first: float, second: float) -> tuple[str, float]:
        clockwise = (second - first) % 360
        if clockwise <= 180:
            return "right", clockwise
        return "left", 360 - clockwise

    @staticmethod
    def _icon_distance(first: np.ndarray, second: np.ndarray) -> float:
        height = min(first.shape[0], second.shape[0])
        width = min(first.shape[1], second.shape[1])
        return float(np.mean(first[:height, :width] != second[:height, :width]))

    def _one_card(self, family: str, value: int | str | None = None) -> VisibleCard:
        candidates = [
            card
            for card in self.cards
            if card.family == family and (value is None or card.value == value)
        ]
        if len(candidates) != 1:
            raise RuntimeError(
                f"visible drawer lookup {family}/{value!r} returned {len(candidates)} cards"
            )
        return candidates[0]

    def _turn_card(
        self,
        direction: str,
        degrees: float,
        references: dict[str, np.ndarray],
    ) -> VisibleCard:
        turns = [card for card in self.cards if card.family == "turn"]
        nearest_value = min(
            {int(card.value) for card in turns},
            key=lambda value: abs(value - degrees),
        )
        candidates = [card for card in turns if int(card.value) == nearest_value]
        if len(candidates) == 1:
            references.setdefault(direction, candidates[0].icon_mask)
            return candidates[0]
        reference = references.get(direction)
        if reference is not None:
            return min(
                candidates,
                key=lambda card: self._icon_distance(card.icon_mask, reference),
            )
        opposite = "left" if direction == "right" else "right"
        opposite_reference = references.get(opposite)
        if opposite_reference is not None:
            return max(
                candidates,
                key=lambda card: self._icon_distance(card.icon_mask, opposite_reference),
            )
        raise RuntimeError("could not visually disambiguate duplicate turn cards")

    def _derive_program(self) -> tuple[list[VisibleCard], dict[str, Any]]:
        if self.expected_strokes is None or len(self.strokes) != self.expected_strokes:
            raise RuntimeError("the complete visible scan has not been measured")
        ordered = [self.strokes[index] for index in range(1, self.expected_strokes + 1)]
        groups: list[list[VisibleStroke]] = []
        for stroke in ordered:
            if not groups or groups[-1][-1].colour_name != stroke.colour_name:
                groups.append([stroke])
            else:
                groups[-1].append(stroke)
        if len(groups) != 2 or any(len(group) < 3 for group in groups):
            raise RuntimeError(
                f"baseline expected two closed coloured subpaths, got {[len(group) for group in groups]}"
            )

        geometry: list[dict[str, Any]] = []
        for group in groups:
            lines = [stroke.line for stroke in group]
            vertices = [
                self._intersection(lines[index - 1], lines[index])
                for index in range(len(lines))
            ]
            lengths = [
                math.dist(vertices[index], vertices[(index + 1) % len(vertices)])
                for index in range(len(vertices))
            ]
            directions = [
                math.degrees(
                    math.atan2(
                        vertices[(index + 1) % len(vertices)][1] - vertices[index][1],
                        vertices[(index + 1) % len(vertices)][0] - vertices[index][0],
                    )
                )
                for index in range(len(vertices))
            ]
            turn_direction, turn_degrees = self._turn_between(directions[0], directions[1])
            geometry.append(
                {
                    "colour": group[0].colour_name,
                    "count": len(group),
                    "vertices": vertices,
                    "lengths": lengths,
                    "side_pixels": float(np.median(lengths)),
                    "directions": directions,
                    "turn_direction": turn_direction,
                    "turn_degrees": turn_degrees,
                }
            )

        displacement_start = geometry[0]["vertices"][0]
        displacement_end = geometry[1]["vertices"][0]
        displacement_pixels = math.dist(displacement_start, displacement_end)
        measurements = [
            geometry[0]["side_pixels"],
            displacement_pixels,
            geometry[1]["side_pixels"],
        ]
        advance_values = sorted(
            {int(card.value) for card in self.cards if card.family == "advance"}
        )
        best: tuple[float, tuple[int, int, int], float] | None = None
        for values in itertools.product(advance_values, repeat=3):
            scales = [measurement / value for measurement, value in zip(measurements, values)]
            log_scale = sum(math.log(scale) for scale in scales) / len(scales)
            loss = sum((math.log(scale) - log_scale) ** 2 for scale in scales)
            candidate = (loss, values, math.exp(log_scale))
            if best is None or candidate < best:
                best = candidate
        if best is None:
            raise RuntimeError("no visible advance cards were available")
        loss, advance_choice, pixel_scale = best
        if loss > 0.02:
            raise RuntimeError(
                f"visible stroke ratios did not match the drawer advances (loss={loss:.5f})"
            )

        references: dict[str, np.ndarray] = {}
        first_shape_turn = self._turn_card(
            geometry[0]["turn_direction"], geometry[0]["turn_degrees"], references
        )
        second_shape_turn = self._turn_card(
            geometry[1]["turn_direction"], geometry[1]["turn_degrees"], references
        )
        relocation_direction = math.degrees(
            math.atan2(
                displacement_end[1] - displacement_start[1],
                displacement_end[0] - displacement_start[0],
            )
        )
        first_relocation_direction, first_relocation_degrees = self._turn_between(
            geometry[0]["directions"][0], relocation_direction
        )
        second_relocation_direction, second_relocation_degrees = self._turn_between(
            relocation_direction, geometry[1]["directions"][0]
        )
        first_relocation_turn = self._turn_card(
            first_relocation_direction, first_relocation_degrees, references
        )
        second_relocation_turn = self._turn_card(
            second_relocation_direction, second_relocation_degrees, references
        )

        program = [
            self._one_card("ink", geometry[0]["colour"]),
            self._one_card("repeat", geometry[0]["count"]),
            self._one_card("advance", advance_choice[0]),
            first_shape_turn,
            self._one_card("close"),
            self._one_card("pen_up"),
            first_relocation_turn,
            self._one_card("advance", advance_choice[1]),
            second_relocation_turn,
            self._one_card("pen_down"),
            self._one_card("ink", geometry[1]["colour"]),
            self._one_card("repeat", geometry[1]["count"]),
            self._one_card("advance", advance_choice[2]),
            second_shape_turn,
            self._one_card("close"),
        ]
        description = [
            f"{card.family}:{card.value}" if card.value is not None else card.family
            for card in program
        ]
        details = {
            "groups": [
                {
                    "colour": item["colour"],
                    "count": item["count"],
                    "vertices": [
                        [round(point[0], 3), round(point[1], 3)]
                        for point in item["vertices"]
                    ],
                    "side_lengths_pixels": [round(value, 3) for value in item["lengths"]],
                    "median_side_pixels": round(item["side_pixels"], 3),
                    "directions_degrees": [round(value, 3) for value in item["directions"]],
                    "turn": [item["turn_direction"], round(item["turn_degrees"], 3)],
                }
                for item in geometry
            ],
            "relocation_pixels": round(displacement_pixels, 3),
            "relocation_turns": [
                [first_relocation_direction, round(first_relocation_degrees, 3)],
                [second_relocation_direction, round(second_relocation_degrees, 3)],
            ],
            "advance_measurements_pixels": [round(value, 3) for value in measurements],
            "advance_choice": list(advance_choice),
            "fitted_pixels_per_turtle_unit": round(pixel_scale, 6),
            "advance_ratio_loss": round(loss, 8),
            "program": description,
        }
        self.program_description = description
        return program, details

    def step(
        self,
        obs: dict[str, Any],
        action_outputs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        del action_outputs
        self.turn += 1
        screen_path = Path(str((obs.get("screen") or {}).get("path") or ""))
        if not screen_path.is_file():
            raise RuntimeError("screenshot policy received no obs['screen'] PNG")
        frames = list(obs.get("frames") or [])
        if not frames or Path(str(frames[-1]["path"])).resolve() != screen_path.resolve():
            raise RuntimeError("obs['screen'] is not the final chronological frame")
        with Image.open(screen_path) as opened:
            image = opened.convert("RGB")
        if image.size != self.display_resolution:
            raise RuntimeError(
                f"unexpected screenshot size {image.size}, expected {self.display_resolution}"
            )

        full_text = _normalise(self._tesseract(image, psm=3))
        pass_text = self._pass_text(image)
        frame_records: list[dict[str, Any]] = []
        details: dict[str, Any] = {}
        if "pass" in pass_text and "plate accepted" in pass_text:
            decision = "finish_after_visible_pass"
            actions: list[dict[str, Any]] = []
            self.done = True
            details = {"targeted_pass_ocr": pass_text}
        elif self.phase == "start_scan":
            self.cards = self._read_cards(image)
            decision = "click_visible_auto_replay"
            actions = _click_actions(image.width * 0.337, image.height * 0.748)
            self.phase = "observe_scan"
            details = {
                "visible_cards": [
                    {
                        "family": card.family,
                        "value": card.value,
                        "centre": list(card.centre),
                        "ocr": card.text,
                    }
                    for card in self.cards
                ]
            }
        elif self.phase == "observe_scan":
            frame_records = self._ingest_frames(obs)
            if (
                self.expected_strokes is not None
                and len(self.strokes) == self.expected_strokes
                and set(self.strokes) == set(range(1, self.expected_strokes + 1))
            ):
                self.program, details = self._derive_program()
                decision = "drag_reconstructed_program_from_visible_drawer"
                tape_target = (round(image.width * 0.50), round(image.height * 0.865))
                actions = _drag_actions(self.program[0].centre, tape_target)
                self.program_cursor = 1
                self.phase = "build_program"
            else:
                decision = "continue_chronological_scan_observation"
                actions = [{"action": "wait", "time": 0.01}]
                details = {
                    "expected_strokes": self.expected_strokes,
                    "measured_indices": sorted(self.strokes),
                }
        elif self.phase == "build_program":
            if self.program_cursor >= len(self.program):
                raise RuntimeError("program construction cursor exceeded the derived tape")
            card = self.program[self.program_cursor]
            decision = "continue_drag_reconstructed_program"
            tape_target = (round(image.width * 0.50), round(image.height * 0.865))
            actions = _drag_actions(card.centre, tape_target)
            details = {
                "program_card_index": self.program_cursor + 1,
                "program_card": self.program_description[self.program_cursor],
            }
            self.program_cursor += 1
            if self.program_cursor == len(self.program):
                self.phase = "proof"
        elif self.phase == "proof":
            decision = "click_visible_run_proof"
            actions = _click_actions(image.width * 0.70, image.height * 0.113)
            self.phase = "certify"
        elif self.phase == "certify":
            proof_score, proof_score_ocr = self._proof_score(image)
            if proof_score != 100.0:
                raise RuntimeError(
                    "visible proof was not 100.00 percent: "
                    f"targeted_ocr={proof_score_ocr!r} full={full_text[:500]}"
                )
            decision = "click_visible_certify_plate"
            actions = _click_actions(image.width * 0.94, image.height * 0.961)
            self.phase = "await_pass"
            details = {
                "visible_proof_score": proof_score,
                "targeted_score_ocr": proof_score_ocr,
            }
        elif self.phase == "await_pass":
            raise RuntimeError(f"certification did not produce a visible PASS: {full_text[:500]}")
        else:
            raise RuntimeError(f"unknown screenshot-policy phase {self.phase!r}")

        row = {
            "turn": self.turn,
            "decision": decision,
            "phase_after": self.phase,
            "screen_path": str(screen_path),
            "screen_sha256": hashlib.sha256(screen_path.read_bytes()).hexdigest(),
            "frame_count": len(frames),
            "screen_is_last_frame": True,
            "task_description_sha256": hashlib.sha256(
                self.task_description.encode("utf-8")
            ).hexdigest(),
            "visible_task_ui_only_rule_present": (
                "Solve only from screenshots" in self.task_description
                and "visible controls in the task webpage" in self.task_description
                and "Developer Tools" in self.task_description
                and "unrelated tabs" in self.task_description
            ),
            "ocr_excerpt": full_text[:500],
            "actions": actions,
            "details": details,
            "chronological_frame_measurements": frame_records,
            "measured_strokes": {
                str(index): {
                    "pixel_length": round(stroke.pixel_length, 3),
                    "colour_name": stroke.colour_name,
                    "colour_rgb": list(stroke.colour_rgb),
                    "source_frame": stroke.frame_path,
                    "source_frame_sha256": stroke.frame_sha256,
                }
                for index, stroke in sorted(self.strokes.items())
            },
            "program": self.program_description,
            "observation_time": obs.get("time"),
            "capture_manifest": obs.get("capture_manifest"),
        }
        self._record(row)
        if self.done:
            return []
        return [{"tool_id": f"turtle-screenshot-{self.turn}", "actions": actions}]

    def finish(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
