(() => {
  "use strict";
  const MECHANIC_ID = "tomorrows_marble";
  const PUBLIC_NAME = "Tomorrow's Marble";
  const esc = (value) => String(value == null ? "" : value).replace(/[&<>\"']/g, (char) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;", "'":"&#39;"}[char]));
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const nodeKey = (node) => `${Number(node.machine_index)}:${Number(node.piece_index)}:${Number(node.slot)}`;
  const sortNodes = (nodes) => [...nodes].sort((left, right) => Number(left.slot) - Number(right.slot) || Number(left.machine_index) - Number(right.machine_index) || Number(left.piece_index) - Number(right.piece_index));
  const sortKeys = (keys) => [...keys].sort((left, right) => {
    const a = left.split(":").map(Number), b = right.split(":").map(Number);
    return a[0] - b[0] || a[1] - b[1] || a[2] - b[2];
  });

  function statefulTransition(source, phase, memory, state) {
    const pieceCount = (state.pieces || []).length;
    const machineCount = (state.machines || []).length;
    const slotCount = Number(state.timeline_slots);
    const carryModulus = Number(state.handoff_carry_modulus);
    const before = [...memory];
    const expected = phase.expected;
    const matched = nodeKey(source) === nodeKey(expected);
    const machine = (state.machines || [])[Number(source.machine_index)];
    const rawBaseSlot = Number(source.slot) + Number(machine.delay);
    const baseTarget = {
      machine_index: Number(machine.next_machine_index),
      piece_index: Number(machine.piece_map[Number(source.piece_index)]),
      slot: rawBaseSlot % slotCount,
    };
    const baseWraps = Math.floor(rawBaseSlot / slotCount);
    if (!matched) {
      const memorySlot = Number(phase.memory_slot) % memory.length;
      memory[memorySlot] = (Number(memory[memorySlot]) + 1) % carryModulus;
    }
    const shift = memory.reduce((total, value) => total + Number(value), 0) % carryModulus;
    const destination = baseTarget;
    let target;
    let wraps;
    if (matched && shift === 0) {
      target = {
        machine_index: Number(destination.machine_index),
        piece_index: Number(destination.piece_index),
        slot: Number(destination.slot),
      };
      wraps = baseWraps;
    } else {
      const rawDelay = Number(machine.delay) + shift * Number(state.handoff_slot_shift);
      target = {
        machine_index: (Number(destination.machine_index) + shift * Number(state.handoff_machine_shift)) % machineCount,
        piece_index: (Number(destination.piece_index) + shift * Number(state.handoff_piece_shift)) % pieceCount,
        slot: (Number(source.slot) + rawDelay) % slotCount,
      };
      wraps = Math.floor((Number(source.slot) + rawDelay) / slotCount);
    }
    return {target, wraps, matched, before, after: [...memory], shift};
  }

  function simulate(schedule, state) {
    const machines = state.machines || [];
    const slotCount = Number(state.timeline_slots);
    const ordered = sortNodes(schedule);
    const sourceKeys = ordered.map(nodeKey);
    const sourceSet = new Set(sourceKeys);
    const program = state.handoff_program || [];
    const memorySize = Number(state.handoff_memory || 0);
    const departures = [];
    const handoffTrace = [];
    const memory = Array.from({length: Math.max(0, memorySize)}, () => 0);
    let firstMismatchStep = null;
    let laterDeparturesShifted = false;
    if (program.length && memory.length) {
      ordered.forEach((source, step) => {
        const phase = program[step % program.length];
        const result = statefulTransition(source, phase, memory, state);
        if (!result.matched && firstMismatchStep == null) firstMismatchStep = step;
        if (firstMismatchStep != null && step > firstMismatchStep && result.shift) laterDeparturesShifted = true;
        departures.push({
          source: clone(source),
          destination: result.target,
          wraps: result.wraps,
          returns_to_past: result.wraps > 0,
        });
        handoffTrace.push({
          step,
          state_label: String(phase.state_label || `H${Number(phase.memory_slot) + 1}`),
          expected_source: clone(phase.expected),
          observed_source: clone(source),
          matched: result.matched,
          memory_before: result.before,
          memory_after: result.after,
          shift: result.shift,
          destination: clone(result.target),
        });
      });
    }
    const destinationCounts = new Map();
    departures.forEach((departure) => {
      const key = nodeKey(departure.destination);
      destinationCounts.set(key, Number(destinationCounts.get(key) || 0) + 1);
    });
    const sourceCounts = new Map();
    sourceKeys.forEach((key) => sourceCounts.set(key, Number(sourceCounts.get(key) || 0) + 1));
    const missing = sortKeys([...sourceCounts.keys()].filter((key) => !destinationCounts.has(key))).map((key) => {
      const [machine_index, piece_index, slot] = key.split(":").map(Number);
      return {machine_index, piece_index, slot};
    });
    const orphan = sortKeys([...destinationCounts.keys()].filter((key) => !sourceCounts.has(key))).map((key) => {
      const [machine_index, piece_index, slot] = key.split(":").map(Number);
      return {machine_index, piece_index, slot};
    });
    const anchors = state.anchors || [];
    const anchorsPresent = anchors.every((anchor) => sourceSet.has(nodeKey(anchor)));
    const machineCoverage = new Set(ordered.map((node) => Number(node.machine_index))).size;
    let sameCounts = sourceCounts.size === ordered.length && sourceCounts.size === destinationCounts.size;
    if (sameCounts) {
      sourceCounts.forEach((count, key) => { if (destinationCounts.get(key) !== count) sameCounts = false; });
    }
    const closed = sameCounts && missing.length === 0 && orphan.length === 0;
    const passed = ordered.length === Number(state.required_entries) && closed && anchorsPresent && machineCoverage === machines.length && handoffTrace.length === ordered.length && handoffTrace.every((item) => item.matched && item.shift === 0);
    return {
      arrival_count: ordered.length,
      arrivals: ordered,
      departures,
      missing_arrivals: missing,
      orphan_departures: orphan,
      anchors_present: anchorsPresent,
      machine_coverage: machineCoverage,
      closed,
      passed,
      handoff_trace: handoffTrace,
      handoff_final_memory: [...memory],
      handoff_contamination: memory.reduce((total, value) => total + Number(value), 0),
      later_departures_shifted: laterDeparturesShifted,
    };
  }

  function render(state, helpers) {
    // The static browser-play smoke gate waits for every external mechanic to
    // publish a non-waiting body marker after its first visible render.
    document.body.dataset.mechanic = MECHANIC_ID;
    const interaction = String(state.interaction_mode || state.control_condition?.interaction || "full");
    const machines = clone(state.machines || []);
    const pieces = clone(state.pieces || []);
    const timelineSlots = Number(state.timeline_slots || 1);
    const machineByIndex = Object.fromEntries(machines.map((machine) => [Number(machine.index), machine]));
    const pieceByIndex = Object.fromEntries(pieces.map((piece) => [Number(piece.index), piece]));
    const anchors = state.anchors || [];
    const anchorsAt = (machineIndex, slot) => anchors.filter((anchor) => Number(anchor.machine_index) === Number(machineIndex) && Number(anchor.slot) === Number(slot));
    const anchorLabel = (machineIndex, slot) => anchorsAt(machineIndex, slot).map((anchor) => {
      const piece = pieceByIndex[Number(anchor.piece_index)] || {};
      return `ORIGIN · ${piece.glyph || "?"} ${piece.name || "MARBLE"}`;
    }).join(" / ");
    const model = {
      state,
      helpers,
      interaction,
      machines,
      pieces,
      schedule: [],
      events: [],
      nextArrivalId: 1,
      selectedPiece: null,
      drag: null,
      running: false,
      terminal: false,
      busy: false,
      runStartedAt: 0,
      runElapsed: 0,
      runSummary: null,
      raf: null,
      revealedMachines: new Set(),
    };
    window.tomorrowsMarbleModel = model;
    const token = (label) => { try { return helpers.beginAction?.(label); } catch (_error) { return null; } };
    const settle = (action) => { try { action?.settle?.(); } catch (_error) {} };
    const setReadout = (text, status = "idle") => helpers.setReadout(text, status);
    const sourceForInput = interaction === "simplified" ? "timeline_click" : "timeline_drag";

    const tubeMarkup = (state.tubes || []).map((tube, index) => {
      const from = machineByIndex[Number(tube.from_machine_index)]?.position || {x: 0, y: 0};
      const to = machineByIndex[Number(tube.to_machine_index)]?.position || {x: 0, y: 0};
      const midpointX = (Number(from.x) + Number(to.x)) / 2;
      const midpointY = (Number(from.y) + Number(to.y)) / 2 + (index % 2 === 0 ? -46 : 46);
      return `<path class="tm-tube" data-tube="${index}" d="M ${from.x} ${from.y} Q ${midpointX} ${midpointY} ${to.x} ${to.y}"></path><path class="tm-tube-arrow" d="M ${to.x - 8} ${to.y - 5} L ${to.x} ${to.y} L ${to.x - 8} ${to.y + 7}"></path>`;
    }).join("");
    const machineMarkup = machines.map((machine) => {
      const target = machineByIndex[Number(machine.next_machine_index)];
      return `<g class="tm-machine" data-machine-index="${machine.index}" transform="translate(${machine.position.x} ${machine.position.y})"><circle class="tm-machine-halo" r="43"></circle><circle class="tm-machine-body" r="31"></circle><circle class="tm-machine-core" r="12"></circle><text class="tm-machine-glyph" y="6">${esc(machine.glyph)}</text><text class="tm-machine-label" y="58">${esc(machine.name)}</text><text class="tm-machine-rule" y="75">→ ${esc(target?.glyph || "?")} · +${machine.delay} ticks</text><text class="tm-machine-map tm-map-hidden" y="92">STAMP RECORD · —</text></g>`;
    }).join("");
    const pieceMarkup = pieces.map((piece) => {
      const isOrigin = anchors.some((anchor) => Number(anchor.piece_index) === Number(piece.index));
      return `<button type="button" class="tm-piece${isOrigin ? " is-origin-piece" : ""}" data-piece-index="${piece.index}" style="--piece-color:${esc(piece.color)}" aria-label="${esc(piece.name)}${isOrigin ? " · visible origin" : ""}"><span class="tm-piece-glyph">${esc(piece.glyph)}</span><span><b>${esc(piece.name)}</b><small>${isOrigin ? "ORIGIN · " : ""}${esc(piece.id)}</small></span></button>`;
    }).join("");
    const slotHeader = Array.from({length: timelineSlots}, (_value, index) => `<div class="tm-slot-head" data-slot-head="${index}">${String(index).padStart(2, "0")}</div>`).join("");
    const rowMarkup = machines.map((machine) => `<div class="tm-row-label"><b>${esc(machine.glyph)} · ${esc(machine.name)}</b><small>output → ${esc(machineByIndex[Number(machine.next_machine_index)]?.glyph || "?")} / +${machine.delay} ticks</small></div><div class="tm-row-cells" data-row-machine="${machine.index}">${Array.from({length: timelineSlots}, (_value, slot) => { const label = anchorLabel(machine.index, slot); return `<div class="tm-cell${label ? " is-anchor" : ""}" data-machine-index="${machine.index}" data-slot="${slot}" aria-label="${esc(machine.name)} at tick ${slot}${label ? ` · ${label}` : ""}"><span class="tm-origin-label">${esc(label)}</span></div>`; }).join("")}</div>`).join("");

    helpers.app.innerHTML = `<section class="tomorrows-marble mode-${esc(interaction)}" data-mechanic="${MECHANIC_ID}" data-interaction="${esc(interaction)}" data-challenge-id="${esc(state.challenge_id || "")}">
      <header class="tm-header"><div><span class="tm-kicker">CHRONAL WORKSHOP / ${esc(String(state.challenge_id || "").slice(0, 8).toUpperCase())}</span><h1>${PUBLIC_NAME}</h1><p>${esc(state.prompt || "Schedule the arrivals and close the loop.")}</p></div><div class="tm-header-note"><span>INPUT SURFACE</span><b>${interaction === "simplified" ? "TIMELINE SELECT" : "DIRECT MARBLE DRAG"}</b><small>${esc(state.caption || "CAUSAL EVENT TRACE")}</small></div></header>
      <div class="readout tm-readout" data-status="idle" aria-live="polite">READY</div>
      <main class="tm-layout">
        <section class="tm-contraption-panel"><div class="tm-section-head"><span>VISIBLE CONTRAPTION / CAUSAL ROUTE</span><b id="tm-run-clock">IDLE</b></div><svg id="tm-contraption" viewBox="0 0 560 430" role="img" aria-label="Four-machine time contraption"><defs><linearGradient id="tm-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#132c3a"></stop><stop offset="1" stop-color="#1b1731"></stop></linearGradient><filter id="tm-glow"><feGaussianBlur stdDeviation="4" result="b"></feGaussianBlur><feMerge><feMergeNode in="b"></feMergeNode><feMergeNode in="SourceGraphic"></feMergeNode></feMerge></filter></defs><rect width="560" height="430" rx="22" fill="url(#tm-bg)"></rect><path class="tm-orbit" d="M 90 95 Q 280 12 455 78 Q 535 215 448 330 Q 280 432 100 342 Q 22 220 90 95"></path>${tubeMarkup}${machineMarkup}<g id="tm-marble-trace"></g><text class="tm-stage-title" x="24" y="28">CAUSAL EVENT TRACE</text><text class="tm-stage-subtitle" x="24" y="407">event trace · wrapped sparks return to tick 00</text></svg><div class="tm-ledger-box" id="tm-ledger-box"><div class="tm-ledger-title"><span>RUN LEDGER</span><b>TRACE</b></div><div class="tm-ledger-lines" id="tm-ledger-lines">—</div></div></section>
        <aside class="tm-console"><div class="tm-console-head"><span>ARRIVAL PALETTE</span><b id="tm-selected-piece">NO MARBLE SELECTED</b></div><div class="tm-piece-rack">${pieceMarkup}</div><div class="tm-handoff-box"><div><span>HANDOFF STATE</span><b id="tm-handoff-state">STATE 0 · CLEAN</b></div></div><div class="tm-rule-reveal" id="tm-rule-reveal"><span>STAMP RECORD</span><b>—</b></div><section class="tm-timeline"><div class="tm-timeline-top"><span>TIMELINE / ARRIVALS FROM THE FUTURE</span><b id="tm-ledger-count">ARRIVALS</b></div><div class="tm-grid" id="tm-grid" style="--tm-slot-count:${timelineSlots}"><div class="tm-grid-corner">MACHINE</div>${slotHeader}${rowMarkup}</div></section><div class="tm-trash" id="tm-trash">REMOVE</div><div class="tm-action-row"><button type="button" class="tm-clear" id="tm-clear">CLEAR LEDGER</button><button type="button" class="tm-run" id="tm-run">RUN CONTRAPTION <span>↗</span></button><button type="button" class="tm-certify" id="tm-certify">CERTIFY LOOP <span>✓</span></button></div></aside>
      </main><footer class="tm-footer"><span>TIME-MACHINE ACCOUNTING / EVENT TRACE</span><span>TRIAL ${esc(String(state.challenge_id || "").slice(-6).toUpperCase())}</span></footer>
    </section>`;
    const root = helpers.app.querySelector(".tomorrows-marble");
    const grid = root.querySelector("#tm-grid");
    const svg = root.querySelector("#tm-contraption");

    function record(event) {
      model.events.push({seq: model.events.length + 1, ...event});
    }

    function findCell(node) {
      if (!node) return null;
      const cell = node.closest?.(".tm-cell");
      if (!cell || !root.contains(cell)) return null;
      return {machine_index: Number(cell.dataset.machineIndex), slot: Number(cell.dataset.slot)};
    }

    function nodeFor(pieceIndex, machineIndex, slot) {
      return {machine_index: Number(machineIndex), piece_index: Number(pieceIndex), slot: Number(slot)};
    }

    function occupied(node, exceptId = null) {
      return model.schedule.some((arrival) => arrival.id !== exceptId && nodeKey(arrival.node) === nodeKey(node));
    }

    function drawTrace(summary = null, phase = null) {
      const group = root.querySelector("#tm-marble-trace");
      group.innerHTML = "";
      const departures = summary?.departures || [];
      departures.forEach((departure, index) => {
        const source = machineByIndex[Number(departure.source.machine_index)];
        const target = machineByIndex[Number(departure.destination.machine_index)];
        if (!source || !target) return;
        const color = pieceByIndex[Number(departure.source.piece_index)]?.color || "#fff";
        const active = phase == null || index <= phase;
        const cx = (Number(source.position.x) + Number(target.position.x)) / 2;
        const cy = (Number(source.position.y) + Number(target.position.y)) / 2;
        group.insertAdjacentHTML("beforeend", `<circle class="tm-trace-dot${active ? " is-active" : ""}" cx="${cx}" cy="${cy}" r="${active ? 6 : 3}" style="--trace-color:${esc(color)}"></circle>`);
        if (active && departure.returns_to_past) group.insertAdjacentHTML("beforeend", `<text class="tm-past-mark" x="${cx + 10}" y="${cy - 8}">PAST</text>`);
      });
      root.querySelectorAll(".tm-machine").forEach((machineNode) => machineNode.classList.remove("is-live", "is-closed", "is-open"));
      if (phase != null) {
        departures.forEach((departure, index) => {
          if (index > phase) return;
          root.querySelector(`.tm-machine[data-machine-index="${departure.source.machine_index}"]`)?.classList.add("is-live");
          root.querySelector(`.tm-machine[data-machine-index="${departure.destination.machine_index}"]`)?.classList.add("is-live");
        });
      }
      if (summary) {
        root.querySelectorAll(".tm-machine").forEach((machineNode) => machineNode.classList.add(summary.passed ? "is-closed" : "is-open"));
      }
    }

    function paintTimeline() {
      root.querySelectorAll(".tm-cell").forEach((cell) => {
        cell.querySelectorAll(".tm-arrival").forEach((arrival) => arrival.remove());
        cell.classList.remove("has-arrival");
      });
      model.schedule.forEach((arrival) => {
        const cell = root.querySelector(`.tm-cell[data-machine-index="${arrival.node.machine_index}"][data-slot="${arrival.node.slot}"]`);
        if (!cell) return;
        const piece = pieceByIndex[Number(arrival.node.piece_index)] || {};
        const button = document.createElement("button");
        button.type = "button";
        button.className = "tm-arrival";
        button.dataset.arrivalId = arrival.id;
        button.style.setProperty("--piece-color", piece.color || "#fff");
        button.title = `${piece.name || "marble"} · tick ${arrival.node.slot}`;
        button.innerHTML = `<span>${esc(piece.glyph || "?")}</span><small>${esc(piece.id || "?")}</small>`;
        cell.appendChild(button);
        cell.classList.add("has-arrival");
        if (model.interaction === "full") {
          button.addEventListener("pointerdown", (event) => {
            if (model.running || model.terminal) return;
            model.drag = {kind: "existing", id: arrival.id, before: clone(arrival.node), action: token(`marble-reschedule:${arrival.id}`)};
            button.setPointerCapture?.(event.pointerId);
            event.preventDefault();
          });
        } else {
          button.addEventListener("click", () => {
            if (model.running || model.terminal) return;
            // A machine/tick cell can carry distinct marble identities when
            // two causal loops cross.  If another marble is armed, let the
            // click bubble to the cell so it schedules beside the existing
            // pill; with no selection the pill remains the remove control.
            if (model.selectedPiece != null) return;
            const action = token(`marble-remove:${arrival.id}`);
            model.schedule = model.schedule.filter((item) => item.id !== arrival.id);
            model.runSummary = null;
            record({type: "unschedule", input_source: sourceForInput, arrival_id: arrival.id});
            settle(action);
            setReadout("ARRIVAL REMOVED", "idle");
            paint();
          });
        }
      });
      root.querySelector("#tm-ledger-count").textContent = "ARRIVALS";
      root.querySelector("#tm-selected-piece").textContent = model.selectedPiece == null ? "NO MARBLE SELECTED" : `${String(pieceByIndex[model.selectedPiece]?.name || "MARBLE").toUpperCase()} READY`;
      root.querySelectorAll(".tm-piece").forEach((button) => button.classList.toggle("is-selected", Number(button.dataset.pieceIndex) === model.selectedPiece));
    }

    function paintLedger(summary = model.runSummary) {
      const lines = root.querySelector("#tm-ledger-lines");
      const ruleReveal = root.querySelector("#tm-rule-reveal");
      const revealed = [...model.revealedMachines].sort((left, right) => left - right);
      if (!revealed.length) {
        ruleReveal.innerHTML = "<span>STAMP RECORD</span><b>—</b>";
      } else {
        ruleReveal.innerHTML = revealed.map((machineIndex) => {
          const machine = machineByIndex[machineIndex];
          const map = (machine?.piece_map || []).map((pieceIndex, index) => `${esc(pieceByIndex[index]?.glyph || "?")}→${esc(pieceByIndex[pieceIndex]?.glyph || "?")}`).join("  ");
          return `<span>${esc(machine?.glyph || "?")} STAMPS</span><b>${map}</b>`;
        }).join("");
      }
      if (!summary) {
        lines.textContent = "—";
        root.querySelector("#tm-ledger-box").dataset.state = "waiting";
        root.querySelector("#tm-handoff-state").textContent = "STATE 0 · CLEAN";
        root.querySelector("#tm-ledger-box .tm-ledger-title b").textContent = "TRACE";
        return;
      }
      const departureLines = (summary.departures || []).map((departure) => {
        const step = Number((summary.departures || []).indexOf(departure));
        const trace = summary.handoff_trace?.[step];
        const sourceMachine = machineByIndex[Number(departure.source.machine_index)]?.glyph || "?";
        const targetMachine = machineByIndex[Number(departure.destination.machine_index)]?.glyph || "?";
        const piece = pieceByIndex[Number(departure.source.piece_index)]?.glyph || "?";
        const phase = trace ? `${esc(trace.state_label)} ${trace.matched && trace.shift === 0 ? "MATCH" : "SLIP"}` : "NO PHASE";
        return `<div class="tm-ledger-line"><span style="--piece-color:${esc(pieceByIndex[Number(departure.source.piece_index)]?.color || "#fff")}">${esc(piece)}</span><b>${sourceMachine} @ ${String(departure.source.slot).padStart(2, "0")} → ${targetMachine} @ ${String(departure.destination.slot).padStart(2, "0")}</b><em class="${trace?.matched && trace.shift === 0 ? "is-match" : "is-past"}">${phase}</em></div>`;
      }).join("");
      lines.innerHTML = departureLines || "—";
      root.querySelector("#tm-ledger-box").dataset.state = summary.passed ? "closed" : "open";
      const finalMemory = (summary.handoff_final_memory || []).join("");
      root.querySelector("#tm-handoff-state").textContent = summary.handoff_contamination ? `CONTAMINATED · ${finalMemory}` : `STATE ${summary.handoff_trace?.length || 0} · CLEAN`;
      root.querySelector("#tm-ledger-box .tm-ledger-title b").textContent = summary.passed ? "HANDOFF CLOSED" : "HANDOFF OPEN";
    }

    function paint() {
      paintTimeline();
      paintLedger();
      root.querySelector("#tm-run").disabled = model.running || model.terminal || model.schedule.length === 0;
      root.querySelector("#tm-clear").disabled = model.running || model.terminal || model.schedule.length === 0;
      root.querySelector("#tm-certify").disabled = model.running || model.terminal || !model.runSummary;
      drawTrace(model.runSummary, model.running ? Math.floor(model.runElapsed / Math.max(1, Number(state.run_duration_ms)) * Math.max(0, model.schedule.length - 1)) : null);
    }

    function schedulePiece(pieceIndex, location, inputSource) {
      if (model.running || model.terminal || !location) return;
      const node = nodeFor(pieceIndex, location.machine_index, location.slot);
      if (occupied(node)) {
        setReadout("CELL OCCUPIED", "error");
        return;
      }
      const action = model.drag ? null : token(`marble-schedule:${pieceIndex}:${location.machine_index}:${location.slot}`);
      const arrival = {id: `a${model.nextArrivalId++}`, node};
      model.schedule.push(arrival);
      record({type: "schedule", input_source: inputSource, arrival_id: arrival.id, node: clone(node)});
      model.runSummary = null;
      model.selectedPiece = null;
      setReadout(`ARRIVAL PLACED · ${pieceByIndex[pieceIndex]?.name || "MARBLE"}`, "idle");
      settle(action);
      paint();
    }

    function rescheduleArrival(arrivalId, before, location) {
      if (model.running || model.terminal || !location) return;
      const arrival = model.schedule.find((item) => item.id === arrivalId);
      if (!arrival) return;
      const after = nodeFor(arrival.node.piece_index, location.machine_index, location.slot);
      if (occupied(after, arrivalId)) {
        setReadout("CELL OCCUPIED", "error");
        return;
      }
      arrival.node = after;
      record({type: "reschedule", input_source: sourceForInput, arrival_id: arrivalId, before: clone(before), after: clone(after)});
      model.runSummary = null;
      setReadout("ARRIVAL RESCHEDULED", "idle");
      paint();
    }

    function removeArrival(arrivalId, inputSource = sourceForInput) {
      const arrival = model.schedule.find((item) => item.id === arrivalId);
      if (!arrival || model.running || model.terminal) return;
      model.schedule = model.schedule.filter((item) => item.id !== arrivalId);
      record({type: "unschedule", input_source: inputSource, arrival_id: arrivalId});
      model.runSummary = null;
      setReadout("ARRIVAL REMOVED", "idle");
      paint();
    }

    function pointerTarget(event) {
      return document.elementFromPoint(event.clientX, event.clientY);
    }

    root.querySelectorAll(".tm-piece").forEach((button) => {
      const pieceIndex = Number(button.dataset.pieceIndex);
      if (interaction === "simplified") {
        button.addEventListener("click", () => {
          if (model.running || model.terminal) return;
          model.selectedPiece = model.selectedPiece === pieceIndex ? null : pieceIndex;
          setReadout(model.selectedPiece == null ? "SELECTION CLEARED" : "MARBLE SELECTED", "idle");
          paint();
        });
      } else {
        button.addEventListener("pointerdown", (event) => {
          if (model.running || model.terminal) return;
          model.drag = {kind: "new", pieceIndex, action: token(`marble-drag:${pieceIndex}`)};
          button.setPointerCapture?.(event.pointerId);
          setReadout("MARBLE HELD", "idle");
          event.preventDefault();
        });
      }
    });

    root.querySelectorAll(".tm-cell").forEach((cell) => {
      cell.addEventListener("click", () => {
        if (interaction !== "simplified" || model.selectedPiece == null) return;
        schedulePiece(model.selectedPiece, findCell(cell), sourceForInput);
      });
    });

    const pointerUp = (event) => {
      if (!model.drag || model.interaction !== "full") return;
      const drag = model.drag;
      try {
        const target = pointerTarget(event);
        const location = findCell(target);
        if (target?.closest?.("#tm-trash") && drag.kind === "existing") {
          removeArrival(drag.id);
        } else if (location && drag.kind === "new") {
          schedulePiece(drag.pieceIndex, location, sourceForInput);
        } else if (location && drag.kind === "existing") {
          rescheduleArrival(drag.id, drag.before, location);
        } else {
          setReadout("DRAG CANCELLED", "error");
        }
      } finally {
        settle(drag.action);
        model.drag = null;
      }
    };
    const pointerCancel = () => {
      if (!model.drag) return;
      settle(model.drag.action);
      model.drag = null;
      setReadout("DRAG CANCELLED", "error");
    };
    document.addEventListener("pointerup", pointerUp);
    document.addEventListener("pointercancel", pointerCancel);

    root.querySelector("#tm-clear").addEventListener("click", () => {
      if (model.running || model.terminal || !model.schedule.length) return;
      const action = token("marble-clear-ledger");
      model.schedule = [];
      model.runSummary = null;
      record({type: "clear", input_source: "clear_button"});
      setReadout("LEDGER CLEARED", "idle");
      settle(action);
      paint();
    });

    function finishRun() {
      model.running = false;
      if (model.raf) cancelAnimationFrame(model.raf);
      model.runSummary = simulate(model.schedule.map((arrival) => arrival.node), state);
      model.schedule.forEach((arrival) => model.revealedMachines.add(Number(arrival.node.machine_index)));
      record({type: "run", input_source: "run_button", schedule: sortNodes(model.schedule.map((arrival) => arrival.node)), summary: clone(model.runSummary)});
      root.querySelector("#tm-run-clock").textContent = model.runSummary.passed ? "LOOP CLOSED" : "PARADOX OPEN";
      setReadout(model.runSummary.passed ? "RUN COMPLETE · LOOP CLOSED" : "RUN COMPLETE · PARADOX OPEN", model.runSummary.passed ? "passed" : "error");
      paint();
    }

    function runFrame(now) {
      if (!model.running) return;
      const current = Number(helpers.interactionNow?.() ?? now);
      model.runElapsed = Math.max(0, current - model.runStartedAt);
      root.querySelector("#tm-run-clock").textContent = `RUNNING · ${Math.min(99, Math.round(model.runElapsed / Math.max(1, Number(state.run_duration_ms)) * 100))}%`;
      // Replay the visible causal route while the run is in progress.  The
      // final summary is still recorded only when the animation completes;
      // this keeps the moving machine trace observational rather than a
      // hidden precomputed answer.
      const liveSummary = simulate(model.schedule.map((arrival) => arrival.node), state);
      drawTrace(liveSummary, Math.floor(model.runElapsed / Math.max(1, Number(state.run_duration_ms)) * Math.max(0, model.schedule.length - 1)));
      if (model.runElapsed >= Number(state.run_duration_ms)) {
        finishRun();
        return;
      }
      model.raf = requestAnimationFrame(runFrame);
    }

    root.querySelector("#tm-run").addEventListener("click", () => {
      if (model.running || model.terminal || !model.schedule.length) return;
      const action = token("marble-run");
      model.runSummary = null;
      model.running = true;
      model.runStartedAt = Number(helpers.interactionNow?.() ?? performance.now());
      model.runElapsed = 0;
      setReadout("CONTRAPTION RUNNING", "idle");
      settle(action);
      paint();
      model.raf = requestAnimationFrame(runFrame);
    });

    root.querySelector("#tm-certify").addEventListener("click", async () => {
      if (model.busy || model.running || model.terminal || !model.runSummary) return;
      model.busy = true;
      setReadout("CERTIFYING EVENT LEDGER…", "idle");
      const action = token("marble-certify");
      try {
        const response = await fetch("/result", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({mechanic_id: state.mechanic_id, task_id: state.task_id, challenge_id: state.challenge_id, interaction_mode: interaction, completed: true, events: model.events})});
        const outcome = await response.json();
        if (outcome.passed === true) {
          model.terminal = true;
          setReadout("PASS · CAUSAL LEDGER CERTIFIED", "passed");
          root.classList.add("is-passed");
          root.querySelector("#tm-run-clock").textContent = "CERTIFIED";
        } else if (outcome.passed === false && outcome.state) {
          await helpers.render(outcome.state);
          helpers.setReadout("FAIL · FRESH CONTRAPTION ISSUED", "error");
        } else {
          model.busy = false;
          setReadout("CERTIFICATION FAILED", "error");
        }
      } catch (_error) {
        model.busy = false;
        setReadout("CERTIFICATION UNAVAILABLE", "error");
      }
      settle(action);
    });

    paint();
    const cleanup = () => {
      pointerCancel();
      if (model.raf) cancelAnimationFrame(model.raf);
      document.removeEventListener("pointerup", pointerUp);
      document.removeEventListener("pointercancel", pointerCancel);
    };
    window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
    window.WeirdCaptchaMechanics[MECHANIC_ID] = {rootSelector: ".tomorrows-marble", render, cleanup};
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {rootSelector: ".tomorrows-marble", render};
})();
