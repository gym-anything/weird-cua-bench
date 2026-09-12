"""Replay the orchard's fixed-step economy; no client outcome is authoritative."""
from __future__ import annotations
import copy

MECHANIC_ID = 'orchard_exchange'
DELTAS = {'up': (0,-1), 'right': (1,0), 'down': (0,1), 'left': (-1,0)}

def initial(w):
    return dict(tick=0, pos=w['start'][:], inventory=[0,0], hunger=w['initial_hunger'], harvest=0,
                bots=copy.deepcopy(w['bots']), offer=[1,1], posted=False, trades=[], delivered=False,
                failed=False, message='Harvest apples, barter, and bring the basket home.')

def terms(w,b):
    return [b['ask'] + int(w['changing_terms'] and b['inventory'][0]>=2), b['give']]

def step(w,s):
    if s['failed'] or s['delivered']: return
    s['tick'] += 1
    s['hunger'] -= 1
    if s['hunger'] <= 0 or s['tick'] >= w['limit_ticks']:
        s['failed']=True; s['message']='FAIL · hungry courier' if s['hunger']<=0 else 'FAIL · market closed'; return
    for b in s['bots']:
        b['hunger']-=1; b['progress']+=1
        if b['progress']>=b['harvest_ticks']:
            b['progress']=0
            if sum(b['inventory']) < b['capacity']: b['inventory'][1]+=1
        if b['hunger']<=0:
            food=0 if b['inventory'][0] else 1
            if b['inventory'][food]:
                b['inventory'][food]-=1
                b['hunger']=b['meal_ticks'] if food==0 else b['meal_ticks']//2
    crop=next((t for t in w['trees'] if t['pos']==s['pos']),None)
    if crop:
        s['harvest']+=1
        duration=w['apple_ticks'] if crop['fruit']==0 else w['banana_ticks']
        if s['harvest']>=duration:
            s['harvest']=0
            amount=min(2 if crop['fruit']==0 else 1,w['capacity']-sum(s['inventory']))
            s['inventory'][crop['fruit']]+=amount
            s['message']='Harvest in basket' if amount else 'Basket full · eat or trade to make room'
    else: s['harvest']=0
    # Posted contracts settle at the next fixed-step clearing, never at editing time.
    if s['posted']:
        for index,b in enumerate(s['bots']):
            give,take=s['offer']
            if sum((s['pos'][j]-b['pos'][j])**2 for j in (0,1))>w['radius']**2: continue
            if terms(w,b)!=[give,take]: continue
            if s['inventory'][0]<give or b['inventory'][1]<take: continue
            if sum(s['inventory'])-give+take>w['capacity'] or sum(b['inventory'])+give-take>b['capacity']: continue
            s['inventory'][0]-=give; s['inventory'][1]+=take
            b['inventory'][0]+=give; b['inventory'][1]-=take
            s['trades'].append(dict(tick=s['tick'],farmer=index,give=give,take=take))
            s['posted']=False; s['message']='TRADE SETTLED · fruit changed hands'; break

def advance(w,s,tick):
    while s['tick']<tick and not (s['failed'] or s['delivered']): step(w,s)

def act(w,s,kind,value=None):
    if s['failed'] or s['delivered']: return
    if kind in DELTAS:
        d=DELTAS[kind]; p=[s['pos'][0]+d[0],s['pos'][1]+d[1]]
        if 0<=p[0]<w['width'] and 0<=p[1]<w['height'] and p not in w['walls']:
            s['pos']=p; s['harvest']=0
            if p in w['water']: s['hunger']-=w['water_cost']
            s['message']='Wading costs food' if p in w['water'] else 'Walking'
            if s['hunger']<=0: s['failed']=True; s['message']='FAIL · hungry courier'
        else: s['message']='Fence · choose another path'
    elif kind in ('give','take'):
        i=0 if kind=='give' else 1
        s['offer'][i]=max(1,min(4,s['offer'][i]+value)); s['posted']=False
        s['message']='Draft offer · post when ready'
    elif kind=='post':
        s['posted']=True; s['message']='OFFER POSTED · waiting for reciprocal stock-backed terms'
    elif kind=='cancel': s['posted']=False; s['message']='Offer withdrawn'
    elif kind=='eat':
        if s['inventory'][value]:
            s['inventory'][value]-=1
            s['hunger']=min(w['max_hunger'],s['hunger']+w['food'][value]); s['message']='Meal eaten · basket changed'
        else: s['message']='No fruit of that kind to eat'
    elif kind=='deliver':
        if s['pos']==w['stall'] and all(a>=b for a,b in zip(s['inventory'],w['demand'])):
            s['delivered']=True; s['message']='PASS · DELIVERY RECEIVED'
        else: s['message']='Delivery needs the full basket at the striped stall'
    else: raise ValueError('unknown action')

def grade(payload,ground_truth,public_state):
    def bad(msg): return dict(graded=True,passed=False,score=0,feedback=msg)
    try:
        for k in ('mechanic_id','task_id','challenge_id'):
            if not ground_truth.get(k) or payload.get(k)!=ground_truth[k] or public_state.get(k)!=ground_truth[k]: return bad(k+' mismatch')
        if ground_truth['mechanic_id']!=MECHANIC_ID: return bad('wrong mechanic')
        if ground_truth['world']!=public_state['world'] or ground_truth.get('control_condition')!=public_state.get('control_condition'): return bad('world or condition mismatch')
        w=ground_truth['world']; s=initial(w)
        mode=(ground_truth.get('control_condition') or {}).get('interaction','full')
        events=payload.get('events')
        if not isinstance(events,list) or not 1<=len(events)<=3000: return bad('missing action transcript')
        previous=0
        for e in events:
            t=e.get('tick'); k=e.get('kind'); v=e.get('value')
            if type(t)!=int or not previous<=t<w['limit_ticks']: return bad('invalid action time')
            if s['failed'] or s['delivered']: return bad('action after terminal state')
            source=('keyboard' if mode=='full' else 'direction_buttons') if k in DELTAS else 'offer_buttons'
            if e.get('source')!=source: return bad('wrong interaction input')
            if k in ('give','take') and (type(v)!=int or v not in (-1,1)): return bad('invalid offer edit')
            if k=='eat' and (type(v)!=int or v not in (0,1)): return bad('invalid meal')
            advance(w,s,t)
            if s['failed']: return bad('hunger or market failure before action')
            act(w,s,k,v); previous=t
        end=payload.get('end_tick')
        if type(end)!=int or not previous<=end<=w['limit_ticks']: return bad('invalid final time')
        advance(w,s,end)
        if payload.get('final')!=s: return bad('submitted state differs from independent replay')
        passed=s['delivered'] and not s['failed'] and s['hunger']>0
        return dict(graded=True,passed=passed,score=100 if passed else 0,feedback=s['message'],trades=len(s['trades']))
    except (KeyError,TypeError,ValueError,IndexError,OverflowError) as exc: return bad('invalid transcript: '+str(exc))

def cheat(public_state,ground_truth):
    return {'answers':[], 'instruction':'Harvest apples. Match a nearby farmer’s current offer, wait for settlement, eat as needed, then deliver.'}
