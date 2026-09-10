"""Plan from public surface geometry and target; execute ordinary browser input."""
import json
import time
from pathlib import Path
MECHANIC_ID='maskmakers_dispatch'

def plan(public_state):
    """Peel monochrome exposed regions backward, then construct them forward.

    Already peeled regions impose no constraint on earlier paint. Removing any
    compatible last paint only relaxes the remaining problem, so this greedy
    reverse elimination is complete for reachable targets with reusable covers.
    It does not read a generator recipe or require its particular operation order.
    """
    covers = [set(c['regions']) for c in public_state['covers']]
    target = public_state['target']
    remaining = set(range(len(target)))
    choices = []
    for bits in range(1 << len(covers)):
        active = {i for i in range(len(covers)) if bits & (1 << i)}
        protected = set().union(*(covers[i] for i in active))
        choices.append((active, set(range(len(target))) - protected))
    reverse = []
    while remaining:
        candidates = []
        for active, exposed in choices:
            visible = exposed & remaining
            colours = {target[i] for i in visible}
            if visible and len(colours) == 1:
                candidates.append((len(visible), -len(active), active, visible, next(iter(colours))))
        if not candidates:
            raise ValueError('Target is not reachable by the available covers')
        _, _, active, visible, colour = max(candidates, key=lambda x: x[:2])
        reverse.append((active, colour))
        remaining -= visible
    actions = []
    worn = set()
    for active, colour in reversed(reverse):
        actions.extend({'kind':'cover','index':i} for i in sorted(worn ^ active))
        actions.append({'kind':'paint','index':colour})
        worn = active
    actions.extend({'kind':'cover','index':i} for i in sorted(worn))
    return actions

def wait_verdict(page,word):
    for _ in range(100):
        if word in page.locator('#md-verdict').inner_text():return
        time.sleep(.05)
    raise AssertionError('Missing verdict '+word)

def click(page,selector):
    box=page.locator(selector).bounding_box()
    page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)

def operation(page,kind,index,mode):
    tool=page.locator(f'[data-kind="{kind}"][data-index="{index}"]')
    if mode=='simplified':click(page,f'[data-kind="{kind}"][data-index="{index}"]')
    else:
        a=page.locator('#md-object').bounding_box();b=tool.bounding_box()
        page.mouse.move(a['x']+a['width']/2,a['y']+a['height']/2)
        page.mouse.down();page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2,steps=12);page.mouse.up()

def fail_once(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    before=json.loads((state_dir/'ground_truth.json').read_text())['challenge_id']
    click(page,'#md-ship');wait_verdict(page,'FAIL')
    after=json.loads((state_dir/'ground_truth.json').read_text())['challenge_id']
    assert before!=after
    page.screenshot(path=str(out_dir/f'{mechanic}-fail-refresh.png'))

def solve(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    public=json.loads((state_dir/'public_state.json').read_text());mode=(public.get('control_condition') or {}).get('interaction','full')
    for i,op in enumerate(plan(public)):
        operation(page,op['kind'],op['index'],mode)
        page.wait_for_timeout(170)
        if i==3:page.screenshot(path=str(out_dir/f'{mechanic}-active.png'))
    page.screenshot(path=str(out_dir/f'{mechanic}-solved.png'))
    click(page,'#md-ship');wait_verdict(page,'PASS')
    page.screenshot(path=str(out_dir/f'{mechanic}-pass.png'))
