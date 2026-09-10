(() => {
  'use strict';
  let m;
  const ornament=(colours,active=[],mini=false)=>`<svg viewBox="-126 -142 252 274" aria-hidden="true"><path d="M-12 -119v-10a12 12 0 0 1 24 0v10" fill="none" stroke="#caa76d" stroke-width="5"/>${m.state.regions.map((points,i)=>{const covered=active.some(c=>m.state.covers[c].regions.includes(i));return `<polygon points="${points.map(p=>p.join(',')).join(' ')}" fill="${covered?'#47515b':colours[i]<0?'#f5efdf':m.state.palette[colours[i]].colour}" stroke="${covered?'#c4cbd0':'#443f3a'}" stroke-width="${mini?.4:.65}"/>`;}).join('')}<circle r="117" fill="none" stroke="#caa76d" stroke-width="3"/></svg>`;
  function update(){
    document.querySelector('#md-object').innerHTML=ornament(m.colours,m.active);
    document.querySelectorAll('[data-kind="cover"]').forEach(el=>{const on=m.active.includes(Number(el.dataset.index));el.classList.toggle('worn',on);el.querySelector('small').textContent=on?'ON · REMOVE':'OFF · APPLY';});
    document.querySelector('#md-count').textContent=`${m.events.length} tool uses`;
  }
  function use(kind,index,source){
    if(m.busy||m.done)return;
    if(kind==='reset'){m.colours=Array(24).fill(-1);m.active=[];}
    else if(kind==='cover'){if(m.active.includes(index))m.active=m.active.filter(x=>x!==index);else m.active.push(index);m.active.sort((a,b)=>a-b);}
    else {const protectedRegions=new Set(m.active.flatMap(c=>m.state.covers[c].regions));m.colours=m.colours.map((c,i)=>protectedRegions.has(i)?c:index);}
    m.events.push({sequence:m.events.length+1,kind,index,input_source:source,colours:[...m.colours],active:[...m.active]});
    document.querySelector('#md-verdict').textContent='WORK IN PROGRESS';
    m.helpers.setReadout(kind==='reset'?'Fresh surface':kind==='paint'?`${m.state.palette[index].name} applied to exposed surface`:'Cover changed','idle');update();
  }
  async function submit(){
    if(m.busy||m.done)return;m.busy=true;
    const current=m;
    const submission=m.helpers.beginAction?.("ship ornament");
    try{
      const response=await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({mechanic_id:m.state.mechanic_id,task_id:m.state.task_id,challenge_id:m.state.challenge_id,events:m.events,colours:m.colours,active:m.active})});
      if(!response.ok)throw Error(`Submission ${response.status}`);
      const verdict=await response.json();
      if(verdict.passed===true){m.done=true;document.querySelector('#md-verdict').textContent='PASS · DISPATCHED';m.helpers.setReadout('PASS','passed');document.querySelector('.md-workshop').classList.add('passed');}
      else if(verdict.passed===false){if(verdict.state)await current.helpers.render(verdict.state);document.querySelector('#md-verdict').textContent='FAIL · NEW ORDER';current.helpers.setReadout('FAIL · Inspect the new order','error');}
      else throw Error('No grading decision');
    }catch(error){current.helpers.setReadout('Submission unavailable · try shipping again','error');}
    finally{m.busy=false;submission?.settle();}
  }
  function render(state,helpers){
    document.body.dataset.mechanic="maskmakers-dispatch";
    m={state,helpers,colours:Array(24).fill(-1),active:[],events:[],busy:false,done:false};
    const mode=state.control_condition?.interaction||'full';
    helpers.app.innerHTML=`<section class="md-workshop" data-interaction="${mode}"><header><div><span>THE SMALL HOURS WORKSHOP</span><h1>Maskmaker’s Dispatch</h1></div><p>Paint. Protect. Reveal.</p></header><div class="md-main"><aside class="md-order"><span>PICTURED ORDER</span><div>${ornament(state.target)}</div><p>Match every colour.<br>Ship with all covers removed.</p><div class="md-stamp">HAND FINISHED<br>ONE OF ONE</div></aside><section class="md-bench"><span>YOUR ORNAMENT</span><div id="md-object" aria-label="ornament"></div><p>${mode==='full'?'Drag the ornament onto a tool.':'Click a tool to use it on the ornament.'}<br>Use a cover again to remove it.</p><div id="md-verdict">WORK IN PROGRESS</div></section><aside class="md-tools"><span>PAINT BATHS · EXPOSED SURFACE ONLY</span><div class="md-paints">${state.palette.map((p,i)=>`<button data-kind="paint" data-index="${i}" aria-label="${p.name} bath"><i style="background:${p.colour}"></i><b>${p.name}</b></button>`).join('')}</div><span>SHAPED COVERS · SHADED AREA IS PROTECTED</span><div class="md-covers">${state.covers.map((c,i)=>`<button data-kind="cover" data-index="${i}" aria-label="${c.name} cover"><div>${ornament(Array(24).fill(-1),[i],true)}</div><b>${c.name}</b><small>OFF · APPLY</small></button>`).join('')}</div></aside></div><footer><button id="md-reset">↺ RESET ORNAMENT</button><div><span id="md-count">0 tool uses</span><div class="readout" data-status="idle">Protect earlier paint beneath a cover.</div></div><button id="md-ship">SHIP ORNAMENT →</button></footer></section>`;
    update();
    document.querySelector('#md-reset').onclick=()=>use('reset',null,'reset_button');
    document.querySelector('#md-ship').onclick=submit;
    if(mode==='simplified')document.querySelectorAll('[data-kind]').forEach(el=>el.onclick=()=>use(el.dataset.kind,Number(el.dataset.index),'tool_click'));
    else {
      const obj=document.querySelector('#md-object');let drag=null,ghost=null;
      obj.addEventListener('pointerdown',event=>{if(event.button!==0||m.busy||m.done||!event.target.closest("polygon,circle,path"))return;event.preventDefault();obj.setPointerCapture(event.pointerId);drag={id:event.pointerId,x:event.clientX,y:event.clientY};ghost=document.createElement('div');ghost.className='md-ghost';ghost.innerHTML=ornament(m.colours,m.active);document.body.appendChild(ghost);ghost.style.left=`${event.clientX}px`;ghost.style.top=`${event.clientY}px`;});
      obj.addEventListener('pointermove',event=>{if(!drag)return;ghost.style.left=`${event.clientX}px`;ghost.style.top=`${event.clientY}px`;});
      const finish=(event,cancel=false)=>{if(!drag)return;const distance=Math.hypot(event.clientX-drag.x,event.clientY-drag.y);ghost.remove();ghost=null;drag=null;if(obj.hasPointerCapture(event.pointerId))obj.releasePointerCapture(event.pointerId);if(cancel)return;const tool=document.elementFromPoint(event.clientX,event.clientY)?.closest('[data-kind]');if(tool&&distance>8)use(tool.dataset.kind,Number(tool.dataset.index),'ornament_drag');};
      obj.addEventListener('pointerup',event=>finish(event));obj.addEventListener('pointercancel',event=>finish(event,true));obj.addEventListener('lostpointercapture',event=>finish(event,true));
    }
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics.maskmakers_dispatch={rootSelector:'.md-workshop',render};
})();
