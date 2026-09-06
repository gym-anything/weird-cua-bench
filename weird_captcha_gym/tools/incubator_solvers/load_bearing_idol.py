"""Wiring-only solver: generated geometry guides ordinary browser inputs."""
import json
from pathlib import Path

MECHANIC_ID='load_bearing_idol'

def gesture(page,b,mode):
    box=page.locator('.idol-stage canvas').bounding_box()
    def xy(x,y):return box['x']+x*box['width']/860,box['y']+y*box['height']/550
    start=[b['x'],b['y']];end=start[:]
    if mode=='simplified':
        page.mouse.click(*xy(*start))
        op='right' if b['kind']=='plank' else 'crumble'
        page.locator(f'[data-op="{op}"]').click()
    elif b['kind']=='chalk':page.mouse.click(*xy(*start))
    else:
        end[0]+=b['w']+60
        page.mouse.move(*xy(*start));page.mouse.down();page.mouse.move(*xy(*end),steps=12);page.mouse.up()

def solve(page,state_dir:Path,out_dir:Path,mechanic=MECHANIC_ID):
    state=json.loads((state_dir/'public_state.json').read_text());mode=(state.get('control_condition') or {}).get('interaction','full')
    bs=state['bodies'];order=[b for b in bs if b['id'].startswith('weight')]+sorted([b for b in bs if b['id'].startswith('piece')],key=lambda b:b['y'])
    for i,b in enumerate(order):
        gesture(page,b,mode)
        page.wait_for_function("!document.querySelector('.idol-certify').disabled",timeout=15000)
        if out_dir:page.screenshot(path=str(out_dir/f'{mechanic}-step-{i}.png'))
    page.locator('.idol-certify').click()
    page.wait_for_function("document.querySelector('.readout').dataset.status==='passed'",timeout=60000)

def fail_once(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    previous=json.loads((state_dir/'public_state.json').read_text())['challenge_id']
    page.locator('.idol-certify').click()
    page.wait_for_function("document.querySelector('.readout').textContent.includes('FAIL')",timeout=60000)
    page.screenshot(path=str(out_dir/f'{mechanic}-failure.png'))
    page.locator('.idol-retry').click()
    page.wait_for_function("!document.querySelector('.idol-stamp') || document.querySelector('.idol-stamp').hidden")
    assert json.loads((state_dir/'public_state.json').read_text())['challenge_id']!=previous
