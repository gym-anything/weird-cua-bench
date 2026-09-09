(() => {
  "use strict";

  const KEY_TO_CONTROL = {
    w: "forward", arrowup: "forward",
    s: "back", arrowdown: "back",
    a: "strafe_left", arrowleft: "strafe_left",
    d: "strafe_right", arrowright: "strafe_right",
  };
  const LOOK_DELTAS = {
    left: [-8, 0], right: [8, 0], up: [0, -8], down: [0, 8],
  };
  let model = null;
  let activeCleanup = null;

  function number(value, fallback = 0) {
    const result = Number(value);
    return Number.isFinite(result) ? result : fallback;
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function platformById(id) {
    return (model?.state?.world?.platforms || []).find((item) => item.id === id) || null;
  }

  function contains(platform, x, y, radius = 0) {
    const width = number(platform.size?.[0]);
    const depth = number(platform.size?.[1]);
    return Math.abs(x - number(platform.center?.[0])) <= Math.max(0, width / 2 - radius)
      && Math.abs(y - number(platform.center?.[1])) <= Math.max(0, depth / 2 - radius);
  }

  function distanceToRect(platform, x, y) {
    const dx = Math.max(Math.abs(x - number(platform.center?.[0])) - number(platform.size?.[0]) / 2, 0);
    const dy = Math.max(Math.abs(y - number(platform.center?.[1])) - number(platform.size?.[1]) / 2, 0);
    return Math.hypot(dx, dy);
  }

  function clampInside(platform, x, y, radius) {
    const cx = number(platform.center?.[0]);
    const cy = number(platform.center?.[1]);
    const halfW = number(platform.size?.[0]) / 2;
    const halfD = number(platform.size?.[1]) / 2;
    return [
      Math.max(cx - halfW + radius, Math.min(cx + halfW - radius, x)),
      Math.max(cy - halfD + radius, Math.min(cy + halfD - radius, y)),
    ];
  }

  function chooseLanding(current, x, y, moveX, moveY) {
    const rules = model.state.world.rules;
    const radius = number(rules.player_radius);
    const currentZ = number(current.center?.[2]);
    const gap = number(rules.walkable_gap) + radius * 2 + 0.04;
    const maxDrop = number(rules.max_drop);
    const candidates = [];
    for (const platform of model.state.world.platforms || []) {
      if (platform.id === current.id) continue;
      const drop = currentZ - number(platform.center?.[2]);
      if (drop <= 0.01 || drop > maxDrop + 1e-6) continue;
      const distance = distanceToRect(platform, x, y);
      if (distance > gap) continue;
      const toward = (number(platform.center?.[0]) - x) * moveX + (number(platform.center?.[1]) - y) * moveY;
      if (toward <= 0) continue;
      candidates.push({platform, distance, drop});
    }
    candidates.sort((first, second) => first.distance - second.distance || second.drop - first.drop || String(first.platform.id).localeCompare(String(second.platform.id)));
    return candidates[0]?.platform || null;
  }

  function pushEvent(record) {
    if (!model) return null;
    const event = {
      seq: model.events.length + 1,
      t_ms: Math.max(0, Math.round((performance.now() - model.startedAt) * 1000) / 1000),
      ...record,
    };
    model.events.push(event);
    return event;
  }

  function updateHud() {
    if (!model) return;
    const support = platformById(model.platformId);
    const altitude = document.querySelector("#downsky-altitude");
    if (altitude) altitude.textContent = `${number(model.z).toFixed(1)} SKY-M`;
    const supportNode = document.querySelector("#downsky-support");
    if (supportNode) supportNode.textContent = model.falling ? "SUPPORT LOST" : support?.kind === "exit" ? "PAVILION FLOOR" : "TERRACE SUPPORT";
    const root = document.querySelector(".downsky-causeway");
    if (root) {
      root.dataset.support = model.platformId || "unknown";
      root.dataset.falling = String(Boolean(model.falling));
      root.dataset.completed = String(Boolean(model.completed));
    }
  }

  function project(point, canvas) {
    const state = model.state.world;
    const start = model;
    const dx = number(point[0]) - start.x;
    const dy = number(point[1]) - start.y;
    const forward = Math.cos(start.heading) * dx + Math.sin(start.heading) * dy;
    const side = -Math.sin(start.heading) * dx + Math.cos(start.heading) * dy;
    if (forward < 0.18) return null;
    const focal = Math.min(canvas.width, canvas.height) * 0.86;
    const horizon = canvas.height * 0.49;
    const cameraZ = start.z + number(state.rules.eye_height);
    const vertical = number(point[2]) - cameraZ;
    return {
      x: canvas.width / 2 + side / forward * focal,
      y: horizon - (vertical / forward + Math.tan(start.pitch)) * focal,
      depth: forward,
    };
  }

  // Clip faces at the camera plane instead of hiding an entire terrace when
  // one corner passes behind the viewer (including the current support).
  function clipNear(points) {
    const distance = (point) => Math.cos(model.heading) * (point[0] - model.x)
      + Math.sin(model.heading) * (point[1] - model.y) - 0.180001;
    const clipped = [];
    for (let i = 0; i < points.length; i += 1) {
      const a = points[i]; const b = points[(i + 1) % points.length];
      const da = distance(a); const db = distance(b);
      if (da >= 0) clipped.push(a);
      if ((da >= 0) !== (db >= 0)) {
        const t = da / (da - db);
        clipped.push(a.map((value, axis) => value + (b[axis] - value) * t));
      }
    }
    return clipped;
  }

  function drawCloud(ctx, cloud, canvas) {
    const projected = project([number(cloud.x), number(cloud.y), number(cloud.z)], canvas);
    if (!projected || projected.depth < 5) return;
    const size = Math.max(5, 86 / projected.depth * number(cloud.scale, 1));
    ctx.save();
    ctx.globalAlpha = Math.max(0.08, Math.min(0.28, 1.2 / projected.depth));
    ctx.fillStyle = ["#fff8ee", "#fff1f5", "#f1faff", "#fff4d8"][number(cloud.tone) % 4];
    ctx.beginPath();
    ctx.ellipse(projected.x, projected.y, size * 1.45, size * 0.48, 0, 0, Math.PI * 2);
    ctx.ellipse(projected.x - size * 0.6, projected.y + size * 0.04, size * 0.72, size * 0.4, 0, 0, Math.PI * 2);
    ctx.ellipse(projected.x + size * 0.65, projected.y + size * 0.03, size * 0.78, size * 0.42, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function drawPlatform(ctx, platform, canvas, palette) {
    const cx = number(platform.center?.[0]);
    const cy = number(platform.center?.[1]);
    const z = number(platform.center?.[2]);
    const width = number(platform.size?.[0]);
    const depth = number(platform.size?.[1]);
    const thickness = number(platform.thickness, 0.36);
    const corners = [
      [cx - width / 2, cy - depth / 2, z],
      [cx + width / 2, cy - depth / 2, z],
      [cx + width / 2, cy + depth / 2, z],
      [cx - width / 2, cy + depth / 2, z],
    ];
    const bottoms = [
      [cx - width / 2, cy - depth / 2, z - thickness],
      [cx + width / 2, cy - depth / 2, z - thickness],
      [cx + width / 2, cy + depth / 2, z - thickness],
      [cx - width / 2, cy + depth / 2, z - thickness],
    ];
    const paletteTop = platform.kind === "exit" ? palette.accent : palette.top;
    const sideColor = platform.kind === "exit" ? "#543f99" : palette.edge;
    const polygon = (points, fill, stroke = null) => {
      points = clipNear(points).map((point) => project(point, canvas));
      if (points.length < 3 || points.some((point) => !point)) return;
      ctx.beginPath();
      points.forEach((point, index) => index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y));
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
      if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1.4; ctx.stroke(); }
    };
    const sides = [[0, 1], [1, 2], [2, 3], [3, 0]];
    sides.sort((first, second) => {
      const depthOf = (point) => Math.cos(model.heading) * (point[0] - model.x) + Math.sin(model.heading) * (point[1] - model.y);
      const a = (depthOf(corners[first[0]]) + depthOf(corners[first[1]])) / 2;
      const b = (depthOf(corners[second[0]]) + depthOf(corners[second[1]])) / 2;
      return b - a;
    });
    for (const [first, second] of sides) polygon([corners[first], corners[second], bottoms[second], bottoms[first]], sideColor);
    polygon(corners, paletteTop, platform.kind === "exit" ? "#fff3b3" : "rgba(73,44,91,.65)");
    ctx.save();
    ctx.globalAlpha = 0.26;
    ctx.strokeStyle = platform.kind === "exit" ? "#fff8c2" : "#fff4cf";
    ctx.lineWidth = 1;
    for (let offset = -3; offset < 4; offset += 1) {
      const segment = clipNear([[cx - width / 2, cy + offset * depth / 8, z + 0.01], [cx + width / 2, cy + offset * depth / 8, z + 0.01]]);
      const a = segment.length ? project(segment[0], canvas) : null;
      const b = segment.length > 1 ? project(segment[1], canvas) : null;
      if (a && b) { ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
    }
    ctx.restore();
    if (platform.kind === "exit") {
      const radius = number(model.state.world.rules.finish_radius);
      const ring = (height) => Array.from({length: 64}, (_, i) => {
        const angle = i * Math.PI / 32;
        return [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle), z + height];
      });
      const floor = ring(0.015); const crown = ring(1.6);
      for (let i = 0; i < floor.length; i += 1) {
        const next = (i + 1) % floor.length;
        polygon([floor[i], floor[next], crown[next], crown[i]], "rgba(255,245,184,.13)");
      }
      polygon(floor, "#fff5b8", "#fffbea");
      polygon(crown, "rgba(255,245,184,.35)", "#fffbea");
      const center = project([cx, cy, z + 1.6], canvas);
      if (center) {
        ctx.save();
        ctx.shadowColor = "#fff4a8";
        ctx.shadowBlur = 18;
        ctx.fillStyle = "#fff5b8";
        ctx.beginPath(); ctx.arc(center.x, center.y, Math.max(3, 13 / center.depth), 0, Math.PI * 2); ctx.fill();
        ctx.restore();
        ctx.fillStyle = "#543f99";
        ctx.font = "700 12px ui-monospace, monospace";
        ctx.fillText("EXIT", center.x + 10, center.y - 9);
      }
    }
  }

  function drawScene() {
    if (!model) return;
    const canvas = document.querySelector("#downsky-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const palette = model.state.palette || {};
    const sky = ctx.createLinearGradient(0, 0, 0, canvas.height);
    sky.addColorStop(0, palette.sky || "#d9f1f2");
    sky.addColorStop(0.55, palette.haze || "#f8d8bc");
    sky.addColorStop(1, "#fff4d5");
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "rgba(255,255,255,.28)";
    ctx.fillRect(0, canvas.height * 0.48, canvas.width, canvas.height * 0.52);
    for (const cloud of model.state.world.clouds || []) drawCloud(ctx, cloud, canvas);
    const platforms = [...(model.state.world.platforms || [])].sort((first, second) => {
      const a = project(first.center, canvas)?.depth || -1;
      const b = project(second.center, canvas)?.depth || -1;
      return b - a;
    });
    for (const platform of platforms) drawPlatform(ctx, platform, canvas, palette);
    const eye = project([model.x, model.y, model.z + 0.05], canvas);
    ctx.save();
    ctx.strokeStyle = "rgba(67,42,83,.78)";
    ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(canvas.width / 2 - 10, canvas.height / 2); ctx.lineTo(canvas.width / 2 + 10, canvas.height / 2); ctx.moveTo(canvas.width / 2, canvas.height / 2 - 10); ctx.lineTo(canvas.width / 2, canvas.height / 2 + 10); ctx.stroke();
    ctx.fillStyle = "rgba(60,39,68,.7)";
    ctx.font = "700 11px ui-monospace, monospace";
    ctx.fillText(model.falling ? "SUPPORT LOST" : "NO JUMP", 18, canvas.height - 18);
    if (eye) {
      ctx.fillStyle = "rgba(255,255,255,.35)";
      ctx.beginPath(); ctx.arc(eye.x, eye.y, 2, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }

  function updateAfterMotion() {
    const support = platformById(model.platformId);
    model.z = number(support?.center?.[2], model.z);
    if (support?.id === model.state.world.exit_platform_id && !model.completed) {
      const contactRadius = number(model.state.world.rules.finish_radius);
      if (Math.hypot(model.x - number(support.center?.[0]), model.y - number(support.center?.[1])) <= contactRadius) {
        model.completed = true;
        if (model.timer) window.clearInterval(model.timer);
        pushEvent({kind: "finish", input_source: "physical_contact"});
        submitResult(true);
      }
    }
    updateHud();
    drawScene();
  }

  function tick() {
    if (!model || model.completed || model.falling) return;
    const rules = model.state.world.rules;
    let current = platformById(model.platformId);
    if (!current) return;
    let dx = 0; let dy = 0;
    if (model.keys.forward) { dx += Math.cos(model.heading); dy += Math.sin(model.heading); }
    if (model.keys.back) { dx -= Math.cos(model.heading); dy -= Math.sin(model.heading); }
    if (model.keys.strafe_right) { dx += Math.cos(model.heading + Math.PI / 2); dy += Math.sin(model.heading + Math.PI / 2); }
    if (model.keys.strafe_left) { dx -= Math.cos(model.heading + Math.PI / 2); dy -= Math.sin(model.heading + Math.PI / 2); }
    const magnitude = Math.hypot(dx, dy);
    if (magnitude > 1e-9) {
      dx /= magnitude; dy /= magnitude;
      const distance = number(rules.move_speed) * number(rules.tick_ms) / 1000;
      const substeps = Math.max(1, Math.ceil(distance / 0.08));
      const step = distance / substeps;
      for (let index = 0; index < substeps; index += 1) {
        const nx = model.x + dx * step;
        const ny = model.y + dy * step;
        if (contains(current, nx, ny, number(rules.player_radius))) {
          model.x = nx; model.y = ny;
          continue;
        }
        const landing = chooseLanding(current, model.x, model.y, dx, dy);
        if (!landing) {
          model.falling = true;
          model.fallAt = performance.now();
          pushEvent({kind: "tick", dt_ms: number(rules.tick_ms), input_source: "physics"});
          model.keys = {forward: false, back: false, strafe_left: false, strafe_right: false};
          if (model.timer) window.clearInterval(model.timer);
          updateHud(); drawScene();
          window.setTimeout(() => submitResult(false), 260);
          return;
        }
        [model.x, model.y] = clampInside(landing, nx, ny, number(rules.player_radius));
        model.platformId = landing.id;
        current = landing;
      }
    }
    pushEvent({kind: "tick", dt_ms: number(rules.tick_ms), input_source: "physics"});
    updateAfterMotion();
  }

  function setKey(control, down, inputSource) {
    if (!model || model.completed || model.falling || model.interaction === "full" && inputSource !== "keyboard" || model.interaction === "simplified" && inputSource !== "control_button") return;
    if (Boolean(model.keys[control]) === Boolean(down)) return;
    clearFailure();
    model.keys[control] = Boolean(down);
    pushEvent({kind: down ? "key_down" : "key_up", control, input_source: inputSource});
    updateHud();
  }

  function applyLook(dx, dy, inputSource) {
    if (!model || model.completed || model.falling) return;
    if (model.interaction === "full" && inputSource !== "viewport_drag") return;
    if (model.interaction === "simplified" && inputSource !== "look_button") return;
    clearFailure();
    const sensitivity = number(model.state.world.rules.look_sensitivity, 0.008);
    // Sparse drag delivery can cross most of the viewport in one sample.
    const parts = Math.max(1, Math.ceil(Math.max(Math.abs(dx), Math.abs(dy)) / 500));
    for (let i = 0; i < parts; i += 1) {
      model.heading += number(dx) / parts * sensitivity;
      model.pitch = Math.max(-0.34, Math.min(0.34, model.pitch + number(dy) / parts * sensitivity * 0.55));
      pushEvent({kind: "look", dx: number(dx) / parts, dy: number(dy) / parts, input_source: inputSource});
    }
    drawScene();
  }

  function clearFailure() {
    const root = document.querySelector(".downsky-causeway");
    if (!root?.classList.contains("is-failed")) return;
    root.classList.remove("is-failed");
    document.querySelector(".downsky-verdict").innerHTML = "";
    model.helpers.setReadout("REACH THE PAVILION", "idle");
  }

  async function submitResult(completed) {
    if (!model || model.submitting) return;
    model.submitting = true;
    const submitted = model;
    submitted.pendingResult = completed;
    const retry = document.querySelector("#downsky-retry");
    if (retry) retry.hidden = true;
    const payload = {
      mechanic_id: submitted.state.mechanic_id,
      task_id: submitted.state.task_id,
      challenge_id: submitted.state.challenge_id,
      interaction: submitted.interaction,
      completed: Boolean(completed),
      events: clone(submitted.events),
      final_position: {x: submitted.x, y: submitted.y, z: submitted.z, platform_id: submitted.platformId},
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (model !== submitted) return;
      if (outcome.passed === true) {
        submitted.completed = true;
        document.querySelector(".downsky-causeway")?.classList.add("is-passed");
        submitted.helpers.setReadout("PASS · PAVILION REACHED", "passed");
        const verdict = document.querySelector(".downsky-verdict");
        if (verdict) verdict.innerHTML = "<b>PASS</b><span>THE CAUSEWAY HOLDS</span>";
      } else if (outcome.passed === false) {
        if (outcome.state) await render(outcome.state, submitted.helpers);
        const root = document.querySelector(".downsky-causeway");
        root?.classList.add("is-failed");
        const verdict = document.querySelector(".downsky-verdict");
        if (verdict) verdict.innerHTML = "<b>FAIL</b><span>NEW CAUSEWAY READY</span>";
        submitted.helpers.setReadout(completed ? "FAIL · ROUTE REJECTED" : "FAIL · NEW CAUSEWAY ISSUED", "error");
      } else {
        throw new Error("missing result decision");
      }
    } catch (_error) {
      submitted.submitting = false;
      submitted.helpers.setReadout("LINK LOST · TRY AGAIN", "error");
      if (retry) retry.hidden = false;
    }
  }

  function bindHoldButtons() {
    const cleanup = [];
    document.querySelectorAll("[data-hold]").forEach((button) => {
      const control = button.dataset.hold;
      const press = (event) => { if (event.button !== 0) return; event.preventDefault(); button.setPointerCapture(event.pointerId); setKey(control, true, "control_button"); };
      const release = (event) => { event.preventDefault(); setKey(control, false, "control_button"); if (button.hasPointerCapture(event.pointerId)) button.releasePointerCapture(event.pointerId); };
      button.addEventListener("pointerdown", press);
      button.addEventListener("pointerup", release);
      button.addEventListener("pointercancel", release);
      button.addEventListener("lostpointercapture", release);
      cleanup.push(() => {
        button.removeEventListener("pointerdown", press); button.removeEventListener("pointerup", release);
        button.removeEventListener("pointercancel", release); button.removeEventListener("lostpointercapture", release);
      });
    });
    document.querySelectorAll("[data-look]").forEach((button) => {
      const handler = () => { const delta = LOOK_DELTAS[button.dataset.look] || [0, 0]; applyLook(delta[0], delta[1], "look_button"); };
      button.addEventListener("click", handler); cleanup.push(() => button.removeEventListener("click", handler));
    });
    return cleanup;
  }

  async function render(state, helpers) {
    if (activeCleanup) activeCleanup();
    document.body.dataset.mechanic = "downsky-causeway";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const interaction = state.control_condition?.interaction || "full";
    const start = state.world.start;
    model = {
      state,
      helpers,
      interaction,
      startedAt: performance.now(),
      x: number(start.position?.[0]),
      y: number(start.position?.[1]),
      z: number(start.position?.[2]),
      heading: number(start.heading),
      pitch: number(start.pitch, -0.04),
      platformId: String(start.platform_id),
      keys: {forward: false, back: false, strafe_left: false, strafe_right: false},
      events: [],
      falling: false,
      completed: false,
      submitting: false,
      timer: null,
    };
    window.downskyCausewayModel = model;
    const simplified = interaction === "simplified";
    helpers.app.innerHTML = `
      <section class="downsky-causeway" data-interaction="${helpers.text(interaction)}" data-falling="false" data-completed="false" tabindex="0">
        <div class="downsky-verdict" aria-live="assertive"></div>
        <header class="downsky-head">
          <div><span>DOWN-SKY CARTOGRAPHY / NO-JUMP EXPEDITION</span><h1>${helpers.text(state.prompt)}</h1></div>
          <div class="downsky-badge">HEIGHT<br><b>MATTERS</b></div>
        </header>
        <section class="downsky-workbench">
          <div class="downsky-view-wrap">
            <canvas id="downsky-canvas" width="900" height="520" aria-label="First-person floating terrace view"></canvas>
            <div class="downsky-view-caption"><span>FIRST-PERSON TERRACE VIEW</span><b>DOWN-SKY EXPEDITION</b></div>
          </div>
          <aside class="downsky-console">
            <div class="downsky-readouts"><span>SUPPORT</span><b id="downsky-support">TERRACE SUPPORT</b><span>ALTITUDE</span><b id="downsky-altitude">-- SKY-M</b></div>
            <div class="downsky-rule-card"><b>NO JUMP</b></div>
            ${simplified ? `
              <div class="downsky-proxy" aria-label="Causeway proxy controls">
                <span>MOVE / HOLD</span><div class="downsky-dpad"><button type="button" data-hold="forward" aria-label="Move forward">▲</button><button type="button" data-hold="strafe_left" aria-label="Strafe left">◀</button><button type="button" data-hold="back" aria-label="Move backward">▼</button><button type="button" data-hold="strafe_right" aria-label="Strafe right">▶</button></div>
                <span>LOOK / STEP</span><div class="downsky-look-grid"><button type="button" data-look="up" aria-label="Look up">↑</button><button type="button" data-look="left" aria-label="Look left">←</button><button type="button" data-look="down" aria-label="Look down">↓</button><button type="button" data-look="right" aria-label="Look right">→</button></div>
              </div>` : `<div class="downsky-full-hint"><b>WASD / ARROWS</b><span>Hold to walk and strafe</span><b>DRAG THE VIEW</b><span>Look around</span></div>`}
            <button type="button" class="downsky-abandon" id="downsky-retry" hidden>RETRY RESULT</button>
            <button type="button" class="downsky-abandon" id="downsky-abandon">ABANDON ROUTE</button>
          </aside>
        </section>
        <footer class="downsky-foot"><div class="readout" data-status="idle">REACH THE PAVILION</div><span>DOWN-SKY CARTOGRAPHY</span></footer>
        ${helpers.cheatPanelTemplate()}
      </section>`;
    const canvas = document.querySelector("#downsky-canvas");
    const shell = document.querySelector(".downsky-causeway");
    const keydown = (event) => {
      if (event.repeat || model.completed || model.falling || model.interaction !== "full") return;
      const control = KEY_TO_CONTROL[String(event.key || "").toLowerCase()];
      if (!control) return;
      event.preventDefault(); setKey(control, true, "keyboard");
    };
    const keyup = (event) => {
      if (model.interaction !== "full") return;
      const control = KEY_TO_CONTROL[String(event.key || "").toLowerCase()];
      if (!control) return;
      event.preventDefault(); setKey(control, false, "keyboard");
    };
    window.addEventListener("keydown", keydown); window.addEventListener("keyup", keyup);
    let dragging = false;
    let lastPointer = null;
    const pointerdown = (event) => { if (model.interaction !== "full" || event.button !== 0) return; clearFailure(); dragging = true; lastPointer = [event.clientX, event.clientY]; canvas.setPointerCapture?.(event.pointerId); };
    const pointermove = (event) => { if (!dragging || !lastPointer) return; const dx = event.clientX - lastPointer[0]; const dy = event.clientY - lastPointer[1]; lastPointer = [event.clientX, event.clientY]; if (dx || dy) applyLook(dx, dy, "viewport_drag"); };
    const pointerup = (event) => { dragging = false; lastPointer = null; try { canvas.releasePointerCapture?.(event.pointerId); } catch (_error) { /* already released */ } };
    canvas.addEventListener("pointerdown", pointerdown); canvas.addEventListener("pointermove", pointermove); canvas.addEventListener("pointerup", pointerup); canvas.addEventListener("pointercancel", pointerup); canvas.addEventListener("lostpointercapture", pointerup);
    const buttonCleanup = simplified ? bindHoldButtons() : [];
    const releaseKeys = () => {
      for (const control of Object.keys(model.keys)) setKey(control, false, simplified ? "control_button" : "keyboard");
      dragging = false; lastPointer = null;
    };
    window.addEventListener("blur", releaseKeys);
    const retryResult = () => submitResult(model.pendingResult);
    document.querySelector("#downsky-retry").addEventListener("click", retryResult);
    const abandon = () => { if (!model.completed) { pushEvent({kind: "abandon", input_source: "route_button"}); model.completed = true; if (model.timer) window.clearInterval(model.timer); submitResult(false); } };
    document.querySelector("#downsky-abandon")?.addEventListener("click", abandon);
    model.timer = window.setInterval(tick, number(state.world.rules.tick_ms, 40));
    activeCleanup = () => {
      window.removeEventListener("keydown", keydown); window.removeEventListener("keyup", keyup);
      window.removeEventListener("blur", releaseKeys);
      canvas.removeEventListener("pointerdown", pointerdown); canvas.removeEventListener("pointermove", pointermove); canvas.removeEventListener("pointerup", pointerup); canvas.removeEventListener("pointercancel", pointerup); canvas.removeEventListener("lostpointercapture", pointerup);
      buttonCleanup.forEach((cleanup) => cleanup()); if (model?.timer) window.clearInterval(model.timer);
    };
    updateHud(); drawScene(); shell?.focus(); helpers.installCheatPanel();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.downsky_causeway = {rootSelector: ".downsky-causeway", render};
})();
