(() => {
  "use strict";

  const MECHANIC_ID = "pocket_animation_studio";
  const FIELDS = {
    circle: ["x", "y", "radius"],
    rect: ["x", "y", "width", "height"],
    line: ["x1", "y1", "x2", "y2", "width"],
  };
  const FIELD_LABELS = {
    x: "X", y: "Y", x1: "X1", y1: "Y1", x2: "X2", y2: "Y2",
    radius: "R", width: "W", height: "H",
  };
  const EXPRESSION_NAMES = {
    const: "CONST", linear: "LINEAR", reverse: "REVERSE", wave: "WAVE",
  };
  const COLORS = ["#f8d66d", "#70e7cf", "#ff7f8a", "#a995ff", "#7fc8ff", "#f4a261"];
  const model = {
    state: null,
    interaction: "full",
    program: [],
    events: [],
    referenceStartedAt: 0,
    previewStartedAt: 0,
    previewRunning: false,
    previewComplete: false,
    runCount: 0,
    animationFrame: 0,
    lastT: 0,
    notice: "",
  };

  function esc(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function round(value) {
    return Math.round(Number(value) * 1000) / 1000;
  }

  function setReadout(api, message, status = "idle") {
    api.setReadout(message, status);
    const node = document.querySelector(".pas-readout");
    if (node) {
      node.textContent = message;
      node.dataset.status = status;
    }
  }

  function condition(state) {
    return state.control_condition || {};
  }

  function allowedExpressionKinds(state = model.state) {
    const declared = state?.studio?.expression_types;
    if (!Array.isArray(declared)) return Object.keys(EXPRESSION_NAMES);
    return declared.map(kind => String(kind)).filter(kind => Object.hasOwn(EXPRESSION_NAMES, kind));
  }

  function defaultExpression(kind) {
    return {kind, a: 50, b: kind === "const" ? 0 : 20, frequency: kind === "wave" ? 1 : 1};
  }

  function expressionValue(expression, t) {
    if (!expression) return null;
    const kind = String(expression.kind || "const");
    const a = Number(expression.a || 0);
    const b = Number(expression.b || 0);
    const frequency = Math.max(1, Number(expression.frequency || 1));
    let value = a;
    if (kind === "linear") value = a + b * t;
    else if (kind === "reverse") value = a + b * (1 - t);
    else if (kind === "wave") value = a + b * Math.sin(Math.PI * 2 * frequency * t);
    return Math.max(0, Math.min(100, value));
  }

  function completeProgram() {
    return model.program.length > 0 && model.program.every(shape =>
      FIELDS[shape.kind] && FIELDS[shape.kind].every(field => shape.expressions && shape.expressions[field])
    );
  }

  function renderedProgram(t) {
    if (!completeProgram()) return [];
    return model.program.map(shape => {
      const item = {id: shape.id, kind: shape.kind, color: shape.color};
      for (const field of FIELDS[shape.kind]) item[field] = round(expressionValue(shape.expressions[field], t));
      return item;
    });
  }

  function frameAt(frames, t) {
    if (!Array.isArray(frames) || !frames.length) return {objects: []};
    const index = Math.max(0, Math.min(frames.length - 1, Math.round(t * (frames.length - 1))));
    return frames[index] || frames[0];
  }

  function mapPoint(width, height, valueX, valueY) {
    return {
      x: 26 + Number(valueX || 0) / 100 * (width - 52),
      y: 24 + Number(valueY || 0) / 100 * (height - 48),
    };
  }

  function drawBackdrop(ctx, width, height, theme, title) {
    const backgrounds = [["#11182b", "#233b53"], ["#171b2d", "#45233d"], ["#0c2223", "#203c37"], ["#241d18", "#3d3545"], ["#161c28", "#254b56"], ["#2a1d2b", "#4a344b"]];
    const colors = backgrounds[Math.abs(Number(theme || 0)) % backgrounds.length];
    const gradient = ctx.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, colors[0]);
    gradient.addColorStop(1, colors[1]);
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);
    ctx.save();
    ctx.globalAlpha = .16;
    ctx.strokeStyle = "#c8efff";
    ctx.lineWidth = 1;
    for (let x = 0; x < width; x += 23) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x - height * .18, height); ctx.stroke();
    }
    for (let y = 20; y < height; y += 27) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
    }
    ctx.restore();
    ctx.fillStyle = "rgba(255,255,255,.58)";
    ctx.font = "700 9px 'Courier New', monospace";
    ctx.letterSpacing = "2px";
    ctx.fillText(String(title || "POCKET SCENE"), 17, 18);
    ctx.fillStyle = "rgba(255,255,255,.12)";
    ctx.fillRect(15, height - 17, width - 30, 1);
  }

  function drawObjects(ctx, width, height, objects, options = {}) {
    const preview = Boolean(options.preview);
    ctx.save();
    for (const object of objects || []) {
      const color = String(object.color || "#ffffff");
      ctx.shadowColor = color;
      ctx.shadowBlur = preview ? 12 : 8;
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineCap = "round";
      if (object.kind === "circle") {
        const point = mapPoint(width, height, object.x, object.y);
        const radius = 7 + Number(object.radius || 0) / 100 * 31;
        ctx.beginPath(); ctx.arc(point.x, point.y, radius, 0, Math.PI * 2); ctx.fill();
        ctx.shadowBlur = 0; ctx.strokeStyle = "rgba(255,255,255,.58)"; ctx.lineWidth = 1.2; ctx.stroke();
      } else if (object.kind === "rect") {
        const point = mapPoint(width, height, object.x, object.y);
        const w = 12 + Number(object.width || 0) / 100 * 70;
        const h = 10 + Number(object.height || 0) / 100 * 56;
        ctx.fillRect(point.x - w / 2, point.y - h / 2, w, h);
        ctx.shadowBlur = 0; ctx.strokeStyle = "rgba(255,255,255,.6)"; ctx.lineWidth = 1.2; ctx.strokeRect(point.x - w / 2, point.y - h / 2, w, h);
      } else if (object.kind === "line") {
        const first = mapPoint(width, height, object.x1, object.y1);
        const second = mapPoint(width, height, object.x2, object.y2);
        ctx.lineWidth = 2 + Number(object.width || 0) / 100 * 9;
        ctx.beginPath(); ctx.moveTo(first.x, first.y); ctx.lineTo(second.x, second.y); ctx.stroke();
        ctx.shadowBlur = 0; ctx.fillStyle = "rgba(255,255,255,.72)";
        ctx.beginPath(); ctx.arc(first.x, first.y, 2.5, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(second.x, second.y, 2.5, 0, Math.PI * 2); ctx.fill();
      }
    }
    ctx.restore();
  }

  function drawCanvas(canvas, objects, state, title, t, preview) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const width = Number(canvas.width || 460);
    const height = Number(canvas.height || 270);
    drawBackdrop(ctx, width, height, state.reference?.palette, title);
    drawObjects(ctx, width, height, objects, {preview});
    ctx.save();
    ctx.fillStyle = "rgba(255,255,255,.68)";
    ctx.font = "700 9px 'Courier New', monospace";
    ctx.fillText(`t = ${Math.round(t * 100)}%`, width - 76, height - 7);
    ctx.restore();
  }

  function pushEvent(type, details = {}) {
    model.events.push({seq: model.events.length + 1, type, ...details});
  }

  function invalidatePreview() {
    model.previewComplete = false;
    model.previewRunning = false;
  }

  function shapeHTML(shape, index, simplified) {
    const fields = FIELDS[shape.kind] || [];
    const fieldLabels = model.state.studio?.field_labels || FIELD_LABELS;
    const sockets = fields.map(field => {
      const expression = shape.expressions?.[field];
      const valueHTML = expression ? expressionEditorHTML(shape.id, field, expression, simplified) : `<div class="pas-empty-socket"><span>DROP EXPRESSION</span></div>`;
      const proxy = simplified && !expression ? proxyExpressionHTML(shape.id, field) : "";
      return `<div class="pas-socket" data-shape-id="${esc(shape.id)}" data-field="${esc(field)}">
        <span class="pas-field-label">${esc(fieldLabels[field] || field.toUpperCase())}</span>${valueHTML}${proxy}
      </div>`;
    }).join("");
    return `<article class="pas-shape-row" data-shape-id="${esc(shape.id)}">
      <div class="pas-shape-heading"><span class="pas-shape-index">${String(index + 1).padStart(2, "0")}</span><strong>${esc(shape.kind.toUpperCase())}</strong><i style="--pen:${esc(shape.color)}"></i><button class="pas-remove" data-remove-shape="${esc(shape.id)}" aria-label="Remove ${esc(shape.kind)} block">×</button></div>
      <div class="pas-sockets">${sockets}</div>
    </article>`;
  }

  function expressionEditorHTML(shapeId, field, expression, simplified) {
    const allowed = allowedExpressionKinds();
    const selected = allowed.includes(expression.kind) ? expression.kind : allowed[0];
    const options = allowed.map(kind => `<option value="${kind}"${selected === kind ? " selected" : ""}>${EXPRESSION_NAMES[kind]}</option>`).join("");
    return `<div class="pas-expression" data-expression-editor="true">
      <select class="pas-op" data-shape-id="${esc(shapeId)}" data-field="${esc(field)}" aria-label="${esc(field)} expression">${options}</select>
      <label>A<input class="pas-num" data-part="a" data-shape-id="${esc(shapeId)}" data-field="${esc(field)}" type="number" min="0" max="100" step="0.1" value="${esc(round(expression.a))}"></label>
      <label>B<input class="pas-num" data-part="b" data-shape-id="${esc(shapeId)}" data-field="${esc(field)}" type="number" min="-100" max="100" step="0.1" value="${esc(round(expression.b))}"></label>
      <label>F<input class="pas-num pas-frequency" data-part="frequency" data-shape-id="${esc(shapeId)}" data-field="${esc(field)}" type="number" min="1" max="8" step="1" value="${esc(Math.max(1, Number(expression.frequency || 1)))}"></label>
    </div>`;
  }

  function proxyExpressionHTML(shapeId, field) {
    return `<div class="pas-proxy-choices" aria-label="Apply expression to ${esc(field)}">${allowedExpressionKinds().map(kind => `<button type="button" data-proxy-kind="${kind}" data-shape-id="${esc(shapeId)}" data-field="${esc(field)}">${EXPRESSION_NAMES[kind]}</button>`).join("")}</div>`;
  }

  function renderProgram() {
    const stack = document.getElementById("pas-program-stack");
    if (!stack) return;
    const simplified = model.interaction === "simplified";
    stack.innerHTML = model.program.length
      ? model.program.map((shape, index) => shapeHTML(shape, index, simplified)).join("")
      : `<div class="pas-empty-program"><span>DROP SHAPE BLOCKS HERE</span><small>The preview stays quiet until a program exists.</small></div>`;
    document.querySelector(".pas-block-count")?.replaceChildren(document.createTextNode(`${model.program.length} / ${model.state.studio.shapes.length} SHAPES`));
    bindProgramEvents();
  }

  function addShape(kind, eventType) {
    if (!FIELDS[kind] || model.program.length >= Number(model.state.studio.shapes.length || 0)) return;
    const index = model.program.length;
    const targetShape = model.state.studio.shapes[index] || {};
    const shape = {
      id: `shape-${index + 1}`,
      kind,
      color: targetShape.color || COLORS[index % COLORS.length],
      expressions: {},
    };
    model.program.push(shape);
    pushEvent(eventType, {shape_id: shape.id, kind});
    invalidatePreview();
    setReadout(window.__pasApi, `ADDED ${kind.toUpperCase()} / DROP ITS EXPRESSIONS`, "idle");
    renderProgram();
  }

  function setExpression(shapeId, field, kind, eventType) {
    const shape = model.program.find(item => item.id === shapeId);
    if (!shape || !FIELDS[shape.kind]?.includes(field)) return;
    if (!allowedExpressionKinds().includes(kind)) {
      setReadout(window.__pasApi, `${String(kind).toUpperCase()} IS NOT AVAILABLE AT THIS LEVEL`, "error");
      return;
    }
    const previous = shape.expressions[field];
    const next = previous ? clone(previous) : defaultExpression(kind);
    next.kind = kind;
    if (kind === "const") next.b = 0;
    if (kind !== "wave") next.frequency = 1;
    shape.expressions[field] = next;
    pushEvent(eventType, {shape_id: shapeId, field, kind});
    invalidatePreview();
    renderProgram();
  }

  function updateNumeric(input) {
    const shape = model.program.find(item => item.id === input.dataset.shapeId);
    const field = input.dataset.field;
    const part = input.dataset.part;
    if (!shape || !shape.expressions?.[field] || !part) return;
    let value = Number(input.value);
    if (!Number.isFinite(value)) value = part === "frequency" ? 1 : 0;
    if (part === "frequency") value = Math.max(1, Math.min(8, Math.round(value)));
    else value = Math.max(-100, Math.min(100, value));
    shape.expressions[field][part] = value;
    pushEvent("numeric_edit", {shape_id: shape.id, field, part, value: round(value)});
    invalidatePreview();
  }

  function removeShape(shapeId) {
    const index = model.program.findIndex(item => item.id === shapeId);
    if (index < 0) return;
    model.program.splice(index, 1);
    model.program.forEach((shape, nextIndex) => { shape.id = `shape-${nextIndex + 1}`; });
    pushEvent("remove_shape", {shape_id: shapeId});
    invalidatePreview();
    renderProgram();
  }

  function bindProgramEvents() {
    document.querySelectorAll("[data-remove-shape]").forEach(button => button.addEventListener("click", () => removeShape(button.dataset.removeShape)));
    document.querySelectorAll(".pas-op").forEach(select => select.addEventListener("change", () => {
      const shape = model.program.find(item => item.id === select.dataset.shapeId);
      const expression = shape?.expressions?.[select.dataset.field];
      if (!expression) return;
      const requestedKind = select.value;
      if (!allowedExpressionKinds().includes(requestedKind)) {
        select.value = expression.kind;
        setReadout(window.__pasApi, `${String(requestedKind).toUpperCase()} IS NOT AVAILABLE AT THIS LEVEL`, "error");
        return;
      }
      expression.kind = select.value;
      if (expression.kind === "const") expression.b = 0;
      if (expression.kind !== "wave") expression.frequency = 1;
      pushEvent("numeric_edit", {shape_id: shape.id, field: select.dataset.field, part: "kind", value: select.value});
      invalidatePreview();
      renderProgram();
    }));
    document.querySelectorAll(".pas-num").forEach(input => input.addEventListener("change", () => updateNumeric(input)));
    document.querySelectorAll("[data-proxy-kind]").forEach(button => button.addEventListener("click", () => {
      setExpression(button.dataset.shapeId, button.dataset.field, button.dataset.proxyKind, "proxy_expression");
    }));
    document.querySelectorAll(".pas-socket").forEach(socket => {
      socket.addEventListener("dragover", event => { if (model.interaction === "full") { event.preventDefault(); socket.classList.add("is-drop-target"); } });
      socket.addEventListener("dragleave", () => socket.classList.remove("is-drop-target"));
      socket.addEventListener("drop", event => {
        event.preventDefault(); socket.classList.remove("is-drop-target");
        if (model.interaction !== "full") return;
        let data = {};
        try { data = JSON.parse(event.dataTransfer.getData("text/plain") || "{}"); } catch (_error) { data = {}; }
        if (data.type === "expression") setExpression(socket.dataset.shapeId, socket.dataset.field, data.kind, "drag_expression");
      });
    });
  }

  function bindPalette() {
    document.querySelectorAll("[data-shape-kind]").forEach(block => {
      block.addEventListener("dragstart", event => {
        event.dataTransfer.setData("text/plain", JSON.stringify({type: "shape", kind: block.dataset.shapeKind}));
        event.dataTransfer.effectAllowed = "copy";
      });
      block.addEventListener("click", () => {
        if (model.interaction === "simplified") addShape(block.dataset.shapeKind, "proxy_shape");
      });
    });
    document.querySelectorAll("[data-expression-kind]").forEach(block => {
      block.addEventListener("dragstart", event => {
        event.dataTransfer.setData("text/plain", JSON.stringify({type: "expression", kind: block.dataset.expressionKind}));
        event.dataTransfer.effectAllowed = "copy";
      });
    });
    const stack = document.getElementById("pas-program-stack");
    stack?.addEventListener("dragover", event => { if (model.interaction === "full") event.preventDefault(); });
    stack?.addEventListener("drop", event => {
      event.preventDefault();
      if (model.interaction !== "full") return;
      let data = {};
      try { data = JSON.parse(event.dataTransfer.getData("text/plain") || "{}"); } catch (_error) { data = {}; }
      if (data.type === "shape") addShape(data.kind, "drag_shape");
    });
    document.getElementById("pas-run")?.addEventListener("click", runPreview);
    document.getElementById("pas-certify")?.addEventListener("click", certify);
    document.getElementById("pas-reset")?.addEventListener("click", () => {
      model.program = []; model.events = []; model.previewComplete = false; model.previewRunning = false; renderProgram();
      setReadout(window.__pasApi, "PROGRAM CLEARED", "idle");
    });
    document.getElementById("pas-ref-toggle")?.addEventListener("click", event => {
      const button = event.currentTarget;
      button.dataset.paused = button.dataset.paused === "true" ? "false" : "true";
      button.textContent = button.dataset.paused === "true" ? "PLAY REFERENCE" : "PAUSE REFERENCE";
      model.referencePaused = button.dataset.paused === "true";
    });
  }

  function installReferenceLoop() {
    if (model.animationFrame) cancelAnimationFrame(model.animationFrame);
    model.referenceStartedAt = performance.now();
    model.referencePaused = false;
    const tick = now => {
      const state = model.state;
      const duration = Number(state.reference.duration_ms || 4200);
      let elapsed = now - model.referenceStartedAt;
      if (model.referencePaused) elapsed = model.lastT * duration;
      const t = model.referencePaused ? model.lastT : ((elapsed % duration) / duration);
      model.lastT = t;
      const frame = frameAt(state.reference.frames, t);
      drawCanvas(document.getElementById("pas-reference"), frame.objects, state, "REFERENCE LOOP", t, false);
      const progress = document.querySelector(".pas-ref-progress");
      if (progress) progress.style.width = `${Math.round(t * 100)}%`;
      if (model.previewRunning) drawPreview(now);
      model.animationFrame = requestAnimationFrame(tick);
    };
    model.animationFrame = requestAnimationFrame(tick);
  }

  function drawPreview(now) {
    const canvas = document.getElementById("pas-preview");
    const overlay = document.querySelector(".pas-preview-overlay");
    const duration = Number(model.state.reference.duration_ms || 4200);
    const elapsed = now - model.previewStartedAt;
    const t = Math.max(0, Math.min(1, elapsed / duration));
    const objects = renderedProgram(t);
    drawCanvas(canvas, objects, model.state, "YOUR PROGRAM", t, true);
    const progress = document.querySelector(".pas-preview-progress");
    if (progress) progress.style.width = `${Math.round(t * 100)}%`;
    if (overlay) overlay.hidden = objects.length > 0;
    if (t >= 1) {
      model.previewRunning = false;
      model.previewComplete = true;
      pushEvent("preview_complete", {duration_ms: duration});
      const score = similarityScore();
      setReadout(window.__pasApi, `PREVIEW COMPLETE / VISUAL DRIFT ${score.max.toFixed(1)} PX`, score.max <= Number(model.state.control_condition?.difficulty_parameters?.render_tolerance || 2.6) ? "idle" : "error");
      updateMeters(score);
      return;
    }
  }

  function similarityScore() {
    const frames = model.state.reference.frames || [];
    let max = 0; let total = 0; let count = 0;
    frames.forEach(frame => {
      const actual = renderedProgram(Number(frame.t || 0));
      (frame.objects || []).forEach((expected, index) => {
        const got = actual[index];
        if (!got) { max = Math.max(max, 100); total += 100; count += 1; return; }
        const fields = FIELDS[expected.kind] || [];
        let errors = fields.map(field => Math.abs(Number(got[field] || 0) - Number(expected[field] || 0)));
        if (expected.kind === "line" && got.kind === "line") {
          const reversedFields = ["x2", "y2", "x1", "y1", "width"];
          const reversedErrors = fields.map((field, i) => Math.abs(Number(got[field] || 0) - Number(expected[reversedFields[i]] || 0)));
          const directMax = Math.max(...errors); const reversedMax = Math.max(...reversedErrors);
          if (reversedMax < directMax || (reversedMax === directMax && reversedErrors.reduce((a, b) => a + b, 0) < errors.reduce((a, b) => a + b, 0))) {
            errors = reversedErrors;
          }
        }
        errors.forEach(error => {
          max = Math.max(max, error); total += error; count += 1;
        });
      });
    });
    return {max, mean: total / Math.max(1, count)};
  }

  function updateMeters(score) {
    const meter = document.querySelector(".pas-drift-meter i");
    if (meter) meter.style.width = `${Math.max(3, Math.min(100, score.max * 12))}%`;
    const label = document.querySelector(".pas-drift-value");
    if (label) label.textContent = `MAX ${score.max.toFixed(1)} / MEAN ${score.mean.toFixed(1)}`;
  }

  function runPreview() {
    if (!completeProgram()) {
      setReadout(window.__pasApi, "PROGRAM INCOMPLETE / FILL EVERY SOCKET", "error");
      pushEvent("run", {accepted: false});
      return;
    }
    model.runCount += 1;
    model.previewStartedAt = performance.now();
    model.previewRunning = true;
    model.previewComplete = false;
    pushEvent("run", {accepted: true, run_index: model.runCount});
    setReadout(window.__pasApi, `RUNNING FULL LOOP ${model.runCount}`, "idle");
    const overlay = document.querySelector(".pas-preview-overlay");
    if (overlay) overlay.hidden = true;
    drawPreview(performance.now());
  }

  async function certify() {
    if (!completeProgram() || !model.previewComplete) {
      setReadout(window.__pasApi, "RUN THE COMPLETE PREVIEW BEFORE CERTIFYING", "error");
      return;
    }
    const score = similarityScore();
    pushEvent("certify", {max_error: round(score.max), mean_error: round(score.mean)});
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      interaction: model.interaction,
      program: clone(model.program),
      events: clone(model.events),
      run_count: model.runCount,
      preview_complete: true,
      completed: true,
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        setReadout(window.__pasApi, "PASS / REFERENCE MATCHED", "passed");
        document.querySelector(".pas-workbench")?.classList.add("is-passed");
        document.querySelector("#pas-certify")?.setAttribute("disabled", "disabled");
        showVerdict("PROGRAM ACCEPTED", "Every sampled moment stayed inside the visual tolerance.", false);
      } else if (outcome.passed === false) {
        const next = outcome.state || model.state;
        render(next, window.__pasApi);
        setReadout(window.__pasApi, "FAIL / A FRESH REFERENCE IS READY", "error");
      } else {
        setReadout(window.__pasApi, "SUBMISSION NOT GRADED", "error");
      }
    } catch (_error) {
      setReadout(window.__pasApi, "SUBMISSION ERROR", "error");
    }
  }

  function showVerdict(title, subtitle, fresh) {
    const node = document.createElement("div");
    node.className = `pas-verdict${fresh ? " is-fresh" : ""}`;
    node.innerHTML = `<strong>${esc(title)}</strong><span>${esc(subtitle)}</span>`;
    document.querySelector(".pocket-animation-studio")?.appendChild(node);
  }

  function render(state, api) {
    if (model.animationFrame) cancelAnimationFrame(model.animationFrame);
    model.state = state;
    model.interaction = String(condition(state).interaction || "full");
    model.program = [];
    model.events = [];
    model.previewRunning = false;
    model.previewComplete = false;
    model.runCount = 0;
    window.__pasApi = api;
    document.body.dataset.mechanic = "pocket-animation-studio";
    document.body.dataset.interaction = model.interaction;
    const simplified = model.interaction === "simplified";
    const shapeBlocks = ["circle", "rect", "line"].map(kind => `<div class="pas-block pas-shape-block" draggable="${simplified ? "false" : "true"}" data-shape-kind="${kind}" role="button" tabindex="0"><b>${kind === "circle" ? "●" : kind === "rect" ? "▰" : "／"}</b><span>${kind.toUpperCase()}</span></div>`).join("");
    const expressionBlocks = allowedExpressionKinds(state).map(kind => `<div class="pas-block pas-expression-block" draggable="${simplified ? "false" : "true"}" data-expression-kind="${kind}" role="button" tabindex="0"><b>${kind === "linear" ? "↗" : kind === "reverse" ? "↘" : kind === "wave" ? "∿" : "·"}</b><span>${EXPRESSION_NAMES[kind] || kind.toUpperCase()}</span></div>`).join("");
    const proxyShapeButtons = simplified ? `<div class="pas-proxy-panel"><span>PROXY ADD</span>${["circle", "rect", "line"].map(kind => `<button type="button" data-shape-kind="${kind}">ADD ${kind.toUpperCase()}</button>`).join("")}</div>` : "";
    const description = simplified ? "Use the labeled controls to edit the program." : "Use the palette and program stack to edit the program.";
    document.getElementById("app").innerHTML = `<section class="pocket-animation-studio" data-challenge-id="${esc(state.challenge_id)}">
      <header class="pas-header"><div><span class="pas-kicker">POCKET ANIMATION STUDIO / VISUAL PROGRAMMING</span><h1>Make the scene move.</h1></div><div class="pas-brief"><strong>${esc(state.reference.title)}</strong><p>${esc(state.prompt)}</p></div><div class="pas-chip">${simplified ? "SIMPLIFIED" : "FULL"}<small>INPUT SURFACE</small></div></header>
      <main class="pas-workbench">
        <section class="pas-canvas-card"><div class="pas-card-title"><span>01 / REFERENCE WINDOW</span><button id="pas-ref-toggle" type="button">PAUSE REFERENCE</button></div><canvas id="pas-reference" width="460" height="270" aria-label="Animated reference scene"></canvas><div class="pas-track"><i class="pas-ref-progress"></i></div><div class="pas-card-note">REFERENCE LOOP / FULL DURATION</div></section>
        <section class="pas-canvas-card pas-preview-card"><div class="pas-card-title"><span>02 / YOUR PREVIEW</span><strong class="pas-drift-value">NO PROGRAM</strong></div><div class="pas-canvas-wrap"><canvas id="pas-preview" width="460" height="270" aria-label="Your animated preview"></canvas><div class="pas-preview-overlay">EMPTY PREVIEW<small>BUILD A PROGRAM BELOW</small></div></div><div class="pas-track"><i class="pas-preview-progress"></i></div><div class="pas-drift-meter"><i></i></div></section>
      </main>
      <section class="pas-editor"><aside class="pas-palette"><div class="pas-section-label">BLOCK PALETTE</div><p>${esc(description)}</p><div class="pas-palette-label">DRAWING</div><div class="pas-block-row">${shapeBlocks}</div><div class="pas-palette-label">EXPRESSIONS</div><div class="pas-block-row">${expressionBlocks}</div>${proxyShapeButtons}<div class="pas-legend"><span><i class="legend-pen"></i> drawing layer</span><span><i class="legend-socket"></i> expression socket</span></div></aside><section class="pas-program"><div class="pas-program-head"><div><div class="pas-section-label">PROGRAM STACK</div><h2>Drop the choreography here.</h2></div><span class="pas-block-count">0 / ${esc(state.studio.shapes.length)} SHAPES</span></div><div id="pas-program-stack" class="pas-program-stack"></div></section></section>
      <footer class="pas-footer"><div class="pas-readout" data-status="idle">READY / STUDY THE REFERENCE LOOP</div><div class="pas-actions"><button id="pas-reset" type="button">CLEAR PROGRAM</button><button id="pas-run" class="pas-run" type="button">RUN FULL PREVIEW</button><button id="pas-certify" class="pas-certify" type="button">CERTIFY MATCH</button></div></footer>
    </section>`;
    bindPalette();
    renderProgram();
    installReferenceLoop();
  }

  window.pocketAnimationStudioModel = model;
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {rootSelector: ".pocket-animation-studio", render};
})();
