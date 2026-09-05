(() => {
'use strict';
const M='load_bearing_idol';
function body(s){const b={...s,vx:0,vy:0,av:0,angle:s.angle||0},mass=b.w*b.h/1000;b.im=b.fixed?0:1/mass;b.ii=b.fixed?0:12/(mass*(b.w*b.w+b.h*b.h));return b;}
function vertices(b){const c=Math.cos(b.angle),s=Math.sin(b.angle);return [[-b.w/2,-b.h/2],[b.w/2,-b.h/2],[b.w/2,b.h/2],[-b.w/2,b.h/2]].map(([x,y])=>[b.x+x*c-y*s,b.y+x*s+y*c]);}
function contact(a,b,margin=0){
 const va=vertices(a),vb=vertices(b);let best=null;
 [a,b].forEach((q,idx)=>{const c=Math.cos(q.angle),s=Math.sin(q.angle);[[c,s],[-s,c]].forEach(([nx,ny],axis)=>{const pa=va.map(([x,y])=>x*nx+y*ny),pb=vb.map(([x,y])=>x*nx+y*ny),depth=Math.min(Math.max(...pa),Math.max(...pb))-Math.max(Math.min(...pa),Math.min(...pb));if(!best||depth<best[0])best=[depth,nx,ny,idx,axis];});});
 let [depth,nx,ny,idx,axis]=best;if(depth< -margin)return null;
 if((b.x-a.x)*nx+(b.y-a.y)*ny<0){nx=-nx;ny=-ny;}
 const ref=idx===0?a:b,inc=idx===0?b:a,rx=idx===0?nx:-nx,ry=idx===0?ny:-ny,tx=-ry,ty=rx;
 const plane=ref.x*rx+ref.y*ry+ref[axis===0?'w':'h']/2,mid=ref.x*tx+ref.y*ty,extent=ref[axis===0?'h':'w']/2,c=Math.cos(inc.angle),s=Math.sin(inc.angle);
 let choices=[[c,s,inc.w/2,inc.h/2],[-s,c,inc.h/2,inc.w/2]];
 let [ux,uy,un,ut]=Math.abs(choices[0][0]*rx+choices[0][1]*ry)>=Math.abs(choices[1][0]*rx+choices[1][1]*ry)?choices[0]:choices[1];
 if(ux*rx+uy*ry>0){ux=-ux;uy=-uy;}
 const center=[inc.x+ux*un,inc.y+uy*un],p=[center[0]-uy*ut,center[1]+ux*ut],q=[center[0]+uy*ut,center[1]-ux*ut],pv=p[0]*tx+p[1]*ty,qv=q[0]*tx+q[1]*ty;
 let lo=0,hi=1;if(Math.abs(qv-pv)>1e-10){const u=(mid-extent-pv)/(qv-pv),v=(mid+extent-pv)/(qv-pv);lo=Math.max(lo,Math.min(u,v));hi=Math.min(hi,Math.max(u,v));}
 const points=[];for(const t of [lo,hi]){const x=p[0]+(q[0]-p[0])*t,y=p[1]+(q[1]-p[1])*t,pen=plane-x*rx-y*ry;if(lo<=hi&&pen>=-margin-.02)points.push([x+rx*pen/2,y+ry*pen/2]);}
 if(!points.length)points.push([(a.x+b.x)/2,(a.y+b.y)/2]);return [depth,nx,ny,points];
}
function step(bs){
 for(const b of bs)if(b.im){b.vy+=.16;b.vx*=.995;b.vy*=.995;b.av*=.99;b.x+=b.vx;b.y+=b.vy;b.angle+=b.av;}
 const contacts=[];
 for(let k=0;k<8;k++)for(let i=0;i<bs.length;i++)for(let j=i+1;j<bs.length;j++){
  const a=bs[i],b=bs[j],inv=a.im+b.im;if(!inv)continue;const hit=contact(a,b);if(!hit)continue;const [depth,nx,ny,points]=hit;if(k===0)contacts.push([a.id,b.id]);
  const cor=Math.max(0,depth-.015)*.65/inv;a.x-=nx*cor*a.im;a.y-=ny*cor*a.im;b.x+=nx*cor*b.im;b.y+=ny*cor*b.im;
  const data=points.map(([px,py])=>{const ra=[px-a.x,py-a.y],rb=[px-b.x,py-b.y],rv=[b.vx-b.av*rb[1]-a.vx+a.av*ra[1],b.vy+b.av*rb[0]-a.vy-a.av*ra[0]];return [ra,rb,rv[0]*nx+rv[1]*ny,ra[0]*ny-ra[1]*nx,rb[0]*ny-rb[1]*nx];});
  let impulses=data.map(()=>0);if(data.length===2){const [u,v]=data,k1=inv+u[3]**2*a.ii+u[4]**2*b.ii,k2=inv+v[3]**2*a.ii+v[4]**2*b.ii,k12=inv+u[3]*v[3]*a.ii+u[4]*v[4]*b.ii,det=k1*k2-k12*k12;if(det>1e-9)impulses=[(-u[2]*k2+v[2]*k12)/det,(-v[2]*k1+u[2]*k12)/det];}
  if(data.length===1||Math.min(...impulses)<0||Math.max(...impulses)===0)impulses=data.map(d=>Math.max(0,-d[2]/(inv+d[3]**2*a.ii+d[4]**2*b.ii))/data.length);
  data.forEach((d,n)=>{const z=impulses[n];a.vx-=z*nx*a.im;a.vy-=z*ny*a.im;a.av-=d[3]*z*a.ii;b.vx+=z*nx*b.im;b.vy+=z*ny*b.im;b.av+=d[4]*z*b.ii;});
  const px=points.reduce((s,p)=>s+p[0],0)/points.length,py=points.reduce((s,p)=>s+p[1],0)/points.length,ra=[px-a.x,py-a.y],rb=[px-b.x,py-b.y],tx=-ny,ty=nx;
  const rv=[b.vx-b.av*rb[1]-a.vx+a.av*ra[1],b.vy+b.av*rb[0]-a.vy-a.av*ra[0]],ta=ra[0]*ty-ra[1]*tx,tb=rb[0]*ty-rb[1]*tx,mu=[a.kind,b.kind].includes('plank')?.015:.45,limit=impulses.reduce((s,x)=>s+x,0)*mu;
  const f=Math.max(-limit,Math.min(limit,-(rv[0]*tx+rv[1]*ty)/(inv+ta*ta*a.ii+tb*tb*b.ii)));a.vx-=f*tx*a.im;a.vy-=f*ty*a.im;a.av-=ta*f*a.ii;b.vx+=f*tx*b.im;b.vy+=f*ty*b.im;b.av+=tb*f*b.ii;
 }
 return contacts;
}
function local(b,p){const c=Math.cos(b.angle),s=Math.sin(b.angle),x=p[0]-b.x,y=p[1]-b.y;return [x*c+y*s,-x*s+y*c];}
function contains(b,p){const [x,y]=local(b,p);return Math.abs(x)<=b.w/2&&Math.abs(y)<=b.h/2;}
function action(bs,e,mode){
 const b=bs.find(b=>b.id===e.body);if(!b||!['chalk','plank','timber'].includes(b.kind))throw Error('Iron cannot be removed.');if(e.source!==mode)throw Error('Wrong input surface.');const p=e.start,q=e.end;
 if(b.kind==='chalk'){if(!contains(b,p)||Math.hypot(p[0]-q[0],p[1]-q[1])>8)throw Error('Click chalk to crumble it.');bs.splice(bs.indexOf(b),1);}
 else if(b.kind==='plank'){if(!contains(b,p)||Math.abs(q[1]-p[1])>12||Math.abs(q[0]-p[0])<b.w+30)throw Error('Pull the plank sideways beyond the stack.');b.extract=q[0]>p[0]?1:-1;b.extract_origin=b.x;}
 else{const a=local(b,p),z=local(b,q);if(!((a[1]<-b.h/2&&z[1]>b.h/2)||(z[1]<-b.h/2&&a[1]>b.h/2)))throw Error('Cross both timber edges.');const cut=a[0]+(z[0]-a[0])*(-a[1])/(z[1]-a[1]);if(Math.abs(cut)>b.w/2-12||Math.abs(a[0]-z[0])>12)throw Error('Make a straight crosscut.');bs.splice(bs.indexOf(b),1);for(const [suffix,l,r] of [['a',-b.w/2,cut-.5],['b',cut+.5,b.w/2]]){const mid=(l+r)/2,c=Math.cos(b.angle),s=Math.sin(b.angle),n=body({...b,id:b.id+suffix,w:r-l,x:b.x+mid*c,y:b.y+mid*s,kind:'fragment'});Object.assign(n,{vx:b.vx-b.av*mid*s,vy:b.vy+b.av*mid*c,av:b.av});bs.push(n);}}
 return b.id;
}
function tick(bs){for(const b of [...bs])if('extract'in b){b.vx=4*b.extract;if((b.x-b.extract_origin)*b.extract>=b.w+60)bs.splice(bs.indexOf(b),1);}const pairs=step(bs),by=Object.fromEntries(bs.map(b=>[b.id,b]));for(let i=0;i<2;i++){const g=by['glass'+i],ledge=by['ledge'+i];if(g&&ledge&&(g.y>ledge.y+45||pairs.some(p=>p.includes(g.id)&&p.includes('floor'))))g.lost=true;}return pairs;}
function outcome(bs,removed,quota,floor){const by=Object.fromEntries(bs.map(b=>[b.id,b])),idol=by.idol;return !bs.some(b=>'extract'in b)&&!floor&&[0,1].every(i=>contact(by['glass'+i],by['ledge'+i],.5)&&!by['glass'+i].lost)&&Math.abs(idol.vx)<.1&&Math.abs(idol.vy)<.3&&Math.abs(idol.av)<.01&&contact(idol,by.cradle,.5)&&removed.size>=quota;}
let current;
function render(state,h){
 document.body.dataset.mechanic=M;
 if(current)cancelAnimationFrame(current.timer);
 const mode=state.control_condition?.interaction||'full';
 h.app.innerHTML=`<section class="idol-room"><header><div><small>DEPARTMENT OF DELICATE DEMOLITION</small><h1>Load Bearing Idol</h1></div><p>Lower the idol into the padded cradle.<br>Keep both ampoules on their ledges.</p></header><main><div class="idol-stage"><canvas width="860" height="550"></canvas><div class="idol-stamp" hidden></div></div><aside><small>FIELD EQUIPMENT / IV</small><h2>Everything<br>rests on<br>something.</h2><dl><dt class="chalk">CHALK</dt><dd>Brittle</dd><dt class="timber">TIMBER</dt><dd>Cuttable</dd><dt class="plank">LOOSE PLANK</dt><dd>↔</dd><dt class="iron">IRON</dt><dd>Unbreakable</dd></dl>${mode==='simplified'?'<div class="idol-proxy"><p>Select a piece in the scene.</p><button data-op="crumble">Crumble</button><button data-op="cut">Crosscut: two points</button><button data-op="left">Extract ←</button><button data-op="right">Extract →</button></div>':''}<div class="idol-count"></div><button class="idol-certify">Certify landing</button><button class="idol-retry">New attempt</button></aside></main><footer><span class="readout" data-status="idle">STRUCTURE READY</span><span>ONE REMOVAL · LET THE STRUCTURE SETTLE</span></footer></section>`;
 const root=h.app.querySelector('.idol-room'),canvas=root.querySelector('canvas'),ctx=canvas.getContext('2d'),stamp=root.querySelector('.idol-stamp');
 const model={bs:state.bodies.map(body),events:[],removed:new Set(),ticks:0,started:performance.now(),busy:0,floor:false,failed:false,selected:null,drag:null,terminal:false};current=model;
 function say(text,status='idle'){h.setReadout(text,status);}
 function pt(e){const r=canvas.getBoundingClientRect();return [(e.clientX-r.left)*860/r.width,(e.clientY-r.top)*550/r.height];}
 function at(p){return [...model.bs].reverse().find(b=>contains(b,p));}
 function commit(e){advance();if(model.busy||model.terminal||model.failed)return;try{action(model.bs,e,mode);model.events.push({...e,tick:model.ticks});model.removed.add(e.body);model.busy=180;model.selected=null;say('SETTLING…');}catch(err){say(err.message,'error');}draw();}
 canvas.addEventListener('pointerdown',e=>{advance();if(model.busy||model.terminal||model.failed)return;const p=pt(e);if(mode==='simplified'){if(model.cut){model.cut.push(p);if(model.cut.length===2){commit({body:model.selected,start:model.cut[0],end:model.cut[1],source:mode});model.cut=null;}}else model.selected=at(p)?.id;draw();return;}model.drag={start:p,end:p,body:at(p)?.id};canvas.setPointerCapture(e.pointerId);});
 canvas.addEventListener('pointermove',e=>{if(model.drag){model.drag.end=pt(e);draw();}});
 canvas.addEventListener('pointerup',e=>{if(!model.drag)return;const d=model.drag;model.drag=null;d.end=pt(e);if(!d.body){const mid=[(d.start[0]+d.end[0])/2,(d.start[1]+d.end[1])/2];d.body=at(mid)?.id;}commit({...d,source:mode});});
 canvas.addEventListener('pointercancel',()=>{model.drag=null;draw();});
 root.querySelectorAll('[data-op]').forEach(btn=>btn.onclick=()=>{const b=model.bs.find(b=>b.id===model.selected);if(!b)return;const op=btn.dataset.op;if(op==='cut'){if(b.kind!=='timber')return say('Choose timber.','error');model.cut=[];say('Click the two ends of the crosscut.');return;}let start=[b.x,b.y],end=[b.x,b.y];if(op==='cut'){const s=Math.sin(b.angle),c=Math.cos(b.angle);start=[b.x+s*(b.h/2+15),b.y-c*(b.h/2+15)];end=[b.x-s*(b.h/2+15),b.y+c*(b.h/2+15)];}if(op==='left'||op==='right')end[0]+=(b.w+60)*(op==='left'?-1:1);if((op==='cut'&&b.kind!=='timber')||(['left','right'].includes(op)&&b.kind!=='plank')||(op==='crumble'&&b.kind!=='chalk'))return say('Choose the matching material.','error');commit({body:b.id,start,end,source:mode});});
 async function submit(retry=false){advance();if(model.terminal&&!retry)return;model.terminal=true;say('CHECKING CONTACTS…');try{const payload={mechanic_id:M,task_id:state.task_id,challenge_id:state.challenge_id,events:retry?[]:model.events,ticks:model.ticks};const response=await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),res=await response.json();if(res.passed){say('PASS · IDOL RECOVERED','passed');stamp.hidden=false;stamp.textContent='SAFELY RECOVERED';}else if(res.state){if(retry){render(res.state,h);return;}say('FAIL · LANDING NOT CERTIFIED','error');stamp.hidden=false;stamp.textContent='RECOVERY FAILED';root.querySelector('.idol-retry').onclick=()=>render(res.state,h);}else{model.terminal=false;say('Verification unavailable. Retry certification.','error');}}catch(e){model.terminal=false;say('Verification unavailable. Retry certification.','error');}}
 root.querySelector('.idol-certify').onclick=()=>{if(!model.busy)submit();};root.querySelector('.idol-retry').onclick=()=>submit(true);
 function draw(){
 ctx.clearRect(0,0,860,550);ctx.fillStyle='#202c2c';ctx.fillRect(0,0,860,550);ctx.strokeStyle='#33403c';ctx.lineWidth=1;for(let x=0;x<860;x+=86){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,550);ctx.stroke();}for(let y=40;y<550;y+=85){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(860,y);ctx.stroke();}
 ctx.fillStyle='#829184';ctx.font='12px monospace';ctx.fillText('RELIC RECOVERY / KEEP THE GLASS INTACT',26,30);
 const colors={chalk:'#e3d9bb',timber:'#a67543',fragment:'#a67543',plank:'#bfa277',iron:'#647878',idol:'#dbab4a',glass:'#a7dcd0',floor:'#142020',cradle:'#688466'};
 for(const b of model.bs){ctx.save();ctx.translate(b.x,b.y);ctx.rotate(b.angle);ctx.fillStyle=colors[b.kind];ctx.strokeStyle='#101d1d';ctx.lineWidth=2;ctx.fillRect(-b.w/2,-b.h/2,b.w,b.h);ctx.strokeRect(-b.w/2,-b.h/2,b.w,b.h);ctx.beginPath();ctx.rect(-b.w/2,-b.h/2,b.w,b.h);ctx.clip();
 if(b.kind==='chalk'){ctx.strokeStyle='#b0a88f';for(let k=-b.w/2+9;k<b.w/2;k+=24){ctx.beginPath();ctx.moveTo(k,-b.h/2+5);ctx.lineTo(k+7,0);ctx.lineTo(k-3,b.h/2-4);ctx.stroke();}}
 if(['timber','fragment','plank'].includes(b.kind)){ctx.strokeStyle='#765536';for(let y=-b.h/2+6;y<b.h/2;y+=8){ctx.beginPath();ctx.moveTo(-b.w/2+3,y);ctx.bezierCurveTo(-12,y+5,15,y-5,b.w/2-3,y);ctx.stroke();}if(b.kind==='plank'){ctx.fillStyle='#ead6a6';ctx.font='18px serif';ctx.textAlign='center';ctx.fillText('↔',0,6);}}
 if(b.kind==='iron'){ctx.fillStyle='#a0b5ae';for(const x of [-b.w/2+7,b.w/2-7]){ctx.beginPath();ctx.arc(x,0,3,0,7);ctx.fill();}}
 if(b.kind==='glass'){ctx.fillStyle='#3d9b91';ctx.fillRect(-b.w/2+3,0,b.w-6,b.h/2-3);ctx.fillStyle='#e7fff0';ctx.fillRect(-b.w/2+4,-b.h/2+4,3,b.h-9);}
 if(b.kind==='idol'){ctx.fillStyle='#56432b';ctx.fillRect(-12,-9,7,7);ctx.fillRect(5,-9,7,7);ctx.fillRect(-8,7,16,3);ctx.strokeStyle='#f6d684';ctx.lineWidth=3;ctx.strokeRect(-18,-20,36,40);}
 if(b.kind==='cradle'){ctx.strokeStyle='#acc69a';for(let x=-b.w/2+10;x<b.w/2;x+=15){ctx.beginPath();ctx.moveTo(x,-b.h/2);ctx.lineTo(x,b.h/2);ctx.stroke();}}
 ctx.restore();if(model.selected===b.id){ctx.strokeStyle='#f8db82';ctx.lineWidth=3;ctx.beginPath();vertices(b).forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.stroke();}}
 if(model.drag){ctx.strokeStyle='#f5df95';ctx.setLineDash([5,4]);ctx.beginPath();ctx.moveTo(...model.drag.start);ctx.lineTo(...model.drag.end);ctx.stroke();ctx.setLineDash([]);}
 root.querySelector('.idol-count').textContent=`REMOVED ${model.removed.size} / ${state.quota} MINIMUM`;
 root.querySelector('.idol-certify').disabled=!!model.busy;
 }
 // Fixed steps follow elapsed task time, including the exact pause-boundary
 // RAF flush. Callback coalescing must never discard simulation time.
 function advance(){
  if(model.terminal)return;
  const target=Math.min(18000,Math.floor((performance.now()-model.started)*60/1000+1e-7));
  while(model.ticks<target){
   const pairs=tick(model.bs);model.ticks++;
   if(pairs.some(p=>p.includes('idol')&&p.includes('floor')))model.floor=true;
   if(model.busy)model.busy--;
  }
  const by=Object.fromEntries(model.bs.map(b=>[b.id,b]));
  if(model.floor||[0,1].some(i=>by['glass'+i].lost)){
   model.failed=true;stamp.hidden=false;stamp.textContent='GLASS OR IDOL LOST';say('FAIL · NEW ATTEMPT AVAILABLE','error');
  }else if(!model.busy)say('STRUCTURE READY');
 }
 function frame(){advance();draw();model.timer=requestAnimationFrame(frame);}
 model.timer=requestAnimationFrame(frame);draw();
}
window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};window.WeirdCaptchaMechanics[M]={rootSelector:'.idol-room',render};
// Read-only numerical API used by independent engine agreement tests, never an agent action.
window.LoadBearingIdolPhysics={body,vertices,contact,step,action,tick,outcome};
})();
