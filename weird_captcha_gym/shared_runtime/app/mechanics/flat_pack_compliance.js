(() => {
  "use strict";
  let model = null;
  const clean = value => String(value == null ? "" : value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const round = value => Math.round(value * 1000) / 1000;
  const pose = body => [round(body.position.x), round(body.position.y), round(body.angle)];
  const angleError = (a, b) => {
    const turn = Math.PI * 2;
    const delta = ((a - b + Math.PI) % turn + turn) % turn - Math.PI;
    return Math.abs(delta);
  };
  function record(kind, details = {}) { const event = {sequence: model.events.length + 1, kind, ...details}; model.events.push(event); return event; }
  function worldPoint(body, local) { const c = Math.cos(body.angle), s = Math.sin(body.angle); return [body.position.x + local[0] * c - local[1] * s, body.position.y + local[0] * s + local[1] * c]; }
  function constraintOffset(body, local) { const c = Math.cos(body.angle), s = Math.sin(body.angle); return {x: local[0] * c - local[1] * s, y: local[0] * s + local[1] * c}; }
  function canvasPoint(event) { const rect = model.canvas.getBoundingClientRect(); return [Math.max(0, Math.min(model.state.stage.width, (event.clientX - rect.left) / rect.width * model.state.stage.width)), Math.max(0, Math.min(model.state.stage.height, (event.clientY - rect.top) / rect.height * model.state.stage.height))]; }
  function partMap() { return Object.fromEntries(model.state.parts.map(part => [part.id, part])); }
  function bodyMap() { return Object.fromEntries(model.bodies.map(body => [body.label, body])); }
  function bodyAt(point) {
    const direct = Matter.Query.point(model.bodies, {x: point[0], y: point[1]})[0];
    if (direct) return direct;
    const bodies = bodyMap();
    for (const joint of model.state.joints) {
      for (const [partId, socket] of [[joint.a, joint.socket_a], [joint.b, joint.socket_b]]) {
        const body = bodies[partId];
        if (!body) continue;
        const visibleSocket = worldPoint(body, socket);
        if (Math.hypot(point[0] - visibleSocket[0], point[1] - visibleSocket[1]) <= 9) return body;
      }
    }
    return null;
  }
  function setMessage(message, status = "idle") { model.helpers.setReadout(message, status); const note = document.querySelector(".flat-live-note"); if (note) note.textContent = message; }
  function clearFreshFailure() { document.querySelector(".flat-fresh-stamp")?.remove(); document.querySelector(".flat-pack-captcha")?.removeAttribute("data-fresh-failure"); }

  function createBodies() {
    const {Bodies, Body, Composite} = Matter;
    model.bodies.forEach(body => Composite.remove(model.engine.world, body));
    model.constraints.forEach(constraint => Composite.remove(model.engine.world, constraint));
    model.bodies = []; model.constraints = []; model.connected.clear(); model.selected = []; model.jig = null;
    for (const part of model.state.parts) {
      const body = Bodies.fromVertices(part.initial_pose[0], part.initial_pose[1], [part.vertices.map(point => ({x: point[0], y: point[1]}))], {
        label: part.id, friction: 0.5, frictionStatic: 0.75, frictionAir: 0.18, restitution: 0.03, density: 0.002,
      }, true);
      Body.setAngle(body, part.initial_pose[2]);
      Body.setStatic(body, true);
      model.bodies.push(body);
    }
    Composite.add(model.engine.world, model.bodies);
    model.engine.gravity.y = 0;
    updateRack(); draw(false);
  }

  function updateRack() {
    document.querySelectorAll(".flat-part-chip").forEach(button => {
      button.dataset.selected = model.selected.includes(button.dataset.partId) ? "true" : "false";
      button.dataset.connected = [...model.connected].some(id => { const joint = model.state.joints.find(item => item.id === id); return joint && [joint.a, joint.b].includes(button.dataset.partId); }) ? "true" : "false";
    });
    const graph = document.querySelector(".flat-graph-value"); if (graph) graph.textContent = `${model.connected.size}/${model.state.joints.length}`;
    const test = document.querySelector(".flat-load"); if (test) test.disabled = model.loading || model.completed;
  }

  function selectPart(partId) {
    if (model.loading || model.completed) return;
    clearFreshFailure();
    const index = model.selected.indexOf(partId);
    if (index >= 0) model.selected.splice(index, 1);
    else { if (model.selected.length >= 2) model.selected.shift(); model.selected.push(partId); }
    updateRack();
  }

  function rotateSelected(direction, inputSource = "side_rotation_buttons") {
    if (model.loading || model.completed || model.selected.length !== 1) { setMessage("SELECT ONE PART BEFORE APPLYING A 90° ROTATION", "pending"); return; }
    const body = model.bodies.find(item => item.label === model.selected[0]);
    const delta = direction * Math.PI / 2;
    Matter.Body.setAngle(body, body.angle + delta);
    Matter.Body.setAngularVelocity(body, 0);
    record("rotate", {part_id: body.label, delta: round(delta), pose: pose(body), input_source: inputSource});
    setMessage(`KEYED ROTATION APPLIED TO ${body.label.toUpperCase()} · COLLISIONS REMAIN ACTIVE`); draw(false);
  }

  function lockJoint(joint, bodies) {
    const constraint = Matter.Constraint.create({
      label: joint.id, bodyA: bodies[joint.a], pointA: constraintOffset(bodies[joint.a], joint.socket_a),
      bodyB: bodies[joint.b], pointB: constraintOffset(bodies[joint.b], joint.socket_b), length: 0,
      stiffness: 1, damping: 0.34,
    });
    model.constraints.push(constraint); Matter.Composite.add(model.engine.world, constraint); model.connected.add(joint.id);
  }

  function mateSelected() {
    if (model.loading || model.completed || model.selected.length !== 2) { setMessage("SELECT EXACTLY TWO PARTS TO TEST THEIR KEYED SOCKETS", "pending"); return; }
    const [first, second] = model.selected;
    const joint = model.state.joints.find(item => [item.a, item.b].includes(first) && [item.a, item.b].includes(second));
    let accepted = false, distance = 999;
    if (joint && !model.connected.has(joint.id)) {
      const bodies = bodyMap(), parts = partMap();
      const a = worldPoint(bodies[joint.a], joint.socket_a), b = worldPoint(bodies[joint.b], joint.socket_b);
      distance = Math.hypot(a[0] - b[0], a[1] - b[1]);
      accepted = distance <= joint.max_distance && angleError(bodies[joint.a].angle, parts[joint.a].target_pose[2]) <= joint.max_angle_error && angleError(bodies[joint.b].angle, parts[joint.b].target_pose[2]) <= joint.max_angle_error;
      if (accepted) lockJoint(joint, bodies);
    }
    record("joint_attempt", {joint_id: joint ? joint.id : `invalid:${[first, second].sort().join("+")}`, accepted, distance: round(distance), input_source: "side_mate_button"});
    model.selected = [];
    if (accepted) setMessage(`SOCKET ${joint.id.toUpperCase()} LOCKED · LOAD PATH CONNECTED`, "passed");
    else { model.rejected += 1; document.querySelector(".flat-stage")?.classList.add("socket-reject"); setTimeout(() => document.querySelector(".flat-stage")?.classList.remove("socket-reject"), 420); setMessage("KEYS / ORIENTATION DO NOT MATCH · JOINT REJECTED", "error"); }
    updateRack(); draw(false);
  }

  function mateDirect(partId) {
    const bodies = bodyMap(), parts = partMap();
    for (const joint of model.state.joints) {
      if (model.connected.has(joint.id) || ![joint.a, joint.b].includes(partId)) continue;
      const a = worldPoint(bodies[joint.a], joint.socket_a), b = worldPoint(bodies[joint.b], joint.socket_b);
      const distance = Math.hypot(a[0] - b[0], a[1] - b[1]);
      const accepted = distance <= joint.max_distance && angleError(bodies[joint.a].angle, parts[joint.a].target_pose[2]) <= joint.max_angle_error && angleError(bodies[joint.b].angle, parts[joint.b].target_pose[2]) <= joint.max_angle_error;
      if (!accepted) continue;
      lockJoint(joint, bodies);
      record("joint_attempt", {joint_id: joint.id, accepted: true, distance: round(distance), input_source: "automatic_socket"});
      setMessage(`SOCKET ${joint.id.toUpperCase()} LOCKED BY DIRECT CONTACT`, "passed");
    }
    updateRack();
  }

  function rotateDirect(event) {
    event.preventDefault();
    if (!model || model.interaction !== "full" || model.loading || model.completed) return;
    const point = canvasPoint(event), body = bodyAt(point);
    if (!body) return;
    model.selected = [body.label];
    const delta = Math.PI / 2;
    Matter.Body.setAngle(body, body.angle + delta); Matter.Body.setAngularVelocity(body, 0);
    record("rotate", {part_id: body.label, delta: round(delta), pose: pose(body), input_source: "part_right_click"});
    setMessage(`DIRECT ROTATION APPLIED TO ${body.label.toUpperCase()}`); updateRack(); draw(false);
  }

  function resetAssembly() {
    if (model.loading || model.completed) return;
    record("reset"); model.resets += 1; model.failure = false;
    document.querySelector(".flat-failure")?.setAttribute("data-visible", "false");
    createBodies(); setMessage("ASSEMBLY REWOUND · PARTS RESTORED");
  }

  function jointLengths() {
    const bodies = bodyMap(), values = {};
    for (const joint of model.state.joints) {
      const a = worldPoint(bodies[joint.a], joint.socket_a), b = worldPoint(bodies[joint.b], joint.socket_b);
      values[joint.id] = round(Math.hypot(a[0] - b[0], a[1] - b[1]));
    }
    return values;
  }
  function contractStrain(step) {
    const contract = model.state.compliance_model;
    const base = Math.abs(step.force_x) * contract.force_x_scale + Math.abs(step.force_y) * contract.force_y_scale;
    return Object.fromEntries(Object.entries(contract.joint_factors).map(([jointId, factor]) => [jointId, round(base * factor)]));
  }

  function beginLoad() {
    if (model.loading || model.completed) return;
    const bodies = bodyMap(), parts = partMap();
    const posesReady = model.state.parts.every(part => Math.hypot(bodies[part.id].position.x - part.target_pose[0], bodies[part.id].position.y - part.target_pose[1]) <= model.state.requirements.pose_tolerance && angleError(bodies[part.id].angle, part.target_pose[2]) <= model.state.requirements.angle_tolerance);
    const accepted = model.connected.size === model.state.joints.length && posesReady;
    record("load_start", {accepted});
    if (!accepted) {
      model.failure = true; const overlay = document.querySelector(".flat-failure"); if (overlay) overlay.dataset.visible = "true";
      setMessage("COMPLIANCE FAIL · OPEN SOCKET OR MISALIGNED KEY · REWIND AND REPAIR", "error"); return;
    }
    model.loading = true; model.loadTick = 0; model.maxStrain = 0; model.engine.gravity.y = 0.16;
    model.bodies.forEach(body => { body.collisionFilter.group = -1; Matter.Body.setStatic(body, false); });
    const core = bodies.core;
    const anchor = Matter.Constraint.create({label: "bench-anchor", pointA: {x: parts.core.target_pose[0], y: parts.core.target_pose[1]}, bodyB: core, pointB: {x: 0, y: 0}, length: 0, stiffness: 0.92, damping: 0.3});
    model.constraints.push(anchor); Matter.Composite.add(model.engine.world, anchor);
    document.querySelector(".flat-stage")?.classList.add("under-load"); setMessage("COMPLIANCE LOAD LIVE · WATCH EVERY SOCKET", "pending"); updateRack();
    model.loadTimer = setInterval(() => {
      const step = model.state.load_steps[model.loadTick];
      const mast = bodyMap().mast;
      Matter.Body.applyForce(mast, mast.position, {x: step.force_x, y: step.force_y});
      const lengths = jointLengths();
      const sensor = contractStrain(step);
      model.maxStrain = Math.max(model.maxStrain, ...Object.values(sensor));
      const poses = Object.fromEntries(model.bodies.map(body => [body.label, pose(body)]));
      record("load_tick", {step: step.step, force_x: step.force_x, force_y: step.force_y, contract_strain: sensor, constraint_lengths: lengths, poses});
      model.loadTick += 1;
      const meter = document.querySelector(".flat-load-meter i"); if (meter) meter.style.width = `${model.loadTick / model.state.load_steps.length * 100}%`;
      const gauge = document.querySelector(".flat-strain-value"); if (gauge) gauge.textContent = `${round(model.maxStrain).toFixed(1)} / ${model.state.requirements.strain_limit}`;
      if (model.loadTick >= model.state.load_steps.length) {
        clearInterval(model.loadTimer); model.loadTimer = null; model.loading = false;
        model.maxStrain = round(model.maxStrain); record("load_end", {max_strain: model.maxStrain});
        model.completed = model.maxStrain <= model.state.requirements.strain_limit;
        document.querySelector(".flat-stage")?.classList.remove("under-load");
        if (model.completed) { document.querySelector(".flat-complete")?.setAttribute("data-visible", "true"); setMessage("LOAD SURVIVED · KEYED GRAPH STABLE · READY TO CERTIFY", "passed"); }
        else { model.failure = true; document.querySelector(".flat-failure")?.setAttribute("data-visible", "true"); setMessage("COMPLIANCE FAIL · A SOCKET SEPARATED UNDER LOAD", "error"); }
        updateRack();
      }
    }, 72);
  }

  async function submit() {
    if (model.submitting || model.terminal) return; model.submitting = true;
    setMessage("CERTIFYING ASSEMBLY…", "pending");
    const payload = {mechanic_id: model.state.mechanic_id, task_id: model.state.task_id, challenge_id: model.state.challenge_id, events: model.events,
      completed: model.completed, joint_ids: [...model.connected].sort(), load_ticks: model.loadTick, resets: model.resets,
      rejected_attempts: model.rejected, collision_contacts: model.contacts, max_strain: round(model.maxStrain)};
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)}); const outcome = await response.json();
      if (outcome.passed === true) { model.terminal = true; document.querySelector(".flat-pack-captcha")?.insertAdjacentHTML("beforeend", '<div class="flat-verdict"><span>ASSEMBLY CERTIFIED</span><strong>PASS</strong><small>ALL SOCKETS HELD UNDER LOAD</small></div>'); model.helpers.setReadout("PASS", "passed"); }
      else if (outcome.passed === false && outcome.state) { await model.helpers.render(outcome.state); const root = document.querySelector(".flat-pack-captcha"); root?.setAttribute("data-fresh-failure", "true"); root?.insertAdjacentHTML("afterbegin", '<div class="flat-fresh-stamp"><b>FAIL</b><span>UNVERIFIED ASSEMBLY · FRESH KIT ISSUED</span></div>'); setTimeout(clearFreshFailure, 1700); const readout = document.querySelector(".readout"); if (readout) { readout.textContent = "FAIL · FRESH FLAT-PACK KIT ISSUED"; readout.dataset.status = "error"; } }
      else { model.submitting = false; setMessage("FAIL · NO AUTHORITATIVE ASSEMBLY GRADE", "error"); }
    } catch (_error) { model.submitting = false; setMessage("FAIL · COMPLIANCE VERIFIER OFFLINE", "error"); }
  }

  function draw(scheduleNext = true) {
    if (!model) return; const ctx = model.canvas.getContext("2d"), state = model.state;
    ctx.clearRect(0, 0, state.stage.width, state.stage.height);
    ctx.fillStyle = "#0b1110"; ctx.fillRect(0, 0, state.stage.width, state.stage.height);
    ctx.strokeStyle = "rgba(243,214,106,.14)"; ctx.lineWidth = 1;
    for (let x = 0; x <= state.stage.width; x += 30) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, state.stage.height); ctx.stroke(); }
    for (let y = 0; y <= state.stage.height; y += 30) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(state.stage.width, y); ctx.stroke(); }
    ctx.setLineDash([7, 7]); ctx.lineWidth = 2;
    for (const part of state.parts) {
      const target = part.target_pose; ctx.save(); ctx.translate(target[0], target[1]); ctx.rotate(target[2]); ctx.strokeStyle = `${part.color}88`; ctx.fillStyle = `${part.color}12`;
      ctx.beginPath(); part.vertices.forEach((point, index) => index ? ctx.lineTo(point[0], point[1]) : ctx.moveTo(point[0], point[1])); ctx.closePath(); ctx.fill(); ctx.stroke(); ctx.restore();
    }
    ctx.setLineDash([]);
    const specs = partMap();
    for (const body of model.bodies) {
      const spec = specs[body.label]; ctx.save(); ctx.beginPath(); body.vertices.forEach((vertex, index) => index ? ctx.lineTo(vertex.x, vertex.y) : ctx.moveTo(vertex.x, vertex.y)); ctx.closePath(); ctx.fillStyle = spec.color; ctx.shadowColor = spec.color; ctx.shadowBlur = model.selected.includes(body.label) ? 22 : 8; ctx.fill(); ctx.shadowBlur = 0; ctx.lineWidth = 3; ctx.strokeStyle = model.selected.includes(body.label) ? "#fff" : "#101413"; ctx.stroke();
      ctx.fillStyle = "#101413"; ctx.font = "800 15px ui-monospace, monospace"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(spec.label, body.position.x, body.position.y); ctx.restore();
    }
    for (const joint of state.joints) { const bodies = bodyMap(), a = worldPoint(bodies[joint.a], joint.socket_a), b = worldPoint(bodies[joint.b], joint.socket_b); ctx.strokeStyle = model.connected.has(joint.id) ? "#b8ff58" : "#ff775f"; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(a[0], a[1], 6, 0, Math.PI * 2); ctx.stroke(); ctx.beginPath(); ctx.arc(b[0], b[1], 6, 0, Math.PI * 2); ctx.stroke(); if (model.connected.has(joint.id)) { ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); } }
    if (scheduleNext !== false) model.raf = requestAnimationFrame(draw);
  }

  function bindPointer() {
    const canvas = model.canvas;
    const placeDrag = (drag, point, forceSample = false) => {
      const distance = Math.hypot(point[0] - drag.last[0], point[1] - drag.last[1]);
      const steps = Math.max(1, Math.ceil(distance / 100));
      if (!forceSample && distance < 6) return;
      for (let step = 1; step <= steps; step += 1) {
        const ratio = step / steps;
        const sample = [
          drag.last[0] + (point[0] - drag.last[0]) * ratio,
          drag.last[1] + (point[1] - drag.last[1]) * ratio,
        ];
        const left = drag.body.position.x - drag.body.bounds.min.x;
        const right = drag.body.bounds.max.x - drag.body.position.x;
        const top = drag.body.position.y - drag.body.bounds.min.y;
        const bottom = drag.body.bounds.max.y - drag.body.position.y;
        Matter.Body.setPosition(drag.body, {
          x: Math.max(left, Math.min(model.state.stage.width - right, sample[0] + drag.offset[0])),
          y: Math.max(top, Math.min(model.state.stage.height - bottom, sample[1] + drag.offset[1])),
        });
        Matter.Body.setVelocity(drag.body, {x: 0, y: 0});
        Matter.Body.setAngularVelocity(drag.body, 0);
        record("drag_sample", {point: sample.map(round), pose: pose(drag.body), input_source: "canvas_drag"});
      }
      drag.last = point;
      draw(false);
    };
    canvas.addEventListener("pointerdown", event => {
      if (event.button !== 0 || model.drag || model.loading || model.completed) return;
      const point = canvasPoint(event), body = bodyAt(point);
      if (!body) return;
      event.preventDefault(); selectPart(body.label);
      model.drag = {body, pointerId: event.pointerId, last: point, offset: [body.position.x - point[0], body.position.y - point[1]]};
      record("drag_start", {part_id: body.label, point: point.map(round), input_source: "canvas_drag"});
      try { canvas.setPointerCapture(event.pointerId); } catch (_) {}
    });
    const move = event => {
      if (!model.drag || event.pointerId !== model.drag.pointerId) return;
      event.preventDefault(); placeDrag(model.drag, canvasPoint(event));
    };
    const end = (event, cancelled = false) => {
      if (!model.drag || event.pointerId !== model.drag.pointerId) return;
      event.preventDefault(); const drag = model.drag;
      placeDrag(drag, cancelled ? drag.last : canvasPoint(event), true);
      model.drag = null;
      record("drag_end", {part_id: drag.body.label, pose: pose(drag.body), input_source: "canvas_drag", cancelled});
      if (!cancelled && model.interaction === "full") mateDirect(drag.body.label);
      draw(false);
      try { canvas.releasePointerCapture(drag.pointerId); } catch (_) {}
    };
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", event => end(event));
    canvas.addEventListener("pointercancel", event => end(event, true));
    canvas.addEventListener("lostpointercapture", event => end(event, true));
    canvas.addEventListener("contextmenu", rotateDirect);
  }

  async function render(state, helpers) {
    if (model?.raf) cancelAnimationFrame(model.raf); if (model?.engineTimer) clearInterval(model.engineTimer); if (model?.loadTimer) clearInterval(model.loadTimer);
    document.body.dataset.mechanic = "flat-pack-compliance"; document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const interaction = state.control_condition?.interaction || "simplified";
    const interactionControls = interaction === "simplified" ? `<div class="flat-controls"><button type="button" class="flat-rotate-left">↶ 90°</button><button type="button" class="flat-rotate-right">90° ↷</button><button type="button" class="flat-mate">LOCK SELECTED SOCKETS</button></div>` : `<div class="flat-direct-note">RIGHT-CLICK A PART TO ROTATE IT 90°. MATCHING SOCKETS LOCK ON CONTACT.</div>`;
    helpers.app.innerHTML = `<section class="flat-pack-captcha" data-interaction="${clean(interaction)}" data-challenge-id="${clean(state.challenge_id)}"><header class="flat-head"><div><span>COMPLIANCE BAY / KIT ${clean(state.challenge_id)}</span><h1>${clean(state.prompt)}</h1></div><div class="flat-rule"><b>LOAD-BEARING KIT</b><span>Fit the asymmetric parts before testing the assembly.</span></div></header><main class="flat-main"><section class="flat-stage"><canvas class="flat-canvas" width="${state.stage.width}" height="${state.stage.height}"></canvas><div class="flat-stage-label">DRAG PARTS ONTO THE DASHED BLUEPRINT</div><div class="flat-failure" data-visible="false"><b>COMPLIANCE FAIL</b><span>OPEN / MISKEYED SOCKET · REWIND AND REPAIR</span></div><div class="flat-complete" data-visible="false"><b>LOAD SURVIVED</b><span>ALL ${state.joints.length} SOCKETS HELD</span></div></section><aside class="flat-console"><p>KEYED PARTS</p><h2>Fit, orient, connect—then prove it under force.</h2><div class="flat-parts">${state.parts.map(part => `<button type="button" class="flat-part-chip" data-part-id="${clean(part.id)}" data-selected="false" data-connected="false" style="--part:${clean(part.color)}"><i></i><span>${clean(part.label)}</span><b>${clean(part.id)}</b></button>`).join("")}</div>${interactionControls}<div class="flat-audit"><div><span>SOCKETS</span><b class="flat-graph-value">0/${state.joints.length}</b></div><div><span>LOAD</span><b class="flat-strain-value">0.0 / ${state.requirements.strain_limit}</b></div><em class="flat-load-meter"><i></i></em></div><ol>${interaction === "full" ? "<li>Right-click parts until their keyed orientation matches.</li><li>Drag matching sockets together to lock them.</li>" : "<li>Place and rotate each part on its dashed pose.</li><li>Select touching parts and lock their matching sockets.</li>"}<li>Run the load test; rewind freely if anything slips.</li></ol><button type="button" class="flat-reset">REWIND / REPAIR</button></aside></main><footer class="flat-foot"><div><span>ASSEMBLY STATUS</span><div class="readout" data-status="idle">DRAG A PART TO BEGIN</div><small class="flat-live-note">COLLISIONS ACTIVE</small></div><button type="button" class="flat-load">BEGIN COMPLIANCE TEST</button><button type="button" class="flat-submit">${clean(state.submit_label)}</button></footer>${helpers.cheatPanelTemplate()}</section>`;
    const engine = Matter.Engine.create({enableSleeping: false}); engine.gravity.y = 0; engine.positionIterations = 10; engine.velocityIterations = 8; engine.constraintIterations = 8;
    const walls = [Matter.Bodies.rectangle(450, -16, 940, 32, {isStatic: true, label: "wall"}), Matter.Bodies.rectangle(450, 496, 940, 32, {isStatic: true, label: "wall"}), Matter.Bodies.rectangle(-16, 240, 32, 520, {isStatic: true, label: "wall"}), Matter.Bodies.rectangle(916, 240, 32, 520, {isStatic: true, label: "wall"})]; Matter.Composite.add(engine.world, walls);
    model = {state, helpers, interaction, engine, walls, bodies: [], constraints: [], selected: [], connected: new Set(), events: [], drag: null, contacts: 0, rejected: 0, resets: 0, loadTick: 0, maxStrain: 0, loading: false, completed: false, failure: false, submitting: false, terminal: false, loadTimer: null, raf: null, canvas: document.querySelector(".flat-canvas")};
    window.flatPackComplianceModel = model; createBodies();
    Matter.Events.on(engine, "collisionStart", event => { for (const pair of event.pairs) { const ids = [pair.bodyA.label, pair.bodyB.label].filter(id => model.state.parts.some(part => part.id === id)); if (ids.length === 2 && ids[0] !== ids[1]) { const sorted = ids.sort(); record("contact", {pair: sorted, tick: model.loadTick}); model.contacts += 1; document.querySelector(".flat-stage")?.classList.add("contact-flash"); setTimeout(() => document.querySelector(".flat-stage")?.classList.remove("contact-flash"), 110); } } });
    model.engineTimer = setInterval(() => Matter.Engine.update(engine, 1000 / 60), 1000 / 60);
    bindPointer(); if (interaction === "simplified") { document.querySelectorAll(".flat-part-chip").forEach(button => button.addEventListener("click", () => selectPart(button.dataset.partId))); document.querySelector(".flat-rotate-left").addEventListener("click", () => rotateSelected(-1)); document.querySelector(".flat-rotate-right").addEventListener("click", () => rotateSelected(1)); document.querySelector(".flat-mate").addEventListener("click", mateSelected); } document.querySelector(".flat-reset").addEventListener("click", resetAssembly); document.querySelector(".flat-load").addEventListener("click", beginLoad); document.querySelector(".flat-submit").addEventListener("click", submit); helpers.installCheatPanel(); model.raf = requestAnimationFrame(draw);
  }
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {}; window.WeirdCaptchaMechanics.flat_pack_compliance = {rootSelector: ".flat-pack-captcha", render};
})();
