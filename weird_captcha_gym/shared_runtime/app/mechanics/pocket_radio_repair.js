(() => {
  "use strict";
  const MECHANIC_ID = "pocket_radio_repair";
  const clone = value => JSON.parse(JSON.stringify(value));
  const esc = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  const round = (value, places = 2) => Math.round(Number(value) * 10 ** places) / 10 ** places;

  function shell(state, body, controls, interaction) {
    return `<section class="pocket-radio-repair" data-interaction="${esc(interaction)}">
      <header class="pr-head"><div><span>BENCH NOTE / RESTORATION BAY</span><h1>POCKET RADIO REPAIR</h1></div><p>${esc(state.prompt)}</p></header>
      <main class="pr-main"><div class="pr-scene">${body}</div><aside class="pr-console">${controls}</aside></main>
      <footer class="pr-foot"><div class="readout" data-status="idle">READY · INSPECT THE RADIO</div><div class="pr-foot-note">${esc(state.radio.mat_name)} · ${esc(state.display.model)}</div></footer>
    </section>`;
  }

  function verdict(kind, title, note) {
    return `<div class="pr-verdict is-${kind}"><strong>${esc(title)}</strong><span>${esc(note)}</span></div>`;
  }

  async function submit(model, payload) {
    if (model.submitting) return;
    model.submitting = true;
    model.helpers.setReadout("INDEPENDENT POWER REPLAY…", "pending");
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true;
        model.helpers.setReadout("PASS · RADIO WORKS", "passed");
        model.helpers.app.insertAdjacentHTML("beforeend", verdict("pass", "RADIO RESTORED", "INDICATOR LIT · SPEAKER CONE MOVES · REPAIR ACCEPTED"));
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        model.helpers.app.insertAdjacentHTML("beforeend", verdict("fresh", "FAIL · FRESH RADIO", "THE UNSOLVED BENCH WAS REPLACED"));
        model.helpers.setReadout("FAIL · FRESH RADIO", "error");
        (window.WeirdCaptchaTime?.native?.setTimeout || window.setTimeout)(() => document.querySelector(".pr-verdict.is-fresh")?.remove(), 2200);
      } else {
        model.submitting = false;
        model.helpers.setReadout("FAIL · VERIFIER OFFLINE", "error");
      }
    } catch (_error) {
      model.submitting = false;
      model.helpers.setReadout("FAIL · VERIFIER OFFLINE", "error");
    }
  }

  function render(state, helpers) {
    document.body.dataset.mechanic = MECHANIC_ID;
    const interaction = state.control_condition?.interaction || "full";
    const params = state.control_condition?.difficulty_parameters || {};
    const model = {
      helpers, state, interaction, params, radio: clone(state.radio), selectedTool: null, events: [],
      gesture: null, terminal: false, submitting: false,
    };
    window.pocketRadioRepairModel = model;

    const canvasBody = `<div class="pr-canvas-wrap"><canvas id="pr-canvas" width="900" height="560" aria-label="pocket radio on repair mat"></canvas><div class="pr-legend"><span><i class="dot dot-shell"></i>SHELL</span><span><i class="dot dot-fault"></i>FAULT</span><span><i class="dot dot-fixed"></i>FIXED</span><span><i class="dot dot-tool"></i>TOOLS</span></div></div>`;
    helpers.app.innerHTML = shell(state, canvasBody, `<div id="pr-controls"></div>`, interaction);
    const canvas = document.getElementById("pr-canvas");
    const controls = document.getElementById("pr-controls");

    const cover = id => model.radio.covers.find(item => item.id === id);
    const screw = id => model.radio.screws.find(item => item.id === id);
    const component = id => model.radio.components.find(item => item.id === id);
    const coverAccessible = item => item && !item.installed && model.radio.covers.filter(other => Number(other.layer) < Number(item.layer)).every(other => !other.installed);
    const componentAccessible = item => coverAccessible(cover(item.cover_id));
    const allScrewsOut = item => item && item.screw_ids.every(id => !screw(id).installed);
    const coverCanInstall = item => item && !item.installed && model.radio.covers.filter(other => Number(other.layer) > Number(item.layer)).every(other => other.installed) && model.radio.components.filter(part => part.cover_id === item.id).every(part => part.installed && part.repaired);
    const radioAccepted = () => model.radio.covers.every(item => item.installed) && model.radio.screws.every(item => item.installed) && model.radio.components.every(item => item.installed && item.repaired);
    const setReadout = (message, status = "idle") => helpers.setReadout(message, status);

    function record(type, details = {}) {
      const item = {seq: model.events.length + 1, type, ...details};
      model.events.push(item);
      return item;
    }

    function apply(type, details) {
      if (type === "select_tool" || type === "tool_drag") model.selectedTool = details.tool_id;
      if (type === "loosen_screw" || type === "screw_rotate") { const item = screw(details.screw_id); if (item) item.installed = false; model.selectedTool = details.tool_id; }
      if (type === "open_cover" || type === "lift_cover") { const item = cover(details.cover_id); if (item) item.installed = false; }
      if (type === "clean_component" || type === "clean_gesture") { const item = component(details.component_id); if (item) item.repaired = true; }
      if (type === "replace_component") { const item = component(details.component_id); if (item) { item.installed = true; item.repaired = true; } }
      if (type === "install_cover") { const item = cover(details.cover_id); if (item) item.installed = true; }
      if (type === "install_screw") { const item = screw(details.screw_id); if (item) item.installed = true; model.selectedTool = details.tool_id; }
    }

    function action(type, details = {}, inputSource) {
      if (model.terminal || model.submitting) return;
      const item = record(type, {...details, input_source: inputSource});
      apply(type, item);
      update();
      return item;
    }

    function buttonControls() {
      const toolButtons = model.radio.tools.map(tool => `<button class="pr-tool-btn ${model.selectedTool === tool.id ? "is-selected" : ""}" data-action="select-tool" data-tool-id="${esc(tool.id)}"><b style="color:${esc(tool.color)}">▰</b> ${esc(tool.label)}</button>`).join("");
      const fasteners = model.radio.screws.map(item => {
        const parent = cover(item.cover_id);
        const enabled = parent?.installed && item.installed && model.selectedTool === item.tool_id;
        return `<button class="pr-action" data-action="loosen" data-screw-id="${esc(item.id)}" ${enabled ? "" : "disabled"}>LOOSEN ${esc(item.id)} · ${esc(item.tool_id)}</button>`;
      }).join("");
      const covers = model.radio.covers.map(item => {
        if (item.installed) return `<button class="pr-action" data-action="open" data-cover-id="${esc(item.id)}" ${allScrewsOut(item) && model.radio.covers.filter(other => Number(other.layer) < Number(item.layer)).every(other => !other.installed) ? "" : "disabled"}>LIFT ${esc(item.label)}</button>`;
        return `<button class="pr-action" data-action="install-cover" data-cover-id="${esc(item.id)}" ${coverCanInstall(item) ? "" : "disabled"}>SEAT ${esc(item.label)}</button>`;
      }).join("");
      const parts = model.radio.components.filter(componentAccessible).map(item => {
        if (item.condition === "dirty" && !item.repaired) return `<button class="pr-action" data-action="clean" data-component-id="${esc(item.id)}">CLEAN ${esc(item.label)}</button>`;
        if (item.condition === "missing" && !item.installed) return `<button class="pr-action" data-action="replace" data-component-id="${esc(item.id)}">REPLACE ${esc(item.label)}</button>`;
        return `<div class="pr-note">${esc(item.label)} · ${item.repaired ? "READY" : "INSPECT"}</div>`;
      }).join("");
      const screwsInRebuild = model.radio.screws.filter(item => !item.installed).map(item => `<button class="pr-action" data-action="install-screw" data-screw-id="${esc(item.id)}" ${model.radio.covers.find(coverItem => coverItem.id === item.cover_id)?.installed && model.selectedTool === item.tool_id && model.radio.components.filter(part => part.cover_id === item.cover_id).every(part => part.repaired) ? "" : "disabled"}>FIT ${esc(item.id)} · ${esc(item.tool_id)}</button>`).join("");
      if (interaction === "simplified") {
        controls.innerHTML = `<h2>SELECT A TOOL</h2><div class="pr-tool-list">${toolButtons}</div><h2>FASTENERS</h2><div class="pr-action-list">${fasteners || "<div class=\"pr-note\">No loose fasteners yet.</div>"}</div><h2>ACCESS / REBUILD</h2><div class="pr-action-list">${covers}${parts}${screwsInRebuild || ""}</div><p class="pr-help">Each labelled control is a proxy for the same visible repair action. Work from the outer shell inward, then rebuild from the inside out.</p>`;
      } else {
        controls.innerHTML = `<h2>DIRECT MANIPULATION</h2><div class="pr-selected">TOOL: <b>${esc(model.selectedTool || "NONE")}</b></div><p class="pr-help">Drag a tool onto its matching fastener, then make a circular screwdriver motion. Drag covers, replacement parts, and the cleaning cloth on the mat.</p><div class="pr-status-list"><div>FASTENERS OUT <b>${model.radio.screws.filter(item => !item.installed).length}/${model.radio.screws.length}</b></div><div>COVERS OPEN <b>${model.radio.covers.filter(item => !item.installed).length}/${model.radio.covers.length}</b></div><div>PARTS READY <b>${model.radio.components.filter(item => item.repaired).length}/${model.radio.components.length}</b></div></div>`;
      }
      controls.insertAdjacentHTML("beforeend", `<button id="pr-test" class="pr-primary" data-action="test">⚡ POWER TEST</button><button id="pr-abandon" class="pr-danger" data-action="abandon">ABANDON / FRESH RADIO</button>`);
      controls.querySelectorAll("[data-action]").forEach(node => node.addEventListener("click", () => {
        const kind = node.dataset.action;
        if (kind === "select-tool") action("select_tool", {tool_id: node.dataset.toolId}, "tool_button");
        else if (kind === "loosen") action("loosen_screw", {screw_id: node.dataset.screwId, tool_id: model.selectedTool, turn_degrees: Number(params.screw_turn_degrees || 360)}, "screw_button");
        else if (kind === "open") action("open_cover", {cover_id: node.dataset.coverId}, "cover_button");
        else if (kind === "install-cover") action("install_cover", {cover_id: node.dataset.coverId}, "cover_button");
        else if (kind === "clean") action("clean_component", {component_id: node.dataset.componentId, stroke_count: Number(params.clean_strokes || 1)}, "clean_button");
        else if (kind === "replace") action("replace_component", {component_id: node.dataset.componentId}, "replace_button");
        else if (kind === "install-screw") action("install_screw", {screw_id: node.dataset.screwId, tool_id: model.selectedTool}, "screw_button");
        else if (kind === "test") powerTest();
        else if (kind === "abandon") submit(model, {mechanic_id: state.mechanic_id, task_id: state.task_id, challenge_id: state.challenge_id, events: [...model.events, {seq: model.events.length + 1, type: "abandon"}], completed: false});
      }));
    }

    function point(event) {
      const box = canvas.getBoundingClientRect();
      return {x: (event.clientX - box.left) * 900 / box.width, y: (event.clientY - box.top) * 560 / box.height};
    }
    function nearest(items, predicate, p, position) {
      return items.filter(predicate).map(item => ({item, distance: dist(p, position(item))})).sort((a, b) => a.distance - b.distance)[0]?.item || null;
    }
    function near(a, b, radius = 34) { return Math.hypot(a.x - Number(b.x), a.y - Number(b.y)) <= radius; }
    function pointInRect(p, r) { return p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h; }
    function visibleScrew(item) { return item.installed ? cover(item.cover_id)?.installed : false; }
    function looseScrewPoint(item) { return {x: 770, y: 170 + model.radio.screws.indexOf(item) * 30}; }
    function removedCoverPoint(item) { return {x: 160, y: 115 + Number(item.layer) * 55}; }

    function fullPointerDown(event) {
      if (model.terminal || model.submitting || interaction !== "full") return;
      const p = point(event);
      const tool = model.radio.tools.find(item => pointInRect(p, item));
      if (tool) model.gesture = {kind: "tool", tool, start: p, path: [p]};
      else {
        const targetScrew = nearest(model.radio.screws, item => (visibleScrew(item) || (!item.installed && cover(item.cover_id)?.installed)) && near(p, item.installed ? item : looseScrewPoint(item), 30), p, item => item.installed ? item : looseScrewPoint(item));
        const loose = nearest(model.radio.screws, item => !item.installed && near(p, looseScrewPoint(item), 30), p, item => looseScrewPoint(item));
        const trayPart = model.radio.components.find(item => componentAccessible(item) && item.condition === "missing" && !item.installed && Math.hypot(p.x - item.tray_x, p.y - item.tray_y) <= 36);
        const part = model.radio.components.find(item => componentAccessible(item) && ((item.condition === "dirty" && !item.repaired) || (item.condition === "missing" && !item.installed)) && pointInRect(p, item));
        const installedCover = model.radio.covers.find(item => item.installed && pointInRect(p, item));
        const removedCover = model.radio.covers.find(item => !item.installed && near(p, removedCoverPoint(item), 54));
        if (targetScrew && targetScrew.installed && model.selectedTool === targetScrew.tool_id) model.gesture = {kind: "screw", screw: targetScrew, start: p, path: [p]};
        else if (trayPart) model.gesture = {kind: "replace", part: trayPart, start: p, path: [p]};
        else if (loose) model.gesture = {kind: "install-screw", screw: loose, start: p, path: [p]};
        else if (part) model.gesture = {kind: part.condition === "dirty" ? "clean" : "replace", part, start: p, path: [p]};
        else if (installedCover) model.gesture = {kind: "lift", cover: installedCover, start: p, path: [p]};
        else if (removedCover) model.gesture = {kind: "install-cover", cover: removedCover, start: p, path: [p]};
        else model.gesture = {kind: "orbit", start: p, path: [p]};
      }
      canvas.setPointerCapture(event.pointerId);
      event.preventDefault();
    }
    function fullPointerMove(event) {
      if (!model.gesture || interaction !== "full") return;
      const p = point(event);
      model.gesture.path.push(p);
      event.preventDefault();
    }
    function fullPointerUp(event) {
      const gesture = model.gesture;
      if (!gesture || interaction !== "full") return;
      const end = point(event); gesture.path.push(end); model.gesture = null;
      if (gesture.kind === "tool") {
        const target = nearest(model.radio.screws, item => (visibleScrew(item) || (!item.installed && cover(item.cover_id)?.installed)) && near(end, item.installed ? item : looseScrewPoint(item), 70), end, item => item.installed ? item : looseScrewPoint(item));
        if (target && target.tool_id === gesture.tool.id) action("tool_drag", {tool_id: gesture.tool.id, screw_id: target.id, start: [round(gesture.start.x), round(gesture.start.y)], end: [round(end.x), round(end.y)]}, "tool_drag");
        else setReadout("DRAG THE MATCHING DRIVER TO A FASTENER", "error");
      } else if (gesture.kind === "screw") {
        const turn = Math.max(Number(params.screw_turn_degrees || 360), gesture.path.length * 28);
        action("screw_rotate", {screw_id: gesture.screw.id, tool_id: model.selectedTool, turn_degrees: turn, start: [round(gesture.start.x), round(gesture.start.y)], end: [round(end.x), round(end.y)]}, "screw_rotate");
      } else if (gesture.kind === "lift") {
        if (end.y < gesture.start.y - 18 && allScrewsOut(gesture.cover) && model.radio.covers.filter(item => Number(item.layer) < Number(gesture.cover.layer)).every(item => !item.installed)) action("lift_cover", {cover_id: gesture.cover.id, start: [round(gesture.start.x), round(gesture.start.y)], end: [round(end.x), round(end.y)]}, "cover_drag");
        else setReadout("REMOVE EVERY VISIBLE FASTENER BEFORE LIFTING", "error");
      } else if (gesture.kind === "install-cover") {
        if (coverCanInstall(gesture.cover)) action("install_cover", {cover_id: gesture.cover.id, start: [round(gesture.start.x), round(gesture.start.y)], end: [round(end.x), round(end.y)]}, "cover_drag");
        else setReadout("REPAIR THE EXPOSED PARTS FIRST", "error");
      } else if (gesture.kind === "clean") {
        const length = gesture.path.slice(1).reduce((total, item, index) => total + dist(item, gesture.path[index]), 0);
        if (length >= Number(params.clean_strokes || 1) * 22) action("clean_gesture", {component_id: gesture.part.id, stroke_length: round(length), start: [round(gesture.start.x), round(gesture.start.y)], end: [round(end.x), round(end.y)]}, "clean_gesture");
        else setReadout("SCRUB A LONGER VISIBLE PATH OVER THE GRIME", "error");
      } else if (gesture.kind === "replace") {
        if (end.x < gesture.start.x - 20 || end.y < gesture.start.y - 20) action("replace_component", {component_id: gesture.part.id, start: [round(gesture.start.x), round(gesture.start.y)], end: [round(end.x), round(end.y)]}, "component_drag");
        else setReadout("DRAG THE REPLACEMENT FROM THE TRAY", "error");
      } else if (gesture.kind === "install-screw") {
        const target = screw(gesture.screw.id);
        if (target && cover(target.cover_id)?.installed && near(end, target, 70) && model.selectedTool === target.tool_id) action("install_screw", {screw_id: target.id, tool_id: model.selectedTool, start: [round(gesture.start.x), round(gesture.start.y)], end: [round(end.x), round(end.y)]}, "screw_drag");
        else setReadout("FIT THE LOOSE FASTENER BACK ON ITS MATCHING COVER", "error");
      }
      try { if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId); } catch (_error) {}
    }

    function powerTest() {
      if (model.terminal || model.submitting) return;
      const accepted = radioAccepted();
      action("test", {accepted, covers_ready: model.radio.covers.filter(item => item.installed).length, fasteners_ready: model.radio.screws.filter(item => item.installed).length, parts_ready: model.radio.components.filter(item => item.repaired).length}, "test_button");
      submit(model, {mechanic_id: state.mechanic_id, task_id: state.task_id, challenge_id: state.challenge_id, events: model.events, completed: true});
    }

    function draw() {
      const ctx = canvas.getContext("2d");
      const w = 900, h = 560;
      ctx.clearRect(0, 0, w, h);
      const mat = ctx.createLinearGradient(0, 0, w, h); mat.addColorStop(0, "#243444"); mat.addColorStop(1, "#111b25"); ctx.fillStyle = mat; ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = "rgba(231, 187, 113, .08)"; for (let x = -h; x < w + h; x += 30) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x - h, h); ctx.strokeStyle = "rgba(255,255,255,.035)"; ctx.stroke(); }
      ctx.fillStyle = "#a9c69e"; ctx.font = "800 11px monospace"; ctx.fillText(model.radio.mat_name, 34, 34); ctx.fillStyle = "#778795"; ctx.font = "10px monospace"; ctx.fillText("VISIBLE PARTS · NO AUDIO REQUIRED", 34, 52);
      const body = model.radio.covers.find(item => item.layer === 0)?.installed ? {x: 260, y: 112, w: 430, h: 320} : {x: 260, y: 112, w: 430, h: 320};
      ctx.save(); ctx.shadowColor = "rgba(0,0,0,.55)"; ctx.shadowBlur = 22; ctx.fillStyle = "#cf7d6e"; ctx.beginPath(); ctx.roundRect(body.x, body.y, body.w, body.h, 24); ctx.fill(); ctx.restore();
      ctx.fillStyle = "rgba(26,34,38,.78)"; ctx.beginPath(); ctx.roundRect(302, 174, 346, 194, 20); ctx.fill();
      ctx.fillStyle = "#d6d9bc"; ctx.font = "900 12px Georgia"; ctx.fillText(model.state.display.model, 326, 205);
      ctx.strokeStyle = "#78d7c0"; ctx.lineWidth = 5; ctx.beginPath(); ctx.arc(365, 272, 52, 0, Math.PI * 2); ctx.stroke(); ctx.fillStyle = "#78d7c0"; ctx.font = "10px monospace"; ctx.fillText("TUNING", 337, 348);
      ctx.fillStyle = "#151d22"; ctx.beginPath(); ctx.arc(552, 272, 66, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#e8bc71"; ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(552, 272, 52, 0, Math.PI * 2); ctx.stroke(); ctx.fillStyle = "#e8bc71"; ctx.font = "9px monospace"; ctx.fillText("SPEAKER", 527, 350);
      ctx.fillStyle = "#f4d36c"; ctx.beginPath(); ctx.arc(618, 145, 11, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#8b9784"; ctx.font = "9px monospace"; ctx.fillText("POWER", 596, 169);

      model.radio.components.filter(item => componentAccessible(item)).forEach(item => {
        ctx.save(); ctx.fillStyle = item.repaired ? "rgba(113, 227, 177, .20)" : item.condition === "missing" ? "rgba(255, 113, 102, .20)" : "rgba(245, 193, 102, .22)"; ctx.strokeStyle = item.repaired ? "#71e3b1" : item.condition === "missing" ? "#ff7166" : "#f5c166"; ctx.lineWidth = 3; ctx.beginPath(); ctx.roundRect(item.x, item.y, item.w, item.h, 10); ctx.fill(); ctx.stroke(); ctx.fillStyle = "#edf5ed"; ctx.font = "900 10px monospace"; ctx.fillText(item.label.toUpperCase(), item.x + 8, item.y + 21); ctx.fillStyle = item.repaired ? "#71e3b1" : item.condition === "missing" ? "#ff958b" : "#f5c166"; ctx.font = "800 9px monospace"; ctx.fillText(item.repaired ? "READY" : item.condition === "missing" ? "MISSING · TRAY" : "DIRTY · SCRUB", item.x + 8, item.y + 40); ctx.restore();
      });
      model.radio.covers.forEach(item => {
        if (item.installed) { ctx.save(); ctx.strokeStyle = `rgba(244, 208, 140, ${0.26 + Number(item.layer) * .08})`; ctx.lineWidth = 3; ctx.setLineDash([8, 5]); ctx.beginPath(); ctx.roundRect(item.x, item.y, item.w, item.h, 20); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle = "rgba(244,208,140,.6)"; ctx.font = "800 9px monospace"; ctx.fillText(item.label, item.x + 16, item.y + 23); ctx.restore(); }
        else { const ghost = removedCoverPoint(item); ctx.save(); ctx.strokeStyle = "rgba(228,164,104,.70)"; ctx.lineWidth = 3; ctx.setLineDash([5, 5]); ctx.strokeRect(ghost.x - 52, ghost.y - 18, 104, 36); ctx.setLineDash([]); ctx.fillStyle = "#e4a468"; ctx.font = "800 9px monospace"; ctx.fillText("REMOVED " + item.label, ghost.x - 47, ghost.y + 4); ctx.restore(); }
      });
      model.radio.screws.forEach(item => { const p = item.installed ? {x: item.x, y: item.y} : looseScrewPoint(item); ctx.save(); ctx.fillStyle = item.installed ? "#e4e8e2" : "#e4a468"; ctx.strokeStyle = model.selectedTool === item.tool_id ? "#79e8c1" : "#5b6972"; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(p.x, p.y, item.radius || 20, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); ctx.strokeStyle = "#36444a"; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(p.x - 9, p.y); ctx.lineTo(p.x + 9, p.y); ctx.stroke(); ctx.fillStyle = "#bbc8c4"; ctx.font = "8px monospace"; ctx.fillText(item.id, p.x - 23, p.y + 34); ctx.restore(); });
      ctx.fillStyle = "#667984"; ctx.font = "800 9px monospace"; ctx.fillText("LOOSE FASTENERS", 720, 118);
      model.radio.tools.forEach(item => { ctx.save(); ctx.fillStyle = item.color; ctx.strokeStyle = model.selectedTool === item.id ? "#ffffff" : "rgba(255,255,255,.25)"; ctx.lineWidth = model.selectedTool === item.id ? 3 : 1; ctx.beginPath(); ctx.roundRect(item.x, item.y, item.w, item.h, 9); ctx.fill(); ctx.stroke(); ctx.fillStyle = "#172228"; ctx.font = "800 8px monospace"; ctx.fillText(item.id.toUpperCase(), item.x + 8, item.y + 26); ctx.restore(); });
      ctx.fillStyle = "#667984"; ctx.font = "800 9px monospace"; ctx.fillText("DRIVER TRAY", 44, 540);
      model.radio.components.filter(item => item.condition === "missing" && !item.installed).forEach(item => { ctx.save(); ctx.fillStyle = "rgba(130, 207, 226, .32)"; ctx.strokeStyle = "#82cfe2"; ctx.strokeRect(item.tray_x - 28, item.tray_y - 20, 56, 40); ctx.fillStyle = "#82cfe2"; ctx.font = "800 8px monospace"; ctx.fillText("REPL", item.tray_x - 16, item.tray_y + 3); ctx.restore(); });
      const fixed = model.radio.components.filter(item => item.repaired).length; const all = model.radio.components.length; ctx.fillStyle = "#d8e5df"; ctx.font = "800 11px monospace"; ctx.fillText(`REPAIR LEDGER  ${fixed}/${all} PARTS READY`, 34, 86);
    }

    function update() { draw(); buttonControls(); if (!model.submitting && !model.terminal) setReadout(`${model.radio.components.filter(item => item.repaired).length}/${model.radio.components.length} PARTS READY · ${model.radio.covers.filter(item => !item.installed).length} COVERS OPEN`, "idle"); }
    canvas.addEventListener("pointerdown", fullPointerDown);
    canvas.addEventListener("pointermove", fullPointerMove);
    canvas.addEventListener("pointerup", fullPointerUp);
    canvas.addEventListener("pointercancel", fullPointerUp);
    update();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {rootSelector: ".pocket-radio-repair", render};
})();
