(() => {
  "use strict";

  let model = null;
  let cleanup = null;
  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const round4 = (value) => Number(Number(value).toFixed(4));
  const interaction = () => String(model?.state?.control_condition?.interaction || "full");

  function command(key) {
    return model.palette.get(String(key));
  }

  function iconFor(item) {
    if (item.op === "forward") return "↑";
    if (item.op === "left") return "↺";
    if (item.op === "right") return "↻";
    if (item.op === "repeat") return "⟳";
    if (item.op === "end") return "⌟";
    if (item.op === "pen_up") return "◇";
    if (item.op === "pen_down") return "◆";
    return "●";
  }

  function record(event) {
    model.editEvents.push({sequence: model.editEvents.length + 1, ...event});
    clearFreshFailure();
  }

  function clearFreshFailure() {
    if (!model?.freshFailure) return;
    model.freshFailure = false;
    document.querySelector(".tfg-verdict")?.remove();
    const root = document.querySelector(".turtle-forger");
    if (root) root.dataset.freshFailure = "false";
    model.helpers.setReadout("ATELIER READY · REFERENCE AVAILABLE", "idle");
  }

  function invalidateProof() {
    model.proofVersion = -1;
    model.renderedSegments = [];
    model.similarity = 0;
    renderProof();
  }

  function parseProgram(keys) {
    const source = keys.map((key) => {
      const item = command(key);
      if (!item) throw new Error("UNKNOWN PUNCH CARD");
      return item;
    });
    const maximum = Number(model.parameters.max_expanded_steps);
    function block(index, nested) {
      const output = [];
      while (index < source.length) {
        const item = source[index];
        if (item.op === "end") {
          if (!nested) throw new Error("ORPHAN CLOSE LOOP CARD");
          return {output, index: index + 1};
        }
        if (item.op === "repeat") {
          const child = block(index + 1, true);
          for (let count = 0; count < Number(item.value); count += 1) {
            child.output.forEach((entry) => output.push(entry));
          }
          index = child.index;
        } else {
          output.push(item);
          index += 1;
        }
        if (output.length > maximum) throw new Error("EXPANDED PROGRAM EXCEEDS PRESS LIMIT");
      }
      if (nested) throw new Error("LOOP CARD HAS NO CLOSE");
      return {output, index};
    }
    return block(0, false).output;
  }

  function executeProgram(keys) {
    const expanded = parseProgram(keys);
    let x = Number(model.state.start.x);
    let y = Number(model.state.start.y);
    let heading = Number(model.state.start.heading || 0);
    let penDown = true;
    let ink = "#202523";
    const segments = [];
    expanded.forEach((item) => {
      if (item.op === "ink") ink = String(item.value);
      else if (item.op === "pen_up") penDown = false;
      else if (item.op === "pen_down") penDown = true;
      else if (item.op === "left") heading = ((heading - Number(item.value)) % 360 + 360) % 360;
      else if (item.op === "right") heading = (heading + Number(item.value)) % 360;
      else if (item.op === "forward") {
        const radians = heading * Math.PI / 180;
        const afterX = x + Math.sin(radians) * Number(item.value);
        const afterY = y - Math.cos(radians) * Number(item.value);
        if (penDown) {
          segments.push({
            order: segments.length + 1,
            x1: round4(x), y1: round4(y), x2: round4(afterX), y2: round4(afterY),
            colour: ink, width: Number(model.state.canvas.stroke_width),
          });
        }
        x = afterX; y = afterY;
      }
    });
    return segments;
  }

  function raster(segments) {
    const cells = new Set();
    segments.forEach((segment) => {
      const x1 = Number(segment.x1); const y1 = Number(segment.y1);
      const x2 = Number(segment.x2); const y2 = Number(segment.y2);
      const length = Math.hypot(x2 - x1, y2 - y1);
      const steps = Math.max(1, Math.ceil(length / 1.25));
      for (let index = 0; index <= steps; index += 1) {
        const part = index / steps;
        const ix = Math.round((x1 + (x2 - x1) * part) / 3);
        const iy = Math.round((y1 + (y2 - y1) * part) / 3);
        for (let ox = -1; ox <= 1; ox += 1) for (let oy = -1; oy <= 1; oy += 1) {
          cells.add(`${segment.colour}|${ix + ox}|${iy + oy}`);
        }
      }
    });
    return cells;
  }

  function similarity(output) {
    const actual = raster(output);
    const expected = raster(model.targetSegments);
    if (!actual.size || !expected.size) return 0;
    let overlap = 0;
    actual.forEach((cell) => { if (expected.has(cell)) overlap += 1; });
    return overlap / (actual.size + expected.size - overlap);
  }

  function gridMarkup(mode) {
    if (mode === "none") return "";
    if (mode === "registration") {
      return `<g class="tfg-registration" aria-hidden="true">
        <path d="M18 28h24M30 16v24M378 28h24M390 16v24M18 272h24M30 260v24M378 272h24M390 260v24" />
        <circle cx="210" cy="150" r="4"></circle><path d="M195 150h30M210 135v30"></path>
      </g>`;
    }
    const spacing = mode === "full" ? 30 : 60;
    const lines = [];
    for (let x = spacing; x < 420; x += spacing) lines.push(`<line x1="${x}" y1="0" x2="${x}" y2="300"></line>`);
    for (let y = spacing; y < 300; y += spacing) lines.push(`<line x1="0" y1="${y}" x2="420" y2="${y}"></line>`);
    return `<g class="tfg-grid tfg-grid-${esc(mode)}" aria-hidden="true">${lines.join("")}</g>`;
  }

  function startMarker() {
    const start = model.state.start;
    return `<g class="tfg-start" transform="translate(${Number(start.x)} ${Number(start.y)}) rotate(${Number(start.heading || 0)})" aria-label="turtle start heading">
      <circle r="9"></circle><path d="M0 -16L-6 -5L6 -5Z"></path><text x="13" y="4">START</text>
    </g>`;
  }

  function referenceBase() {
    return `${gridMarkup(model.parameters.grid_mode)}${startMarker()}<g id="tfg-reference-active"></g>`;
  }

  function drawReference(index, progress) {
    const layer = document.getElementById("tfg-reference-active");
    if (!layer) return;
    if (index < 0 || index >= model.targetSegments.length || progress <= 0) {
      layer.innerHTML = "";
      return;
    }
    const segment = model.targetSegments[index];
    const x = Number(segment.x1) + (Number(segment.x2) - Number(segment.x1)) * progress;
    const y = Number(segment.y1) + (Number(segment.y2) - Number(segment.y1)) * progress;
    layer.innerHTML = `<line class="tfg-scan-stroke" x1="${segment.x1}" y1="${segment.y1}" x2="${x}" y2="${y}" stroke="${esc(segment.colour)}" stroke-width="${segment.width}"></line>
      <circle class="tfg-scan-head" cx="${x}" cy="${y}" r="7" fill="${esc(segment.colour)}"></circle>`;
    const counter = document.getElementById("tfg-scan-counter");
    const cycle = model.autoReplay ? `CYCLE ${String(model.scanCycle).padStart(2, "0")} · ` : "";
    if (counter) counter.textContent = `${cycle}STROKE ${String(index + 1).padStart(2, "0")} / ${String(model.targetSegments.length).padStart(2, "0")}`;
  }

  function updateAutoReplayControl() {
    const button = document.getElementById("tfg-auto-replay");
    if (!button) return;
    button.textContent = `AUTO REPLAY ${model.autoReplay ? "ON" : "OFF"}`;
    button.classList.toggle("is-active", model.autoReplay);
    button.setAttribute("aria-pressed", model.autoReplay ? "true" : "false");
  }

  function toggleAutoReplay() {
    if (!model || model.terminal) return;
    clearFreshFailure();
    model.autoReplay = !model.autoReplay;
    updateAutoReplayControl();
    if (model.autoReplay && !model.scanActive) scanReference();
    else if (model.scanActive) {
      model.helpers.setReadout(
        model.autoReplay ? "AUTO REPLAY ARMED · FULL MASTER WILL REPEAT" : "AUTO REPLAY OFF · CURRENT PASS WILL FINISH",
        "pending",
      );
    }
  }

  function scanReference() {
    if (!model || model.terminal) return;
    clearFreshFailure();
    if (model.scanFrame) cancelAnimationFrame(model.scanFrame);
    model.scanCount += 1;
    model.scanCycle = 1;
    model.scanStarted = performance.now();
    model.scanActive = true;
    document.querySelector(".tfg-reference")?.classList.add("is-scanning");
    model.helpers.setReadout("UV SCAN RUNNING · STROKES DO NOT PERSIST", "pending");
    const strokeMs = Number(model.parameters.stroke_ms);
    const gapMs = Number(model.parameters.gap_ms);
    const cycle = strokeMs + gapMs;
    const tick = (now) => {
      if (!model?.scanActive) return;
      const elapsed = now - model.scanStarted;
      const index = Math.floor(elapsed / cycle);
      if (index >= model.targetSegments.length) {
        if (model.autoReplay) {
          model.scanCount += 1;
          model.scanCycle += 1;
          model.scanStarted = now;
          const counter = document.getElementById("tfg-scan-counter");
          if (counter) counter.textContent = `AUTO REPLAY · CYCLE ${String(model.scanCycle).padStart(2, "0")}`;
          model.helpers.setReadout("AUTO REPLAY · MASTER RESTARTED FROM STROKE 01", "pending");
          model.scanFrame = requestAnimationFrame(tick);
          return;
        }
        model.scanActive = false;
        drawReference(-1, 0);
        document.querySelector(".tfg-reference")?.classList.remove("is-scanning");
        const counter = document.getElementById("tfg-scan-counter");
        if (counter) counter.textContent = "SCAN COMPLETE · REPLAY AVAILABLE";
        model.helpers.setReadout("REFERENCE ERASED · REPLAY WHEN NEEDED", "idle");
        return;
      }
      const local = elapsed - index * cycle;
      drawReference(index, local <= strokeMs ? Math.max(.02, Math.min(1, local / strokeMs)) : 0);
      model.scanFrame = requestAnimationFrame(tick);
    };
    model.scanFrame = requestAnimationFrame(tick);
  }

  function segmentMarkup(segment) {
    return `<line x1="${segment.x1}" y1="${segment.y1}" x2="${segment.x2}" y2="${segment.y2}" stroke="${esc(segment.colour)}" stroke-width="${segment.width}"></line>`;
  }

  function renderProof() {
    const layer = document.getElementById("tfg-proof-lines");
    if (layer) layer.innerHTML = model.renderedSegments.map(segmentMarkup).join("");
    const score = document.getElementById("tfg-score");
    const meter = document.getElementById("tfg-meter-fill");
    const stale = model.proofVersion !== model.editEvents.length;
    if (score) score.textContent = stale ? "UNPROOFED" : `${(model.similarity * 100).toFixed(2)}%`;
    if (meter) meter.style.transform = `scaleX(${stale ? 0 : Math.min(1, model.similarity)})`;
    document.querySelector(".tfg-proof")?.classList.toggle("is-proofed", !stale);
  }

  function proofProgram() {
    if (!model || model.submitting || model.terminal) return;
    clearFreshFailure();
    try {
      model.renderedSegments = executeProgram(model.program);
      model.similarity = similarity(model.renderedSegments);
      model.runCount += 1;
      model.proofVersion = model.editEvents.length;
      renderProof();
      model.helpers.setReadout(`PROOF IMPRESSION ${(model.similarity * 100).toFixed(2)}%`, model.similarity >= Number(model.state.pass_threshold) ? "passed" : "idle");
    } catch (error) {
      model.renderedSegments = [];
      model.similarity = 0;
      model.runCount += 1;
      model.proofVersion = model.editEvents.length;
      renderProof();
      model.helpers.setReadout(`PROGRAM JAM · ${String(error.message || error)}`, "error");
    }
  }

  function paletteMarkup() {
    return [...model.palette.values()].map((item) => `<button type="button" class="tfg-command family-${esc(item.family)}" data-command-key="${esc(item.key)}" style="${item.op === "ink" ? `--card-ink:${esc(item.value)}` : ""}">
      <i>${iconFor(item)}</i><span>${esc(item.label)}</span><small>${esc(item.family)}</small>
    </button>`).join("");
  }

  function programCardMarkup(key, index) {
    const item = command(key);
    const proxy = interaction() === "simplified" ? `<span class="tfg-move-bank"><button type="button" data-move-card="${index}:-1" aria-label="move card left">‹</button><button type="button" data-move-card="${index}:1" aria-label="move card right">›</button></span>` : "";
    return `<article class="tfg-program-card family-${esc(item.family)}" data-program-index="${index}" data-command-key="${esc(key)}" draggable="false" style="${item.op === "ink" ? `--card-ink:${esc(item.value)}` : ""}">
      <b>${String(index + 1).padStart(2, "0")}</b><i>${iconFor(item)}</i><span>${esc(item.label)}</span>${proxy}<button type="button" class="tfg-remove" data-remove-card="${index}" aria-label="remove card">×</button>
    </article>`;
  }

  function renderProgram() {
    const tape = document.getElementById("tfg-program-cards");
    if (!tape) return;
    tape.innerHTML = model.program.length ? model.program.map(programCardMarkup).join("") : `<div class="tfg-empty-tape"><b>EMPTY PROGRAM TAPE</b><span>${interaction() === "full" ? "DRAG CARDS HERE" : "CLICK CARDS TO APPEND"}</span></div>`;
    const count = document.getElementById("tfg-card-count");
    if (count) count.textContent = `${String(model.program.length).padStart(2, "0")} / ${String(model.parameters.program_capacity).padStart(2, "0")}`;
    bindProgramControls();
  }

  function addCard(key, at, source, gesture = null) {
    if (!command(key) || model.program.length >= Number(model.parameters.program_capacity)) {
      model.helpers.setReadout("PROGRAM TAPE IS FULL", "error");
      return;
    }
    at = Math.max(0, Math.min(model.program.length, Number(at)));
    model.program.splice(at, 0, key);
    record({type: "add", command_key: key, at, input_source: source, ...(gesture ? {gesture} : {})});
    invalidateProof();
    renderProgram();
  }

  function removeCard(index) {
    if (!Number.isInteger(index) || index < 0 || index >= model.program.length) return;
    const key = model.program[index];
    model.program.splice(index, 1);
    record({type: "remove", command_key: key, at: index, input_source: "tape_remove"});
    invalidateProof();
    renderProgram();
  }

  function moveCard(before, after, source, gesture = null) {
    if (!Number.isInteger(before) || !Number.isInteger(after) || before === after || before < 0 || after < 0 || before >= model.program.length || after >= model.program.length) return;
    const [key] = model.program.splice(before, 1);
    model.program.splice(after, 0, key);
    record({type: "move", from: before, to: after, input_source: source, ...(gesture ? {gesture} : {})});
    invalidateProof();
    renderProgram();
  }

  function startDrag(event, origin, key, index = null) {
    if (interaction() !== "full" || model.terminal || event.button !== 0) return;
    event.preventDefault();
    clearFreshFailure();
    const item = command(key);
    model.drag = {
      origin, key, index,
      startX: event.clientX, startY: event.clientY,
      lastX: event.clientX, lastY: event.clientY,
      travel: 0, samples: 0,
    };
    const ghost = document.createElement("div");
    ghost.className = `tfg-drag-ghost family-${item.family}`;
    ghost.textContent = item.label;
    document.body.appendChild(ghost);
    model.dragGhost = ghost;
    updateDragGhost(event.clientX, event.clientY);
  }

  function updateDragGhost(x, y) {
    if (!model.dragGhost) return;
    model.dragGhost.style.left = `${x + 14}px`;
    model.dragGhost.style.top = `${y + 14}px`;
  }

  function finishDrag(event) {
    if (!model?.drag) return;
    const drag = model.drag;
    drag.travel += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY);
    drag.samples += 1;
    model.drag = null;
    model.dragGhost?.remove();
    model.dragGhost = null;
    const hitStack = document.elementsFromPoint(event.clientX, event.clientY);
    const target = hitStack.map((node) => node.closest?.("#tfg-tape-zone")).find(Boolean);
    if (!target || drag.travel < 36 || drag.samples < 2) return;
    const card = hitStack.map((node) => node.closest?.("[data-program-index]")).find(Boolean);
    const targetIndex = card ? Number(card.dataset.programIndex) : model.program.length;
    const gesture = {travel_px: round4(drag.travel), sample_count: drag.samples};
    if (drag.origin === "palette") addCard(drag.key, model.program.length, "card_drag", gesture);
    else {
      const after = Math.min(model.program.length - 1, targetIndex);
      moveCard(Number(drag.index), after, "tape_drag", gesture);
    }
  }

  function bindProgramControls() {
    document.querySelectorAll("[data-remove-card]").forEach((button) => {
      button.addEventListener("pointerdown", (event) => event.stopPropagation());
      button.addEventListener("click", (event) => {
        event.stopPropagation(); removeCard(Number(button.dataset.removeCard));
      });
    });
    document.querySelectorAll("[data-move-card]").forEach((button) => {
      button.addEventListener("pointerdown", (event) => event.stopPropagation());
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        const [beforeText, directionText] = button.dataset.moveCard.split(":");
        const before = Number(beforeText); const after = before + Number(directionText);
        moveCard(before, after, "move_buttons");
      });
    });
    if (interaction() === "full") {
      document.querySelectorAll(".tfg-program-card").forEach((card) => card.addEventListener("pointerdown", (event) => startDrag(event, "tape", card.dataset.commandKey, Number(card.dataset.programIndex))));
    }
  }

  function showVerdict(kind) {
    document.querySelector(".tfg-verdict")?.remove();
    const root = document.querySelector(".turtle-forger");
    root?.insertAdjacentHTML("beforeend", `<div class="tfg-verdict is-${kind}"><small>GEOMETRIC SEAL BUREAU</small><b>${kind.toUpperCase()}</b><span>${kind === "pass" ? "PLATE ACCEPTED" : "PLATE REJECTED · FRESH MASTER"}</span></div>`);
  }

  async function certify() {
    if (!model || model.submitting || model.terminal) return;
    if (model.proofVersion !== model.editEvents.length) {
      model.helpers.setReadout("PROOF THE CURRENT PROGRAM BEFORE CERTIFYING", "error");
      return;
    }
    const current = model;
    current.submitting = true;
    current.helpers.setReadout("REPLAYING PUNCH TAPE + RASTER…", "pending");
    try {
      const response = await fetch("/result", {
        method: "POST", headers: {"content-type": "application/json"},
        body: JSON.stringify({
          mechanic_id: current.state.mechanic_id,
          task_id: current.state.task_id,
          challenge_id: current.state.challenge_id,
          interaction_mode: interaction(),
          edit_events: current.editEvents,
          final_program: current.program,
          run_count: current.runCount,
          rendered_segments: current.renderedSegments,
          similarity: current.similarity,
          scan_count: current.scanCount,
          completed: true,
        }),
      });
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.terminal = true;
        current.helpers.setReadout("PASS", "passed");
        showVerdict("pass");
      } else if (outcome.passed === false && outcome.state) {
        const helpers = current.helpers;
        await render(outcome.state, helpers, {freshFailure: true});
        model.helpers.setReadout("FAIL", "error");
        showVerdict("fail");
      } else {
        current.submitting = false;
        current.helpers.setReadout("CERTIFICATION REJECTED", "error");
      }
    } catch (_error) {
      if (model === current) {
        current.submitting = false;
        current.helpers.setReadout("CERTIFICATION LINK OFFLINE", "error");
      }
    }
  }

  function installHandlers() {
    document.getElementById("tfg-scan")?.addEventListener("click", scanReference);
    document.getElementById("tfg-auto-replay")?.addEventListener("click", toggleAutoReplay);
    document.getElementById("tfg-proof")?.addEventListener("click", proofProgram);
    document.getElementById("tfg-certify")?.addEventListener("click", certify);
    document.querySelectorAll("[data-command-key]").forEach((button) => {
      if (!button.classList.contains("tfg-command")) return;
      if (interaction() === "simplified") button.addEventListener("click", () => addCard(button.dataset.commandKey, model.program.length, "palette_click"));
      else button.addEventListener("pointerdown", (event) => startDrag(event, "palette", button.dataset.commandKey));
    });
    bindProgramControls();
    model.pointerMove = (event) => {
      if (!model?.drag) return;
      model.drag.travel += Math.hypot(event.clientX - model.drag.lastX, event.clientY - model.drag.lastY);
      model.drag.lastX = event.clientX; model.drag.lastY = event.clientY; model.drag.samples += 1;
      updateDragGhost(event.clientX, event.clientY);
    };
    model.pointerUp = finishDrag;
    window.addEventListener("pointermove", model.pointerMove);
    window.addEventListener("pointerup", model.pointerUp);
  }

  async function render(state, helpers, options = {}) {
    cleanup?.();
    document.body.dataset.mechanic = "turtle-forger";
    model = {
      state, helpers,
      parameters: state.parameters,
      palette: new Map((state.command_palette || []).map((item) => [String(item.key), item])),
      targetSegments: JSON.parse(JSON.stringify(state.runtime_target_segments || [])),
      program: [], editEvents: [], renderedSegments: [], similarity: 0,
      runCount: 0, scanCount: 0, proofVersion: -1,
      scanFrame: 0, scanActive: false, scanCycle: 0, autoReplay: false,
      drag: null, dragGhost: null,
      freshFailure: Boolean(options.freshFailure), submitting: false, terminal: false,
      pointerMove: null, pointerUp: null,
    };
    helpers.app.innerHTML = `<section class="turtle-forger mode-${esc(interaction())}" data-fresh-failure="${options.freshFailure ? "true" : "false"}">
      <header class="tfg-header">
        <div><small>BUREAU OF GEOMETRIC SEALS / COUNTERFEIT DIVISION</small><h1>${esc(state.prompt)}</h1></div>
        <aside><span>MASTER ${esc(state.seal_id)}</span><b>${interaction().toUpperCase()} PUNCHING</b><i></i></aside>
      </header>
      <main class="tfg-workbench">
        <section class="tfg-plate tfg-reference">
          <header><div><small>01 / UV REFERENCE PLATE</small><b>ONE STROKE AT A TIME</b></div><button id="tfg-scan" type="button">SCAN MASTER</button></header>
          <svg viewBox="0 0 420 300" role="img" aria-label="transient reference plate">${referenceBase()}</svg>
          <footer><span id="tfg-scan-counter">REFERENCE SEALED · START MARK VISIBLE</span><button id="tfg-auto-replay" class="tfg-auto-replay" type="button" aria-pressed="false">AUTO REPLAY OFF</button></footer>
        </section>
        <section class="tfg-plate tfg-proof">
          <header><div><small>02 / COUNTERFEIT PROOF</small><b>PROGRAM OUTPUT</b></div><button id="tfg-proof" type="button">RUN PROOF</button></header>
          <svg viewBox="0 0 420 300" role="img" aria-label="program proof plate">${gridMarkup(model.parameters.grid_mode)}${startMarker()}<g id="tfg-proof-lines"></g></svg>
          <footer><span id="tfg-score">UNPROOFED</span><div class="tfg-meter"><i id="tfg-meter-fill"></i></div><b>RASTER MATCH</b></footer>
        </section>
        <aside class="tfg-drawer">
          <header><small>03 / PUNCH-CARD DRAWER</small><b>${interaction() === "full" ? "DRAG INTO TAPE" : "CLICK TO APPEND"}</b></header>
          <div class="tfg-command-grid">${paletteMarkup()}</div>
          <footer><span>CARDS MAY BE REUSED</span><i>${Number(model.parameters.palette_decoys)} DECOYS MIXED IN</i></footer>
        </aside>
      </main>
      <section class="tfg-program">
        <header><div><small>04 / PROGRAM TAPE</small><b>EXECUTION READS LEFT → RIGHT · LOOPS MAY NEST</b></div><span id="tfg-card-count">00 / ${String(model.parameters.program_capacity).padStart(2, "0")}</span></header>
        <div class="tfg-tape-zone" id="tfg-tape-zone"><div id="tfg-program-cards"><div class="tfg-empty-tape"><b>EMPTY PROGRAM TAPE</b><span>${interaction() === "full" ? "DRAG CARDS HERE" : "CLICK CARDS TO APPEND"}</span></div></div></div>
      </section>
      <footer class="tfg-footer"><div class="readout" data-status="idle">ATELIER READY · REFERENCE AVAILABLE</div><span>TRANSIENT MASTER / INDEPENDENT PROGRAM REPLAY</span><button id="tfg-certify" type="button">CERTIFY PLATE →</button></footer>
      ${helpers.cheatPanelTemplate()}
    </section>`;
    installHandlers();
    renderProof();
    helpers.installCheatPanel();
    cleanup = () => {
      if (model?.scanFrame) cancelAnimationFrame(model.scanFrame);
      if (model?.pointerMove) window.removeEventListener("pointermove", model.pointerMove);
      if (model?.pointerUp) window.removeEventListener("pointerup", model.pointerUp);
      model?.dragGhost?.remove();
    };
    if (options.freshFailure) showVerdict("fail");
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.turtle_forger = {rootSelector: ".turtle-forger", render};
})();
