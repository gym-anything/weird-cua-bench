"""Replay lens positions and shutters against generated moving geometry."""
from __future__ import annotations
import math

MECHANIC_ID = 'fluke_census'
# This polygon is the rendered survey silhouette, including both fluke lobes.
BODY = [(42,0),(34,-12),(10,-17),(-18,-10),(-28,-5),(-34,-19),(-47,-25),(-42,-9),(-35,0),(-42,9),(-47,25),(-34,19),(-28,5),(-18,10),(10,17),(34,12)]

def outline(animal):
    vertices = list(BODY[:7])
    center = -35 + 2 * animal['species']
    for side in range(2):
        start, end = ((center, 0), (-47, 25)) if side else ((-47, -25), (center, 0))
        for i in range(4):
            for fraction, inset in ((.15, 0), (.45, animal['notches'][side*4+i]*.10), (.75, 0)):
                t = (i + fraction) / 4
                vertices.append((start[0]+(end[0]-start[0])*t+inset, start[1]+(end[1]-start[1])*t))
        vertices.append(end)
    return vertices + BODY[11:]

def pose(item, elapsed_ms):
    t = elapsed_ms / 1000
    p = item['phase'] + t * item['omega']
    return item['x'] + 16 * math.sin(p), item['y'] + 12 * math.cos(p), item['angle'], item['scale']

def hit(world, epoch, elapsed_ms, x, y):
    animals = {a['id']: a for a in world['animals']}
    for item in reversed(world['layouts'][epoch]):
        cx, cy, angle, scale = pose(item, elapsed_ms)
        a = math.radians(angle)
        dx, dy = (x-cx)/scale, (y-cy)/scale
        px, py = dx*math.cos(a)+dy*math.sin(a), -dx*math.sin(a)+dy*math.cos(a)
        inside = False
        polygon = outline(animals[item['id']])
        for i,(ax,ay) in enumerate(polygon):
            bx,by = polygon[i-1]
            if (ay>py)!=(by>py) and px < (bx-ax)*(py-ay)/(by-ay)+ax:
                inside = not inside
        if inside:
            return item['id']
    return None

def _fail(message):
    return {'graded': True,'passed':False,'score':0,'feedback':message}

def grade(payload, truth, public):
    if not all(isinstance(x,dict) for x in (payload,truth,public)):
        return _fail('malformed census')
    for k in ('mechanic_id','task_id','challenge_id','control_condition'):
        if payload.get(k) != truth.get(k) or public.get(k) != truth.get(k):
            return _fail('stale task, challenge or control condition')
    if truth.get('mechanic_id') != MECHANIC_ID or not truth.get('challenge_id'):
        return _fail('invalid identity')
    world = truth.get('world')
    if not isinstance(world,dict) or any(public.get(k)!=v for k,v in world.items()):
        return _fail('rendered world differs from replay')
    mode = (truth.get('control_condition') or {}).get('interaction','full')
    if mode not in ('full','simplified') or payload.get('interaction_mode') != mode:
        return _fail('wrong interaction mode')
    sources = {'aim': 'pointer' if mode=='full' else 'coordinates','photo':'space' if mode=='full' else 'photo_button','submit':'census_button'}
    events = payload.get('events')
    if not isinstance(events,list) or not 1 <= len(events) <= 20000:
        return _fail('missing or oversized transcript')
    epoch=0; previous=0; epoch_start=0; aim=None; photos=[]; terminal=False; invalid_photo=False
    try:
        for seq,e in enumerate(events,1):
            if not isinstance(e,dict) or e.get('seq')!=seq or terminal:
                return _fail('invalid sequence or input after census closure')
            kind=e.get('type'); t=e.get('t')
            if isinstance(t,bool) or not isinstance(t,(int,float)) or not math.isfinite(t) or not previous<=t:
                return _fail('invalid task time')
            previous=t
            if e.get('source')!=sources.get(kind) or kind not in sources:
                return _fail('wrong input surface')
            if kind=='aim':
                x,y=e['x'],e['y']
                if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (x,y)) or not 0<=x<=820 or not 0<=y<=430:
                    return _fail('invalid lens coordinates')
                aim=(x,y)
            elif kind=='photo':
                if aim is None or epoch>=len(world['layouts'])-1:
                    return _fail('shutter has no active lens')
                animal=hit(world,epoch,t-epoch_start,*aim)
                if animal is None or e.get('animal_id')!=animal or e.get('epoch')!=epoch:
                    return _fail('shutter misses the rendered animal')
                invalid_photo=animal in photos or animal not in truth['required_ids']
                photos.append(animal);epoch+=1;epoch_start=t;aim=None
                if invalid_photo: terminal=True
            else:
                terminal=True
        required=set(truth['required_ids']);coverage=len(set(photos)&required)
        duplicates=len(photos)-len(set(photos));off_list=len([a for a in photos if a not in required])
        passed=terminal and not invalid_photo and events[-1]['type']=='submit' and set(photos)==required and not duplicates and not off_list
        return {'graded':True,'passed':passed,'score':100 if passed else 0,'coverage':coverage,'required':len(required),'duplicates':duplicates,'off_list':off_list,'feedback':f'Coverage {coverage}/{len(required)} · duplicates {duplicates} · off-list {off_list}'}
    except (KeyError,TypeError,ValueError,IndexError,OverflowError):
        return _fail('malformed census transcript')
