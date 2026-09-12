(function () {
  const DELTAS = {N: [0, -1], E: [1, 0], S: [0, 1], W: [-1, 0]};
  const LABELS = {N: "NORTH", E: "EAST", S: "SOUTH", W: "WEST", LASSO: "LASSO", RESET: "RESET"};
  let helpersCache = null;
  let model = null;
  let keyHandler = null;

  function pointKey(point) { return `${point[0]},${point[1]}`; }
  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function point(value) { return [Number(value[0]), Number(value[1])]; }
  function same(a, b) { return a[0] === b[0] && a[1] === b[1]; }
  function cargoAt(target) { return model.cargo.find((item) => same(item.position, target)); }
  function wallAt(target) { return model.walls.has(pointKey(target)); }
  function solved() { return model.cargo.every((item) => same(item.position, item.pad)); }
  function now() {
    const value = Number(helpersCache?.interactionNow?.() ?? performance.now());
    return Number.isFinite(value) ? value : performance.now();
  }

  function snapshot() {
    return {
      tug: point(model.tug),
      cargo: model.cargo.map((item) => ({id: item.id, position: point(item.position), pulls: Number(item.pulls)})),
      rope_path: model.rope.map(point),
      solved: solved(),
    };
  }

  function resetState() {
    model.tug = point(model.initial.tug);
    model.cargo = clone(model.initial.cargo);
    model.rope = [point(model.tug)];
    model.events = [];
  }

  function appendRope(target) {
    model.rope.push(point(target));
    while (model.rope.length > model.capacity) model.rope.shift();
  }

  function performMove(direction) {
    const delta = DELTAS[direction];
    const target = [model.tug[0] + delta[0], model.tug[1] + delta[1]];
    if (wallAt(target) || target[0] < 0 || target[1] < 0 || target[0] >= model.width || target[1] >= model.height) {
      return "blocked_wall";
    }
    if (cargoAt(target)) return "blocked_cargo";
    model.tug = target;
    appendRope(target);
    return "move";
  }

  function performLasso() {
    const occupied = new Set(model.rope.map(pointKey));
    for (const item of model.cargo) {
      if (same(item.position, item.pad)) continue;
      const required = [[0, -1], [1, 0], [0, 1], [-1, 0]].map(([dx, dy]) => [item.position[0] + dx, item.position[1] + dy]);
      if (!required.every((target) => occupied.has(pointKey(target)))) continue;
      let x = item.position[0];
      let y = item.position[1];
      if (x !== item.pad[0]) x += item.pad[0] > x ? 1 : -1;
      else if (y !== item.pad[1]) y += item.pad[1] > y ? 1 : -1;
      item.position = [x, y];
      item.pulls += 1;
      return `snag:${item.id}`;
    }
    return "lasso_empty";
  }

  function outcomeText(outcome) {
    if (outcome === "move") return "TUG MOVED · ROPE EXTENDED";
    if (outcome === "blocked_wall") return "FENCE CONTACT · TUG HELD";
    if (outcome === "blocked_cargo") return "CARGO BLOCKS ROUTE";
    if (outcome === "lasso_empty") return "NO CLOSED LOOP YET";
    if (outcome.startsWith("snag:")) return `${outcome.slice(5).toUpperCase()} SNAGGED · PULL REGISTERED`;
    if (outcome === "reset") return "YARD RESET · ROPE CLEARED";
    return outcome;
  }

  function ropeMarkup() {
    const path = model.rope.map((item) => `${item[0] * 100 + 50},${item[1] * 100 + 50}`).join(" ");
    if (!path) return "";
    return `<svg class="lasso-rope" viewBox="0 0 ${model.width * 100} ${model.height * 100}" aria-label="trailing rope path" preserveAspectRatio="none">
      <polyline points="${path}" fill="none" stroke="rgba(250,193,72,.26)" stroke-width="30" stroke-linecap="round" stroke-linejoin="round"></polyline>
      <polyline points="${path}" fill="none" stroke="#ffc44e" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"></polyline>
    </svg>`;
  }

  function renderBoard() {
    const grid = document.getElementById("lasso-grid");
    if (!grid) return;
    const walls = model.walls;
    const pads = new Map(model.cargo.map((item) => [pointKey(item.pad), item.id]));
    const cargo = new Map(model.cargo.map((item) => [pointKey(item.position), item]));
    const cells = [];
    for (let y = 0; y < model.height; y += 1) {
      for (let x = 0; x < model.width; x += 1) {
        const key = `${x},${y}`;
        const item = cargo.get(key);
        const pad = pads.get(key);
        const wall = walls.has(key);
        const occupant = same(model.tug, [x, y]);
        cells.push(`<div class="lasso-cell${wall ? " is-wall" : ""}${pad ? " is-pad" : ""}${item ? " has-cargo" : ""}${occupant ? " has-tug" : ""}" data-x="${x}" data-y="${y}">
          ${wall ? '<span class="fence">✦</span>' : pad ? `<span class="pad-mark">${helpersCache.text(pad.replace("cargo-", "C"))}</span>` : '<span class="yard-dash">·</span>'}
          ${item ? `<span class="freight" data-cargo-id="${helpersCache.text(item.id)}"><b>${helpersCache.text(item.id.replace("cargo-", "C"))}</b><i></i></span>` : ""}
          ${occupant ? '<span class="tug" aria-label="walking tug"><i></i><b>▲</b></span>' : ""}
        </div>`);
      }
    }
    grid.innerHTML = `${ropeMarkup()}<div class="lasso-cell-grid">${cells.join("")}</div>`;
  }

  function renderTape() {
    const tape = document.getElementById("lasso-tape");
    if (!tape) return;
    tape.innerHTML = model.events.slice(-12).map((event) => `<li class="tape-${event.outcome.startsWith("blocked") || event.outcome === "lasso_empty" ? "warn" : event.outcome.startsWith("snag") ? "snag" : "move"}">
      <b>${String(event.sequence).padStart(2, "0")}</b><span>${helpersCache.text(LABELS[event.issued] || event.issued)}</span><small>${helpersCache.text(outcomeText(event.outcome))}</small>
    </li>`).join("");
  }

  function renderReadout(issued, outcome) {
    const command = document.getElementById("lasso-last-command");
    const result = document.getElementById("lasso-last-result");
    const rope = document.getElementById("lasso-rope-count");
    const pulls = document.getElementById("lasso-pull-count");
    const status = document.getElementById("lasso-yard-status");
    if (command) command.textContent = issued ? LABELS[issued] || issued : "WAITING";
    if (result) result.textContent = outcome ? outcomeText(outcome) : "NO TRANSITION";
    if (rope) rope.textContent = `${model.rope.length} / ${model.capacity}`;
    if (pulls) pulls.textContent = `${model.cargo.reduce((sum, item) => sum + Number(item.pulls), 0)} / ${model.cargo.reduce((sum, item) => sum + Math.abs(item.pad[0] - model.initial.cargo.find((start) => start.id === item.id).position[0]) + Math.abs(item.pad[1] - model.initial.cargo.find((start) => start.id === item.id).position[1]), 0)}`;
    if (status) status.textContent = solved() ? "ALL PADS OCCUPIED · READY" : "YARD OPEN · LOOP THE ROPE";
  }

  function record(issued, inputSource) {
    if (!model || model.submitting || model.terminal) return;
    const before = snapshot();
    let type;
    let outcome;
    if (DELTAS[issued]) {
      type = "move";
      outcome = performMove(issued);
    } else if (issued === "LASSO") {
      type = "lasso";
      outcome = performLasso();
    } else if (issued === "RESET") {
      type = "reset";
      resetState();
      outcome = "reset";
    } else return;
    const event = {
      sequence: model.events.length + 1,
      t_ms: now(),
      type,
      issued,
      input_source: inputSource,
      before,
      outcome,
      after: snapshot(),
    };
    model.events.push(event);
    renderBoard();
    renderTape();
    renderReadout(issued, outcome);
    helpersCache.setReadout(outcomeText(outcome), outcome.startsWith("blocked") || outcome === "lasso_empty" ? "error" : "idle");
  }

  async function certify() {
    if (!model || model.submitting || model.terminal) return;
    model.submitting = true;
    const button = document.getElementById("lasso-certify");
    if (button) button.disabled = true;
    helpersCache.setReadout("REPLAYING ROPE TRANSCRIPT…", "idle");
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      actions: model.events,
      final_state: snapshot(),
      completed: solved(),
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const result = await response.json();
      if (result.passed === true) {
        model.terminal = true;
        document.querySelector(".lasso-captcha")?.classList.add("is-pass");
        document.getElementById("lasso-verdict").innerHTML = "<b>PASS</b><span>FREIGHT MANIFEST ACCEPTED</span>";
        helpersCache.setReadout("PASS · YARD CERTIFIED", "passed");
      } else if (result.passed === false) {
        if (result.state) await helpersCache.render(result.state);
        else { model.submitting = false; if (button) button.disabled = false; }
        helpersCache.setReadout("FAIL · FRESH YARD ISSUED", "error");
      } else {
        model.submitting = false;
        if (button) button.disabled = false;
        helpersCache.setReadout("AUDIT UNAVAILABLE", "error");
      }
    } catch (_error) {
      model.submitting = false;
      if (button) button.disabled = false;
      helpersCache.setReadout("AUDIT LINK OFFLINE", "error");
    }
  }

  async function render(state, helpers) {
    helpersCache = helpers || helpersCache;
    if (!helpersCache) throw new Error("lasso_freight requires runtime helpers");
    if (keyHandler) window.removeEventListener("keydown", keyHandler);
    const board = state.board || {};
    const interaction = state.control_condition?.interaction || "full";
    model = {
      state,
      interaction,
      width: Number(board.width),
      height: Number(board.height),
      capacity: Number(state.rope_capacity || 96),
      walls: new Set((board.walls || []).map(pointKey)),
      initial: {tug: point(board.start), cargo: clone(board.cargo || [])},
      tug: point(board.start),
      cargo: clone(board.cargo || []),
      rope: [point(board.start)],
      events: [],
      submitting: false,
      terminal: false,
    };
    window.lassoFreightModel = model;
    document.body.dataset.mechanic = "lasso-freight";
    document.body.dataset.lassoPalette = helpersCache.text(board.palette || "copper");
    document.body.dataset.cheatMode = helpersCache.isCheatMode() ? "true" : "false";
    const controls = interaction === "simplified" ? `<div class="lasso-keypad" aria-label="yard direction controls">
      <button type="button" data-command="N" aria-label="move north">↑<small>N</small></button><button type="button" data-command="W" aria-label="move west">←<small>W</small></button><button type="button" data-command="S" aria-label="move south">↓<small>S</small></button><button type="button" data-command="E" aria-label="move east">→<small>E</small></button>
    </div><button class="lasso-pull" type="button" data-command="LASSO">◌ <span>CAST LASSO</span></button><p class="control-note">VISIBLE BUTTONS · TILE BY TILE</p>` : `<div class="keyboard-card"><b>KEYBOARD DECK</b><span>ARROWS / WASD&nbsp; move the tug</span><span>SPACE&nbsp; cast the lasso</span><span>R&nbsp; reset the yard</span></div>`;
    helpersCache.app.innerHTML = `<section class="lasso-captcha" data-interaction="${helpersCache.text(interaction)}" data-challenge-id="${helpersCache.text(state.challenge_id)}">
      <header class="lasso-header"><div><span class="eyebrow">FREIGHT CONTROL / SHIFT 07</span><h1>LASSO <em>FREIGHT</em></h1><p>${helpersCache.text(state.prompt)}</p></div><div class="challenge-stamp"><small>MANIFEST</small><b>${helpersCache.text(String(state.challenge_id).toUpperCase())}</b><i>LIVE YARD</i></div></header>
      <main class="lasso-main"><section class="yard-panel"><div class="yard-topline"><span>TOP-DOWN LOADING YARD</span><b>ROPE LINK <i></i></b></div><div class="lasso-board-wrap"><div id="lasso-grid" class="lasso-grid" style="--cols:${model.width};--rows:${model.height}"></div><div class="board-legend"><span><i class="legend-rope"></i>trailing rope</span><span><i class="legend-pad"></i>receiving pad</span><span><i class="legend-tug"></i>walking tug</span></div><div id="lasso-verdict" class="lasso-verdict"><b>OPEN</b><span>ROUTE IN PROGRESS</span></div></div></section>
        <aside class="lasso-console"><div class="console-head"><span>YARD CONSOLE</span><b>INDIRECT LOAD</b></div><div class="telemetry"><div><small>LAST COMMAND</small><strong id="lasso-last-command">WAITING</strong></div><div><small>PHYSICAL RESULT</small><strong id="lasso-last-result">NO TRANSITION</strong></div></div><div class="meter-row"><span>ROPE OCCUPANCY</span><b id="lasso-rope-count">1 / ${model.capacity}</b></div><div class="meter"><i id="lasso-rope-meter"></i></div><div class="meter-row"><span>PAD PULLS</span><b id="lasso-pull-count">0</b></div><div class="console-controls">${controls}</div>${interaction === "simplified" ? '<button id="lasso-reset" class="reset-control" type="button">↺ RESET YARD</button>' : '<div class="reset-control">R · RESET YARD</div>'}</aside></main>
      <section class="tape-panel"><div class="tape-label"><span>ACTION TAPE</span><small>LEGAL TRANSITIONS ONLY</small></div><ol id="lasso-tape"></ol></section>
      <footer class="lasso-footer"><div><span id="lasso-yard-status">YARD OPEN · LOOP THE ROPE</span><div class="readout" data-status="idle">WAITING FOR TUG COMMAND</div></div><button id="lasso-certify" class="certify" type="button">CERTIFY YARD&nbsp; →</button></footer>
    </section>`;
    document.querySelectorAll("[data-command]").forEach((button) => button.addEventListener("click", () => record(button.dataset.command, "control_buttons")));
    document.getElementById("lasso-reset")?.addEventListener("click", () => record("RESET", "control_buttons"));
    document.getElementById("lasso-certify")?.addEventListener("click", certify);
    keyHandler = (event) => {
      if (interaction !== "full" || event.repeat || model.submitting || model.terminal) return;
      const key = event.key.toLowerCase();
      const direction = {arrowup: "N", w: "N", arrowright: "E", d: "E", arrowdown: "S", s: "S", arrowleft: "W", a: "W"}[key];
      if (direction) { event.preventDefault(); record(direction, "keyboard"); }
      else if (key === " " || key === "spacebar") { event.preventDefault(); record("LASSO", "keyboard"); }
      else if (key === "r") { event.preventDefault(); record("RESET", "keyboard"); }
    };
    window.addEventListener("keydown", keyHandler);
    renderBoard();
    renderTape();
    renderReadout(null, null);
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.lasso_freight = {rootSelector: ".lasso-captcha", render};
})();
