(() => {
  let m;
  const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const rec=id=>m.state.world.bookings.find(r=>r.id===id);
  const mode=()=>m.state.control_condition.interaction;
  const clock=s=>`${String(9+Math.floor(s/2)).padStart(2,'0')}:${s%2?'30':'00'}`;
  function parts(v,end=false){return {day:end&&v>0&&v%16===0?(v-1)/16|0:Math.floor(v/16),slot:end&&v>0&&v%16===0?16:v%16};}
  function date(d){const x=new Date(m.state.world.date+'T12:00:00Z');x.setUTCDate(x.getUTCDate()+d);return x.toISOString().slice(0,10);}
  function stamp(v,end=false){const p=parts(v,end);return `${date(p.day).slice(5)} · ${clock(p.slot)}`;}
  function errors(){const w=m.state.world, out=[];
    w.bookings.forEach((r,i)=>{const [a,b]=m.intervals[r.id];
      if(b-a!==r.duration)out.push(`${r.name}: needs ${r.duration*30} minutes`);
      if(a<r.window[0]||b>r.window[1]||a>=b)out.push(`${r.name}: outside permitted window`);
      if(Math.floor(a/16)!==Math.floor((b-1)/16))out.push(`${r.name}: crosses closing time`);
      w.bookings.slice(i+1).forEach(s=>{const [c,d]=m.intervals[s.id];if(Math.max(a,c)<Math.min(b,d))out.push(`${r.name} + ${s.name}: stage overlap`);});
    });
    w.precedence.forEach(([a,b])=>{if(m.intervals[a][1]>m.intervals[b][0])out.push(`${rec(a).name} must finish before ${rec(b).name}`);});return out;
  }
  function button(label,attrs=''){return `<button ${attrs}>${label}</button>`;}
  function mask(i){return `<svg viewBox="0 0 70 65" aria-hidden="true"><path d="M12 8 Q35 0 58 8 L53 44 Q35 72 17 44Z" fill="var(--cast${i})" stroke="#432c38" stroke-width="2"/><path d="M19 25Q24 18 30 25M40 25Q46 18 51 25" fill="none" stroke="#432c38" stroke-width="3"/><path d="M24 40 Q35 ${i%2?30:55} 46 40" fill="none" stroke="#432c38" stroke-width="3"/></svg>`;}
  function renderDesk(){const w=m.state.world, issues=errors();
    document.querySelector('.cc-main').innerHTML=`<aside class="cc-drawer"><h2>Booking drawer</h2><p>Open a cast record to inspect its contract.</p>${w.bookings.map(r=>button(`${mask(r.color)}<span><b>${esc(r.name)}</b><small>${r.fixed?'◆ FIXED BOOKING':'OPEN RECORD →'}</small></span>`,`class="cc-card" data-record="${r.id}"`)).join('')}</aside><section class="cc-calendar"><div class="cc-cal-title"><div><small>ONE STAGE · REHEARSAL DESK</small><h2>Saved calendar</h2></div>${button('House rules ↗','id="cc-rules"')}</div><p class="cc-key">Each row is a cast booking; bars in the same time column share the same stage.</p>${Array.from({length:w.horizon/16},(_,day)=>`<div class="cc-day"><h3>${date(day)} <small>09:00—17:00</small></h3><div class="cc-axis">${[9,11,13,15,17].map(h=>`<span>${h}:00</span>`).join('')}</div>${w.bookings.map(r=>{const [a,b]=m.intervals[r.id],left=Math.max(a,day*16),right=Math.min(b,(day+1)*16);return `<div class="cc-lane"><span>${esc(r.name)}</span><div class="cc-track">${right>left?button(`${r.fixed?'◆ ':''}${clock(left-day*16)}–${clock(right-day*16)}`,`data-record="${r.id}" class="cc-bar" style="left:${(left-day*16)*6.25}%;width:${(right-left)*6.25}%;background:var(--cast${r.color})"`):''}</div></div>`;}).join('')}</div>`).join('')}<div class="cc-status"><b>${issues.length?`${issues.length} calendar conflicts`:'Calendar clear · ready for curtain call'}</b><div>${issues.slice(0,3).map(esc).join('<br>')}${issues.length>3?`<br>+ ${issues.length-3} more · inspect records and rules`:''}</div></div></section>`;
    document.querySelectorAll('[data-record]').forEach(el=>el.onclick=()=>openRecord(el.dataset.record));
    document.querySelector('#cc-rules').onclick=()=>showRules(0);
  }
  function clearFailure(){m.helpers.setReadout('EDITING CALENDAR','idle');document.querySelector('.cc-banner').textContent='';}
  function openRecord(id){if(m.terminal||m.busy)return;clearFailure();m.selected=id;m.draft=[...m.intervals[id]];m.events.push({type:'open',id});showRecord();}
  function closeRecord(){m.events.push({type:'cancel'});m.selected=null;document.querySelector('.cc-modal').innerHTML='';}
  function showRecord(){const r=rec(m.selected);
    document.querySelector('.cc-modal').innerHTML=`<div class="cc-shade"><article class="cc-dialog"><div class="cc-dialog-head">${mask(r.color)}<div><small>CAST CONTRACT · ${r.fixed?'FIXED':'EDITABLE'}</small><h2>${esc(r.name)}</h2></div></div><p><b>${r.duration*30} minutes</b> on the shared stage. No overnight bookings.</p><p>Permitted: <b>${stamp(r.window[0])}</b> to <b>${stamp(r.window[1],true)}</b></p><p>${m.state.world.precedence.filter(([a,b])=>a===r.id||b===r.id).map(([a,b])=>`${esc(rec(a).name)} → ${esc(rec(b).name)}`).join('<br>')||'No precedence requirement for this cast.'}</p>${[0,1].map(f=>`<div class="cc-field"><b>${f?'End':'Start'}</b>${mode()==='full'?button(stamp(m.draft[f],f===1),`data-picker="${f}" ${r.fixed?'disabled':''}`):`<input aria-label="${f?'End':'Start'} slot" data-field="${f}" type="number" min="0" max="${m.state.world.horizon}" value="${m.draft[f]}" ${r.fixed?'disabled':''}><span>${stamp(m.draft[f],f===1)}</span>`}</div>`).join('')}${mode()==='simplified'?'<small>Direct slots: day 1 starts at 0, day 2 at 16; each slot is 30 minutes from 09:00.</small>':''}<div class="cc-picker"></div><div class="cc-actions">${button('Cancel','id="cc-cancel"')}${button(r.fixed?'Fixed booking':'Save record','id="cc-save" '+(r.fixed?'disabled':''))}</div></article></div>`;
    document.querySelector('#cc-cancel').onclick=closeRecord;
    document.querySelectorAll('[data-picker]').forEach(b=>b.onclick=()=>showPicker(Number(b.dataset.picker)));
    document.querySelectorAll('[data-field]').forEach(input=>input.onchange=()=>{const raw=input.value.trim(),value=Number(raw),field=Number(input.dataset.field);if(raw!==''&&Number.isInteger(value)&&value>=0&&value<=m.state.world.horizon){m.draft[field]=value;m.events.push({type:'set',field,value,input_source:'direct_fields'});showRecord();}else{document.querySelector('.cc-picker').textContent=`Enter a whole slot from 0 to ${m.state.world.horizon}.`;document.querySelector('#cc-save').disabled=true;}});
    document.querySelector('#cc-save').onclick=()=>{if(r.fixed)return;m.events.push({type:'save',before:[...m.intervals[r.id]],after:[...m.draft]});m.intervals[r.id]=[...m.draft];m.selected=null;document.querySelector('.cc-modal').innerHTML='';renderDesk();};
  }
  function showPicker(field){const p=parts(m.draft[field],field===1);
    document.querySelector('.cc-picker').innerHTML=`<h3>${field?'End':'Start'} date & time</h3><div class="cc-dates">${Array.from({length:m.state.world.horizon/16},(_,d)=>button(date(d),`data-day="${d}" class="${p.day===d?'chosen':''}"`)).join('')}</div><div class="cc-times">${Array.from({length:17},(_,s)=>button(clock(s),`data-time="${s}" ${((field===0&&s===16)||(field===1&&s===0))?'disabled':''} class="${p.slot===s?'chosen':''}"`)).join('')}</div>${button('Done','id="cc-picker-done"')}`;
    function pick(part,value){const v=parts(m.draft[field],field===1);v[part==='day'?'day':'slot']=value;m.draft[field]=v.day*16+v.slot;m.events.push({type:'pick',field,part,value,input_source:'datetime_picker'});showPicker(field);}
    document.querySelectorAll('[data-day]').forEach(b=>b.onclick=()=>pick('day',Number(b.dataset.day)));
    document.querySelectorAll('[data-time]').forEach(b=>b.onclick=()=>pick('time',Number(b.dataset.time)));
    document.querySelector('#cc-picker-done').onclick=showRecord;
  }
  function showRules(page){const w=m.state.world;
    document.querySelector('.cc-modal').innerHTML=`<div class="cc-shade"><article class="cc-dialog cc-book"><small>THE LITTLE THEATRE · HOUSE RULES ${page+1}/2</small><h2>${page?'Before the curtain rises':'One stage, many stories'}</h2>${page?`<p>Every arrow means the first cast must finish before the second starts. Touching endpoints are allowed.</p>${w.precedence.map(([a,b])=>`<p class="cc-rule">${esc(rec(a).name)} <b>→</b> ${esc(rec(b).name)}</p>`).join('')}`:'<p>Book the exact duration written inside each cast record. Respect its permitted start/end window.</p><p>The stage holds only one cast at a time, even when the bars occupy different rows. Rehearsals run from 09:00 to 17:00; none may cross closing time.</p><p>◆ Fixed bookings are already valid and must stay unchanged.</p><p>Saving a record updates the calendar. A repair may create another overlap. Inspect the reached calendar before the next edit.</p>'}<div class="cc-actions">${button(page?'← Capacity':'Dependencies →','id="cc-book-next"')}${button('Close booklet','id="cc-book-close"')}</div></article></div>`;
    document.querySelector('#cc-book-next').onclick=()=>showRules(1-page);document.querySelector('#cc-book-close').onclick=()=>{document.querySelector('.cc-modal').innerHTML='';};
  }
  async function submit(){if(m.busy||m.terminal)return;const current=m;current.busy=true;
    try{const response=await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mechanic_id:current.state.mechanic_id,task_id:current.state.task_id,challenge_id:current.state.challenge_id,interaction_mode:mode(),events:current.events,intervals:current.intervals})});const result=await response.json();
      if(result.passed){current.terminal=true;current.helpers.setReadout('PASS','passed');document.querySelector('.cc-banner').innerHTML='<b>CURTAIN UP!</b> Every cast has its moment. ★ ★ ★';document.querySelector('.cc-calendar').classList.add('cc-open');document.querySelector('.cc-status').outerHTML=`<div class="cc-performance"><small>TONIGHT · THE WHOLE COMPANY</small><div>${current.state.world.bookings.map(r=>`<figure>${mask(r.color)}<figcaption>${esc(r.name)}</figcaption></figure>`).join('')}</div><b>✦ &nbsp; CURTAIN CALL &nbsp; ✦</b></div>`;}
      else if(result.state){await render(result.state,current.helpers);m.helpers.setReadout('FAIL','error');document.querySelector('.cc-banner').textContent='CALENDAR RETURNED · A fresh booking case is ready';}
      else{current.busy=false;current.helpers.setReadout('Calendar could not be certified','error');}
    }catch(e){current.busy=false;current.helpers.setReadout('Connection interrupted · try curtain call again','error');}
  }
  async function render(state,helpers){m={state,helpers,events:[],intervals:Object.fromEntries(state.world.bookings.map(r=>[r.id,[...r.initial]])),selected:null,busy:false,terminal:false};document.body.dataset.mechanic='curtain-call-calendar';
    helpers.app.innerHTML=`<section class="curtain-call-calendar"><header class="cc-header"><div class="cc-marquee">✦</div><div><small>THE LITTLE THEATRE · PRODUCTION OFFICE</small><h1>Curtain Call Calendar</h1></div><span>REHEARSAL REPAIR<br><b>${mode().toUpperCase()} · L${state.control_condition.difficulty}</b></span></header><div class="cc-banner"></div><main class="cc-main"></main><footer class="cc-footer"><span>Save the cast. Save the show.</span><div class="readout" data-status="idle">BOOKING DESK OPEN</div>${button('Open the theatre →','id="cc-submit"')}</footer><div class="cc-modal"></div>${helpers.cheatPanelTemplate()}</section>`;renderDesk();document.querySelector('#cc-submit').onclick=submit;helpers.installCheatPanel();}
  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};window.WeirdCaptchaMechanics.curtain_call_calendar={rootSelector:'.curtain-call-calendar',render};
})();
