(() => {
  "use strict";

  let model = null;
  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const interaction = () => model?.state.control_condition?.interaction || "simplified";
  const ordered = (monsters) => [...monsters].sort((left, right) => left.id.localeCompare(right.id));
  const byId = (id) => model.monsters.find((monster) => monster.id === id);

  function dragGeometry() {
    const geometry = model?.state.interaction_geometry || {};
    return {
      radiusCells: Number(geometry.drag_target_radius_cells),
      minTravelPx: Number(geometry.min_drag_travel_px),
      minSamples: Number(geometry.min_drag_samples),
    };
  }

  function pointMatchesMonster(point, monster) {
    const size = Number(model?.state.grid_size);
    const radius = dragGeometry().radiusCells / size;
    if (!monster || !Number.isFinite(radius) || radius <= 0) return false;
    const centerU = (Number(monster.column) + 0.5) / size;
    const centerV = (Number(monster.row) + 0.5) / size;
    return Math.hypot(point.u - centerU, point.v - centerV) <= radius;
  }

  function clearLine(actor, victim, monsters = model.monsters) {
    if (actor.row !== victim.row && actor.column !== victim.column) return false;
    const occupied = new Set(monsters
      .filter((monster) => monster.id !== actor.id && monster.id !== victim.id)
      .map((monster) => `${monster.row},${monster.column}`));
    if (actor.row === victim.row) {
      for (let column = Math.min(actor.column, victim.column) + 1; column < Math.max(actor.column, victim.column); column += 1) {
        if (occupied.has(`${actor.row},${column}`)) return false;
      }
    } else {
      for (let row = Math.min(actor.row, victim.row) + 1; row < Math.max(actor.row, victim.row); row += 1) {
        if (occupied.has(`${row},${actor.column}`)) return false;
      }
    }
    return true;
  }

  function isLegal(actor, victim, monsters = model.monsters) {
    return Boolean(actor && victim && actor.id !== victim.id && actor.mouth === victim.body && clearLine(actor, victim, monsters));
  }

  function legalMoves(monsters = model.monsters) {
    const moves = [];
    monsters.forEach((actor) => monsters.forEach((victim) => {
      if (isLegal(actor, victim, monsters)) moves.push([actor.id, victim.id]);
    }));
    return moves;
  }

  function monsterGraphic(monster) {
    const eyes = Array.from({length: Number(monster.eyes || 2)}, (_, index) => `<i class="coa-eye eye-${index + 1}"><u></u></i>`).join("");
    const horns = Array.from({length: Number(monster.horns || 0)}, (_, index) => `<i class="coa-horn horn-${index + 1}"></i>`).join("");
    return `<span class="coa-shadow"></span>
      <span class="coa-creature shape-${Number(monster.shape || 0)} body-${esc(monster.body)}" style="--coa-tilt:${Number(monster.tilt || 0)}deg">
        <span class="coa-horns">${horns}</span>
        <span class="coa-body-mark mark-${Number(monster.mark || 0)}"></span>
        <span class="coa-eyes eyes-${Number(monster.eyes || 2)}">${eyes}</span>
        <span class="coa-mouth mouth-${esc(monster.mouth)}"><i></i><b></b><i></i></span>
      </span>`;
  }

  function boardMarkup() {
    const size = Number(model.state.grid_size);
    const cells = new Map(model.monsters.map((monster) => [`${monster.row},${monster.column}`, monster]));
    const markup = [];
    for (let row = 0; row < size; row += 1) {
      for (let column = 0; column < size; column += 1) {
        const monster = cells.get(`${row},${column}`);
        if (!monster) {
          markup.push(`<div class="coa-cell is-empty" data-row="${row}" data-column="${column}"><span>·</span></div>`);
          continue;
        }
        const selected = model.selectedId === monster.id ? " is-selected" : "";
        markup.push(`<div class="coa-cell is-occupied" data-row="${row}" data-column="${column}">
          <button type="button" class="coa-monster${selected}" data-monster-id="${esc(monster.id)}"
            aria-label="Creature">${monsterGraphic(monster)}</button>
        </div>`);
      }
    }
    return markup.join("");
  }

  function updateBoard() {
    const board = document.getElementById("coa-board");
    if (!board) return;
    board.innerHTML = boardMarkup();
    bindMonsters();
  }

  function boardPoint(event) {
    const board = document.getElementById("coa-board");
    const rect = board?.getBoundingClientRect();
    const width = Number(board?.clientWidth || 0);
    const height = Number(board?.clientHeight || 0);
    if (!rect || width <= 0 || height <= 0) return {u: 0, v: 0};
    return {
      u: Math.max(0, Math.min(1, (event.clientX - rect.left - board.clientLeft) / width)),
      v: Math.max(0, Math.min(1, (event.clientY - rect.top - board.clientTop) / height)),
    };
  }

  function onPointerMove(event) {
    const drag = model.drag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    const dx = event.clientX - drag.lastX;
    const dy = event.clientY - drag.lastY;
    drag.travel += Math.hypot(dx, dy);
    drag.lastX = event.clientX;
    drag.lastY = event.clientY;
    drag.samples += 1;
    drag.node.style.setProperty("--drag-x", `${event.clientX - drag.startX}px`);
    drag.node.style.setProperty("--drag-y", `${event.clientY - drag.startY}px`);
  }

  function finishPointer(event, cancelled = false) {
    const drag = model.drag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    const endPoint = boardPoint(event);
    const finalTravel = drag.travel + Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY);
    const sampleCount = drag.samples + 2;
    const candidates = cancelled ? [] : document.elementsFromPoint(event.clientX, event.clientY)
      .map((node) => node.closest?.(".coa-monster"))
      .filter((node, index, all) => node && all.indexOf(node) === index && node.dataset.monsterId !== drag.actorId);
    const victimId = candidates[0]?.dataset.monsterId || "";
    drag.node.classList.remove("is-dragging");
    drag.node.style.removeProperty("--drag-x");
    drag.node.style.removeProperty("--drag-y");
    try { drag.node.releasePointerCapture(event.pointerId); } catch (_error) { /* already released */ }
    model.drag = null;
    if (cancelled || !victimId) {
      model.helpers.setReadout("", "idle");
      return;
    }
    const actor = byId(drag.actorId);
    const victim = byId(victimId);
    const geometry = dragGeometry();
    if (
      !pointMatchesMonster(drag.startPoint, actor)
      || !pointMatchesMonster(endPoint, victim)
      || finalTravel < geometry.minTravelPx
      || sampleCount < geometry.minSamples
    ) {
      model.helpers.setReadout("", "idle");
      return;
    }
    attemptMeal(drag.actorId, victimId, "creature_drag", {
      start_u: Number(drag.startPoint.u.toFixed(6)),
      start_v: Number(drag.startPoint.v.toFixed(6)),
      end_u: Number(endPoint.u.toFixed(6)),
      end_v: Number(endPoint.v.toFixed(6)),
      travel_px: Number(finalTravel.toFixed(2)),
      sample_count: sampleCount,
    });
  }

  function bindMonsters() {
    document.querySelectorAll(".coa-monster").forEach((button) => {
      if (interaction() === "simplified") {
        button.addEventListener("click", () => chooseMonster(button.dataset.monsterId));
      }
      button.addEventListener("pointerdown", (event) => {
        if (interaction() !== "full" || event.button !== 0 || model.busy || model.terminal || model.drag) return;
        clearFreshFailure();
        event.preventDefault();
        const startPoint = boardPoint(event);
        const actor = byId(button.dataset.monsterId);
        if (!pointMatchesMonster(startPoint, actor)) {
          model.helpers.setReadout("", "idle");
          return;
        }
        model.drag = {
          pointerId: event.pointerId,
          actorId: button.dataset.monsterId,
          node: button,
          startX: event.clientX,
          startY: event.clientY,
          lastX: event.clientX,
          lastY: event.clientY,
          startPoint,
          travel: 0,
          samples: 0,
        };
        button.classList.add("is-dragging");
        try { button.setPointerCapture(event.pointerId); } catch (_error) { /* capture unsupported */ }
      });
      button.addEventListener("pointermove", onPointerMove);
      button.addEventListener("pointerup", (event) => finishPointer(event));
      button.addEventListener("pointercancel", (event) => finishPointer(event, true));
      button.addEventListener("lostpointercapture", (event) => finishPointer(event, true));
    });
  }

  function chooseMonster(monsterId) {
    if (model.busy || model.terminal) return;
    clearFreshFailure();
    if (!model.selectedId) {
      model.selectedId = monsterId;
      updateBoard();
      model.helpers.setReadout("", "idle");
      return;
    }
    if (model.selectedId === monsterId) {
      model.selectedId = null;
      updateBoard();
      model.helpers.setReadout("", "idle");
      return;
    }
    const actorId = model.selectedId;
    model.selectedId = null;
    attemptMeal(actorId, monsterId, "paired_clicks", null);
  }

  function attemptMeal(actorId, victimId, inputSource, gesture) {
    if (model.busy || model.terminal) return;
    clearFreshFailure();
    const actor = byId(actorId);
    const victim = byId(victimId);
    if (!isLegal(actor, victim)) {
      updateBoard();
      model.helpers.setReadout("", "idle");
      return;
    }
    const event = {
      sequence: model.events.length + 1,
      actor_id: actor.id,
      victim_id: victim.id,
      from: [actor.row, actor.column],
      to: [victim.row, victim.column],
      actor_body: actor.body,
      mouth_before: actor.mouth,
      victim_body: victim.body,
      inherited_mouth: victim.mouth,
      input_source: inputSource,
    };
    if (gesture) event.gesture = gesture;
    actor.row = victim.row;
    actor.column = victim.column;
    actor.mouth = victim.mouth;
    model.monsters = ordered(model.monsters.filter((monster) => monster.id !== victim.id));
    const legalAfter = legalMoves();
    event.remaining_after = model.monsters.length;
    event.outcome = model.monsters.length === 1 ? "solved" : legalAfter.length ? "running" : "deadlock";
    model.events.push(event);
    updateBoard();
    model.helpers.setReadout("", "idle");
    if (event.outcome === "solved") return;
    if (event.outcome === "deadlock") {
      model.terminal = true;
      submit(false);
    }
  }

  function resetTray() {
    if (model.busy) return;
    clearFreshFailure();
    model.monsters = clone(model.state.monsters);
    model.events = [];
    model.selectedId = null;
    model.drag = null;
    model.terminal = false;
    model.passed = false;
    document.querySelector(".chain-of-appetite")?.classList.remove("is-pass");
    document.querySelectorAll(".coa-verdict").forEach((node) => node.remove());
    updateBoard();
    model.helpers.setReadout("", "idle");
  }

  function clearFreshFailure() {
    if (!model?.freshFailure) return;
    model.freshFailure = false;
    document.querySelector(".coa-fresh-failure")?.remove();
    model.helpers.setReadout("", "idle");
  }

  async function submit(completed) {
    if (!model || model.busy || model.passed) return;
    const current = model;
    current.busy = true;
    document.querySelectorAll(".chain-of-appetite button").forEach((button) => { button.disabled = true; });
    current.helpers.setReadout("", "pending");
    const payload = {
      mechanic_id: current.state.mechanic_id,
      task_id: current.state.task_id,
      challenge_id: current.state.challenge_id,
      interaction_mode: interaction(),
      events: clone(current.events),
      final_monsters: clone(ordered(current.monsters)),
      remaining: current.monsters.length,
      completed: completed === true,
    };
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify(payload),
      });
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.busy = false;
        current.passed = true;
        current.terminal = true;
        document.querySelector(".chain-of-appetite")?.classList.add("is-pass");
        document.querySelector(".coa-verdict-layer")?.insertAdjacentHTML("beforeend", '<div class="coa-verdict coa-verdict-pass"><strong>PASS</strong></div>');
        current.helpers.setReadout("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        const helpers = current.helpers;
        await render(outcome.state, helpers, {freshFailure: true});
        model.helpers.setReadout("FAIL", "error");
      } else if (model === current) {
        current.busy = false;
        current.terminal = false;
        document.querySelectorAll(".chain-of-appetite button").forEach((button) => { button.disabled = false; });
        current.helpers.setReadout("FAIL", "error");
      }
    } catch (_error) {
      if (model === current) {
        current.busy = false;
        current.terminal = false;
        document.querySelectorAll(".chain-of-appetite button").forEach((button) => { button.disabled = false; });
        current.helpers.setReadout("FAIL", "error");
      }
    }
  }

  async function render(state, helpers, options = {}) {
    document.body.dataset.mechanic = "chain-of-appetite";
    document.body.dataset.appetitePalette = String(state.palette || "midnight-canteen");
    model = {
      state,
      helpers,
      monsters: clone(state.monsters),
      events: [],
      selectedId: null,
      drag: null,
      busy: false,
      terminal: false,
      passed: false,
      freshFailure: Boolean(options.freshFailure),
    };
    const mode = interaction();
    helpers.app.innerHTML = `<section class="chain-of-appetite mode-${esc(mode)}" data-interaction="${esc(mode)}" data-challenge-id="${esc(state.challenge_id)}">
      <header class="coa-masthead">
        <div class="coa-orbit-mark" aria-hidden="true"><i></i><b>COA</b></div>
        <div class="coa-title"><small>PLANETARY CANTEEN</small><h1>${esc(state.prompt)}</h1></div>
        <div class="coa-stars" aria-hidden="true"><i></i><i></i><i></i></div>
      </header>
      <main class="coa-stage">
        <section class="coa-tray-wrap">
          <div class="coa-tray-head"><span>APPETITE ARRAY</span><i aria-hidden="true"></i></div>
          <div class="coa-board" id="coa-board" style="--coa-grid:${Number(state.grid_size)};--coa-target-diameter:${Number(state.interaction_geometry?.drag_target_radius_cells) * 200}%"></div>
        </section>
      </main>
      <footer class="coa-footer">
        <button type="button" id="coa-reset">↺ RESET</button>
        <div class="readout" data-status="${options.freshFailure ? "error" : "idle"}">${options.freshFailure ? "FAIL" : ""}</div>
        <button type="button" id="coa-certify">SEAL</button>
      </footer>
      <div class="coa-verdict-layer">${options.freshFailure ? '<div class="coa-verdict coa-verdict-fail coa-fresh-failure"><strong>FAIL</strong></div>' : ""}</div>
      ${helpers.cheatPanelTemplate()}
    </section>`;
    updateBoard();
    document.getElementById("coa-reset")?.addEventListener("click", resetTray);
    document.getElementById("coa-certify")?.addEventListener("click", () => submit(model.monsters.length === 1));
    helpers.installCheatPanel();
    window.chainOfAppetiteModel = model;
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.chain_of_appetite = {rootSelector: ".chain-of-appetite", render};
})();
