"""Wiring solver: reads a certified route, executes only ordinary browser input."""
import json
from pathlib import Path
from playwright.sync_api import expect

KEYS={'N':'ArrowUp','E':'ArrowRight','S':'ArrowDown','W':'ArrowLeft'}


def fail_once(page,state_dir,out_dir,mechanic='living_scaffold'):
    before=json.loads((Path(state_dir)/'ground_truth.json').read_text())['challenge_id']
    page.locator('.ls-submit').click()
    expect(page.locator('.readout')).to_contain_text('FAIL',timeout=60000)
    after=json.loads((Path(state_dir)/'ground_truth.json').read_text())['challenge_id']
    assert before!=after
    page.screenshot(path=str(Path(out_dir)/f'{mechanic}-failed.png'))
    page.get_by_role('button',name='Try again',exact=True).click()
    expect(page.locator('.readout')).to_be_empty()
    expect(page.locator('.ls-verdict')).to_be_empty()
    page.screenshot(path=str(Path(out_dir)/f'{mechanic}-fail-refresh.png'))


def solve(page,state_dir,out_dir,mechanic='living_scaffold',pace_ms=65):
    truth=json.loads((Path(state_dir)/'ground_truth.json').read_text())
    mode=(truth.get('control_condition') or {}).get('interaction','full')
    route=truth['solution_path']
    for k,(i,d) in enumerate(route):
        if mode=='full':
            page.locator(f'.ls-creature[data-creature="{i}"] .ls-segment[data-segment="0"]').click()
            page.keyboard.press(KEYS[d])
        else:
            page.locator(f'button[data-select="{i}"]').click()
            page.locator(f'button[data-dir="{d}"]').click()
        if pace_ms: page.wait_for_timeout(pace_ms)
        if k==len(route)//2: page.screenshot(path=str(Path(out_dir)/f'{mechanic}-active.png'))
    page.screenshot(path=str(Path(out_dir)/f'{mechanic}-solved.png'))
    page.locator('.ls-submit').click()
    expect(page.locator('.readout')).to_have_attribute('data-status','passed',timeout=60000)
    page.screenshot(path=str(Path(out_dir)/f'{mechanic}-pass.png'))
