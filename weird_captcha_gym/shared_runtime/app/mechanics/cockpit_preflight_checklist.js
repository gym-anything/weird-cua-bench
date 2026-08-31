(() => {
  "use strict";

  let model = null;
  let cleanup = null;
  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const interaction = () => model.state.control_condition?.interaction || "full";
  const record = (event) => {
    model.events.push({sequence: model.events.length + 1, ...event});
    if (model.freshFailure) {
      model.freshFailure = false;
      const verdict = document.querySelector(".cpf-verdict");
      if (verdict) { verdict.className = "cpf-verdict"; verdict.innerHTML = ""; }
      model.helpers.setReadout("PANEL ACTIVE", "idle");
    }
  };

  function itemById(id) {
    for (const item of model.panel.ranges) if (item.id === id) return item;
    for (const item of model.panel.dials) if (item.id === id) return item;
    for (const branch of model.panel.branches) {
      if (branch.id === id) return branch;
      for (const row of branch.rows) if (row.id === id) return row;
    }
    return null;
  }

  function couplingInto(id, field) {
    return (model.panel.couplings || []).find((item) => item.target.id === id && item.target.field === field) || null;
  }

  function channelLocked(id, field) {
    const coupling = couplingInto(id, field);
    return Boolean(coupling && !model.revealed.has(coupling.id));
  }

  function targetMarkup(id, field, value, pad = false) {
    const coupling = couplingInto(id, field);
    if (coupling && !model.revealed.has(coupling.id)) return '<em class="cpf-sealed">BUS LOCK</em>';
    const text = pad ? String(value).padStart(2, "0") : String(value);
    return `<b>${esc(text)}</b>`;
  }

  function applyCouplings(source, field, before, after) {
    const effects = [];
    const revealed = [];
    const sourceSteps = (after - before) / source.step;
    const sourceTargetField = field === "low" ? "target_low" : field === "high" ? "target_high" : "target";
    const releasesTarget = after === source[sourceTargetField];
    (model.panel.couplings || []).filter((item) => item.source.id === source.id && item.source.field === field).forEach((coupling) => {
      const target = itemById(coupling.target.id);
      const targetField = coupling.target.field;
      const targetBefore = target[targetField];
      let targetAfter = targetBefore + sourceSteps * target.step * coupling.ratio;
      targetAfter = clamp(targetAfter, target.minimum, target.maximum);
      if (targetField === "low") targetAfter = Math.min(targetAfter, target.high - target.step);
      if (targetField === "high") targetAfter = Math.max(targetAfter, target.low + target.step);
      target[targetField] = targetAfter;
      effects.push({coupling_id: coupling.id, id: target.id, field: targetField, before: targetBefore, after: targetAfter});
      if (releasesTarget) {
        model.revealed.add(coupling.id);
        revealed.push(coupling.id);
      }
    });
    return {effects, revealed_coupling_ids: revealed};
  }

  function finalState() {
    const result = {};
    model.panel.ranges.forEach((item) => { result[item.id] = {low: item.low, high: item.high}; });
    model.panel.dials.forEach((item) => { result[item.id] = {value: item.value}; });
    model.panel.branches.forEach((branch) => {
      result[branch.id] = {expanded: branch.expanded};
      branch.rows.forEach((row) => { result[row.id] = {state: row.state}; });
    });
    return result;
  }

  function valueText(value) {
    if (model.panel.readout_mode === "all") return String(value).padStart(2, "0");
    if (model.panel.readout_mode === "active") return "FOCUS";
    return "TICKS";
  }

  function rangeMarkup(item) {
    const low = (item.low - item.minimum) / (item.maximum - item.minimum) * 100;
    const high = (item.high - item.minimum) / (item.maximum - item.minimum) * 100;
    const lowLocked = channelLocked(item.id, "low");
    const highLocked = channelLocked(item.id, "high");
    const proxy = interaction() === "simplified" ? `
      <div class="cpf-step-bank" aria-label="${esc(item.label)} step controls">
        <div><span>LOW</span><button data-range-step="${esc(item.id)}:low:-1" ${lowLocked ? "disabled" : ""}>−</button><b>${lowLocked ? "LOCK" : valueText(item.low)}</b><button data-range-step="${esc(item.id)}:low:1" ${lowLocked ? "disabled" : ""}>+</button></div>
        <div><span>HIGH</span><button data-range-step="${esc(item.id)}:high:-1" ${highLocked ? "disabled" : ""}>−</button><b>${highLocked ? "LOCK" : valueText(item.high)}</b><button data-range-step="${esc(item.id)}:high:1" ${highLocked ? "disabled" : ""}>+</button></div>
      </div>` : "";
    return `<article class="cpf-range-unit" data-range-id="${esc(item.id)}">
      <header><span>${esc(item.label)}</span><b>${valueText(item.low)}—${valueText(item.high)}</b></header>
      <div class="cpf-range-rail" data-range-rail="${esc(item.id)}" role="group" aria-label="${esc(item.label)} multi-thumb range" style="--low:${low}%;--high:${high}%">
        <i class="cpf-range-fill"></i>
        ${Array.from({length: 21}, (_, i) => `<em class="${i % 2 ? "is-minor" : "is-major"}" style="left:${i * 5}%"></em>`).join("")}
        <button class="cpf-thumb cpf-thumb-low ${lowLocked ? "is-locked" : ""}" data-thumb="low" style="left:${low}%" aria-label="${esc(item.label)} low ${item.low}" aria-disabled="${lowLocked}" aria-valuemin="${item.minimum}" aria-valuemax="${item.high - item.step}" aria-valuenow="${item.low}"><small>L</small></button>
        <button class="cpf-thumb cpf-thumb-high ${highLocked ? "is-locked" : ""}" data-thumb="high" style="left:${high}%" aria-label="${esc(item.label)} high ${item.high}" aria-disabled="${highLocked}" aria-valuemin="${item.low + item.step}" aria-valuemax="${item.maximum}" aria-valuenow="${item.high}"><small>H</small></button>
      </div>${proxy}
    </article>`;
  }

  function dialMarkup(item) {
    const angle = -150 + item.value / (item.maximum - item.minimum) * 300;
    const locked = channelLocked(item.id, "value");
    const proxy = interaction() === "simplified" ? `<div class="cpf-dial-step"><button data-dial-step="${esc(item.id)}:-1" ${locked ? "disabled" : ""}>−</button><b>${locked ? "LOCK" : valueText(item.value)}</b><button data-dial-step="${esc(item.id)}:1" ${locked ? "disabled" : ""}>+</button></div>` : "";
    return `<article class="cpf-dial-unit" data-dial-id="${esc(item.id)}">
      <span>${esc(item.label)}</span>
      <button class="cpf-dial ${locked ? "is-locked" : ""}" data-dial="${esc(item.id)}" role="spinbutton" aria-label="${esc(item.label)} rotary spinner" aria-disabled="${locked}" aria-valuemin="${item.minimum}" aria-valuemax="${item.maximum}" aria-valuenow="${item.value}" style="--dial-angle:${angle}deg">
        ${Array.from({length: 12}, (_, i) => {
          const tickAngle = -150 + i / 11 * 300;
          const radians = (tickAngle - 90) * Math.PI / 180;
          const x = 50 + Math.cos(radians) * 42;
          const y = 50 + Math.sin(radians) * 42;
          return `<i style="--tick:${tickAngle}deg;left:${x.toFixed(4)}%;top:${y.toFixed(4)}%"></i>`;
        }).join("")}
        <em></em><strong>${valueText(item.value)}</strong>
      </button>${proxy}
    </article>`;
  }

  function branchMarkup(branch) {
    const direct = interaction() === "full";
    const rows = branch.expanded ? branch.rows.map((row) => `<div class="cpf-tree-row depth-${row.depth}" role="row" data-row-id="${esc(row.id)}">
      <span role="gridcell">${esc(row.label)}</span>
      <button role="gridcell" data-circuit="${esc(row.id)}" aria-label="${esc(row.label)} state ${esc(row.state)}" ${direct ? "" : "tabindex=\"-1\""}>${esc(row.state)}</button>
      ${direct ? "" : `<button class="cpf-cycle" data-circuit-cycle="${esc(row.id)}">CYCLE</button>`}
    </div>`).join("") : "";
    const children = branch.expanded
      ? model.panel.branches.filter((item) => item.parent_id === branch.id).map(branchMarkup).join("")
      : "";
    return `<section class="cpf-tree-branch depth-${branch.depth}" role="rowgroup" data-branch-id="${esc(branch.id)}">
      <div class="cpf-tree-head" role="row">
        <button data-branch="${esc(branch.id)}" aria-expanded="${branch.expanded}" aria-label="${branch.expanded ? "Collapse" : "Expand"} ${esc(branch.label)}">${branch.expanded ? "▾" : "▸"}</button>
        <b role="gridcell">${esc(branch.label)}</b><small>${branch.rows.length} CIRCUITS</small>
        ${direct ? "" : `<button class="cpf-open-proxy" data-branch-toggle="${esc(branch.id)}">${branch.expanded ? "CLOSE" : "OPEN"}</button>`}
      </div>${rows}${children}
    </section>`;
  }

  function checklistMarkup() {
    const rangeLines = model.panel.ranges.map((item) => `<li><span>${esc(item.label)}</span><strong>${targetMarkup(item.id, "low", item.target_low)}<i>—</i>${targetMarkup(item.id, "high", item.target_high)}</strong></li>`).join("");
    const dialLines = model.panel.dials.map((item) => `<li><span>${esc(item.label)}</span>${targetMarkup(item.id, "value", item.target, true)}</li>`).join("");
    const treeLines = model.panel.branches.flatMap((branch) => branch.rows.map((row) => `<li><span>${esc(row.label)}</span><b>${esc(row.target)}</b></li>`)).join("");
    return `<aside class="cpf-checklist" aria-label="preflight target card">
      <div class="cpf-clip"></div><header><small>FORM CPF-27 / REV C</small><h2>PREFLIGHT CARD</h2><p>${esc(model.state.challenge_id.slice(-8).toUpperCase())}</p></header>
      <h3>ENVELOPES</h3><ul>${rangeLines}</ul><h3>ROTARY CHANNELS</h3><ul>${dialLines}</ul><h3>CIRCUIT TREE</h3><ul class="cpf-check-tree">${treeLines}</ul>
      <footer aria-hidden="true"><i></i><span>AIRFRAME 8 / BAY 4<br>FORM CPF-27</span></footer>
    </aside>`;
  }

  function instrumentMarkup() {
    return `<section class="cpf-instruments">
      <div class="cpf-panel-label"><span>FLIGHT TEST ARTICLE 8</span><b>POWER ISOLATED · CONFIGURATION MODE</b></div>
      <section class="cpf-ranges"><h2>ENVELOPE LIMITERS <small>DUAL THUMB / 5-UNIT DETENTS</small></h2>${model.panel.ranges.map(rangeMarkup).join("")}</section>
      <section class="cpf-dials"><h2>ROTARY COMPUTERS <small>12 DETENTS</small></h2><div>${model.panel.dials.map(dialMarkup).join("")}</div></section>
      <section class="cpf-tree" role="treegrid" aria-label="aircraft circuit treegrid"><h2>CIRCUIT TREEGRID <small>DISCLOSE PARENT BAYS · SET STATE CELLS</small></h2>${model.panel.branches.filter((branch) => !branch.parent_id).map(branchMarkup).join("")}</section>
    </section>`;
  }

  function updateActive(item, detail) {
    model.active = item.id;
    const node = document.getElementById("cpf-active-readout");
    const safeDetail = model.panel.readout_mode === "ticks" ? "INDEX CONFIRMED" : detail;
    if (node) node.innerHTML = `<small>ACTIVE CONTROL</small><b>${esc(item.label)}</b><strong>${esc(safeDetail)}</strong>`;
  }

  function update() {
    const checklist = document.querySelector(".cpf-checklist");
    if (checklist) checklist.outerHTML = checklistMarkup();
    const instruments = document.querySelector(".cpf-instruments");
    if (instruments) instruments.outerHTML = instrumentMarkup();
    bindControls();
  }

  function setRange(item, thumb, after, source, fraction, gesture = null) {
    const before = item[thumb];
    after = clamp(after, item.minimum, item.maximum);
    after = item.minimum + Math.round((after - item.minimum) / item.step) * item.step;
    const paired = (model.panel.couplings || []).find((coupling) => coupling.source.id === item.id && coupling.source.field === thumb && coupling.target.id === item.id);
    if (thumb === "low" && paired) {
      const predictedHigh = clamp(item.high + ((after - before) / item.step) * item.step * paired.ratio, item.minimum, item.maximum);
      after = Math.min(after, predictedHigh - item.step);
    } else if (thumb === "low") after = Math.min(after, item.high - item.step);
    else after = Math.max(after, item.low + item.step);
    if (after === before) return;
    item[thumb] = after;
    const coupling = applyCouplings(item, thumb, before, after);
    record({type: "range", id: item.id, thumb, before, after, input_source: source, ...coupling, ...(fraction == null ? {} : {pointer_fraction: Number(fraction.toFixed(6)), gesture})});
    updateActive(item, `${thumb.toUpperCase()} ${after}`);
    update();
  }

  function setDial(item, after, source, fraction, gesture = null) {
    const before = item.value;
    after = clamp(Math.round(after), item.minimum, item.maximum);
    if (after === before) return;
    item.value = after;
    const coupling = applyCouplings(item, "value", before, after);
    record({type: "dial", id: item.id, before, after, input_source: source, ...coupling, ...(fraction == null ? {} : {pointer_fraction: Number(fraction.toFixed(6)), gesture})});
    updateActive(item, `DETENT ${String(after).padStart(2, "0")}`);
    update();
  }

  function toggleBranch(branch, source) {
    const before = branch.expanded;
    branch.expanded = !before;
    record({type: "branch", id: branch.id, before, after: branch.expanded, input_source: source});
    updateActive(branch, branch.expanded ? "BAY OPEN" : "BAY CLOSED");
    update();
  }

  function cycleCircuit(row, source) {
    const states = model.panel.tree_states;
    const before = row.state;
    row.state = states[(states.indexOf(before) + 1) % states.length];
    record({type: "circuit", id: row.id, before, after: row.state, input_source: source});
    updateActive(row, row.state);
    update();
  }

  function pointerFraction(event, node) {
    const rect = node.getBoundingClientRect();
    return clamp((event.clientX - rect.left) / rect.width, 0, 1);
  }

  function dialFraction(event, node) {
    const rect = node.getBoundingClientRect();
    const angle = Math.atan2(event.clientY - (rect.top + rect.height / 2), event.clientX - (rect.left + rect.width / 2)) * 180 / Math.PI + 90;
    const normalized = angle > 180 ? angle - 360 : angle;
    return clamp((normalized + 150) / 300, 0, 1);
  }

  function bindControls() {
    document.querySelectorAll("[data-range-step]").forEach((button) => button.addEventListener("click", () => {
      const [id, thumb, direction] = button.dataset.rangeStep.split(":");
      const item = itemById(id); setRange(item, thumb, item[thumb] + Number(direction) * item.step, "range_step_button");
    }));
    document.querySelectorAll("[data-dial-step]").forEach((button) => button.addEventListener("click", () => {
      const [id, direction] = button.dataset.dialStep.split(":"); const item = itemById(id);
      setDial(item, item.value + Number(direction), "dial_step_button");
    }));
    document.querySelectorAll("[data-branch-toggle]").forEach((button) => button.addEventListener("click", () => toggleBranch(itemById(button.dataset.branchToggle), "tree_navigator")));
    document.querySelectorAll("[data-circuit-cycle]").forEach((button) => button.addEventListener("click", () => cycleCircuit(itemById(button.dataset.circuitCycle), "tree_cycle_button")));
    if (interaction() !== "full") return;
    document.querySelectorAll("[data-range-rail]").forEach((rail) => {
      let gesture = null;
      rail.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        const item = itemById(rail.dataset.rangeRail); const rect = rail.getBoundingClientRect(); const fraction = pointerFraction(event, rail);
        const lowFraction = (item.low - item.minimum) / (item.maximum - item.minimum); const highFraction = (item.high - item.minimum) / (item.maximum - item.minimum);
        const thumb = Math.abs(fraction - lowFraction) <= Math.abs(fraction - highFraction) ? "low" : "high";
        if (channelLocked(item.id, thumb)) return;
        const startFraction = thumb === "low" ? lowFraction : highFraction;
        if (Math.abs(fraction - startFraction) * rect.width > 18) return;
        event.preventDefault();
        gesture = {thumb, startFraction, lastX: event.clientX, travelPx: 0, samples: 0};
        rail.setPointerCapture?.(event.pointerId);
      });
      rail.addEventListener("pointermove", (event) => {
        if (!gesture) return;
        gesture.travelPx += Math.abs(event.clientX - gesture.lastX); gesture.lastX = event.clientX; gesture.samples += 1;
      });
      rail.addEventListener("pointerup", (event) => {
        if (!gesture) return;
        gesture.travelPx += Math.abs(event.clientX - gesture.lastX); gesture.samples += 1;
        const item = itemById(rail.dataset.rangeRail); const fraction = pointerFraction(event, rail);
        const value = item.minimum + Math.round(fraction * ((item.maximum - item.minimum) / item.step)) * item.step;
        const proof = {start_fraction: Number(gesture.startFraction.toFixed(6)), end_fraction: Number(fraction.toFixed(6)), travel_px: Number(gesture.travelPx.toFixed(3)), sample_count: gesture.samples};
        const thumb = gesture.thumb; const valid = gesture.travelPx >= 8 && gesture.samples >= 2;
        gesture = null;
        if (valid) setRange(item, thumb, value, "range_thumb_drag", fraction, proof);
      });
      rail.addEventListener("pointercancel", () => { gesture = null; });
    });
    document.querySelectorAll("[data-dial]").forEach((dial) => {
      let gesture = null;
      dial.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        const item = itemById(dial.dataset.dial); const rect = dial.getBoundingClientRect(); const fraction = (item.value - item.minimum) / (item.maximum - item.minimum);
        if (channelLocked(item.id, "value")) return;
        const angle = (-150 + fraction * 300 - 90) * Math.PI / 180; const radius = Math.min(rect.width, rect.height) * .39;
        const expectedX = rect.left + rect.width / 2 + Math.cos(angle) * radius; const expectedY = rect.top + rect.height / 2 + Math.sin(angle) * radius;
        if (Math.hypot(event.clientX - expectedX, event.clientY - expectedY) > 18) return;
        event.preventDefault();
        gesture = {startFraction: fraction, lastX: event.clientX, lastY: event.clientY, travelPx: 0, samples: 0};
        dial.setPointerCapture?.(event.pointerId);
      });
      dial.addEventListener("pointermove", (event) => {
        if (!gesture) return;
        gesture.travelPx += Math.hypot(event.clientX - gesture.lastX, event.clientY - gesture.lastY); gesture.lastX = event.clientX; gesture.lastY = event.clientY; gesture.samples += 1;
      });
      dial.addEventListener("pointerup", (event) => {
        if (!gesture) return;
        gesture.travelPx += Math.hypot(event.clientX - gesture.lastX, event.clientY - gesture.lastY); gesture.samples += 1;
        const item = itemById(dial.dataset.dial); const fraction = dialFraction(event, dial);
        const proof = {start_fraction: Number(gesture.startFraction.toFixed(6)), end_fraction: Number(fraction.toFixed(6)), travel_px: Number(gesture.travelPx.toFixed(3)), sample_count: gesture.samples};
        const valid = gesture.travelPx >= 8 && gesture.samples >= 2; gesture = null;
        if (valid) setDial(item, item.minimum + Math.round(fraction * (item.maximum - item.minimum)), "rotary_pointer", fraction, proof);
      });
      dial.addEventListener("pointercancel", () => { gesture = null; });
    });
    document.querySelectorAll("[data-branch]").forEach((button) => button.addEventListener("click", () => toggleBranch(itemById(button.dataset.branch), "tree_disclosure")));
    document.querySelectorAll("[data-circuit]").forEach((button) => button.addEventListener("click", () => cycleCircuit(itemById(button.dataset.circuit), "tree_cell")));
  }

  function showVerdict(kind) {
    const node = document.querySelector(".cpf-verdict");
    if (!node) return;
    node.className = `cpf-verdict is-${kind}`;
    node.innerHTML = `<b>${kind.toUpperCase()}</b>`;
  }

  async function submit() {
    if (!model || model.submitting || model.terminal) return;
    const current = model; current.submitting = true;
    current.helpers.setReadout("REPLAYING CONTROL TRANSCRIPT…", "pending");
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({
        mechanic_id: current.state.mechanic_id, task_id: current.state.task_id, challenge_id: current.state.challenge_id,
        interaction_mode: interaction(), events: current.events, final_state: finalState(), completed: true,
      })});
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.terminal = true; current.helpers.setReadout("PASS", "passed"); showVerdict("pass");
      } else if (outcome.passed === false && outcome.state) {
        const helpers = current.helpers;
        await render(outcome.state, helpers, {freshFailure: true});
        model.helpers.setReadout("FAIL", "error"); showVerdict("fail");
      } else {
        current.submitting = false; current.helpers.setReadout("CERTIFICATION REJECTED", "error");
      }
    } catch (_error) {
      if (model === current) { current.submitting = false; current.helpers.setReadout("CERTIFICATION LINK OFFLINE", "error"); }
    }
  }

  async function render(state, helpers, options = {}) {
    cleanup?.();
    document.body.dataset.mechanic = "cockpit-preflight-checklist";
    model = {state, helpers, panel: JSON.parse(JSON.stringify(state.panel)), events: [], revealed: new Set(), active: "", freshFailure: Boolean(options.freshFailure), submitting: false, terminal: false};
    helpers.app.innerHTML = `<section class="cockpit-preflight mode-${interaction()} readout-${esc(model.panel.readout_mode)}" data-fresh-failure="${options.freshFailure ? "true" : "false"}">
      <div class="cpf-verdict"></div>
      <header class="cpf-masthead"><div><small>EXPERIMENTAL AIRFRAME / BAY 4</small><h1>${esc(state.prompt)}</h1></div><div class="cpf-mode"><i></i><span>${interaction().toUpperCase()} INPUT</span><b>STATIC CONFIG</b></div></header>
      <main>${checklistMarkup()}${instrumentMarkup()}</main>
      <footer class="cpf-footer"><div id="cpf-active-readout"><small>ACTIVE CONTROL</small><b>NONE SELECTED</b><strong>—</strong></div><div class="readout" data-status="idle">PANEL READY · CARD NOT CERTIFIED</div><button id="cpf-certify">CERTIFY PANEL</button></footer>
      ${helpers.cheatPanelTemplate()}
    </section>`;
    bindControls();
    document.getElementById("cpf-certify").addEventListener("click", submit);
    helpers.installCheatPanel();
    cleanup = () => {};
    if (options.freshFailure) showVerdict("fail");
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.cockpit_preflight_checklist = {rootSelector: ".cockpit-preflight", render};
})();
