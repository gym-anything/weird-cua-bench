(() => {
  "use strict";

  let model = null;
  const clean = (value) => String(value == null ? "" : value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const observationKey = (blotId, tool) => `${blotId}|${tool}`;

  function record(kind, details = {}) {
    const event = {sequence: model.events.length + 1, kind, ...details};
    model.events.push(event);
    return event;
  }

  function stagePoint(event) {
    const rect = document.querySelector(".ink-stage").getBoundingClientRect();
    return [
      Math.max(0, Math.min(model.state.stage.width, Math.round((event.clientX - rect.left) / rect.width * model.state.stage.width))),
      Math.max(0, Math.min(model.state.stage.height, Math.round((event.clientY - rect.top) / rect.height * model.state.stage.height))),
    ];
  }

  function inside(point, rect) {
    return point[0] >= rect.x && point[0] <= rect.x + rect.width && point[1] >= rect.y && point[1] <= rect.y + rect.height;
  }

  function cycleFor(blotId, tool) {
    return model.state.cycles.find((item) => item.blot_id === blotId && item.tool === tool);
  }

  function isRequired(tool) {
    return model.state.required_tools.includes(tool);
  }

  function isObserved(blotId, tool) {
    return model.observations.has(observationKey(blotId, tool));
  }

  function updateUI() {
    document.querySelectorAll(".ink-card").forEach((card) => {
      card.dataset.selected = card.dataset.blotId === model.selectedId ? "true" : "false";
    });
    document.querySelectorAll(".ink-tool").forEach((node) => {
      const tool = node.dataset.tool;
      const disabled = !model.selectedId || model.active || model.terminal || !isRequired(tool) || isObserved(model.selectedId, tool);
      if ("disabled" in node) node.disabled = disabled;
      node.classList.toggle("is-disabled", disabled);
      node.classList.toggle("is-next", Boolean(model.selectedId) && isRequired(tool) && !isObserved(model.selectedId, tool) && !model.active);
    });
    for (const blot of model.state.blots) {
      for (const tool of model.state.required_tools) {
        const badge = document.querySelector(`.ink-observation[data-blot-id="${CSS.escape(blot.id)}"][data-tool="${tool}"]`);
        if (badge) badge.dataset.status = isObserved(blot.id, tool) ? "done" : "waiting";
      }
    }
    const count = model.observations.size;
    const progress = document.querySelector(".ink-observation-count");
    if (progress) progress.textContent = `${count}/${model.state.observations_required}`;
    const selected = document.querySelector(".ink-selected-specimen b");
    if (selected) selected.textContent = model.selectedId ? model.state.blots.find((item) => item.id === model.selectedId).specimen : "SELECT A CARD";
    const stamp = document.querySelector(".ink-stamp");
    if (stamp) stamp.dataset.ready = count === model.state.observations_required && !model.active ? "true" : "false";
  }

  function selectSpecimen(blotId) {
    if (model.active || model.fold || model.pressureStarted != null || model.terminal) return;
    document.querySelector(".ink-failure-stamp")?.remove();
    model.selectedId = blotId;
    record("select", {blot_id: blotId});
    updateUI();
    model.helpers.setReadout(`${blotId.toUpperCase()} LOADED · APPLY BOTH HIGHLIGHTED TOOLS`, "idle");
  }

  function applySnapshot(snapshot) {
    const blot = document.querySelector(`.ink-blot[data-blot-id="${CSS.escape(snapshot.blot_id)}"]`);
    if (!blot) return;
    blot.style.setProperty("--ink-left", String(snapshot.left / 100));
    blot.style.setProperty("--ink-right", String(snapshot.right / 100));
    blot.style.setProperty("--ink-fold", `${snapshot.fold}%`);
    blot.style.setProperty("--ink-hue", `${snapshot.hue}deg`);
    blot.style.setProperty("--ink-flow", `${snapshot.flow}deg`);
    blot.dataset.flow = String(snapshot.flow);
  }

  function responseLabel(tool, snapshot) {
    if (tool === "FOLD") return snapshot.fold > 40 ? "RETAIN" : "RELAX";
    if (tool === "PRESSURE") return Math.abs(snapshot.left - snapshot.right) < 3 ? "SYMM" : "SKEW";
    return snapshot.flow < 0 ? "INVERT" : "FLOW";
  }

  function finishCycle(cycle, startedAt) {
    const snapshot = cycle.frames.at(-1).snapshot;
    const badge = document.querySelector(`.ink-observation[data-blot-id="${CSS.escape(cycle.blot_id)}"][data-tool="${cycle.tool}"]`);
    if (badge) {
      badge.dataset.status = "done";
      badge.querySelector("b").textContent = responseLabel(cycle.tool, snapshot);
    }
    record("cycle_complete", {blot_id: cycle.blot_id, tool: cycle.tool, elapsed_ms: Math.round(performance.now() - startedAt)});
    model.observations.add(observationKey(cycle.blot_id, cycle.tool));
    model.active = false;
    model.timer = null;
    updateUI();
    const complete = model.observations.size === model.state.observations_required;
    model.helpers.setReadout(complete ? "ALL SPECIMEN RESPONSES ARCHIVED · DRAG THE STAMP" : `${cycle.blot_id.toUpperCase()} / ${cycle.tool} ARCHIVED`, complete ? "passed" : "idle");
  }

  function startProbe(tool) {
    const blotId = model.selectedId;
    const cycle = cycleFor(blotId, tool);
    if (!cycle || isObserved(blotId, tool)) return;
    record("probe", {blot_id: blotId, tool});
    model.active = true;
    updateUI();
    model.helpers.setReadout(`${blotId.toUpperCase()} / ${tool} TRANSIENT ACTIVE · WATCH THIS CARD`, "pending");
    const startedAt = performance.now();
    let tick = 0;
    model.timer = window.setInterval(() => {
      tick += 1;
      const frame = cycle.frames[tick - 1];
      applySnapshot(frame.snapshot);
      const elapsed = Math.max(Math.round(performance.now() - startedAt), tick * 65);
      record("tick", {blot_id: blotId, tool, tick, elapsed_ms: elapsed, snapshot: frame.snapshot});
      model.tickTotal += 1;
      const meter = document.querySelector(".ink-cycle-meter i");
      if (meter) meter.style.width = `${tick / model.state.ticks_per_cycle * 100}%`;
      if (tick >= model.state.ticks_per_cycle) {
        window.clearInterval(model.timer);
        finishCycle(cycle, startedAt);
      }
    }, model.state.tick_ms);
  }

  function foldValue(event) {
    const rect = document.querySelector(".ink-fold-track").getBoundingClientRect();
    return Math.max(0, Math.min(300, Math.round((event.clientX - rect.left) / rect.width * 300)));
  }

  function foldDown(event) {
    if (!model.selectedId || model.active || !isRequired("FOLD") || isObserved(model.selectedId, "FOLD")) return;
    event.preventDefault();
    const value = foldValue(event);
    record("fold_start", {value});
    model.fold = {start: value, last: value, moves: 0};
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function foldMove(event) {
    if (!model?.fold) return;
    event.preventDefault();
    const value = Math.max(model.fold.last, foldValue(event));
    record("fold_move", {value});
    model.fold.last = value;
    model.fold.moves += 1;
    model.foldSamples += 1;
    document.querySelector(".ink-fold-handle").style.left = `${value / 3}%`;
  }

  function foldUp(event) {
    if (!model?.fold) return;
    event.preventDefault();
    const value = model.fold.last;
    const valid = model.fold.moves >= 3 && value - model.fold.start >= model.state.fold_min_distance;
    if (valid) {
      record("fold_end", {value});
      model.fold = null;
      startProbe("FOLD");
    } else {
      record("fold_cancel", {value});
      model.fold = null;
      model.helpers.setReadout("FOLD SWEEP TOO SHORT · RETRY THIS SPECIMEN", "error");
    }
    document.querySelector(".ink-fold-handle").style.left = "0";
  }

  function pressureDown(event) {
    if (!model.selectedId || model.active || !isRequired("PRESSURE") || isObserved(model.selectedId, "PRESSURE")) return;
    event.preventDefault();
    record("pressure_down");
    model.pressureStarted = performance.now();
    event.currentTarget.setPointerCapture(event.pointerId);
    event.currentTarget.classList.add("is-held");
    model.helpers.setReadout("PRESSURE HELD · MAINTAIN THE CLAMP", "pending");
  }

  function pressureUp(event) {
    if (model.pressureStarted == null) return;
    event.preventDefault();
    const duration = Math.round(performance.now() - model.pressureStarted);
    model.pressureStarted = null;
    event.currentTarget.classList.remove("is-held");
    if (duration >= model.state.pressure_min_ms) {
      record("pressure_up", {duration_ms: duration});
      model.pressureHolds += 1;
      startProbe("PRESSURE");
    } else {
      record("pressure_cancel", {duration_ms: duration});
      model.helpers.setReadout("PRESSURE RELEASED EARLY · RETRY THIS SPECIMEN", "error");
    }
  }

  function coolPulse() {
    if (!model.selectedId || model.active || !isRequired("COOL") || isObserved(model.selectedId, "COOL")) return;
    record("thermal_pulse", {polarity: "COOL"});
    model.thermalPulses += 1;
    startProbe("COOL");
  }

  function stampDown(event) {
    const stamp = event.target.closest(".ink-stamp");
    if (!stamp || stamp.dataset.ready !== "true" || model.active || model.terminal) return;
    event.preventDefault();
    record("stamp_down", {point: stagePoint(event)});
    model.stampDrag = {moves: 0};
    document.querySelector(".ink-stage").setPointerCapture(event.pointerId);
    stamp.classList.add("is-dragging");
  }

  function stampMove(event) {
    if (!model?.stampDrag) return;
    event.preventDefault();
    const point = stagePoint(event);
    record("stamp_move", {point});
    model.stampDrag.moves += 1;
    model.stampMoves += 1;
    const ghost = document.querySelector(".ink-stamp-ghost");
    ghost.classList.add("is-visible");
    ghost.style.left = `${point[0] / model.state.stage.width * 100}%`;
    ghost.style.top = `${point[1] / model.state.stage.height * 100}%`;
  }

  function stampUp(event) {
    if (!model?.stampDrag) return;
    event.preventDefault();
    const point = stagePoint(event);
    record("stamp_up", {point});
    const rect = model.state.blot_rects.find((item) => inside(point, item));
    model.stampedId = rect ? rect.id : null;
    model.stampDrag = null;
    document.querySelector(".ink-stamp")?.classList.remove("is-dragging");
    document.querySelector(".ink-stamp-ghost")?.classList.remove("is-visible");
    document.querySelectorAll(".ink-blot").forEach((blot) => blot.classList.toggle("is-stamped", blot.dataset.blotId === model.stampedId));
    model.helpers.setReadout(model.stampedId ? `${model.stampedId.toUpperCase()} STAMPED · CERTIFY WHEN READY` : "STAMP MISSED ALL SPECIMENS", "idle");
  }

  function resetLab() {
    if (model.submitting || model.terminal) return;
    if (model.timer) window.clearInterval(model.timer);
    record("reset");
    model.selectedId = null;
    model.observations.clear();
    model.active = false;
    model.timer = null;
    model.fold = null;
    model.pressureStarted = null;
    model.stampDrag = null;
    model.stampedId = null;
    model.tickTotal = model.foldSamples = model.pressureHolds = model.thermalPulses = model.stampMoves = 0;
    model.resetCount += 1;
    document.querySelectorAll(".ink-blot").forEach((blot) => {
      blot.style.setProperty("--ink-left", "1");
      blot.style.setProperty("--ink-right", "1");
      blot.style.setProperty("--ink-fold", "0%");
      blot.style.setProperty("--ink-hue", "0deg");
      blot.style.setProperty("--ink-flow", "0deg");
      blot.classList.remove("is-stamped");
    });
    document.querySelectorAll(".ink-observation b").forEach((node) => { node.textContent = "UNTESTED"; });
    updateUI();
    model.helpers.setReadout("MATERIAL RUN RESET · SELECT A SPECIMEN", "idle");
  }

  async function submit() {
    if (model.submitting || model.terminal) return;
    model.submitting = true;
    model.helpers.setReadout("REPLAYING TEN SPECIMEN-BOUND RESPONSES…", "pending");
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({
        mechanic_id: model.state.mechanic_id,
        task_id: model.state.task_id,
        challenge_id: model.state.challenge_id,
        events: model.events,
        observation_keys: [...model.observations].sort(),
        observation_count: model.observations.size,
        tick_total: model.tickTotal,
        fold_samples: model.foldSamples,
        pressure_holds: model.pressureHolds,
        thermal_pulses: model.thermalPulses,
        stamp_moves: model.stampMoves,
        stamped_id: model.stampedId,
        reset_count: model.resetCount,
        completed: model.observations.size === model.state.observations_required && Boolean(model.stampedId),
      })});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true;
        document.querySelector(".ink-material-captcha")?.insertAdjacentHTML("beforeend", '<div class="ink-verdict"><span>SPECIMEN RESPONSE MATRIX AUTHENTICATED</span><strong>PASS</strong><small>TEN PHYSICAL PROBES + STAMP REPLAY VERIFIED</small></div>');
        model.helpers.setReadout("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        const shell = document.querySelector(".ink-material-captcha");
        shell?.setAttribute("data-fresh-failure", "true");
        shell?.insertAdjacentHTML("afterbegin", '<div class="ink-failure-stamp"><b>FAIL</b><span>MATERIAL RECORD REJECTED · FRESH SET ISSUED</span></div>');
        const readout = document.querySelector(".readout");
        if (readout) { readout.textContent = "FAIL · FRESH MATERIAL SET ISSUED"; readout.dataset.status = "error"; }
      } else {
        model.submitting = false;
        model.helpers.setReadout("FAIL · NO AUTHORITATIVE GRADE", "error");
      }
    } catch (_error) {
      model.submitting = false;
      model.helpers.setReadout("FAIL · MATERIAL VERIFIER OFFLINE", "error");
    }
  }

  function blotMarkup(item) {
    const a = 25 + (item.visual_seed % 18), b = 60 + (Math.floor(item.visual_seed / 19) % 22), c = 42 + (Math.floor(item.visual_seed / 41) % 18);
    return `<article class="ink-card" data-blot-id="${clean(item.id)}" data-selected="false" style="left:${item.rect.x / model.state.stage.width * 100}%;top:${item.rect.y / model.state.stage.height * 100}%;width:${item.rect.width / model.state.stage.width * 100}%;height:${item.rect.height / model.state.stage.height * 100}%;--ink-a:${a}%;--ink-b:${b}%;--ink-c:${c}%"><header><span>${clean(item.specimen)}</span><i>CLICK TO LOAD</i></header><div class="ink-paper"><div class="ink-blot" data-blot-id="${clean(item.id)}"><i class="ink-left"></i><i class="ink-right"></i><b></b><em></em></div><div class="ink-fold-axis"></div></div><footer><div class="ink-response-strip">${model.state.required_tools.map((tool) => `<span class="ink-observation" data-blot-id="${clean(item.id)}" data-tool="${tool}" data-status="waiting"><i>${tool.slice(0, 1)}</i><b>UNTESTED</b></span>`).join("")}</div></footer></article>`;
  }

  async function render(state, helpers) {
    if (model?.timer) window.clearInterval(model.timer);
    document.body.dataset.mechanic = "inkblot-material";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    model = {state, helpers, events: [], selectedId: null, observations: new Set(), active: false, timer: null, fold: null, pressureStarted: null, stampDrag: null, stampedId: null, tickTotal: 0, foldSamples: 0, pressureHolds: 0, thermalPulses: 0, stampMoves: 0, resetCount: 0, submitting: false, terminal: false};
    window.inkblotMaterialModel = model;
    const dock = state.stamp_dock_rect;
    helpers.app.innerHTML = `<section class="ink-material-captcha" data-challenge-id="${clean(state.challenge_id)}"><header class="ink-head"><div><span>SPECIMEN-BOUND MATERIAL INTERROGATION / ${clean(state.challenge_id)}</span><h1>${clean(state.objective)}</h1></div><div class="ink-protocol">${state.required_tools.map((tool, index) => `<div class="ink-protocol-step" data-status="next"><b>${index + 1}</b><span>${clean(tool)} EVERY CARD</span></div>`).join("")}<div class="ink-protocol-step ink-count"><b>Σ</b><span class="ink-observation-count">0/${state.observations_required}</span></div></div></header><main class="ink-main"><section class="ink-stage">${state.blots.map(blotMarkup).join("")}<div class="ink-stamp" data-ready="false" style="left:${dock.x / state.stage.width * 100}%;top:${dock.y / state.stage.height * 100}%;width:${dock.width / state.stage.width * 100}%;height:${dock.height / state.stage.height * 100}%"><i></i><b>VERIFICATION STAMP</b><span>LOCKED UNTIL ${state.observations_required}/${state.observations_required} PROBES</span></div><div class="ink-stamp-ghost"><b>STAMP</b></div></section><aside class="ink-console"><p>SPECIMEN TOOL RACK</p><h2>Select one card. Physically test both rubric responses.</h2><div class="ink-selected-specimen"><span>LOADED</span><b>SELECT A CARD</b></div><div class="ink-tool ink-fold-tool" data-tool="FOLD"><span>FOLD AXIS DRAG</span><div class="ink-fold-track"><i></i><b class="ink-fold-handle"></b></div><small>SWEEP LEFT → RIGHT</small></div><button type="button" class="ink-tool ink-pressure" data-tool="PRESSURE"><i></i><b>PRESSURE / HOLD</b><span>HOLD ≥ ${(state.pressure_min_ms / 1000).toFixed(1)}s</span></button><button type="button" class="ink-tool ink-cool" data-tool="COOL"><i>❄</i><b>COOLING PULSE</b><span>ONE SPECIMEN</span></button><div class="ink-cycle-meter"><span>TRANSIENT RESPONSE</span><b><i></i></b></div><ol>${state.rubric_labels.map((label, index) => `<li><b>${index + 1}</b><span>${clean(label)}</span></li>`).join("")}</ol><p class="ink-note">Initial appearance is non-diagnostic. A response is archived only for the loaded specimen.</p></aside></main><footer class="ink-foot"><button type="button" class="ink-reset">RESET MATERIAL RUN</button><div><span>LAB RECORD</span><div class="readout" data-status="idle">SELECT A SPECIMEN CARD</div></div><button type="button" class="ink-submit">${clean(state.submit_label)}</button></footer>${helpers.cheatPanelTemplate()}</section>`;
    document.querySelectorAll(".ink-card").forEach((card) => card.addEventListener("click", () => selectSpecimen(card.dataset.blotId)));
    const fold = document.querySelector(".ink-fold-track");
    fold.addEventListener("pointerdown", foldDown); fold.addEventListener("pointermove", foldMove); fold.addEventListener("pointerup", foldUp); fold.addEventListener("pointercancel", foldUp);
    const pressure = document.querySelector(".ink-pressure");
    pressure.addEventListener("pointerdown", pressureDown); pressure.addEventListener("pointerup", pressureUp); pressure.addEventListener("pointercancel", pressureUp);
    document.querySelector(".ink-cool").addEventListener("click", coolPulse);
    const stage = document.querySelector(".ink-stage");
    stage.addEventListener("pointerdown", stampDown); stage.addEventListener("pointermove", stampMove); stage.addEventListener("pointerup", stampUp); stage.addEventListener("pointercancel", stampUp);
    document.querySelector(".ink-reset").addEventListener("click", resetLab);
    document.querySelector(".ink-submit").addEventListener("click", submit);
    updateUI();
    helpers.installCheatPanel();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.rorschach_fixed_rubric = {rootSelector: ".ink-material-captcha", render};
})();
