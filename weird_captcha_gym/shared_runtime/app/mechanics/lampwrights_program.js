(() => {
  "use strict";

  const COMMAND_LABELS = {F: "FORWARD", L: "LEFT", R: "RIGHT", J: "JUMP", G: "LIGHT", A: "AMBER", B: "BLUE"};
  const DIRS = [[1, 0], [0, 1], [-1, 0], [0, -1]];
  let model = null;

  const esc = (value) => String(value == null ? "" : value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const key = (x, y) => `${x},${y}`;
  const copy = (value) => JSON.parse(JSON.stringify(value));

  function posePoint(pose) {
    const x = Number(pose.x || 0), y = Number(pose.y || 0), z = Number(pose.height || 0);
    return [380 + (x - y) * 32, 175 + (x + y) * 16 - z * 24];
  }

  function projectBlock(block) {
    const x = Number(block.x), y = Number(block.y), z = Number(block.height || 0);
    const [cx, cy] = posePoint({x, y, height: z});
    const top = [[cx, cy - 15], [cx + 31, cy], [cx, cy + 15], [cx - 31, cy]];
    const bottom = 26 * (z + 1);
    return {cx, cy, top, left: [[cx - 31, cy], [cx, cy + 15], [cx, cy + 15 + bottom], [cx - 31, cy + bottom]], right: [[cx, cy + 15], [cx + 31, cy], [cx + 31, cy + bottom], [cx, cy + 15 + bottom]]};
  }

  function points(values) { return values.map((point) => point.join(",")).join(" "); }

  function worldMarkup() {
    const world = model.state.world;
    const targets = new Map((world.targets || []).map((item) => [key(item.x, item.y), item]));
    const blocks = [...(world.blocks || [])].sort((a, b) => Number(a.x) + Number(a.y) - Number(b.x) - Number(b.y));
    const markup = blocks.map((block) => {
      const shape = projectBlock(block);
      const target = targets.get(key(block.x, block.y));
      const lit = target && model.lit.has(key(block.x, block.y));
      return `<g class="lp-block ${target ? "has-lamp" : ""} ${lit ? "is-lit" : ""}" data-block="${esc(block.id)}"><polygon class="lp-side lp-left" points="${points(shape.left)}"></polygon><polygon class="lp-side lp-right" points="${points(shape.right)}"></polygon><polygon class="lp-top" points="${points(shape.top)}"></polygon>${target ? `<circle class="lp-lamp" cx="${shape.cx}" cy="${shape.cy - 7}" r="7"></circle><text class="lp-lamp-label" x="${shape.cx}" y="${shape.cy - 4}">${esc(String((world.targets || []).indexOf(target) + 1))}</text>` : ""}</g>`;
    }).join("");
    const pose = model.pose || world.start;
    const [rx, ry] = posePoint(pose);
    const angle = Number(pose.heading || 0) * 90;
    const robot = `<g class="lp-robot" transform="translate(${rx} ${ry - 20}) rotate(${angle})"><ellipse cx="0" cy="16" rx="18" ry="6"></ellipse><rect x="-13" y="-4" width="26" height="22" rx="7"></rect><circle cx="-6" cy="4" r="3"></circle><circle cx="6" cy="4" r="3"></circle><path d="M0 -4 L0 -15 M0 -15 L7 -9" /></g>`;
    return `${markup}${robot}`;
  }

  function renderWorld() {
    const svg = document.querySelector("#lp-world");
    if (svg) svg.innerHTML = `<rect class="lp-sky" x="0" y="0" width="760" height="470"></rect><path class="lp-horizon" d="M0 286 Q180 232 370 278 T760 260 V470 H0 Z"></path>${worldMarkup()}<text class="lp-start-label" x="24" y="438">ROOFTOP SECTOR / ${esc(model.state.challenge_id)}</text>`;
    const count = document.querySelector("#lp-lamp-count");
    if (count) count.textContent = `${model.lit.size}/${model.state.world.targets.length}`;
  }

  function panelMarkup(panel) {
    const limit = Number(model.state.program_limits[panel] || 0);
    const slots = model.program[panel] || [];
    return `<div class="lp-routine-head"><span>${panel === "main" ? "MAIN PROCEDURE" : `${panel === "A" ? "AMBER" : "BLUE"} ROUTINE`}</span><em>${slots.length}/${limit}</em></div><div class="lp-slots" data-panel="${panel}">${Array.from({length: limit}, (_, index) => `<button class="lp-slot ${slots[index] ? "filled" : "empty"}" type="button" draggable="${Boolean(slots[index])}" data-panel="${panel}" data-index="${index}" aria-label="${panel} slot ${index + 1}">${esc(slots[index] || "·")}</button>`).join("")}</div>`;
  }

  function renderProgram() {
    document.querySelector("#lp-routines").innerHTML = ["main", "A", "B"].map(panelMarkup).join("");
    installSlots();
  }

  function setStatus(message, kind = "idle") {
    const status = document.querySelector("#lp-status");
    if (status) { status.textContent = message; status.dataset.kind = kind; }
    model.helpers.setReadout(message, kind === "pass" ? "passed" : kind === "error" ? "error" : "idle");
  }

  function edit(panel, index, command, source) {
    if (!model || model.playing || model.submitting) return;
    model.program[panel][index] = command;
    model.editorEvents.push({type: "place", panel, index, command, input_source: source});
    renderProgram();
    setStatus(`${COMMAND_LABELS[command]} placed in ${panel === "main" ? "MAIN" : panel} / SLOT ${index + 1}`);
  }

  function clearSlot(panel, index, source) {
    if (!model || model.playing || model.submitting || !model.program[panel][index]) return;
    model.editorEvents.push({type: "erase", panel, index, command: model.program[panel][index], input_source: source});
    model.program[panel][index] = null;
    renderProgram();
    setStatus("SLOT CLEARED");
  }

  function reorderSlot(fromPanel, fromIndex, toPanel, toIndex) {
    if (!model || model.playing || model.submitting) return;
    const sourceSlots = model.program[fromPanel] || [];
    const targetSlots = model.program[toPanel] || [];
    const sourceCommand = sourceSlots[fromIndex];
    if (!sourceCommand || fromPanel === undefined || toPanel === undefined) return;
    if (fromPanel === toPanel && fromIndex === toIndex) return;
    const targetCommand = targetSlots[toIndex] || null;
    sourceSlots[fromIndex] = targetCommand;
    targetSlots[toIndex] = sourceCommand;
    model.editorEvents.push({
      type: "reorder",
      from_panel: fromPanel,
      from_index: fromIndex,
      to_panel: toPanel,
      to_index: toIndex,
      from_command: sourceCommand,
      to_command: targetCommand,
      input_source: "drag_drop",
    });
    renderProgram();
    setStatus(`${COMMAND_LABELS[sourceCommand]} moved to ${toPanel === "main" ? "MAIN" : toPanel} / SLOT ${toIndex + 1}`);
  }

  function installSlots() {
    document.querySelectorAll(".lp-slot").forEach((slot) => {
      slot.addEventListener("click", () => {
        if (model.interaction === "full") return;
        if (model.selectedCommand) { edit(slot.dataset.panel, Number(slot.dataset.index), model.selectedCommand, "palette_click"); model.selectedCommand = null; document.querySelectorAll(".lp-token").forEach((node) => node.removeAttribute("data-selected")); }
        else clearSlot(slot.dataset.panel, Number(slot.dataset.index), "palette_click");
      });
      slot.addEventListener("dragover", (event) => { if (model.interaction === "full") event.preventDefault(); });
      slot.addEventListener("drop", (event) => {
        if (model.interaction !== "full") return;
        event.preventDefault();
        let command = event.dataTransfer.getData("text/plain");
        if (command.startsWith("slot:")) {
          const [, fromPanel, fromIndex] = command.split(":");
          reorderSlot(fromPanel, Number(fromIndex), slot.dataset.panel, Number(slot.dataset.index));
          return;
        }
        if (COMMAND_LABELS[command]) edit(slot.dataset.panel, Number(slot.dataset.index), command, "drag_drop");
      });
      slot.addEventListener("dragstart", (event) => { if (model.interaction === "full" && slot.textContent !== "·") event.dataTransfer.setData("text/plain", `slot:${slot.dataset.panel}:${slot.dataset.index}`); });
    });
  }

  function installPalette() {
    document.querySelectorAll(".lp-token").forEach((token) => {
      token.addEventListener("click", () => {
        if (model.interaction !== "simplified") return;
        model.selectedCommand = token.dataset.command;
        document.querySelectorAll(".lp-token").forEach((node) => node.removeAttribute("data-selected"));
        token.dataset.selected = "true";
        setStatus(`SELECTED ${COMMAND_LABELS[model.selectedCommand]} — choose a slot`);
      });
      token.addEventListener("dragstart", (event) => { if (model.interaction === "full") event.dataTransfer.setData("text/plain", token.dataset.command); });
    });
  }

  function terrainMap() {
    return new Map((model.state.world.blocks || []).map((block) => [key(block.x, block.y), Number(block.height || 0)]));
  }

  function evaluate() {
    const terrain = terrainMap();
    const targetKeys = new Set((model.state.world.targets || []).map((item) => key(item.x, item.y)));
    const lit = new Set(), steps = [];
    const pose = copy(model.state.world.start);
    const dirs = DIRS;
    const stack = [["main", 0, 0]];
    let blocked = "", safety = 0;
    while (stack.length && safety < 400) {
      const frame = stack.pop(); const routine = frame[0]; let index = frame[1]; const depth = frame[2];
      const commands = (model.program[routine] || []).filter(Boolean);
      while (index < commands.length) {
        const command = commands[index++]; safety += 1;
        if (command === "A" || command === "B") { if (depth >= 4) { blocked = "PROCEDURE NESTING TOO DEEP"; break; } stack.push([routine, index, depth]); stack.push([command, 0, depth + 1]); break; }
        const before = copy(pose);
        if (command === "L") pose.heading = (pose.heading + 3) % 4;
        else if (command === "R") pose.heading = (pose.heading + 1) % 4;
        else if (command === "F" || command === "J") {
          const [dx, dy] = dirs[pose.heading]; const nx = pose.x + dx, ny = pose.y + dy; const nextKey = key(nx, ny);
          if (!terrain.has(nextKey)) { blocked = `${command} WOULD LEAVE THE ROOFTOP`; break; }
          const delta = terrain.get(nextKey) - pose.height;
          if ((command === "F" && delta !== 0) || (command === "J" && Math.abs(delta) !== 1)) { blocked = `${command} BLOCKED BY HEIGHT ${terrain.get(nextKey)}`; break; }
          pose.x = nx; pose.y = ny; pose.height = terrain.get(nextKey);
        } else if (command === "G") {
          const current = key(pose.x, pose.y); if (!targetKeys.has(current)) { blocked = "LIGHT COMMAND MISSED A MARKED TILE"; break; } lit.add(current);
        } else { blocked = "UNKNOWN INSTRUCTION"; break; }
        steps.push({routine, command, before, after: copy(pose), lit: [...lit]});
      }
      if (blocked) break;
    }
    if (!blocked && stack.length) blocked = "PROGRAM EXCEEDED THE EXECUTION BOUND";
    if (!blocked && lit.size !== targetKeys.size) blocked = `PROGRAM ENDED WITH ${lit.size}/${targetKeys.size} LAMPS LIT`;
    return {ok: !blocked, message: blocked || "ALL ROOFTOP LAMPS LIT", steps, pose, lit};
  }

  function runProgram() {
    if (model.playing || model.submitting) return;
    model.runId += 1; model.lit = new Set(); model.pose = copy(model.state.world.start); renderWorld();
    const result = evaluate();
    const runId = model.runId;
    model.executionEvents.push({type: "run_start", run_id: runId});
    result.steps.forEach((step, index) => model.executionEvents.push({type: "step", run_id: runId, index, routine: step.routine, command: step.command, before: step.before, after: step.after, lit: step.lit}));
    if (result.ok) { model.executionEvents.push({type: "run_complete", run_id: runId}); model.completed = true; }
    else model.executionEvents.push({type: "blocked", run_id: runId, message: result.message});
    model.playing = true; model.playback = result.steps; model.playbackIndex = 0; model.playbackResult = result;
    setStatus("EXECUTING PROGRAM…");
    const tick = () => {
      if (!model || !model.playing || model.runId !== runId) return;
      if (model.playbackIndex >= model.playback.length) {
        model.playing = false; model.pose = result.pose; model.lit = result.lit; renderWorld();
        const certify = document.querySelector("#lp-certify"); if (certify) certify.disabled = !model.completed;
        if (result.ok) setStatus("ROUTE COMPLETE — CERTIFY WHEN READY", "pass"); else setStatus(result.message, "error");
        return;
      }
      const step = model.playback[model.playbackIndex++]; model.pose = step.after; model.lit = new Set(step.lit); renderWorld();
      setTimeout(tick, 150);
    };
    tick();
  }

  async function submit() {
    if (!model || model.playing || model.submitting || !model.completed) return;
    model.submitting = true; setStatus("REPLAYING PROGRAM INDEPENDENTLY…");
    const payload = {mechanic_id: model.state.mechanic_id, task_id: model.state.task_id, challenge_id: model.state.challenge_id, program: Object.fromEntries(Object.entries(model.program).map(([panel, slots]) => [panel, slots.filter(Boolean)])), editor_events: model.editorEvents, execution_events: model.executionEvents, completed: true};
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) { setStatus("PASS — ROOFTOP LIT", "pass"); model.helpers.setReadout("PASS", "passed"); document.querySelector(".lp-shell")?.classList.add("is-passed"); }
      else if (outcome.state) { await render(outcome.state, model.helpers); setStatus("FAIL — FRESH ROOFTOP", "error"); }
      else { model.submitting = false; setStatus("CERTIFICATION REJECTED", "error"); }
    } catch (_error) { model.submitting = false; setStatus("SERVER UNAVAILABLE", "error"); }
  }

  async function render(state, helpers) {
    model = {state, helpers, interaction: state.control_condition?.interaction || "full", program: {main: Array(Number(state.program_limits.main || 0)).fill(null), A: Array(Number(state.program_limits.A || 0)).fill(null), B: Array(Number(state.program_limits.B || 0)).fill(null)}, selectedCommand: null, editorEvents: [], executionEvents: [], runId: 0, pose: copy(state.world.start), lit: new Set(), playing: false, completed: false, submitting: false};
    window.lampwrightsProgramModel = model;
    document.body.dataset.mechanic = "lampwrights-program";
    helpers.app.innerHTML = `<section class="lp-shell" data-interaction="${esc(model.interaction)}"><header class="lp-head"><div><span>LAMPWRIGHT'S PROGRAM / ISOMETRIC ROOFTOP</span><h1>${esc(state.prompt)}</h1><p>Read the stepped blocks. Build a reusable route, then watch the robot execute it.</p></div><div class="lp-counter"><small>LAMPS</small><b id="lp-lamp-count">0/${state.world.targets.length}</b></div></header><main class="lp-layout"><section class="lp-world-card"><div class="lp-card-label">LIVE ROOFTOP MAP · HEIGHTS ARE REAL</div><svg id="lp-world" viewBox="0 0 760 470" role="img" aria-label="Isometric rooftop map"></svg><div class="lp-legend"><span><i class="legend-lamp"></i> unlit target</span><span><i class="legend-block"></i> stepped block</span><span><i class="legend-robot"></i> robot heading</span></div></section><aside class="lp-console"><div class="lp-card-label">ICON EDITOR · ${model.interaction === "full" ? "DRAG INTO A SLOT" : "SELECT THEN PLACE"}</div><div class="lp-palette" aria-label="instruction palette">${Object.keys(COMMAND_LABELS).map((command) => `<button class="lp-token" draggable="${model.interaction === "full"}" type="button" data-command="${command}" aria-label="${COMMAND_LABELS[command]}"><b>${command}</b><span>${COMMAND_LABELS[command]}</span></button>`).join("")}</div><div id="lp-routines" class="lp-routines"></div><div class="lp-actions"><button id="lp-run" type="button">RUN PROGRAM</button><button id="lp-certify" type="button" disabled>CERTIFY</button></div><div id="lp-status" class="lp-status" data-kind="idle">PROGRAM READY</div><div class="readout" data-status="idle">PROGRAM READY</div><p class="lp-hint">F climbs no height. J crosses one visible step. A and B reuse the same routine from a new heading.</p></aside></main><footer class="lp-foot"><span>ORDINARY INPUT ONLY · EDIT, RUN, OBSERVE, REVISE</span><span>ROUTE LICENSE ${esc(state.challenge_id)}</span></footer></section>`;
    renderProgram(); installPalette(); renderWorld();
    document.querySelector("#lp-run").addEventListener("click", runProgram);
    document.querySelector("#lp-certify").addEventListener("click", submit);
    const observer = new MutationObserver(() => { const button = document.querySelector("#lp-certify"); if (button) button.disabled = !model.completed || model.playing || model.submitting; });
    observer.observe(document.querySelector(".lp-shell"), {subtree: true, childList: true});
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.lampwrights_program = {rootSelector: ".lp-shell", render};
})();
