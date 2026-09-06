"""Implementation evidence only: truth-informed routes, ordinary pointer input."""
from __future__ import annotations
import json
import time
from pathlib import Path
from playwright.sync_api import expect

MECHANIC_ID='confectioners_ink'

def stroke(page, points, mode):
    box=page.locator('#ink-canvas').bounding_box()
    def xy(p):return box['x']+p[0]/900*box['width'],box['y']+p[1]/530*box['height']
    if mode=='simplified':
        for p in points:page.mouse.click(*xy(p))
        page.locator('#ink-finish').click()
    else:
        page.mouse.move(*xy(points[0]));page.mouse.down()
        for p in points[1:]:page.mouse.move(*xy(p),steps=12)
        page.mouse.up()

def fail_once(page,state_dir:Path,out_dir:Path,mechanic=MECHANIC_ID):
    old=json.loads((state_dir/'public_state.json').read_text())['challenge_id']
    # Overspending physically drawn ink produces a visible terminal failure.
    mode=page.evaluate('confectionersInkModel.mode')
    for _ in range(3):
        if page.evaluate('confectionersInkModel.lost'):break
        stroke(page,[[20,85],[880,85],[20,100]],mode)
    expect(page.locator('#ink-verdict')).to_contain_text('FAIL')
    page.screenshot(path=str(out_dir/'failure.png'))
    page.locator('#ink-retry').click()
    # The task clock may be paused, so requestAnimationFrame (Playwright's
    # default predicate polling) cannot reliably observe an asynchronous retry.
    deadline = time.monotonic() + 30
    while not page.evaluate('(old)=>confectionersInkModel.state.challenge_id!==old', old):
        if time.monotonic() >= deadline:
            raise TimeoutError('fresh cabinet did not arrive within 30 seconds')
        time.sleep(.025)
    page.screenshot(path=str(out_dir/'retry.png'))

def solve(page,state_dir:Path,out_dir:Path,mechanic=MECHANIC_ID):
    assert mechanic==MECHANIC_ID
    h=json.loads((state_dir/'ground_truth.json').read_text());mode=(h.get('control_condition') or {}).get('interaction','full')
    for i,route in enumerate(h['canonical_routes']):
        page.wait_for_function('(t)=>confectionersInkModel.tick>=t',arg=i*h['world']['batch_ticks']+5,timeout=90000)
        stroke(page,route,mode)
        page.screenshot(path=str(out_dir/f'active-{i+1}.png'))
    page.wait_for_function('confectionersInkModel.done || confectionersInkModel.lost',timeout=90000)
    assert page.evaluate('confectionersInkModel.done'),page.evaluate('({tallies:confectionersInkModel.tallies,tick:confectionersInkModel.tick,waste:confectionersInkModel.waste})')
    page.screenshot(path=str(out_dir/'filled.png'))
    page.locator('#ink-submit').click()
    expect(page.locator('.readout')).to_have_attribute('data-status','passed',timeout=60000)
    page.screenshot(path=str(out_dir/'pass.png'))
