"""Independent integer transport replay. Never trusts a delivered-count claim."""
from __future__ import annotations
import copy
from collections import deque

MECHANIC_ID='lantern_lane'


def edge(a,b): return f'{min(a,b)}:{max(a,b)}'


def neighbors(w,a):
    x,y=a%11,a//11
    return [b for b in (a-11,a-1,a+1,a+11) if 0<=b<77 and abs(b%11-x)+abs(b//11-y)==1 and (not w['parameters']['river'] or (a%11!=5 or a//11 in w['bridges']) and (b%11!=5 or b//11 in w['bridges']))]


def initial(w):
    return dict(tick=0, status='active', roads={edge(a,b):False for a,b in w['initial_roads']},
                entrances=[h['entrance'] for h in w['homes']], sites=[dict(active=x['parent']<0,queue=0,made=0,delivered=0,meter=x['phase']) for x in w['sites']],
                carts=[dict(home=i,node=h['node'],dest=-1,returning=False,to=-1,remaining=0) for i,h in enumerate(w['homes']) for _ in range(w['parameters']['fleet'])],
                peak_queue=0,wait_ticks=0)


def route(w,s,start,target):
    buildings={h['node'] for h in w['homes']}|{x['node'] for x in w['sites']}
    parents={start:None}; q=deque([start])
    while q:
        a=q.popleft()
        if a==target:
            path=[]
            while a is not None: path.append(a); a=parents[a]
            return path[::-1]
        for b in neighbors(w,a):
            if b in parents or edge(a,b) not in s['roads'] or s['roads'][edge(a,b)]:continue
            if b in buildings and b!=target:continue
            valid=True
            for i,h in enumerate(w['homes']):
                if a==h['node'] and b!=s['entrances'][i] or b==h['node'] and a!=s['entrances'][i]:valid=False
            if valid:parents[b]=a;q.append(b)
    return None


def advance(w,s):
    if s['status']!='active':return
    p=w['parameters'];s['tick']+=1
    for j,site in enumerate(s['sites']):
        spec=w['sites'][j]
        if not site['active'] and s['sites'][spec['parent']]['delivered']>=2:
            site['active']=True;site['meter']=0
        if not site['active'] or site['made']>=p['quota']:continue
        delivered=sum(x['delivered'] for x in s['sites'])
        interval=spec['interval']*(100-p['growth_percent'] if delivered>=p['colors']*p['quota']//2 else 100)//100
        site['meter']+=1
        if site['meter']>=interval:
            site['meter']-=interval;site['made']+=1;site['queue']+=1
            s['peak_queue']=max(s['peak_queue'],site['queue'])
            if site['queue']>p['queue_limit']:s['status']='overflow';return
    # Complete occupied segments before routing. A deleted occupied segment stays
    # visibly closing until its last cart leaves; no teleportation or lost cart.
    for c in s['carts']:
        if c['remaining']:
            c['remaining']-=1
            if not c['remaining']:c['node']=c['to'];c['to']=-1
    occupied={edge(c['node'],c['to']) for c in s['carts'] if c['remaining']}
    for e in list(s['roads']):
        if s['roads'][e] and e not in occupied:del s['roads'][e]
    for c in s['carts']:
        if c['remaining']:continue
        home=w['homes'][c['home']]
        if c['dest']>=0 and not c['returning'] and c['node']==w['sites'][c['dest']]['node']:
            site=s['sites'][c['dest']];site['queue']-=1;site['delivered']+=1;c['returning']=True
        if c['returning'] and c['node']==home['node']:
            c['dest']=-1;c['returning']=False
        if c['dest']<0:
            choices=[]
            for j,site in enumerate(s['sites']):
                reserved=sum(k['dest']==j and not k['returning'] for k in s['carts'])
                if site['active'] and w['sites'][j]['color']==home['color'] and site['queue']>reserved:
                    path=route(w,s,c['node'],w['sites'][j]['node'])
                    if path:choices.append((len(path),j))
            if choices:c['dest']=min(choices)[1]
        if c['dest']<0:continue
        target=home['node'] if c['returning'] else w['sites'][c['dest']]['node']
        path=route(w,s,c['node'],target)
        if path and len(path)>1 and edge(c['node'],path[1]) not in occupied:
            c['to']=path[1];c['remaining']=p['trip_ticks'];occupied.add(edge(c['node'],c['to']))
        else:s['wait_ticks']+=1
    if all(x['delivered']>=p['quota'] for x in s['sites']):s['status']='delivered'
    elif s['tick']>=p['max_ticks']:s['status']='timeout'


def apply(w,s,event):
    """Atomic road segment or entrance action; invalid UI operations are no-ops."""
    if s['status']!='active':return False
    kind=event.get('type');a=event.get('a');b=event.get('b')
    if type(a) is not int or type(b) is not int or not 0<=a<77 or b not in neighbors(w,a):return False
    if kind=='orient':
        for i,h in enumerate(w['homes']):
            if a==h['node']:
                if any(x['node']==b for x in w['sites']+w['homes']):return False
                s['entrances'][i]=b;return True
        return False
    e=edge(a,b)
    if kind=='remove':
        if e not in s['roads']:return False
        if any(c['remaining'] and edge(c['node'],c['to'])==e for c in s['carts']):s['roads'][e]=True
        else:del s['roads'][e]
        return True
    if kind!='road':return False
    if any(not s['sites'][j]['active'] and x['node'] in (a,b) for j,x in enumerate(w['sites'])):return False
    if e in s['roads']:s['roads'][e]=False;return True
    if len(s['roads'])>=w['parameters']['road_budget']:return False
    s['roads'][e]=False;return True


def grade(payload,truth,public):
    def fail(msg):return dict(graded=True,passed=False,feedback=msg)
    try:
        for key in ('mechanic_id','task_id','challenge_id'):
            if not truth.get(key) or payload.get(key)!=truth[key] or public.get(key)!=truth[key]:return fail('stale task, challenge, or mechanic')
        if truth['mechanic_id']!=MECHANIC_ID or truth.get('control_condition')!=public.get('control_condition') or truth['world']!=public['world']:return fail('transport contract mismatch')
        mode=(truth.get('control_condition') or {}).get('interaction','full')
        if payload.get('interaction_mode')!=mode:return fail('wrong interaction mode')
        events=payload.get('events');terminal=payload.get('terminal_tick')
        if not isinstance(events,list) or len(events)>4000 or type(terminal) is not int or not 0<=terminal<=truth['world']['parameters']['max_ticks']:return fail('malformed transcript')
        w=truth['world'];s=initial(w)
        sources={'road':'road_drag','orient':'entrance_drag','remove':'road_right_click'} if mode=='full' else {'road':'road_click_pair','orient':'entrance_button','remove':'remove_button'}
        for i,e in enumerate(events):
            t=e.get('tick')
            if type(t) is not int or not s['tick']<=t<=terminal or e.get('sequence')!=i+1 or e.get('input_source')!=sources.get(e.get('type')):return fail('invalid event order or input surface')
            while s['tick']<t:
                if s['status']!='active':return fail('events after terminal state')
                advance(w,s)
            accepted=apply(w,s,e)
            if e.get('accepted') is not accepted:return fail('road/entrance effect disagrees with replay')
        while s['tick']<terminal:
            if s['status']!='active':return fail('clock after terminal state')
            advance(w,s)
        if payload.get('final_state')!=s:return fail('transport state disagrees with independent replay')
        passed=s['status']=='delivered' and payload.get('completed') is True
        return dict(graded=True,passed=passed,feedback=f"{sum(x['delivered'] for x in s['sites'])}/{len(s['sites'])*w['parameters']['quota']} deliveries; peak queue {s['peak_queue']}/{w['parameters']['queue_limit']}; {s['status']}")
    except (TypeError,ValueError,KeyError,IndexError,AttributeError):return fail('malformed transport result')
