"""Ordinary-input structural solver. Uses chart geometry and visible hit marks;
never reads hidden vessel placement. This is scripted wiring evidence, not CUA evaluation.
"""
from pathlib import Path
import json
import math
import time

MECHANIC_ID='coordinates_by_another_name'


def click(page, selector):
    box=page.locator(selector).bounding_box()
    assert box is not None, selector
    page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)


def set_address(page, world, mode, address):
    opts=[sorted(world['bands']),list('ABC'),list(range(1,world['columns']+1))+['*']]
    for a,value in enumerate(address):
        i=opts[a].index(value)
        if mode=='simplified':
            click(page,f'.cn-values button[data-axis="{a}"][data-index="{i}"]')
        else:
            box=page.locator(f'.cn-dial[data-axis="{a}"]').bounding_box()
            angle=math.radians(max(-209.8,min(29.8,-210+240*i/(len(opts[a])-1))))
            start=(box['x']+box['width']/2,box['y']+box['height']/2)
            end=(box['x']+(84+56*math.cos(angle))/168*box['width'],box['y']+(84+56*math.sin(angle))/168*box['height'])
            page.mouse.move(*start);page.mouse.down();page.mouse.move(*end);page.mouse.up()


def shoot(page,world,mode,address):
    set_address(page,world,mode,address)
    click(page,'#cn-fire')


def fail_once(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    old=json.loads((Path(state_dir)/'public_state.json').read_text())['challenge_id']
    click(page,'#cn-certify')
    page.locator('#cn-continue').wait_for()
    page.screenshot(path=str(out_dir/f'{mechanic}-failure.png'))
    click(page,'#cn-continue')
    new=json.loads((Path(state_dir)/'public_state.json').read_text())['challenge_id']
    assert old!=new
    page.screenshot(path=str(out_dir/f'{mechanic}-recovery.png'))


def solve(page,state_dir,out_dir,mechanic=MECHANIC_ID,pace_ms=0):
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    public=json.loads((Path(state_dir)/'public_state.json').read_text())
    world=public['world'];mode=public.get('control_condition',{}).get('interaction','full')
    cells=world['cells'];bypos={(c['row'],c['column']):c['id'] for c in cells}
    for step in range(len(cells)+3):
        if page.locator('.cn-status').inner_text()=='ALL VESSELS SUNK':break
        # Inspect only rendered feedback. An equivalent screenshot policy can
        # enumerate potential straight vessels against these persistent marks.
        classes=page.locator('.cn-cell').evaluate_all('(es)=>es.map(e=>e.getAttribute("class"))')
        seen={c['id'] for c,cl in zip(cells,classes) if any(x in cl for x in ['hit','miss','sunk'])}
        hits={c['id'] for c,cl in zip(cells,classes) if 'hit' in cl}
        sunk={c['id'] for c,cl in zip(cells,classes) if 'sunk' in cl}
        misses=seen-hits-sunk
        lengths=[n for n,cl in zip(world['fleet_lengths'],page.locator('.cn-fleet>div').evaluate_all('(es)=>es.map(e=>e.className)')) if cl!='sunk']
        scores={c['id']:0 for c in cells if c['id'] not in seen}
        for n in lengths:
            for r,c in bypos:
                for dr,dc in [(0,1),(1,0)]:
                    positions=[(r+dr*k,c+dc*k) for k in range(n)]
                    if any(p not in bypos for p in positions):continue
                    ids={bypos[p] for p in positions}
                    if ids & (misses|sunk):continue
                    weight=1+30*len(ids&hits)
                    for id_ in ids-seen:scores[id_]+=weight
        if not scores:raise AssertionError('visible search exhausted without success')
        if int(page.locator('.cn-sweeps').inner_text())>0:
            run=max(world['runs'],key=lambda run:sum(scores.get(c['id'],0) for c in cells if c['band']==run['band'] and c['block']==run['block']))
            address=[run['band'],run['block'],'*']
        else:
            chosen=max(scores,key=scores.get);cell=next(c for c in cells if c['id']==chosen)
            address=[cell['band'],cell['block'],cell['count']]
        shoot(page,world,mode,address)
        if pace_ms:page.wait_for_timeout(pace_ms)
        if step in [0,3,8]:page.screenshot(path=str(out_dir/f'{mechanic}-active-{step}.png'))
    assert page.locator('.cn-status').inner_text()=='ALL VESSELS SUNK'
    page.screenshot(path=str(out_dir/f'{mechanic}-solved.png'))
    click(page,'#cn-certify')
    deadline=time.monotonic()+10
    while page.locator('.readout').get_attribute('data-status')!='passed':
        if time.monotonic()>deadline:raise AssertionError('server did not accept visible solution')
        time.sleep(.05)
    page.screenshot(path=str(out_dir/f'{mechanic}-pass.png'))
