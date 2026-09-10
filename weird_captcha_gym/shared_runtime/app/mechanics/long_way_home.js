(() => {
  'use strict';
  let m, H;
  function inspect() {
    const g=m.state.garden,w=g.width,h=g.height, unseen=new Set(m.board.map((v,i)=>v===0?i:-1).filter(i=>i>=0));
    const neighbors=i=>{const x=i%w,y=Math.floor(i/w);return [[x+1,y],[x,y+1],[x-1,y],[x,y-1]].filter(([a,b])=>a>=0&&a<w&&b>=0&&b<h).map(([a,b])=>b*w+a);};
    let components=0;
    while(unseen.size){components++;const q=[unseen.values().next().value];unseen.delete(q[0]);for(let k=0;k<q.length;k++)for(const j of neighbors(q[k]))if(unseen.has(j)){unseen.delete(j);q.push(j);}}
    const prev=new Map([[g.entrance,null]]),q=[g.entrance];
    for(let k=0;k<q.length;k++)for(const j of neighbors(q[k]))if(!m.board[j]&&!prev.has(j)){prev.set(j,q[k]);q.push(j);}
    const path=[];
    if(prev.has(g.exit)){let i=g.exit;while(i!==null){path.push(i);i=prev.get(i);}path.reverse();}
    return {components,distance:path.length?path.length-1:null,path};
  }
  function draw() {
    const g=m.state.garden;
    document.querySelectorAll('.lwh-tile').forEach(el=>{const i=Number(el.dataset.cell);el.classList.toggle('wall',m.board[i]===1);el.classList.toggle('selected',i===m.selected);});
    const line=document.querySelector('#lwh-route');
    line.setAttribute('points',m.report?m.report.path.map(i=>`${(i%g.width+.5)*48},${(Math.floor(i/g.width)+.5)*48}`).join(' '):'');
    const report=document.querySelector('#lwh-report');
    if(m.report){const r=m.report;const ok=r.components===1&&r.distance===g.target;report.dataset.ok=String(ok);report.innerHTML=`<b>${ok?'GARDEN READY':'DESIGN NEEDS WORK'}</b><div><span>Shortest route</span><strong>${r.distance===null?'BLOCKED':r.distance+' steps'}</strong></div><div><span>Walkable regions</span><strong>${r.components} / 1</strong></div>`;}
    else {report.dataset.ok='';report.innerHTML='<b>UNTESTED CHANGES</b><p>Test the garden to reveal its shortest route and disconnected regions.</p>';}
    document.querySelector('#lwh-selection').textContent=m.mode==='full'?'Drag across tiles to paint.':m.selected===null?'Select a tile in the garden.':`Selected tile: ${m.selected%g.width+1}, ${Math.floor(m.selected/g.width)+1}`;
    document.querySelectorAll('[data-paint]').forEach(el=>el.classList.toggle('chosen',m.mode==='full'&&Number(el.dataset.paint)===m.brush));
  }
  function edit(i,value){
    if(m.busy||m.done||m.locked.has(i)||m.board[i]===value)return;
    m.board[i]=value;m.events.push({kind:'edit',cell:i,value,input_source:m.mode==='full'?'brush':'tile_controls'});m.report=null;H.setReadout('EDITING','idle');draw();
  }
  function test(){if(m.busy||m.done)return;document.querySelector('.lwh').classList.remove('failed');document.querySelector('#lwh-stamp').textContent='DESIGN IN PROGRESS';m.report=inspect();m.events.push({kind:'test',report:m.report});H.setReadout(m.report.components===1&&m.report.distance===m.state.garden.target?'READY TO CERTIFY':'REVISE & RETEST','idle');draw();}
  async function certify(){
    if(m.busy||m.done)return;m.busy=true;document.querySelector('#lwh-certify').disabled=true;
    try {
      const response=await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({mechanic_id:'long_way_home',task_id:m.state.task_id,challenge_id:m.state.challenge_id,interaction:m.mode,events:m.events,board:m.board})});
      const result=await response.json();
      if(result.passed===true){m.done=true;document.querySelector('#lwh-stamp').textContent='PASS · WELCOME HOME';document.querySelector('.lwh').classList.add('passed');H.setReadout('PASS','passed');}
      else if(result.passed===false){
        const fresh=result.state&&result.state.challenge_id!==m.state.challenge_id;
        if(result.state)await H.render(result.state);
        m.busy=false;document.querySelector('#lwh-certify').disabled=false;
        const feedback=fresh?'FAIL · FRESH GARDEN':'FAIL · REVISE & RETRY';
        document.querySelector('.lwh').classList.add('failed');document.querySelector('#lwh-stamp').textContent=feedback;H.setReadout(feedback,'error');
      }
      else throw Error('No grade');
    }catch(e){m.busy=false;document.querySelector('#lwh-certify').disabled=false;H.setReadout('CONNECTION ERROR · TRY AGAIN','error');}
  }
  async function render(state,helpers){
    H=helpers;const g=state.garden;const mode=state.control_condition?.interaction||'full';
    m={state,mode,board:[...g.initial],events:[],locked:new Set([...g.locked,g.entrance,g.exit]),brush:1,selected:null,report:null,busy:false,done:false};
    document.body.dataset.mechanic='long-way-home';
    H.app.innerHTML=`<section class="lwh" data-challenge-id="${H.text(state.challenge_id)}">
      <header><div><span class="lwh-eyebrow">THE GARDEN DESIGN OFFICE · STUDY ${g.width} × ${g.height}</span><h1>The Long Way Home</h1><p>A little distance makes a lovely walk.</p></div><div class="lwh-seal">GARDEN<br><b>WORKS</b><br>FIELD STUDIO</div></header>
      <main><div class="lwh-scene"><div class="lwh-garden" style="--w:${g.width};--h:${g.height}"><div class="lwh-grid">${g.initial.map((v,i)=>`<div class="lwh-tile ${v?'wall':''} ${m.locked.has(i)?'fixed':''} ${i===g.entrance?'entrance':''} ${i===g.exit?'home':''}" data-cell="${i}"><i class="lwh-hedge"></i>${i===g.entrance?'<span class="lwh-gate">IN</span>':i===g.exit?'<span class="lwh-house">⌂</span>':g.locked.includes(i)?'<span class="lwh-stone">◆</span>':''}</div>`).join('')}</div><svg viewBox="0 0 ${g.width*48} ${g.height*48}" preserveAspectRatio="none"><polyline id="lwh-route" points=""/></svg></div><div class="lwh-legend"><span>◆ Fixed stone planter</span><span>IN Entrance</span><span>⌂ Home</span><span class="lwh-thread">━ Test route</span></div><div id="lwh-stamp">DESIGN IN PROGRESS</div></div>
      <aside><div class="lwh-brief"><span>THE COMMISSION</span><strong>${g.target}<small>steps</small></strong><p>Make the <b>shortest</b> entrance-to-home walk exactly this long.</p><p>Every floor tile must belong to <b>one connected area</b>. Walks use tile edges, never diagonals.</p></div><div class="lwh-tools"><label>${mode==='full'?'CHOOSE A BRUSH':'APPLY TO SELECTED TILE'}</label><div><button data-paint="1">▰ Wall</button><button data-paint="0">◇ Floor</button></div><small id="lwh-selection"></small></div><div id="lwh-report"></div><button id="lwh-test">↝ Test garden</button></aside></main>
      <footer><button id="lwh-reset">↺ Restore garden</button><div class="readout" data-status="idle">DESIGN IN PROGRESS</div><button id="lwh-certify">Certify design →</button></footer></section>`;
    const grid=document.querySelector('.lwh-grid');let dragging=false,last=null;
    function cellAt(e){const r=grid.getBoundingClientRect();const x=(e.clientX-r.left)/r.width*g.width,y=(e.clientY-r.top)/r.height*g.height;return [x,y];}
    function stroke(p){if(last){const dx=p[0]-last[0],dy=p[1]-last[1],n=Math.max(1,Math.ceil(Math.max(Math.abs(dx),Math.abs(dy))*8));for(let k=1;k<=n;k++){const x=Math.floor(last[0]+dx*k/n),y=Math.floor(last[1]+dy*k/n);if(x>=0&&x<g.width&&y>=0&&y<g.height)edit(y*g.width+x,m.brush);}}else {const x=Math.floor(p[0]),y=Math.floor(p[1]);if(x>=0&&x<g.width&&y>=0&&y<g.height)edit(y*g.width+x,m.brush);}last=p;}
    grid.addEventListener('pointerdown',e=>{if(e.button!==0||m.busy||m.done)return;e.preventDefault();document.querySelector('.lwh').classList.remove('failed');document.querySelector('#lwh-stamp').textContent='DESIGN IN PROGRESS';const p=cellAt(e);if(mode==='simplified'){m.selected=Math.floor(p[1])*g.width+Math.floor(p[0]);draw();return;}dragging=true;last=null;grid.setPointerCapture(e.pointerId);stroke(p);});
    grid.addEventListener('pointermove',e=>{if(dragging)stroke(cellAt(e));});
    grid.addEventListener('pointerup',e=>{if(dragging)stroke(cellAt(e));dragging=false;last=null;});
    grid.addEventListener('pointercancel',()=>{dragging=false;last=null;});
    grid.addEventListener('lostpointercapture',()=>{dragging=false;last=null;});
    document.querySelectorAll('[data-paint]').forEach(el=>el.onclick=()=>{if(mode==='full'){m.brush=Number(el.dataset.paint);draw();}else if(m.selected!==null)edit(m.selected,Number(el.dataset.paint));});
    document.querySelector('#lwh-test').onclick=test;
    document.querySelector('#lwh-reset').onclick=()=>{if(m.busy||m.done)return;document.querySelector('.lwh').classList.remove('failed');m.board=[...g.initial];m.events.push({kind:'reset'});m.report=null;m.selected=null;document.querySelector('#lwh-stamp').textContent='DESIGN RESTORED';H.setReadout('RESTORED','idle');draw();};
    document.querySelector('#lwh-certify').onclick=certify;draw();
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics.long_way_home={rootSelector:'.lwh',render};
})();
