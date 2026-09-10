(() => {
  "use strict";

  const PI2 = Math.PI * 2;
  const PLATE_CENTERS = [[320, 350], [960, 350]];
  const MIN_RADIUS = 60;
  const RING_SPACING = 30;
  const NUB_DISTANCE = 400;
  const ACTIONS = ["radial_in", "radial_out", "angular_cw", "angular_ccw", "rotate_cw", "rotate_ccw"];
  const model = {
    state: null,
    rear: null,
    tip: null,
    origin: "rear",
    mode: "translate",
    actions: [],
    ready: false,
    terminal: false,
    busy: false,
    interaction: "full",
    helpers: null,
    exitState: {rear: false, tip: false},
    keyHandler: null,
  };

  const clean = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
  const cloneState = (state) => ({rear: [...state.rear], tip: [...state.tip]});
  const normAngle = (angle) => ((angle + Math.PI) % PI2 + PI2) % PI2 - Math.PI;
  const angleDelta = (a, b) => normAngle(a - b);
  const polarXY = (polar, center) => [center[0] + polar[0] * Math.cos(polar[1]), center[1] + polar[0] * Math.sin(polar[1])];
  const xyPolar = (point, center) => {
    const dx = point[0] - center[0];
    const dy = point[1] - center[1];
    return [Math.hypot(dx, dy), normAngle(Math.atan2(dy, dx))];
  };
  const roundState = (state) => ({
    rear: [Number(state.rear[0].toFixed(6)), Number(normAngle(state.rear[1]).toFixed(6))],
    tip: [Number(state.tip[0].toFixed(6)), Number(normAngle(state.tip[1]).toFixed(6))],
  });
  const pointFor = (state, index) => polarXY(index === 0 ? state.rear : state.tip, PLATE_CENTERS[index]);

  function chooseOtherAngle(activeXY, other, otherCenter) {
    const otherRadius = Number(other[0]);
    const dx = activeXY[0] - otherCenter[0];
    const dy = activeXY[1] - otherCenter[1];
    const distance = Math.hypot(dx, dy);
    if (distance < 1e-6 || otherRadius < 1e-6) return null;
    const cosine = (distance * distance + otherRadius * otherRadius - NUB_DISTANCE * NUB_DISTANCE) / (2 * distance * otherRadius);
    if (cosine < -1.000001 || cosine > 1.000001) return null;
    const base = Math.atan2(dy, dx);
    const offset = Math.acos(Math.max(-1, Math.min(1, cosine)));
    const choices = [base + offset, base - offset];
    const selected = choices.sort((a, b) => Math.abs(angleDelta(a, other[1])) - Math.abs(angleDelta(b, other[1])))[0];
    return [otherRadius, normAngle(selected)];
  }

  function radiusOK(radius) {
    const maximum = MIN_RADIUS + (Number(model.state.map.rings) - 1) * RING_SPACING;
    return radius >= MIN_RADIUS - 1e-6 && radius <= maximum + 1e-6;
  }

  function applyRaw(state, origin, action) {
    if (!model.state || !["rear", "tip"].includes(origin) || !ACTIONS.includes(action)) return null;
    const next = cloneState(state);
    const otherOrigin = origin === "rear" ? "tip" : "rear";
    const active = next[origin];
    const other = next[otherOrigin];
    if (action === "radial_in") active[0] -= Number(model.state.map.radial_step);
    if (action === "radial_out") active[0] += Number(model.state.map.radial_step);
    if (action === "angular_cw") active[1] += Number(model.state.map.angular_step_deg) * Math.PI / 180;
    if (action === "angular_ccw") active[1] -= Number(model.state.map.angular_step_deg) * Math.PI / 180;
    if (action.startsWith("radial_") || action.startsWith("angular_")) {
      active[1] = normAngle(active[1]);
      if (!radiusOK(active[0])) return null;
      const activeXY = polarXY(active, PLATE_CENTERS[origin === "rear" ? 0 : 1]);
      const solved = chooseOtherAngle(activeXY, other, PLATE_CENTERS[origin === "rear" ? 1 : 0]);
      if (!solved) return null;
      other[1] = solved[1];
    } else {
      const activeXY = polarXY(active, PLATE_CENTERS[origin === "rear" ? 0 : 1]);
      const otherXY = polarXY(other, PLATE_CENTERS[origin === "rear" ? 1 : 0]);
      const vx = otherXY[0] - activeXY[0];
      const vy = otherXY[1] - activeXY[1];
      const theta = (action === "rotate_cw" ? 1 : -1) * Number(model.state.map.rotation_step_deg) * Math.PI / 180;
      const rotated = [
        activeXY[0] + vx * Math.cos(theta) - vy * Math.sin(theta),
        activeXY[1] + vx * Math.sin(theta) + vy * Math.cos(theta),
      ];
      next[otherOrigin] = xyPolar(rotated, PLATE_CENTERS[origin === "rear" ? 1 : 0]);
    }
    if (!radiusOK(next.rear[0]) || !radiusOK(next.tip[0])) return null;
    return next;
  }

  function cellFor(point, index) {
    const center = PLATE_CENTERS[index];
    const radius = Math.hypot(point[0] - center[0], point[1] - center[1]);
    const angle = Math.atan2(point[1] - center[1], point[0] - center[0]);
    const rings = Number(model.state.map.rings);
    const sectors = Number(model.state.map.sectors);
    const ring = Math.max(0, Math.min(rings - 1, Math.round((radius - MIN_RADIUS) / RING_SPACING)));
    const sector = Math.floor(((angle + Math.PI) / PI2) * sectors) % sectors;
    return [ring, sector];
  }

  function openSet(index) {
    return new Set((model.state.plates[index].open_cells || []).map((cell) => `${cell[0]},${cell[1]}`));
  }

  function pathClear(oldState, nextState) {
    for (let sample = 0; sample <= 12; sample += 1) {
      const t = sample / 12;
      for (let index = 0; index < 2; index += 1) {
        const oldPoint = pointFor(oldState, index);
        const nextPoint = pointFor(nextState, index);
        const point = [oldPoint[0] + (nextPoint[0] - oldPoint[0]) * t, oldPoint[1] + (nextPoint[1] - oldPoint[1]) * t];
        const cell = cellFor(point, index);
        if (!openSet(index).has(`${cell[0]},${cell[1]}`)) return false;
      }
    }
    return true;
  }

  function inExit(state, index) {
    const cell = cellFor(pointFor(state, index), index);
    return (model.state.plates[index].exit_cells || []).some((item) => Number(item[0]) === cell[0] && Number(item[1]) === cell[1]);
  }

  function updateExitState() {
    model.exitState.rear = inExit({rear: model.rear, tip: model.tip}, 0);
    model.exitState.tip = inExit({rear: model.rear, tip: model.tip}, 1);
    model.ready = model.exitState.rear && model.exitState.tip;
  }

  function polarLabel(polar) {
    return `r ${Number(polar[0]).toFixed(0)} · ${Math.round(normAngle(polar[1]) * 180 / Math.PI)}°`;
  }

  function polarPath(center, ring, sector) {
    const sectors = Number(model.state.map.sectors);
    const a1 = -Math.PI + (sector / sectors) * PI2;
    const a2 = -Math.PI + ((sector + 1) / sectors) * PI2;
    const r1 = MIN_RADIUS + ring * RING_SPACING - RING_SPACING / 2;
    const r2 = MIN_RADIUS + ring * RING_SPACING + RING_SPACING / 2;
    const p1 = [center[0] + r2 * Math.cos(a1), center[1] + r2 * Math.sin(a1)];
    const p2 = [center[0] + r2 * Math.cos(a2), center[1] + r2 * Math.sin(a2)];
    const p3 = [center[0] + r1 * Math.cos(a2), center[1] + r1 * Math.sin(a2)];
    const p4 = [center[0] + r1 * Math.cos(a1), center[1] + r1 * Math.sin(a1)];
    return `M ${p1[0].toFixed(2)} ${p1[1].toFixed(2)} A ${r2} ${r2} 0 0 1 ${p2[0].toFixed(2)} ${p2[1].toFixed(2)} L ${p3[0].toFixed(2)} ${p3[1].toFixed(2)} A ${r1} ${r1} 0 0 0 ${p4[0].toFixed(2)} ${p4[1].toFixed(2)} Z`;
  }

  function plateMarkup(plate, index) {
    const center = PLATE_CENTERS[index];
    const open = new Set((plate.open_cells || []).map((cell) => `${cell[0]},${cell[1]}`));
    const exits = new Set((plate.exit_cells || []).map((cell) => `${cell[0]},${cell[1]}`));
    const cells = [];
    const regions = new Map();
    const showGrid = model.state.show_grid !== false;
    for (let ring = 0; ring < Number(model.state.map.rings); ring += 1) {
      for (let sector = 0; sector < Number(model.state.map.sectors); sector += 1) {
        const key = `${ring},${sector}`;
        const kind = `${open.has(key) ? "is-open" : "is-wall"} ${exits.has(key) ? "is-exit" : ""}`;
        const path = polarPath(center, ring, sector);
        if (showGrid) cells.push(`<path class="seal-cell ${kind}" d="${path}"/>`);
        else regions.set(kind, `${regions.get(kind) || ""} ${path}`);
      }
    }
    const rings = [];
    for (let ring = 0; showGrid && ring < Number(model.state.map.rings); ring += 1) {
      rings.push(`<circle class="seal-ring" cx="${center[0]}" cy="${center[1]}" r="${MIN_RADIUS + ring * RING_SPACING}"/>`);
    }
    for (const [kind, path] of regions) cells.push(`<path class="seal-cell ${kind}" d="${path}"/>`);
    return `<g class="seal-plate seal-plate-${index}" data-grid="${showGrid}">
      <circle class="seal-plate-disc" cx="${center[0]}" cy="${center[1]}" r="246"/>
      <circle class="seal-plate-inset" cx="${center[0]}" cy="${center[1]}" r="224"/>
      ${rings.join("")}${cells.join("")}
      <circle class="seal-center-cap" cx="${center[0]}" cy="${center[1]}" r="22"/>
      <text class="seal-plate-name" x="${center[0]}" y="${center[1] - 214}">${index === 0 ? "REAR PLATE" : "TIP PLATE"}</text>
    </g>`;
  }

  function renderScene() {
    const scene = document.getElementById("seal-scene");
    if (!scene || !model.state) return;
    const rear = pointFor({rear: model.rear, tip: model.tip}, 0);
    const tip = pointFor({rear: model.rear, tip: model.tip}, 1);
    scene.innerHTML = `${plateMarkup(model.state.plates[0], 0)}${plateMarkup(model.state.plates[1], 1)}
      <g class="seal-linkage">
        <line class="seal-shoe-shadow" x1="${rear[0]}" y1="${rear[1]}" x2="${tip[0]}" y2="${tip[1]}"/>
        <line class="seal-shoe" x1="${rear[0]}" y1="${rear[1]}" x2="${tip[0]}" y2="${tip[1]}"/>
        <circle class="seal-nub seal-nub-rear" cx="${rear[0]}" cy="${rear[1]}" r="12"/>
        <circle class="seal-nub seal-nub-tip" cx="${tip[0]}" cy="${tip[1]}" r="12"/>
        <circle class="seal-nub-core" cx="${rear[0]}" cy="${rear[1]}" r="4"/>
        <circle class="seal-nub-core" cx="${tip[0]}" cy="${tip[1]}" r="4"/>
      </g>`;
    updatePanels();
  }

  function updatePanels() {
    const active = document.getElementById("seal-active");
    const mode = document.getElementById("seal-mode");
    const moves = document.getElementById("seal-moves");
    const rearReadout = document.getElementById("seal-rear-readout");
    const tipReadout = document.getElementById("seal-tip-readout");
    const rearExit = document.getElementById("seal-rear-exit");
    const tipExit = document.getElementById("seal-tip-exit");
    const release = document.getElementById("seal-release");
    if (active) active.textContent = model.origin === "rear" ? "REAR / RED" : "TIP / BLUE";
    if (mode) mode.textContent = model.mode === "translate" ? "TRANSLATION" : "SHOE ROTATION";
    if (moves) moves.textContent = `${model.actions.filter((item) => item.type === "move").length} / ${Number(model.state.max_actions)}`;
    if (rearReadout) rearReadout.textContent = model.state.show_polar_readout ? polarLabel(model.rear) : "POLAR TELEMETRY HIDDEN";
    if (tipReadout) tipReadout.textContent = model.state.show_polar_readout ? polarLabel(model.tip) : "POLAR TELEMETRY HIDDEN";
    if (rearExit) {
      rearExit.dataset.state = model.exitState.rear ? "clear" : "sealed";
      rearExit.textContent = model.exitState.rear ? "CLEAR" : "SEALED";
    }
    if (tipExit) {
      tipExit.dataset.state = model.exitState.tip ? "clear" : "sealed";
      tipExit.textContent = model.exitState.tip ? "CLEAR" : "SEALED";
    }
    if (release) release.disabled = model.busy || model.terminal;
    document.querySelectorAll("[data-seal-origin]").forEach((node) => node.classList.toggle("is-selected", node.dataset.sealOrigin === model.origin));
    document.querySelectorAll("[data-seal-mode]").forEach((node) => node.classList.toggle("is-selected", node.dataset.sealMode === model.mode));
  }

  function flash(message, status = "idle") {
    model.helpers?.setReadout(message, status);
    const shell = document.querySelector(".twin-groove-seal");
    shell?.classList.remove("is-jolt");
    void shell?.offsetWidth;
    shell?.classList.add("is-jolt");
  }

  function clearFailure() {
    document.querySelectorAll(".seal-verdict-fail").forEach((node) => node.remove());
    document.querySelector(".twin-groove-seal")?.classList.remove("is-fresh-fail");
  }

  function recordMove(origin, action, inputSource) {
    if (model.busy || model.terminal) return;
    clearFailure();
    const before = cloneState({rear: model.rear, tip: model.tip});
    const candidate = applyRaw(before, origin, action);
    const accepted = Boolean(candidate && pathClear(before, candidate));
    const after = accepted ? candidate : before;
    model.actions.push({
      sequence: model.actions.length + 1,
      type: "move",
      origin,
      action,
      input_source: inputSource,
      accepted,
      before: roundState(before),
      after: roundState(after),
    });
    if (accepted) {
      model.rear = after.rear;
      model.tip = after.tip;
      updateExitState();
      flash(model.ready ? "BOTH EXITS CLEAR · RELEASE THE SHOE" : "CONTACTS MOVED · INSPECT BOTH PLATES", model.ready ? "passed" : "idle");
    } else {
      flash("WALL STOP · THE OTHER PLATE FORBIDS THIS MOVE", "error");
    }
    renderScene();
    if (model.actions.filter((item) => item.type === "move").length >= Number(model.state.max_actions) && !model.ready) {
      model.terminal = true;
      flash("MOVE BUDGET EXHAUSTED · SEAL VOID", "error");
      submit(false);
    }
  }

  async function submit(completed) {
    if (model.busy) return;
    model.busy = true;
    updatePanels();
    const finalState = roundState({rear: model.rear, tip: model.tip});
    const releaseEvent = {
      sequence: model.actions.length + 1,
      type: "release",
      input_source: "release_button",
      before: finalState,
      after: finalState,
    };
    flash("AUDITING COUPLED TRAJECTORY…", "pending");
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      actions: [...model.actions, releaseEvent],
      final_state: finalState,
      completed: Boolean(completed),
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.actions.push(releaseEvent);
        model.terminal = true;
        model.busy = false;
        document.querySelector(".twin-groove-seal")?.classList.add("is-pass");
        document.querySelector(".twin-groove-seal")?.insertAdjacentHTML("beforeend", '<div class="seal-verdict seal-verdict-pass"><small>DUAL EXIT TRAJECTORY ACCEPTED</small><strong>PASS</strong></div>');
        flash("PASS", "passed");
        updatePanels();
        return;
      }
      if (outcome.passed === false && outcome.state) {
        const helpers = model.helpers;
        await helpers.render(outcome.state);
        document.querySelector(".twin-groove-seal")?.classList.add("is-fresh-fail");
        document.querySelector(".twin-groove-seal")?.insertAdjacentHTML("beforeend", '<div class="seal-verdict seal-verdict-fail"><small>TRAJECTORY VOID · FRESH PLATES</small><strong>FAIL</strong></div>');
        flash("FAIL · FRESH PLATES LOADED", "error");
        window.setTimeout(() => document.querySelectorAll(".seal-verdict-fail").forEach((node) => node.remove()), 1800);
        return;
      }
      model.busy = false;
      model.terminal = false;
      flash("NOT GRADED · RETRY RELEASE OR RESET SHOE", "error");
      updatePanels();
    } catch (_error) {
      model.busy = false;
      model.terminal = false;
      flash("SERVICE OFFLINE · RETRY RELEASE OR RESET SHOE", "error");
      updatePanels();
    }
  }

  function reset() {
    if (model.busy) return;
    model.rear = [...model.state.start.rear];
    model.tip = [...model.state.start.tip];
    model.origin = "rear";
    model.mode = "translate";
    model.actions = [];
    model.terminal = false;
    updateExitState();
    document.querySelectorAll(".seal-verdict").forEach((node) => node.remove());
    renderScene();
    flash("SEAL RESET · BOTH GROOVES READY", "idle");
  }

  function bindKeyboard() {
    if (model.keyHandler) window.removeEventListener("keydown", model.keyHandler);
    model.keyHandler = (event) => {
      if (model.interaction !== "full" || model.busy || model.terminal || event.repeat) return;
      if (event.key === "Tab") {
        event.preventDefault();
        model.origin = model.origin === "rear" ? "tip" : "rear";
        updatePanels();
        flash(`ACTIVE CONTACT · ${model.origin.toUpperCase()}`, "idle");
        return;
      }
      if (event.code === "Backquote" || event.key === "`" || event.key === "~") {
        event.preventDefault();
        model.mode = model.mode === "translate" ? "rotate" : "translate";
        updatePanels();
        flash(`CONTROL MODE · ${model.mode === "translate" ? "TRANSLATION" : "ROTATION"}`, "idle");
        return;
      }
      const map = model.mode === "translate"
        ? {ArrowUp: "radial_out", ArrowDown: "radial_in", ArrowLeft: "angular_ccw", ArrowRight: "angular_cw"}
        : {ArrowUp: "rotate_ccw", ArrowDown: "rotate_cw", ArrowLeft: "rotate_ccw", ArrowRight: "rotate_cw"};
      if (map[event.key]) {
        event.preventDefault();
        recordMove(model.origin, map[event.key], "keyboard_polar");
      }
    };
    window.addEventListener("keydown", model.keyHandler);
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "twin-groove-seal";
    const interaction = state.control_condition?.interaction || "full";
    Object.assign(model, {
      state,
      rear: [...state.start.rear],
      tip: [...state.start.tip],
      origin: "rear",
      mode: "translate",
      actions: [],
      ready: false,
      terminal: false,
      busy: false,
      interaction,
      helpers,
      exitState: {rear: false, tip: false},
    });
    const simplifiedControls = interaction === "simplified" ? `
      <div class="seal-control-block"><span class="seal-control-label">ACTIVE CONTACT</span><div class="seal-button-row"><button type="button" data-seal-origin="rear">REAR / RED</button><button type="button" data-seal-origin="tip">TIP / BLUE</button></div></div>
      <div class="seal-control-block"><span class="seal-control-label">MOVE FAMILY</span><div class="seal-button-row"><button type="button" data-seal-mode="translate">TRANSLATE</button><button type="button" data-seal-mode="rotate">ROTATE SHOE</button></div></div>
      <div class="seal-control-block seal-action-grid"><span class="seal-control-label">POLAR ACTION</span><div class="seal-button-grid">${ACTIONS.map((action) => `<button type="button" data-seal-action="${action}">${clean(action.replaceAll("_", " "))}</button>`).join("")}</div></div>` : `
      <div class="seal-key-guide"><span>FULL INPUT</span><b>TAB</b><small>choose nub</small><b>` + "`" + `</b><small>change mode</small><b>↑ / ↓</b><small>out / in (translation)</small><b>← / →</b><small>counterclockwise / clockwise</small><small class="seal-key-note">Rotation mode: arrows turn the shoe about the active nub.</small></div>`;
    helpers.app.innerHTML = `
      <section class="twin-groove-seal" data-interaction="${clean(interaction)}" data-challenge-id="${clean(state.challenge_id)}">
        <header class="seal-header"><div><span class="seal-kicker">CAST LABORATORY / COUPLED CONTACT TEST</span><h1>${clean(state.prompt)}</h1><p>One rigid shoe. Two plates. A move is legal only when both contacts stay in their visible grooves.</p></div><div class="seal-ticket"><small>CHALLENGE</small><strong>${clean(String(state.challenge_id).toUpperCase())}</strong><span>${interaction.toUpperCase()} INPUT</span></div></header>
        <main class="seal-main"><section class="seal-stage"><svg id="seal-scene" viewBox="0 90 1280 520" role="img" aria-label="Two circular groove plates linked by a brass shoe"></svg><div class="seal-legend"><span><i class="legend-red"></i>REAR NUB</span><span><i class="legend-blue"></i>TIP NUB</span><span><i class="legend-aqua"></i>EXIT CHANNEL</span><span><i class="legend-wall"></i>WALL / FORBIDDEN</span></div></section><aside class="seal-rail">
          <div class="seal-rail-heading"><span>LINKAGE CONSOLE</span><b id="seal-active">REAR / RED</b></div>
          <div class="seal-readout"><small>CONTROL MODE</small><strong id="seal-mode">TRANSLATION</strong><em>moves <span id="seal-moves">0 / ${Number(state.max_actions)}</span></em></div>
          ${simplifiedControls}
          <div class="seal-contact-readout"><div><span>REAR CONTACT</span><b id="seal-rear-readout">—</b><i id="seal-rear-exit" data-state="sealed">SEALED</i></div><div><span>TIP CONTACT</span><b id="seal-tip-readout">—</b><i id="seal-tip-exit" data-state="sealed">SEALED</i></div></div>
          <div class="seal-rule"><b>WALL STOP</b><span>If either contact crosses a dark wall, the command stops and the shoe stays put. Re-inspect both plates before the next move.</span></div>
        </aside></main>
        <footer class="seal-footer"><button type="button" id="seal-reset">↺ RESET SHOE</button><div class="readout" data-status="idle">${interaction === "full" ? "TAB SELECTS NUB · ` CHANGES MODE · ARROWS MOVE" : "CHOOSE A NUB, A MODE, THEN A POLAR ACTION"}</div><button type="button" id="seal-release">${clean(state.submit_label || "RELEASE THE SEAL")}</button></footer>
        ${helpers.cheatPanelTemplate()}
      </section>`;
    updateExitState();
    renderScene();
    if (interaction === "simplified") {
      document.querySelectorAll("[data-seal-origin]").forEach((node) => node.addEventListener("click", () => { model.origin = node.dataset.sealOrigin; updatePanels(); flash(`ACTIVE CONTACT · ${model.origin.toUpperCase()}`, "idle"); }));
      document.querySelectorAll("[data-seal-mode]").forEach((node) => node.addEventListener("click", () => { model.mode = node.dataset.sealMode; updatePanels(); flash(`CONTROL MODE · ${model.mode.toUpperCase()}`, "idle"); }));
      document.querySelectorAll("[data-seal-action]").forEach((node) => node.addEventListener("click", () => recordMove(model.origin, node.dataset.sealAction, "proxy_controls")));
    }
    document.getElementById("seal-reset")?.addEventListener("click", reset);
    document.getElementById("seal-release")?.addEventListener("click", () => submit(model.ready));
    helpers.installCheatPanel();
    bindKeyboard();
    window.twinGrooveSealModel = model;
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.twin_groove_seal = {rootSelector: ".twin-groove-seal", render};
})();
