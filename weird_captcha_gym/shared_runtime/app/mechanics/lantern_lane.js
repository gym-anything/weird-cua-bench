(() => {
  'use strict';
  const ID='lantern_lane', clone=x=>JSON.parse(JSON.stringify(x)), edge=(a,b)=>`${Math.min(a,b)}:${Math.max(a,b)}`;
  let cleanup=null;
  function neighbors(w,a) {
    return [a-11,a-1,a+1,a+11].filter(b=>b>=0&&b<77&&Math.abs(b%11-a%11)+Math.abs(Math.floor(b/11)-Math.floor(a/11))===1&&(!w.parameters.river||((a%11!==5||w.bridges.includes(Math.floor(a/11)))&&(b%11!==5||w.bridges.includes(Math.floor(b/11))))));
  }
  function initial(w) {
    return {tick:0,status:'active',roads:Object.fromEntries(w.initial_roads.map(([a,b])=>[edge(a,b),false])),entrances:w.homes.map(h=>h.entrance),sites:w.sites.map(x=>({active:x.parent<0,queue:0,made:0,delivered:0,meter:x.phase})),carts:w.homes.flatMap((h,i)=>Array.from({length:w.parameters.fleet},()=>({home:i,node:h.node,dest:-1,returning:false,to:-1,remaining:0}))),peak_queue:0,wait_ticks:0};
  }
  function route(w,s,start,target) {
    const buildings=new Set([...w.homes,...w.sites].map(x=>x.node)), parents=new Map([[start,null]]),q=[start];
    while(q.length) {
      let a=q.shift();
      if(a===target) {const path=[];while(a!==null){path.push(a);a=parents.get(a);}return path.reverse();}
      for(const b of neighbors(w,a)) {
        if(parents.has(b)||!(edge(a,b) in s.roads)||s.roads[edge(a,b)]||(buildings.has(b)&&b!==target))continue;
        if(w.homes.some((h,i)=>(a===h.node&&b!==s.entrances[i])||(b===h.node&&a!==s.entrances[i])))continue;
        parents.set(b,a);q.push(b);
      }
    }
    return null;
  }
  function advance(w,s) {
    if(s.status!=='active')return;
    const p=w.parameters;s.tick++;
    for(let j=0;j<s.sites.length;j++) {
      const site=s.sites[j],spec=w.sites[j];
      if(!site.active&&s.sites[spec.parent].delivered>=2){site.active=true;site.meter=0;}
      if(!site.active||site.made>=p.quota)continue;
      const delivered=s.sites.reduce((n,x)=>n+x.delivered,0);
      const interval=Math.floor(spec.interval*(delivered>=Math.floor(p.colors*p.quota/2)?100-p.growth_percent:100)/100);
      site.meter++;
      if(site.meter>=interval) {
        site.meter-=interval;site.made++;site.queue++;s.peak_queue=Math.max(s.peak_queue,site.queue);
        if(site.queue>p.queue_limit){s.status='overflow';return;}
      }
    }
    for(const c of s.carts)if(c.remaining){c.remaining--;if(!c.remaining){c.node=c.to;c.to=-1;}}
    const occupied=new Set(s.carts.filter(c=>c.remaining).map(c=>edge(c.node,c.to)));
    for(const e of Object.keys(s.roads))if(s.roads[e]&&!occupied.has(e))delete s.roads[e];
    for(const c of s.carts) {
      if(c.remaining)continue;
      const home=w.homes[c.home];
      if(c.dest>=0&&!c.returning&&c.node===w.sites[c.dest].node){const site=s.sites[c.dest];site.queue--;site.delivered++;c.returning=true;}
      if(c.returning&&c.node===home.node){c.dest=-1;c.returning=false;}
      if(c.dest<0){
        const choices=[];
        s.sites.forEach((site,j)=>{
          const reserved=s.carts.filter(k=>k.dest===j&&!k.returning).length;
          if(site.active&&w.sites[j].color===home.color&&site.queue>reserved){const path=route(w,s,c.node,w.sites[j].node);if(path)choices.push([path.length,j]);}
        });
        choices.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);if(choices.length)c.dest=choices[0][1];
      }
      if(c.dest<0)continue;
      const target=c.returning?home.node:w.sites[c.dest].node,path=route(w,s,c.node,target);
      if(path&&path.length>1&&!occupied.has(edge(c.node,path[1]))){c.to=path[1];c.remaining=p.trip_ticks;occupied.add(edge(c.node,c.to));}
      else s.wait_ticks++;
    }
    if(s.sites.every(x=>x.delivered>=p.quota))s.status='delivered';
    else if(s.tick>=p.max_ticks)s.status='timeout';
  }
  function apply(w,s,e) {
    if(s.status!=='active')return false;
    const {type,a,b}=e;
    if(!Number.isInteger(a)||!Number.isInteger(b)||a<0||a>=77||!neighbors(w,a).includes(b))return false;
    if(type==='orient'){
      const i=w.homes.findIndex(h=>h.node===a);
      if(i<0||[...w.homes,...w.sites].some(x=>x.node===b))return false;
      s.entrances[i]=b;return true;
    }
    const k=edge(a,b);
    if(type==='remove'){
      if(!(k in s.roads))return false;
      if(s.carts.some(c=>c.remaining&&edge(c.node,c.to)===k))s.roads[k]=true;else delete s.roads[k];return true;
    }
    if(type!=='road'||w.sites.some((x,j)=>!s.sites[j].active&&(x.node===a||x.node===b)))return false;
    if(k in s.roads){s.roads[k]=false;return true;}
    if(Object.keys(s.roads).length>=w.parameters.road_budget)return false;
    s.roads[k]=false;return true;
  }
  const xy=n=>[64+(n%11)*76,50+Math.floor(n/11)*63];
  function render(state,helpers) {
    cleanup?.();
    document.body.dataset.mechanic=ID;
    const w=state.world,p=w.parameters,mode=state.control_condition?.interaction||'full';
    const m={state,w,s:initial(w),events:[],mode,started:false,submitting:false,selection:null,tool:'road',message:'Draw roads from the front doors. Open the town when ready.'};
    window.lanternLaneModel=m;
    helpers.app.innerHTML=`<section class="lantern-lane" data-challenge-id="${helpers.text(state.challenge_id)}"><header><div><small>THE NIGHT POST · ROAD & ROUTE OFFICE</small><h1>Lantern Lane</h1></div><div class="ll-score"></div></header><div class="ll-body"><canvas width="900" height="492" aria-label="Town road map"></canvas><aside><h2>Keep the lights on</h2><p>Join homes to workshops with the same lantern. Each cart must travel there <b>and back</b>.</p><div class="ll-legend"></div><div class="ll-tools">${mode==='simplified'?'<button data-tool="road">Build road</button><button data-tool="remove">Remove road</button><button data-tool="orient">Turn entrance</button>':''}</div><p class="ll-help">${mode==='full'?'Drag between road pins to build. Drag a home toward a neighboring pin to turn its door. Drag into a home to join its road. Right-click a road to remove it.':'Choose a tool. Click two neighboring pins for a segment. To turn a door, select a home then use a direction button.'}</p>${mode==='simplified'?'<div class="ll-directions"><button data-dir="-11">↑</button><button data-dir="-1">←</button><button data-dir="1">→</button><button data-dir="11">↓</button></div>':''}<p>One cart per segment. Dashed roads close after their cart leaves.</p><p>Fenced workshops open after two deliveries to their partner.</p><div class="ll-budget"></div></aside></div><footer><span class="ll-message"></span><div class="readout" data-status="idle"></div><button id="ll-start">OPEN TOWN</button><button id="ll-submit">CERTIFY</button><button id="ll-retry" hidden>NEW TOWN</button></footer></section>`;
    const root=helpers.app.querySelector('.lantern-lane'),canvas=root.querySelector('canvas'),ctx=canvas.getContext('2d');
    root.querySelector('.ll-legend').innerHTML=w.palette.slice(0,p.colors).map((c,i)=>`<span style="--ink:${c}">${['◆','●','▲'][i]} lantern · ${p.fleet} carts</span>`).join('');
    let timer=null,startTime=0,down=null,last=null;
    function sync(){if(m.started&&!m.submitting){const target=Math.floor((performance.now()-startTime)/p.tick_ms);while(m.s.tick<target&&m.s.status==='active')advance(w,m.s);}paint();}
    function action(type,a,b,source){sync();const token=helpers.beginAction?.('lantern-road-edit');const e={sequence:m.events.length+1,type,a,b,tick:m.s.tick,input_source:source};e.accepted=apply(w,m.s,e);m.events.push(e);m.message=e.accepted?(type==='remove'?'Road closing; carts already on it finish safely.':type==='orient'?'Front door turned.':'Road joined.'):'Cannot place here: check river, fenced workshop, or road supply.';helpers.setReadout('', 'idle');paint();token?.settle();}
    const nearest=(x,y)=>{let best=null,d=26;for(let n=0;n<77;n++){const [a,b]=xy(n),dd=Math.hypot(x-a,y-b);if(dd<d){best=n;d=dd;}}return best;};
    const pos=e=>{const b=canvas.getBoundingClientRect();return [(e.clientX-b.x)*900/b.width,(e.clientY-b.y)*492/b.height];};
    canvas.addEventListener('pointerdown',e=>{
      if(e.button!==0||m.s.status!=='active'||m.submitting)return;
      const [x,y]=pos(e),n=nearest(x,y);if(n===null)return;
      if(mode==='simplified'){
        if(m.tool==='orient'){m.selection=n;paint();return;}
        if(m.selection!==null&&m.selection!==n){action(m.tool,m.selection,n,m.tool==='road'?'road_click_pair':'remove_button');m.selection=n;}else m.selection=n;
        paint();return;
      }
      canvas.setPointerCapture(e.pointerId);down=n;last=n;
    });
    // Resample sparse straight pointer delivery through every crossed road pin.
    function trace(n){
      if(last===null||n===null||n===last)return;
      const ax=last%11,ay=Math.floor(last/11),bx=n%11,by=Math.floor(n/11);
      if(ax!==bx&&ay!==by)return;
      const step=ax===bx?(by>ay?11:-11):(bx>ax?1:-1);
      if(down!==null&&w.homes.some(h=>h.node===down)){action('orient',down,down+step,'entrance_drag');down=null;last=null;return;}
      while(last!==n){action('road',last,last+step,'road_drag');last+=step;}down=null;
    }
    canvas.addEventListener('pointermove',e=>{if(mode==='full'&&last!==null)trace(nearest(...pos(e)));});
    canvas.addEventListener('pointerup',e=>{if(mode==='full'&&last!==null)trace(nearest(...pos(e)));down=null;last=null;});
    canvas.addEventListener('pointercancel',()=>{down=null;last=null;});
    canvas.addEventListener('contextmenu',e=>{
      e.preventDefault();if(mode!=='full')return;const [x,y]=pos(e);let best=null,dist=18;
      for(const key of Object.keys(m.s.roads)){const [a,b]=key.split(':').map(Number),[ax,ay]=xy(a),[bx,by]=xy(b),t=Math.max(0,Math.min(1,((x-ax)*(bx-ax)+(y-ay)*(by-ay))/((bx-ax)**2+(by-ay)**2))),d=Math.hypot(x-ax-t*(bx-ax),y-ay-t*(by-ay));if(d<dist){best=[a,b];dist=d;}}
      if(best)action('remove',...best,'road_right_click');
    });
    root.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>{m.tool=b.dataset.tool;m.selection=null;paint();});
    root.querySelectorAll('[data-dir]').forEach(b=>b.onclick=()=>{if(m.selection!==null&&m.tool==='orient')action('orient',m.selection,m.selection+Number(b.dataset.dir),'entrance_button');});
    root.querySelector('#ll-start').onclick=()=>{if(m.started)return;const t=helpers.beginAction?.('open-town');m.started=true;startTime=performance.now();m.message='Town open. Watch returning carts and workshop queues.';root.querySelector('#ll-start').disabled=true;paint();t?.settle();};
    const payload=()=>({mechanic_id:ID,task_id:state.task_id,challenge_id:state.challenge_id,interaction_mode:mode,events:clone(m.events),terminal_tick:m.s.tick,final_state:clone(m.s),completed:m.s.status==='delivered'});
    async function submit(){
      if(m.submitting)return;sync();m.submitting=true;
      try{const response=await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload())});const result=await response.json();
        if(result.passed===true){helpers.setReadout('PASS','passed');m.message='All lantern orders delivered.';root.classList.add('is-passed');paint();}
        else {helpers.setReadout('FAIL','error');m.message='Town not certified. Start a fresh town to retry.';m.nextState=result.state;root.querySelector('#ll-retry').hidden=false;paint();}
      }catch(error){m.submitting=false;m.message='Submission unavailable. CERTIFY retries this result.';paint();}
    }
    root.querySelector('#ll-submit').onclick=submit;
    root.querySelector('#ll-retry').onclick=()=>{if(m.nextState)render(m.nextState,helpers);};
    function line(a,b,color,width,dash=[]){ctx.beginPath();ctx.setLineDash(dash);ctx.moveTo(...a);ctx.lineTo(...b);ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();ctx.setLineDash([]);}
    function paint(){
      const s=m.s;
      ctx.clearRect(0,0,900,492);ctx.fillStyle='#182e33';ctx.fillRect(0,0,900,492);
      // Original procedural scene; no downloaded imagery or copied game art.
      for(let i=0;i<110;i++){const x=(i*137+19)%900,y=(i*83+21)%485;ctx.fillStyle=i%3?'#254047':'#2a4540';ctx.beginPath();ctx.ellipse(x,y,3,1,0,0,7);ctx.fill();}
      if(p.river){ctx.fillStyle='#254c61';ctx.fillRect(421,0,46,492);for(let y=12;y<490;y+=23)line([431,y],[455,y-5],'#386779',2);for(const y of w.bridges)line([402,xy(y*11+5)[1]],[486,xy(y*11+5)[1]],'#8c9280',23);}
      for(let n=0;n<77;n++){if(p.river&&n%11===5&&!w.bridges.includes(Math.floor(n/11)))continue;const [x,y]=xy(n);ctx.beginPath();ctx.arc(x,y,3,0,7);ctx.fillStyle='#668079';ctx.fill();}
      for(const [key,closing] of Object.entries(s.roads)){const [a,b]=key.split(':').map(Number);line(xy(a),xy(b),'#10272b',15);line(xy(a),xy(b),closing?'#d47770':'#b6b096',9,closing?[6,5]:[]);line(xy(a),xy(b),'#dfd4ac',1, [3,7]);}
      const icon=(x,y,i)=>{ctx.font='bold 16px sans-serif';ctx.textAlign='center';ctx.fillStyle='#132a30';ctx.fillText(['◆','●','▲'][i],x,y+5);};
      w.homes.forEach((h,i)=>{const [x,y]=xy(h.node),c=w.palette[h.color];ctx.fillStyle='#112429';ctx.beginPath();ctx.ellipse(x,y+19,26,9,0,0,7);ctx.fill();ctx.fillStyle='#eadfc1';ctx.fillRect(x-19,y-10,38,30);ctx.fillStyle=c;ctx.beginPath();ctx.moveTo(x-26,y-9);ctx.lineTo(x,y-32);ctx.lineTo(x+26,y-9);ctx.closePath();ctx.fill();icon(x,y,h.color);const [ex,ey]=xy(s.entrances[i]),dx=(ex-x)/Math.hypot(ex-x,ey-y),dy=(ey-y)/Math.hypot(ex-x,ey-y);line([x+dx*18,y+dy*18],[x+dx*32,y+dy*32],c,8);});
      w.sites.forEach((spec,j)=>{
        const site=s.sites[j],[x,y]=xy(spec.node);
        if(!site.active){ctx.strokeStyle='#647b7b';ctx.lineWidth=2;ctx.setLineDash([5,5]);ctx.strokeRect(x-22,y-22,44,44);ctx.setLineDash([]);ctx.fillStyle='#9bab9e';ctx.font='11px sans-serif';ctx.textAlign='center';ctx.fillText('COMING',x,y+4);return;}
        ctx.fillStyle='#12272d';ctx.fillRect(x-27,y-27,54,53);ctx.fillStyle=w.palette[spec.color];ctx.fillRect(x-22,y-21,44,38);ctx.fillStyle='#d9cdad';ctx.fillRect(x+13,y-35,8,15);icon(x,y-3,spec.color);
        ctx.fillStyle='#f4ebd1';ctx.font='bold 12px sans-serif';ctx.textAlign='center';ctx.fillText(`${site.delivered}/${p.quota}`,x,y+31);
        const delivered=s.sites.reduce((n,z)=>n+z.delivered,0),interval=Math.floor(spec.interval*(delivered>=Math.floor(p.colors*p.quota/2)?100-p.growth_percent:100)/100);
        line([x-25,y-32],[x+25,y-32],'#455859',4);if(site.made<p.quota)line([x-25,y-32],[x-25+50*site.meter/interval,y-32],'#f8df90',4);
        for(let k=0;k<p.queue_limit;k++){ctx.fillStyle=k<site.queue?(site.queue>=p.queue_limit?'#f37970':'#ffe4a0'):'#496064';ctx.fillRect(x-26+k*11,y+39,8,9);}
        if(site.queue>p.queue_limit){ctx.fillStyle='#ff7770';ctx.fillText('OVERFLOW',x,y+63);}
      });
      s.carts.forEach((c,i)=>{const [ax,ay]=xy(c.node),[bx,by]=c.to<0?[ax,ay]:xy(c.to),t=c.remaining?1-c.remaining/p.trip_ticks:0,x=ax+(bx-ax)*t,y=ay+(by-ay)*t;ctx.save();ctx.translate(x,y);if(c.remaining)ctx.rotate(Math.atan2(by-ay,bx-ax));else ctx.translate((i%p.fleet)*7-3,13);ctx.fillStyle='#101f25';ctx.fillRect(-8,-6,16,12);ctx.fillStyle=w.palette[w.homes[c.home].color];ctx.fillRect(-6,-4,12,8);if(!c.returning&&c.dest>=0){ctx.shadowColor='#ffeac0';ctx.shadowBlur=12;ctx.fillStyle='#fff2c8';ctx.fillRect(-2,-2,4,4);}ctx.restore();});
      if(m.selection!==null){ctx.beginPath();ctx.arc(...xy(m.selection),26,0,7);ctx.strokeStyle='#fff0c3';ctx.lineWidth=2;ctx.stroke();}
      const count=s.sites.reduce((n,x)=>n+x.delivered,0);root.querySelector('.ll-score').innerHTML=`<strong>${count}<em> / ${w.sites.length*p.quota}</em></strong><span>DELIVERIES · ${Math.floor(s.tick/10)}s</span>`;
      root.querySelector('.ll-budget').textContent=`ROADS ${Object.keys(s.roads).length} / ${p.road_budget} · QUEUE LIMIT ${p.queue_limit}`;
      root.querySelector('.ll-message').textContent=s.status==='overflow'?'FAIL — workshop queue overflowed.':s.status==='timeout'?'FAIL — the night ended.':s.status==='delivered'?'DELIVERED — certify the town.':m.message;
      root.querySelectorAll('[data-tool]').forEach(b=>b.classList.toggle('selected',b.dataset.tool===m.tool));
      if(s.status!=='active'){ctx.fillStyle='#11282dea';ctx.fillRect(225,183,450,89);ctx.textAlign='center';ctx.fillStyle=s.status==='delivered'?'#b9ebc3':'#ff9a8d';ctx.font='bold 31px Georgia';ctx.fillText(s.status==='delivered'?'THE TOWN IS AGLOW':'THE NIGHT POST JAMMED',450,235);}
    }
    paint();timer=setInterval(sync,50);cleanup=()=>clearInterval(timer);
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics[ID]={rootSelector:'.lantern-lane',render};
})();
