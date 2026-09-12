"""Privileged physical oracle: searches legal torque trajectories, then delivers
only native mouse/keyboard inputs. It is not a screenshot-only agent result.
"""
import json,subprocess
from pathlib import Path
from playwright.sync_api import expect
ROOT=Path(__file__).resolve().parents[2]
PLANNER=r'''
const fs=require('fs');global.window={};eval(fs.readFileSync(process.argv[1],'utf8'));
const {step,error,settled}=window.PorcelainPhysics,input=JSON.parse(fs.readFileSync(0,'utf8')),p=input.p;
let randomSeed=123456789;function rng(){randomSeed=(Math.imul(1664525,randomSeed)+1013904223)>>>0;return randomSeed/4294967296;}
let nodes=[{s:input.s,path:[],time:0}],best=9,goals=[];
for(let k=0;k<30000;k++){
 let parent=goals.length&&rng()<.4?goals[Math.floor(rng()*goals.length)]:rng()<.65?nodes[Math.max(0,nodes.length-1-Math.floor(rng()*Math.min(120,nodes.length)))]:nodes[Math.floor(rng()*nodes.length)];
 if(parent.time>18000)parent=nodes[0];
 const u=[Math.floor(rng()*3)-1,Math.floor(rng()*3)-1],ticks=10+Math.floor(rng()*250);let s=parent.s,c=0;
 for(let i=0;i<ticks;i++){let z=step(s,u,p);s=z[0];c+=z[1];}
 const path=[...parent.path,{u,ticks}],node={s,path,time:parent.time+ticks};
 nodes.push(node);
 // Bias later expansion toward states that have actually transferred momentum,
 // while retaining configurations that approach or retract the separate finger.
 if(c>0)nodes.push(node,node);
 if(error(s,p)<.7||k%17===0){let coast=s,hold=0,n=0;for(;n<800;n++){coast=step(coast,[0,0],p)[0];hold=settled(coast,[0,0],p)?hold+1:0;if(hold>=120&&error(coast,p)<p.tolerance*.7){console.log(JSON.stringify({path:[...path,{u:[0,0],ticks:n+1}],iterations:k,final:coast}));process.exit(0);}}
 const cost=error(coast,p);best=Math.min(best,cost);goals.push({s:coast,path:[...path,{u:[0,0],ticks:n}],time:node.time+n,cost});goals.sort((a,b)=>a.cost-b.cost);goals=goals.slice(0,30);}
}
throw Error('No torque solution; best angle error '+best);
'''

def plan(s,p):
    cmd=['node','-e',PLANNER,str(ROOT/'shared_runtime/app/mechanics/porcelain_turntable.js')]
    r=subprocess.run(cmd,input=json.dumps({'s':s,'p':p}),text=True,capture_output=True,timeout=120)
    if r.returncode:raise RuntimeError(r.stderr)
    return json.loads(r.stdout)

def set_torque(page,u,full,current):
    for j in range(2):
        if current[j]==u[j]:continue
        if full:
            key=lambda v:('a' if v<0 else 'd') if j==0 else ('j' if v<0 else 'l')
            if current[j]:page.keyboard.up(key(current[j]))
            if u[j]:page.keyboard.down(key(u[j]))
        else:page.locator(f'[data-j="{j}"][data-u="{u[j]}"]').click(force=True)
    return list(u)

def fail_once(page,state_dir,out_dir,mechanic='porcelain_turntable'):
    old=page.locator('.porcelain').get_attribute('data-challenge-id')
    with page.expect_response(lambda r:r.url.endswith('/result') and r.request.method=='POST') as response:
        page.locator('#pt-submit').click(force=True)
    (out_dir/'failure-response.json').write_text(json.dumps(response.value.json(),indent=2))
    expect(page.locator('.porcelain')).not_to_have_attribute('data-challenge-id',old)
    page.screenshot(path=str(out_dir/'failure-fresh.png'))
    assert page.evaluate('porcelainModel.tick===0 && porcelainModel.events.length===0')

def solve(page,state_dir,out_dir,mechanic='porcelain_turntable',advance=None):
    state=json.loads((state_dir/'public_state.json').read_text());p=state['physics'];full=(state.get('control_condition') or {}).get('interaction','full')=='full'
    solution=plan(page.evaluate('porcelainModel.s'),p)
    (out_dir/'oracle-plan.json').write_text(json.dumps(solution,indent=2))
    page.locator('#pt-start').click(force=True);current=[0,0];shot=False
    for attempt in range(4):
        for action in solution['path']:
            current=set_torque(page,action['u'],full,current)
            if advance:advance(action['ticks']*10)
            else:page.wait_for_timeout(action['ticks']*10)
            if not shot and page.evaluate('porcelainModel.contacts>0'):
                page.screenshot(path=str(out_dir/'active-contact.png'));shot=True
        if page.evaluate('porcelainModel.hold>=80'):break
        current=set_torque(page,[0,0],full,current)
        if advance:advance(6000)
        else:page.wait_for_timeout(6000)
        if page.evaluate('porcelainModel.hold>=80'):break
        solution=plan(page.evaluate('porcelainModel.s'),p)
    assert page.evaluate('porcelainModel.hold>=80'),'Oracle did not settle'
    page.screenshot(path=str(out_dir/'solved.png'));page.locator('#pt-submit').click(force=True)
    expect(page.locator('.readout')).to_have_attribute('data-status','passed',timeout=30000)
