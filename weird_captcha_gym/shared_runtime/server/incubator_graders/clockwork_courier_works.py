"""Independent 60 Hz position-based circle/rod physics; never trust a delivery claim.

Massless pin-jointed rods constrain hub distance. Circular bodies have equal
mass, gravity and inelastic normal contact. Driven rims target angular speed
0.045 rad/tick; contact traction is capped at .18 pixels/tick per step.
"""
import math
MECHANIC_ID='clockwork_courier_works'

def initial(s, wheels, rods):
    bodies=[list(s['parcel'][:2])+[s['parcel'][2],0]]+[list(w) for w in wheels]
    return {'b':bodies,'v':[[0.,0.] for _ in bodies],'rods':[(a,b,math.hypot(bodies[a][0]-bodies[b][0],bodies[a][1]-bodies[b][1])) for a,b in rods],'tick':0,'delivered':False}

def step(s, sim):
    b=sim['b']; old=[p[:2] for p in b]; contacts={}
    for p,v in zip(b,sim['v']):
        v[0]*=.999;v[1]=v[1]*.999+.16;p[0]+=v[0];p[1]+=v[1]
    for _ in range(12):
        for a,c,length in sim['rods']:
            dx=b[c][0]-b[a][0];dy=b[c][1]-b[a][1];dist=math.hypot(dx,dy)
            if dist>1e-9:
                k=(dist-length)/dist*.5;b[a][0]+=dx*k;b[a][1]+=dy*k;b[c][0]-=dx*k;b[c][1]-=dy*k
        for i,p in enumerate(b):
            for q in b[i+1:]:
                dx=q[0]-p[0];dy=q[1]-p[1];d=math.hypot(dx,dy);r=p[2]+q[2]
                if 1e-9<d<r:
                    k=(r-d)/d*.5;p[0]-=dx*k;p[1]-=dy*k;q[0]+=dx*k;q[1]+=dy*k
            for x,y,xx,yy in s['segments']:
                dx=xx-x;dy=yy-y;t=max(0.,min(1.,((p[0]-x)*dx+(p[1]-y)*dy)/(dx*dx+dy*dy)))
                nx=p[0]-x-t*dx;ny=p[1]-y-t*dy;d=math.hypot(nx,ny);r=p[2]+3
                if 1e-9<d<r:
                    nx/=d;ny/=d;p[0]+=nx*(r-d);p[1]+=ny*(r-d);contacts[i]=(nx,ny)
    for i,p in enumerate(b):
        vx=p[0]-old[i][0];vy=p[1]-old[i][1]
        if i in contacts:
            nx,ny=contacts[i];vn=vx*nx+vy*ny
            if vn<0:vx-=vn*nx;vy-=vn*ny
            tx=-ny;ty=nx;speed=vx*tx+vy*ty;target=p[3]*p[2]*.045
            change=max(-.18,min(.18,target-speed));vx+=tx*change;vy+=ty*change
        sim['v'][i]=[vx,vy]
    sim['tick']+=1
    x,y,r,_=b[0];x0,y0,x1,y1=s['receiver']
    sim['delivered']=x-r>=x0 and x+r<=x1 and y-r>=y0 and y+r<=y1
    return sim['delivered']

def simulate(s,wheels,rods,ticks=None):
    sim=initial(s,wheels,rods)
    for _ in range(s['max_ticks'] if ticks is None else ticks):
        if step(s,sim) or sim['b'][0][1]>550:break
    return sim

