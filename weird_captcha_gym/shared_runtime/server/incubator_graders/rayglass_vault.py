"""Independent ray tracing and primitive-input replay for Rayglass Vault."""
from __future__ import annotations

MECHANIC_ID = 'rayglass_vault'
PROFILES = {1: (4, 1), 2: (4, 2), 3: (5, 3), 4: (6, 4), 5: (7, 5)}


def port_start(n, port):
    side, k = divmod(port, n)
    return ((k, -1, 0, 1), (n, k, -1, 0), (n-1-k, n, 0, -1), (-1, n-1-k, 1, 0))[side]


def ray(n, beads, port):
    """Clockwise ports. Head-on absorption precedes diagonal deflection.

    Return H, R, or the zero-based exit port. A simultaneous pair of front
    diagonals reverses direction. Entry-adjacent deflection reflects outside
    the cabinet. Cycle protection covers malformed/unreachable ray states.
    """
    balls = set(beads)
    def has(x, y):
        return 0 <= x < n and 0 <= y < n and y*n+x in balls
    x, y, dx, dy = port_start(n, port)
    if has(x+dx, y+dy):
        return 'H'
    if has(x+dx-dy, y+dy+dx) or has(x+dx+dy, y+dy-dx):
        return 'R'
    x, y = x+dx, y+dy
    seen = set()
    while (x, y, dx, dy) not in seen:
        seen.add((x, y, dx, dy))
        if has(x+dx, y+dy):
            return 'H'
        left = has(x+dx+dy, y+dy-dx)
        right = has(x+dx-dy, y+dy+dx)
        if left and right:
            dx, dy = -dx, -dy
        elif left:
            dx, dy = -dy, dx
        elif right:
            dx, dy = dy, -dx
        else:
            x, y = x+dx, y+dy
            if not (0 <= x < n and 0 <= y < n):
                exit_port = x if y < 0 else n+y if x >= n else 3*n-1-x if y >= n else 4*n-1-y
                return 'R' if exit_port == port else exit_port
    return 'R'


def signature(n, beads):
    return [ray(n, beads, p) for p in range(4*n)]


def geometry(n):
    # The SVG viewBox, visible cells and replayed click bounds share these.
    step = 350/n
    cells = [{'x': 75+(i % n+.5)*step, 'y': 65+(i//n+.5)*step, 'size': step-4} for i in range(n*n)]
    ports = []
    for p in range(4*n):
        x, y, dx, dy = port_start(n, p)
        ports.append({'x': 75+(x+.5)*step if dx == 0 else 450 if dx == -1 else 50,
                      'y': 65+(y+.5)*step if dy == 0 else 40 if dy == 1 else 440,
                      'size': 38})
    return {'width': 500, 'height': 480, 'cells': cells, 'ports': ports}


def _fail(message):
    return {'graded': True, 'passed': False, 'score': 0, 'feedback': message}


def _index(value, size):
    return type(value) is int and 0 <= value < size


def grade(payload, truth, public):
    if not all(isinstance(x, dict) for x in (payload, truth, public)):
        return _fail('Malformed submission')
    for key in ('mechanic_id', 'task_id', 'challenge_id'):
        if not truth.get(key) or payload.get(key) != truth[key] or public.get(key) != truth[key]:
            return _fail('Stale task or challenge')
    if truth['mechanic_id'] != MECHANIC_ID:
        return _fail('Wrong mechanic')
    condition = truth.get('control_condition')
    if payload.get('control_condition') != condition or public.get('control_condition') != condition:
        return _fail('Control condition mismatch')
    mode = (condition or {}).get('interaction', 'full')
    if mode not in ('full', 'simplified') or payload.get('interaction_mode') != mode:
        return _fail('Wrong input surface')
    n, count = truth['size'], truth['bead_count']
    if public.get('size') != n or public.get('bead_count') != count or public.get('geometry') != geometry(n):
        return _fail('World geometry mismatch')
    expected = signature(n, truth['beads'])
    if public.get('sensor_responses') != expected:
        return _fail('Sensor oracle disagrees with ray tracing')
    events = payload.get('events')
    if not isinstance(events, list) or not 1 <= len(events) <= 4096:
        return _fail('Missing or excessive input transcript')
    marks, shots = set(), []
    surface = 'cabinet_click' if mode == 'full' else 'console_button'
    for seq, event in enumerate(events, 1):
        if not isinstance(event, dict) or event.get('seq') != seq or event.get('input_surface') != surface:
            return _fail('Invalid sequence or wrong interaction input')
        kind = event.get('type')
        if kind not in ('probe', 'mark'):
            return _fail('Unknown action')
        idx = event.get('index')
        objects = public['geometry']['ports' if kind == 'probe' else 'cells']
        if not _index(idx, len(objects)):
            return _fail('Invalid target')
        if mode == 'full':
            point = event.get('point')
            obj = objects[idx]
            if not isinstance(point, list) or len(point) != 2:
                return _fail('Missing direct click position')
            try:
                if not all(type(v) in (int, float) and abs(v-obj[a]) <= obj['size']/2 for v, a in zip(point, ('x', 'y'))):
                    return _fail('Click outside visible target')
            except (TypeError, ValueError):
                return _fail('Malformed click')
        elif 'point' in event:
            return _fail('Proxy transcript contains a direct click')
        if kind == 'probe':
            if type(event.get('response')) is not type(expected[idx]) or event.get('response') != expected[idx]:
                return _fail('False sensor response')
            shots.append(idx)
        elif idx in marks:
            marks.remove(idx)
        else:
            marks.add(idx)
    if payload.get('marks') != sorted(marks):
        return _fail('Hypothesis differs from input replay')
    if len(marks) != count:
        return _fail(f'Seal needs {count} bead markers')
    actual = signature(n, marks)
    passed = actual == expected
    return {'graded': True, 'passed': passed, 'score': 100 if passed else 0,
            'feedback': 'All border beams agree. Vault opened.' if passed else 'Beam behavior differs. A fresh cabinet is ready.',
            'metrics': {'beam_queries': len(shots), 'unique_queries': len(set(shots)), 'bead_count': len(marks),
                        'equivalent_layout': passed and sorted(marks) != sorted(truth['beads'])}}
