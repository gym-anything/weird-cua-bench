from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image


ENTRY_ACTIONS = (
    "audit optional",
    "review data",
    "configure privacy",
    "open the processing",
)
FINAL_ACTIONS = (
    "keep only",
    "save selected",
    "my current privacy",
    "confirm these",
)
NEGATIVE_PREFIXES = (
    "do not ",
    "disable ",
    "block ",
    "refuse ",
    "disallow ",
    "prevent ",
    "never ",
    "stop ",
)


def _normalise(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _click_actions(x: float, y: float) -> list[dict[str, Any]]:
    point = [round(x), round(y)]
    return [{"mouse": {"left_click": point}}]


def _drag_actions(
    start_x: float,
    end_x: float,
    y: float,
) -> list[dict[str, Any]]:
    quarter = (end_x - start_x) / 4
    return [
        {"mouse": {"move": [round(start_x), round(y)]}},
        {"mouse": {"buttons": {"left_down": True}}},
        {"mouse": {"move": [round(start_x + quarter), round(y)]}},
        {"mouse": {"move": [round(start_x + 2 * quarter), round(y)]}},
        {"mouse": {"move": [round(start_x + 3 * quarter), round(y)]}},
        {"mouse": {"move": [round(end_x), round(y)]}},
        {"mouse": {"buttons": {"left_up": True}}},
    ]


class ConsentGauntletScreenshotAgent:
    """Task-specific screenshot/OCR policy for authoritative runner evidence.

    The policy is deliberately narrower than a general model agent. It reads
    only the evaluator-delivered PNG, recognises visible text with Tesseract,
    derives switch positions from rendered pixels, and returns native mouse
    actions. It never receives page state, generated truth, DOM access, a URL,
    or a browser handle.
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
        self.processed_drawers: set[str] = set()
        self.current_drawer: str | None = None
        self.last_gateway_stage: str | None = None
        self.last_gateway_task_time_ms: float | None = None
        self.save_path: Path | None = None
        self.display_resolution = (1920, 1080)

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

    def _tesseract(
        self,
        image: Image.Image,
        *,
        psm: int,
        tsv: bool = False,
    ) -> str:
        payload = io.BytesIO()
        image.save(payload, format="PNG")
        command = [
            str(self.agent_args.get("tesseract_binary", "tesseract")),
            "stdin",
            "stdout",
            "--psm",
            str(psm),
        ]
        if tsv:
            command.append("tsv")
        completed = subprocess.run(
            command,
            input=payload.getvalue(),
            check=True,
            capture_output=True,
            timeout=float(self.agent_args.get("inference_timeout_seconds", 10)),
        )
        return completed.stdout.decode("utf-8", errors="replace")

    def _words(self, image: Image.Image) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        reader = csv.DictReader(
            io.StringIO(self._tesseract(image, psm=3, tsv=True)),
            delimiter="\t",
        )
        for item in reader:
            if item.get("level") != "5" or not _normalise(item.get("text") or ""):
                continue
            rows.append(
                {
                    "token": _normalise(item["text"]),
                    "left": int(item["left"]),
                    "top": int(item["top"]),
                    "width": int(item["width"]),
                    "height": int(item["height"]),
                }
            )
        return rows

    @staticmethod
    def _phrase_point(
        words: list[dict[str, Any]],
        phrases: tuple[str, ...],
    ) -> tuple[float, float, str] | None:
        tokens = [item["token"] for item in words]
        for phrase in phrases:
            wanted = _normalise(phrase).split()
            for index in range(0, len(tokens) - len(wanted) + 1):
                if tokens[index : index + len(wanted)] != wanted:
                    continue
                matched = words[index : index + len(wanted)]
                left = min(item["left"] for item in matched)
                top = min(item["top"] for item in matched)
                right = max(item["left"] + item["width"] for item in matched)
                bottom = max(item["top"] + item["height"] for item in matched)
                # The persistent objective can repeat semantic words such as
                # "keep only". Gateway cards occupy the playfield below the
                # header; never turn objective copy into a click coordinate.
                if (top + bottom) / 2 < 140:
                    continue
                return ((left + right) / 2, (top + bottom) / 2, phrase)
        return None

    def _row_centres(self, image: Image.Image) -> list[int]:
        # Each visible purpose row has a solid navy registration bar at the
        # left edge. Derive its vertical spans from pixels rather than a task
        # or DOM description.
        x = round(image.width * 0.1896)
        candidates: list[int] = []
        for y in range(round(image.height * 0.18), round(image.height * 0.86)):
            red, green, blue = image.convert("RGB").getpixel((x, y))
            if red < 45 and green < 65 and blue < 90:
                candidates.append(y)
        groups: list[list[int]] = []
        for y in candidates:
            if not groups or y > groups[-1][-1] + 1:
                groups.append([y])
            else:
                groups[-1].append(y)
        return [
            round((group[0] + group[-1]) / 2)
            for group in groups
            if len(group) >= 35
        ]

    def _visible_orbit_speed(self, image: Image.Image) -> float:
        crop = image.crop(
            (
                round(image.width * 0.885),
                round(image.height * 0.015),
                round(image.width * 0.99),
                round(image.height * 0.095),
            )
        ).resize((800, 320))
        text = self._tesseract(crop, psm=6)
        match = re.search(r"\b(\d{1,2})\s*[^\s]?\s*/\s*s\b", text, re.I)
        if match is None:
            raise RuntimeError(f"could not read visible orbit speed from {text!r}")
        speed = float(match.group(1))
        if not 1 <= speed <= 60:
            raise RuntimeError(f"visible orbit speed is outside the supported range: {speed}")
        return speed

    @staticmethod
    def _shell_origin(image: Image.Image) -> tuple[int, int]:
        rgb = image.convert("RGB")

        def dark(pixel: tuple[int, int, int]) -> bool:
            red, green, blue = pixel
            return red < 55 and green < 75 and blue < 105

        top = next(
            (
                y
                for y in range(round(image.height * 0.12))
                if sum(dark(rgb.getpixel((x, y))) for x in range(0, image.width, 8))
                > image.width / 12
            ),
            0,
        )
        sample_y = min(image.height - 1, top + 35)
        left = next(
            (x for x in range(round(image.width * 0.08)) if dark(rgb.getpixel((x, sample_y)))),
            0,
        )
        return left, top

    def _predict_live_orbit_point(
        self,
        image: Image.Image,
        x: float,
        y: float,
        *,
        horizon: float,
        horizon_source: str,
    ) -> tuple[float, float, dict[str, Any]]:
        left, top = self._shell_origin(image)
        centre_x = left + image.width / 2
        centre_y = top + 92 + (image.height - 148) / 2
        radius_x = image.width * 0.37
        radius_y = (image.height - 148) * 0.31
        phase = math.atan2(
            (y - centre_y) / radius_y,
            (x - centre_x) / radius_x,
        )
        speed = self._visible_orbit_speed(image)
        predicted_phase = phase + math.radians(speed * horizon)
        predicted_x = centre_x + math.cos(predicted_phase) * radius_x
        predicted_y = centre_y + math.sin(predicted_phase) * radius_y
        return predicted_x, predicted_y, {
            "observed_coordinate": [round(x), round(y)],
            "predicted_coordinate": [round(predicted_x), round(predicted_y)],
            "visible_orbit_speed_deg_per_second": speed,
            "prediction_horizon_seconds": horizon,
            "prediction_horizon_source": horizon_source,
            "image_derived_orbit_geometry": {
                "centre": [round(centre_x, 3), round(centre_y, 3)],
                "radii": [round(radius_x, 3), round(radius_y, 3)],
                "shell_origin": [left, top],
            },
        }

    def _live_prediction_horizon(
        self,
        obs: dict[str, Any],
        *,
        stage: str,
    ) -> tuple[float, str]:
        current_ms = float((obs.get("time") or {}).get("task_time_ms") or 0)
        default = float(self.agent_args.get("live_prediction_seconds", 6.1))
        horizon = default
        source = "configured_initial_transport_estimate"
        if (
            self.last_gateway_stage == stage
            and self.last_gateway_task_time_ms is not None
        ):
            measured = (current_ms - self.last_gateway_task_time_ms) / 1000
            if 3 <= measured <= 10:
                horizon = measured
                source = "previous_visible_gateway_cycle"
        self.last_gateway_stage = stage
        self.last_gateway_task_time_ms = current_ms
        return horizon, source

    def _row_text(self, image: Image.Image, centre_y: int) -> str:
        left = round(image.width * 0.215)
        right = round(image.width * 0.78)
        top = max(0, centre_y - 28)
        bottom = min(image.height, centre_y + 28)
        crop = image.crop((left, top, right, bottom))
        return _normalise(self._tesseract(crop, psm=7))

    @staticmethod
    def _switch_state(image: Image.Image, centre_y: int) -> bool:
        rgb = image.convert("RGB")
        handle_centres = {
            False: round(image.width * 0.852),
            True: round(image.width * 0.938),
        }
        scores: dict[bool, int] = {}
        for state, handle_x in handle_centres.items():
            score = 0
            for x in range(handle_x - 10, handle_x + 11):
                for y in range(centre_y - 10, centre_y + 11):
                    if (x - handle_x) ** 2 + (y - centre_y) ** 2 > 10 ** 2:
                        continue
                    red, green, blue = rgb.getpixel((x, y))
                    if red > 220 and green > 220 and blue > 210:
                        score += 1
            scores[state] = score
        state = max(scores, key=scores.get)
        if scores[state] < 80 or abs(scores[False] - scores[True]) < 40:
            raise RuntimeError(f"could not locate visible switch handle near y={centre_y}")
        return state

    @staticmethod
    def _target_from_text(text: str) -> bool:
        # Tesseract may prefix the visible purpose label with its P-number.
        label = re.sub(r"^p[0-9s]+\s+", "", text)
        return label.startswith(NEGATIVE_PREFIXES)

    def _ledger_decision(
        self,
        image: Image.Image,
        full_text: str,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        drawer_match = re.search(r"\b(identity|behaviour) drawer\b", full_text)
        if drawer_match is not None:
            drawer = drawer_match.group(1)
            self.current_drawer = drawer
        elif self.current_drawer is not None:
            drawer = self.current_drawer
        else:
            raise RuntimeError("ledger screenshot did not expose a recognised drawer heading")
        centres = self._row_centres(image)
        if len(centres) != 3:
            raise RuntimeError(f"expected three visible purpose rows, found {centres}")

        row_records: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        false_x = image.width * 0.852
        true_x = image.width * 0.938
        for centre_y in centres:
            label = self._row_text(image, centre_y)
            current = self._switch_state(image, centre_y)
            target = self._target_from_text(label)
            row_records.append(
                {
                    "centre_y": centre_y,
                    "ocr": label,
                    "current": current,
                    "target": target,
                }
            )
            if current != target:
                actions.extend(
                    _drag_actions(
                        true_x if current else false_x,
                        true_x if target else false_x,
                        centre_y,
                    )
                )
        details: dict[str, Any] = {
            "drawer": drawer,
            "visible_rows": row_records,
            "processed_drawers_before": sorted(self.processed_drawers),
        }
        if actions:
            return f"reconcile_{drawer}_switches", actions, details

        self.processed_drawers.add(drawer)
        details["processed_drawers_after"] = sorted(self.processed_drawers)
        if self.processed_drawers == {"identity", "behaviour"}:
            return (
                "review_current_choices",
                _click_actions(image.width * 0.59, image.height * 0.914),
                details,
            )
        other = "behaviour" if drawer == "identity" else "identity"
        self.current_drawer = other
        tab_x = image.width * (0.961 if other == "behaviour" else 0.91)
        return (
            f"open_{other}_drawer",
            _click_actions(tab_x, image.height * 0.151),
            details,
        )

    def step(
        self,
        obs: dict[str, Any],
        action_outputs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        del action_outputs
        self.turn += 1
        screen_path = Path(str((obs.get("screen") or {}).get("path") or ""))
        if not screen_path.is_file():
            raise RuntimeError("screenshot policy received no local obs['screen'] PNG")
        frames = list(obs.get("frames") or [])
        if not frames or Path(str(frames[-1]["path"])).resolve() != screen_path.resolve():
            raise RuntimeError("obs['screen'] is not the final chronological frame")
        with Image.open(screen_path) as opened:
            image = opened.convert("RGB")
        if image.size != self.display_resolution:
            raise RuntimeError(
                f"unexpected screenshot size {image.size}, expected {self.display_resolution}"
            )

        plain_text = self._tesseract(image, psm=3)
        full_text = _normalise(plain_text)
        words = self._words(image)
        details: dict[str, Any] = {}
        if "privacy packet accepted" in full_text or re.search(r"\bpass\b", full_text):
            decision = "finish_after_visible_pass"
            actions: list[dict[str, Any]] = []
            self.done = True
        elif "purpose ledger" in full_text or "optional processing ledger" in full_text or re.search(
            r"\b(identity|behaviour) drawer\b", full_text
        ):
            decision, actions, details = self._ledger_decision(image, full_text)
        elif (
            "final gateway" in full_text
            or "keep your choices" in full_text
            or "commit seal" in full_text
            or "gate 03" in full_text
            or "seal the packet" in full_text
        ):
            target = self._phrase_point(words, FINAL_ACTIONS)
            if target is None:
                raise RuntimeError("OCR did not locate the visible keep-current-choices action")
            x, y, label = target
            prediction: dict[str, Any] = {}
            if str((obs.get("time") or {}).get("mode")) == "live":
                horizon, source = self._live_prediction_horizon(obs, stage="final")
                x, y, prediction = self._predict_live_orbit_point(
                    image,
                    x,
                    y,
                    horizon=horizon,
                    horizon_source=source,
                )
            decision = "click_visible_keep_current_choices_action"
            actions = _click_actions(x, y)
            details = {
                "matched_label": label,
                "coordinate": [round(x), round(y)],
                **prediction,
            }
        elif "notice" in full_text and "dismiss" in full_text:
            target = self._phrase_point(words, ENTRY_ACTIONS)
            if target is None:
                raise RuntimeError("OCR did not locate the visible privacy-controls action")
            x, y, label = target
            prediction = {}
            if str((obs.get("time") or {}).get("mode")) == "live":
                horizon, source = self._live_prediction_horizon(obs, stage="entry")
                x, y, prediction = self._predict_live_orbit_point(
                    image,
                    x,
                    y,
                    horizon=horizon,
                    horizon_source=source,
                )
            decision = "click_visible_privacy_controls_action"
            actions = _click_actions(x, y)
            details = {
                "matched_label": label,
                "coordinate": [round(x), round(y)],
                **prediction,
            }
        else:
            raise RuntimeError(
                f"unrecognised Consent Gauntlet screenshot: {full_text[:300]}"
            )

        row = {
            "turn": self.turn,
            "decision": decision,
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
            "observation_time": obs.get("time"),
            "capture_manifest": obs.get("capture_manifest"),
        }
        self._record(row)
        if self.done:
            return []
        return [{"tool_id": f"consent-screenshot-{self.turn}", "actions": actions}]

    def finish(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
