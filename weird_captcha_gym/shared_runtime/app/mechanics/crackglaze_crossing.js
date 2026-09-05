(() => {
  "use strict";

  const MECHANIC_ID = "crackglaze_crossing";
  let model = null;
  let cleanup = null;

  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const interaction = () => model.state.control_condition?.interaction || "full";
  const cellsById = () => Object.fromEntries(model.state.cells.map((cell) => [cell.id, cell]));
  const cell = (id) => cellsById()[id];

  function pointInBoard(event) {
    const rect = document.querySelector(".crack-board").getBoundingClientRect();
    return [
      Number(((event.clientX - rect.left) / rect.width).toFixed(6)),
      Number(((event.clientY - rect.top) / rect.height).toFixed(6)),
    ];
  }

  function direction(origin, destination) {
    const first = cell(origin); const second = cell(destination);
    const delta = [second.row - first.row, second.column - first.column];
    return ({"-1,0": "up", "1,0": "down", "0,-1": "left", "0,1": "right"})[delta.join(",")] || "";
  }

  function fuseFor(cellId) {
    return Number(model.state.fuse_lengths[cell(cellId).glaze]);
  }

  function updateShattered() {
    model.shattered = new Set(Object.entries(model.litAt)
      .filter(([cellId, litStep]) => model.step - Number(litStep) >= fuseFor(cellId))
      .map(([cellId]) => cellId));
  }

  function tileStage(cellId) {
    if (model.shattered.has(cellId)) return "shattered";
    if (!(cellId in model.litAt)) return "unlit";
    const age = model.step - Number(model.litAt[cellId]);
    const remaining = fuseFor(cellId) - age;
    if (remaining <= 1) return "critical";
    if (remaining <= Math.max(2, Math.ceil(fuseFor(cellId) / 3))) return "crazed";
    if (age >= 1) return "hairline";
    return "lit";
  }

  function tileMarkup(item) {
    const glaze = model.state.glazes.find((value) => value.id === item.glaze);
    const stage = tileStage(item.id);
    const current = model.position === item.id;
    const classes = ["crack-tile", `stage-${stage}`, `glaze-${item.glaze}`];
    if (item.under_gallery) classes.push("under-gallery");
    if (current) classes.push("is-current");
    if (item.exit) classes.push("is-exit");
    if (item.start) classes.push("is-start");
    const inner = `<span class="ceramic" style="--glaze:${esc(glaze.color)};--vein:${esc(glaze.vein)}"><i class="crack-a"></i><i class="crack-b"></i></span>
      ${item.under_gallery ? '<span class="gallery-shadow"><i></i></span>' : ""}
      ${item.lantern && !model.collected.has(item.id) ? '<span class="tile-lantern" aria-label="uncollected lantern"><i></i></span>' : ""}
      ${item.lantern && model.collected.has(item.id) ? '<span class="lantern-echo">✦</span>' : ""}
      ${item.exit ? `<span class="far-door ${model.collected.size === model.state.lantern_ids.length ? "is-open" : ""}"><i></i></span>` : ""}
      ${item.start ? '<span class="start-mark" aria-label="starting tile"></span>' : ""}
      ${current && model.status !== "failed" ? '<span class="walker"><i></i></span>' : ""}`;
    const style = `grid-row:${item.row + 1};grid-column:${item.column + 1}`;
    // The hole remains the visible target geometry for a losing step.  Making
    // shattered ground non-clickable would silently protect Full-mode players
    // from the same expired-destination failure that the direction pad allows.
    if (interaction() === "full") {
      return `<button class="${classes.join(" ")}" data-cell-id="${esc(item.id)}" data-stage="${stage}" style="${style}" aria-label="Ceramic tile ${item.row + 1}, ${item.column + 1}">${inner}</button>`;
    }
    return `<div class="${classes.join(" ")}" data-cell-id="${esc(item.id)}" data-stage="${stage}" style="${style}">${inner}</div>`;
  }

  function controlsMarkup() {
    if (interaction() !== "simplified") return "";
    return `<div class="crack-dpad" aria-label="step controls">
      <button data-direction="up" aria-label="Step up">↑</button>
      <button data-direction="left" aria-label="Step left">←</button>
      <span aria-hidden="true"></span>
      <button data-direction="right" aria-label="Step right">→</button>
      <button data-direction="down" aria-label="Step down">↓</button>
    </div>`;
  }

  function finalState() {
    return {
      position: model.position,
      step_count: model.step,
      collected_lantern_ids: [...model.collected].sort(),
      lit_at: Object.fromEntries(Object.entries(model.litAt).sort(([a], [b]) => a.localeCompare(b))),
      shattered_cell_ids: [...model.shattered].sort(),
      status: model.status,
    };
  }

  function renderRoot() {
    const root = document.querySelector(".crackglaze-crossing");
    if (!root) return;
    root.dataset.position = model.position;
    root.dataset.step = String(model.step);
    root.dataset.terminal = model.verified ? "passed" : model.status === "failed" ? "failed" : "active";
    const tiles = model.state.cells.map(tileMarkup).join("");
    root.innerHTML = `${model.freshFailure ? '<div class="crack-fresh-failure">FAIL</div>' : ""}
      <header class="crack-masthead">
        <div class="crack-seal"><span>窯</span><small>CC</small></div>
        <h1>${esc(model.state.prompt)}</h1>
      </header>
      <main class="crack-stage">
        <section class="crack-board-shell">
          <div class="gallery-canopy" aria-hidden="true"></div>
          <div class="crack-board contrast-${esc(model.state.parameters.crack_contrast)}" style="--rows:${model.state.rows};--columns:${model.state.columns}">${tiles}</div>
        </section>
        ${interaction() === "simplified" ? `<aside class="crack-sidebar">${controlsMarkup()}</aside>` : ""}
      </main>
      <footer class="crack-footer"><div class="readout" data-status="${model.verified ? "passed" : model.status === "failed" ? "error" : "idle"}">${model.verified ? "PASS" : model.status === "failed" ? "FAIL" : ""}</div></footer>
      ${model.helpers.cheatPanelTemplate()}`;
    bind();
    model.helpers.installCheatPanel();
  }

  async function submit(completed) {
    if (model.submitting) return;
    const current = model;
    current.submitting = true;
    current.helpers.setReadout("", "pending");
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({
        mechanic_id: current.state.mechanic_id,
        task_id: current.state.task_id,
        challenge_id: current.state.challenge_id,
        interaction_mode: interaction(),
        events: current.events,
        final_state: finalState(),
        completed,
      })});
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.submitting = false;
        current.status = "passed";
        current.verified = true;
        renderRoot();
        current.helpers.setReadout("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await render(outcome.state, current.helpers, {freshFailure: true});
      } else {
        current.submitting = false;
        current.status = "failed";
        renderRoot();
        current.helpers.setReadout("FAIL", "error");
      }
    } catch (_error) {
      if (model === current) {
        current.submitting = false;
        current.helpers.setReadout("FAIL", "error");
        renderRoot();
      }
    }
  }

  function attemptMove(destination, source, event = null) {
    if (model.submitting || model.status !== "active") return;
    if (!model.state.neighbors[model.position].includes(destination)) return;
    const action = model.helpers.beginAction?.("crackglaze-step");
    model.freshFailure = false;
    const origin = model.position;
    const nextStep = model.step + 1;
    if (!(origin in model.litAt)) model.litAt[origin] = nextStep;
    model.step = nextStep;
    updateShattered();
    const expired = model.shattered.has(destination);
    model.events.push({
      sequence: model.events.length + 1,
      type: "move",
      from: origin,
      to: destination,
      direction: direction(origin, destination),
      step_index: nextStep,
      input_source: source,
      accepted: !expired,
      failure: expired ? "expired_destination" : null,
      ...(source === "tile_click" ? {point: pointInBoard(event)} : {}),
    });
    model.position = destination;
    if (expired) {
      model.status = "failed";
      renderRoot();
      action?.settle();
      submit(false);
      return;
    }
    if (model.state.lantern_ids.includes(destination)) model.collected.add(destination);
    const complete = destination === model.state.exit_id && model.collected.size === model.state.lantern_ids.length;
    model.status = complete ? "passed" : "active";
    action?.settle();
    if (complete) {
      submit(true);
      return;
    }
    renderRoot();
  }

  function destinationFor(requestedDirection) {
    const current = cell(model.position);
    return model.state.neighbors[model.position].find((id) => direction(current.id, id) === requestedDirection) || null;
  }

  function bind() {
    if (interaction() === "full") {
      document.querySelectorAll("button.crack-tile").forEach((tile) => tile.addEventListener("click", (event) => {
        event.preventDefault();
        attemptMove(tile.dataset.cellId, "tile_click", event);
      }));
    } else {
      document.querySelectorAll(".crack-dpad button[data-direction]").forEach((button) => button.addEventListener("click", () => {
        const destination = destinationFor(button.dataset.direction);
        if (destination) attemptMove(destination, "direction_button");
      }));
    }
  }

  async function render(state, helpers, options = {}) {
    cleanup?.();
    document.body.dataset.mechanic = "crackglaze-crossing";
    model = {
      state,
      helpers,
      position: state.start_id,
      step: 0,
      collected: new Set(state.lantern_ids.includes(state.start_id) ? [state.start_id] : []),
      litAt: {},
      shattered: new Set(),
      events: [],
      status: "active",
      verified: false,
      submitting: false,
      freshFailure: Boolean(options.freshFailure),
    };
    helpers.app.innerHTML = `<section class="crackglaze-crossing mode-${esc(interaction())}" data-challenge-id="${esc(state.challenge_id)}" data-interaction="${esc(interaction())}"></section>`;
    renderRoot();
    cleanup = () => {};
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {rootSelector: ".crackglaze-crossing", render};
})();
