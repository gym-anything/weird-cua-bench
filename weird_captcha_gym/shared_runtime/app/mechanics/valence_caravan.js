(() => {
'use strict';
let cleanup=()=>{};
const clone=x=>JSON.parse(JSON.stringify(x));
const delta={N:[0,-1],E:[1,0],S:[0,1],W:[-1,0]};
const keymap={ArrowUp:'N',ArrowRight:'E',ArrowDown:'S',ArrowLeft:'W',w:'N',d:'E',s:'S',a:'W',e:'CW',q:'CCW'};
async function render(publicState,helpers) {
 cleanup();document.body.dataset.mechanic='valence-caravan';
 const world=publicState.world, mode=publicState.control_condition?.interaction||'full';
 let state={positions:clone(world.positions),bonds:[]},history=[],actions=[],busy=false,passed=false;
 const floor=new Set(world.floor.map(p=>p.join(',')));
 const group=()=>{let g=new Set([0]);for(let n=0;n<=state.bonds.length;n++)for(const [a,b] of state.bonds)if(g.has(a)||g.has(b)){g.add(a);g.add(b);}return g;};
 helpers.app.innerHTML=`<section class="valence-caravan" tabindex="0"><header><div><small>REACTION CHAMBER / FIELD STATION 08</small><h1>Valence Caravan</h1></div><span class="vc-badge">ASSEMBLE<br>ONE BODY</span></header><main><div class="vc-map"><svg viewBox="0 0 ${world.size*70} ${world.size*70}" aria-label="Reaction chamber"></svg></div><aside><h2>Assemble one body.</h2><p>Complete the chamber.</p><div class="vc-controls">${mode==='full'?'<p><kbd>↑</kbd> <kbd>←</kbd> <kbd>↓</kbd> <kbd>→</kbd><br><kbd>Q</kbd> <kbd>E</kbd></p>':Object.entries({N:'↑',W:'←',S:'↓',E:'→',CCW:'↶',CW:'↷'}).map(([cmd,label])=>`<button data-command="${cmd}" aria-label="${cmd}">${label}</button>`).join('')}</div><div class="vc-recovery"><button data-command="undo">Undo</button><button data-command="reset">Reset</button></div><button class="vc-submit">Check assembly</button></aside></main><footer><div class="readout" data-status="idle">READY</div></footer><div class="vc-verdict" hidden><b></b><span></span><button>Continue</button></div></section>`;
 const root=helpers.app.querySelector('.valence-caravan'),svg=root.querySelector('svg');
 function draw(){
  const connected=group(),degrees=world.valences.map(()=>0);for(const [a,b] of state.bonds){degrees[a]++;degrees[b]++;}
  let out='';for(let y=0;y<world.size;y++)for(let x=0;x<world.size;x++){const open=floor.has(`${x},${y}`);out+=`<rect x="${x*70+2}" y="${y*70+2}" width="66" height="66" rx="9" fill="${open?'#19373e':'#091c24'}" stroke="${open?'#2a4e53':'#34505a'}"/>`;if(!open)out+=`<path d="M${x*70+20} ${y*70+20}l30 30m0 -30l-30 30" stroke="#34505a" stroke-width="3"/>`;}
  for(const [x,y] of world.turntables)out+=`<circle cx="${x*70+35}" cy="${y*70+35}" r="29" fill="none" stroke="#e8b86d" stroke-width="3" stroke-dasharray="8 5"/><text x="${x*70+35}" y="${y*70+43}" text-anchor="middle" fill="#e8b86d" font-size="28">↻</text>`;
  for(const [a,b] of state.bonds)out+=`<line x1="${state.positions[a][0]*70+35}" y1="${state.positions[a][1]*70+35}" x2="${state.positions[b][0]*70+35}" y2="${state.positions[b][1]*70+35}" stroke="#faf3d8" stroke-width="9"/>`;
  const colors=['#f4bd69','#77d2c4','#dba3dd','#f18e79','#a8c5ef','#c4d68a'];
  state.positions.forEach(([x,y],i)=>{let cx=x*70+35,cy=y*70+35;out+=`<circle cx="${cx}" cy="${cy}" r="25" fill="${colors[i]}" stroke="${connected.has(i)?'#fff4d5':'#36636a'}" stroke-width="${i===0?4:2}"/><text x="${cx}" y="${cy+7}" text-anchor="middle" font-size="21" font-weight="800" fill="#15303a">${String.fromCharCode(65+i)}</text>`;for(let n=0;n<world.valences[i];n++){let angle=(n*2*Math.PI/world.valences[i])-Math.PI/2;out+=`<circle cx="${cx+20*Math.cos(angle)}" cy="${cy+20*Math.sin(angle)}" r="4.5" fill="${n<degrees[i]?'#24444c':'#fff9ea'}" stroke="#24444c" stroke-width="1.5"/>`;}});
  svg.innerHTML=out;
  const done=connected.size===world.valences.length&&degrees.every((n,i)=>n===world.valences[i]);
  return done;
 }
 function act(command,source){
  if(busy||passed||!root.querySelector('.vc-verdict').hidden)return;
  let old=clone(state);
  if(command==='undo'){if(history.length)state=history.pop();}
  else if(command==='reset'){state={positions:clone(world.positions),bonds:[]};history=[];}
  else {
   if(source!==(mode==='full'?'keyboard':'buttons'))return;
   history.push(old);let g=group(),p=clone(state.positions),valid=true;
   if(delta[command]){const [dx,dy]=delta[command];for(const i of g){p[i][0]+=dx;p[i][1]+=dy;}}
   else if(world.turntables.some(v=>v[0]===p[0][0]&&v[1]===p[0][1])){const [px,py]=p[0],s=command==='CW'?1:-1;for(const i of g)p[i]=[px-s*(state.positions[i][1]-py),py+s*(state.positions[i][0]-px)];}
   else {valid=false;}
   if(p.some(v=>!floor.has(v.join(',')))||new Set(p.map(v=>v.join(','))).size!==p.length){valid=false;}
   if(valid){state.positions=p;const degrees=world.valences.map(()=>0);for(const [a,b] of state.bonds){degrees[a]++;degrees[b]++;}for(let a=0;a<p.length;a++)for(let b=a+1;b<p.length;b++){if(!g.has(a)&&!g.has(b))continue;if(!state.bonds.some(e=>e[0]===a&&e[1]===b)&&degrees[a]<world.valences[a]&&degrees[b]<world.valences[b]&&Math.abs(p[a][0]-p[b][0])+Math.abs(p[a][1]-p[b][1])===1){state.bonds.push([a,b]);degrees[a]++;degrees[b]++;}}state.bonds.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);}
  }
  actions.push({seq:actions.length+1,command,source,state:clone(state)});
  draw();helpers.setReadout('READY','idle');
 }
 root.querySelectorAll('[data-command]').forEach(b=>b.addEventListener('click',()=>act(b.dataset.command,['undo','reset'].includes(b.dataset.command)?'toolbar':'buttons')));
 const keydown=e=>{if(e.repeat||mode!=='full'||!keymap[e.key])return;e.preventDefault();act(keymap[e.key],'keyboard');};window.addEventListener('keydown',keydown);cleanup=()=>window.removeEventListener('keydown',keydown);
 root.querySelector('.vc-submit').addEventListener('click',async()=>{
  if(busy||passed||!root.querySelector('.vc-verdict').hidden)return;busy=true;
  try{const response=await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mechanic_id:publicState.mechanic_id,task_id:publicState.task_id,challenge_id:publicState.challenge_id,actions,final_state:state})});if(!response.ok)throw Error('request');const outcome=await response.json();
   if(outcome.passed){passed=true;helpers.setReadout('PASS','passed');const panel=root.querySelector('.vc-verdict');panel.hidden=false;panel.querySelector('b').textContent='PASS';panel.querySelector('span').textContent='';panel.querySelector('button').hidden=true;}
   else {if(outcome.state)await render(outcome.state,helpers);const panel=helpers.app.querySelector('.vc-verdict');panel.hidden=false;panel.querySelector('b').textContent='FAIL';panel.querySelector('span').textContent='';helpers.app.querySelector('.valence-caravan main').inert=true;panel.querySelector('button').focus();helpers.setReadout('FAIL','error');}
  }catch(e){busy=false;helpers.setReadout('Connection unavailable. Check again.','error');}
 });
 root.querySelector('.vc-verdict button').addEventListener('click',()=>{root.querySelector('.vc-verdict').hidden=true;root.querySelector('main').inert=false;helpers.setReadout('READY','idle');root.focus();});
 draw();root.focus();
}
window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
window.WeirdCaptchaMechanics.valence_caravan={rootSelector:'.valence-caravan',render};
})();
