(() => {
  "use strict";

  let model = null;
  const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));
  const round2 = (value) => Math.round(Number(value) * 100) / 100;
  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");

  function settleAction(action) {
    action?.settle();
  }

  function tokenColor(palette, token) {
    if (!token || token === "none") return null;
    return palette[token] || token;
  }

  function roundedRectPath(context, x, y, width, height, radius) {
    const r = Math.min(Math.max(0, Number(radius) || 0), Math.abs(width) / 2, Math.abs(height) / 2);
    context.beginPath();
    context.moveTo(x + r, y);
    context.lineTo(x + width - r, y);
    context.quadraticCurveTo(x + width, y, x + width, y + r);
    context.lineTo(x + width, y + height - r);
    context.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
    context.lineTo(x + r, y + height);
    context.quadraticCurveTo(x, y + height, x, y + height - r);
    context.lineTo(x, y + r);
    context.quadraticCurveTo(x, y, x + r, y);
    context.closePath();
  }

  function paintShape(context, primitive, palette) {
    context.save();
    context.globalAlpha = Number(primitive.alpha ?? 1);
    context.lineCap = "round";
    context.lineJoin = "round";
    const fill = tokenColor(palette, primitive.fill);
    const stroke = tokenColor(palette, primitive.stroke);
    if (primitive.kind === "line") {
      context.beginPath();
      context.moveTo(primitive.points[0], primitive.points[1]);
      context.lineTo(primitive.points[2], primitive.points[3]);
    } else if (primitive.kind === "ellipse") {
      context.beginPath();
      context.ellipse(primitive.cx, primitive.cy, primitive.rx, primitive.ry, 0, 0, Math.PI * 2);
    } else if (primitive.kind === "rect") {
      roundedRectPath(context, primitive.x, primitive.y, primitive.width, primitive.height, primitive.radius || 0);
    } else if (primitive.kind === "poly") {
      context.beginPath();
      primitive.points.forEach((point, index) => {
        if (index === 0) context.moveTo(point[0], point[1]);
        else context.lineTo(point[0], point[1]);
      });
      context.closePath();
    } else if (primitive.kind === "arc") {
      context.beginPath();
      context.arc(primitive.cx, primitive.cy, primitive.radius, primitive.start, primitive.end);
    } else {
      context.restore();
      return;
    }
    if (fill) {
      context.fillStyle = fill;
      context.fill();
    }
    if (stroke) {
      context.strokeStyle = stroke;
      context.lineWidth = Number(primitive.width ?? primitive.line_width ?? 1);
      context.stroke();
    }
    context.restore();
  }

  function seededNoise(seed) {
    let value = (Number(seed) || 1) >>> 0;
    return () => {
      value ^= value << 13;
      value ^= value >>> 17;
      value ^= value << 5;
      return (value >>> 0) / 4294967296;
    };
  }

  function buildSceneCanvas(state) {
    const canvas = document.createElement("canvas");
    canvas.width = state.stage.width;
    canvas.height = state.stage.height;
    const context = canvas.getContext("2d");
    const palette = state.scene.palette;
    const paper = context.createLinearGradient(0, 0, state.stage.width, state.stage.height);
    paper.addColorStop(0, palette.paper);
    paper.addColorStop(0.52, "#ead8b4");
    paper.addColorStop(1, palette.paper);
    context.fillStyle = paper;
    context.fillRect(0, 0, canvas.width, canvas.height);

    context.save();
    context.strokeStyle = "rgba(42,28,22,.16)";
    context.lineWidth = 2;
    for (let y = 26; y < canvas.height; y += 39) {
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(canvas.width, y + 9);
      context.stroke();
    }
    context.restore();
    state.scene.decorations.filter((item) => item.layer !== "foreground").forEach((item) => paintShape(context, item, palette));

    const subject = state.scene.subject;
    context.save();
    context.translate(subject.cx, subject.cy);
    context.rotate(subject.rotation_deg * Math.PI / 180);
    context.scale(subject.scale, subject.scale);
    state.scene.subject_primitives.forEach((primitive) => paintShape(context, primitive, palette));
    context.restore();
    state.scene.decorations.filter((item) => item.layer === "foreground").forEach((item) => paintShape(context, item, palette));

    const random = seededNoise(state.scene.grain_seed);
    context.save();
    for (let index = 0; index < 820; index += 1) {
      const x = random() * canvas.width;
      const y = random() * canvas.height;
      const alpha = 0.025 + random() * 0.085;
      context.fillStyle = `rgba(48,27,18,${alpha})`;
      const size = random() > 0.92 ? 2 : 1;
      context.fillRect(x, y, size, size);
    }
    context.restore();
    return canvas;
  }

  function drawFog(context, state) {
    const fog = context.createRadialGradient(430, 225, 25, 450, 250, 590);
    fog.addColorStop(0, "#d8d0be");
    fog.addColorStop(0.58, "#b9b1a4");
    fog.addColorStop(1, "#85807b");
    context.fillStyle = fog;
    context.fillRect(0, 0, state.stage.width, state.stage.height);
    const random = seededNoise(state.scene.grain_seed + 1709);
    context.save();
    for (let index = 0; index < 950; index += 1) {
      const x = random() * state.stage.width;
      const y = random() * state.stage.height;
      const light = random() > 0.5 ? 255 : 37;
      context.fillStyle = `rgba(${light},${light},${light},${0.018 + random() * 0.045})`;
      context.fillRect(x, y, random() > 0.94 ? 3 : 1, random() > 0.94 ? 3 : 1);
    }
    context.strokeStyle = "rgba(64,50,43,.18)";
    context.lineWidth = 1;
    for (let x = 20; x < state.stage.width; x += 44) {
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x - 28, state.stage.height);
      context.stroke();
    }
    context.restore();
  }

  function redraw() {
    if (!model) return;
    const canvas = document.getElementById("reveal-plate");
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    drawFog(context, model.state);
    for (const event of model.events) {
      const point = event.point;
      context.save();
      context.beginPath();
      context.arc(point[0], point[1], model.state.reveal.radius, 0, Math.PI * 2);
      context.clip();
      context.drawImage(model.sceneCanvas, 0, 0);
      context.restore();
      context.save();
      context.beginPath();
      context.arc(point[0], point[1], model.state.reveal.radius, 0, Math.PI * 2);
      context.strokeStyle = "rgba(103,36,30,.9)";
      context.lineWidth = 5;
      context.stroke();
      context.beginPath();
      context.arc(point[0], point[1], model.state.reveal.radius - 7, 0, Math.PI * 2);
      context.strokeStyle = "rgba(255,235,188,.65)";
      context.lineWidth = 2;
      context.stroke();
      context.fillStyle = "rgba(50,22,19,.88)";
      context.beginPath();
      context.arc(point[0] + model.state.reveal.radius * 0.68, point[1] - model.state.reveal.radius * 0.68, 14, 0, Math.PI * 2);
      context.fill();
      context.fillStyle = "#fff0c0";
      context.font = "900 13px 'Avenir Next Condensed', sans-serif";
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillText(String(event.sequence), point[0] + model.state.reveal.radius * 0.68, point[1] - model.state.reveal.radius * 0.68 + 1);
      context.restore();
    }
    if (model.interaction === "simplified" && model.cursor) {
      context.save();
      context.strokeStyle = "rgba(107,30,29,.95)";
      context.lineWidth = 3;
      context.beginPath();
      context.arc(model.cursor[0], model.cursor[1], 13, 0, Math.PI * 2);
      context.moveTo(model.cursor[0] - 22, model.cursor[1]);
      context.lineTo(model.cursor[0] + 22, model.cursor[1]);
      context.moveTo(model.cursor[0], model.cursor[1] - 22);
      context.lineTo(model.cursor[0], model.cursor[1] + 22);
      context.stroke();
      context.restore();
    }
  }

  function root() {
    return document.querySelector(".reveal-identify");
  }

  function clearFreshFailure() {
    if (!model?.freshFailure) return;
    model.freshFailure = false;
    root()?.setAttribute("data-fresh-failure", "false");
    const verdict = document.querySelector(".reveal-verdict");
    if (verdict) verdict.innerHTML = "";
    model.helpers.setReadout("FRESH PLATE · REVEALS RESTORED", "idle");
  }

  function update() {
    if (!model) return;
    const used = model.events.length;
    const remaining = model.state.reveal.budget - used;
    const shell = root();
    if (shell) {
      shell.dataset.revealCount = String(used);
      shell.dataset.remaining = String(remaining);
      shell.dataset.completed = String(model.terminal);
    }
    const usedNode = document.getElementById("reveal-used");
    const remainNode = document.getElementById("reveal-remaining");
    const meter = document.querySelector(".reveal-meter-fill");
    if (usedNode) usedNode.textContent = String(used);
    if (remainNode) remainNode.textContent = String(remaining);
    if (meter) meter.style.width = `${remaining / model.state.reveal.budget * 100}%`;
    const submit = document.getElementById("reveal-submit");
    if (submit) submit.disabled = model.submitting || model.terminal;
    redraw();
  }

  function pointFromEvent(event) {
    const canvas = document.getElementById("reveal-plate");
    const rect = canvas.getBoundingClientRect();
    return [
      round2(clamp((event.clientX - rect.left) / rect.width * model.state.stage.width, 0, model.state.stage.width)),
      round2(clamp((event.clientY - rect.top) / rect.height * model.state.stage.height, 0, model.state.stage.height)),
    ];
  }

  function coordinatePoint() {
    const x = Number(document.getElementById("reveal-x")?.value);
    const y = Number(document.getElementById("reveal-y")?.value);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return [
      round2(clamp(x, 0, model.state.stage.width)),
      round2(clamp(y, 0, model.state.stage.height)),
    ];
  }

  function revealAt(point, inputSource, action) {
    try {
      if (!model || model.submitting || model.terminal) return;
      clearFreshFailure();
      if (model.events.length >= model.state.reveal.budget) {
        model.helpers.setReadout("REVEAL BUDGET SPENT · FILE AN IDENTIFICATION", "error");
        return;
      }
      const sequence = model.events.length + 1;
      model.events.push({
        sequence,
        kind: "reveal",
        point: point.map(round2),
        radius: model.state.reveal.radius,
        remaining_after: model.state.reveal.budget - sequence,
        input_source: inputSource,
      });
      model.cursor = [...point];
      model.helpers.setReadout(
        sequence === model.state.reveal.budget ? "LAST WINDOW EXPOSED · NAME THE OBJECT" : `WINDOW ${sequence} EXPOSED`,
        "idle",
      );
      update();
    } finally {
      settleAction(action);
    }
  }

  function handlePlateClick(event) {
    if (model?.interaction !== "full") return;
    const action = model.helpers.beginAction?.("reveal-to-identify-plate-click") || null;
    revealAt(pointFromEvent(event), "plate_click", action);
  }

  function handleCoordinateReveal() {
    if (model?.interaction !== "simplified") return;
    const action = model.helpers.beginAction?.("reveal-to-identify-coordinate") || null;
    const point = coordinatePoint();
    if (!point) {
      model.helpers.setReadout("ENTER VALID PLATE COORDINATES", "error");
      settleAction(action);
      return;
    }
    revealAt(point, "coordinate_reveal", action);
  }

  function showPass() {
    const verdict = document.querySelector(".reveal-verdict");
    if (verdict) verdict.innerHTML = "<small>ARCHIVE MATCH</small><b>PASS</b><span>IDENTIFICATION FILED</span>";
    root()?.setAttribute("data-verdict", "pass");
  }

  async function submit() {
    if (!model || model.submitting || model.terminal) return;
    clearFreshFailure();
    const answerNode = document.getElementById("reveal-answer");
    const answer = String(answerNode?.value || "").trim();
    if (!model.events.length) {
      model.helpers.setReadout("EXPOSE AT LEAST ONE WINDOW BEFORE FILING", "error");
      return;
    }
    if (!answer) {
      model.helpers.setReadout("ENTER THE OBJECT'S COMMON NAME", "error");
      answerNode?.focus();
      return;
    }
    const current = model;
    current.submitting = true;
    current.helpers.setReadout("COMPARING PLATE AND IDENTIFICATION…", "pending");
    update();
    const payload = {
      mechanic_id: current.state.mechanic_id,
      task_id: current.state.task_id,
      challenge_id: current.state.challenge_id,
      interaction_mode: current.interaction,
      events: current.events.map((event) => ({...event, point: [...event.point]})),
      revealed_centers: current.events.map((event) => [...event.point]),
      reveal_count: current.events.length,
      remaining_budget: current.state.reveal.budget - current.events.length,
      answer,
      completed: true,
    };
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify(payload),
      });
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.terminal = true;
        current.submitting = false;
        current.helpers.setReadout("PASS", "passed");
        showPass();
        update();
      } else if (outcome.passed === false && outcome.state) {
        await render(outcome.state, current.helpers, {freshFailure: true});
        model.helpers.setReadout("FAIL · FRESH PLATE LOADED", "error");
      } else {
        current.submitting = false;
        current.helpers.setReadout("ARCHIVE REJECTED THE PACKET", "error");
        update();
      }
    } catch (_error) {
      if (model === current) {
        current.submitting = false;
        current.helpers.setReadout("ARCHIVE LINK OFFLINE", "error");
        update();
      }
    }
  }

  function bindCoordinatePreview() {
    if (model?.interaction !== "simplified") return;
    const preview = () => {
      const point = coordinatePoint();
      if (!point) return;
      model.cursor = point;
      redraw();
    };
    document.getElementById("reveal-x")?.addEventListener("input", preview);
    document.getElementById("reveal-y")?.addEventListener("input", preview);
  }

  async function render(state, helpers, options = {}) {
    document.body.dataset.mechanic = "reveal-to-identify";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const interaction = state.control_condition?.interaction || "full";
    const center = [Math.round(state.stage.width / 2), Math.round(state.stage.height / 2)];
    model = {
      state,
      helpers,
      interaction,
      events: [],
      cursor: interaction === "simplified" ? center : null,
      sceneCanvas: buildSceneCanvas(state),
      freshFailure: Boolean(options.freshFailure),
      submitting: false,
      terminal: false,
    };
    window.revealToIdentifyModel = model;
    const coordinateControls = interaction === "simplified" ? `
      <section class="reveal-coordinate-controls">
        <label>PLATE X<input id="reveal-x" type="number" min="0" max="${state.stage.width}" step="1" value="${center[0]}"></label>
        <label>PLATE Y<input id="reveal-y" type="number" min="0" max="${state.stage.height}" step="1" value="${center[1]}"></label>
        <button id="reveal-coordinate-button">REVEAL DISC</button>
      </section>` : "";
    helpers.app.innerHTML = `
      <section class="reveal-identify" data-interaction="${esc(interaction)}" data-fresh-failure="${options.freshFailure ? "true" : "false"}" data-verdict="">
        <div class="reveal-verdict">${options.freshFailure ? "<small>PLATE MISIDENTIFIED</small><b>FAIL</b><span>FRESH PLATE LOADED</span>" : ""}</div>
        <header class="reveal-head">
          <div><small>DEPARTMENT OF OBSCURED OBJECTS · PLATE ${esc(state.challenge_id)}</small><h1>${esc(state.prompt)}</h1></div>
          <aside><span>${interaction.toUpperCase()} INPUT</span><b>${state.reveal.radius}px</b><em>DISC RADIUS</em></aside>
        </header>
        <main class="reveal-workbench">
          <aside class="reveal-budget-panel">
            <small>EXPOSURE WALLET</small>
            <div class="reveal-counter"><b id="reveal-remaining">${state.reveal.budget}</b><span>REVEALS<br>REMAIN</span></div>
            <div class="reveal-meter"><i class="reveal-meter-fill"></i></div>
            <dl><div><dt>USED</dt><dd id="reveal-used">0</dd></div><div><dt>PLATE</dt><dd>${state.stage.width}×${state.stage.height}</dd></div></dl>
            <p>${interaction === "full" ? "Click directly on the emulsion. Every opening is permanent and spends one reveal." : "Set a plate coordinate, then expose exactly one disc at that point."}</p>
            <div class="reveal-seal"><i></i><span>NO OBJECT PIXELS ARE VISIBLE UNTIL EXPOSED</span></div>
          </aside>
          <section class="reveal-plate-wrap">
            <canvas id="reveal-plate" width="${state.stage.width}" height="${state.stage.height}" aria-label="Fogged photographic plate"></canvas>
            <span class="plate-corner corner-a">A</span><span class="plate-corner corner-b">B</span>
          </section>
          <aside class="reveal-file-panel">
            <small>IDENTIFICATION FILE</small>
            ${coordinateControls}
            <label class="reveal-answer-label" for="reveal-answer">COMMON ENGLISH NAME</label>
            <input id="reveal-answer" maxlength="32" autocomplete="off" spellcheck="false" placeholder="TYPE OBJECT NAME">
            <button id="reveal-submit">${esc(state.submit_label)}</button>
            <p class="reveal-file-note">One wrong filing closes this plate. A fresh specimen follows immediately.</p>
            <div class="reveal-stamp"><span>VISUAL EVIDENCE</span><b>REQUIRED</b></div>
          </aside>
        </main>
        <footer class="reveal-foot"><span>ACTIVE PERCEPTION ARCHIVE · ORIGINAL PROCEDURAL PLATE</span><div class="readout" data-status="idle">CHOOSE THE FIRST REVEAL</div><span>NO LIVE MOTION</span></footer>
        ${helpers.cheatPanelTemplate()}
      </section>`;
    document.getElementById("reveal-plate")?.addEventListener("click", handlePlateClick);
    document.getElementById("reveal-coordinate-button")?.addEventListener("click", handleCoordinateReveal);
    document.getElementById("reveal-submit")?.addEventListener("click", submit);
    document.getElementById("reveal-answer")?.addEventListener("input", clearFreshFailure);
    document.getElementById("reveal-answer")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") void submit();
    });
    bindCoordinatePreview();
    helpers.installCheatPanel();
    update();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.reveal_to_identify = {rootSelector: ".reveal-identify", render};
})();
