(() => {
  "use strict";

  let model = null;
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const esc = (value) => String(value == null ? "" : value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const deltas = {up: [-1, 0], down: [1, 0], left: [0, -1], right: [0, 1]};
  const directionLabel = {up: "NORTH", down: "SOUTH", left: "WEST", right: "EAST"};
  const interaction = () => model?.state?.control_condition?.interaction || "full";
  const workerById = (id) => model.board.workers.find((worker) => worker.id === id);

  function occupied() {
    const result = new Map();
    model.board.workers.forEach((worker) => result.set(worker.position.join(","), {kind: "worker", id: worker.id}));
    model.board.crates.forEach((crate) => result.set(crate.position.join(","), {kind: "crate", id: crate.id}));
    return result;
  }

  function switchOpen(switchId) {
    const sw = model.board.switches.find((item) => item.id === switchId);
    if (!sw) return false;
    const point = sw.position.join(",");
    return model.board.workers.concat(model.board.crates).some((item) => item.position.join(",") === point);
  }

  function passable(point, workerId) {
    const [row, column] = point;
    if (row < 0 || row >= model.board.rows || column < 0 || column >= model.board.columns) return false;
    if (model.board.walls.some((wall) => wall[0] === row && wall[1] === column)) return false;
    const door = model.board.doors.find((item) => item.position[0] === row && item.position[1] === column);
    if (door && !switchOpen(door.switch_id)) return false;
    const occupant = occupied().get(`${row},${column}`);
    return !occupant || occupant.kind === "crate" || (occupant.kind === "worker" && occupant.id === workerId);
  }

  function applyMove(workerId, direction) {
    const next = clone(model.board);
    const worker = next.workers.find((item) => item.id === workerId);
    if (!worker || !deltas[direction]) return null;
    const [dr, dc] = deltas[direction];
    const old = [...worker.position];
    const dest = [old[0] + dr, old[1] + dc];
    const oldBoard = model.board;
    const oldOccupied = occupied();
    if (!passable(dest, workerId)) return null;
    const occupant = oldOccupied.get(dest.join(","));
    if (occupant?.kind === "worker") return null;
    const crate = next.crates.find((item) => item.position[0] === dest[0] && item.position[1] === dest[1]);
    let ability = "move";
    let crateId = null;
    if (crate) {
      crateId = crate.id;
      if (worker.role === "fighter") {
        const beyond = [dest[0] + dr, dest[1] + dc];
        const beyondOccupied = oldOccupied.get(beyond.join(","));
        if (!passable(beyond, workerId) || beyondOccupied) return null;
        crate.position = beyond;
        ability = "push";
      } else {
        crate.position = old;
        ability = worker.role === "thief" ? "pull" : "swap";
      }
    } else if (worker.role === "thief") {
      const behind = [old[0] - dr, old[1] - dc];
      const trailing = next.crates.find((item) => item.position[0] === behind[0] && item.position[1] === behind[1]);
      if (trailing) {
        trailing.position = old;
        crateId = trailing.id;
        ability = "pull";
      }
    }
    worker.position = dest;
    const doorStates = {};
    next.doors.forEach((door) => {
      const sw = next.switches.find((item) => item.id === door.switch_id);
      const point = sw?.position?.join(",");
      doorStates[door.id] = next.workers.concat(next.crates).some((item) => item.position.join(",") === point);
    });
    return {
      board: next,
      info: {
        worker_id: workerId,
        direction,
        from: old,
        to: dest,
        ability,
        crate_id: crateId,
        door_states: doorStates,
        workers_after: clone(next.workers),
        crates_after: clone(next.crates),
      },
    };
  }

  function solved() {
    return model.board.workers.every((worker) => {
      const goal = model.board.goals.find((item) => item.worker_id === worker.id);
      return goal && goal.position[0] === worker.position[0] && goal.position[1] === worker.position[1];
    });
  }

  function selectWorker(workerId, inputSource) {
    if (model.busy || model.passed || !workerById(workerId)) return;
    document.querySelector(".ttc-verdict-layer .ttc-fail")?.remove();
    model.selected = workerId;
    model.selections.push({worker_id: workerId, input_source: inputSource, movement_index: model.events.length});
    update();
    model.helpers.setReadout(`${workerById(workerId).label} ACTIVE`, "idle");
  }

  function move(direction, inputSource) {
    if (model.busy || model.passed || !model.selected) return;
    document.querySelector(".ttc-verdict-layer .ttc-fail")?.remove();
    const result = applyMove(model.selected, direction);
    if (!result) {
      model.helpers.setReadout("BLOCKED", "error");
      return;
    }
    model.board = result.board;
    const event = result.info;
    event.sequence = model.events.length + 1;
    event.input_source = inputSource;
    model.events.push(event);
    update();
    model.helpers.setReadout(solved() ? "ALL BAYS READY" : `${event.ability.toUpperCase()} · ${directionLabel[direction]}`, solved() ? "passed" : "idle");
  }

  function workerMarkup(worker) {
    const selected = worker.id === model.selected ? " is-selected" : "";
    return `<button type="button" class="ttc-worker-card${selected}" data-worker-id="${esc(worker.id)}" aria-label="${esc(worker.label)}">
      <span class="ttc-worker-icon role-${esc(worker.role)}"><i></i><b></b></span><span><strong>${esc(worker.label)}</strong><small>${esc(worker.role === "fighter" ? "PUSH" : worker.role === "thief" ? "PULL" : "SWAP")}</small></span>
    </button>`;
  }

  function cellMarkup(row, column) {
    const key = `${row},${column}`;
    const wall = model.board.walls.some((item) => item[0] === row && item[1] === column);
    if (wall) return `<div class="ttc-cell ttc-wall" data-row="${row}" data-column="${column}"><span></span></div>`;
    const door = model.board.doors.find((item) => item.position[0] === row && item.position[1] === column);
    const sw = model.board.switches.find((item) => item.position[0] === row && item.position[1] === column);
    const goal = model.board.goals.find((item) => item.position[0] === row && item.position[1] === column);
    const worker = model.board.workers.find((item) => item.position[0] === row && item.position[1] === column);
    const crate = model.board.crates.find((item) => item.position[0] === row && item.position[1] === column);
    const classes = ["ttc-cell"];
    if (door) classes.push("ttc-door", `door-${door.color}`, switchOpen(door.switch_id) ? "is-open" : "is-closed");
    if (sw) classes.push("ttc-switch", `switch-${sw.color}`);
    if (goal) classes.push("ttc-goal");
    let content = "";
    if (goal) content += `<span class="ttc-goal-mark">${esc(goal.label)}</span>`;
    if (sw) content += `<span class="ttc-switch-mark">${esc(sw.label)}</span>`;
    if (door) content += `<span class="ttc-door-mark">${switchOpen(door.switch_id) ? "OPEN" : "LOCK"}</span>`;
    if (crate) content += `<span class="ttc-crate" style="--crate-color:${esc(crate.color)}"><i></i><b>${esc(crate.id.slice(-1))}</b></span>`;
    if (worker) content += `<span class="ttc-worker-token role-${esc(worker.role)}${worker.id === model.selected ? " is-selected" : ""}"><i></i><b>${esc(worker.label[0])}</b></span>`;
    return `<div class="${classes.join(" ")}" data-row="${row}" data-column="${column}">${content}</div>`;
  }

  function boardMarkup() {
    const cells = [];
    for (let row = 0; row < model.board.rows; row += 1) {
      for (let column = 0; column < model.board.columns; column += 1) cells.push(cellMarkup(row, column));
    }
    return cells.join("");
  }

  function controlsMarkup() {
    const dirs = ["up", "left", "down", "right"];
    return `<div class="ttc-direction-pad">${dirs.map((dir) => `<button type="button" data-direction="${dir}"><span>${dir === "up" ? "▲" : dir === "down" ? "▼" : dir === "left" ? "◀" : "▶"}</span><small>${directionLabel[dir]}</small></button>`).join("")}</div>`;
  }

  function update() {
    const board = document.querySelector(".ttc-board");
    if (board) board.innerHTML = boardMarkup();
    document.querySelectorAll(".ttc-worker-card").forEach((button) => button.classList.toggle("is-selected", button.dataset.workerId === model.selected));
    document.querySelector(".ttc-count")?.replaceChildren(document.createTextNode(`${model.events.length} MOVES`));
    bindControls();
  }

  function bindControls() {
    document.querySelectorAll(".ttc-worker-card").forEach((button) => {
      if (interaction() === "simplified") button.onclick = () => selectWorker(button.dataset.workerId, "worker_card");
    });
    document.querySelectorAll(".ttc-direction-pad button").forEach((button) => {
      button.onclick = () => move(button.dataset.direction, "direction_button");
    });
  }

  function keyHandler(event) {
    if (interaction() !== "full" || event.repeat || model.busy || model.passed) return;
    const selectMap = {Digit1: "fighter", Digit2: "thief", Digit3: "wizard"};
    if (selectMap[event.code]) { event.preventDefault(); selectWorker(selectMap[event.code], "keyboard_select"); return; }
    if (event.key.toLowerCase() === "x") {
      event.preventDefault();
      const index = model.board.workers.findIndex((worker) => worker.id === model.selected);
      selectWorker(model.board.workers[(index + 1 + model.board.workers.length) % model.board.workers.length].id, "keyboard_select");
      return;
    }
    const direction = {ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right"}[event.key];
    if (direction) { event.preventDefault(); move(direction, "keyboard_move"); }
  }

  async function submit(completed) {
    if (model.busy || model.passed) return;
    model.busy = true;
    model.helpers.setReadout("CHECKING", "pending");
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      interaction_mode: interaction(),
      selection_events: clone(model.selections),
      events: clone(model.events),
      final_board: {workers: clone(model.board.workers), crates: clone(model.board.crates)},
      completed: completed === true,
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.busy = false; model.passed = true;
        document.querySelector(".three-trade-crew")?.classList.add("is-pass");
        document.querySelector(".ttc-verdict-layer .ttc-fail")?.remove();
        document.querySelector(".ttc-verdict-layer")?.insertAdjacentHTML("beforeend", '<div class="ttc-verdict ttc-pass"><strong>PASS</strong><small>CREW PARKED</small></div>');
        model.helpers.setReadout("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await render(outcome.state, model.helpers, {freshFailure: true});
        model.helpers.setReadout("FAIL", "error");
      } else {
        model.busy = false; model.helpers.setReadout("FAIL", "error");
      }
    } catch (_error) {
      model.busy = false; model.helpers.setReadout("FAIL", "error");
    }
  }

  async function render(state, helpers, options = {}) {
    document.body.dataset.mechanic = "three-trade-crew";
    model = {state, helpers, board: clone(state.board), selected: "fighter", selections: [], events: [], busy: false, passed: false};
    helpers.app.innerHTML = `<section class="three-trade-crew mode-${esc(interaction())}" data-challenge-id="${esc(state.challenge_id)}">
      <header class="ttc-header"><div class="ttc-badge"><i></i><b>3</b></div><div><small>THE THREE-TRADE WORKSHOP</small><h1>${esc(state.prompt)}</h1></div><div class="ttc-count">0 MOVES</div></header>
      <main class="ttc-main"><aside class="ttc-sidebar"><div class="ttc-panel-title">CREW ROSTER</div><div class="ttc-roster">${model.board.workers.map(workerMarkup).join("")}</div></aside><section class="ttc-arena"><div class="ttc-arena-label"><span>WORKSHOP FLOOR</span><i></i><span>EXIT BAYS F / T / W</span></div><div class="ttc-board" style="--ttc-cols:${state.board.columns};--ttc-rows:${state.board.rows}">${boardMarkup()}</div></section><aside class="ttc-controls"><div class="ttc-panel-title">${interaction() === "full" ? "KEYBOARD DECK" : "CONTROL DECK"}</div>${interaction() === "full" ? '<p class="ttc-key-help">1 / 2 / 3 selects a worker · X cycles · ARROW KEYS move</p>' : '<p class="ttc-key-help">Select a worker, then send one square at a time.</p>'}${controlsMarkup()}</aside></main>
      <footer class="ttc-footer"><button type="button" id="ttc-reset">RESET VIEW</button><div class="ttc-status"><div class="readout" data-status="idle">${options.freshFailure ? "FAIL · FRESH WORKSHOP" : ""}</div></div><button type="button" id="ttc-certify">CERTIFY CREW</button></footer><div class="ttc-verdict-layer">${options.freshFailure ? '<div class="ttc-verdict ttc-fail"><strong>FAIL</strong><small>FRESH WORKSHOP LOADED</small></div>' : ""}</div>${helpers.cheatPanelTemplate()}</section>`;
    bindControls();
    document.getElementById("ttc-certify")?.addEventListener("click", () => submit(solved()));
    document.getElementById("ttc-reset")?.addEventListener("click", () => { model.board = clone(model.state.board); model.selections = []; model.events = []; model.selected = "fighter"; update(); model.helpers.setReadout("RESET", "idle"); });
    window.removeEventListener("keydown", keyHandler);
    window.addEventListener("keydown", keyHandler);
    helpers.installCheatPanel();
    window.threeTradeCrewModel = model;
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.three_trade_crew = {rootSelector: ".three-trade-crew", render};
})();
