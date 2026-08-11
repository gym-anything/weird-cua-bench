(() => {
  "use strict";

  let model = null;
  const esc = value => String(value == null ? "" : value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const wrap = value => ((value % 360) + 360) % 360;
  const delta = (a, b) => ((a - b + 180) % 360 + 360) % 360 - 180;
  const color = {cyan: "rgba(0,167,190,.72)", magenta: "rgba(218,24,111,.65)", amber: "rgba(232,163,0,.7)", violet: "rgba(125,84,224,.61)", lime: "rgba(145,195,45,.58)"};
  const plateCountName = count => ({1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE"}[count] || String(count));

  function record(kind, details = {}) { const event = {sequence: model.events.length + 1, kind, ...details}; model.events.push(event); return event; }
  function updateWheel(id) { const wheel = document.querySelector(`.registration-wheel[data-plate-id="${CSS.escape(id)}"]`); if (wheel) wheel.style.setProperty("--wheel-angle", `${model.angles[id]}deg`); }

  function draw() {
    const canvas = document.querySelector(".registration-canvas"); if (!canvas) return;
    const ctx = canvas.getContext("2d"), press = model.state.press, token = [...press.token];
    const fontSize = token.length > 5 ? 62 : 76, letterSpacing = token.length > 5 ? 80 : 98;
    const firstX = canvas.width / 2 - (token.length - 1) * letterSpacing / 2 - 42;
    ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.fillStyle = "#eee8d8"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "rgba(34,42,43,.09)";
    for (let x = 0; x < canvas.width; x += 24) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x - 60, canvas.height); ctx.stroke(); }
    ctx.globalCompositeOperation = "multiply";
    press.plates.forEach((plate, plateIndex) => {
      const error = delta(model.angles[plate.id], plate.target), strength = Math.min(1, Math.abs(error) / 80), radians = error * Math.PI / 180;
      ctx.fillStyle = color[plate.color] || color.amber; ctx.font = `800 ${fontSize}px Georgia,serif`; ctx.textBaseline = "middle";
      token.forEach((char, index) => {
        const baseX = firstX + index * letterSpacing, baseY = 145;
        const y = baseY + Math.sin(radians * plate.harmonic + index * .76) * plate.warp * strength;
        const x = baseX + Math.cos(radians * (plate.harmonic + 1) + index * .44) * plate.warp * .65 * strength;
        ctx.save(); ctx.translate(x, y); ctx.rotate(radians * .13 + Math.sin(index + plateIndex) * strength * .08); ctx.fillText(char, 0, 0); ctx.restore();
      });
    });
    ctx.globalCompositeOperation = "source-over"; ctx.strokeStyle = "rgba(30,36,36,.35)"; ctx.lineWidth = 2; ctx.strokeRect(18, 18, canvas.width - 36, canvas.height - 36);
  }

  function rotatePlate(id, degrees, inputSource) {
    if (model.locked.has(id)) return;
    model.angles[id] = wrap(model.angles[id] + degrees); updateWheel(id); draw();
    const details = {plate_id: id, delta: Number(degrees.toFixed(4))}; if (model.state.control_condition) details.input_source = inputSource; record("wheel_drag", details);
  }

  function installWheel(node) {
    const id = node.dataset.plateId;
    node.addEventListener("pointerdown", event => {
      if (event.button !== 0 || model.locked.has(id) || node.dataset.dragging === "true") return;
      event.preventDefault(); node.setPointerCapture(event.pointerId);
      const pointerId = event.pointerId, initial = model.angles[id]; let last = event.clientX, total = 0;
      node.dataset.dragging = "true";
      const move = moveEvent => {
        if (moveEvent.pointerId !== pointerId) return;
        moveEvent.preventDefault();
        const dx = moveEvent.clientX - last;
        last = moveEvent.clientX;
        const degrees = dx * Number(model.state.press.degrees_per_pixel);
        total += degrees; model.angles[id] = wrap(model.angles[id] + degrees); updateWheel(id); draw();
      };
      const finish = (finishEvent, cancelled = false) => {
        if (finishEvent.pointerId !== pointerId) return;
        node.removeEventListener("pointermove", move); node.removeEventListener("pointerup", up); node.removeEventListener("pointercancel", cancel); node.removeEventListener("lostpointercapture", cancel);
        node.dataset.dragging = "false";
        if (cancelled) { model.angles[id] = initial; updateWheel(id); draw(); return; }
        try { node.releasePointerCapture(pointerId); } catch (_) {}
        const details = {plate_id: id, delta: Number(total.toFixed(4))}; if (model.state.control_condition) details.input_source = "wheel_drag"; record("wheel_drag", details);
      };
      const up = upEvent => finish(upEvent);
      const cancel = cancelEvent => finish(cancelEvent, true);
      node.addEventListener("pointermove", move); node.addEventListener("pointerup", up); node.addEventListener("pointercancel", cancel); node.addEventListener("lostpointercapture", cancel);
    });
  }

  function toggleLock(button) {
    const id = button.dataset.plateId;
    if (model.locked.has(id)) { model.locked.delete(id); button.dataset.locked = "false"; record("lock", {plate_id: id, locked: false}); }
    else { model.locked.add(id); button.dataset.locked = "true"; record("lock", {plate_id: id, locked: true}); }
    const wheel = document.querySelector(`.registration-wheel[data-plate-id="${CSS.escape(id)}"]`); if (wheel) wheel.dataset.locked = String(model.locked.has(id));
    document.querySelector(".registration-press").disabled = model.locked.size !== model.state.press.plates.length;
  }

  async function submit() {
    if (model.submitting || model.locked.size !== model.state.press.plates.length) return;
    model.submitting = true; record("press", {}); document.querySelector(".registration-machine").classList.add("is-pressing");
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({mechanic_id: model.state.mechanic_id, task_id: model.state.task_id, challenge_id: model.state.challenge_id, events: model.events})});
      const outcome = await response.json();
      if (outcome.passed === true) { model.helpers.setReadout("PASS", "passed"); document.querySelector(".registration-captcha").classList.add("is-passed"); }
      else { model.helpers.setReadout("FAIL", "error"); setTimeout(() => outcome.state && model.helpers.render(outcome.state), 850); }
    } catch (_error) { model.submitting = false; model.helpers.setReadout("FAIL", "error"); }
  }

  function wheelMarkup(plate, index, interaction, step, coarseStep) {
    const wheel = interaction === "simplified"
      ? `<div class="registration-wheel" role="img" aria-label="Plate ${index + 1} angle" data-plate-id="${esc(plate.id)}" data-locked="false" style="--wheel-angle:${plate.initial}deg"><i></i><b>${index + 1}</b></div>`
      : `<button type="button" class="registration-wheel" data-plate-id="${esc(plate.id)}" data-locked="false" style="--wheel-angle:${plate.initial}deg"><i></i><b>${index + 1}</b></button>`;
    const proxySteps = [...new Set([Number(step), Number(coarseStep)].filter(value => value > 0))].sort((first, second) => second - first);
    const proxy = interaction === "simplified"
      ? `<div class="registration-proxy">${proxySteps.flatMap(value => [-value, value]).map(value => `<button type="button" class="plate-step" data-plate-id="${esc(plate.id)}" data-delta="${value}" aria-label="Turn plate ${index + 1} ${value < 0 ? "backward" : "forward"} ${Math.abs(value)} degrees">${value < 0 ? "−" : "+"}${Math.abs(value)}°</button>`).join("")}</div>` : "";
    return `<div class="wheel-station station-${esc(plate.color)}">${wheel}${proxy}<button type="button" class="plate-lock" data-plate-id="${esc(plate.id)}" data-locked="false" aria-label="Toggle plate ${index + 1} lock">⌁</button></div>`;
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "wonky-registration-v2";
    const interaction = state.control_condition?.interaction || "full", step = Number(state.control_condition?.difficulty_parameters?.proxy_step_degrees || 5), coarseStep = Number(state.control_condition?.difficulty_parameters?.proxy_coarse_step_degrees || 0);
    model = {state, helpers, events: [], angles: Object.fromEntries(state.press.plates.map(plate => [plate.id, Number(plate.initial)])), locked: new Set(), submitting: false};
    helpers.app.innerHTML = `<section class="registration-captcha" data-interaction="${esc(interaction)}"><header><span>ANAMORPHIC TYPE FOUNDRY / ${plateCountName(state.press.plates.length)} PLATES</span><h1>${esc(state.prompt)}</h1></header><section class="registration-machine"><div class="press-arm"><i></i><b></b></div><canvas class="registration-canvas" width="700" height="290"></canvas><div class="registration-wheels" data-count="${state.press.plates.length}">${state.press.plates.map((plate, index) => wheelMarkup(plate, index, interaction, step, coarseStep)).join("")}</div></section><footer><div class="readout" data-status="idle"></div><span>REGISTER · LOCK · PRESS</span><button class="registration-press" type="button" disabled>PRESS</button></footer></section>`;
    if (interaction === "full") document.querySelectorAll(".registration-wheel").forEach(installWheel);
    document.querySelectorAll(".plate-step").forEach(button => button.addEventListener("click", () => rotatePlate(button.dataset.plateId, Number(button.dataset.delta), "proxy_step")));
    document.querySelectorAll(".plate-lock").forEach(button => button.addEventListener("click", () => toggleLock(button)));
    document.querySelector(".registration-press").addEventListener("click", submit); draw();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.wonky_text_hostile_rendering = {render, rootSelector: ".registration-captcha"};
})();
