(() => {
'use strict';
const R=[16,23,32,44,59,78,102],colors=['#64e4e6','#8593ff','#ee85c3','#ffb76b','#c9ee83','#fff1aa','#ffffff'];
const body=(t,x,y)=>({t,x,y,vx:0,vy:0});
function tick(bs,w){
 let merges=0;
 for(const b of bs){b.vy=(b.vy+.11)*.992;b.vx*=.992;b.x+=b.vx;b.y+=b.vy;}
 for(let it=0;it<6;it++){
  for(const b of bs){let r=R[b.t];if(b.x<r){b.x=r;b.vx=Math.abs(b.vx)*.15;}if(b.x>w.width-r){b.x=w.width-r;b.vx=-Math.abs(b.vx)*.15;}if(b.y>w.height-r){b.y=w.height-r;b.vy=-Math.abs(b.vy)*.1;b.vx*=.94;}}
  let merged=false;
  for(let i=0;i<bs.length&&!merged;i++)for(let j=i+1;j<bs.length;j++){
   const a=bs[i],b=bs[j],ra=R[a.t],rb=R[b.t],dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy);
   if(d>ra+rb)continue;
   if(a.t===b.t&&a.t<6){let c=body(a.t+1,(a.x+b.x)/2,(a.y+b.y)/2);c.vx=(a.vx+b.vx)/2;c.vy=(a.vy+b.vy)/2;bs.splice(j,1);bs.splice(i,1);bs.push(c);merges++;merged=true;break;}
   const nx=d>1e-9?dx/d:1,ny=d>1e-9?dy/d:0,ia=1/(2**a.t),ib=1/(2**b.t),total=ia+ib,overlap=ra+rb-d;
   a.x-=nx*overlap*ia/total;a.y-=ny*overlap*ia/total;b.x+=nx*overlap*ib/total;b.y+=ny*overlap*ib/total;
   const v=(b.vx-a.vx)*nx+(b.vy-a.vy)*ny;
   if(v<0){let impulse=-1.1*v/total;a.vx-=impulse*ia*nx;a.vy-=impulse*ia*ny;b.vx+=impulse*ib*nx;b.vy+=impulse*ib*ny;}
  }
 }
 return merges;
}
let oldTimer;
function render(s,h){
 document.body.dataset.mechanic='prismfall-kiln';
 clearInterval(oldTimer);
 const full=(s.control_condition?.interaction||'full')==='full';
 let bs=structuredClone(s.initial),events=[],active=false,terminal=false,aim=s.world.width/2,ticks=0,quiet=0,dropX=0;
 // Read-only rendering telemetry for scripted implementation checks, never a solution route.
 window.prismfallKilnModel={get bodies(){return structuredClone(bs);},get events(){return structuredClone(events);},get terminal(){return terminal;}};
 h.app.innerHTML=`<section class="prismfall"><header><div><small>THE GLASSWORKS</small><h1>Prismfall Kiln</h1></div></header><main><aside><small>MAKE THIS FORM</small><canvas id="kiln-goal" width="180" height="180"></canvas><h2 id="kiln-status">READY TO POUR</h2><div class="kiln-chain">${colors.slice(0,s.target+1).map((c,i)=>`<i style="background:${c}">${i+1}</i>`).join('<b>›</b>')}</div></aside><div class="kiln-vessel"><canvas id="kiln-canvas" width="420" height="490" aria-label="Glass kiln release rail"></canvas></div><aside><small>ONE PIECE AHEAD</small><canvas id="kiln-preview" width="180" height="130"></canvas>${full?'':`<label>RELEASE POSITION<input id="kiln-position" type="number" min="0" max="${s.world.width}" value="${s.world.width/2}" step="any"></label><button id="kiln-release">RELEASE ↓</button>`}<button id="kiln-certify">CERTIFY</button><button id="kiln-retry">NEW BATCH</button><div class="readout" data-status="idle">READY</div></aside></main></section>`;
 const canvas=document.getElementById('kiln-canvas'),ctx=canvas.getContext('2d');
 const scale=Math.min(370/s.world.width,420/s.world.height),ox=(420-s.world.width*scale)/2,oy=42;
 function orb(c,x,y,r,t){const g=c.createRadialGradient(x-r*.35,y-r*.4,1,x,y,r);g.addColorStop(0,'#fff');g.addColorStop(.18,colors[t]);g.addColorStop(1,colors[t]+'55');c.fillStyle=g;c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fill();c.strokeStyle=colors[t];c.lineWidth=2;c.stroke();c.fillStyle='#12263b';c.font=`bold ${Math.max(13,r*.5)}px sans-serif`;c.textAlign='center';c.textBaseline='middle';c.fillText(t+1,x,y);}
 const gc=document.getElementById('kiln-goal').getContext('2d');orb(gc,90,90,Math.min(76,R[s.target]),s.target);
 function draw(){
  ctx.clearRect(0,0,420,490);ctx.save();ctx.translate(ox,oy);ctx.scale(scale,scale);
  ctx.fillStyle='#132735';ctx.fillRect(0,0,s.world.width,s.world.height);ctx.strokeStyle='#96d1d6';ctx.lineWidth=3;ctx.strokeRect(0,0,s.world.width,s.world.height);
  ctx.setLineDash([7,5]);ctx.strokeStyle='#ff877f';ctx.beginPath();ctx.moveTo(0,s.world.overflow);ctx.lineTo(s.world.width,s.world.overflow);ctx.stroke();ctx.setLineDash([]);
  for(const b of bs)orb(ctx,b.x,b.y,R[b.t],b.t);
  if(!active&&!terminal){let t=s.offers[events.length];orb(ctx,aim,38,R[t],t);ctx.strokeStyle='#ffffff55';ctx.setLineDash([3,5]);ctx.beginPath();ctx.moveTo(aim,38+R[t]);ctx.lineTo(aim,s.world.height);ctx.stroke();}
  ctx.restore();
  const pc=document.getElementById('kiln-preview').getContext('2d');pc.clearRect(0,0,180,130);let next=s.offers[events.length+1];if(next!==undefined)orb(pc,90,65,R[next],next);
  for(const id of ['kiln-position','kiln-release']){const node=document.getElementById(id);if(node)node.disabled=active||terminal||(id==='kiln-release'&&!Number.isFinite(document.getElementById('kiln-position').valueAsNumber));}
  for(const id of ['kiln-certify','kiln-retry'])document.getElementById(id).disabled=active;
  canvas.dataset.active=String(active);canvas.dataset.terminal=String(terminal);canvas.dataset.drops=events.length;
 }
 function release(){if(active||terminal)return;const r=R[s.offers[events.length]];aim=Math.max(r,Math.min(s.world.width-r,aim));h.setReadout('SETTLING','pending');document.getElementById('kiln-status').textContent='GLASS IN MOTION';dropX=aim;bs.push(body(s.offers[events.length],aim,38));active=true;ticks=quiet=0;draw();}
 function setAim(x){if(!Number.isFinite(x)){draw();return;}let r=R[s.offers[events.length]];aim=Math.max(r,Math.min(s.world.width-r,Math.round(x*10)/10));draw();}
 canvas.addEventListener('pointermove',e=>{if(!full||active||terminal)return;let q=canvas.getBoundingClientRect();setAim(((e.clientX-q.left)*420/q.width-ox)/scale);});
 canvas.addEventListener('click',e=>{if(!full||active||terminal)return;let q=canvas.getBoundingClientRect();let y=(e.clientY-q.top)*490/q.height;if(y>oy+s.world.overflow*scale)return;setAim(((e.clientX-q.left)*420/q.width-ox)/scale);release();});
 if(!full){document.getElementById('kiln-position').addEventListener('input',e=>{if(!active&&!terminal)setAim(e.target.valueAsNumber);});document.getElementById('kiln-release').onclick=release;}
 async function submit(){if(active)return;try{let resp=await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({mechanic_id:s.mechanic_id,task_id:s.task_id,challenge_id:s.challenge_id,events})});let out=await resp.json();if(out.passed){terminal=true;document.getElementById('kiln-status').textContent='PASS';h.setReadout('PASS','passed');}else if(out.state){await h.render(out.state);h.setReadout('FAIL','error');}else h.setReadout('FAIL','error');}catch(e){h.setReadout('CONNECTION LOST · RETRY CERTIFY','error');}}
 document.getElementById('kiln-certify').onclick=submit;
 document.getElementById('kiln-retry').onclick=async()=>{if(active)return;events=[];await submit();};
 oldTimer=setInterval(()=>{if(!active)return;for(let k=0;k<2&&active;k++){
  const before=bs.map(b=>[b.x,b.y]),m=tick(bs,s.world);ticks++;
  const motion=Math.max(0,...bs.slice(0,before.length).map((b,i)=>Math.abs(b.x-before[i][0])+Math.abs(b.y-before[i][1])));
  quiet=!m&&motion<.045?quiet+1:0;
  if(quiet>=24||ticks>=1200){active=false;for(const b of bs)b.vx=b.vy=0;
   events.push({seq:events.length+1,input_source:full?'rail_click':'position_button',x:dropX,ticks,bodies:bs.map(b=>({t:b.t,x:b.x,y:b.y}))});
   const over=ticks>=1200||bs.some(b=>b.y-R[b.t]<s.world.overflow),win=!over&&bs.some(b=>b.t>=s.target);terminal=over||win||events.length>=s.offers.length;
   if(!terminal){const radius=R[s.offers[events.length]];aim=Math.max(radius,Math.min(s.world.width-radius,aim));const proxy=document.getElementById('kiln-position');if(proxy)proxy.value=aim;}
   const failed=over||(!win&&terminal);
   document.getElementById('kiln-status').textContent=failed?'FAIL':'READY';h.setReadout(failed?'FAIL':'READY',failed?'error':'idle');
  }
 }draw();},1000/60);
 draw();
}
window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
window.WeirdCaptchaMechanics.prismfall_kiln={rootSelector:'.prismfall',render};
})();
