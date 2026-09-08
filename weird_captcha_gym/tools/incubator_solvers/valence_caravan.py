"""Implementation oracle for browser validation, not a screenshot-only agent."""
import json
from pathlib import Path
from playwright.sync_api import expect
KEYS={'N':'ArrowUp','E':'ArrowRight','S':'ArrowDown','W':'ArrowLeft','CW':'e','CCW':'q'}
def fail_once(page,state_dir,out_dir,mechanic):
    before=json.loads((state_dir/'ground_truth.json').read_text())['challenge_id']
    page.locator('.vc-submit').click()
    expect(page.locator('.vc-verdict b')).to_have_text('FAIL')
    page.screenshot(path=str(out_dir/f'{mechanic}-fail.png'))
    assert json.loads((state_dir/'ground_truth.json').read_text())['challenge_id']!=before
    page.locator('.vc-verdict button').click()
    page.screenshot(path=str(out_dir/f'{mechanic}-fresh.png'))
def solve(page,state_dir,out_dir,mechanic):
    truth=json.loads((state_dir/'ground_truth.json').read_text())
    full=(truth.get('control_condition') or {}).get('interaction','full')=='full'
    for i,cmd in enumerate(truth['solution_path']):
        if full:page.keyboard.press(KEYS[cmd])
        else:page.locator(f'[data-command="{cmd}"]').click()
        page.wait_for_timeout(110)
        if i==len(truth['solution_path'])//2:page.screenshot(path=str(out_dir/f'{mechanic}-active.png'))
    expect(page.locator('.vc-submit')).to_be_visible()
    page.screenshot(path=str(out_dir/f'{mechanic}-solved.png'))
    page.locator('.vc-submit').click()
    expect(page.locator('.vc-verdict b')).to_have_text('PASS')
    page.screenshot(path=str(out_dir/f'{mechanic}-pass.png'))
