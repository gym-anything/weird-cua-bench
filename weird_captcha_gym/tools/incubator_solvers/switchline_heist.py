"""Privileged test observer, ordinary browser inputs only; not agent evidence."""
import time
from pathlib import Path
from playwright.sync_api import expect

def snapshot(page):return page.evaluate('JSON.parse(JSON.stringify(window.switchlineHeist))')

def wait(page,ms=100):
    if page.evaluate("window.WeirdCaptchaTime?.status().state === 'paused'"):
        page.evaluate('WeirdCaptchaTime.runFor(250)')
        for _ in range(100):
            if page.evaluate("WeirdCaptchaTime.status().phase === 'completed'"):break
            page.wait_for_timeout(10)
        else:raise AssertionError('observation window did not complete')
    else:page.wait_for_timeout(ms)

def move(page,target,mode):
    current=snapshot(page)['state']['x']
    direction=1 if target>current else -1
    if mode=='full':page.keyboard.down('ArrowRight' if direction==1 else 'ArrowLeft')
    else:
        b=page.locator('#sh-right' if direction==1 else '#sh-left').bounding_box();page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2);page.mouse.down()
    try:
        for _ in range(500):
            s=snapshot(page)['state']
            if s['caught']:raise AssertionError(f'caught while walking to {target}: {s}')
            if (target-s['x'])*direction<=10:break
            wait(page,50)
        else:raise AssertionError(f'walk blocked toward {target}: {s}')
    finally:
        if mode=='full':page.keyboard.up('ArrowRight' if direction==1 else 'ArrowLeft')
        else:page.mouse.up()

def control(page,name,mode):
    if mode=='full':page.keyboard.press({'use':'e','hide':'Space','pickup':'f'}[name])
    else:page.locator('#sh-'+name).click()

def wire(page,src,dst,mode):
    if not snapshot(page)['state']['overlay']:page.locator('#sh-overlay').click()
    w=snapshot(page)['world'];a=next(x for x in w['switches'] if x['id']==src);b=next(x for x in w['outputs'] if x['id']==dst)
    r=page.locator('.sh-stage canvas').bounding_box()
    def point(x,y):return(r['x']+x*r['width']/1000,r['y']+y*r['height']/400)
    if mode=='full':
        page.mouse.move(*point(a['x'],58));page.mouse.down();page.mouse.move(*point(b['x'],111),steps=8);page.mouse.up()
    else:page.mouse.click(*point(a['x'],58));page.mouse.click(*point(b['x'],111))
    assert snapshot(page)['state']['wires'][src]==dst
    page.locator('#sh-overlay').click()

def fail_once(page,state_dir:Path,out_dir:Path,mechanic='switchline_heist'):
    old=page.evaluate('window.switchlineHeist.world')
    page.locator('#sh-extract').click()
    page.wait_for_function("document.querySelector('.readout').textContent.includes('FRESH')")
    page.screenshot(path=str(out_dir/'failure-fresh.png'))

def solve(page,state_dir:Path,out_dir:Path,mechanic='switchline_heist'):
    mode='simplified' if page.locator('#sh-use').count() else 'full'
    w=snapshot(page)['world']
    for i,g in enumerate(w['gates']):
        src=f's{i}L';move(page,g['x']-64,mode);wire(page,src,g['id'],mode);control(page,'use',mode)
        if i<len(w['gates'])-1:move(page,g['x']+100,mode)
    i=len(w['gates'])-1;g=w['gates'][-1]
    wire(page,f's{i}L','lamp',mode);control(page,'use',mode)
    for _ in range(300):
        if snapshot(page)['state']['gx']>=936:break
        wait(page,100)
    else:raise AssertionError('attendant did not investigate')
    page.screenshot(path=str(out_dir/'active-darkness.png'))
    move(page,w['item'],mode);control(page,'hide',mode);control(page,'pickup',mode)
    if w['parameters']['alarm']:
        for _ in range(500):
            s=snapshot(page)['state']
            if 908<=s['gx']<=916 and s['gd']==1:break
            wait(page,100)
        else:raise AssertionError('no escape window')
    control(page,'hide',mode)
    move(page,g['x']+64,mode)
    for i in reversed(range(len(w['gates']))):
        g=w['gates'][i];move(page,g['x']+64,mode)
        if not snapshot(page)['state']['gates'][g['id']]:
            wire(page,f's{i}R',g['id'],mode);control(page,'use',mode)
        move(page,g['x']-64,mode)
    move(page,64,mode)
    page.screenshot(path=str(out_dir/'solved.png'))
    page.locator('#sh-extract').click()
    expect(page.locator('.readout')).to_have_attribute('data-status','passed',timeout=10000)
