(() => {
  "use strict";

  const MECHANIC_ID = "collision_chimes";
  const SIDES = ["top", "right", "bottom", "left"];
  const DIRECTIONS = ["up", "right", "down", "left"];
  const DELTAS = [[-1, 0], [0, 1], [1, 0], [0, -1]];
  let model = null;

  const esc = value => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
  const clone = value => JSON.parse(JSON.stringify(value));
  const canonical = cells => cells.slice().sort((left, right) => String(left.id).localeCompare(String(right.id)))
    .map(cell => ({id: String(cell.id), row: Number(cell.row), col: Number(cell.col), direction: Number(cell.direction) % 4}));
  const canonicalEvents = events => events.slice().sort((a, b) =>
    a.beat - b.beat || SIDES.indexOf(a.side) - SIDES.indexOf(b.side) || a.slot - b.slot);
  const sameEvents = (left, right) => JSON.stringify(canonicalEvents(left)) === JSON.stringify(canonicalEvents(right));
  const interaction = () => String(model?.state?.control_condition?.interaction || "simplified");
  const sourcePair = () => interaction() === "full" ? ["cell_drag", "cell_click"] : ["add_button", "cycle_button"];

  function clearFreshFailure() {
    const root = document.querySelector(".collision-chimes");
    if (!root) return;
    root.dataset.freshFailure = "false";
    root.classList.remove("is-failed");
  }

  function resetFilm() {
    if (model.timer != null) {
      window.clearTimeout(model.timer);
      model.timer = null;
    }
    model.phase = "edit";
    model.beat = 0;
    model.simCells = canonical(model.cells);
    model.wallEvents = [];
    document.querySelectorAll(".wall-rail").forEach(rail => {
      delete rail.dataset.flashBeat;
      rail.classList.remove("is-flashing");
      rail.querySelectorAll(".wall-slot").forEach(slot => slot.classList.remove("is-hit"));
    });
    renderGrid();
    renderLedger();
    const beatNode = document.querySelector("#beat-count");
    if (beatNode) beatNode.textContent = "00";
    const eventCount = document.querySelector("#event-count");
    if (eventCount) eventCount.textContent = "00";
    updateControls();
  }

  function selectCell(cellId) {
    model.selectedCellId = cellId == null ? null : String(cellId);
    if (cellId != null) model.selectedSquare = null;
    document.querySelectorAll(".placed-cell").forEach(node => {
      node.classList.toggle("is-selected", node.dataset.cellId === model.selectedCellId);
    });
    updateControls();
  }

  function cellAt(row, col, cells = model.cells) {
    return cells.find(cell => Number(cell.row) === Number(row) && Number(cell.col) === Number(col));
  }

  function recordAdd(row, col, inputSource) {
    if (model.phase !== "edit" || model.cells.length >= Number(model.contract.max_cells) || cellAt(row, col)) return null;
    clearFreshFailure();
    const id = `c${model.nextId++}`;
    const cell = {id, row: Number(row), col: Number(col), direction: 0};
    model.cells.push(cell);
    model.editEvents.push({sequence: model.editEvents.length + 1, type: "add", id, row: Number(row), col: Number(col), direction: 0, input_source: inputSource});
    model.selectedCellId = id;
    renderGrid();
    renderLedger();
    updateControls();
    model.helpers.setReadout(`ARROW ${id.toUpperCase()} PLACED · ROTATE IT OR ADD ANOTHER`, "idle");
    return cell;
  }

  function cycleSelected(inputSource) {
    if (model.phase !== "edit" || !model.selectedCellId) return;
    const cell = model.cells.find(item => item.id === model.selectedCellId);
    if (!cell) return;
    clearFreshFailure();
    const before = Number(cell.direction);
    const after = (before + 1) % 4;
    cell.direction = after;
    model.editEvents.push({sequence: model.editEvents.length + 1, type: "cycle", id: cell.id, row: Number(cell.row), col: Number(cell.col), before_direction: before, after_direction: after, input_source: inputSource});
    renderGrid();
    renderLedger();
    updateControls();
    model.helpers.setReadout(`${cell.id.toUpperCase()} NOW POINTS ${DIRECTIONS[after].toUpperCase()}`, "idle");
  }

  function cellMarkup(cell, moving = false) {
    const classes = ["placed-cell"];
    if (cell.id === model.selectedCellId) classes.push("is-selected");
    if (moving) classes.push("is-moving");
    return `<button type="button" class="${classes.join(" ")}" data-cell-id="${esc(cell.id)}" aria-label="${esc(cell.id)} arrow pointing ${esc(DIRECTIONS[cell.direction])}" style="--cell-row:${Number(cell.row)};--cell-col:${Number(cell.col)};--arrow-angle:${Number(cell.direction) * 90}deg"><span class="cell-core"><i></i><b>${esc(cell.id.replace(/^c/, ""))}</b></span></button>`;
  }

  function renderGrid() {
    const grid = document.querySelector("#chime-grid");
    if (!grid) return;
    grid.innerHTML = Array.from({length: Number(model.contract.grid_size) * Number(model.contract.grid_size)}, (_, index) => {
      const row = Math.floor(index / Number(model.contract.grid_size));
      const col = index % Number(model.contract.grid_size);
      const cell = model.phase === "edit" ? cellAt(row, col) : cellAt(row, col, model.simCells);
      const selected = model.selectedCellId && cell?.id === model.selectedCellId ? " is-selected-square" : "";
      return `<div class="grid-cell${selected}" data-row="${row}" data-col="${col}" role="gridcell" aria-label="grid row ${row + 1}, column ${col + 1}">${cell ? cellMarkup(cell, model.phase === "running") : "<span class=\"empty-mark\">·</span>"}</div>`;
    }).join("");
    grid.querySelectorAll(".grid-cell").forEach(square => {
      square.addEventListener("click", event => {
        if (event.target.closest(".placed-cell")) return;
        if (model.phase !== "edit") return;
        if (interaction() === "simplified") {
          selectCell(null);
          model.selectedSquare = {row: Number(square.dataset.row), col: Number(square.dataset.col)};
          square.classList.add("is-selected-square");
          model.helpers.setReadout(`SQUARE R${Number(square.dataset.row) + 1} C${Number(square.dataset.col) + 1} ARMED · PRESS ADD`, "idle");
          updateControls();
        }
      });
      square.addEventListener("dragover", event => {
        if (interaction() === "full" && model.phase === "edit") event.preventDefault();
      });
      square.addEventListener("drop", event => {
        if (interaction() !== "full" || model.phase !== "edit") return;
        event.preventDefault();
        recordAdd(Number(square.dataset.row), Number(square.dataset.col), sourcePair()[0]);
      });
    });
    grid.querySelectorAll(".placed-cell").forEach(button => {
      button.addEventListener("click", event => {
        event.stopPropagation();
        if (model.phase !== "edit") return;
        selectCell(button.dataset.cellId);
        if (interaction() === "full") cycleSelected(sourcePair()[1]);
      });
    });
  }

  function renderTarget() {
    const node = document.querySelector("#target-sequence");
    if (!node) return;
    const target = canonicalEvents(model.contract.target_events || []);
    node.innerHTML = target.length ? target.map((event, index) => `<li><b>${String(index + 1).padStart(2, "0")}</b><span>BEAT ${String(event.beat).padStart(2, "0")}</span><strong>${esc(event.side.toUpperCase())} · SLOT ${Number(event.slot) + 1}</strong></li>`).join("") : "<li class=\"empty-ledger\">NO WALL CHIMES</li>";
  }

  function renderLedger() {
    const node = document.querySelector("#event-log");
    if (!node) return;
    if (!model.wallEvents.length) {
      node.innerHTML = "<li class=\"empty-ledger\">WAITING FOR A FILM</li>";
      return;
    }
    node.innerHTML = model.wallEvents.map((event, index) => `<li class="event-row"><b>${String(index + 1).padStart(2, "0")}</b><span>BEAT ${String(event.beat).padStart(2, "0")}</span><strong>${esc(event.side.toUpperCase())} · ${Number(event.slot) + 1}</strong></li>`).join("");
  }

  function flashWall(event) {
    const rail = document.querySelector(`.wall-rail[data-side="${event.side}"]`);
    if (!rail) return;
    const beat = String(event.beat);
    if (rail.dataset.flashBeat !== beat) {
      rail.classList.remove("is-flashing");
      rail.querySelectorAll(".wall-slot").forEach(slot => slot.classList.remove("is-hit"));
      void rail.getBoundingClientRect();
      rail.dataset.flashBeat = beat;
    }
    rail.classList.add("is-flashing");
    rail.querySelector(`.wall-slot[data-slot="${event.slot}"]`)?.classList.add("is-hit");
    window.setTimeout(() => {
      if (rail.dataset.flashBeat === beat) rail.classList.remove("is-flashing");
    }, Math.min(480, Number(model.contract.beat_ms) * 0.85));
  }

  function applyStep() {
    const cells = canonical(model.simCells);
    const occupied = new Set(cells.map(cell => `${cell.row},${cell.col}`));
    const proposals = cells.map(cell => {
      const [deltaRow, deltaCol] = DELTAS[Number(cell.direction) % 4];
      return {row: Number(cell.row) + deltaRow, col: Number(cell.col) + deltaCol};
    });
    const duplicateCounts = new Map();
    proposals.forEach(proposal => {
      const key = `${proposal.row},${proposal.col}`;
      duplicateCounts.set(key, (duplicateCounts.get(key) || 0) + 1);
    });
    const next = [];
    const beat = model.beat + 1;
    cells.forEach((cell, index) => {
      const proposal = proposals[index];
      const direction = Number(cell.direction) % 4;
      const key = `${proposal.row},${proposal.col}`;
      if (proposal.row < 0 || proposal.row >= Number(model.contract.grid_size) || proposal.col < 0 || proposal.col >= Number(model.contract.grid_size)) {
        const side = SIDES[direction];
        const slot = side === "top" || side === "bottom" ? Number(cell.col) : Number(cell.row);
        const event = {beat, side, slot};
        model.wallEvents.push(event);
        next.push({...cell, direction: (direction + 2) % 4});
        flashWall(event);
      } else if (occupied.has(key) || duplicateCounts.get(key) > 1) {
        next.push({...cell, direction: (direction + 1) % 4});
      } else {
        next.push({...cell, row: proposal.row, col: proposal.col});
      }
    });
    model.wallEvents = canonicalEvents(model.wallEvents);
    model.simCells = next;
    model.beat = beat;
    renderGrid();
    renderLedger();
    const beatNode = document.querySelector("#beat-count");
    if (beatNode) beatNode.textContent = String(model.beat).padStart(2, "0");
    const eventCount = document.querySelector("#event-count");
    if (eventCount) eventCount.textContent = String(model.wallEvents.length).padStart(2, "0");
  }

  function finishFilm() {
    model.phase = "complete";
    model.timer = null;
    model.actionSettle?.settle?.();
    model.actionSettle = null;
    document.querySelector(".collision-chimes")?.classList.add("is-complete");
    model.helpers.setReadout("FILM COMPLETE · COMPARE THE WALL LEDGER, THEN CHECK SEQUENCE", "idle");
    updateControls();
  }

  function scheduleNext() {
    if (!model || model.phase !== "running") return;
    if (model.beat >= Number(model.contract.beats)) {
      finishFilm();
      return;
    }
    model.timer = window.setTimeout(() => {
      if (!model || model.phase !== "running") return;
      applyStep();
      scheduleNext();
    }, Number(model.contract.beat_ms));
  }

  function startFilm() {
    if (model.phase === "running" || model.phase === "submitting") return;
    clearFreshFailure();
    if (model.phase !== "edit") resetFilm();
    model.phase = "running";
    model.beat = 0;
    model.simCells = canonical(model.cells);
    model.wallEvents = [];
    document.querySelector(".collision-chimes")?.classList.remove("is-complete");
    renderGrid();
    renderLedger();
    document.querySelector("#beat-count").textContent = "00";
    document.querySelector("#event-count").textContent = "00";
    model.helpers.setReadout("FILM RUNNING · WATCH FOR WALL FLASHES", "pending");
    model.actionSettle = model.helpers.beginAction?.("collision-chimes-film") || null;
    applyStep();
    scheduleNext();
    updateControls();
  }

  function stepFilm() {
    if (model.phase === "running" || model.phase === "submitting" || model.phase === "complete") return;
    clearFreshFailure();
    model.phase = "stepping";
    if (model.beat === 0) {
      model.simCells = canonical(model.cells);
      model.wallEvents = [];
    }
    model.helpers.setReadout(`STEP ${model.beat + 1} OF ${model.contract.beats} · WATCH THE CELLS`, "pending");
    applyStep();
    if (model.beat >= Number(model.contract.beats)) finishFilm();
    updateControls();
  }

  function reviseFilm() {
    if (model.phase !== 'complete' && model.phase !== 'stepping') return;
    const observed = clone(model.wallEvents);
    resetFilm();
    model.wallEvents = observed;
    renderLedger();
    document.querySelector('.collision-chimes')?.classList.remove('is-complete');
    model.helpers.setReadout('EDIT STARTING ARROWS · LAST FILM LEDGER RETAINED UNTIL NEXT RUN', 'idle');
  }

  function resetBoard() {
    if (model.phase === "running" || model.phase === "submitting") return;
    clearFreshFailure();
    model.cells = [];
    model.editEvents = [];
    model.nextId = 0;
    model.selectedCellId = null;
    model.selectedSquare = null;
    resetFilm();
    model.helpers.setReadout("BOARD CLEARED · PLACE THE FIRST ARROW", "idle");
  }

  async function submit() {
    if (model.phase !== "complete" || model.submitting) return;
    model.phase = "submitting";
    model.submitting = true;
    model.helpers.setReadout("REPLAYING THE CHIME LEDGER…", "pending");
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      input_surface: interaction(),
      edit_events: clone(model.editEvents),
      cells: canonical(model.cells),
      wall_events: clone(model.wallEvents),
      beats_run: model.beat,
      run_completed: true,
      completed: sameEvents(model.wallEvents, model.contract.target_events),
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.helpers.setReadout("PASS · COLLISION CHIMES VERIFIED", "passed");
        document.querySelector(".collision-chimes")?.classList.add("is-passed");
        model.submitting = false;
        return;
      }
      if (outcome.state) {
        await model.helpers.render(outcome.state);
        const freshRoot = document.querySelector(".collision-chimes");
        if (freshRoot) {
          freshRoot.dataset.freshFailure = "true";
          freshRoot.classList.add("is-failed");
        }
        model.helpers.setReadout("FAIL · FRESH CHIME BOARD", "error");
        window.setTimeout(() => document.querySelector(".collision-chimes")?.classList.remove("is-failed"), 1400);
      } else {
        model.submitting = false;
        model.phase = "complete";
        model.helpers.setReadout("FAIL · AUTHORITATIVE LEDGER UNAVAILABLE", "error");
      }
    } catch (_error) {
      model.submitting = false;
      model.phase = "complete";
      model.helpers.setReadout("FAIL · CHIME SERVER UNAVAILABLE", "error");
    }
  }

  function updateControls() {
    const edit = model.phase === "edit";
    const running = model.phase === "running";
    const complete = model.phase === "complete";
    const addButton = document.querySelector("#add-cell");
    const cycleButton = document.querySelector("#cycle-cell");
    const runButton = document.querySelector("#run-film");
    const stepButton = document.querySelector("#step-beat");
    const submitButton = document.querySelector("#submit-sequence");
    const reviseButton = document.querySelector('#revise-film');
    if (reviseButton) reviseButton.disabled = !(complete || model.phase === 'stepping') || model.submitting;
    if (addButton) addButton.disabled = !edit || !model.selectedSquare || model.cells.length >= Number(model.contract.max_cells);
    if (cycleButton) cycleButton.disabled = !edit || !model.selectedCellId;
    if (runButton) runButton.disabled = running || model.submitting || model.cells.length === 0;
    if (stepButton) stepButton.disabled = running || complete || model.submitting || model.cells.length === 0;
    if (submitButton) submitButton.disabled = !complete || model.submitting;
    document.querySelector("#cell-count").textContent = `${model.cells.length} / ${model.contract.max_cells}`;
  }

  function installControls() {
    const reviseButton = document.createElement('button');
    reviseButton.id = 'revise-film';
    reviseButton.type = 'button';
    reviseButton.textContent = '↶ REVISE STARTING ARROWS';
    reviseButton.addEventListener('click', reviseFilm);
    document.querySelector('#step-beat').after(reviseButton);
    document.querySelector("#add-cell")?.addEventListener("click", () => {
      if (!model.selectedSquare) return;
      const placed = recordAdd(model.selectedSquare.row, model.selectedSquare.col, sourcePair()[0]);
      if (placed) model.selectedSquare = null;
      renderGrid();
      updateControls();
    });
    document.querySelector("#cycle-cell")?.addEventListener("click", () => cycleSelected(sourcePair()[1]));
    document.querySelector("#run-film")?.addEventListener("click", startFilm);
    document.querySelector("#step-beat")?.addEventListener("click", stepFilm);
    document.querySelector("#reset-board")?.addEventListener("click", resetBoard);
    document.querySelector("#submit-sequence")?.addEventListener("click", submit);
    const seed = document.querySelector("#chime-seed");
    seed?.addEventListener("dragstart", event => {
      if (model.phase !== "edit") return;
      event.dataTransfer?.setData("text/plain", "chime-seed");
      event.dataTransfer?.setDragImage(seed, 25, 25);
    });
    seed?.addEventListener("keydown", event => {
      if (interaction() === "full" && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        model.helpers.setReadout("DRAG THE BRASS ARROW ONTO AN EMPTY SQUARE", "idle");
      }
    });
  }

  function render(state, helpers) {
    document.body.dataset.mechanic = "collision-chimes-v1";
    const contract = state.contract || {};
    model = {
      state, helpers, contract,
      cells: [], simCells: [], editEvents: [], wallEvents: [],
      selectedCellId: null, selectedSquare: null, nextId: 0,
      beat: 0, phase: "edit", timer: null, actionSettle: null, submitting: false,
    };
    const full = interaction() === "full";
    const target = contract.target_events || [];
    helpers.app.innerHTML = `<section class="collision-chimes" data-interaction="${esc(interaction())}" data-fresh-failure="false" style="--grid-size:${Number(contract.grid_size)};--beat-ms:${Number(contract.beat_ms)}ms;--ink:${esc(contract.palette?.ink || "#182b30")};--paper:${esc(contract.palette?.paper || "#f5f0df")};--coral:${esc(contract.palette?.coral || "#e77b5c")};--mint:${esc(contract.palette?.mint || "#8fc9bd")};--gold:${esc(contract.palette?.gold || "#e7bd68")}">
      <header class="chimes-header"><div><span>FIELD NOTE / MOVING CELL SONIFICATION</span><h1>Collision Chimes</h1><p>${esc(state.prompt)}</p></div><div class="challenge-stamp"><small>BOARD</small><b>${esc(String(state.challenge_id).slice(0, 8).toUpperCase())}</b><i>${full ? "DIRECT" : "PROXY"} INPUT</i></div></header>
      <main class="chimes-main">
        <aside class="chimes-target panel"><div class="panel-kicker">TARGET WALL LEDGER</div><h2>Make these flashes</h2><p class="target-help">The board is judged by every wall, slot, and beat — not by a single starting picture.</p><ol id="target-sequence" aria-label="target wall event sequence">${target.map((event, index) => `<li><b>${String(index + 1).padStart(2, "0")}</b><span>BEAT ${String(event.beat).padStart(2, "0")}</span><strong>${esc(event.side.toUpperCase())} · SLOT ${Number(event.slot) + 1}</strong></li>`).join("")}</ol><div class="sequence-key"><span><i class="key-dot top"></i>top / bottom use columns</span><span><i class="key-dot side"></i>left / right use rows</span></div></aside>
        <section class="chimes-stage panel"><div class="stage-ribbon"><span>LIVE BOARD</span><b>BEAT <strong id="beat-count">00</strong> / ${Number(contract.beats)}</b><i><em id="event-count">00</em> WALL HITS</i></div><div class="board-frame"><div class="wall-rail rail-top" data-side="top"><label>TOP</label><div class="wall-slots">${Array.from({length: Number(contract.grid_size)}, (_, index) => `<i class="wall-slot" data-slot="${index}"></i>`).join("")}</div></div><div class="wall-rail rail-right" data-side="right"><label>RIGHT</label><div class="wall-slots">${Array.from({length: Number(contract.grid_size)}, (_, index) => `<i class="wall-slot" data-slot="${index}"></i>`).join("")}</div></div><div class="wall-rail rail-bottom" data-side="bottom"><label>BOTTOM</label><div class="wall-slots">${Array.from({length: Number(contract.grid_size)}, (_, index) => `<i class="wall-slot" data-slot="${index}"></i>`).join("")}</div></div><div class="wall-rail rail-left" data-side="left"><label>LEFT</label><div class="wall-slots">${Array.from({length: Number(contract.grid_size)}, (_, index) => `<i class="wall-slot" data-slot="${index}"></i>`).join("")}</div></div><div id="chime-grid" class="chime-grid" role="grid" aria-label="collision chimes board"></div></div><div class="rule-card"><b>FOUR BEATS, ONE MACHINE</b><span>arrows move → walls reverse them → encounters turn them clockwise</span></div></section>
        <aside class="chimes-console panel"><div class="panel-kicker">CONFIGURE / OBSERVE / REVISE</div><h2>${full ? "Direct placement" : "Proxy controls"}</h2><p class="console-copy">${full ? "Drag the brass arrow onto an empty square. Click a placed arrow to cycle its direction." : "Click an empty square, add an up arrow, then select it and rotate it with the proxy button."}</p>${full ? `<div class="seed-tray"><div id="chime-seed" class="chime-seed" draggable="true" role="button" tabindex="0" aria-label="drag a brass arrow onto the board"><i></i><b>DRAG ARROW</b><span>STARTS UP</span></div></div>` : `<div class="proxy-controls"><button type="button" id="add-cell">＋ ADD TO ARMED SQUARE</button><button type="button" id="cycle-cell" disabled>↻ ROTATE SELECTED ARROW</button></div>`}<div class="console-meter"><span>CELLS IN CONFIGURATION</span><b id="cell-count">0 / ${Number(contract.max_cells)}</b></div><div class="button-stack"><button type="button" id="run-film" class="primary">▶ RUN ${Number(contract.beats)} BEATS</button><button type="button" id="step-beat">＋ STEP ONE BEAT</button><button type="button" id="reset-board">× CLEAR CONFIGURATION</button><button type="button" id="submit-sequence" class="check" disabled>✓ CHECK SEQUENCE</button></div><div class="readout" data-status="idle">PLACE ARROWS, THEN RUN A FILM</div></aside>
      </main>
      <footer class="chimes-footer"><div><span class="footer-kicker">OBSERVED WALL EVENTS</span><ol id="event-log"><li class="empty-ledger">WAITING FOR A FILM</li></ol></div><div class="footer-note"><b>VISIBLE RULES</b><p>All edits happen before a film. A test run can be watched, compared with the target ledger, and revised.</p></div></footer>
    </section>`;
    renderGrid();
    renderTarget();
    installControls();
    updateControls();
    window.collisionChimesModel = model;
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {render, rootSelector: ".collision-chimes"};
})();
