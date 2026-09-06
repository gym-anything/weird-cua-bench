"""Independent replay of primitive browser events, including held-input time."""
from __future__ import annotations
import math

MECHANIC_ID = 'museum_of_lost_gestures'
GESTURES = {'double','right','drag','hold','scroll','resize','return','dwell','modifier','chord'}

class Replay:
    def __init__(self, world, mode):
        self.w, self.mode = world, mode
        self.opened, self.history, self.recognized = set(), [], []
        self.point = [-1000, -1000]; self.down = None; self.keys = set()
        self.last_tap = None; self.entered = False; self.left = False
        self.still_since = 0; self.still_origin = self.point[:]; self.dwelled = False
        self.width = world['room_width']; self.scroll = 0; self.used = 0
        self.pending = None; self.time = 0

    def inside(self, p):
        x,y,w,h = self.w['plinth']
        return x <= p[0] <= x+w and y <= p[1] <= y+h

    def emit(self, gesture):
        if self.used >= self.w['budget']: return
        self.recognized.append(gesture)
        if gesture not in GESTURES: return
        self.used += 1
        self.history = (self.history + [gesture])[-max(3, self.w['parameters']['composition']):]
        available = [c for c in self.w['cases'] if set(c['requires']) <= self.opened]
        for c in available:
            if self.history[-len(c['recipe']):] == c['recipe']:
                self.opened.add(c['id'])

    def event(self, e):
        t, kind = e['t'], e['type']; self.time = t
        if self.mode == 'simplified':
            if kind == 'proxy':
                g = e.get('gesture')
                if g not in GESTURES or self.pending: raise ValueError('invalid or overlapping proxy')
                duration = self.w['hold_ms'] if g == 'hold' else self.w['dwell_ms'] if g == 'dwell' else 0
                if duration: self.pending = [g, t + duration]
                else: self.emit(g)
            elif kind == 'tick':
                if self.pending and t >= self.pending[1]:
                    self.emit(self.pending[0]); self.pending = None
            else: raise ValueError('wrong simplified input surface')
            return
        if kind == 'proxy': raise ValueError('wrong full input surface')
        if kind in ('move','down','up','enter'):
            p = e.get('point')
            if not isinstance(p, list) or len(p) != 2 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>4000 for v in p):
                raise ValueError('invalid coordinates')
            self.point = p[:]
            if math.dist(p, self.still_origin) > self.w['still_px']:
                self.still_since = t; self.still_origin = p[:]; self.dwelled = False
            if self.down: self.down['distance'] = max(self.down['distance'], math.dist(p,self.down['point']))
        if kind == 'enter':
            if self.left: self.emit('return'); self.left = False
            self.entered = True; self.still_since = t; self.dwelled = False
        elif kind == 'leave':
            self.left = self.entered; self.entered = False; self.dwelled = False
        elif kind == 'cancel':
            self.down = None; self.last_tap = None
            self.still_since = t; self.dwelled = False
        elif kind == 'move': pass
        elif kind == 'down':
            if self.down or e.get('button') not in (0,2): raise ValueError('invalid pointer down')
            self.down = {'point':self.point[:], 't':t, 'button':e['button'], 'distance':0, 'held':False}
        elif kind == 'up':
            if not self.down or e.get('button') != self.down['button']: raise ValueError('unpaired pointer up')
            d = self.down; self.down = None
            if self.inside(d['point']):
                if d['button'] == 2: self.emit('right')
                elif d['distance'] >= self.w['plinth'][2]: self.emit('drag'); self.last_tap = None
                elif d['held']: pass
                elif d['distance'] <= self.w['still_px'] and self.inside(self.point):
                    if 'Shift' in self.keys: self.emit('modifier'); self.last_tap = None
                    elif self.last_tap and t-self.last_tap[0] <= self.w['double_ms'] and math.dist(self.point,self.last_tap[1]) <= 6:
                        self.emit('double'); self.last_tap = None
                    else: self.emit('tap'); self.last_tap = [t,self.point[:]]
            self.still_since = t; self.dwelled = False
        elif kind in ('key_down','key_up'):
            key = e.get('key')
            if key not in ('Shift','a','s'): raise ValueError('unsupported key')
            if kind == 'key_down':
                if key in self.keys: raise ValueError('repeated key')
                self.keys.add(key)
                if {'a','s'} <= self.keys: self.emit('chord')
            else:
                if key not in self.keys: raise ValueError('unpaired key release')
                self.keys.remove(key)
        elif kind == 'scroll':
            value = e.get('value')
            if type(value) not in (int,float) or not math.isfinite(value) or not 0 <= value <= self.w['scroll_max']+1: raise ValueError('invalid scroll')
            if value >= self.w['scroll_max']-1 and self.scroll < self.w['scroll_max']-1: self.emit('scroll')
            self.scroll = value
        elif kind == 'resize':
            value = e.get('value')
            if type(value) not in (int,float) or not math.isfinite(value) or not 360 <= value <= 600: raise ValueError('invalid viewport size')
            if abs(value-self.width) >= self.w['resize_px']: self.emit('resize'); self.width = value
        elif kind == 'tick':
            if self.down and self.down['button']==0 and self.inside(self.down['point']) and self.down['distance'] <= self.w['still_px'] and not self.down['held'] and t-self.down['t'] >= self.w['hold_ms']:
                self.down['held'] = True; self.emit('hold'); self.last_tap = None
            if self.entered and not self.down and self.inside(self.point) and not self.dwelled and t-self.still_since >= self.w['dwell_ms']:
                self.dwelled = True; self.emit('dwell')
        else: raise ValueError('unknown event')


def grade(payload, ground_truth, public_state):
    def fail(reason): return {'graded':True,'passed':False,'score':0,'feedback':reason}
    if not all(isinstance(value, dict) for value in (payload, ground_truth, public_state)):
        return fail('invalid submission envelope')
    try:
        for key in ('mechanic_id','task_id','challenge_id'):
            if not ground_truth.get(key) or payload.get(key) != ground_truth[key] or public_state.get(key) != ground_truth[key]: return fail(f'{key} mismatch')
        if ground_truth['mechanic_id'] != MECHANIC_ID: return fail('wrong mechanic')
        if public_state.get('world') != ground_truth.get('world'): return fail('world mismatch')
        cond = ground_truth.get('control_condition')
        if public_state.get('control_condition') != cond or payload.get('control_condition') != cond: return fail('condition mismatch')
        mode = (cond or {}).get('interaction','full')
        if mode not in ('full','simplified'): return fail('invalid mode')
        events = payload.get('events')
        if not isinstance(events,list) or not 1 <= len(events) <= 20000: return fail('missing or excessive transcript')
        r = Replay(ground_truth['world'],mode); previous = -1
        for i,e in enumerate(events):
            if not isinstance(e,dict) or e.get('seq') != i+1 or e.get('source') != mode: return fail('invalid sequence or input surface')
            t=e.get('t')
            if type(t) not in (int,float) or not math.isfinite(t) or not previous <= t <= 600000: return fail('invalid task time')
            previous=t; r.event(e)
        if payload.get('opened') != sorted(r.opened): return fail('forged case flags')
        score = len(r.opened)*10
        return {'graded':True, 'passed':len(r.opened)==10, 'score':score,
                'feedback':f'Cases recovered {len(r.opened)}/10; gestures {r.used}/{r.w["budget"]}'}
    except (ValueError,TypeError,KeyError,OverflowError) as exc: return fail(f'invalid event transcript: {exc}')


def cheat(public_state, ground_truth):
    return {'answers':[], 'instruction':'Perform each case recipe in dependency order.', 'order':ground_truth['solution_order']}
