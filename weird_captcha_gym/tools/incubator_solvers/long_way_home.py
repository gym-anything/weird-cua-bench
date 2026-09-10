"""Wiring solver: reads the private witness, executes only visible pointer controls."""
import json
from pathlib import Path
from playwright.sync_api import expect
MECHANIC_ID='long_way_home'


def shot(page,out_dir,label):
    Path(out_dir).mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(Path(out_dir)/f'long_way_home-{label}.png'))


def fail_once(page,state_dir,out_dir,mechanic):
    before=json.loads((state_dir/'ground_truth.json').read_text())['challenge_id']
    page.locator('#lwh-certify').click()
    expect(page.locator(".readout")).to_contain_text("FAIL")
    assert json.loads((state_dir/'ground_truth.json').read_text())['challenge_id']!=before
    shot(page,out_dir,'fail-refresh')


def paint(page,cell,value,mode):
    tile=page.locator(f'[data-cell="{cell}"]')
    if mode=='simplified':
        tile.click();page.locator(f'[data-paint="{value}"]').click()
    else:
        page.locator(f'[data-paint="{value}"]').click()
        r=tile.bounding_box();x,y=r['x']+r['width']/2,r['y']+r['height']/2
        page.mouse.move(x-5,y);page.mouse.down();page.mouse.move(x+5,y,steps=2);page.mouse.up()


def solve(page,state_dir,out_dir,mechanic):
    assert mechanic==MECHANIC_ID
    truth=json.loads((state_dir/'ground_truth.json').read_text());g=truth['garden'];mode=(truth.get('control_condition') or {}).get('interaction','full')
    page.locator('#lwh-test').click();shot(page,out_dir,'initial-route')
    changes=[(i,v) for i,v in enumerate(truth['solution_board']) if v!=g['initial'][i]]
    for k,(i,v) in enumerate(changes):
        paint(page,i,v,mode)
        page.locator('#lwh-test').click()
        if k==len(changes)//2:shot(page,out_dir,'active-route')
        page.wait_for_timeout(100)
    assert page.locator('#lwh-report').get_attribute('data-ok')=='true'
    shot(page,out_dir,'solved');page.locator('#lwh-certify').click()
    expect(page.locator(".readout")).to_have_text("PASS")
    shot(page,out_dir,'pass')
