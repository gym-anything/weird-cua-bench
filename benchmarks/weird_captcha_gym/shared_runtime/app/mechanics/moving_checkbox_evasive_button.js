(() => {
  "use strict";

  const MECHANIC_ID = "moving_checkbox_evasive_button";
  let model = null;
  let cleanupActive = null;

  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const sign = (value) => value > 0 ? 1 : value < 0 ? -1 : 0;
  const ratio = (value, numerator, denominator = 1000) => Math.trunc(value * numerator / denominator);
  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;");

  function record(type, details = {}) {
    model.events.push({seq: model.events.length + 1, type, ...details});
  }

  function clearFreshFailure() {
    const root = document.querySelector(".scroll-cage");
    if (root?.dataset.freshFailure === "true") root.dataset.freshFailure = "false";
  }

  function bodyState() {
    const {x, y, vx, vy, captured} = model.body;
    return {x, y, vx, vy, captured};
  }

  function portalGeometry(boundary) {
    const leftY = Number(boundary.left_base_y) - model.offsets[Number(boundary.left_shaft)];
    const rightY = Number(boundary.right_base_y) - model.offsets[Number(boundary.right_shaft)];
    return {
      leftY,
      rightY,
      y: Math.trunc((leftY + rightY) / 2),
      aligned: Math.abs(leftY - rightY) <= Number(boundary.alignment_tolerance),
    };
  }

  function stepBody() {
    if (!model || model.body.captured || model.terminal || model.submitting) return;
    const scene = model.state.scene;
    const physics = model.state.physics;
    let {x, y} = model.body;
    let vx = ratio(model.body.vx, Number(physics.friction_milli));
    let vy = ratio(model.body.vy, Number(physics.friction_milli));
    if (model.cursor.active) {
      const dx = x - model.cursor.x;
      const dy = y - model.cursor.y;
      const radius = Number(physics.cursor_radius);
      const distanceSq = dx * dx + dy * dy;
      if (distanceSq > 0 && distanceSq < radius * radius) {
        const acceleration = 1 + Math.trunc((radius * radius - distanceSq) * (Number(physics.cursor_acceleration) - 1) / (radius * radius));
        if (Math.abs(dx) * 2 >= Math.abs(dy)) vx += sign(dx) * acceleration;
        if (Math.abs(dy) * 2 >= Math.abs(dx)) vy += sign(dy) * acceleration;
      }
    }
    const maximum = Number(physics.max_speed);
    vx = clamp(vx, -maximum, maximum);
    vy = clamp(vy, -maximum, maximum);
    let nextX = x + vx;
    let nextY = y + vy;
    const radius = Number(scene.target.radius);
    const restitution = Number(physics.wall_restitution_milli);
    const top = Number(physics.top);
    const bottom = Number(physics.bottom);
    if (nextY - radius < top) {
      nextY = top + radius;
      vy = Math.abs(ratio(vy, restitution));
    } else if (nextY + radius > bottom) {
      nextY = bottom - radius;
      vy = -Math.abs(ratio(vy, restitution));
    }
    const leftEdge = Number(scene.shaft_lefts[0]) + radius;
    const rightEdge = Number(scene.shaft_lefts.at(-1)) + Number(scene.shaft_width) - radius;
    if (nextX < leftEdge) {
      nextX = leftEdge;
      vx = Math.abs(ratio(vx, restitution));
    } else if (nextX > rightEdge) {
      nextX = rightEdge;
      vx = -Math.abs(ratio(vx, restitution));
    }
    scene.boundaries.forEach((boundary) => {
      const boundaryX = Number(boundary.x);
      const portal = portalGeometry(boundary);
      const withinOpening = Math.abs(nextY - portal.y) <= Number(boundary.opening_half_height) - radius;
      if (vx > 0 && x <= boundaryX - radius && boundaryX - radius < nextX) {
        if (!(portal.aligned && withinOpening)) {
          nextX = boundaryX - radius;
          vx = -Math.abs(ratio(vx, restitution));
        }
      } else if (vx < 0 && x >= boundaryX + radius && boundaryX + radius > nextX) {
        if (!(portal.aligned && withinOpening)) {
          nextX = boundaryX + radius;
          vx = Math.abs(ratio(vx, restitution));
        }
      }
    });
    const captureDx = nextX - Number(scene.clamp.x);
    const captureDy = nextY - Number(scene.clamp.y);
    const captured = captureDx * captureDx + captureDy * captureDy <= Number(scene.clamp.capture_radius) ** 2;
    if (captured) {
      nextX = Number(scene.clamp.x);
      nextY = Number(scene.clamp.y);
      vx = 0;
      vy = 0;
    }
    model.body = {x: nextX, y: nextY, vx, vy, captured};
    model.tick += 1;
    record("tick", {tick: model.tick, body: bodyState()});
    if (captured && !model.capturedAnnounced) {
      model.capturedAnnounced = true;
      model.helpers.setReadout("CLAMP CONTACT · PHYSICAL CHECKBOX ARMED", "passed");
    }
    paint();
  }

  function setOffset(shaft, delta) {
    if (!model || model.terminal || model.submitting) return;
    clearFreshFailure();
    const scene = model.state.scene;
    const before = model.offsets[shaft];
    const after = clamp(before + delta, Number(scene.offset_min), Number(scene.offset_max));
    if (before === after) return;
    model.offsets[shaft] = after;
    record("scroll", {shaft, delta: after - before, before, after});
    model.helpers.setReadout(`SHAFT 0${shaft + 1} INDEX ${after > 0 ? "+" : ""}${after} · PORTALS MOVED`, "idle");
    paint();
  }

  function paint() {
    if (!model) return;
    const scene = model.state.scene;
    const target = document.getElementById("scroll-cage-target");
    if (target) {
      target.style.left = `${model.body.x / scene.width * 100}%`;
      target.style.top = `${model.body.y / scene.height * 100}%`;
      target.dataset.captured = String(model.body.captured);
      target.dataset.checked = String(model.checked);
    }
    const field = document.getElementById("scroll-cage-field");
    if (field) {
      field.hidden = !model.cursor.active;
      field.style.left = `${model.cursor.x / scene.width * 100}%`;
      field.style.top = `${model.cursor.y / scene.height * 100}%`;
      field.style.setProperty("--field-size", `${Number(model.state.physics.cursor_radius) * 2 / scene.width * 100}%`);
    }
    model.offsets.forEach((offset, shaft) => {
      document.querySelectorAll(`[data-offset-label="${shaft}"]`).forEach((label) => {
        label.textContent = `${offset > 0 ? "+" : ""}${offset}`;
      });
      document.querySelectorAll(`[data-scroll-surface="${shaft}"]`).forEach((surface) => {
        const arena = document.getElementById("scroll-cage-arena");
        surface.style.transform = `translateY(${-offset * (arena?.clientHeight || scene.height) / scene.height}px)`;
      });
    });
    scene.boundaries.forEach((boundary, index) => {
      const portal = portalGeometry(boundary);
      const gate = document.querySelector(`[data-gate="${index}"]`);
      if (gate) {
        gate.dataset.aligned = String(portal.aligned);
        const status = gate.querySelector("b");
        if (status) status.textContent = portal.aligned ? "OPEN" : "SPLIT";
      }
    });
    const check = document.getElementById("scroll-cage-check");
    if (check) {
      check.disabled = !model.body.captured || model.checked || model.submitting || model.terminal;
      check.dataset.checked = String(model.checked);
      check.setAttribute("aria-checked", String(model.checked));
    }
    const tick = document.getElementById("scroll-cage-tick");
    if (tick) tick.textContent = String(model.tick).padStart(4, "0");
    const velocity = document.getElementById("scroll-cage-velocity");
    if (velocity) velocity.textContent = `${model.body.vx},${model.body.vy}`;
  }

  function checkTarget() {
    if (!model || !model.body.captured || model.checked || model.submitting || model.terminal) return;
    clearFreshFailure();
    model.checked = true;
    record("check", {checked: true, body: bodyState()});
    model.helpers.setReadout("BOX CHECKED · FILE THE PHYSICAL TRANSCRIPT", "passed");
    paint();
  }

  async function verify() {
    if (!model || model.submitting || model.terminal) return;
    record("verify", {tick: model.tick, offsets: [...model.offsets], body: bodyState(), checked: model.checked});
    const current = model;
    current.submitting = true;
    current.helpers.setReadout("REPLAYING SCROLL SURFACES + COLLISIONS…", "pending");
    paint();
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({
          mechanic_id: MECHANIC_ID,
          task_id: current.state.task_id,
          challenge_id: current.state.challenge_id,
          events: current.events,
          completed: current.checked && current.body.captured,
        }),
      });
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.terminal = true;
        window.clearInterval(current.timer);
        current.helpers.setReadout("PASS", "passed");
        document.querySelector(".scroll-cage")?.setAttribute("data-verdict", "pass");
      } else if (outcome.passed === false && outcome.state) {
        const helpers = current.helpers;
        await render(outcome.state, helpers, {freshFailure: true});
        model.helpers.setReadout("FAIL · FRESH CAGE ISSUED", "error");
      } else {
        current.submitting = false;
        current.helpers.setReadout("TRANSCRIPT REJECTED", "error");
        paint();
      }
    } catch (_error) {
      if (model === current) {
        current.submitting = false;
        current.helpers.setReadout("PHYSICAL ARCHIVE OFFLINE", "error");
        paint();
      }
    }
  }

  function portalMarkup(state, shaft) {
    const scene = state.scene;
    return scene.boundaries.map((boundary, index) => {
      const isLeft = Number(boundary.left_shaft) === shaft;
      const isRight = Number(boundary.right_shaft) === shaft;
      if (!isLeft && !isRight) return "";
      const baseY = Number(isLeft ? boundary.left_base_y : boundary.right_base_y);
      const side = isLeft ? "right" : "left";
      return `<div class="scroll-cage-portal portal-${side}" style="--portal-y:${baseY / scene.height * 100}%;--portal-half:${Number(boundary.opening_half_height) / scene.height * 100}%" data-portal="${index}-${side}"><i></i><span>G${index + 1}</span></div>`;
    }).join("");
  }

  async function render(state, helpers, options = {}) {
    if (cleanupActive) cleanupActive();
    document.body.dataset.mechanic = "scroll-cage-checkbox";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const scene = state.scene;
    model = {
      state,
      helpers,
      events: [],
      offsets: [...scene.initial_offsets],
      body: {...scene.target, captured: false},
      cursor: {active: false, x: 0, y: 0},
      tick: 0,
      checked: false,
      capturedAnnounced: false,
      submitting: false,
      terminal: false,
      timer: null,
      drag: null,
    };
    window.scrollCageModel = model;
    helpers.app.innerHTML = `<section class="scroll-cage palette-${esc(state.palette)}" data-fresh-failure="${options.freshFailure ? "true" : "false"}" data-verdict="">
      <div class="scroll-cage-verdict" aria-live="assertive"><b>${options.freshFailure ? "FAIL" : ""}</b><span>${options.freshFailure ? "CAGE RE-INDEXED" : ""}</span></div>
      <header class="scroll-cage-head">
        <div><span>DEPARTMENT OF ORDINARY CONFIRMATIONS / FORM ${esc(state.challenge_id)}</span><h1>${esc(state.prompt)}</h1></div>
        <aside><i>☑</i><span>PHYSICAL<br><b>FORM</b></span></aside>
      </header>
      <main class="scroll-cage-workbench">
        <section class="scroll-cage-stage" id="scroll-cage-stage">
          <div class="scroll-cage-arena" id="scroll-cage-arena" role="application" aria-label="four independently scrollable checkbox shafts">
            <div class="scroll-cage-grid"></div>
            ${scene.shaft_lefts.map((left, shaft) => `<div class="scroll-cage-shaft" data-shaft="${shaft}" style="--left:${left / scene.width * 100}%;--width:${Number(scene.shaft_width) / scene.width * 100}%">
              <div class="scroll-cage-surface" data-scroll-surface="${shaft}">${portalMarkup(state, shaft)}${Array.from({length: 14}, (_, row) => `<i class="index-mark" style="--row:${row}"></i>`).join("")}</div>
              <div class="shaft-label"><b>0${shaft + 1}</b><span data-offset-label="${shaft}">0</span></div>
            </div>`).join("")}
            ${scene.boundaries.map((boundary, index) => `<div class="scroll-cage-wall" style="--x:${Number(boundary.x) / scene.width * 100}%" data-gate="${index}" data-aligned="false"><span>GATE 0${index + 1}</span><b>SPLIT</b></div>`).join("")}
            <div class="scroll-cage-clamp" style="--x:${Number(scene.clamp.x) / scene.width * 100}%;--y:${Number(scene.clamp.y) / scene.height * 100}%;--r:${Number(scene.clamp.capture_radius) / scene.width * 100}%"><span>FINAL<br>CLAMP</span></div>
            <div id="scroll-cage-field" class="scroll-cage-field" hidden><i></i></div>
            <button type="button" id="scroll-cage-target" class="scroll-cage-target" aria-label="physical checkbox" data-captured="false" data-checked="false"><i></i></button>
          </div>
          <div class="scroll-cage-instrument"><span>POINTER FIELD <b>REPULSE</b></span><span>TICK <b id="scroll-cage-tick">0000</b></span><span>VELOCITY <b id="scroll-cage-velocity">0,0</b></span><span>PORTALS <b>SCROLL-BOUND</b></span></div>
        </section>
        <aside class="scroll-cage-console">
          <div class="scroll-cage-register"><span>SHAFT INDEX</span><p>OFFSET REGISTER / PAPER-BOUND APERTURES</p></div>
          ${scene.shaft_lefts.map((_left, shaft) => `<section class="shaft-control" data-shaft-control="${shaft}">
            <header><b>0${shaft + 1}</b><span>INDEPENDENT SHAFT</span><em data-offset-label="${shaft}">${scene.initial_offsets[shaft] > 0 ? "+" : ""}${scene.initial_offsets[shaft]}</em></header>
            <div class="shaft-control-buttons"><button type="button" data-shaft-up="${shaft}" aria-label="scroll shaft ${shaft + 1} up">↑</button><div class="shaft-drag" data-shaft-drag="${shaft}"><i></i><span>DRAG / WHEEL</span></div><button type="button" data-shaft-down="${shaft}" aria-label="scroll shaft ${shaft + 1} down">↓</button></div>
          </section>`).join("")}
          <button type="button" id="scroll-cage-check" class="scroll-cage-check" role="checkbox" aria-checked="false" data-checked="false" disabled><i></i><span>CHECK THE BOX</span></button>
        </aside>
      </main>
      <footer class="scroll-cage-foot"><div class="readout" data-status="idle">MOVE THE FORM · MOVE THE FIELD</div><button type="button" id="scroll-cage-submit">${esc(state.submit_label || "VERIFY")}</button></footer>
      ${helpers.cheatPanelTemplate()}
    </section>`;

    const arena = document.getElementById("scroll-cage-arena");
    arena.addEventListener("pointermove", (event) => {
      if (!model || model.terminal || model.submitting) return;
      clearFreshFailure();
      const rect = arena.getBoundingClientRect();
      model.cursor = {
        active: true,
        x: Math.round(clamp((event.clientX - rect.left) / rect.width * scene.width, 0, scene.width)),
        y: Math.round(clamp((event.clientY - rect.top) / rect.height * scene.height, 0, scene.height)),
      };
      record("cursor", {...model.cursor});
      paint();
    });
    arena.addEventListener("pointerleave", () => {
      if (!model || !model.cursor.active || model.terminal || model.submitting) return;
      model.cursor = {active: false, x: 0, y: 0};
      record("cursor", {active: false});
      paint();
    });
    document.querySelectorAll("[data-shaft]").forEach((shaftNode) => shaftNode.addEventListener("wheel", (event) => {
      event.preventDefault();
      setOffset(Number(shaftNode.dataset.shaft), event.deltaY > 0 ? Number(scene.offset_step) : -Number(scene.offset_step));
    }, {passive: false}));
    document.querySelectorAll("[data-shaft-control]").forEach((node) => node.addEventListener("wheel", (event) => {
      event.preventDefault();
      setOffset(Number(node.dataset.shaftControl), event.deltaY > 0 ? Number(scene.offset_step) : -Number(scene.offset_step));
    }, {passive: false}));
    document.querySelectorAll("[data-shaft-up]").forEach((button) => button.addEventListener("click", () => setOffset(Number(button.dataset.shaftUp), -Number(scene.offset_step))));
    document.querySelectorAll("[data-shaft-down]").forEach((button) => button.addEventListener("click", () => setOffset(Number(button.dataset.shaftDown), Number(scene.offset_step))));
    document.querySelectorAll("[data-shaft-drag]").forEach((drag) => {
      drag.addEventListener("pointerdown", (event) => {
        if (!model || model.terminal || model.submitting) return;
        model.drag = {shaft: Number(drag.dataset.shaftDrag), y: event.clientY, residual: 0};
        drag.setPointerCapture(event.pointerId);
        drag.dataset.dragging = "true";
      });
      drag.addEventListener("pointermove", (event) => {
        if (!model?.drag || model.drag.shaft !== Number(drag.dataset.shaftDrag)) return;
        model.drag.residual += event.clientY - model.drag.y;
        model.drag.y = event.clientY;
        while (Math.abs(model.drag.residual) >= 18) {
          const direction = sign(model.drag.residual);
          setOffset(model.drag.shaft, direction * Number(scene.offset_step));
          model.drag.residual -= direction * 18;
        }
      });
      const release = () => { if (model) model.drag = null; drag.dataset.dragging = "false"; };
      drag.addEventListener("pointerup", release);
      drag.addEventListener("pointercancel", release);
    });
    document.getElementById("scroll-cage-target").addEventListener("click", checkTarget);
    document.getElementById("scroll-cage-check").addEventListener("click", checkTarget);
    document.getElementById("scroll-cage-submit").addEventListener("click", verify);
    model.timer = window.setInterval(stepBody, Number(state.physics.tick_ms));
    cleanupActive = () => {
      if (model?.timer) window.clearInterval(model.timer);
      cleanupActive = null;
    };
    paint();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {rootSelector: ".scroll-cage", render};
})();
