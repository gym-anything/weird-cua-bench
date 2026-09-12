"""Replay editing operations, then grade every frame retained in the exported cut."""
from __future__ import annotations
MECHANIC_ID='last_cut_studio'
def grade(payload, truth, public):
    def result(ok,msg):return dict(graded=True,passed=ok,feedback=msg)
    try:
        for k in ['mechanic_id','task_id','challenge_id']:
            if not truth.get(k) or payload.get(k)!=truth[k] or public.get(k)!=truth[k]:return result(False,'Stale task or challenge')
        if truth['mechanic_id']!=MECHANIC_ID:return result(False,'Wrong mechanic')
        if public.get('control_condition')!=truth.get('control_condition') or payload.get('control_condition')!=truth.get('control_condition'):return result(False,'Wrong condition')
        for k in ['clips','target_frames','tolerance']:
            if public.get(k)!=truth.get(k):return result(False,'Footage contract mismatch')
        mode=(truth.get('control_condition') or {}).get('interaction','full')
        surface={'full':'direct','simplified':'proxy'}[mode]
        clips={c['id']:c for c in truth['clips']}; edit=[]
        events=payload.get('events')
        if not isinstance(events,list) or len(events)>5000:return result(False,'Invalid edit history')
        def integer(v):return type(v) is int
        for n,e in enumerate(events):
            if not isinstance(e,dict) or e.get('seq')!=n+1 or e.get('input_source')!=surface:return result(False,'Wrong editing input surface')
            op=e.get('type')
            if op=='add':
                c=clips[e['clip']]
                if len(edit)>=8:return result(False,'Too many clips')
                edit.append(dict(clip=c['id'],in_frame=0,out_frame=c['frames']))
            elif op in ['trim','remove','move']:
                i=e['index']
                if not integer(i) or not 0<=i<len(edit):return result(False,'Invalid selected clip')
                if op=='remove':edit.pop(i)
                elif op=='move':
                    j=e['to']
                    if not integer(j) or not 0<=j<len(edit):return result(False,'Invalid destination')
                    edit.insert(j,edit.pop(i))
                else:
                    a,b=e['in_frame'],e['out_frame']
                    if not integer(a) or not integer(b) or not 0<=a<b<=clips[edit[i]['clip']]['frames']:return result(False,'Invalid trim range')
                    edit[i].update(in_frame=a,out_frame=b)
            else:return result(False,'Unknown edit')
        if payload.get('montage')!=edit:return result(False,'Export differs from edit history')
        if [e['clip'] for e in edit]!=truth['required']:return result(False,'FAIL — shot identity or order differs from brief')
        for i,e in enumerate(edit):
            c=clips[e['clip']];a,b=e['in_frame'],e['out_frame']
            if a>c['start'] or b<c['end']:return result(False,f'FAIL — shot {i+1} cuts off part of the action')
            if a<c['safe_start'] or b>c['safe_end']:return result(False,f'FAIL — shot {i+1} includes slate or cleanup')
        duration=sum(e['out_frame']-e['in_frame'] for e in edit)
        if abs(duration-truth['target_frames'])>truth['tolerance']:return result(False,'FAIL — montage duration outside brief')
        return result(True,'PASS — complete actions, clean cuts, correct order and duration')
    except (KeyError,TypeError,ValueError,IndexError):return result(False,'Malformed montage')
