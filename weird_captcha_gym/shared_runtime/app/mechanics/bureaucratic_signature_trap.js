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

  const LETTERS = ["A", "B", "C", "D", "E"];
  const COUNT_WORDS = {1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE"};

  function sheetDragSamples(start, end) {
    const distance = Math.hypot(end[0] - start[0], end[1] - start[1]);
    const count = Math.max(1, Math.ceil(distance / 40));
    return Array.from({length: count}, (_unused, index) => {
      const amount = (index + 1) / count;
      return [
        Math.round(start[0] + (end[0] - start[0]) * amount),
        Math.round(start[1] + (end[1] - start[1]) * amount),
      ];
    });
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
    const count = model.state.form.layers.length;
    document.querySelector(".carbon-register").textContent = open
      ? "APERTURE REGISTERED"
      : `REGISTER ${COUNT_WORDS[count] || count} WINDOWS`;
  }

  function installSheet(layer) {
    const handle = document.querySelector(`.sheet-tab[data-control-id="${CSS.escape(layer.id)}"]`);
    handle.addEventListener("pointerdown", (event) => {
      if (model.stroke || model.submitting) return;
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      const start = [event.clientX, event.clientY];
      const origin = {...model.offsets[layer.id]};
      handle.dataset.dragging = "true";
      const move = (moveEvent) => {
        const offset = {
          x: Math.max(-170, Math.min(170, origin.x + moveEvent.clientX - start[0])),
          y: Math.max(-110, Math.min(110, origin.y + moveEvent.clientY - start[1])),
        };
        model.offsets[layer.id] = offset;
        updateLayers();
      };
      const up = () => {
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", up);
        handle.removeEventListener("pointercancel", up);
        handle.dataset.dragging = "false";
        const end = [Math.round(model.offsets[layer.id].x), Math.round(model.offsets[layer.id].y)];
        const startOffset = [Math.round(origin.x), Math.round(origin.y)];
        if (end[0] !== startOffset[0] || end[1] !== startOffset[1]) {
          record("sheet_drag", {
            sheet_id: layer.id,
            input_source: "fixed_registration_tab",
            start: startOffset,
            samples: sheetDragSamples(startOffset, end),
            end,
          });
        }
      };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", up);
      handle.addEventListener("pointercancel", up);
    });
  }

  function nudgeSheet(layer, dx, dy) {
    if (model.stroke || model.submitting) return;
    const origin = {...model.offsets[layer.id]};
    const offset = {
      x: Math.max(-170, Math.min(170, origin.x + dx)),
      y: Math.max(-110, Math.min(110, origin.y + dy)),
    };
    if (offset.x === origin.x && offset.y === origin.y) return;
    model.offsets[layer.id] = offset;
    record("sheet_drag", {
      sheet_id: layer.id,
      input_source: "sheet_nudge_button",
      start: [origin.x, origin.y],
      samples: [[offset.x, offset.y]],
      end: [offset.x, offset.y],
    });
    updateLayers();
  }

  function clearStroke() {
    if (!model.stroke || model.submitting) return;
    model.stroke = null;
    const canvas = document.querySelector(".signature-surface");
    canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    record("signature_clear", {input_source: "clear_ink_button"});
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
        record("signature", {points, input_source: "signature_canvas"});
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
    record("certify", {input_source: "certify_button"});
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({
          mechanic_id: model.state.mechanic_id,
          task_id: model.state.task_id,
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
    const interaction = state.control_condition?.interaction || "full";
    model = {
      state,
      helpers,
      interaction,
      events: [],
      offsets: Object.fromEntries(state.form.layers.map((layer) => [layer.id, {...layer.initial}])),
      stroke: null,
      submitting: false,
    };
    const aperture = state.form.aperture;
    const layerRange = state.form.layers.length === 1
      ? "A"
      : `A–${LETTERS[state.form.layers.length - 1]}`;
    const points = state.form.original_trace.map((point) => point.join(",")).join(" ");
    const sheetControls = interaction === "simplified"
      ? `<nav class="sheet-controls sheet-nudges" aria-label="carbon sheet nudge controls">${state.form.layers.map((layer, index) => `<div class="sheet-nudge-row sheet-${esc(layer.color)}"><b>${LETTERS[index]}</b><button type="button" data-control-id="${esc(layer.id)}" data-direction="left" aria-label="Move sheet ${index + 1} left">←</button><button type="button" data-control-id="${esc(layer.id)}" data-direction="up" aria-label="Move sheet ${index + 1} up">↑</button><button type="button" data-control-id="${esc(layer.id)}" data-direction="down" aria-label="Move sheet ${index + 1} down">↓</button><button type="button" data-control-id="${esc(layer.id)}" data-direction="right" aria-label="Move sheet ${index + 1} right">→</button></div>`).join("")}</nav>`
      : `<nav class="sheet-controls" aria-label="carbon sheet registration tabs">${state.form.layers.map((layer, index) => `<button type="button" class="sheet-tab sheet-${esc(layer.color)}" data-control-id="${esc(layer.id)}"><i></i><b>${LETTERS[index]}</b></button>`).join("")}</nav>`;
    helpers.app.innerHTML = `<section class="carbon-captcha" data-interaction="${esc(interaction)}">
      <header><span>CARBON OFFICE / ORIGINAL BURIED</span><h1>${esc(state.prompt)}</h1><b class="carbon-register">REGISTER ${COUNT_WORDS[state.form.layers.length] || state.form.layers.length} WINDOWS</b></header>
      <section class="carbon-stage" data-open="false">
        ${state.form.layers.map((layer, index) => {
          const localX = aperture.x - layer.target.x;
          const localY = aperture.y - layer.target.y;
          return `<div class="carbon-sheet sheet-${esc(layer.color)}" data-sheet-id="${esc(layer.id)}" style="--sheet-x:${layer.initial.x}px;--sheet-y:${layer.initial.y}px;--aperture-x:${localX}px;--aperture-y:${localY}px;--aperture-radius:${aperture.radius}px;--aperture-diameter:${aperture.radius * 2}px;z-index:${10 + index}">
            <div class="sheet-lines"></div><div class="sheet-aperture"><i data-fragment="${index}"></i></div>
          </div>`;
        }).join("")}
        <div class="original-paper"><div class="original-aperture" style="left:${aperture.x - aperture.radius}px;top:${aperture.y - aperture.radius}px;width:${aperture.radius * 2}px;height:${aperture.radius * 2}px"></div></div>
        <svg class="original-signature" viewBox="0 0 700 390" aria-hidden="true"><polyline points="${points}"></polyline><circle cx="${state.form.original_trace[0][0]}" cy="${state.form.original_trace[0][1]}" r="6"></circle></svg>
        <canvas class="signature-surface" data-enabled="false" width="700" height="390"></canvas>
        ${sheetControls}
      </section>
      <footer><div class="readout" data-status="idle"></div><span>${interaction === "simplified" ? `NUDGE SHEETS WITH ${layerRange} CONTROLS` : `DRAG THE FIXED ${layerRange} TABS`} · THEN TRACE WITHOUT LIFTING</span><div><button class="carbon-clear" type="button" disabled>CLEAR INK</button><button class="carbon-submit" type="button" disabled>CERTIFY</button></div></footer>
    </section>`;
    const context = document.querySelector(".signature-surface").getContext("2d");
    context.strokeStyle = "#e1372f";
    context.lineWidth = 4;
    context.lineCap = "round";
    context.lineJoin = "round";
    if (interaction === "full") {
      state.form.layers.forEach(installSheet);
    } else {
      const directions = {left: [-8, 0], up: [0, -8], down: [0, 8], right: [8, 0]};
      document.querySelectorAll(".sheet-nudges [data-control-id]").forEach((button) => {
        button.addEventListener("click", () => {
          const layer = state.form.layers.find((item) => item.id === button.dataset.controlId);
          const delta = directions[button.dataset.direction];
          if (layer && delta) nudgeSheet(layer, delta[0], delta[1]);
        });
      });
    }
    installSignature();
    document.querySelector(".carbon-clear").addEventListener("click", clearStroke);
    document.querySelector(".carbon-submit").addEventListener("click", submit);
    updateLayers();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.bureaucratic_signature_trap = {render, rootSelector: ".carbon-captcha"};
})();
