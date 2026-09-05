"""Replay board edits and independently evaluate every Boolean input class."""
from __future__ import annotations
MECHANIC_ID='sorting_belt_logic_bench'
ARITY={'AND':2,'OR':2,'NAND':2,'NOT':1}


def outputs(gates, wires, world):
    def evaluate(bits):
        cache={f's{i}':v for i,v in enumerate(bits)};visiting=set()
        def value(source):
            if source in cache:return cache[source]
            if source not in gates:raise ValueError('unconnected input')
            if source in visiting:raise ValueError('feedback loop')
            visiting.add(source)
            kind=gates[source]['kind']
            args=[value(wires.get(f'{source}:{i}')) for i in range(ARITY[kind])]
            cache[source]=int(not args[0]) if kind=='NOT' else int(all(args)) if kind=='AND' else int(any(args)) if kind=='OR' else int(not all(args))
            visiting.remove(source);return cache[source]
        # Disconnected palette leftovers are allowed, but all installed gates
        # must be electrically valid. No accidental floating-input constants.
        for key in gates:value(key)
        return value(wires.get('eject'))
    return [evaluate(row['bits']) for row in world['rows']]


def grade(payload,truth,public):
    def fail(reason):return {'graded':True,'passed':False,'feedback':reason}
    try:
        for key in ('mechanic_id','task_id','challenge_id'):
            if not truth.get(key) or any(x.get(key)!=truth[key] for x in (payload,public)):return fail('stale task or challenge')
        if truth['mechanic_id']!=MECHANIC_ID:return fail('wrong mechanic')
        if public.get('world')!=truth['world'] or public.get('control_condition')!=truth.get('control_condition'):return fail('world or condition mismatch')
        mode=(truth.get('control_condition') or {}).get('interaction','full')
        source={'full':'drag','simplified':'click_pair'}[mode]
        w=truth['world'];gates={};wires={};used=set();last_run=None
        events=payload.get('events')
        if not isinstance(events,list) or not 1<=len(events)<=2000:return fail('missing board transcript')
        for seq,e in enumerate(events,1):
            if not isinstance(e,dict) or e.get('seq')!=seq:raise ValueError('invalid sequence')
            kind=e.get('type')
            if kind in ('place','wire','move') and e.get('input_source')!=source:raise ValueError('wrong interaction surface')
            if kind=='place':
                key=e['id'];slot=e['slot']
                if not isinstance(key,str) or not key.startswith('g') or key in used or len(key)>24 or e['kind'] not in ARITY:raise ValueError('invalid gate')
                if type(slot)!=int or not 0<=slot<12 or any(g['slot']==slot for g in gates.values()) or len(gates)>=w['gate_budget']:raise ValueError('occupied socket or gate budget')
                gates[key]={'kind':e['kind'],'slot':slot};used.add(key);last_run=None
            elif kind=='move':
                slot=e['slot']
                if e['id'] not in gates or type(slot)!=int or not 0<=slot<12 or any(k!=e['id'] and g['slot']==slot for k,g in gates.items()):raise ValueError('invalid move')
                gates[e['id']]['slot']=slot;last_run=None
            elif kind=='wire':
                src=e['from'];dst=e['to']
                if src not in gates and src not in [f's{i}' for i in range(w['attribute_count'])]:raise ValueError('invalid output pin')
                valid=['eject']+[f'{k}:{i}' for k,g in gates.items() for i in range(ARITY[g['kind']])]
                if dst not in valid:raise ValueError('invalid input pin')
                wires[dst]=src;last_run=None
            elif kind=='remove':
                key=e['id']
                if key not in gates:raise ValueError('missing gate')
                del gates[key];wires={d:s for d,s in wires.items() if s!=key and not d.startswith(key+':')};last_run=None
            elif kind=='unwire':
                if e['to'] not in wires:raise ValueError('missing wire')
                del wires[e['to']];last_run=None
            elif kind=='run':
                try:actual=outputs(gates,wires,w)
                except ValueError:actual=None
                if e.get('outputs')!=actual:raise ValueError('false circuit output')
                if actual is None:last_run=None;continue
                routed=[{'row':i,'eject':actual[i]} for i in w['batch_order']]
                if e.get('routed')!=routed or type(e.get('elapsed_ms')) not in (int,float) or not len(routed)*w['token_ms']<=e['elapsed_ms']<=600000:raise ValueError('batch not run to completion')
                last_run=actual
            elif kind=='certify':
                if seq!=len(events):raise ValueError('events after certification')
            else:raise ValueError('unknown board event')
        if events[-1]['type']!='certify' or last_run is None:return fail('run a connected circuit before certification')
        wrong=sum(v!=row['eject'] for v,row in zip(last_run,w['rows']))
        passed=wrong==0
        return {'graded':True,'passed':passed,'feedback':f'{wrong} misroutes; {len(gates)}/{w["gate_budget"]} gates','gate_count':len(gates),'correct_rows':len(w['rows'])-wrong,'elegance':round(1-len(gates)/(w['gate_budget']+1),4) if passed else 0}
    except (KeyError,TypeError,ValueError,IndexError,RecursionError):return fail('invalid circuit transcript')
