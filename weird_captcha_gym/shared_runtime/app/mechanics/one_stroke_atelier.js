(() => {
  "use strict";
  let model = null;
  const clean = value => String(value == null ? "" : value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const arrows = {right: "→", left: "←", up: "↑", down: "↓"};
  const labels = {tool: "TOOL", colour: "COLOUR", width: "WIDTH", stamp: "STAMP", burnish: "BURNISH"};
  const key = () => `${model.phase}|${model.prefix.join("/")}`;

  function record(kind, details = {}) {
    const sources = model.interaction === "full"
      ? {stroke_start: "direct_stroke", gate_cross: "direct_stroke", motif_sample: "direct_stroke", stroke_end: "direct_stroke"}
      : {stroke_start: "proxy_stroke", gate_cross: "proxy_gate", motif_sample: "proxy_motif", stroke_end: "proxy_stroke"};
    model.events.push({sequence: model.events.length + 1, kind, input_source: sources[kind], ...details});
  }
  function stagePoint(event) {
    const stage = document.querySelector(".atelier-stage"), rect = stage.getBoundingClientRect();
    return [
      Math.max(0, Math.min(model.state.stage.width, Math.round((event.clientX - rect.left - stage.clientLeft) / stage.clientWidth * model.state.stage.width))),
      Math.max(0, Math.min(model.state.stage.height, Math.round((event.clientY - rect.top - stage.clientTop) / stage.clientHeight * model.state.stage.height))),
    ];
  }
  function pointSegmentDistance(point, first, second) {
    const vx = second[0] - first[0], vy = second[1] - first[1], lengthSq = vx * vx + vy * vy;
    const t = lengthSq ? Math.max(0, Math.min(1, ((point[0] - first[0]) * vx + (point[1] - first[1]) * vy) / lengthSq)) : 0;
    const projection = [first[0] + vx * t, first[1] + vy * t];
    return {distance: distance(point, projection), projection};
  }
  function crossing(first, second, gate) {
    const [x, y] = gate.center, half = gate.hit_half_length ?? gate.half_length + gate.tolerance;
    if (gate.orientation === "vertical") {
      const delta = second[0] - first[0];
      if (!delta || (gate.direction === "right" && delta <= 0) || (gate.direction === "left" && delta >= 0)) return null;
      if (x < Math.min(first[0], second[0]) || x > Math.max(first[0], second[0])) return null;
      const t = (x - first[0]) / delta, iy = first[1] + t * (second[1] - first[1]);
      return Math.abs(iy - y) <= half ? t : null;
    }
    const delta = second[1] - first[1];
    if (!delta || (gate.direction === "down" && delta <= 0) || (gate.direction === "up" && delta >= 0)) return null;
    if (y < Math.min(first[1], second[1]) || y > Math.max(first[1], second[1])) return null;
    const t = (y - first[1]) / delta, ix = first[0] + t * (second[0] - first[0]);
    return Math.abs(ix - x) <= half ? t : null;
  }
  function hitsLockedBar(first, second, gate) {
    const [x, y] = gate.center, along = gate.hit_half_length ?? gate.half_length + gate.tolerance;
    const halfX = gate.orientation === "vertical" ? 9 : along;
    const halfY = gate.orientation === "vertical" ? along : 9;
    const bounds = [[x - halfX, x + halfX], [y - halfY, y + halfY]];
    const delta = [second[0] - first[0], second[1] - first[1]];
    let low = 0, high = 1;
    for (let axis = 0; axis < 2; axis += 1) {
      if (Math.abs(delta[axis]) < 1e-9) {
        if (first[axis] < bounds[axis][0] || first[axis] > bounds[axis][1]) return false;
        continue;
      }
      let enter = (bounds[axis][0] - first[axis]) / delta[axis];
      let leave = (bounds[axis][1] - first[axis]) / delta[axis];
      if (enter > leave) [enter, leave] = [leave, enter];
      low = Math.max(low, enter); high = Math.min(high, leave);
      if (low > high) return false;
    }
    return true;
  }
  function currentGates() { return model.state.gate_sets[key()] || []; }
  function appendInk(point) {
    model.ink.push(point);
    const polyline = document.querySelector(".atelier-ink");
    if (polyline) polyline.setAttribute("points", model.ink.map(item => item.join(",")).join(" "));
  }
  function updateReceipt() {
    document.querySelectorAll(".atelier-receipt-row").forEach(row => {
      const field = row.dataset.field, value = model.selected[field];
      row.dataset.filled = value ? "true" : "false";
      const output = row.querySelector("b");
      if (output) output.textContent = value ? value.toUpperCase() : "—";
    });
    const count = document.querySelector(".atelier-stroke-count");
    if (count) count.textContent = `${model.strokeCount}/${model.state.stroke_budget}`;
  }
  function gateMarkup(gate, locked = false) {
    const along = gate.hit_half_length ?? gate.half_length + gate.tolerance;
    const width = gate.orientation === "horizontal" ? along * 2 : 18;
    const height = gate.orientation === "vertical" ? along * 2 : 18;
    return `<div class="atelier-gate atelier-gate--${gate.orientation}${locked ? " atelier-gate--locked" : ""}" data-gate-id="${clean(gate.id)}" data-direction="${gate.direction}" data-locked="${locked}" style="left:${gate.center[0] / model.state.stage.width * 100}%;top:${gate.center[1] / model.state.stage.height * 100}%;width:${width / model.state.stage.width * 100}%;height:${height / model.state.stage.height * 100}%;--swatch:${clean(gate.swatch || "#d1ab58")}"><i></i><span class="atelier-glyph">${clean(gate.glyph)}</span><strong>${clean(gate.label)}</strong><em>${locked ? "×" : arrows[gate.direction]}</em></div>`;
  }
  function motifMarkup() {
    const points = model.state.motif.points;
    return `<svg class="atelier-jig" viewBox="0 0 ${model.state.stage.width} ${model.state.stage.height}" aria-label="badge tracing jig"><polyline points="${points.map(item => item.join(",")).join(" ")}"/></svg>${points.map((point, index) => `<button type="button" class="atelier-checkpoint" data-index="${index}" data-active="${index === model.motifIndex}" style="left:${point[0] / model.state.stage.width * 100}%;top:${point[1] / model.state.stage.height * 100}%"><span>${index === points.length - 1 ? "FINISH" : index + 1}</span></button>`).join("")}`;
  }
  function bindDynamic() {
    return;
  }
  function renderDynamic() {
    const layer = document.querySelector(".atelier-dynamic");
    if (!layer) return;
    const locked = `<div class="atelier-locked-layer">${model.lockedGates.map(gate => gateMarkup(gate, true)).join("")}</div>`;
    if (model.phase < model.state.active_fields.length) {
      const field = model.state.active_fields[model.phase];
      layer.innerHTML = `${locked}<div class="atelier-bank-title"><b>${labels[field]}</b></div>${currentGates().map(gate => gateMarkup(gate)).join("")}`;
    } else {
      layer.innerHTML = `${locked}<div class="atelier-bank-title atelier-bank-title--jig"><b>MOTIF</b></div>${motifMarkup()}`;
    }
    bindDynamic();
    updateReceipt();
  }
  function activateGate(gate, before, after, pathSegment = null) {
    const field = model.state.active_fields[model.phase];
    record("gate_cross", {stroke: model.strokeCount, gate_id: gate.id, field, value: gate.value, direction: gate.direction, before, after, path_segment: pathSegment});
    model.selected[field] = gate.value;
    model.prefix.push(gate.value);
    if (model.state.locked_gate_memory > 0) {
      model.lockedGates.push({...gate});
      model.lockedGates = model.lockedGates.slice(-model.state.locked_gate_memory);
    }
    model.phase += 1;
    renderDynamic();
    model.helpers.setReadout(clean(gate.label), "pending");
  }
  function reachMotif(point, pathSegment = null) {
    const index = model.motifIndex;
    if (!model.motifTrace.length || distance(model.motifTrace.at(-1), point) > 1) model.motifTrace.push(point);
    record("motif_sample", {stroke: model.strokeCount, checkpoint: index, point, path_segment: pathSegment});
    model.motifIndex += 1;
    renderDynamic();
    model.helpers.setReadout("MOTIF", "pending");
  }
  function moveStroke(point) {
    if (!model.inStroke) return;
    const before = model.lastPoint;
    appendInk(point);
    const pathSegment = model.ink.length - 2;
    const lockedHit = model.lockedGates.find(gate => hitsLockedBar(before, point, gate));
    if (model.invalid || lockedHit) {
      if (lockedHit && !model.invalid) model.routeViolations.push({kind: "locked_bar", gate_id: lockedHit.id, before, after: point});
      model.invalid = true;
      model.lastPoint = point;
      document.querySelector(".atelier-stage")?.setAttribute("data-invalid", "true");
      model.helpers.setReadout("FAIL", "error");
      return;
    }
    if (model.phase < model.state.active_fields.length) {
      const hits = currentGates().map(gate => ({gate, t: crossing(before, point, gate)})).filter(item => item.t != null).sort((a, b) => a.t - b.t);
      if (hits.length) activateGate(hits[0].gate, before, point, pathSegment);
    } else if (model.motifIndex < model.state.motif.points.length) {
      const expected = model.state.motif.points[model.motifIndex], hit = pointSegmentDistance(expected, before, point);
      if (model.motifIndex > 0) model.motifTrace.push(point);
      if (hit.distance <= model.state.motif.tolerance) reachMotif(hit.projection.map(Math.round), pathSegment);
    }
    model.lastPoint = point;
  }
  function startStroke(point, event = null) {
    if (model.inStroke || model.completed || model.submitting || model.strokeCount >= model.state.stroke_budget) return;
    if (distance(point, model.state.start) > 38) return;
    model.strokeCount += 1;
    model.inStroke = true;
    model.lastPoint = point;
    model.phase = 0;
    model.prefix = [];
    model.selected = {};
    model.motifIndex = 0;
    model.motifTrace = [];
    model.lockedGates = [];
    model.ink = [point];
    model.events = [];
    model.routeViolations = [];
    model.invalid = false;
    record("stroke_start", {stroke: model.strokeCount, point, path_index: 0});
    if (event) {
      event.preventDefault();
      model.activePointerId = event.pointerId;
      document.querySelector(".atelier-stage").setPointerCapture(event.pointerId);
    }
    document.querySelector(".atelier-stage")?.setAttribute("data-stroking", "true");
    document.querySelector(".atelier-stage")?.setAttribute("data-invalid", "false");
    renderDynamic();
    model.helpers.setReadout("STROKE", "pending");
  }
  function resetForRetry() {
    model.phase = 0; model.prefix = []; model.selected = {}; model.motifIndex = 0; model.motifTrace = []; model.lockedGates = []; model.ink = []; model.events = []; model.routeViolations = []; model.invalid = false; model.completed = false;
    document.querySelector(".atelier-ink")?.setAttribute("points", "");
    document.querySelector(".atelier-stage")?.setAttribute("data-invalid", "false");
    document.querySelector(".atelier-shell")?.setAttribute("data-complete", "false");
    const submitButton = document.querySelector(".atelier-submit");
    if (submitButton) submitButton.disabled = true;
    renderDynamic();
  }
  function cancelStroke(termination) {
    if (!model.inStroke) return;
    model.interruptions.push({sequence: model.interruptions.length + 1, kind: "stroke_cancel", input_source: "direct_stroke", termination, stroke: model.strokeCount, complete: false});
    model.inStroke = false;
    model.activePointerId = null;
    model.strokeCount = Math.max(0, model.strokeCount - 1);
    document.querySelector(".atelier-stage")?.setAttribute("data-stroking", "false");
    resetForRetry();
    model.helpers.setReadout("FAIL", "error");
    updateReceipt();
  }
  function endStroke(point, termination) {
    if (!model.inStroke) return;
    if (model.interaction === "full" && distance(model.lastPoint, point) > 0) {
      appendInk(point);
      model.lastPoint = point;
    }
    const last = model.state.motif.points.at(-1), complete = !model.invalid && model.motifIndex === model.state.motif.points.length && distance(point, last) <= model.state.motif.tolerance;
    record("stroke_end", {stroke: model.strokeCount, point, complete, termination, path_index: model.ink.length - 1});
    model.inStroke = false;
    model.activePointerId = null;
    document.querySelector(".atelier-stage")?.setAttribute("data-stroking", "false");
    if (complete) {
      model.completed = true;
      document.querySelector(".atelier-shell")?.setAttribute("data-complete", "true");
      document.querySelector(".atelier-submit").disabled = false;
      model.helpers.setReadout("READY", "passed");
    } else if (model.strokeCount < model.state.stroke_budget) {
      resetForRetry();
      model.helpers.setReadout("FAIL", "error");
    } else {
      document.querySelector(".atelier-submit").disabled = false;
      model.helpers.setReadout("FAIL", "error");
    }
    updateReceipt();
  }
  function proxyStart() { startStroke(model.state.start); }
  function proxyEnd() {
    endStroke(model.lastPoint || model.state.start, "proxy_end");
  }
  async function submit() {
    if (model.submitting || model.terminal || (!model.completed && model.strokeCount < model.state.stroke_budget)) return;
    model.submitting = true;
    model.helpers.setReadout("READY", "pending");
    const payload = {mechanic_id: model.state.mechanic_id, challenge_id: model.state.challenge_id, interaction: model.interaction, events: model.events, interruptions: model.interruptions, route_violations: model.routeViolations, selected_fields: model.selected, drawn_geometry: model.motifTrace, stroke_geometry: model.ink, stroke_count: model.strokeCount, completed: model.completed};
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true;
        document.querySelector(".atelier-shell")?.insertAdjacentHTML("beforeend", '<div class="atelier-verdict"><strong>PASS</strong></div>');
        model.helpers.setReadout("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        const shell = document.querySelector(".atelier-shell");
        shell?.setAttribute("data-fresh-failure", "true");
        shell?.insertAdjacentHTML("afterbegin", '<div class="atelier-failure"><b>FAIL</b></div>');
        model.helpers.setReadout("FAIL", "error");
      } else throw new Error("authoritative grade unavailable");
    } catch (_error) {
      model.submitting = false;
      document.querySelector(".atelier-submit").disabled = false;
      model.helpers.setReadout("READY", "idle");
    }
  }
  function targetMarkup(item) {
    return `<div class="atelier-target-field"><span>${labels[item.field]}</span><b>${clean(item.glyph)} ${clean(item.label)}</b>${item.swatch ? `<i style="background:${clean(item.swatch)}"></i>` : ""}</div>`;
  }
  async function render(state, helpers) {
    document.body.dataset.mechanic = "one-stroke-atelier";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const interaction = state.control_condition?.interaction || "full", motif = state.motif.points;
    model = {state, helpers, interaction, events: [], interruptions: [], routeViolations: [], phase: 0, prefix: [], selected: {}, motifIndex: 0, motifTrace: [], lockedGates: [], ink: [], lastPoint: null, activePointerId: null, inStroke: false, invalid: false, strokeCount: 0, completed: false, submitting: false, terminal: false};
    window.oneStrokeAtelierModel = model;
    helpers.app.innerHTML = `<section class="atelier-shell" data-challenge-id="${clean(state.challenge_id)}" data-interaction="${interaction}" data-complete="false"><header class="atelier-header"><div><span>MAISON VERVAIN · ENAMEL ROOM</span><h1>One-Stroke Atelier</h1><p>${clean(state.prompt)}</p></div><div class="atelier-commission"><span>COMMISSION</span><b>No. ${clean(state.challenge_id)}</b><small>${interaction === "full" ? "DIRECT LATHE" : "PROXY CONSOLE"}</small></div></header><main class="atelier-main"><aside class="atelier-target"><div class="atelier-target-head"><span>TARGET</span></div><div class="atelier-badge"><svg viewBox="580 200 310 150"><polyline points="${motif.map(item => item.join(",")).join(" ")}"/></svg><i>${clean(state.target.find(item => item.field === "stamp")?.glyph || "✦")}</i></div><div class="atelier-target-fields">${state.target.map(targetMarkup).join("")}</div></aside><section class="atelier-bench"><div class="atelier-stage" data-stroking="false" data-invalid="false"><div class="atelier-grain"></div><svg class="atelier-ink-svg" viewBox="0 0 ${state.stage.width} ${state.stage.height}"><polyline class="atelier-ink" points=""/></svg><div class="atelier-start" style="left:${state.start[0] / state.stage.width * 100}%;top:${state.start[1] / state.stage.height * 100}%"><i></i><b>START</b><span>${interaction === "full" ? "HOLD" : "PROXY"}</span></div><div class="atelier-dynamic"></div></div><div class="atelier-controls">${interaction === "simplified" ? '<button type="button" class="atelier-proxy-start">BEGIN</button><button type="button" class="atelier-proxy-end">END</button>' : ''}<div class="atelier-readout"><span>STATUS</span><div class="readout" data-status="idle">READY</div></div></div></section><aside class="atelier-ledger"><div class="atelier-ledger-head"><span>RECEIPT</span><b>STROKE <i class="atelier-stroke-count">0/${state.stroke_budget}</i></b></div>${state.active_fields.map(field => `<div class="atelier-receipt-row" data-field="${field}" data-filled="false"><span>${labels[field]}</span><b>—</b></div>`).join("")}<button type="button" class="atelier-submit" disabled>${clean(state.submit_label)}</button></aside></main>${helpers.cheatPanelTemplate()}</section>`;
    const stage = document.querySelector(".atelier-stage");
    if (interaction === "full") {
      stage.addEventListener("pointerdown", event => { if (event.button === 0) startStroke(stagePoint(event), event); });
      stage.addEventListener("pointermove", event => moveStroke(stagePoint(event)));
      stage.addEventListener("pointerup", event => endStroke(stagePoint(event), "pointerup"));
      stage.addEventListener("pointercancel", () => cancelStroke("pointercancel"));
      stage.addEventListener("lostpointercapture", () => cancelStroke("lostpointercapture"));
    } else {
      document.querySelector(".atelier-proxy-start").addEventListener("click", proxyStart);
      document.querySelector(".atelier-proxy-end").addEventListener("click", proxyEnd);
      stage.addEventListener("click", event => moveStroke(stagePoint(event)));
    }
    document.querySelector(".atelier-submit").addEventListener("click", submit);
    renderDynamic();
    helpers.installCheatPanel();
  }
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.one_stroke_atelier = {rootSelector: ".atelier-shell", render};
})();
