(() => {
  "use strict";

  const DELTAS = {
    UP: [0, 1],
    RIGHT: [1, 0],
    DOWN: [0, -1],
    LEFT: [-1, 0],
  };
  const KEYS = {UP: "ArrowUp", RIGHT: "ArrowRight", DOWN: "ArrowDown", LEFT: "ArrowLeft"};
  let helpersCache = null;
  let keyHandler = null;
  let model = null;

  function pointKey(face, floor, x) {
    return `${Number(face)},${Number(floor)},${Number(x)}`;
  }

  function clonePoint(point) {
    return [Number(point[0]), Number(point[1]), Number(point[2])];
  }

  function positionKey(position) {
    return pointKey(position[0], position[1], position[2]);
  }

  function currentFloor(face, floor) {
    return model.state.tower.faces[face]?.floors[floor] || {walls: [], ladders: [], fires: []};
  }

  function hasValue(values, value) {
    return (values || []).some((item) => Number(item) === Number(value));
  }

  function fireAt(position) {
    const floor = currentFloor(position[0], position[1]);
    return (floor.fires || []).find((fire) =>
      Number(fire.x) === Number(position[2])
      || (Array.isArray(fire.cells) && fire.cells.some((x) => Number(x) === Number(position[2])))
    ) || null;
  }

  function fireIsCleared(fire) {
    return Boolean(fire && model.clearedFires.has(String(fire.id)));
  }

  function wallAt(position) {
    return hasValue(currentFloor(position[0], position[1]).walls, position[2]);
  }

  function targetFor(position, direction) {
    const width = Number(model.state.tower.floor_width);
    const [dx, dy] = DELTAS[direction];
    let face = Number(position[0]);
    let floor = Number(position[1]) + dy;
    let x = Number(position[2]) + dx;
    if (direction === "RIGHT" && position[2] === width - 1) {
      face = 1 - face;
      x = 0;
    } else if (direction === "LEFT" && position[2] === 0) {
      face = 1 - face;
      x = width - 1;
    }
    return [face, floor, x];
  }

  function ladderAllows(position, target, direction) {
    const ladderFloor = direction === "UP" ? position[1] : target[1];
    if (ladderFloor < 0 || ladderFloor >= Number(model.state.tower.floor_count) - 1) return false;
    return hasValue(currentFloor(position[0], ladderFloor).ladders, position[2]);
  }

  function snapshot() {
    return {
      player: clonePoint(model.player),
      facing: model.facing,
      cleared_fires: Array.from(model.clearedFires).sort(),
      extinguishers_left: Number(model.extinguishersLeft),
      inspection_face: Number(model.inspectionFace),
    };
  }

  function renderMap() {
    const map = document.getElementById("firewatch-map");
    if (!map) return;
    const tower = model.state.tower;
    map.style.setProperty("--firewatch-cols", String(Number(tower.floor_width || 9)));
    const face = Number(model.inspectionFace);
    const faceData = tower.faces[face];
    const floors = [];
    for (let floorIndex = Number(tower.floor_count) - 1; floorIndex >= 0; floorIndex -= 1) {
      const floor = faceData.floors[floorIndex] || {};
      const cells = [];
      for (let x = 0; x < Number(tower.floor_width); x += 1) {
        const cell = [face, floorIndex, x];
        const key = positionKey(cell);
        const wall = hasValue(floor.walls, x);
        const ladder = hasValue(floor.ladders, x);
        const fire = (floor.fires || []).find((item) =>
          Number(item.x) === x
          || (Array.isArray(item.cells) && item.cells.some((cell) => Number(cell) === x))
        ) || null;
        const cleared = fireIsCleared(fire);
        const player = model.player[0] === face && model.player[1] === floorIndex && model.player[2] === x;
        const resident = tower.resident[0] === face && tower.resident[1] === floorIndex && tower.resident[2] === x;
        const classes = ["firewatch-cell"];
        if (wall) classes.push("is-wall");
        if (ladder && !wall) classes.push("has-ladder");
        if (fire && !cleared && !wall) classes.push("has-fire");
        if (fire && cleared) classes.push("is-cleared");
        if (player) classes.push("has-firefighter");
        if (resident) classes.push("has-resident");
        cells.push(`<div class="${classes.join(" ")}" data-face="${face}" data-floor="${floorIndex}" data-x="${x}">
          <span class="firewatch-cell-number">${x + 1}</span>
          ${wall ? '<span class="firewatch-wall-mark">▦</span>' : ""}
          ${ladder && !wall ? '<span class="firewatch-ladder-mark">╫</span>' : ""}
          ${fire && !cleared && !wall ? '<span class="firewatch-fire-mark">✹</span>' : ""}
          ${fire && cleared ? '<span class="firewatch-ash-mark">✦</span>' : ""}
          ${resident ? '<span class="firewatch-resident-mark">♙</span>' : ""}
          ${player ? '<span class="firewatch-firefighter-mark">✚</span>' : ""}
        </div>`);
      }
      floors.push(`<section class="firewatch-floor" data-floor="${floorIndex}">
        <header><span>F${String(floorIndex + 1).padStart(2, "0")}</span><i>${floorIndex === Number(tower.floor_count) - 1 ? "ROOF" : floorIndex === 0 ? "GROUND" : "SERVICE LEVEL"}</i></header>
        <div class="firewatch-floor-cells">${cells.join("")}</div>
      </section>`);
    }
    map.dataset.inspectionFace = String(face);
    map.innerHTML = floors.join("");
  }

  function renderHud() {
    const position = document.getElementById("firewatch-position");
    const facing = document.getElementById("firewatch-facing");
    const stock = document.getElementById("firewatch-stock");
    const inspected = document.getElementById("firewatch-inspected-face");
    const inspectButton = document.getElementById("firewatch-inspect");
    const cert = document.getElementById("firewatch-certify");
    if (position) position.textContent = `F${String(model.player[1] + 1).padStart(2, "0")} · ${model.state.tower.faces[model.player[0]].label}`;
    if (facing) facing.textContent = `${model.facing} ${({UP: "↑", RIGHT: "→", DOWN: "↓", LEFT: "←"})[model.facing]}`;
    if (stock) {
      stock.textContent = `${model.extinguishersLeft} / ${model.state.extinguisher_count}`;
      stock.dataset.empty = model.extinguishersLeft === 0 ? "true" : "false";
    }
    if (inspected) inspected.textContent = model.state.tower.faces[model.inspectionFace].label;
    const inspectedDuplicate = document.getElementById("firewatch-inspected-face-duplicate");
    if (inspectedDuplicate) inspectedDuplicate.textContent = model.state.tower.faces[model.inspectionFace].label;
    if (inspectButton) inspectButton.textContent = `◉ INSPECT ${model.state.tower.faces[1 - model.player[0]].label}`;
    const reached = model.player[0] === model.state.tower.resident[0] && model.player[1] === model.state.tower.resident[1] && model.player[2] === model.state.tower.resident[2];
    if (cert) cert.classList.toggle("is-ready", reached);
  }

  function renderAll() {
    renderMap();
    renderHud();
  }

  function addEvent(action, inputSource, before, outcome, extra = {}) {
    const event = {
      sequence: model.events.length + 1,
      action,
      input_source: inputSource,
      before,
      after: snapshot(),
      outcome,
      ...extra,
    };
    model.events.push(event);
    renderAll();
    helpersCache.setReadout("ACTION RECORDED", "idle");
  }

  function recordMove(direction, inputSource) {
    if (!model || model.submitting || model.terminal || !DELTAS[direction]) return;
    const before = snapshot();
    model.facing = direction;
    const target = targetFor(model.player, direction);
    let outcome;
    if (wallAt(target)) {
      outcome = "blocked_wall";
    } else if (fireAt(target) && !fireIsCleared(fireAt(target))) {
      outcome = "blocked_fire";
    } else if (direction === "UP" || direction === "DOWN") {
      if (!ladderAllows(model.player, target, direction) || target[1] < 0 || target[1] >= Number(model.state.tower.floor_count)) {
        outcome = "blocked_ladder";
      } else {
        model.player = target;
        outcome = "climbed";
      }
    } else {
      model.player = target;
      outcome = target[0] !== before.player[0] ? "seam_crossed" : "walked";
    }
    addEvent("MOVE", inputSource, before, outcome, {direction});
  }

  function recordExtinguish(inputSource) {
    if (!model || model.submitting || model.terminal) return;
    const before = snapshot();
    const target = targetFor(model.player, model.facing);
    const fire = fireAt(target);
    let outcome;
    if (!fire || fireIsCleared(fire)) {
      outcome = "no_fire";
    } else if (model.extinguishersLeft <= 0) {
      outcome = "stock_empty";
    } else {
      model.clearedFires.add(String(fire.id));
      model.extinguishersLeft -= 1;
      outcome = "extinguished";
    }
    addEvent("EXTINGUISH", inputSource, before, outcome, {direction: model.facing});
  }

  function inspectOtherFace() {
    if (!model || model.submitting || model.terminal) return;
    const before = snapshot();
    model.inspectionFace = 1 - model.player[0];
    addEvent("INSPECT", "eye_button", before, "inspected", {face: model.inspectionFace});
  }

  async function certify() {
    if (!model || model.submitting || model.terminal) return;
    model.submitting = true;
    const button = document.getElementById("firewatch-certify");
    if (button) button.disabled = true;
    helpersCache.setReadout("REPLAYING RESCUE LEDGER…", "idle");
    const resident = model.state.tower.resident;
    const completed = model.player[0] === resident[0] && model.player[1] === resident[1] && model.player[2] === resident[2];
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      actions: model.events,
      final_state: snapshot(),
      extinguishers_used: Number(model.state.extinguisher_count) - Number(model.extinguishersLeft),
      completed,
      certify_input_source: "certify_button",
    };
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (result.passed === true) {
        model.terminal = true;
        document.querySelector(".firewatch-captcha")?.classList.add("is-pass");
        const verdict = document.getElementById("firewatch-verdict");
        if (verdict) verdict.innerHTML = "<b>PASS</b><span>RESIDENT REACHED</span>";
        helpersCache.setReadout("PASS · RESCUE VERIFIED", "passed");
      } else if (result.passed === false) {
        if (result.state) await helpersCache.render(result.state);
        helpersCache.setReadout("FAIL · FRESH TOWER ISSUED", "error");
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
    if (!helpersCache) throw new Error("firewatch_fold requires runtime helpers");
    if (keyHandler) window.removeEventListener("keydown", keyHandler);
    const tower = state.tower || {};
    const interaction = state.control_condition?.interaction || state.interaction || "full";
    model = {
      state,
      interaction,
      player: clonePoint(tower.start || [0, 0, 0]),
      facing: "RIGHT",
      inspectionFace: Number((tower.start || [0])[0]),
      clearedFires: new Set(),
      extinguishersLeft: Number(state.extinguisher_count || 0),
      events: [],
      submitting: false,
      terminal: false,
    };
    window.firewatchFoldModel = model;
    document.body.dataset.mechanic = "firewatch-fold";
    document.body.dataset.firewatchPalette = String(tower.palette || 0);
    const controls = interaction === "simplified" ? `<div class="firewatch-direction-pad" aria-label="firefighter direction controls">
      <button type="button" data-move="UP" aria-label="move up">↑<small>UP</small></button>
      <button type="button" data-move="LEFT" aria-label="move left">←<small>LEFT</small></button>
      <button type="button" data-move="DOWN" aria-label="move down">↓<small>DOWN</small></button>
      <button type="button" data-move="RIGHT" aria-label="move right">→<small>RIGHT</small></button>
    </div><button class="firewatch-extinguish" id="firewatch-extinguish" type="button"><span>EXTINGUISH AHEAD</span></button>` : `<div class="firewatch-key-guide"><b>ARROWS / WASD</b><span>KEYBOARD MOVEMENT</span><b>SHIFT</b><span>EXTINGUISH AHEAD</span></div>`;
    helpersCache.app.innerHTML = `<section class="firewatch-captcha" data-interaction="${helpersCache.text(interaction)}" data-challenge-id="${helpersCache.text(state.challenge_id)}" tabindex="0">
      <header class="firewatch-header"><div><span class="firewatch-kicker">EMERGENCY ARCHIVE / TOWER ${helpersCache.text(state.challenge_id).toUpperCase()}</span><h1>FIREWATCH <i>FOLD</i></h1><p>${helpersCache.text(state.prompt)}</p></div><div class="firewatch-stamp"><span>RESCUE LEDGER</span><b>OPEN</b></div></header>
      <main class="firewatch-workspace"><section class="firewatch-map-shell"><div class="firewatch-map-top"><div><span class="firewatch-section-label">VISIBLE ELEVATION</span><h2 id="firewatch-inspected-face">${helpersCache.text(tower.faces?.[0]?.label || "NORTH FACE")}</h2></div><div class="firewatch-map-state"><span>PLAYER</span><b id="firewatch-position">F01 · NORTH FACE</b><span>VIEW</span><b id="firewatch-inspected-face-duplicate">—</b></div></div><div class="firewatch-map" id="firewatch-map" aria-label="tower face map"></div><div class="firewatch-map-legend"><span><i class="legend-fire">✹</i> ACTIVE FIRE</span><span><i class="legend-ladder">╫</i> LADDER</span><span><i class="legend-resident">♙</i> RESIDENT</span><span><i class="legend-cross">✚</i> FIREFIGHTER</span></div><div class="firewatch-verdict" id="firewatch-verdict"><b>LIVE</b><span>MAP REPLAY ARMED</span></div></section>
        <aside class="firewatch-console"><div class="firewatch-console-head"><span>FIELD CONSOLE</span><i>SECTOR ${helpersCache.text(state.challenge_id).slice(0, 4).toUpperCase()}</i></div><section class="firewatch-inventory"><label>EXTINGUISHER STOCK</label><div><b id="firewatch-stock">${Number(state.extinguisher_count || 0)} / ${Number(state.extinguisher_count || 0)}</b><span>ONE-USE CANISTERS</span></div></section><section class="firewatch-facing"><label>FACING</label><b id="firewatch-facing">RIGHT →</b></section><button class="firewatch-inspect" id="firewatch-inspect" type="button">◉ INSPECT OTHER FACE</button>${controls}</aside></main>
      <footer class="firewatch-footer"><div><span id="firewatch-manifest-state">ROUTE UNCONFIRMED</span><div class="readout" data-status="idle">READY</div></div><button class="firewatch-certify" id="firewatch-certify" type="button">${helpersCache.text(state.submit_label || "CERTIFY RESCUE")} →</button></footer>
    </section>`;
    const duplicate = document.getElementById("firewatch-inspected-face-duplicate");
    if (duplicate) duplicate.textContent = tower.faces?.[0]?.label || "NORTH FACE";
    document.querySelectorAll("[data-move]").forEach((button) => button.addEventListener("click", () => recordMove(button.dataset.move, "control_buttons")));
    document.getElementById("firewatch-extinguish")?.addEventListener("click", () => recordExtinguish("extinguish_button"));
    document.getElementById("firewatch-inspect")?.addEventListener("click", inspectOtherFace);
    document.getElementById("firewatch-certify")?.addEventListener("click", certify);
    keyHandler = (event) => {
      if (event.repeat || model?.submitting || model?.terminal || model?.interaction !== "full") return;
      const key = String(event.key || "");
      const lower = key.toLowerCase();
      const direction = {ArrowUp: "UP", ArrowRight: "RIGHT", ArrowDown: "DOWN", ArrowLeft: "LEFT", w: "UP", d: "RIGHT", s: "DOWN", a: "LEFT"}[key] || {w: "UP", d: "RIGHT", s: "DOWN", a: "LEFT"}[lower];
      if (direction) {
        event.preventDefault();
        recordMove(direction, "keyboard");
      } else if (key === "Shift") {
        event.preventDefault();
        recordExtinguish("keyboard");
      }
    };
    window.addEventListener("keydown", keyHandler);
    renderAll();
    document.querySelector(".firewatch-captcha")?.focus();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.firewatch_fold = {
    rootSelector: ".firewatch-captcha",
    render,
  };
})();
