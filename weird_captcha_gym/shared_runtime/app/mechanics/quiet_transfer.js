(() => {
  "use strict";

  const ID = "quiet_transfer";
  const TAU = Math.PI * 2;
  const GOAL_SCALES = {
    center: 0.015,
    velocity: 0.020,
    width: 0.0015,
    width_velocity: 0.003,
    phase: 0.070,
  };
  let model = null;

  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

  function smoothstep(value) {
    const x = clamp(Number(value), 0, 1);
    return x * x * (3 - 2 * x);
  }

  function interpolate(curve, tick, ticks) {
    const position = clamp(Number(tick) / Math.max(1, Number(ticks)), 0, 1) * (curve.length - 1);
    const index = Math.min(curve.length - 2, Math.max(0, Math.floor(position)));
    const fraction = position - index;
    return Number(curve[index]) * (1 - fraction) + Number(curve[index + 1]) * fraction;
  }

  function visibleGoal() {
    return model.state.requirements.goal_state;
  }

  function fidelity(state) {
    const goal = visibleGoal();
    const squaredError = Object.entries(GOAL_SCALES).reduce((sum, [field, scale]) => (
      sum + ((Number(state[field]) - Number(goal[field])) / scale) ** 2
    ), 0);
    return clamp(Math.exp(-0.5 * squaredError), 0, 1);
  }

  function stateAt(curve, tick) {
    const config = model.state;
    const wave = config.wave_model;
    const ticks = Number(config.curve.playback_ticks);
    const dt = Number(wave.dt);
    const spring = Number(wave.spring_strength);
    const damping = Number(wave.velocity_damping);
    const excitation = Number(wave.excitation_gain);
    const widthDamping = Number(wave.width_damping);
    const widthRestore = Number(wave.width_restore);
    const base = Number(wave.base_width);
    let center = Number(curve[0]);
    let velocity = 0;
    let width = base;
    let widthVelocity = 0;
    let previousTrap = Number(curve[0]);
    let previousPreviousTrap = Number(curve[0]);
    for (let currentTick = 1; currentTick <= Math.max(0, Number(tick)); currentTick += 1) {
      const trap = interpolate(curve, currentTick, ticks);
      const acceleration = trap - 2 * previousTrap + previousPreviousTrap;
      velocity += (3.5 * spring * (trap - center) - damping * velocity) * dt;
      center += velocity * dt;
      widthVelocity += (
        Math.abs(acceleration) * excitation
        - widthDamping * widthVelocity
        - widthRestore * (width - base)
      ) * dt;
      width += widthVelocity * dt;
      previousPreviousTrap = previousTrap;
      previousTrap = trap;
    }
    const state = {
      tick: Number(tick),
      trap: interpolate(curve, Number(tick), ticks),
      center,
      velocity,
      width,
      width_velocity: widthVelocity,
      phase: velocity * 4 + widthVelocity * 8,
    };
    state.fidelity = fidelity(state);
    return state;
  }

  function record(type, fields = {}) {
    model.events.push({seq: model.events.length + 1, type, ...fields});
  }

  function curvePoint(index, value = model.curve[index]) {
    const count = model.curve.length;
    return {
      x: 40 + (index / Math.max(1, count - 1)) * 820,
      y: 220 - Number(value) * 180,
    };
  }

  function currentRoot() {
    return document.querySelector(".quiet-transfer-shell");
  }

  function setReadout(message, status = "idle") {
    const node = currentRoot()?.querySelector(".readout");
    if (!node) return;
    node.textContent = String(message);
    node.dataset.status = status;
  }

  function revisedCurve() {
    if (!model.firstCompleteCurve) return false;
    const error = Math.sqrt(model.curve.reduce((sum, value, index) =>
      sum + (value - model.firstCompleteCurve[index]) ** 2, 0) / model.curve.length);
    return error > 0.002;
  }

  function clearFailure() {
    currentRoot()?.removeAttribute("data-fresh-failure");
  }

  // Raw state and public goal on the same fixed axes, never an error or score.
  // Density alone cannot expose velocity and width velocity independently.
  function drawState(ctx, state, colors) {
    const goal = visibleGoal();
    const fields = [
      ["center", "POSITION", 0, 1],
      ["velocity", "VELOCITY", -0.6, 0.6],
      ["width", "WIDTH", 0.07, 0.15],
      ["width_velocity", "WIDTH RATE", -0.06, 0.06],
      ["phase", "PHASE", -3, 3],
    ];
    fields.forEach(([field, label, low, high], index) => {
      const left = 42 + index * 166;
      const x = value => left + clamp((value - low) / (high - low), 0, 1) * 144;
      ctx.font = "700 11px ui-monospace, monospace";
      ctx.fillStyle = "#b8cfca";
      ctx.fillText(label, left, 341);
      ctx.strokeStyle = "#50717c";
      ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(left, 366); ctx.lineTo(left + 144, 366); ctx.stroke();
      ctx.strokeStyle = colors.violet;
      ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(x(goal[field]), 349); ctx.lineTo(x(goal[field]), 383); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = colors.cyan;
      ctx.beginPath(); ctx.arc(x(state[field]), 366, 4, 0, TAU); ctx.fill();
      if (model.state.requirements.numeric_state_readout) {
        ctx.font = "11px ui-monospace, monospace";
        ctx.fillText(Number(state[field]).toFixed(3), left, 403);
        ctx.fillStyle = colors.violet;
        ctx.fillText(Number(goal[field]).toFixed(3), left + 83, 403);
      }
    });
  }

  function drawCurve() {
    const svg = document.getElementById("qt-curve");
    if (!svg) return;
    const root = currentRoot();
    const path = svg.querySelector("[data-curve-path]");
    const points = model.curve.map((value, index) => curvePoint(index, value));
    const d = points.map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ");
    if (path) path.setAttribute("d", d);
    svg.querySelectorAll("[data-knot]").forEach((node) => {
      const index = Number(node.dataset.knot);
      const point = points[index];
      node.setAttribute("cx", point.x);
      node.setAttribute("cy", point.y);
      node.classList.toggle("is-endpoint", index === 0 || index === points.length - 1);
      node.setAttribute("aria-label", `control knot ${index + 1}, position ${model.curve[index].toFixed(2)}`);
    });
    root?.querySelectorAll("[data-knot-value]").forEach((node) => {
      const index = Number(node.dataset.knotValue);
      node.textContent = Number(model.curve[index]).toFixed(2);
    });
    const run = document.getElementById("qt-run");
    if (run && !model.running) run.disabled = false;
  }

  function density(x, state, phaseOffset = 0) {
    const width = Math.max(0.025, Number(state.width));
    const distance = (x - Number(state.center)) / width;
    const envelope = Math.exp(-0.5 * distance * distance);
    const ripple = 0.78 + 0.22 * Math.cos(Number(state.phase) + phaseOffset + distance * 2.3);
    return Math.max(0, envelope * ripple);
  }

  function drawWorld() {
    const canvas = document.getElementById("quiet-transfer-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const width = Number(model.state.stage.width);
    const height = Number(model.state.stage.height);
    const colors = model.state.palette;
    const gradient = ctx.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, colors.ink);
    gradient.addColorStop(1, "#102b3a");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = "rgba(125, 232, 225, 0.09)";
    ctx.lineWidth = 1;
    for (let x = 40; x <= 860; x += 41) {
      ctx.beginPath(); ctx.moveTo(x, 28); ctx.lineTo(x, 332); ctx.stroke();
    }
    for (let y = 40; y <= 320; y += 35) {
      ctx.beginPath(); ctx.moveTo(36, y); ctx.lineTo(864, y); ctx.stroke();
    }

    const toX = (value) => 40 + Number(value) * 820;
    const baseline = 235;
    const sourceX = toX(model.state.source.position);
    const destinationX = toX(model.state.destination.position);
    const well = (x, color, label, dashed = false) => {
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      if (dashed) ctx.setLineDash([5, 5]);
      ctx.beginPath();
      ctx.moveTo(x - 48, baseline + 3);
      ctx.quadraticCurveTo(x, baseline + 65, x + 48, baseline + 3);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = color;
      ctx.font = "700 12px ui-monospace, monospace";
      ctx.fillText(label, x - ctx.measureText(label).width / 2, 32);
      ctx.restore();
    };
    well(sourceX, colors.gold, "SOURCE WELL");
    well(destinationX, colors.violet, "QUIET DESTINATION", true);

    const state = model.lastState || stateAt(model.curve, model.tick);
    const trapX = toX(state.trap);
    ctx.strokeStyle = "rgba(255, 209, 102, 0.7)";
    ctx.setLineDash([4, 7]);
    ctx.beginPath(); ctx.moveTo(trapX, 54); ctx.lineTo(trapX, 306); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = colors.gold;
    ctx.beginPath(); ctx.arc(trapX, 54, 7, 0, TAU); ctx.fill();
    ctx.font = "700 10px ui-monospace, monospace";
    ctx.fillText("MOVING TRAP", clamp(trapX - 39, 40, 790), 48);

    // The target outline is the public terminal wave-state goal.  It is the
    // same goal used by the deterministic grader, not a hidden answer curve.
    if (model.state.requirements.target_outline) {
      const goal = visibleGoal();
      ctx.save();
      ctx.strokeStyle = `${colors.violet}99`;
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 2;
      ctx.beginPath();
      for (let pixel = 40; pixel <= 860; pixel += 4) {
        const x = (pixel - 40) / 820;
        const y = baseline - density(x, {center: goal.center, width: goal.width, phase: goal.phase}, 0) * 112;
        if (pixel === 40) ctx.moveTo(pixel, y); else ctx.lineTo(pixel, y);
      }
      ctx.stroke();
      ctx.restore();
    }

    ctx.save();
    ctx.beginPath();
    for (let pixel = 40; pixel <= 860; pixel += 4) {
      const x = (pixel - 40) / 820;
      const y = baseline - density(x, state, 0) * 112;
      if (pixel === 40) ctx.moveTo(pixel, y); else ctx.lineTo(pixel, y);
    }
    ctx.lineTo(860, baseline); ctx.lineTo(40, baseline); ctx.closePath();
    const waveGradient = ctx.createLinearGradient(0, 65, 0, baseline);
    waveGradient.addColorStop(0, `${colors.cyan}dd`);
    waveGradient.addColorStop(1, `${colors.cyan}18`);
    ctx.fillStyle = waveGradient; ctx.fill();
    ctx.beginPath();
    for (let pixel = 40; pixel <= 860; pixel += 4) {
      const x = (pixel - 40) / 820;
      const y = baseline - density(x, state, 0) * 112;
      if (pixel === 40) ctx.moveTo(pixel, y); else ctx.lineTo(pixel, y);
    }
    ctx.strokeStyle = colors.cyan; ctx.lineWidth = 3; ctx.stroke();
    ctx.restore();

    drawState(ctx, state, colors);
  }

  function draw() {
    drawWorld();
    drawCurve();
  }

  function setCurve(index, value, inputSource) {
    if (model.running || model.terminal || model.submitting || index <= 0 || index >= model.curve.length - 1) return;
    const before = Number(model.curve[index]);
    const after = Math.round(clamp(Number(value), Number(model.state.curve.minimum), Number(model.state.curve.maximum)) * 1000) / 1000;
    if (Math.abs(after - before) < 0.0005) return;
    model.curve[index] = after;
    record("curve_edit", {index, before, after, input_source: inputSource});
    if (model.playbacks > 0) model.revisedAfterPlayback = true;
    model.lastState = null;
    model.lastFidelity = null;
    model.tick = 0;
    clearFailure();
    const certify = document.getElementById("qt-certify");
    if (certify) certify.disabled = true;
    setReadout("", "idle");

    draw();
  }

  function resetCurve() {
    if (model.running || model.terminal || model.submitting) return;
    const before = model.curve.slice();
    model.curve = model.initialCurve.slice();
    model.lastState = null;
    model.lastFidelity = null;
    model.tick = 0;
    clearFailure();
    record("curve_reset", {before, after: model.curve.slice(), input_source: "reset_button"});
    const certify = document.getElementById("qt-certify");
    if (certify) certify.disabled = true;

    setReadout("", "idle");
    draw();
  }

  function bindCurvePointer() {
    const svg = document.getElementById("qt-curve");
    if (!svg || model.interaction !== "full") return;
    const locate = (event) => {
      const rect = svg.getBoundingClientRect();
      const sx = 900 / rect.width;
      const sy = 250 / rect.height;
      return {x: (event.clientX - rect.left) * sx, y: (event.clientY - rect.top) * sy};
    };
    const indexAt = (point) => {
      const raw = Math.round((point.x - 40) / 820 * (model.curve.length - 1));
      return clamp(raw, 1, model.curve.length - 2);
    };
    const valueAt = (point) => clamp((220 - point.y) / 180, Number(model.state.curve.minimum), Number(model.state.curve.maximum));
    svg.addEventListener("pointerdown", (event) => {
      if (model.running || model.terminal || model.submitting) return;
      const point = locate(event);
      const index = indexAt(point);
      const center = curvePoint(index);
      if (Math.hypot(point.x - center.x, point.y - center.y) > 30) return;
      model.dragIndex = index;
      svg.setPointerCapture?.(event.pointerId);
      setCurve(index, valueAt(point), "curve_drag");
      event.preventDefault();
    });
    svg.addEventListener("pointermove", (event) => {
      if (model.dragIndex == null) return;
      const point = locate(event);
      setCurve(model.dragIndex, valueAt(point), "curve_drag");
      event.preventDefault();
    });
    const release = (event) => {
      if (model.dragIndex == null) return;
      svg.releasePointerCapture?.(event.pointerId);
      model.dragIndex = null;
    };
    svg.addEventListener("pointerup", release);
    svg.addEventListener("pointercancel", release);
  }

  function runTransfer() {
    if (model.running || model.terminal || model.submitting) return;
    clearFailure();
    model.running = true;
    model.tick = 0;
    model.lastState = stateAt(model.curve, 0);
    model.runCurve = model.curve.slice();
    record("run_start", {curve: model.runCurve.slice(), input_source: "run_button"});
    const runButton = document.getElementById("qt-run");
    const certify = document.getElementById("qt-certify");
    if (runButton) { runButton.disabled = true; runButton.textContent = "RUNNING…"; }
    if (certify) certify.disabled = true;
    setReadout("", "running");

    draw();
    const action = model.helpers.beginAction?.("quiet transfer playback");
    action?.settle?.();
    model.timer = window.setInterval(() => {
      model.tick += 1;
      model.lastState = stateAt(model.runCurve, model.tick);
      model.states.push(model.lastState);
      record("playback_sample", {tick: model.tick, state: {...model.lastState}});
  
      drawWorld();
      if (model.tick >= Number(model.state.curve.playback_ticks)) {
        window.clearInterval(model.timer);
        model.timer = null;
        model.running = false;
        model.lastFidelity = Number(model.lastState.fidelity);
        record("run_complete", {
          ticks: model.tick,
          curve: model.runCurve.slice(),
          state: {...model.lastState},
        });
        model.firstCompleteCurve ||= model.runCurve.slice();
        model.playbacks += 1;
        const minimumPlaybacks = Number(model.state.requirements.minimum_playbacks || 2);
        const readyToCertify = model.playbacks >= minimumPlaybacks && model.revisedAfterPlayback && revisedCurve();
        if (runButton) { runButton.disabled = false; runButton.textContent = "RUN TRANSFER AGAIN"; }
        if (certify) certify.disabled = !readyToCertify;
        setReadout("", "idle");
        draw();
      }
    }, Number(model.state.curve.tick_ms));
  }

  async function certify() {
    const minimumPlaybacks = Number(model.state.requirements.minimum_playbacks || 2);
    if (model.running || model.terminal || model.submitting || !model.lastState || model.playbacks < minimumPlaybacks || !model.revisedAfterPlayback || !revisedCurve()) return;
    const submittedModel = model;
    model.submitting = true;
    document.getElementById("qt-certify").disabled = true;
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({
          mechanic_id: model.state.mechanic_id,
          task_id: model.state.task_id,
          challenge_id: model.state.challenge_id,
          interaction: model.interaction,
          curve: model.curve.slice(),
          events: model.events.slice(),
          completed: true,
        }),
      });
      if (!response.ok) throw new Error("Submission unavailable");
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true;
        setReadout("PASS", "passed");
        currentRoot()?.setAttribute("data-phase", "passed");
        document.getElementById("qt-certify")?.setAttribute("disabled", "disabled");
        document.getElementById("qt-run")?.setAttribute("disabled", "disabled");
        return;
      }
      if (outcome.passed === false) {
        currentRoot()?.setAttribute("data-phase", "failed");
        if (outcome.state) {
          await model.helpers.render(outcome.state);
          currentRoot()?.setAttribute("data-fresh-failure", "true");
          setReadout("FAIL", "error");
        } else {
          setReadout("FAIL", "error");
        }
      }
    } catch (error) {
      if (model === submittedModel) setReadout("SUBMISSION UNAVAILABLE", "error");
    } finally {
      submittedModel.submitting = false;
      if (model === submittedModel && !model.terminal) {
        document.getElementById("qt-certify").disabled = false;
      }
    }
  }

  async function render(state, helpers) {
    if (model?.timer) window.clearInterval(model.timer);
    const interaction = String(state.control_condition?.interaction || state.interaction_mode || "full");
    document.body.dataset.mechanic = "quiet-transfer";
    const count = Number(state.curve.knot_count);
    const initial = state.curve.initial.map(Number);
    const buttons = interaction === "simplified"
      ? `<div class="qt-nudge-grid">${initial.map((value, index) => ({value, index})).filter(({index}) => index > 0 && index < count - 1).map(({value, index}) => `<div class="qt-nudge-row"><b>K${String(index + 1).padStart(2, "0")}</b><button type="button" data-knot="${index}" data-delta="-${state.curve.nudge_step}">−</button><output data-knot-value="${index}">${value.toFixed(2)}</output><button type="button" data-knot="${index}" data-delta="${state.curve.nudge_step}">+</button></div>`).join("")}</div>`
      : "";
    helpers.app.innerHTML = `
      <section class="quiet-transfer-shell" data-interaction="${esc(interaction)}" data-phase="edit" data-challenge-id="${esc(state.challenge_id)}">
        <header class="qt-header">
          <div><span class="qt-kicker">COLD-ATOM CONTROL ROOM</span><h1>QUIET TRANSFER</h1><p>${esc(state.prompt)}</p></div>

        </header>
        <main class="qt-main">
          <section class="qt-world-panel">
            <canvas id="quiet-transfer-canvas" width="900" height="430" aria-label="animated wave packet and potential wells"></canvas>
            <div class="qt-world-caption"><span><i class="qt-current-key"></i> PACKET</span><span><i class="qt-goal-key"></i> GOAL</span></div>
          </section>
          <aside class="qt-console">
            <div class="qt-console-head"><span>CONTROL CURVE</span></div>
            <svg id="qt-curve" class="qt-curve" viewBox="0 0 900 250" role="img" aria-label="time versus trap position control curve">
              <rect x="0" y="0" width="900" height="250" rx="12" fill="rgba(2,10,18,.58)" />
              <path d="M40 220H860M40 40V220" class="qt-axis" />
              <path d="M40 220H860" class="qt-well-line" />
              <path d="M40 190H860M40 160H860M40 130H860M40 100H860M40 70H860" class="qt-grid" />
              <path data-curve-path class="qt-curve-path" d="" />
              ${initial.map((value, index) => `<circle data-knot="${index}" class="qt-knot" cx="0" cy="0" r="${index === 0 || index === count - 1 ? 7 : 8}" tabindex="0" />`).join("")}
              <text x="42" y="242" class="qt-axis-label">TIME 0</text><text x="810" y="242" class="qt-axis-label">TIME T</text>
              <text x="10" y="47" class="qt-axis-label">DEST</text><text x="10" y="217" class="qt-axis-label">SOURCE</text>
            </svg>
            ${buttons}
            <button id="qt-run" type="button" class="qt-primary">RUN TRANSFER</button>
            <button id="qt-certify" type="button" class="qt-certify" disabled>${esc(state.submit_label)}</button>
            <button id="qt-reset" type="button" class="qt-reset">REWIND CURVE</button>
          </aside>
        </main>
        <footer class="qt-footer"><div class="readout" data-status="idle"></div></footer>
        ${helpers.cheatPanelTemplate()}
      </section>`;

    model = {
      state,
      helpers,
      interaction,
      curve: initial.slice(),
      initialCurve: initial.slice(),
      events: [],
      running: false,
      terminal: false,
      tick: 0,
      states: [],
      lastState: null,
      lastFidelity: null,
      playbacks: 0,
      firstCompleteCurve: null,
      revisedAfterPlayback: false,
      dragIndex: null,
      timer: null,
    };
    window.quietTransferModel = model;
    document.querySelectorAll("[data-knot][data-delta]").forEach((button) => {
      button.addEventListener("click", () => {
        const index = Number(button.dataset.knot);
        const step = Number(state.curve.nudge_step);
        const position = model.curve[index] / step;
        const grid = Number(button.dataset.delta) > 0
          ? Math.floor(position + 1e-7) + 1 : Math.ceil(position - 1e-7) - 1;
        setCurve(index, grid * step, "nudge_buttons");
      });
    });
    document.getElementById("qt-run")?.addEventListener("click", runTransfer);
    document.getElementById("qt-certify")?.addEventListener("click", certify);
    document.getElementById("qt-reset")?.addEventListener("click", resetCurve);
    bindCurvePointer();
    helpers.installCheatPanel();
    draw();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[ID] = {rootSelector: ".quiet-transfer-shell", render};
})();
