(() => {
  'use strict';
  const EPS=1e-7, sub=(a,b)=>[a[0]-b[0],a[1]-b[1]], add=(a,b)=>[a[0]+b[0],a[1]+b[1]], mul=(a,s)=>[a[0]*s,a[1]*s], dot=(a,b)=>a[0]*b[0]+a[1]*b[1], cross=(a,b)=>a[0]*b[1]-a[1]*b[0], dist=(a,b)=>Math.hypot(...sub(a,b));
  function intersect(a,b){
    if(a.kind==='circle'&&b.kind==='line') return intersect(b,a);
    const p=a.p,q=b.p;
    if(a.kind===b.kind&&a.kind==='line') {const u=sub(a.q,p),v=sub(b.q,q),den=cross(u,v);return Math.abs(den)<EPS?[]:[add(p,mul(u,cross(sub(q,p),v)/den))];}
    if(a.kind==='line') {const u=sub(a.q,p),v=sub(p,q),aa=dot(u,u),bb=2*dot(u,v),cc=dot(v,v)-b.r*b.r,dd=bb*bb-4*aa*cc;if(dd < -EPS)return [];return [(-bb-Math.sqrt(Math.max(0,dd)))/(2*aa),(-bb+Math.sqrt(Math.max(0,dd)))/(2*aa)].slice(0,Math.abs(dd)<EPS?1:2).map(t=>add(p,mul(u,t)));}
    const d=dist(p,q);if(d<EPS||d>a.r+b.r+EPS||d<Math.abs(a.r-b.r)-EPS)return [];
    const x=(a.r*a.r-b.r*b.r+d*d)/(2*d),h=Math.sqrt(Math.max(0,a.r*a.r-x*x)),u=mul(sub(q,p),1/d),base=add(p,mul(u,x)),v=[-u[1],u[0]];
    return [add(base,mul(v,h)),add(base,mul(v,-h))].slice(0,h<EPS?1:2);
  }
  function build(world,ops,givens){
    const points=Object.fromEntries((givens||world.givens).map((p,i)=>['g'+i,p])),objects=[],marked=[];
    for(const op of [...world.initial_objects,...ops]){
      const p=points[op.a];if(!p)throw Error('Missing intersection');
      if(op.kind==='point'){marked.push(op.a);continue;}
      const q=points[op.b];if(!q||dist(p,q)<EPS)throw Error('Choose two different points');
      const obj={kind:op.kind,p,q,r:dist(p,q)},j=objects.length;
      objects.forEach((o,i)=>intersect(o,obj).forEach((pt,k)=>{if(pt.every(x=>Number.isFinite(x)&&Math.abs(x)<1e7))points[`x${i}_${j}_${k}`]=pt;}));objects.push(obj);
    }
    return {points,objects,marked};
  }
  function target(world,givens){
    const [a,b,c]=givens,mid=mul(add(a,b),.5),ab=sub(b,a),ac=sub(c,a);
    if(['midpoint','bisector'].includes(world.goal))return {p:mid,q:add(mid,[-ab[1],ab[0]])};
    const den=2*cross(ab,ac),u=[(dot(ab,ab)*ac[1]-dot(ac,ac)*ab[1])/den,(ab[0]*dot(ac,ac)-ac[0]*dot(ab,ab))/den],o=add(a,u);
    if(world.goal==='circumcenter')return {p:o};
    if(world.goal==='orthocenter')return {p:sub(add(add(a,b),c),mul(o,2))};
    const ll=[dist(b,c),dist(a,c),dist(a,b)],p=mul(add(add(mul(a,ll[0]),mul(b,ll[1])),mul(c,ll[2])),1/ll.reduce((x,y)=>x+y));return {p,r:Math.abs(cross(ab,sub(p,a)))/dist(a,b)};
  }
  let m,h;
  function render(state,helpers){
    h=helpers; document.body.dataset.mechanic='compass-vault';
    m={state,ops:[],givens:state.world.givens.map(p=>[...p]),tool:'point',selected:null,hover:null,drag:null,scale:.8,offset:[84,54],terminal:false,busy:false};
    h.app.innerHTML=`<section class="compass-vault"><header><div><small>GEOMETRIC INSTRUMENTS / No. 03</small><h1>Compass Vault</h1></div><div class="cv-seal">∠<span>EXACT BY CONSTRUCTION</span></div></header><div class="cv-work"><aside><small>COMMISSION</small><h2>${h.text(state.prompt)}</h2><p>The dashed gold figure is the goal. Only givens and intersections can anchor a construction.</p><div class="cv-tools"><button data-tool="point"><b>·</b><span>Place point<small>Mark a crossing</small></span></button><button data-tool="line"><b>╱</b><span>Straightedge<small>Line through two points</small></span></button><button data-tool="circle"><b>○</b><span>Compass<small>Centre → radius point</small></span></button></div><p id="cv-gesture"></p><div class="cv-budget"><strong id="cv-count">0</strong><span> / ${state.world.move_budget} strokes</span></div><p class="cv-note">Test checks the same construction with eight new triangles. Eyeballing does not unlock the vault.</p></aside><div class="cv-paper"><canvas id="cv-canvas" width="840" height="540" aria-label="Geometric construction canvas"></canvas><div class="cv-paper-tools"><button id="cv-home">Reset view</button><span>Wheel to zoom · Point tool: drag a given to explore</span></div><div id="cv-verdict"></div></div></div><footer><button id="cv-reset">Clear construction</button><div class="readout" data-status="idle">Choose an instrument</div><button id="cv-test">TEST CONSTRUCTION →</button></footer></section>`;
    const canvas=document.getElementById('cv-canvas'),ctx=canvas.getContext('2d');
    const full=state.control_condition?.interaction!=='simplified';
    const screen=p=>add(mul(p,m.scale),m.offset);
    const world=p=>mul(sub(p,m.offset),1/m.scale);
    const position=e=>{const r=canvas.getBoundingClientRect();return [(e.clientX-r.left)*840/r.width,(e.clientY-r.top)*540/r.height];};
    function pick(pos){let best=null,d=13;for(const [ref,p] of Object.entries(m.geometry.points)){const dd=dist(screen(p),pos);if(dd<d-1e-5){best=ref;d=dd;}}return best;}
    function paint(){
      m.geometry=build(state.world,m.ops,m.givens);
      ctx.clearRect(0,0,840,540);ctx.fillStyle='#f5efdf';ctx.fillRect(0,0,840,540);
      ctx.fillStyle='#d6cfbe';for(let x=24;x<840;x+=24)for(let y=24;y<540;y+=24){ctx.beginPath();ctx.arc(x,y,.65,0,Math.PI*2);ctx.fill();}
      const curve=(o,color,width,dashed=false)=>{ctx.strokeStyle=color;ctx.lineWidth=width;ctx.setLineDash(dashed?[6,6]:[]);ctx.beginPath();const p=screen(o.p);if(o.kind==='circle'){ctx.arc(...p,o.r*m.scale,0,Math.PI*2);}else{const v=mul(sub(o.q,o.p),2000/dist(o.q,o.p));ctx.moveTo(...screen(sub(o.p,v)));ctx.lineTo(...screen(add(o.p,v)));}ctx.stroke();ctx.setLineDash([]);};
      m.geometry.objects.forEach((o,i)=>curve(o,i<state.world.initial_objects.length?'#9b947f':'#315e66',i<state.world.initial_objects.length?1.4:1.65));
      if(['midpoint','bisector'].includes(state.world.goal)){ctx.strokeStyle='#202c2b';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(...screen(m.givens[0]));ctx.lineTo(...screen(m.givens[1]));ctx.stroke();}
      const t=target(state.world,m.givens);if(state.world.goal==='bisector')curve({kind:'line',...t},'#b88832',2,true);else if(t.r)curve({kind:'circle',...t},'#b88832',2,true);else{ctx.strokeStyle='#b88832';ctx.setLineDash([3,4]);ctx.lineWidth=2;ctx.beginPath();ctx.arc(...screen(t.p),12,0,Math.PI*2);ctx.stroke();ctx.setLineDash([]);}
      const seen=[];for(const [ref,p] of Object.entries(m.geometry.points)){const s=screen(p);if(s[0]<0||s[0]>840||s[1]<0||s[1]>540||seen.some(q=>dist(q,s)<1))continue;seen.push(s);ctx.beginPath();ctx.arc(...s,ref.startsWith('g')?6:4,0,Math.PI*2);ctx.fillStyle=ref.startsWith('g')?'#202c2b':'#f5efdf';ctx.fill();ctx.strokeStyle='#315e66';ctx.lineWidth=1.5;ctx.stroke();}
      for(const ref of m.geometry.marked){ctx.fillStyle='#b88832';ctx.beginPath();ctx.arc(...screen(m.geometry.points[ref]),6,0,Math.PI*2);ctx.fill();}
      for(const ref of [m.hover,m.selected])if(ref&&m.geometry.points[ref]){ctx.strokeStyle='#cf693f';ctx.lineWidth=2;ctx.beginPath();ctx.arc(...screen(m.geometry.points[ref]),11,0,Math.PI*2);ctx.stroke();}
      document.querySelectorAll('[data-tool]').forEach(b=>b.classList.toggle('active',b.dataset.tool===m.tool));
      document.getElementById('cv-count').textContent=m.ops.filter(o=>o.kind!=='point').length;
      document.getElementById('cv-gesture').textContent=m.tool==='point'?'Click a crossing to mark it. Drag a black given to reshape the construction.':full?'Drag from the first point to the second.':'Click the first point, then the second.';
    }
    function act(a,b){if(m.terminal||m.busy||!a)return;
      const op={kind:m.tool,a,input_source:m.tool==='point'?'point_click':full?'canvas_drag':'canvas_clicks'};
      if(m.tool!=='point'){if(!b||dist(m.geometry.points[a],m.geometry.points[b])<EPS){h.setReadout('Choose two different points','error');return;}op.b=b;}
      if(m.ops.some(o=>o.kind===op.kind&&o.a===a&&o.b===op.b)){h.setReadout('That construction already exists','idle');return;}
      if(m.ops.filter(o=>o.kind!=='point').length>=state.world.move_budget&&op.kind!=='point'){h.setReadout('STROKE BUDGET SPENT · Test or clear','error');return;}
      if(op.kind==='point')m.ops=m.ops.filter(o=>o.kind!=='point');
      m.ops.push(op);m.selected=null;paint();h.setReadout(op.kind==='point'?'POINT MARKED':'INTERSECTIONS AVAILABLE','idle');
    }
    canvas.addEventListener('pointerdown',e=>{if(e.button!==0||m.terminal||m.busy)return;e.preventDefault();canvas.setPointerCapture(e.pointerId);const pos=position(e),ref=pick(pos);m.drag={ref,pos};if(m.tool!=='point'&&full)m.selected=ref;paint();});
    canvas.addEventListener('pointermove',e=>{const pos=position(e);m.hover=pick(pos);if(m.drag&&m.tool==='point'&&m.drag.ref?.startsWith('g')&&dist(pos,m.drag.pos)>4){const i=Number(m.drag.ref.slice(1)),p=world(pos),base=state.world.givens[i];const candidate=m.givens.map(p=>[...p]);candidate[i]=p.map((v,j)=>Math.max(base[j]-28,Math.min(base[j]+28,v)));try{build(state.world,m.ops,candidate);m.givens=candidate;m.drag.moved=true;}catch(_){h.setReadout('That position makes a crossing undefined','error');}}paint();});
    canvas.addEventListener('pointerup',e=>{if(!m.drag)return;const start=m.drag; m.drag=null;const ref=pick(position(e));if(start.moved){h.setReadout('BASE POINT MOVED · dependent geometry rebuilt','idle');paint();return;}if(m.tool==='point')act(ref);else if(full)act(start.ref,ref);else if(ref){if(m.selected)act(m.selected,ref);else{m.selected=ref;paint();}}});
    canvas.addEventListener('pointercancel',()=>{m.drag=null;m.selected=null;paint();});
    canvas.addEventListener('wheel',e=>{e.preventDefault();const pos=position(e),p=world(pos);m.scale=Math.max(.35,Math.min(3,m.scale*(e.deltaY<0?1.15:1/1.15)));m.offset=sub(pos,mul(p,m.scale));paint();},{passive:false});
    document.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>{m.tool=b.dataset.tool;m.selected=null;paint();});
    document.getElementById('cv-home').onclick=()=>{m.scale=.8;m.offset=[84,54];paint();};
    document.getElementById('cv-reset').onclick=()=>{if(m.busy||m.terminal)return;m.ops=[];m.givens=state.world.givens.map(p=>[...p]);m.selected=null;paint();h.setReadout('CONSTRUCTION CLEARED','idle');};
    document.getElementById('cv-test').onclick=async()=>{if(m.busy||m.terminal)return;m.busy=true;h.setReadout('TESTING INVARIANT…','idle');try{const payload={mechanic_id:state.mechanic_id,task_id:state.task_id,challenge_id:state.challenge_id,control_condition:state.control_condition,operations:m.ops,displayed_givens:m.givens};const response=await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),result=await response.json();if(result.passed===true){m.terminal=true;document.getElementById('cv-verdict').innerHTML='<strong>VAULT OPEN</strong><span>Construction survives every check</span>';h.setReadout('PASS','passed');}else if(result.passed===false){if(result.state)await h.render(result.state);h.setReadout('FAIL · Fresh commission','error');}else{m.busy=false;h.setReadout('Test unavailable · try again','error');}}catch(_){m.busy=false;h.setReadout('Connection interrupted · try again','error');}};
    paint();
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics.compass_vault={rootSelector:'.compass-vault',render};
})();
