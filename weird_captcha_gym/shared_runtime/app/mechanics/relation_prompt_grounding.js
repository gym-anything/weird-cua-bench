(() => {
  "use strict";

  let model = null;

  function clean(value) {
    return String(value == null ? "" : value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  }

  function record(kind, details = {}) {
    const event = {sequence: model.events.length + 1, kind, ...details};
    model.events.push(event);
    return event;
  }

  function stagePoint(event) {
    const rect = document.querySelector(".rel-stage").getBoundingClientRect();
    return [
      Math.max(0, Math.min(model.state.stage.width, Math.round((event.clientX - rect.left) / rect.width * model.state.stage.width))),
      Math.max(0, Math.min(model.state.stage.height, Math.round((event.clientY - rect.top) / rect.height * model.state.stage.height))),
    ];
  }

  function inside(point, rect) {
    return point[0] >= rect.x && point[0] <= rect.x + rect.width && point[1] >= rect.y && point[1] <= rect.y + rect.height;
  }

  function carouselPoint(item) {
    const carousel = model.state.carousel;
    const angle = Math.PI * 2 * ((item.carousel_phase + model.carouselTick) % carousel.ticks) / carousel.ticks;
    return [
      Math.round(carousel.center[0] + carousel.radius_x * Math.cos(angle)),
      Math.round(carousel.center[1] + carousel.radius_y * Math.sin(angle)),
    ];
  }

  function stateSnapshot() {
    return Object.keys(model.objects).sort().map((id) => {
      const item = model.objects[id];
      return {id, x: item.x, y: item.y, depth: item.depth, placed: item.placed};
    });
  }

  function objectPosition(item) {
    return item.placed ? [item.x, item.y] : carouselPoint(item);
  }

  function projectionPoint(item, view) {
    const table = model.state.worktable_rect;
    if (view === "front") return [
      (item.x - table.x) / table.width * 100,
      (item.y - table.y) / table.height * 100,
    ];
    return [item.depth, (item.y - table.y) / table.height * 100];
  }

  function updateProjections() {
    for (const item of Object.values(model.objects)) {
      for (const view of ["front", "side"]) {
        const marker = document.querySelector(`.rel-live-mark[data-object-id="${CSS.escape(item.id)}"][data-view="${view}"]`);
        if (!marker) continue;
        marker.dataset.placed = item.placed ? "true" : "false";
        if (item.placed) {
          const [x, y] = projectionPoint(item, view);
          marker.style.left = `${x}%`;
          marker.style.top = `${y}%`;
        }
      }
    }
  }

  function applyObjectStyles() {
    for (const item of Object.values(model.objects)) {
      const node = document.querySelector(`.rel-object[data-object-id="${CSS.escape(item.id)}"]`);
      if (!node) continue;
      const point = objectPosition(item);
      node.style.left = `${point[0] / model.state.stage.width * 100}%`;
      node.style.top = `${point[1] / model.state.stage.height * 100}%`;
      node.style.setProperty("--rel-size", `${item.radius * 2 / model.state.stage.width * 100}%`);
      node.style.setProperty("--rel-depth-scale", String(.78 + item.depth * .0045));
      node.style.zIndex = String(10 + item.depth);
      node.dataset.placed = item.placed ? "true" : "false";
      node.classList.toggle("is-selected", model.selectedId === item.id);
    }
    const placed = Object.values(model.objects).filter((item) => item.placed).length;
    const placedNode = document.querySelector(".rel-placed-count");
    if (placedNode) placedNode.textContent = `${placed}/${Object.keys(model.objects).length} ON TABLE`;
    updateProjections();
  }

  function updateDepthConsole() {
    const selected = model.objects[model.selectedId];
    const label = document.querySelector(".rel-depth-selection b");
    const value = document.querySelector(".rel-depth-value");
    const knob = document.querySelector(".rel-depth-knob");
    if (label) label.textContent = selected ? selected.label : "NO OBJECT";
    if (value) value.textContent = selected ? String(selected.depth).padStart(3, "0") : "---";
    if (knob) knob.style.top = `${selected ? 100 - selected.depth : 50}%`;
    document.querySelectorAll(".rel-select").forEach((button) => button.classList.toggle("is-selected", button.dataset.objectId === model.selectedId));
  }

  function selectObject(objectId) {
    if (!model.objects[objectId]?.placed || model.settling || model.settled) return;
    model.selectedId = objectId;
    applyObjectStyles();
    updateDepthConsole();
    model.helpers.setReadout(`${model.objects[objectId].label} SELECTED · ADJUST DEPTH OR POSITION`, "idle");
  }

  function dragStart(event) {
    const node = event.target.closest(".rel-object");
    if (model.interaction === "simplified") { proxyStageClick(event, node); return; }
    if (!node || model.settling || model.settled || model.submitting || model.terminal) return;
    event.preventDefault();
    document.querySelector(".rel-failure-stamp")?.remove();
    const objectId = node.dataset.objectId;
    const item = model.objects[objectId];
    const point = stagePoint(event);
    record("drag_start", {object_id: objectId, source: item.placed ? "table" : "carousel", carousel_tick: model.carouselTick, point, input_source:"direct_drag"});
    model.drag = {objectId, original: {...item}, start: point, moves: 0};
    model.selectedId = objectId;
    document.querySelector(".rel-stage").setPointerCapture(event.pointerId);
    node.classList.add("is-dragging");
    applyObjectStyles();
    updateDepthConsole();
  }

  function dragMove(event) {
    if (!model?.drag || model.interaction !== "full") return;
    event.preventDefault();
    const point = stagePoint(event);
    record("drag_move", {object_id: model.drag.objectId, point, input_source:"direct_drag"});
    model.drag.moves += 1;
    model.dragSamples += 1;
    const item = model.objects[model.drag.objectId];
    item.x = point[0]; item.y = point[1]; item.placed = true;
    applyObjectStyles();
  }

  function dragEnd(event) {
    if (!model?.drag || model.interaction !== "full") return;
    event.preventDefault();
    const point = stagePoint(event);
    const drag = model.drag;
    const item = model.objects[drag.objectId];
    document.querySelector(`.rel-object[data-object-id="${CSS.escape(drag.objectId)}"]`)?.classList.remove("is-dragging");
    if (drag.moves >= 2 && inside(point, model.state.worktable_rect)) {
      record("drag_end", {object_id: drag.objectId, point, input_source:"direct_drag"});
      item.x = point[0]; item.y = point[1]; item.placed = true;
      model.dragCount += 1;
      model.helpers.setReadout(`${item.label} PLACED · DEPTH ${item.depth}`, "idle");
    } else {
      record("drag_cancel", {object_id: drag.objectId, point, input_source:"direct_drag"});
      Object.assign(item, drag.original);
      model.helpers.setReadout("DROP CANCELLED · OBJECT RETURNED", "error");
    }
    model.drag = null;
    applyObjectStyles();
    updateDepthConsole();
    updateControls();
  }

  function proxyStageClick(event, node) {
    if (model.settling || model.settled || model.submitting || model.terminal) return;
    event.preventDefault();
    document.querySelector(".rel-failure-stamp")?.remove();
    const point = stagePoint(event);
    if (node) {
      const objectId = node.dataset.objectId;
      const item = model.objects[objectId];
      record("proxy_select", {object_id:objectId, source:item.placed ? "table" : "carousel", carousel_tick:model.carouselTick, point, input_source:"proxy_click"});
      model.proxySelection = objectId;
      model.selectedId = objectId;
      applyObjectStyles(); updateDepthConsole();
      model.helpers.setReadout(`${item.label} SELECTED · CLICK THE WORKTABLE TO PLACE`, "idle");
      return;
    }
    if (!model.proxySelection || !inside(point, model.state.worktable_rect)) return;
    const item = model.objects[model.proxySelection];
    record("proxy_place", {object_id:item.id, point, input_source:"proxy_click"});
    item.x=point[0]; item.y=point[1]; item.placed=true;
    model.proxyPlaceCount += 1;
    model.proxySelection=null;
    applyObjectStyles(); updateDepthConsole(); updateControls();
    model.helpers.setReadout(`${item.label} PLACED · USE DEPTH BUTTONS`, "idle");
  }

  function depthValue(event) {
    const rect = document.querySelector(".rel-depth-track").getBoundingClientRect();
    return Math.max(0, Math.min(100, Math.round(100 - (event.clientY - rect.top) / rect.height * 100)));
  }

  function depthStart(event) {
    if (model.interaction !== "full") return;
    const item = model.objects[model.selectedId];
    if (!item?.placed || model.settling || model.settled || model.terminal) return;
    event.preventDefault();
    document.querySelector(".rel-failure-stamp")?.remove();
    record("depth_start", {object_id: item.id, value: item.depth, input_source:"depth_rail"});
    model.depthDrag = {objectId: item.id, start: item.depth, moves: 0};
    document.querySelector(".rel-depth-track").setPointerCapture(event.pointerId);
  }

  function depthMove(event) {
    if (!model?.depthDrag || model.interaction !== "full") return;
    event.preventDefault();
    const value = depthValue(event);
    record("depth_move", {object_id: model.depthDrag.objectId, value, input_source:"depth_rail"});
    model.objects[model.depthDrag.objectId].depth = value;
    model.depthDrag.moves += 1;
    model.depthSamples += 1;
    applyObjectStyles();
    updateDepthConsole();
  }

  function depthEnd(event) {
    if (!model?.depthDrag || model.interaction !== "full") return;
    event.preventDefault();
    const item = model.objects[model.depthDrag.objectId];
    if (model.depthDrag.moves < 2) {
      const target = depthValue(event);
      for (const value of [Math.round((item.depth + target) / 2), target]) {
        record("depth_move", {object_id: item.id, value, input_source:"depth_rail"});
        item.depth = value;
        model.depthDrag.moves += 1;
        model.depthSamples += 1;
      }
    }
    record("depth_end", {object_id: item.id, value: item.depth, input_source:"depth_rail"});
    model.depthDistance += Math.abs(item.depth - model.depthDrag.start);
    model.depthDrag = null;
    applyObjectStyles(); updateDepthConsole(); updateControls();
    model.helpers.setReadout(`${item.label} DEPTH LOCKED AT ${item.depth}`, "idle");
  }

  function nudgeDepth(event) {
    if (model.interaction !== "simplified" || model.settling || model.settled || model.terminal) return;
    const item=model.objects[model.selectedId]; const delta=Number(event.currentTarget.dataset.delta);
    if (!item?.placed || ![-10,-1,1,10].includes(delta) || item.depth+delta<0 || item.depth+delta>100) return;
    document.querySelector(".rel-failure-stamp")?.remove();
    item.depth+=delta;
    record("depth_nudge", {object_id:item.id,delta,value:item.depth,input_source:"depth_buttons"});
    model.depthSamples+=1; model.depthDistance+=Math.abs(delta);
    applyObjectStyles(); updateDepthConsole();
    model.helpers.setReadout(`${item.label} DEPTH ${item.depth} · BUTTON CALIBRATION`, "idle");
  }

  function updateControls() {
    const allPlaced = Object.values(model.objects).every((item) => item.placed);
    const settleButton = document.querySelector(".rel-settle");
    if (settleButton) settleButton.disabled = !allPlaced || model.settling || model.settled;
    const status = document.querySelector(".rel-placed-count");
    if (status) status.dataset.ready = allPlaced ? "true" : "false";
  }

  function startSettle() {
    if (model.settling || model.settled || !Object.values(model.objects).every((item) => item.placed)) return;
    document.querySelector(".rel-failure-stamp")?.remove();
    record("settle_start");
    // The same visible eight-tick inspection runs in every time mode.  This
    // registration only tells the shared clock that an accepted action has a
    // finite transition, so a paused evaluator waits for the existing settle
    // timer rather than freezing an accepted inspection halfway through.
    model.settleTransition = model.helpers.beginAction?.("relation_force_settle");
    model.settling = true;
    model.selectedId = null;
    updateDepthConsole(); updateControls();
    document.querySelector(".rel-stage")?.classList.add("is-settling");
    model.helpers.setReadout("SETTLE TEST RUNNING · OBSERVE THE FINAL GRAPH", "pending");
    const startedAt = performance.now();
    let tick = 0;
    model.settleTimer = window.setInterval(() => {
      tick += 1;
      for (const item of Object.values(model.objects)) {
        const vector = model.state.settle_vectors[item.id];
        const factor = model.state.settle_ticks - tick + 1;
        item.x += Math.round(vector.dx * factor / model.state.settle_ticks);
        item.y += Math.round(vector.dy * factor / model.state.settle_ticks);
      }
      applyObjectStyles();
      const elapsed = Math.max(Math.round(performance.now() - startedAt), tick * 70);
      record("settle_tick", {tick, elapsed_ms: elapsed, snapshot: stateSnapshot()});
      model.settleSamples += 1;
      const meter = document.querySelector(".rel-settle-meter i");
      if (meter) meter.style.width = `${tick / model.state.settle_ticks * 100}%`;
      if (tick >= model.state.settle_ticks) {
        window.clearInterval(model.settleTimer);
        model.settleTimer = null;
        model.settling = false;
        model.settled = true;
        record("settle_complete", {elapsed_ms: Math.round(performance.now() - startedAt)});
        model.settleTransition?.settle();
        model.settleTransition = null;
        document.querySelector(".rel-stage")?.classList.remove("is-settling");
        document.querySelector(".rel-stage")?.classList.add("is-settled");
        model.helpers.setReadout("SETTLED · INSPECT THE FINAL RELATION GRAPH", "idle");
        updateControls();
      }
    }, model.state.settle_tick_ms);
  }

  function resetAssembly() {
    if (model.submitting || model.terminal) return;
    document.querySelector(".rel-failure-stamp")?.remove();
    if (model.settleTimer) window.clearInterval(model.settleTimer);
    model.settleTimer = null;
    model.settleTransition?.settle();
    model.settleTransition = null;
    record("reset");
    model.objects = Object.fromEntries(model.state.objects.map((item) => [item.id, {...item, x: null, y: null, depth: item.initial_depth, placed: false}]));
    model.drag = model.depthDrag = model.proxySelection = null;
    model.selectedId = null;
    model.settling = model.settled = false;
    model.dragCount = model.dragSamples = model.depthSamples = model.depthDistance = model.settleSamples = model.proxyPlaceCount = 0;
    model.resetCount += 1;
    document.querySelector(".rel-stage")?.classList.remove("is-settling", "is-settled");
    const meter = document.querySelector(".rel-settle-meter i"); if (meter) meter.style.width = "0";
    applyObjectStyles(); updateDepthConsole(); updateControls();
    model.helpers.setReadout("ASSEMBLY RESET · CAROUSEL RESTORED", "idle");
  }

  async function submit() {
    if (model.submitting || model.terminal) return;
    model.submitting = true;
    model.helpers.setReadout("REPLAYING GEOMETRY AND SETTLE FORCES…", "pending");
    try {
      const response = await fetch("/result", {method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({
        mechanic_id:model.state.mechanic_id,task_id:model.state.task_id,challenge_id:model.state.challenge_id,interaction:model.interaction,events:model.events,final_states:stateSnapshot(),
        drag_count:model.dragCount,drag_samples:model.dragSamples,depth_samples:model.depthSamples,depth_distance:model.depthDistance,
        settle_samples:model.settleSamples,proxy_place_count:model.proxyPlaceCount,reset_count:model.resetCount,completed:model.settled,
      })});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true;
        document.querySelector(".relation-assembly-captcha")?.insertAdjacentHTML("beforeend",'<div class="rel-verdict"><span>DUAL-PROJECTION SCULPTURE CERTIFIED</span><strong>PASS</strong><small>FRONT · SIDE · SETTLE REPLAY VERIFIED</small></div>');
        model.helpers.setReadout("PASS","passed");
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        const shell=document.querySelector(".relation-assembly-captcha"); shell?.setAttribute("data-fresh-failure","true"); shell?.insertAdjacentHTML("afterbegin",'<div class="rel-failure-stamp"><b>FAIL</b><span>PROJECTION MISMATCH · FRESH SEALS ISSUED</span></div>');
        const readout=document.querySelector(".readout"); if(readout){readout.textContent="FAIL · FRESH PROJECTION SEALS ISSUED";readout.dataset.status="error";}
      } else { model.submitting=false; model.helpers.setReadout("FAIL · NO AUTHORITATIVE GRADE","error"); }
    } catch (_error) { model.submitting=false; model.helpers.setReadout("FAIL · GEOMETRY VERIFIER OFFLINE","error"); }
  }

  function objectMarkup(item) {
    return `<div class="rel-object rel-shape-${clean(item.shape)} rel-color-${clean(item.color)}" data-object-id="${clean(item.id)}"><div class="rel-object-art"><i></i><b></b></div><span>${clean(item.label)}</span></div>`;
  }

  function projectionMarkup(state, view) {
    const table = state.worktable_rect;
    const point = (item) => view === "front"
      ? [(item.x - table.x) / table.width * 100, (item.y - table.y) / table.height * 100]
      : [item.depth, (item.y - table.y) / table.height * 100];
    return `<div class="rel-projection" data-view="${view}"><header><b>${view === "front" ? "FRONT / X·Y" : "SIDE / Z·Y"}</b><span>TARGET OUTLINE + LIVE SOLID</span></header><div>${state.projection_targets.map((item) => { const [x,y]=point(item); return `<i class="rel-target-mark rel-mini-${clean(item.shape)}" style="left:${x}%;top:${y}%"></i><i class="rel-live-mark rel-mini-${clean(item.shape)}" data-object-id="${clean(item.id)}" data-view="${view}" data-placed="false"></i>`; }).join("")}</div></div>`;
  }

  async function render(state, helpers) {
    if (model?.carouselTimer) window.clearInterval(model.carouselTimer);
    if (model?.settleTimer) window.clearInterval(model.settleTimer);
    model?.settleTransition?.settle();
    const interaction=state.control_condition?.interaction||"full";
    const objectCount=state.objects.length;
    const depthControls=interaction === "simplified"
      ? `<div class="rel-depth-proxies" aria-label="Depth calibration buttons"><button type="button" data-delta="-10">REAR 10</button><button type="button" data-delta="-1">REAR 1</button><button type="button" data-delta="1">FRONT 1</button><button type="button" data-delta="10">FRONT 10</button></div>`
      : `<div class="rel-depth-rig"><div><span>FRONT / 100</span><div class="rel-depth-track"><i></i><b class="rel-depth-knob"></b></div><span>REAR / 000</span></div><strong class="rel-depth-value">---</strong></div>`;
    const controlCopy=interaction === "simplified"
      ? {title:"Click an object, then click its table destination.",note:"Selected object depth changes through labelled FRONT/REAR buttons. The same two seals and settle inspection apply."}
      : {title:"Make both camera seals coincide.",note:"Outlined marks are target projections; solid marks are your live sculpture. FRONT fixes X/Y. SIDE fixes depth/Y. Anticipate the visible settle drift."};
    document.body.dataset.mechanic="relation-assembly"; document.body.dataset.cheatMode=helpers.isCheatMode()?"true":"false";
    model={state,helpers,interaction,objects:Object.fromEntries(state.objects.map((item)=>[item.id,{...item,x:null,y:null,depth:item.initial_depth,placed:false}])),events:[],carouselTick:0,carouselTimer:null,settleTimer:null,settleTransition:null,drag:null,depthDrag:null,proxySelection:null,selectedId:null,settling:false,settled:false,dragCount:0,dragSamples:0,depthSamples:0,depthDistance:0,settleSamples:0,proxyPlaceCount:0,resetCount:0,submitting:false,terminal:false};
    window.relationAssemblyModel=model;
    helpers.app.innerHTML=`<section class="relation-assembly-captcha" data-challenge-id="${clean(state.challenge_id)}" data-interaction="${clean(interaction)}"><header class="rel-head"><div><span>DUAL-PROJECTION SCULPTURE RIG / ${clean(state.challenge_id)}</span><h1>${clean(state.prompt)}</h1></div><div class="rel-projections">${projectionMarkup(state,"front")}${projectionMarkup(state,"side")}</div></header><main class="rel-main"><section class="rel-stage"><div class="rel-carousel"><span>ROTATING STAGING CAROUSEL</span><i></i></div><div class="rel-table"><span>SCULPTURE WORKTABLE</span><div class="rel-depth-bands"><i>REAR</i><i>MID</i><i>FRONT</i></div></div>${state.objects.map(objectMarkup).join("")}<div class="rel-settle-overlay"><b>FORCE / INSPECTION</b><span>SEALS DESCRIBE THE FINAL SETTLED STATE</span></div></section><aside class="rel-console"><p>DEPTH CALIBRATION${state.control_condition ? ` / ${clean(interaction)}` : ""}</p><h2>${controlCopy.title}</h2><div class="rel-depth-selection"><span>SELECTED OBJECT</span><b>NO OBJECT</b></div>${depthControls}<div class="rel-object-list">${state.objects.map((item)=>`<button type="button" class="rel-select" data-object-id="${clean(item.id)}"><i class="rel-mini-${clean(item.shape)}"></i><span>${clean(item.label)}</span></button>`).join("")}</div><div class="rel-settle-meter"><span>FORCE-SETTLE OBSERVATION</span><b><i></i></b></div><button type="button" class="rel-settle" disabled>RUN FORCE / INSPECTION</button><p class="rel-console-note">${controlCopy.note}</p></aside></main><footer class="rel-foot"><button type="button" class="rel-reset">RESET SCULPTURE</button><div><span class="rel-placed-count" data-ready="false">0/${objectCount} ON TABLE</span><div class="readout" data-status="idle">MOVE EVERY OBJECT FROM THE CAROUSEL</div></div><button type="button" class="rel-submit">${clean(state.submit_label)}</button></footer>${helpers.cheatPanelTemplate()}</section>`;
    const stage=document.querySelector(".rel-stage"); stage.addEventListener("pointerdown",dragStart);stage.addEventListener("pointermove",dragMove);stage.addEventListener("pointerup",dragEnd);stage.addEventListener("pointercancel",dragEnd);
    const depth=document.querySelector(".rel-depth-track"); if(depth){depth.addEventListener("pointerdown",depthStart);depth.addEventListener("pointermove",depthMove);depth.addEventListener("pointerup",depthEnd);depth.addEventListener("pointercancel",depthEnd);}
    document.querySelectorAll(".rel-depth-proxies button").forEach((button)=>button.addEventListener("click",nudgeDepth));
    document.querySelectorAll(".rel-console .rel-select").forEach((button)=>button.addEventListener("click",()=>selectObject(button.dataset.objectId)));
    document.querySelector(".rel-settle").addEventListener("click",startSettle);document.querySelector(".rel-reset").addEventListener("click",resetAssembly);document.querySelector(".rel-submit").addEventListener("click",submit);
    model.carouselTimer=window.setInterval(()=>{model.carouselTick=(model.carouselTick+1)%state.carousel.ticks;applyObjectStyles();},state.carousel.tick_ms);
    applyObjectStyles();updateDepthConsole();updateControls();helpers.installCheatPanel();
  }

  window.WeirdCaptchaMechanics=window.WeirdCaptchaMechanics||{};
  window.WeirdCaptchaMechanics.relation_prompt_grounding={rootSelector:".relation-assembly-captcha",render};
})();
