"""Read-only PR audit, with all generated state kept outside the source snapshot."""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import traceback
from urllib.request import urlopen

SOURCE = next(parent for parent in Path(__file__).resolve().parents
              if (parent / "weird_captcha_gym/environments").is_dir())
OUT = Path(os.environ.get("PR49_OUTPUT", str(SOURCE / "outputs/pr49_quality_fixes_20260906")))
OUT.mkdir(parents=True, exist_ok=True)
BENCH = SOURCE / "weird_captcha_gym"
REPO = SOURCE
sys.path.insert(0, str(SOURCE))
BASE = "e73658eb52ea69c86f3ec64c082e40d965536237"
HEAD = "2155caa0e1ea96a16277c4ef47f8fa1f2d2e4399"

def read(path):
    return json.loads(Path(path).read_text())

def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True))

def contract_snapshot(m):
    env = BENCH / "environments" / (m + "_env")
    task = env / "tasks" / (m + "_seed_0001")
    paths = [*env.glob("*.json"), *task.glob("*"),
             BENCH / "shared_scripts/setup_task.py",
             BENCH / "shared_scripts/incubator_generators" / (m + ".py"),
             BENCH / "shared_runtime/server/incubator_graders" / (m + ".py"),
             BENCH / "tools/incubator_solvers" / (m + ".py"),
             BENCH / "tools/incubator_solvers/common.py",
             * (BENCH / "shared_runtime/app").glob("*.js"),
             * (BENCH / "shared_runtime/app").glob("*.css"),
             * (BENCH / "shared_runtime/server").glob("*.py"),
             * (BENCH / "shared_scripts").glob("*verif*.py"),
             * (BENCH / "shared_runtime/app/mechanics").glob(m + ".*")]
    return {str(path.relative_to(SOURCE)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(paths)) if path.is_file()}

def mechanics():
    paths = subprocess.check_output(["git", "diff", "--diff-filter=A", "--name-only", BASE, HEAD], cwd=REPO, text=True).splitlines()
    return sorted(Path(p).parent.name.removesuffix("_env") for p in paths if p.startswith("weird_captcha_gym/environments/") and p.endswith("/env.json"))

def inventory():
    from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment
    result = {"base": BASE, "head": HEAD, "tasks": {}}
    films_root = BENCH / "evidence/round_three_v1/solution_videos"
    manifest = read(films_root / "manifest.json")
    for m in mechanics():
        env = BENCH / "environments" / (m + "_env")
        task_dir = env / "tasks" / (m + "_seed_0001")
        paths = [env / "env.json", env / "controls.json", task_dir / "task.json", task_dir / "setup_task.sh", task_dir / "export_result.sh", task_dir / "verifier.py", BENCH / "shared_scripts/incubator_generators" / (m + ".py"), BENCH / "shared_runtime/app/mechanics" / (m + ".js"), BENCH / "shared_runtime/app/mechanics" / (m + ".css"), BENCH / "shared_runtime/server/incubator_graders" / (m + ".py"), BENCH / "tools/incubator_solvers" / (m + ".py"), BENCH / "shared_runtime/assets/provenance" / (m + "_v0.json"), BENCH / "splits" / (m + "_split.json")]
        task = read(task_dir / "task.json")
        controls = read(env / "controls.json")
        materialized = materialize_environment(env, OUT / "controlled_tasks")
        record = {"name": task["name"], "missing": [str(p.relative_to(SOURCE)) for p in paths if not p.is_file()], "materialized": len(materialized), "baseline": controls["baseline"], "runner_options": read(env / "env.json").get("runner_options"), "status": task.get("metadata", {}).get("status"), "notes": task.get("metadata", {}).get("notes"), "has_film": m in manifest["videos"], "tests": [p.name for p in (SOURCE / "tests").glob("test_*" + m + "*.py")]}
        result["tasks"][m] = record
    result["films"] = {}
    for key, film in manifest["videos"].items():
        hashes = {}
        for fmt in ("mp4", "webm"):
            path = films_root / film[fmt]
            hashes[fmt] = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == film[fmt + "_sha256"]
        result["films"][key] = {"hashes_match": hashes, "grades_pass": {label: film.get(label, {}).get("passed") for label in ("server_grade", "direct_grade", "verifier")}, "console_errors": film.get("console_errors"), "duration": film.get("media", {}).get("duration_seconds")}
    save(OUT / "inventory.json", result)
    print(json.dumps({"tasks": len(result["tasks"]), "variants": sum(v["materialized"] for v in result["tasks"].values()), "missing": {k:v["missing"] for k,v in result["tasks"].items() if v["missing"]}, "films": len(result["films"]), "bad_films": {k:v for k,v in result["films"].items() if not all(v["hashes_match"].values()) or not all(v["grades_pass"].values())}}, indent=2))

