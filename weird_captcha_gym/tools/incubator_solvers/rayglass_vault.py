"""Scripted demonstration: infer from revealed ledger entries, use normal inputs.

This algorithmic solver is implementation evidence, not a screenshot-only agent.
It reads public size/count and enumerates hypotheses with the Python ray engine;
no hidden bead coordinates or unrevealed sensor responses choose its actions.
"""
from __future__ import annotations
import importlib.util
import itertools
import json
import time
from collections import Counter
from pathlib import Path

MECHANIC_ID = 'rayglass_vault'
ROOT = Path(__file__).resolve().parents[2]


def physics():
    spec=importlib.util.spec_from_file_location('rv_solver_physics',ROOT/'shared_runtime/server/incubator_graders/rayglass_vault.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def choose(page, selector, index):
    # Native popup typeahead works across Chromium platforms; Home/arrow
    # handling in an open macOS popup does not reliably change selection.
    control = page.locator(selector)
    option = control.locator('option').nth(index)
    label, value = option.inner_text(), option.get_attribute('value')
    # Cycle the first-character group. Typing a repeated-digit label like
    # "22" can be interpreted as two cycle requests, skipping the target.
    for _ in range(control.locator('option').count()+1):
        if control.input_value() == value:
            return
        control.click()
        page.keyboard.type(label[0])
        page.keyboard.press('Enter')
        page.keyboard.press('Tab')
    raise AssertionError(f'Rayglass native selection did not choose {label}')


def click_probe(page, port, mode):
    if mode == 'full':
        page.locator(f'[data-port="{port}"]').click()
    else:
        choose(page, '#rv-port-select', port)
        page.locator('#rv-fire').click()


def click_mark(page, index, n, mode):
    if mode == 'full':
        page.locator(f'[data-cell="{index}"]').click()
    else:
        choose(page, '#rv-row', index//n)
        choose(page, '#rv-col', index%n)
        page.locator('#rv-mark').click()


def read_response(page, port):
    text=page.locator('#rv-ledger .rv-entry').nth(port).inner_text()
    if '↔' in text:
        return int(text.split('↔')[1].strip())-1
    value=text.split('·')[-1].strip()
    if value not in ('H','R'):
        raise AssertionError(f'no visible response: {text}')
    return value


def solve(page, state_dir, out_dir, mechanic=MECHANIC_ID):
    assert mechanic == MECHANIC_ID
    state=json.loads((Path(state_dir)/'public_state.json').read_text())
    n,count=state['size'],state['bead_count']
    mode=(state.get('control_condition') or {}).get('interaction','full')
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    page.wait_for_selector('#rv-cabinet')
    page.screenshot(path=str(out_dir/f'{mechanic}-initial.png'))
    g=physics();candidates=None;unused=list(range(4*n));history=[]
    while unused:
        if candidates is None:
            port=0
            pool=itertools.combinations(range(n*n),count)
        else:
            # First check that the whole remaining set is one observable class.
            first=g.signature(n,candidates[0])
            different=next((b for b in candidates[1:] if g.signature(n,b)!=first),None) if len(candidates)<400 else True
            if different is None:
                break
            sample=candidates[::max(1,len(candidates)//160)][:160]
            def gain(p):
                groups=Counter(g.ray(n,b,p) for b in sample)
                return sum(v*v for v in groups.values())
            port=min(unused,key=gain)
            pool=candidates
        click_probe(page,port,mode)
        response=read_response(page,port)
        candidates=[b for b in pool if g.ray(n,b,port)==response]
        assert candidates,'visible sensor response eliminated every layout'
        history.append({'port':port+1,'response':response+1 if type(response)==int else response,'remaining_candidates':len(candidates)})
        unused.remove(port)
        if len(history)==3:page.screenshot(path=str(out_dir/f'{mechanic}-active.png'))
    assert candidates
    for index in candidates[0]:
        click_mark(page,index,n,mode)
    page.screenshot(path=str(out_dir/f'{mechanic}-hypothesis.png'))
    page.locator('#rv-seal').click()
    from playwright.sync_api import expect
    expect(page.locator('#rv-status')).to_have_text('PASS · VAULT OPEN',timeout=20000)
    page.screenshot(path=str(out_dir/f'{mechanic}-pass.png'))
    (out_dir/'deduction.json').write_text(json.dumps({'steps':history,'selected_layout':candidates[0],'remaining_equivalent_layouts':len(candidates)},indent=2))


def fail_once(page, state_dir, out_dir, mechanic=MECHANIC_ID):
    assert mechanic==MECHANIC_ID
    state=json.loads((Path(state_dir)/'public_state.json').read_text())
    n,count=state['size'],state['bead_count'];mode=(state.get('control_condition') or {}).get('interaction','full')
    g=physics()
    # Negative fixture intentionally uses truth to guarantee rejection. It is
    # separate from the successful inference/film trajectory.
    truth=json.loads((Path(state_dir)/'ground_truth.json').read_text())
    signature=g.signature(n,truth['beads'])
    wrong=next(b for b in itertools.combinations(range(n*n),count) if g.signature(n,b)!=signature)
    for i in wrong:click_mark(page,i,n,mode)
    page.locator('#rv-seal').click()
    from playwright.sync_api import expect
    expect(page.locator('#rv-verdict')).to_be_visible(timeout=20000)
    page.screenshot(path=str(Path(out_dir)/f'{mechanic}-fail.png'))
    new=json.loads((Path(state_dir)/'public_state.json').read_text())
    assert new['challenge_id']!=state['challenge_id']
    page.locator('#rv-retry').click()
    expect(page.locator('.rayglass-vault')).to_have_attribute('data-mark-count','0')
    expect(page.locator('.rayglass-vault')).to_have_attribute('data-query-count','0')
    page.screenshot(path=str(Path(out_dir)/f'{mechanic}-recovery.png'))
