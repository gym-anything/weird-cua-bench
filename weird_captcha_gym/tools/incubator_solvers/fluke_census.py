"""Wiring solver: knows generated identities, uses only normal browser inputs."""
from __future__ import annotations
import json
import math
import time
from pathlib import Path

MECHANIC_ID='fluke_census'

def wait_true(page,expression,arg=None):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        if page.evaluate(expression,arg):return
        time.sleep(.05)
    raise AssertionError('visible state did not arrive: '+expression)

def aim_at(page, state, epoch, animal_id):
    item=next(i for i in state['layouts'][epoch] if i['id']==animal_id)
    elapsed=page.evaluate('performance.now()-flukeCensusModel.started-flukeCensusModel.epochStart')/1000
    x=item['x']+16*math.sin(item['phase']+elapsed*item['omega'])
    y=item['y']+12*math.cos(item['phase']+elapsed*item['omega'])
    mode=(state.get('control_condition') or {}).get('interaction','full')
    if mode=='full':
        box=page.locator('#fc-sea').bounding_box()
        page.mouse.move(box['x']+x*box['width']/820,box['y']+y*box['height']/430)
    else:
        page.locator('#fc-x').fill(str(round(x,3)))
        page.locator('#fc-y').fill(str(round(y,3)))
        page.locator('#fc-aim').click()

def shutter(page,state):
    if (state.get('control_condition') or {}).get('interaction','full')=='full':page.keyboard.press('Space')
    else:page.locator('#fc-photo').click()

def fail_once(page,state_dir:Path,out_dir:Path,mechanic=MECHANIC_ID):
    page.locator('#fc-submit').click()
    page.wait_for_selector('#fc-retry')
    page.screenshot(path=str(out_dir/'fluke_census-failed.png'))
    page.locator('#fc-retry').click()
    wait_true(page,"document.querySelector('#fc-count')?.textContent === '00'")
    page.screenshot(path=str(out_dir/'fluke_census-recovered.png'))

def solve(page,state_dir:Path,out_dir:Path,mechanic=MECHANIC_ID,inspection_delay_ms=180,after_action=None,before_action=None):
    state=json.loads((state_dir/'public_state.json').read_text())
    truth=json.loads((state_dir/'ground_truth.json').read_text())
    for epoch,animal in enumerate(truth['required_ids']):
        if before_action:before_action(f"aim-{epoch}")
        aim_at(page,state,epoch,animal)
        if after_action:after_action(f"aim-{epoch}")
        page.wait_for_timeout(inspection_delay_ms)
        if epoch==0:page.screenshot(path=str(out_dir/'fluke_census-inspection.png'))
        if before_action:before_action(f"photo-{epoch}")
        shutter(page,state)
        if after_action:after_action(f"photo-{epoch}")
        wait_true(page,'(n)=>Number(document.querySelector("#fc-count").textContent)===n',arg=epoch+1)
    page.screenshot(path=str(out_dir/'fluke_census-before-submit.png'))
    if before_action:before_action('submit')
    page.locator('#fc-submit').click()
    if after_action:after_action('submit')
    wait_true(page,"document.querySelector('.readout')?.textContent === 'PASS'")
    page.screenshot(path=str(out_dir/'fluke_census-pass.png'))
