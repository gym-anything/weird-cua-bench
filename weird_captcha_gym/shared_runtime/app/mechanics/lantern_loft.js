(() => {
  "use strict";

  const SIDE_ORDER = ["n", "e", "s", "w"];
  const OPPOSITE = {n: "s", e: "w", s: "n", w: "e"};
  const DELTA = {n: [0, -1], e: [1, 0], s: [0, 1], w: [-1, 0]};
  let model = null;
  let activeCleanup = null;

  function n(value, fallback = 0) {
    const result = Number(value);
    return Number.isFinite(result) ? result : fallback;
  }
  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function xy(slot) { return [slot % 3, Math.floor(slot / 3)]; }
  function slot(x, y) { return y * 3 + x; }
  function adjacent(a, b) {
    const [ax, ay] = xy(a); const [bx, by] = xy(b);
    const dx = bx - ax; const dy = by - ay;
    for (const [side, delta] of Object.entries(DELTA)) if (dx === delta[0] && dy === delta[1]) return side;
    return null;
  }
  function moduleAt(slotId) { return model?.modules?.[model.board[slotId]] || null; }
  function slotPoint(slotId, height = 0) {
    const [x, y] = xy(slotId);
    return [450 + (x - y) * 108, 145 + (x + y) * 52 - n(height) * 34];
  }
  function polygon(slotId, height = 0) {
    const [cx, cy] = slotPoint(slotId, height);
    return [[cx, cy - 52], [cx + 108, cy], [cx, cy + 52], [cx - 108, cy]];
  }
  function pointIn(point, points) {
    let inside = false;
    for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
      const [xi, yi] = points[i]; const [xj, yj] = points[j];
      if ((yi > point[1]) !== (yj > point[1]) && point[0] < (xj - xi) * (point[1] - yi) / ((yj - yi) || 1e-9) + xi) inside = !inside;
    }
    return inside;
  }
  function hitSlot(x, y) {
    const candidates = [];
    for (let slotId = 0; slotId < 9; slotId += 1) {
      const module = moduleAt(slotId);
      if (module) candidates.push({slot: slotId, height: n(module.height)});
    }
    // Match the front-to-back inverse of drawScene's painter order.
    candidates.sort((a, b) => {
      const [ax,ay] = xy(a.slot), [bx,by] = xy(b.slot);
      return bx+by-ax-ay || b.slot-a.slot;
    });
    for (const candidate of candidates) {
      const top=polygon(candidate.slot,candidate.height);
      if (pointIn([x,y],top)) return candidate.slot;
      const bottom=top.map(([px,py])=>[px,py+22+candidate.height*34]);
      for(let edge=0;edge<4;edge+=1) {
        const next=(edge+1)%4;
        if(pointIn([x,y],[top[edge],top[next],bottom[next],bottom[edge]])) return null;
      }
    }
    return pointIn([x,y],polygon(model.emptySlot,0)) ? model.emptySlot : null;
  }
  function connected(a, b) {
    const side = adjacent(a, b);
    if (!side) return false;
    const first = moduleAt(a); const second = moduleAt(b);
    if (!first || !second) return false;
    if (!first.openings?.[side] || !second.openings?.[OPPOSITE[side]]) return false;
    const difference = Math.abs(n(first.height) - n(second.height));
    if (difference === 0) return true;
    return difference <= n(model.state.world.rules.max_height_delta, 1)
      && (Boolean(first.stairs?.[side]) || Boolean(second.stairs?.[OPPOSITE[side]]));
  }
  function push(record) {
    const event = {seq: model.events.length + 1, t_ms: Math.max(0, Math.round((performance.now() - model.startedAt) * 1000) / 1000), ...record};
    model.events.push(event);
    return event;
  }
  function setStatus(text, kind = "idle") {
    model.helpers.setReadout(text, kind);
    const node = document.querySelector(".lantern-loft .lantern-status");
    if (node) { node.dataset.status = kind; node.textContent = text; }
  }
  function updateProxy() {
    const slideBox = document.querySelector("#lantern-slide-proxy");
    const stepBox = document.querySelector("#lantern-step-proxy");
    if (!slideBox || !stepBox) return;
    slideBox.innerHTML = Array.from({length: 9}, (_, source) => source).filter(source => moduleAt(source)).map((source) => {
      const module = moduleAt(source);
      return `<button type="button" data-slide-module="${model.helpers.text(module.id)}" data-slide-from="${source}" data-slide-to="${model.emptySlot}">Slide ${model.helpers.text(module.label)} (${source+1})</button>`;
    }).join("");
    stepBox.innerHTML = Array.from({length: 9}, (_, target) => `<button type="button" data-step-slot="${target}">Step ${target + 1}</button>`).join("");
    slideBox.querySelectorAll("[data-slide-module]").forEach((button) => button.addEventListener("click", () => {
      performSlide(n(button.dataset.slideFrom), n(button.dataset.slideTo), "proxy_slide");
    }));
    stepBox.querySelectorAll("[data-step-slot]").forEach((button) => button.addEventListener("click", () => {
      performStep(n(button.dataset.stepSlot), "proxy_step");
    }));
  }
  function updateHud() {
    const carrier = document.querySelector("#lantern-carrier-readout");
    const rail = document.querySelector("#lantern-rail-readout");
    const elevation = document.querySelector("#lantern-elevation-readout");
    if (carrier) carrier.textContent = `SURFACE ${model.carrierSlot + 1}`;
    if (rail) rail.textContent = `OPEN ${model.emptySlot + 1}`;
    if (elevation) elevation.textContent = `Z${n(moduleAt(model.carrierSlot)?.height)}`;
    const root = document.querySelector(".lantern-loft");
    if (root) { root.dataset.completed = String(Boolean(model.completed)); root.dataset.interaction = model.interaction; }
  }
  function drawModule(ctx, slotId, module, palette) {
    const height = n(module.height); const top = polygon(slotId, height);
    const [cx, cy] = slotPoint(slotId, height);
    const thickness = 22 + height * 34;
    const bottom = top.map(([x, y]) => [x, y + thickness]);
    const side = (a, b, fill) => { ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.lineTo(bottom[top.indexOf(b)][0], bottom[top.indexOf(b)][1]); ctx.lineTo(bottom[top.indexOf(a)][0], bottom[top.indexOf(a)][1]); ctx.closePath(); ctx.fillStyle = fill; ctx.fill(); };
    side(top[3], top[0], palette.edge); side(top[0], top[1], palette.edge); side(top[1], top[2], "#603b2d"); side(top[2], top[3], "#80513b");
    ctx.beginPath(); top.forEach((point, index) => index ? ctx.lineTo(point[0], point[1]) : ctx.moveTo(point[0], point[1])); ctx.closePath();
    ctx.fillStyle = palette.wood; ctx.fill(); ctx.strokeStyle = "rgba(48,29,38,.62)"; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.save(); ctx.globalAlpha = .28; ctx.strokeStyle = palette.paper; ctx.lineWidth = 1;
    for (let line = -2; line <= 2; line += 1) { ctx.beginPath(); ctx.moveTo(cx - 42, cy + line * 7); ctx.lineTo(cx + 42, cy - line * 7); ctx.stroke(); }
    ctx.restore();
    for (const sideName of SIDE_ORDER) {
      const index = {n: 0, e: 1, s: 2, w: 3}[sideName]; const next = top[(index + 1) % 4]; const start = top[index];
      if (module.openings?.[sideName]) {
        ctx.strokeStyle = module.stairs?.[sideName] ? palette.glow : "rgba(255,244,205,.88)"; ctx.lineWidth = module.stairs?.[sideName] ? 5 : 2;
        ctx.beginPath(); ctx.moveTo(start[0], start[1]); ctx.lineTo(next[0], next[1]); ctx.stroke();
        if (module.stairs?.[sideName]) { ctx.strokeStyle = palette.accent; ctx.lineWidth = 1; for (let step = .2; step < 1; step += .2) { const x = start[0] + (next[0] - start[0]) * step; const y = start[1] + (next[1] - start[1]) * step; ctx.beginPath(); ctx.moveTo(x - 4, y - 2); ctx.lineTo(x + 4, y + 2); ctx.stroke(); } }
      } else { ctx.strokeStyle = palette.ink; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(start[0], start[1]); ctx.lineTo(next[0], next[1]); ctx.stroke(); }
    }
    ctx.fillStyle = "rgba(255,250,224,.82)"; ctx.font = "700 9px ui-monospace, monospace"; ctx.textAlign = "center"; ctx.fillText(`Z${height}`, cx, cy + 3);
    ctx.font = "700 8px ui-monospace, monospace"; ctx.fillStyle = "rgba(47,36,57,.76)"; ctx.fillText(module.label, cx, cy + 16); ctx.textAlign = "start";
    if (slotId === model.exitSlot) {
      ctx.save(); ctx.shadowColor = palette.glow; ctx.shadowBlur = 22; ctx.fillStyle = palette.glow; ctx.beginPath(); ctx.arc(cx, cy - 14, 9, 0, Math.PI * 2); ctx.fill(); ctx.restore();
      ctx.fillStyle = palette.ink; ctx.font = "900 9px ui-monospace, monospace"; ctx.fillText("EXIT", cx + 13, cy - 11);
    }
  }
  function drawScene() {
    const canvas = document.querySelector("#lantern-loft-canvas"); if (!canvas || !model) return;
    const ctx = canvas.getContext("2d"); const palette = model.state.palette || {};
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height); gradient.addColorStop(0, palette.paper || "#fff4dc"); gradient.addColorStop(1, "#e7d6cc"); ctx.fillStyle = gradient; ctx.fillRect(0, 0, canvas.width, canvas.height);
    for (let y = 0; y < 3; y += 1) for (let x = 0; x < 3; x += 1) {
      const id=slot(x,y), p=polygon(id,0), [cx,cy]=slotPoint(id,0);
      ctx.fillStyle="rgba(80,53,62,.08)"; ctx.strokeStyle="rgba(80,53,62,.24)";
      ctx.beginPath(); p.forEach((point,index) => index ? ctx.lineTo(...point) : ctx.moveTo(...point)); ctx.closePath(); ctx.fill(); ctx.stroke();
      if (!moduleAt(id)) { ctx.fillStyle=palette.ink; ctx.font="700 11px ui-monospace, monospace"; ctx.textAlign="center"; ctx.fillText(`EMPTY RAIL ${id+1}`,cx,cy); if(id===model.exitSlot) ctx.fillText("EXIT LANDING",cx,cy+15); ctx.textAlign="start"; }
    }
    const order = Array.from({length: 9}, (_, id) => id).sort((a, b) => { const [ax, ay] = xy(a); const [bx, by] = xy(b); return ax + ay - bx - by; });
    for (const slotId of order) { const module = moduleAt(slotId); if (module) drawModule(ctx, slotId, module, palette); }
    // Render the actual height span at joined stair edges, not just a stripe
    // suggesting a staircase on a same-height surface.
    for (let a=0;a<9;a+=1) for (let b=a+1;b<9;b+=1) {
      if (!connected(a,b)) continue;
      const first=moduleAt(a), second=moduleAt(b);
      if (first.height === second.height) continue;
      const side=SIDE_ORDER.indexOf(adjacent(a,b)), edge=polygon(a,first.height);
      const p=edge[side], q=edge[(side+1)%4], dy=(first.height-second.height)*34;
      const from=[p[0]*.65+q[0]*.35,p[1]*.65+q[1]*.35], to=[p[0]*.35+q[0]*.65,p[1]*.35+q[1]*.65];
      ctx.fillStyle=palette.glow;ctx.strokeStyle=palette.accent;ctx.lineWidth=1;
      ctx.beginPath();ctx.moveTo(...from);ctx.lineTo(...to);ctx.lineTo(to[0],to[1]+dy);ctx.lineTo(from[0],from[1]+dy);ctx.closePath();ctx.fill();ctx.stroke();
      for(let step=1;step<5;step+=1) {ctx.beginPath();ctx.moveTo(from[0],from[1]+dy*step/5);ctx.lineTo(to[0],to[1]+dy*step/5);ctx.stroke();}
    }
    ctx.fillStyle=palette.ink;ctx.font="700 10px ui-monospace, monospace";ctx.textAlign="center";
    for(let id=0;id<9;id+=1) {const m=moduleAt(id);if(m){const [cx,cy]=slotPoint(id,m.height);ctx.fillText(`SURFACE ${id+1}`,cx,cy+32);}}
    ctx.textAlign="start";
    const carrierModule = moduleAt(model.carrierSlot); const [cx, cy] = slotPoint(model.carrierSlot, carrierModule?.height || 0);
    ctx.save(); ctx.shadowColor = palette.glow || "#ffd56b"; ctx.shadowBlur = 18; ctx.fillStyle = palette.glow || "#ffd56b"; ctx.beginPath(); ctx.arc(cx, cy - 20, 9, 0, Math.PI * 2); ctx.fill(); ctx.restore();
    ctx.fillStyle = palette.ink || "#2f2439"; ctx.beginPath(); ctx.arc(cx, cy - 18, 4, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "rgba(47,36,57,.68)"; ctx.font = "800 11px ui-monospace, monospace"; ctx.fillText(model.completed ? "LOFT EXIT CONTACT" : "SLIDE · JOIN · WALK", 18, canvas.height - 18);
    if (model.dragging) { ctx.strokeStyle = palette.accent || "#5f73bd"; ctx.setLineDash([5, 5]); ctx.lineWidth = 2; const p = slotPoint(model.dragging.source, moduleAt(model.dragging.source)?.height || 0); ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(model.dragging.x, model.dragging.y); ctx.stroke(); ctx.setLineDash([]); }
  }
  function updateAll() { updateHud(); updateProxy(); drawScene(); }
  function performSlide(source, target, inputSource) {
    if (!model || model.completed) return false;
    if (!moduleAt(source) || source === model.carrierSlot || target !== model.emptySlot || !adjacent(source, target)) { setStatus("BLOCKED · SLIDE AN UNOCCUPIED ADJACENT MODULE INTO THE EMPTY RAIL", "error"); return false; }
    const moduleId = model.board[source]; model.board[target] = moduleId; model.board[source] = null; model.emptySlot = source;
    push({kind: "slide", module_id: moduleId, from_slot: source, to_slot: target, input_source: inputSource}); setStatus("SLIDE REGISTERED · CHECK THE NEW ELEVATION LINKS"); updateAll(); return true;
  }
  function performStep(target, inputSource) {
    if (!model || model.completed) return false;
    if (!connected(model.carrierSlot, target)) { setStatus("BLOCKED · MATCH BOTH OPENINGS AND THE ELEVATION / STAIR CONNECTION", "error"); return false; }
    const from = model.carrierSlot; model.carrierSlot = target; push({kind: "step", from_slot: from, to_slot: target, input_source: inputSource});
    if (model.carrierSlot === model.exitSlot) { model.completed = true; push({kind: "finish", input_source: "physical_contact"}); submitResult(true); setStatus("EXIT CONTACT · CERTIFYING", "passed"); }
    else setStatus("CARRIER MOVED · REASSESS THE NEXT SURFACE");
    updateAll(); return true;
  }
  async function submitResult(completed) {
    if (!model || model.submitting) return; model.submitting = true;
    const submitted = model;
    const payload = {mechanic_id: submitted.state.mechanic_id, task_id: submitted.state.task_id, challenge_id: submitted.state.challenge_id, interaction: submitted.interaction, completed: Boolean(completed), events: clone(submitted.events), final: {carrier_slot: submitted.carrierSlot, empty_slot: submitted.emptySlot}};
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)}); const outcome = await response.json();
      if (outcome.passed === true) { setStatus("PASS · LANTERN AT THE LOFT EXIT", "passed"); submitted.helpers.setReadout("PASS · LANTERN AT THE LOFT EXIT", "passed"); document.querySelector(".lantern-loft")?.classList.add("is-passed"); const verdict = document.querySelector(".lantern-verdict"); if (verdict) verdict.innerHTML = "<b>PASS</b><span>THE LOFT CONNECTS</span>"; }
      else if (outcome.passed === false) { if (outcome.state) await render(outcome.state, submitted.helpers); }
    } catch (_error) { submitted.submitting = false; setStatus("LINK LOST · TRY AGAIN", "error"); }
  }
  function render(state, helpers) {
    if (activeCleanup) activeCleanup();
    document.body.dataset.mechanic = "lantern-loft"; document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const interaction = state.control_condition?.interaction || "full"; const world = state.world;
    model = {state, helpers, interaction, board: clone(world.board), emptySlot: n(world.empty_slot), carrierSlot: n(world.carrier_slot), exitSlot: n(world.exit_slot), modules: Object.fromEntries((world.modules || []).map((item) => [item.id, item])), events: [], startedAt: performance.now(), completed: false, submitting: false, dragging: null};
    model.slotPoint = (slotId) => slotPoint(n(slotId), n(model.modules[model.board[n(slotId)]]?.height));
    window.lanternLoftModel = model;
    const simplified = interaction === "simplified";
    helpers.app.innerHTML = `<section class="lantern-loft" data-interaction="${helpers.text(interaction)}" data-completed="false" tabindex="0"><div class="lantern-verdict" aria-live="assertive"></div><header class="lantern-head"><div><span>LANtern LOFT / ELEVATION IS NOT A SHADOW</span><h1>${helpers.text(state.prompt)}</h1></div><div class="lantern-mark">3D<br><b>ROUTE</b></div></header><section class="lantern-workbench"><div class="lantern-view-wrap"><canvas id="lantern-loft-canvas" width="900" height="560" aria-label="Isometric loft modules with a lantern carrier"></canvas><div class="lantern-caption"><span>ISOMETRIC LOFT PLAN</span><b>SCREEN OVERLAP IS NOT A PASSAGE</b></div></div><aside class="lantern-console"><div class="lantern-readouts"><span>CARRIER</span><b id="lantern-carrier-readout">SURFACE --</b><span>OPEN RAIL</span><b id="lantern-rail-readout">OPEN --</b><span>HEIGHT</span><b id="lantern-elevation-readout">Z--</b></div><div class="lantern-rule"><b>BUILD A WALKABLE LOFT</b><span>Slide a module into the empty rail. Then move the lantern only across matching openings; a stair is required when elevations differ.</span></div>${simplified ? `<div class="lantern-proxy"><span>SLIDE PROXY</span><div id="lantern-slide-proxy"></div><span>STEP PROXY</span><div id="lantern-step-proxy"></div></div>` : `<div class="lantern-full-hint"><b>DIRECT MANIPULATION</b><span>Drag a module into the empty rail position. Click a joined surface to move the lantern.</span></div>`}<button type="button" class="lantern-abandon" id="lantern-abandon">ABANDON LOFT</button></aside></section><footer class="lantern-foot"><div class="lantern-status" data-status="idle">SLIDE · JOIN · WALK · REPEAT UNTIL THE EXIT LANTERN</div><span>VISIBLE Z-LEVELS ARE PART OF THE GEOMETRY</span></footer>${helpers.cheatPanelTemplate()}</section>`;
    const canvas = document.querySelector("#lantern-loft-canvas"); let pointer = null;
    const coords = (event) => { const box = canvas.getBoundingClientRect(); return [(event.clientX - box.left) / box.width * canvas.width, (event.clientY - box.top) / box.height * canvas.height]; };
    const down = (event) => { if (model.interaction !== "full" || model.completed || event.button !== 0) return; const [x, y] = coords(event); const hit = hitSlot(x, y); if (hit === null) return; pointer = {hit, startX: x, startY: y, x, y, candidate: Boolean(moduleAt(hit) && hit !== model.carrierSlot && adjacent(hit, model.emptySlot))}; canvas.setPointerCapture?.(event.pointerId); };
    const move = (event) => { if (!pointer) return; [pointer.x, pointer.y] = coords(event); if (pointer.candidate && Math.hypot(pointer.x - pointer.startX, pointer.y - pointer.startY) > 5) { pointer.source = pointer.hit; pointer.moduleId = model.board[pointer.hit]; model.dragging = pointer; drawScene(); } };
    const up = (event) => { if (!pointer) return; const current = pointer; pointer = null; model.dragging = null; const [x, y] = coords(event); const hit = hitSlot(x, y); if (current.source !== undefined) { if (hit !== null) performSlide(current.source, hit, "drag"); } else if (hit !== null) performStep(hit, "surface_click"); drawScene(); };
    canvas.addEventListener("pointerdown", down); canvas.addEventListener("pointermove", move); canvas.addEventListener("pointerup", up); canvas.addEventListener("pointercancel", up);
    const abandon = () => { if (!model.completed) { push({kind: "abandon", input_source: "route_button"}); model.completed = true; submitResult(false); } }; document.querySelector("#lantern-abandon")?.addEventListener("click", abandon);
    activeCleanup = () => { canvas.removeEventListener("pointerdown", down); canvas.removeEventListener("pointermove", move); canvas.removeEventListener("pointerup", up); canvas.removeEventListener("pointercancel", up); document.querySelector("#lantern-abandon")?.removeEventListener("click", abandon); };
    updateAll(); helpers.installCheatPanel(); document.querySelector(".lantern-loft")?.focus();
  }
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.lantern_loft = {rootSelector: ".lantern-loft", render};
})();
