"""Wiring solver: reads generated recipes but acts only through native browser input."""
from __future__ import annotations
import json
import time
from pathlib import Path
MECHANIC_ID='museum_of_lost_gestures'

def wait_browser(page, expression):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        if page.evaluate(expression):return
        page.wait_for_timeout(25)
    raise AssertionError('browser condition timed out: '+expression)

def wait_task(page, milliseconds):
    if page.evaluate("window.WeirdCaptchaTime?.status().state === 'paused'"):
        for _ in range((milliseconds+499)//500):
            page.evaluate('WeirdCaptchaTime.runFor(500)')
            wait_browser(page, "WeirdCaptchaTime.status().phase === 'completed'")
    else: page.wait_for_timeout(milliseconds)

def perform(page, world, gesture, mode):
    if mode=='simplified':
        page.locator(f'[data-gesture="{gesture}"]').click()
        if gesture in ('hold','dwell'): wait_task(page, world['hold_ms']+150 if gesture=='hold' else world['dwell_ms']+150)
        return
    frame=page.locator('#museum-room');r=frame.bounding_box();x,y,w,h=world['plinth'];cx=r['x']+x+w/2;cy=r['y']+y+h/2
    page.mouse.move(cx,cy)
    if gesture=='double':page.mouse.dblclick(cx,cy,delay=110)
    elif gesture=='right':page.mouse.click(cx,cy,button='right')
    elif gesture=='drag':
        page.mouse.down();page.mouse.move(cx+w+22,cy,steps=8);page.mouse.up()
    elif gesture=='hold':
        page.mouse.down();wait_task(page,world['hold_ms']+150);page.mouse.up()
    elif gesture=='scroll':
        page.mouse.wheel(0,-1200);page.wait_for_timeout(120)
        page.mouse.wheel(0,1200);page.wait_for_timeout(120)
    elif gesture=='resize':
        b=page.locator('#museum-resize').bounding_box();page.mouse.move(b['x']+15,b['y']+15);page.mouse.down()
        page.mouse.move(b['x']+15+(95 if r['width']<510 else -95),b['y']+15,steps=8);page.mouse.up();page.wait_for_timeout(150)
    elif gesture=='return':
        page.mouse.move(r['x']-12,cy);page.mouse.move(cx,cy)
    elif gesture=='dwell':
        page.mouse.move(cx+12,cy);wait_task(page,world['dwell_ms']+150)
    elif gesture=='modifier':
        page.mouse.click(r['x']+25,r['y']+80);page.keyboard.down('Shift');page.mouse.click(cx,cy);page.keyboard.up('Shift')
    elif gesture=='chord':
        page.mouse.click(r['x']+25,r['y']+80);page.keyboard.down('a');page.keyboard.down('s');page.keyboard.up('s');page.keyboard.up('a')
    page.wait_for_timeout(70)

def fail_once(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    before=json.loads((state_dir/'ground_truth.json').read_text())['challenge_id']
    page.locator('#museum-certify').click()
    wait_browser(page,"document.querySelector('.readout')?.textContent.includes('FAIL')")
    assert json.loads((state_dir/'ground_truth.json').read_text())['challenge_id']!=before
    page.screenshot(path=str(out_dir/'failure-fresh.png'))

def solve(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    truth=json.loads((state_dir/'ground_truth.json').read_text());world=truth['world'];mode=truth.get('control_condition',{}).get('interaction','full')
    cases={c['id']:c for c in world['cases']}
    for i,id in enumerate(truth['solution_order']):
        if page.locator(f'[data-case="{id}"].found').count():continue
        for gesture in cases[id]['recipe']:perform(page,world,gesture,mode)
        assert page.locator(f'[data-case="{id}"].found').count(),f'case did not open: {cases[id]}; '+str(page.evaluate('window.museumOfLostGesturesModel.recognized'))
        if i in (2,6):page.screenshot(path=str(out_dir/f'active-{i}.png'))
    page.screenshot(path=str(out_dir/'solved.png'))
    page.locator('#museum-certify').click()
    wait_browser(page,"document.querySelector('.readout')?.textContent==='PASS'")
