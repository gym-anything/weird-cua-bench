(() => {
'use strict';
let m,h,timer,keyHandler;
const D={up:[0,-1],right:[1,0],down:[0,1],left:[-1,0]};
const clone=x=>JSON.parse(JSON.stringify(x));
const eq=(a,b)=>a[0]===b[0]&&a[1]===b[1];
function terms(b){return [b.ask+Number(m.w.changing_terms&&b.inventory[0]>=2),b.give];}
function tick(){
 const s=m.s,w=m.w;if(!m.running||s.failed||s.delivered)return;
 s.tick++;s.hunger--;
 if(s.hunger<=0||s.tick>=w.limit_ticks){s.failed=true;s.message=s.hunger<=0?'FAIL · hungry courier':'FAIL · market closed';paint();return;}
 for(const b of s.bots){
  b.hunger--;b.progress++;
  if(b.progress>=b.harvest_ticks){b.progress=0;if(b.inventory[0]+b.inventory[1]<b.capacity)b.inventory[1]++;}
  if(b.hunger<=0){const food=b.inventory[0]?0:1;if(b.inventory[food]){b.inventory[food]--;b.hunger=food===0?b.meal_ticks:Math.floor(b.meal_ticks/2);}}
 }
 const crop=w.trees.find(t=>eq(t.pos,s.pos));
 if(crop){s.harvest++;const duration=crop.fruit===0?w.apple_ticks:w.banana_ticks;
  if(s.harvest>=duration){s.harvest=0;const amount=Math.min(crop.fruit===0?2:1,w.capacity-s.inventory[0]-s.inventory[1]);s.inventory[crop.fruit]+=amount;s.message=amount?'Harvest in basket':'Basket full · eat or trade to make room';}
 }else s.harvest=0;
 if(s.posted){for(let i=0;i<s.bots.length;i++){
  const b=s.bots[i],[give,take]=s.offer;
  if((s.pos[0]-b.pos[0])**2+(s.pos[1]-b.pos[1])**2>w.radius**2||!eq(terms(b),s.offer))continue;
  if(s.inventory[0]<give||b.inventory[1]<take||s.inventory[0]+s.inventory[1]-give+take>w.capacity||b.inventory[0]+b.inventory[1]+give-take>b.capacity)continue;
  s.inventory[0]-=give;s.inventory[1]+=take;b.inventory[0]+=give;b.inventory[1]-=take;
  s.trades.push({tick:s.tick,farmer:i,give,take});s.posted=false;s.message='TRADE SETTLED · fruit changed hands';break;
 }}paint();
}
function act(kind,value=null){
 const s=m.s,w=m.w;if(!m.running||m.submitting||s.failed||s.delivered)return;
 const source=kind in D?(m.mode==='full'?'keyboard':'direction_buttons'):'offer_buttons';
 m.events.push({tick:s.tick,kind,value,source});
 if(kind in D){const d=D[kind],p=[s.pos[0]+d[0],s.pos[1]+d[1]];
  if(p[0]>=0&&p[0]<w.width&&p[1]>=0&&p[1]<w.height&&!w.walls.some(x=>eq(x,p))){
   s.pos=p;s.harvest=0;const water=w.water.some(x=>eq(x,p));if(water)s.hunger-=w.water_cost;
   s.message=water?'Wading costs food':'Walking';if(s.hunger<=0){s.failed=true;s.message='FAIL · hungry courier';}
  }else s.message='Fence · choose another path';
 }else if(kind==='give'||kind==='take'){
  const i=kind==='give'?0:1;s.offer[i]=Math.max(1,Math.min(4,s.offer[i]+value));s.posted=false;s.message='Draft offer · post when ready';
 }else if(kind==='post'){s.posted=true;s.message='OFFER POSTED · waiting for reciprocal stock-backed terms';}
 else if(kind==='cancel'){s.posted=false;s.message='Offer withdrawn';}
 else if(kind==='eat'){
  if(s.inventory[value]){s.inventory[value]--;s.hunger=Math.min(w.max_hunger,s.hunger+w.food[value]);s.message='Meal eaten · basket changed';}
  else s.message='No fruit of that kind to eat';
 }else if(kind==='deliver'){
  if(eq(s.pos,w.stall)&&s.inventory.every((a,i)=>a>=w.demand[i])){s.delivered=true;s.message='PASS · DELIVERY RECEIVED';}
  else s.message='Delivery needs the full basket at the striped stall';
 }paint();
}
async function submit(){
 if(m.submitting)return;
 if(!m.s.failed)act('deliver');m.submitting=true;clearInterval(timer);paint();
 const payload={mechanic_id:m.state.mechanic_id,task_id:m.state.task_id,challenge_id:m.state.challenge_id,events:clone(m.events),end_tick:m.s.tick,final:clone(m.s)};
 try{const r=await(await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)})).json();
  if(r.passed){m.running=false;document.querySelector('#ox-verdict').textContent='PASS · DELIVERY RECEIVED';h.setReadout('PASS','passed');}
  else if(r.state){await h.render(r.state);document.querySelector('#ox-verdict').textContent='FAIL · fresh orchard ready';h.setReadout('FAIL · press Enter orchard to retry','error');}
  else {m.submitting=false;h.setReadout('Grade unavailable · retry delivery','error');timer=setInterval(tick,m.w.tick_ms);}
 }catch(e){m.submitting=false;h.setReadout('Connection interrupted · retry delivery','error');timer=setInterval(tick,m.w.tick_ms);}
}
function fruit(c,x,y,type,r=9){
 c.save();c.translate(x,y);c.fillStyle=type===0?'#df5949':'#f5cb59';c.strokeStyle=type===0?'#983b35':'#ab802d';c.lineWidth=2;
 if(type===0){c.beginPath();c.arc(-r*.3,0,r*.7,0,Math.PI*2);c.arc(r*.3,0,r*.7,0,Math.PI*2);c.fill();c.stroke();c.strokeStyle='#416442';c.beginPath();c.moveTo(0,-r*.6);c.lineTo(3,-r*1.25);c.stroke();}
 else{c.beginPath();c.arc(0,-r*.3,r,-.1,Math.PI);c.quadraticCurveTo(-r*.1,r*1.7,r,-r*.4);c.fill();c.stroke();}c.restore();
}
function draw(){
 const c=document.querySelector('#ox-field').getContext('2d'),w=m.w,s=m.s;
 const X=x=>35+x*68,Y=y=>46+y*61;
 c.clearRect(0,0,700,460);c.fillStyle='#c8d4a0';c.fillRect(0,0,700,460);
 for(let y=0;y<7;y++)for(let x=0;x<10;x++){
  c.fillStyle=(x+y)%2?'#c1ce96':'#c8d4a0';c.fillRect(x*68+1,y*61+16,68,61);
  c.fillStyle='#97b27b';c.fillRect(x*68+17,y*61+33,3,4);
 }
 for(const p of w.water){const x=X(p[0]),y=Y(p[1]);c.fillStyle='#69a8ae';c.fillRect(x-34,y-30,68,61);c.strokeStyle='#b4d8cf';c.beginPath();c.moveTo(x-22,y+3);c.quadraticCurveTo(x,y-8,x+23,y+3);c.stroke();}
 if(w.water.length){const p=w.water[0];let x=X(p[0]);c.fillStyle='#b48759';c.fillRect(x-34,Y(w.bridge)-27,68,54);c.strokeStyle='#785737';for(let j=-25;j<27;j+=9){c.beginPath();c.moveTo(x-34,Y(w.bridge)+j);c.lineTo(x+34,Y(w.bridge)+j);c.stroke();}}
 for(const t of w.trees){const x=X(t.pos[0]),y=Y(t.pos[1]);c.fillStyle='#795437';c.fillRect(x-6,y-21,12,32);c.fillStyle=t.fruit===0?'#4b8058':'#729650';c.beginPath();c.ellipse(x,y-22,28,25,0,0,7);c.fill();fruit(c,x-12,y-23,t.fruit);fruit(c,x+12,y-15,t.fruit);c.strokeStyle='#fff3bc';c.lineWidth=2;c.strokeRect(x-30,y-29,60,58);}
 const sx=X(w.stall[0]),sy=Y(w.stall[1]);c.fillStyle='#775846';c.fillRect(sx-27,sy-10,54,27);c.fillStyle='#f3e6b8';c.fillRect(sx-31,sy-32,62,22);c.fillStyle='#cd6556';for(let i=0;i<5;i++)c.fillRect(sx-31+i*13,sy-32,6,22);c.fillStyle='#fff8dd';c.font='bold 10px sans-serif';c.textAlign='center';c.fillText('DELIVERY',sx,sy+8);
 for(let i=0;i<s.bots.length;i++){
  const b=s.bots[i],x=X(b.pos[0]),y=Y(b.pos[1]);
  c.strokeStyle='#faf5c2';c.lineWidth=2;c.setLineDash([4,5]);c.beginPath();c.ellipse(x,y,68*w.radius,61*w.radius,0,0,7);c.stroke();c.setLineDash([]);
  c.fillStyle=['#a56986','#577992','#b17c4d'][i];c.beginPath();c.ellipse(x,y+6,16,20,0,0,7);c.fill();c.fillStyle='#f1ce94';c.beginPath();c.arc(x,y-11,12,0,7);c.fill();c.fillStyle='#eed19a';c.fillRect(x-18,y-25,36,8);
  c.fillStyle='#304c41';c.font='bold 13px sans-serif';c.fillText(b.name,x,y+39);
  const tr=terms(b);c.fillStyle='#fff9dc';c.fillRect(x-43,y-67,86,29);c.fillStyle='#304c41';c.font='bold 15px sans-serif';c.fillText(`${tr[1]}    → ${tr[0]}`,x-3,y-47);fruit(c,x-16,y-53,1,6);fruit(c,x+32,y-53,0,6);
 }
 const px=X(s.pos[0]),py=Y(s.pos[1]);c.fillStyle='#2a5447';c.beginPath();c.ellipse(px,py+11,14,18,0,0,7);c.fill();c.fillStyle='#ffe2b6';c.beginPath();c.arc(px,py-8,11,0,7);c.fill();c.fillStyle='#f9f4cf';c.fillRect(px-15,py-20,30,7);c.fillStyle='#fff';c.font='bold 11px sans-serif';c.fillText('YOU',px,py+37);
 const crop=w.trees.find(t=>eq(t.pos,s.pos));if(crop){const q=s.harvest/(crop.fruit===0?w.apple_ticks:w.banana_ticks);c.fillStyle='#324c40';c.fillRect(px-27,py+22,54,5);c.fillStyle='#f4d978';c.fillRect(px-27,py+22,54*q,5);}
 c.strokeStyle='#69835f';c.lineWidth=4;c.strokeRect(2,17,678,427);
}
function pictograms(){
 const root=document.querySelector('.ox-root'),walk=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),nodes=[];
 while(walk.nextNode())if(/[🍎🍌]/u.test(walk.currentNode.textContent))nodes.push(walk.currentNode);
 for(const n of nodes){const f=document.createDocumentFragment();for(const part of n.textContent.split(/(🍎|🍌)/u)){
  if(part==='🍎'||part==='🍌'){const el=document.createElement('span');el.className='ox-fruit';el.setAttribute('role','img');el.setAttribute('aria-label',part==='🍎'?'apples':'bananas');
   el.innerHTML=part==='🍎'?'<svg viewBox="0 0 24 24"><path fill="#d95948" stroke="#973d34" d="M12 6C2 1 0 13 7 21Q12 19 17 21C24 13 22 1 12 6Z"/><path fill="none" stroke="#487348" stroke-width="2" d="M12 7Q11 1 17 2"/></svg>':'<svg viewBox="0 0 24 24"><path fill="#f2c84e" stroke="#9a792b" stroke-width="1.4" d="M3 3C2 20 19 24 22 6C17 16 8 15 3 3Z"/></svg>';f.append(el);
  }else f.append(document.createTextNode(part));
 }n.replaceWith(f);}
}
function paint(){
 if(!m)return;const s=m.s,w=m.w;draw();
 document.querySelector('#ox-closing').textContent=`Market closes in ${Math.ceil((w.limit_ticks-s.tick)/10)}s`;
 document.querySelector('#ox-stock').textContent=`🍎 ${s.inventory[0]}   🍌 ${s.inventory[1]}   / ${w.capacity}`;
 document.querySelector('#ox-hunger').style.width=`${Math.max(0,s.hunger)/w.max_hunger*100}%`;
 document.querySelector('#ox-food-time').textContent=`${Math.max(0,s.hunger/10).toFixed(1)}s food reserve`;
 document.querySelector('#ox-give').textContent=s.offer[0];document.querySelector('#ox-take').textContent=s.offer[1];
 document.querySelector('#ox-post').textContent=s.posted?'OFFER POSTED':'POST OFFER';
 document.querySelector('#ox-message').textContent=s.message;
 document.querySelector('#ox-farmers').innerHTML=s.bots.map((b,i)=>{const tr=terms(b);return `<article><strong>${b.name}</strong><span>Gives 🍌 ${tr[1]} · wants 🍎 ${tr[0]}</span><span>Basket 🍎 ${b.inventory[0]}  🍌 ${b.inventory[1]} / ${b.capacity}</span><div class="ox-mini"><i style="width:${Math.max(0,b.hunger)/b.meal_ticks*100}%"></i></div><small>Meal ${Math.max(0,b.hunger/10).toFixed(1)}s · harvest ${((b.harvest_ticks-b.progress)/10).toFixed(1)}s</small></article>`;}).join('');
 document.querySelector('#ox-trades').textContent=s.trades.length?`${s.trades.length} settled · last: gave 🍎 ${s.trades.at(-1).give}, received 🍌 ${s.trades.at(-1).take}`:'No trades settled';
 if(s.failed)document.querySelector('#ox-verdict').textContent=s.message;
 pictograms();
}
async function render(state,helpers){
 clearInterval(timer);if(keyHandler)window.removeEventListener('keydown',keyHandler);h=helpers;
 const w=state.world;m={state,w,mode:state.control_condition?.interaction||'full',events:[],running:false,submitting:false,
 s:{tick:0,pos:clone(w.start),inventory:[0,0],hunger:w.initial_hunger,harvest:0,bots:clone(w.bots),offer:[1,1],posted:false,trades:[],delivered:false,failed:false,message:'Harvest apples, barter, and bring the basket home.'}};
 window.orchardExchangeModel=m;document.body.dataset.mechanic='orchard-exchange';
 h.app.innerHTML=`<section class="ox-root"><header><div><small>THE COMMONS / A LITTLE MARKET WITH APPETITES</small><h1>Orchard Exchange</h1></div><div class="ox-demand">DELIVERY BASKET <b>🍎 ${w.demand[0]} &nbsp; 🍌 ${w.demand[1]}</b><small id="ox-closing"></small></div></header>
 <main><div class="ox-map"><canvas id="ox-field" width="700" height="460" aria-label="Orchard, trees, farmers and delivery stall"></canvas><div class="ox-mapnote">Stand on a tree to harvest · 🍎 2 / 1.8s · 🍌 1 / 90s${w.water.length?` · water costs ${w.water_cost/10}s food per step`:''}</div><div id="ox-verdict"></div><div class="ox-start"><h2>A basket for the village</h2><p>You grow apples quickly. Farmers grow bananas and prefer eating apples.</p><p>Match their sign, stand inside the dashed radius, and post your offer. Both baskets must pay.</p><button id="ox-start">Enter orchard</button></div></div>
 <aside><label>YOUR BASKET</label><strong id="ox-stock"></strong><div class="ox-meter"><i id="ox-hunger"></i></div><small id="ox-food-time"></small><div class="ox-eat"><button data-eat="0">Eat 🍎 +17s</button><button data-eat="1">Eat 🍌 +34s</button></div><div id="ox-farmers"></div></aside></main>
 <section class="ox-desk"><div class="ox-move">${m.mode==='simplified'?Object.keys(D).map(k=>`<button data-dir="${k}">${{up:'↑',right:'→',down:'↓',left:'←'}[k]}</button>`).join(''):'<b>WASD / ARROWS</b><span>One press · one step</span>'}</div><div class="ox-offer"><label>YOU GIVE 🍎</label><div><button data-edit="give" data-value="-1">−</button><b id="ox-give"></b><button data-edit="give" data-value="1">+</button></div></div><span class="ox-arrow">⇄</span><div class="ox-offer"><label>YOU RECEIVE 🍌</label><div><button data-edit="take" data-value="-1">−</button><b id="ox-take"></b><button data-edit="take" data-value="1">+</button></div></div><div class="ox-post"><button id="ox-post">POST OFFER</button><button id="ox-cancel">Withdraw</button></div><button id="ox-deliver">Deliver / retry</button></section>
 <footer><div><strong id="ox-message"></strong><small id="ox-trades"></small></div><div class="readout" data-status="idle">MARKET READY</div></footer></section>`;
 document.querySelector('#ox-start').onclick=()=>{m.running=true;document.querySelector('.ox-start').remove();document.querySelector('#ox-verdict').textContent='';h.setReadout('MARKET OPEN','idle');timer=setInterval(tick,w.tick_ms);};
 document.querySelectorAll('[data-dir]').forEach(b=>b.onclick=()=>act(b.dataset.dir));
 document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>act(b.dataset.edit,Number(b.dataset.value)));
 document.querySelectorAll('[data-eat]').forEach(b=>b.onclick=()=>act('eat',Number(b.dataset.eat)));
 document.querySelector('#ox-post').onclick=()=>act('post');document.querySelector('#ox-cancel').onclick=()=>act('cancel');document.querySelector('#ox-deliver').onclick=submit;
 keyHandler=e=>{if(e.repeat||m.mode!=='full')return;const k={w:'up',a:'left',s:'down',d:'right',ArrowUp:'up',ArrowLeft:'left',ArrowDown:'down',ArrowRight:'right'}[e.key];if(k){e.preventDefault();act(k);}};window.addEventListener('keydown',keyHandler);paint();
}
window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
window.WeirdCaptchaMechanics.orchard_exchange={rootSelector:'.ox-root',render};
})();
