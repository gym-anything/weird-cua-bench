(() => {
  "use strict";
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};

  const MECHANIC_ID = "loopmakers_trial";
  const esc = (value) => String(value == null ? "" : value).replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;", "'":"&#39;"}[char]));
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const close = (a, b, tolerance = 0.03) => Number.isFinite(Number(a)) && Number.isFinite(Number(b)) && Math.abs(Number(a) - Number(b)) <= tolerance;

  function samplePath(points, sampleSteps) {
    const path = [];
    for (let index = 0; index < points.length - 1; index += 1) {
      const first = points[index], second = points[index + 1];
      for (let step = 0; step < sampleSteps; step += 1) {
        const ratio = step / sampleSteps;
        path.push({x: Number(first.x) + (Number(second.x) - Number(first.x)) * ratio, y: Number(first.y) + (Number(second.y) - Number(first.y)) * ratio});
      }
    }
    const last = points[points.length - 1];
    path.push({x: Number(last.x), y: Number(last.y)});
    return path;
  }

  const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

  function radius(path, index, minimum) {
    if (index <= 0 || index >= path.length - 1) return 1000000;
    const first = path[index - 1], middle = path[index], last = path[index + 1];
    const a = distance(first, middle), b = distance(middle, last), c = distance(first, last);
    const cross = Math.abs((middle.x - first.x) * (last.y - first.y) - (middle.y - first.y) * (last.x - first.x));
    if (cross < 1e-6) return 1000000;
    return Math.max(minimum, (a * b * c) / (2 * cross));
  }

  function simulate(points, features, physics) {
    const sampleSteps = Number(physics.sample_steps);
    const path = samplePath(points, sampleSteps);
    const distances = [0];
    for (let index = 1; index < path.length; index += 1) distances.push(distances[index - 1] + distance(path[index - 1], path[index]));
    const speeds = [], forces = [];
    const startY = Number(points[0].y);
    for (let index = 0; index < path.length; index += 1) {
      const item = path[index];
      const heightGain = (startY - Number(item.y)) / Number(physics.pixels_per_meter);
      const energy = Number(physics.initial_speed_mps) ** 2 + 2 * Number(physics.gravity) * heightGain - Number(physics.friction_per_pixel) * distances[index];
      const speed = Math.sqrt(Math.max(0, energy));
      const prior = index === 0 ? path[0] : path[index - 1];
      const tangentX = index === 0 ? path[1].x - path[0].x : item.x - prior.x;
      const tangentY = index === 0 ? path[1].y - path[0].y : item.y - prior.y;
      const localRadius = radius(path, index, Number(physics.minimum_radius_px));
      const centripetal = localRadius > 900000 ? 0 : speed * speed / (Number(physics.gravity) * (localRadius / Number(physics.pixels_per_meter)));
      speeds.push(speed);
      forces.push(centripetal + Math.abs(Math.cos(Math.atan2(tangentY, tangentX))));
    }
    const metrics = features.map((feature) => {
      const index = Math.min(path.length - 1, Number(feature.point_index) * sampleSteps);
      const constraints = feature.constraints;
      const speed = speeds[index], force = forces[index];
      const contact = force >= Number(constraints.min_force_g);
      const reasons = [];
      if (speed < Number(constraints.min_speed)) reasons.push("speed below thrill minimum");
      if (speed > Number(constraints.max_speed)) reasons.push("speed above envelope");
      if (force < Number(constraints.min_force_g)) reasons.push("normal force below contact minimum");
      if (force > Number(constraints.max_force_g)) reasons.push("normal force above envelope");
      if (constraints.require_contact && !contact) reasons.push("rider lost contact");
      return {
        id: feature.id,
        label: feature.label,
        point_index: feature.point_index,
        speed_mps: Number(speed.toFixed(4)),
        force_g: Number(force.toFixed(4)),
        contact,
        ok: reasons.length === 0,
        reasons,
      };
    });
    let stalledAt = null;
    for (let index = 0; index < speeds.length; index += 1) {
      if (speeds[index] < Number(physics.stall_speed_mps)) { stalledAt = index; break; }
    }
    const completed = stalledAt === null && path.length > 0 && speeds[speeds.length - 1] >= Number(physics.stall_speed_mps);
    return {
      completed,
      passed: completed && metrics.every((metric) => metric.ok),
      stalled: stalledAt !== null,
      stalled_at_sample: stalledAt,
      distance_px: Number(distances[distances.length - 1].toFixed(4)),
      duration_ms: Number(physics.run_duration_ms),
      feature_metrics: metrics,
      end_speed_mps: Number((speeds[speeds.length - 1] || 0).toFixed(4)),
      sample_count: path.length,
    };
  }

  function pathString(points) { return points.map((point) => `${Number(point.x).toFixed(1)},${Number(point.y).toFixed(1)}`).join(" "); }

  function render(state, helpers) {
    document.body.dataset.mechanic = MECHANIC_ID;
    const root = document.createElement("section");
    root.className = "loopmakers-trial";
    root.dataset.mechanic = MECHANIC_ID;
    root.dataset.interaction = state.interaction_mode || state.control_condition?.interaction || "full";
    root.dataset.challengeId = state.challenge_id || "";
    const interaction = root.dataset.interaction;
    const points = clone(state.points || []);
    const events = [];
    const canvas = state.canvas || {width: 900, height: 470};
    const physics = state.physics || {};
    const features = state.features || [];
    const model = {state, helpers, root, points, events, selectedId: null, drag: null, running: false, terminal: false, raf: null, runSummary: null, runDistance: 0, runLastTime: 0, runPath: [], runDistances: [], runSpeeds: []};
    window.loopmakersTrialModel = model;

    const featureMarkup = features.map((feature) => {
      const point = points[Number(feature.point_index)] || points[0];
      return `<g class="lm-feature" data-feature-id="${esc(feature.id)}" transform="translate(${point.x} ${point.y})"><circle r="15"></circle><text y="-20">${esc(feature.label)}</text><text class="lm-feature-readout" y="28">--</text></g>`;
    }).join("");
    const pointMarkup = points.map((point, index) => `<g class="lm-point${index === 0 || index === points.length - 1 ? " is-locked" : ""}" data-point-id="${esc(point.id)}" data-point-index="${index}" transform="translate(${point.x} ${point.y})"><circle r="9"></circle><circle class="lm-point-core" r="3"></circle><text y="-15">${index === 0 ? "LAUNCH" : index === points.length - 1 ? "BRAKE" : point.id.toUpperCase()}</text></g>`).join("");
    const featureCards = features.map((feature) => `<article class="lm-card" data-card-id="${esc(feature.id)}"><div><span>${esc(feature.label)}</span><b>WAITING</b></div><p><strong class="lm-speed">--</strong> m/s <i>·</i> <strong class="lm-force">--</strong> g</p><small>speed ${Number(feature.constraints.min_speed).toFixed(1)}–${Number(feature.constraints.max_speed).toFixed(1)} · force ${Number(feature.constraints.min_force_g).toFixed(1)}–${Number(feature.constraints.max_force_g).toFixed(1)} g</small></article>`).join("");
    const proxyControls = interaction === "simplified" ? `<div class="lm-proxy" id="lm-proxy-controls"><p>Selected point is edited in fixed increments.</p><div class="lm-button-grid"><button type="button" data-action="raise" id="lm-raise">RAISE</button><button type="button" data-action="lower" id="lm-lower">LOWER</button><button type="button" data-action="widen" id="lm-widen">WIDEN</button><button type="button" data-action="tighten" id="lm-tighten">TIGHTEN</button></div></div>` : `<div class="lm-proxy lm-direct-note"><p>Full surface: drag amber control points. Horizontal spacing changes the local radius.</p></div>`;
    root.innerHTML = `
      <div class="lm-masthead"><div><span class="lm-kicker">FIELD ENGINEERING / ROUTE ${esc(String(state.challenge_id || "").slice(0, 8).toUpperCase())}</span><h1>Loopmaker's Trial</h1><p>${esc(state.prompt || "Tune the route until the rider completes the marked features.")}</p></div><div class="lm-contract"><span>INPUT SURFACE</span><strong>${interaction === "simplified" ? "PROXY CONTROLS" : "DIRECT DRAG"}</strong><small>${esc(state.route_caption || "Energy and curvature are coupled along one continuous path.")}</small></div></div>
      <div class="readout lm-readout" data-status="idle" aria-live="polite">SELECT A CONTROL POINT TO BEGIN</div>
      <div class="lm-layout">
        <section class="lm-board-wrap"><div class="lm-board-label"><span>TRACK PLAN / LIVE RIDE</span><span class="lm-board-help">${interaction === "simplified" ? "select a node, then tune" : "drag nodes, then test"}</span></div><div class="lm-board" id="lm-route-board"><svg id="lm-route-svg" viewBox="0 0 ${canvas.width} ${canvas.height}" role="img" aria-label="Editable roller coaster route"><defs><linearGradient id="lm-track-gradient" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f5bd4b"></stop><stop offset="1" stop-color="#ff6e50"></stop></linearGradient><filter id="lm-glow"><feGaussianBlur stdDeviation="5" result="blur"></feGaussianBlur><feMerge><feMergeNode in="blur"></feMergeNode><feMergeNode in="SourceGraphic"></feMergeNode></feMerge></filter></defs><path class="lm-gridline" d="M 20 410 H 880 M 20 300 H 880 M 20 190 H 880 M 20 80 H 880"></path><path class="lm-track-shadow" d="M ${pathString(points)}"></path><polyline class="lm-track" id="lm-track" points="${pathString(points)}"></polyline><path class="lm-ground" d="M 0 418 C 160 400 250 432 420 416 S 710 432 900 410"></path>${featureMarkup}${pointMarkup}<g id="lm-vehicle" class="lm-vehicle"><circle r="12"></circle><circle class="lm-wheel" cx="-8" cy="10" r="4"></circle><circle class="lm-wheel" cx="8" cy="10" r="4"></circle><path d="M-10,-11 Q0,-23 10,-11"></path></g></svg><div class="lm-run-ribbon" id="lm-run-status">ROUTE UNTESTED · EDIT A POINT THEN SEND THE RIDER</div></div></section>
        <aside class="lm-panel"><div class="lm-panel-head"><span>DESIGN CONSOLE</span><strong id="lm-selected-label">NO POINT SELECTED</strong></div><div class="lm-console-copy">A successful run must finish the whole route. Read the speed and normal-force cards after each test; local fixes can move downstream readings.</div>${proxyControls}<div class="lm-actions"><button class="lm-test" type="button" id="lm-run">TEST RUN <span>↗</span></button><button class="lm-submit" type="button" id="lm-submit">CERTIFY ROUTE <span>✓</span></button></div><div class="lm-cards" id="lm-cards">${featureCards}</div><div class="lm-legend"><span><i class="dot amber"></i>control point</span><span><i class="dot cyan"></i>marked feature</span><span><i class="dot coral"></i>rider telemetry</span></div></aside>
      </div>
      <div class="lm-footer"><span>PHYSICS REPLAY / height → energy → speed → contact</span><span>TRIAL ${esc(String(state.challenge_id || "").slice(-6).toUpperCase())}</span></div>
    `;
    helpers.app.innerHTML = "";
    helpers.app.appendChild(root);

    const svg = root.querySelector("#lm-route-svg");
    const vehicle = root.querySelector("#lm-vehicle");
    const board = root.querySelector("#lm-route-board");
    const pointNode = (id) => root.querySelector(`.lm-point[data-point-id="${CSS.escape(id)}"]`);
    const selected = () => points.find((point) => point.id === model.selectedId);
    const editable = (point) => point && point !== points[0] && point !== points[points.length - 1];
    const pointCoords = (event) => {
      return new DOMPoint(event.clientX, event.clientY).matrixTransform(svg.getScreenCTM().inverse());
    };
    const token = (label) => { try { return helpers.beginAction?.(label); } catch (_error) { return null; } };
    const settle = (action) => { try { action?.settle?.(); } catch (_error) {} };

    function paint() {
      root.querySelector("#lm-track").setAttribute("points", pathString(points));
      root.querySelector(".lm-track-shadow").setAttribute("d", `M ${pathString(points)}`);
      root.querySelectorAll(".lm-point").forEach((node) => {
        const point = points.find((item) => item.id === node.dataset.pointId);
        if (point) node.setAttribute("transform", `translate(${point.x} ${point.y})`);
        node.classList.toggle("is-selected", point?.id === model.selectedId);
      });
      root.querySelectorAll(".lm-feature").forEach((node) => {
        const feature = features.find((item) => item.id === node.dataset.featureId);
        const point = feature && points[Number(feature.point_index)];
        if (point) node.setAttribute("transform", `translate(${point.x} ${point.y})`);
      });
      const selectedPoint = selected();
      root.querySelector("#lm-selected-label").textContent = selectedPoint ? `${selectedPoint.id.toUpperCase()} · ${Number(selectedPoint.x).toFixed(0)}, ${Number(selectedPoint.y).toFixed(0)}` : "NO POINT SELECTED";
      root.querySelectorAll(".lm-proxy button").forEach((button) => { button.disabled = !editable(selectedPoint) || model.running || model.terminal; });
      root.querySelector("#lm-track").classList.toggle("is-live", model.running);
    }

    function recordAdjust(point, before, source, action, pointerStart, pointerEnd) {
      const entry = {seq: events.length + 1, type: "adjust", point_id: point.id, action, input_source: source, before: {x: Number(before.x), y: Number(before.y)}, after: {x: Number(point.x), y: Number(point.y)}};
      if (pointerStart) { entry.pointer_start = pointerStart; entry.pointer_end = pointerEnd; }
      events.push(entry);
      model.runSummary = null;
      root.classList.remove("lm-run-complete", "lm-run-failed");
      updateCards(null);
      root.querySelector("#lm-run-status").textContent = `EDIT LOGGED · ${point.id.toUpperCase()} · TEST THE WHOLE ROUTE`;
      helpers.setReadout("ROUTE EDITED · TEST THE WHOLE RIDE", "idle");
    }

    function choose(id) {
      model.selectedId = id;
      root.querySelectorAll(".lm-point").forEach((node) => node.classList.toggle("is-selected", node.dataset.pointId === id));
      paint();
    }

    root.querySelectorAll(".lm-point").forEach((node) => {
      node.addEventListener("click", () => choose(node.dataset.pointId));
      if (node.classList.contains("is-locked")) return;
      node.addEventListener("pointerdown", (event) => {
        choose(node.dataset.pointId);
        if (interaction !== "full" || model.running || model.terminal || model.drag || event.button !== 0) return;
        const point = selected();
        model.drag = {pointId: point.id, before: clone(point), start: {x: event.clientX, y: event.clientY}, action: token(`loopmaker-drag:${point.id}`)};
        node.setPointerCapture?.(event.pointerId);
        event.preventDefault();
      });
      node.addEventListener("pointermove", (event) => {
        if (!model.drag || model.drag.pointId !== node.dataset.pointId) return;
        const point = points.find((item) => item.id === model.drag.pointId);
        if (!point) return;
        const next = pointCoords(event);
        point.x = Math.max(18, Math.min(Number(canvas.width) - 18, next.x));
        point.y = Math.max(14, Math.min(Number(canvas.height) - 26, next.y));
        paint();
      });
      const finishDrag = (event) => {
        if (!model.drag || model.drag.pointId !== node.dataset.pointId) return;
        const drag = model.drag;
        const point = points.find((item) => item.id === drag.pointId);
        model.drag = null;
        if (point && (!close(point.x, drag.before.x) || !close(point.y, drag.before.y))) recordAdjust(point, drag.before, "point_drag", "drag", drag.start, {x: event.clientX, y: event.clientY});
        if (point && close(point.x, drag.before.x) && close(point.y, drag.before.y)) Object.assign(point, drag.before);
        settle(drag.action);
        paint();
      };
      node.addEventListener("pointerup", finishDrag);
      node.addEventListener("pointercancel", finishDrag);
    });

    root.querySelectorAll(".lm-proxy button").forEach((button) => button.addEventListener("click", () => {
      const point = selected();
      if (!editable(point) || model.running || model.terminal) return;
      const action = button.dataset.action;
      const before = clone(point);
      const params = state.control_condition?.difficulty_parameters || {};
      const heightStep = Number(params.height_step || 10), radiusStep = Number(params.radius_step || 15);
      if (action === "raise") point.y -= heightStep;
      if (action === "lower") point.y += heightStep;
      if (action === "widen") point.x += radiusStep;
      if (action === "tighten") point.x -= radiusStep;
      point.x = Math.max(18, Math.min(Number(canvas.width) - 18, point.x));
      point.y = Math.max(14, Math.min(Number(canvas.height) - 26, point.y));
      if (close(point.x, before.x) && close(point.y, before.y)) {
        helpers.setReadout("POINT AT BOARD LIMIT · CHOOSE ANOTHER EDIT", "error");
        paint();
        return;
      }
      const actionToken = token(`loopmaker-proxy:${action}`);
      recordAdjust(point, before, "proxy_controls", action);
      settle(actionToken);
      paint();
    }));

    function updateCards(summary, progressIndex = null) {
      const metrics = summary?.feature_metrics || [];
      root.querySelectorAll(".lm-card").forEach((card) => {
        const metric = metrics.find((item) => item.id === card.dataset.cardId);
        if (!metric) {
          card.classList.remove("is-seen", "is-good", "is-bad");
          card.querySelector("b").textContent = "WAITING";
          card.querySelector(".lm-speed").textContent = "--";
          card.querySelector(".lm-force").textContent = "--";
          return;
        }
        const feature = features.find((item) => item.id === metric.id);
        const visible = progressIndex === null || Number(feature.point_index) * Number(physics.sample_steps) <= progressIndex;
        card.classList.toggle("is-seen", visible);
        card.classList.toggle("is-good", visible && metric.ok);
        card.classList.toggle("is-bad", visible && !metric.ok);
        card.querySelector("b").textContent = visible ? (metric.ok ? "IN ENVELOPE" : (metric.reasons[0] || "REVISE")) : "AHEAD";
        card.querySelector(".lm-speed").textContent = visible ? Number(metric.speed_mps).toFixed(1) : "--";
        card.querySelector(".lm-force").textContent = visible ? Number(metric.force_g).toFixed(1) : "--";
      });
    }

    function positionVehicle() {
      if (!model.runPath.length) return;
      let index = 1;
      while (index < model.runDistances.length - 1 && model.runDistances[index] < model.runDistance) index += 1;
      const before = model.runPath[Math.max(0, index - 1)], after = model.runPath[index] || before;
      const span = Math.max(0.001, model.runDistances[index] - model.runDistances[Math.max(0, index - 1)]);
      const ratio = Math.max(0, Math.min(1, (model.runDistance - model.runDistances[Math.max(0, index - 1)]) / span));
      const x = before.x + (after.x - before.x) * ratio, y = before.y + (after.y - before.y) * ratio;
      vehicle.setAttribute("transform", `translate(${x} ${y})`);
      root.querySelector("#lm-run-status").textContent = `RIDER IN TRANSIT · ${Math.round(model.runDistance)} / ${Math.round(model.runDistances[model.runDistances.length - 1])} PX`;
      updateCards(model.runSummary, index);
    }

    function runFrame(now) {
      if (!model.running) return;
      const currentNow = Number(helpers.interactionNow?.() ?? now);
      const delta = Math.max(0, Math.min(90, currentNow - model.runLastTime));
      model.runLastTime = currentNow;
      let sampleIndex = 1;
      while (sampleIndex < model.runDistances.length - 1 && model.runDistances[sampleIndex] < model.runDistance) sampleIndex += 1;
      const speed = model.runSpeeds[Math.min(model.runSpeeds.length - 1, sampleIndex)] || 0;
      const stopIndex = model.runSummary.stalled_at_sample ?? (model.runDistances.length - 1);
      const stopDistance = model.runDistances[stopIndex];
      model.runDistance = Math.min(stopDistance, model.runDistance + speed * Number(physics.pixels_per_meter) * delta / 1000);
      // A slow but valid route must visibly reach its brake. The observation
      // duration is only a fallback for a stalled rider that no longer moves.
      const stopped = model.runSummary.stalled && currentNow - model.runStartedAt >= Number(physics.run_duration_ms);
      if (stopped) model.runDistance = stopDistance;
      positionVehicle();
      if (model.runDistance >= stopDistance || stopped) {
        finishRun();
        return;
      }
      model.raf = requestAnimationFrame(runFrame);
    }

    function finishRun() {
      model.running = false;
      if (model.raf) cancelAnimationFrame(model.raf);
      model.runSummary = simulate(points, features, physics);
      events.push({seq: events.length + 1, type: "test_run", input_source: "test_button", points: clone(points), summary: clone(model.runSummary)});
      root.classList.add("lm-run-complete");
      root.classList.toggle("lm-run-failed", !model.runSummary.passed);
      root.querySelector("#lm-run-status").textContent = model.runSummary.passed ? "RUN COMPLETE · ALL MARKERS SAFE" : model.runSummary.stalled ? "RUN COMPLETE · RIDER STALLED · REVISE THE ROUTE" : `RUN COMPLETE · ${model.runSummary.feature_metrics.filter((item) => !item.ok).length} MARKER(S) NEED REVISION`;
      helpers.setReadout(model.runSummary.passed ? "RUN PASSED · CERTIFY WHEN READY" : "TEST FAILED · REVISE THE ROUTE", model.runSummary.passed ? "idle" : "error");
      updateCards(model.runSummary, model.runSummary.sample_count);
      paint();
    }

    root.querySelector("#lm-run").addEventListener("click", () => {
      if (model.running || model.terminal || model.drag) return;
      const action = token("loopmaker-test-run");
      const replay = simulate(points, features, physics);
      const path = samplePath(points, Number(physics.sample_steps));
      model.runPath = path;
      model.runDistances = [0];
      for (let index = 1; index < path.length; index += 1) model.runDistances.push(model.runDistances[index - 1] + distance(path[index - 1], path[index]));
      const startY = Number(points[0].y);
      model.runSpeeds = path.map((point, index) => {
        const heightGain = (startY - Number(point.y)) / Number(physics.pixels_per_meter);
        const energy = Number(physics.initial_speed_mps) ** 2 + 2 * Number(physics.gravity) * heightGain - Number(physics.friction_per_pixel) * model.runDistances[index];
        return Math.sqrt(Math.max(0, energy));
      });
      model.runSummary = replay;
      model.runDistance = 0;
      model.running = true;
      model.runStartedAt = Number(helpers.interactionNow?.() ?? performance.now());
      model.runLastTime = model.runStartedAt;
      root.classList.remove("lm-run-complete", "lm-run-failed");
      root.querySelector("#lm-run-status").textContent = "RIDER RELEASED · OBSERVE THE FULL ROUTE";
      helpers.setReadout("RIDER RELEASED · WATCH THE MARKERS", "idle");
      updateCards(replay, 0);
      paint();
      settle(action);
      model.raf = requestAnimationFrame(runFrame);
    });

    root.querySelector("#lm-submit").addEventListener("click", async () => {
      if (model.running || model.terminal || model.drag || !model.runSummary) {
        helpers.setReadout(model.running ? "RIDE STILL IN MOTION" : "TEST THE ROUTE BEFORE CERTIFYING", "error");
        return;
      }
      const action = token("loopmaker-certify-route");
      const payload = {mechanic_id: state.mechanic_id, task_id: state.task_id, challenge_id: state.challenge_id, interaction_mode: interaction, completed: true, events: clone(events)};
      model.terminal = true;
      helpers.setReadout("REPLAYING GEOMETRY AND RIDER TELEMETRY…", "idle");
      try {
        const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
        const outcome = await response.json();
        if (outcome.passed === true) {
          root.dataset.verdict = "pass";
          root.querySelector("#lm-run-status").textContent = "CERTIFIED · PHYSICAL REPLAY AGREES";
          helpers.setReadout("PASS", "passed");
        } else if (outcome.passed === false && outcome.state) {
          await helpers.render(outcome.state);
          const fresh = document.querySelector(".loopmakers-trial");
          fresh?.classList.add("lm-fresh-failure");
          helpers.setReadout("FAIL · FRESH TRIAL ISSUED", "error");
        } else {
          model.terminal = false;
          helpers.setReadout("CERTIFICATION UNAVAILABLE · RETRY", "error");
        }
      } catch (_error) {
        model.terminal = false;
        helpers.setReadout("VERIFIER LINK UNAVAILABLE · RETRY", "error");
      }
      settle(action);
    });

    helpers.installCheatPanel?.();
    vehicle.setAttribute("transform", `translate(${points[0].x} ${points[0].y})`);
    updateCards(null);
    paint();
    helpers.setReadout("SELECT A CONTROL POINT TO BEGIN", "idle");
  }

  window.WeirdCaptchaMechanics[MECHANIC_ID] = {rootSelector: ".loopmakers-trial", render};
})();
