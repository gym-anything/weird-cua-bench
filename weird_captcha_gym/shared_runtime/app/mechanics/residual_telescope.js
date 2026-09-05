(() => {
  "use strict";

  let model = null;
  const clean = value => String(value == null ? "" : value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const distance = (first, second) => Math.hypot(first[0] - second[0], first[1] - second[1]);

  function segmentDistance(x, y, first, second) {
    const vx = second[0] - first[0], vy = second[1] - first[1];
    const lengthSq = vx * vx + vy * vy;
    const amount = lengthSq <= 0 ? 0 : clamp(((x - first[0]) * vx + (y - first[1]) * vy) / lengthSq, 0, 1);
    return Math.hypot(x - (first[0] + amount * vx), y - (first[1] + amount * vy));
  }

  function derive(component, points) {
    if (component.startsWith("arm_")) return points.map(point => [...point]);
    const first = points[0], second = points[1];
    const angle = Math.atan2(second[1] - first[1], second[0] - first[0]);
    if (component === "disc" || component === "core") {
      return {center: [...first], radius: distance(first, second), angle};
    }
    return {center: [(first[0] + second[0]) / 2, (first[1] + second[1]) / 2], length: distance(first, second), width: 2.75, angle};
  }

  function activeComponent() {
    return model.redrawComponent || model.state.component_sequence[model.shapeIndex] || null;
  }

  function geometryForRender() {
    const geometry = {...model.geometry, arms: model.geometry.arms.map(points => points.map(point => [...point]))};
    const component = activeComponent();
    if (!component || model.draft.length < 2) return geometry;
    const preview = derive(component, model.draft);
    if (component.startsWith("arm_")) geometry.arms[Number(component.split("_")[1]) - 1] = preview;
    else geometry[component] = preview;
    return geometry;
  }

  function renderField(geometry, values) {
    const width = model.state.image.width, height = model.state.image.height;
    const pixels = [];
    const disc = geometry.disc, core = geometry.core, bar = geometry.bar, arms = geometry.arms || [];
    const discCenter = disc?.center || [width / 2, height / 2], discRadius = Math.max(1, Number(disc?.radius || 18));
    for (let row = 0; row < height; row += 1) {
      const line = [];
      for (let column = 0; column < width; column += 1) {
        const x = column + 0.5, y = row + 0.5;
        let light = 0.016;
        if (disc) {
          const dx = x - disc.center[0], dy = y - disc.center[1], cosine = Math.cos(disc.angle), sine = Math.sin(disc.angle);
          const xr = cosine * dx + sine * dy, yr = -sine * dx + cosine * dy;
          const extent = 0.76 + values.disc_extent * 0.052, falloff = 1.48 - values.disc_falloff * 0.055;
          const elliptical = Math.hypot(xr, yr / 0.61) / Math.max(1, disc.radius * extent);
          light += (0.11 + values.disc_brightness * 0.039) * Math.exp(-elliptical * 2.05 * falloff);
        }
        if (core) {
          const dx = x - core.center[0], dy = y - core.center[1], cosine = Math.cos(core.angle), sine = Math.sin(core.angle);
          const xr = cosine * dx + sine * dy, yr = -sine * dx + cosine * dy;
          const elliptical = Math.hypot(xr, yr / 0.78) / Math.max(1, core.radius);
          const concentration = 1.18 + values.core_concentration * 0.18;
          light += (0.13 + values.core_brightness * 0.044) * Math.exp(-(elliptical ** concentration) * 1.8);
        }
        if (bar) {
          const dx = x - bar.center[0], dy = y - bar.center[1], cosine = Math.cos(bar.angle), sine = Math.sin(bar.angle);
          const xr = Math.abs(cosine * dx + sine * dy) / Math.max(1, bar.length / 2);
          const yr = Math.abs(-sine * dx + cosine * dy) / Math.max(1, bar.width);
          const power = 1.45 + values.bar_boxiness * 0.22;
          const norm = (xr ** power + yr ** power) ** (1 / power);
          light += (0.08 + values.bar_brightness * 0.034) * Math.exp(-(norm ** 3.2) * 2.2);
        }
        if (arms.length) {
          const spread = 1.05 + values.arms_spread * 0.25;
          const radial = Math.hypot(x - discCenter[0], y - discCenter[1]) / discRadius;
          const radialFalloff = 0.58 + values.arms_falloff * 0.065;
          for (const points of arms) {
            let nearest = Infinity;
            for (let index = 0; index + 1 < points.length; index += 1) nearest = Math.min(nearest, segmentDistance(x, y, points[index], points[index + 1]));
            light += (0.045 + values.arms_brightness * 0.018) * Math.exp(-(nearest ** 2) / (2 * spread ** 2)) * Math.exp(-radial * radialFalloff);
          }
        }
        line.push(clamp(light, 0, 1));
      }
      pixels.push(line);
    }
    return pixels;
  }

  function paintRaster(canvas, pixels, palette) {
    const width = model.state.image.width, height = model.state.image.height;
    const scratch = document.createElement("canvas");
    scratch.width = width; scratch.height = height;
    const context = scratch.getContext("2d"), image = context.createImageData(width, height);
    for (let row = 0; row < height; row += 1) {
      for (let column = 0; column < width; column += 1) {
        const rgb = palette(pixels[row][column], row, column), offset = (row * width + column) * 4;
        image.data[offset] = rgb[0]; image.data[offset + 1] = rgb[1]; image.data[offset + 2] = rgb[2]; image.data[offset + 3] = 255;
      }
    }
    context.putImageData(image, 0, 0);
    const target = canvas.getContext("2d");
    target.clearRect(0, 0, canvas.width, canvas.height);
    target.imageSmoothingEnabled = true;
    target.drawImage(scratch, 0, 0, canvas.width, canvas.height);
  }

  function residual(modelPixels) {
    const target = model.state.target_pixels, values = [];
    let squared = 0, count = 0;
    for (let row = 0; row < target.length; row += 1) {
      const line = [];
      for (let column = 0; column < target[row].length; column += 1) {
        const value = target[row][column] - modelPixels[row][column];
        line.push(value); squared += value * value; count += 1;
      }
      values.push(line);
    }
    return {values, rms: Math.sqrt(squared / Math.max(1, count))};
  }

  function drawOverlay(canvas) {
    const context = canvas.getContext("2d"), sx = canvas.width / model.state.image.width, sy = canvas.height / model.state.image.height;
    context.save(); context.scale(sx, sy); context.lineWidth = 0.45; context.strokeStyle = "rgba(115, 241, 218, .72)"; context.fillStyle = "rgba(115, 241, 218, .13)";
    const shapes = geometryForRender();
    for (const name of ["disc", "core"]) {
      const shape = shapes[name]; if (!shape) continue;
      context.save(); context.translate(shape.center[0], shape.center[1]); context.rotate(shape.angle); context.beginPath();
      context.ellipse(0, 0, shape.radius, shape.radius * (name === "disc" ? 0.61 : 0.78), 0, 0, Math.PI * 2); context.stroke(); context.restore();
    }
    if (shapes.bar) {
      context.save(); context.translate(shapes.bar.center[0], shapes.bar.center[1]); context.rotate(shapes.bar.angle); context.strokeRect(-shapes.bar.length / 2, -shapes.bar.width, shapes.bar.length, shapes.bar.width * 2); context.restore();
    }
    for (const points of shapes.arms) {
      context.beginPath(); points.forEach((point, index) => index ? context.lineTo(point[0], point[1]) : context.moveTo(point[0], point[1])); context.stroke();
    }
    if (model.draft.length) {
      context.strokeStyle = "rgba(255, 244, 196, .95)"; context.setLineDash([1.1, 1]); context.beginPath();
      model.draft.forEach((point, index) => index ? context.lineTo(point[0], point[1]) : context.moveTo(point[0], point[1])); context.stroke(); context.setLineDash([]);
      for (const point of model.draft) { context.beginPath(); context.arc(point[0], point[1], .6, 0, Math.PI * 2); context.fill(); }
    }
    context.restore();
  }

  function updateCanvases() {
    const targetCanvas = document.querySelector(".residual-target-canvas"), modelCanvas = document.querySelector(".residual-model-canvas"), residualCanvas = document.querySelector(".residual-difference-canvas");
    if (!targetCanvas || !modelCanvas || !residualCanvas) return;
    const computed = renderField(geometryForRender(), model.values), difference = residual(computed);
    model.rms = difference.rms;
    paintRaster(targetCanvas, model.state.target_pixels, value => {
      const glow = clamp(value, 0, 1); return [Math.round(9 + glow * 242), Math.round(14 + glow * 216), Math.round(22 + glow * 152)];
    });
    paintRaster(modelCanvas, computed, value => {
      const glow = clamp(value, 0, 1); return [Math.round(5 + glow * 88), Math.round(18 + glow * 228), Math.round(22 + glow * 204)];
    });
    paintRaster(residualCanvas, difference.values, value => {
      const strength = clamp(Math.abs(value) * 5.2, 0, 1);
      return value >= 0
        ? [Math.round(11 + strength * 244), Math.round(14 + strength * 139), Math.round(24 + strength * 40)]
        : [Math.round(11 + strength * 85), Math.round(14 + strength * 42), Math.round(24 + strength * 229)];
    });
    drawOverlay(modelCanvas);
    const quiet = model.shapesComplete && !model.redrawComponent && !model.drawing && model.rms <= model.state.residual_threshold;
    const residualState = quiet ? "quiet" : model.rms < model.state.residual_threshold * 3 ? "narrow" : "loud";
    const shell = document.querySelector(".residual-shell");
    shell?.setAttribute("data-residual-state", residualState);
    const meter = document.querySelector(".residual-meter i");
    if (meter) meter.style.width = `${clamp(100 - model.rms * 780, 4, 100)}%`;
    const word = document.querySelector(".residual-meter b");
    if (word) word.textContent = quiet ? "QUIET" : residualState === "narrow" ? "NARROW" : "LOUD";
    updateReady();
  }

  function updateReady() {
    const tuned = model.seenParameters.size === model.state.parameter_specs.length;
    const complete = model.shapesComplete && !model.redrawComponent && !model.drawing && tuned && model.rms <= model.state.residual_threshold;
    model.completed = complete;
    const shell = document.querySelector(".residual-shell"), submit = document.querySelector(".residual-submit");
    shell?.setAttribute("data-complete", String(complete));
    if (submit) submit.disabled = !(tuned && model.shapesComplete) || Boolean(model.redrawComponent) || model.drawing || model.submitting || model.terminal;
  }

  function updateLedger() {
    document.querySelectorAll(".residual-component-row").forEach((row, index) => {
      const state = model.redrawComponent === row.dataset.component ? "active" : index < model.shapeIndex ? "done" : index === model.shapeIndex ? "active" : "locked";
      row.setAttribute("data-state", state);
    });
    const moves = document.querySelector(".residual-move-count"); if (moves) moves.textContent = `${model.events.length}/${model.state.move_budget}`;
    const optics = document.querySelector(".residual-optics"); if (optics) optics.setAttribute("data-locked", String(!model.shapesComplete));
    document.querySelectorAll(".residual-slider-track, .residual-nudge").forEach(element => { element.disabled = !model.shapesComplete || model.events.length >= model.state.move_budget; });
    document.querySelectorAll(".residual-redraw").forEach(element => { element.disabled = model.drawing || model.events.length >= model.state.move_budget; });
    updateReady();
  }

  function record(kind, details) {
    if (model.events.length >= model.state.move_budget) return false;
    model.events.push({sequence: model.events.length + 1, kind, ...details});
    updateLedger(); return true;
  }

  function commitShape(points) {
    const component = activeComponent();
    if (!component || points.length < 2) return;
    const source = model.interaction === "full" ? "direct_draw" : "proxy_points";
    const normalized = points.map(point => point.map(value => Math.round(value * 100) / 100));
    if (!record("shape_commit", {component, input_source: source, points: normalized})) return;
    const shape = derive(component, normalized);
    const wasRedraw = Boolean(model.redrawComponent);
    if (component.startsWith("arm_")) {
      const armIndex = Number(component.split("_")[1]) - 1;
      if (wasRedraw) model.geometry.arms[armIndex] = shape; else model.geometry.arms.push(shape);
    } else model.geometry[component] = shape;
    if (wasRedraw) model.redrawComponent = null; else model.shapeIndex += 1;
    model.draft = []; model.shapesComplete = model.shapeIndex === model.state.component_sequence.length;
    updateLedger(); updateCanvases();
    model.helpers.setReadout("SET", "pending");
  }

  function canvasPoint(event) {
    const canvas = document.querySelector(".residual-model-canvas"), rect = canvas.getBoundingClientRect();
    return [
      clamp((event.clientX - rect.left) / rect.width * model.state.image.width, 0, model.state.image.width),
      clamp((event.clientY - rect.top) / rect.height * model.state.image.height, 0, model.state.image.height),
    ];
  }

  function installDrawing() {
    const canvas = document.querySelector(".residual-model-canvas");
    if (model.interaction === "full") {
      canvas.addEventListener("pointerdown", event => {
        if ((model.shapesComplete && !model.redrawComponent) || model.events.length >= model.state.move_budget) return;
        model.drawing = true; model.draft = [canvasPoint(event)]; canvas.setPointerCapture(event.pointerId); updateCanvases();
      });
      canvas.addEventListener("pointermove", event => {
        if (!model.drawing) return;
        const point = canvasPoint(event), component = activeComponent();
        if (component.startsWith("arm_")) {
          if (distance(point, model.draft.at(-1)) >= .7) model.draft.push(point);
        } else model.draft = [model.draft[0], point];
        updateCanvases();
      });
      const finish = event => {
        if (!model.drawing) return; model.drawing = false;
        const component = activeComponent(), point = canvasPoint(event);
        if (component?.startsWith("arm_")) {
          if (distance(point, model.draft.at(-1)) >= .2) model.draft.push(point);
        } else model.draft = [model.draft[0], point];
        if (model.draft.length >= (component?.startsWith("arm_") ? 4 : 2)) commitShape(model.draft); else { model.draft = []; updateCanvases(); }
      };
      canvas.addEventListener("pointerup", finish); canvas.addEventListener("pointercancel", finish);
    } else {
      canvas.addEventListener("click", event => {
        if ((model.shapesComplete && !model.redrawComponent) || model.events.length >= model.state.move_budget) return;
        const component = activeComponent(); model.draft.push(canvasPoint(event)); updateCanvases();
        const required = component.startsWith("arm_") ? model.state.arm_point_count : 2;
        if (model.draft.length >= required) commitShape(model.draft);
      });
    }
  }

  function setParameter(parameterId, value, source) {
    if (!model.shapesComplete || model.events.length >= model.state.move_budget) return false;
    value = clamp(Math.round(value), 0, 10);
    if (value === model.values[parameterId]) return false;
    if (Math.abs(value - model.values[parameterId]) !== 1) return false;
    model.values[parameterId] = value; model.seenParameters.add(parameterId);
    record("parameter_set", {parameter_id: parameterId, value, input_source: source});
    updateParameterMarkup(parameterId); updateCanvases();
    model.helpers.setReadout("SET", "pending");
    return true;
  }

  function updateParameterMarkup(parameterId) {
    const spec = model.state.parameter_specs.find(item => item.id === parameterId), value = model.values[parameterId];
    const row = document.querySelector(`.residual-parameter[data-parameter="${CSS.escape(parameterId)}"]`); if (!row) return;
    row.querySelector(".residual-parameter-value").textContent = value;
    const fill = row.querySelector(".residual-slider-fill"), handle = row.querySelector(".residual-slider-handle");
    const amount = (value - spec.minimum) / (spec.maximum - spec.minimum) * 100;
    if (fill) fill.style.width = `${amount}%`; if (handle) handle.style.left = `${amount}%`;
    row.setAttribute("data-tuned", String(model.seenParameters.has(parameterId)));
  }

  function installOptics() {
    if (model.interaction === "full") {
      document.querySelectorAll(".residual-slider-track").forEach(track => {
        let dragging = false;
        const apply = event => {
          const spec = model.state.parameter_specs.find(item => item.id === track.dataset.parameter), rect = track.getBoundingClientRect();
          const raw = spec.minimum + clamp((event.clientX - rect.left) / rect.width, 0, 1) * (spec.maximum - spec.minimum);
          const target = clamp(Math.round(raw), spec.minimum, spec.maximum);
          while (model.values[spec.id] !== target && model.events.length < model.state.move_budget) {
            const step = model.values[spec.id] + Math.sign(target - model.values[spec.id]);
            if (!setParameter(spec.id, step, "direct_slider")) break;
          }
        };
        track.addEventListener("pointerdown", event => {
          if (!model.shapesComplete || model.events.length >= model.state.move_budget) return;
          dragging = true; track.setPointerCapture(event.pointerId); apply(event);
        });
        track.addEventListener("pointermove", event => { if (dragging) apply(event); });
        track.addEventListener("pointerup", event => {
          if (!dragging) return; apply(event); dragging = false;
        });
        track.addEventListener("pointercancel", () => { dragging = false; });
      });
    } else {
      document.querySelectorAll(".residual-nudge").forEach(button => button.addEventListener("click", () => setParameter(button.dataset.parameter, model.values[button.dataset.parameter] + Number(button.dataset.delta), "proxy_nudge")));
    }
  }

  function installRedraw() {
    document.querySelectorAll(".residual-redraw").forEach(button => button.addEventListener("click", () => {
      if (model.state.component_sequence.indexOf(button.dataset.component) >= model.shapeIndex || model.drawing || model.events.length >= model.state.move_budget) return;
      model.redrawComponent = button.dataset.component; model.draft = []; updateLedger(); updateCanvases();
      model.helpers.setReadout("REDRAW", "pending");
    }));
  }

  function parameterMarkup(spec) {
    const amount = (spec.initial - spec.minimum) / (spec.maximum - spec.minimum) * 100;
    const control = model.interaction === "full"
      ? `<button type="button" class="residual-slider-track" data-parameter="${clean(spec.id)}" aria-label="${clean(spec.label)} slider"><i class="residual-slider-fill" style="width:${amount}%"></i><b class="residual-slider-handle" style="left:${amount}%"></b></button>`
      : `<div class="residual-nudge-pair"><button type="button" class="residual-nudge" data-parameter="${clean(spec.id)}" data-delta="-1" aria-label="Decrease ${clean(spec.label)}">−</button><i></i><button type="button" class="residual-nudge" data-parameter="${clean(spec.id)}" data-delta="1" aria-label="Increase ${clean(spec.label)}">+</button></div>`;
    return `<div class="residual-parameter" data-parameter="${clean(spec.id)}" data-component="${clean(spec.component)}" data-tuned="false"><span>${clean(spec.label)}</span><b class="residual-parameter-value">${spec.initial}</b>${control}</div>`;
  }

  async function submit() {
    if (model.submitting || model.terminal || !model.shapesComplete || model.seenParameters.size !== model.state.parameter_specs.length) return;
    model.submitting = true; updateReady(); model.helpers.setReadout("VERIFYING", "pending");
    const payload = {mechanic_id: model.state.mechanic_id, challenge_id: model.state.challenge_id, interaction: model.interaction, events: model.events, completed: model.completed};
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true; document.querySelector(".residual-shell")?.setAttribute("data-verdict", "passed");
        document.querySelector(".residual-shell")?.insertAdjacentHTML("beforeend", '<div class="residual-verdict"><strong>PASS</strong></div>');
        model.helpers.setReadout("PASS", "passed"); updateReady();
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state); const shell = document.querySelector(".residual-shell");
        shell?.setAttribute("data-fresh-failure", "true"); shell?.insertAdjacentHTML("afterbegin", '<div class="residual-failure"><b>FAIL</b></div>');
        model.helpers.setReadout("FAIL", "error");
      } else throw new Error("authoritative grade unavailable");
    } catch (_error) {
      model.submitting = false; updateReady(); model.helpers.setReadout("OFFLINE", "error");
    }
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "residual-telescope";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const interaction = state.control_condition?.interaction || "full";
    const values = {disc_brightness: 5, core_brightness: 5, disc_extent: 5, bar_brightness: 5, bar_boxiness: 5, core_concentration: 5, arms_brightness: 5, arms_spread: 5, disc_falloff: 5, arms_falloff: 5, ...state.initial_values};
    model = {state, helpers, interaction, values, geometry: {arms: []}, events: [], seenParameters: new Set(), shapeIndex: 0, shapesComplete: false, redrawComponent: null, draft: [], drawing: false, rms: Infinity, completed: false, submitting: false, terminal: false};
    window.residualTelescopeModel = model;
    helpers.app.innerHTML = `<section class="residual-shell" data-challenge-id="${clean(state.challenge_id)}" data-interaction="${clean(interaction)}" data-complete="false" data-residual-state="loud"><header class="residual-header"><div><span>THE LIMINAL OBSERVATORY · BAY 03</span><h1>The Residual Telescope</h1><p>${clean(state.prompt)}</p></div><div class="residual-ticket"><span>PLATE</span><b>${clean(state.challenge_id)}</b><small>${interaction === "full" ? "DIRECT OPTICAL BENCH" : "POINT / NUDGE CONSOLE"}</small></div></header><main class="residual-workspace"><section class="residual-imaging"><div class="residual-panels"><figure><figcaption><b>01</b><span>SOURCE</span></figcaption><div class="residual-plate"><canvas class="residual-target-canvas" width="244" height="244"></canvas><u></u></div></figure><figure><figcaption><b>02</b><span>MODEL</span></figcaption><div class="residual-plate residual-draw"><canvas class="residual-model-canvas" width="244" height="244"></canvas><u></u></div></figure><figure><figcaption><b>03</b><span>SIGNED DIFFERENCE</span><i><mark>+</mark><mark>−</mark></i></figcaption><div class="residual-plate"><canvas class="residual-difference-canvas" width="244" height="244"></canvas><u></u></div></figure></div><div class="residual-imaging-footer"><div class="residual-meter"><span>RESIDUAL</span><em><i></i></em><b>LOUD</b></div></div></section><aside class="residual-console"><div class="residual-console-head"><span>MASKS</span><b>MOVES <i class="residual-move-count">0/${state.move_budget}</i></b></div><div class="residual-component-ledger">${state.component_sequence.map((component, index) => `<div class="residual-component-row" data-component="${clean(component)}" data-state="${index === 0 ? "active" : "locked"}"><i>${String(index + 1).padStart(2, "0")}</i><span>${clean(component.replace("_", " ").toUpperCase())}</span><div><i class="residual-component-symbol" aria-hidden="true"></i><button type="button" class="residual-redraw" data-component="${clean(component)}" disabled>REDRAW</button></div></div>`).join("")}</div><section class="residual-optics" data-locked="true"><header><span>OPTICS</span><b aria-hidden="true"></b></header><div class="residual-parameter-list">${state.parameter_specs.map(parameterMarkup).join("")}</div></section><footer><div class="readout" data-status="idle">READY</div><button type="button" class="residual-submit" disabled>${clean(state.submit_label)}</button></footer></aside></main>${helpers.cheatPanelTemplate()}</section>`;
    installDrawing(); installOptics(); installRedraw(); document.querySelector(".residual-submit").addEventListener("click", submit);
    updateLedger(); updateCanvases(); helpers.installCheatPanel();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.residual_telescope = {rootSelector: ".residual-shell", render};
})();
