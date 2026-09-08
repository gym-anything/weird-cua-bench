"""Implementation evidence solver: reads generated geometry, uses only UI inputs."""
import json
import importlib.util
import itertools
import math
from pathlib import Path
from playwright.sync_api import expect
MECHANIC_ID='clockwork_courier_works'

def physics():
    path = Path(__file__).resolve().parents[2]/'shared_runtime/server/incubator_graders/clockwork_courier_works.py'
    spec = importlib.util.spec_from_file_location('courier_solver_physics', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def designs(state):
    """A finite engineering search for evidence, never a grader answer key.

    Candidate dimensions depend on visible hub positions; delivery is checked
    by the unmodified physics. The UI still accepts constructions outside this
    diagnostic search, including other wheel counts and topologies.
    """
    x, y, _ = state['parcel']
    preferred = [(36,36,35,35,75), (48,48,15,15,85),
                 (24,24,-15,-15,75), (24,24,0,0,55),
                 (36,36,0,0,75), (36,36,-15,0,55),
                 (24,36,0,30,75), (24,24,-15,30,55)]
    grid = itertools.product([24,36,48], [24,36,48], [-15,0,15,30], [-15,0,15,30], [55,75,85])
    seen = set()
    for r1,r2,dy1,dy2,spacing in itertools.chain(preferred,grid):
        key = (r1,r2,dy1,dy2,spacing)
        if key in seen: continue
        seen.add(key)
        wheels = [[x-spacing,y+dy1,r1,1],[x+spacing,y+dy2,r2,1]]
        x0,y0,x1,y1 = state['build_box']
        if any(not (x0+r<=xx<=x1-r and y0+r<=yy<=y1-r) for xx,yy,r,_ in wheels): continue
        bodies = [state['parcel'],*wheels]
        if any(math.hypot(p[0]-q[0],p[1]-q[1]) < p[2]+q[2]
               for i,p in enumerate(bodies) for q in bodies[i+1:]): continue
        for rods in [[(0,1),(0,2),(1,2)], [(0,1),(0,2)]]:
            yield wheels, rods


def choose_design(state):
    model = physics()
    for wheels, rods in designs(state):
        if model.simulate(state, wheels, rods)['delivered']:
            return wheels, rods
    raise AssertionError('No delivery found in the evidence solver search')


def construct(page,state,radius=None,height=None,design=None):
    mode=state.get('control_condition',{}).get('interaction','full')
    if design is not None:
        wheels, rods = design
    elif radius is not None or height is not None:
        x,y,_ = state['parcel']
        wheels=[[x-75,height or 345,radius or 36,1],[x+75,height or 345,radius or 36,1]]
        rods=[(0,1),(0,2),(1,2)]
    else:
        wheels, rods = choose_design(state)
    positions=[tuple(state['parcel'][:2]),*[tuple(w[:2]) for w in wheels]]
    box=page.locator('.cc-canvas').evaluate("canvas=>{const r=canvas.getBoundingClientRect(),s=getComputedStyle(canvas),l=parseFloat(s.borderLeftWidth)||0,t=parseFloat(s.borderTopWidth)||0;return {x:r.x+l,y:r.y+t,width:r.width-l-(parseFloat(s.borderRightWidth)||0),height:r.height-t-(parseFloat(s.borderBottomWidth)||0)};}")
    def pt(p):return (box['x']+p[0]/920*box['width'],box['y']+p[1]/480*box['height'])
    def drag(a,b):
        page.mouse.move(*a);page.mouse.down();page.mouse.move(*b,steps=8);page.mouse.up()
    for wheel in wheels:
        p=wheel[:2]
        button=page.locator(f'[data-radius="{wheel[2]}"]')
        if mode=='full':
            r=button.bounding_box();drag((r['x']+r['width']/2,r['y']+r['height']/2),pt(p))
        else:button.click();page.mouse.click(*pt(p))
    page.locator('[data-tool="rod"]').click()
    for a,b in rods:
        if mode=='full':drag(pt(positions[a]),pt(positions[b]))
        else:page.mouse.click(*pt(positions[a]));page.mouse.click(*pt(positions[b]))
    return positions

def fail_once(page,state_dir,out_dir,mechanic):
    old=json.loads((state_dir/'public_state.json').read_text())['challenge_id']
    page.locator('.cc-submit').click()
    expect(page.locator('.readout')).to_contain_text('FAIL')
    page.screenshot(path=str(out_dir/'failure-fresh.png'))
    new=json.loads((state_dir/'public_state.json').read_text())['challenge_id']
    assert new!=old

def solve(page,state_dir,out_dir,mechanic):
    assert mechanic==MECHANIC_ID
    state=json.loads((state_dir/'public_state.json').read_text())
    construct(page,state)
    page.screenshot(path=str(out_dir/'constructed.png'))
    page.locator('.cc-run').click()
    page.wait_for_timeout(2500)
    page.screenshot(path=str(out_dir/'active.png'))
    expect(page.locator('.readout')).to_contain_text('DELIVERED',timeout=30000)
    page.screenshot(path=str(out_dir/'delivered.png'))
    page.locator('.cc-submit').click()
    expect(page.locator('.readout')).to_have_text('PASS',timeout=10000)
