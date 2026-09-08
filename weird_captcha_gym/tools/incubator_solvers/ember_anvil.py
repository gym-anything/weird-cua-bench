"""Wiring solver: private generated route, ordinary Playwright inputs only."""
from __future__ import annotations
import json
import time
from pathlib import Path
MECHANIC_ID='ember_anvil'


def wait(page, expression, timeout=10):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if page.evaluate(expression):return
        page.wait_for_timeout(50)
    raise AssertionError(f'Visible browser condition timed out: {expression}')


def read(p):return json.loads(Path(p).read_text())


def drag(page, source, x, y):
    r=page.locator(source).bounding_box()
    page.mouse.move(r['x']+r['width']/2,r['y']+r['height']/2)
    page.mouse.down();page.mouse.move(x,y,steps=5);page.mouse.up()


def orbit(page, full, delta=1):
    if full:
        r=page.locator('#ea-orbit-rail').bounding_box()
        drag(page,'#ea-orbit-rail',r['x']+r['width']/2+delta*85,r['y']+r['height']/2)
    else:page.locator('#ea-right' if delta==1 else '#ea-left').click()


def transfer(page, full, to_forge):
    if full:
        r=page.locator('#ea-forge' if to_forge else '#ea-work').bounding_box()
        drag(page,'#ea-tongs',r['x']+r['width']/2,r['y']+r['height']/2)
    else:page.locator('#ea-transfer').click()


def top_point(page, cell):
    r=page.locator('#ea-work').bounding_box()
    x=350+(cell%7+.5-3.5)*34*1.35
    y=360*.53+(cell//7+.5-3.5)*34*1.05
    return r['x']+x*r['width']/700,r['y']+y*r['height']/360


def fail_once(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    before=read(state_dir/'ground_truth.json')['challenge_id']
    page.locator('#ea-stamp').click()
    wait(page,"document.querySelector('#ea-verdict')?.textContent.includes('FAIL')")
    assert read(state_dir/'ground_truth.json')['challenge_id']!=before
    page.screenshot(path=str(out_dir/'ember_anvil-fail-refresh.png'))


def solve(page,state_dir,out_dir,mechanic=MECHANIC_ID,observe=None):
    observe=observe or (lambda: None)
    assert mechanic==MECHANIC_ID
    truth=read(state_dir/'ground_truth.json');full=(truth.get('control_condition') or {}).get('interaction')=='full'
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out_dir/'ember_anvil-initial.png'))
    # Top view gives accessible contact faces. The route uses private heights;
    # it is implementation evidence, never a screenshot-agent evaluation.
    for _ in range(4):orbit(page,full)
    for index,a in enumerate(truth['solution']):
        if 'TOO COLD' in page.locator('#ea-heat').inner_text():
            transfer(page,full,True)
            page.wait_for_timeout(2500)
            for _ in range(5):observe()
            transfer(page,full,False)
        page.locator(f'[data-mode="{a["mode"]}"]').click()
        page.locator(f'[data-direction="{a["direction"]}"]').click()
        x,y=top_point(page,a['cell'])
        if full:drag(page,'#ea-hammer',x,y)
        else:page.mouse.click(x,y)
        observe()
        if index==len(truth['solution'])//2:
            orbit(page,full,1)
            page.screenshot(path=str(out_dir/'ember_anvil-active.png'))
            orbit(page,full,-1)
    orbit(page,full,1)
    page.screenshot(path=str(out_dir/'ember_anvil-solved.png'))
    page.locator('#ea-stamp').click()
    wait(page,"document.querySelector('#ea-verdict')?.textContent.includes('PASS')")
    page.screenshot(path=str(out_dir/'ember_anvil-pass.png'))
