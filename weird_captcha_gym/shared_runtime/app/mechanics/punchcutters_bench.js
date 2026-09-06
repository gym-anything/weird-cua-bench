(() => {
  'use strict';
  const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;');
  const flatten=ns=>ns.flatMap((a,i)=>{const b=ns[(i+1)%ns.length];return Array.from({length:48},(_,k)=>{const t=k/48,u=1-t;return [0,1].map(j=>u**3*a[j]+3*u*u*t*(a[j]+a[j+2])+3*u*t*t*(b[j]-b[j+2])+t**3*b[j]);});});
  const dist=(p,a,b)=>{const dx=b[0]-a[0],dy=b[1]-a[1],den=dx*dx+dy*dy,t=den?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)):0;return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy);};
  const deviation=(ns,ms)=>{const a=flatten(ns),b=flatten(ms);const directed=(x,y)=>Math.max(...x.map(p=>Math.min(...y.map((v,i)=>dist(p,v,y[(i+1)%y.length])))));return Math.max(directed(a,b),directed(b,a));};
  function render(state,helpers) {
    document.body.dataset.mechanic='punchcutters_bench';
    const b=state.bench,full=(state.control_condition?.interaction||'full')==='full';
    let nodes=[],closed=false,stage=1,selected=-1,pending=null,gesture=null,busy=false,retryState=null;
    const events=[],positions=[...b.initial_positions];
    const record=(kind,detail={})=>events.push({sequence:events.length+1,kind,...detail});
    helpers.app.innerHTML=`<section class="punch-bench" data-stage="1" data-interaction="${full?'full':'simplified'}" data-challenge-id="${esc(state.challenge_id)}">
      <header><div><span class="punch-eyebrow">THE LETTER FOUNDRY &nbsp; / &nbsp; STUDY No. 01</span><h1>Punchcutter’s Bench</h1></div><div class="punch-stages"><b class="punch-current">01 / CUT</b><span>02 / SPACE</span></div></header>
      <div class="punch-work"><aside><span class="punch-eyebrow">YOUR COMMISSION</span><h2 class="punch-title">Cut the master.</h2><div class="punch-tools">${full?'': '<button data-tool="corner" class="chosen">Corner</button><button data-tool="smooth">Smooth</button>'}<button class="punch-undo">Undo</button><button class="punch-close">Close outline</button></div><p class="punch-budget"></p><div class="punch-legend"><i></i> Master outline<br><i></i> Your cut</div></aside>
      <div class="punch-paper"><canvas width="800" height="410" aria-label="Glyph workbench"></canvas><div class="punch-caption"><span>ORIGINAL PROCEDURAL TYPE</span><span class="punch-paper-status">PEN / OPEN PATH</span></div></div></div>
      <footer><div class="readout" data-status="idle"></div><span class="punch-feedback"></span><button class="punch-proof">Proof cut →</button><button class="punch-certify" hidden>Certify spacing →</button><button class="punch-retry" hidden>Fresh bench →</button></footer></section>`;
    const root=helpers.app.querySelector('.punch-bench'),canvas=root.querySelector('canvas'),ctx=canvas.getContext('2d');
    canvas.tabIndex=0;
    let tool='corner';const $=s=>root.querySelector(s); const feedback=s=>$('.punch-feedback').textContent=s;
    function path(ns,close=true){if(!ns.length)return;ctx.beginPath();ctx.moveTo(ns[0][0],ns[0][1]);for(let i=1;i<ns.length+(close?1:0);i++){const a=ns[i-1],c=ns[i%ns.length];ctx.bezierCurveTo(a[0]+a[2],a[1]+a[3],c[0]-c[2],c[1]-c[3],c[0],c[1]);}if(close)ctx.closePath();}
    function polygons(){return b.glyphs.map((g,i)=>i===b.cut_index?flatten(nodes).map(([x,y])=>[(x-b.glyph_origin[0])/b.glyph_scale[0]*g.width,(y-b.glyph_origin[1])/b.glyph_scale[1]*140]):g.polygon);}
    function draw(){
      ctx.clearRect(0,0,800,410);
      if(stage===1){path(b.master);ctx.fillStyle='#e8e4d9';ctx.fill();ctx.strokeStyle='#a3a091';ctx.lineWidth=2;ctx.stroke();
        const live=gesture?[...nodes,[...gesture.anchor,gesture.tip[0]-gesture.anchor[0],gesture.tip[1]-gesture.anchor[1]]]:nodes;
        if(live.length){path(live,closed);ctx.strokeStyle='#b5442c';ctx.lineWidth=2.5;ctx.stroke();if(closed){ctx.fillStyle='#b5442c22';ctx.fill();}}
        for(const a of live){if(a[2]||a[3]){ctx.beginPath();ctx.moveTo(a[0]-a[2],a[1]-a[3]);ctx.lineTo(a[0]+a[2],a[1]+a[3]);ctx.strokeStyle='#b5442c';ctx.lineWidth=1;ctx.stroke();for(const sign of [-1,1]){ctx.beginPath();ctx.arc(a[0]+sign*a[2],a[1]+sign*a[3],4,0,Math.PI*2);ctx.fillStyle='#b5442c';ctx.fill();}}ctx.fillStyle='#fffcf1';ctx.fillRect(a[0]-4,a[1]-4,8,8);ctx.strokeStyle='#b5442c';ctx.strokeRect(a[0]-4,a[1]-4,8,8);}
        if(pending){ctx.beginPath();ctx.arc(...pending,7,0,Math.PI*2);ctx.strokeStyle='#b5442c';ctx.stroke();}
        $('.punch-budget').textContent=`${nodes.length} / ${b.node_budget} nodes used`;
      }else{polygons().forEach((poly,i)=>{ctx.beginPath();poly.forEach(([x,y],j)=>j?ctx.lineTo(x+positions[i],y+124):ctx.moveTo(x+positions[i],y+124));ctx.closePath();ctx.fillStyle=i===selected?'#b5442c':'#252b29';ctx.fill();ctx.font='11px monospace';ctx.textAlign='center';ctx.fillStyle='#7e8077';ctx.fillText(i===0||i===positions.length-1?'FIXED':i===selected?'SELECTED':'',positions[i]+b.glyphs[i].width/2,305);});}
    }
    const point=e=>{const r=canvas.getBoundingClientRect();return [Math.round(Math.max(0,Math.min(800,(e.clientX-r.left)*800/r.width))*100)/100,Math.round(Math.max(0,Math.min(410,(e.clientY-r.top)*410/r.height))*100)/100];};
    function add(a,t){nodes.push([...a,t[0]-a[0],t[1]-a[1]]);record('node',{anchor:a,tip:t,input_source:full?'pen_drag':'pen_clicks'});feedback('');helpers.setReadout('','idle');draw();}
    function moveLetter(i,x,source,start=positions[i]){x=Math.round(Math.max(20,Math.min(720,x))*100)/100;positions[i]=x;if(start!==x)record('letter',{index:i,start,end:x,input_source:source});draw();}
    function hit(p){const ps=polygons();for(let i=ps.length-2;i>0;i--){const poly=ps[i];ctx.beginPath();poly.forEach(([x,y],j)=>j?ctx.lineTo(x+positions[i],y+124):ctx.moveTo(x+positions[i],y+124));ctx.closePath();if(ctx.isPointInPath(...p))return i;}return -1;}
    canvas.addEventListener('pointerdown',e=>{
      if(busy||retryState)return;e.preventDefault();canvas.focus();const p=point(e);
      if(stage===1){if(closed||nodes.length>=b.node_budget)return;
        if(!full){if(tool==='corner'){add(p,p);}else if(!pending){pending=p;feedback('');draw();}else{add(pending,p);pending=null;draw();}return;}
        gesture={anchor:p,tip:p};canvas.setPointerCapture(e.pointerId);draw();
      }else{if(!full&&selected>0){moveLetter(selected,p[0]-b.glyphs[selected].width/2,'letter_place');selected=-1;draw();return;}
        selected=hit(p);if(full&&selected>0){gesture={index:selected,mouse:p[0],start:positions[selected]};canvas.setPointerCapture(e.pointerId);}draw();}
    });
    canvas.addEventListener('pointermove',e=>{if(!gesture)return;const p=point(e);if(stage===1)gesture.tip=p;else positions[gesture.index]=Math.round(Math.max(20,Math.min(720,gesture.start+p[0]-gesture.mouse))*100)/100;draw();});
    canvas.addEventListener('pointerup',e=>{if(!gesture)return;const p=point(e),g=gesture;gesture=null;if(stage===1)add(g.anchor,p);else moveLetter(g.index,Math.max(20,Math.min(720,g.start+p[0]-g.mouse)),'letter_drag',g.start);});
    canvas.addEventListener('pointercancel',()=>{if(gesture&&stage===2)positions[gesture.index]=gesture.start;gesture=null;draw();});
    root.tabIndex=0;root.addEventListener('keydown',e=>{if(!full||stage!==2||busy||retryState||selected<1||!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();if(e.repeat)return;if(gesture){const g=gesture,current=positions[g.index];moveLetter(g.index,current,'letter_drag',g.start);g.mouse+=current-g.start;g.start=current;}const d=(e.key==='ArrowLeft'?-1:1)*(e.shiftKey?10:1);if(positions[selected]+d>=20&&positions[selected]+d<=720)moveLetter(selected,positions[selected]+d,'letter_key');if(gesture)gesture.start=positions[selected];});
    root.querySelectorAll('[data-tool]').forEach(el=>el.onclick=()=>{tool=el.dataset.tool;pending=null;root.querySelectorAll('[data-tool]').forEach(x=>x.classList.toggle('chosen',x===el));draw();});
    $('.punch-undo').onclick=()=>{if(stage!==1||busy)return;if(pending){pending=null;draw();return;}if(!nodes.length)return;if(closed)closed=false;else nodes.pop();record('undo',{input_source:'undo_button'});feedback('');helpers.setReadout('','idle');$('.punch-paper-status').textContent='PEN / OPEN PATH';draw();};
    $('.punch-close').onclick=()=>{if(stage!==1||closed||nodes.length<3||pending||gesture)return;closed=true;record('close',{input_source:'close_button'});$('.punch-paper-status').textContent='PEN / CLOSED PATH';draw();};
    $('.punch-proof').onclick=()=>{if(!closed){feedback('');helpers.setReadout('FAIL','error');return;}const d=deviation(nodes,b.master);if(d>b.parameters.outline_tolerance){feedback('');helpers.setReadout('FAIL','error');return;}record('proof',{input_source:'proof_button'});stage=2;root.dataset.stage='2';$('.punch-title').textContent='Space the word.';$('.punch-tools').hidden=true;$('.punch-budget').textContent='';$('.punch-legend').hidden=true;$('.punch-paper-status').textContent='SPACING';$('.punch-stages').innerHTML='<span>01 / CUT</span><b class="punch-current">02 / SPACE</b>';$('.punch-proof').hidden=true;$('.punch-certify').hidden=false;feedback('');helpers.setReadout('','idle');draw();};
    $('.punch-certify').onclick=async()=>{if(busy||stage!==2)return;busy=true;record('certify',{input_source:'certify_button'});try{const response=await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({mechanic_id:state.mechanic_id,task_id:state.task_id,challenge_id:state.challenge_id,events})});const outcome=await response.json();if(!response.ok||typeof outcome.passed!=='boolean'||(!outcome.passed&&(!outcome.state||typeof outcome.state!=='object')))throw new Error('Invalid submission response');if(outcome.passed){helpers.setReadout('PASS','passed');feedback('');root.classList.add('is-passed');}else{helpers.setReadout('FAIL','error');feedback('');retryState=outcome.state;$('.punch-retry').hidden=false;}$('.punch-certify').hidden=true;}catch(error){events.pop();busy=false;retryState=null;$('.punch-certify').hidden=false;$('.punch-retry').hidden=true;feedback('Submission unavailable.');}};
    $('.punch-retry').onclick=()=>{if(retryState)helpers.render(retryState);};draw();
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics.punchcutters_bench={render,rootSelector:'.punch-bench'};
})();
