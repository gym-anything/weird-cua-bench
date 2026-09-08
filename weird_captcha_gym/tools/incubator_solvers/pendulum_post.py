"""Privileged implementation probe; all actions use ordinary browser mouse input.

Reads the reference schedule for wiring validation, not an agent evaluation.
"""
import json
import math
from pathlib import Path

MECHANIC_ID='pendulum_post'


def swipe_rope(page,index):
    info=page.evaluate('''i=>{const m=pendulumPostModel,r=m.state.world.ropes[i],s=m.sim;return {r,s};}''',index)
    r,s=info['r'],info['s'];dx,dy=s['x']-r['x'],s['y']-r['y'];d=math.hypot(dx,dy);sag=math.sqrt(max(0,r['length']**2-d*d))/2
    nx,ny=-dy/d,dx/d
    if ny<0:nx,ny=-nx,-ny
    mid=[(r['x']+s['x'])/2+nx*sag,(r['y']+s['y'])/2+ny*sag]
    dx,dy=mid[0]-r['x'],mid[1]-r['y'];d=math.hypot(dx,dy)
    x,y=r['x']+.40*dx,r['y']+.40*dy
    a=[x-dy/d*22,y+dx/d*22];b=[x+dy/d*22,y-dx/d*22]
    box=page.locator('.pp-cabinet canvas').bounding_box()
    # Canvas has an 8 px CSS border on each side.
    def screen(p):return box['x']+8+p[0]*(box['width']-16)/900,box['y']+8+p[1]*(box['height']-16)/480
    page.mouse.move(*screen(a));page.mouse.down();page.mouse.move(*screen(b));page.mouse.up()


def solve(page,state_dir:Path,out_dir:Path,mechanic=MECHANIC_ID):
    truth=json.loads((state_dir/'ground_truth.json').read_text())
    mode=(truth.get('control_condition') or {}).get('interaction','full')
    page.locator('.pp-start').click()
    offset=0
    for step,e in enumerate(truth['reference_schedule']):
        target=e['tick']+offset
        page.wait_for_function('t=>pendulumPostModel.sim.tick>=t',arg=max(0,target-3),polling=10)
        if mode=='full':swipe_rope(page,e['rope'])
        else:page.locator(f'[data-rope="{e["rope"]}"]').click()
        actual=page.evaluate('pendulumPostModel.events.at(-1)')
        assert actual and actual['rope']==e['rope'],actual
        if step==0:offset=actual['tick']-e['tick']
        page.screenshot(path=str(out_dir/f'{mechanic}-cut-{e["rope"]}.png'))
    page.wait_for_function("pendulumPostModel.sim.status!=='active'",timeout=30000)
    status=page.evaluate('pendulumPostModel.sim')
    assert status['status']=='delivered',status
    page.screenshot(path=str(out_dir/f'{mechanic}-delivered.png'))
    page.locator('.pp-submit').click()
    page.wait_for_function("document.querySelector('.readout').textContent==='PASS'")


def fail_once(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    old=page.evaluate('pendulumPostModel.state.challenge_id')
    page.locator('.pp-new').click()
    page.wait_for_function('id=>pendulumPostModel.state.challenge_id!==id',arg=old)
