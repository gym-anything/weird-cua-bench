(() => {
  "use strict";
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};

  const DIRECTIONS = {N: [0, -1], E: [1, 0], S: [0, 1], W: [-1, 0]};
  const esc = (value) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;", "'":"&#39;"}[char]));
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const key = (x, y) => `${Number(x)},${Number(y)}`;

  function snapshot(model) {
    return {
      avatar: clone(model.current.avatar),
      boxes: clone(model.current.boxes),
      held: model.current.held,
      delivered: Boolean(model.current.delivered),
    };
  }

  function boxAt(model, x, y) {
    return model.current.boxes.find((box) => Number(box.x) === Number(x) && Number(box.y) === Number(y)) || null;
  }

  function cellAt(model, x, y) {
    return model.cells.get(key(x, y)) || null;
  }

  function inputSource(model, type) {
    if (type === "camera") return model.interaction === "full" ? "camera_drag" : "camera_button";
    if (type === "move") return model.interaction === "full" ? "keyboard_move" : "proxy_move";
    if (["climb", "pickup", "drop"].includes(type)) return model.interaction === "full" ? "keyboard_action" : "proxy_action";
    return "certify_button";
  }

  function applyMove(model, direction) {
    const vector = DIRECTIONS[direction];
    if (!vector) throw new Error("Unknown direction.");
    const avatar = model.current.avatar;
    const tx = Number(avatar.x) + vector[0];
    const ty = Number(avatar.y) + vector[1];
    const cell = cellAt(model, tx, ty);
    if (!cell) throw new Error("The garden edge blocks that step.");
    const box = boxAt(model, tx, ty);
    if (box) {
      const top = Number(cell.height) + 1;
      if (Number(avatar.z) >= top && Number(avatar.z) - top <= 1) {
        avatar.x = tx; avatar.y = ty; avatar.z = top;
        return;
      }
      const dest = cellAt(model, tx + vector[0], ty + vector[1]);
      if (model.current.held || !dest || box.kind === "cargo" || boxAt(model, tx + vector[0], ty + vector[1]) || Number(cell.height) !== Number(avatar.z) || Number(dest.height) !== Number(avatar.z)) {
        throw new Error("That crate cannot move there.");
      }
      box.x = tx + vector[0]; box.y = ty + vector[1]; box.base_z = Number(dest.height);
      avatar.x = tx; avatar.y = ty; avatar.z = Number(cell.height);
      return;
    }
    if (Math.abs(Number(cell.height) - Number(avatar.z)) > 1) throw new Error("That ledge is too high from here.");
    avatar.x = tx; avatar.y = ty; avatar.z = Number(cell.height);
  }

  function applyAction(model, action) {
    const type = action.type;
    if (type === "move") {
      applyMove(model, action.direction);
      return;
    }
    if (type === "climb") {
      const vector = DIRECTIONS[action.direction || "E"];
      const avatar = model.current.avatar;
      const tx = Number(avatar.x) + vector[0];
      const ty = Number(avatar.y) + vector[1];
      const cell = cellAt(model, tx, ty);
      const box = boxAt(model, tx, ty);
      if (!cell || !box || Number(cell.height) !== Number(avatar.z)) throw new Error("There is no same-level crate to climb.");
      avatar.x = tx; avatar.y = ty; avatar.z = Number(cell.height) + 1;
      return;
    }
    if (type === "pickup") {
      if (model.current.held) throw new Error("Your hands are already full.");
      const avatar = model.current.avatar;
      const cargoIndex = model.current.boxes.findIndex((box) => box.kind === "cargo" && Math.abs(Number(box.x) - Number(avatar.x)) + Math.abs(Number(box.y) - Number(avatar.y)) === 1 && Number(box.base_z) === Number(avatar.z));
      if (cargoIndex < 0) throw new Error("Stand beside the marked cargo to pick it up.");
      model.current.held = model.current.boxes[cargoIndex].id;
      model.current.boxes.splice(cargoIndex, 1);
      return;
    }
    if (type === "drop") {
      const avatar = model.current.avatar;
      const hearth = model.world.hearth;
      if (!model.current.held || Number(avatar.x) !== Number(hearth.x) || Number(avatar.y) !== Number(hearth.y) || Number(avatar.z) !== Number(hearth.height)) throw new Error("The marked cargo must be held over the glowing hearth.");
      model.current.held = null;
      model.current.delivered = true;
      return;
    }
    throw new Error(`Unsupported action ${type}.`);
  }

  function rawProject(model, x, y, z) {
    const yaw = Number(model.cameraYaw);
    const rx = Number(x) * Math.cos(yaw) - Number(y) * Math.sin(yaw);
    const depth = Number(x) * Math.sin(yaw) + Number(y) * Math.cos(yaw);
    return {x: rx * 25, y: -depth * 18 - Number(z) * 32, depth};
  }

  function fitProjection(model) {
    const points = [];
    const addPoint = (x, y, z) => points.push(rawProject(model, x, y, z));
    (model.world.cells || []).forEach((cell) => {
      addPoint(cell.x, cell.y, Number(cell.height));
      addPoint(cell.x, cell.y, -0.25);
    });
    (model.current.boxes || []).forEach((box) => addPoint(box.x, box.y, Number(box.base_z) + 1));
    const hearth = model.world.hearth;
    if (hearth) addPoint(hearth.x, hearth.y, Number(hearth.height) + 0.06);
    const avatar = model.current.avatar;
    if (avatar) addPoint(avatar.x, avatar.y, Number(avatar.z) + 0.48);
    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    const depths = points.map((point) => point.depth);
    const minX = Math.min(...xs, 0);
    const maxX = Math.max(...xs, 0);
    const minY = Math.min(...ys, 0);
    const maxY = Math.max(...ys, 0);
    const spanX = Math.max(1, maxX - minX);
    const spanY = Math.max(1, maxY - minY);
    const scale = Math.min(1.14, 730 / (spanX + 90), 390 / (spanY + 80));
    model.projection = {
      scale,
      centerX: (minX + maxX) / 2,
      centerY: (minY + maxY) / 2,
      depthMin: Math.min(...depths, 0),
      depthMax: Math.max(...depths, 1),
    };
  }

  function project(model, x, y, z) {
    const raw = rawProject(model, x, y, z);
    const projection = model.projection || {scale: 1, centerX: 0, centerY: 0};
    return {
      x: 430 + (raw.x - projection.centerX) * projection.scale,
      y: 270 + (raw.y - projection.centerY) * projection.scale,
      depth: raw.depth,
    };
  }

  function visibilityOpacity(model, depth) {
    const projection = model.projection || {depthMin: 0, depthMax: 1};
    const obscurity = Math.max(0, Math.min(1, Number(model.world.camera?.obscurity || 0)));
    const span = Math.max(1, projection.depthMax - projection.depthMin);
    const farFraction = Math.max(0, Math.min(1, (Number(depth) - projection.depthMin) / span));
    return Math.max(0.34, 1 - obscurity * 0.68 * farFraction);
  }

  function footprint(model, x, y, z, half = 0.48) {
    return [[-half,-half], [half,-half], [half,half], [-half,half]]
      .map(([dx,dy]) => project(model, Number(x)+dx, Number(y)+dy, z));
  }

  function prism(model, x, y, topZ, baseZ, half, fill) {
    const top = footprint(model, x, y, topZ, half);
    const base = footprint(model, x, y, baseZ, half);
    const points = values => values.map(p => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");
    const faces = top.map((point, index) => {
      const next = (index+1)%4;
      return {depth: (point.depth+top[next].depth)/2,
        html: `<polygon points="${points([point,top[next],base[next],base[index]])}" fill="${fill}" opacity="${index%2 ? 0.68 : 0.86}"/>`};
    }).sort((a,b) => b.depth-a.depth);
    return faces.map(face => face.html).join("") + `<polygon points="${points(top)}" fill="${fill}"/>`;
  }

  function cubeMarkup(model, box) {
    const p = project(model, box.x, box.y, Number(box.base_z) + 1);
    const tileScale = model.projection?.scale || 1;
    const fill = box.kind === "cargo" ? "#ffd66b" : box.kind === "helper" ? "#75c9b2" : "#9b769d";
    const cls = box.kind === "cargo" ? "hl-cargo" : box.kind === "helper" ? "hl-helper" : "hl-decoy";
    return `<g class="hl-box ${cls}" opacity="${visibilityOpacity(model, p.depth).toFixed(3)}" data-box-id="${esc(box.id)}">${prism(model,box.x,box.y,Number(box.base_z)+1,Number(box.base_z),0.42,fill)}<text x="${p.x.toFixed(1)}" y="${(p.y - 20 * tileScale).toFixed(1)}">${box.kind === "cargo" ? "CARGO" : box.kind === "helper" ? "STEP" : "DECOY"}</text></g>`;
  }

  function renderScene(model) {
    fitProjection(model);
    const svg = model.svg;
    const objects = model.world.cells.map((cell) => {
      const top = project(model, cell.x, cell.y, cell.height);
      const fill = cell.material === "hearthstone" ? "#ca765d" : cell.material === "side-shelf" ? "#796d8e" : "#72b49b";
      return {depth: top.depth, order: 0, html: `<g class="hl-cell" opacity="${visibilityOpacity(model, top.depth).toFixed(3)}">${prism(model,cell.x,cell.y,cell.height,-0.25,0.48,fill)}<text class="hl-elevation" x="${top.x.toFixed(1)}" y="${(top.y+3).toFixed(1)}">${cell.height}</text></g>`};
    });
    const hearth = model.world.hearth;
    const hp = project(model, hearth.x, hearth.y, hearth.height + 0.06);
    const tileScale = model.projection?.scale || 1;
    const flame = `<g class="hl-hearth"><ellipse cx="${hp.x.toFixed(1)}" cy="${(hp.y + 11 * tileScale).toFixed(1)}" rx="${(28 * tileScale).toFixed(1)}" ry="${(10 * tileScale).toFixed(1)}"/><path d="M ${hp.x.toFixed(1)} ${(hp.y + 3 * tileScale).toFixed(1)} C ${(hp.x - 14 * tileScale).toFixed(1)} ${(hp.y - 11 * tileScale).toFixed(1)}, ${(hp.x - 4 * tileScale).toFixed(1)} ${(hp.y - 22 * tileScale).toFixed(1)}, ${hp.x.toFixed(1)} ${(hp.y - 29 * tileScale).toFixed(1)} C ${(hp.x + 15 * tileScale).toFixed(1)} ${(hp.y - 13 * tileScale).toFixed(1)}, ${(hp.x + 13 * tileScale).toFixed(1)} ${(hp.y - 5 * tileScale).toFixed(1)}, ${hp.x.toFixed(1)} ${(hp.y + 3 * tileScale).toFixed(1)}Z"/><text x="${hp.x.toFixed(1)}" y="${(hp.y - 38 * tileScale).toFixed(1)}">HEARTH</text></g>`;
    model.current.boxes.forEach(box => objects.push({depth: project(model,box.x,box.y,box.base_z).depth, order: 1, html: cubeMarkup(model,box)}));
    const avatar = model.current.avatar;
    const ap = project(model, avatar.x, avatar.y, Number(avatar.z) + 0.48);
    const held = model.current.held ? `<rect x="${(ap.x - 14).toFixed(1)}" y="${(ap.y - 34).toFixed(1)}" width="28" height="24" rx="4" fill="#ffd66b" stroke="#fff1ae" stroke-width="3"/><text x="${ap.x.toFixed(1)}" y="${(ap.y - 39).toFixed(1)}">CARGO</text>` : "";
    const avatarMarkup = `<g class="hl-avatar"><ellipse cx="${ap.x.toFixed(1)}" cy="${(ap.y + 18).toFixed(1)}" rx="19" ry="7"/><rect x="${(ap.x - 13).toFixed(1)}" y="${(ap.y - 18).toFixed(1)}" width="26" height="38" rx="10"/><circle cx="${(ap.x).toFixed(1)}" cy="${(ap.y - 25).toFixed(1)}" r="11"/>${held}<text x="${ap.x.toFixed(1)}" y="${(ap.y + 38).toFixed(1)}">COURIER</text></g>`;
    objects.push({depth: hp.depth, order: 2, html: flame}, {depth: ap.depth, order: 3, html: avatarMarkup});
    objects.sort((a,b) => b.depth-a.depth || a.order-b.order);
    svg.innerHTML = `<defs><filter id="hl-glow"><feGaussianBlur stdDeviation="5"/></filter></defs><rect class="hl-sky" x="0" y="0" width="860" height="540" rx="22"/><g>${objects.map(item => item.html).join("")}</g>`;
    model.shell.querySelectorAll(".hl-camera-value").forEach(node => { node.textContent = `${Math.round(Number(model.cameraYaw) * 57.2958)}°`; });
    model.heightValue.textContent = `FEET Z ${avatar.z}`;
    model.cargoValue.textContent = model.current.delivered ? "DELIVERED" : model.current.held ? "IN HAND" : "WAITING";
    model.positionValue.textContent = `${avatar.x}, ${avatar.y}`;
    model.obscurityValue.textContent = `${Math.round(Number(model.world.camera?.obscurity || 0) * 100)}% FOG`;
    model.shell.dataset.cameraYaw = String(Math.round(Number(model.cameraYaw) * 1000) / 1000);
    model.shell.dataset.cameraObscurity = String(Number(model.world.camera?.obscurity || 0));
    model.shell.dataset.projectionScale = String(Math.round((model.projection?.scale || 1) * 1000) / 1000);
    model.shell.dataset.delivered = model.current.delivered ? "true" : "false";
  }

  function setReadout(model, message, status = "idle") {
    model.readout.dataset.status = status;
    model.readout.textContent = message;
  }

  function recordAction(model, action) {
    if (model.submitting || model.completed) return false;
    const before = snapshot(model);
    try {
      applyAction(model, action);
    } catch (error) {
      setReadout(model, `BLOCKED · ${error.message}`, "error");
      return false;
    }
    const after = snapshot(model);
    const event = {seq: model.events.length + 1, type: action.type, input_source: inputSource(model, action.type), before, after};
    if (action.direction) event.direction = action.direction;
    model.events.push(event);
    renderScene(model);
    if (action.type === "move") setReadout(model, `MOVED ${action.direction} · INSPECT THE UPDATED STACKS.`);
    if (action.type === "climb") setReadout(model, "CLIMBED · THE SUPPORT HEIGHT CHANGED.");
    if (action.type === "pickup") setReadout(model, "CARGO IN HAND · RETURN THROUGH THE LIFTED ROUTE.");
    if (action.type === "drop") setReadout(model, "CARGO AT HEARTH · CERTIFY THE DELIVERY.", "passed");
    return true;
  }

  function recordCamera(model, delta, source) {
    if (model.submitting || model.completed) return;
    const before = Number(model.cameraYaw);
    model.cameraYaw = Math.round((before + Number(delta)) * 10000) / 10000;
    const event = {seq: model.events.length + 1, type: "camera", input_source: source, delta: Number(delta), camera_before: Math.round(before * 10000) / 10000, camera_after: model.cameraYaw, before: snapshot(model), after: snapshot(model)};
    model.events.push(event);
    renderScene(model);
    setReadout(model, "CAMERA ORBITED · READ THE NEAR AND FAR BOX FACES.");
  }

  async function submit(model, helpers) {
    if (model.submitting || model.completed) return;
    model.submitting = true;
    model.submit.disabled = true;
    model.abandon.disabled = true;
    const finalSnapshot = snapshot(model);
    model.events.push({seq: model.events.length + 1, type: "certify", input_source: "certify_button", before: finalSnapshot, after: finalSnapshot});
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({mechanic_id: model.state.mechanic_id, task_id: model.state.task_id, challenge_id: model.state.challenge_id, control_condition: model.state.control_condition, events: model.events, completed: true, final_state: finalSnapshot})});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.completed = true;
        setReadout(model, "PASS", "passed");
        helpers.setReadout("PASS", "passed");
        return;
      }
      model.submitting = false;
      if (outcome.state) {
        render(outcome.state, helpers);
        setReadout(window.hearthliftCourierModel, "FAIL · NEW HEARTH READY", "error");
        helpers.setReadout("FAIL · NEW HEARTH READY", "error");
      } else {
        model.submit.disabled = false;
        model.abandon.disabled = false;
        setReadout(model, "FAIL · REPAIR THE ROUTE AND RETRY.", "error");
      }
    } catch (_error) {
      model.submitting = false;
      model.submit.disabled = false;
      model.abandon.disabled = false;
      setReadout(model, "LINK UNAVAILABLE · RETRY.", "error");
    }
  }

  function render(state, helpers) {
    const app = helpers.app;
    document.body.dataset.mechanic = "hearthlift_courier";
    const interaction = String(state.control_condition?.interaction || state.interaction || "full");
    const world = state.world || {};
    const model = {
      state, world, interaction, helpers, events: [], submitting: false, completed: false,
      current: {avatar: clone(world.avatar_start), boxes: clone(world.boxes || []), held: null, delivered: false},
      cameraYaw: Number(world.camera?.initial_yaw || -0.62), cells: new Map((world.cells || []).map((cell) => [key(cell.x, cell.y), cell])),
    };
    app.innerHTML = `<section class="hl-shell" data-interaction="${esc(interaction)}" data-challenge-id="${esc(state.challenge_id)}"><header class="hl-header"><div><p class="hl-kicker">VOXEL DELIVERY / HEARTHLIFT COURIER</p><h1>Carry the marked crate to the ember hearth.</h1><p class="hl-prompt">${esc(state.prompt)}</p></div><div class="hl-badge"><span>WORLD</span><strong>3D STACK</strong><small>${interaction === "full" ? "DIRECT INPUT" : "PROXY INPUT"}</small></div></header><main class="hl-main"><section class="hl-stage-card"><div class="hl-stage-top"><span>ROTATE THE GARDEN TO INSPECT DEPTH</span><span>CAMERA <b class="hl-camera-value">-36°</b> · VISIBILITY <b class="hl-obscurity-value">—</b></span></div><div class="hl-viewport"><svg class="hl-scene" viewBox="0 0 860 540" role="application" aria-label="Isometric voxel garden with stacked boxes, courier, and glowing hearth"></svg><div class="hl-stage-caption">Push a crate to make a step. CLIMB its top, then cross the higher ledge. The glowing hearth is the only delivery point.</div></div></section><aside class="hl-sidebar"><section class="hl-ledger"><p class="hl-section-label">COURIER LEDGER</p><div class="hl-ledger-grid"><span>POSITION <b class="hl-position">—</b></span><span><b class="hl-height">FEET Z —</b></span><span>CARGO <b class="hl-cargo-value">WAITING</b></span><span>CAMERA <b class="hl-camera-value">—</b></span></div></section><section class="hl-controls hl-proxy" ${interaction === "full" ? "hidden" : ""}><p class="hl-section-label">PROXY MOVEMENT</p><div class="hl-dpad"><button data-direction="N">NORTH</button><button data-direction="W">WEST</button><button data-direction="E">EAST</button><button data-direction="S">SOUTH</button></div><div class="hl-action-row"><button class="hl-climb">CLIMB</button><button class="hl-cargo">PICK UP / DROP</button></div><div class="hl-camera-row"><button data-camera="-0.34">ORBIT LEFT</button><button data-camera="0.34">ORBIT RIGHT</button></div></section><section class="hl-controls hl-direct" ${interaction === "simplified" ? "hidden" : ""}><p class="hl-section-label">DIRECT INPUT</p><div class="hl-keyboard"><kbd>WASD</kbd> or <kbd>ARROWS</kbd> move<br><kbd>C</kbd> climbs an adjacent crate<br><kbd>E</kbd> picks up or drops cargo</div><p class="hl-hint">Drag the voxel garden itself to orbit. Camera motion changes the view, not the route.</p></section><section class="hl-rules"><p class="hl-section-label">VISIBLE RULES</p><ol><li>Crates at your feet can be pushed into an empty same-height cell.</li><li>Use CLIMB / C when a crate top is one voxel above you.</li><li>Return for the marked crate, then carry it to the hearth.</li></ol></section><div class="hl-actions"><button class="hl-abandon">ABANDON ATTEMPT</button><button class="hl-submit">${esc(state.submit_label || "CERTIFY DELIVERY")}</button></div><div class="hl-readout" data-status="idle">ORBIT FIRST, THEN READ THE STACKED ROUTE.</div></aside></main></section>`;
    model.shell = app.querySelector(".hl-shell");
    model.shell.querySelector(".hl-rules ol").insertAdjacentHTML("beforeend", "<li>Each ledge rises two voxels. Carrying prevents pushing. Move up or down at most one voxel per step; floor numbers show elevation.</li>");
    model.svg = app.querySelector(".hl-scene");
    model.readout = app.querySelector(".hl-readout");
    model.submit = app.querySelector(".hl-submit");
    model.abandon = app.querySelector(".hl-abandon");
    model.cameraValue = app.querySelector(".hl-camera-value");
    model.obscurityValue = app.querySelector(".hl-obscurity-value");
    model.heightValue = app.querySelector(".hl-height");
    model.cargoValue = app.querySelector(".hl-cargo-value");
    model.positionValue = app.querySelector(".hl-position");
    window.hearthliftCourierModel = model;

    app.querySelectorAll("[data-direction]").forEach((button) => button.addEventListener("click", () => recordAction(model, {type: "move", direction: button.dataset.direction})));
    app.querySelector(".hl-climb").addEventListener("click", () => recordAction(model, {type: "climb", direction: "E"}));
    app.querySelector(".hl-cargo").addEventListener("click", () => recordAction(model, {type: model.current.held ? "drop" : "pickup"}));
    app.querySelectorAll("[data-camera]").forEach((button) => button.addEventListener("click", () => recordCamera(model, Number(button.dataset.camera), "camera_button")));
    model.submit.addEventListener("click", () => submit(model, helpers));
    model.abandon.addEventListener("click", () => submit(model, helpers));
    if (window.__hearthliftCourierKeyHandler) document.removeEventListener("keydown", window.__hearthliftCourierKeyHandler);
    window.__hearthliftCourierKeyHandler = (event) => {
      if (model.interaction !== "full" || event.repeat) return;
      const keyName = String(event.key || "").toLowerCase();
      const move = {w: "N", arrowup: "N", d: "E", arrowright: "E", s: "S", arrowdown: "S", a: "W", arrowleft: "W"}[keyName];
      if (move) { event.preventDefault(); recordAction(model, {type: "move", direction: move}); return; }
      if (keyName === "c") { event.preventDefault(); recordAction(model, {type: "climb", direction: "E"}); return; }
      if (keyName === "e") { event.preventDefault(); recordAction(model, {type: model.current.held ? "drop" : "pickup"}); }
    };
    document.addEventListener("keydown", window.__hearthliftCourierKeyHandler);
    let drag = null;
    model.svg.addEventListener("pointerdown", (event) => {
      if (model.interaction !== "full") return;
      drag = {start: event.clientX, last: event.clientX, moved: false};
      model.svg.setPointerCapture?.(event.pointerId);
    });
    model.svg.addEventListener("pointermove", (event) => {
      if (!drag) return;
      const delta = event.clientX - drag.last;
      if (Math.abs(event.clientX - drag.start) > 4) drag.moved = true;
      drag.last = event.clientX;
      model.cameraYaw = Math.round((model.cameraYaw + delta * 0.008) * 10000) / 10000;
      renderScene(model);
    });
    model.svg.addEventListener("pointerup", (event) => {
      if (!drag) return;
      const delta = (drag.last - drag.start) * 0.008;
      const moved = drag.moved;
      drag = null;
      model.svg.releasePointerCapture?.(event.pointerId);
      if (moved && Math.abs(delta) > 0.01) {
        // The visual drag has already moved the camera. Rebuild the event's
        // exact before/after values from the drag length without duplicating
        // the physical world state.
        const after = Number(model.cameraYaw);
        const before = Math.round((after - delta) * 10000) / 10000;
        model.events.push({seq: model.events.length + 1, type: "camera", input_source: "camera_drag", delta: Math.round(delta * 10000) / 10000, camera_before: before, camera_after: after, before: snapshot(model), after: snapshot(model)});
        setReadout(model, "CAMERA ORBITED · READ THE NEAR AND FAR BOX FACES.");
      }
    });
    model.svg.addEventListener("pointercancel", () => { drag = null; });
    renderScene(model);
  }

  window.WeirdCaptchaMechanics.hearthlift_courier = {rootSelector: ".hl-shell", render};
})();
