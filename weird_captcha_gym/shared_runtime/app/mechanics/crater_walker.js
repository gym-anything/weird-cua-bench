(() => {
  "use strict";

  const MECHANIC = "crater_walker";
  const LEGS = ["front_left", "front_right", "rear_left", "rear_right"];
  const ACTUATORS = ["yaw", "lift", "extend"];
  const BASE_X = {front_left: 0.84, front_right: 0.84, rear_left: -0.84, rear_right: -0.84};
  const BASE_Y = {front_left: -0.64, front_right: 0.64, rear_left: -0.64, rear_right: 0.64};
  const COLORS = {front_left: "#ffcf72", front_right: "#71e4d5", rear_left: "#d69cff", rear_right: "#ff8e9a"};
  const LIFT_SCALE = 0.45;
  const EXTEND_SCALE = 0.30;
  const YAW_SCALE = 0.18;
  const RAISED = 3;
  let model = null;
  let cleanup = null;

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function esc(value) { return String(value == null ? "" : value).replace(/[&<>\"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }
  function clamp(value, lo, hi) { return Math.max(lo, Math.min(hi, value)); }
  function pointKey(p) { return `${Number(p.x).toFixed(4)},${Number(p.y).toFixed(4)},${Number(p.z).toFixed(4)}`; }

  function footTarget(pose, leg, controls) {
    return {
      x: Number((Number(pose.x) + BASE_X[leg] + Number(controls.extend) * EXTEND_SCALE).toFixed(4)),
      y: Number((Number(pose.y) + BASE_Y[leg] + Number(controls.yaw) * YAW_SCALE).toFixed(4)),
      z: Number((Number(pose.z) - 1.28 + Number(controls.lift) * LIFT_SCALE).toFixed(4)),
    };
  }

  function distance(a, b) {
    return Math.sqrt(["x", "y", "z"].reduce((sum, key) => sum + (Number(a[key]) - Number(b[key])) ** 2, 0));
  }

  function insideXY(quad, point) {
    const vertices = quad.vertices || [];
    if (vertices.length !== 4) return false;
    const crosses = vertices.map((vertex, index) => {
      const following = vertices[(index + 1) % vertices.length];
      return (Number(following.x) - Number(vertex.x)) * (Number(point.y) - Number(vertex.y))
        - (Number(following.y) - Number(vertex.y)) * (Number(point.x) - Number(vertex.x));
    });
    return Math.min(...crosses) >= -1e-7 || Math.max(...crosses) <= 1e-7;
  }

  function quadZ(quad) {
    return (quad.vertices || []).reduce((sum, vertex) => sum + Number(vertex.z), 0) / (quad.vertices || []).length;
  }

  function terrainSurfaceZ(point) {
    const surfaces = (model.world.terrain_quads || []).filter((quad) => insideXY(quad, point));
    return surfaces.length ? Math.max(...surfaces.map(quadZ)) : null;
  }

  function padSurfaceZ(padId, point) {
    const surface = (model.world.terrain_quads || []).find((quad) => (
      String(quad.kind || "") === "support_surface" && String(quad.pad_id) === String(padId)
    ));
    return surface && insideXY(surface, point) ? quadZ(surface) : null;
  }

  function bodyClearOfTerrain(body) {
    const surface = terrainSurfaceZ(body);
    return surface !== null && Number(body.z) >= surface + .20;
  }

  function contactsFor() {
    const contacts = {};
    const occupied = new Set();
    for (const leg of LEGS) {
      const controls = model.actuators[leg];
      if (Number(controls.lift) >= RAISED) { contacts[leg] = null; continue; }
      const target = footTarget(model.body, leg, controls);
      const candidates = model.world.pads.filter((pad) => (
        !occupied.has(String(pad.id))
        && distance(target, pad) <= Number(model.world.contact_tolerance)
        && padSurfaceZ(String(pad.id), target) !== null
      ));
      candidates.sort((a, b) => distance(target, a) - distance(target, b) || String(a.id).localeCompare(String(b.id)));
      contacts[leg] = candidates.length ? String(candidates[0].id) : null;
      if (contacts[leg]) occupied.add(contacts[leg]);
    }
    return contacts;
  }

  function posture(contacts) {
    const byId = Object.fromEntries(model.world.pads.map((pad) => [String(pad.id), pad]));
    const points = Object.values(contacts).filter(Boolean).map((id) => byId[id]).filter(Boolean);
    if (points.length < 2) return {roll: 1, pitch: 1};
    const mean = points.reduce((sum, point) => sum + Number(point.z), 0) / points.length;
    const group = (predicate) => LEGS.filter(predicate).map((leg) => byId[contacts[leg]]).filter(Boolean);
    const average = (items) => items.length ? items.reduce((sum, p) => sum + Number(p.z), 0) / items.length : mean;
    const left = average(group((leg) => leg.endsWith("left")));
    const right = average(group((leg) => leg.endsWith("right")));
    const front = average(group((leg) => leg.startsWith("front")));
    const rear = average(group((leg) => leg.startsWith("rear")));
    return {roll: Number(((left - right) * 0.75).toFixed(4)), pitch: Number(((front - rear) * 0.75).toFixed(4))};
  }

  function project(point) {
    const yaw = Number(model.camera.yaw);
    const dx = Number(point.x) - Number(model.world.escape_x) / 2;
    const dy = Number(point.y);
    const dz = Number(point.z);
    const horizontal = dx * Math.cos(yaw) - dy * Math.sin(yaw);
    const depth = dx * Math.sin(yaw) + dy * Math.cos(yaw);
    return {x: 450 + horizontal * 66, y: 370 + depth * 19 - dz * 70 - Number(model.camera.pitch) * 40, depth};
  }

  function polygon(ctx, points, fill, stroke = null) {
    ctx.beginPath();
    points.forEach((p, index) => index ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y));
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke(); }
  }

  function drawPad(ctx, pad, contactIds) {
    const radius = Number(pad.radius || 0.3);
    const top = [
      {x: pad.x - radius, y: pad.y, z: pad.z},
      {x: pad.x, y: pad.y - radius * .72, z: pad.z},
      {x: pad.x + radius, y: pad.y, z: pad.z},
      {x: pad.x, y: pad.y + radius * .72, z: pad.z},
    ].map(project);
    const low = top.map((p) => ({x: p.x, y: p.y + 7, depth: p.depth}));
    polygon(ctx, [top[0], top[1], low[1], low[0]], "rgba(8,19,32,.55)");
    polygon(ctx, [top[2], top[3], low[3], low[2]], "rgba(8,19,32,.48)");
    const active = contactIds.has(String(pad.id));
    polygon(ctx, top, active ? "#f4c36f" : (pad.material === "smoke" ? "#516174" : "#557b83"), active ? "#fff1b4" : "rgba(174,228,218,.55)");
    const center = project(pad);
    ctx.fillStyle = active ? "#2c1b16" : "#c3e3dc";
    ctx.font = "700 8px 'Courier New', monospace";
    ctx.textAlign = "center";
    ctx.fillText(active ? "●" : "·", center.x, center.y + 3);
  }

  function drawWalker(ctx, contacts) {
    const byId = Object.fromEntries(model.world.pads.map((pad) => [String(pad.id), pad]));
    const body = model.body;
    for (const leg of LEGS) {
      const target = contacts[leg] && byId[contacts[leg]] ? byId[contacts[leg]] : footTarget(body, leg, model.actuators[leg]);
      const hip = {x: body.x + BASE_X[leg] * .62, y: body.y + BASE_Y[leg] * .62, z: body.z - .22};
      const knee = {x: (hip.x + target.x) / 2, y: (hip.y + target.y) / 2, z: Math.max(target.z + .16, body.z - .88)};
      const h = project(hip), k = project(knee), f = project(target);
      ctx.strokeStyle = COLORS[leg];
      ctx.lineWidth = 8;
      ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(h.x, h.y); ctx.lineTo(k.x, k.y); ctx.lineTo(f.x, f.y); ctx.stroke();
      ctx.strokeStyle = "rgba(21,15,36,.8)";
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(h.x, h.y); ctx.lineTo(k.x, k.y); ctx.lineTo(f.x, f.y); ctx.stroke();
      ctx.fillStyle = contacts[leg] ? "#ffe7a5" : "#8291a6";
      ctx.beginPath(); ctx.arc(f.x, f.y, contacts[leg] ? 6 : 5, 0, Math.PI * 2); ctx.fill();
    }
    const center = project(body);
    const corners = [
      {x: body.x - .82, y: body.y - .54, z: body.z - .22}, {x: body.x + .82, y: body.y - .54, z: body.z - .22},
      {x: body.x + .82, y: body.y + .54, z: body.z - .22}, {x: body.x - .82, y: body.y + .54, z: body.z - .22},
      {x: body.x - .82, y: body.y - .54, z: body.z + .28}, {x: body.x + .82, y: body.y - .54, z: body.z + .28},
      {x: body.x + .82, y: body.y + .54, z: body.z + .28}, {x: body.x - .82, y: body.y + .54, z: body.z + .28},
    ].map(project);
    polygon(ctx, [corners[0], corners[1], corners[5], corners[4]], "#b87935", "#f4d28a");
    polygon(ctx, [corners[1], corners[2], corners[6], corners[5]], "#805028", "#d9a95e");
    polygon(ctx, [corners[4], corners[5], corners[6], corners[7]], "#e1ad55", "#fff0b5");
    ctx.fillStyle = "#39254a";
    ctx.font = "800 13px Georgia, serif";
    ctx.textAlign = "center";
    ctx.fillText("CW", center.x, center.y + 5);
  }

  function drawScene() {
    if (!model) return;
    const canvas = document.querySelector(".crater-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const bg = ctx.createLinearGradient(0, 0, 0, canvas.height);
    bg.addColorStop(0, "#0e1835"); bg.addColorStop(.62, "#192647"); bg.addColorStop(1, "#281d43");
    ctx.fillStyle = bg; ctx.fillRect(0, 0, canvas.width, canvas.height);
    for (let i = 0; i < 16; i += 1) {
      ctx.fillStyle = `rgba(148,218,214,${.025 + (i % 3) * .012})`;
      ctx.beginPath(); ctx.arc((i * 211) % 920, 58 + (i * 47) % 230, 1.5 + (i % 3), 0, Math.PI * 2); ctx.fill();
    }
    const quads = [...(model.world.terrain_quads || [])].sort((a, b) => {
      const da = a.vertices.reduce((sum, p) => sum + project(p).depth, 0);
      const db = b.vertices.reduce((sum, p) => sum + project(p).depth, 0);
      return da - db;
    });
    quads.forEach((quad, index) => {
      const points = quad.vertices.map(project);
      const shade = 23 + (index % 5) * 4;
      polygon(ctx, points, `rgb(${shade},${39 + (index % 4) * 4},${66 + (index % 5) * 5})`, "rgba(124,174,181,.12)");
    });
    const rimA = project({x: model.world.escape_x, y: -2.72, z: .18});
    const rimB = project({x: model.world.escape_x, y: 2.72, z: .18});
    ctx.strokeStyle = "#f6cf7c"; ctx.lineWidth = 5; ctx.setLineDash([9, 7]);
    ctx.beginPath(); ctx.moveTo(rimA.x, rimA.y); ctx.lineTo(rimB.x, rimB.y); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = "#ffe8a4"; ctx.font = "800 11px 'Courier New', monospace"; ctx.textAlign = "left";
    ctx.fillText("OUTSIDE LEDGE", rimA.x + 10, rimA.y - 8);
    const contacts = model.contacts;
    const contactIds = new Set(Object.values(contacts).filter(Boolean));
    [...model.world.pads].sort((a, b) => project(a).depth - project(b).depth).forEach((pad) => drawPad(ctx, pad, contactIds));
    drawWalker(ctx, contacts);
    ctx.fillStyle = "rgba(230,247,242,.72)"; ctx.font = "700 9px 'Courier New', monospace"; ctx.textAlign = "left";
    ctx.fillText(`TERRACE ${model.stage + 1}/${model.world.stages.length}   YAW ${Number(model.camera.yaw).toFixed(2)}   DEPTH VIEW`, 18, 25);
    ctx.fillStyle = "rgba(230,247,242,.55)"; ctx.fillText("GOLD = CONTACT · BLUE = AVAILABLE PAD · GREY = DECOY", 18, 42);
  }

  function setReadout(message, status = "idle") { model?.helpers?.setReadout(message, status); }
  function record(entry) { model.actions.push({seq: model.actions.length + 1, tick: model.tick, ...entry}); }
  function updateLabels() {
    if (!model) return;
    const nextStage = model.stage < model.world.stages.length - 1 ? model.world.stages[model.stage + 1] : null;
    const indicatedLeg = nextStage ? String(nextStage.transfer_leg) : null;
    document.querySelectorAll("[data-leg-card]").forEach((card) => {
      const leg = card.dataset.legCard;
      card.classList.toggle("is-selected", leg === model.selected);
      card.classList.toggle("is-indicated", leg === indicatedLeg && !model.motion);
      for (const actuator of ACTUATORS) {
        const value = String(model.actuators[leg][actuator]);
        const output = card.querySelector(`[data-value-for="${actuator}"]`); if (output) output.textContent = value;
        const input = card.querySelector(`input[data-actuator="${actuator}"]`); if (input) input.value = value;
      }
    });
    const support = document.querySelector(".crater-support"); if (support) support.textContent = `${Object.values(model.contacts).filter(Boolean).length} / 4`;
    const stage = document.querySelector(".crater-stage"); if (stage) stage.textContent = `${model.stage + 1} / ${model.world.stages.length}`;
    const pose = posture(model.contacts);
    const poseNode = document.querySelector(".crater-pose"); if (poseNode) poseNode.textContent = `ROLL ${pose.roll.toFixed(2)} · PITCH ${pose.pitch.toFixed(2)}`;
    const marker = document.querySelector(".crater-transfer-leg");
    if (marker) marker.textContent = model.motion ? "BODY TRANSIT" : (indicatedLeg ? indicatedLeg.replace("_", " ").toUpperCase() : "ESCAPE LEDGE");
    const markerNote = document.querySelector(".crater-transfer-note");
    if (markerNote) markerNote.textContent = model.motion ? "body advancing over the raised terrain" : (indicatedLeg ? "highlighted card · release only this support" : "all supports established");
    const certify = document.querySelector(".crater-certify"); if (certify) certify.disabled = !model.readyToCertify || model.failed || model.completed;
    const settle = document.querySelector(".crater-settle"); if (settle) settle.disabled = model.failed || model.completed;
  }

  function applyControl(leg, actuator, value, source) {
    if (!model || model.failed || model.completed || !LEGS.includes(leg) || !ACTUATORS.includes(actuator)) return;
    const before = Number(model.actuators[leg][actuator]);
    const next = clamp(Math.round(Number(value)), -5, 5);
    if (before === next) return;
    model.selected = leg;
    model.actuators[leg][actuator] = next;
    record({type: "control", input_source: source, leg, actuator, before, value: next, after: next});
    setReadout(`${leg.replace("_", " ").toUpperCase()} · ${actuator.toUpperCase()} ${next > 0 ? "+" : ""}${next}`);
    updateLabels(); drawScene();
  }

  function settle() {
    if (!model || model.failed || model.completed) return;
    model.tick += 1;
    const stageBefore = model.stage;
    const bodyBefore = clone(model.body);
    let pose = posture(model.contacts);
    let failed = false;
    if (model.motion) {
      const targetStage = Number(model.motion.targetStage);
      const path = model.world.stages[targetStage].body_path_from_previous || [];
      const step = Number(model.motion.step);
      const nextBody = path[step] ? clone(path[step]) : null;
      if (!nextBody || !bodyClearOfTerrain(nextBody)) {
        model.failed = true;
        failed = true;
        model.readyToCertify = false;
        setReadout("FAIL · WALKER BODY COLLIDED WITH THE TERRAIN", "error");
      } else {
        model.body = nextBody;
        model.bodyTrace.push(clone(nextBody));
        model.motion.step = step + 1;
        if (model.motion.step >= path.length) {
          const destination = model.world.stages[targetStage];
          model.stage = targetStage;
          model.body = clone(path[path.length - 1]);
          model.actuators = clone(destination.stance_controls);
          model.contacts = clone(destination.support_pad_ids);
          model.motion = null;
          setReadout(`TERRACE ${model.stage + 1} REACHED · BODY CROSSED RAISED TERRAIN`, "passed");
        } else {
          setReadout(`BODY TRANSIT · STEP ${model.motion.step}/${path.length} · SUPPORT HELD`);
        }
      }
    } else {
      const contacts = contactsFor();
      const supportCount = Object.values(contacts).filter(Boolean).length;
      pose = posture(contacts);
      model.contacts = contacts;
      failed = supportCount < 3 || Math.abs(pose.roll) > Number(model.world.posture_limit) || Math.abs(pose.pitch) > Number(model.world.posture_limit);
      if (failed) {
        model.failed = true;
        model.readyToCertify = false;
        setReadout(`FAIL · SUPPORT ${supportCount}/4 ORIENTATION OUT OF LIMIT`, "error");
      } else if (model.stage < model.world.stages.length - 1) {
        const nextStage = model.world.stages[model.stage + 1];
        const transferLeg = String(nextStage.transfer_leg);
        const current = model.world.stages[model.stage];
        const otherSafe = LEGS.filter((leg) => leg !== transferLeg).every((leg) => contacts[leg] === String(current.support_pad_ids[leg]));
        if (!contacts[transferLeg] && Number(model.actuators[transferLeg].lift) >= RAISED && otherSafe) {
          if (!model.released.includes(model.stage)) model.released.push(model.stage);
        } else if (model.released.includes(model.stage) && contacts[transferLeg] === String(nextStage.support_pad_ids[transferLeg]) && otherSafe) {
          model.motion = {targetStage: model.stage + 1, step: 0};
          setReadout("FOOT PLACED · BODY TRANSIT BEGINS OVER RAISED TERRAIN", "passed");
        } else {
          setReadout(`SUPPORT ${supportCount}/4 · FOLLOW THE HIGHLIGHTED TRANSFER LEG`);
        }
      }
    }
    if (!failed && model.stage === model.world.stages.length - 1 && Number(model.body.x) >= Number(model.world.escape_x) && new Set(Object.values(model.contacts)).size === 4) {
      model.readyToCertify = true;
      setReadout("ESCAPE LEDGE REACHED · CERTIFY THE WALKER", "passed");
    }
    record({type: "settle", input_source: "settle_button", stage_before: stageBefore, stage_after: model.stage, body_before: bodyBefore, body_after: clone(model.body), motion_step_after: model.motion ? model.motion.step : null, contacts_after: clone(model.contacts), support_count: Object.values(model.contacts).filter(Boolean).length, failed: model.failed, roll: pose.roll, pitch: pose.pitch});
    updateLabels(); drawScene();
  }

  async function submit() {
    if (!model || model.completed || !model.readyToCertify) return;
    model.completed = true; updateLabels(); setReadout("CERTIFYING CONTACT REPLAY…");
    const payload = {mechanic_id: MECHANIC, task_id: model.state.task_id, challenge_id: model.state.challenge_id, completed: true, actions: model.actions, final_stage: model.stage, final_contacts: clone(model.contacts)};
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) { setReadout("PASS · FOUR FEET ON THE OUTSIDE LEDGE", "passed"); document.querySelector(".crater-root")?.classList.add("is-passed"); }
      else if (outcome.state) { await render(outcome.state, model.helpers); }
      else { model.completed = false; setReadout("FAIL · REPLAY REJECTED", "error"); updateLabels(); }
    } catch (_error) { model.completed = false; setReadout("CERTIFICATION LINK LOST", "error"); updateLabels(); }
  }

  async function retry() {
    if (!model) return;
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({mechanic_id: MECHANIC, task_id: model.state.task_id, challenge_id: model.state.challenge_id, completed: false, actions: model.actions})});
      const outcome = await response.json();
      if (outcome.state) await render(outcome.state, model.helpers);
      else setReadout("NEW ATTEMPT UNAVAILABLE", "error");
    } catch (_error) { setReadout("RETRY LINK LOST", "error"); }
  }

  function installCheat() {
    const form = document.getElementById("cheat-form"); if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const output = document.getElementById("cheat-output");
      try {
        const response = await fetch("/cheat", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({password: document.getElementById("cheat-password")?.value || ""})});
        const data = await response.json();
        output.textContent = response.ok ? `Oracle stages: ${JSON.stringify(data.transfer_controls || [])}` : "Denied.";
      } catch (_error) { output.textContent = "Unavailable."; }
    });
  }

  async function render(state, helpers) {
    if (cleanup) cleanup();
    document.body.dataset.mechanic = MECHANIC;
    const mode = String(state.control_condition?.interaction || "simplified");
    const first = state.world.stages[0];
    model = {state, helpers, world: state.world, mode, stage: 0, body: clone(first.body_pose), bodyTrace: [clone(first.body_pose)], motion: null, actuators: clone(first.stance_controls), contacts: clone(first.support_pad_ids), released: [], failed: false, completed: false, readyToCertify: false, selected: "front_left", tick: 0, actions: [], camera: clone(state.world.camera || {yaw: -.66, pitch: .44})};
    const cards = LEGS.map((leg) => `<article class="crater-leg-card" data-leg-card="${leg}" data-leg="${leg}"><button class="leg-name" type="button" data-select-leg="${leg}"><span class="leg-dot" style="--leg-color:${COLORS[leg]}"></span>${leg.replace("_", " ").toUpperCase()}</button><div class="actuator-grid">${ACTUATORS.map((actuator) => mode === "full" ? `<label><span>${actuator.toUpperCase()} <output data-value-for="${actuator}">0</output></span><input type="range" min="-5" max="5" step="1" value="0" data-actuator="${actuator}" aria-label="${leg} ${actuator}"></label>` : `<div class="nudge-row"><span>${actuator.toUpperCase()} <output data-value-for="${actuator}">0</output></span><button type="button" data-actuator="${actuator}" data-nudge="-1" aria-label="Decrease ${leg} ${actuator}">−</button><button type="button" data-actuator="${actuator}" data-nudge="1" aria-label="Increase ${leg} ${actuator}">+</button></div>`).join("")}</div></article>`).join("");
    helpers.app.innerHTML = `<section class="crater-root" data-interaction="${esc(mode)}"><header class="crater-header"><div><span class="crater-kicker">FIELD UNIT 04 / CONTACT TERRAIN</span><h1>Crater Walker</h1><p>${esc(state.prompt)}</p></div><div class="walker-badge">C·W<br><b>ESCAPE</b></div></header><main class="crater-main"><section class="crater-stage-panel"><div class="crater-canvas-wrap"><canvas class="crater-canvas" width="900" height="560" aria-label="3D crater terrain and brass quadruped"></canvas><div class="canvas-help">DRAG TO ORBIT · GOLD PADS ARE LOAD-BEARING CONTACTS</div></div><div class="view-controls"><span>VIEW</span><button type="button" data-orbit="-1">◀</button><button type="button" data-orbit="1">▶</button><button type="button" data-pitch="-1">▲</button><button type="button" data-pitch="1">▼</button><small>near / far feet may overlap in projection</small></div></section><aside class="crater-console"><div class="console-intro"><span>ACTUATOR BANK</span><b>${mode === "full" ? "DIRECT RAILS" : "PROXY NUDGES"}</b><p>One leg can leave the load only while the other three remain on their visible pads.</p></div><div class="crater-transfer-banner" aria-live="polite"><span>TRANSFER LEG</span><strong class="crater-transfer-leg">FRONT LEFT</strong><small class="crater-transfer-note">highlighted card · release only this support</small></div><div class="crater-leg-cards">${cards}</div><div class="crater-stats"><span>TERRACE <b class="crater-stage">1 / ${state.world.stages.length}</b></span><span>SUPPORT <b class="crater-support">4 / 4</b></span><span class="crater-pose">ROLL 0.00 · PITCH 0.00</span></div><button type="button" class="crater-settle">SETTLE SUPPORT</button><button type="button" class="crater-certify" disabled>CERTIFY ESCAPE</button><button type="button" class="crater-retry">NEW ATTEMPT</button></aside></main><footer class="crater-footer"><span class="crater-readout readout" data-status="idle">READY · FOUR INITIAL FEET SUPPORTED</span><span>YAW · LIFT · EXTEND / 3D CONTACT REPLAY</span></footer>${helpers.cheatPanelTemplate()}</section>`;
    const root = helpers.app.querySelector(".crater-root");
    const canvas = root.querySelector(".crater-canvas");
    const on = (target, event, fn) => target.addEventListener(event, fn);
    root.querySelectorAll("[data-select-leg]").forEach((button) => on(button, "click", () => { model.selected = button.dataset.selectLeg; updateLabels(); }));
    if (mode === "full") root.querySelectorAll("input[data-actuator]").forEach((input) => on(input, "input", () => applyControl(input.closest("[data-leg-card]").dataset.legCard, input.dataset.actuator, input.value, "slider_drag")));
    else root.querySelectorAll("button[data-nudge]").forEach((button) => on(button, "click", () => { const card = button.closest("[data-leg-card]"); const leg = card.dataset.legCard; applyControl(leg, button.dataset.actuator, Number(model.actuators[leg][button.dataset.actuator]) + Number(button.dataset.nudge), "nudge_button"); }));
    on(root.querySelector(".crater-settle"), "click", settle); on(root.querySelector(".crater-certify"), "click", submit); on(root.querySelector(".crater-retry"), "click", retry);
    root.querySelectorAll("[data-orbit]").forEach((button) => on(button, "click", () => { model.camera.yaw += Number(button.dataset.orbit) * .18; drawScene(); }));
    root.querySelectorAll("[data-pitch]").forEach((button) => on(button, "click", () => { model.camera.pitch = clamp(model.camera.pitch + Number(button.dataset.pitch) * .06, .16, .72); drawScene(); }));
    let drag = null;
    on(canvas, "pointerdown", (event) => { drag = {x: event.clientX, y: event.clientY}; canvas.setPointerCapture(event.pointerId); });
    on(canvas, "pointermove", (event) => { if (!drag) return; model.camera.yaw += (event.clientX - drag.x) * .008; model.camera.pitch = clamp(model.camera.pitch + (event.clientY - drag.y) * .003, .16, .72); drag = {x: event.clientX, y: event.clientY}; drawScene(); });
    on(canvas, "pointerup", () => { drag = null; }); on(canvas, "pointercancel", () => { drag = null; });
    installCheat(); updateLabels(); drawScene();
    cleanup = () => { drag = null; };
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC] = {rootSelector: ".crater-root", render};
})();
