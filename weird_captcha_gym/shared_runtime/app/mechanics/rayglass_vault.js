(() => {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  async function render(state, helpers, options={}) {
    document.body.dataset.mechanic='rayglass-vault';
    const n=state.size, full=state.control_condition?.interaction!=='simplified';
    let marks=new Set(), shots=new Map(), events=[], active=null, done=false, busy=false;
    const esc=helpers.text;
    const mode=full?'full':'simplified';
    helpers.app.innerHTML=`<section class="rayglass-vault" data-interaction="${mode}" data-challenge="${esc(state.challenge_id)}">
      <header class="rv-head"><div><div class="rv-kicker">THE OPTICAL ARCHIVE <span> / CABINET ${esc(state.case_number)}</span></div><h1>Rayglass Vault</h1><p>Send light into the dark. Find what bends it.</p></div><div class="rv-emblem">◈<small>SEALED<br>SPECIMENS</small></div></header>
      <main class="rv-work"><div class="rv-stage"><div class="rv-stage-label"><span>OPAQUE GLASS / ${n} × ${n}</span><b id="rv-count"></b></div>
        <svg id="rv-cabinet" viewBox="0 0 500 480" aria-label="Optical cabinet with numbered beam ports and hypothesis cells">
          <defs><linearGradient id="rv-brass" x2="1" y2="1"><stop stop-color="#cead70"/><stop offset=".35" stop-color="#493d2b"/><stop offset=".6" stop-color="#a0804a"/><stop offset="1" stop-color="#3e372b"/></linearGradient><linearGradient id="rv-glass" x2=".8" y2="1"><stop stop-color="#173b3d"/><stop offset=".6" stop-color="#0a2027"/><stop offset="1" stop-color="#23424a"/></linearGradient></defs>
          <rect x="12" y="2" width="476" height="476" rx="28" fill="#0a191f" stroke="#58625c" stroke-width="2"/>
          <rect x="68" y="58" width="364" height="364" rx="5" fill="url(#rv-brass)"/><rect x="73" y="63" width="354" height="354" fill="url(#rv-glass)"/>
          <g id="rv-cells"></g><g id="rv-ports"></g>
          <g fill="#bca777">${[[27,17],[473,17],[27,463],[473,463]].map(([x,y])=>`<circle cx="${x}" cy="${y}" r="4"/>`).join('')}</g>
          <text x="250" y="470" text-anchor="middle" class="rv-engrave">R A Y G L A S S  /  OPTICAL INSTRUMENTS</text>
        </svg><p class="rv-hint">${full?'Click a border port to probe · Click a cell to mark / erase':'Use the console to probe ports and mark / erase cells'}</p>
      </div><aside class="rv-console">
        <div class="rv-rules"><div><b>H</b><span>HEAD-ON<br>absorbed</span></div><div><b>R</b><span>RETURN<br>reflected</span></div><div><b>↔</b><span>PAIR<br>entry / exit</span></div></div>
        <div class="rv-law"><svg viewBox="0 0 90 44" aria-label="A beam bends away from a diagonal bead"><path d="M4 20 H43 V4" fill="none" stroke="#88e2d3" stroke-width="3"/><path d="m38 10 5-6 5 6" fill="none" stroke="#88e2d3" stroke-width="2"/><circle cx="64" cy="36" r="7" fill="#d6b475"/></svg><span>Diagonal bead → turn away<br>Direct hit takes priority<br>Two diagonals → reverse · Edge deflection → R</span></div>
        ${full?'':`<div class="rv-proxy"><div><label>PORT <select id="rv-port-select">${Array.from({length:4*n},(_,i)=>`<option value="${i}">${i+1}</option>`).join('')}</select></label><button id="rv-fire">FIRE BEAM</button></div><div><label>ROW <select id="rv-row">${Array.from({length:n},(_,i)=>`<option value="${i}">${String.fromCharCode(65+i)}</option>`).join('')}</select></label><label>COL <select id="rv-col">${Array.from({length:n},(_,i)=>`<option value="${i}">${i+1}</option>`).join('')}</select></label><button id="rv-mark">MARK / ERASE</button></div></div>`}
        <div class="rv-ledger-title"><h2>Probe ledger</h2><span id="rv-queries">0 shots</span></div><div id="rv-ledger"></div>
        <div class="rv-readout" id="rv-reading">Choose a port. The glass keeps its secrets.</div>
        <div class="rv-seal-info">Place ${state.bead_count} beads. Any layout with the same response at <em>every</em> port opens the vault.</div>
        <button id="rv-seal">SEAL HYPOTHESIS <span>↗</span></button>
      </aside></main><footer class="rv-foot"><div class="readout" id="rv-status" data-status="idle">${options.failed?'FAIL · Fresh cabinet ready':'READY TO INVESTIGATE'}</div><span>BEAM QUERIES COUNTED · NO QUERY LIMIT</span></footer>
      <div id="rv-verdict" ${options.failed?'':'hidden'}><b>FAIL</b><span>Hypothesis rejected. A fresh cabinet is ready.</span><button id="rv-retry">INVESTIGATE NEW CABINET →</button></div>
    </section>`;
    const root=helpers.app.querySelector('.rayglass-vault'), svg=root.querySelector('#rv-cabinet');
    function make(tag,attrs,parent,text) {const e=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;parent.append(e);return e;}
    const cellEls=[],portEls=[];
    state.geometry.cells.forEach((c,i)=>{
      const g=make('g',{'data-cell':i, class:'rv-cell',role:full?'button':'img','aria-label':`Cell ${String.fromCharCode(65+Math.floor(i/n))}${i%n+1}`,tabindex:full?0:-1},root.querySelector('#rv-cells'));
      make('rect',{x:c.x-c.size/2,y:c.y-c.size/2,width:c.size,height:c.size,rx:3},g);
      make('text',{x:c.x-c.size/2+5,y:c.y-c.size/2+12,class:'rv-coordinate'},g,`${String.fromCharCode(65+Math.floor(i/n))}${i%n+1}`);
      make('circle',{cx:c.x,cy:c.y,r:Math.min(17,c.size*.28),class:'rv-bead'},g);
      make('circle',{cx:c.x-4,cy:c.y-5,r:4,class:'rv-glint'},g);
      cellEls.push(g);
      if(full) bind(g,'mark',i);
    });
    state.geometry.ports.forEach((c,i)=>{
      const g=make('g',{'data-port':i,class:'rv-port',role:full?'button':'img','aria-label':`Port ${i+1}`,tabindex:full?0:-1},root.querySelector('#rv-ports'));
      make('rect',{x:c.x-19,y:c.y-19,width:38,height:38,rx:9},g);
      make('text',{x:c.x,y:c.y+5,'text-anchor':'middle'},g,String(i+1));
      portEls.push(g);if(full)bind(g,'probe',i);
    });
    function bind(el,kind,index) {
      el.addEventListener('click',e=>{
        const p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;
        const pt=p.matrixTransform(svg.getScreenCTM().inverse());
        if(e.detail===0) {const c=state.geometry[kind==='probe'?'ports':'cells'][index];act(kind,index,[c.x,c.y]);}
        else act(kind,index,[Number(pt.x.toFixed(3)),Number(pt.y.toFixed(3))]);
      });
      el.addEventListener('keydown',e=>{if(!e.repeat&&['Enter',' '].includes(e.key)){e.preventDefault();const c=state.geometry[kind==='probe'?'ports':'cells'][index];act(kind,index,[c.x,c.y]);}});
    }
    function responseLabel(p,r) {return typeof r==='number'?`${p+1} ↔ ${r+1}`:`${p+1} · ${r}`;}
    function act(kind,index,point) {
      if(done||busy||!root.querySelector('#rv-verdict').hidden)return;
      const item={seq:events.length+1,type:kind,index,input_surface:full?'cabinet_click':'console_button'};
      if(full)item.point=point;
      if(kind==='probe'){
        const r=state.sensor_responses[index];item.response=r;shots.set(index,r);active=index;
      } else if(marks.has(index))marks.delete(index);else marks.add(index);
      events.push(item);update();
    }
    function update() {
      cellEls.forEach((el,i)=>el.classList.toggle('is-marked',marks.has(i)));
      const activeResponse=active===null?null:shots.get(active);
      portEls.forEach((el,i)=>{el.classList.toggle('is-probed',shots.has(i));el.classList.toggle('is-active',i===active||i===activeResponse);});
      root.querySelector('#rv-count').textContent=`${marks.size} / ${state.bead_count} BEADS`;
      root.querySelector('#rv-queries').textContent=`${events.filter(e=>e.type==='probe').length} shots`;
      root.querySelector('#rv-ledger').innerHTML=Array.from({length:4*n},(_,i)=>{
        const r=shots.get(i);return `<div class="rv-entry ${r===undefined?'unfired':''} ${i===active?'active':''}">${r===undefined?`${i+1} · —`:responseLabel(i,r)}</div>`;
      }).join('');
      root.querySelector('#rv-reading').textContent=active===null?'Choose a port. The glass keeps its secrets.':`LAST BEAM: ${responseLabel(active,activeResponse)}${activeResponse==='H'?' · absorbed':activeResponse==='R'?' · returned to entry':' · paired ports glow'}`;
      const seal=root.querySelector('#rv-seal');seal.disabled=marks.size!==state.bead_count||busy||done;
      root.dataset.markCount=String(marks.size);root.dataset.queryCount=String(events.filter(e=>e.type==='probe').length);
    }
    if(!full) {
      root.querySelector('#rv-fire').onclick=()=>act('probe',Number(root.querySelector('#rv-port-select').value));
      root.querySelector('#rv-mark').onclick=()=>act('mark',Number(root.querySelector('#rv-row').value)*n+Number(root.querySelector('#rv-col').value));
    }
    root.querySelector('#rv-retry').onclick=()=>{root.querySelector('#rv-verdict').hidden=true;root.querySelector('#rv-status').textContent='READY TO INVESTIGATE';};
    root.querySelector('#rv-seal').onclick=async()=>{
      if(busy||done||marks.size!==state.bead_count)return;
      busy=true;update();
      const status=root.querySelector('#rv-status');status.textContent='CHECKING OPTICAL SIGNATURE…';
      try{
        const response=await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mechanic_id:state.mechanic_id,task_id:state.task_id,challenge_id:state.challenge_id,control_condition:state.control_condition,interaction_mode:mode,events,marks:[...marks].sort((a,b)=>a-b)})});
        if(!response.ok)throw new Error('submission unavailable');
        const outcome=await response.json();
        if(outcome.passed){done=true;status.textContent='PASS · VAULT OPEN';status.dataset.status='passed';root.classList.add('is-open');root.querySelector('#rv-reading').textContent='All border beams agree. Optical seal released.';}
        else if(outcome.state){await render(outcome.state,helpers,{failed:true});return;}
        else{status.textContent='FAIL · Check hypothesis';status.dataset.status='error';}
      }catch(_err){status.textContent='LINK UNAVAILABLE · Retry seal';}
      busy=false;update();
    };
    update();
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics.rayglass_vault={rootSelector:'.rayglass-vault',render};
})();
