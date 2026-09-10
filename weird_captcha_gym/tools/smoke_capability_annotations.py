#!/usr/bin/env python3
"""Smoke-test capability annotations in an exported dashboard.

This check deliberately goes through the rendered dashboard.  The catalog is
also read through the page so that the assertions describe the same artifact
that a collaborator would see, rather than importing the dashboard's Python
builders directly.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable


LABEL_KEYS = ("visual", "temporal", "reasoning_planning", "exploration_interface")
PROFILE_KEYS = {
    "source_revision",
    "status",
    "baseline",
    "configurations",
    "rationale",
    "configuration_exceptions",
}
BASELINE_ANNOTATION_KEYS = {
    "public_name",
    "real_time",
    "interaction",
    "difficulty",
    "visual",
    "temporal",
    "reasoning_planning",
    "exploration_interface",
}
RATIONALE_OPTIONAL_KEYS = {"configuration_review"}
MODES = ("full", "simplified")
LEVELS = tuple(str(level) for level in range(1, 6))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test baseline capability annotations and configuration changes in an exported dashboard."
    )
    parser.add_argument("--site", type=Path, required=True, help="Exported static dashboard directory")
    parser.add_argument("--out", type=Path, required=True, help="Output directory, or a .json report path")
    return parser.parse_args()


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def output_paths(path: Path) -> tuple[Path, Path]:
    """Return (report path, screenshot directory) for either --out convention."""
    resolved = path.expanduser().resolve()
    if resolved.suffix.lower() == ".json":
        return resolved, resolved.parent
    return resolved / "summary.json", resolved


def error_text(error: BaseException) -> str:
    return str(error).splitlines()[0] or error.__class__.__name__


def labels_for_display(labels: dict[str, Any]) -> dict[str, str]:
    return {
        "visual": str(labels["visual"]),
        "temporal": "Yes" if labels["temporal"] else "No",
        "reasoning_planning": "Yes" if labels["reasoning_planning"] else "No",
        "exploration_interface": "Yes" if labels["exploration_interface"] else "No",
    }


def validate_profile(environment: dict[str, Any]) -> list[str]:
    """Validate the public profile shape and baseline/configuration matrix."""
    problems: list[str] = []
    environment_id = str(environment.get("id") or "<unknown>")
    profile = environment.get("capability_profile_annotations")
    if not isinstance(profile, dict):
        return []
    if set(profile) != PROFILE_KEYS:
        problems.append(f"{environment_id}: profile keys are {sorted(profile)}, expected {sorted(PROFILE_KEYS)}")

    source_revision = profile.get("source_revision")
    if not isinstance(source_revision, str) or not source_revision.strip():
        problems.append(f"{environment_id}: source_revision is empty")
    status = profile.get("status")
    if not isinstance(status, str) or not status.strip():
        problems.append(f"{environment_id}: status is empty")

    baseline = profile.get("baseline")
    if (
        not isinstance(baseline, dict)
        or set(baseline) != {"difficulty", "interaction"}
        or type(baseline.get("difficulty")) is not int
        or baseline.get("difficulty") not in range(1, 6)
        or baseline.get("interaction") not in MODES
    ):
        problems.append(f"{environment_id}: invalid baseline {baseline!r}")
        baseline = None

    control = environment.get("difficulty_control") or {}
    if baseline is not None and control:
        if int(control.get("baseline_level", 0)) != baseline["difficulty"]:
            problems.append(f"{environment_id}: profile/control baseline difficulty disagrees")
        if str(control.get("baseline_interaction")) != baseline["interaction"]:
            problems.append(f"{environment_id}: profile/control baseline interaction disagrees")

    configurations = profile.get("configurations")
    if not isinstance(configurations, dict) or set(configurations) != set(MODES):
        problems.append(f"{environment_id}: configurations must contain full and simplified")
        configurations = {}
    for mode in MODES:
        mode_config = configurations.get(mode)
        if not isinstance(mode_config, dict) or set(mode_config) != set(LEVELS):
            problems.append(f"{environment_id}: {mode} configurations must contain levels 1-5")
            continue
        for level in LEVELS:
            labels = mode_config[level]
            if not isinstance(labels, dict) or set(labels) != set(LABEL_KEYS):
                problems.append(f"{environment_id}: {mode} L{level} labels have the wrong shape")
                continue
            if labels["visual"] not in {"2D", "3D"}:
                problems.append(f"{environment_id}: {mode} L{level} visual label is invalid")
            for key in LABEL_KEYS[1:]:
                if type(labels[key]) is not bool:
                    problems.append(f"{environment_id}: {mode} L{level} {key} is not boolean")

    rationale = profile.get("rationale")
    rationale_keys = set(rationale) if isinstance(rationale, dict) else set()
    allowed_rationale_keys = set(LABEL_KEYS) | RATIONALE_OPTIONAL_KEYS
    if not isinstance(rationale, dict) or not set(LABEL_KEYS).issubset(rationale_keys) or not rationale_keys.issubset(allowed_rationale_keys):
        problems.append(f"{environment_id}: rationale has the wrong shape")
    elif any(not isinstance(rationale[key], str) or not rationale[key].strip() for key in LABEL_KEYS):
        problems.append(f"{environment_id}: rationale contains an empty explanation")

    if not isinstance(profile.get("configuration_exceptions"), list):
        problems.append(f"{environment_id}: configuration_exceptions is not a list")
    return problems


def validate_baseline_annotation(environment: dict[str, Any]) -> list[str]:
    """Validate the baseline annotation shown for every built environment."""
    environment_id = str(environment.get("id") or "<unknown>")
    annotation = environment.get("capability_annotation")
    if not isinstance(annotation, dict):
        return [f"{environment_id}: missing capability_annotation"]
    problems: list[str] = []
    if set(annotation) != BASELINE_ANNOTATION_KEYS:
        problems.append(f"{environment_id}: baseline annotation keys are {sorted(annotation)}")
    if annotation.get("public_name") != environment.get("title"):
        problems.append(f"{environment_id}: baseline public_name does not match the dashboard title")
    if annotation.get("real_time") not in {None, "yes", "no", "observation_only"}:
        problems.append(f"{environment_id}: invalid baseline real_time {annotation.get('real_time')!r}")
    if annotation.get("visual") not in {"2D", "3D"}:
        problems.append(f"{environment_id}: invalid baseline visual label")
    for key in LABEL_KEYS[1:]:
        if type(annotation.get(key)) is not bool:
            problems.append(f"{environment_id}: baseline {key} is not boolean")
    for key in ("interaction", "difficulty"):
        if not isinstance(annotation.get(key), str) or not annotation[key].strip():
            problems.append(f"{environment_id}: baseline {key} is empty")
    profile = environment.get("capability_profile_annotations")
    if isinstance(profile, dict) and isinstance(profile.get("baseline"), dict):
        baseline = profile["baseline"]
        configurations = profile.get("configurations") or {}
        labels = (configurations.get(baseline.get("interaction")) or {}).get(str(baseline.get("difficulty")))
        if isinstance(labels, dict):
            for key in LABEL_KEYS:
                if annotation.get(key) != labels.get(key):
                    problems.append(f"{environment_id}: baseline {key} disagrees with its profile")
    return problems


def read_catalog(page: Any) -> dict[str, Any]:
    return page.evaluate("async () => await (await fetch('data/catalog.json')).json()")


def wait_for_detail(page: Any) -> None:
    page.wait_for_selector("#capability-assessment-title", state="visible", timeout=10_000)
    page.wait_for_function(
        """() => document.querySelectorAll('.capability-core-list > div').length === 4""",
        timeout=10_000,
    )


def read_detail_values(page: Any) -> dict[str, str]:
    values = page.evaluate(
        """() => {
          const rows = [...document.querySelectorAll('.capability-core-list > div')];
          const realTime = [...document.querySelectorAll('.capability-knob-list > div')]
            .find(row => row.querySelector('dt')?.textContent.trim().toLowerCase() === 'real time');
          return {
            visual: rows[0]?.querySelector('dd')?.textContent.trim() || '',
            temporal: rows[1]?.querySelector('dd')?.textContent.trim() || '',
            reasoning_planning: rows[2]?.querySelector('dd')?.textContent.trim() || '',
            exploration_interface: rows[3]?.querySelector('dd')?.textContent.trim() || '',
            real_time: realTime?.querySelector('dd')?.textContent.trim() || '',
          };
        }"""
    )
    if any(not values.get(key) for key in LABEL_KEYS):
        raise AssertionError(f"detail capability rows are incomplete: {values!r}")
    return values


def wait_for_detail_values(page: Any, expected: dict[str, str]) -> dict[str, str]:
    page.wait_for_function(
        """expected => {
          const rows = [...document.querySelectorAll('.capability-core-list > div')];
          if (rows.length !== 4) return false;
          const values = rows.map(row => row.querySelector('dd')?.textContent.trim() || '');
          return values.every((value, index) => value === expected[['visual', 'temporal', 'reasoning_planning', 'exploration_interface'][index]]);
        }""",
        arg=expected,
        timeout=5_000,
    )
    return read_detail_values(page)


def expected_caption(level: int, mode: str) -> str:
    return f"Selected L{level} · {mode.capitalize()} · source review"


def assert_selected_caption(page: Any, level: int, mode: str) -> None:
    caption = expected_caption(level, mode)
    page.wait_for_function(
        "caption => document.querySelector('.capability-assessment')?.textContent.includes(caption) === true",
        arg=caption,
        timeout=5_000,
    )


def click_difficulty(page: Any, environment_id: str, level: int) -> None:
    button = page.locator(
        f'button[data-difficulty-environment="{environment_id}"][data-difficulty-level="{level}"]'
    )
    if button.count() != 1:
        raise AssertionError(f"expected one difficulty button for {environment_id} L{level}, found {button.count()}")
    button.click()


def click_interaction(page: Any, environment_id: str, mode: str) -> None:
    button = page.locator(
        f'button[data-interaction-environment="{environment_id}"][data-interaction-mode="{mode}"]'
    )
    if button.count() != 1:
        raise AssertionError(f"expected one {mode} button for {environment_id}, found {button.count()}")
    button.click()


def visit_detail(page: Any, base_url: str, environment: dict[str, Any]) -> dict[str, str]:
    environment_id = str(environment["id"])
    page.goto(f"{base_url}/#/environment/{environment_id}", wait_until="networkidle")
    if f"#/environment/{environment_id}" not in page.url:
        raise AssertionError(f"dashboard did not stay on the requested route: {page.url}")
    wait_for_detail(page)
    return read_detail_values(page)


def main() -> int:
    args = parse_args()
    site = args.site.expanduser().resolve()
    report_path, screenshot_dir = output_paths(args.out)
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "ok": False,
        "site": str(site),
        "counts": {},
        "checks": {},
        "screenshots": [],
        "errors": [],
    }
    if not site.is_dir():
        report["errors"].append({"check": "site", "error": f"site is not a directory: {site}"})
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1

    server: ThreadingHTTPServer | None = None
    thread: threading.Thread | None = None
    browser: Any = None

    def record_error(check: str, error: BaseException) -> None:
        report["errors"].append({"check": check, "error": error_text(error)})

    def run_check(name: str, check: Callable[[], Any]) -> Any:
        try:
            value = check()
            report["checks"][name] = {"ok": True, "result": value}
            return value
        except Exception as error:  # noqa: BLE001 - report every check before exiting.
            report["checks"][name] = {"ok": False, "error": error_text(error)}
            record_error(name, error)
            return None

    try:
        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, name="capability-smoke-http", daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"

        # Keep the Playwright import inside main so --help remains available in
        # environments that have not installed the optional browser package.
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
            page = context.new_page()
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))

            page.goto(f"{base_url}/#/environments", wait_until="networkidle")
            page.wait_for_selector("#environment-grid", state="visible", timeout=10_000)
            catalog = read_catalog(page)
            built = [item for item in catalog.get("environments", []) if item.get("stage") == "built"]
            report["counts"]["built"] = len(built)
            if len(built) != 155:
                record_error("built_count", AssertionError(f"expected 155 built environments, found {len(built)}"))

            baseline_errors = [problem for environment in built for problem in validate_baseline_annotation(environment)]
            profile_errors = [problem for environment in built for problem in validate_profile(environment)]
            profile_count = sum(isinstance(environment.get("capability_profile_annotations"), dict) for environment in built)
            report["counts"]["baseline_annotations"] = len(built) - len({problem.split(":", 1)[0] for problem in baseline_errors})
            report["counts"]["profile_annotations"] = profile_count
            report["counts"]["baseline_annotation_errors"] = len(baseline_errors)
            report["counts"]["profile_annotation_errors"] = len(profile_errors)
            if baseline_errors:
                report["errors"].extend({"check": "baseline_annotations", "error": problem} for problem in baseline_errors)
            if profile_errors:
                report["errors"].extend({"check": "profile_annotations", "error": problem} for problem in profile_errors)
            if profile_count != 80:
                record_error("profile_annotation_count", AssertionError(f"expected 80 source-reviewed profiles, found {profile_count}"))
            report["checks"]["baseline_annotations"] = {
                "ok": not baseline_errors and not profile_errors and len(built) == 155 and profile_count == 80,
                "result": {"built": len(built), "annotated": len(built) - len({problem.split(':', 1)[0] for problem in baseline_errors}), "source_review_profiles": profile_count},
            }

            def filter_check() -> dict[str, Any]:
                page.goto(f"{base_url}/#/environments", wait_until="networkidle")
                page.wait_for_selector("#environment-grid", state="visible", timeout=10_000)
                checks: dict[str, Any] = {}
                for group, value, profile_field in (
                    ("visual", "2D", "visual"),
                    ("core", "temporal", "temporal"),
                    ("core", "reasoning_planning", "reasoning_planning"),
                    ("core", "exploration_interface", "exploration_interface"),
                ):
                    expected_ids: set[str] = set()
                    for environment in built:
                        profile = environment.get("capability_profile_annotations")
                        if isinstance(profile, dict):
                            baseline = profile["baseline"]
                            labels = profile["configurations"][baseline["interaction"]][str(baseline["difficulty"])]
                        else:
                            labels = environment["capability_annotation"]
                        matches = labels[profile_field] == value if profile_field == "visual" else labels[profile_field] is True
                        if matches:
                            expected_ids.add(str(environment["id"]))
                    chip = page.locator(f'button[data-capability-group="{group}"][data-capability-value="{value}"]')
                    if chip.count() != 1:
                        raise AssertionError(f"missing {group}={value} capability filter")
                    chip.click()
                    cards = set(page.locator("#environment-grid .environment-card[data-open-env]").evaluate_all("nodes => nodes.map(node => node.dataset.openEnv)"))
                    count_text = page.locator(".catalog-count").inner_text().strip()
                    shown = int(re.match(r"^(\d+)", count_text).group(1)) if re.match(r"^(\d+)", count_text) else -1
                    if cards != expected_ids or shown != len(expected_ids):
                        raise AssertionError(f"{group}={value} showed {shown}/{len(cards)}, expected {len(expected_ids)}")
                    checks[f"{group}={value}"] = len(cards)
                    if group == "core" and value == "temporal":
                        path = screenshot_dir / "capability-filter-temporal.png"
                        page.screenshot(path=str(path), full_page=False)
                        report["screenshots"].append(str(path))
                    chip.click()
                return checks

            run_check("baseline_filters", filter_check)

            by_id = {str(item["id"]): item for item in built}

            def transition_check(environment_id: str, start_level: int, end_level: int, field: str, expected_start: bool, expected_end: bool) -> dict[str, Any]:
                environment = by_id[environment_id]
                profile = environment["capability_profile_annotations"]
                mode = str(profile["baseline"]["interaction"])
                start = labels_for_display(profile["configurations"][mode][str(start_level)])
                end = labels_for_display(profile["configurations"][mode][str(end_level)])
                visit_detail(page, base_url, environment)
                click_difficulty(page, environment_id, start_level)
                values = wait_for_detail_values(page, start)
                click_interaction(page, environment_id, mode)
                values = wait_for_detail_values(page, start)
                assert_selected_caption(page, start_level, mode)
                if values[field] != start[field]:
                    raise AssertionError(f"{environment_id} L{start_level} route value {field}={values[field]!r}, expected {start[field]!r}")
                click_difficulty(page, environment_id, end_level)
                values = wait_for_detail_values(page, end)
                assert_selected_caption(page, end_level, mode)
                expected = "Yes" if expected_end else "No"
                if values[field] != expected:
                    raise AssertionError(f"{environment_id} L{end_level} {field}={values[field]!r}, expected {expected!r}")
                path_start = screenshot_dir / f"capability-{environment_id}-L{start_level}.png"
                page.goto(f"{base_url}/#/environment/{environment_id}", wait_until="networkidle")
                wait_for_detail(page)
                click_difficulty(page, environment_id, start_level)
                wait_for_detail_values(page, start)
                click_interaction(page, environment_id, mode)
                wait_for_detail_values(page, start)
                assert_selected_caption(page, start_level, mode)
                page.locator(".capability-assessment").screenshot(path=str(path_start))
                report["screenshots"].append(str(path_start))
                path_end = screenshot_dir / f"capability-{environment_id}-L{end_level}.png"
                click_difficulty(page, environment_id, end_level)
                wait_for_detail_values(page, end)
                assert_selected_caption(page, end_level, mode)
                page.locator(".capability-assessment").screenshot(path=str(path_end))
                report["screenshots"].append(str(path_end))
                expected = "Yes" if expected_start else "No"
                if start[field] != expected:
                    raise AssertionError(f"{environment_id} catalog L{start_level} {field}={start[field]!r}, expected {expected!r}")
                return {"mode": mode, "start": start[field], "end": values[field]}

            run_check(
                "fluke_census_temporal",
                lambda: transition_check("fluke_census_env", 1, 4, "temporal", False, True),
            )
            run_check(
                "restless_piston_temporal",
                lambda: transition_check("restless_piston_env", 1, 3, "temporal", False, True),
            )
            run_check(
                "pocket_locksmith_exploration",
                lambda: transition_check("pocket_locksmith_env", 1, 4, "exploration_interface", False, True),
            )

            def apothecary_interaction_check() -> dict[str, str]:
                environment = by_id["apothecary_dead_reckoning_env"]
                profile = environment["capability_profile_annotations"]
                if profile["baseline"] != {"difficulty": 2, "interaction": "full"}:
                    raise AssertionError(f"Apothecary baseline changed: {profile['baseline']!r}")
                full = labels_for_display(profile["configurations"]["full"]["2"])
                simplified = labels_for_display(profile["configurations"]["simplified"]["2"])
                visit_detail(page, base_url, environment)
                click_difficulty(page, environment["id"], 2)
                click_interaction(page, environment["id"], "full")
                full_values = wait_for_detail_values(page, full)
                assert_selected_caption(page, 2, "full")
                click_interaction(page, environment["id"], "simplified")
                simplified_values = wait_for_detail_values(page, simplified)
                assert_selected_caption(page, 2, "simplified")
                if full_values["temporal"] != "Yes" or simplified_values["temporal"] != "No":
                    raise AssertionError(f"Apothecary temporal interaction change was not rendered: {full_values} -> {simplified_values}")
                return {"full_temporal": full_values["temporal"], "simplified_temporal": simplified_values["temporal"]}

            run_check("apothecary_interaction_temporal", apothecary_interaction_check)

            def cockpit_baseline_check() -> dict[str, str]:
                environment = by_id["cockpit_preflight_checklist_env"]
                profile = environment["capability_profile_annotations"]
                mode = str(profile["baseline"]["interaction"])
                level = str(profile["baseline"]["difficulty"])
                expected = labels_for_display(profile["configurations"][mode][level])
                if expected["exploration_interface"] != "No":
                    raise AssertionError(f"Cockpit baseline exploration is invented as {expected['exploration_interface']}")
                values = visit_detail(page, base_url, environment)
                assert_selected_caption(page, int(level), mode)
                if values["exploration_interface"] != "No":
                    raise AssertionError(f"Cockpit baseline UI exploration is {values['exploration_interface']}")
                return {"exploration_interface": values["exploration_interface"]}

            run_check("cockpit_baseline_exploration", cockpit_baseline_check)

            def unknown_real_time_check() -> dict[str, str]:
                environment = by_id["fluke_census_env"]
                values = visit_detail(page, base_url, environment)
                shown = values.get("real_time", "")
                if shown != "Not reviewed":
                    raise AssertionError(f"unknown real-time annotation rendered as {shown!r}, expected 'Not reviewed'")
                return {"environment": environment["title"], "real_time": shown}

            run_check("unknown_real_time_is_not_invented", unknown_real_time_check)

            report["counts"]["routes_exercised"] = len(report["checks"])
            report["counts"]["page_errors"] = len(page_errors)
            if page_errors:
                report["errors"].extend({"check": "pageerror", "error": error} for error in page_errors)
    except Exception as error:  # noqa: BLE001 - still emit a machine-readable report.
        record_error("runner", error)
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=3)

    report["ok"] = not report["errors"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
