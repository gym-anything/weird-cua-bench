(() => {
  "use strict";

  let model = null;
  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");

  function record(kind, details = {}) {
    const event = {sequence: model.events.length + 1, kind, ...details};
    model.events.push(event);
    return event;
  }

  function aligned() {
    const tolerance = Number(model.state.form.alignment_tolerance);
    return model.state.form.layers.every((layer) => {
      const offset = model.offsets[layer.id];
      return Math.hypot(offset.x - layer.target.x, offset.y - layer.target.y) <= tolerance;
    });
  }

  function updateLayers() {
    model.state.form.layers.forEach((layer) => {
      const node = document.querySelector(`[data-sheet-id="${CSS.escape(layer.id)}"]`);
      const offset = model.offsets[layer.id];
      node.style.setProperty("--sheet-x", `${offset.x}px`);
      node.style.setProperty("--sheet-y", `${offset.y}px`);
    });
    const open = aligned();
    document.querySelector(".carbon-stage").dataset.open = String(open);
    document.querySelector(".signature-surface").dataset.enabled = String(open && !model.stroke);
    document.querySelector(".carbon-register").textContent = open ? "APERTURE REGISTERED" : "REGISTER FOUR WINDOWS";
  }

  function installSheet(layer) {
    const tab = document.querySelector(`.sheet-tab[data-control-id="${CSS.escape(layer.id)}"]`);
    tab.addEventListener("pointerdown", (event) => {
      if (model.stroke || model.submitting) return;
      event.preventDefault();
      tab.setPointerCapture(event.pointerId);
      const start = [event.clientX, event.clientY];
      const origin = {...model.offsets[layer.id]};
      const samples = [];
      tab.dataset.dragging = "true";
      const move = (moveEvent) => {
        const offset = {
          x: Math.max(-170, Math.min(170, origin.x + moveEvent.clientX - start[0])),
          y: Math.max(-110, Math.min(110, origin.y + moveEvent.clientY - start[1])),
        };
        model.offsets[layer.id] = offset;
        samples.push([Math.round(offset.x), Math.round(offset.y)]);
        updateLayers();
      };
      const up = () => {
        tab.removeEventListener("pointermove", move);
        tab.removeEventListener("pointerup", up);
        tab.removeEventListener("pointercancel", up);
        tab.dataset.dragging = "false";
        if (samples.length) {
          record("sheet_drag", {
            sheet_id: layer.id,
            start: [origin.x, origin.y],
            samples: samples.slice(-180),
            end: [Math.round(model.offsets[layer.id].x), Math.round(model.offsets[layer.id].y)],
          });
        }
      };
      tab.addEventListener("pointermove", move);
      tab.addEventListener("pointerup", up);
      tab.addEventListener("pointercancel", up);
    });
  }

  function clearStroke() {
    if (!model.stroke || model.submitting) return;
    model.stroke = null;
    const canvas = document.querySelector(".signature-surface");
    canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    record("signature_clear");
    document.querySelector(".carbon-submit").disabled = true;
    document.querySelector(".carbon-clear").disabled = true;
    updateLayers();
  }

  function installSignature() {
    const canvas = document.querySelector(".signature-surface");
    const context = canvas.getContext("2d");
    const stage = document.querySelector(".carbon-stage");
    canvas.addEventListener("pointerdown", (event) => {
      if (!aligned() || model.stroke || model.submitting) return;
      event.preventDefault();
      canvas.setPointerCapture(event.pointerId);
      const stageRect = stage.getBoundingClientRect();
      const points = [];
      const point = (moveEvent) => [
        Math.round((moveEvent.clientX - stageRect.left) / stageRect.width * model.state.form.stage.width),
        Math.round((moveEvent.clientY - stageRect.top) / stageRect.height * model.state.form.stage.height),
      ];
      const first = point(event);
      points.push(first);
      context.beginPath();
      context.moveTo(first[0], first[1]);
      canvas.dataset.drawing = "true";
      const move = (moveEvent) => {
        const next = point(moveEvent);
        const previous = points[points.length - 1];
        if (next[0] === previous[0] && next[1] === previous[1]) return;
        points.push(next);
        context.lineTo(next[0], next[1]);
        context.stroke();
      };
      const up = () => {
        canvas.removeEventListener("pointermove", move);
        canvas.removeEventListener("pointerup", up);
        canvas.removeEventListener("pointercancel", up);
        canvas.dataset.drawing = "false";
        model.stroke = points;
        record("signature", {points});
        document.querySelector(".carbon-submit").disabled = points.length < 2;
        document.querySelector(".carbon-clear").disabled = false;
        updateLayers();
      };
      canvas.addEventListener("pointermove", move);
      canvas.addEventListener("pointerup", up);
      canvas.addEventListener("pointercancel", up);
    });
  }

  async function submit() {
    if (model.submitting || !model.stroke) return;
    model.submitting = true;
    record("certify");
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({
          mechanic_id: model.state.mechanic_id,
          challenge_id: model.state.challenge_id,
          events: model.events,
        }),
      });
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.helpers.setReadout("PASS", "passed");
        document.querySelector(".carbon-captcha").classList.add("is-passed");
      } else {
        model.helpers.setReadout("FAIL", "error");
        window.setTimeout(() => outcome.state && model.helpers.render(outcome.state), 850);
      }
    } catch (_error) {
      model.submitting = false;
      model.helpers.setReadout("FAIL", "error");
    }
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "carbon-signature-v3";
    model = {
      state,
      helpers,
      events: [],
      offsets: Object.fromEntries(state.form.layers.map((layer) => [layer.id, {...layer.initial}])),
      stroke: null,
      submitting: false,
    };
    const aperture = state.form.aperture;
    const points = state.form.original_trace.map((point) => point.join(",")).join(" ");
    helpers.app.innerHTML = `<section class="carbon-captcha">
      <header><span>CARBON OFFICE / ORIGINAL BURIED</span><h1>${esc(state.prompt)}</h1><b class="carbon-register">REGISTER FOUR WINDOWS</b></header>
      <section class="carbon-stage" data-open="false">
        ${state.form.layers.map((layer, index) => {
          const localX = aperture.x - layer.target.x;
          const localY = aperture.y - layer.target.y;
          return `<div class="carbon-sheet sheet-${esc(layer.color)}" data-sheet-id="${esc(layer.id)}" style="--sheet-x:${layer.initial.x}px;--sheet-y:${layer.initial.y}px;--aperture-x:${localX}px;--aperture-y:${localY}px;z-index:${10 + index}">
            <div class="sheet-lines"></div><div class="sheet-aperture"><i data-fragment="${index}"></i></div>
          </div>`;
        }).join("")}
        <div class="original-paper"><div class="original-aperture" style="left:${aperture.x - aperture.radius}px;top:${aperture.y - aperture.radius}px;width:${aperture.radius * 2}px;height:${aperture.radius * 2}px"></div></div>
        <svg class="original-signature" viewBox="0 0 700 390" aria-hidden="true"><polyline points="${points}"></polyline><circle cx="${state.form.original_trace[0][0]}" cy="${state.form.original_trace[0][1]}" r="6"></circle></svg>
        <canvas class="signature-surface" data-enabled="false" width="700" height="390"></canvas>
        <nav class="sheet-controls" aria-label="carbon sheet registration tabs">${state.form.layers.map((layer, index) => `<button type="button" class="sheet-tab sheet-${esc(layer.color)}" data-control-id="${esc(layer.id)}"><i></i><b>${["A", "B", "C", "D"][index]}</b></button>`).join("")}</nav>
      </section>
      <footer><div class="readout" data-status="idle"></div><span>START AT THE SOLID DOT · TRACE WITHOUT LIFTING</span><div><button class="carbon-clear" type="button" disabled>CLEAR INK</button><button class="carbon-submit" type="button" disabled>CERTIFY</button></div></footer>
    </section>`;
    const context = document.querySelector(".signature-surface").getContext("2d");
    context.strokeStyle = "#e1372f";
    context.lineWidth = 4;
    context.lineCap = "round";
    context.lineJoin = "round";
    state.form.layers.forEach(installSheet);
    installSignature();
    document.querySelector(".carbon-clear").addEventListener("click", clearStroke);
    document.querySelector(".carbon-submit").addEventListener("click", submit);
    updateLayers();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.bureaucratic_signature_trap = {render, rootSelector: ".carbon-captcha"};
})();
