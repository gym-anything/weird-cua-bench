(() => {
  'use strict';
  const esc = s => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
  async function render(state, helpers) {
    document.body.dataset.mechanic = 'comparator-engine';
    const manual = state.manual_readings === true;
    let measured = !manual;
    const full = state.control_condition?.interaction === 'full';
    const row = state.slides.map(s => s.id), slides = Object.fromEntries(state.slides.map(s => [s.id,s]));
    let cursor=0, advances=0, exchanges=0, readings=manual?0:1, terminal=null, busy=false, pending=null;
    const events=[];
    const actions = manual?['advance','exchange','weigh','seal']:['advance','exchange','seal'];
    const controls = actions.map(a => full
      ? `<div class="ce-control"><div class="ce-lever" data-action="${a}" aria-label="${a} lever"><div class="ce-track"></div><span class="ce-knob"></span><i>↓</i></div><b>${a.toUpperCase()}</b></div>`
      : `<button class="ce-button" data-action="${a}"><b>${a.toUpperCase()}</b></button>`).join('');
    helpers.app.innerHTML = `<section class="ce-engine" data-challenge-id="${esc(state.challenge_id)}" data-interaction="${full?'full':'simplified'}">
      <header class="ce-header"><div><span>THE ENTOMOLOGICAL WEIGHTS OFFICE / No. 09</span><h1>The Comparator Engine</h1></div><div class="ce-seal">STANDARD<br>OF MASS<br><b>⚖</b></div></header>
      <div class="ce-rule">LIGHTEST <span>← &nbsp; Seal the entire frame in ascending weight &nbsp; →</span> HEAVIEST</div>
      <main class="ce-instrument"><div class="ce-rail"><div class="ce-carriage"><div class="ce-lamp"><span>HEAVIER SIDE</span><svg viewBox="0 0 140 58"><path d="M70 22 L55 52 H85 Z" fill="#bc9655"/><g class="ce-beam"><path d="M15 22 H125" stroke="#f8df9a" stroke-width="5"/><circle class="ce-left" cx="18" cy="22" r="10"/><circle class="ce-right" cx="122" cy="22" r="10"/></g></svg></div><div class="ce-windows"><i></i><i></i></div></div><div class="ce-row"></div></div>
      <div class="ce-legend"><span aria-hidden="true"></span><b class="ce-pair-label"></b></div></main>
      <section class="ce-console"><aside><span>MECHANICAL RESERVE</span><div class="ce-counter"></div><p class="ce-pass">PASS 1</p></aside><div class="ce-controls">${controls}</div><aside class="ce-console-spacer" aria-hidden="true"></aside></section>
      <footer><div class="readout" data-status="idle">FRAME OPEN</div></footer>
      <div class="ce-verdict" hidden></div></section>`;
    const root=helpers.app.querySelector('.ce-engine');
    if(manual)root.classList.add('ce-metered');
    const drawMoth = (canvas,s) => {
      const c=canvas.getContext('2d'); c.clearRect(0,0,80,118); c.save();c.translate(40,59);
      const scale=.56+s.size_band*.095; c.scale(scale,scale);c.strokeStyle='#563f23';c.fillStyle='#b7a074';c.lineWidth=1.6;
      for(const side of [-1,1]) {c.save();c.scale(side,1);c.beginPath();c.moveTo(0,-16);c.bezierCurveTo(18,-57,47,-48,37,-9);c.bezierCurveTo(62,23,30,50,4,19);c.closePath();c.fill();c.stroke();
        for(let j=0;j<4;j++){c.beginPath();c.moveTo(0,-10+j*7);c.lineTo(33,-32+j*16);c.stroke();}
        c.fillStyle='#4a3929'; for(let j=0;j<s.spots;j++){c.beginPath();c.ellipse(18+j*5,-20+j*15,3+s.engraving%3,5,0,0,Math.PI*2);c.fill();}c.restore();}
      c.fillStyle='#433222';c.beginPath();c.ellipse(0,0,4,30,0,0,Math.PI*2);c.fill();c.beginPath();c.moveTo(0,-27);c.lineTo(-12,-43);c.moveTo(0,-27);c.lineTo(12,-43);c.stroke();c.restore();
    };
    function draw() {
      root.style.setProperty('--n',row.length);
      root.querySelector('.ce-row').innerHTML=row.map((id,i)=>`<article class="ce-slide ${i===cursor||i===cursor+1?'is-current':''}"><span class="ce-slot">${String(i+1).padStart(2,'0')}</span><canvas width="80" height="118"></canvas><b>${esc(id)}</b>${manual?`<span class="ce-band">SIZE ${slides[id].size_band+1}</span>`:''}</article>`).join('');
      root.querySelectorAll('.ce-slide canvas').forEach((c,i)=>drawMoth(c,slides[row[i]]));
      root.querySelector('.ce-carriage').style.left=`${cursor*100/row.length}%`;
      root.querySelector('.ce-carriage').style.width=`${200/row.length}%`;
      const heavier=measured?(state.runtime_weights[row[cursor]]>state.runtime_weights[row[cursor+1]]?'left':'right'):null;
      root.querySelector('.ce-beam').setAttribute('transform',`rotate(${heavier===null?0:heavier==='left'?-12:12} 70 22)`);
      root.querySelector('.ce-left').setAttribute('fill',heavier==='left'?'#fff3ac':'#645136');
      root.querySelector('.ce-right').setAttribute('fill',heavier==='right'?'#fff3ac':'#645136');
      root.querySelector('.ce-pair-label').textContent=`${row[cursor]} · ${row[cursor+1]} / ${heavier?heavier.toUpperCase()+' HEAVIER':'NOT WEIGHED'}`;
      root.querySelector('.ce-counter').innerHTML=`<b>${state.limits.readings-readings}</b> readings left <br><b>${state.limits.levers-advances-exchanges}</b> ${manual?'carriage moves':'lever pulls'} left`;
      root.querySelector('.ce-pass').textContent=`PASS ${Math.floor(advances/(row.length-1))+1} · ${advances%(row.length-1)===0 && advances?'↻ BELL / WRAPPED':'PAIR '+(cursor+1)+'–'+(cursor+2)}`;
    }
    function show(title,button,callback) {
      const box=root.querySelector('.ce-verdict');box.hidden=false;
      box.innerHTML=`<strong>${esc(title)}</strong>${button?`<button>${esc(button)}</button>`:''}`;
      if(button)box.querySelector('button').onclick=callback;
    }
    async function submit() {
      if(busy)return;busy=true;
      show('CHECKING SEAL');
      try {
        const response=await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(pending)});
        if(!response.ok)throw new Error('Server unavailable');
        const result=await response.json();
        if(result.passed===true){helpers.setReadout('PASS','passed');show('PASS');}
        else if(result.passed===false && result.state){helpers.setReadout('FAIL','error');show('FAIL','LOAD FRESH FRAME',()=>helpers.render(result.state));}
        else throw new Error(result.error||'No grade received');
      } catch(error){busy=false;show('SEAL NOT RECEIVED','RETRY SEAL',submit);}
    }
    function act(type,gesture) {
      if(terminal||busy)return;
      events.push({seq:events.length+1,type,cursor,pair:row.slice(cursor,cursor+2),input_source:full?'lever_drag':'button',...(gesture?{gesture}:{})});
      if(type==='seal')terminal=row.every((a,i)=>!i||state.runtime_weights[row[i-1]]<state.runtime_weights[a])?'sorted':'unsorted_seal';
      else if(type==='weigh'){if(readings>=state.limits.readings)terminal='comparison_exhausted';else{readings++;measured=true;}}
      else if(advances+exchanges>=state.limits.levers)terminal='lever_exhausted';
      else if(type==='advance'&&!manual&&readings>=state.limits.readings)terminal='comparison_exhausted';
      else if(type==='advance'){cursor=(cursor+1)%(row.length-1);advances++;if(manual)measured=false;else readings++;}
      else{[row[cursor],row[cursor+1]]=[row[cursor+1],row[cursor]];exchanges++;}
      draw();
      if(terminal){pending={mechanic_id:state.mechanic_id,task_id:state.task_id,challenge_id:state.challenge_id,control_condition:state.control_condition||null,events,final_order:[...row],counts:{advances,exchanges,readings},completed:terminal==='sorted'};submit();}
      else helpers.setReadout(type==='exchange'?'PAIR EXCHANGED':type==='weigh'?'PAIR WEIGHED':'CARRIAGE ADVANCED','idle');
    }
    root.querySelectorAll('.ce-button').forEach(b=>b.addEventListener('click',()=>act(b.dataset.action)));
    root.querySelectorAll('.ce-lever').forEach(lever=>{
      let drag=null;
      const point=e=>{const b=lever.getBoundingClientRect();return {x:(e.clientX-b.left)/b.width,y:(e.clientY-b.top)/b.height};};
      lever.addEventListener('pointerdown',e=>{
        if(e.button!==0||terminal||busy||!e.target.classList.contains('ce-knob'))return;
        const p=point(e);if(p.x<.25||p.x>.75||p.y<0||p.y>.4)return;
        drag={id:e.pointerId,...p};lever.setPointerCapture(e.pointerId);e.preventDefault();
      });
      lever.addEventListener('pointermove',e=>{if(drag&&drag.id===e.pointerId){lever.querySelector('.ce-knob').style.top=`${Math.max(0,Math.min(70,point(e).y*100-15))}%`;e.preventDefault();}});
      const release=(e,commit)=>{
        if(!drag||drag.id!==e.pointerId)return;const from=drag;drag=null;const p=point(e);
        lever.querySelector('.ce-knob').style.top='';if(lever.hasPointerCapture(e.pointerId))lever.releasePointerCapture(e.pointerId);
        if(commit&&p.x>=.1&&p.x<=.9&&p.y>=.72&&p.y<=1)act(lever.dataset.action,{x0:from.x,y0:from.y,x1:p.x,y1:p.y});
        e.preventDefault();
      };
      lever.addEventListener('pointerup',e=>release(e,true));lever.addEventListener('pointercancel',e=>release(e,false));
      lever.addEventListener('lostpointercapture',()=>{drag=null;lever.querySelector('.ce-knob').style.top='';});
    });
    draw();
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics.comparator_engine={rootSelector:'.ce-engine',render};
})();
