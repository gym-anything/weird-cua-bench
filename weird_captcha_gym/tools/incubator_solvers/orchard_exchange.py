"""White-box oracle for wiring evidence, driving only browser mouse/keyboard input."""
from __future__ import annotations
import heapq
import json
import time
from pathlib import Path

MECHANIC_ID='orchard_exchange'
D={'up':(0,-1),'right':(1,0),'down':(0,1),'left':(-1,0)}

def route(w,start,target):
    q=[(0,tuple(start),[])];seen=set()
    while q:
        cost,p,path=heapq.heappop(q)
        if p in seen:continue
        seen.add(p)
        if list(p)==target:return path
        for k,d in D.items():
            n=(p[0]+d[0],p[1]+d[1])
            if 0<=n[0]<w['width'] and 0<=n[1]<w['height'] and list(n) not in w['walls']:
                heapq.heappush(q,(cost+1+(20 if list(n) in w['water'] else 0),n,path+[k]))
    raise ValueError('unreachable destination')

def fail_once(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    old=json.loads((state_dir/'ground_truth.json').read_text())['challenge_id']
    page.locator('#ox-start').click();page.locator('#ox-deliver').click()
    page.wait_for_function("old=>window.orchardExchangeModel.state.challenge_id!==old",arg=old)
    page.screenshot(path=str(out_dir/'failure-refresh.png'))

def solve(page,state_dir,out_dir,mechanic=MECHANIC_ID,advance=None):
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    def read():return page.evaluate('() => ({s:window.orchardExchangeModel.s,w:window.orchardExchangeModel.w,mode:window.orchardExchangeModel.mode})')
    def wait(ms):
        if advance:advance(ms)
        else:page.wait_for_timeout(ms)
    def click(sel):
        page.locator(sel).click()
        if advance:advance(500)
    def move(target):
        a=read()
        for k in route(a['w'],a['s']['pos'],target):
            eat_if_needed()
            if a['mode']=='full':page.keyboard.press({'up':'ArrowUp','right':'ArrowRight','down':'ArrowDown','left':'ArrowLeft'}[k])
            else:page.locator(f'[data-dir="{k}"]').click()
            wait(80)
    def eat_if_needed():
        s=read()['s']
        if s['hunger']<100:
            if s['inventory'][0]:click('[data-eat="0"]')
            elif s['inventory'][1]:click('[data-eat="1"]')
    def gather(desired):
        a=read();trees=[t['pos'] for t in a['w']['trees'] if t['fruit']==0]
        target=min(trees,key=lambda p:len(route(a['w'],a['s']['pos'],p)))
        move(target)
        for _ in range(150):
            eat_if_needed();a=read();s=a['s']
            if s['failed']:raise AssertionError('oracle failed during harvest')
            goal=min(desired,a['w']['capacity']-s['inventory'][1])
            if s['inventory'][0]>=goal:return
            wait(500)
        raise AssertionError('harvest did not fill basket')
    click('#ox-start')
    gather(8)
    page.screenshot(path=str(out_dir/'active-harvest.png'))
    captured=False
    for _ in range(120):
        eat_if_needed();a=read();s,w=a['s'],a['w']
        if s['failed']:raise AssertionError('oracle hunger failure')
        if s['inventory'][1]>=w['demand'][1]:
            if s['inventory'][0]<w['demand'][0]:gather(w['demand'][0]);continue
            move(w['stall']);eat_if_needed();s=read()['s']
            if any(x<y for x,y in zip(s['inventory'],w['demand'])):continue
            page.screenshot(path=str(out_dir/'solved-before-delivery.png'));click('#ox-deliver')
            for _ in range(100):
                if page.locator('.readout').get_attribute('data-status')=='passed':break
                time.sleep(.1)
            else:raise AssertionError('browser did not show server PASS')
            return
        b=s['bots'][0];ask=b['ask']+int(w['changing_terms'] and b['inventory'][0]>=2)
        if s['inventory'][0]<max(ask,2):gather(min(8,w['capacity']-s['inventory'][1]));continue
        move(b['pos']);a=read();s=a['s'];b=s['bots'][0]
        ask=b['ask']+int(w['changing_terms'] and b['inventory'][0]>=2)
        if s['inventory'][0]<ask:continue
        for name,i,target in [('give',0,ask),('take',1,b['give'])]:
            while (v:=read()['s']['offer'][i])!=target:click(f'[data-edit="{name}"][data-value="{1 if target>v else -1}"]')
        before=len(read()['s']['trades']);click('#ox-post')
        if not captured:page.screenshot(path=str(out_dir/'active-posted.png'));captured=True
        for _ in range(40):
            wait(500);eat_if_needed();s=read()['s']
            if len(s['trades'])>before:break
            b=s['bots'][0]
            if s['offer'][0]!=b['ask']+int(w['changing_terms'] and b['inventory'][0]>=2):break
            if s['inventory'][0]<s['offer'][0]:break
        click('#ox-cancel')
    raise AssertionError('oracle did not finish')
