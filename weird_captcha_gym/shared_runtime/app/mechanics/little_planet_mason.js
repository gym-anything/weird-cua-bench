(() => {
  "use strict";

  const STEP = Math.PI / 12;
  const model = {
    state: null,
    interaction: "full",
    selected: null,
    angles: {},
    placed: {},
    events: [],
    busy: false,
    terminal: false,
    drag: null,
    helpers: null,
  };

  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
  const num = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const point = (value) => ({x: num(value?.[0]), y: num(value?.[1])});
  const normalize = (value) => { const tau = 2 * Math.PI; const wrapped = (num(value) + Math.PI) % tau; return ((wrapped + tau) % tau) - Math.PI; };
  const byId = (id) => (model.state?.blocks || []).find((block) => String(block.id) === String(id)) || null;
  const requiredBlocks = () => (model.state?.blocks || []).filter((block) => block.required);
  const svgPoint = (event) => {
    const svg = document.getElementById("planet-mason-svg");
    const rect = svg.getBoundingClientRect();
    return {x: (event.clientX - rect.left) * 900 / rect.width, y: (event.clientY - rect.top) * 520 / rect.height};
  };
  const displayPoint = (event) => svgPoint(event);
  const radialSettle = (block, drop) => {
    const planet = model.state?.planet || {x: 450, y: 258};
    const px = num(planet.x, 450), py = num(planet.y, 258);
    const target = point(block.target);
    const dx = drop.x - px, dy = drop.y - py;
    const radius = Math.hypot(dx, dy);
    const targetRadius = Math.hypot(target.x - px, target.y - py);
    if (radius <= 1e-9) return target;
    return {x: px + dx / radius * targetRadius, y: py + dy / radius * targetRadius};
  };

  function push(kind, blockId, extra = {}) {
    model.events.push({sequence: model.events.length + 1, kind, block_id: String(blockId), ...extra});
  }

  function flash(message, status = "idle") {
    model.helpers?.setReadout(message, status);
    const shell = document.querySelector(".little-planet-mason");
    shell?.classList.remove("is-jolt");
    void shell?.offsetWidth;
    shell?.classList.add("is-jolt");
  }

  function socketMarkup(block) {
    if (!block.required || model.placed[block.id]) return "";
    const [x, y] = block.target;
    const p = point(block.target);
    const [px, py] = [num(model.state.planet.x), num(model.state.planet.y)];
    const dx = px - p.x;
    const dy = py - p.y;
    const length = Math.max(1, Math.hypot(dx, dy));
    const ax = p.x + dx / length * 28;
    const ay = p.y + dy / length * 28;
    return `<g class="planet-socket" data-socket-id="${esc(block.id)}" tabindex="0" aria-label="Landing socket for ${esc(block.label)}">
      <circle cx="${x}" cy="${y}" r="22"/><path d="M ${x} ${y} L ${ax.toFixed(2)} ${ay.toFixed(2)}"/><text x="${x}" y="${y + 4}" text-anchor="middle">${esc(block.id.replace("block-", ""))}</text>
    </g>`;
  }

  function blockMarkup(block, placed = false) {
    const id = esc(block.id);
    const color = esc(block.color);
    const p = placed ? point(block.target) : point(block.palette);
    const angle = placed ? num(model.placed[block.id]?.angle) : num(model.angles[block.id]);
    const cls = placed ? "mason-block placed-block" : `mason-block palette-block${model.selected === block.id ? " is-selected" : ""}`;
    const label = block.required ? block.label.replace("MASON ", "") : "SPARE";
    return `<g class="${cls}" data-block-id="${id}" transform="translate(${p.x} ${p.y}) rotate(${angle * 180 / Math.PI})" tabindex="0" aria-label="${esc(block.label)}">
      <rect x="-19" y="-19" width="38" height="38" rx="3" data-block-hit="true"/>
      <path d="M -12 -12 L 12 -12 M -12 -6 L 12 -6 M -12 0 L 12 0 M -12 6 L 12 6" class="brick-lines"/>
      <text x="0" y="4" text-anchor="middle">${esc(label)}</text>
    </g>`;
  }

  function svgMarkup() {
    const planet = model.state.planet || {x: 450, y: 258, radius: 116};
    const px = num(planet.x), py = num(planet.y), radius = num(planet.radius, 116);
    const sockets = requiredBlocks().map(socketMarkup).join("");
    const placed = requiredBlocks().filter((block) => model.placed[block.id]).map((block) => blockMarkup(block, true)).join("");
    const arrows = requiredBlocks().filter((block) => !model.placed[block.id]).map((block) => {
      const p = point(block.target);
      const dx = px - p.x, dy = py - p.y, length = Math.max(1, Math.hypot(dx, dy));
      return `<path class="gravity-arrow" d="M ${p.x} ${p.y} L ${(p.x + dx / length * 40).toFixed(2)} ${(p.y + dy / length * 40).toFixed(2)}"/>`;
    }).join("");
    return `<svg id="planet-mason-svg" viewBox="0 0 900 520" role="img" aria-label="Tiny planet with radial gravity and landing sockets">
      <defs><radialGradient id="planet-fill"><stop offset="0" stop-color="#e9bd70"/><stop offset=".72" stop-color="#bb7547"/><stop offset="1" stop-color="#773e37"/></radialGradient><pattern id="planet-hatch" width="12" height="12" patternUnits="userSpaceOnUse"><path d="M -2 12 L 12 -2 M 4 16 L 16 4" stroke="#fff1bd" stroke-opacity=".18" stroke-width="2"/></pattern></defs>
      <rect width="900" height="520" class="space-backdrop"/>
      <circle cx="${px}" cy="${py}" r="${radius + 100}" class="atmosphere atmosphere-outer"/><circle cx="${px}" cy="${py}" r="${radius + 65}" class="atmosphere atmosphere-inner"/>
      ${arrows}<circle cx="${px}" cy="${py}" r="${radius}" fill="url(#planet-fill)" class="planet-body"/><circle cx="${px}" cy="${py}" r="${radius}" fill="url(#planet-hatch)" class="planet-hatch"/>
      <text x="${px}" y="${py + 6}" text-anchor="middle" class="planet-name">LITTLE PLANET</text>
      ${sockets}${placed}
      <text x="${px}" y="${py + radius + 127}" text-anchor="middle" class="gravity-caption">↓ arrows point toward the planet's centre · place support-first</text>
      ${(model.state.blocks || []).map((block) => blockMarkup(block, false)).join("")}
    </svg>`;
  }

  function missionMarkup() {
    const required = requiredBlocks();
    return required.map((block, index) => {
      const done = Boolean(model.placed[block.id]);
      return `<li class="mission-row ${done ? "is-done" : ""}"><span>${done ? "✓" : String(index + 1).padStart(2, "0")}</span><b>${esc(block.label)}</b><small>${esc(block.support === "planet" ? "planet support" : `rests on ${block.support}`)}</small></li>`;
    }).join("");
  }

  function renderBoard() {
    const root = document.querySelector(".little-planet-mason");
    if (!root) return;
    const placedCount = Object.keys(model.placed).length;
    const total = requiredBlocks().length;
    const angle = model.selected ? Math.round(num(model.angles[model.selected]) * 180 / Math.PI) : 0;
    const selectedLabel = model.selected ? byId(model.selected)?.label : "NONE";
    root.querySelector("#planet-mason-stage").innerHTML = svgMarkup();
    root.querySelector("#planet-mason-mission").innerHTML = missionMarkup();
    root.querySelector("#planet-mason-count").textContent = `${placedCount} / ${total}`;
    root.querySelector("#planet-mason-selected").textContent = selectedLabel || "NONE";
    root.querySelector("#planet-mason-angle").textContent = `${angle}°`;
    const certify = root.querySelector("#planet-mason-certify");
    if (certify) certify.disabled = model.busy || model.terminal;
    bindStage();
  }

  function select(blockId) {
    if (model.busy || model.terminal) return;
    const block = byId(blockId);
    if (!block || model.placed[block.id]) return;
    if (model.interaction !== "simplified") return;
    model.selected = block.id;
    push("select", block.id, {input_source: "tray_select"});
    flash(`${block.label} SELECTED · CHOOSE ITS SOCKET`, "idle");
    renderBoard();
  }

  function rotate(blockId, source) {
    if (model.busy || model.terminal) return;
    const block = byId(blockId);
    if (!block || model.placed[block.id]) return;
    if (model.interaction === "simplified" && source !== "rotate_button") return;
    if (model.interaction === "full" && source !== "block_right_click") return;
    const before = num(model.angles[block.id]);
    const delta = source === "rotate_button" && model.pendingRotation === "left" ? -STEP : STEP;
    const after = normalize(before + delta);
    model.angles[block.id] = after;
    push("rotate", block.id, {input_source: source, delta, angle_before: before, angle_after: after});
    flash(`${block.label} ROTATED · ${Math.round(after * 180 / Math.PI)}°`, "idle");
    renderBoard();
  }

  function settle(blockId, drop, source) {
    const block = byId(blockId);
    if (!block || model.busy || model.terminal || model.placed[block.id]) return;
    if (model.interaction === "simplified" && source !== "socket_click") return;
    if (model.interaction === "full" && source !== "direct_drag") return;
    const target = point(block.target);
    const recordedDrop = {x: Number(drop.x.toFixed(4)), y: Number(drop.y.toFixed(4))};
    const settled = radialSettle(block, recordedDrop);
    const recordedSettled = {x: Number(settled.x.toFixed(4)), y: Number(settled.y.toFixed(4))};
    const supportReady = block.support === "planet" || Boolean(model.placed[block.support]);
    const tolerance = num(model.state.requirements?.placement_tolerance, 20);
    const closeEnough = Math.hypot(recordedSettled.x - target.x, recordedSettled.y - target.y) <= tolerance;
    const targetAngle = num(block.target_angle);
    const oriented = Math.abs(normalize(num(model.angles[block.id]) - targetAngle)) <= num(model.state.requirements?.angle_tolerance, .2);
    if (!supportReady || !closeEnough || !oriented) {
      flash(!supportReady ? "NO SUPPORT YET · BUILD FROM THE PLANET OUTWARD" : !oriented ? "FACE MISALIGNED · ROTATE WITH RADIAL GRAVITY" : "BLOCK DRIFTED · RELEASE INSIDE THE MARKED SOCKET", "error");
      return;
    }
    model.placed[block.id] = {x: recordedSettled.x, y: recordedSettled.y, angle: num(model.angles[block.id]), support: block.support};
    push("place", block.id, {input_source: source, drop: [recordedDrop.x, recordedDrop.y], settled: [recordedSettled.x, recordedSettled.y], angle: num(model.angles[block.id]), support: block.support, accepted: true});
    model.selected = null;
    flash(`${block.label} SETTLED · SUPPORT ${String(block.support).toUpperCase()}`, "passed");
    renderBoard();
  }

  function bindStage() {
    const stage = document.getElementById("planet-mason-stage");
    if (!stage) return;
    stage.querySelectorAll(".palette-block").forEach((node) => {
      node.addEventListener("click", () => select(node.dataset.blockId));
      node.addEventListener("contextmenu", (event) => { event.preventDefault(); rotate(node.dataset.blockId, "block_right_click"); });
      node.addEventListener("pointerdown", (event) => {
        if (model.interaction !== "full" || event.button !== 0 || model.busy || model.terminal) return;
        event.preventDefault();
        const p = displayPoint(event);
        model.drag = {id: node.dataset.blockId, pointerId: event.pointerId, offset: {x: p.x - num(byId(node.dataset.blockId)?.palette?.[0]), y: p.y - num(byId(node.dataset.blockId)?.palette?.[1])}};
        node.setPointerCapture?.(event.pointerId);
        stage.classList.add("is-dragging");
      });
      node.addEventListener("pointermove", (event) => {
        if (!model.drag || model.drag.id !== node.dataset.blockId) return;
        const p = displayPoint(event);
        node.setAttribute("transform", `translate(${p.x - model.drag.offset.x} ${p.y - model.drag.offset.y}) rotate(${num(model.angles[node.dataset.blockId]) * 180 / Math.PI})`);
      });
      node.addEventListener("pointerup", (event) => {
        if (!model.drag || model.drag.id !== node.dataset.blockId) return;
        const p = displayPoint(event);
        model.drag = null; stage.classList.remove("is-dragging");
        settle(node.dataset.blockId, p, "direct_drag");
      });
    });
    stage.querySelectorAll(".planet-socket").forEach((node) => node.addEventListener("click", () => {
      if (model.interaction !== "simplified" || !model.selected) return;
      const block = byId(model.selected);
      settle(model.selected, point(block?.target), "socket_click");
    }));
  }

  function reset() {
    if (model.busy) return;
    model.selected = null; model.angles = {}; model.placed = {}; model.events = []; model.terminal = false;
    (model.state.blocks || []).forEach((block) => { model.angles[block.id] = 0; });
    flash("ATTEMPT RESET · SUPPORTS CLEARED", "idle");
    renderBoard();
  }

  async function submit() {
    if (!model.state || model.busy || model.terminal) return;
    model.busy = true; renderBoard();
    const complete = Object.keys(model.placed).length === requiredBlocks().length;
    flash(complete ? "CERTIFYING STRUCTURE…" : "CERTIFYING INCOMPLETE STRUCTURE…", "pending");
    const payload = {mechanic_id: model.state.mechanic_id, task_id: model.state.task_id, challenge_id: model.state.challenge_id, interaction_mode: model.interaction, events: model.events, completed: complete};
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true; model.busy = false;
        document.querySelector(".little-planet-mason")?.classList.add("is-pass");
        flash("PASS · STRUCTURE HOLDS", "passed");
      } else if (outcome.state) {
        await model.helpers.render(outcome.state, model.helpers);
        document.querySelector(".little-planet-mason")?.classList.add("is-fail");
        flash("FAIL · NEW PLANET DRAWN", "error");
      } else {
        model.busy = false; renderBoard(); flash("FAIL · STRUCTURE REJECTED", "error");
      }
    } catch (_error) {
      model.busy = false; renderBoard(); flash("FAIL · REGISTER OFFLINE", "error");
    }
  }

  function markup(state) {
    const mode = model.interaction;
    const controls = mode === "simplified"
      ? `<div class="mason-buttons"><button id="planet-mason-left" type="button">↺ TURN LEFT</button><button id="planet-mason-right" type="button">TURN RIGHT ↻</button></div><p class="control-copy">Select a tray block, nudge its face, then click its numbered landing socket.</p>`
      : `<p class="control-copy"><b>DIRECT HANDS</b><br>Drag a masonry block around the planet. Right-click a tray block to rotate it by 15° before the release.</p>`;
    return `<section class="little-planet-mason">
      <header class="mason-header"><div><span class="mason-eyebrow">CELESTIAL WORKS · RADIAL GRAVITY</span><h1>Little Planet Mason</h1><p>Build a stable ring where “down” always points to the centre.</p></div><div class="mason-badge">STRUCTURE<br><b>LIVE REGISTER</b></div></header>
      <div class="mason-layout"><main><div class="mason-stage-label"><span>ORBITAL WORKBENCH</span><span>GRAVITY VECTOR: CENTREWARD</span></div><div id="planet-mason-stage" class="mason-stage"></div><div class="mason-tray-label">BLOCK TRAY · ${mode === "full" ? "DIRECT DRAG SURFACE" : "SELECT SURFACE"}</div></main>
        <aside class="mason-side"><section class="mason-card mission-card"><div class="card-kicker">SUPPORT MAP <span id="planet-mason-count">0 / 0</span></div><ol id="planet-mason-mission"></ol></section><section class="mason-card control-card"><div class="card-kicker">${mode === "full" ? "FULL HAND" : "SIMPLIFIED HAND"}</div>${controls}<div class="selected-readout">SELECTED <b id="planet-mason-selected">NONE</b><span>ANGLE <b id="planet-mason-angle">0°</b></span></div></section><section class="mason-card rule-card"><div class="card-kicker">RADIAL RULE</div><p>Each face must meet the support below it. A block placed changes the next available support.</p><div class="rule-diagram">↙ &nbsp; ◉ &nbsp; ↗<small>all arrows converge here</small></div></section></aside></div>
      <footer class="mason-footer"><button id="planet-mason-reset" type="button">RESET ATTEMPT</button><div class="readout" data-status="idle">READ THE SUPPORTS · BUILD OUTWARD</div><button id="planet-mason-certify" type="button">CERTIFY STRUCTURE</button></footer>
    </section>`;
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "little_planet_mason";
    if (model.state?.mechanic_id !== state.mechanic_id) model.angles = {};
    model.state = state; model.helpers = helpers; model.interaction = String((state.control_condition || {}).interaction || "full");
    model.selected = null; model.placed = {}; model.events = []; model.busy = false; model.terminal = false; model.drag = null;
    (state.blocks || []).forEach((block) => { model.angles[block.id] = 0; });
    helpers.app.innerHTML = markup(state);
    document.getElementById("planet-mason-reset")?.addEventListener("click", reset);
    document.getElementById("planet-mason-certify")?.addEventListener("click", submit);
    document.getElementById("planet-mason-left")?.addEventListener("click", () => { model.pendingRotation = "left"; if (model.selected) rotate(model.selected, "rotate_button"); model.pendingRotation = null; });
    document.getElementById("planet-mason-right")?.addEventListener("click", () => { model.pendingRotation = "right"; if (model.selected) rotate(model.selected, "rotate_button"); model.pendingRotation = null; });
    renderBoard();
    window.littlePlanetMasonModel = model;
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.little_planet_mason = {rootSelector: ".little-planet-mason", render};
})();
