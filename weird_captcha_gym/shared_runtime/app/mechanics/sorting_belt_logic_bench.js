(() => {
  'use strict';
  const ID='sorting_belt_logic_bench', arity={AND:2,OR:2,NOT:1,NAND:2};
  let cleanup=()=>{};
  const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
  function token(bits,x=0,y=0,scale=1){
    const color=bits[0]?'#ecad46':'#72b6ca';
    return `<g transform="translate(${x} ${y}) scale(${scale})">${bits[1]?`<rect x="-19" y="-19" width="38" height="38" rx="3" fill="${color}"/>`:`<circle r="21" fill="${color}"/>`}<path d="M-8,-19 v9 ${bits[2]?'M8,-19 v9':''}" stroke="#172d32" stroke-width="5"/>${bits[3]?'<circle r="7" fill="#f4eee0" stroke="#172d32" stroke-width="2"/>':''}</g>`;
  }
  function render(state,h){
    cleanup(); document.body.dataset.mechanic=ID;
    const w=state.world,mode=state.control_condition?.interaction||'full',inputSource=mode==='full'?'drag':'click_pair';
    const m={gates:{},wires:{},events:[],serial:0,selection:null,selectedGate:null,gesture:null,running:false,terminal:false,submitting:false,outputs:null,active:null,start:0,tokenStart:0,batchIndex:0,frame:0,timer:0,hover:null};
    const event=(type,data={})=>m.events.push({seq:m.events.length+1,type,...data});
    const slotPoint=i=>[230+165*Math.floor(i/3),65+110*(i%3)];
    const outPoint=s=>s?.startsWith('s')?[70,45+80*Number(s.slice(1))]:m.gates[s]?[slotPoint(m.gates[s].slot)[0]+48,slotPoint(m.gates[s].slot)[1]]:null;
    const inPoint=d=>d==='eject'?[885,175]:m.gates[d?.split(':')[0]]?(()=>{let [g,i]=d.split(':'),[x,y]=slotPoint(m.gates[g].slot);return [x-48,y+(arity[m.gates[g].kind]===1?0:Number(i)?20:-20)];})():null;
    h.app.innerHTML=`<section class="sorting-bench" data-challenge-id="${esc(state.challenge_id)}" data-interaction="${mode}"><header><div><small>DEPARTMENT OF SELECTIVE MATERIALS / BENCH 07</small><h1>Sorting Belt <em>Logic Bench</em></h1></div><div class="sb-budget">GATES <strong>0 / ${w.gate_budget}</strong></div></header><main><aside class="sb-poster"><h2>Dispatch specification</h2><p>↑ EJECT &nbsp; · &nbsp; → PASS</p><div class="sb-classes">${w.rows.map((r,i)=>`<button class="sb-class" data-row="${i}"><svg viewBox="0 0 64 48">${token(r.bits,26,24,.82)}<text x="49" y="30">${r.eject?'↑':'→'}</text></svg></button>`).join('')}</div><div class="sb-legend">Amber / blue · square / circle${w.attribute_count>2?'<br>Two / one notch':''}${w.attribute_count>3?' · marked / plain':''}</div><p class="sb-note">Build a sorter for this dispatch specification.</p></aside><section class="sb-machine"><div class="sb-toolbar"><span>COMPONENT TRAY</span>${w.gate_types.map(k=>`<button data-palette="${k}">${k}</button>`).join('')}<button id="sb-remove" disabled>Remove gate</button></div><div class="sb-workspace"><svg class="sb-board" viewBox="0 0 930 360" preserveAspectRatio="none" aria-label="Circuit board"></svg></div><div class="sb-belt-head"><b>TEST CONVEYOR</b><span class="sb-progress">NO BATCH RUN</span></div><svg class="sb-belt" viewBox="0 0 930 100"></svg><div class="sb-controls"><button id="sb-run">▶ Run batch</button><button id="sb-certify">Certify sorter</button></div></section></main><footer><div class="readout" data-status="idle"></div></footer></section>`;
    const root=h.app.querySelector('.sorting-bench'),board=root.querySelector('.sb-board'),belt=root.querySelector('.sb-belt');
    const locked=()=>m.running||m.submitting||m.terminal;
    function evaluate(bits){
      const values=Object.fromEntries(bits.map((v,i)=>['s'+i,v])),visiting=new Set();
      function value(src){
        if(src in values)return values[src];
        if(!m.gates[src])throw Error('Unconnected input');
        if(visiting.has(src))throw Error('Feedback loop');
        visiting.add(src);const kind=m.gates[src].kind,a=Array.from({length:arity[kind]},(_,i)=>value(m.wires[src+':'+i]));
        values[src]=Number(kind==='NOT'?!a[0]:kind==='AND'?a.every(Boolean):kind==='OR'?a.some(Boolean):!a.every(Boolean));visiting.delete(src);return values[src];
      }
      Object.keys(m.gates).forEach(value);return {out:value(m.wires.eject),values};
    }
    function signalValues(){if(m.active===null)return {};try{return evaluate(w.rows[m.active].bits).values;}catch(_){return Object.fromEntries(w.rows[m.active].bits.map((v,i)=>['s'+i,v]));}}
    function pin(p,id,direction,lit=false){return `<circle class="sb-pin ${lit?'lit':''} ${m.selection===id?'selected':''}" data-pin="${id}" data-direction="${direction}" cx="${p[0]}" cy="${p[1]}" r="12"><title>${id} ${direction}</title></circle>`;}
    function draw(){
      const values=signalValues();
      board.innerHTML=`<defs><pattern id="sb-grid" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".7" fill="#537077"/></pattern></defs><rect width="930" height="360" fill="url(#sb-grid)"/><text x="18" y="18" class="sb-caption">SENSOR OUTPUTS</text>${Array.from({length:12},(_,i)=>{const [x,y]=slotPoint(i);return `<rect data-slot="${i}" class="sb-slot" x="${x-47}" y="${y-37}" width="94" height="74" rx="7"/>`;}).join('')}${Object.entries(m.wires).map(([d,s])=>{const a=outPoint(s),b=inPoint(d);return `<path class="sb-wire ${values[s]?'live':''}" d="M${a[0]},${a[1]} C${a[0]+50},${a[1]} ${b[0]-50},${b[1]} ${b[0]},${b[1]}"/><text class="sb-wire-label" x="${b[0]-18}" y="${b[1]-8}" text-anchor="end">${esc(s.toUpperCase())}</text>`;}).join('')}${w.sensors.map((s,i)=>`${pin(outPoint('s'+i),'s'+i,'out',values['s'+i])}<text x="90" y="${49+80*i}">S${i} ${esc(s)}</text>`).join('')}${Object.entries(m.gates).map(([id,g])=>{const[x,y]=slotPoint(g.slot);return `<g data-gate="${id}"><rect class="sb-gate ${m.selectedGate===id?'chosen':''}" x="${x-35}" y="${y-33}" width="70" height="66" rx="8"/><text x="${x}" y="${y-10}" text-anchor="middle" class="sb-caption">${id.toUpperCase()}</text><text x="${x}" y="${y+12}" text-anchor="middle">${g.kind}</text></g>${pin(outPoint(id),id,'out',values[id])}${Array.from({length:arity[g.kind]},(_,i)=>pin(inPoint(id+':'+i),id+':'+i,'in',values[m.wires[id+':'+i]])).join('')}`;}).join('')}<rect x="850" y="131" width="70" height="88" rx="6" class="sb-ejector"/><text x="885" y="153" text-anchor="middle">EJECT</text>${pin(inPoint('eject'),'eject','in',values[m.wires.eject])}<text x="885" y="205" text-anchor="middle">↑</text>`;
      root.querySelector('.sb-budget strong').textContent=Object.keys(m.gates).length+' / '+w.gate_budget;
      root.querySelector('#sb-remove').disabled=locked()||!m.selectedGate;
      root.querySelectorAll('[data-palette],#sb-run,#sb-certify').forEach(b=>b.disabled=locked());
      root.querySelectorAll('[data-palette]').forEach(b=>b.classList.toggle('chosen',m.selection==='palette:'+b.dataset.palette));
      root.querySelectorAll('.sb-class').forEach(b=>b.classList.toggle('active',m.active===Number(b.dataset.row)));
    }
    function drawBelt(){
      const elapsed=m.running?performance.now()-m.tokenStart:0,index=m.batchIndex,phase=Math.min(1,elapsed/w.token_ms);
      let current='';
      if(m.running){const row=w.batch_order[index],eject=m.outputs[row],x=30+phase*850,y=phase>.55&&eject?65-(phase-.55)*130:65;current=token(w.rows[row].bits,x,y,.8);}
      belt.innerHTML=`<rect x="12" y="42" width="906" height="46" rx="20" fill="#152b30"/>${Array.from({length:25},(_,i)=>`<circle cx="${25+i*36}" cy="80" r="6" fill="#3f5960"/>`).join('')}<path d="M495,8 V40 M495,40 L475,20 M495,40 L515,20" stroke="#edb553" fill="none" stroke-width="4"/><text x="535" y="24">↑ EJECT</text><text x="820" y="29">PASS →</text>${current}`;
    }
    function invalidate(){m.outputs=null;m.selection=null;h.setReadout('','idle');draw();drawBelt();}
    function place(kind,slot){if(locked()||Object.keys(m.gates).length>=w.gate_budget||Object.values(m.gates).some(g=>g.slot===slot))return;const id='g'+m.serial++;m.gates[id]={kind,slot};event('place',{id,kind,slot,input_source:inputSource});invalidate();}
    function wire(src,dst){if(locked()||!outPoint(src)||!inPoint(dst))return;m.wires[dst]=src;event('wire',{from:src,to:dst,input_source:inputSource});invalidate();}
    function point(e){const b=board.getBoundingClientRect();return [(e.clientX-b.x)*930/b.width,(e.clientY-b.y)*360/b.height];}
    function nearestSlot(p){let i=Array.from({length:12},(_,i)=>i).find(i=>{const q=slotPoint(i);return Math.abs(p[0]-q[0])<=47&&Math.abs(p[1]-q[1])<=37;});return i;}
    // Match SVG's painted hit area: radius 12 plus half the 3-unit pin stroke.
    function hitInput(p){return ['eject',...Object.keys(m.gates).flatMap(k=>Array.from({length:arity[m.gates[k].kind]},(_,i)=>k+':'+i))].find(d=>{const q=inPoint(d);return Math.hypot(p[0]-q[0],p[1]-q[1])<=13.5;});}
    root.querySelectorAll('[data-palette]').forEach(b=>{
      if(mode==='simplified')b.onclick=()=>{m.selection='palette:'+b.dataset.palette;draw();};
      else b.onpointerdown=e=>{if(locked()||e.button!==0)return;e.preventDefault();m.gesture={kind:b.dataset.palette};b.setPointerCapture(e.pointerId);};
    });
    board.onpointerdown=e=>{
      if(locked()||e.button!==0)return;
      const pin=e.target.closest('[data-pin]'),gate=e.target.closest('[data-gate]');
      if(mode==='full'){
        if(pin?.dataset.direction==='out')m.gesture={src:pin.dataset.pin};
        else if(gate){m.selectedGate=gate.dataset.gate;m.gesture={gate:m.selectedGate};}
        if(m.gesture){e.preventDefault();board.setPointerCapture(e.pointerId);}
      } else {
        if(pin?.dataset.direction==='out')m.selection=pin.dataset.pin;
        else if(pin?.dataset.direction==='in'&&m.selection&&!m.selection.startsWith('palette:'))wire(m.selection,pin.dataset.pin);
        else if(gate){m.selectedGate=gate.dataset.gate;m.selection='move:'+m.selectedGate;}
        else {const slot=nearestSlot(point(e));if(slot!==undefined&&m.selection?.startsWith('palette:'))place(m.selection.slice(8),slot);else if(slot!==undefined&&m.selection?.startsWith('move:'))move(m.selection.slice(5),slot);}
      }
      draw();
    };
    function move(id,slot){if(Object.entries(m.gates).some(([k,g])=>k!==id&&g.slot===slot))return;m.gates[id].slot=slot;event('move',{id,slot,input_source:inputSource});invalidate();}
    const up=e=>{board.querySelector('#sb-preview')?.remove();if(!m.gesture)return;const g=m.gesture;m.gesture=null;if(locked())return;const p=point(e),slot=nearestSlot(p);if(g.kind&&slot!==undefined)place(g.kind,slot);else if(g.src){const dst=hitInput(p);if(dst)wire(g.src,dst);}else if(g.gate&&slot!==undefined)move(g.gate,slot);draw();};
    root.addEventListener('pointermove',e=>{
      if(!m.gesture)return;
      board.querySelector('#sb-preview')?.remove();const p=point(e),g=m.gesture;
      const a=g.src?outPoint(g.src):null;
      board.insertAdjacentHTML('beforeend',`<g id="sb-preview" style="pointer-events:none;opacity:.7">${a?`<path d="M${a[0]},${a[1]} L${p[0]},${p[1]}" stroke="#ffce62" stroke-width="3"/>`:`<rect x="${p[0]-35}" y="${p[1]-33}" width="70" height="66" rx="8" fill="#e5b254"/><text x="${p[0]}" y="${p[1]}" text-anchor="middle">${g.kind||m.gates[g.gate].kind}</text>`}</g>`);
    });
    const cancelGesture=()=>{m.gesture=null;board.querySelector('#sb-preview')?.remove();};
    root.addEventListener('pointerup',up);root.addEventListener('pointercancel',cancelGesture);root.addEventListener('lostpointercapture',cancelGesture);
    board.oncontextmenu=e=>{e.preventDefault();if(locked())return;const d=e.target.closest('[data-pin]')?.dataset.pin;if(d&&m.wires[d]){delete m.wires[d];event('unwire',{to:d});invalidate();}};
    root.querySelector('#sb-remove').onclick=()=>{if(locked()||!m.selectedGate)return;const id=m.selectedGate;delete m.gates[id];m.wires=Object.fromEntries(Object.entries(m.wires).filter(([d,s])=>s!==id&&!d.startsWith(id+':')));event('remove',{id});m.selectedGate=null;invalidate();};
    root.querySelectorAll('.sb-class').forEach(b=>b.onclick=()=>{if(m.running)return;m.active=Number(b.dataset.row);draw();});
    function frame(){if(!m.running)return;drawBelt();m.frame=requestAnimationFrame(frame);}
    root.querySelector('#sb-run').onclick=()=>{
      if(locked())return;
      try{m.outputs=w.rows.map(r=>evaluate(r.bits).out);}catch(_){event('run',{outputs:null});h.setReadout('FAIL','error');return;}
      h.setReadout('','pending');root.querySelector('.sb-progress').textContent='RUNNING';m.running=true;m.start=performance.now();m.tokenStart=m.start;m.batchIndex=0;m.active=w.batch_order[0];draw();frame();
      let finished=0;
      function tick(){
        finished++;
        root.querySelector('.sb-progress').textContent=finished+' / '+w.rows.length+' SORTED';
        if(finished===w.rows.length){m.running=false;cancelAnimationFrame(m.frame);event('run',{outputs:m.outputs.slice(),routed:w.batch_order.map(i=>({row:i,eject:m.outputs[i]})),elapsed_ms:Math.max(w.rows.length*w.token_ms,performance.now()-m.start)});h.setReadout('BATCH COMPLETE','idle');draw();drawBelt();}
        else{m.batchIndex=finished;m.tokenStart=performance.now();m.active=w.batch_order[finished];draw();m.timer=setTimeout(tick,w.token_ms);}
      }
      m.timer=setTimeout(tick,w.token_ms);
    };
    root.querySelector('#sb-certify').onclick=async()=>{
      if(locked())return;m.submitting=true;draw();event('certify');
      try{const r=await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mechanic_id:ID,task_id:state.task_id,challenge_id:state.challenge_id,events:m.events})});const result=await r.json();
        if(result.passed){m.terminal=true;h.setReadout('PASS','passed');root.dataset.terminal='pass';}
        else if(result.state){await h.render(result.state);h.setReadout('FAIL','error');}
        else {m.events.pop();h.setReadout('SUBMISSION UNAVAILABLE','error');}
      }catch(_){m.events.pop();h.setReadout('SUBMISSION UNAVAILABLE','error');}finally{m.submitting=false;if(root.isConnected)draw();}
    };
    cleanup=()=>{clearTimeout(m.timer);cancelAnimationFrame(m.frame);};
    draw();drawBelt();
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics[ID]={rootSelector:'.sorting-bench',render};
})();
