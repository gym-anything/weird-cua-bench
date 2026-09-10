(() => {
'use strict';
const D={UP:[0,-1],RIGHT:[1,0],DOWN:[0,1],LEFT:[-1,0],WAIT:[0,0]}, glyph={UP:'↑',RIGHT:'→',DOWN:'↓',LEFT:'←',WAIT:'·'};
let timer, handler;
const equal=(a,b)=>a[0]===b[0]&&a[1]===b[1];
function render(state,h){
 document.body.dataset.mechanic="clockbeat_catacomb";
 clearInterval(timer);if(handler)window.removeEventListener('keydown',handler);
 const b=state.board, mode=state.control_condition?.interaction||'full';
 const s={player:[...b.start],hp:b.health,enemies:structuredClone(b.enemies),beat:0,used:false,won:false};
 let start=null,elapsed=0,events=[],submitted=false,message='Wind the clock when ready.';
 const ph=e=>(s.beat+e.offset)%({crawler:1,hopper:2,lancer:3}[e.kind]);
 const solid=p=>b.walls.some(q=>equal(p,q));
 function act(key){
  if(s.won||s.hp<=0||s.used)return 'unavailable';s.used=true;
  if(key==='WAIT')return 'wait';
  const [dx,dy]=D[key],p=[s.player[0]+dx,s.player[1]+dy];if(solid(p))return 'wall';
  const e=s.enemies.find(e=>e.hp>0&&equal(e.pos,p));
  if(e){if(e.kind==='hopper'&&ph(e)===1)return 'shield';e.hp--;return e.hp===0?'defeated':'hit';}
  s.player=p;s.won=equal(p,b.exit)&&s.enemies.every(e=>e.hp===0);return s.won?'escaped':'move';
 }
 function step(){
  if(s.won||s.hp<=0)return;
  for(const e of s.enemies){
   if(e.hp<=0)continue;const phase=ph(e);
   if(e.kind==='hopper'&&phase===0)continue;if(e.kind==='lancer'&&phase!==1)continue;
   const [x,y]=e.pos,[px,py]=s.player,dist=Math.abs(x-px)+Math.abs(y-py);
   if(e.kind==='lancer'){if(dist===1)s.hp--;continue;}
   const choices=Object.values(D).map((d,i)=>({d,i,dist:Math.abs(x+d[0]-px)+Math.abs(y+d[1]-py)})).sort((a,b)=>a.dist-b.dist||a.i-b.i);
   for(const {d,i,dist:nd} of choices){if(i===4||nd>=dist)continue;const p=[x+d[0],y+d[1]];
    if(solid(p)||s.enemies.some(o=>o!==e&&o.hp>0&&equal(o.pos,p)))continue;
    if(equal(p,s.player))s.hp--;else e.pos=p;break;
   }
  }s.beat++;s.used=false;
 }
 function sync(){
  if(start===null||s.won||s.hp<=0||submitted)return;
  elapsed=Math.min(b.max_beats*b.beat_ms,Math.floor(performance.now()-start));
  while(s.beat<Math.floor(elapsed/b.beat_ms)&&s.hp>0&&!s.won)step();
  if(s.beat>=b.max_beats)message='CLOCK EXHAUSTED · Submit to try a fresh catacomb.';
 }
 h.app.innerHTML=`<section class="cc" tabindex="0"><header><div><small>THE UNDERGROUND HOROLOGICAL SOCIETY</small><h1>Clockbeat Catacomb</h1></div><div class="cc-health"></div></header><main><div class="cc-chamber"><div class="cc-board" style="--n:${b.size}"></div><div class="cc-verdict"></div></div><aside><small>SHARED BEAT</small><div class="cc-pulse"><i></i></div><h2 class="cc-beat">CLOCK AT REST</h2><p class="cc-window">One move or attack while the bar is gold.</p><div class="cc-roster"></div><p class="cc-rule">Move into a sentry to attack. At the end of every beat, sentries act in numbered order. Chasers favor ↑ → ↓ ← on ties; blocked paths do not detour. Clear every sentry, then enter the stair.</p>${mode==='full'?'<div class="cc-keys">← ↑ ↓ →<small>ARROWS / WASD · SPACE TO WAIT</small></div>':`<div class="cc-buttons">${Object.keys(D).map(k=>`<button data-cc-key="${k}" aria-label="${k}">${glyph[k]}</button>`).join('')}</div>`}</aside></main><footer><button class="cc-start">WIND THE CLOCK</button><div class="cc-message"></div><button class="cc-submit">SUBMIT EXPEDITION</button></footer><div class="readout" data-status="idle"></div></section>`;
 const root=h.app.querySelector('.cc'),board=root.querySelector('.cc-board');
 function draw(){
  const active=start!==null&&!s.won&&s.hp>0&&s.beat<b.max_beats;
  root.querySelector('.cc-health').textContent='LANTERN '+ '♥'.repeat(Math.max(0,s.hp))+'♡'.repeat(Math.max(0,b.health-s.hp));
  root.querySelector('.cc-beat').textContent=start===null?'CLOCK AT REST':`BEAT ${s.beat+1} · ${s.used?'PLAYED':elapsed%b.beat_ms<b.open_ms?'ACT NOW':'LISTEN'}`;
  const pulse=root.querySelector('.cc-pulse');pulse.style.setProperty('--progress',`${100*(elapsed%b.beat_ms)/b.beat_ms}%`);pulse.classList.toggle('closed',elapsed%b.beat_ms>=b.open_ms);
  root.querySelector('.cc-message').textContent=message;
  root.querySelector('.cc-roster').innerHTML=s.enemies.map(e=>`<div class="cc-entry ${e.kind}"><b>${e.id} · ${{crawler:'Brass Mite',hopper:'Vault Beetle',lancer:'Chime Thorn'}[e.kind]}</b><span>${e.hp<=0?'DISMANTLED':e.kind==='crawler'?'CHASE → CHASE':e.kind==='hopper'?(ph(e)===0?'REST / OPEN → SHIELD + CHASE':'SHIELD + CHASE → REST / OPEN'):['PREPARE → STRIKE','STRIKE → REST','REST → PREPARE'][ph(e)]}</span><small>${e.kind==='lancer'?'Strikes four adjacent tiles; stays rooted.':e.kind==='hopper'?'Armored during chase. Attack while resting.':'Chases one tile; contact costs one heart.'}</small></div>`).join('');
  let cells='';for(let y=0;y<b.size;y++)for(let x=0;x<b.size;x++){
   const p=[x,y],wall=solid(p),e=s.enemies.find(e=>e.hp>0&&equal(e.pos,p)),player=equal(s.player,p),exit=equal(b.exit,p);
   const danger=s.enemies.some(e=>e.hp>0&&e.kind==='lancer'&&ph(e)===1&&Math.abs(x-e.pos[0])+Math.abs(y-e.pos[1])===1);
   cells+=`<div class="cc-tile ${wall?'wall':''} ${danger&&!wall?'danger':''}">${exit?`<span class="cc-stair ${s.enemies.every(e=>e.hp===0)?'unlocked':''}">≋</span>`:''}${e?`<span class="cc-enemy ${e.kind} ${e.kind==='hopper'&&ph(e)===1?'shield':''}"><b>${e.id}</b><i>${'•'.repeat(e.hp)}</i></span>`:''}${player?'<span class="cc-player"><i></i></span>':''}</div>`;
  }board.innerHTML=cells;
  root.querySelector('.cc-verdict').textContent=s.won?'STAIR OPEN · ESCAPED':s.hp<=0?'LANTERN OUT · FAILED':'';
  root.querySelector('.cc-verdict').classList.toggle('visible',s.won||s.hp<=0);
  root.dataset.beat=String(s.beat);root.dataset.used=String(s.used);root.dataset.ms=String(elapsed);root.dataset.won=String(s.won);
 }
 function input(key,source){
  sync();if(start===null||submitted||s.won||s.hp<=0||s.beat>=b.max_beats)return;
  const outcome=elapsed%b.beat_ms>=b.open_ms?'offbeat':act(key);
  events.push({sequence:events.length+1,ms:elapsed,key,input_source:source,outcome});
  message={offbeat:'OFF BEAT · No move. Sentries still advance.',unavailable:'BEAT ALREADY PLAYED · Wait for the next gold bar.',shield:'ARMORED · Attack blocked.',wall:'WALL · Beat spent.',defeated:'SENTRY DISMANTLED',hit:'HIT · Sentry damaged.',move:'STEP ACCEPTED',wait:'WAIT ACCEPTED',escaped:'ESCAPED · Submit expedition.'}[outcome];draw();
 }
 root.querySelector('.cc-start').onclick=()=>{if(start!==null)return;h.setReadout('', 'idle');start=performance.now();message='The clock is running.';root.querySelector('.cc-start').disabled=true;draw();};
 root.querySelectorAll('[data-cc-key]').forEach(el=>el.onclick=()=>input(el.dataset.ccKey,'direction_buttons'));
 handler=e=>{if(mode!=='full'||e.repeat)return;const key={ArrowUp:'UP',ArrowRight:'RIGHT',ArrowDown:'DOWN',ArrowLeft:'LEFT',w:'UP',d:'RIGHT',s:'DOWN',a:'LEFT',' ':'WAIT'}[e.key];if(key){e.preventDefault();input(key,'keyboard');}};window.addEventListener('keydown',handler);
 root.querySelector('.cc-submit').onclick=async()=>{
  if(submitted)return;sync();submitted=true;
  const payload={mechanic_id:state.mechanic_id,task_id:state.task_id,challenge_id:state.challenge_id,actions:events,final_ms:elapsed,final_state:structuredClone(s)};
  try{const response=await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const out=await response.json();
   if(out.passed){root.querySelector('.cc-verdict').textContent='PASS · EXPEDITION VERIFIED';root.querySelector('.cc-verdict').classList.add('visible');h.setReadout('PASS','passed');clearInterval(timer);}
   else if(out.state){await h.render(out.state);h.setReadout('FAIL · Fresh catacomb ready','error');}
   else{submitted=false;message='Submission unavailable. Try again.';draw();}
  }catch(e){submitted=false;message='Submission unavailable. Try again.';draw();}
 };
 timer=setInterval(()=>{sync();draw();},50);draw();root.focus();
}
window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};window.WeirdCaptchaMechanics.clockbeat_catacomb={rootSelector:'.cc',render};
})();
