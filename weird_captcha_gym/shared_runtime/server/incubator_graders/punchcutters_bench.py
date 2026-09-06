"""Replay pen operations, compare cubic geometry, then grade optical whitespace."""
from __future__ import annotations
import math
MECHANIC_ID='punchcutters_bench'


def flatten(nodes, steps=48):
    points=[]
    for a,b in zip(nodes,nodes[1:]+nodes[:1]):
        for k in range(steps):
            t=k/steps;u=1-t
            points.append([u**3*a[j]+3*u*u*t*(a[j]+a[j+2])+3*u*t*t*(b[j]-b[j+2])+t**3*b[j] for j in (0,1)])
    return points


def point_segment(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]; den=dx*dx+dy*dy
    t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)) if den else 0
    return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)


def deviation(nodes,master):
    a,b=flatten(nodes),flatten(master)
    def directed(x,y):
        segments=list(zip(y,y[1:]+y[:1]))
        return max(min(point_segment(p,s,e) for s,e in segments) for p in x)
    return max(directed(a,b),directed(b,a))


def glyph_polygons(bench,nodes):
    ox,oy=bench['glyph_origin'];w,h=bench['glyph_scale']
    return [([[ (x-ox)/w*g['width'], (y-oy)/h*140] for x,y in flatten(nodes)] if i==bench['cut_index'] else g['polygon']) for i,g in enumerate(bench['glyphs'])]


def edges(poly):
    # Mean facing ink edges over central 80% of cap height; negative space is
    # integrated by horizontal scanline, not a bounding-box distance.
    left=[];right=[]
    for k in range(64):
        y=14+(k+.5)*112/64; xs=[]
        for a,b in zip(poly,poly[1:]+poly[:1]):
            if (a[1]<=y<b[1]) or (b[1]<=y<a[1]):
                xs.append(a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1]))
        if xs: left.append(min(xs));right.append(max(xs))
    if len(left)<48: raise ValueError('glyph has insufficient ink height')
    return sum(left)/len(left),sum(right)/len(right)


def spacing_reference(bench,nodes):
    es=[edges(p) for p in glyph_polygons(bench,nodes)]
    initial=bench['initial_positions'];n=len(es)
    gap=(initial[-1]-initial[0]-sum(es[i][1]-es[i+1][0] for i in range(n-1)))/(n-1)
    ref=[initial[0]]
    for i in range(n-1):ref.append(ref[-1]+es[i][1]-es[i+1][0]+gap)
    return ref


def spacing_score(bench,nodes,positions):
    ref=spacing_reference(bench,nodes)
    return max(0,100-2*max(abs(a-b) for a,b in zip(ref,positions)))


def grade(payload,ground_truth,public_state):
    def fail(msg):return dict(graded=True,passed=False,score=0,feedback=msg)
    for key in ('mechanic_id','task_id','challenge_id'):
        v=ground_truth.get(key)
        if not v or payload.get(key)!=v or public_state.get(key)!=v:return fail('stale task, challenge or mechanic')
    if ground_truth['mechanic_id']!=MECHANIC_ID:return fail('wrong mechanic')
    bench=ground_truth.get('bench');condition=ground_truth.get('control_condition')
    if not isinstance(bench,dict) or public_state.get('bench')!=bench or public_state.get('control_condition')!=condition:return fail('world or control mismatch')
    mode=(condition or {}).get('interaction','full');source={'full':'pen_drag','simplified':'pen_clicks'}.get(mode)
    if not source:return fail('invalid interaction')
    events=payload.get('events');nodes=[];closed=False;cut=False;certified=False;positions=list(bench['initial_positions']);dev=None
    if not isinstance(events,list) or not 1<=len(events)<=1200:return fail('missing transcript')
    def vec(v,n):
        if not isinstance(v,list) or len(v)!=n or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in v):raise ValueError('malformed geometry')
        return v
    try:
        for seq,e in enumerate(events,1):
            if not isinstance(e,dict) or e.get('sequence')!=seq or certified:raise ValueError('invalid event order')
            kind=e.get('kind')
            if kind=='node':
                if cut or closed or e.get('input_source')!=source or len(nodes)>=bench['node_budget']:raise ValueError('invalid pen action')
                a=vec(e.get('anchor'),2);tip=vec(e.get('tip'),2)
                if any(not 0<=v<=limit for v,limit in zip(a,[800,410])) or any(not 0<=v<=limit for v,limit in zip(tip,[800,410])):raise ValueError('pen outside work area')
                nodes.append(a+[tip[0]-a[0],tip[1]-a[1]])
            elif kind=='undo':
                if cut or not nodes or e.get('input_source')!='undo_button':raise ValueError('invalid undo')
                if closed:closed=False
                else:nodes.pop()
            elif kind=='close':
                if cut or closed or len(nodes)<3 or e.get('input_source')!='close_button':raise ValueError('invalid closure')
                closed=True
            elif kind=='proof':
                if cut or not closed or e.get('input_source')!='proof_button':raise ValueError('outline not closed')
                dev=deviation(nodes,bench['master'])
                if dev>bench['parameters']['outline_tolerance']:raise ValueError(f'outline deviation {dev:.2f}px exceeds tolerance')
                cut=True
            elif kind=='letter':
                i=e.get('index');start=e.get('start');end=e.get('end')
                if not cut or isinstance(i,bool) or not isinstance(i,int) or not 0<i<len(positions)-1:raise ValueError('fixed or premature letter')
                vec([start,end],2)
                if abs(start-positions[i])>.01 or not 20<=end<=720:raise ValueError('letter discontinuity')
                src=e.get('input_source')
                if mode=='simplified' and src!='letter_place':raise ValueError('wrong spacing input')
                if mode=='full' and src not in ('letter_drag','letter_key'):raise ValueError('wrong spacing input')
                if src=='letter_key' and min(abs((end-start)-delta) for delta in (-10,-1,1,10))>1e-6:raise ValueError('invalid key nudge')
                positions[i]=end
            elif kind=='certify':
                if not cut or e.get('input_source')!='certify_button':raise ValueError('cut stage incomplete')
                certified=True
            else:raise ValueError('unknown bench event')
        if not certified:return fail('bench not certified')
        # Preserve the word's order; the shape-dependent reference determines spacing.
        if any(positions[i]>=positions[i+1] for i in range(len(positions)-1)):return fail('letter order changed')
        score=spacing_score(bench,nodes,positions)
        passed=score>=bench['parameters']['spacing_threshold']
        return dict(graded=True,passed=passed,score=100 if passed else round(score,2),feedback=f'outline {dev:.2f}px; nodes {len(nodes)}/{bench["node_budget"]}; optical spacing {score:.1f}/100',metrics={'max_deviation_px':dev,'node_count':len(nodes),'node_budget':bench['node_budget'],'spacing_score':score})
    except (KeyError,ValueError,TypeError,OverflowError) as exc:return fail(str(exc))
