(() => {
  "use strict";

  let model = null;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const round2 = (value) => Math.round(Number(value) * 100) / 100;
  const round4 = (value) => Math.round(Number(value) * 10000) / 10000;
  const norm = (angle) => ((Number(angle) % 360) + 360) % 360;
  const angleDelta = (angle) => ((Number(angle) + 180) % 360 + 360) % 360 - 180;
  const clean = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
  const valueIndex = (value) => clamp(Number(String(value).split("-").at(-1)) || 0, 0, 3);
  const pointDistance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

  function record(kind, details = {}) {
    const event = {sequence: model.events.length + 1, kind, ...details};
    model.events.push(event);
    return event;
  }

  function canvasPoint(event) {
    const canvas = document.getElementById("landfall-panorama");
    const rect = canvas.getBoundingClientRect();
    return [
      round2(clamp((event.clientX - rect.left) / rect.width * model.state.journey.panorama_width, 0, model.state.journey.panorama_width)),
      round2(clamp((event.clientY - rect.top) / rect.height * model.state.journey.panorama_height, 0, model.state.journey.panorama_height)),
    ];
  }

  function mapPoint(event) {
    const svg = document.getElementById("landfall-map");
    const matrix = svg.getScreenCTM();
    if (matrix) {
      const screenPoint = svg.createSVGPoint();
      screenPoint.x = event.clientX;
      screenPoint.y = event.clientY;
      const mapped = screenPoint.matrixTransform(matrix.inverse());
      return [
        round2(clamp(mapped.x, 0, model.state.map.width)),
        round2(clamp(mapped.y, 0, model.state.map.height)),
      ];
    }
    const rect = svg.getBoundingClientRect();
    return [
      round2(clamp((event.clientX - rect.left) / rect.width * model.state.map.width, 0, model.state.map.width)),
      round2(clamp((event.clientY - rect.top) / rect.height * model.state.map.height, 0, model.state.map.height)),
    ];
  }

  function clampMapPan(pan = model.mapPan, zoom = model.mapZoom) {
    return [
      round2(clamp(pan[0], model.state.map.width * (1 - zoom), 0)),
      round2(clamp(pan[1], model.state.map.height * (1 - zoom), 0)),
    ];
  }

  function currentNode() {
    return model.nodeById[model.currentNode];
  }

  function arrowPoint(road) {
    const journey = model.state.journey;
    const difference = angleDelta(Number(road.bearing) - model.yaw);
    if (Math.abs(difference) > journey.field_of_view_deg / 2 - 4) return null;
    return [
      journey.panorama_width / 2 + difference / (journey.field_of_view_deg / 2) * journey.panorama_width * .43,
      journey.panorama_height * .78 + Math.min(Math.abs(difference) / (journey.field_of_view_deg / 2), 1) * 18,
    ];
  }

  function iconSvg(feature, value, compact = false) {
    const index = valueIndex(value);
    const ink = "#182b31";
    const rust = ["#b5543c", "#d28b35", "#3f7a72", "#745677"][index];
    let body = "";
    if (feature === "script") {
      const glyphs = [
        '<circle cx="28" cy="30" r="9"/><path d="M46 18v25m0-14 15-11m-15 12 16 12"/>',
        '<path d="M18 42 29 18l11 24m-17-11h13M49 18l15 24m0-24L49 42"/>',
        '<rect x="18" y="19" width="18" height="22"/><path d="M47 19h18v22H47m0-11h18"/>',
        '<path d="M18 19q22 2 18 22m12-22q-5 20 18 22M23 31h37"/>',
      ][index];
      body = `<rect x="8" y="10" width="80" height="43" rx="3" fill="#e8dfc5" stroke="${ink}" stroke-width="3"/><g fill="none" stroke="${rust}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">${glyphs}</g>`;
    } else if (feature === "milestone") {
      const shapes = [
        "M30 54V26q0-17 18-17t18 17v28Z",
        "M28 54V24L48 7l20 17v30Z",
        "M28 54V12h15v13h10V12h15v42Z",
        "M29 54V10h38v19l-10 8 10 8v9Z",
      ];
      body = `<path d="${shapes[index]}" fill="#eee4c9" stroke="${ink}" stroke-width="3"/><path d="M38 34h20" stroke="${rust}" stroke-width="5"/>`;
    } else if (feature === "pole") {
      const colors = ["#b5543c", "#d19b38", "#397a73", "#72597b"];
      let bands = "";
      for (let row = 0; row < 4; row += 1) {
        const fill = colors[(row + index) % 4];
        const width = index === 2 && row % 2 ? 13 : 20;
        bands += `<rect x="${48 - width / 2}" y="${17 + row * 9}" width="${width}" height="7" fill="${fill}"/>`;
      }
      body = `<path d="M48 7v49M21 17h54" stroke="${ink}" stroke-width="5" stroke-linecap="round"/>${bands}`;
    } else if (feature === "roof") {
      const peaks = [22, 12, 31, 18];
      const over = [14, 8, 18, 11];
      body = `<path d="M12 48h72L48 ${peaks[index]}Z" fill="${rust}" stroke="${ink}" stroke-width="3"/><path d="M${over[index]} 49v10h${96 - over[index] * 2}V49" fill="#e8dfc5" stroke="${ink}" stroke-width="3"/>`;
    } else if (feature === "crop") {
      const heads = ["circle", "diamond", "fork", "reed"][index];
      let stalks = "";
      for (let x = 19; x <= 77; x += 14) {
        stalks += `<path d="M${x} 56V22" stroke="${ink}" stroke-width="3"/>`;
        if (heads === "circle") stalks += `<circle cx="${x}" cy="18" r="6" fill="${rust}"/>`;
        else if (heads === "diamond") stalks += `<path d="m${x} 10 7 8-7 8-7-8Z" fill="${rust}"/>`;
        else if (heads === "fork") stalks += `<path d="M${x} 23l-7-11m7 11 7-11" stroke="${rust}" stroke-width="4"/>`;
        else stalks += `<path d="M${x} 24q-12-8-9-15m9 15q12-8 9-15" fill="none" stroke="${rust}" stroke-width="4"/>`;
      }
      body = stalks;
    } else {
      const marks = [
        '<rect x="18" y="24" width="22" height="16"/><circle cx="59" cy="32" r="8"/>',
        '<circle cx="29" cy="32" r="9"/><rect x="47" y="24" width="28" height="16"/>',
        '<rect x="16" y="22" width="14" height="20"/><rect x="40" y="22" width="14" height="20"/><rect x="64" y="22" width="14" height="20"/>',
        '<path d="M17 40V24h18l10 16m5-16h28v16H50Z"/>',
      ][index];
      body = `<rect x="7" y="14" width="82" height="36" rx="7" fill="#e8dfc5" stroke="${ink}" stroke-width="3"/><g fill="${rust}" stroke="${rust}" stroke-width="3">${marks}</g>`;
    }
    return `<svg class="landfall-feature-icon${compact ? " is-compact" : ""}" viewBox="0 0 96 64" aria-hidden="true">${body}</svg>`;
  }

  function drawEvidence(context, clue, x, y) {
    const index = valueIndex(clue.value);
    const rust = ["#c9543a", "#df9c38", "#3f8d7d", "#8a5a8f"][index];
    context.save();
    context.translate(x, y);
    context.shadowColor = "rgba(0,0,0,.38)";
    context.shadowBlur = 14;
    context.lineJoin = "round";
    context.lineCap = "round";
    context.strokeStyle = "#183139";
    context.fillStyle = "#efe4c4";
    context.lineWidth = 5;
    if (clue.feature === "script") {
      context.fillRect(-82, -62, 164, 76); context.strokeRect(-82, -62, 164, 76);
      context.strokeStyle = rust; context.lineWidth = 8;
      if (index === 0) { context.beginPath(); context.arc(-34, -25, 16, 0, Math.PI * 2); context.stroke(); context.beginPath(); context.moveTo(14, -44); context.lineTo(14, -5); context.moveTo(14, -24); context.lineTo(50, -43); context.moveTo(14, -23); context.lineTo(50, -4); context.stroke(); }
      else if (index === 1) { context.beginPath(); context.moveTo(-58, -7); context.lineTo(-34, -49); context.lineTo(-10, -7); context.moveTo(-50, -23); context.lineTo(-18, -23); context.moveTo(17, -49); context.lineTo(52, -7); context.moveTo(52, -49); context.lineTo(17, -7); context.stroke(); }
      else if (index === 2) { context.strokeRect(-57, -47, 39, 39); context.strokeRect(14, -47, 39, 39); context.beginPath(); context.moveTo(14, -27); context.lineTo(53, -27); context.stroke(); }
      else { context.beginPath(); context.moveTo(-56, -46); context.quadraticCurveTo(-6, -42, -18, -7); context.moveTo(12, -46); context.quadraticCurveTo(4, -9, 57, -7); context.moveTo(-46, -26); context.lineTo(48, -26); context.stroke(); }
      context.strokeStyle = "#5e4b35"; context.lineWidth = 7; context.beginPath(); context.moveTo(-55, 15); context.lineTo(-55, 74); context.moveTo(55, 15); context.lineTo(55, 74); context.stroke();
    } else if (clue.feature === "milestone") {
      context.beginPath();
      if (index === 0) { context.moveTo(-38, 46); context.lineTo(-38, -12); context.arc(0, -12, 38, Math.PI, 0); context.lineTo(38, 46); }
      else if (index === 1) { context.moveTo(-40, 46); context.lineTo(-40, -12); context.lineTo(0, -54); context.lineTo(40, -12); context.lineTo(40, 46); }
      else if (index === 2) { context.moveTo(-42, 46); context.lineTo(-42, -45); context.lineTo(-12, -45); context.lineTo(-12, -15); context.lineTo(12, -15); context.lineTo(12, -45); context.lineTo(42, -45); context.lineTo(42, 46); }
      else { context.moveTo(-40, 46); context.lineTo(-40, -48); context.lineTo(40, -48); context.lineTo(40, -5); context.lineTo(18, 9); context.lineTo(40, 24); context.lineTo(40, 46); }
      context.closePath(); context.fill(); context.stroke();
      context.strokeStyle = rust; context.lineWidth = 10; context.beginPath(); context.moveTo(-20, 10); context.lineTo(20, 10); context.stroke();
    } else if (clue.feature === "pole") {
      context.strokeStyle = "#23353b"; context.lineWidth = 10; context.beginPath(); context.moveTo(0, -82); context.lineTo(0, 66); context.moveTo(-62, -58); context.lineTo(62, -58); context.stroke();
      const colors = ["#c9543a", "#df9c38", "#3f8d7d", "#8a5a8f"];
      for (let row = 0; row < 4; row += 1) { context.fillStyle = colors[(row + index) % 4]; const width = index === 2 && row % 2 ? 24 : 38; context.fillRect(-width / 2, -35 + row * 23, width, 16); }
    } else if (clue.feature === "roof") {
      const peaks = [-71, -91, -48, -75]; context.fillStyle = rust;
      context.beginPath(); context.moveTo(-92, 25); context.lineTo(0, peaks[index]); context.lineTo(92, 25); context.closePath(); context.fill(); context.stroke();
      context.fillStyle = "#e9debd"; context.fillRect(-72, 25, 144, 66); context.strokeRect(-72, 25, 144, 66);
      context.fillStyle = "#203840"; context.fillRect(-16, 52, 32, 39);
    } else if (clue.feature === "crop") {
      context.shadowBlur = 0; const head = ["circle", "diamond", "fork", "reed"][index];
      for (let sx = -66; sx <= 66; sx += 22) { context.strokeStyle = "#294b43"; context.lineWidth = 5; context.beginPath(); context.moveTo(sx, 66); context.lineTo(sx, -23); context.stroke(); context.fillStyle = rust; if (head === "circle") { context.beginPath(); context.arc(sx, -32, 11, 0, Math.PI * 2); context.fill(); } else if (head === "diamond") { context.beginPath(); context.moveTo(sx, -48); context.lineTo(sx + 12, -32); context.lineTo(sx, -16); context.lineTo(sx - 12, -32); context.closePath(); context.fill(); } else { context.strokeStyle = rust; context.lineWidth = 7; context.beginPath(); context.moveTo(sx, -20); context.lineTo(sx - 13, -47); context.moveTo(sx, -20); context.lineTo(sx + 13, -47); context.stroke(); } }
    } else {
      context.fillStyle = "#3b4547"; context.fillRect(-100, -54, 200, 102); context.fillStyle = "#eadfbd"; context.fillRect(-60, -25, 120, 45); context.strokeRect(-60, -25, 120, 45); context.fillStyle = rust;
      if (index === 0) { context.fillRect(-48, -14, 33, 24); context.beginPath(); context.arc(29, -2, 14, 0, Math.PI * 2); context.fill(); }
      else if (index === 1) { context.beginPath(); context.arc(-28, -2, 15, 0, Math.PI * 2); context.fill(); context.fillRect(5, -14, 42, 24); }
      else if (index === 2) { [-38, -6, 26].forEach((px) => context.fillRect(px, -16, 18, 28)); }
      else { context.beginPath(); context.moveTo(-48, 12); context.lineTo(-48, -16); context.lineTo(-10, -16); context.lineTo(8, 12); context.lineTo(8, -16); context.lineTo(48, -16); context.lineTo(48, 12); context.closePath(); context.fill(); }
    }
    context.shadowBlur = 0;
    context.fillStyle = "rgba(13,31,37,.86)"; context.fillRect(-84, 77, 168, 24);
    context.fillStyle = "#f5e8c4"; context.font = "700 12px Georgia"; context.textAlign = "center";
    context.fillText(model.state.feature_labels[clue.feature], 0, 94);
    context.restore();
  }

  function drawLandmark(context, landmark, x, y) {
    context.save(); context.translate(x, y); context.strokeStyle = "#213b3d"; context.fillStyle = "#e6cf94"; context.lineWidth = 6; context.lineCap = "round"; context.lineJoin = "round";
    if (landmark.kind === "wind-pump") { context.beginPath(); context.moveTo(0, 66); context.lineTo(0, -48); context.stroke(); for (let angle = 0; angle < 4; angle += 1) { context.save(); context.rotate(angle * Math.PI / 2); context.fillRect(-5, -57, 10, 48); context.restore(); } context.beginPath(); context.arc(0, -8, 12, 0, Math.PI * 2); context.fill(); }
    else if (landmark.kind === "stone-ring") { context.beginPath(); context.arc(0, 10, 48, 0, Math.PI * 2); context.stroke(); context.beginPath(); context.arc(0, 10, 24, 0, Math.PI * 2); context.stroke(); }
    else if (landmark.kind === "signal-pine") { for (let row = 0; row < 3; row += 1) { context.beginPath(); context.moveTo(0, -60 + row * 27); context.lineTo(-42 + row * 7, 10 + row * 18); context.lineTo(42 - row * 7, 10 + row * 18); context.closePath(); context.fill(); context.stroke(); } context.beginPath(); context.moveTo(0, 0); context.lineTo(0, 72); context.stroke(); }
    else { context.beginPath(); context.ellipse(0, 37, 54, 20, 0, 0, Math.PI * 2); context.fill(); context.stroke(); context.beginPath(); context.moveTo(-35, 34); context.lineTo(-15, -43); context.lineTo(15, -43); context.lineTo(35, 34); context.stroke(); }
    context.restore();
  }

  function drawPanorama() {
    if (!model) return;
    const canvas = document.getElementById("landfall-panorama");
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    const width = model.state.journey.panorama_width;
    const height = model.state.journey.panorama_height;
    const scene = currentNode();
    const sky = context.createLinearGradient(0, 0, 0, height);
    sky.addColorStop(0, "#8fb3b0"); sky.addColorStop(.52, "#d8c8a1"); sky.addColorStop(.53, "#8b9a67"); sky.addColorStop(1, "#32473d");
    context.fillStyle = sky; context.fillRect(0, 0, width, height);
    context.fillStyle = "rgba(238,224,184,.62)"; context.beginPath(); context.arc(width * .74, 90, 47, 0, Math.PI * 2); context.fill();
    const shift = model.yaw / 360 * 180;
    context.fillStyle = "#6e785c"; context.beginPath(); context.moveTo(0, 290); for (let x = -80; x <= width + 80; x += 80) context.lineTo(x, 250 + Math.sin((x + shift) * .018 + scene.scene_variant) * 34); context.lineTo(width, 350); context.lineTo(0, 350); context.fill();
    context.fillStyle = "#798353"; context.fillRect(0, 315, width, height - 315);
    context.fillStyle = "rgba(234,214,160,.25)"; for (let x = -100 + shift % 82; x < width; x += 82) context.fillRect(x, 330, 2, height - 330);
    for (const road of scene.roads) {
      const point = arrowPoint(road); if (!point) continue;
      const roadWidth = 84;
      context.fillStyle = "rgba(211,196,159,.72)"; context.beginPath(); context.moveTo(width / 2 - 36, height); context.lineTo(width / 2 + 36, height); context.lineTo(point[0] + roadWidth / 2, point[1] + 30); context.lineTo(point[0] - roadWidth / 2, point[1] + 30); context.closePath(); context.fill();
    }
    const objects = [];
    if (scene.clue) { const difference = angleDelta(scene.clue.bearing - model.yaw); if (Math.abs(difference) <= model.state.journey.field_of_view_deg / 2 - 2) objects.push({kind: "clue", value: scene.clue, diff: difference}); }
    if (scene.landmark) { const difference = angleDelta(scene.landmark.bearing - model.yaw); if (Math.abs(difference) <= model.state.journey.field_of_view_deg / 2 - 2) objects.push({kind: "landmark", value: scene.landmark, diff: difference}); }
    objects.forEach((item) => { const x = width / 2 + item.diff / (model.state.journey.field_of_view_deg / 2) * width * .43; if (item.kind === "clue") drawEvidence(context, item.value, x, 325); else drawLandmark(context, item.value, x, 305); });
    for (const road of scene.roads) {
      const point = arrowPoint(road); if (!point) continue;
      context.save(); context.translate(point[0], point[1]); context.fillStyle = "#f1dfad"; context.strokeStyle = "#1b353b"; context.lineWidth = 5; context.shadowColor = "rgba(0,0,0,.35)"; context.shadowBlur = 12; context.beginPath(); context.arc(0, 0, 31, 0, Math.PI * 2); context.fill(); context.stroke(); context.shadowBlur = 0; context.fillStyle = "#b64d38"; context.beginPath(); context.moveTo(0, -15); context.lineTo(17, 11); context.lineTo(6, 9); context.lineTo(6, 19); context.lineTo(-6, 19); context.lineTo(-6, 9); context.lineTo(-17, 11); context.closePath(); context.fill(); context.restore();
    }
    context.fillStyle = "rgba(14,38,43,.82)"; context.fillRect(18, 18, 210, 44); context.fillStyle = "#f2e3b7"; context.font = "700 14px Georgia"; context.textAlign = "left"; context.fillText(`BEARING ${String(Math.round(model.yaw)).padStart(3, "0")}°`, 34, 45);
    context.fillStyle = "rgba(14,38,43,.74)"; context.fillRect(width - 252, 18, 234, 44); context.fillStyle = "#f2e3b7"; context.textAlign = "right"; context.fillText(`POSITION UNMARKED  ·  ${model.steps}/${model.state.journey.step_budget}`, width - 34, 45);
    updateRoadControls();
  }

  function updateRoadControls() {
    const shell = document.getElementById("landfall-road-buttons");
    if (!shell || model.interaction !== "simplified") return;
    const visible = currentNode().roads.filter((road) => arrowPoint(road));
    shell.innerHTML = visible.length
      ? visible.map((road) => `<button type="button" data-road-target="${clean(road.to)}">TAKE ROAD ${Math.round(road.bearing)}°</button>`).join("")
      : "";
  }

  function updateHeader() {
    const steps = document.getElementById("landfall-steps"); if (steps) steps.textContent = `${model.steps}/${model.state.journey.step_budget}`;
    const current = document.getElementById("landfall-current-road"); if (current) current.textContent = "UNMARKED";
    const submit = document.getElementById("landfall-submit"); if (submit) submit.dataset.ready = Object.keys(model.selections).length === model.state.active_features.length && Boolean(model.pin) ? "true" : "false";
    drawPanorama();
  }

  function beginPan(event) {
    if (model.interaction !== "full" || model.panHold || model.submitting || model.terminal) return;
    const point = canvasPoint(event);
    model.panHold = {pointerId: event.pointerId, start: point, baseYaw: model.yaw, moved: false};
    record("pan_start", {point, yaw_before: round2(model.yaw), input_source: "panorama_drag"});
    event.currentTarget.setPointerCapture?.(event.pointerId); event.preventDefault();
  }

  function movePan(event) {
    if (!model.panHold || model.panHold.pointerId !== event.pointerId) return;
    const point = canvasPoint(event);
    if (pointDistance(point, model.panHold.start) > 5) model.panHold.moved = true;
    model.yaw = round2(norm(model.panHold.baseYaw - (point[0] - model.panHold.start[0]) * .32));
    record("pan_move", {point, yaw_after: model.yaw, input_source: "panorama_drag"});
    model.helpers.setReadout("SURVEY OPEN", "idle"); drawPanorama(); event.preventDefault();
  }

  function endPan(event) {
    if (!model.panHold || model.panHold.pointerId !== event.pointerId) return;
    const point = canvasPoint(event); const hold = model.panHold; model.panHold = null;
    record("pan_end", {point, yaw: round2(model.yaw), input_source: "panorama_drag"});
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    if (!hold.moved) {
      const road = currentNode().roads.map((item) => ({item, point: arrowPoint(item)})).find(({point: arrow}) => arrow && pointDistance(point, arrow) <= 38)?.item;
      if (road) travel(road.to, "road_click", "road_arrow", point);
    }
    drawPanorama();
  }

  function turnStep(delta) {
    if (model.interaction !== "simplified" || model.submitting || model.terminal) return;
    const before = model.yaw; model.yaw = round2(norm(before + delta));
    record("turn_step", {yaw_before: round2(before), delta, yaw_after: model.yaw, input_source: "turn_buttons"});
    model.helpers.setReadout("SURVEY OPEN", "idle"); drawPanorama();
  }

  function travel(destination, kind, inputSource, point = null) {
    if (model.steps >= model.state.journey.step_budget || model.submitting || model.terminal) return;
    const road = currentNode().roads.find((item) => item.to === destination);
    if (!road || !arrowPoint(road)) return;
    const details = {from: model.currentNode, to: destination, yaw: round2(model.yaw), input_source: inputSource};
    if (point) details.point = point;
    record(kind, details);
    model.currentNode = destination; model.steps += 1; if (!model.visited.includes(destination)) model.visited.push(destination);
    model.helpers.setReadout("SURVEY OPEN", "idle"); updateHeader();
  }

  function mapMarkup() {
    const roads = [];
    const regions = [];
    for (const province of model.state.map.provinces) {
      const points = province.polygon.map((point) => point.join(",")).join(" ");
      regions.push(`<polygon class="landfall-province wash-${province.wash}" points="${points}"/><text class="landfall-map-label" x="${province.label[0]}" y="${province.label[1]}">${clean(province.name)}</text>`);
      const byId = Object.fromEntries(province.road.nodes.map((node) => [node.id, node]));
      for (const edge of province.road.edges) { const a = byId[edge[0]], b = byId[edge[1]]; roads.push(`<line class="landfall-map-road" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`); }
      for (const node of province.road.nodes) roads.push(`<circle class="landfall-map-node" cx="${node.x}" cy="${node.y}" r="2.8"/>`);
      const landmark = byId[province.road.landmark_node];
      roads.push(`<g class="landfall-map-landmark" transform="translate(${landmark.x} ${landmark.y})"><circle r="7"/><path d="M0-5 5 4-5 4Z"/></g>`);
    }
    const pin = model.pin ? `<g class="landfall-pin" transform="translate(${model.pin.x} ${model.pin.y})"><path d="M0 10C-10-2-12-8-12-15a12 12 0 1 1 24 0C12-8 10-2 0 10Z"/><circle cy="-15" r="4"/></g>` : "";
    return `<g id="landfall-map-world" transform="translate(${model.mapPan[0]} ${model.mapPan[1]}) scale(${model.mapZoom})">${regions.join("")}${roads.join("")}${pin}</g>`;
  }

  function renderMap() {
    const svg = document.getElementById("landfall-map"); if (!svg) return;
    svg.innerHTML = mapMarkup();
    const zoom = document.getElementById("landfall-map-zoom"); if (zoom) zoom.textContent = `${Math.round(model.mapZoom * 100)}%`;
  }

  function beginMapDrag(event) {
    if (model.interaction !== "full" || model.mapHold || model.submitting || model.terminal) return;
    const point = mapPoint(event); model.mapHold = {pointerId: event.pointerId, start: point, basePan: [...model.mapPan], moved: false};
    record("map_drag_start", {point, pan_before: [...model.mapPan], input_source: "map_drag"});
    event.currentTarget.setPointerCapture?.(event.pointerId); event.preventDefault();
  }

  function moveMapDrag(event) {
    if (!model.mapHold || model.mapHold.pointerId !== event.pointerId) return;
    const point = mapPoint(event); if (pointDistance(point, model.mapHold.start) > 5) model.mapHold.moved = true;
    model.mapPan = clampMapPan([model.mapHold.basePan[0] + point[0] - model.mapHold.start[0], model.mapHold.basePan[1] + point[1] - model.mapHold.start[1]]);
    record("map_drag_move", {point, pan_after: [...model.mapPan], input_source: "map_drag"}); renderMap(); event.preventDefault();
  }

  function endMapDrag(event) {
    if (!model.mapHold || model.mapHold.pointerId !== event.pointerId) return;
    const point = mapPoint(event); const hold = model.mapHold; model.mapHold = null;
    record("map_drag_end", {point, pan_after: [...model.mapPan], input_source: "map_drag"}); event.currentTarget.releasePointerCapture?.(event.pointerId);
    if (!hold.moved) placePin(point);
    renderMap();
  }

  function placePin(viewPoint) {
    const worldPoint = [round2((viewPoint[0] - model.mapPan[0]) / model.mapZoom), round2((viewPoint[1] - model.mapPan[1]) / model.mapZoom)];
    if (worldPoint[0] < 0 || worldPoint[0] > model.state.map.width || worldPoint[1] < 0 || worldPoint[1] > model.state.map.height) return;
    model.pin = {x: worldPoint[0], y: worldPoint[1]};
    record("map_pin", {view_point: viewPoint, world_point: worldPoint, input_source: "map_direct"});
    model.helpers.setReadout("LANDING PIN SET", "idle"); renderMap(); updateHeader();
  }

  function mapWheel(event) {
    if (model.interaction !== "full" || model.submitting || model.terminal) return;
    event.preventDefault(); const point = mapPoint(event); const before = model.mapZoom;
    const factor = event.deltaY < 0 ? 1.18 : 1 / 1.18; const after = clamp(before * factor, 1, model.state.map.max_zoom);
    const world = [(point[0] - model.mapPan[0]) / before, (point[1] - model.mapPan[1]) / before];
    model.mapZoom = round4(after); model.mapPan = clampMapPan([point[0] - world[0] * model.mapZoom, point[1] - world[1] * model.mapZoom]);
    record("map_wheel", {point, delta: event.deltaY < 0 ? -1 : 1, zoom_before: round4(before), zoom_after: model.mapZoom, pan_after: [...model.mapPan], input_source: "map_wheel"}); renderMap();
  }

  function mapZoomStep(direction) {
    if (model.interaction !== "simplified" || model.submitting || model.terminal) return;
    const before = model.mapZoom; const factor = direction > 0 ? 1.18 : 1 / 1.18; const after = clamp(before * factor, 1, model.state.map.max_zoom);
    const center = [model.state.map.width / 2, model.state.map.height / 2]; const world = [(center[0] - model.mapPan[0]) / before, (center[1] - model.mapPan[1]) / before];
    model.mapZoom = round4(after); model.mapPan = clampMapPan([center[0] - world[0] * model.mapZoom, center[1] - world[1] * model.mapZoom]);
    record("map_zoom_step", {direction, zoom_after: model.mapZoom, pan_after: [...model.mapPan], input_source: "map_buttons"}); renderMap();
  }

  function mapPanStep(direction) {
    if (model.interaction !== "simplified" || model.submitting || model.terminal) return;
    const deltas = {left: [36, 0], right: [-36, 0], up: [0, 36], down: [0, -36]}; const delta = deltas[direction]; if (!delta) return;
    model.mapPan = clampMapPan([model.mapPan[0] + delta[0], model.mapPan[1] + delta[1]]);
    record("map_pan_step", {direction, pan_after: [...model.mapPan], input_source: "map_buttons"}); renderMap();
  }

  function renderGuide() {
    const shell = document.getElementById("landfall-guide-cards"); if (!shell) return;
    const pageSize = model.state.guide.page_size; const start = model.guidePage * pageSize;
    shell.innerHTML = model.state.guide.provinces.slice(start, start + pageSize).map((province) => `<article class="landfall-guide-card"><header><h3>${clean(province.name)}</h3></header><div class="landfall-guide-features">${model.state.active_features.map((feature) => `<div><span>${clean(model.state.feature_labels[feature])}</span>${iconSvg(feature, province.signature[feature], true)}</div>`).join("")}</div></article>`).join("");
    const pages = Math.ceil(model.state.guide.provinces.length / pageSize); document.getElementById("landfall-guide-page").textContent = `PLATE ${model.guidePage + 1}/${pages}`;
    document.getElementById("landfall-guide-prev").disabled = model.guidePage === 0; document.getElementById("landfall-guide-next").disabled = model.guidePage >= pages - 1;
  }

  function renderDeposition() {
    const shell = document.getElementById("landfall-deposition-fields"); if (!shell) return;
    shell.innerHTML = model.state.active_features.map((feature) => `<fieldset><legend>${clean(model.state.feature_labels[feature])}</legend><div>${model.state.feature_values[feature].map((value) => `<button type="button" data-feature="${clean(feature)}" data-value="${clean(value)}" data-selected="${model.selections[feature] === value ? "true" : "false"}">${iconSvg(feature, value, true)}</button>`).join("")}</div></fieldset>`).join("");
  }

  function chooseAnswer(feature, value) {
    if (model.submitting || model.terminal) return;
    model.selections[feature] = value; record("answer_select", {feature, value, input_source: "deposition_buttons"});
    model.helpers.setReadout(`${model.state.feature_labels[feature]} ENTERED`, "idle"); renderDeposition(); updateHeader();
  }

  function changeGuidePage(delta) {
    const pages = Math.ceil(model.state.guide.provinces.length / model.state.guide.page_size); const next = clamp(model.guidePage + delta, 0, pages - 1); if (next === model.guidePage) return;
    model.guidePage = next; record("guide_page", {page: next}); renderGuide();
  }

  function openSurface(surface) {
    model.surface = surface; record("surface_tab", {surface});
    document.querySelectorAll("[data-landfall-surface]").forEach((node) => node.dataset.active = node.dataset.landfallSurface === surface ? "true" : "false");
    document.querySelectorAll("[data-landfall-tab]").forEach((node) => node.dataset.active = node.dataset.landfallTab === surface ? "true" : "false");
    if (surface === "map") renderMap(); if (surface === "guide") renderGuide(); if (surface === "deposition") renderDeposition();
  }

  function payload() {
    return {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      events: model.events,
      current_node: model.currentNode,
      step_count: model.steps,
      visited_nodes: [...model.visited],
      final_yaw: round2(model.yaw),
      selections: {...model.selections},
      pin: model.pin ? {...model.pin} : null,
      map_zoom: round4(model.mapZoom),
      map_pan: model.mapPan.map(round2),
      submission_count: model.submissionCount,
      completed: Object.keys(model.selections).length === model.state.active_features.length && Boolean(model.pin),
    };
  }

  async function submit() {
    if (!model || model.submitting || model.terminal || model.panHold || model.mapHold) return;
    record("submit"); model.submissionCount += 1; const current = model; current.submitting = true; current.helpers.setReadout("SUBMITTING", "pending");
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload())}); const outcome = await response.json();
      if (outcome.passed === true) {
        current.terminal = true; current.helpers.setReadout("PASS", "passed"); const root = document.querySelector(".unmarked-landfall"); if (root) root.dataset.verdict = "pass"; const verdict = document.querySelector(".landfall-verdict"); if (verdict) verdict.innerHTML = "<b>PASS</b>";
      } else if (outcome.passed === false && outcome.state) {
        const helpers = current.helpers; await render(outcome.state, helpers, {freshFailure: true}); model.helpers.setReadout("FAIL", "error");
      } else { current.submitting = false; current.helpers.setReadout("FAIL", "error"); }
    } catch (_error) { if (model === current) { current.submitting = false; current.helpers.setReadout("FAIL", "error"); } }
  }

  function clearFreshFailure() {
    const root = document.querySelector(".unmarked-landfall");
    if (!root || root.dataset.freshFailure !== "true") return;
    root.dataset.freshFailure = "false";
    if (!model.events.length) model.helpers.setReadout("SURVEY OPEN", "idle");
  }

  function installEvents() {
    const root = document.querySelector(".unmarked-landfall");
    root?.addEventListener("pointerdown", clearFreshFailure, true);
    root?.addEventListener("wheel", clearFreshFailure, {capture: true, passive: true});
    const canvas = document.getElementById("landfall-panorama");
    canvas.addEventListener("pointerdown", beginPan); canvas.addEventListener("pointermove", movePan); canvas.addEventListener("pointerup", endPan); canvas.addEventListener("pointercancel", endPan);
    document.getElementById("landfall-turn-left")?.addEventListener("click", () => turnStep(-30)); document.getElementById("landfall-turn-right")?.addEventListener("click", () => turnStep(30));
    document.getElementById("landfall-road-buttons")?.addEventListener("click", (event) => { const button = event.target.closest("[data-road-target]"); if (button) travel(button.dataset.roadTarget, "road_button", "road_buttons"); });
    document.querySelectorAll("[data-landfall-tab]").forEach((button) => button.addEventListener("click", () => openSurface(button.dataset.landfallTab)));
    const map = document.getElementById("landfall-map"); map.addEventListener("wheel", mapWheel, {passive: false}); map.addEventListener("pointerdown", beginMapDrag); map.addEventListener("pointermove", moveMapDrag); map.addEventListener("pointerup", endMapDrag); map.addEventListener("pointercancel", endMapDrag);
    if (model.interaction === "simplified") map.addEventListener("click", (event) => placePin(mapPoint(event)));
    document.querySelectorAll("[data-map-zoom]").forEach((button) => button.addEventListener("click", () => mapZoomStep(Number(button.dataset.mapZoom))));
    document.querySelectorAll("[data-map-pan]").forEach((button) => button.addEventListener("click", () => mapPanStep(button.dataset.mapPan)));
    document.getElementById("landfall-guide-prev").addEventListener("click", () => changeGuidePage(-1)); document.getElementById("landfall-guide-next").addEventListener("click", () => changeGuidePage(1));
    document.getElementById("landfall-deposition-fields").addEventListener("click", (event) => { const button = event.target.closest("[data-feature][data-value]"); if (button) chooseAnswer(button.dataset.feature, button.dataset.value); });
    document.getElementById("landfall-submit").addEventListener("click", submit);
  }

  async function render(state, helpers, options = {}) {
    document.body.dataset.mechanic = "unmarked-landfall"; document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const interaction = state.control_condition?.interaction || "full";
    model = {
      state, helpers, interaction, nodeById: Object.fromEntries(state.journey.nodes.map((node) => [node.id, node])), currentNode: state.journey.landing_node,
      yaw: Number(state.journey.initial_yaw), steps: 0, visited: [state.journey.landing_node], selections: {}, pin: null, events: [], panHold: null, mapHold: null,
      mapZoom: 1, mapPan: [0, 0], guidePage: 0, surface: "guide", submissionCount: 0, submitting: false, terminal: false,
    };
    window.unmarkedLandfallModel = model;
    const panoramaControls = interaction === "simplified" ? `<div class="landfall-pan-controls"><button id="landfall-turn-left" type="button">TURN −30°</button><div id="landfall-road-buttons"></div><button id="landfall-turn-right" type="button">TURN +30°</button></div>` : "";
    const mapControls = interaction === "simplified" ? `<div class="landfall-map-controls"><button data-map-zoom="1">+</button><button data-map-pan="up">↑</button><button data-map-zoom="-1">−</button><button data-map-pan="left">←</button><button data-map-pan="down">↓</button><button data-map-pan="right">→</button></div>` : "";
    helpers.app.innerHTML = `<section class="unmarked-landfall" data-interaction="${clean(interaction)}" data-fresh-failure="${options.freshFailure ? "true" : "false"}" data-verdict=""><div class="landfall-verdict">${options.freshFailure ? "<b>FAIL</b>" : ""}</div><header class="landfall-head"><div><span>OFFICE OF UNMAPPED AFFAIRS · ${clean(state.challenge_id)}</span><h1>UNMARKED LANDFALL</h1><p>${clean(state.prompt)}</p></div><dl><div><dt>POSITION</dt><dd id="landfall-current-road">UNMARKED</dd></div><div><dt>STEPS</dt><dd id="landfall-steps">0/${state.journey.step_budget}</dd></div></dl></header><main class="landfall-workspace"><section class="landfall-panorama-shell"><canvas id="landfall-panorama" width="${state.journey.panorama_width}" height="${state.journey.panorama_height}"></canvas>${panoramaControls}</section><aside class="landfall-atlas"><nav><button type="button" data-landfall-tab="map" data-active="false">REGIONAL MAP</button><button type="button" data-landfall-tab="guide" data-active="true">FIELD GUIDE</button><button type="button" data-landfall-tab="deposition" data-active="false">DEPOSITION</button></nav><section class="landfall-surface landfall-map-surface" data-landfall-surface="map" data-active="false"><div class="landfall-map-meta"><span>UNMARKED REGIONAL SHEET</span><b id="landfall-map-zoom">100%</b></div><svg id="landfall-map" viewBox="0 0 ${state.map.width} ${state.map.height}" aria-label="Unmarked regional road map"></svg>${mapControls}</section><section class="landfall-surface landfall-guide-surface" data-landfall-surface="guide" data-active="true"><div class="landfall-guide-index"><span>PROVINCIAL INDEX</span></div><div id="landfall-guide-cards"></div><footer><button id="landfall-guide-prev" type="button">← PREVIOUS</button><b id="landfall-guide-page">PLATE 1</b><button id="landfall-guide-next" type="button">NEXT →</button></footer></section><section class="landfall-surface landfall-deposition-surface" data-landfall-surface="deposition" data-active="false"><header><span>FORM UL–7</span><h2>OBSERVED CONVENTIONS</h2></header><div id="landfall-deposition-fields"></div></section></aside></main><footer class="landfall-foot"><div><span>FIELD RECORD UL–7 · ORIGINAL DROP SITE UNMARKED</span><div class="readout" data-status="idle">SURVEY OPEN</div></div><button id="landfall-submit" data-ready="false" type="button">${clean(state.submit_label)}</button></footer>${helpers.cheatPanelTemplate()}</section>`;
    installEvents(); renderMap(); renderGuide(); renderDeposition(); updateHeader(); helpers.installCheatPanel();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.unmarked_landfall = {rootSelector: ".unmarked-landfall", render};
})();
