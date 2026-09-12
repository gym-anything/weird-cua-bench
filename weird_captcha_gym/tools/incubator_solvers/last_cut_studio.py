"""Privileged oracle for wiring evidence, issuing only ordinary browser input."""
import json
import time
from pathlib import Path
MECHANIC_ID='last_cut_studio'
def click(page,selector):
    b=page.locator(selector).bounding_box();assert b,selector
    page.mouse.click(b['x']+b['width']/2,b['y']+b['height']/2)
def drag(page,selector,x,y):
    b=page.locator(selector).bounding_box();assert b,selector
    page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2);page.mouse.down();page.mouse.move(x,y,steps=8);page.mouse.up()
def oracle(truth):
    clips={c['id']:c for c in truth['clips']}
    extra=truth['target_frames']-sum(clips[i]['end']-clips[i]['start'] for i in truth['required'])
    edits=[]
    for i in truth['required']:
        c=clips[i];a=min(c['start']-c['safe_start'],extra//(2*(len(truth['required'])-len(edits))));extra-=a
        b=min(c['safe_end']-c['end'],extra//(2*(len(truth['required'])-len(edits))-1));extra-=b
        edits.append(dict(clip=i,in_frame=c['start']-a,out_frame=c['end']+b))
    assert extra==0
    return edits

def fail_once(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    old=json.loads((state_dir/'public_state.json').read_text())['challenge_id']
    click(page,'#lc-export')
    for _ in range(100):
        if page.locator('.lc-notice').get_attribute('data-status')=='error':break
        time.sleep(.1)
    assert page.locator('.lc-notice').get_attribute('data-status')=='error'
    assert json.loads((state_dir/'public_state.json').read_text())['challenge_id']!=old
    page.screenshot(path=str(out_dir/'failure-fresh.png'))

def solve(page,state_dir,out_dir,mechanic=MECHANIC_ID,*,film=False):
    public=json.loads((state_dir/'public_state.json').read_text());truth=json.loads((state_dir/'ground_truth.json').read_text())
    full=public.get('control_condition',{}).get('interaction','full')=='full'
    for slot,e in enumerate(oracle(truth)):
        index=next(i for i,c in enumerate(public['clips']) if c['id']==e['clip']);c=public['clips'][index]
        click(page,f'[data-reel="{index}"]')
        if film:
            click(page,'#lc-play');page.wait_for_timeout(c['frames']/20*1000+100)
        if full:
            b=page.locator('#lc-timeline').bounding_box();drag(page,f'[data-reel="{index}"]',b['x']+b['width']*.9,b['y']+b['height']/2)
        else:click(page,'#lc-add')
        click(page,f'[data-shot="{slot}"]')
        for edge in ['in','out']:
            desired=e[edge+'_frame']
            if full:
                b=page.locator('#lc-timeline').bounding_box()
                extent=max(sum(x['out_frame']-x['in_frame'] for x in oracle(truth)[:slot])+c['frames']-(e['in_frame'] if edge=='out' else 0),public['target_frames'])
                handle=f'[data-shot="{slot}"] .lc-edge-{edge}'
                h=page.locator(handle).bounding_box();current=0 if edge=='in' else c['frames']
                drag(page,handle,h['x']+h['width']/2+(desired-current)*b['width']/extent,h['y']+h['height']/2)
            else:
                current=0 if edge=='in' else c['frames'];delta=desired-current
                for magnitude in [10,1]:
                    while abs(delta)>=magnitude:
                        step=magnitude if delta>0 else -magnitude;click(page,f'[data-edge="{edge}"][data-delta="{step}"]');delta-=step
        page.screenshot(path=str(out_dir/f'shot-{slot+1}-trimmed.png'))
    click(page,'#lc-cut');click(page,'#lc-play')
    page.wait_for_timeout((sum(e['out_frame']-e['in_frame'] for e in oracle(truth))/20*1000+150) if film else 450)
    page.screenshot(path=str(out_dir/'montage-preview.png'))
    click(page,'#lc-play') if page.locator('#lc-running').inner_text()=='PLAYING' else None
    click(page,'#lc-export')
    for _ in range(100):
        if page.locator('.lc-notice').get_attribute('data-status')=='passed':break
        time.sleep(.1)
    assert page.locator('.lc-notice').get_attribute('data-status')=='passed'
    page.screenshot(path=str(out_dir/'pass.png'))
