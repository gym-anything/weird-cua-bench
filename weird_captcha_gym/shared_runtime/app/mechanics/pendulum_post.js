(() => {
  'use strict';
  const clone=x=>JSON.parse(JSON.stringify(x));
  let cleanup=()=>{};
  function distance(p,a,b) {const dx=b[0]-a[0],dy=b[1]-a[1],dd=dx*dx+dy*dy,t=dd?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/dd)):0;return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy);}
  function crossing(a,b,c,d) {const cross=(u,v)=>u[0]*v[1]-u[1]*v[0],r=[b[0]-a[0],b[1]-a[1]],q=[d[0]-c[0],d[1]-c[1]],den=cross(r,q);if(Math.abs(den)<1e-9)return false;const v=[c[0]-a[0],c[1]-a[1]],t=cross(v,q)/den,u=cross(v,r)/den;return t>=0&&t<=1&&u>=.04&&u<=.96;}
  function ropePoints(r,s) {const a=[r.x,r.y],b=[s.x,s.y],dx=b[0]-a[0],dy=b[1]-a[1],d=Math.hypot(dx,dy),sag=Math.sqrt(Math.max(0,r.length*r.length-d*d))/2;let nx=d?-dy/d:0,ny=d?dx/d:1;if(ny<0){nx=-nx;ny=-ny;}return [a,[(a[0]+b[0])/2+nx*sag,(a[1]+b[1])/2+ny*sag],b];}
  function advance(s,w) {
    if(s.status!=='active')return;s.tick++;const a=[s.x,s.y];s.vy+=w.gravity*.01;s.x+=s.vx*.01;s.y+=s.vy*.01;
    for(let z=0;z<12;z++)w.ropes.forEach((r,i)=>{if(!s.active[i])return;const dx=s.x-r.x,dy=s.y-r.y,d=Math.hypot(dx,dy);if(d>r.length){const nx=dx/d,ny=dy/d;s.x=r.x+nx*r.length;s.y=r.y+ny*r.length;const out=Math.max(0,s.vx*nx+s.vy*ny);s.vx-=out*nx;s.vy-=out*ny;}});
    const b=[s.x,s.y];w.seals.forEach((p,i)=>{if(!s.seals.includes(i)&&distance(p,a,b)<=w.radius+w.seal_radius)s.seals.push(i);});
    if(w.hazards.some(h=>distance(h,a,b)<=w.radius+h[2]))s.status='damaged';
    const basket=w.basket;if(s.status==='active'&&a[1]+w.radius<basket.y&&basket.y<=b[1]+w.radius){const t=(basket.y-w.radius-a[1])/(b[1]-a[1]),x=a[0]+t*(b[0]-a[0]);if(Math.abs(x-basket.x)<=basket.width/2-w.radius&&!s.active.some(Boolean))s.status=s.seals.length===w.seals.length?'delivered':'missing_seals';else if(Math.abs(x-basket.x)<=basket.width/2+w.radius)s.status='damaged';}
    if(s.status==='active'&&(s.x<w.radius||s.x>900-w.radius||s.y>470-w.radius))s.status='lost';if(s.status==='active'&&s.tick>=9000)s.status='timeout';
  }
  function render(state,h) {
    cleanup();document.body.dataset.mechanic='pendulum-post';const w=state.world,mode=state.control_condition?.interaction||'full';
    const m={state,sim:{tick:0,x:w.start[0],y:w.start[1],vx:0,vy:0,active:w.ropes.map(()=>true),seals:[],status:'active'},events:[],running:false,start:0,submitted:false};window.pendulumPostModel=m;
    h.app.innerHTML=`<section class="pendulum-post"><header><div class="pp-emblem">P<span>POST</span></div><div><small>THE DEPARTMENT OF PRECARIOUS DELIVERIES</small><h1>Pendulum Post</h1></div><div class="pp-seal-count"></div></header><div class="pp-cabinet"><canvas width="900" height="480" aria-label="Parcel, ropes, seals and receiving basket"></canvas><aside><small>DISPATCH DESK</small><h2>Every seal.<br>One safe landing.</h2><p>${mode==='full'?'Swipe across a rope to cut it.':'Click a numbered rope button to cut it.'}</p><div class="pp-buttons">${mode==='simplified'?w.ropes.map((_,i)=>`<button data-rope="${i}">✂ Rope ${i+1}</button>`).join(''):'<div class="pp-swipe">✂<span>HOLD · SWIPE · RELEASE</span></div>'}</div><p class="pp-hint">Cuts are permanent.<br>Keep the parcel out of ink.</p><button class="pp-start">Release cabinet</button><button class="pp-new">New parcel</button></aside></div><footer><div class="readout" data-status="idle">READY</div><span class="pp-status">Collect the wax seals, then reach the basket.</span><button class="pp-submit" hidden>Certify delivery</button></footer></section>`;
    const root=h.app.querySelector('.pendulum-post'),canvas=root.querySelector('canvas'),ctx=canvas.getContext('2d'),status=root.querySelector('.pp-status');
    function line(points,color,width=3){ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();}
    function disk(x,y,r,c){ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle=c;ctx.fill();}
    function draw(){const s=m.sim;ctx.clearRect(0,0,900,480);ctx.fillStyle='#e9dec2';ctx.fillRect(0,0,900,480);
      ctx.strokeStyle='#d7c7a4';ctx.lineWidth=1;for(let x=30;x<900;x+=60){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,480);ctx.stroke();}for(let y=30;y<480;y+=60){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(900,y);ctx.stroke();}
      ctx.fillStyle='#244b4b';ctx.font='12px monospace';ctx.fillText('AIR MAIL / SORTING CABINET',22,25);
      w.hazards.forEach(a=>{disk(a[0],a[1],a[2],'#263645');ctx.fillStyle='#f3b0a0';ctx.font='bold 19px sans-serif';ctx.textAlign='center';ctx.fillText('×',a[0],a[1]+6);});
      w.seals.forEach((a,i)=>{disk(a[0],a[1],w.seal_radius,s.seals.includes(i)?'#8d9f85':'#b6403f');ctx.strokeStyle='#f4c687';ctx.lineWidth=2;ctx.stroke();ctx.fillStyle='#fff0cd';ctx.textAlign='center';ctx.font='bold 16px serif';ctx.fillText(s.seals.includes(i)?'✓':'✦',a[0],a[1]+5);});
      w.ropes.forEach((r,i)=>{if(s.active[i]){const pts=ropePoints(r,s);line(pts,'#5d4430',7);line(pts,'#c6a875',3);}disk(r.x,r.y,13,'#234a4b');ctx.fillStyle='#fff3d4';ctx.textAlign='center';ctx.font='bold 15px sans-serif';ctx.fillText(String(i+1),r.x,r.y+5);});
      const b=w.basket;ctx.fillStyle='#466b65';ctx.fillRect(b.x-b.width/2,b.y,b.width,34);line([[b.x-b.width/2,b.y],[b.x-b.width/2,b.y+34],[b.x+b.width/2,b.y+34],[b.x+b.width/2,b.y]],'#244b4b',5);for(let x=b.x-b.width/2+10;x<b.x+b.width/2;x+=15)line([[x,b.y+4],[x,b.y+30]],'#a9bba0',2);ctx.fillStyle='#fff0cd';ctx.font='bold 12px monospace';ctx.fillText('RECEIVING',b.x,b.y+22);
      disk(s.x+3,s.y+5,w.radius,'#b8aa8b');disk(s.x,s.y,w.radius,s.status==='damaged'?'#38404a':'#c69256');ctx.strokeStyle='#654c32';ctx.lineWidth=2;ctx.stroke();line([[s.x-w.radius+2,s.y],[s.x+w.radius-2,s.y]],'#f2d9a6',4);line([[s.x,s.y-w.radius+2],[s.x,s.y+w.radius-2]],'#f2d9a6',4);
      root.querySelector('.pp-seal-count').textContent=`${s.seals.length} / ${w.seals.length} SEALS`;root.querySelectorAll('[data-rope]').forEach(b=>b.disabled=!m.running||!s.active[+b.dataset.rope]||s.status!=='active');
      if(s.status!=='active'&&!m.certified){m.running=false;const ok=s.status==='delivered';status.textContent=ok?'All seals collected. Parcel received.':({missing_seals:'Delivery rejected: missing seals.',damaged:'Parcel damaged by ink or the basket rim.',lost:'Parcel missed the basket.',timeout:'Dispatch window closed.'}[s.status]);h.setReadout(ok?'DELIVERED':'FAIL',ok?'passed':'error');root.querySelector('.pp-submit').hidden=!ok;}
    }
    function tick(){if(m.running){const target=Math.floor((performance.now()-m.start)/10+1e-7);while(m.sim.tick<target&&m.sim.status==='active')advance(m.sim,w);}draw();}
    function cut(i,a,b){tick();if(!m.running||!m.sim.active[i]||m.sim.status!=='active')return;m.sim.active[i]=false;m.events.push({tick:m.sim.tick,rope:i,input_source:mode==='full'?'rope_swipe':'rope_button',...(mode==='full'?{a,b}:{})});draw();}
    root.querySelector('.pp-start').onclick=()=>{if(m.running||m.sim.tick)return;m.running=true;m.start=performance.now();root.querySelector('.pp-start').disabled=true;h.setReadout('IN TRANSIT','idle');};
    root.querySelectorAll('[data-rope]').forEach(b=>b.onclick=()=>cut(+b.dataset.rope));
    // Pointer positions must use the painted content box, excluding the cabinet border.
    let last=null;const pos=e=>{const r=canvas.getBoundingClientRect(),style=getComputedStyle(canvas),left=parseFloat(style.borderLeftWidth),right=parseFloat(style.borderRightWidth),top=parseFloat(style.borderTopWidth),bottom=parseFloat(style.borderBottomWidth);return [(e.clientX-r.left-left)*canvas.width/(r.width-left-right),(e.clientY-r.top-top)*canvas.height/(r.height-top-bottom)];};
    canvas.onpointerdown=e=>{if(mode!=='full'||e.button!==0)return;canvas.setPointerCapture(e.pointerId);last=pos(e);};
    function swipe(e){if(!last)return;const p=pos(e);tick();w.ropes.forEach((r,i)=>{const pts=ropePoints(r,m.sim);if(m.sim.active[i]&&[0,1].some(j=>crossing(last,p,pts[j],pts[j+1])))cut(i,last,p);});last=p;}
    canvas.onpointermove=swipe;canvas.onpointerup=e=>{swipe(e);last=null;};canvas.onpointercancel=()=>last=null;
    async function submit(abandon=false){if(m.submitted)return;tick();m.running=false;m.submitted=true;const payload={mechanic_id:state.mechanic_id,task_id:state.task_id,challenge_id:state.challenge_id,interaction_mode:mode,events:abandon?[]:clone(m.events),terminal_tick:m.sim.tick,completed:!abandon&&m.sim.status==='delivered'};try{const r=await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const out=await r.json();if(out.passed){m.certified=true;h.setReadout('PASS','passed');status.textContent='DELIVERY CERTIFIED';root.querySelector('.pp-submit').hidden=true;}else if(out.state){render(out.state,h);}else{m.submitted=false;h.setReadout('FAIL','error');}}catch(e){m.submitted=false;status.textContent='Submission unavailable. Retry certification.';}}
    root.querySelector('.pp-submit').onclick=()=>submit();root.querySelector('.pp-new').onclick=()=>submit(true);
    let frame;function loop(){tick();frame=requestAnimationFrame(loop);}frame=requestAnimationFrame(loop);cleanup=()=>cancelAnimationFrame(frame);draw();
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};window.WeirdCaptchaMechanics.pendulum_post={rootSelector:'.pendulum-post',render};
})();
