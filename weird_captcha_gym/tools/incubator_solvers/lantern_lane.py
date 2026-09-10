"""Wiring solver: reads public simulation for tests, sends only native UI inputs.
This is not a screenshot-only model evaluation and makes no difficulty claim.
"""
from __future__ import annotations
import heapq
import json
import time
from pathlib import Path

MECHANIC_ID='lantern_lane'


def plan(w,s,home,target):
    """Find a short route while preferring useful existing roads."""
    buildings={x['node'] for x in w['homes']+w['sites']}
    start=w['homes'][home]['node']; q=[(0,start,[])];seen={}
    while q:
        cost,a,path=heapq.heappop(q)
        if a in seen:continue
        seen[a]=cost;path=path+[a]
        if a==target:return path
        for b in (a-11,a-1,a+1,a+11):
            if not 0<=b<77 or abs(a%11-b%11)+abs(a//11-b//11)!=1:continue
            if b in buildings and b!=target:continue
            if a==start and b!=s['entrances'][home]:continue
            if w['parameters']['river'] and (a%11==5 and a//11 not in w['bridges'] or b%11==5 and b//11 not in w['bridges']):continue
            e=f'{min(a,b)}:{max(a,b)}'
            heapq.heappush(q,(cost+(0.7 if e in s['roads'] else 1),b,path))
    raise ValueError('unreachable site')


def needed(w,s):
    for j,site in enumerate(s['sites']):
        if not site['active']:continue
        home=next(i for i,h in enumerate(w['homes']) if h['color']==w['sites'][j]['color'])
        path=plan(w,s,home,w['sites'][j]['node'])
        for a,b in zip(path,path[1:]):
            e=f'{min(a,b)}:{max(a,b)}'
            if e not in s['roads'] or s['roads'][e]:return a,b
    return None


def next_action(w,s):
    # A newly commissioned order book can overflow before its first delivery.
    # Temporarily close the already-served primary's spur so nearest-first carts
    # serve the new workshop. Reopen it after one satellite delivery. This is
    # network control, not a cart command, and interrupted carts retain position.
    paused=set()
    for j,site in enumerate(s['sites']):
        parent=w['sites'][j]['parent']
        if parent>=0 and site['active'] and site['delivered']==0:
            paused.add(parent)
    for j in sorted(paused):
        n=w['sites'][j]['node']
        for key,closing in s['roads'].items():
            a,b=map(int,key.split(':'))
            if n in (a,b) and not closing:return 'remove',a,b
    for j,site in enumerate(s['sites']):
        if not site['active'] or j in paused:continue
        home=next(i for i,h in enumerate(w['homes']) if h['color']==w['sites'][j]['color'])
        path=plan(w,s,home,w['sites'][j]['node'])
        for a,b in zip(path,path[1:]):
            key=f'{min(a,b)}:{max(a,b)}'
            if key not in s['roads'] or s['roads'][key]:return 'road',a,b
    return None


def manipulate(page,action,mode):
    kind,a,b=action
    if kind=='road':return build(page,a,b,mode)
    if mode=='full':
        x,y=point(page,a);xx,yy=point(page,b);page.mouse.click((x+xx)/2,(y+yy)/2,button='right')
    else:
        page.locator('[data-tool="remove"]').click();page.mouse.click(*point(page,a));page.mouse.click(*point(page,b))


def point(page,n):
    box=page.locator('.lantern-lane canvas').bounding_box()
    return box['x']+(64+n%11*76)*box['width']/900,box['y']+(50+n//11*63)*box['height']/492


def build(page,a,b,mode):
    if mode=='full':
        if page.evaluate('(a)=>lanternLaneModel.w.homes.some(h=>h.node===a)',a):a,b=b,a
        page.mouse.move(*point(page,a));page.mouse.down();page.mouse.move(*point(page,b),steps=3);page.mouse.up()
    else:
        page.locator('[data-tool="road"]').click()  # clears the previous endpoint
        page.mouse.click(*point(page,a));page.mouse.click(*point(page,b))


def fail_once(page,state_dir:Path,out_dir:Path,mechanic:str=MECHANIC_ID):
    old=page.locator('.lantern-lane').get_attribute('data-challenge-id')
    page.locator('#ll-submit').click();page.wait_for_function("document.querySelector('.readout')?.textContent==='FAIL'")
    page.screenshot(path=str(out_dir/'failure.png'))
    page.locator('#ll-retry').click();page.wait_for_function('(old)=>document.querySelector(".lantern-lane").dataset.challengeId!==old',arg=old)
    assert page.locator('.readout').inner_text()!='FAIL'
    page.screenshot(path=str(out_dir/'retry.png'))


def solve(page,state_dir:Path,out_dir:Path,mechanic:str=MECHANIC_ID):
    assert mechanic==MECHANIC_ID
    out_dir.mkdir(parents=True,exist_ok=True)
    page.wait_for_selector('.lantern-lane')
    deadline=time.monotonic()+210;active_saved=False
    while time.monotonic()<deadline:
        m=page.evaluate('({w:lanternLaneModel.w,s:lanternLaneModel.s,mode:lanternLaneModel.mode,started:lanternLaneModel.started})')
        if m['s']['status']=='delivered':break
        if m['s']['status']!='active':raise AssertionError(m['s'])
        action=next_action(m['w'],m['s'])
        if action:
            manipulate(page,action,m['mode'])
        elif not m['started']:
            page.screenshot(path=str(out_dir/'prepared.png'));page.locator('#ll-start').click()
        else:
            if not active_saved and sum(x['active'] for x in m['s']['sites'])>m['w']['parameters']['colors']:
                page.screenshot(path=str(out_dir/'active-expansion.png'));active_saved=True
            page.wait_for_timeout(150)
    else:raise TimeoutError('Lantern Lane did not finish')
    page.screenshot(path=str(out_dir/'delivered.png'));page.locator('#ll-submit').click()
    page.wait_for_function("document.querySelector('.readout')?.textContent==='PASS'",timeout=20000)
    page.screenshot(path=str(out_dir/'pass.png'))
