"""Privileged wiring solver; all outcomes produced by native browser inputs."""
import json
import math
import time
from pathlib import Path
MECHANIC_ID='waggle_dispatch'


def sun(w,t):
    return w['sun_phase']+w['sun_direction']*w['parameters']['sun_speed']*(t/1000+1.5*(math.sin(t/6000+w['sun_wave'])-math.sin(w['sun_wave'])))


def wait(page, expression, arg=None, timeout=10):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if page.evaluate(expression,arg):return
        page.wait_for_timeout(25)
    raise AssertionError('Browser condition timed out: '+expression)


def advance(page,ms):
    page.evaluate('(ms)=>WeirdCaptchaTime.runFor(ms)',ms)
    wait(page,"WeirdCaptchaTime.status().phase === 'completed'",timeout=ms/1000+5)


def dance(page,public,target=None,paused=False):
    w=public['world'];target=w['target'] if target is None else target;site=w['sites'][target]
    duration=math.hypot(site['x'],site['y'])/w['distance_per_second']*1000
    # Quantize the hold to whole observation windows within the landing tolerance.
    if paused:duration=round(duration/240)*240
    mode=public.get('control_condition',{}).get('interaction','full')
    box=page.locator('.waggle canvas').bounding_box()
    def point(x,y):return (box['x']+(235+x)*box['width']/1100,box['y']+(215+y)*box['height']/430)
    def angle_at(end):return math.atan2(site['x'],-site['y'])-math.radians(sun(w,end))
    t=page.evaluate('performance.now()-waggleDispatchModel.epoch')
    a=angle_at(t+duration+(0 if paused else 80))
    x,y=point(110*math.sin(a),-110*math.cos(a))
    if mode=='full':
        page.mouse.move(*point(0,0));page.mouse.down();page.mouse.move(x,y)
    else:
        page.mouse.click(x,y);page.locator('.waggle-toggle').click()
    start=page.evaluate('waggleDispatchModel.hold')
    if paused:
        for _ in range(round(duration/240)):advance(page,240)
    else:
        remaining=duration-(page.evaluate('performance.now()-waggleDispatchModel.epoch')-start)-35
        page.wait_for_timeout(max(0,remaining))
    # Re-aim at the evidenced current sun immediately before release.
    end=page.evaluate('performance.now()-waggleDispatchModel.epoch')+(0 if paused else 25)
    a=angle_at(end);x,y=point(110*math.sin(a),-110*math.cos(a))
    if mode=='full':page.mouse.move(x,y);page.mouse.up()
    else:page.mouse.click(x,y);page.locator('.waggle-toggle').click()
    if paused:
        for _ in range(11):advance(page,240)
    else:page.wait_for_timeout(w['flight_ms']+100)
    assert page.evaluate('waggleDispatchModel.scouts.at(-1)')==target, page.evaluate('({scouts:waggleDispatchModel.scouts,events:waggleDispatchModel.events})')


def fail_once(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    before=page.locator('.waggle').get_attribute('data-challenge-id')
    page.locator('.waggle-submit').click()
    wait(page,'(old)=>document.querySelector(".waggle").dataset.challengeId!==old',before)
    page.screenshot(path=str(Path(out_dir)/'failure-fresh.png'))


def solve(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    public=json.loads((Path(state_dir)/'public_state.json').read_text())
    paused=page.evaluate("WeirdCaptchaTime.status().mode === 'paused'")
    for i in range(public['world']['required']):
        dance(page,public,paused=paused)
        if i==0:page.screenshot(path=str(Path(out_dir)/'first-report.png'))
    page.screenshot(path=str(Path(out_dir)/'solved.png'))
    page.locator('.waggle-submit').click()
    wait(page,"document.querySelector('.readout').dataset.status==='passed'")
