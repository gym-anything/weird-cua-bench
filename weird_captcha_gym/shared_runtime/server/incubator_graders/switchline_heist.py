"""Independent fixed-step replay of wiring, traversal, light and attendant events."""
import copy

MECHANIC_ID='switchline_heist'

def initial(w):
    return dict(x=w['start'], move=0, hidden=False, item=False, caught=False, overlay=False,
                gates={g['id']:False for g in w['gates']}, light=True,
                wires=copy.deepcopy(w['wires']), permissions=list(w['initial_permissions']),
                gx=w['guard_x'], gd=w['guard_dir'], repair=0, tick=0, service_count=0)

def blocked(w,s,a,b):
    return any(not s['gates'][g['id']] and min(a,b)-18 < g['x'] < max(a,b)+18 for g in w['gates'])

def detect(w,s):
    if s['hidden'] or s['x'] < w['archive_start']: return
    delta=s['x']-s['gx']
    if abs(delta)<22 or (s['light'] and 0<=delta*s['gd']<=w['parameters']['sight']): s['caught']=True

def output(w,s,target):
    if target=='lamp':
        s['light']=not s['light']
        s['repair']=0
    elif target in s['gates']:
        gate=next(g for g in w['gates'] if g['id']==target)
        if s['gates'][target] and abs(s['x']-gate['x'])<18: return
        s['gates'][target]=not s['gates'][target]
        if s['gates'][target] and w['parameters']['interlock']:
            for k in s['gates']:
                if k!=target and abs(s['x']-next(g['x'] for g in w['gates'] if g['id']==k))>=18: s['gates'][k]=False

def tick(w,s):
    if s['caught']: return
    s['tick']+=1
    if s['move'] and not s['overlay'] and not s['hidden']:
        x=max(44,min(962,s['x']+s['move']*w['player_speed']))
        if not blocked(w,s,s['x'],x): s['x']=x
    for chip in w['chips']:
        if abs(s['x']-chip['x'])<=22 and chip['color'] not in s['permissions']: s['permissions'].append(chip['color'])
    if not s['light']:
        s['gd']=1
        s['gx']=min(948,s['gx']+w['guard_speed'])
        if s['gx']==948:
            s['repair']+=1
            if s['repair']>=w['parameters']['repair_ticks']:
                s['light']=True
                s['repair']=0
                s['service_count']+=1
                # The attendant restores the lamp mechanically, then operates the wired service switch.
                output(w,s,s['wires']['service'])
    else:
        s['gx']+=s['gd']*w['guard_speed']
        if s['gx']>=948: s['gx']=948;s['gd']=-1
        if s['gx']<=808: s['gx']=808;s['gd']=1
    detect(w,s)

def action(w,s,e):
    a=e['type']
    if a=='overlay':
        s['overlay']=not s['overlay'];s['move']=0
    elif a=='move':
        if type(e.get('direction')) is not int or e['direction'] not in (-1,0,1): raise ValueError('invalid direction')
        s['move']=e['direction']
    elif a=='hide':
        if not s['overlay'] and any(abs(s['x']-x)<=25 for x in w['booths']):
            s['hidden']=not s['hidden'];s['move']=0
    elif a=='wire':
        src=next((x for x in w['switches'] if x['id']==e.get('source')),None)
        dst=next((x for x in w['outputs'] if x['id']==e.get('target')),None)
        if not s['overlay'] or not src or not dst or src['color']!=dst['color'] or src['color'] not in s['permissions'] or (src['kind']=='attendant' and dst['kind']!='gate'):
            raise ValueError('illegal circuit connection')
        s['wires'][src['id']]=dst['id']
    elif a=='use':
        src=next((x for x in w['switches'] if x['id']==e.get('source')),None)
        if s['overlay'] or not src or src['kind']!='switch' or abs(s['x']-src['x'])>38 or blocked(w,s,s['x'],src['x']):
            raise ValueError('switch out of physical reach')
        output(w,s,s['wires'][src['id']])
    elif a=='pickup':
        if s['overlay'] or abs(s['x']-w['item'])>24 or s['item']: raise ValueError('item out of reach')
        s['item']=True
        if w['parameters']['alarm']: s['light']=True;s['repair']=0
    elif a=='extract': pass
    else: raise ValueError('unknown action')
    detect(w,s)

def grade(payload,truth,public):
    def fail(msg): return dict(graded=True,passed=False,feedback=msg)
    if not all(isinstance(value,dict) for value in (payload,truth,public)):
        return fail('result, ground truth and public state must be objects')
    try:
        for k in ('mechanic_id','task_id','challenge_id'):
            if not truth.get(k) or payload.get(k)!=truth[k] or public.get(k)!=truth[k]: return fail('stale task or challenge')
        if truth['mechanic_id']!=MECHANIC_ID or public['world']!=truth['world'] or public.get('control_condition')!=truth.get('control_condition'): return fail('world or condition mismatch')
        mode=(truth.get('control_condition') or {}).get('interaction','full')
        expected='proxy' if mode=='simplified' else 'direct'
        events=payload.get('events')
        if not isinstance(events,list) or not 1<=len(events)<=5000: return fail('missing action transcript')
        w=truth['world'];s=initial(w)
        for i,e in enumerate(events):
            if not isinstance(e,dict) or e.get('seq')!=i+1 or e.get('input_source')!=expected: return fail('invalid sequence or interaction surface')
            t=e.get('tick')
            if type(t) is not int or not s['tick']<=t<=12000: return fail('invalid time')
            while s['tick']<t:
                tick(w,s)
                if s['caught']: return fail('caught during traversal')
            if s['caught']: return fail('caught')
            action(w,s,e)
            if e['type']=='extract' and i!=len(events)-1: return fail('events after extraction')
        passed=events[-1]['type']=='extract' and s['item'] and s['x']<=84 and not s['caught']
        return dict(graded=True,passed=passed,feedback='Item recovered and returned unseen.' if passed else 'Extraction requires the item at the exit without capture.', replay=s)
    except (KeyError,TypeError,ValueError,OverflowError) as exc: return fail(str(exc))
