(() => {
  "use strict";

  const KEY_TO_CONTROL = {
    w: "forward", arrowup: "forward",
    s: "back", arrowdown: "back",
    a: "strafe_left", arrowleft: "strafe_left",
    d: "strafe_right", arrowright: "strafe_right",
  };
  const LOOK_BUTTONS = {left: [-9, 0], right: [9, 0], up: [0, -9], down: [0, 9]};
  let model = null;
  let activeCleanup = null;
  let sceneBlocks = [];

  function number(value, fallback = 0) {
    const result = Number(value);
    return Number.isFinite(result) ? result : fallback;
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function chamber() {
    return model.state.world.chamber;
  }

  function pointById(id) {
    return (chamber().actuators || []).find((item) => item.id === id) || null;
  }

  function launcherById(id) {
    return (chamber().launchers || []).find((item) => item.id === id) || null;
  }

  function projectPoint(point) {
    if (!model) return null;
    const canvas = document.querySelector("#rising-causeway-canvas");
    if (!canvas) return null;
    const dx = number(point?.[0]) - model.x;
    const dy = number(point?.[1]) - model.y;
    const forward = Math.cos(model.heading) * dx + Math.sin(model.heading) * dy;
    const side = -Math.sin(model.heading) * dx + Math.cos(model.heading) * dy;
    if (forward < 0.18) return null;
    const focal = Math.min(canvas.width, canvas.height) * 0.92;
    const horizon = canvas.height * 0.48;
    const vertical = number(point?.[2]) - (model.z + number(chamber().rules.eye_height));
    return {
      x: canvas.width / 2 + (side / forward) * focal,
      y: horizon - (vertical / forward + Math.tan(model.pitch)) * focal,
      depth: forward,
    };
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

  function surfaceCandidates(x, y) {
    const geometry = chamber().geometry || {};
    const covers = (surface) => surface && number(surface.x0) - 0.0001 <= x && x <= number(surface.x1) + 0.0001
      && number(surface.y0) - 0.0001 <= y && y <= number(surface.y1) + 0.0001;
    const candidates = [];
    if (covers(geometry.approach_surface)) candidates.push(number(geometry.approach_surface.z));
    for (const extension of geometry.red_extensions || []) {
      if (model.redStage >= number(extension.required_stage) && covers(extension)) candidates.push(number(extension.z));
    }
    if (model.stairEnd === "left" || model.stairEnd === "right") {
      const key = model.stairEnd === "left" ? "z_left" : "z_right";
      for (const step of geometry.stair_steps || []) if (covers(step)) candidates.push(number(step[key]));
    }
    if (covers(geometry.launch_surface)) candidates.push(number(geometry.launch_surface.z));
    if (model.landed && model.primed) {
      const platform = (geometry.landing_platforms || []).find((item) => item.launcher_id === model.primed);
      if (covers(platform)) candidates.push(number(platform.z));
    }
    return candidates;
  }

  function supportZAt(x, y) {
    const candidates = surfaceCandidates(x, y);
    if (!candidates.length) return null;
    const current = number(model.z);
    const maxUp = number(chamber().rules.max_step_up, 0.46);
    const maxDown = number(chamber().rules.max_step_down, 0.72);
    const accessible = candidates.filter((z) => z - current <= maxUp + 0.0001 && current - z <= maxDown + 0.0001);
    if (!accessible.length) return null;
    return accessible.sort((a, b) => Math.abs(a - current) - Math.abs(b - current))[0];
  }

  function supportZ() { return supportZAt(model.x, model.y); }

  function updateHud(message = null, status = null) {
    if (!model) return;
    const root = document.querySelector(".rising-causeway");
    if (root) {
      root.dataset.failed = String(Boolean(model.failed));
      root.dataset.completed = String(Boolean(model.completed));
      root.dataset.flight = String(Boolean(model.inFlight));
    }
    const stage = document.querySelector("#rising-red-stage");
    if (stage) stage.textContent = `${model.redStage}/${number(chamber().rules.red_stage_target, 3)}`;
    const stair = document.querySelector("#rising-stair-state");
    if (stair) stair.textContent = model.stairEnd ? `${model.stairEnd.toUpperCase()} HIGH` : "UNSET";
    const launch = document.querySelector("#rising-launch-state");
    if (launch) launch.textContent = model.primed ? `${model.primed.toUpperCase()} PRIMED` : "UNPRIMED";
    const position = document.querySelector("#rising-position");
    if (position) position.textContent = `X ${model.x.toFixed(1)} · Y ${model.y.toFixed(1)} · Z ${model.z.toFixed(1)}`;
    if (message) model.helpers.setReadout(message, status || "idle");
  }

  function polygon(ctx, points, fill, stroke = null) {
    if (!points || points.some((point) => !point)) return;
    ctx.beginPath();
    points.forEach((point, index) => index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y));
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1.3; ctx.stroke(); }
  }

  // Clip world polygons at the camera plane before projecting. Dropping an
  // entire surface when one corner is behind the avatar hides its own floor.
  function projectPolygon(points) {
    const depth = (p) => Math.cos(model.heading) * (p[0] - model.x) + Math.sin(model.heading) * (p[1] - model.y);
    const clipped = [];
    const near = 0.181;
    for (let i = 0; i < points.length; i += 1) {
      const a = points[i]; const b = points[(i + 1) % points.length];
      const da = depth(a); const db = depth(b);
      if (da >= near) clipped.push(a);
      if ((da >= near) !== (db >= near)) {
        const t = (near - da) / (db - da);
        clipped.push(a.map((value, axis) => value + t * (b[axis] - value)));
      }
    }
    return clipped.length >= 3 ? clipped.map(projectPoint) : null;
  }

  function drawFloor(ctx, x0, x1, yHalf, z, fill, stroke) {
    const corners = projectPolygon([[x0, -yHalf, z], [x1, -yHalf, z], [x1, yHalf, z], [x0, yHalf, z]]);
    polygon(ctx, corners, fill, stroke);
    if (corners?.every(Boolean)) {
      ctx.save();
      ctx.globalAlpha = 0.22;
      ctx.strokeStyle = "#dce8df";
      for (let x = x0 + 0.6; x < x1; x += 0.65) {
        const a = projectPoint([x, -yHalf, z + 0.006]);
        const b = projectPoint([x, yHalf, z + 0.006]);
        if (a && b) { ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
      }
      ctx.restore();
    }
  }

  function drawSurface(ctx, surface, z, fill, stroke) {
    if (!surface) return;
    const corners = projectPolygon([
      [number(surface.x0), number(surface.y0), z],
      [number(surface.x1), number(surface.y0), z],
      [number(surface.x1), number(surface.y1), z],
      [number(surface.x0), number(surface.y1), z],
    ]);
    polygon(ctx, corners, fill, stroke);
  }

  function blockSize(projected, scale) {
    return Math.max(7, Math.min(42, 190 / projected.depth * scale));
  }

  function drawBlock(ctx, point, color, label, scale = 1, glow = false) {
    const projected = projectPoint(point);
    if (projected) sceneBlocks.push({ctx, point, color, label, scale, glow, depth: projected.depth});
  }

  function paintBlock({ctx, point, color, label, scale, glow}) {
    const projected = projectPoint(point);
    if (!projected) return;
    const size = blockSize(projected, scale);
    ctx.save();
    if (glow) { ctx.shadowColor = color; ctx.shadowBlur = 20; }
    ctx.fillStyle = color;
    ctx.fillRect(projected.x - size / 2, projected.y - size / 2, size, size);
    ctx.strokeStyle = "rgba(245,250,236,.85)";
    ctx.lineWidth = 1.2;
    ctx.strokeRect(projected.x - size / 2, projected.y - size / 2, size, size);
    ctx.shadowBlur = 0;
    ctx.fillStyle = "rgba(13,20,28,.88)";
    ctx.font = `${Math.max(9, Math.round(size * 0.22))}px ui-monospace, monospace`;
    ctx.textAlign = "center";
    ctx.fillText(label, projected.x, projected.y + 3);
    ctx.restore();
  }

  function drawStairs(ctx, palette) {
    const selected = model.stairEnd;
    const steps = chamber().geometry?.stair_steps || [];
    for (let index = steps.length - 1; index >= 0; index -= 1) {
      const step = steps[index];
      const stepHeight = selected ? number(step[selected === "left" ? "z_left" : "z_right"]) : number(chamber().rules.stair_height) * 0.45;
      drawSurface(ctx, step, stepHeight, index === 1 ? palette.yellow : "#b08a43", "rgba(250,230,152,.6)");
      const bottom = 0;
      polygon(ctx, projectPolygon([[step.x0, step.y0, bottom], [step.x0, step.y1, bottom], [step.x0, step.y1, stepHeight], [step.x0, step.y0, stepHeight]]), "#715d35", "rgba(250,230,152,.4)");
    }
    const center = projectPoint([number(chamber().rules.stair_start) + 0.45, model.y + number(chamber().corridor_half_width) + 0.62, number(chamber().rules.stair_height) * 0.8]);
    if (center) {
      ctx.fillStyle = palette.yellow;
      ctx.font = "800 11px ui-monospace, monospace";
      ctx.fillText(selected ? `HIGH END: ${selected.toUpperCase()}` : "CLICK ONE END · 3 / 2 / 1", center.x, center.y);
    }
  }

  function drawScene() {
    if (!model) return;
    const canvas = document.querySelector("#rising-causeway-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    sceneBlocks = [];
    const palette = model.state.palette || {};
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
    gradient.addColorStop(0, palette.sky || "#171d2d");
    gradient.addColorStop(0.5, palette.haze || "#35435a");
    gradient.addColorStop(1, "#11161f");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "rgba(224,244,228,.06)";
    ctx.fillRect(0, canvas.height * 0.47, canvas.width, canvas.height * 0.53);

    const yHalf = number(chamber().rules.outer_y_half_width);
    const stone = palette.stone || "#807b8c";
    const geometry = chamber().geometry || {};
    const approach = geometry.approach_surface;
    drawSurface(ctx, approach, number(approach.z), stone, palette.edge || "#3e4052");
    for (const extension of geometry.red_extensions || []) {
      const open = model.redStage >= number(extension.required_stage);
      if (open) {
        drawFloor(ctx, number(extension.x0), number(extension.x1), number(chamber().corridor_half_width), number(extension.z), "#747b83", palette.glow || "#d6f6e7");
      } else {
        drawBlock(ctx, [number(extension.x0) + 0.18, 0, 1.1], palette.red || "#ef5d63", `R${extension.required_stage}`, 1.0, false);
      }
    }
    drawStairs(ctx, palette);
    const launchSurface = geometry.launch_surface;
    drawFloor(ctx, number(launchSurface.x0), number(launchSurface.x1), number(chamber().corridor_half_width), number(launchSurface.z), "#68717a", palette.edge || "#3e4052");
    const launchRun = (geometry.landing_platforms || []).find((item) => item.launcher_id === model.primed);
    if (launchRun) {
      drawSurface(ctx, launchRun, number(launchRun.z), "#727b83", palette.edge || "#3e4052");
    }

    // The chamber's side planes make the height relationship visible rather than
    // presenting the actuators as a flat icon board.
    for (const side of [-1, 1]) {
      const a = projectPoint([0, side * yHalf, 0]);
      const b = projectPoint([number(chamber().length), side * yHalf, 0]);
      const c = projectPoint([number(chamber().length), side * yHalf, 3.7]);
      const d = projectPoint([0, side * yHalf, 3.7]);
      polygon(ctx, [a, b, c, d], side < 0 ? "rgba(46,53,67,.33)" : "rgba(34,42,51,.48)", "rgba(189,214,202,.15)");
    }

    const redPoint = pointById("red-main")?.position;
    if (redPoint) {
      drawBlock(ctx, redPoint, palette.red || "#ef5d63", `R${model.redStage}`, 1.25, model.redStage === number(chamber().rules.red_stage_target));
      const redProjected = projectPoint([redPoint[0], redPoint[1], redPoint[2] + 0.62]);
      if (redProjected) {
        ctx.fillStyle = "#f5e6c3";
        ctx.font = "800 10px ui-monospace, monospace";
        ctx.fillText(`EXTENSION ${model.redStage}/${number(chamber().rules.red_stage_target, 3)}`, redProjected.x - 36, redProjected.y);
      }
    }
    const yellowPoint = pointById("yellow-triple")?.position;
    if (yellowPoint) {
      const spread = 0.76;
      drawBlock(ctx, [yellowPoint[0], yellowPoint[1] - spread, yellowPoint[2]], palette.yellow || "#f2ca55", "1", 0.9);
      drawBlock(ctx, [yellowPoint[0], yellowPoint[1], yellowPoint[2] + 0.08], palette.yellow || "#f2ca55", "2", 0.9);
      drawBlock(ctx, [yellowPoint[0], yellowPoint[1] + spread, yellowPoint[2] + 0.16], palette.yellow || "#f2ca55", "3", 0.9);
    }
    for (const actuator of chamber().actuators || []) {
      if (actuator.id === "red-main" || actuator.id === "yellow-triple") continue;
      drawBlock(ctx, actuator.position, "#7e8794", "?", 0.85);
    }
    for (const launcher of chamber().launchers || []) {
      const selected = launcher.id === model.primed;
      drawBlock(ctx, launcher.position, palette.blue || "#5dd6e7", selected ? "ON" : launcher.id.replace("launcher-", "L"), 1.08, selected);
      const projected = projectPoint(launcher.position);
      if (projected) {
        ctx.save();
        ctx.strokeStyle = launcher.kind === "floor" ? "#e7f7ff" : "#b8ffff";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(projected.x, projected.y);
        ctx.lineTo(projected.x + (launcher.kind === "floor" ? 0 : (launcher.facing === "left" ? -21 : 21)), projected.y - (launcher.kind === "floor" ? 27 : 2));
        ctx.stroke();
        ctx.restore();
      }
    }
    const terminal = chamber().terminal;
    drawBlock(ctx, terminal.visual_position || terminal.position, palette.glow || "#d6f6e7", model.completed ? "OPEN" : "TERMINAL", 1.32, true);
    if (model.inFlight && model.flightOrigin && model.flightVelocity) {
      ctx.save();
      ctx.strokeStyle = palette.glow || "#d6f6e7";
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      const gravity = number(chamber().rules.gravity, 9.8);
      const total = number(chamber().rules.flight_duration_ms, 840) / 1000;
      for (let fraction = 0; fraction <= 1.0001; fraction += 0.1) {
        const t = total * fraction;
        const point = projectPoint([
          model.flightOrigin[0] + model.flightVelocity[0] * t,
          model.flightOrigin[1] + model.flightVelocity[1] * t,
          model.flightOrigin[2] + model.flightVelocity[2] * t - 0.5 * gravity * t * t,
        ]);
        if (!point) continue;
        if (fraction === 0) ctx.moveTo(point.x, point.y); else ctx.lineTo(point.x, point.y);
      }
      ctx.stroke();
      ctx.restore();
      drawBlock(ctx, [model.x, model.y, model.z], palette.glow || "#d6f6e7", "ARC", 1.1, true);
    }

    sceneBlocks.sort((a, b) => b.depth - a.depth).forEach(paintBlock);
    ctx.save();
    ctx.strokeStyle = "rgba(238,255,242,.8)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(canvas.width / 2 - 12, canvas.height / 2); ctx.lineTo(canvas.width / 2 + 12, canvas.height / 2);
    ctx.moveTo(canvas.width / 2, canvas.height / 2 - 12); ctx.lineTo(canvas.width / 2, canvas.height / 2 + 12);
    ctx.stroke();
    ctx.fillStyle = "rgba(234,247,230,.78)";
    ctx.font = "800 11px ui-monospace, monospace";
    ctx.fillText(model.inFlight ? "CONTACT LAUNCH · READING ARC" : "3D VIEW · ACTUATE THEN TRAVERSE", 18, canvas.height - 18);
    ctx.restore();
  }

  function failRoute(message) {
    if (!model || model.failed || model.completed || model.submitting) return;
    model.failed = true;
    model.keys = {forward: false, back: false, strafe_left: false, strafe_right: false};
    updateHud(`FAIL · ${message}`, "error");
    submitResult(false);
  }

  function startLaunch() {
    if (!model || model.inFlight || model.completed || model.failed || !model.primed) return;
    const launcher = launcherById(model.primed);
    if (!launcher) return;
    const contact = launcher.contact;
    const contactDistance = Math.hypot(model.x - number(contact[0]), model.y - number(contact[1]), model.z - number(contact[2]));
    if (contactDistance > number(chamber().rules.contact_radius, 0.56)) {
      if (model.x >= number(chamber().rules.launcher_end) - 0.05) failRoute("THE PRIMED SURFACE WAS NOT TOUCHED");
      return;
    }
    model.x = number(contact[0]);
    model.y = number(contact[1]);
    model.z = number(contact[2]);
    model.inFlight = true;
    model.flightOrigin = [model.x, model.y, model.z];
    model.flightVelocity = clone(launcher.launch_velocity);
    model.flightElapsedMs = 0;
    pushEvent({kind: "launch_start", launcher_id: launcher.id, contact: clone(contact), velocity: clone(model.flightVelocity), input_source: "contact_physics"});
  }

  function tick() {
    if (!model || model.failed || model.completed || model.submitting) return;
    if (!model.inFlight) {
      let dx = 0; let dy = 0;
      if (model.keys.forward) { dx += Math.cos(model.heading); dy += Math.sin(model.heading); }
      if (model.keys.back) { dx -= Math.cos(model.heading); dy -= Math.sin(model.heading); }
      if (model.keys.strafe_right) { dx += Math.cos(model.heading + Math.PI / 2); dy += Math.sin(model.heading + Math.PI / 2); }
      if (model.keys.strafe_left) { dx -= Math.cos(model.heading + Math.PI / 2); dy -= Math.sin(model.heading + Math.PI / 2); }
      const magnitude = Math.hypot(dx, dy);
      if (magnitude > 1e-9) {
        dx /= magnitude; dy /= magnitude;
        const rules = chamber().rules;
        const distance = number(rules.move_speed) * number(rules.tick_ms) / 1000;
        const substeps = Math.max(1, Math.ceil(distance / 0.07));
        const step = distance / substeps;
        for (let index = 0; index < substeps; index += 1) {
          const nx = model.x + dx * step;
          const ny = model.y + dy * step;
          if (Math.abs(ny) > number(rules.outer_y_half_width)) { failRoute("THE OUTER LEDGE IS TOO LOW"); return; }
          if (model.x < number(rules.stair_end) && nx >= number(rules.stair_end) && model.stairEnd !== model.requiredStairEnd) { failRoute("THE TRIPLE STAIR RISES THE WRONG WAY"); return; }
          const nextSupport = supportZAt(nx, ny);
          if (nextSupport === null) { failRoute("THE AVATAR CROSSED A GAP IN THE SUPPORT GEOMETRY"); return; }
          model.x = nx; model.y = ny; model.z = nextSupport;
        }
      }
    } else {
      const dt = number(chamber().rules.tick_ms, 40);
      model.flightElapsedMs += dt;
      const elapsed = model.flightElapsedMs / 1000;
      const gravity = number(chamber().rules.gravity, 9.8);
      model.x = model.flightOrigin[0] + model.flightVelocity[0] * elapsed;
      model.y = model.flightOrigin[1] + model.flightVelocity[1] * elapsed;
      model.z = model.flightOrigin[2] + model.flightVelocity[2] * elapsed - 0.5 * gravity * elapsed * elapsed;
      }
    pushEvent({kind: "tick", dt_ms: number(chamber().rules.tick_ms), input_source: "physics"});
    if (model.inFlight && model.flightElapsedMs >= number(chamber().rules.flight_duration_ms, 840)) {
      const launcher = launcherById(model.primed);
      const target = launcher.landing;
      model.x = number(target[0]); model.y = number(target[1]); model.z = number(target[2]);
      model.landingZ = model.z;
      model.landed = true;
      model.inFlight = false;
      pushEvent({kind: "launch_land", launcher_id: launcher.id, x: model.x, y: model.y, z: model.z, flight_time_ms: model.flightElapsedMs, input_source: "contact_physics"});
      updateHud("LANDING CONFIRMED · WALK TO THE TERMINAL", "idle");
    } else if (!model.inFlight && !model.landed && model.primed) {
      startLaunch();
    }
    updateHud();
    drawScene();
  }

  function setKey(control, down, source) {
    // A launch blocks new movement, but a release must still clear a held
    // control so it cannot resume walking after the landing animation.
    if (!model || model.failed || model.completed || (model.inFlight && down)) return;
    if (model.interaction === "full" && source !== "keyboard") return;
    if (model.interaction === "simplified" && source !== "control_button") return;
    if (Boolean(model.keys[control]) === Boolean(down)) return;
    model.keys[control] = Boolean(down);
    pushEvent({kind: down ? "key_down" : "key_up", control, input_source: source});
    updateHud();
  }

  function applyLook(dx, dy, source) {
    if (!model || model.failed || model.completed || model.inFlight) return;
    if (model.interaction === "full" && source !== "viewport_drag") return;
    if (model.interaction === "simplified" && source !== "look_button") return;
    const sensitivity = number(chamber().rules.look_sensitivity, 0.008);
    model.heading += number(dx) * sensitivity;
    model.pitch = Math.max(-0.34, Math.min(0.34, model.pitch + number(dy) * sensitivity * 0.55));
    // Sparse drags can span the viewport in one native event. Preserve the
    // movement while recording bounded deltas accepted by replay.
    const parts = Math.max(1, Math.ceil(Math.max(Math.abs(dx), Math.abs(dy)) / 500));
    for (let i = 0; i < parts; i += 1) pushEvent({kind: "look", dx: number(dx) / parts, dy: number(dy) / parts, input_source: source});
    drawScene();
  }

  function activateRed(source) {
    if (!model || model.failed || model.completed || model.inFlight) return;
    const before = model.redStage;
    const maximum = number(chamber().rules.red_stage_target, 3);
    if (before >= maximum) return;
    const after = before + 1;
    model.redStage = after;
    pushEvent({kind: "red_actuator", target_id: "red-main", before_stage: before, after_stage: after, input_source: source});
    updateHud(`RED TILE · STAGE ${after}/${maximum}`, "idle");
    drawScene();
  }

  function activateStair(highEnd, source) {
    if (!model || model.failed || model.completed || model.inFlight || !["left", "right"].includes(highEnd)) return;
    model.stairEnd = highEnd;
    pushEvent({kind: "stair_actuator", target_id: "yellow-triple", high_end: highEnd, input_source: source});
    updateHud(`TRIPLE STAIR · ${highEnd.toUpperCase()} END HIGH`, "idle");
    drawScene();
  }

  function primeLauncher(identifier, source) {
    if (!model || model.failed || model.completed || model.inFlight) return;
    const launcher = launcherById(identifier);
    if (!launcher) return;
    model.primed = identifier;
    model.selectedLauncher = identifier;
    pushEvent({kind: "launcher_prime", launcher_id: identifier, input_source: source});
    updateHud(`${identifier.toUpperCase()} PRIMED · CONTACT TO LAUNCH`, "idle");
    drawScene();
  }

  function activateTerminal(source) {
    if (!model || model.failed || model.completed || model.inFlight) return;
    const target = chamber().terminal.position;
    const distance = Math.hypot(model.x - number(target[0]), model.y - number(target[1]), model.z - number(target[2]));
    if (!model.landed || distance > number(chamber().terminal.radius)) {
      updateHud("TERMINAL OUT OF REACH · COMPLETE THE CONTACT LAUNCH", "error");
      return;
    }
    releaseKeys();
    model.completed = true;
    pushEvent({kind: "terminal_activate", input_source: source});
    submitResult(true);
  }

  function hitTest(canvasX, canvasY) {
    const candidates = [];
    const add = (kind, id, point, scale = 1) => {
      const projected = projectPoint(point);
      if (!projected) return;
      const halfSize = blockSize(projected, scale) / 2 + 1;
      if (Math.abs(projected.x - canvasX) <= halfSize && Math.abs(projected.y - canvasY) <= halfSize) candidates.push({kind, id, depth: projected.depth});
    };
    const red = pointById("red-main");
    const yellow = pointById("yellow-triple");
    if (red) add("red", red.id, red.position, 1.25);
    if (yellow) {
      add("yellow-left", yellow.id, [yellow.position[0], yellow.position[1] - 0.76, yellow.position[2]], 0.9);
      add("decoration", yellow.id, [yellow.position[0], yellow.position[1], yellow.position[2] + 0.08], 0.9);
      add("yellow-right", yellow.id, [yellow.position[0], yellow.position[1] + 0.76, yellow.position[2] + 0.16], 0.9);
    }
    for (const actuator of chamber().actuators || []) if (!["red-main", "yellow-triple"].includes(actuator.id)) add("decoration", actuator.id, actuator.position, 0.85);
    for (const launcher of chamber().launchers || []) add("launcher", launcher.id, launcher.position, 1.08);
    add("terminal", "terminal", chamber().terminal.visual_position || chamber().terminal.position, 1.32);
    // Match the renderer's far-to-near paint order for overlapping blocks.
    candidates.sort((a, b) => b.depth - a.depth);
    return candidates[candidates.length - 1] || null;
  }

  function handleViewClick(canvasX, canvasY) {
    const hit = hitTest(canvasX, canvasY);
    if (!hit) return;
    if (hit.kind === "red") activateRed("viewport_click");
    else if (hit.kind === "yellow-left") activateStair("left", "viewport_click");
    else if (hit.kind === "yellow-right") activateStair("right", "viewport_click");
    else if (hit.kind === "launcher") primeLauncher(hit.id, "viewport_click");
    else if (hit.kind === "terminal") activateTerminal("viewport_click");
  }

  async function submitResult(completed) {
    if (!model || model.submitting) return;
    model.submitting = true;
    const submitted = model;
    const payload = submitted.pendingSubmission || {
      mechanic_id: submitted.state.mechanic_id,
      task_id: submitted.state.task_id,
      challenge_id: submitted.state.challenge_id,
      interaction: submitted.interaction,
      completed: Boolean(completed),
      events: clone(submitted.events),
      final_position: {x: submitted.x, y: submitted.y, z: submitted.z},
    };
    submitted.pendingSubmission = payload;
    const retry = document.querySelector("#rising-retry");
    if (retry) retry.hidden = true;
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      if (!response.ok) throw new Error(`submission HTTP ${response.status}`);
      const outcome = await response.json();
      if (typeof outcome.passed !== "boolean") throw new Error("invalid grade response");
      submitted.pendingSubmission = null;
      if (outcome.passed === true) {
        submitted.helpers.setReadout("PASS · TERMINAL ACTIVATED", "passed");
        document.querySelector(".rising-causeway")?.classList.add("is-passed");
        const verdict = document.querySelector(".rising-verdict");
        if (verdict) verdict.innerHTML = "<b>PASS</b><span>THE CAUSEWAY RISES</span>";
      } else if (outcome.passed === false) {
        if (outcome.state) await submitted.helpers.render(outcome.state);
        else submitted.helpers.setReadout("FAIL · ROUTE REJECTED", "error");
      }
    } catch (_error) {
      submitted.submitting = false;
      if (retry) retry.hidden = false;
      submitted.helpers.setReadout("LINK LOST · RETRY SUBMISSION", "error");
    }
  }

  function releaseKeys() {
    if (!model) return;
    const source = model.interaction === "full" ? "keyboard" : "control_button";
    for (const control of Object.keys(model.keys)) setKey(control, false, source);
  }

  function bindSimplified() {
    const cleanup = [];
    document.querySelectorAll("[data-rising-action]").forEach((button) => {
      const action = button.dataset.risingAction;
      const handler = () => {
        if (action === "red") activateRed("proxy_button");
        else if (action === "stair-left") activateStair("left", "proxy_button");
        else if (action === "stair-right") activateStair("right", "proxy_button");
        else if (action === "terminal") activateTerminal("proxy_button");
        else if (action.startsWith("launcher:")) primeLauncher(action.split(":")[1], "proxy_button");
        else if (action.startsWith("look:")) { const delta = LOOK_BUTTONS[action.split(":")[1]] || [0, 0]; applyLook(delta[0], delta[1], "look_button"); }
      };
      button.addEventListener("click", handler); cleanup.push(() => button.removeEventListener("click", handler));
    });
    document.querySelectorAll("[data-rising-hold]").forEach((button) => {
      const control = button.dataset.risingHold;
      const down = (event) => { if (event.button !== 0) return; event.preventDefault(); button.setPointerCapture(event.pointerId); setKey(control, true, "control_button"); };
      const up = (event) => { event.preventDefault(); setKey(control, false, "control_button"); };
      button.addEventListener("pointerdown", down); button.addEventListener("pointerup", up); button.addEventListener("pointercancel", up); button.addEventListener("lostpointercapture", up);
      cleanup.push(() => { button.removeEventListener("pointerdown", down); button.removeEventListener("pointerup", up); button.removeEventListener("pointercancel", up); button.removeEventListener("lostpointercapture", up); });
    });
    return cleanup;
  }

  async function render(state, helpers) {
    if (activeCleanup) activeCleanup();
    document.body.dataset.mechanic = "rising-causeway";
    const interaction = state.control_condition?.interaction || "full";
    const start = state.world.chamber.start;
    model = {
      state, helpers, interaction,
      startedAt: performance.now(),
      x: number(start.position[0]), y: number(start.position[1]), z: number(start.position[2]),
      heading: number(start.heading), pitch: number(start.pitch, -0.035),
      redStage: 0, stairEnd: null, selectedLauncher: null, primed: null,
      requiredStairEnd: null, landed: false, landingZ: null, inFlight: false,
      flightStart: 0, flightOrigin: null, flightTarget: null, flightVelocity: null, flightElapsedMs: 0,
      keys: {forward: false, back: false, strafe_left: false, strafe_right: false},
      events: [], failed: false, completed: false, submitting: false, timer: null,
    };
    // The action target is not exposed as a task answer. The browser only needs
    // its geometric consequences to perform local collision and rendering.
    model.requiredStairEnd = state.world.chamber.mirror < 0 ? "left" : "right";
    model.projectPoint = projectPoint;
    window.risingCausewayModel = model;
    const simplified = interaction === "simplified";
    const launcherButtons = (state.world.launcher_gallery || []).map((launcher) => `<button type="button" data-rising-action="launcher:${helpers.text(launcher.id)}" aria-label="Prime ${helpers.text(launcher.id)}">${helpers.text(launcher.id).toUpperCase()} · ${helpers.text(launcher.kind)}</button>`).join("");
    helpers.app.innerHTML = `
      <section class="rising-causeway" data-interaction="${helpers.text(interaction)}" data-failed="false" data-completed="false" data-flight="false" tabindex="0">
        <div class="rising-verdict" aria-live="assertive"></div>
        <header class="rising-head"><div><span>CHAMBER 07 / ARCHITECTURAL ACTUATION</span><h1>${helpers.text(state.prompt)}</h1></div><div class="rising-badge">3D<br><b>CAUSEWAY</b></div></header>
        <section class="rising-workbench">
          <div class="rising-view-wrap"><canvas id="rising-causeway-canvas" width="900" height="520" aria-label="First-person three-dimensional causeway chamber"></canvas><div class="rising-caption"><span>FIRST-PERSON CHAMBER VIEW</span><b>HEIGHT · NORMAL · CONTACT</b></div></div>
          <aside class="rising-console">
            <div class="rising-readouts"><span>RED TILE</span><b id="rising-red-stage">0/${number(state.world.chamber.rules.red_stage_target, 3)}</b><span>TRIPLE</span><b id="rising-stair-state">UNSET</b><span>LAUNCH</span><b id="rising-launch-state">UNPRIMED</b><span>POSITION</span><b id="rising-position">X 1.2 · Y 0.0 · Z 0.0</b></div>
            <div class="rising-rule-card"><b>READ THE SOLID</b><span>Extrusion changes support. The clicked stair end makes the high side. A primed block only acts on contact.</span></div>
            ${simplified ? `<div class="rising-proxy"><span>ARCHITECTURE</span><div class="rising-buttons"><button type="button" data-rising-action="red">EXTEND RED</button><button type="button" data-rising-action="stair-left">STAIR LEFT HIGH</button><button type="button" data-rising-action="stair-right">STAIR RIGHT HIGH</button></div><span>LAUNCHER GALLERY</span><div class="rising-buttons">${launcherButtons}</div><span>MOVE / LOOK</span><div class="rising-dpad"><button type="button" data-rising-hold="forward">▲</button><button type="button" data-rising-hold="strafe_left">◀</button><button type="button" data-rising-hold="back">▼</button><button type="button" data-rising-hold="strafe_right">▶</button></div><div class="rising-buttons"><button type="button" data-rising-action="look:left">LOOK ◀</button><button type="button" data-rising-action="look:right">LOOK ▶</button><button type="button" data-rising-action="look:up">LOOK ▲</button><button type="button" data-rising-action="look:down">LOOK ▼</button></div><button type="button" class="rising-terminal-button" data-rising-action="terminal">ACTIVATE TERMINAL</button></div>` : `<div class="rising-full-hint"><b>WASD / ARROWS</b><span>Hold to walk and strafe across the changed support.</span><b>DRAG THE VIEW</b><span>Mouse-look and click the coloured blocks, then click the reached terminal.</span></div>`}
            <button type="button" class="rising-terminal-button" id="rising-retry" hidden>RETRY SUBMISSION</button>
            <button type="button" class="rising-abandon" id="rising-abandon">ABANDON CHAMBER</button>
          </aside>
        </section>
        <footer class="rising-foot"><div class="readout" data-status="idle">INSPECT THE CHAMBER · CONFIGURE THE ROUTE · FIND THE FAR TERMINAL</div><span>THE BLOCKS ARE FIXED; THEIR SUPPORT EFFECTS ARE NOT</span></footer>
        ${helpers.cheatPanelTemplate()}
      </section>`;
    const canvas = document.querySelector("#rising-causeway-canvas");
    const keydown = (event) => {
      if (event.repeat || model.interaction !== "full") return;
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
    window.addEventListener("blur", releaseKeys);
    let dragging = false; let dragMoved = false; let lastPointer = null; let pointerStart = null;
    const pointerdown = (event) => {
      if (model.interaction !== "full" || event.button !== 0 || model.failed || model.completed) return;
      dragging = true; dragMoved = false; lastPointer = [event.clientX, event.clientY]; pointerStart = [event.offsetX, event.offsetY]; canvas.setPointerCapture?.(event.pointerId);
    };
    const pointermove = (event) => {
      if (!dragging || !lastPointer) return;
      const dx = event.clientX - lastPointer[0]; const dy = event.clientY - lastPointer[1];
      if (Math.abs(dx) + Math.abs(dy) > 1) dragMoved = true;
      lastPointer = [event.clientX, event.clientY];
      if (dx || dy) applyLook(dx, dy, "viewport_drag");
    };
    const pointerup = (event) => {
      if (dragging && !dragMoved && pointerStart) {
        const scaleX = canvas.width / Math.max(1, canvas.clientWidth);
        const scaleY = canvas.height / Math.max(1, canvas.clientHeight);
        handleViewClick(pointerStart[0] * scaleX, pointerStart[1] * scaleY);
      }
      dragging = false; dragMoved = false; lastPointer = null; pointerStart = null;
      try { canvas.releasePointerCapture?.(event.pointerId); } catch (_error) { /* already released */ }
    };
    const pointercancel = () => { dragging = false; dragMoved = false; lastPointer = null; pointerStart = null; };
    canvas.addEventListener("pointerdown", pointerdown); canvas.addEventListener("pointermove", pointermove); canvas.addEventListener("pointerup", pointerup); canvas.addEventListener("pointercancel", pointercancel); canvas.addEventListener("lostpointercapture", pointercancel);
    const simpleCleanup = simplified ? bindSimplified() : [];
    const abandon = () => { if (!model.completed && !model.submitting) { pushEvent({kind: "abandon", input_source: "route_button"}); model.failed = true; submitResult(false); } };
    document.querySelector("#rising-abandon")?.addEventListener("click", abandon);
    document.querySelector("#rising-retry")?.addEventListener("click", () => { if (model.pendingSubmission) submitResult(model.pendingSubmission.completed); });
    model.timer = window.setInterval(tick, number(state.world.chamber.rules.tick_ms, 40));
    activeCleanup = () => {
      window.removeEventListener("keydown", keydown); window.removeEventListener("keyup", keyup);
      window.removeEventListener("blur", releaseKeys);
      canvas.removeEventListener("pointerdown", pointerdown); canvas.removeEventListener("pointermove", pointermove); canvas.removeEventListener("pointerup", pointerup); canvas.removeEventListener("pointercancel", pointercancel); canvas.removeEventListener("lostpointercapture", pointercancel);
      simpleCleanup.forEach((cleanup) => cleanup());
      if (model?.timer) window.clearInterval(model.timer);
    };
    updateHud(); drawScene(); canvas.focus(); helpers.installCheatPanel();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.rising_causeway = {rootSelector: ".rising-causeway", render};
})();
