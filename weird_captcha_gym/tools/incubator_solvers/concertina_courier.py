"""Privileged observation for wiring tests; all actions use visible pointer controls."""
import json
import copy
from weird_captcha_gym.shared_runtime.server.incubator_graders.concertina_courier import advance
import time
from pathlib import Path



def settle_plan(state, world, target):
    """Reference controller only: plan a drive/brake/coast manoeuvre from feedback.

    Saturation matters: equal opposite discrete pulses need not cancel once
    the speed cap is reached. Search actual replay dynamics, including contact.
    """
    ranked=[]
    r=world['parameters']['drag']**.25
    for direction in [-1,1]:
        for drive in range(0,65,2):
            for brake in range(0,17,2):
                x,v=state['x'],state['vx']
                for c,n in [(direction,drive),(-direction,brake)]:
                    for _ in range(n*4):
                        v=max(-4,min(4,(v+c*.35)*r));x+=v/4
                rest=x+v*r/(4*(1-r))
                tape=[([direction,0],drive),([-direction,0],brake),([0,0],130)]
                ranked.append((abs(target-rest)+.0001*(drive+brake),tape))
    best=None
    # Ranking is analytic; acceptance of a manoeuvre uses the actual contacts,
    # gravity and collection replay. No solver estimate enters task grading.
    for _,tape in sorted(ranked,key=lambda v:v[0])[:12]:
        sim=copy.deepcopy(state)
        for control,ticks in tape:
            for _ in range(ticks):advance(sim,control,world)
        cost=abs(target-sim['x'])
        if sim['status'] not in ('active','solved'):cost+=10000
        if best is None or cost<best[0]:best=(cost,tape)
    return best[1]


def fail_once(page,state_dir,out_dir,mechanic):
    from playwright.sync_api import expect
    before=json.loads((state_dir/'ground_truth.json').read_text())['challenge_id']
    page.locator('.cc-new').click()
    expect(page.locator('.readout')).to_contain_text('FAIL')
    deadline=time.monotonic()+10
    while json.loads((state_dir/'ground_truth.json').read_text())['challenge_id']==before:
        if time.monotonic()>deadline:raise AssertionError('new challenge was not received')
        time.sleep(.02)
    page.screenshot(path=str(out_dir/f'{mechanic}-failure-retry.png'))


def solve(page,state_dir,out_dir,mechanic):
    from playwright.sync_api import expect
    w=json.loads((state_dir/'ground_truth.json').read_text());mode=(w.get('control_condition') or {}).get('interaction','full')
    paused=page.evaluate("new URLSearchParams(location.search).get('time_mode')==='paused'")
    current=[0,0]
    def command(c):
        nonlocal current
        if c==current:return
        if mode=='full':
            if current!=[0,0]:page.mouse.up()
            if c!=[0,0]:
                b=page.locator(f'[data-c="{c[0]},{c[1]}"]').bounding_box();page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2);page.mouse.down()
        else:page.locator(f'[data-latch="{c[0]},{c[1]}"]').click()
        current=c
    def move(target,shape=None,precision=16):
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            s=page.evaluate('concertinaCourierModel.sim')
            if s['status']=='solved':command([0,0]);return
            assert s['status']=='active',s
            if shape is None and precision<16:
                if abs(target-s['x'])<precision and abs(s['vx'])<.15:
                    command([0,0]);return
                for c,ticks in settle_plan(s,w,target):
                    if not ticks:continue
                    command(c)
                    for _ in range(ticks//2):
                        if paused:
                            page.evaluate('WeirdCaptchaTime.runFor(80)')
                            while page.evaluate('WeirdCaptchaTime.status().phase')!='completed':time.sleep(.01)
                        else:time.sleep(.08)
                        if page.evaluate('concertinaCourierModel.sim.status')!='active':break
                continue
            if shape is not None:
                error=shape-s['h'];c=[0,1 if error>1.5 else -1 if error<-1.5 else 0]
                done=(0<=error<6) if paused else abs(error)<3
            else:
                error=target-s['x'];lead=s['vx']*w['parameters']['drag']**.25/(4*(1-w['parameters']['drag']**.25))
                band=min(10,precision/2)
                c=[1 if error-lead>band else -1 if error-lead<-band else 0,0]
                if paused:
                    choices=[]
                    r=w['parameters']['drag']**.25
                    for first in [0,-1,1]:
                        for second in [0,-1,1]:
                            predicted=copy.deepcopy(s)
                            for u in [first,first,second,second]:advance(predicted,[u,0],w)
                            rest=predicted['x']+predicted['vx']*r/(4*(1-r))
                            cost=abs(target-rest)+.001*abs(predicted['vx'])+.001*(abs(first)+2*abs(second))
                            choices.append((cost,first))
                    c=[min(choices)[1],0]
                    if abs(target-(s['x']+s['vx']*r/(4*(1-r))))<precision/2:c=[0,0]
                done=abs(error)<precision and abs(s['vx'])<.15
            if done:command([0,0]);return
            command(c)
            if paused:
                page.evaluate('WeirdCaptchaTime.runFor(80)')
                while page.evaluate("WeirdCaptchaTime.status().phase")!='completed':time.sleep(.01)
            else:time.sleep(.04)
        raise AssertionError(f'control failed target={target} shape={shape}, state={s}')
    # Use room geometry, not a seed-specific action tape.
    if w['parameters'].get('layout')=='island':
        move(0,200);move(w['seals'][0][0],precision=8)
        page.screenshot(path=str(out_dir/f'{mechanic}-extended.png'))
        move(0,32)
        move(w['seals'][3][0],precision=3)
        page.screenshot(path=str(out_dir/f'{mechanic}-under-shelf.png'))
        move(0,200)
    else:
        shelf=w['solids'][2] if w['parameters']['gap'] else w['solids'][1]
        end=shelf[0]+shelf[2]
        move(0,w['parameters']['clearance']-8);move(end+125)
        page.screenshot(path=str(out_dir/f'{mechanic}-under-shelf.png'))
        move(0,200);move(w['seals'][2][0])
        page.screenshot(path=str(out_dir/f'{mechanic}-extended.png'))
        move(end+125);move(0,32)
        move(847.5 if w['parameters']['alcove'] else w['seals'][3][0])
        move(0,200)
    command([0,0])
    page.screenshot(path=str(out_dir/f'{mechanic}-ready-to-certify.png'))
    page.locator('.cc-submit').click()
    expect(page.locator('.readout')).to_have_attribute('data-status','passed',timeout=10000)
    page.screenshot(path=str(out_dir/f'{mechanic}-pass.png'))
