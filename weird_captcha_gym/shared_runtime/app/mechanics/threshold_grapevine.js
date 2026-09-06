(() => {
  'use strict';
  const mechanic='threshold_grapevine';
  function render(state,helpers) {
    document.body.dataset.mechanic='threshold-grapevine';
    const w=state.world, full=(state.control_condition?.interaction||'full')==='full';
    const key=(a,b)=>[Math.min(a,b),Math.max(a,b)].join(':');
    const initial=new Set(w.edges.map(e=>key(...e))), fixed=new Set(w.fixed_edges.map(e=>key(...e)));
    let edges=new Set(initial),stage=0,active=new Set(w.seeds),events=[],running=false,settled=false,terminal=false,selection=[],stroke=null,round=0,timer=null,pending=null;
    const start=performance.now();
    helpers.app.innerHTML=`<section class="tg-root"><header><div><small>THE NEIGHBOURHOOD EXPERIMENT / 08</small><h1>Threshold Grapevine</h1></div><div class="tg-badge">IDEAS TRAVEL<br>THROUGH FRIENDS</div></header><div class="tg-body"><main><div class="tg-stage"></div><canvas width="860" height="470" aria-label="Friendship network"></canvas><div class="tg-legend"><span>● Convinced</span><span>◉ Seed</span><span>◌ Quarantine</span><span>━ Fixed friendship</span></div></main><aside><h2 class="tg-goal"></h2><p>A face joins when its convinced-friend fraction reaches its badge.</p><div class="tg-count"></div><div class="tg-reserve"></div><p class="tg-help">${full?'Drag face → face to connect.<br>Scratch across one thin line to cut.':'Select two faces, then add or cut their friendship.'}<br>Thick lines are fixed.</p>${full?'':'<div class="tg-pair">Choose two faces</div><div class="tg-pair-buttons"><button data-action="add">ADD</button><button data-action="cut">CUT</button></div>'}<button class="tg-run">LET IT SPREAD →</button><button class="tg-reset">RESTORE BOARD</button><button class="tg-accept" hidden></button><button class="tg-abandon">ABANDON ATTEMPT</button></aside></div><footer><div class="readout" data-status="idle">Rewire the neighbourhood.</div><span class="tg-round"></span></footer><div class="tg-verdict" hidden></div></section>`;
    const root=helpers.app.querySelector('.tg-root'),canvas=root.querySelector('canvas'),ctx=canvas.getContext('2d');
    const log=(type,extra={})=>events.push({seq:events.length+1,type,stage,t:performance.now()-start,...extra});
    const point=e=>{const b=canvas.getBoundingClientRect();return [Math.max(0,Math.min(860,(e.clientX-b.left)*860/b.width)),Math.max(0,Math.min(470,(e.clientY-b.top)*470/b.height))];};
    const hit=p=>w.nodes.findIndex(n=>Math.hypot(p[0]-n.x,p[1]-n.y)<=25);
    const cross=(u,v,z)=>(v[0]-u[0])*(z[1]-u[1])-(v[1]-u[1])*(z[0]-u[0]);
    const intersects=(p,q,a,b)=>cross(p,q,a)*cross(p,q,b)<0&&cross(a,b,p)*cross(a,b,q)<0;
    const changed=()=>new Set([...edges].filter(e=>!initial.has(e)).concat([...initial].filter(e=>!edges.has(e)))).size;
    function next(current){const result=new Set(current);for(const node of w.nodes){const neighbors=[...edges].map(e=>e.split(':').map(Number)).filter(e=>e.includes(node.id)).map(e=>e[0]===node.id?e[1]:e[0]);if(neighbors.length&&neighbors.filter(i=>current.has(i)).length*node.threshold[1]>=neighbors.length*node.threshold[0])result.add(node.id);}return result;}
    function draw(){
      ctx.clearRect(0,0,860,470);ctx.fillStyle='#f1ead8';ctx.fillRect(0,0,860,470);
      for(const e of edges){const [a,b]=e.split(':').map(Number),x=w.nodes[a],y=w.nodes[b];ctx.strokeStyle=active.has(a)&&active.has(b)?'#408367':'#a09a87';ctx.lineWidth=fixed.has(e)?6:2.5;ctx.beginPath();ctx.moveTo(x.x,x.y);ctx.lineTo(y.x,y.y);ctx.stroke();}
      if(stroke){ctx.strokeStyle='#d05b37';ctx.lineWidth=3;ctx.beginPath();stroke.path.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.stroke();}
      for(const n of w.nodes){const on=active.has(n.id),protectedNode=stage===1&&w.quarantine.includes(n.id);ctx.save();ctx.translate(n.x,n.y);
        if(protectedNode){ctx.strokeStyle='#b85337';ctx.lineWidth=2;ctx.setLineDash([5,4]);ctx.beginPath();ctx.arc(0,0,34,0,Math.PI*2);ctx.stroke();ctx.setLineDash([]);}
        ctx.fillStyle=on?'#eabf53':'#d4d0c2';ctx.strokeStyle=selection.includes(n.id)?'#dc4d2c':'#324c42';ctx.lineWidth=selection.includes(n.id)?4:2;ctx.beginPath();ctx.arc(0,0,25,0,Math.PI*2);ctx.fill();ctx.stroke();
        if(w.seeds.includes(n.id)){ctx.lineWidth=2;ctx.beginPath();ctx.arc(0,0,21,0,Math.PI*2);ctx.stroke();}
        ctx.fillStyle='#324c42';ctx.beginPath();ctx.arc(-8,-3,2.3,0,Math.PI*2);ctx.arc(8,-3,2.3,0,Math.PI*2);ctx.fill();ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(-8,9);on?ctx.quadraticCurveTo(0,17,8,9):ctx.lineTo(8,9);ctx.stroke();
        if(n.portrait%2){ctx.beginPath();ctx.moveTo(-17,-12);ctx.quadraticCurveTo(-5,-30,12,-18);ctx.stroke();}if(n.portrait>2){ctx.strokeRect(-14,-8,11,10);ctx.strokeRect(3,-8,11,10);}
        ctx.fillStyle='#f8f2e4';ctx.fillRect(-20,26,40,19);ctx.fillStyle='#324c42';ctx.font='bold 14px Georgia';ctx.textAlign='center';ctx.fillText(n.threshold.join('/'),0,41);ctx.restore();}
      root.querySelector('.tg-stage').textContent=`${String(stage+1).padStart(2,'0')} / ${w.targets.length===1?'SPREAD':'SPREAD → CONTAIN'}${stage===1?' · ORIGINAL BOARD RESTORED':''}`;
      root.querySelector('.tg-goal').textContent=stage===0?'Convince everyone.':'Keep the marked group grey.';
      root.querySelector('.tg-count').innerHTML=`<b>${active.size}</b> / ${w.nodes.length} convinced <small>${[...next(active)].filter(i=>!active.has(i)).length} ready to join</small>`;
      root.querySelector('.tg-reserve').textContent=`${changed()} / ${w.edit_limit} links changed`;
      root.querySelector('.tg-round').textContent=running?`SPREADING · ROUND ${round}`:settled?`SETTLED · ${round} ROUNDS`:'';
      root.querySelector('.tg-run').disabled=running||terminal;root.querySelector('.tg-reset').disabled=running||terminal;root.querySelector('.tg-abandon').disabled=running||terminal;
      const won=settled&&JSON.stringify([...active].sort((a,b)=>a-b))===JSON.stringify(w.targets[stage]);
      root.querySelector('.tg-accept').hidden=!won;root.querySelector('.tg-accept').textContent=stage+1<w.targets.length?'ACCEPT → CONTAINMENT':w.targets.length===1?'CERTIFY GOAL':'CERTIFY BOTH GOALS';
      if(!full){root.querySelector('.tg-pair').textContent=selection.length===2?'Two faces selected':selection.length?'Choose another face':'Choose two faces';for(const b of root.querySelectorAll('.tg-pair-buttons button'))b.disabled=running||terminal||selection.length!==2;}
    }
    function edit(a,b,operation,path){if(running||terminal||a<0||b<0||a===b)return;const e=key(a,b);if(fixed.has(e)){helpers.setReadout('Fixed friendship · cannot cut','idle');return;}if((operation==='add')===edges.has(e)){helpers.setReadout(operation==='add'?'Already connected':'No friendship to cut','idle');return;}
      edges.has(e)?edges.delete(e):edges.add(e);if(changed()>w.edit_limit){edges.has(e)?edges.delete(e):edges.add(e);helpers.setReadout('Changed-link limit reached · undo or restore','error');return;}
      log('edit',{edge:e.split(':').map(Number),operation,input_source:full?'graph_gesture':'pair_buttons',...(path?{path}:{})});active=new Set(w.seeds);round=0;settled=false;selection=[];helpers.setReadout('Friendship '+(operation==='add'?'added':'cut'),'idle');draw();}
    canvas.addEventListener('pointerdown',e=>{if(e.button!==0||running||terminal)return;const p=point(e);if(full){stroke={id:e.pointerId,path:[p]};canvas.setPointerCapture(e.pointerId);}else{const i=hit(p);if(i>=0){selection=selection.includes(i)?selection.filter(v=>v!==i):[...selection.slice(-1),i];draw();}}e.preventDefault();});
    canvas.addEventListener('pointermove',e=>{if(stroke&&stroke.id===e.pointerId){if(stroke.path.length<510)stroke.path.push(point(e));draw();}});
    canvas.addEventListener('pointerup',e=>{if(!stroke||stroke.id!==e.pointerId)return;const s=stroke;stroke=null;s.path.push(point(e));if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);const a=hit(s.path[0]),b=hit(s.path.at(-1));if(a>=0)edit(a,b,'add',s.path);else{const crossed=[...edges].filter(edge=>!fixed.has(edge)).filter(edge=>{const [a,b]=edge.split(':').map(Number),x=w.nodes[a],y=w.nodes[b];return s.path.slice(1).some((q,i)=>intersects(s.path[i],q,[x.x,x.y],[y.x,y.y]));});if(crossed.length===1)edit(...crossed[0].split(':').map(Number),'cut',s.path);else helpers.setReadout(crossed.length?'Stroke crosses several lines · cut one at a time':'No thin friendship crossed','idle');}draw();});
    canvas.addEventListener('pointercancel',()=>{stroke=null;draw();});canvas.addEventListener('lostpointercapture',()=>{stroke=null;draw();});
    if(!full)root.querySelectorAll('.tg-pair-buttons button').forEach(b=>b.onclick=()=>edit(...selection,b.dataset.action));
    let rounds=[];
    root.querySelector('.tg-run').onclick=()=>{if(running||terminal)return;log('run');active=new Set(w.seeds);rounds=[[...active].sort((a,b)=>a-b)];running=true;settled=false;round=0;selection=[];helpers.setReadout('The idea is spreading…','idle');draw();
      function tick(){if(!root.isConnected)return;const following=next(active);round++;if(following.size===active.size){running=false;settled=true;const won=JSON.stringify([...active].sort((a,b)=>a-b))===JSON.stringify(w.targets[stage]);helpers.setReadout(won?'GOAL REACHED · accept this network':stage===1&&w.quarantine.some(i=>active.has(i))?'QUARANTINE BREACHED · repair and rerun':'CASCADE STALLED · repair and rerun',won?'idle':'error');draw();return;}active=following;rounds.push([...active].sort((a,b)=>a-b));draw();timer=setTimeout(tick,w.round_ms);}timer=setTimeout(tick,w.round_ms);};
    root.querySelector('.tg-reset').onclick=()=>{if(running||terminal)return;log('reset');edges=new Set(initial);active=new Set(w.seeds);selection=[];settled=false;round=0;helpers.setReadout('Original board restored','idle');draw();};
    function show(text,label,callback){const v=root.querySelector('.tg-verdict');v.hidden=false;v.replaceChildren();const title=document.createElement('strong');title.textContent=text;v.append(title);if(label){const b=document.createElement('button');b.textContent=label;b.onclick=callback;v.append(b);}}
    async function submit(){show('CHECKING NETWORK');try{const response=await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(pending)});if(!response.ok)throw new Error('Transport');const result=await response.json();if(result.passed===true){helpers.setReadout('PASS','passed');show('PASS · THE GRAPEVINE HOLDS');}else if(result.passed===false&&result.state){helpers.setReadout('FAIL','error');show('FAIL · ATTEMPT ENDED','NEW NEIGHBOURHOOD',()=>helpers.render(result.state));}else throw new Error('Missing grade');}catch(error){show('NETWORK NOT RECEIVED','RETRY SUBMISSION',submit);}}
    function payload(completed){return {mechanic_id:mechanic,task_id:state.task_id,challenge_id:state.challenge_id,control_condition:state.control_condition||null,events,completed};}
    root.querySelector('.tg-accept').onclick=()=>{if(running||terminal||!settled)return;log('accept',{rounds});if(stage+1===w.targets.length){terminal=true;pending=payload(true);submit();}else{stage++;edges=new Set(initial);active=new Set(w.seeds);settled=false;round=0;helpers.setReadout('Containment · reach everyone outside the marked group','idle');draw();}};
    root.querySelector('.tg-abandon').onclick=()=>{if(running||terminal)return;log('abandon');terminal=true;pending=payload(false);submit();};
    draw();
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};window.WeirdCaptchaMechanics[mechanic]={rootSelector:'.tg-root',render};
})();
