(() => {
  'use strict';
  const BODY = [[42,0],[34,-12],[10,-17],[-18,-10],[-28,-5],[-34,-19],[-47,-25],[-42,-9],[-35,0],[-42,9],[-47,25],[-34,19],[-28,5],[-18,10],[10,17],[34,12]];
  const SPECIES = ['Crescent', 'Harbour', 'Deepwater'];
  let current;
  function render(state, helpers) {
    document.body.dataset.mechanic = "fluke-census";
    if (current) { current.dead = true; window.removeEventListener('keydown', current.key); }
    const m = {state, epoch:0, photos:[], events:[], aim:null, started:performance.now(), epochStart:0, dead:false, busy:false};
    current = m;
    window.flukeCensusModel = m;
    const mode = state.control_condition?.interaction || 'full';
    helpers.app.innerHTML = `<main class="fluke-census" data-interaction="${mode}">
      <header><div><small>NORTH SOUND FIELD STATION / SURVEY 07</small><h1>Fluke Census<span>∿</span></h1></div><div class="fc-log"><b id="fc-count">00</b><small>PHOTOGRAPHS</small></div></header>
      <div class="fc-work"><section class="fc-water"><canvas id="fc-sea" width="820" height="430" aria-label="Pod survey and inspection lens"></canvas><div class="fc-water-label">NORTH SOUND <span>↗ N</span></div></section>
      <aside><small>INSPECTION / ONE INDIVIDUAL</small><canvas id="fc-card" width="280" height="220"></canvas><p id="fc-inspect">Place the lens over an animal.</p><div class="fc-list"><small>CENSUS LIST</small><div id="fc-species"></div></div><p class="fc-rule">No marks. No contact sheet.</p></aside></div>
      <footer><div class="fc-input">${mode==='full'?'<b>MOVE POINTER · INSPECT</b><span>SPACE · PHOTOGRAPH</span>':'<label>Lens X <input id="fc-x" type="number" min="0" max="820" value="410"></label><label>Y <input id="fc-y" type="number" min="0" max="430" value="215"></label><button id="fc-aim">Position lens</button><button id="fc-photo">Photograph</button>'}</div><button id="fc-submit">Census complete →</button></footer>
      <div class="fc-bottom"><span id="fc-note">A duplicate or off-list photograph ends this survey.</span><div class="readout" data-status="idle"></div></div>
    </main>`;
    const root = helpers.app.querySelector('.fluke-census');
    const sea = root.querySelector('#fc-sea'), ctx=sea.getContext('2d');
    const card=root.querySelector('#fc-card'), c=card.getContext('2d');
    const animals=new Map(state.animals.map(a=>[a.id,a]));
    const now=()=> Math.max(0, performance.now()-m.started);
    function record(type, source, data={}, t=now()) { m.events.push({seq:m.events.length+1,type,source,t,...data}); }
    function outline(a) {
      const vertices=BODY.slice(0,7).map(v=>[...v]);
      const center=-35+2*a.species;
      for(let side=0;side<2;side++) {
        const from=side ? [center,0] : [-47,-25];
        const to=side ? [-47,25] : [center,0];
        for(let i=0;i<4;i++) {
          for(const [f,inset] of [[.15,0],[.45,a.notches[side*4+i]*.10],[.75,0]]) {
            const t=(i+f)/4;
            vertices.push([from[0]+(to[0]-from[0])*t+inset,from[1]+(to[1]-from[1])*t]);
          }
        }
        vertices.push(to);
      }
      return vertices.concat(BODY.slice(11));
    }
    function path(a) {
      const p=new Path2D();outline(a).forEach((v,i)=>i?p.lineTo(...v):p.moveTo(...v));p.closePath();return p;
    }
    function animal(g,a) {
      g.fillStyle='#405e60';g.strokeStyle='#193b40';g.lineWidth=.35;
      const shape=path(a);g.fill(shape);g.stroke(shape);
    }
    function fluke(g,a,x,y,size=1) {
      g.save();g.translate(x,y);g.scale(size*4,size*4);g.rotate(-Math.PI/2);
      g.translate(37,0);g.beginPath();g.rect(-53,-29,25,58);g.clip();animal(g,a);g.restore();
    }
    state.listed_species.forEach(species=> {
      const row=document.createElement('div');row.className='fc-species';
      const cv=document.createElement('canvas');cv.width=92;cv.height=43;
      fluke(cv.getContext('2d'),{species,notches:Array(8).fill(0)},46,21,.36);
      row.append(cv,document.createTextNode(SPECIES[species]));root.querySelector('#fc-species').append(row);
    });
    function pose(item,t) {const p=item.phase+t/1000*item.omega;return {x:item.x+16*Math.sin(p),y:item.y+12*Math.cos(p),angle:item.angle*Math.PI/180,scale:item.scale};}
    function find(t) {
      if(!m.aim)return null;
      for(const item of [...state.layouts[m.epoch]].reverse()) {
        const p=pose(item,t-m.epochStart),dx=(m.aim.x-p.x)/p.scale,dy=(m.aim.y-p.y)/p.scale;
        if(ctx.isPointInPath(path(animals.get(item.id)),dx*Math.cos(p.angle)+dy*Math.sin(p.angle),-dx*Math.sin(p.angle)+dy*Math.cos(p.angle)))return item;
      }
      return null;
    }
    function draw() {
      if(m.dead)return;
      const t=now();
      ctx.fillStyle='#b9d5cc';ctx.fillRect(0,0,820,430);
      ctx.strokeStyle='#97bcb6';ctx.lineWidth=1;
      for(let y=40;y<430;y+=52){ctx.beginPath();for(let x=0;x<=820;x+=10){const yy=y+5*Math.sin(x/90+t/6000);x?ctx.lineTo(x,yy):ctx.moveTo(x,yy);}ctx.stroke();}
      for(const item of state.layouts[m.epoch]) {
        const p=pose(item,t-m.epochStart);ctx.save();ctx.translate(p.x,p.y);ctx.rotate(p.angle);ctx.scale(p.scale,p.scale);
        animal(ctx,animals.get(item.id));
        ctx.strokeStyle='#96b8b2';ctx.beginPath();ctx.moveTo(30,-5);ctx.quadraticCurveTo(4,-12,-18,-5);ctx.stroke();ctx.restore();
      }
      const focus=find(t);
      if(m.aim){ctx.strokeStyle='#e8a456';ctx.lineWidth=2;ctx.beginPath();ctx.arc(m.aim.x,m.aim.y,43,0,Math.PI*2);ctx.stroke();ctx.beginPath();ctx.moveTo(m.aim.x-49,m.aim.y);ctx.lineTo(m.aim.x-37,m.aim.y);ctx.moveTo(m.aim.x+37,m.aim.y);ctx.lineTo(m.aim.x+49,m.aim.y);ctx.stroke();}
      c.fillStyle='#f5edda';c.fillRect(0,0,280,220);c.strokeStyle='#d2c7aa';c.lineWidth=1;
      for(let x=20;x<280;x+=20){c.beginPath();c.moveTo(x,0);c.lineTo(x,220);c.stroke();}
      for(let y=10;y<220;y+=20){c.beginPath();c.moveTo(0,y);c.lineTo(280,y);c.stroke();}
      if(focus) {
        const a=animals.get(focus.id);const p=pose(focus,t-m.epochStart);
        // A magnified crop of the same tail geometry, with the same pose.
        c.save();c.translate(140,110);c.rotate(p.angle);c.scale(3.0*p.scale,3.0*p.scale);
        c.translate(37,0);c.beginPath();c.rect(-52,-29,26,58);c.clip();
        animal(c,a);c.restore();
        root.querySelector('#fc-inspect').textContent=SPECIES[a.species]+' · tail-edge inspection';
      } else {c.fillStyle='#8c927f';c.font='42px Georgia';c.fillText('⌖',120,110);root.querySelector('#fc-inspect').textContent='Place the lens over an animal.';}
      if(!m.busy)requestAnimationFrame(draw);
    }
    function aim(x,y,source) {
      if(m.busy||m.closed||!Number.isFinite(x)||!Number.isFinite(y)||x<0||x>820||y<0||y>430)return;
      m.aim={x,y};record('aim',source,{x,y});
      // Paused native input must synchronously reveal its new lens result.
      drawOnce();
    }
    function drawOnce(){const b=m.busy;m.busy=true;draw();m.busy=b;}
    async function submit() {
      m.busy=true;m.closed=true;
      try {
        const response=await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mechanic_id:state.mechanic_id,task_id:state.task_id,challenge_id:state.challenge_id,control_condition:state.control_condition,interaction_mode:mode,events:m.events})});
        const outcome=await response.json();
        const overlay=document.createElement('div');overlay.className='fc-verdict';
        const title=document.createElement('strong');title.textContent=outcome.passed?'CENSUS ACCEPTED':'SURVEY CLOSED';
        const message=document.createElement('p');message.textContent=outcome.passed ? "Every listed individual was photographed once." : "Incomplete census, duplicate, or off-list photograph. Begin a fresh survey.";overlay.append(title,message);
        if(!outcome.passed&&outcome.state){const retry=document.createElement('button');retry.id='fc-retry';retry.textContent='Begin a fresh survey →';retry.onclick=()=>helpers.render(outcome.state);overlay.append(retry);}
        root.append(overlay);helpers.setReadout(outcome.passed?'PASS':'FAIL',outcome.passed?'passed':'error');
      }catch(error){m.busy=false;root.querySelector('#fc-note').textContent='Connection interrupted. Submit again to retry.';requestAnimationFrame(draw);}
    }
    function photograph() {
      if(m.busy||m.closed)return;const t=now(),focus=find(t);if(!focus){root.querySelector('#fc-note').textContent='No animal in the lens. Reposition and try again.';return;}
      record('photo',mode==='full'?'space':'photo_button',{animal_id:focus.id,epoch:m.epoch},t);
      const bad=m.photos.includes(focus.id)||!state.listed_species.includes(animals.get(focus.id).species);
      m.photos.push(focus.id);m.epoch++;m.epochStart=t;m.aim=null;
      root.querySelector('#fc-count').textContent=String(m.photos.length).padStart(2,'0');
      root.querySelector('#fc-note').textContent='Shutter recorded. The pod has scattered.';drawOnce();
      if(bad)submit();
    }
    if(mode==='full') {
      sea.addEventListener('pointermove',e=>{const r=sea.getBoundingClientRect();aim((e.clientX-r.left)*820/r.width,(e.clientY-r.top)*430/r.height,'pointer');});
      m.key=e=>{if(e.code==='Space'&&!e.repeat){e.preventDefault();photograph();}};window.addEventListener('keydown',m.key);
    }else {
      root.querySelector('#fc-aim').onclick=()=>aim(Number(root.querySelector('#fc-x').value),Number(root.querySelector('#fc-y').value),'coordinates');
      root.querySelector('#fc-photo').onclick=photograph;
    }
    root.querySelector('#fc-submit').onclick=()=>{if(!m.busy){if(m.events.at(-1)?.type!=='submit')record('submit','census_button');submit();}};
    helpers.setReadout('','idle');draw();
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics.fluke_census={render,rootSelector:'.fluke-census'};
})();
