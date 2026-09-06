"""Privileged reference plan, executed only through ordinary visible UI inputs."""
import json
from pathlib import Path
from playwright.sync_api import expect
MECHANIC_ID='sorting_belt_logic_bench'


def drag(page, source, target):
    a=source.bounding_box();b=target.bounding_box()
    page.mouse.move(a['x']+a['width']/2,a['y']+a['height']/2)
    page.mouse.down();page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2,steps=6);page.mouse.up()


def connect(page,source,target,mode):
    a=page.locator(f'[data-pin="{source}"][data-direction="out"]');b=page.locator(f'[data-pin="{target}"][data-direction="in"]')
    if mode=='full':drag(page,a,b)
    else:a.click();b.click()


def build(page,truth):
    mode=(truth.get('control_condition') or {}).get('interaction','full')
    for gate in truth['solution']['gates']:
        a=page.locator(f'[data-palette="{gate["kind"]}"]');b=page.locator(f'[data-slot="{gate["slot"]}"]')
        if mode=='full':drag(page,a,b)
        else:a.click();b.click()
        expect(page.locator(f'[data-gate="{gate["id"]}"]')).to_be_visible()
    for gate in truth['solution']['gates']:
        for i,source in enumerate(gate['sources']):connect(page,source,f'{gate["id"]}:{i}',mode)
    connect(page,truth['solution']['output'],'eject',mode)


def fail_once(page,state_dir,out_dir,mechanic):
    assert mechanic==MECHANIC_ID
    before=json.loads((state_dir/'ground_truth.json').read_text())['challenge_id']
    page.locator('#sb-certify').click()
    expect(page.locator('.readout')).to_contain_text('FAIL',timeout=10000)
    assert page.locator('.sorting-bench').get_attribute('data-challenge-id')!=before
    page.screenshot(path=str(out_dir/f'{mechanic}-fail-refresh.png'))


def solve(page,state_dir,out_dir,mechanic):
    assert mechanic==MECHANIC_ID
    truth=json.loads((state_dir/'ground_truth.json').read_text());build(page,truth)
    page.screenshot(path=str(out_dir/f'{mechanic}-wired.png'))
    page.locator('#sb-run').click()
    page.wait_for_timeout(850)
    page.screenshot(path=str(out_dir/f'{mechanic}-active.png'))
    expect(page.locator('.readout')).to_contain_text('BATCH COMPLETE',timeout=30000)
    page.screenshot(path=str(out_dir/f'{mechanic}-solved.png'))
    page.locator('#sb-certify').click()
    expect(page.locator('.readout')).to_contain_text('PASS',timeout=10000)
