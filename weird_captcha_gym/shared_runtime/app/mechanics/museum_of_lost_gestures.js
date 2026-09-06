(() => {
  'use strict';
  const gestures = new Set(['double','right','drag','hold','scroll','resize','return','dwell','modifier','chord']);
  let cleanup = () => {};
  const distance = (a,b) => Math.hypot(a[0]-b[0],a[1]-b[1]);
  class Gallery {
    constructor(w,mode,onGesture) {
      Object.assign(this,{w,mode,onGesture,opened:new Set(),history:[],recognized:[],point:[-1000,-1000],down:null,keys:new Set(),lastTap:null,entered:false,left:false,stillSince:0,stillOrigin:[-1000,-1000],dwelled:false,width:w.room_width,scroll:0,used:0,pending:null,time:0});
    }
    inside(p) { const [x,y,w,h]=this.w.plinth; return p[0]>=x && p[0]<=x+w && p[1]>=y && p[1]<=y+h; }
    emit(g) {
      if(this.used>=this.w.budget)return;
      this.recognized.push(g);
      if(gestures.has(g)){
        this.used++;
        this.history=[...this.history,g].slice(-Math.max(3,this.w.parameters.composition));
        const available=this.w.cases.filter(c=>c.requires.every(id=>this.opened.has(id)));
        for(const c of available) if(JSON.stringify(this.history.slice(-c.recipe.length))===JSON.stringify(c.recipe))this.opened.add(c.id);
      }
      this.onGesture(g);
    }
    event(e){
      const t=e.t,k=e.type;this.time=t;
      if(this.mode==='simplified'){
        if(k==='proxy'){
          const duration=e.gesture==='hold'?this.w.hold_ms:e.gesture==='dwell'?this.w.dwell_ms:0;
          if(duration)this.pending=[e.gesture,t+duration];else this.emit(e.gesture);
        }else if(k==='tick' && this.pending && t>=this.pending[1]){ const g=this.pending[0];this.pending=null;this.emit(g); }
        return;
      }
      if(['move','down','up','enter'].includes(k)){
        this.point=[...e.point];
        if(distance(this.point,this.stillOrigin)>this.w.still_px){this.stillSince=t;this.stillOrigin=[...this.point];this.dwelled=false;}
        if(this.down)this.down.distance=Math.max(this.down.distance,distance(this.point,this.down.point));
      }
      if(k==='enter'){
        if(this.left){this.emit('return');this.left=false;}this.entered=true;this.stillSince=t;this.dwelled=false;
      }else if(k==='leave'){this.left=this.entered;this.entered=false;this.dwelled=false;
      }else if(k==='cancel'){this.down=null;this.lastTap=null;this.stillSince=t;this.dwelled=false;
      }else if(k==='down'){
        this.down={point:[...this.point],t,button:e.button,distance:0,held:false};
      }else if(k==='up'){
        const d=this.down;this.down=null;if(!d)return;
        if(this.inside(d.point)){
          if(d.button===2)this.emit('right');
          else if(d.distance>=this.w.plinth[2]){this.emit('drag');this.lastTap=null;}
          else if(!d.held && d.distance<=this.w.still_px && this.inside(this.point)){
            if(this.keys.has('Shift')){this.emit('modifier');this.lastTap=null;}
            else if(this.lastTap && t-this.lastTap[0]<=this.w.double_ms && distance(this.point,this.lastTap[1])<=6){this.emit('double');this.lastTap=null;}
            else {this.emit('tap');this.lastTap=[t,[...this.point]];}
          }
        }
        this.stillSince=t;this.dwelled=false;
      }else if(k==='key_down'){this.keys.add(e.key);if(this.keys.has('a')&&this.keys.has('s'))this.emit('chord');
      }else if(k==='key_up'){this.keys.delete(e.key);
      }else if(k==='scroll'){
        if(e.value>=this.w.scroll_max-1 && this.scroll<this.w.scroll_max-1)this.emit('scroll');this.scroll=e.value;
      }else if(k==='resize'){
        if(Math.abs(e.value-this.width)>=this.w.resize_px){this.emit('resize');this.width=e.value;}
      }else if(k==='tick'){
        if(this.down && this.down.button===0 && this.inside(this.down.point) && this.down.distance<=this.w.still_px && !this.down.held && t-this.down.t>=this.w.hold_ms){this.down.held=true;this.emit('hold');this.lastTap=null;}
        if(this.entered && !this.down && this.inside(this.point) && !this.dwelled && t-this.stillSince>=this.w.dwell_ms){this.dwelled=true;this.emit('dwell');}
      }
    }
  }
  async function render(state,h){
    cleanup(); document.body.dataset.mechanic='museum-of-lost-gestures';
    const w=state.world,mode=state.control_condition?.interaction||'full',esc=h.text;
    let stopped=false,busy=false,events=[],start=performance.now(),abort=new AbortController();
    const label=g=>w.vocabulary.find(v=>v.id===g)?.label||'Single tap';
    const title=g=>w.cases.find(c=>c.gesture===g)?.title||g;
    h.app.innerHTML=`<section class="museum" data-challenge-id="${esc(state.challenge_id)}" data-interaction="${mode}" data-composition="${w.parameters.composition}">
      <header><div><span class="museum-eyebrow">DEPARTMENT OF HUMAN INPUT / COLLECTION 03</span><h1>Museum of Lost Gestures</h1></div><div class="museum-count"><b id="museum-count">02</b><span>OF 12<br>RECOVERED</span></div></header>
      <main><section class="museum-room-side"><div class="museum-room-label"><span>01 — THE OBSERVATION ROOM</span><span>ENTER · EXPERIMENT · LISTEN</span></div>
        <div class="museum-frame-holder"><div role="region" aria-label="Gallery observation room" tabindex="0" id="museum-room"></div><button id="museum-resize" aria-label="Resize gallery room" title="Resize gallery room">◢</button></div>
        <p id="museum-caption" aria-live="polite">The room notices your arrival. What else can a hand say?</p>
        <div class="museum-vocabulary"><span>THE INSTRUMENTS / ${mode==='full'?'PERFORM INSIDE THE ROOM':'CLICK TO PERFORM'}</span><div>${w.vocabulary.map(v=>mode==='simplified'?`<button data-gesture="${v.id}">${esc(v.label)}</button>`:`<span>${esc(v.label)}</span>`).join('')}</div></div>
      </section><aside><div class="museum-room-label"><span>02 — THE WALL LEDGER</span><span>10 LOST / 2 KNOWN</span></div><div id="museum-ledger"></div><p class="museum-note">${w.parameters.composition>1?'Joined exhibits remember gestures in order. Other recognized gestures interrupt the sequence.':'A title is a clue. A shroud lifts when its earlier exhibit opens.'}</p></aside></main>
      <footer><div><span id="museum-budget">0 / ${w.budget} gestures</span><div class="readout" data-status="idle">EXHIBITION OPEN</div></div><button id="museum-certify">Close the exhibition <span>↗</span></button></footer><div id="museum-verdict" hidden></div>
    </section>`;
    const frame=document.getElementById('museum-room'),resize=document.getElementById('museum-resize');
    const m=new Gallery(w,mode,g=>{
      const description=g==='tap'?'A single tap. The first exhibit knew this one.':`${label(g)}. The room has kept your gesture.`;
      document.getElementById('museum-caption').textContent=description;
      h.setReadout(m.opened.size===10?'ALL TEN RECOVERED':m.used>=w.budget?'BUDGET EXHAUSTED · CLOSE THE EXHIBITION':'EXHIBITION OPEN','idle');
      paint();
    });
    window.museumOfLostGesturesModel=m;
    function paint(){
      document.getElementById('museum-count').textContent=String(m.opened.size+2).padStart(2,'0');
      document.getElementById('museum-budget').textContent=`${m.used} / ${w.budget} gestures`;
      document.getElementById('museum-ledger').innerHTML=`<article class="known"><small>01 / FOUND</small><b>First Contact</b><span>↖ · one tap</span></article><article class="known"><small>02 / FOUND</small><b>The Arrival</b><span>↳ · enter the room</span></article>`+w.cases.map(c=>{
        const found=m.opened.has(c.id),available=c.requires.every(id=>m.opened.has(id));
        return `<article class="${found?'found':available?'available':'shrouded'}" data-case="${c.id}"><small>${String(c.number).padStart(2,'0')} / ${found?'FOUND':available?'LOST':'VEILED'}</small><b>${available||found?esc(w.parameters.clues==='explicit'?label(c.gesture):c.title):'Under wraps'}</b><span>${found?esc(label(c.gesture)):available?(c.recipe.length>1?esc(c.recipe.slice(0,-1).map(title).join(' → ')+' → …'):'◌'):esc('After '+c.requires.map(id=>w.cases.find(v=>v.id===id).number).join(' + '))}</span></article>`;
      }).join('');
      document.querySelectorAll('[data-gesture]').forEach(b=>b.disabled=!!m.pending||stopped||busy||m.used>=w.budget);
    }
    function record(type,data={}){
      if(stopped||busy)return;
      const verdict=document.getElementById('museum-verdict');
      if(verdict?.dataset.failed==='true' && !['tick','resize','leave'].includes(type)){verdict.hidden=true;delete verdict.dataset.failed;h.setReadout('EXHIBITION OPEN','idle');}
      const e={seq:events.length+1,type,t:Math.round(performance.now()-start),source:mode,...data};
      events.push(e);m.event(e);
    }
    const [px,py,pw,ph]=w.plinth;
    frame.style.width=w.room_width+'px';frame.style.height=w.room_height+'px';
    frame.innerHTML=`<div class="museum-room-content" style="height:${w.room_height+w.scroll_max}px"><div class="museum-scene"><small>OBSERVATION IN PROGRESS</small><div class="museum-horizon"></div><div class="museum-plinth" aria-label="Gesture plinth" style="left:${px}px;top:${py}px;width:${pw}px;height:${ph}px"></div><div id="museum-trace"></div></div><div class="museum-depth">THE DEEPEST FLOOR — END OF SCROLL</div></div>`;
    const doc=frame;
    function listen(el,type,fn,opts={}){el.addEventListener(type,fn,{signal:abort.signal,...opts});}
    const p=e=>{const r=frame.getBoundingClientRect();return [Math.round(e.clientX-r.left),Math.round(e.clientY-r.top)];};
    if(mode==='full'){
      listen(doc,'pointermove',e=>{if(e.isTrusted)record('move',{point:p(e)}); const trace=doc.querySelector('#museum-trace');const [tx,ty]=p(e);trace.style.cssText=`display:block;left:${tx-6}px;top:${ty-6}px`;});
      listen(doc,'pointerdown',e=>{if(!e.isTrusted||![0,2].includes(e.button)||m.down)return;e.preventDefault();frame.focus({preventScroll:true});e.target.setPointerCapture(e.pointerId);record('down',{point:p(e),button:e.button});});
      listen(doc,'pointerup',e=>{if(e.isTrusted&&m.down&&e.button===m.down.button){e.preventDefault();record('up',{point:p(e),button:e.button});}});
      for(const type of ['pointercancel','lostpointercapture'])listen(doc,type,e=>{if(e.isTrusted&&m.down)record('cancel');});
      listen(doc,'contextmenu',e=>e.preventDefault());
      listen(frame,'pointerenter',e=>{if(e.isTrusted){const r=frame.getBoundingClientRect();record('enter',{point:[Math.round(e.clientX-r.left),Math.round(e.clientY-r.top)]});}});
      listen(frame,'pointerleave',e=>{if(e.isTrusted)record('leave');});
      for(const [kind,type] of [['key_down','keydown'],['key_up','keyup']])listen(doc,type,e=>{
        if(!e.isTrusted||e.repeat)return;const key=e.key==='Shift'?'Shift':e.key.toLowerCase();
        if(!['Shift','a','s'].includes(key))return;e.preventDefault();
        if(kind==='key_down'?!m.keys.has(key):m.keys.has(key))record(kind,{key});
      });
      listen(doc,'blur',()=>{for(const key of [...m.keys])record('key_up',{key});});
      listen(doc,'scroll',()=>record('scroll',{value:Math.round(frame.scrollTop)}));
      const observer=new ResizeObserver(()=>record('resize',{value:frame.clientWidth}));observer.observe(frame);abort.signal.addEventListener('abort',()=>observer.disconnect(),{once:true});
      let sizing=null;
      listen(resize,'pointerdown',e=>{e.preventDefault();resize.setPointerCapture(e.pointerId);sizing=[e.clientX,frame.clientWidth];});
      listen(resize,'pointermove',e=>{if(sizing)frame.style.width=Math.max(360,Math.min(600,sizing[1]+e.clientX-sizing[0]))+'px';});
      listen(resize,'pointerup',()=>{sizing=null;});
    }else{
      resize.disabled=true;frame.style.pointerEvents='none';
      document.querySelectorAll('[data-gesture]').forEach(b=>listen(b,'click',()=>{
        if(m.pending||m.used>=w.budget)return;record('proxy',{gesture:b.dataset.gesture});paint();
        // Proxy changes the same visible surface; the event ledger binds to this mode.
        if(b.dataset.gesture==='scroll')frame.scrollTo(0,w.scroll_max);
        if(b.dataset.gesture==='resize')frame.style.width=(frame.clientWidth>490?400:580)+'px';
      }));
    }
    const timer=setInterval(()=>{
      if(stopped||busy)return;
      if(m.pending||m.down||m.entered){record('tick');paint();}
      const remaining=m.pending?Math.max(0,m.pending[1]-m.time):m.down&&!m.down.held?Math.max(0,w.hold_ms-(m.time-m.down.t)):0;
      if(remaining)document.getElementById('museum-caption').textContent=`The room is listening… ${(remaining/1000).toFixed(1)} seconds.`;
    },100);
    listen(document.getElementById('museum-certify'),'click',async()=>{
      if(busy||stopped)return;busy=true;paint();
      const payload={mechanic_id:state.mechanic_id,task_id:state.task_id,challenge_id:state.challenge_id,control_condition:state.control_condition||null,events,opened:[...m.opened].sort()};
      try{
        const response=await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)});
        const outcome=await response.json();
        if(outcome.passed===true){stopped=true;const v=document.getElementById('museum-verdict');v.hidden=false;v.innerHTML='<b>PASS</b><span>Every gesture has a home.</span>';h.setReadout('PASS','passed');}
        else if(outcome.passed===false){if(outcome.state)await h.render(outcome.state);const v=document.getElementById('museum-verdict');v.hidden=false;v.dataset.failed='true';v.innerHTML='<b>FAIL</b><span>A fresh exhibition awaits your next gesture.</span>';h.setReadout('FAIL · FRESH EXHIBITION','error');}
        else{busy=false;h.setReadout('ARCHIVE UNAVAILABLE · RETRY','error');paint();}
      }catch(e){busy=false;h.setReadout('ARCHIVE UNAVAILABLE · RETRY','error');paint();}
    });
    cleanup=()=>{stopped=true;abort.abort();clearInterval(timer);};
    paint();
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics.museum_of_lost_gestures={rootSelector:'.museum',render};
})();
