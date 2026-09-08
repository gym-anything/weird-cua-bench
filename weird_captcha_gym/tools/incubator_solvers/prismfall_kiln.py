"""Construction-aware scripted witness; all actions use visible browser controls."""
import json
import importlib.util
from pathlib import Path
MECHANIC_ID='prismfall_kiln'
def _engine():
 p=Path(__file__).resolve().parents[2]/'shared_runtime/server/incubator_graders/prismfall_kiln.py';s=importlib.util.spec_from_file_location('kiln_solver_physics',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def release(page,public,x):
 if (public.get('control_condition') or {}).get('interaction','full')=='simplified':
  page.locator('#kiln-position').fill(str(x));page.locator('#kiln-release').click()
 else:
  box=page.locator('#kiln-canvas').bounding_box();w=public['world'];scale=min(370/w['width'],420/w['height']);ox=(420-w['width']*scale)/2
  page.mouse.click(round(box['x']+(ox+x*scale)*box['width']/420),round(box['y']+(42+38*scale)*box['height']/490))

def choose_drop(page,public,bs,t):
 sim=_engine();w=public['world']
 if (public.get('control_condition') or {}).get('interaction','full')=='simplified':return sim.choose(bs,w,t,public['target'])
 box=page.locator('#kiln-canvas').bounding_box();scale=min(370/w['width'],420/w['height']);ox=(420-w['width']*scale)/2
 proposed=[sim.RADII[t]+2,w['width']-sim.RADII[t]-2,w['width']/2]+[b['x'] for b in bs]+[w['width']*i/10 for i in range(1,10)]
 # MouseEvent click coordinates are integer CSS pixels. Score the positions
 # that this visible browser surface can actually deliver.
 candidates=[]
 for x in proposed:
  sx=round(box['x']+(ox+x*scale)*box['width']/420)
  actual=round(((sx-box['x'])*420/box['width']-ox)/scale,1)
  candidates.append(actual)
 return sim.choose(bs,w,t,public['target'],candidates=sorted(set(candidates)))

def solve(page,state_dir,out_dir,mechanic=MECHANIC_ID):
 public=json.loads((state_dir/'public_state.json').read_text());sim=_engine();bs=public['initial']
 for i,t in enumerate(public['offers']):
  x,bs,n,over=choose_drop(page,public,bs,t);release(page,public,x)
  try:
   page.wait_for_function("n=>document.querySelector('#kiln-canvas').dataset.drops===String(n)",arg=i+1,timeout=20000)
  except Exception:
   page.screenshot(path=str(out_dir/'solver-failure.png'))
   (out_dir/'solver-failure.json').write_text(json.dumps({'expected_drop':i+1,'requested_x':x,'public':public,'model':page.evaluate('({bodies:prismfallKilnModel.bodies,events:prismfallKilnModel.events,terminal:prismfallKilnModel.terminal})')},indent=2))
   raise
  bs=page.evaluate('window.prismfallKilnModel.bodies')
  if any(b['y']-sim.RADII[b['t']]<public['world']['overflow'] for b in bs):raise AssertionError('scripted kiln overflow')
  if any(b['t']>=public['target'] for b in bs):break
 page.locator('#kiln-certify').click();page.wait_for_function("document.querySelector('.readout').textContent==='PASS'",timeout=20000)

def fail_once(page,state_dir,out_dir,mechanic=MECHANIC_ID):
 old=json.loads((state_dir/'public_state.json').read_text())['challenge_id'];page.locator('#kiln-certify').click()
 page.wait_for_function("document.querySelector('.readout').textContent.includes('FAIL')")
 assert json.loads((state_dir/'public_state.json').read_text())['challenge_id']!=old
 page.screenshot(path=str(out_dir/'failure-fresh.png'))