def one(m, seed, recovery=False, omit_landfall_map=False):
    from playwright.sync_api import sync_playwright, expect
    from weird_captcha_gym.tools.smoke_incubator_batch_one_ui import load_module, exported_payload, run_task_verifier
    target = OUT / "browser" / seed / m
    target.mkdir(parents=True, exist_ok=True)
    state = target / "state"
    state.mkdir(exist_ok=True)
    captures = target / "captures"
    captures.mkdir(exist_ok=True)
    record = {"mechanic": m, "seed": seed + "-" + m, "ok": False, "recovery": recovery, "console_errors": [], "clock_calls": [], "result_responses": [], "omit_landfall_map": omit_landfall_map,
              "source_before": contract_snapshot(m),
              "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True).strip()}
    started = time.monotonic()
    server = page = browser = context = None
    server_log = (target / "server.log").open("w")
    def deadline(signum, frame):
        raise TimeoutError("audit case exceeded 240 seconds")
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(240)
    try:
        task = BENCH / "environments" / (m + "_env") / "tasks" / (m + "_seed_0001") / "task.json"
        subprocess.run([sys.executable, "-B", str(BENCH / "shared_scripts/setup_task.py"), "--task-json", str(task), "--state-dir", str(state), "--seed", record["seed"]], cwd=SOURCE, check=True, stdout=server_log, stderr=server_log, timeout=60)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        server = subprocess.Popen([sys.executable, "-B", str(BENCH / "shared_runtime/server/weird_captcha_server.py"), "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(BENCH / "shared_runtime/app"), "--state-dir", str(state)], cwd=SOURCE, stdout=server_log, stderr=server_log)
        for _ in range(100):
            try:
                urlopen(f"http://127.0.0.1:{port}/health", timeout=.5).read()
                break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError("isolated task server exited")
                time.sleep(.1)
        with sync_playwright() as pw:
            launch_options = {"headless": True}
            if os.environ.get("PR49_BROWSER_EXECUTABLE"):
                launch_options["executable_path"] = os.environ["PR49_BROWSER_EXECUTABLE"]
            browser = pw.chromium.launch(**launch_options)
            record["browser_version"] = browser.version
            viewport = {"width": int(os.environ.get("PR49_WIDTH", "1280")), "height": int(os.environ.get("PR49_HEIGHT", "720"))}
            record["viewport"] = viewport
            video_options = {"record_video_dir": str(target / "raw-video"), "record_video_size": viewport} if os.environ.get("PR49_RECORD_VIDEO") else {}
            context = browser.new_context(viewport=viewport, device_scale_factor=1, **video_options)
            page = context.new_page()
            if m == "passphrase_under_siege":
                page.add_init_script("""window.__pr49PointerEvents=[]; for (const type of ['pointerdown','pointerup','pointercancel','lostpointercapture']) document.addEventListener(type,e=>{window.__pr49PointerEvents.push({type,target:e.target.className,x:e.clientX,y:e.clientY,buttons:e.buttons});},true);""")
            if os.environ.get("PR49_INPUT_DELAY_MS"):
                delay = int(os.environ["PR49_INPUT_DELAY_MS"])
                original_down, original_up = page.mouse.down, page.mouse.up
                def mouse_down(*a, **kw):
                    original_down(*a, **kw)
                    page.wait_for_timeout(delay)
                def mouse_up(*a, **kw):
                    page.wait_for_timeout(delay)
                    original_up(*a, **kw)
                    page.wait_for_timeout(delay)
                page.mouse.down, page.mouse.up = mouse_down, mouse_up
            page.on("console", lambda msg: record["console_errors"].append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda err: record["console_errors"].append(str(err)))
            def result_response(response):
                if response.url.endswith("/result"):
                    record["result_responses"].append(response.json())
            page.on("response", result_response)
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            page.wait_for_function("m => typeof window.WeirdCaptchaMechanics?.[m]?.render === 'function'", arg=m)
            root = page.evaluate("m => window.WeirdCaptchaMechanics[m].rootSelector || '#app'", m)
            expect(page.locator(root)).to_be_visible()
            page.screenshot(path=str(captures / "00-initial.png"))
            original_evaluate = page.evaluate
            def track_evaluate(expression, arg=None):
                if any(token in expression for token in (".pause(", ".resume(", ".runFor(", ".setMode(")):
                    record["clock_calls"].append({"expression": expression, "arg": arg})
                return original_evaluate(expression, arg)
            page.evaluate = track_evaluate
            solver = load_module(BENCH / "tools/incubator_solvers" / (m + ".py"), "audit_solver_" + m)
            if m == "passphrase_under_siege":
                record["selection_checks"] = []
                original_select = solver._select_range
                def traced_select(*a, **kw):
                    original_select(*a, **kw)
                    record["selection_checks"].append({"requested": list(a[1:3]), "selected": page.locator(".siege-char.is-selected").evaluate_all("nodes=>nodes.map(n=>n.dataset.index)"), "readout": page.locator(".readout").inner_text(), "pointer_events": page.evaluate("window.__pr49PointerEvents.slice(-8)")})
                solver._select_range = traced_select
            if omit_landfall_map:
                assert m == "unmarked_landfall"
                original_pin = solver._pin_landing
                def pin_without_unneeded_gesture(*a, **kw):
                    return original_pin(*a, **{**kw, "exercise_map_controls": False})
                solver._pin_landing = pin_without_unneeded_gesture
            if recovery:
                if hasattr(solver, "fail_once"):
                    solver.fail_once(page, state, captures, m)
                    record["recovery_exercised"] = True
                else:
                    record["recovery_exercised"] = False
            try:
                solver.solve(page, state, captures, m)
                expect(page.locator(".readout")).to_have_attribute("data-status", "passed")
                record["readout_text"] = page.locator(".readout").inner_text()
                page.screenshot(path=str(captures / "99-final.png"))
                exported = exported_payload(state)
                save(target / "export.json", exported)
                grader = load_module(BENCH / "shared_runtime/server/incubator_graders" / (m + ".py"), "audit_grader_" + m)
                grades = {"server": exported["result"].get("server_grade") or {}, "direct": grader.grade(exported["result"], exported["ground_truth"], exported["public_state"]), "verifier": run_task_verifier(m, exported, target)}
                record["grades"] = grades
                record["ok"] = all(g.get("passed") is True for g in grades.values()) and not record["console_errors"]
            except Exception:
                page.screenshot(path=str(captures / "99-failure.png"), timeout=5000)
                raise
            finally:
                context.close()
                if video_options:
                    from weird_captcha_gym.tools.record_next_ten_solution_videos import _transcode, _probe
                    webm = target / (m + ".webm")
                    mp4 = target / (m + ".mp4")
                    assert not webm.exists() and not mp4.exists(), "use a fresh capture seed"
                    page.video.save_as(str(webm))
                    _transcode(webm, mp4)
                    record["video"] = {"media": _probe(mp4)}
                    for fmt, path in (("webm", webm), ("mp4", mp4)):
                        record["video"][fmt] = path.name
                        record["video"][fmt + "_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                browser.close()
    except Exception as exc:
        record["error"] = str(exc)
        record["traceback"] = traceback.format_exc()
    finally:
        signal.alarm(0)
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        server_log.close()
        record["seconds"] = round(time.monotonic() - started, 2)
        record["source_after"] = contract_snapshot(m)
        record["source_unchanged"] = record["source_before"] == record["source_after"]
        record["ok"] = record["ok"] and record["source_unchanged"] and "error" not in record
        save(target / "result.json", record)
    print(json.dumps({k:v for k,v in record.items() if k not in ("traceback", "clock_calls")}), flush=True)

def batch(seed, recovery=False, selected=None):
    chosen = selected or mechanics()
    def launch(m):
        target = OUT / "browser" / seed / m
        target.mkdir(parents=True, exist_ok=True)
        with (target / "audit.log").open("w") as log:
            cmd = [sys.executable, str(Path(__file__)), "one", "--mechanic", m, "--seed", seed]
            if recovery:
                cmd.append("--recovery")
            try:
                proc = subprocess.run(cmd, cwd=SOURCE, stdout=log, stderr=log, timeout=275)
                result = read(target / "result.json") if (target / "result.json").exists() else {"ok": False, "error": "audit process returned " + str(proc.returncode)}
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
        print(f"{'PASS' if result['ok'] else 'FAIL'} {m}: {result.get('seconds')}s {result.get('error', '')[:180]}", flush=True)
        return m, result
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for m, result in pool.map(launch, chosen):
            results[m] = result
            save(OUT / (seed + "-browser.json"), results)
    print(f"COMPLETE {sum(r['ok'] for r in results.values())}/{len(results)}", flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("inventory", "batch", "one"))
    p.add_argument("--mechanic", action="append")
    p.add_argument("--seed", default="pr49-fresh-a")
    p.add_argument("--recovery", action="store_true")
    p.add_argument("--omit-landfall-map", action="store_true")
    args = p.parse_args()
    if args.mode == "inventory": inventory()
    elif args.mode == "one": one(args.mechanic[0], args.seed, args.recovery, args.omit_landfall_map)
    else: batch(args.seed, args.recovery, args.mechanic)
