(() => {
  "use strict";

  const model = {
    state: null,
    tileMap: {},
    sets: [],
    rack: [],
    actions: [],
    selectedTile: null,
    pointerDrag: null,
    busy: false,
    terminal: false,
    newSetCounter: 0,
    helpers: null,
  };

  const clean = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const tile = (id) => model.tileMap[id];

  function currentLocation(tileId) {
    if (model.rack.includes(tileId)) return {zone: "rack"};
    const group = model.sets.find((entry) => entry.tiles.includes(tileId));
    return group ? {zone: "table", set_id: group.id} : null;
  }

  function validKind(tileIds) {
    if (tileIds.length < 3) return "needs 3+ tiles";
    const values = tileIds.map(tile);
    const numbers = values.map((entry) => Number(entry.number));
    const colors = values.map((entry) => String(entry.color));
    if (new Set(numbers).size === 1 && tileIds.length <= 4 && new Set(colors).size === colors.length) return "VALID GROUP";
    const ordered = [...numbers].sort((a, b) => a - b);
    if (new Set(colors).size === 1 && new Set(numbers).size === numbers.length && ordered.every((value, index) => value === ordered[0] + index)) return "VALID RUN";
    return "NEEDS REPAIR";
  }

  function isValid(tileIds) {
    return validKind(tileIds).startsWith("VALID");
  }

  function tileMarkup(tileId) {
    const entry = tile(tileId);
    if (!entry) return "";
    const label = `${entry.color} ${entry.number}`;
    return `<button type="button" class="borrowed-tile glaze-${Number(entry.pattern || 0)}" data-tile-id="${clean(tileId)}" aria-label="${clean(label)}">
      <span class="tile-corner">${Number(entry.number)}</span><strong>${Number(entry.number)}</strong><small>${clean(entry.color)}</small>
    </button>`;
  }

  function setMarkup(entry) {
    const kind = validKind(entry.tiles);
    const statusClass = kind.startsWith("VALID") ? "is-valid" : "is-open";
    return `<article class="borrow-set ${statusClass}" data-set-id="${clean(entry.id)}">
      <header><span>${clean(entry.label)}</span><b>${kind}</b></header>
      <div class="borrow-set-tiles">${entry.tiles.map(tileMarkup).join("")}</div>
      <div class="borrow-dropzone borrow-set-dropzone" data-drop-zone="table" data-set-id="${clean(entry.id)}">DROP TILE HERE</div>
    </article>`;
  }

  function rackMarkup() {
    const state = model.rack.length ? `${model.rack.length} TILE${model.rack.length === 1 ? "" : "S"} REMAIN` : "RACK EMPTY";
    return `<section class="borrow-rack-zone">
      <div class="borrow-rack-head"><span>YOUR RACK</span><b>${state}</b></div>
      <div class="borrow-rack-tiles">${model.rack.map(tileMarkup).join("")}</div>
      <div class="borrow-dropzone borrow-rack-dropzone" data-drop-zone="rack">RETURN TILE TO RACK</div>
    </section>`;
  }

  function newSetMarkup() {
    return `<div class="borrow-new-set"><div class="borrow-dropzone" data-drop-zone="new">＋ DROP TO START A NEW SET</div><small>Split a run or group here, then repair it.</small></div>`;
  }

  function renderLayout() {
    const table = document.getElementById("borrow-table");
    const rack = document.getElementById("borrow-rack-wrap");
    const newZone = document.getElementById("borrow-new-zone");
    if (table) table.innerHTML = model.sets.map(setMarkup).join("");
    if (rack) rack.innerHTML = rackMarkup();
    if (newZone) newZone.innerHTML = newSetMarkup();
    bindControls();
    updateReadout();
  }

  function updateReadout() {
    const count = model.sets.filter((entry) => isValid(entry.tiles)).length;
    const needed = model.sets.length;
    const valid = count === needed && model.rack.length === 0 && model.actions.length > 0;
    const commit = document.getElementById("borrow-commit");
    const meter = document.getElementById("borrow-valid-meter");
    const moves = document.getElementById("borrow-move-count");
    if (meter) meter.textContent = `${count} / ${needed} SETS VALID`;
    if (moves) moves.textContent = String(model.actions.length).padStart(2, "0");
    if (commit) commit.classList.toggle("is-ready", valid);
  }

  function clearVerdict() {
    document.querySelectorAll(".borrow-verdict").forEach((node) => node.remove());
    document.querySelector(".borrowed-tiles-captcha")?.classList.remove("is-fresh-fail");
  }

  function removeTile(tileId) {
    const rackIndex = model.rack.indexOf(tileId);
    if (rackIndex >= 0) {
      model.rack.splice(rackIndex, 1);
      return;
    }
    const source = model.sets.find((entry) => entry.tiles.includes(tileId));
    if (!source) throw new Error("tile is not in the visible layout");
    source.tiles.splice(source.tiles.indexOf(tileId), 1);
  }

  function ensureNewSet() {
    let id;
    do {
      model.newSetCounter += 1;
      id = `new_set_${model.newSetCounter}`;
    } while (model.sets.some((entry) => entry.id === id));
    model.sets.push({id, label: `FRESH SET ${model.newSetCounter}`, tiles: []});
    return id;
  }

  function moveTile(tileId, destination, inputSource) {
    if (model.busy || model.terminal) return;
    const from = currentLocation(tileId);
    if (!from) return;
    const target = destination.zone === "new" ? {zone: "table", set_id: ensureNewSet()} : destination;
    if (target.zone === from.zone && target.set_id === from.set_id) {
      model.helpers.setReadout("CHOOSE A DIFFERENT DROP ZONE", "error");
      return;
    }
    clearVerdict();
    removeTile(tileId);
    if (target.zone === "rack") {
      model.rack.push(tileId);
    } else {
      const set = model.sets.find((entry) => entry.id === target.set_id);
      if (!set) return;
      set.tiles.push(tileId);
    }
    model.actions.push({
      sequence: model.actions.length + 1,
      tile_id: tileId,
      from: clone(from),
      to: clone(target),
      input_source: inputSource,
    });
    model.selectedTile = null;
    model.helpers.setReadout(`MOVED ${tile(tileId).color.toUpperCase()} ${tile(tileId).number} · CHECK EVERY SET`, "idle");
    renderLayout();
  }

  function selectTile(tileId) {
    if (model.busy || model.terminal) return;
    clearVerdict();
    if (model.selectedTile === tileId) {
      model.selectedTile = null;
      renderLayout();
      return;
    }
    model.selectedTile = tileId;
    model.helpers.setReadout("TILE HELD · CHOOSE A DROP ZONE", "idle");
    document.querySelectorAll(".borrowed-tile").forEach((node) => node.classList.toggle("is-selected", node.dataset.tileId === tileId));
  }

  function dragMove(event) {
    const drag = model.pointerDrag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    drag.node.style.setProperty("--drag-x", `${event.clientX - drag.startX}px`);
    drag.node.style.setProperty("--drag-y", `${event.clientY - drag.startY}px`);
  }

  function dragEnd(event, cancelled = false) {
    const drag = model.pointerDrag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    const dropNode = cancelled ? null : document.elementsFromPoint(event.clientX, event.clientY).find((node) => node.dataset?.dropZone);
    model.pointerDrag = null;
    drag.node.classList.remove("is-dragging");
    drag.node.style.removeProperty("--drag-x");
    drag.node.style.removeProperty("--drag-y");
    try { drag.node.releasePointerCapture(event.pointerId); } catch (_error) { /* already released */ }
    if (!dropNode) {
      model.helpers.setReadout("DROP CANCELED · TILE RETURNED", "error");
      return;
    }
    moveTile(drag.tileId, {zone: dropNode.dataset.dropZone, set_id: dropNode.dataset.setId}, "tile_drag");
  }

  function bindControls() {
    const interaction = model.state.control_condition?.interaction || "full";
    document.querySelectorAll(".borrowed-tile").forEach((node) => {
      node.addEventListener("click", (event) => {
        if (interaction === "simplified") {
          event.stopPropagation();
          selectTile(node.dataset.tileId);
        }
      });
      node.addEventListener("pointerdown", (event) => {
        if (interaction !== "full" || event.button !== 0 || model.busy || model.terminal || model.pointerDrag) return;
        event.preventDefault();
        model.pointerDrag = {pointerId: event.pointerId, tileId: node.dataset.tileId, node, startX: event.clientX, startY: event.clientY};
        node.classList.add("is-dragging");
        try { node.setPointerCapture(event.pointerId); } catch (_error) { /* no capture */ }
      });
      node.addEventListener("pointermove", dragMove);
      node.addEventListener("pointerup", (event) => dragEnd(event));
      node.addEventListener("pointercancel", (event) => dragEnd(event, true));
    });
    document.querySelectorAll("[data-drop-zone]").forEach((node) => {
      node.addEventListener("click", () => {
        if (interaction !== "simplified" || !model.selectedTile) return;
        moveTile(model.selectedTile, {zone: node.dataset.dropZone, set_id: node.dataset.setId}, "tile_click_drop");
      });
    });
  }

  async function commit() {
    if (model.busy || model.terminal) return;
    model.busy = true;
    document.querySelectorAll("button").forEach((node) => { node.disabled = true; });
    model.helpers.setReadout("AUDITING THE TABLE…", "pending");
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      actions: clone(model.actions),
      table_sets: model.sets.map((entry) => ({id: entry.id, tiles: entry.tiles.slice()})),
      rack_tiles: model.rack.slice(),
      completed: true,
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true;
        document.querySelector(".borrowed-tiles-captcha")?.classList.add("is-pass");
        document.querySelector(".borrowed-tiles-captcha")?.insertAdjacentHTML("beforeend", '<div class="borrow-verdict borrow-verdict-pass"><small>TABLE BALANCED</small><strong>PASS</strong></div>');
        model.helpers.setReadout("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        document.querySelector(".borrowed-tiles-captcha")?.classList.add("is-fresh-fail");
        document.querySelector(".borrowed-tiles-captcha")?.insertAdjacentHTML("beforeend", '<div class="borrow-verdict borrow-verdict-fail"><small>TABLE REJECTED · FRESH DEAL</small><strong>FAIL</strong></div>');
        model.helpers.setReadout("FAIL · FRESH DEAL", "error");
      } else {
        model.busy = false;
        document.querySelectorAll("button").forEach((node) => { node.disabled = false; });
        model.helpers.setReadout("FAIL · TABLE NOT ACCEPTED", "error");
      }
    } catch (_error) {
      model.busy = false;
      document.querySelectorAll("button").forEach((node) => { node.disabled = false; });
      model.helpers.setReadout("FAIL · REGISTER OFFLINE", "error");
    }
  }

  function reset() {
    if (model.busy || model.terminal) return;
    model.sets = clone(model.state.table_sets);
    model.rack = model.state.rack_tiles.slice();
    model.actions = [];
    model.selectedTile = null;
    model.newSetCounter = 0;
    clearVerdict();
    renderLayout();
    model.helpers.setReadout("WORKTABLE RESET · NO MOVES RECORDED", "idle");
  }

  function render(state, helpers) {
    document.body.dataset.mechanic = "borrowed-tiles";
    document.body.dataset.borrowPalette = String(state.palette || "terracotta");
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    Object.assign(model, {
      state,
      tileMap: Object.fromEntries((state.tiles || []).map((entry) => [entry.id, entry])),
      sets: clone(state.table_sets || []),
      rack: (state.rack_tiles || []).slice(),
      actions: [],
      selectedTile: null,
      pointerDrag: null,
      busy: false,
      terminal: false,
      newSetCounter: 0,
      helpers,
    });
    const interaction = state.control_condition?.interaction || "full";
    helpers.app.innerHTML = `<section class="borrowed-tiles-captcha" data-interaction="${clean(interaction)}" data-challenge-id="${clean(state.challenge_id)}">
      <header class="borrow-header"><div class="borrow-title"><span>ARCHIVE OF LOOSE CERAMICS · TABLE ${String(state.generator?.module_count || 0).padStart(2, "0")}</span><h1>${clean(state.prompt)}</h1></div><div class="borrow-ticket"><small>CONSERVE EVERY IDENTITY</small><strong>${(state.tiles || []).length}</strong><i>TILES</i></div></header>
      <div class="borrow-rulebar"><span>RUN · 3+ CONSECUTIVE / ONE COLOUR</span><span>GROUP · 3–4 EQUAL / DIFFERENT COLOURS</span><b>${interaction === "full" ? "DIRECT DRAG" : "SELECT THEN DROP"}</b></div>
      <main class="borrow-workbench"><section class="borrow-table-case"><div class="borrow-section-head"><div><span>THE TABLE</span><small>Temporary breaks are allowed. Commit only when every set is green.</small></div><b id="borrow-valid-meter">0 / 0 SETS VALID</b></div><div class="borrow-table" id="borrow-table"></div><div id="borrow-new-zone"></div></section><aside class="borrow-side"><div class="borrow-ledger"><span>MOVE LEDGER</span><strong id="borrow-move-count">00</strong><small>VISIBLE TRANSFERS</small><div class="ledger-line"></div><p>Every tile is tracked by identity. A borrowed table piece must finish in a different set.</p></div><div class="borrow-legend"><span>READ THE GLAZE</span><i class="legend-coral"></i><i class="legend-azure"></i><i class="legend-amber"></i><i class="legend-jade"></i><small>Colour names are printed on each tile.</small></div></aside></main><div id="borrow-rack-wrap"></div><footer class="borrow-footer"><button type="button" id="borrow-reset">↺ RESET WORKTABLE</button><div class="readout" data-status="idle">${interaction === "full" ? "DRAG A TILE TO A SET" : "SELECT A TILE, THEN A DROP ZONE"}</div><button type="button" id="borrow-commit">COMMIT TABLE</button></footer>${helpers.cheatPanelTemplate()}</section>`;
    renderLayout();
    document.getElementById("borrow-reset")?.addEventListener("click", reset);
    document.getElementById("borrow-commit")?.addEventListener("click", commit);
    helpers.installCheatPanel();
    window.borrowedTilesModel = model;
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.borrowed_tiles = {rootSelector: ".borrowed-tiles-captcha", render};
})();
