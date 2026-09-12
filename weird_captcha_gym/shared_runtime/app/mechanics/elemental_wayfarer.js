(() => {
  "use strict";

  const DIRECTIONS = {
    UP: [0, -1],
    DOWN: [0, 1],
    LEFT: [-1, 0],
    RIGHT: [1, 0],
  };
  const ELEMENTS = {
    ember: {label: "EMBER", glyph: "✦", color: "ember"},
    tide: {label: "TIDE", glyph: "≈", color: "tide"},
    zephyr: {label: "ZEPHYR", glyph: "⌁", color: "zephyr"},
    basalt: {label: "BASALT", glyph: "◆", color: "basalt"},
  };
  const model = {
    state: null,
    tiles: new Map(),
    pos: {x: 0, y: 0},
    start: {x: 0, y: 0},
    exit: {x: 0, y: 0, requires: ""},
    form: "clay",
    collected: new Set(),
    actions: [],
    ready: false,
    terminal: false,
    busy: false,
    interaction: "full",
    helpers: null,
    keyHandler: null,
  };

  const clean = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

  function tileAt(x, y) { return model.tiles.get(`${x},${y}`) || null; }

  function formLabel(form) { return form === "clay" ? "CLAY" : (ELEMENTS[form]?.label || String(form).toUpperCase()); }
  function formGlyph(form) { return form === "clay" ? "●" : (ELEMENTS[form]?.glyph || "●"); }

  function tileClass(tile) {
    const special = tile.element ? ` element-${clean(tile.element)}` : "";
    return `wayfarer-tile tile-${clean(tile.kind)}${special}`;
  }

  function tileMarkup(tile) {
    const isHere = model.pos.x === tile.x && model.pos.y === tile.y;
    const isExit = model.exit.x === tile.x && model.exit.y === tile.y;
    const isCollected = tile.id && model.collected.has(String(tile.id));
    const body = tile.kind === "wall" ? "" : tile.kind === "token" || tile.kind === "decoy"
      ? `<span class="tile-token-glyph">${clean(ELEMENTS[tile.element]?.glyph || "?")}</span><small>${clean(formLabel(tile.element))}</small>`
      : tile.kind === "gate"
        ? `<span class="tile-gate-glyph">${clean(ELEMENTS[tile.element]?.glyph || "◇")}</span><small>SEAL</small>`
        : isExit
          ? `<span class="tile-exit-glyph">✧</span><small>EXIT</small>`
          : "";
    const traveler = isHere ? `<span class="wayfarer-avatar element-${clean(model.form)}"><b>${clean(formGlyph(model.form))}</b></span>` : "";
    const classes = `${tileClass(tile)}${isHere ? " is-current" : ""}${isCollected ? " is-collected" : ""}`;
    return `<div class="${classes}" data-x="${tile.x}" data-y="${tile.y}">${body}${traveler}</div>`;
  }

  function boardMarkup() {
    const chamber = model.state.chamber;
    return model.state.chamber.tiles.map(tileMarkup).join("");
  }

  function actionButtons() {
    if (model.interaction !== "simplified") return `<div class="keyboard-card"><b>KEYBOARD PILOT</b><p>Use <kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> or the arrow keys to move one tile.</p><span>Direction controls are not active in this mode.</span></div>`;
    return `<div class="direction-pad" aria-label="Direction controls">
      <button type="button" data-action="UP" aria-label="Move up">▲</button>
      <div><button type="button" data-action="LEFT" aria-label="Move left">◀</button><button type="button" data-action="DOWN" aria-label="Move down">▼</button><button type="button" data-action="RIGHT" aria-label="Move right">▶</button></div>
    </div>`;
  }

  function rulesMarkup() {
    return Object.entries(ELEMENTS).map(([element, info]) => `<div class="rule-row element-${element}"><b>${clean(info.glyph)}</b><span><strong>${clean(info.label)}</strong><small>changes the traveler's form</small></span></div>`).join("");
  }

  function renderBoard() {
    const board = document.getElementById("wayfarer-board");
    if (board) board.innerHTML = boardMarkup();
    const position = document.getElementById("wayfarer-position");
    if (position) position.textContent = `${model.pos.x + 1},${model.pos.y + 1}`;
    const form = document.getElementById("wayfarer-form");
    if (form) {
      form.textContent = formLabel(model.form);
      form.dataset.element = model.form;
    }
    const sideForm = document.getElementById("wayfarer-side-form");
    if (sideForm) sideForm.textContent = formLabel(model.form);
    const sideGlyph = document.getElementById("wayfarer-side-form-glyph");
    if (sideGlyph) sideGlyph.textContent = formGlyph(model.form);
    const glyph = document.getElementById("wayfarer-form-glyph");
    if (glyph) glyph.textContent = formGlyph(model.form);
    const count = document.getElementById("wayfarer-collected");
    if (count) count.textContent = `${model.collected.size}`;
    const certify = document.getElementById("wayfarer-certify");
    if (certify) certify.disabled = model.busy || model.terminal;
    document.querySelectorAll(".wayfarer-token-list li").forEach((node) => {
      node.classList.toggle("is-collected", model.collected.has(node.dataset.tokenId));
    });
  }

  function flash(message, status = "idle") {
    model.helpers.setReadout(message, status);
    const shell = document.querySelector(".elemental-wayfarer");
    shell?.classList.remove("is-jolt");
    void shell?.offsetWidth;
    shell?.classList.add("is-jolt");
  }

  function clearVerdict() {
    document.querySelectorAll(".wayfarer-verdict").forEach((node) => node.remove());
    document.querySelector(".elemental-wayfarer")?.classList.remove("is-pass", "is-fail");
  }

  function setTokenList() {
    const node = document.getElementById("wayfarer-token-list");
    if (!node) return;
    node.innerHTML = model.state.chamber.tiles
      .filter((tile) => tile.kind === "token")
      .map((tile) => `<li data-token-id="${clean(tile.id)}" class="element-${clean(tile.element)}"><b>${clean(tile.order)}</b><span>${clean(ELEMENTS[tile.element]?.glyph || "?")}</span><strong>${clean(formLabel(tile.element))}</strong></li>`)
      .join("");
  }

  function resetAttempt() {
    if (model.busy) return;
    model.pos = {...model.start};
    model.form = "clay";
    model.collected = new Set();
    model.actions = [];
    model.ready = false;
    model.terminal = false;
    clearVerdict();
    renderBoard();
    flash("CHAMBER RESET · CLAY FORM RESTORED", "idle");
  }

  async function submit(completed) {
    if (!model.state || model.busy) return;
    model.busy = true;
    renderBoard();
    model.helpers.setReadout(completed ? "CERTIFYING ARRIVAL…" : "VOIDING ATTEMPT…", "pending");
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      actions: model.actions,
      completed,
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true;
        document.querySelector(".elemental-wayfarer")?.classList.add("is-pass");
        document.querySelector(".elemental-wayfarer")?.insertAdjacentHTML("beforeend", '<div class="wayfarer-verdict wayfarer-verdict-pass"><small>CHAMBER ROUTE ACCEPTED</small><strong>PASS</strong></div>');
        model.helpers.setReadout("PASS · WAYFARER ARRIVED", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state, model.helpers);
        document.querySelector(".elemental-wayfarer")?.classList.add("is-fail");
        document.querySelector(".elemental-wayfarer")?.insertAdjacentHTML("beforeend", '<div class="wayfarer-verdict wayfarer-verdict-fail"><small>ROUTE VOID · NEW CHAMBER</small><strong>FAIL</strong></div>');
        model.helpers.setReadout("FAIL · NEW CHAMBER DRAWN", "error");
      } else {
        model.busy = false;
        renderBoard();
        model.helpers.setReadout("FAIL · EXIT NOT REACHED", "error");
      }
    } catch (_error) {
      model.busy = false;
      renderBoard();
      model.helpers.setReadout("FAIL · REGISTER OFFLINE", "error");
    }
  }

  function move(action, source) {
    if (model.busy || model.terminal) return;
    if (model.interaction === "simplified" && source !== "direction_button") return;
    if (model.interaction === "full" && source !== "keyboard") return;
    clearVerdict();
    const [dx, dy] = DIRECTIONS[action];
    const from = [model.pos.x, model.pos.y];
    const candidate = {x: model.pos.x + dx, y: model.pos.y + dy};
    const tile = tileAt(candidate.x, candidate.y);
    let outcome = "blocked_wall";
    let to = {...model.pos};
    let nextForm = model.form;
    let collectedToken = null;
    if (tile && tile.kind !== "wall") {
      if (tile.kind === "gate" && tile.element !== model.form) {
        outcome = "blocked_gate";
        flash(`SEAL REJECTED · NEED ${formLabel(tile.element)}`, "error");
      } else {
        model.pos = candidate;
        to = {...candidate};
        outcome = "step";
        if ((tile.kind === "token" || tile.kind === "decoy") && !model.collected.has(String(tile.id))) {
          collectedToken = String(tile.id);
          model.collected.add(collectedToken);
          nextForm = tile.element;
          model.form = nextForm;
          outcome = `collect_${nextForm}`;
          flash(`FORM SHIFT · ${formLabel(nextForm)}`, "passed");
        }
        if (candidate.x === model.exit.x && candidate.y === model.exit.y && nextForm === model.exit.requires) {
          model.ready = true;
          outcome = "arrive";
          flash("EXIT REACHED · CERTIFY THE ARRIVAL", "passed");
        } else if (outcome === "step") {
          flash(`MOVED ${action} · ${formLabel(model.form)} FORM`, "idle");
        }
      }
    } else {
      flash("WALL · CHOOSE ANOTHER DIRECTION", "error");
    }
    const event = {
      sequence: model.actions.length + 1,
      action,
      input_source: source,
      from,
      to: [to.x, to.y],
      outcome,
      form_after: model.form,
      collected_token: collectedToken,
    };
    model.actions.push(event);
    renderBoard();
  }

  function bindControls() {
    document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => move(button.dataset.action, "direction_button")));
    document.getElementById("wayfarer-reset")?.addEventListener("click", resetAttempt);
    document.getElementById("wayfarer-certify")?.addEventListener("click", () => submit(model.ready));
    if (model.keyHandler) window.removeEventListener("keydown", model.keyHandler);
    model.keyHandler = (event) => {
      if (model.interaction !== "full" || event.repeat) return;
      const key = String(event.key || "").toLowerCase();
      const action = {arrowup: "UP", w: "UP", arrowdown: "DOWN", s: "DOWN", arrowleft: "LEFT", a: "LEFT", arrowright: "RIGHT", d: "RIGHT"}[key];
      if (!action) return;
      event.preventDefault();
      move(action, "keyboard");
    };
    window.addEventListener("keydown", model.keyHandler);
  }

  async function render(state, helpers) {
    if (model.keyHandler) window.removeEventListener("keydown", model.keyHandler);
    const chamber = state.chamber || {};
    model.state = state;
    model.tiles = new Map((chamber.tiles || []).map((tile) => [`${tile.x},${tile.y}`, {...tile}]));
    model.start = {...chamber.start};
    model.exit = {...chamber.exit};
    model.pos = {...model.start};
    model.form = state.initial_form || "clay";
    model.collected = new Set();
    model.actions = [];
    model.ready = false;
    model.terminal = false;
    model.busy = false;
    model.interaction = state.control_condition?.interaction || "full";
    model.helpers = helpers;
    document.body.dataset.mechanic = "elemental-wayfarer";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    helpers.app.innerHTML = `<section class="elemental-wayfarer" data-interaction="${clean(model.interaction)}" data-challenge-id="${clean(state.challenge_id)}">
      <header class="wayfarer-head"><div><span class="wayfarer-kicker">THE LANTERNED PASSAGE · CHAMBER ${Number(state.generator?.level || 4)}</span><h1>${clean(state.prompt)}</h1></div><div class="wayfarer-stamp"><small>CURRENT FORM</small><b id="wayfarer-form-glyph">●</b><strong id="wayfarer-form">CLAY</strong><i id="wayfarer-position">1,1</i></div></header>
      <main class="wayfarer-workbench"><section class="wayfarer-map-panel"><div class="wayfarer-panel-label"><span>VISIBLE CHAMBER MAP</span><b>${Number(chamber.width)} × ${Number(chamber.height)}</b></div><div class="wayfarer-board-wrap"><div class="wayfarer-board" id="wayfarer-board" style="--cols:${Number(chamber.width)};--rows:${Number(chamber.height)}">${boardMarkup()}</div></div><div class="wayfarer-map-note"><span><i class="legend-swatch traveler"></i>TRAVELER</span><span><i class="legend-swatch seal"></i>FORM SEAL</span><span><i class="legend-swatch exit"></i>EXIT</span><b>READ THE GLYPH BEFORE CROSSING</b></div></section>
        <aside class="wayfarer-side"><section class="wayfarer-now"><small>TRAVELER STATE</small><div class="wayfarer-now-form"><b id="wayfarer-side-form-glyph">●</b><span id="wayfarer-side-form">CLAY</span></div><p>Collected route tokens: <strong id="wayfarer-collected">0</strong></p></section><section class="wayfarer-token-card"><header><span>ROUTE TOKENS</span><small>INVISIBLE ORDER IS NOT USED</small></header><ol class="wayfarer-token-list" id="wayfarer-token-list"></ol></section><section class="wayfarer-rules"><header>VISIBLE MATERIAL RULES</header>${rulesMarkup()}<p class="wayfarer-exit-rule">EXIT REQUIRES <b>${clean(formLabel(model.exit.requires))}</b></p></section>${actionButtons()}</aside></main>
      <footer class="wayfarer-foot"><button type="button" id="wayfarer-reset">↺ RESET CHAMBER</button><div class="readout" data-status="idle">${clean(model.interaction === "full" ? "KEYBOARD PILOT · CLAY FORM" : "CHOOSE A DIRECTION · CLAY FORM")}</div><button type="button" id="wayfarer-certify">${clean(state.submit_label || "CERTIFY ARRIVAL")}</button></footer>${helpers.cheatPanelTemplate()}</section>`;
    setTokenList();
    bindControls();
    renderBoard();
    helpers.installCheatPanel();
    window.elementalWayfarerModel = model;
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.elemental_wayfarer = {rootSelector: ".elemental-wayfarer", render};
})();
