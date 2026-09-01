(() => {
  "use strict";

  const DIRECTIONS = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];
  const DIRECTION_NAMES = ["E", "NE", "NW", "W", "SW", "SE"];
  const DRIVER_RADIUS = 0.68;
  const DRIVER_TOLERANCE = 0.3;
  const model = {
    state: null,
    helpers: null,
    cells: [],
    cellSet: new Set(),
    geometry: new Map(),
    blocked: new Set(),
    initialFences: new Set(),
    playerFences: [],
    fox: [0, 0],
    events: [],
    turns: 0,
    interaction: "simplified",
    busy: false,
    terminal: "active",
    ready: false,
    pointerDrag: null,
    activeAction: null,
  };

  const key = (coord) => `${coord[0]},${coord[1]}`;
  const coordFromKey = (value) => value.split(",").map(Number);
  const same = (first, second) => first[0] === second[0] && first[1] === second[1];
  const clean = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

  function isEdge(coord) {
    const [q, r] = coord;
    return Math.max(Math.abs(q), Math.abs(r), Math.abs(-q - r)) === Number(model.state.radius);
  }

  function neighbors(coord) {
    return DIRECTIONS.map(([dq, dr]) => [coord[0] + dq, coord[1] + dr])
      .filter((candidate) => model.cellSet.has(key(candidate)));
  }

  function distanceMap(blocked) {
    const distances = new Map();
    const queue = [];
    model.cells.forEach((cell) => {
      if (isEdge(cell) && !blocked.has(key(cell))) {
        distances.set(key(cell), 0);
        queue.push(cell);
      }
    });
    let cursor = 0;
    while (cursor < queue.length) {
      const current = queue[cursor++];
      const currentDistance = distances.get(key(current));
      neighbors(current).forEach((neighbor) => {
        const neighborKey = key(neighbor);
        if (blocked.has(neighborKey) || distances.has(neighborKey)) return;
        distances.set(neighborKey, currentDistance + 1);
        queue.push(neighbor);
      });
    }
    return distances;
  }

  function windStartForTurn(turn = model.turns) {
    const sequence = model.state.runtime_wind_sequence || [model.state.wind_start || 0];
    return Number(sequence[Math.min(turn, sequence.length - 1)] || 0);
  }

  function windOrder(start = windStartForTurn()) {
    return Array.from({length: DIRECTIONS.length}, (_unused, index) => (
      DIRECTION_NAMES[(start + index) % DIRECTIONS.length]
    ));
  }

  function driverPatternForTurn(turn = model.turns) {
    const patterns = model.state.runtime_driver_patterns || [];
    return (patterns[Math.min(turn, patterns.length - 1)] || [0, 4]).map(Number);
  }

  function driverCheckpoint(angleIndex) {
    const angle = Number(angleIndex) * Math.PI / 6 - Math.PI / 2;
    return [Math.cos(angle) * DRIVER_RADIUS, Math.sin(angle) * DRIVER_RADIUS];
  }

  function foxChoice(fox, blocked, windStart) {
    const distances = distanceMap(blocked);
    if (!distances.has(key(fox))) return {outcome: "trapped", fox: [...fox], distance: null};
    const start = Number(windStart || 0);
    const ordered = [...DIRECTIONS.slice(start), ...DIRECTIONS.slice(0, start)];
    const windRanks = new Map(ordered.map((direction, index) => [key(direction), index]));
    const options = neighbors(fox).filter((neighbor) => !blocked.has(key(neighbor)) && distances.has(key(neighbor)))
      .map((neighbor) => {
        const onward = neighbors(neighbor).filter((candidate) => (
          !blocked.has(key(candidate))
          && distances.has(key(candidate))
          && distances.get(key(candidate)) === distances.get(key(neighbor)) - 1
        )).length;
        const degree = neighbors(neighbor).filter((candidate) => !blocked.has(key(candidate))).length;
        const direction = [neighbor[0] - fox[0], neighbor[1] - fox[1]];
        return {neighbor, distance: distances.get(key(neighbor)), onward, degree, wind: windRanks.get(key(direction))};
      });
    if (!options.length) return {outcome: "trapped", fox: [...fox], distance: null};
    options.sort((first, second) => (
      first.distance - second.distance
      || first.wind - second.wind
      || second.onward - first.onward
      || second.degree - first.degree
    ));
    const destination = options[0].neighbor;
    return {outcome: isEdge(destination) ? "escaped" : "moved", fox: [...destination], distance: options[0].distance};
  }

  function buildGeometry() {
    const size = Number(model.state.radius) === 4 ? 33 : 38;
    const raw = model.cells.map(([q, r]) => ({
      coord: [q, r],
      x: Math.sqrt(3) * size * (q + r / 2),
      y: 1.5 * size * r,
    }));
    const minX = Math.min(...raw.map((item) => item.x)) - size - 5;
    const maxX = Math.max(...raw.map((item) => item.x)) + size + 5;
    const minY = Math.min(...raw.map((item) => item.y)) - size - 5;
    const maxY = Math.max(...raw.map((item) => item.y)) + size + 5;
    model.geometry = new Map(raw.map((item) => [key(item.coord), {
      x: item.x - minX,
      y: item.y - minY,
      size,
    }]));
    return {width: maxX - minX, height: maxY - minY, size};
  }

  function fenceMarkup(initial) {
    return `<span class="fox-fence-piece ${initial ? "is-bramble" : "is-stake"}" aria-hidden="true">
      <i></i><i></i><b></b><em></em>
    </span>`;
  }

  function cellsMarkup() {
    return model.cells.map((coord) => {
      const cellKey = key(coord);
      const geometry = model.geometry.get(cellKey);
      const initial = model.initialFences.has(cellKey);
      const player = model.playerFences.some((item) => same(item, coord));
      const blocked = initial || player;
      const classes = ["fox-cell", isEdge(coord) ? "is-rim" : "", initial ? "is-initial-fence" : "", player ? "is-player-fence" : ""]
        .filter(Boolean).join(" ");
      const label = blocked ? `${initial ? "Bramble" : "Stake"} at hex ${coord[0]}, ${coord[1]}` : `Open hex ${coord[0]}, ${coord[1]}`;
      return `<button type="button" class="${classes}" data-cell-key="${cellKey}" data-q="${coord[0]}" data-r="${coord[1]}"
        style="--cell-x:${geometry.x}px;--cell-y:${geometry.y}px;--cell-size:${geometry.size}px" aria-label="${clean(label)}" ${blocked ? "disabled" : ""}>
        <span class="fox-cell-ground"></span>${blocked ? fenceMarkup(initial) : ""}
      </button>`;
    }).join("");
  }

  function foxMarkup() {
    return `<div class="fox-runner" id="fox-runner" aria-label="fox">
      <svg viewBox="0 0 104 92" role="img" aria-label="Stylized orange fox">
        <path class="fox-tail-tip" d="M78 69 C105 58 102 32 87 29 C94 45 86 51 68 52 Z"/>
        <path class="fox-tail" d="M62 73 C91 80 105 63 96 43 C91 57 80 58 63 50 Z"/>
        <path class="fox-body" d="M29 50 C36 38 59 35 73 49 L70 72 C58 79 38 76 27 66 Z"/>
        <path class="fox-ear" d="M29 45 L25 15 L43 34 Z"/><path class="fox-ear" d="M53 35 L68 13 L64 49 Z"/>
        <path class="fox-face" d="M26 37 C36 28 58 30 67 42 L57 62 L39 65 L24 54 Z"/>
        <path class="fox-cheek" d="M27 46 L44 55 L37 65 L24 55 Z"/><path class="fox-cheek" d="M65 45 L50 56 L57 63 L70 51 Z"/>
        <circle class="fox-eye" cx="38" cy="44" r="2.7"/><circle class="fox-eye" cx="56" cy="43" r="2.7"/>
        <path class="fox-nose" d="M45 58 L51 57 L48 62 Z"/>
        <path class="fox-leg" d="M35 67 L36 82 L45 82 L47 69 Z"/><path class="fox-leg" d="M58 68 L61 82 L70 82 L69 66 Z"/>
      </svg>
    </div>`;
  }

  function positionFox(animate = false) {
    const runner = document.getElementById("fox-runner");
    const geometry = model.geometry.get(key(model.fox));
    if (!runner || !geometry) return;
    runner.classList.toggle("is-moving", animate);
    runner.style.left = `${geometry.x + geometry.size}px`;
    runner.style.top = `${geometry.y + geometry.size}px`;
    if (animate) window.setTimeout(() => runner.classList.remove("is-moving"), 330);
  }

  function updatePanels() {
    const stakesLeft = Math.max(0, Number(model.state.stake_budget) - model.turns);
    const stakeNode = document.getElementById("fox-stakes-left");
    const turnNode = document.getElementById("fox-turn-count");
    const token = document.getElementById("fox-stake-token");
    const certify = document.getElementById("fox-certify");
    const vane = document.getElementById("fox-vane-order");
    if (stakeNode) stakeNode.textContent = String(stakesLeft).padStart(2, "0");
    if (turnNode) turnNode.textContent = String(model.turns).padStart(2, "0");
    if (token) token.classList.toggle("is-empty", stakesLeft === 0 || model.terminal !== "active");
    if (certify) certify.disabled = model.busy || model.terminal === "escaped" || model.terminal === "exhausted";
    if (vane) vane.textContent = windOrder().join(" › ");
  }

  function clearFreshFailure() {
    document.querySelector(".fox-verdict.is-fail")?.remove();
    document.querySelector(".fence-fox-captcha")?.classList.remove("is-fresh-fail");
  }

  function flash(message, status = "idle") {
    model.helpers.setReadout(message, status);
    const readout = document.querySelector(".fox-readout");
    readout?.classList.remove("is-flash");
    void readout?.offsetWidth;
    readout?.classList.add("is-flash");
  }

  function addPlayerFence(coord) {
    const cellKey = key(coord);
    model.blocked.add(cellKey);
    model.playerFences.push([...coord]);
    const cell = document.querySelector(`.fox-cell[data-cell-key="${CSS.escape(cellKey)}"]`);
    if (cell) {
      cell.disabled = true;
      cell.classList.add("is-player-fence");
      cell.setAttribute("aria-label", `Stake at hex ${coord[0]}, ${coord[1]}`);
      cell.insertAdjacentHTML("beforeend", fenceMarkup(false));
    }
  }

  function settleAction(action) {
    action?.settle();
    if (model.activeAction === action) model.activeAction = null;
  }

  async function submit(completed) {
    if (!model.state || model.busy) return;
    model.busy = true;
    updatePanels();
    flash("RANGER REVIEW IN PROGRESS…", "pending");
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      events: model.events,
      final_fox: [...model.fox],
      player_fences: model.playerFences.map((coord) => [...coord]),
      turns: model.turns,
      terminal_outcome: model.terminal,
      completed,
    };
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify(payload),
      });
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = "trapped";
        document.querySelector(".fence-fox-captcha")?.classList.add("is-pass");
        document.querySelector(".fence-fox-captcha")?.insertAdjacentHTML("beforeend", '<div class="fox-verdict is-pass"><small>PERIMETER SECURE</small><strong>PASS</strong></div>');
        model.helpers.setReadout("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        const shell = document.querySelector(".fence-fox-captcha");
        shell?.classList.add("is-fresh-fail");
        shell?.insertAdjacentHTML("beforeend", '<div class="fox-verdict is-fail"><small>RUN CLOSED · FRESH FIELD ISSUED</small><strong>FAIL</strong></div>');
        model.helpers.setReadout("FAIL · FRESH FIELD", "error");
      } else {
        model.busy = false;
        updatePanels();
        flash("FAIL · FIELD REPORT UNGRADED", "error");
      }
    } catch (_error) {
      model.busy = false;
      updatePanels();
      flash("FAIL · WATCHTOWER OFFLINE", "error");
    }
  }

  function finishTurn(placement, inputSource, gesture, foxFrom, windStart, reply, action) {
    model.fox = [...reply.fox];
    if (reply.outcome !== "trapped") positionFox(true);
    const event = {
      sequence: model.events.length + 1,
      placed: [...placement],
      fox_from: [...foxFrom],
      fox_to: reply.outcome === "trapped" ? null : [...reply.fox],
      outcome: reply.outcome,
      distance_after: reply.distance,
      wind_start: windStart,
      input_source: inputSource,
    };
    if (gesture) event.gesture = gesture;
    model.events.push(event);
    model.busy = false;
    if (reply.outcome === "trapped") {
      model.terminal = "trapped";
      model.ready = true;
      document.querySelector(".fence-fox-captcha")?.classList.add("is-trapped");
      flash("FOX ENCLOSED · CHECK THE PERIMETER", "passed");
      settleAction(action);
    } else if (reply.outcome === "escaped") {
      model.terminal = "escaped";
      document.querySelector(".fence-fox-captcha")?.classList.add("is-escaped");
      document.querySelector(".fence-fox-captcha")?.insertAdjacentHTML("beforeend", '<div class="fox-local-terminal"><small>THE RIM WAS OPEN</small><strong>ESCAPED</strong></div>');
      flash("FOX REACHED THE RIM", "error");
      window.setTimeout(async () => {
        await submit(false);
        settleAction(action);
      }, 620);
    } else if (model.turns >= Number(model.state.stake_budget)) {
      model.terminal = "exhausted";
      document.querySelector(".fence-fox-captcha")?.insertAdjacentHTML("beforeend", '<div class="fox-local-terminal"><small>SUPPLY CRATE EMPTY</small><strong>OUT OF STAKES</strong></div>');
      flash("NO STAKES LEFT · ROUTE STILL OPEN", "error");
      window.setTimeout(async () => {
        await submit(false);
        settleAction(action);
      }, 620);
    } else {
      flash(`FOX MOVED · NEW WIND ${windOrder().join(" › ")} · ${Number(model.state.stake_budget) - model.turns} STAKE${Number(model.state.stake_budget) - model.turns === 1 ? "" : "S"} LEFT`, "idle");
      settleAction(action);
    }
    updatePanels();
  }

  function placeFence(coord, inputSource, gesture = null, action = null) {
    if (model.busy || model.terminal !== "active") {
      settleAction(action);
      return false;
    }
    clearFreshFailure();
    const cellKey = key(coord);
    if (!model.cellSet.has(cellKey) || model.blocked.has(cellKey) || same(coord, model.fox)) {
      flash(same(coord, model.fox) ? "THE FOX OCCUPIES THAT HEX" : "THAT HEX IS ALREADY CLOSED", "error");
      settleAction(action);
      return false;
    }
    if (model.turns >= Number(model.state.stake_budget)) {
      settleAction(action);
      return false;
    }
    model.activeAction = action;
    model.busy = true;
    const foxFrom = [...model.fox];
    const windStart = windStartForTurn();
    addPlayerFence(coord);
    model.turns += 1;
    updatePanels();
    flash("STAKE SET · FOX CHOOSING A ROUTE…", "pending");
    const reply = foxChoice(model.fox, model.blocked, windStart);
    window.setTimeout(
      () => finishTurn(coord, inputSource, gesture, foxFrom, windStart, reply, action),
      16,
    );
    return true;
  }

  function bindSimplifiedCells() {
    document.querySelectorAll(".fox-cell:not(:disabled)").forEach((cell) => {
      cell.addEventListener("click", () => {
        if (model.interaction !== "simplified") return;
        const action = model.helpers.beginAction?.("fence-the-fox-cell") || null;
        placeFence([Number(cell.dataset.q), Number(cell.dataset.r)], "cell_click", null, action);
      });
    });
  }

  function resetDraggedToken() {
    const token = document.getElementById("fox-stake-token");
    token?.classList.remove("is-dragging", "is-driver-armed");
    token?.style.removeProperty("--drag-x");
    token?.style.removeProperty("--drag-y");
  }

  function clearDriverTrack() {
    document.getElementById("fox-driver-track")?.remove();
  }

  function showDriverTrack(coord, pattern) {
    clearDriverTrack();
    const geometry = model.geometry.get(key(coord));
    const field = document.getElementById("fox-field");
    if (!geometry || !field) return;
    const markers = pattern.map((angleIndex, index) => {
      const [dx, dy] = driverCheckpoint(angleIndex);
      return `<span class="fox-driver-checkpoint${index === 0 ? " is-current" : ""}" data-driver-sequence="${index}"
        style="--driver-x:${dx * geometry.size}px;--driver-y:${dy * geometry.size}px">${index + 1}</span>`;
    }).join("");
    field.insertAdjacentHTML("beforeend", `<div class="fox-driver-track" id="fox-driver-track"
      style="left:${geometry.x + geometry.size}px;top:${geometry.y + geometry.size}px">
      <strong class="fox-driver-instruction">STEP 1 OF 2</strong>
      <i class="fox-driver-ring"></i>${markers}<b class="fox-driver-center">SET</b>
    </div>`);
  }

  function updateDriverTrack(drag) {
    document.querySelectorAll(".fox-driver-checkpoint").forEach((marker) => {
      const sequence = Number(marker.dataset.driverSequence);
      marker.classList.toggle("is-complete", sequence < drag.driverProgress);
      marker.classList.toggle("is-current", sequence === drag.driverProgress);
    });
    document.querySelector(".fox-driver-center")?.classList.toggle(
      "is-current",
      drag.driverProgress >= drag.pattern.length,
    );
    document.querySelector(".fox-driver-center")?.classList.toggle("is-ready", drag.driverReady);
    const instruction = document.querySelector(".fox-driver-instruction");
    if (instruction) {
      instruction.textContent = drag.driverReady
        ? "RELEASE STAKE"
        : drag.driverProgress >= drag.pattern.length
          ? "RETURN TO CENTER"
          : `STEP ${drag.driverProgress + 1} OF ${drag.pattern.length}`;
    }
  }

  function normalizedPointer(cell, event) {
    const bounds = cell.getBoundingClientRect();
    const radius = Math.max(1, bounds.width / 2);
    return [
      (event.clientX - (bounds.left + bounds.width / 2)) / radius,
      (event.clientY - (bounds.top + bounds.height / 2)) / radius,
    ];
  }

  function armDriver(drag, cell) {
    if (model.pointerDrag !== drag || drag.armedCell || model.busy) return;
    const coord = [Number(cell.dataset.q), Number(cell.dataset.r)];
    const cellKey = key(coord);
    if (cell.disabled || model.blocked.has(cellKey) || same(coord, model.fox)) return;
    drag.armedCell = cell;
    drag.coord = coord;
    drag.pattern = driverPatternForTurn();
    drag.driverPath = [[0, 0]];
    drag.driverProgress = 0;
    drag.driverReady = false;
    document.getElementById("fox-stake-token")?.classList.add("is-driver-armed");
    showDriverTrack(coord, drag.pattern);
    flash("DRIVER KEY REVEALED · FOLLOW 1 → 2 → CENTER, THEN RELEASE", "pending");
  }

  function bindStakeDrag() {
    const token = document.getElementById("fox-stake-token");
    if (!token || model.interaction !== "full") return;
    token.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || model.busy || model.terminal !== "active" || model.pointerDrag) return;
      event.preventDefault();
      model.pointerDrag = {
        pointerId: event.pointerId,
        start: [event.clientX, event.clientY],
        last: [event.clientX, event.clientY],
        travel: 0,
        samples: 0,
        hoverCandidateKey: null,
        armedCell: null,
        coord: null,
        pattern: [],
        driverPath: [],
        driverProgress: 0,
        driverReady: false,
        action: model.helpers.beginAction?.("fence-the-fox-stake-driver") || null,
      };
      clearDriverTrack();
      token.classList.add("is-dragging");
      try { token.setPointerCapture(event.pointerId); } catch (_error) { /* pointer capture unavailable */ }
    });
    token.addEventListener("pointermove", (event) => {
      const drag = model.pointerDrag;
      if (!drag || drag.pointerId !== event.pointerId) return;
      event.preventDefault();
      drag.travel += Math.hypot(event.clientX - drag.last[0], event.clientY - drag.last[1]);
      drag.last = [event.clientX, event.clientY];
      drag.samples += 1;
      token.style.setProperty("--drag-x", `${event.clientX - drag.start[0]}px`);
      token.style.setProperty("--drag-y", `${event.clientY - drag.start[1]}px`);
      if (!drag.armedCell) {
        const candidate = document.elementsFromPoint(event.clientX, event.clientY)
          .find((node) => node.classList?.contains("fox-cell") && !node.disabled);
        const candidateKey = candidate?.dataset?.cellKey || null;
        drag.hoverCandidateKey = candidateKey;
        if (candidate && candidateKey && drag.travel >= 48) {
          window.setTimeout(() => {
            if (model.pointerDrag === drag && drag.hoverCandidateKey === candidateKey) {
              armDriver(drag, candidate);
            }
          }, 90);
        }
        return;
      }
      const point = normalizedPointer(drag.armedCell, event);
      drag.driverPath.push(point.map((value) => Math.round(value * 1000) / 1000));
      if (drag.driverProgress < drag.pattern.length) {
        const expected = driverCheckpoint(drag.pattern[drag.driverProgress]);
        if (Math.hypot(point[0] - expected[0], point[1] - expected[1]) <= DRIVER_TOLERANCE) {
          drag.driverProgress += 1;
          flash(
            drag.driverProgress < drag.pattern.length
              ? `DRIVER MARK ${drag.driverProgress} SET · FOLLOW ${drag.driverProgress + 1}`
              : "DRIVER MARKS SET · RETURN TO CENTER AND RELEASE",
            "pending",
          );
        }
      } else if (Math.hypot(point[0], point[1]) <= DRIVER_TOLERANCE) {
        drag.driverReady = true;
        flash("STAKE ALIGNED · RELEASE AT CENTER", "pending");
      }
      updateDriverTrack(drag);
    });
    const end = (event, cancelled = false) => {
      const drag = model.pointerDrag;
      if (!drag || drag.pointerId !== event.pointerId) return;
      event.preventDefault();
      const releaseCell = cancelled ? null : document.elementsFromPoint(event.clientX, event.clientY)
        .find((node) => node.classList?.contains("fox-cell"));
      model.pointerDrag = null;
      try { token.releasePointerCapture(event.pointerId); } catch (_error) { /* capture already released */ }
      resetDraggedToken();
      clearDriverTrack();
      if (cancelled || !drag.armedCell || !drag.coord) {
        if (!cancelled) {
          const releaseCoord = releaseCell
            ? [Number(releaseCell.dataset.q), Number(releaseCell.dataset.r)]
            : null;
          flash(
            releaseCoord && same(releaseCoord, model.fox)
              ? "THE FOX OCCUPIES THAT HEX"
              : "HOLD THE STAKE OVER AN OPEN HEX UNTIL ITS DRIVER KEY APPEARS",
            "error",
          );
        }
        settleAction(drag.action);
        return;
      }
      const endPoint = normalizedPointer(drag.armedCell, event);
      drag.driverPath.push(endPoint.map((value) => Math.round(value * 1000) / 1000));
      if (!drag.driverReady || Math.hypot(endPoint[0], endPoint[1]) > DRIVER_TOLERANCE) {
        flash("STAKE NOT SEATED · FOLLOW 1 → 2 → CENTER WHILE HOLDING", "error");
        settleAction(drag.action);
        return;
      }
      placeFence(drag.coord, "stake_driver", {
        travel_px: Math.round(drag.travel * 1000) / 1000,
        sample_count: drag.samples,
        start: drag.start.map((value) => Math.round(value * 1000) / 1000),
        end: [event.clientX, event.clientY].map((value) => Math.round(value * 1000) / 1000),
        drop_cell: [...drag.coord],
        driver_path: drag.driverPath,
      }, drag.action);
    };
    token.addEventListener("pointerup", (event) => end(event));
    token.addEventListener("pointercancel", (event) => end(event, true));
    token.addEventListener("lostpointercapture", (event) => end(event, true));
  }

  async function render(state, helpers) {
    settleAction(model.pointerDrag?.action);
    settleAction(model.activeAction);
    clearDriverTrack();
    document.body.dataset.mechanic = "fence-the-fox";
    document.body.dataset.foxPalette = String(state.palette || "ember-pine");
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const interaction = state.control_condition?.interaction || "simplified";
    Object.assign(model, {
      state,
      helpers,
      cells: (state.cells || []).map((coord) => [Number(coord[0]), Number(coord[1])]),
      cellSet: new Set((state.cells || []).map((coord) => key(coord))),
      blocked: new Set((state.initial_fences || []).map((coord) => key(coord))),
      initialFences: new Set((state.initial_fences || []).map((coord) => key(coord))),
      playerFences: [],
      fox: [...state.fox_start],
      events: [],
      turns: 0,
      interaction,
      busy: false,
      terminal: "active",
      ready: false,
      pointerDrag: null,
      activeAction: null,
    });
    const board = buildGeometry();
    helpers.app.innerHTML = `
      <section class="fence-fox-captcha mode-${clean(interaction)}" data-challenge-id="${clean(state.challenge_id)}">
        <header class="fox-header">
          <div class="fox-title-mark"><span>RANGER FIELD NOTE / ${clean(state.challenge_id)}</span><h1>Fence the Fox</h1></div>
          <p>${clean(state.prompt)}</p>
          <div class="fox-condition"><small>FIELD</small><b>R${Number(state.radius)}</b><span>${Number(state.cells?.length || 0)} HEXES</span></div>
        </header>
        <main class="fox-workbench">
          <aside class="fox-left-rail">
            <div class="fox-supply-card">
              <span>FIELD SUPPLY</span><div><strong id="fox-stakes-left">${String(state.stake_budget).padStart(2, "0")}</strong><small>STAKES<br>LEFT</small></div>
              <div class="fox-stake-token" id="fox-stake-token" role="button" tabindex="${interaction === "full" ? "0" : "-1"}" aria-label="Reusable fence stake. Drag to an open hex, hold for the numbered driver key, trace it, return to center, and release.">
                <i></i><i></i><b></b><em></em>
              </div>
            </div>
            <div class="fox-vane-card"><small>CURRENT WIND</small><strong id="fox-vane-order">${clean(windOrder(Number(state.wind_start || 0)).join(" › "))}</strong><span>CHANGES AFTER EACH FOX STEP</span></div>
            <div class="fox-turn-card"><small>PLACEMENTS</small><strong id="fox-turn-count">00</strong></div>
          </aside>
          <section class="fox-map-panel">
            <div class="fox-map-caption"><span>WATCH SECTOR 17 · AXIAL HEX FIELD</span><b>FIELD ACTIVE</b></div>
            <div class="fox-field-frame">
              <div class="fox-field" id="fox-field" style="width:${board.width}px;height:${board.height}px;--hex-size:${board.size}px">
                <div class="fox-contour contour-one"></div><div class="fox-contour contour-two"></div>
                ${cellsMarkup()}${foxMarkup()}
              </div>
            </div>
          </section>
        </main>
        <footer class="fox-footer">
          <div class="fox-seal">F/17</div>
          <div class="readout fox-readout" data-status="idle">FIELD OPEN · STUDY THE ESCAPE BRANCHES</div>
          <button type="button" class="fox-certify" id="fox-certify">${clean(state.submit_label || "CHECK ENCLOSURE")}</button>
        </footer>
        ${helpers.cheatPanelTemplate()}
      </section>`;
    positionFox(false);
    bindSimplifiedCells();
    bindStakeDrag();
    document.getElementById("fox-certify")?.addEventListener("click", () => submit(model.ready));
    helpers.installCheatPanel?.();
    window.fenceTheFoxModel = model;
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.fence_the_fox = {render};
})();
