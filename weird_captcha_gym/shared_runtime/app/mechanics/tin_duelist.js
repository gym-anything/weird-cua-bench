(() => {
'use strict';
const ID='tin_duelist', clone=x=>JSON.parse(JSON.stringify(x));
let cleanup=null;
const MOVES={jab:{start:8,active:4,recovery:16,reach:95,damage:12},lunge:{start:16,active:4,recovery:26,reach:170,damage:22},hammer:{start:22,active:4,recovery:30,reach:105,damage:28}};
function initial(w){const f=x=>({x,hp:100,move:'',age:0,stun:0,guard:false,hit:false});return {tick:0,player:f(w.player_x),enemy:f(w.enemy_x),direction:0,guard:false,rng:w.policy_seed,next_decision:12,last_exchange:'none',status:'active',contacts:[]};}
function data(name,enemy,p){const m={...MOVES[name]};if(enemy){m.start+=p.startup_bonus;m.recovery+=p.recovery_bonus;}return m;}
function attack(f,name){if(!f.move&&!f.stun){Object.assign(f,{move:name,age:0,hit:false,guard:false});return true;}return false;}
function step(s,w){
 if(s.status!=='active')return;
 const p=w.parameters;s.tick++;const a=s.player,b=s.enemy;
 for(const [enemy,f] of [[false,a],[true,b]]){if(f.stun)f.stun--;if(f.move){f.age++;const m=data(f.move,enemy,p);if(f.age>=m.start+m.active+m.recovery)Object.assign(f,{move:'',age:0});}}
 a.guard=Boolean(s.guard&&!a.move&&!a.stun);
 if(!a.move&&!a.stun&&!a.guard)a.x=Math.max(40,Math.min(b.x-48,a.x+s.direction*5));
 b.guard=false;const gap=b.x-a.x-48;
 if(!b.move&&!b.stun){
  if(p.enemy_guard&&a.move&&a.age<MOVES[a.move].start+MOVES[a.move].active&&gap<=175&&a.move!=='hammer')b.guard=true;
  else if(s.tick>=s.next_decision){s.rng=(s.rng*25173+13849)%65536;s.next_decision=s.tick+p.decision_ticks+s.rng%5;
   if(gap<=Math.max(...p.enemy_moves.map(n=>MOVES[n].reach))){let choices=p.enemy_moves.filter(n=>MOVES[n].reach>=gap);if(!choices.length)choices=['lunge'];let name=choices[s.rng%choices.length];if(p.adaptive&&a.guard&&choices.includes('hammer'))name='hammer';else if(p.adaptive&&s.last_exchange==='enemy_miss'&&choices.includes('jab')&&gap<=90)name='jab';attack(b,name);}}
  if(!b.move&&!b.guard)b.x=Math.max(a.x+48,Math.min(960,gap>w.approach_gap-10?b.x-p.enemy_speed:b.x));
 }
 const hits=[];
 for(const [enemy,f,target] of [[false,a,b],[true,b,a]]){if(!f.move)continue;const m=data(f.move,enemy,p);
  if(m.start<=f.age&&f.age<m.start+m.active&&!f.hit&&b.x-a.x-48<=m.reach){const blocked=target.guard&&f.move!=='hammer';hits.push([enemy,blocked,m.damage,f.move]);f.hit=true;}
  if(f.age===m.start+m.active&&!f.hit)s.last_exchange=enemy?'enemy_miss':'player_miss';
 }
 for(const [enemy,blocked,damage,name] of hits){const target=enemy?a:b;if(!blocked){target.hp=Math.max(0,target.hp-damage);Object.assign(target,{stun:10,move:'',age:0,guard:false});}target.x=Math.max(40,Math.min(960,target.x+(enemy?-1:1)*(blocked?12:24)));s.last_exchange=(enemy?'enemy_':'player_')+(blocked?'block':'hit');s.contacts.push({tick:s.tick,attacker:enemy?'enemy':'player',move:name,blocked,damage:blocked?0:damage});}
 if(a.hp===0||b.hp===0||s.tick>=p.max_ticks)s.status=a.hp>b.hp?'won':'lost';
}
async function render(state,h){
 if(cleanup)cleanup();document.body.dataset.mechanic='tin-duelist';
 const mode=state.control_condition?.interaction||'full';const w=state.world,p=w.parameters;
 const model={state,sim:initial(w),events:[],running:false,submitted:false,start:0,raf:0};window.tinDuelistModel=model;
 h.app.innerHTML=`<section class="tin-duelist"><header><div><small>THE CLOCKMAKER'S EXHIBITION / BOUT 01</small><h1>Tin Duelist</h1></div><span class="tin-badge">WIND-UP LEAGUE</span></header><div class="tin-score"><div><b>YOU · VERDIGRIS</b><meter id="tin-your-health" min="0" max="100" value="100"></meter></div><strong id="tin-time">90</strong><div><b>RIVAL · COPPER</b><meter id="tin-rival-health" min="0" max="100" value="100"></meter></div></div><canvas width="1000" height="330" aria-label="Side-view duel arena"></canvas><div class="tin-message" aria-live="polite">Win by knockout, or more health at the bell. A tie loses.</div><div class="tin-moves"><span>JAB <b>short · quick</b></span><span>LUNGE <b>long · committed</b></span><span>HAMMER <b>short · breaks guard</b></span></div><div class="tin-controls">${mode==='simplified'?'<button data-action="direction" data-value="-1">← WALK</button><button data-action="direction" data-value="0">STOP</button><button data-action="direction" data-value="1">WALK →</button><button data-action="guard" data-value="true">GUARD</button><button data-action="guard" data-value="false">LOWER</button><button data-action="jab">JAB</button><button data-action="lunge">LUNGE</button><button data-action="hammer">HAMMER</button>':'<span>HOLD <kbd>←</kbd> <kbd>→</kbd> WALK &nbsp; <kbd>Space</kbd> GUARD &nbsp; PRESS <kbd>J</kbd> JAB <kbd>K</kbd> LUNGE <kbd>L</kbd> HAMMER</span>'}</div><footer><button class="tin-start">WIND BOTH · START</button><div class="readout" data-status="idle">READY</div><button class="tin-submit" disabled>CERTIFY BOUT</button><button class="tin-retry">NEW BOUT</button></footer><div class="tin-verdict"></div></section>`;
 const root=h.app.querySelector('.tin-duelist'),canvas=root.querySelector('canvas'),ctx=canvas.getContext('2d');
 const colors=[['#66c9b5','#de9267'],['#74b8dd','#e6af65'],['#94c783','#d88486'],['#a3b8e8','#edbb78']][w.palette];
 function fighter(f,enemy){
  const sign=enemy?-1:1,c=colors[enemy?1:0];let phase=f.stun?'STAGGER':f.guard?'GUARD':'READY',progress=0,m=null;
  if(f.move){m=data(f.move,enemy,p);phase=f.age<m.start?'WINDING':f.age<m.start+m.active?'STRIKE':'RECOVERY';progress=f.age<m.start?f.age/m.start:(f.age-m.start-m.active)/m.recovery;}
  const x=f.x,y=245;ctx.save();ctx.translate(x,y);ctx.scale(sign,1);
  // The solid chassis is exactly the 48-wide hurtbox; the gold strike bar is the actual attack rectangle.
  ctx.fillStyle='#11191d';ctx.beginPath();ctx.ellipse(0,61,38,7,0,0,7);ctx.fill();
  ctx.strokeStyle='#65716e';ctx.lineWidth=8;ctx.beginPath();ctx.moveTo(-13,34);ctx.lineTo(-18,58);ctx.moveTo(13,34);ctx.lineTo(20,58);ctx.stroke();
  ctx.fillStyle=c;ctx.strokeStyle='#172d30';ctx.lineWidth=3;ctx.fillRect(-24,-52,48,92);ctx.strokeRect(-24,-52,48,92);
  ctx.fillStyle='#e9e0bb';ctx.fillRect(-20,-83,40,29);ctx.strokeRect(-20,-83,40,29);ctx.fillStyle='#183c3f';ctx.fillRect(3,-74,12,5);
  ctx.strokeStyle='#d7c080';ctx.lineWidth=4;ctx.beginPath();ctx.moveTo(-25,-17);ctx.lineTo(-40,-17);ctx.moveTo(-40,-28);ctx.lineTo(-40,-6);ctx.stroke();
  ctx.fillStyle='#263b3d';ctx.beginPath();ctx.arc(0,-7,13,0,7);ctx.fill();ctx.strokeStyle='#d3b775';ctx.beginPath();ctx.moveTo(0,-7);ctx.lineTo(9*Math.cos(f.age/4),-7+9*Math.sin(f.age/4));ctx.stroke();
  if(f.guard){ctx.fillStyle='#9acdd7';ctx.fillRect(24,-55,10,79);ctx.strokeStyle='#e6ffff';ctx.strokeRect(24,-55,10,79);}
  if(m&&phase==='STRIKE'){ctx.fillStyle=f.move==='hammer'?'#ffae7a':'#ffe3a0';ctx.fillRect(24,-27,m.reach,18);ctx.strokeStyle='#fff2c4';ctx.strokeRect(24,-27,m.reach,18);}
  else {ctx.save();ctx.translate(18,-24);ctx.rotate(phase==='WINDING'?(f.move==='hammer'?-1.8:-.65-progress*.7):phase==='RECOVERY'?.65:0);ctx.fillStyle='#b5c6bd';ctx.fillRect(0,-4,36,8);if(f.move==='hammer'){ctx.fillStyle='#da975e';ctx.fillRect(30,-15,20,29);}ctx.restore();}
  ctx.restore();ctx.textAlign='center';ctx.font='bold 13px monospace';ctx.fillStyle=phase==='WINDING'?'#ffcf81':phase==='RECOVERY'?'#9fa9ac':'#d8e4db';ctx.fillText((f.move?f.move.toUpperCase()+' / ':'')+phase,x,116);
  if(m){ctx.fillStyle='#344347';ctx.fillRect(x-38,124,76,4);ctx.fillStyle=phase==='WINDING'?'#ffc679':'#7ea6ac';ctx.fillRect(x-38,124,76*Math.max(0,Math.min(1,progress)),4);}
 }
 function draw(){
  const s=model.sim;ctx.clearRect(0,0,1000,330);const bg=ctx.createLinearGradient(0,0,0,330);bg.addColorStop(0,'#152e34');bg.addColorStop(1,'#071519');ctx.fillStyle=bg;ctx.fillRect(0,0,1000,330);
  for(let i=0;i<9;i++){const x=60+i*110;ctx.strokeStyle='#28434a';ctx.lineWidth=2;ctx.beginPath();ctx.arc(x,160,78,Math.PI,0);ctx.lineTo(x+78,295);ctx.moveTo(x-78,160);ctx.lineTo(x-78,295);ctx.stroke();}
  ctx.fillStyle='#a18c60';ctx.fillRect(0,306,1000,4);ctx.fillStyle='#213437';ctx.fillRect(0,310,1000,20);ctx.strokeStyle='#596557';for(let x=0;x<1000;x+=50){ctx.beginPath();ctx.moveTo(x,310);ctx.lineTo(x-12,330);ctx.stroke();}
  ctx.font='12px monospace';ctx.textAlign='center';ctx.fillStyle='#6f9093';ctx.fillText('CLOCKWORK EXHIBITION     ✦     NO. '+state.challenge_id.slice(0,6).toUpperCase(),500,35);
  fighter(s.player,false);fighter(s.enemy,true);
  root.querySelector('#tin-your-health').value=s.player.hp;root.querySelector('#tin-rival-health').value=s.enemy.hp;root.querySelector('#tin-time').textContent=Math.ceil((p.max_ticks-s.tick)*p.tick_ms/1000);
  if(s.contacts.length){const c=s.contacts.at(-1);if(s.tick-c.tick<16){ctx.font='bold 24px monospace';ctx.fillStyle=c.blocked?'#a4d9e4':'#ffe3a0';ctx.fillText(c.blocked?'BLOCK':'−'+c.damage,(s.player.x+s.enemy.x)/2,78);}}
  if(s.status!=='active'){root.querySelector('.tin-verdict').textContent=s.status==='won'?'BOUT WON':'BOUT LOST';root.querySelector('.tin-submit').disabled=false;h.setReadout(s.status==='won'?'BOUT WON':'BOUT LOST',s.status==='won'?'idle':'error');}
 }
 function tick(){if(!model.running||model.sim.status!=='active')return;const target=Math.floor((performance.now()-model.start)/p.tick_ms+1e-7);while(model.sim.tick<target&&model.sim.status==='active')step(model.sim,w);draw();}
 function input(action,value,source){tick();if(!model.running||model.submitted||model.sim.status!=='active')return;const token=h.beginAction?.('duel-input');model.events.push({seq:model.events.length+1,tick:model.sim.tick,action,value,input_source:source});if(action==='direction')model.sim.direction=value;else if(action==='guard')model.sim.guard=value;else attack(model.sim.player,action);draw();token?.settle();}
 root.querySelector('.tin-start').onclick=()=>{if(model.running)return;model.running=true;model.start=performance.now();root.querySelector('.tin-start').disabled=true;h.setReadout('DUEL','idle');};
 for(const b of root.querySelectorAll('[data-action]'))b.onclick=()=>input(b.dataset.action,b.dataset.value===undefined?null:JSON.parse(b.dataset.value),'button');
 const held=new Set();const keydown=e=>{if(mode!=='full'||!['ArrowLeft','ArrowRight','Space','KeyJ','KeyK','KeyL'].includes(e.code))return;e.preventDefault();if(e.repeat)return;held.add(e.code);if(e.code==='Space')input('guard',true,'keyboard');else if(e.code.startsWith('Arrow'))input('direction',(held.has('ArrowRight')?1:0)-(held.has('ArrowLeft')?1:0),'keyboard');else input({KeyJ:'jab',KeyK:'lunge',KeyL:'hammer'}[e.code],null,'keyboard');};
 const keyup=e=>{if(mode!=='full'||!held.has(e.code))return;e.preventDefault();held.delete(e.code);if(e.code==='Space')input('guard',false,'keyboard');else if(e.code.startsWith('Arrow'))input('direction',(held.has('ArrowRight')?1:0)-(held.has('ArrowLeft')?1:0),'keyboard');};
 const blur=()=>{if(mode==='full'){held.clear();input('direction',0,'keyboard');input('guard',false,'keyboard');}};
 document.addEventListener('keydown',keydown);document.addEventListener('keyup',keyup);window.addEventListener('blur',blur);
 async function submit(abandon=false){if(model.submitted)return;tick();model.submitted=true;const outgoing={mechanic_id:ID,task_id:state.task_id,challenge_id:state.challenge_id,interaction_mode:mode,events:clone(model.events),terminal_tick:model.sim.tick,final_state:clone(model.sim),completed:!abandon&&model.sim.status==='won'};try{const r=await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(outgoing)});const result=await r.json();if(result.passed){root.querySelector('.tin-verdict').textContent='PASS';h.setReadout('PASS','passed');}else if(result.state){await render(result.state,h);h.setReadout('FAIL · FRESH BOUT READY','error');}else{model.submitted=false;h.setReadout('FAIL','error');}}catch(e){model.submitted=false;h.setReadout('SUBMISSION FAILED · RETRY','error');}}
 root.querySelector('.tin-submit').onclick=()=>submit();root.querySelector('.tin-retry').onclick=()=>submit(true);
 const frame=()=>{tick();model.raf=requestAnimationFrame(frame);};draw();model.raf=requestAnimationFrame(frame);
 cleanup=()=>{cancelAnimationFrame(model.raf);document.removeEventListener('keydown',keydown);document.removeEventListener('keyup',keyup);window.removeEventListener('blur',blur);};
}
window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};window.WeirdCaptchaMechanics[ID]={rootSelector:'.tin-duelist',render};
})();