def grade(payload, ground_truth, public_state):
    def fail(message):
        return {'graded': True, 'passed': False, 'score': 0, 'feedback': message}

    s = ground_truth
    if not all(isinstance(value, dict) for value in (payload, s, public_state)):
        return fail('malformed task or result')
    identity = ('mechanic_id', 'task_id', 'challenge_id')
    if any(not s.get(key) or payload.get(key) != s[key] or public_state.get(key) != s[key]
           for key in identity) or s['mechanic_id'] != MECHANIC_ID:
        return fail('stale task or challenge')
    if public_state != s:
        return fail('world contract mismatch')
    mode = s.get('control_condition', {}).get('interaction', 'full')
    if mode not in ('full', 'simplified'):
        return fail('invalid interaction condition')
    events = payload.get('events')
    if not isinstance(events, list) or not 1 <= len(events) <= 500:
        return fail('missing construction transcript')
    wheels, rods, sim = [], [], None
    finished = False

    def number(value):
        return type(value) in (int, float) and math.isfinite(value)

    def wheel_index(value):
        return type(value) is int and 1 <= value <= len(wheels)

    def inside(point, radius):
        x0, y0, x1, y1 = s['build_box']
        return (isinstance(point, (list, tuple)) and len(point) == 2
                and all(number(value) for value in point)
                and x0 + radius <= point[0] <= x1 - radius
                and y0 + radius <= point[1] <= y1 - radius)

    try:
        for event in events:
            kind = event['kind']
            if kind in ('place', 'move', 'rod', 'unrod', 'reverse', 'delete'):
                expected_source = 'drag' if mode == 'full' else 'click'
                if event.get('input_source') != expected_source:
                    return fail('wrong interaction surface')
                if sim is not None:
                    return fail('return to workbench before editing')
            if kind == 'place':
                wheel = event['wheel']
                if (not isinstance(wheel, (list, tuple)) or len(wheel) != 4
                        or not all(number(value) for value in wheel)):
                    return fail('invalid wheel')
                if (wheel[2] not in s['wheel_radii'] or wheel[3] not in (-1, 1)
                        or len(wheels) >= s['max_wheels']):
                    return fail('invalid wheel type')
                if not inside(wheel[:2], wheel[2]):
                    return fail('wheel placement outside workbench')
                wheels.append(list(wheel))
            elif kind == 'move':
                index = event['index']
                if not wheel_index(index) or not inside(event['point'], wheels[index - 1][2]):
                    return fail('invalid wheel move')
                wheels[index - 1][:2] = event['point']
            elif kind == 'reverse':
                if not wheel_index(event['index']):
                    return fail('invalid wheel selection')
                wheels[event['index'] - 1][3] *= -1
            elif kind == 'delete':
                index = event['index']
                if not wheel_index(index):
                    return fail('invalid wheel selection')
                wheels.pop(index - 1)
                rods = [(a - (a > index), b - (b > index)) for a, b in rods
                        if index not in (a, b)]
            elif kind in ('rod', 'unrod'):
                a, b = event['ends']
                if (not all(type(value) is int and 0 <= value <= len(wheels) for value in (a, b))
                        or a == b):
                    return fail('invalid joint')
                edge = (min(a, b), max(a, b))
                if kind == 'rod':
                    if edge in rods or len(rods) >= s['max_rods']:
                        return fail('invalid joint')
                    rods.append(edge)
                else:
                    if edge not in rods:
                        return fail('rod does not exist')
                    rods.remove(edge)
            elif kind == 'run':
                if sim is not None:
                    return fail('duplicate run')
                bodies = [s['parcel']] + wheels
                if any(math.hypot(p[0] - q[0], p[1] - q[1]) < p[2] + q[2] - .01
                       for index, p in enumerate(bodies) for q in bodies[index + 1:]):
                    return fail('overlapping initial bodies')
                sim = initial(s, wheels, rods)
                finished = False
            elif kind == 'finish':
                ticks = event['ticks']
                # A user may return to the editor at the same paused action
                # boundary as Run. That is a legal zero-tick aborted test.
                if sim is None or finished or type(ticks) is not int or not 0 <= ticks <= s['max_ticks']:
                    return fail('invalid run duration')
                for _ in range(ticks):
                    if sim['delivered'] or sim['b'][0][1] > 550:
                        return fail('continued after terminal run')
                    step(s, sim)
                finished = True
            elif kind == 'edit':
                if sim is None or not finished:
                    return fail('run must stop before returning to workbench')
                sim = None
                finished = False
            else:
                return fail('unknown action')
        if sim is None or not finished or not sim['delivered']:
            return fail('parcel did not enter receiver')
        return {'graded': True, 'passed': True, 'score': 100,
                'feedback': f"Parcel delivered by independent physics replay at tick {sim['tick']}."}
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        return fail('malformed construction')

def cheat(public_state,ground_truth):return {'hint':'Construct and simulate a stable wheel-and-rod machine.'}
