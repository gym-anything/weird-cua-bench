"""Implementation witness: reads generated repairs, executes only normal pointer controls.

This is not a screenshot-only agent evaluation or a difficulty measurement.
"""
import json
import math
from pathlib import Path
from playwright.sync_api import expect
MECHANIC_ID='threshold_grapevine'


def scratch_path(world, edges, edge):
    points=[(n['x'],n['y']) for n in world['nodes']]
    a,b=(points[i] for i in edge);dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
    def distance(p,a,b):
        x,y=b[0]-a[0],b[1]-a[1];u=max(0,min(1,((p[0]-a[0])*x+(p[1]-a[1])*y)/(x*x+y*y)))
        return math.hypot(p[0]-a[0]-u*x,p[1]-a[1]-u*y)
    candidates=[]
    for k in range(15,86):
        f=k/100;p=(a[0]+f*dx,a[1]+f*dy)
        clearance=min([math.dist(p,v)-28 for v in points]+[distance(p,points[u],points[v]) for u,v in edges if (u,v)!=tuple(edge)])
        candidates.append((clearance,p))
    clearance,p=max(candidates)
    if clearance<3:raise AssertionError('No isolated cut segment')
    half=min(16,clearance*.65)
    return [[p[0]-dy/length*half,p[1]+dx/length*half],[p[0]+dy/length*half,p[1]-dx/length*half]]


def perform_edit(page, world, edges, edge, full, *, sparse=False):
    adding=tuple(edge) not in edges
    b=page.locator('.tg-root canvas').bounding_box()
    def screen(p):return b['x']+p[0]*b['width']/860,b['y']+p[1]*b['height']/470
    points=[(world['nodes'][i]['x'],world['nodes'][i]['y']) for i in edge]
    if full:
        path=points if adding else scratch_path(world,edges,edge)
        page.mouse.move(*screen(path[0]));page.mouse.down();page.mouse.move(*screen(path[1]),steps=1 if sparse else 12);page.mouse.up()
    else:
        for p in points:page.mouse.click(*screen(p))
        page.locator(f'[data-action={"add" if adding else "cut"}]').click()
    if adding:edges.add(tuple(edge))
    else:edges.remove(tuple(edge))
    expect(page.locator('.readout')).to_contain_text('Friendship '+('added' if adding else 'cut'))


def fail_once(page,state_dir:Path,out_dir:Path,mechanic=MECHANIC_ID):
    old=json.loads((state_dir/'public_state.json').read_text())['challenge_id']
    page.locator('.tg-abandon').click();expect(page.locator('.tg-verdict')).to_contain_text('FAIL')
    page.screenshot(path=str(out_dir/f'{mechanic}-failure.png'))
    page.get_by_role('button',name='NEW NEIGHBOURHOOD',exact=True).click()
    expect(page.locator('.tg-verdict')).to_be_hidden()
    new=json.loads((state_dir/'public_state.json').read_text())['challenge_id'];assert new!=old
    page.screenshot(path=str(out_dir/f'{mechanic}-recovery.png'))


def solve(page,state_dir:Path,out_dir:Path,mechanic=MECHANIC_ID,advance=None):
    truth=json.loads((state_dir/'ground_truth.json').read_text());w=truth['world'];full=(truth.get('control_condition') or {}).get('interaction','full')=='full'
    for stage,repair in enumerate(truth['repairs']):
        edges={tuple(e) for e in w['edges']}
        for edge in repair:perform_edit(page,w,edges,edge,full)
        page.screenshot(path=str(out_dir/f'{mechanic}-stage{stage+1}-prepared.png'))
        page.locator('.tg-run').click()
        if advance:
            while page.locator('.tg-run').is_disabled():advance()
        else:expect(page.locator('.tg-run')).to_be_enabled(timeout=12000)
        expect(page.locator('.tg-accept')).to_be_visible()
        page.screenshot(path=str(out_dir/f'{mechanic}-stage{stage+1}-settled.png'))
        page.locator('.tg-accept').click()
    expect(page.locator('.readout')).to_have_attribute('data-status','passed',timeout=12000)
