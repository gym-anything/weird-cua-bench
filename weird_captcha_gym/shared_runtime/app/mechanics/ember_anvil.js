(() => {
  'use strict';
  let m, helpers, timer;
  const D = [[1,0],[0,1],[-1,0],[0,-1]];
  const names = ['E','S','W','N'];
  const $ = s => helpers.app.querySelector(s);
  function clock() { return Math.max(0, Math.floor(performance.now()-m.start)); }
  function thermal(t=clock()) {
    const dt=t-m.last;
    m.heat=m.location==='forge'?Math.min(1,m.heat+dt/m.w.heat_ms):Math.max(0,m.heat-dt/m.w.cooling_ms);
    m.last=t; return t;
  }
  function log(type, data={}, source='tool_control', t=thermal()) {
    m.events.push({seq:m.events.length+1,type,t,input_source:source,...data});
  }
  function note(s) { $('#ea-message').textContent=s; helpers.setReadout(s,'idle'); }
  function active() { return !m.busy&&!m.terminal; }
  function surface() { return m.interaction==='full'?'direct_drag':'proxy_click'; }
  function transfer() {
    if(!active())return;
    const t=thermal(); m.location=m.location==='anvil'?'forge':'anvil';
    if(m.location==='forge')m.reheats++;
    log('transfer',{to:m.location},surface(),t);
    note(m.location==='forge'?'The forge warms the same workpiece.':'Back on the anvil.');paint();
  }
  function orbit(delta) { if(!active())return; m.turn=(m.turn+delta+5)%5;log('orbit',{delta},surface());paint(); }
  function strike(i) {
    if(!active())return;
    const t=thermal();let result='moved';const h=m.h;
    if(m.location!=='anvil')result='in_forge';
    else if(m.heat+1e-9<m.w.workable)result='cold';
    else if(!h[i])result='empty';
    else if(m.tool==='split') {h[i]--;m.discarded++;result='split';}
    else {
      const [dx,dy]=D[m.direction],x=i%7+dx,y=Math.floor(i/7)+dy,j=y*7+x;
      if(x<0||x>=7||y<0||y>=7||h[j]>=m.w.max_height||(m.tool==='draw'&&h[j]>=h[i])||(m.tool==='upset'&&h[j]!==h[i]))result='blocked';
      else {h[i]--;h[j]++;}
    }
    log('strike',{cell:i,mode:m.tool,direction:m.direction,outcome:result,heights:h.slice()},surface(),t);
    const words={moved:'Metal displaced.',split:'One voxel discarded permanently.',cold:'TOO COLD · Return the workpiece to the forge.',blocked:'BLOCKED · Draw into lower metal; upset onto equal height.',empty:'No metal at this contact.',in_forge:'Return the workpiece to the anvil first.'};
    note(words[result]);m.flash={i,until:t+450};paint();
    if(m.h.reduce((a,b)=>a+b,0)<m.w.target.reduce((a,b)=>a+b,0))note('INSUFFICIENT METAL · Stamp to reject and start a fresh billet.');
  }
  function rotated(x,y) {
    for(let k=0;k<m.turn;k++){const old=x;x=7-y;y=old;}return [x,y];
  }
  function project(x,y,z,cx,cy,s) {
    if(m.turn===4)return [cx+(x-3.5)*s*1.35,cy+(y-3.5)*s*1.05];
    const [a,b]=rotated(x,y);return [cx+(a-b)*s,cy+(a+b-7)*s*.48-z*s*.72];
  }
  function poly(ctx,points,fill,stroke='#562f22') {
    ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.fillStyle=fill;ctx.fill();ctx.strokeStyle=stroke;ctx.lineWidth=1.15;ctx.stroke();
  }
  function drawSolid(canvas,h,target=false) {
    const ctx=canvas.getContext('2d'),W=canvas.width,H=canvas.height,s=target?20:34,cx=W/2,cy=target?H*.58:H*.53;
    ctx.clearRect(0,0,W,H);let faces=[];
    const p=(x,y,z)=>project(x,y,z,cx,cy,s);
    const base=[p(-.35,-.35,-.25),p(7.35,-.35,-.25),p(7.35,7.35,-.25),p(-.35,7.35,-.25)];
    poly(ctx,base,target?'#152b2b':'#30373d',target?'#42615a':'#69777e');
    if(!target) {
      // Anvil body, drawn from the same projected plane as the metal bed.
      ctx.save();ctx.globalAlpha=.2;
      for(let x=0;x<=7;x++){ctx.beginPath();ctx.moveTo(...p(x,0,0));ctx.lineTo(...p(x,7,0));ctx.stroke();}
      for(let y=0;y<=7;y++){ctx.beginPath();ctx.moveTo(...p(0,y,0));ctx.lineTo(...p(7,y,0));ctx.stroke();}ctx.restore();
    }
    const cubes=[];
    for(let i=0;i<49;i++)for(let z=0;z<h[i];z++) {
      const x=i%7,y=Math.floor(i/7),[a,b]=rotated(x+.5,y+.5);cubes.push({i,x,y,z,depth:a+b});
    }
    cubes.sort((a,b)=>a.depth-b.depth||a.z-b.z);
    for(const c of cubes) {
      const {i,x,y,z}=c;
      const points=[p(x,y,z+1),p(x+1,y,z+1),p(x+1,y+1,z+1),p(x,y+1,z+1)];
      // Select the two camera-facing sides after the actual quarter-turn transform.
      const edges=[];
      for(let k=0;k<4;k++) {
        const a=points[k],b=points[(k+1)%4];
        edges.push({k,y:(a[1]+b[1])/2});
      }
      edges.sort((a,b)=>b.y-a.y);
      const lum=target?55:25+Math.round(m.heat*43),sat=target?26:Math.round(20+m.heat*68),hue=target?158:12+m.heat*22;
      for(const {k} of (m.turn===4?[]:edges.slice(0,2))) {
        const a=points[k],b=points[(k+1)%4],down=s*.72;
        const face=[a,b,[b[0],b[1]+down],[a[0],a[1]+down]];
        poly(ctx,face,`hsl(${hue} ${sat}% ${lum-(k%2?17:25)}%)`,target?'#476d60':'#533427');
        faces.push({points:face,i,top:false});
      }
      poly(ctx,points,`hsl(${hue} ${sat}% ${lum}%)`,target?'#b1d2a7':'#6a3b28');
      faces.push({points,i,top:z===h[i]-1});
      if(!target&&z===h[i]-1&&(m.hover===i||(m.flash?.i===i&&m.last<m.flash.until))) {
        ctx.save();ctx.strokeStyle='#fff2b6';ctx.lineWidth=3;ctx.beginPath();points.forEach(([px,py],k)=>k?ctx.lineTo(px,py):ctx.moveTo(px,py));ctx.closePath();ctx.stroke();ctx.restore();
      }
    }
    if(!target) {
      m.faces=faces;
      for(let d=0;d<4;d++) {
        const [dx,dy]=D[d],[x,y]=p(3.5+dx*4.45,3.5+dy*4.45,0);
        ctx.font='bold 16px sans-serif';ctx.textAlign='center';ctx.fillStyle=d===m.direction?'#ffe2a1':'#b5b6ac';ctx.fillText(names[d],x,y+5);
      }
      if(m.location==='forge') {
        ctx.fillStyle='rgba(15,21,25,.91)';ctx.fillRect(0,0,W,H);ctx.fillStyle='#e9c9a0';ctx.font='24px Georgia';ctx.textAlign='center';ctx.fillText('Workpiece in the forge',W/2,H/2);ctx.font='15px sans-serif';ctx.fillText('Its shape is preserved.',W/2,H/2+30);
      }
    }
  }
  function inside(x,y,points) {
    let yes=false;
    for(let i=0,j=points.length-1;i<points.length;j=i++) {
      const [a,b]=points[i],[c,d]=points[j];
      if((b>y)!==(d>y)&&x<(c-a)*(y-b)/(d-b)+a)yes=!yes;
    }return yes;
  }
  function hit(clientX,clientY) {
    const c=$('#ea-work'),r=c.getBoundingClientRect(),x=(clientX-r.left)*c.width/r.width,y=(clientY-r.top)*c.height/r.height;
    if(m.location!=='anvil')return null;
    for(let i=m.faces.length-1;i>=0;i--)if(inside(x,y,m.faces[i].points))return m.faces[i].top?m.faces[i].i:null;
    return null;
  }
  function paint() {
    thermal();drawSolid($('#ea-work'),m.h);drawSolid($('#ea-target'),m.w.target,true);
    $('#ea-heat-fill').style.width=`${m.heat*100}%`;
    $('#ea-heat').textContent=m.heat>=.95?'BRIGHT · WORKABLE':m.heat>=m.w.workable?'GLOWING · WORKABLE':'DARK · TOO COLD';
    $('#ea-forge').classList.toggle('occupied',m.location==='forge');
    $('#ea-tongs').classList.toggle('at-forge',m.location==='forge');
    $('#ea-tongs').textContent=m.location==='forge'?'♜ TONGS · FORGE':'♜ TONGS · ANVIL';
    $('#ea-transfer')?.replaceChildren(document.createTextNode(m.location==='forge'?'Return to anvil':'Move to forge'));
    $('#ea-ledger').textContent=`Discarded ${m.discarded} · Reheats ${m.reheats}`;
    $('#ea-turn').textContent=m.turn===4?'TOP VIEW':`VIEW ${m.turn+1} / 4`;
    $('#ea-tool').textContent=`${m.tool.toUpperCase()} ${m.tool==='split'?'':names[m.direction]} · ${m.interaction==='full'?'DRAG HAMMER TO METAL':'CLICK A TOP FACE'}`;
  }
  async function stamp() {
    if(!active())return;
    log('stamp');m.busy=true;
    const payload={mechanic_id:m.state.mechanic_id,task_id:m.state.task_id,challenge_id:m.state.challenge_id,events:m.events,heights:m.h.slice(),discarded:m.discarded,reheats:m.reheats};
    try {
      const r=await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)}),out=await r.json();
      if(out.passed===true){m.terminal=true;$('#ea-verdict').textContent='PASS · TOOL ACCEPTED';$('#ea-verdict').classList.add('show','pass');helpers.setReadout('PASS','passed');}
      else if(out.passed===false){if(out.state)await helpers.render(out.state);$('#ea-verdict').textContent='FAIL · FRESH BILLET';$('#ea-verdict').classList.add('show');helpers.setReadout('FAIL · FRESH BILLET','error');}
      else{m.events.pop();m.busy=false;note('Stamp unavailable · try again.');}
    }catch(e){m.events.pop();m.busy=false;note('Stamp link unavailable · try again.');}
  }
  function clearFailure(){if(!m.terminal){$('#ea-verdict').classList.remove('show');helpers.setReadout('WORKSHOP OPEN','idle');}}
  async function render(state,h) {
    if(timer)clearInterval(timer);helpers=h;
    m={state,w:state.world,h:state.world.initial.slice(),heat:state.world.initial_heat,last:0,start:performance.now(),location:'anvil',events:[],tool:'draw',direction:0,turn:0,discarded:0,reheats:0,faces:[],hover:null,busy:false,terminal:false,interaction:state.control_condition?.interaction||'simplified'};
    document.body.dataset.mechanic='ember-anvil';
    helpers.app.innerHTML=`<section class="ember-anvil" data-challenge-id="${helpers.text(state.challenge_id)}">
      <header><div><small>THE EMBER WORKSHOP</small><h1>Ember Anvil</h1></div><p>Shape the metal. Keep every layer true.</p><span class="ea-badge">${m.interaction.toUpperCase()}</span></header>
      <main><section class="ea-bench"><div class="ea-caption"><b>WORKPIECE · ${m.w.max_height} LAYERS MAX</b><span id="ea-turn"></span></div><canvas id="ea-work" width="700" height="360"></canvas><div id="ea-verdict"></div><div class="ea-orbit">${m.interaction==='simplified'?'<button id="ea-left">↶ Turn left</button><button id="ea-right">Turn right ↷</button>':'<div id="ea-orbit-rail">↔ DRAG TO TURN THE ANVIL</div>'}</div><div class="ea-thermal"><span id="ea-heat"></span><div class="ea-meter"><i id="ea-heat-fill"></i><b></b></div><small>DARK ← TEMPER → BRIGHT</small></div></section>
      <aside><div class="ea-caption"><b>TARGET · ${helpers.text(m.w.title)}</b></div><canvas id="ea-target" width="290" height="230"></canvas><p class="ea-target-note">Match the solid, including thickness.<br>Both models turn together.</p><div id="ea-forge"><div class="ea-flames">♨</div><strong>FORGE</strong><span>Reheat without undoing strikes</span></div></aside></main>
      <section class="ea-tools"><div class="ea-modes"><button data-mode="draw" class="selected">DRAW<small>into a lower neighbor</small></button><button data-mode="upset">UPSET<small>onto an equal neighbor</small></button><button data-mode="split">SPLIT<small>discard one voxel</small></button></div><div class="ea-directions">${names.map((v,i)=>`<button data-direction="${i}" class="${i===0?'selected':''}">${v}</button>`).join('')}</div><div id="ea-hammer" role="button" tabindex="0" aria-label="Hammer"><svg width="50" height="45" viewBox="0 0 50 45"><path d="M18 16L35 42" stroke="#a77a4b" stroke-width="9"/><path d="M4 13L26 2L36 15L14 27Z" fill="#c7c9bd" stroke="#5b605c" stroke-width="3"/></svg><span>${m.interaction==='full'?'DRAG HAMMER':'HAMMER'}</span></div></section>
      <section class="ea-transfer-row"><b id="ea-tool"></b><div id="ea-tongs" role="button" tabindex="0"></div>${m.interaction==='simplified'?'<button id="ea-transfer"></button>':'<span class="ea-drag-note">Drag tongs to the forge / anvil</span>'}</section>
      <footer><div><span id="ea-message">Choose a mode and shape the glowing metal.</span><small id="ea-ledger"></small><div class="readout" data-status="idle">WORKSHOP OPEN</div></div><button id="ea-stamp">STAMP TOOL →</button></footer></section>`;
    helpers.app.addEventListener('pointerdown',clearFailure,{once:true});
    $('.ea-modes').addEventListener('click',e=>{const b=e.target.closest('[data-mode]');if(!b||!active())return;clearFailure();m.tool=b.dataset.mode;log('mode',{mode:m.tool});$('.ea-modes').querySelectorAll('button').forEach(x=>x.classList.toggle('selected',x===b));paint();});
    $('.ea-directions').addEventListener('click',e=>{const b=e.target.closest('[data-direction]');if(!b||!active())return;clearFailure();m.direction=Number(b.dataset.direction);log('direction',{direction:m.direction});$('.ea-directions').querySelectorAll('button').forEach(x=>x.classList.toggle('selected',x===b));paint();});
    $('#ea-work').addEventListener('pointermove',e=>{m.hover=hit(e.clientX,e.clientY);});
    if(m.interaction==='simplified') {
      $('#ea-work').addEventListener('click',e=>{clearFailure();const i=hit(e.clientX,e.clientY);if(i!==null)strike(i);});
      $('#ea-transfer').onclick=()=>{clearFailure();transfer();};$('#ea-left').onclick=()=>orbit(-1);$('#ea-right').onclick=()=>orbit(1);
    } else {
      const drag=(node,done)=>node.addEventListener('pointerdown',e=>{if(e.button!==0||!active())return;e.preventDefault();clearFailure();node.setPointerCapture(e.pointerId);const x=e.clientX,y=e.clientY;node.classList.add('dragging');const up=v=>{node.classList.remove('dragging');node.removeEventListener('pointerup',up);if(node.hasPointerCapture(v.pointerId))node.releasePointerCapture(v.pointerId);done(v,x,y);};node.addEventListener('pointerup',up);node.addEventListener('pointercancel',()=>{node.classList.remove('dragging');node.removeEventListener('pointerup',up);},{once:true});});
      drag($('#ea-hammer'),e=>{const i=hit(e.clientX,e.clientY);if(i!==null)strike(i);});
      drag($('#ea-orbit-rail'),(e,x)=>{if(Math.abs(e.clientX-x)>=60)orbit(e.clientX>x?1:-1);});
      drag($('#ea-tongs'),e=>{const r=$(m.location==='forge'?'#ea-work':'#ea-forge').getBoundingClientRect();if(e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom)transfer();});
    }
    $('#ea-stamp').onclick=stamp;paint();timer=setInterval(()=>{if(!m.terminal)paint();},80);
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics.ember_anvil={rootSelector:'.ember-anvil',render};
})();
