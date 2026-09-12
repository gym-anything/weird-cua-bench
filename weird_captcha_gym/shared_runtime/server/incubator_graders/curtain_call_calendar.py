"""Replay record editing and validate any feasible final calendar."""
from __future__ import annotations
MECHANIC_ID = 'curtain_call_calendar'


def violations(world, intervals):
    errors=[]
    records=world['bookings']
    for r in records:
        a,b=intervals[r['id']]
        if b-a != r['duration']: errors.append(f"{r['name']}: duration")
        if a < r['window'][0] or b > r['window'][1] or a < 0 or b > world['horizon'] or a >= b: errors.append(f"{r['name']}: window")
        if a//16 != (b-1)//16: errors.append(f"{r['name']}: overnight")
        if r['fixed'] and [a,b] != r['initial']: errors.append(f"{r['name']}: fixed booking changed")
    for i,r in enumerate(records):
        a,b=intervals[r['id']]
        for s in records[i+1:]:
            c,d=intervals[s['id']]
            if max(a,c)<min(b,d): errors.append(f"{r['name']} / {s['name']}: stage overlap")
    for a,b in world['precedence']:
        if intervals[a][1] > intervals[b][0]: errors.append(f'{a} → {b}: precedence')
    return errors


def grade(payload, ground_truth, public_state):
    def fail(message): return {'graded':True,'passed':False,'feedback':message}
    if not all(isinstance(x,dict) for x in (payload,ground_truth,public_state)): return fail('malformed calendar envelope')
    try:
        for key in ('mechanic_id','task_id','challenge_id','control_condition'):
            if ground_truth.get(key) != public_state.get(key): return fail('public/private contract mismatch')
        for key in ('mechanic_id','task_id','challenge_id'):
            if payload.get(key) != ground_truth.get(key) or not payload.get(key): return fail('stale or mismatched identity')
        if payload['mechanic_id'] != MECHANIC_ID or ground_truth['world'] != public_state['world']: return fail('world mismatch')
        mode=ground_truth['control_condition']['interaction']
        if payload.get('interaction_mode') != mode: return fail('wrong interaction mode')
        world=ground_truth['world']; records={r['id']:r for r in world['bookings']}
        intervals={k:list(r['initial']) for k,r in records.items()}
        selected=None; draft=None
        events=payload.get('events')
        if not isinstance(events,list) or len(events)>5000: return fail('invalid events')
        for e in events:
            kind=e['type']
            if kind=='open':
                selected=e['id']
                if selected not in records: return fail('unknown record')
                draft=list(intervals[selected])
            elif kind=='cancel': selected=None; draft=None
            elif kind in ('pick','set'):
                if selected is None or records[selected]['fixed']: return fail('editing unavailable record')
                if e.get('input_source') != ('datetime_picker' if mode=='full' else 'direct_fields'): return fail('wrong input surface')
                field=e['field']; value=e['value']
                if type(field) is not int or field not in (0,1) or type(value) is not int: return fail('invalid field value')
                if kind=='set':
                    if mode!='simplified' or not 0 <= value <= world['horizon']: return fail('invalid direct field')
                    draft[field]=value
                else:
                    if mode!='full': return fail('picker in simplified transcript')
                    part=e['part']
                    old=draft[field]
                    # End-of-day is represented as 17:00 on the preceding day.
                    day=(old-1)//16 if field==1 and old>0 and old%16==0 else old//16
                    slot=16 if field==1 and old>0 and old%16==0 else old%16
                    if part=='day' and 0 <= value < world['horizon']//16: day=value
                    elif part=='time' and (0 <= value < 16 if field==0 else 1 <= value <= 16): slot=value
                    else: return fail('invalid picker selection')
                    draft[field]=day*16+slot
            elif kind=='save':
                if selected is None or records[selected]['fixed']: return fail('save unavailable')
                if e.get('before') != intervals[selected] or e.get('after') != draft: return fail('save replay mismatch')
                intervals[selected]=list(draft); selected=None; draft=None
            else: return fail('unknown event')
        if payload.get('intervals') != intervals: return fail('final intervals differ from replay')
        errors=violations(world,intervals)
        return {'graded':True,'passed':not errors,'feedback':'; '.join(errors) if errors else 'Every rehearsal fits. Curtain up!','intervals':intervals}
    except (KeyError,TypeError,ValueError,IndexError,OverflowError): return fail('malformed calendar transcript')
