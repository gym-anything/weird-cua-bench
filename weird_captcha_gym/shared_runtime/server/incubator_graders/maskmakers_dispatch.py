"""Independent replay of cover unions and paint effects; grade the actual surface."""
MECHANIC_ID='maskmakers_dispatch'

def grade(payload, ground_truth, public_state):
    def fail(msg):return {'graded':True,'passed':False,'feedback':msg}
    if not all(isinstance(x,dict) for x in [payload,ground_truth,public_state]):return fail('Malformed payload')
    for key in ('mechanic_id','task_id','challenge_id'):
        if not ground_truth.get(key) or payload.get(key)!=ground_truth[key] or public_state.get(key)!=ground_truth[key]:return fail('Stale or mismatched '+key)
    if ground_truth['mechanic_id']!=MECHANIC_ID:return fail('Wrong mechanic')
    for key in ('regions','covers','palette','target','control_condition'):
        if ground_truth.get(key)!=public_state.get(key):return fail('Surface contract mismatch')
    mode=(ground_truth.get('control_condition') or {}).get('interaction','full')
    source={'full':'ornament_drag','simplified':'tool_click'}.get(mode)
    if not source:return fail('Invalid interaction condition')
    events=payload.get('events')
    # Recovery does not consume a task-specific operation budget. Replay every
    # recorded event, including history before resets; never discard evidence.
    if not isinstance(events,list) or not events:return fail('Missing operations')
    colours=[-1]*len(ground_truth['regions']);active=set();resets=0
    for seq,event in enumerate(events,1):
        if not isinstance(event,dict) or event.get('sequence')!=seq:return fail('Invalid sequence')
        kind=event.get('kind');i=event.get('index')
        if kind=='reset':
            if event.get('input_source')!='reset_button':return fail('Invalid reset surface')
            colours=[-1]*len(colours);active=set();resets+=1
        elif kind in ('paint','cover'):
            if event.get('input_source')!=source:return fail('Wrong interaction surface')
            limit=len(ground_truth['palette' if kind=='paint' else 'covers'])
            if type(i)!=int or not 0<=i<limit:return fail('Invalid tool')
            if kind=='cover':
                if i in active:active.remove(i)
                else:active.add(i)
            else:
                protected={r for c in active for r in ground_truth['covers'][c]['regions']}
                colours=[old if r in protected else i for r,old in enumerate(colours)]
        else:return fail('Invalid operation')
        if event.get('colours')!=colours or event.get('active')!=sorted(active):return fail('Paint or cover replay mismatch')
    if payload.get('colours')!=colours or payload.get('active')!=sorted(active):return fail('Final surface mismatch')
    matched=sum(a==b for a,b in zip(colours,ground_truth['target']))
    passed=not active and colours==ground_truth['target']
    return {'graded':True,'passed':passed,'feedback':f'{matched}/{len(colours)} regions match; {len(active)} covers remain; {resets} resets.'}

def cheat(public_state,ground_truth):
    return {'answers':[],'solution':ground_truth['solution'],'instruction':'Apply each tool using the selected visible interaction surface.'}
