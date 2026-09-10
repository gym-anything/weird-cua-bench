(() => {
  "use strict";

  const DELTAS = {N: [0, -1], E: [1, 0], S: [0, 1], W: [-1, 0]};
  let model = null;
  let cleanup = null;

  function shape(boat) {
    return boat.orientation === "horizontal" ? [2, 1] : [1, 2];
  }

  function cells(boat, x = boat.x, y = boat.y) {
    const [width, height] = shape(boat);
    const result = [];
    for (let dx = 0; dx < width; dx += 1) {
      for (let dy = 0; dy < height; dy += 1) result.push([x + dx, y + dy]);
    }
    return result;
  }

  function ropeCells(boat, x = boat.x, y = boat.y) {
    if (boat.orientation === "horizontal") return [[x, y - 1], [x + 1, y - 1], [x, y + 1], [x + 1, y + 1]];
    return [[x - 1, y], [x - 1, y + 1], [x + 1, y], [x + 1, y + 1]];
  }

  function key(x, y) { return `${x},${y}`; }
  function boatById(id) { return model.boats.find((boat) => boat.id === id); }
  function passengerById(id) { return model.passengers.find((passenger) => passenger.id === id); }

  function clearVerdict() {
    const root = document.querySelector(".lagoon-captcha");
    root?.classList.remove("is-passed", "is-failed");
    const verdict = root?.querySelector(".lagoon-verdict");
    if (verdict) verdict.replaceChildren();
  }

  function verdict(kind, title, detail) {
    const root = document.querySelector(".lagoon-captcha");
    const node = root?.querySelector(".lagoon-verdict");
    if (!root || !node) return;
    root.classList.toggle("is-passed", kind === "pass");
    root.classList.toggle("is-failed", kind === "fail");
    node.innerHTML = detail ? `<b>${title}</b><span>${detail}</span>` : `<b>${title}</b>`;
  }

  function boardPoint(event) {
    const board = document.querySelector(".lagoon-board");
    const rect = board.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(model.state.board.columns - 1, Math.floor((event.clientX - rect.left) / rect.width * model.state.board.columns))),
      y: Math.max(0, Math.min(model.state.board.rows - 1, Math.floor((event.clientY - rect.top) / rect.height * model.state.board.rows))),
    };
  }

  function footprintClear(boat, x, y) {
    const reefKeys = new Set(model.reefs.map((item) => key(item[0], item[1])));
    const candidate = cells(boat, x, y);
    if (candidate.some(([cx, cy]) => cx < 0 || cy < 0 || cx >= model.state.board.columns || cy >= model.state.board.rows)) return false;
    if (candidate.some(([cx, cy]) => reefKeys.has(key(cx, cy)))) return false;
    return model.boats.every((other) => other.id === boat.id || !candidate.some(([cx, cy]) => cells(other).some(([ox, oy]) => cx === ox && cy === oy)));
  }

  function displayBoatPosition(boat) {
    if (model.drag?.boatId === boat.id && model.drag.preview) return model.drag.preview;
    return {x: boat.x, y: boat.y};
  }

  function draw() {
    if (!model) return;
    const board = document.querySelector(".lagoon-board");
    const entities = document.querySelector(".lagoon-entities");
    if (!board || !entities) return;
    entities.replaceChildren();
    for (const passenger of model.passengers) {
      if (passenger.boarded) continue;
      const node = document.createElement("span");
      node.className = "lagoon-passenger";
      node.dataset.passengerId = passenger.id;
      node.style.left = `${(passenger.position[0] + 0.5) / model.state.board.columns * 100}%`;
      node.style.top = `${(passenger.position[1] + 0.5) / model.state.board.rows * 100}%`;
      node.innerHTML = "<i></i><b>•</b>";
      entities.appendChild(node);
    }
    for (const boat of model.boats) {
      const [width, height] = shape(boat);
      const position = displayBoatPosition(boat);
      const node = document.createElement("button");
      node.type = "button";
      node.className = `lagoon-boat boat-${boat.color}${model.selectedBoatId === boat.id ? " is-selected" : ""}`;
      node.dataset.boatId = boat.id;
      node.dataset.orientation = boat.orientation;
      node.style.left = `${position.x / model.state.board.columns * 100}%`;
      node.style.top = `${position.y / model.state.board.rows * 100}%`;
      node.style.width = `${width / model.state.board.columns * 100}%`;
      node.style.height = `${height / model.state.board.rows * 100}%`;
      const ropeMarkup = boat.orientation === "horizontal"
        ? "<i class='lagoon-rope rope-north'></i><i class='lagoon-rope rope-south'></i>"
        : "<i class='lagoon-rope rope-west'></i><i class='lagoon-rope rope-east'></i>";
      const seats = Array.from({length: boat.capacity}, (_, index) => `<i class="lagoon-seat ${index < boat.occupants.length ? "is-filled" : ""}"></i>`).join("");
      node.innerHTML = `${ropeMarkup}<span class="boat-name">${boat.id.replace("boat-", "BOAT ")}</span><span class="lagoon-seats">${seats}</span>`;
      entities.appendChild(node);
    }
    const selected = document.querySelector(".lagoon-selected-name");
    if (selected) selected.textContent = model.selectedBoatId ? model.selectedBoatId.replace("boat-", "BOAT ") : "NONE";
    document.querySelectorAll("[data-lagoon-select]").forEach((row) => {
      row.classList.toggle("is-selected", row.dataset.lagoonSelect === model.selectedBoatId);
    });
    document.querySelector(".lagoon-certify").disabled = model.submitting || model.terminal;
    if (model.interaction === "full" && !model.submitting && !model.terminal) {
      document.querySelectorAll(".lagoon-boat").forEach(attachFullDrag);
    }
  }

  function recordAction(action) {
    model.actions.push({sequence: model.actions.length + 1, ...action});
  }

  function move(boatId, direction, inputSource) {
    if (!model || model.submitting || model.terminal || !DELTAS[direction]) return;
    clearVerdict();
    const boat = boatById(boatId);
    if (!boat) return;
    const from = [boat.x, boat.y];
    const [dx, dy] = DELTAS[direction];
    const to = [boat.x + dx, boat.y + dy];
    if (!footprintClear(boat, to[0], to[1])) {
      model.helpers.setReadout("MOVE BLOCKED", "error");
      draw();
      return;
    }
    boat.x = to[0];
    boat.y = to[1];
    const contacts = new Set(ropeCells(boat).map(([x, y]) => key(x, y)));
    const boarded = [];
    let free = boat.capacity - boat.occupants.length;
    for (const passenger of [...model.passengers].sort((a, b) => a.id.localeCompare(b.id))) {
      if (passenger.boarded || free <= 0 || !contacts.has(key(passenger.position[0], passenger.position[1]))) continue;
      passenger.boarded = true;
      passenger.boat_id = boatId;
      passenger.seat = boat.occupants.length;
      boat.occupants.push(passenger.id);
      boarded.push(passenger.id);
      free -= 1;
    }
    recordAction({boat_id: boatId, direction, from, to, input_source: inputSource, accepted: true, boarded});
    model.helpers.setReadout("READY", "idle");
    draw();
  }

  function selectBoat(id) {
    if (model.terminal || model.submitting) return;
    model.selectedBoatId = id;
    draw();
  }

  function attachFullDrag(node) {
    const boatId = node.dataset.boatId;
    node.addEventListener("pointerdown", (event) => {
      if (model.submitting || model.terminal || event.button !== 0) return;
      event.preventDefault();
      clearVerdict();
      const boat = boatById(boatId);
      model.selectedBoatId = boatId;
      node.classList.add("is-selected");
      const selected = document.querySelector(".lagoon-selected-name");
      if (selected) selected.textContent = boatId.replace("boat-", "BOAT ");
      node.setPointerCapture?.(event.pointerId);
      const board = document.querySelector(".lagoon-board");
      const rect = board.getBoundingClientRect();
      model.drag = {
        boatId,
        start: [boat.x, boat.y],
        preview: {x: boat.x, y: boat.y},
        pointerId: event.pointerId,
        startClient: [event.clientX, event.clientY],
        cellSize: [rect.width / model.state.board.columns, rect.height / model.state.board.rows],
        node,
      };
    });
    node.addEventListener("pointermove", (event) => {
      if (!model.drag || model.drag.boatId !== boatId || model.drag.pointerId !== event.pointerId) return;
      const [cellWidth, cellHeight] = model.drag.cellSize;
      const dx = Math.round((event.clientX - model.drag.startClient[0]) / cellWidth);
      const dy = Math.round((event.clientY - model.drag.startClient[1]) / cellHeight);
      model.drag.preview = {x: model.drag.start[0] + dx, y: model.drag.start[1] + dy};
      node.style.left = `${model.drag.preview.x / model.state.board.columns * 100}%`;
      node.style.top = `${model.drag.preview.y / model.state.board.rows * 100}%`;
    });
    const release = (event) => {
      if (!model.drag || model.drag.boatId !== boatId || model.drag.pointerId !== event.pointerId) return;
      const drag = model.drag;
      model.drag = null;
      const [cellWidth, cellHeight] = drag.cellSize;
      const dx = Math.round((event.clientX - drag.startClient[0]) / cellWidth);
      const dy = Math.round((event.clientY - drag.startClient[1]) / cellHeight);
      if (Math.abs(dx) + Math.abs(dy) !== 1) {
        model.helpers.setReadout("MOVE BLOCKED", "error");
        draw();
        return;
      }
      const direction = dx === 1 ? "E" : dx === -1 ? "W" : dy === 1 ? "S" : "N";
      move(boatId, direction, "drag");
    };
    node.addEventListener("pointerup", release);
    node.addEventListener("pointercancel", (event) => {
      if (model.drag?.pointerId !== event.pointerId) return;
      model.drag = null;
      draw();
    });
  }

  function finalSnapshot() {
    return {
      boats: model.boats.map((boat) => ({id: boat.id, x: boat.x, y: boat.y})),
      boarded: model.passengers.filter((passenger) => passenger.boarded).map((passenger) => passenger.id),
    };
  }

  async function submit(completed) {
    if (!model || model.submitting || model.terminal) return;
    model.submitting = true;
    draw();
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      completed,
      interaction_mode: model.interaction,
      actions: completed ? model.actions : [],
      final: completed ? finalSnapshot() : {},
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true;
        model.submitting = false;
        verdict("pass", "PASS", "");
        model.helpers.setReadout("PASS · RESCUE CERTIFIED", "passed");
        draw();
      } else if (outcome.state) {
        const helpers = model.helpers;
        // Keep the failed attempt visible long enough to provide a useful
        // failure frame, then render the server-issued challenge as a fresh
        // neutral attempt.  The old implementation rendered the new state
        // and painted FAIL onto it, leaving a stale terminal label on the
        // first frame of the next attempt.
        verdict("fail", "FAIL", "");
        helpers.setReadout("FAIL", "error");
        const wallTimer = window.WeirdCaptchaTime?.native?.setTimeout || window.setTimeout;
        await new Promise((resolve) => wallTimer(resolve, 300));
        await render(outcome.state, helpers);
      } else {
        model.submitting = false;
        model.helpers.setReadout("FAIL", "error");
        draw();
      }
    } catch (_error) {
      model.submitting = false;
      model.helpers.setReadout("ERROR", "error");
      draw();
    }
  }

  async function render(state, helpers) {
    if (cleanup) cleanup();
    document.body.dataset.mechanic = "last-seats-in-the-lagoon";
    const interaction = state.control_condition?.interaction || "full";
    model = {
      state,
      helpers,
      interaction,
      boats: (state.boats || []).map((boat) => ({...boat, occupants: [...(boat.occupants || [])]})),
      passengers: (state.passengers || []).map((passenger) => ({...passenger, boarded: false})),
      reefs: (state.reefs || []).map((reef) => [Number(reef[0]), Number(reef[1])]),
      actions: [],
      selectedBoatId: null,
      drag: null,
      submitting: false,
      terminal: false,
    };
    const cellsMarkup = [];
    for (let y = 0; y < state.board.rows; y += 1) {
      for (let x = 0; x < state.board.columns; x += 1) {
        const reef = model.reefs.some((item) => item[0] === x && item[1] === y);
        cellsMarkup.push(`<i class="lagoon-cell${reef ? " is-reef" : ""}" data-cell="${x},${y}">${reef ? "✦" : ""}</i>`);
      }
    }
    const buttonMarkup = interaction === "simplified"
      ? `<div class="lagoon-direction-pad" aria-label="Boat movement controls"><button type="button" data-lagoon-direction="N">↑</button><button type="button" data-lagoon-direction="W">←</button><button type="button" data-lagoon-direction="S">↓</button><button type="button" data-lagoon-direction="E">→</button></div>`
      : "";
    helpers.app.innerHTML = `
      <section class="lagoon-captcha" data-interaction="${helpers.text(interaction)}" data-challenge-id="${helpers.text(state.challenge_id)}" tabindex="0">
        <div class="lagoon-verdict" aria-live="assertive"></div>
        <header class="lagoon-header"><div><span>LAGOON</span><h1>Last Seats in the Lagoon</h1><p>Seat every passenger.</p></div></header>
        <div class="lagoon-layout">
          <div class="lagoon-board-wrap"><div class="lagoon-board" style="--lagoon-columns:${state.board.columns};--lagoon-rows:${state.board.rows}"><div class="lagoon-grid">${cellsMarkup.join("")}</div><div class="lagoon-entities"></div></div></div>
          <aside class="lagoon-console"><div class="console-kicker">LAGOON</div><div class="console-selected">SELECTED <b class="lagoon-selected-name">NONE</b></div><div class="lagoon-fleet">${state.boats.map((boat) => `<button type="button" class="lagoon-fleet-row" data-lagoon-select="${boat.id}"><span class="fleet-swatch boat-${boat.color}"></span><b>${boat.id.replace("boat-", "BOAT ")}</b></button>`).join("")}</div>${buttonMarkup}</aside>
        </div>
        <footer class="lagoon-footer"><div class="readout" data-status="idle">READY</div><button type="button" class="lagoon-abandon">ABANDON / NEW LAGOON</button><button type="button" class="lagoon-certify">CERTIFY RESCUE</button></footer>
      </section>`;
    document.querySelectorAll("[data-lagoon-select]").forEach((node) => node.addEventListener("click", () => selectBoat(node.dataset.lagoonSelect)));
    document.querySelectorAll("[data-lagoon-direction]").forEach((node) => node.addEventListener("click", () => {
      if (!model.selectedBoatId) return;
      move(model.selectedBoatId, node.dataset.lagoonDirection, "direction_buttons");
    }));
    document.querySelector(".lagoon-abandon").addEventListener("click", () => submit(false));
    document.querySelector(".lagoon-certify").addEventListener("click", () => submit(true));
    cleanup = () => { model.drag = null; };
    draw();
    document.querySelector(".lagoon-board")?.focus();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.last_seats_in_the_lagoon = {rootSelector: ".lagoon-captcha", render};
})();
