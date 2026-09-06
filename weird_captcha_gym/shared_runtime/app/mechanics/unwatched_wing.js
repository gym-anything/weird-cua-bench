(() => {
  "use strict";

  const VIEW_WIDTH = 860;
  const VIEW_HEIGHT = 470;
  const model = {
    state: null,
    helpers: null,
    interaction: "full",
    pose: null,
    targetCursor: 0,
    targetArmed: true,
    dockOccupied: false,
    lampOn: true,
    viewerOpen: false,
    probePlinthId: null,
    lights: {},
    pinReady: new Set(),
    jumpCount: 0,
    rejectedHandoffs: 0,
    entangled: false,
    events: [],
    counts: {moves: 0, looks: 0, equipment: 0, breakers: 0},
    drag: null,
    keyHandler: null,
    submitting: false,
    terminal: false,
    forceReveal: false,
    canvas: null,
    context: null,
    darknessSample: {mean_luminance: 1, max_luminance: 1},
  };

  const clean = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const q = (value) => Math.round(Number(value) * 1e6) / 1e6;
  const normalizeMdeg = (value) => ((Math.round(value) % 360000) + 360000) % 360000;
  const angleRadians = (value = model.pose.angle_mdeg) => Number(value) / 1000 * Math.PI / 180;
  const signedRadians = (value) => ((value + Math.PI) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2) - Math.PI;
  const poseObject = () => ({x: q(model.pose.x), y: q(model.pose.y), angle_mdeg: normalizeMdeg(model.pose.angle_mdeg)});
  const distance = (first, second) => Math.hypot(first[0] - second[0], first[1] - second[1]);
  const record = (kind, details = {}) => {
    const event = {sequence: model.events.length + 1, kind, ...details};
    model.events.push(event);
    return event;
  };

  function cleanup() {
    if (model.keyHandler) window.removeEventListener("keydown", model.keyHandler);
    model.keyHandler = null;
  }

  function beginAction() {
    document.querySelector(".uw-verdict.is-fail")?.remove();
  }

  function circleClear(x, y) {
    const rows = model.state.map;
    const radius = Number(model.state.controls.player_radius);
    for (let cellY = Math.floor(y - radius); cellY <= Math.floor(y + radius); cellY += 1) {
      for (let cellX = Math.floor(x - radius); cellX <= Math.floor(x + radius); cellX += 1) {
        if (cellY < 0 || cellY >= rows.length || cellX < 0 || cellX >= rows[0].length) return false;
        if (rows[cellY][cellX] !== "#") continue;
        const nearestX = Math.max(cellX, Math.min(x, cellX + 1));
        const nearestY = Math.max(cellY, Math.min(y, cellY + 1));
        if ((x - nearestX) ** 2 + (y - nearestY) ** 2 < radius ** 2 - 1e-10) return false;
      }
    }
    return true;
  }

  function castWall(x, y, angleMdeg) {
    const rows = model.state.map;
    const angle = angleRadians(angleMdeg);
    const directionX = Math.cos(angle);
    const directionY = Math.sin(angle);
    let mapX = Math.floor(x);
    let mapY = Math.floor(y);
    const deltaX = Math.abs(directionX) > 1e-12 ? Math.abs(1 / directionX) : 1e30;
    const deltaY = Math.abs(directionY) > 1e-12 ? Math.abs(1 / directionY) : 1e30;
    const stepX = directionX < 0 ? -1 : 1;
    const stepY = directionY < 0 ? -1 : 1;
    let sideX = directionX < 0 ? (x - mapX) * deltaX : (mapX + 1 - x) * deltaX;
    let sideY = directionY < 0 ? (y - mapY) * deltaY : (mapY + 1 - y) * deltaY;
    let side = 0;
    let range = 0;
    for (let count = 0; count < 256; count += 1) {
      if (sideX < sideY) {
        range = sideX; sideX += deltaX; mapX += stepX; side = 0;
      } else {
        range = sideY; sideY += deltaY; mapY += stepY; side = 1;
      }
      if (mapY < 0 || mapY >= rows.length || mapX < 0 || mapX >= rows[0].length || rows[mapY][mapX] === "#") {
        return {distance: range, side, mapX, mapY};
      }
    }
    return {distance: 1e9, side, mapX, mapY};
  }

  function lineOfSight(first, second) {
    const range = distance(first, second);
    if (range <= 1e-9) return true;
    const angle = Math.round(Math.atan2(second[1] - first[1], second[0] - first[0]) * 180 / Math.PI * 1000);
    return castWall(first[0], first[1], angle).distance >= range - 0.08;
  }

  function plinthById(id) {
    return model.state.plinths.find((item) => String(item.id) === String(id));
  }

  function pointFor(id) {
    const item = String(id) === String(model.state.dock.id) ? model.state.dock : plinthById(id);
    return [Number(item.center[0]), Number(item.center[1])];
  }

  function currentTargetPlinthId() {
    return model.dockOccupied ? model.state.dock.id : model.state.target_path[model.targetCursor];
  }

  function relativeAngle(point) {
    const bearing = Math.atan2(point[1] - model.pose.y, point[0] - model.pose.x);
    return signedRadians(bearing - angleRadians());
  }

  function geometricVisible(point, halfAngleScale = 1) {
    const origin = [model.pose.x, model.pose.y];
    const half = Number(model.state.controls.field_of_view_deg) / 2 * Math.PI / 180 * halfAngleScale;
    return distance(origin, point) <= Number(model.state.controls.visible_range)
      && Math.abs(relativeAngle(point)) <= half
      && lineOfSight(origin, point);
  }

  function visibleLights() {
    return model.state.wall_lights.filter((item) => model.lights[item.id] && geometricVisible(item.center.map(Number)));
  }

  function targetObservation() {
    if (model.dockOccupied) return {main: true, hand: false, ambient: false, probe: false};
    const plinthId = currentTargetPlinthId();
    const target = pointFor(plinthId);
    const origin = [model.pose.x, model.pose.y];
    const hand = Boolean(model.lampOn && distance(origin, target) <= Number(model.state.controls.hand_lamp_range) && lineOfSight(origin, target));
    const ambient = model.state.wall_lights.some((item) => model.lights[item.id] && item.plinth_id === plinthId);
    const sceneLit = Boolean(model.lampOn || visibleLights().length || model.viewerOpen);
    const main = Boolean(sceneLit && geometricVisible(target) && (hand || ambient || model.lampOn));
    const probe = Boolean(model.viewerOpen && model.probePlinthId === plinthId);
    return {main, hand, ambient, probe};
  }

  function renderDark() {
    return !model.forceReveal && !model.lampOn && !model.viewerOpen && visibleLights().length === 0;
  }

  function settleObservation() {
    if (model.dockOccupied) return;
    const cursor = model.targetCursor;
    const observation = targetObservation();
    const observed = Object.values(observation).some(Boolean);
    const current = pointFor(model.state.target_path[cursor]);
    const finalReady = cursor === model.state.target_path.length - 1
      && distance([model.pose.x, model.pose.y], current) <= Number(model.state.controls.entangle_radius)
      && renderDark()
      && !observation.ambient
      && model.probePlinthId == null
      && !model.viewerOpen
      && !model.lampOn;
    if (finalReady) {
      const dock = pointFor(model.state.dock.id);
      model.targetCursor = model.state.target_path.length;
      model.dockOccupied = true;
      model.entangled = true;
      model.targetArmed = false;
      model.jumpCount += 1;
      model.pose.x = q(dock[0]);
      model.pose.y = q(dock[1]);
      return;
    }
    if (observed) {
      model.targetArmed = true;
      const onlyProbe = observation.probe && !observation.main && !observation.hand && !observation.ambient;
      if (onlyProbe && model.state.required_pin_steps.includes(cursor)) {
        const release = pointFor(model.state.target_path[cursor + 1]);
        if (distance([model.pose.x, model.pose.y], release) <= Number(model.state.controls.release_radius)) model.pinReady.add(cursor);
      }
      return;
    }
    if (!model.targetArmed) return;
    if (cursor === model.state.target_path.length - 1) {
      model.targetCursor = Math.max(0, cursor - 1);
      model.rejectedHandoffs += 1;
    } else if (model.state.required_pin_steps.includes(cursor) && !model.pinReady.has(cursor)) {
      model.targetCursor = Math.max(0, cursor - 1);
      model.rejectedHandoffs += 1;
    } else {
      model.targetCursor = cursor + 1;
    }
    model.targetArmed = false;
    model.jumpCount += 1;
  }

  function measureDarkness() {
    if (!model.canvas || !model.context) return {mean_luminance: 1, max_luminance: 1};
    const data = model.context.getImageData(0, 0, model.canvas.width, model.canvas.height).data;
    let sum = 0;
    let maximum = 0;
    const pixels = data.length / 4;
    for (let index = 0; index < data.length; index += 4) {
      const luminance = (0.2126 * data[index] + 0.7152 * data[index + 1] + 0.0722 * data[index + 2]) / 255;
      sum += luminance;
      maximum = Math.max(maximum, luminance);
    }
    return {mean_luminance: q(sum / pixels), max_luminance: q(maximum)};
  }

  function afterAction() {
    settleObservation();
    drawWorld();
    updatePanels();
    if (model.entangled && !model.submitting) {
      model.darknessSample = measureDarkness();
      void submit(true);
    }
  }

  function move(forward, strafe, inputSource) {
    if (model.terminal || model.submitting) return;
    beginAction();
    const from = poseObject();
    const angle = angleRadians();
    const step = Number(model.state.controls.move_step);
    const intendedX = q(model.pose.x + (Math.cos(angle) * forward + Math.cos(angle + Math.PI / 2) * strafe) * step);
    const intendedY = q(model.pose.y + (Math.sin(angle) * forward + Math.sin(angle + Math.PI / 2) * strafe) * step);
    const blockedX = !circleClear(intendedX, model.pose.y);
    if (!blockedX) model.pose.x = intendedX;
    const blockedY = !circleClear(model.pose.x, intendedY);
    if (!blockedY) model.pose.y = intendedY;
    model.pose.x = q(model.pose.x);
    model.pose.y = q(model.pose.y);
    model.counts.moves += 1;
    record("move", {forward, strafe, from, to: poseObject(), blocked_x: blockedX, blocked_y: blockedY, input_source: inputSource});
    afterAction();
  }

  function look(deltaMdeg, inputSource) {
    if (model.terminal || model.submitting) return;
    beginAction();
    let remaining = Math.round(deltaMdeg);
    while (remaining) {
      const delta = Math.sign(remaining) * Math.min(30000, Math.abs(remaining));
      const before = normalizeMdeg(model.pose.angle_mdeg);
      model.pose.angle_mdeg = normalizeMdeg(before + delta);
      model.counts.looks += 1;
      record("look", {delta_mdeg: delta, before_mdeg: before, after_mdeg: model.pose.angle_mdeg, input_source: inputSource});
      settleObservation();
      remaining -= delta;
    }
    afterAction();
  }

  function toggleLamp(inputSource) {
    if (model.terminal || model.submitting) return;
    beginAction();
    model.lampOn = !model.lampOn;
    model.counts.equipment += 1;
    record("lamp", {enabled: model.lampOn, input_source: inputSource});
    afterAction();
  }

  function toggleViewer(inputSource) {
    if (model.terminal || model.submitting) return;
    beginAction();
    model.viewerOpen = !model.viewerOpen;
    model.counts.equipment += 1;
    record("viewer", {open: model.viewerOpen, input_source: inputSource});
    afterAction();
  }

  function aimedPlinth() {
    const origin = [model.pose.x, model.pose.y];
    const tolerance = Number(model.state.controls.probe_aim_tolerance_deg) * Math.PI / 180;
    const candidates = model.state.plinths.map((item) => {
      const point = item.center.map(Number);
      return {id: item.id, error: Math.abs(relativeAngle(point)), distance: distance(origin, point), point};
    }).filter((item) => item.distance <= Number(model.state.controls.probe_range) && item.error <= tolerance && lineOfSight(origin, item.point));
    candidates.sort((a, b) => a.error - b.error || a.distance - b.distance || String(a.id).localeCompare(String(b.id)));
    return candidates[0]?.id || null;
  }

  function deployProbe(inputSource) {
    if (model.terminal || model.submitting) return;
    beginAction();
    const plinthId = aimedPlinth();
    if (!plinthId) return;
    model.probePlinthId = plinthId;
    model.counts.equipment += 1;
    record("probe_deploy", {plinth_id: plinthId, input_source: inputSource});
    afterAction();
  }

  function recallProbe(inputSource) {
    if (model.terminal || model.submitting || model.probePlinthId == null) return;
    beginAction();
    const plinthId = model.probePlinthId;
    model.probePlinthId = null;
    model.counts.equipment += 1;
    record("probe_recall", {plinth_id: plinthId, input_source: inputSource});
    afterAction();
  }

  function nearestBreaker() {
    const origin = [model.pose.x, model.pose.y];
    const candidates = model.state.wall_lights.map((item) => ({
      id: item.id,
      distance: distance(origin, item.center.map(Number)),
      point: item.center.map(Number),
    })).filter((item) => item.distance <= Number(model.state.controls.breaker_range) && lineOfSight(origin, item.point));
    candidates.sort((a, b) => a.distance - b.distance || String(a.id).localeCompare(String(b.id)));
    return candidates[0]?.id || null;
  }

  function toggleBreaker(inputSource) {
    if (model.terminal || model.submitting) return;
    beginAction();
    const lightId = nearestBreaker();
    if (!lightId) return;
    model.lights[lightId] = !model.lights[lightId];
    model.counts.breakers += 1;
    record("breaker", {light_id: lightId, enabled: model.lights[lightId], input_source: inputSource});
    afterAction();
  }

  function drawExhibit(ctx, style, x, y, scale) {
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(scale, scale);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = style.accent;
    ctx.fillStyle = style.color;
    ctx.lineWidth = 4;
    if (["heron", "ibis"].includes(style.glyph)) {
      ctx.beginPath(); ctx.ellipse(0, -18, 18, 29, -.25, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.moveTo(5, -42); ctx.quadraticCurveTo(28, -65, 14, -87); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(14, -87); ctx.lineTo(39, -82); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(-7, 8); ctx.lineTo(-12, 38); ctx.moveTo(7, 8); ctx.lineTo(13, 38); ctx.stroke();
    } else if (style.glyph === "moth") {
      ctx.beginPath(); ctx.moveTo(0, -55); ctx.bezierCurveTo(-20, -88, -56, -73, -50, -29); ctx.bezierCurveTo(-31, -37, -18, -28, 0, -3); ctx.bezierCurveTo(18, -28, 31, -37, 50, -29); ctx.bezierCurveTo(56, -73, 20, -88, 0, -55); ctx.fill();
      ctx.beginPath(); ctx.moveTo(0, -62); ctx.lineTo(0, 8); ctx.stroke();
    } else if (style.glyph === "stag") {
      ctx.beginPath(); ctx.moveTo(-20, -45); ctx.lineTo(-13, 2); ctx.lineTo(13, 2); ctx.lineTo(20, -45); ctx.closePath(); ctx.fill();
      [-1, 1].forEach((side) => { ctx.beginPath(); ctx.moveTo(side * 12, -43); ctx.lineTo(side * 28, -76); ctx.lineTo(side * 45, -90); ctx.moveTo(side * 27, -73); ctx.lineTo(side * 45, -64); ctx.stroke(); });
    } else if (style.glyph === "comet") {
      ctx.beginPath(); ctx.arc(13, -45, 26, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.moveTo(-10, -45); ctx.quadraticCurveTo(-48, -29, -58, 9); ctx.moveTo(-4, -58); ctx.quadraticCurveTo(-44, -55, -66, -20); ctx.stroke();
    } else if (style.glyph === "orrery") {
      ctx.beginPath(); ctx.arc(0, -37, 14, 0, Math.PI * 2); ctx.fill();
      [24, 38].forEach((radius, index) => { ctx.beginPath(); ctx.ellipse(0, -37, radius, radius * .48, index ? -.35 : .3, 0, Math.PI * 2); ctx.stroke(); });
      ctx.beginPath(); ctx.arc(31, -48, 6, 0, Math.PI * 2); ctx.fill();
    } else if (style.glyph === "lantern") {
      ctx.beginPath(); ctx.moveTo(-24, -62); ctx.lineTo(24, -62); ctx.lineTo(18, 0); ctx.lineTo(-18, 0); ctx.closePath(); ctx.fill();
      ctx.beginPath(); ctx.arc(0, -64, 28, Math.PI, Math.PI * 2); ctx.stroke();
      ctx.strokeRect(-12, -48, 24, 31);
    } else {
      ctx.beginPath(); ctx.moveTo(-39, -32); ctx.lineTo(-18, -48); ctx.lineTo(-10, -78); ctx.lineTo(0, -56); ctx.lineTo(12, -82); ctx.lineTo(19, -49); ctx.lineTo(40, -31); ctx.lineTo(29, 2); ctx.lineTo(-29, 2); ctx.closePath(); ctx.fill();
    }
    ctx.shadowColor = style.accent;
    ctx.shadowBlur = 12;
    ctx.strokeStyle = style.accent;
    ctx.stroke();
    ctx.restore();
  }

  function project(point) {
    const relative = relativeAngle(point);
    const range = distance([model.pose.x, model.pose.y], point);
    const fov = Number(model.state.controls.field_of_view_deg) * Math.PI / 180;
    if (Math.abs(relative) >= fov * .55 || range <= .05) return null;
    const corrected = range * Math.cos(relative);
    return {
      x: VIEW_WIDTH / 2 + Math.tan(relative) / Math.tan(fov / 2) * VIEW_WIDTH / 2,
      corrected,
      range,
    };
  }

  function drawWorld() {
    if (!model.context || !model.canvas) return;
    const ctx = model.context;
    const palette = model.state.palette;
    if (renderDark()) {
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, VIEW_WIDTH, VIEW_HEIGHT);
      document.querySelector(".unwatched-wing")?.setAttribute("data-blackout", "true");
      return;
    }
    document.querySelector(".unwatched-wing")?.setAttribute("data-blackout", "false");
    const ceiling = ctx.createLinearGradient(0, 0, 0, VIEW_HEIGHT * .5);
    ceiling.addColorStop(0, palette.void); ceiling.addColorStop(1, palette.wall);
    ctx.fillStyle = ceiling; ctx.fillRect(0, 0, VIEW_WIDTH, VIEW_HEIGHT / 2);
    const floor = ctx.createLinearGradient(0, VIEW_HEIGHT / 2, 0, VIEW_HEIGHT);
    floor.addColorStop(0, palette.floor); floor.addColorStop(1, palette.void);
    ctx.fillStyle = floor; ctx.fillRect(0, VIEW_HEIGHT / 2, VIEW_WIDTH, VIEW_HEIGHT / 2);
    const depth = new Float32Array(VIEW_WIDTH);
    const fov = Number(model.state.controls.field_of_view_deg) * Math.PI / 180;
    for (let screenX = 0; screenX < VIEW_WIDTH; screenX += 2) {
      const relative = (screenX / VIEW_WIDTH - .5) * fov;
      const ray = castWall(model.pose.x, model.pose.y, normalizeMdeg(model.pose.angle_mdeg + relative * 180 / Math.PI * 1000));
      const corrected = Math.max(.001, ray.distance * Math.cos(relative));
      const wallHeight = Math.min(VIEW_HEIGHT * 1.8, VIEW_HEIGHT / corrected);
      const top = Math.round((VIEW_HEIGHT - wallHeight) / 2);
      const grain = Math.abs(ray.mapX * 13 + ray.mapY * 29) % 4;
      const lampFactor = model.lampOn ? Math.max(.22, Math.min(1, 2.7 / corrected)) : .22;
      const base = ray.side ? palette.wall : palette.wall_alt;
      const rgb = base.match(/[a-f\d]{2}/gi).map((part) => parseInt(part, 16));
      ctx.fillStyle = `rgb(${rgb.map((value) => Math.round((value + grain * 4) * lampFactor)).join(",")})`;
      ctx.fillRect(screenX, top, 2, wallHeight);
      ctx.fillStyle = `rgba(216,184,111,${.08 * lampFactor})`;
      if (grain === 0) ctx.fillRect(screenX, top, 1, wallHeight);
      depth[screenX] = corrected;
      if (screenX + 1 < VIEW_WIDTH) depth[screenX + 1] = corrected;
    }

    const scene = [];
    model.state.plinths.forEach((item) => scene.push({kind: "plinth", item, point: item.center.map(Number)}));
    scene.push({kind: "dock", item: model.state.dock, point: model.state.dock.center.map(Number)});
    model.state.wall_lights.forEach((item) => scene.push({kind: "light", item, point: item.center.map(Number)}));
    if (!model.dockOccupied) scene.push({kind: "target", item: model.state.target_exhibit, point: pointFor(currentTargetPlinthId())});
    model.state.decoy_exhibits.forEach((item) => scene.push({kind: "decoy", item, point: pointFor(item.plinth_id)}));
    scene.sort((a, b) => distance([model.pose.x, model.pose.y], b.point) - distance([model.pose.x, model.pose.y], a.point));
    scene.forEach((entry) => {
      const projected = project(entry.point);
      if (!projected || !lineOfSight([model.pose.x, model.pose.y], entry.point)) return;
      const centerX = Math.round(projected.x);
      if (centerX < 0 || centerX >= VIEW_WIDTH || projected.corrected > depth[centerX] + .08) return;
      const ambient = entry.kind === "target"
        ? model.state.wall_lights.some((light) => model.lights[light.id] && light.plinth_id === currentTargetPlinthId())
        : entry.kind === "decoy" && model.state.wall_lights.some((light) => model.lights[light.id] && light.plinth_id === entry.item.plinth_id);
      const objectVisible = model.lampOn || ambient || entry.kind === "light" || entry.kind === "dock" || entry.kind === "plinth";
      if (!objectVisible) return;
      const scale = Math.min(2.4, 1 / Math.max(.34, projected.corrected));
      const baseY = VIEW_HEIGHT / 2 + 72 * scale;
      if (entry.kind === "plinth") {
        const width = 70 * scale, height = 42 * scale;
        ctx.fillStyle = "rgba(29,32,30,.96)"; ctx.fillRect(centerX - width / 2, baseY - height, width, height);
        ctx.strokeStyle = palette.brass; ctx.lineWidth = Math.max(1, 2 * scale); ctx.strokeRect(centerX - width / 2, baseY - height, width, height);
        if (entry.item.probe_threshold) {
          ctx.fillStyle = palette.signal;
          ctx.font = `900 ${Math.max(9, 14 * scale)}px ui-monospace,monospace`;
          ctx.textAlign = "center";
          ctx.fillText("↠", centerX, baseY - height - 7 * scale);
        }
        if (projected.corrected < 4.5) { ctx.fillStyle = palette.brass; ctx.font = `800 ${Math.max(8, 11 * scale)}px ui-monospace,monospace`; ctx.textAlign = "center"; ctx.fillText(entry.item.label, centerX, baseY - 10 * scale); }
      } else if (entry.kind === "target" || entry.kind === "decoy") {
        drawExhibit(ctx, entry.item, centerX, baseY - 34 * scale, .55 * scale);
      } else if (entry.kind === "light") {
        ctx.fillStyle = model.lights[entry.item.id] ? "#ffe0a0" : "#423d34";
        ctx.shadowColor = model.lights[entry.item.id] ? "#ffd078" : "transparent"; ctx.shadowBlur = model.lights[entry.item.id] ? 24 : 0;
        ctx.beginPath(); ctx.arc(centerX, baseY - 72 * scale, Math.max(4, 9 * scale), 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0;
      } else if (entry.kind === "dock") {
        const width = 92 * scale, height = 132 * scale;
        ctx.fillStyle = "rgba(7,17,18,.82)"; ctx.fillRect(centerX - width / 2, baseY - height, width, height);
        ctx.strokeStyle = model.dockOccupied ? "#ecdc9b" : palette.signal; ctx.lineWidth = Math.max(2, 5 * scale); ctx.strokeRect(centerX - width / 2, baseY - height, width, height);
        ctx.fillStyle = palette.signal; ctx.font = `900 ${Math.max(9, 12 * scale)}px ui-monospace,monospace`; ctx.textAlign = "center"; ctx.fillText("DOCK 00", centerX, baseY - height * .45);
      }
    });
    ctx.shadowBlur = 0;
    ctx.strokeStyle = "rgba(240,216,154,.9)"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(VIEW_WIDTH / 2 - 15, VIEW_HEIGHT / 2); ctx.lineTo(VIEW_WIDTH / 2 - 5, VIEW_HEIGHT / 2); ctx.moveTo(VIEW_WIDTH / 2 + 5, VIEW_HEIGHT / 2); ctx.lineTo(VIEW_WIDTH / 2 + 15, VIEW_HEIGHT / 2); ctx.moveTo(VIEW_WIDTH / 2, VIEW_HEIGHT / 2 - 15); ctx.lineTo(VIEW_WIDTH / 2, VIEW_HEIGHT / 2 - 5); ctx.moveTo(VIEW_WIDTH / 2, VIEW_HEIGHT / 2 + 5); ctx.lineTo(VIEW_WIDTH / 2, VIEW_HEIGHT / 2 + 15); ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,.025)"; for (let y = 0; y < VIEW_HEIGHT; y += 4) ctx.fillRect(0, y, VIEW_WIDTH, 1);
  }

  function drawProbeFeed() {
    const canvas = document.getElementById("uw-probe-feed");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#020606"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "rgba(119,224,211,.18)"; for (let y = 4; y < canvas.height; y += 8) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke(); }
    const live = model.viewerOpen && model.probePlinthId;
    const targetHere = live && !model.dockOccupied && model.probePlinthId === currentTargetPlinthId();
    const decoy = live && model.state.decoy_exhibits.find((item) => item.plinth_id === model.probePlinthId);
    if (targetHere) drawExhibit(ctx, model.state.target_exhibit, canvas.width / 2, canvas.height - 18, .7);
    else if (decoy) drawExhibit(ctx, decoy, canvas.width / 2, canvas.height - 18, .7);
  }

  function drawDossier() {
    const canvas = document.getElementById("uw-dossier-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawExhibit(ctx, model.state.target_dossier, canvas.width / 2, canvas.height - 12, .58);
  }

  function updatePanels() {
    const set = (id, value) => { const node = document.getElementById(id); if (node) node.textContent = value; };
    set("uw-lamp-state", model.lampOn ? "ON" : "OFF");
    set("uw-viewer-state", model.viewerOpen ? "OPEN" : "CLOSED");
    set("uw-probe-state", model.probePlinthId ? "DEPLOYED" : "RECALLED");
    document.querySelector(".unwatched-wing")?.setAttribute("data-viewer", model.viewerOpen ? "open" : "closed");
    document.querySelector(".unwatched-wing")?.setAttribute("data-lamp", model.lampOn ? "on" : "off");
    drawProbeFeed();
  }

  function payload(completed) {
    return {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      control_condition: model.state.control_condition || null,
      interaction_mode: model.interaction,
      events: model.events,
      completed,
      final_pose: poseObject(),
      final_target_plinth_id: currentTargetPlinthId(),
      dock_occupied: model.dockOccupied,
      jump_count: model.jumpCount,
      rejected_handoffs: model.rejectedHandoffs,
      pin_ready_steps: [...model.pinReady].sort((a, b) => a - b),
      equipment: {lamp_on: model.lampOn, viewer_open: model.viewerOpen, probe_plinth_id: model.probePlinthId, wall_lights: {...model.lights}},
      interaction_counts: {...model.counts},
      darkness_sample: {...model.darknessSample},
    };
  }

  function showRetryVerdict() {
    const root = document.querySelector(".unwatched-wing");
    root?.insertAdjacentHTML("beforeend", '<div class="uw-verdict is-fail"><i>FAIL</i></div>');
  }

  async function submit(completed) {
    if (model.submitting) return;
    model.submitting = true;
    model.terminal = true;
    record("submit", {input_source: "dock_auto"});
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload(completed))});
      const outcome = await response.json();
      if (outcome.passed === true) {
        document.querySelector(".unwatched-wing")?.insertAdjacentHTML("beforeend", '<div class="uw-verdict is-pass"><i>PASS</i></div>');
        model.helpers.setReadout("", "passed");
        return;
      }
      if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        showRetryVerdict();
        return;
      }
      model.submitting = false; model.terminal = false; showRetryVerdict();
    } catch (_error) {
      model.submitting = false; model.terminal = false; showRetryVerdict();
    }
  }

  async function abandon() {
    if (model.submitting) return;
    beginAction();
    model.submitting = true;
    model.terminal = true;
    record("abandon", {input_source: "abandon_button"});
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload(false))});
      const outcome = await response.json();
      if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        showRetryVerdict();
      }
    } catch (_error) {
      model.submitting = false; model.terminal = false; showRetryVerdict();
    }
  }

  function installFullControls() {
    model.keyHandler = (event) => {
      if (model.interaction !== "full" || model.terminal || model.submitting || event.repeat || event.metaKey || event.ctrlKey || event.altKey) return;
      const code = event.code;
      if (["KeyW", "KeyA", "KeyS", "KeyD", "KeyF", "KeyV", "KeyR", "KeyE"].includes(code)) event.preventDefault();
      if (code === "KeyW") move(1, 0, "keyboard");
      else if (code === "KeyS") move(-1, 0, "keyboard");
      else if (code === "KeyA") move(0, -1, "keyboard");
      else if (code === "KeyD") move(0, 1, "keyboard");
      else if (code === "KeyF") toggleLamp("keyboard_lamp");
      else if (code === "KeyV") toggleViewer("keyboard_viewer");
      else if (code === "KeyR") recallProbe("keyboard_recall");
      else if (code === "KeyE") toggleBreaker("keyboard_breaker");
    };
    window.addEventListener("keydown", model.keyHandler);
    model.canvas.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || model.terminal || model.submitting) return;
      event.preventDefault();
      model.canvas.setPointerCapture?.(event.pointerId);
      model.drag = {pointerId: event.pointerId, lastX: event.clientX, travel: 0};
    });
    model.canvas.addEventListener("pointermove", (event) => {
      if (!model.drag || model.drag.pointerId !== event.pointerId) return;
      const delta = event.clientX - model.drag.lastX;
      model.drag.lastX = event.clientX;
      model.drag.travel += Math.abs(delta);
      const quantized = Math.round(delta * 180);
      if (quantized) look(quantized, "viewport_drag");
      event.preventDefault();
    });
    const release = (event) => {
      if (!model.drag || model.drag.pointerId !== event.pointerId) return;
      const drag = model.drag;
      model.drag = null;
      model.canvas.releasePointerCapture?.(event.pointerId);
      if (event.type !== "pointercancel" && drag.travel < 5) deployProbe("viewport_probe");
      event.preventDefault();
    };
    model.canvas.addEventListener("pointerup", release);
    model.canvas.addEventListener("pointercancel", release);
  }

  function installSimplifiedControls() {
    document.querySelectorAll("[data-uw-move]").forEach((button) => button.addEventListener("click", () => {
      const [forward, strafe] = button.dataset.uwMove.split(",").map(Number);
      move(forward, strafe, "control_buttons");
    }));
    document.querySelectorAll("[data-uw-turn]").forEach((button) => button.addEventListener("click", () => look(Number(button.dataset.uwTurn), "turn_buttons")));
    document.getElementById("uw-lamp")?.addEventListener("click", () => toggleLamp("lamp_button"));
    document.getElementById("uw-viewer")?.addEventListener("click", () => toggleViewer("viewer_button"));
    document.getElementById("uw-probe")?.addEventListener("click", () => deployProbe("probe_button"));
    document.getElementById("uw-recall")?.addEventListener("click", () => recallProbe("recall_button"));
    document.getElementById("uw-breaker")?.addEventListener("click", () => toggleBreaker("breaker_button"));
  }

  async function render(state, helpers) {
    cleanup();
    document.body.dataset.mechanic = "unwatched-wing";
    const interaction = state.control_condition?.interaction || "full";
    Object.assign(model, {
      state,
      helpers,
      interaction,
      pose: {x: Number(state.initial_pose.x), y: Number(state.initial_pose.y), angle_mdeg: normalizeMdeg(state.initial_pose.angle_mdeg)},
      targetCursor: 0,
      targetArmed: true,
      dockOccupied: false,
      lampOn: true,
      viewerOpen: false,
      probePlinthId: null,
      lights: Object.fromEntries(state.wall_lights.map((item) => [item.id, Boolean(item.enabled)])),
      pinReady: new Set(),
      jumpCount: 0,
      rejectedHandoffs: 0,
      entangled: false,
      events: [],
      counts: {moves: 0, looks: 0, equipment: 0, breakers: 0},
      drag: null,
      submitting: false,
      terminal: false,
      forceReveal: false,
      canvas: null,
      context: null,
      darknessSample: {mean_luminance: 1, max_luminance: 1},
    });
    const equipment = interaction === "full"
      ? `<div class="uw-equipment uw-equipment-full" aria-label="equipment and keyboard controls"><span><small><kbd>F</kbd>HAND LAMP</small><b id="uw-lamp-state">ON</b></span><span><small><kbd>V</kbd>VIEWER</small><b id="uw-viewer-state">CLOSED</b></span><span><small>PROBE · <kbd>R</kbd>RECALL</small><b id="uw-probe-state">RECALLED</b></span><span class="uw-equipment-command"><small><kbd>E</kbd>ISOLATOR</small></span></div>`
      : `<div class="uw-equipment"><span><small>HAND LAMP</small><b id="uw-lamp-state">ON</b></span><span><small>VIEWER</small><b id="uw-viewer-state">CLOSED</b></span><span><small>PROBE</small><b id="uw-probe-state">RECALLED</b></span></div>`;
    const simplified = interaction === "simplified" ? `<div class="uw-simple-pad"><button data-uw-turn="-15000" aria-label="turn left">↶</button><button data-uw-move="1,0" aria-label="step forward">↑</button><button data-uw-turn="15000" aria-label="turn right">↷</button><button data-uw-move="0,-1" aria-label="step left">←</button><i></i><button data-uw-move="0,1" aria-label="step right">→</button><span></span><button data-uw-move="-1,0" aria-label="step backward">↓</button><span></span></div><div class="uw-simple-tools"><button id="uw-lamp">LAMP</button><button id="uw-viewer">VIEWER</button><button id="uw-probe">PROBE</button><button id="uw-recall">RECALL</button><button id="uw-breaker">ISOLATOR</button></div>` : "";
    helpers.app.innerHTML = `<section class="unwatched-wing" data-interaction="${clean(interaction)}" data-blackout="false" data-viewer="closed" data-lamp="on" tabindex="0">
      <header class="uw-head"><div><span>MINISTRY OF UNSTABLE COLLECTIONS / NIGHT TRANSFER</span><h1>${clean(state.prompt)}</h1></div><aside><small>CONSIGNMENT</small><canvas id="uw-dossier-canvas" width="116" height="112"></canvas><b>${clean(state.target_dossier.name)}</b></aside></header>
      <main class="uw-main"><section class="uw-viewport"><canvas id="uw-world" width="${VIEW_WIDTH}" height="${VIEW_HEIGHT}" aria-label="first-person view of the unstable museum wing"></canvas><div class="uw-probe-view"><canvas id="uw-probe-feed" width="218" height="132"></canvas></div></section>
      <aside class="uw-console">${equipment}${simplified}</aside></main>
      <footer class="uw-foot"><div class="readout" data-status="idle"></div><button id="uw-abandon" type="button">ABORT / FRESH WING</button></footer>
      <div class="uw-blackout" aria-hidden="true"></div>${helpers.cheatPanelTemplate()}
    </section>`;
    model.canvas = document.getElementById("uw-world");
    model.context = model.canvas.getContext("2d", {alpha: false, willReadFrequently: true});
    if (interaction === "full") installFullControls(); else installSimplifiedControls();
    document.getElementById("uw-abandon")?.addEventListener("click", abandon);
    helpers.installCheatPanel();
    window.unwatchedWingModel = model;
    window.unwatchedWingPublicMath = {circleClear, castWall, lineOfSight, targetObservation, settleObservation, boundary: "public render geometry only; no private solver route"};
    drawDossier();
    drawWorld();
    updatePanels();
    document.querySelector(".unwatched-wing")?.focus();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.unwatched_wing = {render, rootSelector: ".unwatched-wing"};
})();
