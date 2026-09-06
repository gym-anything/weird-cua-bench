"""Isolated rendered regression for elapsed-time physics and pause boundaries."""
import hashlib
import json
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pathlib import Path
import importlib.util
B = Path(__file__).resolve().parents[1] / 'weird_captcha_gym'
spec = importlib.util.spec_from_file_location('idol_browser_generator', B/'shared_scripts/incubator_generators/load_bearing_idol.py')
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)
TASK = json.loads((B/'environments/load_bearing_idol_env/tasks/load_bearing_idol_seed_0001/task.json').read_text())


def test_delayed_callbacks_preserve_world_and_settling_duration(tmp_path):
    playwright = pytest.importorskip('playwright.sync_api')
    state, _ = G.generate(TASK, 'audit-late-clock')
    for source, name in [(B/'shared_runtime/app/time_controller.js', 'clock.js'),
                         (B/'shared_runtime/app/mechanics/load_bearing_idol.js', 'mechanic.js')]:
        (tmp_path/name).write_text(source.read_text())
    (tmp_path/'index.html').write_text('''<div id="app"></div>
<script src="clock.js"></script><script src="mechanic.js"></script><script>
const app=document.querySelector('#app');
WeirdCaptchaMechanics.load_bearing_idol.render(STATE,{app,
 setReadout(text,status='idle'){const r=app.querySelector('.readout');r.textContent=text;r.dataset.status=status;}});
WeirdCaptchaTime.markReady();</script>'''.replace('STATE', json.dumps(state)))

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    observations = []
    try:
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for duration, stall in [(600, 0), (600, 850), (600, 850), (3000, 3150)]:
                    context = browser.new_context(viewport={'width': 1920, 'height': 1080})
                    try:
                        page = context.new_page()
                        requests = []
                        def result(route):
                            requests.append(route.request.post_data_json)
                            route.fulfill(json={'passed': False})
                        page.route('**/result', result)
                        page.goto(f'http://127.0.0.1:{server.server_port}/?time_mode=paused', wait_until='networkidle')
                        b = next(b for b in state['bodies'] if b['id'] == 'weight0')
                        box = page.locator('canvas').bounding_box()
                        page.mouse.click(box['x']+b['x'], box['y']+b['y'])
                        page.evaluate('''([duration,stall])=>{
                          WeirdCaptchaTime.runFor(duration);
                          const start=WeirdCaptchaTime.native.performanceNow();
                          while(WeirdCaptchaTime.native.performanceNow()-start<stall){}
                        }''', [duration, stall])
                        deadline = time.monotonic()+10
                        while page.evaluate('WeirdCaptchaTime.status().phase') != 'completed':
                            assert time.monotonic() < deadline
                            time.sleep(.02)
                        assert page.evaluate('WeirdCaptchaTime.status().task_time_ms') == duration
                        assert page.locator('.idol-certify').is_disabled() == (duration < 3000)
                        rendered = hashlib.sha256(page.locator('canvas').screenshot()).hexdigest()
                        page.locator('.idol-retry').click()
                        assert requests[0]['ticks'] == duration*60//1000
                        observations.append((duration, rendered))
                    finally:
                        context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert len({digest for duration, digest in observations if duration == 600}) == 1
