(() => {
  "use strict";

  const ID = "patchwork_skirmish";
  const DIRS = {north: [-1, 0], south: [1, 0], west: [0, -1], east: [0, 1]};
  const TIE_ORDER = ["north", "west", "south", "east"];
  let model = null;

  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
  const live = (owner) => Object.values(model.units).filter((unit) => unit.cells.length && (owner == null || Number(unit.owner) === owner));
  const cellsKey = (cells) => new Set(cells.map(([row, col]) => `${row},${col}`));
  const distance = (a, b) => Math.min(...a.flatMap(([ar, ac]) => b.map(([br, bc]) => Math.abs(ar - br) + Math.abs(ac - bc))));
  const adjacent = (a, b) => distance(a, b) === 1;

  function occupied(skip) {
    const result = new Set();
    Object.values(model.units).forEach((unit) => {
      if (unit.id === skip) return;
      unit.cells.forEach(([row, col]) => result.add(`${row},${col}`));
    });
    return result;
  }

  function translated(cells, direction) {
    const [dr, dc] = DIRS[direction] || [0, 0];
    return cells.map(([row, col]) => [row + dr, col + dc]);
  }

  function validTranslation(unitId, direction) {
    if (!DIRS[direction]) return null;
    const cells = translated(model.units[unitId].cells, direction);
    const blocked = occupied(unitId);
    if (cells.some(([row, col]) => row < 0 || row >= model.world.height || col < 0 || col >= model.world.width || blocked.has(`${row},${col}`))) return null;
    return cells;
  }

  function nearest(unit) {
    const owner = Number(unit.owner) === 0 ? 1 : 0;
    const choices = live(owner);
    return choices.sort((a, b) => distance(unit.cells, a.cells) - distance(unit.cells, b.cells) || String(a.id).localeCompare(String(b.id)))[0] || null;
  }

  function removeEdge(unit, power) {
    const count = Math.min(Math.max(0, Number(power)), unit.cells.length);
    if (count) unit.cells.splice(unit.cells.length - count, count);
    return count;
  }

  function enemyResponse() {
    const notes = [];
    live(1).sort((a, b) => String(a.id).localeCompare(String(b.id))).forEach((enemy) => {
      if (!enemy.cells.length) return;
      let target = nearest(enemy);
      if (!target) return;
      if (adjacent(enemy.cells, target.cells)) {
        const removed = removeEdge(target, 1);
        model.enemyActions += 1;
        notes.push(`${enemy.id} chips ${target.id} (${removed} cell)`);
        return;
      }
      for (let step = 0; step < Number(model.world.enemy_movement_points); step += 1) {
        target = nearest(enemy);
        if (!target || !enemy.cells.length) break;
        const choices = Object.keys(DIRS).map((direction) => {
          const next = validTranslation(enemy.id, direction);
          return next ? [distance(next, target.cells), direction, next] : null;
        }).filter(Boolean);
        if (!choices.length) break;
        choices.sort((a, b) => a[0] - b[0] || TIE_ORDER.indexOf(a[1]) - TIE_ORDER.indexOf(b[1]));
        enemy.cells = choices[0][2];
        model.enemyActions += 1;
        notes.push(`${enemy.id} drifts ${choices[0][1]}`);
      }
    });
    model.lastResponse = notes.length ? notes.join("; ") : "RIVALS HAVE NO LEGAL RESPONSE";
  }

  function applyEvent(event) {
    if (model.terminal) throw new Error("the skirmish is already over");
    const type = String(event.type || "");
    if (type === "move") {
      const unit = model.units[String(event.unit_id || "")];
      if (!unit || Number(unit.owner) !== 0 || !unit.cells.length) throw new Error("move must select a living player patch");
      if (Number(unit.moves_left) <= 0) throw new Error("that patch has spent its movement");
      const cells = validTranslation(unit.id, String(event.direction || ""));
      if (!cells) throw new Error("move collides with the board or another patch");
      unit.cells = cells;
      unit.moves_left -= 1;
    } else if (type === "attack") {
      const unit = model.units[String(event.unit_id || "")];
      const target = model.units[String(event.target_id || "")];
      if (!unit || !target || Number(unit.owner) !== 0 || Number(target.owner) !== 1) throw new Error("attack must select a player and rival patch");
      if (!unit.cells.length || !target.cells.length || Number(unit.attacks_left) <= 0) throw new Error("that patch cannot attack now");
      if (!adjacent(unit.cells, target.cells)) throw new Error("the rival patch is not neighboring");
      removeEdge(target, model.world.attack_power);
      unit.attacks_left -= 1;
    } else if (type === "end_turn") {
      if (!live(1).length) {
        model.terminal = true;
        model.won = Boolean(live(0).length);
        return;
      }
      enemyResponse();
      model.turn += 1;
      live().filter((unit) => Number(unit.owner) === 0).forEach((unit) => {
        unit.moves_left = Number(model.world.movement_points);
        unit.attacks_left = 1;
      });
      if (!live(0).length || model.turn >= Number(model.world.max_turns)) {
        model.terminal = true;
        model.won = false;
      }
    } else {
      throw new Error("unknown patchwork action");
    }
    model.actionCount += 1;
  }

  function snapshot() {
    const units = {};
    Object.keys(model.units).sort().forEach((unitId) => {
      const unit = model.units[unitId];
      units[unitId] = {cells: unit.cells.map((cell) => [...cell]), moves_left: Number(unit.moves_left), attacks_left: Number(unit.attacks_left)};
    });
    return {turn: Number(model.turn), units, terminal: Boolean(model.terminal), won: Boolean(model.won), action_count: Number(model.actionCount), enemy_actions: Number(model.enemyActions), last_response: String(model.lastResponse)};
  }

  function event(type, details) {
    const item = {sequence: model.events.length + 1, type, input_source: type === "end_turn" ? "turn_button" : model.interaction === "full" ? "board_direct" : "command_panel", ...details};
    try {
      applyEvent(item);
    } catch (error) {
      model.helpers.setReadout(`INVALID · ${error.message.toUpperCase()}`, "error");
      return;
    }
    model.events.push(item);
    model.selected = model.units[item.unit_id]?.cells.length ? item.unit_id : model.selected;
    update();
  }

  function choose(unitId) {
    const unit = model.units[unitId];
    if (!unit || Number(unit.owner) !== 0 || !unit.cells.length) return;
    model.selected = unitId;
    model.helpers.setReadout(`${unit.label} SELECTED · READ THE HIGHLIGHTED SEAMS`, "idle");
    update();
  }

  function cellAction(row, col) {
    const unitId = Object.keys(model.units).find((id) => cellsKey(model.units[id].cells).has(`${row},${col}`));
    if (unitId && Number(model.units[unitId].owner) === 0) {
      if (model.interaction === "full" && model.selected === unitId) {
        for (const direction of Object.keys(DIRS)) {
          const next = validTranslation(model.selected, direction);
          if (next && cellsKey(next).has(`${row},${col}`)) {
            event("move", {unit_id: model.selected, direction});
            return;
          }
        }
      }
      choose(unitId);
      return;
    }
    if (!model.selected || model.interaction !== "full") return;
    const selected = model.units[model.selected];
    if (!selected || !selected.cells.length) return;
    for (const direction of Object.keys(DIRS)) {
      const next = validTranslation(model.selected, direction);
      if (next && cellsKey(next).has(`${row},${col}`)) {
        event("move", {unit_id: model.selected, direction});
        return;
      }
    }
    if (unitId && Number(model.units[unitId].owner) === 1 && adjacent(selected.cells, model.units[unitId].cells)) {
      event("attack", {unit_id: model.selected, target_id: unitId});
    } else {
      model.helpers.setReadout("CHOOSE A GOLD MOVE SQUARE OR NEIGHBORING RIVAL", "error");
    }
  }

  function boardMarkup() {
    const byCell = {};
    Object.values(model.units).forEach((unit) => unit.cells.forEach(([row, col]) => { byCell[`${row},${col}`] = unit; }));
    const cells = [];
    for (let row = 0; row < model.world.height; row += 1) {
      for (let col = 0; col < model.world.width; col += 1) {
        const unit = byCell[`${row},${col}`];
        const selected = unit && unit.id === model.selected;
        let legal = false;
        if (model.selected && model.interaction === "full") {
          const selectedUnit = model.units[model.selected];
          legal = Object.keys(DIRS).some((direction) => validTranslation(model.selected, direction)?.some(([r, c]) => r === row && c === col));
          if (unit && Number(unit.owner) === 1 && selectedUnit && adjacent(selectedUnit.cells, unit.cells)) legal = true;
        }
        const seam = model.world.seams[row] || {offset: 0, tone: "gold"};
        const classes = ["patchwork-cell", unit ? `is-${Number(unit.owner) === 0 ? "player" : "rival"}` : "is-empty", selected ? "is-selected" : "", legal ? "is-legal" : ""].filter(Boolean).join(" ");
        cells.push(`<button type="button" class="${classes}" data-cell="${row},${col}" data-unit-id="${unit ? esc(unit.id) : ""}" aria-label="${unit ? esc(unit.label) : "empty quilt square"} at row ${row + 1}, column ${col + 1}" style="--seam:${(Number(seam.offset) + col) % 4};--tone:${esc(seam.tone)}"><span>${unit ? esc(unit.id) : ""}</span></button>`);
      }
    }
    return cells.join("");
  }

  function panelMarkup() {
    const selected = model.selected ? model.units[model.selected] : null;
    const playerRoster = Object.values(model.units).filter((unit) => Number(unit.owner) === 0).map((unit) => `<button type="button" class="patchwork-roster-unit ${unit.id === model.selected ? "is-selected" : ""} ${unit.cells.length ? "" : "is-gone"}" data-select-unit="${esc(unit.id)}"><span class="roster-swatch palette-${esc(unit.palette)}"></span><b>${esc(unit.label)}</b><small>${unit.cells.length ? `${unit.cells.length} CELLS · ${unit.moves_left} MOVES` : "REMOVED"}</small></button>`).join("");
    const rivals = Object.values(model.units).filter((unit) => Number(unit.owner) === 1 && unit.cells.length).map((unit) => `<button type="button" class="patchwork-attack-target" data-action="attack" data-target="${esc(unit.id)}" ${!selected || !adjacent(selected.cells, unit.cells) || Number(selected.attacks_left) <= 0 ? "disabled" : ""}>STRIKE ${esc(unit.id)} · ${unit.cells.length} CELLS</button>`).join("") || `<span class="patchwork-muted">NO RIVALS IN RANGE</span>`;
    const moveButtons = Object.keys(DIRS).map((direction) => `<button type="button" class="patchwork-move" data-action="move" data-direction="${direction}" ${!selected || !validTranslation(model.selected, direction) || Number(selected.moves_left) <= 0 ? "disabled" : ""}>${direction.toUpperCase()}</button>`).join("");
    return `<div class="patchwork-rail-head"><span>FRIENDLY PATCHES</span><b>${live(0).length} ALIVE</b></div><div class="patchwork-roster">${playerRoster}</div><div class="patchwork-inspector"><span>SELECTED READOUT</span><strong>${selected ? esc(selected.id) : "—"}</strong><small>${selected ? `${selected.cells.length} OCCUPIED CELLS = HEALTH · ${selected.moves_left} MOVES · ${selected.attacks_left} STRIKE` : "SELECT ON THE QUILT"}</small></div>${model.interaction === "simplified" ? `<div class="patchwork-command"><span>COMMAND PANEL</span><div class="patchwork-moves">${moveButtons}</div><div class="patchwork-rivals">${rivals}</div></div>` : `<div class="patchwork-direct-note"><span>BOARD DIRECT</span><p>Select a friendly patch, then click a gold square to translate its whole footprint. Click a neighboring rival to remove one edge cell.</p></div>`}<div class="patchwork-rail-divider"></div><div class="patchwork-threat"><span>RIVAL PATCHES</span><b>${live(1).length} REMAIN</b><small>${model.lastResponse}</small></div>`;
  }

  function update() {
    const root = document.querySelector(".patchwork-skirmish");
    if (!root) return;
    const board = root.querySelector(".patchwork-board");
    if (board) board.innerHTML = boardMarkup();
    const rail = root.querySelector(".patchwork-rail");
    if (rail) rail.innerHTML = panelMarkup();
    root.querySelector("#patchwork-turn").textContent = `TURN ${model.turn + 1} / ${model.world.max_turns}`;
    root.querySelector("#patchwork-event-count").textContent = `${model.events.length} COMMITTED ACTIONS`;
    root.querySelector("#patchwork-status-line").textContent = model.terminal ? (model.won ? "ALL RIVALS REMOVED · CERTIFY THE SURVIVING QUILT" : "YOUR PATCHWORK IS LOST · CERTIFY TO REQUEST A FRESH PATCH") : model.interaction === "full" ? "SELECT A FRIENDLY FOOTPRINT" : "SELECT A PATCH FROM THE ROSTER";
    root.querySelector("#patchwork-end-turn").disabled = model.terminal;
    root.querySelectorAll(".patchwork-cell").forEach((button) => button.addEventListener("click", () => {
      const [row, col] = button.dataset.cell.split(",").map(Number);
      cellAction(row, col);
    }));
    root.querySelectorAll("[data-select-unit]").forEach((button) => button.addEventListener("click", () => choose(button.dataset.selectUnit)));
    root.querySelectorAll("[data-action='move'],[data-action='attack']").forEach((button) => button.addEventListener("click", () => {
      if (button.dataset.target) event("attack", {unit_id: model.selected, target_id: button.dataset.target});
      else event("move", {unit_id: model.selected, direction: button.dataset.direction});
    }));
    root.querySelector("#patchwork-end-turn").onclick = () => event("end_turn", {});
    root.querySelector("#patchwork-submit").onclick = submit;
  }

  async function submit() {
    if (!model || model.submitting) return;
    model.submitting = true;
    const current = model;
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({
        mechanic_id: current.state.mechanic_id, task_id: current.state.task_id, challenge_id: current.state.challenge_id, events: current.events, final_state: snapshot(),
      })});
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.completed = true;
        current.helpers.setReadout("PASS", "passed");
        document.querySelector(".patchwork-skirmish")?.setAttribute("data-verdict", "pass");
        return;
      }
      if (outcome.passed === false && outcome.state) {
        await render(outcome.state, current.helpers, {freshFailure: true});
        current.helpers.setReadout("FAIL · FRESH PATCH ISSUED", "error");
      } else {
        current.submitting = false;
        current.helpers.setReadout("RUN REJECTED", "error");
      }
    } catch (_error) {
      if (model === current) {
        current.submitting = false;
        current.helpers.setReadout("VERIFIER LINK LOST · RETRY CERTIFY", "error");
      }
    }
  }

  async function render(state, helpers, options = {}) {
    document.body.dataset.mechanic = ID;
    model = {
      state, helpers, world: state.world, interaction: state.control_condition?.interaction || "full", units: {}, selected: null,
      events: [], turn: 0, terminal: false, won: false, actionCount: 0, enemyActions: 0, lastResponse: "RIVALS WAIT IN THEIR STITCHES", submitting: false, completed: false,
    };
    (state.world.units || []).forEach((raw) => { model.units[raw.id] = {...raw, cells: raw.cells.map((cell) => [...cell]), moves_left: Number(state.world.movement_points), attacks_left: 1}; });
    const root = helpers.app;
    root.innerHTML = `<section class="patchwork-skirmish" data-interaction="${esc(model.interaction)}" data-challenge-id="${esc(state.challenge_id)}" data-fresh-failure="${options.freshFailure ? "true" : "false"}" data-verdict=""><header class="patchwork-header"><div><span class="patchwork-kicker">QUARANTINE QUILT / TACTICAL RECOVERY GRID</span><h1>PATCHWORK SKIRMISH</h1><p>${esc(state.prompt)}</p></div><div class="patchwork-turn"><span id="patchwork-turn">TURN 1 / ${state.world.max_turns}</span><strong>OCCUPIED AREA = HEALTH</strong></div></header><main class="patchwork-main"><section class="patchwork-stage"><div class="patchwork-board" style="--board-cols:${state.world.width};--board-rows:${state.world.height}">${boardMarkup()}</div><div class="patchwork-legend"><span><i class="legend-player"></i>YOUR PATCHES</span><span><i class="legend-rival"></i>RIVAL PATCHES</span><span><i class="legend-legal"></i>LEGAL BOARD INPUT</span></div></section><aside class="patchwork-rail">${panelMarkup()}</aside></main><footer class="patchwork-footer"><div><span id="patchwork-status-line">${model.interaction === "full" ? "SELECT A FRIENDLY FOOTPRINT" : "SELECT A PATCH FROM THE ROSTER"}</span><small id="patchwork-event-count">0 COMMITTED ACTIONS</small><div class="readout" data-status="idle">BOARD LIVE</div></div><div class="patchwork-footer-actions"><button type="button" id="patchwork-end-turn">END TURN ↗</button><button type="button" id="patchwork-submit">${esc(state.submit_label || "CERTIFY SKIRMISH")}</button></div></footer>${helpers.cheatPanelTemplate ? helpers.cheatPanelTemplate() : ""}</section>`;
    window.patchworkSkirmishModel = {snapshot, state: () => model.state, events: () => model.events};
    update();
    if (helpers.installCheatPanel) helpers.installCheatPanel();
    if (options.freshFailure) setTimeout(() => document.querySelector(".patchwork-skirmish")?.setAttribute("data-fresh-failure", "false"), 1100);
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[ID] = {rootSelector: ".patchwork-skirmish", render};
})();
