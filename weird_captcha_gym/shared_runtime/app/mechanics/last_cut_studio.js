(() => {
'use strict';
const ID='last_cut_studio'; let raf=0;
function render(s,api){
 cancelAnimationFrame(raf);
 const full=(s.control_condition?.interaction||'full')==='full', source=full?'direct':'proxy';
 let selectedSource=0,selected=-1,edit=[],events=[],frame=0,cutFrame=0,playing=false,view='source',last=performance.now(),drag=null,submitted=false;
 const clips=s.clips, root=document.getElementById('app');
 const $=q=>root.querySelector(q), $$=q=>[...root.querySelectorAll(q)];
 const log=(type,v)=>events.push({seq:events.length+1,type,input_source:source,...v});
 const current=()=>clips[selectedSource], total=()=>edit.reduce((a,c)=>a+c.out_frame-c.in_frame,0);
 const clearFailure=()=>{if($('.lc-notice')?.dataset.status==='error')note('READY — inspect the fresh footage');};
 const note=(text,status='idle')=>{ $('.lc-notice').textContent=text;$('.lc-notice').dataset.status=status;api.setReadout(text,status);};
 const time=f=>(f/s.fps).toFixed(2)+'s';
 const actionName=c=>({leap:'Leap',flight:'Fly',bloom:'Bloom',roll:'Roll'}[c.kind])+(c.cycles===2?' twice':'')+(c.direction===1?' →':' ←');
 root.innerHTML=`<section class="last-cut-studio"><header><div><small>PAPER THEATRE / EDIT SUITE 04</small><h1>Last Cut Studio<span>●</span></h1></div><div class="lc-mode">${full?'FULL · DRAG EDITING':'SIMPLIFIED · BUTTON EDITING'}<br><small>20 frames / second</small></div></header>
 <section class="lc-brief"><b>DIRECTOR’S BRIEF</b><div class="lc-story">${s.brief.map((c,i)=>`<div><canvas width="94" height="58" data-brief="${i}"></canvas><span>${i+1}. ${actionName(c)}</span></div>`).join('')}</div><p>Keep each complete action, in this order.<br>Remove every <strong>slate</strong> and <strong>cleanup hand</strong>.<br><b>${time(s.target_frames)} ± ${time(s.tolerance)}</b> · one continuous cut per shot</p></section>
 <main><aside class="lc-bin"><div class="lc-label">SOURCE REELS <small>${full?'drag to timeline':'select then add'}</small></div>${clips.map((c,i)=>`<button class="lc-reel" data-reel="${i}"><canvas width="92" height="58"></canvas><span>${c.label}<small>${time(c.frames)}</small></span></button>`).join('')}</aside>
 <section class="lc-monitor"><div class="lc-label"><span id="lc-view">SOURCE MONITOR</span><span id="lc-counter"></span></div><canvas id="lc-screen" width="660" height="276"></canvas><div class="lc-transport"><button id="lc-source">SOURCE</button><button id="lc-cut">MONTAGE</button><button id="lc-back">◀ FRAME</button><button id="lc-play">▶ PLAY</button><button id="lc-next">FRAME ▶</button><span id="lc-running"></span></div><div id="lc-scrub" class="lc-scrub"><i></i></div></section>
 <aside class="lc-tools"><div class="lc-label">SELECTED SHOT</div><strong id="lc-selected">No timeline clip</strong><p>Scrub footage to inspect boundaries.<br>${full?'Drag timeline edges to trim.':'Use IN / OUT buttons to trim.'}</p><div id="lc-inout"></div>${!full?'<button id="lc-add">ADD SOURCE TO END</button><div class="lc-nudges">'+['in','out'].map(edge=>`<b>${edge.toUpperCase()}</b>${[-10,-1,1,10].map(d=>`<button data-edge="${edge}" data-delta="${d}">${d>0?'+':''}${d}</button>`).join('')}`).join('')+'</div><button id="lc-left">MOVE EARLIER</button><button id="lc-right">MOVE LATER</button>':''}<button id="lc-delete">REMOVE SELECTED</button></aside></main>
 <section class="lc-edit"><div class="lc-label"><span>TRIM SELECTED CLIP · SOURCE TIME</span><span id="lc-trimlabel">Select a timeline clip</span></div><div class="lc-range"><div class="lc-kept"></div><button class="lc-handle lc-in" aria-label="Trim in">❮</button><button class="lc-handle lc-out" aria-label="Trim out">❯</button></div><div class="lc-label"><span>ASSEMBLED TIMELINE · RIPPLE EDIT</span><b id="lc-duration">0.00s</b></div><div id="lc-ruler" aria-label="Montage playhead"><span>0.00s</span><span id="lc-ruler-end"></span></div><div id="lc-timeline"><span>Drop source reels here to assemble your film</span></div></section>
 <footer><div class="lc-notice">READY — inspect the raw footage</div><button id="lc-export">EXPORT MONTAGE ↗</button></footer></section>`;
 document.body.dataset.mechanic='last-cut-studio';
 function scene(canvas,c,f,brief=false){
  const g=canvas.getContext('2d'),w=canvas.width,h=canvas.height;
  g.clearRect(0,0,w,h);g.save();g.scale(w/660,h/276);
  const skies=['#243e50','#43394e','#354b43'];g.fillStyle=skies[c.backdrop||0];g.fillRect(0,0,660,276);
  g.fillStyle='#dfccaa';g.beginPath();g.moveTo(0,234);g.quadraticCurveTo(130,201,310,231);g.quadraticCurveTo(530,191,660,230);g.lineTo(660,276);g.lineTo(0,276);g.fill();
  g.fillStyle='#ffffff12';for(let i=0;i<16;i++){g.beginPath();g.arc((i*79+38)%660,(i*37)%170+10,2,0,7);g.fill();}
  const a=c.start||0,b=c.end||100,cycles=c.cycles||1;
  let p=brief?.48:Math.max(0,Math.min(1,(f-a+1)/(b-a)));
  let q=p===1?1:(p*cycles)%1;if(f<a&&!brief)q=0;
  g.save();if(c.direction===-1){g.translate(660,0);g.scale(-1,1);}
  let x=130+400*q,y=210;
  g.fillStyle='#14232866';g.beginPath();g.ellipse(x,232,36,7,0,0,7);g.fill();
  g.fillStyle=c.color;g.strokeStyle='#fff4d6';g.lineWidth=3;
  if(c.kind==='leap'){
    y-=125*Math.sin(Math.PI*q);g.beginPath();g.ellipse(x,y,34,23,-.18,0,7);g.fill();g.stroke();
    g.beginPath();g.moveTo(x-30,y);g.lineTo(x-55,y-22);g.lineTo(x-55,y+18);g.closePath();g.fill();
    g.fillStyle='#172e3e';g.beginPath();g.arc(x+17,y-7,4,0,7);g.fill();
    g.fillStyle='#648c9d';g.fillRect(0,246,660,30);
  }else if(c.kind==='flight'){
    y=195-100*Math.sin(Math.PI*q)-45*q;g.save();g.translate(x,y);g.rotate(-.23);
    g.beginPath();g.moveTo(47,0);g.lineTo(-40,-26);g.lineTo(-14,5);g.lineTo(-36,29);g.closePath();g.fill();g.stroke();g.beginPath();g.moveTo(47,0);g.lineTo(-14,5);g.stroke();g.restore();
  }else if(c.kind==='bloom'){
    x=310+55*q;y=205-110*q;g.strokeStyle='#81af88';g.lineWidth=10;g.beginPath();g.moveTo(310,240);g.quadraticCurveTo(305,150,x,y);g.stroke();
    for(let k=0;k<6;k++){let ang=k*Math.PI/3;g.fillStyle=c.color;g.beginPath();g.ellipse(x+Math.cos(ang)*(5+23*q),y+Math.sin(ang)*(5+23*q),9+14*q,8+10*q,ang,0,7);g.fill();}
    g.fillStyle='#f8d574';g.beginPath();g.arc(x,y,9+7*q,0,7);g.fill();
  }else{
    y=207;g.save();g.translate(x,y);g.rotate(q*Math.PI*4);g.fillStyle=c.color;g.fillRect(-27,-27,54,54);g.strokeStyle='#fff4d6';g.strokeRect(-27,-27,54,54);g.fillStyle='#20313d';g.beginPath();g.arc(10,-10,5,0,7);g.fill();g.restore();
  }
  g.restore();
  if(!brief&&f<c.safe_start){g.fillStyle='#17212b';g.fillRect(225,76,215,107);g.fillStyle='#f6edd9';g.font='bold 24px monospace';g.fillText('SLATE',288,143);for(let i=0;i<7;i++){g.fillStyle=i%2?'#e9dec8':'#161e24';g.fillRect(225+i*31,76,31,19);}}
  if(!brief&&f>=c.safe_end){g.fillStyle='#e8aa88';g.fillRect(480,88,180,42);g.beginPath();g.ellipse(475,128,46,57,-.5,0,7);g.fill();g.fillStyle='#533b34';g.font='18px monospace';g.fillText('CREW',535,116);}
  g.restore();
 }
 $$('[data-brief]').forEach((el,i)=>scene(el,s.brief[i],0,true));
 $$('.lc-reel').forEach((el,i)=>scene(el.querySelector('canvas'),clips[i],0,true));
 function refresh(){
  $$('.lc-reel').forEach((el,i)=>el.classList.toggle('chosen',i===selectedSource));
  const e=edit[selected],c=e?clips.find(c=>c.id===e.clip):null;
  $('#lc-selected').textContent=c?c.label:'No timeline clip';
  $('#lc-inout').textContent=e?`IN ${e.in_frame}  /  OUT ${e.out_frame}`:'Drag or add a reel';
  $('#lc-trimlabel').textContent=c?`${c.label} · 0 — ${c.frames} frames`:'';
  $('.lc-range').classList.toggle('disabled',!e);
  if(e){$('.lc-in').style.left=`${100*e.in_frame/c.frames}%`;$('.lc-out').style.left=`${100*e.out_frame/c.frames}%`;$('.lc-kept').style.left=`${100*e.in_frame/c.frames}%`;$('.lc-kept').style.width=`${100*(e.out_frame-e.in_frame)/c.frames}%`;}
  $('.lc-in').disabled=!full||!e;$('.lc-out').disabled=!full||!e;
  $('#lc-duration').textContent=`${time(total())} / ${time(s.target_frames)} ± ${time(s.tolerance)}`;
  const extent=drag?.kind==='timelineTrim'?drag.extent:Math.max(total(),s.target_frames,1);
  let offset=0;
  $('#lc-ruler-end').textContent=time(extent);
  $('#lc-timeline').innerHTML=(edit.length?edit.map((e,i)=>{
   const c=clips.find(c=>c.id===e.clip),length=e.out_frame-e.in_frame,start=offset;offset+=length;
   return `<button class="lc-shot ${i===selected?'chosen':''}" data-shot="${i}" style="left:${start/extent*100}%;width:${length/extent*100}%;--clip:${c.color}">${full?'<span class="lc-edge lc-edge-in" data-edge="in" title="Drag IN edge">❮</span>':''}<b>${c.label}</b><small>${time(start)} → ${time(offset)}</small>${full?'<span class="lc-edge lc-edge-out" data-edge="out" title="Drag OUT edge">❯</span>':''}</button>`;
  }).join(''):'<span>Drop source reels here to assemble your film</span>')+'<i id="lc-cut-playhead"></i>';
  $$('.lc-shot').forEach(el=>{
   const i=Number(el.dataset.shot);
   el.onclick=ev=>{if(!ev.target.closest('.lc-edge'))select(i);};
   if(full)el.onpointerdown=ev=>{
    const edge=ev.target.closest('.lc-edge');
    if(edge){
     const r=$('#lc-timeline').getBoundingClientRect(),value=edit[i][edge.dataset.edge+'_frame'];
     selected=i;
     startDrag(ev,{kind:'timelineTrim',edge:edge.dataset.edge,value,extent,pixelsPerFrame:r.width/extent});
     // Capture on the stable root: ripple redraw replaces the clip element.
     root.setPointerCapture(ev.pointerId);ev.preventDefault();
    }else startDrag(ev,{kind:'move',index:i});
   };
  });
  draw();
 }
 function select(i){selected=i;selectedSource=clips.findIndex(c=>c.id===edit[i].clip);frame=edit[i].in_frame;view='source';playing=false;refresh();}
 function changed(){playing=false;submitted=false;$('#lc-export').disabled=false;note('EDIT UPDATED — preview the new cut');refresh();}
 function add(i){if(edit.length>=8)return;const c=clips[i];log('add',{clip:c.id});edit.push({clip:c.id,in_frame:0,out_frame:c.frames});selected=edit.length-1;selectedSource=i;frame=0;view='source';changed();}
 function move(i,j){if(i===j||j<0||j>=edit.length)return;log('move',{index:i,to:j});edit.splice(j,0,edit.splice(i,1)[0]);selected=j;changed();}
 function trim(edge,value){const e=edit[selected];if(!e)return;selectedSource=clips.findIndex(c=>c.id===e.clip);const c=clips[selectedSource];value=Math.round(value);if(edge==='in')e.in_frame=Math.max(0,Math.min(e.out_frame-1,value));else e.out_frame=Math.min(c.frames,Math.max(e.in_frame+1,value));log('trim',{index:selected,in_frame:e.in_frame,out_frame:e.out_frame});frame=edge==='in'?e.in_frame:e.out_frame-1;view='source';changed();}
 function draw(){
  let c=current(),f=Math.floor(frame),tmax=c.frames;
  if(view==='cut'){
   let offset=Math.min(cutFrame,Math.max(0,total()-1));tmax=total();
   for(const e of edit){const len=e.out_frame-e.in_frame;if(offset<len){c=clips.find(c=>c.id===e.clip);f=e.in_frame+Math.floor(offset);break;}offset-=len;}
  }
  scene($('#lc-screen'),c,f);
  $('#lc-view').textContent=view==='cut'?'MONTAGE · '+c.label:'SOURCE · '+c.label;
  $('#lc-counter').textContent=`${time(view==='cut'?cutFrame:frame)} / ${time(tmax)} · F${f}`;
  $('#lc-play').textContent=playing?'Ⅱ PAUSE':'▶ PLAY';$('#lc-running').textContent=playing?'PLAYING':'PAUSED';
  $('#lc-cut-playhead').style.left=`${100*Math.min(cutFrame,total())/Math.max(total(),s.target_frames,1)}%`;
  $('#lc-cut-playhead').hidden=view!=='cut'||!edit.length;
  $('#lc-scrub i').style.left=`${100*(view==='cut'?cutFrame:frame)/Math.max(tmax,1)}%`;
 }
 function startDrag(ev,data){clearFailure();if(ev.button!==0||submitted)return;drag={...data,x:ev.clientX,y:ev.clientY,node:ev.currentTarget};ev.currentTarget.setPointerCapture(ev.pointerId);}
 $$('.lc-reel').forEach((el,i)=>{el.onclick=()=>{clearFailure();selectedSource=i;frame=0;view='source';playing=false;refresh();};if(full)el.onpointerdown=ev=>startDrag(ev,{kind:'add',index:i});});
 const range=$('.lc-range');
 ['in','out'].forEach(edge=>$('.lc-'+edge).onpointerdown=ev=>{if(full&&edit[selected])startDrag(ev,{kind:'trim',edge});});
 root.onpointermove=ev=>{if(!drag)return;if(drag.kind==='timelineTrim'){trim(drag.edge,drag.value+(ev.clientX-drag.x)/drag.pixelsPerFrame);}else if(drag.kind==='montageScrub'){seekMontage(ev.clientX);}else if(drag.kind==='trim'){const r=range.getBoundingClientRect();const c=clips.find(c=>c.id===edit[selected].clip);const f=Math.round((ev.clientX-r.left)/r.width*c.frames);trim(drag.edge,f);}else if(drag.kind==='scrub')seek(ev.clientX);};
 root.onpointerup=ev=>{
  if(!drag)return;const d=drag;drag=null;
  if(d.kind==='timelineTrim'){trim(d.edge,d.value+(ev.clientX-d.x)/d.pixelsPerFrame);}
  if(d.kind==='trim'){const r=range.getBoundingClientRect();trim(d.edge,(ev.clientX-r.left)/r.width*clips.find(c=>c.id===edit[selected].clip).frames);}
  if(d.kind==='add'||d.kind==='move'){
   const r=$('#lc-timeline').getBoundingClientRect();if(ev.clientY>=r.top&&ev.clientY<=r.bottom&&ev.clientX>=r.left&&ev.clientX<=r.right){
    if(d.kind==='add')add(d.index);else{const boxes=$$('.lc-shot').map(el=>el.getBoundingClientRect());let j=boxes.findIndex(b=>ev.clientX<b.right);move(d.index,j<0?edit.length-1:j);}
   }
  }
 };
 root.onpointercancel=()=>{drag=null;refresh();};
 function seekMontage(x){const r=$('#lc-timeline').getBoundingClientRect();view='cut';playing=false;cutFrame=Math.max(0,Math.min(total()-1,Math.round((x-r.left)/r.width*Math.max(total(),s.target_frames,1))));draw();}
 $('#lc-ruler').onpointerdown=ev=>{if(edit.length){seekMontage(ev.clientX);startDrag(ev,{kind:'montageScrub'});}};
 function seek(x){const r=$('#lc-scrub').getBoundingClientRect();const max=view==='cut'?total():current().frames;const f=Math.max(0,Math.min(max-1,Math.round((x-r.left)/r.width*max)));if(view==='cut')cutFrame=f;else frame=f;playing=false;draw();}
 $('#lc-scrub').onpointerdown=ev=>{seek(ev.clientX);startDrag(ev,{kind:'scrub'});};
 $('#lc-source').onclick=()=>{view='source';playing=false;draw();};
 $('#lc-cut').onclick=()=>{if(edit.length){view='cut';cutFrame=0;playing=false;draw();}};
 $('#lc-back').onclick=()=>{playing=false;if(view==='cut')cutFrame=Math.max(0,Math.floor(cutFrame)-1);else frame=Math.max(0,Math.floor(frame)-1);draw();};
 $('#lc-next').onclick=()=>{playing=false;if(view==='cut')cutFrame=Math.min(total()-1,Math.floor(cutFrame)+1);else frame=Math.min(current().frames-1,Math.floor(frame)+1);draw();};
 $('#lc-play').onclick=()=>{clearFailure();const max=view==='cut'?total():current().frames;if(view==='cut'&&cutFrame>=max-1)cutFrame=0;if(view==='source'&&frame>=max-1)frame=0;playing=!playing;last=performance.now();draw();};
 if(!full){$('#lc-add').onclick=()=>add(selectedSource);$$('[data-edge]').forEach(el=>el.onclick=()=>{const e=edit[selected];if(e)trim(el.dataset.edge,e[el.dataset.edge+'_frame']+Number(el.dataset.delta));});$('#lc-left').onclick=()=>move(selected,selected-1);$('#lc-right').onclick=()=>move(selected,selected+1);}
 $('#lc-delete').onclick=()=>{if(selected<0)return;log('remove',{index:selected});edit.splice(selected,1);selected=Math.min(selected,edit.length-1);changed();};
 $('#lc-export').onclick=async()=>{
  if(submitted)return;playing=false;submitted=true;$('#lc-export').disabled=true;
  const payload={mechanic_id:ID,task_id:s.task_id,challenge_id:s.challenge_id,control_condition:s.control_condition,events,montage:edit};
  try{const response=await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const out=await response.json();
   if(out.passed){note('PASS — MONTAGE EXPORTED','passed');$('.last-cut-studio').classList.add('lc-passed');}
   else if(out.state){render(out.state,api);api.setReadout('FAIL — fresh footage loaded','error');const n=document.querySelector('.lc-notice');n.textContent=out.feedback||'FAIL — fresh footage loaded';n.dataset.status='error';}
   else{note(out.feedback||'EXPORT FAILED','error');submitted=false;$('#lc-export').disabled=false;}
  }catch(e){note('EXPORT ERROR — retry available','error');submitted=false;$('#lc-export').disabled=false;}
 };
 function tick(now){const dt=now-last;last=now;if(playing){const max=view==='cut'?total():current().frames;if(view==='cut')cutFrame=Math.min(max-1,cutFrame+dt*s.fps/1000);else frame=Math.min(max-1,frame+dt*s.fps/1000);if((view==='cut'?cutFrame:frame)>=max-1)playing=false;draw();}raf=requestAnimationFrame(tick);}
 refresh();raf=requestAnimationFrame(tick);
}
window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
window.WeirdCaptchaMechanics[ID]={rootSelector:'.last-cut-studio',render};
})();
