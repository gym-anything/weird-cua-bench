(() => {
  "use strict";

  let model = null;
  let cleanup = null;
  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const mode = () => model.state.control_condition?.interaction || "full";

  function ticket() {
    const id = model.workshop.runtime_ticket_sequence[model.ticketIndex];
    return model.workshop.tickets.find((item) => item.id === id) || null;
  }

  function labelById(id) { return model.workshop.labels.find((item) => item.id === id) || null; }
  function fruitById(id) { return model.workshop.fruits.find((item) => item.id === id) || null; }
  function point(index) { return model.workshop.loop_points[index]; }

  function target() {
    const current = ticket();
    if (!current) return null;
    if (model.npcPhase === "signal") return labelById(current.label_id).station;
    return {
      jar: model.workshop.stations.jar_rack,
      handoff: model.workshop.stations.colleague_handoff,
      press: model.workshop.stations.colleague_press,
      hatch: model.workshop.stations.hatch,
    }[model.npcPhase] ?? null;
  }

  function moveNpc(direction) {
    const candidate = (model.npcPos + direction + model.workshop.loop_size) % model.workshop.loop_size;
    if (candidate === model.playerPos) {
      model.jams += 1;
      model.bump = "colleague";
      model.message = "LOOP BLOCKED";
    } else {
      model.npcPos = candidate;
      model.bump = null;
    }
  }

  function npcStep() {
    if (model.terminalFailure || !ticket()) return;
    const current = ticket();
    if (model.npcPhase === "press_wait") {
      if (model.tick > model.primeUntil) {
        model.spoils += 1;
        model.npcPhase = "signal";
        model.npcWait = 0;
        model.primeUntil = null;
        model.message = `SEAL MISSED · ${model.spoils}/${model.parameters.max_spoils} JARS SPOILED`;
        if (model.spoils >= model.parameters.max_spoils) {
          model.terminalFailure = true;
          model.message = "SHIFT FAILED · TOO MANY JARS SPOILED";
        }
      }
      return;
    }
    const destination = target();
    if (destination == null) return;
    if (model.npcPos !== destination) {
      moveNpc(Number(current.direction));
      if (model.npcPhase === "signal" && model.npcPos === destination) {
        model.npcWait = 1;
        model.message = "LABEL RACK VISITED";
      }
      return;
    }
    if (model.npcPhase === "signal") {
      if (model.npcWait <= 0) {
        model.npcWait = 1;
        model.message = "LABEL RACK VISITED";
      } else if (model.npcWait < model.parameters.signal_ticks) {
        model.npcWait += 1;
        model.message = "LABEL RACK VISITED";
      } else {
        model.npcWait = 0;
        model.npcPhase = "jar";
        model.message = "LABEL RACK CLEARED";
        moveNpc(Number(current.direction));
      }
    } else if (model.npcPhase === "jar") {
      model.npcPhase = "handoff";
      model.message = "EMPTY JAR LIFTED";
    } else if (model.npcPhase === "handoff") {
      if (model.shelf === current.fruit_id) {
        model.shelf = null;
        model.npcPhase = "press";
        model.message = "FRUIT TAKEN FROM PASS";
      } else if (model.shelf) {
        model.message = "PASS REFUSED";
        model.sigh = true;
      } else {
        model.message = "PASS EMPTY";
      }
    } else if (model.npcPhase === "press") {
      model.npcPhase = "press_wait";
      model.primeUntil = model.tick + model.parameters.press_window_ticks - 1;
      model.message = "HANDLE FLASH";
    } else if (model.npcPhase === "hatch") {
      model.delivered.push(current.id);
      model.ticketIndex += 1;
      model.npcPhase = "signal";
      model.npcWait = 0;
      model.message = ticket() ? "JAR DELIVERED" : "EVERY TICKET FILLED";
    }
  }

  function advance() {
    if (!model || model.submitting || model.completed) return;
    model.tick += 1;
    model.sigh = false;
    npcStep();
    if (!ticket() && !model.terminalFailure) model.ready = true;
  }

  function advanceToNow() {
    if (!model || model.submitting || model.completed) return;
    const target = Math.floor((performance.now() - model.started) / Number(model.parameters.tick_ms) + 1e-7);
    while (model.tick < target) advance();
  }

  function stationFruit() {
    return model.workshop.fruits.find((item) => Number(item.station) === model.playerPos)?.id || null;
  }

  function applyAction(action) {
    const before = model.playerPos;
    if (action === "ccw" || action === "cw") {
      const direction = action === "ccw" ? -1 : 1;
      const candidate = (before + direction + model.workshop.loop_size) % model.workshop.loop_size;
      const moved = candidate !== model.npcPos;
      if (moved) {
        model.playerPos = candidate;
        model.bump = null;
      } else {
        model.jams += 1;
        model.bump = "player";
        model.message = "OCCUPIED TILE";
      }
      return {kind: "move", action, from: before, to: model.playerPos, moved};
    }
    let effect = "idle";
    const fruit = stationFruit();
    const stations = model.workshop.stations;
    if (fruit) {
      model.playerCarrying = fruit;
      effect = "pick_fruit";
      model.message = `${fruitById(fruit).name} CRATE OPENED · CARRYING ONE BATCH`;
    } else if (model.playerPos === stations.handoff) {
      if (model.playerCarrying) {
        model.shelf = model.playerCarrying;
        model.playerCarrying = null;
        effect = "place_handoff";
        model.message = "FRUIT LEFT ON THE SHARED PASS";
      } else if (model.shelf) {
        model.playerCarrying = model.shelf;
        model.shelf = null;
        effect = "retrieve_handoff";
        model.message = "FRUIT RETRIEVED FROM THE PASS";
      }
    } else if (model.playerPos === stations.player_press && model.npcPhase === "press_wait" && model.primeUntil != null && model.tick <= model.primeUntil) {
      model.npcPhase = "hatch";
      model.primeUntil = null;
      effect = "paired_press";
      model.message = "BOTH HANDLES LANDED · JAR SEALED";
    } else {
      model.message = "NO AVAILABLE ACTION AT THIS TILE";
    }
    return {kind: "use", action: "use", position: model.playerPos, effect, carrying: model.playerCarrying, shelf: model.shelf};
  }

  function act(action, inputSource) {
    advanceToNow();
    if (!model || model.submitting || model.completed || model.terminalFailure) return;
    const claim = applyAction(action);
    model.events.push({sequence: model.events.length + 1, tick: model.tick, input_source: inputSource, ...claim});
    renderSurface();
  }

  function visibleIntent() {
    const current = ticket();
    if (!current) return "";
    const atSignal = model.npcPhase === "signal" && model.npcPos === labelById(current.label_id).station;
    if (model.parameters.intent_mode === "fruit_badge") {
      const fruit = fruitById(current.fruit_id);
      return `<span class="sc-intent" style="--intent:${fruit.hue}">${esc(fruit.glyph)}</span>`;
    }
    if (model.parameters.intent_mode === "label_badge" || (model.parameters.intent_mode === "hover_badge" && atSignal)) {
      const label = labelById(current.label_id);
      return `<span class="sc-intent" style="--intent:${label.hue}">${esc(label.sigil)}</span>`;
    }
    return "";
  }

  function stationMarkup() {
    const stations = [];
    model.workshop.fruits.forEach((fruit) => stations.push({index: fruit.station, cls: "fruit", title: fruit.name, glyph: fruit.glyph, hue: fruit.hue}));
    model.workshop.labels.forEach((label) => stations.push({index: label.station, cls: "label", title: `${label.name} LABEL`, glyph: label.sigil, hue: label.hue}));
    const fixed = model.workshop.stations;
    stations.push(
      {index: fixed.handoff, cls: "handoff player-handoff", title: "YOUR PASS", glyph: model.shelf ? fruitById(model.shelf).glyph : "⇄", hue: model.shelf ? fruitById(model.shelf).hue : "#d6c49c"},
      {index: fixed.player_press, cls: "press player-press", title: "YOUR HANDLE", glyph: "Ⅰ", hue: "#e8a84d"},
      {index: fixed.colleague_press, cls: "press colleague-press", title: "THEIR HANDLE", glyph: "Ⅱ", hue: "#6fbfc1"},
      {index: fixed.colleague_handoff, cls: "handoff colleague-handoff", title: "THEIR PASS", glyph: model.shelf ? fruitById(model.shelf).glyph : "⇄", hue: model.shelf ? fruitById(model.shelf).hue : "#d6c49c"},
      {index: fixed.jar_rack, cls: "jar", title: "JAR RACK", glyph: "▱", hue: "#d6e5dc"},
      {index: fixed.hatch, cls: "hatch", title: "DELIVERY HATCH", glyph: "↥", hue: "#b8d692"},
    );
    return stations.map((item) => {
      const [x, y] = point(item.index);
      const activePress = item.cls.includes("player-press") && model.npcPhase === "press_wait";
      return `<div class="sc-station ${item.cls} ${activePress ? "is-primed" : ""}" style="--x:${x}%;--y:${y}%;--station:${item.hue}" data-station-index="${item.index}"><b>${esc(item.glyph)}</b><span>${esc(item.title)}</span></div>`;
    }).join("");
  }

  function avatarMarkup(role, index) {
    const [x, y] = point(index);
    const carrying = role === "player" ? model.playerCarrying : (model.npcPhase === "jar" || model.npcPhase === "handoff" || model.npcPhase === "press" || model.npcPhase === "press_wait" ? "jar" : null);
    const bump = model.bump === role ? "is-bumped" : "";
    return `<div class="sc-avatar ${role} ${bump} ${role === "colleague" && model.sigh ? "is-sighing" : ""}" style="--x:${x}%;--y:${y}%" data-loop-index="${index}">
      ${role === "colleague" ? visibleIntent() : ""}<i><b>${role === "player" ? "YOU" : "Ⅱ"}</b></i>
      ${carrying ? `<em>${carrying === "jar" ? "▱" : esc(fruitById(carrying).glyph)}</em>` : ""}
      <span>${role === "player" ? "PRESERVER" : "COLLEAGUE"}</span>
    </div>`;
  }

  function ticketMarkup(item) {
    const delivered = model.delivered.includes(item.id);
    const label = labelById(item.label_id);
    const fruit = fruitById(item.fruit_id);
    return `<article class="sc-ticket ${delivered ? "is-done" : ""}">
      <div style="--label:${label.hue}">${esc(label.sigil)}</div><span><small>LABEL ${esc(label.name)}</small><strong>${esc(fruit.glyph)} · ${esc(fruit.name)}</strong></span><b>${delivered ? "SEALED" : "OPEN"}</b>
    </article>`;
  }

  function snapshot() {
    return {
      tick: model.tick, player_pos: model.playerPos, npc_pos: model.npcPos, player_carrying: model.playerCarrying,
      shelf: model.shelf, ticket_index: model.ticketIndex, npc_phase: model.npcPhase, npc_wait: model.npcWait,
      prime_until: model.primeUntil, delivered: [...model.delivered], spoils: model.spoils, jams: model.jams,
      terminal_failure: model.terminalFailure,
    };
  }

  function bindControls() {
    document.querySelector('[data-sc-act="ccw"]')?.addEventListener("click", () => act("ccw", "proxy_step"));
    document.querySelector('[data-sc-act="cw"]')?.addEventListener("click", () => act("cw", "proxy_step"));
    document.querySelector('[data-sc-act="use"]')?.addEventListener("click", () => act("use", "proxy_action"));
    document.getElementById("sc-certify")?.addEventListener("click", submit);
  }

  function renderSurface() {
    const root = document.querySelector(".silent-colleague");
    if (!root || !model) return;
    root.querySelector(".sc-floor").innerHTML = `<div class="sc-counter"><small>SHARED LINE</small><b>QUIET PRESERVES</b><span>ONE TILE · TWO WORKERS</span></div>${stationMarkup()}${avatarMarkup("player", model.playerPos)}${avatarMarkup("colleague", model.npcPos)}`;
    root.querySelector(".sc-ticket-list").innerHTML = model.workshop.tickets.map(ticketMarkup).join("");
    const pressRemaining = model.npcPhase === "press_wait" ? Math.max(0, model.primeUntil - model.tick + 1) : 0;
    root.querySelector(".sc-telemetry").innerHTML = `<div><small>WORK LINE</small><b>${model.ready ? "SHIFT COMPLETE" : model.terminalFailure ? "SHIFT STOPPED" : "IN MOTION"}</b></div><div><small>PRESS WINDOW</small><b class="${pressRemaining ? "is-hot" : ""}">${pressRemaining ? `${pressRemaining} TICKS` : "DORMANT"}</b></div><div><small>SPOILED</small><b>${model.spoils}/${model.parameters.max_spoils}</b></div><div><small>LOOP BLOCKS</small><b>${model.jams}</b></div>`;
    root.querySelector(".sc-message").textContent = model.message;
    const proxy = root.querySelector(".sc-proxy");
    if (proxy) proxy.hidden = mode() !== "simplified";
    const certify = document.getElementById("sc-certify");
    certify.disabled = model.submitting || model.completed;
    certify.textContent = model.ready ? "CERTIFY FILLED SHIFT" : model.terminalFailure ? "CERTIFY FAILED SHIFT" : "END & CERTIFY SHIFT";
    root.dataset.phase = model.npcPhase;
    root.dataset.ready = model.ready ? "true" : "false";
  }

  async function submit() {
    advanceToNow();
    if (!model || model.submitting || model.completed) return;
    const current = model;
    current.submitting = true;
    current.message = "INDEPENDENTLY REPLAYING EVERY STEP AND COLLEAGUE TICK…";
    renderSurface();
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({
        mechanic_id: current.state.mechanic_id, task_id: current.state.task_id, challenge_id: current.state.challenge_id,
        interaction_mode: mode(), events: current.events, final_tick: current.tick, final_state: snapshot(), completed: current.ready,
      })});
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.completed = true;
        current.message = "PASS · ALL TICKETS AND JOINT PRESSES REPLAYED";
        current.helpers.setReadout("PASS", "passed");
        renderSurface();
        document.querySelector(".silent-colleague")?.insertAdjacentHTML("beforeend", '<div class="sc-verdict is-pass"><small>SHIFT LEDGER ACCEPTED</small><strong>PASS</strong><span>THE LINE HELD TOGETHER</span></div>');
      } else if (outcome.passed === false && outcome.state) {
        const helpers = current.helpers;
        await render(outcome.state, helpers, {freshFailure: true});
        model.helpers.setReadout("FAIL", "error");
      } else {
        current.submitting = false;
        current.message = "CERTIFICATION REJECTED";
        current.helpers.setReadout("FAIL", "error");
        renderSurface();
      }
    } catch (_error) {
      if (model === current) {
        current.submitting = false;
        current.message = "CERTIFICATION LINK OFFLINE";
        current.helpers.setReadout("FAIL", "error");
        renderSurface();
      }
    }
  }

  function onKey(event) {
    if (event.repeat || mode() !== "full") return;
    if (["ArrowLeft", "ArrowRight", "a", "A", "d", "D", " "].includes(event.key)) event.preventDefault();
    if (event.key === "ArrowLeft" || event.key === "a" || event.key === "A") act("ccw", "keyboard_move");
    else if (event.key === "ArrowRight" || event.key === "d" || event.key === "D") act("cw", "keyboard_move");
    else if (event.key === " ") act("use", "keyboard_action");
  }

  async function render(state, helpers, options = {}) {
    cleanup?.();
    document.body.dataset.mechanic = "silent-colleague";
    model = {
      state, helpers, workshop: JSON.parse(JSON.stringify(state.workshop)), parameters: JSON.parse(JSON.stringify(state.parameters)),
      tick: 0, started: performance.now(), playerPos: state.workshop.player_start, npcPos: state.workshop.colleague_start,
      playerCarrying: null, shelf: null, ticketIndex: 0, npcPhase: "signal", npcWait: 0, primeUntil: null,
      delivered: [], spoils: 0, jams: 0, terminalFailure: false, ready: false, completed: false, submitting: false,
      bump: null, sigh: false, events: [], message: options.freshFailure ? "FAIL · FRESH SHIFT LOADED · LEDGER CLEARED" : "SHIFT OPEN",
    };
    helpers.app.innerHTML = `<section class="silent-colleague mode-${mode()}" data-mechanic="${esc(state.mechanic_id)}" data-interaction="${mode()}" data-fresh-failure="${options.freshFailure ? "true" : "false"}">
      <header class="sc-masthead"><div><small>BRAMBLE & BRINE CO-OPERATIVE · ${esc(state.workshop.batch_code)}</small><h1>${esc(state.prompt)}</h1></div><div class="sc-shift"><i></i><span>${mode().toUpperCase()} INPUT</span><b>D${state.control_condition?.difficulty || 4} · TICK ${state.parameters.tick_ms}MS</b></div></header>
      <main><section class="sc-workshop"><div class="sc-floor" aria-label="one-tile preservation workshop loop"></div><div class="sc-message readout" data-status="idle"></div></section><aside class="sc-orders"><header><small>DELIVERY HATCH / SHIFT LEDGER</small><h2>PRESERVE TICKETS</h2></header><div class="sc-ticket-list"></div><div class="sc-key"><span><i class="you"></i>YOU</span><span><i class="them"></i>COLLEAGUE</span></div></aside></main>
      <footer><div class="sc-telemetry"></div><div class="sc-proxy" hidden><button data-sc-act="ccw">↶ STEP</button><button data-sc-act="use">USE STATION</button><button data-sc-act="cw">STEP ↷</button></div><div class="sc-full-help">A / ← COUNTER-CLOCKWISE &nbsp; · &nbsp; D / → CLOCKWISE &nbsp; · &nbsp; SPACE USE</div><button id="sc-certify">END & CERTIFY SHIFT</button></footer>
      ${options.freshFailure ? '<div class="sc-verdict is-fail"><small>PRIOR LEDGER REJECTED</small><strong>FAIL</strong><span>FRESH SHIFT ISSUED</span></div>' : ""}
      ${helpers.cheatPanelTemplate()}
    </section>`;
    renderSurface();
    bindControls();
    helpers.installCheatPanel();
    window.addEventListener("keydown", onKey);
    let timer;
    const frame = () => {
      const before = model.tick;
      advanceToNow();
      if (model.tick !== before) renderSurface();
      timer = requestAnimationFrame(frame);
    };
    timer = requestAnimationFrame(frame);
    cleanup = () => { cancelAnimationFrame(timer); window.removeEventListener("keydown", onKey); };
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.silent_colleague = {rootSelector: ".silent-colleague", render};
})();
