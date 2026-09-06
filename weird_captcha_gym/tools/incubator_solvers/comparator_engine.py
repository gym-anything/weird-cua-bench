"""Visible-label automation for browser wiring checks, not a CUA model result.

Reads rendered labels only; never reads challenge truth or page implementation state.
Remembered identity relations allow early sealing when they certify the whole row.
"""
import json
from pathlib import Path
from playwright.sync_api import expect
MECHANIC_ID = 'comparator_engine'


def pull(page, action, full=False):
    if not full:
        page.locator(f'.ce-button[data-action="{action}"]').click()
        return
    box = page.locator(f'.ce-lever[data-action="{action}"]').bounding_box()
    x = box['x'] + box['width']*.5
    page.mouse.move(x, box['y'] + box['height']*.18)
    page.mouse.down()
    page.mouse.move(x, box['y'] + box['height']*.87, steps=5)
    page.mouse.up()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic=MECHANIC_ID):
    assert mechanic == MECHANIC_ID
    old = page.locator('.ce-engine').get_attribute('data-challenge-id')
    pull(page, 'seal', page.locator('.ce-lever').count() > 0)
    page.get_by_role('button', name='LOAD FRESH FRAME').wait_for()
    page.screenshot(path=str(out_dir/'comparator_engine-failure.png'))
    page.get_by_role('button', name='LOAD FRESH FRAME').click()
    page.locator('.ce-verdict[hidden]').wait_for(state='attached')
    fresh = page.locator('.ce-engine').get_attribute('data-challenge-id')
    assert fresh != old
    page.screenshot(path=str(out_dir/'comparator_engine-retry.png'))


def solve_metered(page, out_dir, full):
    """Choose comparisons through a remembered ordered prefix using visible IDs."""
    def row():
        return page.locator('.ce-slide > b').all_text_contents()
    def go(index):
        for _ in range(len(row())):
            current = int(page.locator('.ce-slide.is-current .ce-slot').first.inner_text())-1
            if current == index:
                return
            pull(page,'advance',full)
        raise AssertionError('carriage did not reach visible slot')
    def swap(index):
        go(index);pull(page,'exchange',full)
    observations=[];relations=set()
    for k in range(1,len(row())):
        pivot=row()[k];prefix=row()[:k]
        lo,hi=0,k
        while lo < hi:
            mid=(lo+hi)//2;anchor=prefix[mid]
            while abs(row().index(pivot)-row().index(anchor)) > 1:
                bank=row();p,q=bank.index(pivot),bank.index(anchor)
                swap(p-1 if p > q else p)
            bank=row();go(min(bank.index(pivot),bank.index(anchor)))
            pull(page,'weigh',full)
            label=page.locator('.ce-pair-label').inner_text()
            pair,verdict=label.split(' / ');a,b=pair.split(' · ')
            assert verdict in ('LEFT HEAVIER','RIGHT HEAVIER'), 'metered reading rejected'
            lighter,heavier=(b,a) if verdict=='LEFT HEAVIER' else (a,b)
            relations.add((lighter,heavier))
            observations.append({'row':row(),'pivot':pivot,'ordered_prefix':prefix,
                'lower':lo,'upper':hi,'anchor':anchor,'comparison':label})
            if len(observations)==3:
                page.screenshot(path=str(out_dir/'comparator_engine-measurement.png'))
            if lighter==pivot:hi=mid
            else:lo=mid+1
        while row().index(pivot)!=lo:
            p=row().index(pivot);swap(p-1 if p>lo else p)
        if k==3:page.screenshot(path=str(out_dir/'comparator_engine-active.png'))
    (out_dir/'visible-solver-trace.json').write_text(json.dumps({
        'policy':'binary insertion through visible adjacent comparisons',
        'hidden_state_reads':False,'metered':True,'seal_reason':'binary_insertion',
        'relations':sorted(relations),'observations':observations,
    },indent=2)+'\n')
    page.screenshot(path=str(out_dir/'comparator_engine-solved.png'))
    pull(page,'seal',full)
    expect(page.locator('.readout')).to_have_text('PASS',timeout=90000)
    page.screenshot(path=str(out_dir/'comparator_engine-pass.png'))


def solve(page, state_dir: Path, out_dir: Path, mechanic=MECHANIC_ID):
    assert mechanic == MECHANIC_ID
    full = page.locator('.ce-lever').count() > 0
    manual = page.locator('[data-action="weigh"]').count() > 0
    if manual:
        return solve_metered(page,out_dir,full)
    relations = set()
    trace = []
    def ordered(a, b):
        frontier, seen = [a], set()
        while frontier:
            node = frontier.pop()
            if node == b:
                return True
            if node in seen:
                continue
            seen.add(node)
            frontier.extend(y for x, y in relations if x == node)
        return False

    for count in range(100):
        row = page.locator('.ce-slide > b').all_text_contents()
        label = page.locator('.ce-pair-label').inner_text()
        pair, verdict = label.split(' / ')
        a, b = pair.split(' · ')
        left_heavier = verdict == 'LEFT HEAVIER'
        assert verdict in ('LEFT HEAVIER', 'RIGHT HEAVIER')
        relations.add((b, a) if left_heavier else (a, b))
        trace.append({'row': row, 'comparison': label})
        if left_heavier:
            pull(page, 'exchange', full)
            row = page.locator('.ce-slide > b').all_text_contents()
        certified = all(ordered(a, b) for a, b in zip(row, row[1:]))
        remaining = int(page.locator('.ce-counter b').first.inner_text())
        if certified or remaining == 0:
            # The latter is the independently documented generator-bound policy;
            # do not describe it as a remembered comparison certificate.
            reason = 'remembered_relations' if certified else 'generation_bound'
            break
        pull(page, 'advance', full)
        if count == 3:
            page.screenshot(path=str(out_dir/'comparator_engine-active.png'))
    else:
        raise AssertionError('visible solver exceeded the comparison bound')
    (out_dir/'visible-solver-trace.json').write_text(json.dumps({
        'policy': 'visible labels with remembered identity relations',
        'hidden_state_reads': False, 'seal_reason': reason, 'metered': manual,
        'relations': sorted(relations), 'observations': trace,
    }, indent=2)+'\n')
    page.screenshot(path=str(out_dir/'comparator_engine-solved.png'))
    pull(page,'seal',full)
    expect(page.locator(".readout")).to_have_text("PASS", timeout=10000)
    page.screenshot(path=str(out_dir/'comparator_engine-pass.png'))
