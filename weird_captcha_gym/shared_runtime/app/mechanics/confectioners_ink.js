(() => {
  'use strict';
  const colours = {rose:'#e65b87',mint:'#299e8f',lemon:'#d9a821',white:'#ece7dc'};
  const q = x => Math.floor(x*1e6+.5)/1e6;
  let current;
  // Frictional circle/capsule contact. Drawn and painted surfaces use exactly
  // the endpoints rendered below; two substeps prevent high-speed tunnelling.
  function contact(g,a,b,radius,gate=null,paint=null) {
    const dx=b[0]-a[0],dy=b[1]-a[1],l2=dx*dx+dy*dy;
    if (!l2) return;
    const u=Math.max(0,Math.min(1,((g.x-a[0])*dx+(g.y-a[1])*dy)/l2));
    const x=a[0]+u*dx,y=a[1]+u*dy;
    let nx=g.x-x,ny=g.y-y;const dist=Math.hypot(nx,ny);
    if(dist>=radius+2 || (gate===g.colour && g.vy>=0)) return;
    if(dist<1e-10){
      const length=Math.sqrt(l2);nx=-dy/length;ny=dx/length;
      const approach=nx*g.vx+ny*g.vy;
      if(approach>0 || (approach===0&&(ny>0 || (ny===0&&nx>0)))){nx=-nx;ny=-ny;}
    }else{nx/=dist;ny/=dist;}g.x=x+nx*(radius+2);g.y=y+ny*(radius+2);
    const vn=g.vx*nx+g.vy*ny;
    if(vn<0){g.vx=(g.vx-vn*nx)*.985;g.vy=(g.vy-vn*ny)*.985;}
    if(paint!==null)g.colour=paint;
  }
  function step(m) {
    if(m.done || m.lost || m.submitting)return;
    m.tick++;const w=m.state.world,stage=Math.floor((m.tick-1)/w.batch_ticks);
    if(stage<w.jars.length && (m.tick-1)%w.emit_every===0){
      const i=m.spawned++;let colour=w.colours[stage];if(stage===2 && w.plate)colour='white';
      m.grains.push({x:w.hopper[0]+((i*17)%11-5),y:w.hopper[1],vx:0,vy:0,colour});
    }
    const alive=[];
    for(const g of m.grains){
      const oldY=g.y;
      for(let sub=0;sub<2;sub++){
        g.vy=Math.min(5.5,g.vy+.07);g.vx*=.998;g.x+=g.vx*.5;g.y+=g.vy*.5;
        for(const [a,b] of m.lines)contact(g,a,b,2);
        if(w.plate)contact(g,w.plate.a,w.plate.b,w.plate.radius,null,w.plate.colour);
        for(const p of w.pegs)contact(g,[p.x-.000001,p.y],[p.x+.000001,p.y],p.radius);
        for(const j of w.jars){const x=j.x,r=j.width/2,y=j.y;
          contact(g,[x-r,y-16],[x+r,y-16],2,j.colour);
          contact(g,[x-r,y],[x-r,515],3);contact(g,[x+r,y],[x+r,515],3);
        }
        for(const k of ['x','y','vx','vy'])g[k]=q(g[k]);
      }
      let collected=false;
      for(let i=0;i<w.jars.length;i++){
        const j=w.jars[i];
        if(oldY<j.y && j.y<=g.y && Math.abs(g.x-j.x)<j.width/2-3){
          m.tallies[i][g.colour]=(m.tallies[i][g.colour]||0)+1;
          if(g.colour!==j.colour)m.waste++;
          collected=true;break;
        }
      }
      if(collected)continue;
      if(g.y>530 || g.x<0 || g.x>900)m.waste++;else alive.push(g);
    }
    m.grains=alive;
    m.done=w.jars.every((j,i)=>(m.tallies[i][j.colour]||0)>=j.required && Object.entries(m.tallies[i]).every(([c,n])=>c===j.colour || n===0));
    m.lost=m.waste>w.max_waste || m.tick>=w.max_ticks;
  }
  function advance(m) {
    if(current!==m || m.submitting)return;
    const target=Math.floor((performance.now()-m.started)/m.state.world.tick_ms+1e-7);
    while(m.tick<target && !m.done && !m.lost)step(m);
  }
  function draw(m){
    if(current!==m)return;
    const w=m.state.world,c=m.canvas.getContext('2d');
    c.fillStyle='#fff5df';c.fillRect(0,0,900,530);
    c.fillStyle='#dfcdaa';for(let x=22;x<900;x+=28)for(let y=24;y<435;y+=28){c.beginPath();c.arc(x,y,.7,0,7);c.fill();}
    const line=(a,b,colour,width)=>{c.strokeStyle=colour;c.lineWidth=width;c.lineCap='round';c.beginPath();c.moveTo(...a);c.lineTo(...b);c.stroke();};
    const stage=Math.min(w.jars.length-1,Math.floor(m.tick/w.batch_ticks));
    c.fillStyle='#542c3d';c.beginPath();c.moveTo(w.hopper[0]-43,8);c.lineTo(w.hopper[0]+43,8);c.lineTo(w.hopper[0]+10,57);c.lineTo(w.hopper[0]-10,57);c.closePath();c.fill();
    c.fillStyle=colours[stage===2&&w.plate?'white':w.colours[stage]];c.fillRect(w.hopper[0]-24,14,48,15);
    c.font='bold 12px monospace';c.textAlign='center';c.fillStyle='#542c3d';c.fillText('HOPPER',w.hopper[0],76);
    w.pegs.forEach(p=>{c.fillStyle='#c3aa86';c.strokeStyle='#725441';c.lineWidth=3;c.beginPath();c.arc(p.x,p.y,p.radius,0,7);c.fill();c.stroke();c.fillStyle='#725441';c.fillRect(p.x-5,p.y-1,10,2);});
    if(w.plate){const p=w.plate;line(p.a,p.b,'#873b28',p.radius*2);line(p.a,p.b,colours[p.colour],4);c.fillStyle='#873b28';c.font='bold 12px monospace';c.fillText('HOT → '+p.colour.toUpperCase(),(p.a[0]+p.b[0])/2,(p.a[1]+p.b[1])/2+31);}
    for(const j of w.jars){
      const i=w.jars.indexOf(j),x=j.x,r=j.width/2,y=j.y,n=m.tallies[i][j.colour]||0;
      c.fillStyle=colours[j.colour]+'44';c.fillRect(x-r+3,y+58-Math.min(52,n/j.required*38),j.width-6,Math.min(52,n/j.required*38));
      line([x-r,y],[x-r,515],'#674951',6);line([x+r,y],[x+r,515],'#674951',6);line([x-r,515],[x+r,515],'#674951',6);
      line([x-r,y-16],[x+r,y-16],colours[j.colour],4);
      c.fillStyle=colours[j.colour];c.font='bold 14px monospace';c.textAlign='center';c.fillText('↓',x,y-23);
      c.setLineDash([4,4]);line([x-r+3,y+20],[x+r-3,y+20],'#674951',1);c.setLineDash([]);
      c.fillStyle='#452437';c.font='bold 12px monospace';c.fillText(j.colour.toUpperCase(),x,y+39);c.fillText(`${n}/${j.required}`,x,y+55);
      const foreign=Object.entries(m.tallies[i]).reduce((total,[colour,count])=>total+(colour===j.colour?0:count),0);
      if(foreign){c.fillStyle='#9b273c';c.fillText(`MIXED +${foreign}`,x,y+10);}
    }
    for(const [a,b] of m.lines)line(a,b,'#422742',4);
    for(const g of m.grains){c.fillStyle='#79515b';c.beginPath();c.arc(g.x,g.y,2,0,7);c.fill();c.fillStyle=colours[g.colour];c.beginPath();c.arc(g.x,g.y,1.4,0,7);c.fill();}
    if(m.last){c.strokeStyle='#e65b87';c.lineWidth=2;c.beginPath();c.arc(...m.last,7,0,7);c.stroke();}
    document.getElementById('ink-stock').textContent=Math.max(0,w.ink_budget-Math.ceil(m.ink));
    document.getElementById('ink-waste').textContent=`${m.waste} / ${w.max_waste}`;
    document.getElementById('ink-batch').textContent=`${Math.min(stage+1,w.jars.length)} / ${w.jars.length}`;
    document.getElementById('ink-material').style.width=`${Math.max(0,100*(1-m.spawned/(w.batch_grains*w.jars.length)))}%`;
    document.getElementById('ink-submit').disabled=!m.done || m.submitting;
    if(m.done || m.lost){
      m.last=null;m.holding=false;
      const v=document.getElementById('ink-verdict');v.hidden=false;
      const reason=m.failureReason || (m.waste>w.max_waste?'Too much sugar wasted':'Sugar stock exhausted before a pure fill');
      v.innerHTML=m.done?'<b>JARS FILLED</b><span>Ready to seal</span>':`<b>FAIL</b><span>${reason}. Start a fresh cabinet.</span>`;
      m.helpers.setReadout(m.done?'READY TO SEAL':'FAIL',m.done?'idle':'error');
    }
  }
  async function submit(m,abandon=false){
    advance(m);
    if(m.submitting)return;m.submitting=true;
    const payload={mechanic_id:m.state.mechanic_id,task_id:m.state.task_id,challenge_id:m.state.challenge_id,events:m.events,tick:m.tick,tallies:m.tallies,waste:m.waste,ink:m.ink,completed:m.done&&!abandon};
    try{
      const response=await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)});
      const outcome=await response.json();
      if(outcome.passed){cancelAnimationFrame(m.timer);m.helpers.setReadout('PASS','passed');document.getElementById('ink-verdict').innerHTML='<b>PASS</b><span>Confectionery sealed</span>';}
      else if(outcome.state){cancelAnimationFrame(m.timer);await render(outcome.state,m.helpers);current.helpers.setReadout('FRESH CABINET','idle');}
      else {m.submitting=false;m.helpers.setReadout('FAIL','error');}
    }catch(e){m.submitting=false;m.helpers.setReadout('CONNECTION LOST · RETRY SEAL','error');}
  }
  async function render(state,helpers){
    if(current)cancelAnimationFrame(current.timer);
    document.body.dataset.mechanic='confectioners-ink';
    const mode=state.control_condition?.interaction||'full';
    helpers.app.innerHTML=`<section class="confectioners-ink"><header><div><small>THE SUGAR CABINET · No. 07</small><h1>Confectioner's Ink</h1></div><p>Draw the way down.<br>Fill every jar with its own colour.</p></header><main><div class="ink-glass"><canvas id="ink-canvas" width="900" height="530" aria-label="Sugar cabinet drawing surface"></canvas><div id="ink-verdict" hidden></div></div><aside><span class="ink-label">PERMANENT INK</span><strong id="ink-stock"></strong><span class="ink-unit">pixels remaining</span><hr><span class="ink-label">SUGAR STOCK</span><div class="ink-meter"><i id="ink-material"></i></div><dl><dt>Batch</dt><dd id="ink-batch"></dd><dt>Wasted</dt><dd id="ink-waste"></dd></dl><p class="ink-instructions">${mode==='full'?'Press · draw · release':'Click successive corners'}<br>Each line becomes a solid chute.<br><br>Coloured gates let only matching sugar fall through. ${state.world.plate?'The hot plate recolours on contact.':''}</p>${mode==='simplified'?'<button id="ink-finish">Finish stroke</button>':''}<button id="ink-retry">Fresh cabinet ↻</button></aside></main><footer><div class="readout" data-status="idle">HOPPER POURING</div><span>INK CANNOT BE ERASED</span><button id="ink-submit" disabled>Seal the jars →</button></footer></section>`;
    const m={state,helpers,mode,tick:0,spawned:0,grains:[],lines:[],ink:0,waste:0,tallies:state.world.jars.map(()=>({})),events:[],last:null,holding:false,done:false,lost:false,submitting:false,canvas:document.getElementById('ink-canvas')};
    m.started=performance.now();current=m;window.confectionersInkModel=m;
    const point=e=>{const r=m.canvas.getBoundingClientRect();return [Math.round(Math.max(0,Math.min(900,(e.clientX-r.left)*900/r.width))*100)/100,Math.round(Math.max(70,Math.min(435,(e.clientY-r.top)*530/r.height))*100)/100];};
    const event=(type,p)=>{m.events.push({type,tick:m.tick,source:mode==='full'?'freehand':'vertices',...(p?{point:p}:{})});};
    const add=p=>{
      advance(m);
      if(m.done||m.lost||m.submitting)return;
      if(!m.last){m.last=p;event('begin',p);}
      else if(Math.hypot(p[0]-m.last[0],p[1]-m.last[1])>=.5){
        const length=Math.hypot(p[0]-m.last[0],p[1]-m.last[1]);event('point',p);
        if(m.ink+length>state.world.ink_budget+1e-6){m.lost=true;m.failureReason='This segment exceeds the remaining ink';}
        else{m.ink+=length;m.lines.push([m.last,p]);m.last=p;}
      }
      draw(m);
    };
    const end=()=>{advance(m);if(m.last&&!m.done&&!m.lost){event('end');m.last=null;}m.holding=false;draw(m);};
    m.canvas.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();if(mode==='full'){m.holding=true;m.canvas.setPointerCapture(e.pointerId);add(point(e));}});
    m.canvas.addEventListener('pointermove',e=>{if(mode==='full'&&m.holding)add(point(e));});
    m.canvas.addEventListener('pointerup',e=>{if(mode==='full'&&m.holding){add(point(e));end();}});
    m.canvas.addEventListener('pointercancel',end);
    if(mode==='simplified'){m.canvas.addEventListener('click',e=>add(point(e)));document.getElementById('ink-finish').onclick=end;}
    document.getElementById('ink-retry').onclick=()=>submit(m,true);
    document.getElementById('ink-submit').onclick=()=>submit(m);
    const frame=()=>{if(current!==m)return;advance(m);if(!m.submitting)draw(m);m.timer=requestAnimationFrame(frame);};
    draw(m);m.timer=requestAnimationFrame(frame);
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics.confectioners_ink={rootSelector:'.confectioners-ink',render};
})();
