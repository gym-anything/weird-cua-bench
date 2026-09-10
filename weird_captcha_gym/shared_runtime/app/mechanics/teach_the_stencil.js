(() => {
  "use strict";
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};

  const PALETTE = ["#ead8ae", "#6fbf78", "#b48555", "#ee8eb0", "#f1c963", "#9b8ba9"];
  const MIN_FULL_PATH_LENGTH = 4.0;
  const BRUSH_OFFSETS = {
    1: [[0, 0]],
    2: [[0, 0], [1, 0]],
    3: [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]],
    4: [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [-1, -1]],
    5: [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [-1, -1], [1, -1], [-1, 1], [2, 0], [-2, 0], [0, 2], [0, -2]],
  };
  const model = {
    state: null,
    helpers: null,
    canvas: null,
    ctx: null,
    plot: {x: 26, y: 20, width: 848, height: 440},
    selectedClass: null,
    tool: "paint",
    brushSize: 2,
    samples: [],
    predictions: null,
    events: [],
    pointer: null,
    drawing: false,
    submitting: false,
    updateCount: 0,
    verdict: "idle",
  };

  function interaction() {
    return String(model.state?.control_condition?.interaction || "simplified");
  }

  function sourceFor(type) {
    if (type === "paint") return interaction() === "full" ? "brush_drag" : "proxy_stamp";
    return interaction() === "full" ? "eraser_drag" : "proxy_erase";
  }

  function pointFromEvent(event) {
    if (!model.canvas || !model.state?.plate) return null;
    const rect = model.canvas.getBoundingClientRect();
    const sx = model.canvas.width / rect.width;
    const sy = model.canvas.height / rect.height;
    const px = (event.clientX - rect.left) * sx;
    const py = (event.clientY - rect.top) * sy;
    const x = (px - model.plot.x) * Number(model.state.plate.width) / model.plot.width;
    const y = (py - model.plot.y) * Number(model.state.plate.height) / model.plot.height;
    if (x < 0 || y < 0 || x >= Number(model.state.plate.width) || y >= Number(model.state.plate.height)) return null;
    return {x: Math.max(0, Math.min(Number(model.state.plate.width) - 0.01, Number(x.toFixed(2)))), y: Math.max(0, Math.min(Number(model.state.plate.height) - 0.01, Number(y.toFixed(2))))};
  }

  function addEvent(type, details) {
    model.events.push(Object.assign({seq: model.events.length + 1, type}, details || {}));
  }

  function featureAt(point) {
    const width = Number(model.state.plate.width);
    const index = Math.min(model.state.plate.pixels.length - 1, Math.max(0, Math.floor(point.y) * width + Math.floor(point.x)));
    return model.state.plate.pixels[index];
  }

  function brushSizeValue(value) {
    const size = Math.round(Number(value));
    return Number.isInteger(size) && BRUSH_OFFSETS[size] ? size : 1;
  }

  function brushPoints(point, size) {
    const width = Number(model.state.plate.width);
    const height = Number(model.state.plate.height);
    const baseX = Math.floor(Number(point.x));
    const baseY = Math.floor(Number(point.y));
    const result = [];
    for (const [offsetX, offsetY] of BRUSH_OFFSETS[size]) {
      const x = baseX + offsetX;
      const y = baseY + offsetY;
      if (x < 0 || y < 0 || x >= width || y >= height) continue;
      if (!result.some((item) => item.x === x && item.y === y)) result.push({x, y});
    }
    return result;
  }

  function eraserRadius(size) {
    return 0.8 + 0.55 * Number(size);
  }

  function pathLength(points) {
    let length = 0;
    for (let index = 1; index < points.length; index += 1) {
      length += Math.hypot(points[index].x - points[index - 1].x, points[index].y - points[index - 1].y);
    }
    return length;
  }

  function applyStroke(type, points, classId, brushSize = 1) {
    const size = brushSizeValue(brushSize);
    if (type === "paint") {
      for (const point of points) {
        for (const samplePoint of brushPoints(point, size)) {
          model.samples.push({class_id: classId, x: samplePoint.x, y: samplePoint.y, feature: featureAt(samplePoint)});
        }
      }
      return;
    }
    const radius = eraserRadius(size);
    model.samples = model.samples.filter((sample) => !points.some((point) => Math.hypot(Number(sample.x) - point.x, Number(sample.y) - point.y) <= radius));
  }

  function distance(feature, centroid) {
    let value = 0;
    for (let i = 0; i < 3; i += 1) value += (Number(feature[i]) / 255 - Number(centroid[i]) / 255) ** 2;
    value += 0.65 * (Number(feature[3]) - Number(centroid[3])) ** 2;
    return value;
  }

  function predict() {
    const classCount = model.state.classes.length;
    const centroids = [];
    for (let classId = 0; classId < classCount; classId += 1) {
      const points = model.samples.filter((sample) => Number(sample.class_id) === classId);
      if (!points.length) return null;
      centroids[classId] = [0, 0, 0, 0];
      for (const point of points) for (let channel = 0; channel < 4; channel += 1) centroids[classId][channel] += Number(point.feature[channel]);
      centroids[classId] = centroids[classId].map((value) => value / points.length);
    }
    return model.state.plate.pixels.map((feature) => {
      let best = 0;
      let bestDistance = Infinity;
      for (let classId = 0; classId < classCount; classId += 1) {
        const current = distance(feature, centroids[classId]);
        if (current < bestDistance) { best = classId; bestDistance = current; }
      }
      return best;
    });
  }

  function classColor(classId) {
    return model.state.classes[classId]?.swatch || PALETTE[classId % PALETTE.length];
  }

  function draw() {
    if (!model.ctx || !model.state) return;
    const ctx = model.ctx;
    const width = Number(model.state.plate.width);
    const height = Number(model.state.plate.height);
    ctx.clearRect(0, 0, model.canvas.width, model.canvas.height);
    const gradient = ctx.createLinearGradient(0, 0, model.canvas.width, model.canvas.height);
    gradient.addColorStop(0, "#192d31");
    gradient.addColorStop(1, "#0b181d");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, model.canvas.width, model.canvas.height);
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,.45)";
    ctx.shadowBlur = 24;
    ctx.fillStyle = "#d8cbb1";
    ctx.fillRect(model.plot.x - 8, model.plot.y - 8, model.plot.width + 16, model.plot.height + 16);
    ctx.restore();
    const cellWidth = model.plot.width / width;
    const cellHeight = model.plot.height / height;
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const feature = model.state.plate.pixels[y * width + x];
        ctx.fillStyle = `rgb(${Math.round(feature[0])},${Math.round(feature[1])},${Math.round(feature[2])})`;
        ctx.fillRect(model.plot.x + x * cellWidth, model.plot.y + y * cellHeight, cellWidth + 0.5, cellHeight + 0.5);
      }
    }
    if (Array.isArray(model.predictions)) {
      ctx.globalAlpha = 0.43;
      for (let y = 0; y < height; y += 1) {
        for (let x = 0; x < width; x += 1) {
          ctx.fillStyle = classColor(model.predictions[y * width + x]);
          ctx.fillRect(model.plot.x + x * cellWidth, model.plot.y + y * cellHeight, cellWidth + 0.5, cellHeight + 0.5);
        }
      }
      ctx.globalAlpha = 1;
    }
    for (const sample of model.samples) {
      const sx = model.plot.x + Number(sample.x) * cellWidth;
      const sy = model.plot.y + Number(sample.y) * cellHeight;
      ctx.beginPath();
      ctx.arc(sx, sy, Math.max(2.5, Number(model.brushSize) * 1.6), 0, Math.PI * 2);
      ctx.fillStyle = classColor(Number(sample.class_id));
      ctx.globalAlpha = 0.92;
      ctx.fill();
      ctx.strokeStyle = "rgba(15,29,29,.85)";
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    ctx.strokeStyle = "rgba(255,245,213,.9)";
    ctx.lineWidth = 2;
    ctx.strokeRect(model.plot.x, model.plot.y, model.plot.width, model.plot.height);
  }

  function status(message, state = "idle") {
    model.helpers?.setReadout(message, state);
    const node = document.querySelector(".teach-stencil-verdict");
    if (node) { node.dataset.status = state; node.textContent = message; }
  }

  function chooseClass(classId) {
    model.selectedClass = Number(classId);
    document.querySelectorAll("[data-stencil-class]").forEach((button) => button.classList.toggle("is-selected", Number(button.dataset.stencilClass) === model.selectedClass));
    addEvent("select_class", {class_id: model.selectedClass, input_source: "palette_button"});
    status("ACTIVE", "active");
  }

  function setTool(tool) {
    model.tool = tool;
    document.querySelectorAll("[data-stencil-tool]").forEach((button) => button.classList.toggle("is-selected", button.dataset.stencilTool === tool));
    const canvas = document.querySelector("#teach-stencil-canvas");
    if (canvas) canvas.dataset.tool = tool;
  }

  function finishStroke(points) {
    if (!points.length) return;
    if (model.tool === "paint" && model.selectedClass == null) {
      status("FAIL", "error");
      return;
    }
    const type = model.tool === "paint" ? "paint" : "erase";
    if (interaction() === "full" && (points.length < 2 || pathLength(points) < MIN_FULL_PATH_LENGTH)) {
      status("FAIL", "error");
      return;
    }
    const size = brushSizeValue(model.brushSize);
    const details = {points, brush_size: size, input_source: sourceFor(type)};
    if (type === "paint") details.class_id = model.selectedClass;
    addEvent(type, details);
    applyStroke(type, points, model.selectedClass, size);
    draw();
    status(type === "paint" ? "MARKED" : "ERASED", "active");
  }

  function installPointerHandlers() {
    model.canvas.addEventListener("pointerdown", (event) => {
      const point = pointFromEvent(event);
      if (!point) return;
      model.pointer = point;
      model.drawing = true;
      model.canvas.setPointerCapture(event.pointerId);
      if (interaction() === "simplified") finishStroke([point]);
      else finishStroke([]);
      if (interaction() === "full") model.pointer = {points: [point], last: point, pointerId: event.pointerId};
    });
    model.canvas.addEventListener("pointermove", (event) => {
      if (!model.drawing || interaction() !== "full" || !model.pointer?.points) return;
      const point = pointFromEvent(event);
      if (!point) return;
      if (Math.hypot(point.x - model.pointer.last.x, point.y - model.pointer.last.y) >= 0.55) {
        model.pointer.points.push(point);
        model.pointer.last = point;
        draw();
      }
    });
    const finish = (event) => {
      if (!model.drawing || interaction() !== "full" || !model.pointer?.points) { model.drawing = false; return; }
      model.drawing = false;
      const points = model.pointer.points;
      model.pointer = null;
      finishStroke(points);
    };
    model.canvas.addEventListener("pointerup", finish);
    model.canvas.addEventListener("pointercancel", finish);
  }

  function recomputeFromEvents() {
    model.samples = [];
    model.predictions = null;
    model.updateCount = 0;
    for (const event of model.events) {
      if (event.type === "paint") applyStroke("paint", event.points || [], event.class_id, event.brush_size);
      else if (event.type === "erase") applyStroke("erase", event.points || [], null, event.brush_size);
      else if (event.type === "live_update") { model.predictions = predict(); model.updateCount += 1; }
    }
    draw();
  }

  function undo() {
    let index = model.events.length - 1;
    while (index >= 0 && !["paint", "erase"].includes(model.events[index].type)) index -= 1;
    if (index < 0) return;
    model.events.splice(index, 1);
    model.events.forEach((event, eventIndex) => { event.seq = eventIndex + 1; });
    recomputeFromEvents();
    status("READY", "idle");
  }

  async function updateModel() {
    if (!model.samples.length) { status("FAIL", "error"); return; }
    const prediction = predict();
    if (!prediction) { status("FAIL", "error"); return; }
    addEvent("live_update", {input_source: "live_update_button"});
    model.predictions = prediction;
    model.updateCount += 1;
    draw();
    status("UPDATED", "active");
  }

  async function postPayload(completed, includeCertify) {
    if (model.submitting) return;
    model.submitting = true;
    if (includeCertify) addEvent("certify", {input_source: "certify_button"});
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      control_condition: model.state.control_condition,
      input_surface: interaction(),
      events: model.events,
      completed,
      world_fingerprint: model.state.plate.world_fingerprint,
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.verdict = "passed";
        status("PASS", "passed");
      } else if (outcome.passed === false) {
        model.verdict = "error";
        if (outcome.state) {
          await render(outcome.state, model.helpers);
          status("FAIL", "error");
        } else status("FAIL", "error");
      }
    } catch (_error) {
      status("FAIL", "error");
    } finally {
      model.submitting = false;
    }
  }

  function resetLocal() {
    model.events = [];
    model.samples = [];
    model.predictions = null;
    model.selectedClass = null;
    model.updateCount = 0;
    document.querySelectorAll("[data-stencil-class]").forEach((button) => button.classList.remove("is-selected"));
    draw();
    status("READY", "idle");
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "teach-stencil";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    model.state = state;
    model.helpers = helpers;
    model.canvas = null;
    model.ctx = null;
    model.selectedClass = null;
    model.tool = "paint";
    model.brushSize = Number(state.tools?.default_brush_size || 2);
    model.samples = [];
    model.predictions = null;
    model.events = [];
    model.pointer = null;
    model.drawing = false;
    model.updateCount = 0;
    model.verdict = "idle";
    const mode = interaction();
    helpers.app.innerHTML = `
      <section class="teach-stencil" data-interaction="${helpers.text(mode)}">
        <header class="teach-stencil-header">
          <div><p class="teach-kicker">BOTANICAL PLATE</p><h1>Teach the Stencil</h1><p class="teach-prompt">${helpers.text(state.prompt)}</p></div>
          <div class="teach-contract"><span class="teach-contract-dot"></span><span>${helpers.text(mode.toUpperCase())} INPUT</span></div>
        </header>
        <div class="teach-stencil-grid">
          <aside class="teach-sidebar">
            <div class="teach-panel"><div class="teach-panel-label">MATERIAL PALETTE</div><div class="teach-palette">${state.classes.map((item) => `<button type="button" class="teach-class" data-stencil-class="${Number(item.id)}"><i style="--swatch:${helpers.text(item.swatch)}"></i><span>${helpers.text(item.name)}</span><small>${helpers.text(item.description)}</small></button>`).join("")}</div></div>
            <div class="teach-panel teach-tools"><div class="teach-panel-label">MARKING TOOL</div><div class="teach-tool-row"><button type="button" class="teach-tool is-selected" data-stencil-tool="paint">BRUSH</button><button type="button" class="teach-tool" data-stencil-tool="erase">ERASER</button></div><label class="teach-range">BRUSH SIZE <input id="teach-stencil-size" type="range" min="1" max="5" value="${model.brushSize}"><output id="teach-stencil-size-value">${model.brushSize}</output></label></div>
            <button type="button" class="teach-update" id="teach-stencil-update"><span>↻</span> LIVE UPDATE</button>
            <button type="button" class="teach-certify" id="teach-stencil-certify">CERTIFY MASK</button>
            <button type="button" class="teach-quiet-button" id="teach-stencil-undo">UNDO LAST MARK</button>
            <button type="button" class="teach-quiet-button" id="teach-stencil-fresh">NEW PLATE</button>
          </aside>
          <main class="teach-stage"><div class="teach-stage-top"><span>PLATE VIEW</span></div><canvas id="teach-stencil-canvas" width="900" height="480" aria-label="Botanical plate annotation canvas"></canvas><div class="teach-stage-caption"><span>PLATE</span></div><div class="teach-stencil-verdict readout" data-status="idle">READY</div></main>
        </div>
      </section>`;
    model.canvas = document.querySelector("#teach-stencil-canvas");
    model.ctx = model.canvas.getContext("2d");
    installPointerHandlers();
    document.querySelectorAll("[data-stencil-class]").forEach((button) => button.addEventListener("click", () => chooseClass(button.dataset.stencilClass)));
    document.querySelectorAll("[data-stencil-tool]").forEach((button) => button.addEventListener("click", () => setTool(button.dataset.stencilTool)));
    document.querySelector("#teach-stencil-size")?.addEventListener("input", (event) => { model.brushSize = Number(event.target.value); document.querySelector("#teach-stencil-size-value").textContent = String(model.brushSize); draw(); });
    document.querySelector("#teach-stencil-update")?.addEventListener("click", updateModel);
    document.querySelector("#teach-stencil-certify")?.addEventListener("click", () => postPayload(true, true));
    document.querySelector("#teach-stencil-undo")?.addEventListener("click", undo);
    document.querySelector("#teach-stencil-fresh")?.addEventListener("click", () => postPayload(false, false));
    draw();
  }

  window.teachTheStencilModel = model;
  window.WeirdCaptchaMechanics.teach_the_stencil = {rootSelector: ".teach-stencil", render};
})();
