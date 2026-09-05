(() => {
  "use strict";

  const DISC_IDS = ["north", "southwest", "southeast"];
  const DISC_SLOTS = [[3, 7, 6, 0, 5, 4], [3, 10, 9, 1, 8, 7], [3, 4, 12, 2, 11, 10]];
  let model = null;

  const esc = value => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const same = (left, right) => left.length === right.length && left.every((value, index) => value === right[index]);

  function legal(state, discIndex) {
    const slots = DISC_SLOTS[discIndex];
    const heartSlot = state.indexOf(3);
    return slots.includes(heartSlot) && [0, 1, 2].every(point => point === discIndex || !slots.includes(state.indexOf(point)));
  }

  function turn(state, discIndex, direction) {
    const slots = DISC_SLOTS[discIndex];
    const values = slots.map(slot => state[slot]);
    const shifted = direction === 1 ? values.slice(-1).concat(values.slice(0, -1)) : values.slice(1).concat(values.slice(0, 1));
    const next = state.slice();
    slots.forEach((slot, index) => { next[slot] = shifted[index]; });
    return next;
  }

  function pieceMarkup(piece, slot, compact = false) {
    const [x, y] = slot.center;
    const scale = compact ? 0.41 : 1;
    const lead = compact ? 4 : 5;
    const cls = `glass-piece piece-${piece.kind}`;
    let shape;
    if (piece.kind === "heart") {
      shape = `<path d="M0 31 C-43 4 -45 -32 -18 -39 C-2 -43 0 -27 0 -19 C0 -27 2 -43 18 -39 C45 -32 43 4 0 31 Z"/>`;
    } else if (piece.kind === "point") {
      shape = `<path d="M0 -49 L30 13 L0 43 L-30 13 Z"/>`;
    } else {
      shape = `<path d="M-36 -38 Q0 -54 36 -38 L31 15 Q24 41 0 50 Q-24 41 -31 15 Z"/>`;
    }
    const motif = Number(piece.motif || 0);
    const decoration = motif % 3 === 0
      ? `<path class="glass-vein" d="M-20 -20 L20 24 M18 -24 L-17 20"/>`
      : motif % 3 === 1
        ? `<circle class="glass-jewel" cx="0" cy="4" r="11"/><path class="glass-vein" d="M0 -31 V-8 M0 16 V35"/>`
        : `<path class="glass-vein" d="M-25 7 Q0 -17 25 7 Q0 31 -25 7 Z"/>`;
    return `<g class="${cls}" data-piece="${piece.id}" transform="translate(${x} ${y}) scale(${scale})" style="--glass:${esc(piece.glass)};--lead:${lead}px">${shape}${decoration}</g>`;
  }

  function glassFor(state) {
    const byId = new Map(model.state.rose.pieces.map(piece => [Number(piece.id), piece]));
    return state.map((pieceId, slotIndex) => pieceMarkup(byId.get(Number(pieceId)), model.state.rose.slots[slotIndex], false)).join("");
  }

  function discRings(target = false) {
    return model.state.rose.discs.map(disc => `<circle class="disc-ring" data-disc-ring="${esc(disc.id)}" cx="${disc.center[0]}" cy="${disc.center[1]}" r="${disc.radius}"/>`).join("");
  }

  function handleMarkup(disc) {
    const angle = Number(disc.handle_angle) * Math.PI / 180;
    const radius = Number(disc.handle_radius || disc.radius);
    const x = Number(disc.center[0]) + Math.cos(angle) * radius;
    const y = Number(disc.center[1]) + Math.sin(angle) * radius;
    return `<g class="rose-handle" data-disc="${esc(disc.id)}" transform="translate(${x} ${y})"><circle r="20"/><circle r="9"/><path d="M-7 0 H7 M0 -7 V7"/></g>`;
  }

  function roseSvg(state, target = false) {
    return `<svg class="rose-svg${target ? " target-svg" : ""}" viewBox="180 18 640 510" role="img" aria-label="${target ? "Reference rose arrangement" : "Current bandaged rose"}">
      <defs><filter id="roseGlow"><feGaussianBlur stdDeviation="5" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
      <path class="stone-tracery" d="M500 25 C696 25 807 176 807 349 C807 482 695 520 500 520 C305 520 193 482 193 349 C193 176 304 25 500 25 Z"/>
      ${discRings(target)}
      ${glassFor(state)}
      <circle class="rose-boss" cx="500" cy="300" r="15"/>
      ${target || model.interaction !== "full" ? "" : model.state.rose.discs.map(handleMarkup).join("")}
    </svg>`;
  }

  function controlsMarkup() {
    if (model.interaction === "full") {
      return "";
    }
    return `<div class="rose-button-bank">${model.state.rose.discs.map(disc => `<div class="disc-buttons"><span>${esc(disc.label)}</span><button class="rose-turn-button" type="button" data-disc="${esc(disc.id)}" data-direction="-1" aria-label="Turn ${esc(disc.label)} counter-clockwise">↶</button><button class="rose-turn-button" type="button" data-disc="${esc(disc.id)}" data-direction="1" aria-label="Turn ${esc(disc.label)} clockwise">↷</button></div>`).join("")}</div>`;
  }

  function updateVisible() {
    const mount = document.querySelector(".current-rose");
    if (mount) mount.innerHTML = roseSvg(model.current, false);
    model.ready = same(model.current, model.state.rose.solved_state);
    installHandles();
  }

  function attempt(discId, direction, inputSource) {
    if (model.submitting) return;
    const discIndex = DISC_IDS.indexOf(String(discId));
    if (discIndex < 0 || ![-1, 1].includes(direction)) return;
    const root = document.querySelector(".bandaged-rose-captcha");
    if (root?.dataset.freshFailure === "true") {
      delete root.dataset.freshFailure;
    }
    const before = model.current.slice();
    const allowed = legal(before, discIndex);
    const after = allowed ? turn(before, discIndex, direction) : before.slice();
    if (allowed) model.successful += 1;
    else model.refused += 1;
    model.events.push({
      sequence: model.events.length + 1,
      disc_id: discId,
      direction,
      input_source: inputSource,
      outcome: allowed ? "turned" : "refused",
      before_state: before,
      after_state: after.slice(),
      turns_after: model.successful,
    });
    model.current = after;
    if (allowed) updateVisible();
  }

  function svgPoint(svg, event) {
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    return point.matrixTransform(svg.getScreenCTM().inverse());
  }

  function installHandles() {
    if (!model || model.interaction !== "full") return;
    document.querySelectorAll(".rose-handle").forEach(handle => {
      handle.addEventListener("pointerdown", event => {
        event.preventDefault();
        const svg = handle.closest("svg");
        const disc = model.state.rose.discs.find(item => item.id === handle.dataset.disc);
        if (!svg || !disc) return;
        handle.setPointerCapture(event.pointerId);
        const start = svgPoint(svg, event);
        const initialAngle = Math.atan2(start.y - disc.center[1], start.x - disc.center[0]);
        const initialTransform = handle.getAttribute("transform");
        handle.classList.add("is-dragging");
        const move = moveEvent => {
          if (moveEvent.pointerId !== event.pointerId) return;
          moveEvent.preventDefault();
          const point = svgPoint(svg, moveEvent);
          const angle = Math.atan2(point.y - disc.center[1], point.x - disc.center[0]);
          const radius = Number(disc.handle_radius || disc.radius);
          const x = Number(disc.center[0]) + Math.cos(angle) * radius;
          const y = Number(disc.center[1]) + Math.sin(angle) * radius;
          handle.setAttribute("transform", `translate(${x} ${y})`);
        };
        const finish = (endEvent, cancelled) => {
          if (endEvent.pointerId !== event.pointerId) return;
          handle.removeEventListener("pointermove", move);
          handle.removeEventListener("pointerup", up);
          handle.removeEventListener("pointercancel", cancel);
          handle.classList.remove("is-dragging");
          handle.setAttribute("transform", initialTransform);
          if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
          if (cancelled) return;
          const end = svgPoint(svg, endEvent);
          let delta = Math.atan2(end.y - disc.center[1], end.x - disc.center[0]) - initialAngle;
          while (delta > Math.PI) delta -= Math.PI * 2;
          while (delta < -Math.PI) delta += Math.PI * 2;
          if (Math.abs(delta) >= 0.45) attempt(disc.id, delta > 0 ? 1 : -1, "rim_drag");
        };
        const up = endEvent => finish(endEvent, false);
        const cancel = endEvent => finish(endEvent, true);
        handle.addEventListener("pointermove", move);
        handle.addEventListener("pointerup", up);
        handle.addEventListener("pointercancel", cancel);
      });
    });
  }

  async function retryFreshRose() {
    if (!model?.pendingState) return;
    const state = model.pendingState;
    const helpers = model.helpers;
    await helpers.render(state);
    const root = document.querySelector(".bandaged-rose-captcha");
    if (root) root.dataset.freshFailure = "true";
  }

  async function submit() {
    if (model.submitting) return;
    model.submitting = true;
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      events: model.events,
      final_state: model.current,
      successful_turns: model.successful,
      refused_turns: model.refused,
      completed: same(model.current, model.state.rose.solved_state),
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.helpers.setReadout("PASS", "passed");
        document.querySelector(".bandaged-rose-captcha").classList.add("is-passed");
      } else if (outcome.state) {
        const root = document.querySelector(".bandaged-rose-captcha");
        model.pendingState = outcome.state;
        if (root) {
          root.classList.add("is-failed");
          root.dataset.failureReady = "true";
        }
        model.helpers.setReadout("FAIL", "error");
      } else {
        const root = document.querySelector(".bandaged-rose-captcha");
        if (root) root.classList.add("is-failed");
        model.helpers.setReadout("FAIL", "error");
      }
    } catch (_error) {
      const root = document.querySelector(".bandaged-rose-captcha");
      if (root) root.classList.add("is-failed");
      model.helpers.setReadout("FAIL", "error");
    }
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "bandaged-rose-window-v1";
    const interaction = state.control_condition?.interaction || "full";
    model = {state, helpers, interaction, current: state.rose.initial_state.slice(), successful: 0, refused: 0, events: [], ready: false, submitting: false, pendingState: null};
    helpers.app.innerHTML = `<main class="bandaged-rose-captcha" data-interaction="${esc(interaction)}">
      <header class="rose-header"><h1>Bandaged Rose Window</h1><p>${esc(state.prompt)}</p></header>
      <section class="rose-workbench">
        <aside class="reference-panel"><span class="panel-label">REFERENCE</span><div class="reference-rose">${roseSvg(state.rose.solved_state, true)}</div></aside>
        <section class="window-panel"><div class="arch-glow"></div><div class="current-rose">${roseSvg(model.current, false)}</div></section>
        <aside class="control-panel">${controlsMarkup()}<div class="readout" hidden aria-hidden="true" style="display:none" data-status="idle"></div><button id="rose-certify" type="button">${esc(state.submit_label || "SEAL")}</button></aside>
      </section>
      <div class="rose-fail-card"><b>FAIL</b><button id="rose-retry" type="button">RETRY</button></div>
      <div class="rose-pass-card"><b>PASS</b></div>
    </main>`;
    document.querySelectorAll(".rose-turn-button").forEach(button => button.addEventListener("click", () => attempt(button.dataset.disc, Number(button.dataset.direction), "proxy_buttons")));
    document.querySelector("#rose-certify").addEventListener("click", submit);
    document.querySelector("#rose-retry").addEventListener("click", retryFreshRose);
    installHandles();
    window.bandagedRoseWindowModel = model;
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.bandaged_rose_window = {render, rootSelector: ".bandaged-rose-captcha"};
})();
