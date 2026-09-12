"""Privileged scheduling oracle, ordinary browser mouse/keyboard execution."""
from pathlib import Path
import json

MECHANIC_ID='curtain_call_calendar'


def plan(world):
    """Backtrack over visible contracts, rather than use the generator witness."""
    records=world['bookings']; result={r['id']:r['initial'][:] for r in records if r['fixed']}
    def valid(k,a,b):
        if a//16 != (b-1)//16: return False
        for c,d in result.values():
            if max(a,c)<min(b,d): return False
        for before,after in world['precedence']:
            if after==k and before in result and result[before][1]>a:return False
            if before==k and after in result and b>result[after][0]:return False
        return True
    def search():
        if len(result)==len(records):return dict(result)
        choices=[]
        for r in records:
            if r['id'] in result:continue
            options=[(a,a+r['duration']) for a in range(r['window'][0],r['window'][1]-r['duration']+1) if valid(r['id'],a,a+r['duration'])]
            choices.append((len(options),r['id'],options))
        _,k,options=min(choices)
        for a,b in options:
            result[k]=[a,b]; answer=search()
            if answer:return answer
            del result[k]
        return None
    answer=search()
    if not answer:raise ValueError('calendar has no solution')
    return answer


def edit(page,record_id,interval,mode):
    page.locator(f'.cc-card[data-record="{record_id}"]').click()
    for field,value in enumerate(interval):
        if mode=='simplified':
            item=page.locator(f'[data-field="{field}"]');item.click();page.keyboard.press('Control+A');page.keyboard.type(str(value));page.keyboard.press('Tab')
        else:
            day=(value-1)//16 if field==1 and value>0 and value%16==0 else value//16
            slot=16 if field==1 and value>0 and value%16==0 else value%16
            page.locator(f'[data-picker="{field}"]').click()
            # Choose an interior time first to avoid end-of-day normalization.
            page.locator('[data-time="1"]').click()
            page.locator(f'[data-day="{day}"]').click()
            page.locator(f'[data-time="{slot}"]').click()
            page.locator('#cc-picker-done').click()
    page.locator('#cc-save').click()


def fail_once(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    from playwright.sync_api import expect
    before=json.loads((state_dir/'public_state.json').read_text())['challenge_id']
    page.locator('#cc-submit').click()
    expect(page.locator(".readout")).to_have_text("FAIL")
    assert json.loads((state_dir/'public_state.json').read_text())['challenge_id']!=before
    page.screenshot(path=str(out_dir/f'{mechanic}-failure.png'))


def solve(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    public=json.loads((state_dir/'public_state.json').read_text())
    solve_world(page,public,out_dir)


def solve_world(page,public,out_dir=None):
    from playwright.sync_api import expect
    answer=plan(public['world']);mode=public['control_condition']['interaction']
    page.locator('#cc-rules').click();page.locator('#cc-book-next').click()
    if out_dir:page.screenshot(path=str(out_dir/'rules.png'))
    page.locator('#cc-book-close').click()
    for i,r in enumerate(public['world']['bookings']):
        if r['fixed']:continue
        edit(page,r['id'],answer[r['id']],mode)
        if out_dir:page.screenshot(path=str(out_dir/f'saved-{i}.png'))
    if out_dir:page.screenshot(path=str(out_dir/'solved.png'))
    page.locator('#cc-submit').click()
    expect(page.locator(".readout")).to_have_text("PASS")
    return answer
