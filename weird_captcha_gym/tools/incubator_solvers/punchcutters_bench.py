"""Wiring solver: reads generated geometry, sends only real browser input."""
import json
from pathlib import Path
from weird_captcha_gym.shared_runtime.server.incubator_graders.punchcutters_bench import spacing_reference, glyph_polygons
MECHANIC_ID='punchcutters_bench'


def screen(page,p):
    box=page.locator('.punch-paper canvas').bounding_box()
    return box['x']+p[0]*box['width']/800,box['y']+p[1]*box['height']/410


def cut(page,bench,out_dir=None):
    full=page.locator('.punch-bench').get_attribute('data-interaction')=='full'
    for i,(x,y,dx,dy) in enumerate(bench['master']):
        if full:
            page.mouse.move(*screen(page,[x,y]));page.mouse.down();page.mouse.move(*screen(page,[x+dx,y+dy]),steps=1);page.mouse.up()
        else:
            page.locator('[data-tool="smooth"]' if dx or dy else '[data-tool="corner"]').click()
            page.mouse.click(*screen(page,[x,y]))
            if dx or dy:page.mouse.click(*screen(page,[x+dx,y+dy]))
        if out_dir and i==len(bench['master'])//2:page.screenshot(path=str(Path(out_dir)/'active-cut.png'))
    page.locator('.punch-close').click()
    if out_dir:page.screenshot(path=str(Path(out_dir)/'closed-outline.png'))
    page.locator('.punch-proof').click()
    assert page.locator('.punch-bench').get_attribute('data-stage')=='2'


def ink_point(bench,index,position):
    """Pick an interior point of visible ink by crossing its actual contour."""
    poly=glyph_polygons(bench,bench['master'])[index];y=70;xs=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if (a[1]<=y<b[1]) or (b[1]<=y<a[1]):
            xs.append(a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1]))
    xs.sort();assert len(xs)>=2
    return position+(xs[0]+xs[1])/2,124+y


def space(page,bench,out_dir=None):
    full=page.locator('.punch-bench').get_attribute('data-interaction')=='full'
    # Use rendered contour coordinates from the known solve, corrected for normal
    # screen rounding, by reconstructing the pen transcript recorded by input.
    # Truth nodes suffice at the public tolerance; no browser state mutation.
    ref=spacing_reference(bench,bench['master'])
    for i in range(1,len(ref)-1):
        g=bench['glyphs'][i];x=bench['initial_positions'][i]
        px,py=ink_point(bench,i,x)
        page.mouse.move(*screen(page,[px,py]));page.mouse.down()
        if full:page.mouse.move(*screen(page,[px+ref[i]-x,py]),steps=1)
        page.mouse.up()
        if not full:page.mouse.click(*screen(page,[ref[i]+g['width']/2,py]))
    if out_dir:page.screenshot(path=str(Path(out_dir)/'spaced-word.png'))


def solve(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    assert mechanic==MECHANIC_ID
    bench=json.loads((Path(state_dir)/'public_state.json').read_text())['bench']
    cut(page,bench,out_dir);space(page,bench,out_dir);page.locator('.punch-certify').click()


def fail_once(page,state_dir,out_dir,mechanic=MECHANIC_ID):
    bench=json.loads((Path(state_dir)/'public_state.json').read_text())['bench']
    cut(page,bench)
    # Move a movable letter visibly out of spacing, then submit.
    full=page.locator('.punch-bench').get_attribute('data-interaction')=='full'
    x,y=ink_point(bench,1,bench['initial_positions'][1])
    page.mouse.move(*screen(page,[x,y]));page.mouse.down()
    if full:page.mouse.move(*screen(page,[x+100,y]))
    page.mouse.up()
    if not full:page.mouse.click(*screen(page,[bench['initial_positions'][1]+bench['glyphs'][1]['width']/2+100,y]))
    page.locator('.punch-certify').click();page.locator('.punch-retry').wait_for(state='visible')
    page.screenshot(path=str(Path(out_dir)/'failure.png'));page.locator('.punch-retry').click()
    page.locator('.punch-proof').wait_for(state='visible');page.screenshot(path=str(Path(out_dir)/'fresh-retry.png'))
