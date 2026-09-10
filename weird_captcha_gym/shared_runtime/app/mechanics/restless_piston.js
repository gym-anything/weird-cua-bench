(() => {
  "use strict";

  const MODE_ACTIONS = {
    nothing: new Set(["pump", "heat", "wall"]),
    volume: new Set(["pump", "heat"]),
    temperature: new Set(["pump", "wall"]),
    pressure_v: new Set(["pump", "heat"]),
    pressure_t: new Set(["pump", "wall"]),
  };
  const MODE_LABELS = {
    nothing: "Nothing",
    volume: "Volume (V)",
    temperature: "Temperature (T)",
    pressure_v: "Pressure with V varying",
    pressure_t: "Pressure with T varying",
  };
  const copy = (value) => JSON.parse(JSON.stringify(value));
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const round = (value, places = 3) => Math.round(Number(value) * 10 ** places) / 10 ** places;
  const esc = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const pressure = (model) => Number(model.particles) * Number(model.temperature) / (Number(model.volume) * 1000);
  const event = (model, type, details = {}) => {
    const item = {seq: model.events.length + 1, type, ...details};
    model.events.push(item);
    return item;
  };

  function rootMarkup(state, interaction) {
    const options = (state.mode_options || []).map((option) => `<option value="${esc(option.id)}">${esc(option.label)}</option>`).join("");
    const goal = state.goal || {};
    const t = goal.tolerances || {};
    const direct = interaction === "full";
    return `
      <section class="rp-root" data-interaction="${esc(interaction)}" data-challenge-id="${esc(state.challenge_id)}">
        <header class="rp-header">
          <div><span>THERMODYNAMIC INCIDENT DESK</span><h1>THE RESTLESS PISTON</h1></div>
          <p>${esc(state.prompt || "Reach the operating conditions while the particles keep moving.")}</p>
        </header>
        <main class="rp-main">
          <section class="rp-bench">
            <canvas id="rp-canvas" width="900" height="500" aria-label="transparent gas chamber with moving particles"></canvas>
            <div class="rp-gauges">
              <div class="rp-gauge rp-gauge-pressure"><span>PRESSURE · NOISY</span><b id="rp-pressure">--</b><i><em id="rp-pressure-bar"></em></i></div>
              <div class="rp-gauge"><span>TEMPERATURE</span><b id="rp-temperature">--</b><i><em id="rp-temperature-bar"></em></i></div>
              <div class="rp-gauge"><span>VOLUME</span><b id="rp-volume">--</b><i><em id="rp-volume-bar"></em></i></div>
            </div>
          </section>
          <aside class="rp-console">
            <h2>OPERATING CARD</h2>
            <div class="rp-target"><span>REQUIRED CONSTRAINT</span><strong id="rp-required-mode">${esc(goal.required_mode_label || "Choose a mode")}</strong></div>
            <div class="rp-target-grid">
              <div><span>P</span><b>${Number(goal.pressure).toFixed(2)}</b><small>±${Number(t.pressure || 0).toFixed(2)}</small></div>
              <div><span>T</span><b>${Number(goal.temperature).toFixed(1)} K</b><small>±${Number(t.temperature || 0).toFixed(1)}</small></div>
              <div><span>V</span><b>${Number(goal.volume).toFixed(3)}</b><small>±${Number(t.volume || 0).toFixed(3)}</small></div>
            </div>
            <h2>HOLD CONSTANT</h2>
            <select id="rp-mode" aria-label="Hold Constant"><option value="" selected disabled>SELECT A SETTING</option>${options}</select>
            <div class="rp-actions ${direct ? "is-direct" : ""}">
              ${direct ? `<p class="rp-direct-note">DRAG THE PUMP PLUNGER, HEAT COIL, OR PISTON WALL ON THE BENCH.</p>` : `
                <h2>PROXY CONTROLS</h2>
                <div class="rp-control-group"><span>PUMP PARTICLES</span><div><button data-action="pump" data-dir="-1">− PUMP</button><button data-action="pump" data-dir="1">+ PUMP</button></div></div>
                <div class="rp-control-group"><span>HEAT CONTROL</span><div><button data-action="heat" data-dir="-1">− COOL</button><button data-action="heat" data-dir="1">+ HEAT</button></div></div>
                <div class="rp-control-group"><span>PISTON WALL</span><div><button data-action="wall" data-dir="-1">IN</button><button data-action="wall" data-dir="1">OUT</button></div></div>
              `}
            </div>
            <button id="rp-certify" class="rp-primary">CERTIFY SETTLED STATE</button>
            <button id="rp-abandon" class="rp-danger">VENT CHAMBER / FRESH TRIAL</button>
          </aside>
        </main>
        <footer class="rp-footer"><span>${esc(String(state.challenge_id || "").toUpperCase())} · VISIBLE PHYSICAL MODEL</span><div class="rp-readout readout" data-status="idle">READY</div></footer>
      </section>`;
  }

  function setReadout(model, message, status = "idle") {
    if (model.terminal && message !== "PASS") return;
    model.helpers.setReadout(message, status);
  }

  function canHold(model, mode) {
    const physics = model.state.physics;
    if (mode === "temperature" && model.particles <= 0) return {ok: false, reason: "TEMPERATURE CANNOT BE HELD WITH AN EMPTY CHAMBER"};
    const reference = Number(model.state.reference_pressure || model.state.initial.pressure);
    if (mode === "pressure_v") {
      const targetVolume = pressure(model) > 0
        ? model.particles * model.temperature / (reference * 1000)
        : Infinity;
      if (targetVolume < Number(physics.min_volume) || targetVolume > Number(physics.max_volume)) return {ok: false, reason: "PRESSURE HOLD WOULD DRIVE THE PISTON OUT OF RANGE"};
    }
    if (mode === "pressure_t") {
      const targetTemperature = model.particles > 0
        ? reference * 1000 * model.volume / model.particles
        : Infinity;
      if (targetTemperature < Number(physics.min_temperature) || targetTemperature > Number(physics.max_temperature)) return {ok: false, reason: "PRESSURE HOLD WOULD DRIVE TEMPERATURE OUT OF RANGE"};
    }
    return {ok: true, reason: ""};
  }

  function macroAfter(model, action, direction) {
    const next = {particles: model.particles, temperature: model.temperature, volume: model.volume};
    const sign = Number(direction) > 0 ? 1 : -1;
    const physics = model.state.physics;
    if (!MODE_ACTIONS[model.mode]?.has(action)) return null;
    if (action === "pump") next.particles += sign * Number(physics.pump_delta);
    if (action === "heat") next.temperature += sign * Number(physics.heat_delta);
    if (action === "wall") next.volume += sign * Number(physics.wall_delta);
    if (next.particles < 6 || next.particles > 92) return null;
    if (next.temperature < Number(physics.min_temperature) || next.temperature > Number(physics.max_temperature)) return null;
    if (next.volume < Number(physics.min_volume) || next.volume > Number(physics.max_volume)) return null;
    const reference = Number(model.state.reference_pressure || model.state.initial.pressure);
    if (model.mode === "pressure_v" && (action === "pump" || action === "heat")) next.volume = next.particles * next.temperature / (reference * 1000);
    if (model.mode === "pressure_t" && (action === "pump" || action === "wall")) next.temperature = reference * 1000 * next.volume / next.particles;
    if (next.volume < Number(physics.min_volume) || next.volume > Number(physics.max_volume)) return null;
    if (next.temperature < Number(physics.min_temperature) || next.temperature > Number(physics.max_temperature)) return null;
    return next;
  }

  function withinGoal(model) {
    const goal = model.state.goal, t = goal.tolerances;
    return Math.abs(pressure(model) - Number(goal.pressure)) <= Number(t.pressure)
      && Math.abs(model.temperature - Number(goal.temperature)) <= Number(t.temperature)
      && Math.abs(model.volume - Number(goal.volume)) <= Number(t.volume);
  }

  function logicalPoint(canvas, pointerEvent) {
    const box = canvas.getBoundingClientRect();
    const scale = Math.min(box.width / canvas.width, box.height / canvas.height);
    const left = box.left + (box.width - canvas.width * scale) / 2;
    const top = box.top + (box.height - canvas.height * scale) / 2;
    return {x: (pointerEvent.clientX - left) / scale, y: (pointerEvent.clientY - top) / scale};
  }

  function renderCanvas(model) {
    const canvas = document.getElementById("rp-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const state = model.state, physics = state.physics;
    const left = 76, top = 105, height = 292, maxWidth = 620;
    const wallX = left + model.volume / Number(physics.max_volume) * maxWidth;
    const right = left + maxWidth;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const bg = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
    bg.addColorStop(0, "#0e3440"); bg.addColorStop(.55, "#081a25"); bg.addColorStop(1, "#201227");
    ctx.fillStyle = bg; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#2a6670"; ctx.lineWidth = 1;
    for (let x = 20; x < canvas.width; x += 32) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke(); }
    for (let y = 18; y < canvas.height; y += 32) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke(); }
    ctx.fillStyle = "#071016cc"; ctx.fillRect(left, top, maxWidth, height);
    ctx.strokeStyle = "#8ad8d2"; ctx.lineWidth = 4; ctx.strokeRect(left, top, maxWidth, height);
    const gasWidth = Math.max(10, wallX - left);
    ctx.fillStyle = "#58ced522"; ctx.fillRect(left + 4, top + 4, gasWidth - 8, height - 8);
    ctx.strokeStyle = "#ebc765"; ctx.lineWidth = 9; ctx.beginPath(); ctx.moveTo(wallX, top - 20); ctx.lineTo(wallX, top + height + 20); ctx.stroke();
    ctx.strokeStyle = "#f7e6bd"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(wallX, top - 32); ctx.lineTo(wallX, top + height + 32); ctx.stroke();
    ctx.fillStyle = "#d3ff88"; ctx.font = "900 11px Courier New"; ctx.fillText("MOVABLE WALL", clamp(wallX - 42, left, right - 90), top + height + 54);
    const limitY = top + height + 72;
    ctx.strokeStyle = "#75a7a8"; ctx.lineWidth = 1; ctx.setLineDash([5, 6]); ctx.beginPath(); ctx.moveTo(left, limitY); ctx.lineTo(right, limitY); ctx.stroke(); ctx.setLineDash([]);
    const selectedModeLabel = MODE_LABELS[model.mode] || "SELECT HOLD CONSTANT";
    ctx.fillStyle = "#a1c5c2"; ctx.font = "700 10px Courier New"; ctx.fillText(`VOLUME ${model.volume.toFixed(3)} · ${selectedModeLabel}`, left, limitY + 19);
    model.particlesCloud.forEach((particle) => {
      const margin = Number(particle.radius) + 5;
      const x = left + margin + clamp(Number(particle.x), 0, 1) * (gasWidth - 2 * margin);
      const y = top + margin + clamp(Number(particle.y), 0, 1) * (height - 2 * margin);
      ctx.fillStyle = particle.color; ctx.shadowBlur = 8; ctx.shadowColor = particle.color; ctx.beginPath(); ctx.arc(x, y, Number(particle.radius), 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0;
    });
    ctx.fillStyle = "#f1d48d"; ctx.font = "900 13px Courier New"; ctx.fillText(`${model.particles} PARTICLES`, left + 16, top + 27);
    ctx.fillStyle = "#5b3035"; ctx.fillRect(740, 118, 96, 184); ctx.strokeStyle = "#ed8f67"; ctx.lineWidth = 3; ctx.strokeRect(740, 118, 96, 184);
    ctx.fillStyle = "#ffc26e"; ctx.fillRect(782, 150, 12, 112); ctx.fillStyle = "#fff0bd"; ctx.fillRect(766, 141, 44, 14);
    ctx.fillStyle = "#f4cf78"; ctx.font = "900 10px Courier New"; ctx.fillText("PUMP", 765, 286); ctx.fillText("DRAG PLUNGER", 744, 318);
    ctx.strokeStyle = "#e77979"; ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(788, 391, 43, 0, Math.PI * 2); ctx.stroke(); ctx.strokeStyle = "#f8d18a"; ctx.lineWidth = 7; ctx.beginPath(); ctx.moveTo(788, 391); ctx.lineTo(788 + Math.cos(model.heatAngle) * 29, 391 + Math.sin(model.heatAngle) * 29); ctx.stroke(); ctx.fillStyle = "#f2d4a4"; ctx.font = "900 10px Courier New"; ctx.fillText("HEAT", 773, 448); ctx.fillText("DRAG", 772, 462);
    const displayedPressure = pressure(model) * (1 + Number(physics.gauge_noise_ratio) * (.56 * Math.sin(model.tick * .73) + .31 * Math.cos(model.tick * 1.11)));
    const gaugeAngle = clamp((displayedPressure / Math.max(.1, Number(state.goal.pressure) * 1.7)) * Math.PI * 1.42 - Math.PI * .71, -Math.PI * .71, Math.PI * .71);
    ctx.fillStyle = "#111b20"; ctx.beginPath(); ctx.arc(650, 55, 39, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#f28a79"; ctx.lineWidth = 3; ctx.stroke(); ctx.strokeStyle = "#fbe7b0"; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(650, 55); ctx.lineTo(650 + Math.cos(gaugeAngle) * 29, 55 + Math.sin(gaugeAngle) * 29); ctx.stroke(); ctx.fillStyle = "#f1dba8"; ctx.font = "900 9px Courier New"; ctx.fillText("PRESSURE", 621, 104);
  }

  function updateReadouts(model) {
    const state = model.state, physics = state.physics;
    const noisy = pressure(model) * (1 + Number(physics.gauge_noise_ratio) * (.56 * Math.sin(model.tick * .73) + .31 * Math.cos(model.tick * 1.11)));
    const pressureNode = document.getElementById("rp-pressure");
    if (!pressureNode) return;
    pressureNode.textContent = `${noisy.toFixed(2)} kPa`;
    document.getElementById("rp-temperature").textContent = `${model.temperature.toFixed(1)} K`;
    document.getElementById("rp-volume").textContent = model.volume.toFixed(3);
    document.getElementById("rp-pressure-bar").style.width = `${clamp(noisy / Math.max(.1, Number(state.goal.pressure) * 1.7) * 100, 2, 100)}%`;
    document.getElementById("rp-temperature-bar").style.width = `${clamp((model.temperature - Number(physics.min_temperature)) / (Number(physics.max_temperature) - Number(physics.min_temperature)) * 100, 2, 100)}%`;
    document.getElementById("rp-volume-bar").style.width = `${clamp((model.volume - Number(physics.min_volume)) / (Number(physics.max_volume) - Number(physics.min_volume)) * 100, 2, 100)}%`;
    document.querySelectorAll("[data-action]").forEach((button) => { button.disabled = model.expired || !MODE_ACTIONS[model.mode]?.has(button.dataset.action); });
  }

  function draw(model) {
    renderCanvas(model); updateReadouts(model);
  }

  async function submit(model, payload, passTitle, passNote) {
    if (model.submitting || model.terminal) return;
    model.submitting = true;
    setReadout(model, "INDEPENDENT REPLAY IN PROGRESS…", "pending");
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const result = await response.json();
      if (result.passed === true) {
        model.terminal = true;
        document.querySelector(".rp-root")?.insertAdjacentHTML("beforeend", `<div class="rp-verdict is-pass"><strong>${esc(passTitle || "PASS")}</strong><span>${esc(passNote || "PHYSICAL CHAMBER TRANSCRIPT ACCEPTED")}</span></div>`);
        setReadout(model, "PASS", "passed");
      } else if (result.passed === false && result.state) {
        await model.helpers.render(result.state);
        document.querySelector(".rp-root")?.insertAdjacentHTML("beforeend", `<div class="rp-verdict is-fresh"><strong>FAIL · FRESH CHAMBER</strong><span>${esc(result.feedback || "THE FAILED WORLD WAS REPLACED")}</span></div>`);
        setTimeout(() => document.querySelector(".rp-verdict.is-fresh")?.remove(), 1900);
        document.querySelector(".rp-readout")?.setAttribute("data-status", "error");
      } else {
        model.events.pop(); // The ungraded terminal attempt may be retried.
        model.submitting = false;
        setReadout(model, `FAIL · ${result.feedback || result.error || "NO AUTHORITATIVE GRADE"}`, "error");
      }
    } catch (error) {
      model.events.pop();
      model.submitting = false;
      setReadout(model, `FAIL · VERIFIER OFFLINE · ${error.message}`, "error");
    }
  }

  function render(state, helpers) {
    if (window.restlessPistonModel?.interval) clearInterval(window.restlessPistonModel.interval);
    document.body.dataset.mechanic = "restless-piston";
    const interaction = state.control_condition?.interaction || state.interaction_mode || "simplified";
    const model = {
      state, helpers, interaction, mode: null, events: [], tick: 0, stable: 0,
      particles: Number(state.initial.particles), temperature: Number(state.initial.temperature), volume: Number(state.initial.volume),
      particlesCloud: copy(state.particles || []), heatAngle: -Math.PI / 2, terminal: false, submitting: false, expired: false, interval: null, drag: null,
    };
    window.restlessPistonModel = model;
    helpers.app.innerHTML = rootMarkup(state, interaction);
    const canvas = document.getElementById("rp-canvas");
    const allowedModes = new Set((state.mode_options || []).map((option) => String(option.id)));
    const allowed = () => MODE_ACTIONS[model.mode] || new Set();
    const action = (name, direction, source) => {
      if (model.terminal || model.submitting || model.expired) return;
      if (!model.mode || !allowed().has(name)) { setReadout(model, "CONTROL UNAVAILABLE", "error"); return; }
      const next = macroAfter(model, name, direction);
      if (!next) { setReadout(model, "PHYSICAL LIMIT · CHOOSE A RECOVERABLE CONTROL", "error"); return; }
      const before = {particles: model.particles, temperature: model.temperature, volume: model.volume};
      model.particles = next.particles; model.temperature = next.temperature; model.volume = next.volume; model.stable = 0;
      while (model.particlesCloud.length < model.particles) {
        const index = model.particlesCloud.length;
        const template = state.particles[index % state.particles.length];
        model.particlesCloud.push({...copy(template), x: .95, y: .1 + ((index * .173) % .8)});
      }
      model.particlesCloud.length = model.particles;
      if (name === "heat") model.heatAngle += direction * .2;
      event(model, "action", {tick: model.tick, action: name, direction: Number(direction) > 0 ? 1 : -1, input_source: source, before, after: {particles: model.particles, temperature: model.temperature, volume: model.volume}});
      setReadout(model, `${name.toUpperCase()} REGISTERED · WATCH THE GAUGES`, "idle"); draw(model);
    };
    const selectMode = (mode) => {
      if (model.terminal || model.submitting || model.expired) return;
      if (!allowedModes.has(mode)) {
        event(model, "mode_error", {tick: model.tick, mode, reason: "mode unavailable", input_source: "mode_selector"});
        document.getElementById("rp-mode").value = "";
        setReadout(model, "MODE UNAVAILABLE", "error");
        return;
      }
      const check = canHold(model, mode);
      if (!check.ok) {
        event(model, "mode_error", {tick: model.tick, mode, reason: check.reason, input_source: "mode_selector"});
        document.getElementById("rp-mode").value = model.mode;
        setReadout(model, check.reason, "error");
        return;
      }
      model.mode = mode;
      model.stable = 0;
      event(model, "mode_select", {tick: model.tick, mode, input_source: "mode_selector"});
      setReadout(model, `HOLD CONSTANT · ${MODE_LABELS[mode].toUpperCase()}`, "idle"); draw(model);
    };
    document.getElementById("rp-mode").addEventListener("change", (eventObject) => selectMode(eventObject.target.value));
    document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => action(button.dataset.action, Number(button.dataset.dir), "proxy_control")));
    document.getElementById("rp-certify").addEventListener("click", async () => {
      if (model.terminal || model.submitting || model.expired) return;
      const accepted = model.events.some(item => item.type === "action") && model.mode === String(state.goal.required_mode) && withinGoal(model) && model.stable >= Number(state.goal.settle_ticks);
      if (!accepted) { setReadout(model, "CERTIFICATION REFUSED · REACH THE TARGET AND WAIT FOR A STEADY READING", "error"); return; }
      event(model, "certify", {tick: model.tick, mode: model.mode, stable_ticks: model.stable, accepted, state: {pressure: round(pressure(model), 6), temperature: round(model.temperature, 6), volume: round(model.volume, 6)}});
      await submit(model, {mechanic_id: state.mechanic_id, task_id: state.task_id, challenge_id: state.challenge_id, interaction_mode: interaction, events: model.events, completed: true}, "CHAMBER CERTIFIED", `${esc(state.goal.required_mode_label).toUpperCase()} · SETTLED PRESSURE · REPLAY ACCEPTED`);
    });
    document.getElementById("rp-abandon").addEventListener("click", async () => {
      if (model.terminal || model.submitting) return;
      event(model, "abandon", {tick: model.tick, input_source: "fresh_trial_button"});
      await submit(model, {mechanic_id: state.mechanic_id, task_id: state.task_id, challenge_id: state.challenge_id, interaction_mode: interaction, events: model.events, completed: false}, "", "");
    });
    if (interaction === "full") {
      const pointAt = (eventObject) => logicalPoint(canvas, eventObject);
      const wallX = () => { const physics = state.physics; return 76 + model.volume / Number(physics.max_volume) * 620; };
      canvas.addEventListener("pointerdown", (pointerEvent) => {
        if (model.terminal || model.submitting) return;
        const point = pointAt(pointerEvent);
        if (Math.abs(point.x - wallX()) < 30 && point.y > 65 && point.y < 430) model.drag = {kind: "wall", pointerId: pointerEvent.pointerId, last: point.x, accumulator: 0};
        else if (point.x > 720 && point.x < 825 && point.y > 110 && point.y < 325) model.drag = {kind: "pump", pointerId: pointerEvent.pointerId, last: point.y, accumulator: 0};
        else if (point.x > 730 && point.x < 845 && point.y > 345 && point.y < 465) model.drag = {kind: "heat", pointerId: pointerEvent.pointerId, last: point.x, accumulator: 0};
        if (model.drag) { canvas.setPointerCapture(pointerEvent.pointerId); pointerEvent.preventDefault(); }
      });
      canvas.addEventListener("pointermove", (pointerEvent) => {
        const drag = model.drag; if (!drag || drag.pointerId !== pointerEvent.pointerId) return;
        const point = pointAt(pointerEvent);
        if (drag.kind === "wall") drag.accumulator += point.x - drag.last, drag.last = point.x;
        if (drag.kind === "heat") drag.accumulator += point.x - drag.last, drag.last = point.x;
        if (drag.kind === "pump") drag.accumulator += drag.last - point.y, drag.last = point.y;
        while (Math.abs(drag.accumulator) >= 24) {
          const sign = Math.sign(drag.accumulator); action(drag.kind, sign, "direct_manipulation"); drag.accumulator -= sign * 24;
        }
        pointerEvent.preventDefault(); draw(model);
      });
      const endDrag = (pointerEvent) => { if (!model.drag || model.drag.pointerId !== pointerEvent.pointerId) return; model.drag = null; try { canvas.releasePointerCapture(pointerEvent.pointerId); } catch (_) {} };
      canvas.addEventListener("pointerup", endDrag); canvas.addEventListener("pointercancel", endDrag);
    }
    const step = () => {
      if (model.terminal || model.submitting) return;
      model.tick += 1;
      const physics = state.physics, maxX = 0.985;
      model.particlesCloud.forEach((particle) => {
        particle.x += Number(particle.vx); particle.y += Number(particle.vy);
        if (particle.y < .025 || particle.y > .975) { particle.y = clamp(particle.y, .025, .975); particle.vy *= -1; }
        if (particle.x < .015 || particle.x > maxX) { particle.x = clamp(particle.x, .015, maxX); particle.vx *= -1; }
      });
      model.stable = withinGoal(model) ? model.stable + 1 : 0;
      if (model.tick >= Number(physics.max_ticks)) {
        clearInterval(model.interval); model.expired = true;
        document.getElementById("rp-mode").disabled = true;
        document.getElementById("rp-certify").disabled = true;
        setReadout(model, "PLAY WINDOW EXPIRED · VENT AND START FRESH", "error");
      }
      draw(model);
    };
    model.interval = setInterval(step, Number(state.physics.tick_ms));
    draw(model);
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.restless_piston = {rootSelector: ".rp-root", render};
})();
