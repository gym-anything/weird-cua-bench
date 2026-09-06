(() => {
  "use strict";

  const SIZE = 900;
  const ORIGIN = SIZE / 2;
  const DISC_RADIUS = 420;
  const IDENTITY = [[1, 0], [0, 0], [0, 0], [1, 0]];
  let model = null;

  const clone = value => JSON.parse(JSON.stringify(value));
  const c = (x, y = 0) => [Number(x), Number(y)];
  const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
  const mul = (a, b) => [a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0]];
  const div = (a, b) => {
    const denominator = b[0] * b[0] + b[1] * b[1];
    return [(a[0] * b[0] + a[1] * b[1]) / denominator, (a[1] * b[0] - a[0] * b[1]) / denominator];
  };
  const conj = z => [z[0], -z[1]];
  const magnitude = z => Math.hypot(z[0], z[1]);
  const scale = (z, amount) => [z[0] * amount, z[1] * amount];
  const multiply = (left, right) => {
    const [a, b, cc, d] = left;
    const [e, f, g, h] = right;
    return [add(mul(a, e), mul(b, g)), add(mul(a, f), mul(b, h)), add(mul(cc, e), mul(d, g)), add(mul(cc, f), mul(d, h))];
  };
  const applyView = (matrix, point) => div(add(mul(matrix[0], point), matrix[1]), add(mul(matrix[2], point), matrix[3]));
  const phi = point => [c(1), scale(point, -1), scale(conj(point), -1), c(1)];
  const inversePhi = point => [c(1), point.slice(), conj(point), c(1)];
  const translation = (start, end) => multiply(inversePhi(end), phi(start));
  const toCanvas = point => [ORIGIN + point[0] * DISC_RADIUS, ORIGIN + point[1] * DISC_RADIUS];
  const sameState = (left, right) => JSON.stringify(left) === JSON.stringify(right);
  const escaped = value => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");

  function geodesicPoint(first, second, t) {
    const mapped = applyView(phi(first), second);
    const length = magnitude(mapped);
    if (length < 1e-9) return first.slice();
    const bounded = Math.min(length, 0.999999);
    const radial = Math.tanh(t * Math.atanh(bounded)) / length;
    return applyView(inversePhi(first), scale(mapped, radial));
  }

  function traceGeodesic(path, first, second, firstPoint) {
    for (let step = firstPoint ? 0 : 1; step <= 8; step += 1) {
      const point = toCanvas(applyView(model.view, geodesicPoint(first, second, step / 8)));
      if (step === 0 && firstPoint) path.moveTo(point[0], point[1]);
      else path.lineTo(point[0], point[1]);
    }
  }

  function polygonPath(vertices) {
    const path = new Path2D();
    vertices.forEach((vertex, index) => traceGeodesic(path, vertex, vertices[(index + 1) % vertices.length], index === 0));
    path.closePath();
    return path;
  }

  function wedgePath(face, sector) {
    const center = face.center;
    const first = face.vertices[sector];
    const second = face.vertices[(sector + 1) % face.vertices.length];
    const path = new Path2D();
    traceGeodesic(path, center, first, true);
    traceGeodesic(path, first, second, false);
    traceGeodesic(path, second, center, false);
    path.closePath();
    return path;
  }

  function motif(ctx, face, sector, path, color) {
    ctx.save();
    ctx.clip(path);
    const center = toCanvas(applyView(model.view, geodesicPoint(face.center, geodesicPoint(face.vertices[sector], face.vertices[(sector + 1) % 7], 0.5), 0.57)));
    ctx.translate(center[0], center[1]);
    ctx.rotate((sector / 7) * Math.PI * 2 + 0.2);
    ctx.globalAlpha = 0.42;
    ctx.strokeStyle = color.glint;
    ctx.lineWidth = 2;
    const motifIndex = Number(color.motif) % 3;
    if (motifIndex === 0) {
      ctx.beginPath(); ctx.moveTo(-14, -4); ctx.lineTo(14, 4); ctx.stroke();
    } else if (motifIndex === 1) {
      ctx.beginPath(); ctx.arc(0, 0, 6, 0, Math.PI * 2); ctx.stroke();
    } else {
      ctx.beginPath(); ctx.moveTo(-9, 5); ctx.lineTo(0, -7); ctx.lineTo(9, 5); ctx.stroke();
    }
    ctx.restore();
  }

  function draw() {
    if (!model?.ctx) return;
    const ctx = model.ctx;
    ctx.clearRect(0, 0, SIZE, SIZE);
    const disc = new Path2D();
    disc.arc(ORIGIN, ORIGIN, DISC_RADIUS, 0, Math.PI * 2);
    ctx.save();
    ctx.clip(disc);

    const sky = ctx.createRadialGradient(ORIGIN - 95, ORIGIN - 140, 25, ORIGIN, ORIGIN, DISC_RADIUS);
    sky.addColorStop(0, "#24313a");
    sky.addColorStop(0.56, "#111b22");
    sky.addColorStop(1, "#060a0d");
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, SIZE, SIZE);

    const byTile = new Map(model.puzzle.faces.map(face => [Number(face.tile_id), face]));
    const sortedTiles = model.puzzle.tiles.slice().sort((left, right) => right.depth - left.depth);
    for (const tile of sortedTiles) {
      if (byTile.has(Number(tile.id))) continue;
      const path = polygonPath(tile.vertices);
      const center = applyView(model.view, tile.center);
      const haze = Math.max(0, Math.min(1, 1 - magnitude(center)));
      ctx.fillStyle = `rgba(26, ${31 + Math.round(haze * 13)}, ${35 + Math.round(haze * 16)}, .74)`;
      ctx.fill(path);
      ctx.strokeStyle = tile.depth === 3 ? "rgba(148,117,72,.16)" : "rgba(178,143,88,.25)";
      ctx.lineWidth = tile.depth === 3 ? 1 : 1.6;
      ctx.stroke(path);
    }

    model.facePaths = [];
    for (const face of model.puzzle.faces) {
      const facePath = polygonPath(face.vertices);
      model.facePaths.push({id: Number(face.id), path: facePath, center: applyView(model.view, face.center)});
      for (let sector = 0; sector < 7; sector += 1) {
        const path = wedgePath(face, sector);
        const color = model.palette[model.current[face.id][sector]];
        const center = toCanvas(applyView(model.view, face.center));
        const edge = toCanvas(applyView(model.view, face.vertices[sector]));
        const glow = Math.max(12, Math.min(180, Math.hypot(edge[0] - center[0], edge[1] - center[1])));
        const gradient = ctx.createRadialGradient(center[0] - glow * .18, center[1] - glow * .22, 1, center[0], center[1], glow);
        gradient.addColorStop(0, color.glint);
        gradient.addColorStop(.42, color.fill);
        gradient.addColorStop(1, color.fill);
        ctx.fillStyle = gradient;
        ctx.fill(path);
        ctx.strokeStyle = "rgba(16,14,13,.72)";
        ctx.lineWidth = 1.5;
        ctx.stroke(path);
        motif(ctx, face, sector, path, color);
      }
      const pointed = Number(face.id) === model.focusedFace || Number(face.id) === model.hoveredFace;
      ctx.strokeStyle = pointed ? "#fff0a6" : "rgba(220,180,102,.74)";
      ctx.lineWidth = pointed ? 4 : 2.2;
      ctx.stroke(facePath);
    }

    const aperture = model.puzzle.activation_radius * DISC_RADIUS;
    ctx.setLineDash([8, 9]);
    ctx.strokeStyle = "rgba(255,230,149,.65)";
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(ORIGIN, ORIGIN, aperture, 0, Math.PI * 2); ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();

    ctx.strokeStyle = "#9b7742";
    ctx.lineWidth = 14;
    ctx.beginPath(); ctx.arc(ORIGIN, ORIGIN, DISC_RADIUS + 7, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = "rgba(255,226,157,.52)";
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(ORIGIN, ORIGIN, DISC_RADIUS - 2, 0, Math.PI * 2); ctx.stroke();
  }

  function canvasPoint(event) {
    const box = model.canvas.getBoundingClientRect();
    return [(event.clientX - box.left) * SIZE / box.width, (event.clientY - box.top) * SIZE / box.height];
  }

  function discPoint(event) {
    const point = canvasPoint(event);
    return [(point[0] - ORIGIN) / DISC_RADIUS, (point[1] - ORIGIN) / DISC_RADIUS];
  }

  function faceAt(event) {
    const point = canvasPoint(event);
    for (let index = model.facePaths.length - 1; index >= 0; index -= 1) {
      if (model.ctx.isPointInPath(model.facePaths[index].path, point[0], point[1])) return model.facePaths[index].id;
    }
    return null;
  }

  function pushViewEvent(event) {
    model.events.push({sequence: model.events.length + 1, ...event});
    model.viewEvents += 1;
  }

  function updatePanel(message) {
    const count = document.querySelector("#circle-twist-count");
    if (count) count.textContent = `${model.twists} / ${model.puzzle.move_budget}`;
    document.querySelectorAll(".twist-meter i").forEach((bar, index) => bar.classList.toggle("used", index < model.twists));
    const selected = document.querySelector("#circle-selection");
    if (selected) selected.textContent = model.focusedFace == null ? "NO FACE CENTERED" : "FACE CENTERED";
    const readout = document.querySelector(".circle-limit-twist .readout");
    if (readout && message) readout.textContent = message;
    document.querySelector(".circle-limit-twist")?.classList.toggle("is-spent", model.twists >= model.puzzle.move_budget);
  }

  function applyTwist(faceId, direction, inputSource) {
    if (model.submitting || model.twists >= model.puzzle.move_budget || ![-1, 1].includes(direction)) return false;
    const face = model.puzzle.faces[faceId];
    const distance = magnitude(applyView(model.view, face.center));
    if (distance > model.puzzle.activation_radius + 0.002) {
      updatePanel("NO CHANGE");
      return false;
    }
    const before = clone(model.current);
    const after = clone(model.current);
    const cycle = model.puzzle.twist_cycles[String(faceId)];
    for (const name of ["own", "ring"]) {
      const positions = cycle[name];
      const values = positions.map(([faceIndex, sector]) => before[faceIndex][sector]);
      const shifted = direction === 1 ? values.slice(-1).concat(values.slice(0, -1)) : values.slice(1).concat(values.slice(0, 1));
      positions.forEach(([faceIndex, sector], index) => { after[faceIndex][sector] = shifted[index]; });
    }
    model.twists += 1;
    model.events.push({
      sequence: model.events.length + 1,
      kind: "twist",
      input_source: inputSource,
      face_id: faceId,
      direction,
      focus_distance: Number(distance.toFixed(7)),
      before_state: before,
      after_state: clone(after),
      twists_after: model.twists,
    });
    model.current = after;
    model.focusedFace = faceId;
    draw();
    updatePanel(direction === 1 ? "CLOCKWISE TWIST RECORDED" : "COUNTER-CLOCKWISE TWIST RECORDED");
    return true;
  }

  function installCanvas() {
    const canvas = model.canvas;
    canvas.addEventListener("contextmenu", event => event.preventDefault());
    canvas.addEventListener("pointermove", event => {
      if (!model.drag) {
        model.hoveredFace = faceAt(event);
        draw();
        return;
      }
      event.preventDefault();
      const next = discPoint(event);
      if (magnitude(next) >= .98) return;
      const previous = model.drag.last;
      if (magnitude(sub(next, previous)) < .001) return;
      model.view = multiply(translation(previous, next), model.view);
      model.drag.distance += magnitude(sub(next, previous));
      model.drag.last = next;
      draw();
    });
    canvas.addEventListener("pointerdown", event => {
      if (model.interaction !== "full" || ![0, 2].includes(event.button) || model.submitting) return;
      const start = discPoint(event);
      if (magnitude(start) >= .98) return;
      event.preventDefault();
      canvas.setPointerCapture(event.pointerId);
      model.drag = {pointerId: event.pointerId, button: event.button, start, last: start, distance: 0};
      canvas.classList.add("is-dragging");
    });
    const finish = (event, cancelled) => {
      if (!model.drag || event.pointerId !== model.drag.pointerId) return;
      const drag = model.drag;
      model.drag = null;
      canvas.classList.remove("is-dragging");
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
      if (magnitude(sub(drag.last, drag.start)) >= .001) {
        pushViewEvent({
          kind: "pan",
          input_source: "mobius_drag",
          start: drag.start.map(value => Number(value.toFixed(7))),
          end: drag.last.map(value => Number(value.toFixed(7))),
        });
      }
      if (!cancelled && drag.distance < .012) {
        const faceId = faceAt(event);
        if (faceId != null) applyTwist(faceId, drag.button === 2 ? 1 : -1, "canvas_click");
      }
    };
    canvas.addEventListener("pointerup", event => finish(event, false));
    canvas.addEventListener("pointercancel", event => finish(event, true));
    canvas.addEventListener("click", event => {
      if (model.interaction !== "simplified" || model.submitting) return;
      const faceId = faceAt(event);
      if (faceId == null) return;
      const current = applyView(model.view, model.puzzle.faces[faceId].center);
      if (magnitude(current) >= .985) return;
      pushViewEvent({kind: "focus", input_source: "focus_click", face_id: faceId});
      model.view = multiply(phi(current), model.view);
      model.focusedFace = faceId;
      draw();
      updatePanel("FACE CENTERED");
    });
    canvas.addEventListener("mouseleave", () => {
      if (!model.drag) { model.hoveredFace = null; draw(); }
    });
  }

  function resetPuzzle() {
    if (!model || model.submitting) return;
    model.current = clone(model.puzzle.initial_state);
    model.view = clone(IDENTITY);
    model.events = [];
    model.twists = 0;
    model.viewEvents = 0;
    model.focusedFace = null;
    model.hoveredFace = null;
    draw();
    updatePanel("SCRAMBLE RESTORED");
  }

  async function retryFresh() {
    if (!model?.pendingState) return;
    const state = model.pendingState;
    const helpers = model.helpers;
    await helpers.render(state);
    const root = document.querySelector(".circle-limit-twist");
    if (root) root.dataset.freshFailure = "true";
  }

  async function submit() {
    if (!model || model.submitting) return;
    model.submitting = true;
    updatePanel("VERIFYING…");
    const completed = model.current.every(face => new Set(face).size === 1) && model.twists <= model.puzzle.move_budget;
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      events: model.events,
      final_state: clone(model.current),
      twist_count: model.twists,
      view_event_count: model.viewEvents,
      completed,
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      const root = document.querySelector(".circle-limit-twist");
      if (outcome.passed === true) {
        root?.classList.add("is-passed");
        model.helpers.setReadout("PASS", "passed");
      } else {
        model.pendingState = outcome.state || null;
        root?.classList.add("is-failed");
        if (root && outcome.state) root.dataset.failureReady = "true";
        model.helpers.setReadout("FAIL", "error");
      }
    } catch (_error) {
      document.querySelector(".circle-limit-twist")?.classList.add("is-failed");
      model.helpers.setReadout("FAIL", "error");
    }
  }

  function controlMarkup(interaction) {
    if (interaction === "simplified") {
      return `<div class="twist-proxy" aria-label="Turn controls">
        <div id="circle-selection">NO FACE CENTERED</div>
        <button type="button" data-direction="-1" aria-label="Twist centered face counter-clockwise"><b>↶</b><span>COUNTER</span></button>
        <button type="button" data-direction="1" aria-label="Twist centered face clockwise"><b>↷</b><span>CLOCKWISE</span></button>
      </div>`;
    }
    return "";
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "circle-limit-twist-v1";
    const interaction = String(state.control_condition?.interaction || "full");
    helpers.app.innerHTML = `<main class="circle-limit-twist" data-interaction="${escaped(interaction)}">
      <header class="circle-header">
        <div class="circle-title"><span>NON-EUCLIDEAN RESTORATION OFFICE · PLATE 07</span><h1>Circle Limit Twist</h1></div>
        <p>${escaped(state.prompt)}</p>
      </header>
      <section class="circle-stage">
        <aside class="circle-index">
          <span class="eyebrow">SOLVED CONDITION</span>
          <div class="monochrome-mark"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
          <h2>ONE COLOR<br>PER HEPTAGON</h2>
        </aside>
        <div class="disc-vault">
          <div class="vault-compass"><span>N</span><span>E</span><span>S</span><span>W</span></div>
          <canvas id="circle-disc" width="${SIZE}" height="${SIZE}" aria-label="Colored heptagon puzzle"></canvas>
        </div>
        <aside class="circle-console">
          <span class="eyebrow">CONTROL SURFACE · ${interaction.toUpperCase()}</span>
          ${controlMarkup(interaction)}
          <div class="twist-meter"><span>TWISTS USED</span><b id="circle-twist-count">0 / ${state.puzzle.move_budget}</b><div>${Array.from({length: state.puzzle.move_budget}, (_, index) => `<i style="--n:${index}"></i>`).join("")}</div></div>
          <div class="readout" data-status="idle">READY</div>
          <button id="circle-reset" type="button">RESET SCRAMBLE</button>
          <button id="circle-certify" type="button">${escaped(state.submit_label || "CERTIFY")}</button>
        </aside>
      </section>
      <div class="circle-overlay fail"><b>FAIL</b><button id="circle-retry" type="button">FRESH CHALLENGE</button></div>
      <div class="circle-overlay pass"><b>PASS</b></div>
    </main>`;
    const canvas = document.querySelector("#circle-disc");
    model = {
      state,
      helpers,
      interaction,
      puzzle: state.puzzle,
      palette: state.puzzle.palette,
      current: clone(state.puzzle.initial_state),
      view: clone(IDENTITY),
      events: [],
      twists: 0,
      viewEvents: 0,
      focusedFace: null,
      hoveredFace: null,
      facePaths: [],
      drag: null,
      submitting: false,
      pendingState: null,
      canvas,
      ctx: canvas.getContext("2d"),
    };
    installCanvas();
    document.querySelectorAll(".twist-proxy button").forEach(button => button.addEventListener("click", () => {
      if (model.focusedFace != null) applyTwist(model.focusedFace, Number(button.dataset.direction), "proxy_buttons");
      else updatePanel("NO FACE CENTERED");
    }));
    document.querySelector("#circle-reset")?.addEventListener("click", resetPuzzle);
    document.querySelector("#circle-certify")?.addEventListener("click", submit);
    document.querySelector("#circle-retry")?.addEventListener("click", retryFresh);
    window.circleLimitTwistModel = model;
    window.circleLimitTwistMath = {applyView, multiply, phi, translation};
    draw();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.circle_limit_twist = {render, rootSelector: ".circle-limit-twist"};
})();
