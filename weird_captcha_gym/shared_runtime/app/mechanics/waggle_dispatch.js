(() => {
  'use strict';
  let frame;
  const M='waggle_dispatch', rad=Math.PI/180;
  function render(state,h) {
    cancelAnimationFrame(frame);
    document.body.dataset.mechanic='waggle-dispatch';
    const w=state.world, mode=state.control_condition?.interaction || 'full';
    const s={epoch:performance.now(),events:[],scouts:[],hold:null,aim:{x:0,y:-110},flight:null,done:false,busy:false};
    window.waggleDispatchModel=s;
    const now=()=>performance.now()-s.epoch;
    const sun=t=>w.sun_phase+w.sun_direction*w.parameters.sun_speed*(t/1000+1.5*(Math.sin(t/6000+w.sun_wave)-Math.sin(w.sun_wave)));
    h.app.innerHTML=`<section class="waggle" data-challenge-id="${state.challenge_id}">
      <header><div><small>FIELD STATION 07 / APIS MELLIFERA</small><h1>Waggle Dispatch<span>the language of distance</span></h1></div><aside>RECRUIT <b>6</b> TO THE <strong>${w.sites[w.target].name.toUpperCase()}</strong><small>NO SCOUTS AT OTHER SITES</small></aside></header>
      <div class="waggle-labels"><span>01 / THE DARK COMB</span><span>02 / THE SUNLIT MEADOW <i>rings = seconds of dance</i></span></div>
      <canvas width="1100" height="430" aria-label="Honeycomb dance surface and meadow map"></canvas>
      <div class="waggle-strip"><span class="waggle-report">The scouts are listening.</span><div class="waggle-counts"></div></div>
      <div class="waggle-controls"><p>${mode==='full'?'Press the bee → drag to aim → hold → release.':'Click the comb to aim. Start dance → wait → End dance.'}<br><em>Up means toward the sun at release. Longer holds mean farther flights.</em></p>${mode==='simplified'?'<button class="waggle-toggle">Start dance</button>':''}<button class="waggle-recall">Recall last scout</button><button class="waggle-submit">Certify dispatch</button></div>
      <footer><div class="readout" data-status="idle">READY</div><span>ONE DANCE · ONE SCOUT · WAIT FOR THE REPORT</span></footer><div class="waggle-verdict" hidden></div></section>`;
    const root=h.app.querySelector('.waggle'),c=root.querySelector('canvas'),g=c.getContext('2d'),report=root.querySelector('.waggle-report'),toggle=root.querySelector('.waggle-toggle');
    const emit=(type,data={})=>s.events.push({seq:s.events.length,type,t:now(),...data});
    const status=t=>{report.textContent=t;};
    function clearFailure(){const v=root.querySelector('.waggle-verdict');if(v.dataset.failure==='true'){v.hidden=true;v.dataset.failure='false';h.setReadout('READY','idle');}}
    function begin(){clearFailure();if(s.hold!==null||s.flight||s.done||s.busy)return;s.hold=now();status('Dancing… the direction at release names the bearing.');h.setReadout('DANCING','pending');if(toggle)toggle.textContent='End dance';}
    function finish(){
      if(s.hold===null)return;
      const end=now(),start=s.hold;s.hold=null;if(toggle)toggle.textContent='Start dance';
      if(end-start<100||end-start>w.max_hold_ms){status('Dance too short or too long. No scout left; try again.');h.setReadout('TRY AGAIN','error');return;}
      const {x,y}=s.aim;
      const a=Math.atan2(x,-y)+sun(end)*rad,d=(end-start)/1000*w.distance_per_second;
      const px=Math.sin(a)*d,py=-Math.cos(a)*d;
      const hit=w.sites.find(site=>Math.hypot(px-site.x,py-site.y)<=site.radius)?.id ?? null;
      emit('dance',{start,t:end,x,y,source:mode==='full'?'comb_drag_hold':'comb_toggle'});
      s.flight={start:end,x:px,y:py,hit};status('A scout follows the dance. Await her return.');h.setReadout('SCOUT IN FLIGHT','pending');
    }
    function position(e){const b=c.getBoundingClientRect();return {x:(e.clientX-b.left)*1100/b.width-235,y:(e.clientY-b.top)*430/b.height-215};}
    function aim(p){const d=Math.hypot(p.x,p.y);if(d>=35){s.aim={x:p.x/d*110,y:p.y/d*110};}}
    c.onpointerdown=e=>{if(e.button!==0||s.flight||s.done||s.busy)return;const p=position(e);if(mode==='full'){if(Math.hypot(p.x,p.y)>34)return;e.preventDefault();c.setPointerCapture(e.pointerId);begin();}else if(Math.hypot(p.x,p.y)<=155){clearFailure();aim(p);}};
    c.onpointermove=e=>{if(mode==='full'&&s.hold!==null)aim(position(e));};
    c.onpointerup=e=>{if(mode==='full'&&s.hold!==null){aim(position(e));finish();}};
    c.onpointercancel=()=>{s.hold=null;if(toggle)toggle.textContent='Start dance';status('Dance cancelled; no scout dispatched.');};
    if(toggle)toggle.onclick=()=>s.hold===null?begin():finish();
    root.querySelector('.waggle-recall').onclick=()=>{if(s.flight||s.hold!==null||s.done||s.busy||!s.scouts.length)return;emit('recall');s.scouts.pop();status('Last scout recalled. The remaining commitments stand.');h.setReadout('READY','idle');};
    root.querySelector('.waggle-submit').onclick=async()=>{
      if(s.flight||s.hold!==null||s.busy||s.done)return;
      emit('certify');s.busy=true;
      try {
        const r=await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({mechanic_id:M,task_id:state.task_id,challenge_id:state.challenge_id,interaction_mode:mode,events:s.events})});
        const result=await r.json();
        if(result.passed){s.done=true;s.busy=false;const v=root.querySelector('.waggle-verdict');v.hidden=false;v.textContent='PASS · DISPATCH ACCEPTED';h.setReadout('PASS','passed');}
        else if(result.state){await h.render(result.state);const v=h.app.querySelector('.waggle-verdict');v.hidden=false;v.dataset.failure='true';v.textContent='FAIL · FRESH MEADOW';h.setReadout('FAIL · FRESH MEADOW ISSUED','error');}
        else {s.events.pop();s.busy=false;h.setReadout('FAIL · RETRY CERTIFICATION','error');}
      } catch(e){s.events.pop();s.busy=false;h.setReadout('CONNECTION LOST · RETRY CERTIFICATION','error');}
    };
    function circle(x,y,r,fill,stroke){g.beginPath();g.arc(x,y,r,0,Math.PI*2);if(fill){g.fillStyle=fill;g.fill();}if(stroke){g.strokeStyle=stroke;g.stroke();}}
    function text(t,x,y,color='#e9cf8b',size=14){g.fillStyle=color;g.font=`${size}px Georgia`;g.textAlign='center';g.fillText(t,x,y);}
    function bee(x,y,a=0,scale=1){g.save();g.translate(x,y);g.rotate(a);g.scale(scale,scale);g.fillStyle='#eee8ca';g.beginPath();g.ellipse(-7,-3,5,10,-.5,0,7);g.ellipse(7,-3,5,10,.5,0,7);g.fill();g.fillStyle='#efbb49';g.beginPath();g.ellipse(0,0,6,11,0,0,7);g.fill();g.fillStyle='#312b24';g.fillRect(-5,-3,10,3);g.fillRect(-5,3,10,3);circle(0,-11,4,'#302c23');g.restore();}
    function draw(){
      if(!root.isConnected)return;
      const t=now();
      if(s.flight&&t>=s.flight.start+w.flight_ms){const f=s.flight;s.scouts.push(f.hit);s.flight=null;status(f.hit===null?'Report: open meadow. No site found.':`Report: ${w.sites[f.hit].name}. One scout committed.`);h.setReadout('REPORT RECEIVED','idle');}
      g.clearRect(0,0,1100,430);g.fillStyle='#272923';g.fillRect(0,0,470,430);g.fillStyle='#dddcc0';g.fillRect(470,0,630,430);
      g.lineWidth=1;g.save();g.beginPath();g.rect(0,0,470,430);g.clip();
      for(let row=0;row<10;row++)for(let col=0;col<12;col++){const x=col*44+(row%2)*22,y=row*39;g.beginPath();for(let k=0;k<6;k++){const a=(k*60+30)*rad;g.lineTo(x+25*Math.cos(a),y+25*Math.sin(a));}g.closePath();g.strokeStyle='#4e4b34';g.stroke();}
      g.restore();
      circle(235,215,156,'#242720dd','#938151');circle(235,215,110,null,'#696345');
      for(let i=0;i<12;i++){const a=i*Math.PI/6;g.beginPath();g.moveTo(235+142*Math.sin(a),215-142*Math.cos(a));g.lineTo(235+152*Math.sin(a),215-152*Math.cos(a));g.stroke();}
      text('TOWARD SUN',235,41);text('HOLD = DISTANCE',235,407,'#b7a979',12);
      g.strokeStyle='#e7bd64';g.lineWidth=3;g.beginPath();g.moveTo(235,215);g.lineTo(235+s.aim.x,215+s.aim.y);g.stroke();circle(235+s.aim.x,215+s.aim.y,7,'#f5d582');
      const a=Math.atan2(s.aim.x,-s.aim.y);bee(235+(s.hold!==null?Math.sin(t/55)*3:0),215,a,1.7);
      for(let i=0;i<6;i++)bee(84+i*59,365,Math.sin(t/1800+i)*.1,.8);
      // Meadow coordinates and landing disks are exactly those used in replay.
      const mx=785,my=215;
      for(let i=1;i<=5;i++){g.lineWidth=1;circle(mx,my,i*36,null,'#aeb59b');text(`${i}s`,mx+7,my-i*36+14,'#78836e',11);}
      for(let i=0;i<85;i++){const x=488+(i*83%591),y=12+(i*67%405);g.strokeStyle='#adb598';g.beginPath();g.moveTo(x,y);g.lineTo(x+3,y-5);g.stroke();}
      const sa=sun(t)*rad;g.setLineDash([5,7]);g.strokeStyle='#a99140';g.beginPath();g.moveTo(mx,my);g.lineTo(mx+199*Math.sin(sa),my-199*Math.cos(sa));g.stroke();g.setLineDash([]);
      const sx=mx+199*Math.sin(sa),sy=my-199*Math.cos(sa);circle(sx,sy,14,'#f9cf55','#8f7946');
      w.sites.forEach(site=>{const x=mx+site.x,y=my+site.y;circle(x,y,site.radius,'#71907855','#4d7055');
        if(site.name==='Oak'){g.fillStyle='#795e3d';g.fillRect(x-3,y-7,6,20);circle(x,y-11,11,'#416e53');circle(x-8,y-6,8,'#567b50');circle(x+7,y-8,8,'#325d46');}
        else if(site.name==='Quarry'){g.fillStyle='#8e8c80';g.beginPath();g.moveTo(x-12,y+9);g.lineTo(x-7,y-10);g.lineTo(x+9,y-6);g.lineTo(x+14,y+9);g.fill();}
        else {g.fillStyle='#e8dfbd';g.fillRect(x-9,y-5,18,17);g.fillStyle='#906c4e';g.beginPath();g.moveTo(x-13,y-5);g.lineTo(x,y-18);g.lineTo(x+13,y-5);g.fill();}
        text(site.name,x,y+site.radius+16>416?y-site.radius-10:y+site.radius+16,'#334d3b',14);
      });
      circle(mx,my,16,'#c9994e','#665333');text('HIVE',mx,my+30,'#475638',11);
      if(s.flight){const f=s.flight,p=Math.min(1,(t-f.start)/w.flight_ms),u=p<.5?p*2:(1-p)*2;g.strokeStyle='#a66e36';g.beginPath();g.moveTo(mx,my);g.lineTo(mx+f.x*u,my+f.y*u);g.stroke();bee(mx+f.x*u,my+f.y*u,Math.atan2(f.x,-f.y)+(p>.5?Math.PI:0));if(p>.45&&p<.7)circle(mx+f.x,my+f.y,5,null,'#aa5d3b');}
      root.querySelector('.waggle-counts').textContent=w.sites.map(site=>`${site.name} ${s.scouts.filter(id=>id===site.id).length}`).join('  /  ');
      root.querySelector('.waggle-recall').disabled=!!s.flight||s.hold!==null||s.done||!s.scouts.length;
      root.querySelector('.waggle-submit').disabled=!!s.flight||s.hold!==null||s.done;
      if(toggle)toggle.disabled=!!s.flight||s.done;
      frame=requestAnimationFrame(draw);
    }
    draw();
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics.waggle_dispatch={rootSelector:'.waggle',render};
})();
