(() => {
  "use strict";

  const MECHANIC_ID = "pocket_locksmith";
  const copy = value => JSON.parse(JSON.stringify(value));
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const esc = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const distance2 = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  const norm = vector => { const length = Math.hypot(...vector); return length > 1e-9 ? vector.map(value => value / length) : [1, 0, 0]; };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const angleError = (a, b) => Math.abs(((Number(a) - Number(b) + 180) % 360 + 360) % 360 - 180);
  const round = (value, places = 3) => Math.round(Number(value) * 10 ** places) / 10 ** places;

  function rotate(point, origin, axis, radians) {
    const relative = point.map((value, index) => value - origin[index]);
    const cosine = Math.cos(radians), sine = Math.sin(radians), c = cross(axis, relative);
    const dot = axis.reduce((sum, value, index) => sum + value * relative[index], 0);
    return relative.map((value, index) => origin[index] + value * cosine + c[index] * sine + axis[index] * dot * (1 - cosine));
  }

  function forwardKinematics(base, torsions) {
    const points = base.map(point => point.map(Number));
    torsions.forEach((angle, bondIndex) => {
      if (bondIndex + 2 >= points.length) return;
      const origin = points[bondIndex];
      const axis = norm(points[bondIndex + 1].map((value, index) => value - origin[index]));
      for (let pointIndex = bondIndex + 2; pointIndex < points.length; pointIndex += 1) {
        points[pointIndex] = rotate(points[pointIndex], origin, axis, Number(angle) * Math.PI / 180);
      }
    });
    return points;
  }

  function perpendicular(axis, sign) {
    let candidate = cross(axis, [0, 1, 0]);
    if (Math.hypot(...candidate) < 1e-7) candidate = cross(axis, [0, 0, 1]);
    return norm(candidate).map(value => value * sign);
  }

  function cameraPoint(point, camera, state) {
    const target = (camera.target || [0.22, 0, 0]).map(Number);
    const relative = point.map((value, index) => Number(value) - target[index]);
    const yaw = Number(camera.yaw || 0) * Math.PI / 180, pitch = Number(camera.pitch || 0) * Math.PI / 180;
    const x1 = Math.cos(yaw) * relative[0] + Math.sin(yaw) * relative[2];
    const z1 = -Math.sin(yaw) * relative[0] + Math.cos(yaw) * relative[2];
    const y2 = Math.cos(pitch) * relative[1] - Math.sin(pitch) * z1;
    const z2 = Math.sin(pitch) * relative[1] + Math.cos(pitch) * z1;
    const depth = Math.max(0.2, Number(camera.distance || 7.1) + z2);
    const scale = Number(state.view.focal || camera.focal || 570) / depth;
    return {x: Number(state.view.canvas_width) / 2 + x1 * scale, y: Number(state.view.canvas_height) / 2 - y2 * scale, depth, scale};
  }

  function handleWorld(points, bondIndex, side, state) {
    const first = points[bondIndex], second = points[bondIndex + 1];
    const axis = norm(second.map((value, index) => value - first[index]));
    const midpoint = first.map((value, index) => (value + second[index]) / 2);
    const direction = perpendicular(axis, side);
    const lift = Number(state.view.handle_lift || 0.34);
    return midpoint.map((value, index) => value + direction[index] * lift);
  }

  function handleInfo(state, points, camera, bondIndex, side) {
    const world = handleWorld(points, bondIndex, side, state);
    const projected = cameraPoint(world, camera, state);
    let visible = projected.x >= -80 && projected.x <= Number(state.view.canvas_width) + 80 && projected.y >= -80 && projected.y <= Number(state.view.canvas_height) + 80;
    if (visible && state.view.handle_occlusion !== false) {
      const radius = Number(state.view.handle_radius || 0.23) * projected.scale;
      (state.ligand.atoms || []).forEach((atom, index) => {
        if (!visible || index === bondIndex || index === bondIndex + 1) return;
        const atomProjection = cameraPoint(points[index], camera, state);
        const atomRadius = Number(atom.radius || 0.18) * atomProjection.scale;
        if (atomProjection.depth < projected.depth - 0.015 && Math.hypot(atomProjection.x - projected.x, atomProjection.y - projected.y) <= radius + atomRadius * 0.82) visible = false;
      });
    }
    return {...projected, world, side, bondIndex, visible};
  }

  function line(ctx, a, b, color, width = 1, dash = []) {
    ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash); ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); ctx.restore();
  }

  function arrowHead(ctx, point, angle, color) {
    ctx.save(); ctx.translate(point.x, point.y); ctx.rotate(angle); ctx.fillStyle = color; ctx.beginPath(); ctx.moveTo(10, 0); ctx.lineTo(-6, -5); ctx.lineTo(-3, 0); ctx.lineTo(-6, 5); ctx.closePath(); ctx.fill(); ctx.restore();
  }

  function shell(state, body, controls, interaction) {
    return `<section class="pocket-locksmith" data-interaction="${esc(interaction)}">
      <header class="pl-head"><div><span>MOLECULAR ACCESS / TORSION BAY</span><h1>POCKET LOCKSMITH</h1></div><p>${esc(state.prompt)}</p></header>
      <main class="pl-main"><div class="pl-scene">${body}</div><aside class="pl-console">${controls}</aside></main>
      <footer class="pl-foot"><div class="readout" data-status="idle">READY</div><div class="pl-footer-note">${esc(state.display.pocket_name)}</div></footer>
    </section>`;
  }

  function verdict(kind, title, note) {
    return `<div class="pl-verdict is-${kind}"><strong>${esc(title)}</strong><span>${esc(note)}</span></div>`;
  }

  async function submit(model, payload) {
    if (model.submitting || model.terminal) return;
    model.submitting = true;
    model.helpers.setReadout("INDEPENDENT FIT REPLAY…", "pending");
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true;
        document.querySelector(".pocket-locksmith")?.insertAdjacentHTML("beforeend", verdict("pass", "POCKET FIT ACCEPTED", "PASS"));
        model.helpers.setReadout("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        document.querySelector(".pocket-locksmith")?.insertAdjacentHTML("beforeend", verdict("fresh", "FAIL · FRESH POCKET", "THE FAILED CONFORMATION WAS REPLACED"));
        model.helpers.setReadout("FAIL · FRESH POCKET", "error");
        window.setTimeout(() => document.querySelector(".pl-verdict.is-fresh")?.remove(), 2100);
      } else {
        model.submitting = false;
        model.helpers.setReadout("FAIL · FIT NOT ACCEPTED", "error");
      }
    } catch (error) {
      model.submitting = false;
      model.helpers.setReadout("FAIL · VERIFIER OFFLINE", "error");
    }
  }

  function render(state, helpers) {
    document.body.dataset.mechanic = "pocket-locksmith";
    const interaction = state.control_condition?.interaction || "full";
    const model = {
      state,
      helpers,
      interaction,
      events: [],
      torsions: (state.ligand.initial_torsions || []).map(Number),
      camera: copy(state.camera),
      points: [],
      handles: [],
      terminal: false,
      submitting: false,
      gesture: null,
      local: null,
    };
    window.pocketLocksmithModel = model;
    const canvasBody = `<div class="pl-canvas-wrap"><canvas id="pl-canvas" width="780" height="480" aria-label="three-dimensional pocket and articulated key"></canvas><div class="pl-scene-legend"><span><i class="pl-dot dot-key"></i>CONNECTED KEY</span><span><i class="pl-dot dot-site"></i>BINDING SITES</span><span><i class="pl-dot dot-wall"></i>POCKET WALL</span></div></div>`;
    const orbitButtons = `<div class="pl-orbit-grid"><button data-orbit="yaw-minus">⟲ YAW</button><button data-orbit="pitch-plus">PITCH ↑</button><button data-orbit="pitch-minus">PITCH ↓</button><button data-orbit="yaw-plus">YAW ⟳</button></div>`;
    const torsionButtons = (state.ligand.bonds || []).filter(bond => bond.rotatable).map((bond, index) => `<div class="pl-joint"><span>${esc(bond.id.toUpperCase())}</span><button data-torsion="${index}" data-side="-1">↶</button><button data-torsion="${index}" data-side="1">↷</button></div>`).join("");
    const simplifiedControls = `${orbitButtons}<h2>ROTATABLE BONDS</h2><div class="pl-joints">${torsionButtons}</div>`;
    const fullControls = `<h2>DIRECT VIEWPORT</h2>`;
    const controls = `${interaction === "simplified" ? simplifiedControls : fullControls}<button id="pl-certify" class="pl-primary">CERTIFY FIT</button><button id="pl-abandon" class="pl-danger">ABANDON / FRESH POCKET</button>`;
    helpers.app.innerHTML = shell(state, canvasBody, controls, interaction);
    const canvas = document.getElementById("pl-canvas");

    function projectedSites() {
      return (state.pocket.sites || []).map(site => ({site, ...cameraPoint(site.center, model.camera, state)}));
    }

    function localCheck() {
      const atomRadius = 0.18, margin = Number(state.control_condition?.difficulty_parameters?.clearance_margin ?? 0.04);
      const siteHits = (state.pocket.sites || []).map(site => ({id: site.id, hit: model.points.some(point => Math.hypot(point[0] - site.center[0], point[1] - site.center[1], point[2] - site.center[2]) <= Number(site.radius))}));
      const contactHits = siteHits.filter(item => item.hit).length;
      const obstacleHits = (state.pocket.obstacles || []).filter(obstacle => model.points.some(point => Math.hypot(...point.map((value, index) => value - obstacle.center[index])) < atomRadius + Number(obstacle.radius) + margin)).map(obstacle => obstacle.id);
      const obstacleClashes = (state.pocket.obstacles || []).reduce((count, obstacle) => count + model.points.filter(point => Math.hypot(...point.map((value, index) => value - obstacle.center[index])) < atomRadius + Number(obstacle.radius) + margin).length, 0);
      let atomClashes = 0;
      for (let first = 0; first < model.points.length; first += 1) for (let second = first + 2; second < model.points.length; second += 1) if (Math.hypot(...model.points[first].map((value, index) => value - model.points[second][index])) < atomRadius * 2 + margin) atomClashes += 1;
      const outOfBounds = model.points.some(point => point.some((value, index) => Math.abs(value - state.pocket.center[index]) > Number(state.pocket.bounds[index]) - atomRadius));
      return {contactHits, contactTotal: state.pocket.sites.length, siteHits, obstacleHits, clashes: obstacleClashes + atomClashes, outOfBounds, accepted: contactHits === state.pocket.sites.length && obstacleClashes + atomClashes === 0 && !outOfBounds};
    }

    function record(type, details = {}) {
      const item = {seq: model.events.length + 1, type, ...details};
      model.events.push(item);
      return item;
    }

    function orbit(deltaYaw, deltaPitch, inputSource, gesture = null) {
      if (model.terminal || model.submitting) return;
      const before = copy(model.camera);
      const after = copy(model.camera);
      after.yaw = (Number(before.yaw || 0) + Number(deltaYaw) + 180) % 360 - 180;
      after.pitch = clamp(Number(before.pitch || 0) + Number(deltaPitch), -72, 72);
      const actual = {yaw: after.yaw - Number(before.yaw || 0), pitch: after.pitch - Number(before.pitch || 0)};
      if (actual.yaw > 180) actual.yaw -= 360; if (actual.yaw < -180) actual.yaw += 360;
      if (Math.abs(actual.yaw) + Math.abs(actual.pitch) < 0.05) return;
      model.camera = after;
      record("orbit", {before, after: copy(after), delta: {yaw: round(actual.yaw), pitch: round(actual.pitch)}, input_source: inputSource, ...(gesture ? {gesture} : {})});
      update();
    }

    function adjustBond(bondIndex, side, inputSource, screen = null) {
      if (model.terminal || model.submitting) return;
      const before = Number(model.torsions[bondIndex]);
      const step = Number(state.control_condition?.difficulty_parameters?.torsion_step_deg ?? 15);
      const after = before + Number(side) * step;
      model.torsions[bondIndex] = after;
      const details = {bond_id: state.ligand.bonds[bondIndex].id, before: round(before), after: round(after), side: Number(side), input_source: inputSource};
      if (inputSource === "torsion_drag") { details.camera = copy(model.camera); details.screen = screen ? [round(screen.x), round(screen.y)] : null; }
      record("torsion", details);
      update();
    }

    function draw() {
      const ctx = canvas.getContext("2d");
      const width = Number(state.view.canvas_width), height = Number(state.view.canvas_height);
      ctx.clearRect(0, 0, width, height);
      const gradient = ctx.createLinearGradient(0, 0, width, height); gradient.addColorStop(0, "#07111d"); gradient.addColorStop(1, "#160e24"); ctx.fillStyle = gradient; ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = "#a9c4df";
      for (let index = 0; index < 80; index += 1) { const x = (index * 97 + state.challenge_id.charCodeAt(index % state.challenge_id.length) * 3) % width; const y = (index * 53 + 31) % height; ctx.globalAlpha = index % 5 === 0 ? 0.55 : 0.2; ctx.fillRect(x, y, 1.5, 1.5); }
      ctx.globalAlpha = 1;
      const center = {x: width / 2, y: height / 2};
      ctx.save(); ctx.translate(center.x, center.y); ctx.rotate(Number(model.camera.yaw) * Math.PI / 180 * 0.12); ctx.scale(1, 0.64); ctx.fillStyle = "rgba(67, 151, 183, .16)"; ctx.strokeStyle = "rgba(130, 234, 240, .65)"; ctx.lineWidth = 4; ctx.beginPath(); ctx.ellipse(0, 0, 302, 192, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); ctx.strokeStyle = "rgba(180, 223, 232, .23)"; ctx.lineWidth = 1; for (let ring = 1; ring < 4; ring += 1) { ctx.beginPath(); ctx.ellipse(0, 0, 302 - ring * 28, 192 - ring * 19, 0, 0, Math.PI * 2); ctx.stroke(); } ctx.restore();
      const drawObjects = [];
      (state.pocket.obstacles || []).forEach(obstacle => drawObjects.push({kind: "obstacle", obstacle, projection: cameraPoint(obstacle.center, model.camera, state)}));
      model.points.forEach((point, index) => drawObjects.push({kind: "atom", index, projection: cameraPoint(point, model.camera, state)}));
      drawObjects.sort((a, b) => b.projection.depth - a.projection.depth);
      (state.pocket.sites || []).forEach(site => { const p = cameraPoint(site.center, model.camera, state); ctx.save(); ctx.strokeStyle = site.color; ctx.shadowColor = site.color; ctx.shadowBlur = 15; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(p.x, p.y, Math.max(11, Number(site.radius) * p.scale), 0, Math.PI * 2); ctx.stroke(); ctx.shadowBlur = 0; ctx.fillStyle = site.color; ctx.font = "800 10px monospace"; ctx.fillText(`SITE ${site.label}`, p.x - 20, p.y - 20); ctx.restore(); });
      state.ligand.bonds.forEach((bond, index) => { const a = cameraPoint(model.points[index], model.camera, state), b = cameraPoint(model.points[index + 1], model.camera, state); line(ctx, a, b, bond.rotatable ? "rgba(239, 214, 153, .82)" : "rgba(170, 188, 214, .62)", bond.rotatable ? 7 : 4); line(ctx, a, b, "rgba(255,255,255,.20)", 1); });
      drawObjects.forEach(item => { if (item.kind === "obstacle") { const p = item.projection, radius = Math.max(8, Number(item.obstacle.radius) * p.scale); ctx.save(); ctx.fillStyle = item.obstacle.material === "pocket-wall" ? "rgba(196, 130, 255, .43)" : "rgba(244, 181, 99, .55)"; ctx.strokeStyle = "rgba(255, 227, 176, .75)"; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(p.x, p.y, radius, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); ctx.strokeStyle = "rgba(20, 22, 40, .5)"; ctx.beginPath(); ctx.moveTo(p.x - radius * .6, p.y - radius * .6); ctx.lineTo(p.x + radius * .6, p.y + radius * .6); ctx.moveTo(p.x + radius * .6, p.y - radius * .6); ctx.lineTo(p.x - radius * .6, p.y + radius * .6); ctx.stroke(); ctx.restore(); } else { const atom = state.ligand.atoms[item.index], p = item.projection, radius = Math.max(10, Number(atom.radius) * p.scale); ctx.save(); ctx.fillStyle = atom.color; ctx.shadowColor = atom.color; ctx.shadowBlur = 15; ctx.beginPath(); ctx.arc(p.x, p.y, radius, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0; ctx.strokeStyle = "rgba(255,255,255,.76)"; ctx.lineWidth = 2; ctx.stroke(); ctx.fillStyle = "#101725"; ctx.font = "900 10px monospace"; ctx.textAlign = "center"; ctx.fillText(atom.element, p.x, p.y + 4); ctx.restore(); } });
      model.handles.forEach(handle => { if (!handle.visible) return; const bond = state.ligand.bonds[handle.bondIndex]; const color = handle.side > 0 ? "#79f2d1" : "#ff9a76"; const midpoint = cameraPoint(model.points[handle.bondIndex], model.camera, state); const endpoint = {x: handle.x, y: handle.y}; ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.setLineDash([5, 4]); ctx.beginPath(); ctx.arc(midpoint.x, midpoint.y, Math.max(15, Math.hypot(endpoint.x - midpoint.x, endpoint.y - midpoint.y) * .92), 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle = color; ctx.beginPath(); ctx.arc(endpoint.x, endpoint.y, 13, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#06111b"; ctx.lineWidth = 2; ctx.stroke(); arrowHead(ctx, endpoint, Math.atan2(endpoint.y - midpoint.y, endpoint.x - midpoint.x), "#06111b"); ctx.restore(); });
    }

    function update() {
      // The public base scaffold is safe to expose; the target torsions remain
      // server-only. Replaying absolute torsions from this scaffold keeps the
      // visible conformation identical to the independent grader.
      model.points = forwardKinematics(state.ligand.base_points || state.ligand.initial_points, model.torsions);
      model.handles = state.ligand.bonds.map((bond, index) => bond.rotatable ? [-1, 1].map(side => handleInfo(state, model.points, model.camera, index, side)) : []).flat();
      model.local = localCheck();
      window.pocketLocksmithModel = model;
      draw();
      if (!model.terminal && !model.submitting) helpers.setReadout(model.local.accepted ? "FIT READY · CERTIFY" : "FIT IN PROGRESS", model.local.accepted ? "passed" : "idle");
    }

    document.querySelectorAll("[data-orbit]").forEach(button => button.addEventListener("click", () => {
      const actions = {"yaw-minus": [-Number(state.view.camera_step_deg || state.view.camera_step_deg || state.control_condition?.difficulty_parameters?.camera_step_deg || 18), 0], "yaw-plus": [Number(state.view.camera_step_deg || state.control_condition?.difficulty_parameters?.camera_step_deg || 18), 0], "pitch-minus": [0, -Number(state.control_condition?.difficulty_parameters?.camera_step_deg || 18)], "pitch-plus": [0, Number(state.control_condition?.difficulty_parameters?.camera_step_deg || 18)]};
      const delta = actions[button.dataset.orbit]; if (delta) orbit(delta[0], delta[1], "orbit_button");
    }));
    document.querySelectorAll("[data-torsion]").forEach(button => button.addEventListener("click", () => adjustBond(Number(button.dataset.torsion), Number(button.dataset.side), "torsion_button")));

    const localPoint = event => { const box = canvas.getBoundingClientRect(); return {x: (event.clientX - box.left) * Number(state.view.canvas_width) / box.width, y: (event.clientY - box.top) * Number(state.view.canvas_height) / box.height}; };
    if (interaction === "full") {
      canvas.addEventListener("pointerdown", event => {
        if (model.terminal || model.submitting) return;
        const point = localPoint(event);
        const handleCandidate = model.handles
          .filter(item => item.visible)
          .map(item => ({item, distance: Math.hypot(item.x - point.x, item.y - point.y)}))
          .filter(item => item.distance <= 26)
          .sort((first, second) => first.distance - second.distance)[0];
        const handle = handleCandidate?.item;
        if (handle) model.gesture = {kind: "torsion", handle, start: point, applied: false};
        else model.gesture = {kind: "orbit", last: point};
        canvas.setPointerCapture(event.pointerId); event.preventDefault();
      });
      canvas.addEventListener("pointermove", event => {
        const gesture = model.gesture; if (!gesture) return; const point = localPoint(event);
        if (gesture.kind === "torsion") {
          if (!gesture.applied && Math.hypot(point.x - gesture.start.x, point.y - gesture.start.y) > 10) { adjustBond(gesture.handle.bondIndex, gesture.handle.side, "torsion_drag", gesture.handle); gesture.applied = true; }
        } else {
          const start = gesture.last, dx = point.x - start.x, dy = point.y - start.y;
          if (Math.abs(dx) + Math.abs(dy) > 0.7) { orbit(dx * .42, dy * -.42, "orbit_drag", {start: [round(start.x), round(start.y)], end: [round(point.x), round(point.y)]}); gesture.last = point; }
        }
        event.preventDefault();
      });
      const endGesture = event => { if (!model.gesture) return; try { if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId); } catch (_error) { /* capture already ended */ } model.gesture = null; };
      canvas.addEventListener("pointerup", endGesture); canvas.addEventListener("pointercancel", endGesture);
    }

    document.getElementById("pl-certify").addEventListener("click", () => {
      if (model.terminal || model.submitting) return;
      const accepted = Boolean(model.local?.accepted);
      record("certify", {accepted, camera: copy(model.camera), torsions: model.torsions.map(round), contacts: model.local?.contactHits || 0, clashes: model.local?.clashes || 0});
      submit(model, {mechanic_id: state.mechanic_id, task_id: state.task_id, challenge_id: state.challenge_id, events: model.events, completed: true});
    });
    document.getElementById("pl-abandon").addEventListener("click", () => submit(model, {mechanic_id: state.mechanic_id, task_id: state.task_id, challenge_id: state.challenge_id, events: [...model.events, {seq: model.events.length + 1, type: "abandon"}], completed: false}));
    update();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {rootSelector: ".pocket-locksmith", render};
})();
