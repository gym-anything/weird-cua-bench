(() => {
  "use strict";

  const MECHANIC_ID = "flip_gate_cascade";
  let model = null;

  const esc = value => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const same = (left, right) => left.length === right.length && left.every((value, index) => value === right[index]);

  function simulate(state, chute) {
    const machine = model.state.machine;
    const next = state.slice();
    const path = [];
    const visits = [];
    let column = Number(machine.entry_columns[chute]);
    for (let row = 0; row < machine.row_count; row += 1) {
      const gate = machine.row_offsets[row] + column;
      const pointsRight = Boolean(next[gate]);
      path.push(gate);
      visits.push({gate, pointsRight});
      next[gate] = pointsRight ? 0 : 1;
      if (pointsRight) column += 1;
    }
    return {after: next, path, visits, exitColumn: column};
  }

  function gateMarkup(gate, state, compact = false) {
    const pointsRight = Boolean(state[gate.id]);
    const angle = pointsRight ? 34 : -34;
    const scale = compact ? 0.62 : 1;
    return `<g class="cascade-gate${compact ? " compact" : ""}" data-gate-id="${gate.id}" transform="translate(${gate.center[0]} ${gate.center[1]}) scale(${scale})">
      <circle class="gate-well" r="34"/>
      <circle class="gate-index-ring" r="25"/>
      <g class="gate-vane" transform="rotate(${angle})" style="--vane:${pointsRight ? model.palette.right : model.palette.left}">
        <rect x="-38" y="-8" width="76" height="16" rx="8"/>
        <circle r="7"/>
      </g>
      <circle class="gate-lamp" cx="0" cy="25" r="4" style="--lamp:${pointsRight ? model.palette.right : model.palette.left}"/>
    </g>`;
  }

  function railMarkup(compact = false) {
    const machine = model.state.machine;
    const byId = new Map(machine.gates.map(gate => [gate.id, gate]));
    const rails = [];
    for (const gate of machine.gates) {
      if (gate.row >= machine.row_count - 1) continue;
      const left = byId.get(machine.row_offsets[gate.row + 1] + gate.column);
      const right = byId.get(machine.row_offsets[gate.row + 1] + gate.column + 1);
      const bendY = (gate.center[1] + left.center[1]) / 2;
      rails.push(`<path d="M${gate.center[0] - 21},${gate.center[1] + 18} Q${gate.center[0] - 37},${bendY} ${left.center[0]},${left.center[1] - 32}"/>`);
      rails.push(`<path d="M${gate.center[0] + 21},${gate.center[1] + 18} Q${gate.center[0] + 37},${bendY} ${right.center[0]},${right.center[1] - 32}"/>`);
    }
    return `<g class="cascade-rails${compact ? " compact" : ""}">${rails.join("")}</g>`;
  }

  function chuteMarkup(chute) {
    const clickable = model.interaction === "simplified";
    const label = clickable
      ? `Inspect chute ${esc(chute.label)} inlet; activate to drop a marble`
      : `Inspect chute ${esc(chute.label)} inlet; drag the feed marble here to drop`;
    return `<g class="cascade-chute${clickable ? " is-clickable" : ""}" data-chute="${chute.id}" transform="translate(${chute.center[0]} ${chute.center[1]})" role="${clickable ? "button" : "img"}" tabindex="0" aria-label="${label}">
      <path class="chute-funnel" d="M-38 -25 H38 L23 17 H-23 Z"/>
      <rect class="chute-throat" x="-22" y="14" width="44" height="47" rx="9"/>
      <text y="-4">${esc(chute.label)}</text>
      ${clickable ? '<text class="drop-word" y="43">DROP</text>' : ""}
    </g>`;
  }

  function machineSvg(state, target = false) {
    const machine = model.state.machine;
    const lastRow = machine.gates.filter(gate => gate.row === machine.row_count - 1);
    const drains = lastRow.map(gate => `<path d="M${gate.center[0]},${gate.center[1] + 31} V566"/>`).join("");
    const inlets = machine.chutes.map(chute => {
      const gate = machine.gates[machine.row_offsets[0] + Number(machine.entry_columns[chute.id])];
      return `<path d="M${chute.center[0]},94 L${chute.center[0]},98 L${gate.center[0]},${gate.center[1] - 34}"/>`;
    }).join("");
    return `<svg class="cascade-machine-svg${target ? " target-machine-svg" : ""}" viewBox="0 0 760 600" role="img" aria-label="${target ? "Target vane pattern" : "Current flip-gate machine"}">
      <defs>
        <filter id="marbleGlow"><feGaussianBlur stdDeviation="5" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <linearGradient id="cabinetGlass" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#fff" stop-opacity=".09"/><stop offset=".46" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#7ed2cc" stop-opacity=".06"/></linearGradient>
      </defs>
      <rect class="cabinet-bed" x="18" y="14" width="724" height="572" rx="32"/>
      ${target ? "" : `<g class="chute-feed-lines">${inlets}</g>`}
      ${railMarkup(target)}
      <g class="drain-lines">${drains}</g>
      <g class="cascade-gates">${machine.gates.map(gate => gateMarkup(gate, state, target)).join("")}</g>
      ${target ? "" : `<g class="inlet-manifold-cover"><rect x="53" y="91" width="654" height="42" rx="10"/><path d="M69,104 H691 M69,121 H691"/><text x="380" y="116">SEALED INLET MANIFOLD</text></g><g class="cascade-chutes">${machine.chutes.map(chuteMarkup).join("")}</g><path id="cascade-inspection-trace"/><path id="cascade-active-trace"/><circle id="cascade-marble" r="12"/>`}
      <rect class="cabinet-glass" x="25" y="20" width="710" height="560" rx="27"/>
    </svg>`;
  }

  function targetCard() {
    return `<aside class="cascade-target-card">
      <div class="card-pin"></div>
      <span class="eyebrow">INSPECTION PATTERN</span>
      <h2>Target vanes</h2>
      <div class="target-diagram">${machineSvg(model.state.machine.target_state, true)}</div>
    </aside>`;
  }

  function controlPanel() {
    const full = model.interaction === "full";
    return `<aside class="cascade-control-panel">
      <div><span class="eyebrow">MARBLE ISSUE</span><h2>${full ? "Feed cup" : "Drop bank"}</h2></div>
      <div class="marble-feed${full ? " is-draggable" : ""}">
        ${full ? `<div class="feed-cup"><div class="feed-marble" role="button" tabindex="0" aria-label="Drag this marble into a chute"></div></div>` : `<div class="click-schematic" aria-hidden="true"><i></i><i></i><i></i></div>`}
      </div>
      <div class="tray-meter"><span>DROPS REMAINING</span><b id="cascade-drops-left">${model.budget}</b><div id="cascade-tray-pips"></div></div>
      <div class="readout" hidden aria-hidden="true" style="display:none" data-status="idle"></div>
    </aside>`;
  }

  function setGateState(gateId, value) {
    const gate = document.querySelector(`.cascade-cabinet .cascade-gate[data-gate-id="${gateId}"]`);
    if (!gate) return;
    const vane = gate.querySelector(".gate-vane");
    const lamp = gate.querySelector(".gate-lamp");
    const pointsRight = Boolean(value);
    vane?.setAttribute("transform", `rotate(${pointsRight ? 34 : -34})`);
    vane?.style.setProperty("--vane", pointsRight ? model.palette.right : model.palette.left);
    lamp?.style.setProperty("--lamp", pointsRight ? model.palette.right : model.palette.left);
    gate.classList.remove("just-flipped");
    void gate.getBoundingClientRect();
    gate.classList.add("just-flipped");
  }

  function updateMeters() {
    const left = Math.max(0, model.budget - model.events.length);
    const count = document.querySelector("#cascade-drops-left");
    const pips = document.querySelector("#cascade-tray-pips");
    if (count) count.textContent = String(left).padStart(2, "0");
    if (pips) pips.innerHTML = Array.from({length: model.budget}, (_, index) => `<i class="${index < left ? "loaded" : "spent"}"></i>`).join("");
  }

  function inletPath(chuteId) {
    const machine = model.state.machine;
    const chute = machine.chutes.find(item => Number(item.id) === Number(chuteId));
    if (!chute) return "";
    const gate = machine.gates[machine.row_offsets[0] + Number(machine.entry_columns[chute.id])];
    return `M${chute.center[0]},20 L${chute.center[0]},98 L${gate.center[0]},${gate.center[1]}`;
  }

  function inspectInlet(chuteId) {
    if (!model || model.busy || model.submitting) return;
    const trace = document.querySelector("#cascade-inspection-trace");
    if (!trace) return;
    document.querySelectorAll(".cascade-chute.is-inspecting").forEach(chute => chute.classList.remove("is-inspecting"));
    const chute = document.querySelector(`.cascade-chute[data-chute="${Number(chuteId)}"]`);
    chute?.classList.add("is-inspecting");
    trace.setAttribute("d", inletPath(chuteId));
    trace.classList.add("is-visible");
  }

  function clearInspection(chuteId = null) {
    const active = document.querySelector(".cascade-chute.is-inspecting");
    if (chuteId != null && active && Number(active.dataset.chute) !== Number(chuteId)) return;
    active?.classList.remove("is-inspecting");
    document.querySelector("#cascade-inspection-trace")?.classList.remove("is-visible");
  }

  function polylinePosition(points, progress) {
    const segmentCount = points.length - 1;
    const scaled = Math.min(0.999999, Math.max(0, progress)) * segmentCount;
    const index = Math.min(segmentCount - 1, Math.floor(scaled));
    const local = scaled - index;
    return {
      x: points[index][0] + (points[index + 1][0] - points[index][0]) * local,
      y: points[index][1] + (points[index + 1][1] - points[index][1]) * local,
    };
  }

  function pathPoints(chute, simulated) {
    const machine = model.state.machine;
    const points = [[chute.center[0], 20], [chute.center[0], 98]];
    for (const gateId of simulated.path) {
      const gate = machine.gates[gateId];
      points.push([gate.center[0], gate.center[1]]);
    }
    const lastVisit = simulated.visits[simulated.visits.length - 1];
    const lastGate = machine.gates[lastVisit.gate];
    points.push([lastGate.center[0] + (lastVisit.pointsRight ? 58 : -58), 586]);
    return points;
  }

  function startDrop(chuteId, inputSource) {
    if (!model || model.busy || model.submitting || model.events.length >= model.budget) return;
    const chute = model.state.machine.chutes.find(item => Number(item.id) === Number(chuteId));
    if (!chute) return;
    const root = document.querySelector(".flip-gate-cascade");
    if (root?.dataset.freshFailure === "true") delete root.dataset.freshFailure;
    const before = model.current.slice();
    const simulated = simulate(before, Number(chute.id));
    const points = pathPoints(chute, simulated);
    const marble = document.querySelector("#cascade-marble");
    const trace = document.querySelector("#cascade-active-trace");
    if (!marble || !trace) return;
    clearInspection();
    const action = window.WeirdCaptchaTime?.beginAction("flip-gate-marble-transit");
    model.busy = true;
    root?.classList.add("is-dropping");
    trace.setAttribute("d", points.map((point, index) => `${index ? "L" : "M"}${point[0]},${point[1]}`).join(" "));
    trace.classList.remove("is-settled");
    const traceLength = trace.getTotalLength();
    trace.style.strokeDasharray = String(traceLength);
    trace.style.strokeDashoffset = String(traceLength);
    marble.setAttribute("cx", String(points[0][0]));
    marble.setAttribute("cy", String(points[0][1]));
    marble.classList.add("is-visible");
    let startedAt = null;
    let flipped = 0;
    const pointCount = points.length - 1;
    const gateThresholds = simulated.path.map((_, index) => (index + 2) / pointCount);
    const duration = Number(model.state.machine.animation_ms);
    const token = model.token;

    const frame = timestamp => {
      if (!model || model.token !== token) {
        action?.settle();
        return;
      }
      if (startedAt == null) startedAt = timestamp;
      const progress = Math.min(1, Math.max(0, (timestamp - startedAt) / duration));
      const position = polylinePosition(points, progress);
      marble.setAttribute("cx", String(position.x));
      marble.setAttribute("cy", String(position.y));
      trace.style.strokeDashoffset = String(traceLength * (1 - progress));
      while (flipped < gateThresholds.length && progress >= gateThresholds[flipped]) {
        const gateId = simulated.path[flipped];
        model.current[gateId] = simulated.after[gateId];
        setGateState(gateId, model.current[gateId]);
        flipped += 1;
      }
      if (progress < 1) {
        requestAnimationFrame(frame);
        return;
      }
      while (flipped < simulated.path.length) {
        const gateId = simulated.path[flipped];
        model.current[gateId] = simulated.after[gateId];
        setGateState(gateId, model.current[gateId]);
        flipped += 1;
      }
      marble.classList.remove("is-visible");
      trace.classList.add("is-settled");
      model.events.push({
        sequence: model.events.length + 1,
        chute: Number(chute.id),
        input_source: inputSource,
        before_state: before,
        path: simulated.path.slice(),
        after_state: simulated.after.slice(),
        drops_after: model.events.length + 1,
        settled: true,
      });
      model.current = simulated.after.slice();
      model.busy = false;
      root?.classList.remove("is-dropping");
      updateMeters();
      action?.settle();
      if (same(model.current, model.state.machine.target_state)) {
        submit(true);
      } else if (model.events.length >= model.budget) {
        submit(false);
      }
    };
    requestAnimationFrame(frame);
  }

  async function submit(completed) {
    if (!model || model.submitting) return;
    model.submitting = true;
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      events: model.events,
      final_state: model.current,
      drops_used: model.events.length,
      completed,
      budget_exhausted: model.events.length >= model.budget && !completed,
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      const root = document.querySelector(".flip-gate-cascade");
      if (outcome.passed === true) {
        model.helpers.setReadout("PASS", "passed");
        root?.classList.add("is-passed");
      } else {
        root?.classList.add("is-failed");
        if (root) root.dataset.failureReady = "true";
        model.helpers.setReadout("FAIL", "error");
        if (outcome.state) {
          const failedToken = model.token;
          const helpers = model.helpers;
          await helpers.render(outcome.state);
          if (!model || model.token === failedToken) return;
          const freshRoot = document.querySelector(".flip-gate-cascade");
          const freshToken = model.token;
          if (freshRoot) {
            freshRoot.dataset.failureReady = "true";
            freshRoot.dataset.freshFailure = "true";
            freshRoot.classList.add("is-failed");
          }
          window.setTimeout(() => {
            if (!model || model.token !== freshToken) return;
            document.querySelector(".flip-gate-cascade")?.classList.remove("is-failed");
          }, 1400);
        }
      }
    } catch (_error) {
      const root = document.querySelector(".flip-gate-cascade");
      root?.classList.add("is-failed");
      if (root) root.dataset.failureReady = "true";
      model.helpers.setReadout("FAIL", "error");
    }
  }

  function installChutes() {
    document.querySelectorAll(".cascade-chute").forEach(chute => {
      const chuteId = Number(chute.dataset.chute);
      const action = () => startDrop(chuteId, "chute_click");
      chute.addEventListener("pointerenter", () => inspectInlet(chuteId));
      chute.addEventListener("pointerleave", () => clearInspection(chuteId));
      chute.addEventListener("focus", () => inspectInlet(chuteId));
      chute.addEventListener("blur", () => clearInspection(chuteId));
      if (!chute.classList.contains("is-clickable")) return;
      chute.addEventListener("click", action);
      chute.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          action();
        }
      });
    });
  }

  function installMarbleDrag() {
    if (model.interaction !== "full") return;
    const marble = document.querySelector(".feed-marble");
    if (!marble) return;
    marble.addEventListener("pointerdown", event => {
      if (model.busy || model.submitting) return;
      event.preventDefault();
      const origin = {x: event.clientX, y: event.clientY};
      marble.setPointerCapture(event.pointerId);
      marble.classList.add("is-held");
      const move = moveEvent => {
        if (moveEvent.pointerId !== event.pointerId) return;
        marble.style.transform = `translate(${moveEvent.clientX - origin.x}px, ${moveEvent.clientY - origin.y}px)`;
      };
      const finish = (endEvent, cancelled) => {
        if (endEvent.pointerId !== event.pointerId) return;
        marble.removeEventListener("pointermove", move);
        marble.removeEventListener("pointerup", up);
        marble.removeEventListener("pointercancel", cancel);
        marble.classList.remove("is-held");
        marble.style.transform = "";
        if (marble.hasPointerCapture(event.pointerId)) marble.releasePointerCapture(event.pointerId);
        if (cancelled) return;
        let selected = null;
        let distance = Infinity;
        document.querySelectorAll(".cascade-chute").forEach(chute => {
          const box = chute.getBoundingClientRect();
          const value = Math.hypot(endEvent.clientX - (box.left + box.width / 2), endEvent.clientY - (box.top + box.height / 2));
          if (value < distance) {
            distance = value;
            selected = chute;
          }
        });
        if (selected && distance <= 72) startDrop(Number(selected.dataset.chute), "marble_drag");
      };
      const up = endEvent => finish(endEvent, false);
      const cancel = endEvent => finish(endEvent, true);
      marble.addEventListener("pointermove", move);
      marble.addEventListener("pointerup", up);
      marble.addEventListener("pointercancel", cancel);
    });
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "flip-gate-cascade-v1";
    const interaction = state.control_condition?.interaction || "simplified";
    model = {
      state,
      helpers,
      interaction,
      palette: state.machine.palette,
      current: state.machine.initial_state.slice(),
      budget: Number(state.machine.drop_budget),
      events: [],
      busy: false,
      submitting: false,
      token: Symbol("flip-gate-render"),
    };
    helpers.app.innerHTML = `<main class="flip-gate-cascade" data-interaction="${esc(interaction)}">
      <header class="cascade-header"><div><span>EDUCATION SCIENCE RESEARCH / TEST BENCH 04</span><h1>Flip-Gate Cascade</h1></div><p>${esc(state.prompt)}</p></header>
      <section class="cascade-workbench">
        ${targetCard()}
        <section class="cascade-cabinet"><div class="cabinet-nameplate"><i></i><b>CASCADE LOGIC UNIT</b><i></i></div>${machineSvg(model.current, false)}<div class="cabinet-serial">SERIAL ${esc(state.challenge_id.toUpperCase())}</div></section>
        ${controlPanel()}
      </section>
      <div class="cascade-fail-card"><b>FAIL</b></div>
      <div class="cascade-pass-card"><b>PASS</b></div>
    </main>`;
    installChutes();
    installMarbleDrag();
    updateMeters();
    window.flipGateCascadeModel = model;
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {render, rootSelector: ".flip-gate-cascade"};
})();
