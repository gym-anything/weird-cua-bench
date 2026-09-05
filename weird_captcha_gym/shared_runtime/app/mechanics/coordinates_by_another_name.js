(() => {
  'use strict';
  const ID='coordinates_by_another_name';
  let m, h;
  const $=s=>document.querySelector(s);
  function angle(i,n){return (-210+240*i/(n-1))*Math.PI/180;}
  function point(i,n,r){const a=angle(i,n);return [84+Math.cos(a)*r,84+Math.sin(a)*r];}
  function stamp(text,status='idle'){h.setReadout(text,status);}
  function selector(axis){
    const vals=m.options[axis];
    const selected=m.indices[axis];
    if(m.mode==='simplified')return `<div class="cn-values">${vals.map((v,i)=>`<button data-axis="${axis}" data-index="${i}" aria-pressed="${i===selected}">${v}</button>`).join('')}</div>`;
    const [x,y]=point(selected,vals.length,47);
    return `<svg class="cn-dial" data-axis="${axis}" viewBox="0 0 168 168" role="img" aria-label="${['Band','Block','Count'][axis]} rotary selector, drag to a label"><path d="M 28 116 A 65 65 0 1 1 140 116" fill="none" stroke="#9a8051" stroke-width="2"/>${vals.map((v,i)=>{const [tx,ty]=point(i,vals.length,69);return `<text x="${tx}" y="${ty+5}" text-anchor="middle" class="${selected===i?'selected':''}">${v}</text>`;}).join('')}<circle cx="84" cy="84" r="43" class="cn-knob"/><line x1="84" y1="84" x2="${x}" y2="${y}" stroke="#f0b748" stroke-width="5"/><circle cx="84" cy="84" r="7" fill="#a89876"/><text x="84" y="152" text-anchor="middle" class="cn-drag-label">DRAG TO SET</text></svg>`;
  }
  function drawSelectors(){
    $('.cn-selectors').innerHTML=m.options.map((_,axis)=>`<section><label>${['01 / BAND','02 / BLOCK','03 / COUNT'][axis]}</label>${selector(axis)}</section>`).join('');
    $('.cn-address').textContent=m.indices.map((v,a)=>m.options[a][v]).join(' · ');
    document.querySelectorAll('.cn-values button').forEach(b=>b.addEventListener('click',()=>select(+b.dataset.axis,+b.dataset.index,'value_button')));
    document.querySelectorAll('.cn-dial').forEach(d=>{
      let drag=null;
      const position=e=>{const r=d.getBoundingClientRect();return [+(168*(e.clientX-r.left)/r.width).toFixed(4),+(168*(e.clientY-r.top)/r.height).toFixed(4)];};
      d.addEventListener('pointerdown',e=>{
        if(e.button!==0||m.busy||m.terminal||m.sunk.length===m.state.runtime_fleet.length)return;
        const start=position(e);
        if(Math.hypot(start[0]-84,start[1]-84)>43)return;
        drag=start;d.setPointerCapture(e.pointerId);
      });
      d.addEventListener('pointercancel',()=>{drag=null;});
      d.addEventListener('pointerup',e=>{
        if(!drag)return;const start=drag;drag=null;
        const [x,y]=position(e);
        if(Math.hypot(x-start[0],y-start[1])<8)return;
        let delta=((Math.atan2(y-84,x-84)*180/Math.PI+210)%360+360)%360;
        const radius=Math.hypot(x-84,y-84);
        const a=+d.dataset.axis;
        const halfStep=120/(m.options[a].length-1);
        if(radius<24||radius>86||(delta>240+halfStep&&delta<360-halfStep)){stamp('SELECTOR NOT SEATED · RELEASE ON A LABELED ARC','error');return;}
        delta=delta>=360-halfStep?0:Math.min(240,delta);
        select(a,Math.round(delta/240*(m.options[a].length-1)),'rotary_drag',[x,y],start);
      });
    });
  }
  function select(axis,index,source,release,start){
    if(m.busy||m.terminal||m.sunk.length===m.state.runtime_fleet.length)return;
    const e={sequence:m.events.length+1,action:'select',axis,index,input_source:source};if(release){e.release=release;e.start=start;}
    m.events.push(e);m.indices[axis]=index;stamp('DESIGNATION SET · FIRE WHEN READY');drawSelectors();
  }
  function board(){
    const w=m.state.world;const width=740,height=300,cw=660/w.columns,rh=250/w.rows,left=65,top=20;
    const target=new Map();m.state.runtime_fleet.forEach((s,i)=>s.cells.forEach(c=>target.set(c,i)));
    const cells=w.cells.map(c=>{
      const x=left+c.column*cw,y=top+c.row*rh;const shot=m.seen.has(c.id),ship=target.get(c.id),hit=shot&&ship!==undefined,sunk=hit&&m.sunk.includes(ship);
      const mark=hit?(w.orientation_feedback?m.state.runtime_fleet[ship].orientation==='H'?'↔':'↕':'✚'):'×';
      return `<g class="cn-cell ${sunk?'sunk':hit?'hit':shot?'miss':''}" transform="translate(${x},${y})"><rect width="${cw-5}" height="${rh-18}" rx="3"/>${shot?`<text x="${(cw-5)/2}" y="${(rh-18)/2+8}" text-anchor="middle">${mark}</text>`:''}</g>`;
    }).join('');
    const runs=w.runs.map(run=>{
      const x=left+run.start*cw,y=top+run.row*rh+rh-14;
      return `<path d="M${x+2} ${y-4}v5h${run.width*cw-10}v-5" stroke="#9f885b" fill="none"/><text x="${x+run.width*cw/2-3}" y="${y+12}" text-anchor="middle" class="cn-run">${run.block} ${run.reverse?'←':'→'}</text>`;
    }).join('');
    $('.cn-chart').innerHTML=`<svg viewBox="0 0 ${width} ${height}" aria-label="Fleet evidence chart">${w.bands.map((band,r)=>`<text x="48" y="${top+r*rh+(rh-18)/2+6}" text-anchor="middle" class="cn-band">${band}</text>`).join('')}${cells}${runs}</svg>`;
    $('.cn-fleet').innerHTML=w.fleet_lengths.map((n,i)=>`<div class="${m.sunk.includes(i)?'sunk':''}"><span>${'▪'.repeat(n)}</span><b>${n} CELLS</b><em>${m.sunk.includes(i)?'SUNK':'UNLOCATED'}</em></div>`).join('');
    $('.cn-shots').textContent=String(m.shots).padStart(2,'0');$('.cn-sweeps').textContent=m.sweeps;
    $('.cn-last').textContent=m.last;
    const solved=m.sunk.length===m.state.runtime_fleet.length;
    $('#cn-fire').disabled=solved||m.busy||m.terminal;
    $('#cn-certify').textContent=solved?'CERTIFY FLEET →':'END ATTEMPT →';
    $('.cn-status').textContent=solved?'ALL VESSELS SUNK':`${m.sunk.length} / ${w.fleet_lengths.length} VESSELS SUNK`;
  }
  function fire(){
    if(m.busy||m.terminal||m.sunk.length===m.state.runtime_fleet.length)return;
    const address=m.indices.map((v,a)=>m.options[a][v]);const [band,block,count]=address;
    const targets=m.state.world.cells.filter(c=>c.band===band&&c.block===block&&(count==='*'||c.count===count)).map(c=>c.id).sort();
    let outcome=!targets.length?'invalid':count==='*'&&!m.sweeps?'no_sweeps':targets.every(c=>m.seen.has(c))?'repeat':'shot';
    let hits=[],sunk=[];
    if(outcome==='shot'){
      m.shots++;if(count==='*')m.sweeps--;
      targets.forEach(c=>m.seen.add(c));
      hits=targets.filter(c=>m.state.runtime_fleet.some(s=>s.cells.includes(c)));
      sunk=m.state.runtime_fleet.map((s,i)=>i).filter(i=>!m.sunk.includes(i)&&m.state.runtime_fleet[i].cells.every(c=>m.seen.has(c)));
      m.sunk.push(...sunk);
    }
    m.events.push({sequence:m.events.length+1,action:'fire',input_source:'fire_button',designation:address,outcome,hits,sunk});
    const label={invalid:'NO SUCH CELL · NO SHOT USED',no_sweeps:'SWEEP CHARGES EMPTY · SELECT A COUNT',repeat:'ALREADY CHARTED · NO SHOT USED',shot:sunk.length?'HIT + SINK':hits.length?'HIT':'MISS'}[outcome];
    m.last=`${address.join(' · ')}   /   ${label}`;stamp(label,outcome==='shot'?'idle':'error');board();
  }
  function payload(){return {mechanic_id:ID,task_id:m.state.task_id,challenge_id:m.state.challenge_id,events:m.events,final:{shots:m.shots,sweeps:m.sweeps,seen:[...m.seen].sort(),sunk:[...m.sunk].sort((a,b)=>a-b)}};}
  async function certify(){
    if(m.busy||m.terminal)return;
    m.busy=true;$('#cn-certify').disabled=true;
    try{
      const response=await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload())});
      if(!response.ok)throw Error('submission unavailable');
      const result=await response.json();
      if(result.passed===true){
        // The shared POST response confirms completion; GET carries the exact
        // Python grade in both the local-server and static-browser runtimes.
        const exported=await (await fetch('/result')).json();
        const grade=exported.server_grade||exported.browser_grade;
        if(!grade||!Number.isFinite(grade.score))throw Error('score unavailable');
        m.terminal=true;$('.cn-verdict').innerHTML=`<strong>PASS</strong><span>FLEET ACCOUNTED FOR</span><span class="cn-score">SCORE ${grade.score.toFixed(1)} / 100</span>`;
        stamp(`PASS · SCORE ${grade.score.toFixed(1)} / 100`,'passed');board();
      }
      else if(result.passed===false&&result.state){
        await h.render(result.state);$('.cn-verdict').innerHTML='<strong>FAIL</strong><span>FLEET INCOMPLETE · NEW CHART ISSUED</span><button id="cn-continue">CONTINUE →</button>';
        m.busy=true;stamp('FAIL · NEW CHART ISSUED','error');$('#cn-continue').onclick=()=>{m.busy=false;$('.cn-verdict').innerHTML='';stamp('FRESH CHART · READY');board();};
      }else throw Error('submission unavailable');
    }catch(_){m.busy=false;$('#cn-certify').disabled=false;stamp('CONNECTION FAILED · RETRY CERTIFICATION','error');}
  }
  async function render(state,helpers){
    h=helpers||h;const w=state.world;document.body.dataset.mechanic=ID;
    m={state,mode:state.control_condition?.interaction||'full',options:[[...w.bands].sort((a,b)=>a-b),['A','B','C'],[...Array(w.columns)].map((_,i)=>i+1).concat('*')],indices:[0,0,0],seen:new Set(),sunk:[],shots:0,sweeps:w.sweeps,events:[],busy:false,terminal:false,last:'NO SHOTS FIRED'};
    h.app.innerHTML=`<article class="cn-root"><header><div><p>THE HYDROGRAPHIC OFFICE / DESIGNATION CONSOLE</p><h1>Coordinates by Another Name</h1></div><aside><small>SHOTS FIRED</small><b class="cn-shots">00</b></aside></header><main><section class="cn-map"><div class="cn-map-title"><b>UNCHARTED WATERS</b><span>BAND / BLOCK / COUNT</span></div><div class="cn-chart"></div><div class="cn-map-key"><span>× MISS</span><span>✚ HIT</span><span>GOLD = SUNK</span><span>VOID = NO CELL</span></div><div class="cn-last"></div></section><aside class="cn-manifest"><p>VESSEL MANIFEST</p><div class="cn-fleet"></div><div class="cn-rules">${w.touching?'Vessels may touch.':'Vessels never touch, even at corners.'}<br>Each runs straight across adjacent cells.<br>${w.orientation_feedback?'Hit arrows show vessel orientation.':'Hits do not reveal orientation.'}</div><div class="cn-sweep-box"><b class="cn-sweeps"></b><span>SWEEPS REMAIN<br>Count * covers one band + block run.</span></div></aside></main><div class="cn-console"><div class="cn-selectors"></div><div class="cn-commit"><small>NEXT DESIGNATION</small><div class="cn-address"></div><button id="cn-fire">FIRE</button><p>Count from 1 in the bracket’s arrow direction. Voids still occupy a count.</p></div></div><footer><div><b class="cn-status"></b><div class="readout" data-status="idle">READY · FEWER SHOTS EARN A HIGHER SCORE</div></div><button id="cn-certify">END ATTEMPT →</button></footer><div class="cn-verdict"></div></article>`;
    drawSelectors();board();$('#cn-fire').onclick=fire;$('#cn-certify').onclick=certify;
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics[ID]={rootSelector:'.cn-root',render};
})();
