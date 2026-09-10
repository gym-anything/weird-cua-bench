"""Headless implementation checks using the repository's existing UI solvers.

These are privileged wiring checks, not screenshot-only model evaluations.
Every browser is a new headless Chromium process with a fresh temporary profile.
"""

import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def run(case_index, level, mode, seed, failure=False, scroll_atp_diagnostic=False, premature_submit_diagnostic=False, rayglass_select_diagnostic=False, rayglass_option_diagnostic=False, hearth_carry_first_diagnostic=False, crack_tile_edge_diagnostic=False, rising_reconfigure_diagnostic=False, five_scaled_flick_diagnostic=False, letter_fast_poll_diagnostic=False):
    manifest = read(ROOT / "manifest.json")
    case = next(c for c in manifest["cases"] if c["case_index"] == case_index)
    source = Path(manifest["source_root"])
    sys.path.insert(0, str(source))
    bench = source / "weird_captcha_gym"
    helper = load(bench / "tools/smoke_incubator_batch_one_ui.py", "pilot_smoke_helper")
    mechanic = case["environment_id"].removesuffix("_env")
    suffix = "failure" if failure else "solve"
    name = f"{case_index:03d}_{mechanic}_d{level}_{mode}_seed{seed}_{suffix}"
    if scroll_atp_diagnostic:
        assert mechanic == "cell_gatekeeper" and mode == "full" and not failure
        name += "_scroll_atp_diagnostic"
    if premature_submit_diagnostic:
        assert mechanic == "clockbeat_catacomb" and failure
        name += "_premature_submit_diagnostic"
    if rayglass_select_diagnostic:
        assert mechanic == "rayglass_vault" and mode == "simplified"
        name += "_rayglass_select_diagnostic"
    if rayglass_option_diagnostic:
        assert mechanic == "rayglass_vault" and mode == "simplified" and not rayglass_select_diagnostic
        name += "_rayglass_option_diagnostic"
    if hearth_carry_first_diagnostic:
        assert mechanic == "hearthlift_courier" and not failure
        name += "_hearth_carry_first_diagnostic"
    if crack_tile_edge_diagnostic:
        assert mechanic == "crackglaze_crossing" and mode == "full" and not failure
        name += "_crack_tile_edge_diagnostic"
    if rising_reconfigure_diagnostic:
        assert mechanic == "rising_causeway" and not failure
        name += "_rising_reconfigure_diagnostic"
    if five_scaled_flick_diagnostic:
        assert mechanic == "five_second_rule" and mode == "full" and not failure
        name += "_five_scaled_flick_diagnostic"
    if letter_fast_poll_diagnostic:
        assert mechanic == "letter_rapids" and not failure
        name += "_letter_fast_poll_diagnostic"
    out = ROOT / "outputs" / "browser" / name
    out.mkdir(parents=True, exist_ok=False)
    screenshot_dir = ROOT / "screenshots" / name
    screenshot_dir.mkdir(parents=True, exist_ok=False)
    evidence_dir = ROOT / "browser_checks"
    evidence_dir.mkdir(exist_ok=True)
    record = {"case_index": case_index, "environment_id": case["environment_id"], "public_name": case["public_name"],
              "difficulty": level, "interaction": mode, "seed": seed, "check": suffix,
              "headless": True, "fresh_browser_profile": True, "viewport": [1920, 1080],
              "source_revision": manifest["source_revision"], "scope": "Privileged existing-solver wiring check; not an agent difficulty measurement"}
    state_dir = out / "state"
    state_dir.mkdir()
    generated = ROOT / "outputs" / "generation" / mechanic / f"d{level}_{mode}_seed{seed}"
    task = read(generated / "task.json")
    public = read(generated / "public_state.json")
    truth = read(generated / "ground_truth.json")
    write(state_dir / "public_state.json", public)
    write(state_dir / "ground_truth.json", truth)
    token = "difficulty-audit-" + name
    write(state_dir / "current_task.json", {"task": task, "seed": str(seed), "attempt": 0, "client_task_token": token})
    # The existing /state task-token contract prevents initial navigation from
    # regenerating the fixed-seed challenge. No UI or grading code is changed.
    server = None
    started = time.monotonic()
    try:
        diagnostic = any((scroll_atp_diagnostic, premature_submit_diagnostic, rayglass_select_diagnostic, rayglass_option_diagnostic, hearth_carry_first_diagnostic, crack_tile_edge_diagnostic, rising_reconfigure_diagnostic, five_scaled_flick_diagnostic, letter_fast_poll_diagnostic))
        port = (24800 if diagnostic else 19800) + case_index
        with (out / "server.log").open("x") as server_log:
            server = subprocess.Popen([sys.executable, "-B", str(bench / "shared_runtime/server/weird_captcha_server.py"),
                "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(bench / "shared_runtime/app"),
                "--state-dir", str(state_dir)], cwd=source,
                env={**os.environ, "WEIRD_CAPTCHA_CHALLENGE_SEED": f"pilot-{mechanic}-{seed}"},
                stdout=server_log, stderr=server_log)
            deadline = time.monotonic() + 15
            while True:
                if server.poll() is not None:
                    raise RuntimeError("isolated loopback server exited before health check")
                try:
                    urlopen(f"http://127.0.0.1:{port}/health", timeout=.5).read()
                    break
                except Exception:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("isolated loopback server did not become healthy")
                    time.sleep(.1)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                    record["browser_errors"] = errors
                    page.set_default_timeout(15000)
                    page.goto(f"http://127.0.0.1:{port}/?task={token}", wait_until="networkidle")
                    page.wait_for_function("mechanic => Boolean(window.WeirdCaptchaMechanics?.[mechanic]?.rootSelector)", arg=mechanic)
                    selector = page.evaluate("mechanic => window.WeirdCaptchaMechanics[mechanic].rootSelector", mechanic)
                    page.locator(selector).wait_for(state="visible")
                    page.screenshot(path=str(screenshot_dir / "initial.png"), full_page=True)
                    assert read(state_dir / "public_state.json") == public, "initial navigation changed the frozen state"
                    assert read(state_dir / "ground_truth.json") == truth, "initial navigation changed frozen truth"
                    record["initial_fixed_seed_preserved"] = True
                    solver = load(bench / "tools/incubator_solvers" / f"{mechanic}.py", f"pilot_solver_{mechanic}")
                    if letter_fast_poll_diagnostic:
                        def fast_output_wait(page, output, timeout=8000):
                            page.wait_for_function("output => document.querySelector('.rapids-output-value')?.getAttribute('data-output') === output", arg=output, polling=16, timeout=timeout)
                        solver._wait_output = fast_output_wait
                        record["solver_adjustment"] = "Separate harness diagnostic: poll the displayed output attribute every 16 ms instead of the default assertion polling schedule. All inputs, target, live clock, travel budget, physics and grading remain unchanged. DOM-observation wiring evidence, not screenshot-only agent performance; original failures remain preserved."
                    if five_scaled_flick_diagnostic:
                        original_flick = solver._solve_flick
                        def scaled_flick(page, spec, mode):
                            box = page.locator(".fsr-stage").bounding_box()
                            vertical = spec["flick"]["flick_direction"] in ("NORTH", "SOUTH")
                            scale = box["height"] / 390 if vertical else box["width"] / 820
                            adjusted = copy.deepcopy(spec)
                            original_distance = float(spec["flick"]["min_travel_px"]) + 24
                            adjusted["flick"]["min_travel_px"] = original_distance * scale - 24
                            record["flick_coordinate_conversion"] = {"stage_bounds": box, "axis_scale": scale,
                                "intended_logical_distance": original_distance, "commanded_screen_distance": original_distance * scale}
                            original_flick(page, adjusted, mode)
                        solver._solve_flick = scaled_flick
                        record["solver_adjustment"] = "Separate harness diagnostic: convert the oracle's intended logical flick distance to screen pixels using the rendered stage size. Only the solver-local drag-distance calculation changes; puzzle state, rules, timing and grader are unchanged. Original errors remain preserved."
                    if rising_reconfigure_diagnostic:
                        wrong_side = "right" if truth["required_stair_end"] == "left" else "left"
                        if mode == "simplified":
                            page.locator(f'[data-rising-action="stair-{wrong_side}"]').click()
                        else:
                            yellow = truth["world"]["chamber"]["actuators"][1]["position"]
                            offset = -.76 if wrong_side == "left" else .76
                            solver._click_world(page, [yellow[0], yellow[1] + offset, yellow[2] + (.16 if wrong_side == "right" else 0)])
                        record["wrong_stair_before_reconfiguration"] = solver._model(page)
                        assert record["wrong_stair_before_reconfiguration"]["stairEnd"] == wrong_side
                        assert not record["wrong_stair_before_reconfiguration"]["failed"]
                        page.screenshot(path=str(screenshot_dir / "wrong-stair-before-reconfiguration.png"), full_page=True)
                        record["solver_adjustment"] = "Separate recovery diagnostic: select the wrong stair end through the visible input surface, then run the unchanged solver which selects the other end before traversal. No reset, regeneration, task edit or hidden-state write. Private geometry is used only by this wiring oracle."
                    if crack_tile_edge_diagnostic:
                        original_step = solver._step
                        def visible_tile_edge(page, state, origin, destination):
                            if record.get("edge_click"):
                                return original_step(page, state, origin, destination)
                            target = next(cell for cell in state["cells"] if cell["id"] == destination)
                            point = page.evaluate("""({target, rows, columns}) => {
                                const tile = document.querySelector(`[data-cell-id="${target.id}"]`);
                                const box = tile.getBoundingClientRect();
                                const board = document.querySelector('.crack-board').getBoundingClientRect();
                                for (const fx of [.03, .97, .5]) for (const fy of [.03, .97, .5]) {
                                    const x = box.x + box.width * fx, y = box.y + box.height * fy;
                                    if (document.elementFromPoint(x, y)?.closest('[data-cell-id]') !== tile) continue;
                                    const p = [(x-board.x)/board.width, (y-board.y)/board.height];
                                    const r = [target.column/columns, target.row/rows, 1/columns, 1/rows];
                                    if (p[0] < r[0]-.008 || p[0] > r[0]+r[2]+.008 || p[1] < r[1]-.008 || p[1] > r[1]+r[3]+.008)
                                        return {x, y, normalized: p, ideal_rect: r, target: target.id, actual_hit_target: tile.dataset.cellId};
                                }
                                return null;
                            }""", {"target": target, "rows": state["rows"], "columns": state["columns"]})
                            if point:
                                record["edge_click"] = point
                                page.screenshot(path=str(screenshot_dir / "before-visible-edge-click.png"), full_page=True)
                                page.mouse.click(point["x"], point["y"])
                                record["edge_click"]["browser_position_after_click"] = page.locator(".crackglaze-crossing").get_attribute("data-position")
                            else:
                                original_step(page, state, origin, destination)
                        solver._step = visible_tile_edge
                        record["solver_adjustment"] = "Separate geometry diagnostic: one real pointer click inside the visible tile hit target but outside the grader's ideal unpadded cell rectangle; all other inputs use the unchanged oracle. DOM-assisted hit-target diagnostics, not a screenshot-agent evaluation. No task modification."
                    if hearth_carry_first_diagnostic:
                        diagnostic_module = load(ROOT / "check_hearthlift_carry_first.py", "carry_first_browser_diagnostic")
                        def carry_first_solve(page, state_dir, screenshot_dir, mechanic):
                            for action in diagnostic_module.carry_first_actions(truth):
                                solver._action(page, action, mode)
                                page.wait_for_timeout(18)
                            page.screenshot(path=str(screenshot_dir / "carry-first-before-certify.png"), full_page=True)
                            page.locator(".hl-submit").click()
                            from playwright.sync_api import expect
                            expect(page.locator(".hl-readout")).to_have_text("PASS", timeout=15000)
                        solver.solve = carry_first_solve
                        record["solver_adjustment"] = "Separate carry-first diagnostic: orbit, immediately pick up cargo, climb each unmoved helper, walk to the hearth, and drop. Uses the existing visible input helpers, not source or state modification. Original canonical run is preserved."
                    if rayglass_select_diagnostic:
                        def closed_select_keyboard(page, selector, index):
                            control = page.locator(selector)
                            control.focus()
                            control.press("Home")
                            for _ in range(index):
                                control.press("ArrowDown")
                            control.press("Tab")
                            actual = control.input_value()
                            record.setdefault("select_diagnostic_values", []).append({"selector": selector, "requested": index, "actual": actual})
                            assert actual == str(index), "closed select keyboard did not select requested visible option"
                        solver.choose = closed_select_keyboard
                        record["solver_adjustment"] = "Separate harness diagnostic: focus the existing closed native select and use Home/ArrowDown/Tab, verifying its value. No task source/state mutation; original click-open-dropdown errors are preserved. Not screenshot-only agent evidence."
                    if rayglass_option_diagnostic:
                        def native_select_option(page, selector, index):
                            control = page.locator(selector)
                            label = control.locator("option").nth(index).inner_text()
                            control.select_option(index=index)
                            record.setdefault("select_diagnostic_values", []).append({"selector": selector, "option_label": label, "requested": index, "actual": control.input_value()})
                            assert control.input_value() == str(index)
                        solver.choose = native_select_option
                        record["solver_adjustment"] = "Separate DOM-assisted harness diagnostic: Playwright selects an existing native dropdown option by index, then the solver clicks the existing FIRE/MARK buttons. This is not primitive-input or screenshot-only evidence. No puzzle code or hidden task truth is changed; both earlier keyboard failures are preserved."
                    if scroll_atp_diagnostic:
                        original_supply = solver._supply
                        def scroll_then_supply(page, state, mode, units):
                            token_locator = page.locator("[data-atp-token]")
                            record["atp_token_before_scroll"] = token_locator.bounding_box()
                            token_locator.scroll_into_view_if_needed()
                            record["atp_token_after_scroll"] = token_locator.bounding_box()
                            original_supply(page, state, mode, units)
                        solver._supply = scroll_then_supply
                        record["solver_adjustment"] = "Separate diagnostic only: scroll the visible ATP token into view before the unchanged solver supplies fuel. No task source/state mutation. Original failed check is preserved."
                    try:
                        if failure:
                            if premature_submit_diagnostic:
                                record["diagnostic_action"] = "Click the visible SUBMIT EXPEDITION control before winding the clock; no source or task state changes."
                                page.locator(".cc-submit").click()
                                deadline = time.monotonic() + 10
                                while read(state_dir / "ground_truth.json").get("challenge_id") == truth.get("challenge_id"):
                                    if time.monotonic() >= deadline:
                                        raise AssertionError("premature submission did not generate a fresh catacomb")
                                    page.wait_for_timeout(50)
                                page.locator(".readout[data-status=error]").wait_for(state="visible")
                                record["status"] = "failure_control_completed"
                                record["fresh_challenge_after_failure"] = True
                            elif not hasattr(solver, "fail_once"):
                                record["status"] = "missing_existing_failure_helper"
                            else:
                                solver.fail_once(page, state_dir, screenshot_dir, mechanic)
                                record["status"] = "failure_helper_completed"
                                record["fresh_challenge_after_failure"] = read(state_dir / "ground_truth.json").get("challenge_id") != truth.get("challenge_id")
                        else:
                            solver.solve(page, state_dir, screenshot_dir, mechanic)
                            exported = helper.exported_payload(state_dir)
                            write(out / "exported.json", exported)
                            grader = load(bench / "shared_runtime/server/incubator_graders" / f"{mechanic}.py", f"pilot_grade_{mechanic}")
                            record["server_grade"] = exported["result"].get("server_grade") or {}
                            record["direct_grade"] = grader.grade(exported["result"], exported["ground_truth"], exported["public_state"])
                            record["exported_verifier"] = helper.run_task_verifier(mechanic, exported, out)
                            other_mode = "full" if mode == "simplified" else "simplified"
                            other = ROOT / "outputs" / "generation" / mechanic / f"d{level}_{other_mode}_seed{seed}"
                            other_truth, other_public = read(other / "ground_truth.json"), read(other / "public_state.json")
                            rebound = copy.deepcopy(exported["result"])
                            for identity in ("challenge_id", "task_id"):
                                if identity in rebound:
                                    rebound[identity] = other_truth.get(identity, other_public.get(identity))
                            record["opposite_mode_identity_rebound_grade"] = grader.grade(rebound, other_truth, other_public)
                            record["status"] = "wiring_pass" if all(record[k].get("passed") is True for k in ("server_grade", "direct_grade", "exported_verifier")) and not errors else "wiring_check_failed"
                    finally:
                        page.screenshot(path=str(screenshot_dir / "final.png"), full_page=True)
                finally:
                    browser.close()
    except Exception as exc:
        record["status"] = "check_error"
        record["error_type"] = type(exc).__name__
        record["error"] = str(exc)
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        record["elapsed_seconds"] = round(time.monotonic() - started, 2)
        record["screenshots"] = [str(p.relative_to(ROOT)) for p in sorted(screenshot_dir.glob("*.png"))]
        write(evidence_dir / f"{name}.json", record)
    print(json.dumps(record), flush=True)
    return record["status"] in ("wiring_pass", "failure_helper_completed", "failure_control_completed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_index", type=int)
    parser.add_argument("--level", type=int, choices=range(1, 6), required=True)
    parser.add_argument("--interaction", choices=("simplified", "full"), required=True)
    parser.add_argument("--seed", type=int, choices=(1, 17, 101), default=1)
    parser.add_argument("--failure", action="store_true")
    parser.add_argument("--scroll-atp-diagnostic", action="store_true")
    parser.add_argument("--premature-submit-diagnostic", action="store_true")
    parser.add_argument("--rayglass-select-diagnostic", action="store_true")
    parser.add_argument("--rayglass-option-diagnostic", action="store_true")
    parser.add_argument("--hearth-carry-first-diagnostic", action="store_true")
    parser.add_argument("--crack-tile-edge-diagnostic", action="store_true")
    parser.add_argument("--rising-reconfigure-diagnostic", action="store_true")
    parser.add_argument("--five-scaled-flick-diagnostic", action="store_true")
    parser.add_argument("--letter-fast-poll-diagnostic", action="store_true")
    args = parser.parse_args()
    raise SystemExit(0 if run(args.case_index, args.level, args.interaction, args.seed, args.failure, args.scroll_atp_diagnostic, args.premature_submit_diagnostic, args.rayglass_select_diagnostic, args.rayglass_option_diagnostic, args.hearth_carry_first_diagnostic, args.crack_tile_edge_diagnostic, args.rising_reconfigure_diagnostic, args.five_scaled_flick_diagnostic, args.letter_fast_poll_diagnostic) else 1)


if __name__ == "__main__":
    main()
