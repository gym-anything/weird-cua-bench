(() => {
  "use strict";

  const registry = window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  const esc = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const vectors = {north: [0, -1], east: [1, 0], south: [0, 1], west: [-1, 0]};
  const arrows = {north: "↑", east: "→", south: "↓", west: "←"};
  const copy = (value) => JSON.parse(JSON.stringify(value));
  let model = null;
  let cleanup = null;

  function conditionInteraction(state) {
    return String(state.control_condition?.interaction || "simplified");
  }

  function tileMap(course) {
    return new Map((course.tiles || []).map((tile) => [`${Number(tile.x)},${Number(tile.y)}`, tile]));
  }

  function stateSnapshot() {
    const tile = model.tiles.get(`${model.ball.x},${model.ball.y}`);
    return {x: model.ball.x, y: model.ball.y, z: model.ball.z, surface: String(tile?.surface || ""), used_card_ids: [...model.used]};
  }

  function transition(before, card, direction) {
    const vector = vectors[direction];
    if (!vector) return {error: "DIRECTION UNKNOWN"};
    const kind = String(card.kind || "");
    const distance = Number(card.distance);
    if (!Number.isInteger(distance) || distance < 1 || distance > 3) return {error: "CARD RULE INVALID"};
    const rules = model.state.course.rules || {};
    let x = Number(before.x), y = Number(before.y), z = Number(before.z);
    const originX = x, originY = y;
    if (kind === "roll") {
      if (before.surface === "sand" && distance > Number(rules.sand_roll_limit || 1)) return {error: "SAND STOPS A LONG ROLL"};
      for (let offset = 1; offset <= distance; offset += 1) {
        const tile = model.tiles.get(`${originX + vector[0] * offset},${originY + vector[1] * offset}`);
        if (!tile || tile.surface === "water") return {error: "A ROLL CANNOT CROSS WATER"};
        const nextZ = Number(tile.z), heightChange = nextZ - z;
        if (Math.abs(heightChange) > Number(rules.roll_max_step_height || 1)) return {error: "RISER TOO HIGH FOR A ROLL"};
        if (heightChange > 0 && tile.surface !== "ramp") return {error: "UPHILL ROLL NEEDS A RAMP"};
        if (tile.surface === "sand" && offset < distance) return {error: "THE BALL SETTLES IN SAND EARLY"};
        x = Number(tile.x); y = Number(tile.y); z = nextZ;
      }
    } else if (kind === "chip") {
      const tile = model.tiles.get(`${x + vector[0] * distance},${y + vector[1] * distance}`);
      if (!tile || tile.surface === "water") return {error: "CHIP NEEDS A VISIBLE LANDING TILE"};
      if (Math.abs(Number(tile.z) - z) > Number(rules.chip_clearance || 1)) return {error: "LANDING HEIGHT BEYOND THIS CHIP"};
      x = Number(tile.x); y = Number(tile.y); z = Number(tile.z);
    } else {
      return {error: "CARD TYPE UNKNOWN"};
    }
    const tile = model.tiles.get(`${x},${y}`);
    return {x, y, z, surface: String(tile?.surface || "")};
  }

  function project(x, y, z) {
    const course = model.state.course;
    const tileW = Math.min(58, 680 / Math.max(Number(course.width), Number(course.height)));
    const tileH = tileW * 0.5;
    const originX = 380;
    const originY = 62;
    return {x: originX + (Number(x) - Number(y)) * tileW * 0.5, y: originY + (Number(x) + Number(y)) * tileH * 0.5 - Number(z) * 25, tileW, tileH};
  }

  function diamond(ctx, point, inset = 0) {
    const w = point.tileW - inset, h = point.tileH - inset * 0.48;
    return [[point.x, point.y - h], [point.x + w, point.y], [point.x, point.y + h], [point.x - w, point.y]];
  }

  function polygon(ctx, points, fill, stroke = "none", width = 1) {
    ctx.beginPath(); points.forEach((point, index) => index ? ctx.lineTo(point[0], point[1]) : ctx.moveTo(point[0], point[1])); ctx.closePath();
    ctx.fillStyle = fill; ctx.fill();
    if (stroke !== "none") { ctx.strokeStyle = stroke; ctx.lineWidth = width; ctx.stroke(); }
  }

  function drawClouds(ctx) {
    ctx.fillStyle = model.state.palette.cloud;
    [[78, 62, 36], [165, 32, 22], [635, 76, 42], [692, 164, 22], [92, 360, 28]].forEach(([x, y, radius]) => {
      ctx.globalAlpha = 0.5; ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.arc(x + radius * .7, y + 4, radius * .7, 0, Math.PI * 2); ctx.arc(x - radius * .7, y + 6, radius * .6, 0, Math.PI * 2); ctx.fill();
    }); ctx.globalAlpha = 1;
  }

  function drawScene() {
    const canvas = document.getElementById("cloudstep-course");
    const ctx = canvas?.getContext("2d");
    if (!ctx || !model) return;
    const palette = model.state.palette;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height); gradient.addColorStop(0, palette.sky); gradient.addColorStop(1, "#eef5de"); ctx.fillStyle = gradient; ctx.fillRect(0, 0, canvas.width, canvas.height);
    drawClouds(ctx);
    const ordered = [...(model.state.course.tiles || [])].sort((a, b) => (Number(a.x) + Number(a.y) + Number(a.z) * .01) - (Number(b.x) + Number(b.y) + Number(b.z) * .01));
    ordered.forEach((tile) => {
      const p = project(tile.x, tile.y, tile.z), top = diamond(ctx, p), drop = 13 + Number(tile.z) * 2;
      const colors = {fairway: palette.fairway, sand: palette.sand, water: palette.water, ramp: palette.ramp, cup: palette.cup};
      const lower = top.map(([x, y]) => [x, y + drop]);
      polygon(ctx, [top[3], top[2], lower[2], lower[3]], palette.fairway_dark);
      polygon(ctx, [top[1], top[2], lower[2], lower[1]], palette.fairway_dark);
      polygon(ctx, top, colors[tile.surface] || palette.fairway, palette.ink, 1);
      if (tile.surface === "water") {
        ctx.strokeStyle = "rgba(236,255,255,.7)"; ctx.lineWidth = 2;
        for (let wave = -0.42; wave <= 0.42; wave += .28) { ctx.beginPath(); ctx.moveTo(p.x - p.tileW * .42, p.y + wave * p.tileH); ctx.lineTo(p.x - p.tileW * .08, p.y + (wave + .05) * p.tileH); ctx.lineTo(p.x + p.tileW * .28, p.y + wave * p.tileH); ctx.stroke(); }
      } else if (tile.surface === "sand") {
        ctx.fillStyle = "rgba(124,77,36,.38)"; [[-.25, -.1], [.2, .08], [0, .28]].forEach(([ox, oy]) => { ctx.beginPath(); ctx.arc(p.x + ox * p.tileW, p.y + oy * p.tileH, 2, 0, Math.PI * 2); ctx.fill(); });
      } else if (tile.surface === "ramp") {
        ctx.strokeStyle = palette.ink; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(p.x - p.tileW * .35, p.y + p.tileH * .1); ctx.lineTo(p.x + p.tileW * .35, p.y - p.tileH * .1); ctx.stroke();
      }
      if (tile.surface === "cup") {
        ctx.strokeStyle = palette.ink; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(p.x, p.y + 1, p.tileW * .23, 0, Math.PI * 2); ctx.stroke();
        ctx.strokeStyle = palette.accent; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(p.x, p.y, p.x, p.y - 28); ctx.stroke(); polygon(ctx, [[p.x, p.y - 28], [p.x + 21, p.y - 22], [p.x, p.y - 16]], palette.accent);
      }
    });
    const cup = model.state.course.cup, cupPoint = project(cup.x, cup.y, cup.z);
    ctx.strokeStyle = "rgba(255,255,255,.7)"; ctx.setLineDash([3, 6]); ctx.beginPath(); ctx.moveTo(cupPoint.x, cupPoint.y); ctx.lineTo(cupPoint.x, cupPoint.y - 42); ctx.stroke(); ctx.setLineDash([]);
    const ball = project(model.ball.x, model.ball.y, model.ball.z);
    ctx.fillStyle = "rgba(19,47,45,.28)"; ctx.beginPath(); ctx.ellipse(ball.x, ball.y + 7, 13, 5, 0, 0, Math.PI * 2); ctx.fill();
    const shine = ctx.createRadialGradient(ball.x - 4, ball.y - 5, 1, ball.x, ball.y, 13); shine.addColorStop(0, "#fffde0"); shine.addColorStop(1, palette.accent); ctx.fillStyle = shine; ctx.beginPath(); ctx.arc(ball.x, ball.y - 4, 12, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = palette.ink; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = palette.ink; ctx.font = "800 11px ui-monospace, monospace"; ctx.fillText(`ELEVATION ${model.ball.z}  ·  ${model.used.length}/${model.state.cards.length} CARDS SPENT`, 18, 27);
  }

  function renderHand() {
    const hand = document.getElementById("cloudstep-hand");
    if (!hand) return;
    hand.innerHTML = model.state.cards.map((card) => {
      const used = model.used.includes(String(card.id));
      const selected = model.selectedCard === String(card.id);
      return `<button type="button" class="cloud-card${used ? " is-used" : ""}${selected ? " is-selected" : ""}" data-card-id="${esc(card.id)}"${used ? " disabled" : ""} draggable="${model.interaction === "full" && !used}"><span class="cloud-card-kind">${esc(card.kind.toUpperCase())}</span><strong>${esc(card.distance)}</strong><small>${used ? "SPENT" : "STROKE"}</small></button>`;
    }).join("");
    hand.querySelectorAll(".cloud-card").forEach((button) => {
      button.addEventListener("click", () => {
        if (model.interaction === "full") { model.helpers.setReadout("DRAG THE CARD TO A COMPASS DIRECTION", "idle"); return; }
        model.selectedCard = String(button.dataset.cardId); renderHand(); model.helpers.setReadout("CARD ARMED · CHOOSE A DIRECTION", "idle");
      });
      if (model.interaction === "full") {
        button.addEventListener("pointerdown", (event) => {
          if (button.disabled) return;
          event.preventDefault(); model.drag = {cardId: String(button.dataset.cardId), pointerId: event.pointerId}; button.setPointerCapture(event.pointerId); button.classList.add("is-dragging"); model.helpers.setReadout("CARRY THE CARD TO NORTH, EAST, SOUTH OR WEST", "idle");
        });
        button.addEventListener("pointerup", (event) => {
          if (!model.drag || model.drag.pointerId !== event.pointerId) return;
          const target = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-direction]"); button.classList.remove("is-dragging"); const cardId = model.drag.cardId; model.drag = null;
          if (!target) { model.helpers.setReadout("CARD RETURNED · DROP ON A COMPASS DIRECTION", "error"); return; }
          dispatch(cardId, String(target.dataset.direction), "card_drag_to_compass");
        });
      }
    });
  }

  function dispatch(cardId, direction, inputSource) {
    if (model.terminal) return;
    const card = model.state.cards.find((item) => String(item.id) === String(cardId));
    if (!card || model.used.includes(String(card.id))) return;
    const before = stateSnapshot();
    const result = transition(before, card, direction);
    if (result.error) { model.helpers.setReadout(result.error, "error"); model.selectedCard = null; renderHand(); return; }
    const after = {...result, used_card_ids: [...model.used, String(card.id)]};
    model.events.push({seq: model.events.length + 1, type: "stroke", card_id: String(card.id), direction, before, after, input_source: inputSource});
    model.ball = {x: after.x, y: after.y, z: after.z}; model.used.push(String(card.id)); model.selectedCard = null;
    model.helpers.setReadout(`${card.kind.toUpperCase()} ${card.distance} ${arrows[direction]} · ${after.surface.toUpperCase()}`, "idle"); renderHand(); drawScene(); updateStatus();
  }

  function updateStatus() {
    const root = document.querySelector(".cloudstep-caddie"); if (!root) return;
    root.dataset.used = String(model.used.length); root.dataset.atCup = String(model.ball.x === Number(model.state.course.cup.x) && model.ball.y === Number(model.state.course.cup.y) && model.ball.z === Number(model.state.course.cup.z));
    const counter = document.getElementById("cloudstep-counter"); if (counter) counter.textContent = `${model.used.length} / ${model.state.cards.length}`;
    const submit = document.getElementById("cloudstep-submit"); if (submit) submit.disabled = model.terminal;
  }

  async function certify() {
    if (model.terminal || model.submitting) return;
    const cup = model.state.course.cup;
    const accepted = model.ball.x === Number(cup.x) && model.ball.y === Number(cup.y) && model.ball.z === Number(cup.z) && model.used.length === model.state.cards.length;
    const ball = stateSnapshot();
    model.events.push({seq: model.events.length + 1, type: "certify", ball, used_card_ids: [...model.used], accepted, input_source: "certify_button"});
    model.submitting = true; updateStatus(); model.helpers.setReadout("COURSE REPLAY IN PROGRESS…", "pending");
    const submittedState = model.state;
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({mechanic_id: submittedState.mechanic_id, task_id: submittedState.task_id, challenge_id: submittedState.challenge_id, interaction_mode: model.interaction, events: model.events, completed: true})});
      const outcome = await response.json();
      if (outcome.passed === true) { model.terminal = true; model.helpers.setReadout("PASS", "passed"); document.querySelector(".cloudstep-caddie")?.classList.add("is-passed"); }
      else if (outcome.passed === false && outcome.state) { await model.helpers.render(outcome.state); model.helpers.setReadout("FAIL · FRESH COURSE", "error"); }
      else { model.submitting = false; model.helpers.setReadout(`FAIL · ${outcome.feedback || "COURSE REJECTED"}`, "error"); }
    } catch (_error) { model.submitting = false; model.helpers.setReadout("FAIL · VERIFIER OFFLINE", "error"); }
  }

  function installCompass() {
    document.querySelectorAll("[data-direction]").forEach((button) => button.addEventListener("click", () => {
      if (model.interaction === "full") { model.helpers.setReadout("FULL INPUT · DRAG A CARD ONTO THIS COMPASS", "idle"); return; }
      if (!model.selectedCard) { model.helpers.setReadout("SELECT A CARD FIRST", "error"); return; }
      dispatch(model.selectedCard, String(button.dataset.direction), "card_then_direction_buttons");
    }));
  }

  async function render(state, helpers) {
    if (cleanup) cleanup();
    model = {state, helpers, interaction: conditionInteraction(state), tiles: tileMap(state.course), ball: {x: Number(state.course.start.x), y: Number(state.course.start.y), z: Number(state.course.start.z)}, used: [], selectedCard: null, events: [], drag: null, submitting: false, terminal: false};
    document.body.dataset.mechanic = "cloudstep-caddie";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const directNote = model.interaction === "full" ? "Drag a pictured stroke card onto a direction. Release on the compass." : "Click a pictured stroke card, then choose its direction.";
    helpers.app.innerHTML = `<section class="cloudstep-caddie" data-interaction="${esc(model.interaction)}" data-challenge-id="${esc(state.challenge_id)}"><header class="cloudstep-head"><div><span>CLOUD ISLANDS / STROKE LEDGER</span><h1>Cloudstep Caddie</h1><p>${esc(state.prompt)}</p></div><div class="cloudstep-mark">⛳<b>HEIGHT<br>MATTERS</b></div></header><main class="cloudstep-workbench"><section class="cloudstep-stage"><canvas id="cloudstep-course" width="760" height="480" aria-label="isometric cloud island golf course"></canvas><div class="cloudstep-legend"><span><i class="legend-fairway"></i>FAIRWAY</span><span><i class="legend-sand"></i>SAND</span><span><i class="legend-water"></i>WATER</span><span><i class="legend-ramp"></i>RAMP</span><span><i class="legend-cup"></i>CUP</span></div></section><aside class="cloudstep-console"><div class="cloudstep-console-head"><span>DEALT HAND</span><b id="cloudstep-counter">0 / ${state.cards.length}</b></div><p class="cloudstep-directive">${esc(directNote)}</p><div id="cloudstep-hand" class="cloudstep-hand"></div><div class="cloudstep-compass" aria-label="direction compass"><span>CHOOSE DIRECTION</span><div class="compass-grid"><button type="button" data-direction="north">↑<small>N</small></button><button type="button" data-direction="west">←<small>W</small></button><div class="compass-center">⟡</div><button type="button" data-direction="east">→<small>E</small></button><button type="button" data-direction="south">↓<small>S</small></button></div></div><div class="cloudstep-rule"><b>FIELD NOTES</b><span>Rolls cannot cross water. Chips clear gaps and height. Sand stops a long roll.</span></div><button id="cloudstep-submit" class="cloudstep-submit" type="button">CERTIFY SUNKEN BALL</button></aside></main><footer class="cloudstep-foot"><div class="readout" data-status="idle">READY · READ THE HEIGHT STEPS</div><span>${esc(state.challenge_id.toUpperCase())} / FIXED HAND / TILE CONTACT REPLAY</span></footer></section>`;
    document.getElementById("cloudstep-submit").addEventListener("click", certify);
    renderHand(); installCompass(); drawScene(); updateStatus();
    cleanup = () => {};
  }

  registry.cloudstep_caddie = {rootSelector: ".cloudstep-caddie", render};
})();
