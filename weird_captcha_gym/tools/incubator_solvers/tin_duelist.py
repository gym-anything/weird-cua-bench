"""Scripted implementation probe using ordinary visible controls.
Reads displayed combat state for feedback; this is not a screenshot-agent score.
"""
from pathlib import Path
import time

MECHANIC_ID='tin_duelist'

def choose(s,w):
    a,b=s['player'],s['enemy'];gap=b['x']-a['x']-48;p=w['parameters']
    if a['move'] or a['stun']:return 0,False,None
    if b['move']:
        starts={'jab':8,'lunge':16,'hammer':22};rec={'jab':16,'lunge':26,'hammer':30}
        start=starts[b['move']]+p['startup_bonus'];end=start+4
        if b['age']<end:
            if b['move']=='hammer':return (-1 if gap<125 else 0),False,None
            return 0,True,None
        left=end+rec[b['move']]+p['recovery_bonus']-b['age']
        if gap<=170 and left>=17:return 0,False,'lunge'
        if gap<=95 and left>=9:return 0,False,'jab'
        return (1 if gap>125 else 0),False,None
    return (1 if gap>125 else 0),True if gap<=125 else False,None

def solve(page,state_dir:Path,out_dir:Path,mechanic=MECHANIC_ID):
    assert mechanic==MECHANIC_ID
    page.locator('.tin-start').click()
    held=set();direction=0;guard=False;shot=False
    deadline=time.monotonic()+110
    while time.monotonic()<deadline:
        m=page.evaluate('({sim:window.tinDuelistModel.sim,world:window.tinDuelistModel.state.world,mode:window.tinDuelistModel.state.control_condition?.interaction||"full"})')
        if m['sim']['status']!='active':break
        d,g,attack=choose(m['sim'],m['world'])
        if m['mode']=='full':
            desired=set()
            if d:desired.add('ArrowRight' if d>0 else 'ArrowLeft')
            if g:desired.add('Space')
            for key in held-desired:page.keyboard.up(key)
            for key in desired-held:page.keyboard.down(key)
            held=desired
            if attack:page.keyboard.press({'jab':'j','lunge':'k','hammer':'l'}[attack])
        else:
            if d!=direction:page.locator(f'[data-action="direction"][data-value="{d}"]').click()
            if g!=guard:page.locator(f'[data-action="guard"][data-value="{str(g).lower()}"]').click()
            if attack:page.locator(f'[data-action="{attack}"]').click()
            direction,guard=d,g
        if not shot and m['sim']['contacts']:
            page.screenshot(path=str(out_dir/'tin_duelist-active.png'));shot=True
        page.wait_for_timeout(170)
    for key in held:page.keyboard.up(key)
    final=page.evaluate('window.tinDuelistModel.sim')
    page.screenshot(path=str(out_dir/'tin_duelist-solved.png'))
    assert final['status']=='won',final
    page.locator('.tin-submit').click()
    page.wait_for_function('document.querySelector(".tin-verdict").textContent==="PASS"')

def fail_once(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    before=page.evaluate('window.tinDuelistModel.state.challenge_id')
    page.locator('.tin-retry').click()
    page.wait_for_function('(old)=>window.tinDuelistModel.state.challenge_id!==old',arg=before)
    page.screenshot(path=str(out_dir/'tin_duelist-failure-fresh.png'))
