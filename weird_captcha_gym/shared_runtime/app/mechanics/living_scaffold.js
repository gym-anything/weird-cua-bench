(() => {
  'use strict';
  const delta={N:[0,-1],E:[1,0],S:[0,1],W:[-1,0]};
  const keys={ArrowUp:'N',ArrowRight:'E',ArrowDown:'S',ArrowLeft:'W',w:'N',d:'E',s:'S',a:'W'};
  const colors=['#e78458','#61b6a7','#b39cdb'];
  const copy=x=>JSON.parse(JSON.stringify(x));
  const key=p=>p.join(',');
  let cleanup=()=>{};
  function initial(b){return {bodies:copy(b.creatures),food:copy(b.food),dead:false};}
  function settle(b,s){
    const rocks=new Set(b.rocks.map(key));
    for(let tick=0;tick<b.height+2;tick++){
      if(!s.food.length) s.bodies=s.bodies.map((body,i)=>body.length && key(body[0])===key(b.exits[i]) ? []:body);
      const supported=new Set();
      let changed=true;
      while(changed){
        changed=false;
        const solid=new Set([...rocks,...[...supported].flatMap(i=>s.bodies[i].map(key))]);
        s.bodies.forEach((body,i)=>{
          const own=new Set(body.map(key));
          if(body.length && !supported.has(i) && body.some(([x,y])=>solid.has(key([x,y+1]))&&!own.has(key([x,y+1])))){
            supported.add(i);changed=true;
          }
        });
      }
      const falling=s.bodies.map((body,i)=>body.length&&!supported.has(i)?i:-1).filter(i=>i>=0);
      if(!falling.length) return s;
      falling.forEach(i=>{s.bodies[i]=s.bodies[i].map(([x,y])=>[x,y+1]);});
      if(s.bodies.some(body=>body.some(([,y])=>y>=b.height))){s.dead=true;return s;}
    }
    throw new Error('Gravity did not settle');
  }
  function step(b,state,i,d){
    if(state.dead||!state.bodies[i]?.length)return state;
    const body=state.bodies[i], [dx,dy]=delta[d], target=[body[0][0]+dx,body[0][1]+dy];
    const growing=state.food.some(p=>key(p)===key(target));
    const occupied=new Set(b.rocks.map(key));
    state.bodies.forEach((s,j)=>(i!==j||growing?s:s.slice(0,-1)).forEach(p=>occupied.add(key(p))));
    if(occupied.has(key(target))||target[0]<0||target[0]>=b.width||target[1]<0||target[1]>=b.height)return state;
    const next=copy(state);
    next.bodies[i]=[target,...(growing?body:body.slice(0,-1))];
    next.food=next.food.filter(p=>key(p)!==key(target));
    return settle(b,next);
  }
  const solved=s=>!s.dead&&!s.food.length&&s.bodies.every(b=>!b.length);
  async function render(publicState,helpers){
    cleanup();
    document.body.dataset.mechanic='living-scaffold';
    const b=publicState.board, mode=publicState.control_condition?.interaction||'full';
    let state=initial(b), selected=0, history=[],actions=[],busy=false,passed=false,retryState=null;
    helpers.app.innerHTML=`<section class="living-scaffold" tabindex="0">
      <header class="ls-head"><div><span>THE SUSPENDED GARDEN / FIELD STUDY 04</span><h1>Living Scaffold</h1></div><div class="ls-seal" aria-hidden="true"></div></header>
      <div class="ls-work"><div class="ls-world"><svg class="ls-board" viewBox="0 0 ${b.width*64} ${b.height*64}" role="img" aria-label="Garden creatures on suspended ledges"></svg><div class="ls-verdict" aria-live="assertive"></div></div>
      <aside><div class="ls-kicker">GARDEN CREW</div><div class="ls-roster"></div>
      ${mode==='simplified'?'<div class="ls-pad"><button data-dir="N" aria-label="Move up">↑</button><button data-dir="W" aria-label="Move left">←</button><button data-dir="S" aria-label="Move down">↓</button><button data-dir="E" aria-label="Move right">→</button></div>':'<div class="ls-keys" aria-hidden="true">↑<br>← ↓ →</div>'}
      <div class="ls-recovery"><button class="ls-undo">↶ Undo</button><button class="ls-reset">Restart</button></div><button class="ls-submit">Check garden</button></aside></div>
      <footer><div class="readout" aria-live="assertive" data-status="idle"></div></footer></section>`;
    const root=helpers.app.querySelector('.living-scaffold'),svg=root.querySelector('svg'),verdict=root.querySelector('.ls-verdict');
    function draw(){
      let art=`<defs><linearGradient id="ls-sky" x2="0" y2="1"><stop stop-color="#e8f0dc"/><stop offset="1" stop-color="#c5ddd0"/></linearGradient></defs><rect width="100%" height="100%" rx="20" fill="url(#ls-sky)"/>`;
      for(let y=0;y<b.height;y++)for(let x=0;x<b.width;x++) art+=`<circle cx="${x*64+32}" cy="${y*64+32}" r="1.5" fill="#436553" opacity=".15"/>`;
      art+=`<path d="M0 ${b.height*64-22} Q160 ${b.height*64-45} 320 ${b.height*64-18} T640 ${b.height*64-24} V${b.height*64} H0Z" fill="#618b82" opacity=".35"/>`;
      b.rocks.forEach(([x,y])=>{art+=`<g><rect x="${x*64}" y="${y*64}" width="64" height="64" rx="3" fill="#526b59"/><path d="M${x*64} ${y*64+5}h64" stroke="#8ba76e" stroke-width="10"/><path d="M${x*64+12} ${y*64+24}l18 12m10 8l12-18" fill="none" stroke="#82927c" stroke-width="3"/></g>`;});
      b.exits.forEach(([x,y],i)=>{
        const cx=x*64+32,cy=y*64+32;
        art+=`<g class="ls-flower">`;
        for(let a=0;a<6;a++){const t=a*Math.PI/3;art+=`<ellipse cx="${cx+Math.cos(t)*17}" cy="${cy+Math.sin(t)*17}" rx="12" ry="12" fill="${colors[i]}" stroke="#f9f9e8" stroke-width="2"/>`;}
        art+=`<circle cx="${cx}" cy="${cy}" r="17" fill="#fff8c7"/></g>`;
      });
      state.food.forEach(([x,y])=>{art+=`<g class="ls-fruit"><path d="M${x*64+32} ${y*64+22}q-18-10-20 10q0 22 20 19q20 3 20-19q-2-20-20-10" fill="#f1c74e" stroke="#ac8033" stroke-width="2"/><path d="M${x*64+32} ${y*64+24}q-3-17 11-15" fill="none" stroke="#547753" stroke-width="5"/></g>`;});
      state.bodies.forEach((body,i)=>{
        if(!body.length)return;
        const points=body.map(([x,y])=>`${x*64+32},${y*64+32}`).join(' ');
        art+=`<g class="ls-creature" data-creature="${i}" style="cursor:pointer"><polyline points="${points}" fill="none" stroke="${i===selected?'#fdf8d4':'#3e6153'}" stroke-width="64" stroke-linecap="round" stroke-linejoin="round"/><polyline points="${points}" fill="none" stroke="${colors[i]}" stroke-width="56" stroke-linecap="round" stroke-linejoin="round"/>`;
        body.forEach(([x,y],j)=>{art+=`<circle class="ls-segment" data-x="${x}" data-y="${y}" data-segment="${j}" cx="${x*64+32}" cy="${y*64+32}" r="${j?17:22}" fill="${colors[i]}" stroke="#ffffff" stroke-opacity=".15" stroke-width="2"/>`;});
        const [x,y]=body[0],cx=x*64+32,cy=y*64+32;
        art+=`<circle cx="${cx-8}" cy="${cy-6}" r="6" fill="#fffbe9"/><circle cx="${cx+8}" cy="${cy-6}" r="6" fill="#fffbe9"/><circle cx="${cx-7}" cy="${cy-5}" r="2.6" fill="#293e36"/><circle cx="${cx+9}" cy="${cy-5}" r="2.6" fill="#293e36"/></g>`;
      });
      svg.innerHTML=art;
      root.querySelector('.ls-roster').innerHTML=state.bodies.map((body,i)=>`<${mode==='simplified'?'button':'div'} class="ls-card ${i===selected?'selected':''}" data-select="${i}" style="--creature:${colors[i]}" aria-label="Select creature"><span class="ls-swatch" aria-hidden="true"></span></${mode==='simplified'?'button':'div'}>`).join('');
      root.querySelectorAll('button[data-select]').forEach(el=>{el.onclick=()=>select(Number(el.dataset.select));});
      svg.querySelectorAll('[data-creature]').forEach(el=>{el.onclick=()=>{if(mode==='full')select(Number(el.dataset.creature));};});
      if(state.dead){verdict.innerHTML='<b>FAIL</b>';verdict.dataset.kind='fail';helpers.setReadout('FAIL','error');}
      else if(!passed){verdict.innerHTML='';verdict.dataset.kind='idle';helpers.setReadout('','idle');}
    }
    function select(i){if(busy||passed||retryState||!state.bodies[i].length)return;selected=i;draw();}
    function move(d){
      if(busy||passed||retryState)return;
      const next=step(b,state,selected,d);
      actions.push({type:'move',creature:selected,direction:d,input_source:mode==='full'?'keyboard':'buttons'});
      if(JSON.stringify(next)!==JSON.stringify(state)){history.push(copy(state));state=next;}
      draw();
    }
    root.querySelectorAll('[data-dir]').forEach(el=>el.onclick=()=>move(el.dataset.dir));
    root.querySelector('.ls-undo').onclick=()=>{if(busy||passed||retryState)return;actions.push({type:'undo'});if(history.length)state=history.pop();draw();};
    root.querySelector('.ls-reset').onclick=()=>{if(busy||passed)return;if(retryState){render(retryState,helpers);return;}actions.push({type:'reset'});state=initial(b);history=[];draw();};
    root.querySelector('.ls-submit').onclick=async()=>{
      if(busy||passed||retryState)return;busy=true;
      try{
        const response=await fetch('/result',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({mechanic_id:publicState.mechanic_id,task_id:publicState.task_id,challenge_id:publicState.challenge_id,control_condition:publicState.control_condition||null,actions})});
        if(!response.ok)throw new Error('Result unavailable');
        const result=await response.json();
        if(typeof result.passed!=='boolean')throw new Error('Result unavailable');
        if(result.passed){passed=true;verdict.innerHTML='<b>PASS</b>';verdict.dataset.kind='pass';helpers.setReadout('PASS','passed');}
        else {
          // Keep the rejected attempt visible until retry is explicitly requested.
          retryState=result.state||publicState;
          verdict.innerHTML='<b>FAIL</b>';verdict.dataset.kind='fail';
          helpers.setReadout('FAIL','error');
          root.querySelectorAll('button').forEach(el=>{el.disabled=!el.matches('.ls-reset');});
          root.querySelector('.ls-reset').textContent='Try again';
        }
      }catch(e){helpers.setReadout('Check unavailable','error');}
      finally{busy=false;}
    };
    const onKey=e=>{if(mode!=='full'||e.repeat||!keys[e.key])return;e.preventDefault();move(keys[e.key]);};
    window.addEventListener('keydown',onKey);cleanup=()=>window.removeEventListener('keydown',onKey);
    draw();root.focus();
  }
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics.living_scaffold={rootSelector:'.living-scaffold',render};
})();
