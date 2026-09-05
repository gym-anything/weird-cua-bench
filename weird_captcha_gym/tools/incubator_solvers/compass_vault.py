"""Privileged test planner; execution uses ordinary browser pointer inputs only."""
import importlib.util
import json
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
_spec=importlib.util.spec_from_file_location('compass_geometry',ROOT/'shared_runtime/server/incubator_graders/compass_vault.py')
g=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(g)
MECHANIC_ID='compass_vault'

def plan(world,mode='full'):
    m=g.Construction(world);ops=[]
    def nearest(p, refs=None):
        candidates=refs or list(m.points)
        # Same stable nearest-point resolution as the canvas, including coincident crossings.
        best=candidates[0]
        for ref in candidates:
            if g.dist(m.points[ref],p)<g.dist(m.points[best],p)-1e-5:best=ref
        if g.dist(m.points[best],p)>1e-4:raise ValueError(('missing constructed point',p))
        return best
    def op(kind,a,b=None):
        a=nearest(m.points[a]); b=nearest(m.points[b]) if b else None
        data={'kind':kind,'a':a,'input_source':'point_click' if kind=='point' else 'canvas_drag' if mode=='full' else 'canvas_clicks'}
        if b:data['b']=b
        idx=len(m.objects);ops.append(data);m.apply(data);return idx
    def crossing(i,j,which=0):
        return nearest(g.intersections(m.objects[i],m.objects[j])[which])
    def bisector(a,b):
        i=op('circle',a,b);j=op('circle',b,a)
        return op('line',crossing(i,j,0),crossing(i,j,1))
    def perpendicular(vertex,side_a,side_b,side_index):
        # Circle about the vertex meets the side twice; bisect the chord.
        circle=op('circle',vertex,side_a)
        candidates=g.intersections(m.objects[side_index],m.objects[circle])
        other=max(candidates,key=lambda p:g.dist(p,m.points[side_a]))
        return bisector(side_a,nearest(other))
    goal=world['goal']
    if goal=='midpoint':
        line=op('line',crossing(1,2,0),crossing(1,2,1));op('point',crossing(0,line))
    elif goal=='bisector':bisector('g0','g1')
    elif goal=='circumcenter':
        i=bisector('g0','g1');j=bisector('g1','g2');op('point',crossing(i,j))
    elif goal=='orthocenter':
        i=perpendicular('g2','g0','g1',0);j=perpendicular('g0','g1','g2',1);op('point',crossing(i,j))
    else:
        def angle(vertex,first,second,side_index):
            circle=op('circle',vertex,first)
            v=m.points[vertex];direction=g.sub(m.points[second],v)
            candidates=g.intersections(m.objects[side_index],m.objects[circle])
            point=max(candidates,key=lambda p:g.dot(g.sub(p,v),direction))
            other=nearest(point)
            line=bisector(first,other)
            return line
        i=angle('g0','g1','g2',2);j=angle('g1','g0','g2',1);center=crossing(i,j)
        perp=perpendicular(center,'g0','g1',0);foot=crossing(0,perp);op('circle',center,foot)
    return ops

def wait_readout(page,text):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        if text in page.locator('.readout').inner_text():return
        time.sleep(.05)
    raise AssertionError(page.locator('.readout').inner_text())

def fail_once(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    before=json.loads((state_dir/'ground_truth.json').read_text())['challenge_id']
    page.locator('#cv-test').click();wait_readout(page,'FAIL')
    assert json.loads((state_dir/'ground_truth.json').read_text())['challenge_id']!=before
    page.screenshot(path=str(out_dir/'compass_vault-fail-refresh.png'))

def solve(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    truth=json.loads((state_dir/'ground_truth.json').read_text());world=truth['world'];mode=(truth.get('control_condition') or {}).get('interaction','full');m=g.Construction(world)
    scale=.8;offset=[84.,54.]
    for index,op in enumerate(plan(world,mode)):
        page.locator(f'[data-tool="{op["kind"]}"]').click()
        box=page.locator('#cv-canvas').bounding_box()
        def screen(ref):
            p=m.points[ref];return (box['x']+(offset[0]+scale*p[0])*box['width']/840,box['y']+(offset[1]+scale*p[1])*box['height']/540)
        for _ in range(8):
            anchors=[screen(op[ref]) for ref in ('a','b') if ref in op]
            if all(box['x']+16<p[0]<box['x']+box['width']-16 and box['y']+16<p[1]<box['y']+box['height']-16 for p in anchors):break
            center=[420,270];world_center=[(center[j]-offset[j])/scale for j in range(2)]
            page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.wheel(0,120);page.wait_for_timeout(80)
            scale=max(.35,scale/1.15);offset=[center[j]-world_center[j]*scale for j in range(2)]
        a=screen(op['a']);b=screen(op['b']) if 'b' in op else None
        for p in [a]+([b] if b else []):
            if not(box['x']<p[0]<box['x']+box['width'] and box['y']<p[1]<box['y']+box['height']):raise ValueError(('offscreen anchor',index,op,p))
        if b and mode=='full':
            page.mouse.move(*a);page.mouse.down();page.mouse.move(*b,steps=8);page.mouse.up()
        else:
            page.mouse.click(*a)
            if b:page.mouse.click(*b)
        m.apply(op)
        page.wait_for_timeout(100)
        if index in (0,2,len(plan(world,mode))-2):page.screenshot(path=str(out_dir/f'compass_vault-active-{index}.png'))
    page.screenshot(path=str(out_dir/'compass_vault-solved.png'))
    page.locator('#cv-test').click();wait_readout(page,'PASS')
