(() => {
  'use strict';
  const colors={amber:'#ffc568',cyan:'#65e4e0',violet:'#bb9eff'};
  let timer=null, cleanup=null;
  function render(state,h) {
    if(timer)clearInterval(timer); if(cleanup)cleanup();
    const w=state.world,p=w.parameters,mode=state.control_condition?.interaction||'full',surface=mode==='full'?'direct':'proxy';
    const s={x:w.start,move:0,hidden:false,item:false,caught:false,overlay:false,gates:Object.fromEntries(w.gates.map(g=>[g.id,false])),light:true,wires:{...w.wires},permissions:[...w.initial_permissions],gx:w.guard_x,gd:w.guard_dir,repair:0,tick:0,service_count:0};
    let events=[],busy=false,terminal=false,pendingSubmission=null,selected=null,drag=null,message='Recover the archive case. Return to the green exit.';
    document.body.dataset.mechanic='switchline-heist';
    h.app.innerHTML=`<section class="switchline-heist"><header><div><small>NIGHT OPERATIONS / CIRCUIT DIVISION</small><h1>Switchline Heist</h1></div><div class="sh-badges"></div></header><div class="sh-toolbar"><button id="sh-overlay">CIRCUIT OVERLAY</button><span id="sh-mode"></span><span id="sh-inventory">CASE ○</span></div><div class="sh-stage"><canvas width="1000" height="400"></canvas><div id="sh-verdict"></div></div><footer><div class="sh-controls">${mode==='simplified'?'<button id="sh-left">◀ WALK</button><button id="sh-right">WALK ▶</button><button id="sh-hide">HIDE / LEAVE</button><button id="sh-use">USE SWITCH</button><button id="sh-pickup">TAKE CASE</button>':'<span>← → walk · E switch · Space hide · F take case</span>'}<button id="sh-extract">EXTRACT</button><button id="sh-retry">RETRY</button></div><div class="readout" data-status="idle"></div></footer></section>`;
    const root=h.app.querySelector('.switchline-heist'),canvas=root.querySelector('canvas'),ctx=canvas.getContext('2d');
    const $=id=>root.querySelector(id);
    function blocked(a,b){return w.gates.some(g=>!s.gates[g.id]&&Math.min(a,b)-18<g.x&&g.x<Math.max(a,b)+18);}
    function detect(){if(s.hidden||s.x<w.archive_start)return;let d=s.x-s.gx;if(Math.abs(d)<22||(s.light&&d*s.gd>=0&&d*s.gd<=p.sight)){s.caught=true;s.move=0;message='CAUGHT · the attendant spotted you.';$('#sh-verdict').textContent='CAUGHT';$('#sh-verdict').className='fail';}}
    function output(target){if(target==='lamp'){s.light=!s.light;s.repair=0;}else if(target in s.gates){const g=w.gates.find(g=>g.id===target);if(s.gates[target]&&Math.abs(s.x-g.x)<18)return;s.gates[target]=!s.gates[target];if(s.gates[target]&&p.interlock)for(const g of w.gates)if(g.id!==target&&Math.abs(s.x-g.x)>=18)s.gates[g.id]=false;}}
    function record(type,data={}){events.push({seq:events.length+1,tick:s.tick,type,input_source:surface,...data});}
    function act(type,data={}){
      if(busy||terminal||pendingSubmission||s.caught)return;
      if(type==='wire'){
        const src=w.switches.find(x=>x.id===data.source),dst=w.outputs.find(x=>x.id===data.target);
        if(!s.overlay||!src||!dst||src.color!==dst.color||!s.permissions.includes(src.color)||(src.kind==='attendant'&&dst.kind!=='gate')){message='LINK REFUSED · match an unlocked circuit; service relay drives gates only.';draw();return;}
        record(type,data);s.wires[src.id]=dst.id;message='Connection replaced. Operate the switch in the building.';
      }else if(type==='overlay'){record(type);s.overlay=!s.overlay;s.move=0;selected=null;}
      else if(type==='move'){record(type,data);s.move=data.direction;}
      else if(type==='hide'){record(type);if(!s.overlay&&w.booths.some(x=>Math.abs(s.x-x)<=25)){s.hidden=!s.hidden;s.move=0;}}
      else if(type==='use'){
        const src=w.switches.filter(x=>x.kind==='switch'&&Math.abs(s.x-x.x)<=38&&!blocked(s.x,x.x)).sort((a,b)=>Math.abs(s.x-a.x)-Math.abs(s.x-b.x))[0];
        if(s.overlay||!src){message='Move next to a wall switch.';draw();return;}
        record(type,{source:src.id});output(s.wires[src.id]);message=`Switch ${src.label} operated.`;
      }else if(type==='pickup'){if(s.overlay||Math.abs(s.x-w.item)>24||s.item)return;record(type);s.item=true;if(p.alarm){s.light=true;s.repair=0;}message=p.alarm?'CASE TAKEN · archive light alarm!':'Case secured. Return to exit.';}
      detect();draw();
    }
    function step(){if(busy||terminal||pendingSubmission||s.caught)return;s.tick++;
      if(s.move&&!s.overlay&&!s.hidden){const x=Math.max(44,Math.min(962,s.x+s.move*w.player_speed));if(!blocked(s.x,x))s.x=x;}
      for(const chip of w.chips)if(Math.abs(s.x-chip.x)<=22&&!s.permissions.includes(chip.color)){s.permissions.push(chip.color);message='Circuit access acquired.';}
      if(!s.light){s.gd=1;s.gx=Math.min(948,s.gx+w.guard_speed);if(s.gx===948){s.repair++;if(s.repair>=p.repair_ticks){s.light=true;s.repair=0;s.service_count++;output(s.wires.service);message='Attendant restored the light and operated SERVICE.';}}}
      else{s.gx+=s.gd*w.guard_speed;if(s.gx>=948){s.gx=948;s.gd=-1;}if(s.gx<=808){s.gx=808;s.gd=1;}}
      detect();draw();
    }
    function rect(x,y,a,b,color){ctx.fillStyle=color;ctx.fillRect(x,y,a,b);}
    function text(t,x,y,color='#dae7e8',size=12){ctx.fillStyle=color;ctx.font=`${size}px ui-monospace,monospace`;ctx.textAlign='center';ctx.fillText(t,x,y);}
    function circle(x,y,r,color){ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();}
    function draw(){
      rect(0,0,1000,400,'#101d2b');
      for(let x=10;x<1000;x+=60){rect(x,25,34,100,'#203446');rect(x+4,30,26,45,'#293e50');}
      rect(24,142,952,228,'#263a49');rect(w.archive_start,142,976-w.archive_start,228,s.light?'#5b5140':'#172939');
      for(let x=30;x<975;x+=32)rect(x,362,30,8,'#506674');
      rect(34,252,45,108,'#256d67');text('EXIT',56,240,'#9bffe2',14);
      text('PUBLIC WING',170,170,'#91a9b7',13);text('SECURED ARCHIVE',850,165,'#eed8a8',14);
      for(const x of w.booths){rect(x-25,266,50,96,'#15202d');rect(x-22,270,44,5,'#7692a0');text('HIDE',x,386,'#9ebbc5',11);}
      for(const g of w.gates){rect(g.x-8,192,16,s.gates[g.id]?20:168,colors[g.color]);text(g.label||`G${w.gates.indexOf(g)+1}`,g.x,182,colors[g.color],12);}
      for(const chip of w.chips){rect(chip.x-13,224,26,28,s.permissions.includes(chip.color)?'#3d5960':colors[chip.color]);text('ACCESS',chip.x,217,colors[chip.color],9);}
      for(const sw of w.switches){rect(sw.x-14,238,28,32,colors[sw.color]);rect(sw.x-3,245,6,18,'#203343');text(sw.label,sw.x,230,colors[sw.color],11);}
      circle(850,197,14,s.light?'#ffeab6':'#445564');text(s.light?'LIGHT ON':'LIGHT OFF',850,222,'#e0cea3',10);
      if(!s.item){if(p.alarm)text('ALARM CASE',w.item,288,'#ffc568',10);rect(w.item-13,329,26,18,'#ecc872');rect(w.item-6,323,12,6,'#ecc872');}
      if(s.light){ctx.fillStyle='#f8da6540';ctx.beginPath();ctx.moveTo(s.gx,305);ctx.lineTo(s.gx+s.gd*p.sight,278);ctx.lineTo(s.gx+s.gd*p.sight,355);ctx.closePath();ctx.fill();}
      rect(s.gx-10,316,20,42,'#d88e6f');circle(s.gx,306,10,'#e5b68e');rect(s.gx-12,296,24,7,'#a56e5c');
      if(!s.light&&s.gx===948){rect(913,278,60,5,'#304c59');rect(913,278,60*s.repair/p.repair_ticks,5,'#ffc568');}
      if(!s.hidden){rect(s.x-10,320,20,38,s.caught?'#fb6b69':'#77d6d1');circle(s.x,310,9,'#d9f4e6');if(s.item)rect(s.x+8,337,12,9,'#ecc872');}else text('●',s.x,315,'#77d6d1',20);
      if(s.overlay){rect(0,0,1000,140,'#0a182df5');text(mode==='full'?'DRAG TRIGGER → OUTPUT':'CLICK TRIGGER, THEN OUTPUT',490,20,'#c1e5ee',12);
        for(const sw of w.switches){const dst=w.outputs.find(o=>o.id===s.wires[sw.id]);if(dst){ctx.strokeStyle=colors[sw.color];ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(sw.x,58);ctx.bezierCurveTo(sw.x,85,dst.x,82,dst.x,111);ctx.stroke();}}
        for(const sw of w.switches){circle(sw.x,58,17,s.permissions.includes(sw.color)?colors[sw.color]:'#435264');text(sw.label,sw.x,62,'#0c1c2d',10);if(selected===sw.id){ctx.strokeStyle='white';ctx.lineWidth=2;ctx.strokeRect(sw.x-22,36,44,44);}}
        for(const o of w.outputs){rect(o.x-22,94,44,34,colors[o.color]);text(o.kind==='lamp'?'LIGHT':`G${w.gates.findIndex(g=>g.id===o.id)+1}`,o.x,115,'#152534',10);}
      }
      $('.sh-badges').innerHTML=['amber','cyan','violet'].map(c=>`<span style="color:${colors[c]};opacity:${s.permissions.includes(c)?1:.3}">◆ ${c.toUpperCase()}</span>`).join('');
      $('#sh-mode').textContent=s.overlay?'WIRING · WORLD REMAINS LIVE':(p.interlock?'INTERLOCK · one open gate at a time':'BUILDING');
      $('#sh-inventory').textContent=s.item?'CASE ●':'CASE ○';
      if(!terminal){$('.readout').textContent=message;$('.readout').dataset.status=s.caught?'error':'idle';}
    }
    async function submit(){
      if(busy||terminal)return;
      // Extraction ends this attempt. Retain the exact payload if its response
      // is lost: another extraction or gameplay event would invalidate replay.
      if(!pendingSubmission){
        record('extract');
        pendingSubmission=JSON.stringify({mechanic_id:state.mechanic_id,task_id:state.task_id,challenge_id:state.challenge_id,events,completed:s.item&&!s.caught&&s.x<=84});
        s.move=0;
      }
      busy=true;
      try{
        const response=await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:pendingSubmission});
        if(!response.ok)throw new Error('Submission unavailable');
        const result=await response.json();
        if(result.passed){
          terminal=true;$('#sh-verdict').textContent='HEIST COMPLETE';$('#sh-verdict').className='pass';h.setReadout('PASS · ITEM EXTRACTED','passed');
        }else if(result.state){
          await h.render(result.state);h.setReadout('FAIL · FRESH BUILDING','error');
        }else{
          busy=false;message='Submission unavailable. Retry submission.';draw();
        }
      }catch(e){
        busy=false;message='Connection unavailable. Retry submission.';draw();
      }
    }
    $('#sh-overlay').onclick=()=>act('overlay');$('#sh-extract').onclick=submit;$('#sh-retry').onclick=submit;
    if(mode==='simplified'){
      for(const [id,d] of [['#sh-left',-1],['#sh-right',1]]){const b=$(id);b.onpointerdown=e=>{b.setPointerCapture(e.pointerId);act('move',{direction:d});};b.onpointerup=b.onpointercancel=()=>act('move',{direction:0});}
      $('#sh-hide').onclick=()=>act('hide');$('#sh-use').onclick=()=>act('use');$('#sh-pickup').onclick=()=>act('pickup');
    }
    const keydown=e=>{if(mode!=='full'||e.repeat||e.target.tagName==='INPUT')return;const map={ArrowLeft:-1,ArrowRight:1,a:-1,d:1};if(e.key in map){e.preventDefault();act('move',{direction:map[e.key]});}else if(e.key===' '){e.preventDefault();act('hide');}else if(e.key.toLowerCase()==='e')act('use');else if(e.key.toLowerCase()==='f')act('pickup');};
    const keyup=e=>{if(mode==='full'&&['ArrowLeft','ArrowRight','a','d'].includes(e.key))act('move',{direction:0});};
    window.addEventListener('keydown',keydown);window.addEventListener('keyup',keyup);
    cleanup=()=>{window.removeEventListener('keydown',keydown);window.removeEventListener('keyup',keyup);};
    const point=e=>{const b=canvas.getBoundingClientRect();return{x:(e.clientX-b.x)*1000/b.width,y:(e.clientY-b.y)*400/b.height};};
    canvas.onpointerdown=e=>{if(!s.overlay)return;const q=point(e),sw=w.switches.find(x=>Math.hypot(q.x-x.x,q.y-58)<=22);if(mode==='full'){if(sw){drag=sw.id;selected=sw.id;canvas.setPointerCapture(e.pointerId);draw();}}else if(sw){selected=sw.id;draw();}else{const o=w.outputs.find(x=>Math.abs(q.x-x.x)<=26&&Math.abs(q.y-111)<=22);if(o&&selected){act('wire',{source:selected,target:o.id});selected=null;draw();}}};
    canvas.onpointerup=e=>{if(mode==='full'&&drag){const q=point(e),o=w.outputs.find(x=>Math.abs(q.x-x.x)<=26&&Math.abs(q.y-111)<=22);if(o)act('wire',{source:drag,target:o.id});drag=null;selected=null;draw();}};
    canvas.onpointercancel=()=>{drag=null;selected=null;draw();};
    timer=setInterval(step,w.tick_ms);window.switchlineHeist={state:s,world:w,events};draw();
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics.switchline_heist={rootSelector:'.switchline-heist',render};
})();
