(() => {
  "use strict";

  const MECHANIC_ID = "four_pane_pilgrimage";
  let model = null;
  const esc = value => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const round = value => Math.round(Number(value) * 1000) / 1000;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const copy = value => JSON.parse(JSON.stringify(value));
  const interaction = () => model?.state?.control_condition?.interaction || "full";
  const inputSource = () => interaction() === "simplified" ? "proxy_controls" : "direct_manipulation";
  const panelById = id => model.state.panels.find(panel => panel.id === id);
  const plateById = id => model.state.plates.find(plate => plate.id === id);
  const slotForPanel = id => model.slots.indexOf(id);

  function normalizedPoint(event, node) {
    const rect = node?.getBoundingClientRect?.();
    if (!rect || rect.width <= 0 || rect.height <= 0) return null;
    return [round(clamp((event.clientX - rect.left) / rect.width, 0, 1)), round(clamp((event.clientY - rect.top) / rect.height, 0, 1))];
  }

  function tracePoint(event) {
    return normalizedPoint(event, document.querySelector(".four-pane-pilgrimage"));
  }

  function appendTrace(drag, event) {
    const point = tracePoint(event);
    if (!point) return;
    const previous = drag.trace.at(-1);
    if (previous && Math.hypot(point[0] - previous[0], point[1] - previous[1]) < .006) return;
    if (drag.trace.length < 32) drag.trace.push(point);
    else drag.trace[drag.trace.length - 1] = point;
  }

  function record(kind, details = {}) {
    const event = {sequence: model.events.length + 1, kind, ...details};
    model.events.push(event);
    return event;
  }

  function applyPoint(point, transform) {
    return [
      (point[0] - 150) * transform.zoom + 150 + transform.pan_x,
      (point[1] - 100) * transform.zoom + 100 + transform.pan_y,
    ];
  }

  function joinError(panel, join, transform, source) {
    const indices = join[source ? "source_indices" : "target_indices"];
    const targets = join[source ? "source_targets" : "target_targets"];
    let sum = 0;
    indices.forEach((index, offset) => {
      const actual = applyPoint(panel.path_points[index], transform);
      const target = targets[offset];
      sum += (actual[0] - target[0]) ** 2 + (actual[1] - target[1]) ** 2;
    });
    return 2 * Math.sqrt(sum / Math.max(1, indices.length));
  }

  function eligible() {
    const join = model.state.joins[model.stage];
    if (!join) return {accepted: false, source: 0, target: 0};
    if (model.slots[join.source_slot] !== join.source_panel_id || model.slots[join.target_slot] !== join.target_panel_id) {
      return {accepted: false, source: Infinity, target: Infinity};
    }
    const source = joinError(panelById(join.source_panel_id), join, model.transforms[join.source_panel_id], true);
    const target = joinError(panelById(join.target_panel_id), join, model.transforms[join.target_panel_id], false);
    const tolerance = model.state.limits.alignment_tolerance_units;
    let plateReady = true;
    if (join.required_plate_id) {
      const status = model.plates[join.required_plate_id];
      const plate = plateById(join.required_plate_id);
      const pose = status?.pose;
      const target = plate?.target_pose;
      const poseReady = Array.isArray(pose) && Array.isArray(target)
        && Math.abs(pose[0] - target[0]) <= model.state.limits.plate_drop_tolerance_units
        && Math.abs(pose[1] - target[1]) <= model.state.limits.plate_drop_tolerance_units;
      plateReady = status?.status === "stacked" && status.target_panel_id === join.target_panel_id && poseReady;
    }
    return {accepted: source <= tolerance && target <= tolerance && plateReady, source, target};
  }

  function transformAttr(transform) {
    return `translate(${150 + transform.pan_x} ${100 + transform.pan_y}) scale(${transform.zoom}) translate(-150 -100)`;
  }

  function pathD(points) {
    return points.map((point, index) => `${index ? "L" : "M"}${round(point[0])},${round(point[1])}`).join(" ");
  }

  function motifSvg(outline, size = 44) {
    const motif = outline?.motif || "keyhole";
    const ink = "currentColor";
    const shapes = {
      keyhole: `<path d="M22 7a10 10 0 1 0 6 18l5 12H11l5-12A10 10 0 0 0 22 7Z"/>`,
      split_moon: `<path d="M30 8a15 15 0 1 0 2 27A17 17 0 0 1 30 8Z"/><path d="M22 7v30" fill="none"/>`,
      ogive: `<path d="M7 38V22Q22 1 37 22v16Z"/><path d="M13 37V23Q22 10 31 23v14" fill="none"/>`,
      well: `<ellipse cx="22" cy="15" rx="16" ry="8"/><path d="M6 15v16c0 5 32 5 32 0V15M10 32h24" fill="none"/>`,
      lantern: `<path d="M15 9h14l6 9-4 18H13L9 18Z"/><path d="M17 9q5-9 10 0M14 19h16" fill="none"/>`,
      leaf: `<path d="M7 35Q9 8 38 7Q35 35 7 35Z"/><path d="M10 33 34 11M19 25l-1-10M25 19l9 1" fill="none"/>`,
    };
    return `<svg viewBox="0 0 44 44" width="${size}" height="${size}" aria-hidden="true"><g fill="none" stroke="${ink}" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" transform="rotate(${outline?.rotation_deg || 0} 22 22) scale(${outline?.scale || 1}) translate(${outline?.notch || 0} 0)">${shapes[motif] || shapes.keyhole}</g></svg>`;
  }

  function bridgeGeometry(fragment, targetOnly = false) {
    const horizontal = fragment?.axis !== "vertical";
    const offset = Number(fragment?.line_offset || 0);
    const crossbar = Number(fragment?.crossbar || 10);
    const hatchCount = Number(fragment?.hatch_count || 2);
    const slant = Number(fragment?.hatch_slant || 1);
    const main = horizontal
      ? (targetOnly ? `<path d="M2 ${32 + offset}h13m34 0h13"/>` : `<path d="M1 ${32 + offset}H63"/>`)
      : (targetOnly ? `<path d="M${32 + offset} 2v13m0 34v13"/>` : `<path d="M${32 + offset} 1V63"/>`);
    const bars = Array.from({length: hatchCount}, (_, index) => {
      const shift = (index - (hatchCount - 1) / 2) * 7;
      return horizontal
        ? `<path d="M${32 + shift} ${32 + offset - crossbar / 2}l${slant * 4} ${crossbar}"/>`
        : `<path d="M${32 + offset - crossbar / 2} ${32 + shift}l${crossbar} ${slant * 4}"/>`;
    }).join("");
    return `${main}${bars}`;
  }

  function fragmentSvg(plate, size = 64) {
    return `<svg class="fpp-fragment-art" viewBox="0 0 64 64" width="${size}" height="${size}" aria-hidden="true"><path class="fpp-fragment-paper" d="M7 13Q19 2 35 7T58 18L55 48Q41 62 24 56L6 47Z"/><g class="fpp-fragment-lines">${bridgeGeometry(plate.fragment)}</g><g class="fpp-fragment-silhouette" transform="translate(10 10) scale(1)">${motifSvg(plate.outline, 44)}</g></svg>`;
  }

  function targetFragmentSvg(plate, size = 68) {
    return `<svg class="fpp-target-art" viewBox="0 0 64 64" width="${size}" height="${size}" aria-hidden="true"><path class="fpp-torn-edge" d="M7 13Q19 2 35 7T58 18L55 48Q41 62 24 56L6 47Z"/><g class="fpp-target-lines">${bridgeGeometry(plate.fragment, true)}</g></svg>`;
  }

  function sceneSvg(panel) {
    const p = model.state.palette;
    const variant = panel.landmark_variant || 0;
    const common = `<path class="fpp-wash" d="M-20 ${154 + panel.wash_offset[1]} Q70 ${92 + panel.wash_offset[0] * .2} 155 ${145 - panel.wash_offset[1] * .4} T330 ${126 + panel.wash_offset[0] * .2}V220H-20Z"/>`;
    const scenes = {
      terraced_garden: `${common}<path d="M-8 164Q58 132 122 152T308 128M-8 178Q74 146 146 168T308 145M40 145v-58m-12 26q13-25 25 0m-18-12q-18-16-27 2m103 42V62m-16 41q16-32 33 0m-11-17q-20-19-33 2"/><circle cx="${242 + variant}" cy="45" r="22"/>`,
      bell_tower: `${common}<path d="M86 168V55l22-26 22 26v113M78 168h61M94 87h28M100 59q8-14 16 0v19h-16Zm8 19v44M171 170V94l23-18 22 18v76M180 112h28"/><path d="M16 153q42-28 72-5M215 148q45-22 93 2"/>`,
      moon_well: `${common}<ellipse cx="145" cy="137" rx="58" ry="24"/><ellipse cx="145" cy="137" rx="43" ry="15"/><path d="M87 137v31m116-31v31M68 168h154M55 81q42-45 84 0t86 0"/><circle cx="${235 - variant}" cy="48" r="28"/><path d="M224 28q-18 24 5 43"/>`,
      hill_shrine: `${common}<path d="M38 167Q80 91 142 148Q209 72 286 167M188 138V70h52v68M180 70h68l-13-16h-42ZM205 55V35m-12 0h25M75 145V98m-15 47h31M66 98h18l-9-20Z"/><circle cx="54" cy="48" r="18"/>`,
    };
    const clutter = panel.strokes.map((stroke, index) => `<path class="fpp-hatch hatch-${index % 3}" d="${pathD(stroke)}"/>`).join("");
    return `<g class="fpp-scene-art">${scenes[panel.scene_kind] || scenes.terraced_garden}${clutter}</g>`;
  }

  function routeSvg(panel) {
    const incoming = model.state.joins.find(join => join.target_panel_id === panel.id);
    const points = incoming?.required_plate_id ? panel.path_points.slice(1) : panel.path_points;
    const style = panel.route_style || {ink_key: "ink", accent_key: "wash", width: 3};
    const ink = model.state.palette[style.ink_key] || model.state.palette.ink;
    const accent = model.state.palette[style.accent_key] || model.state.palette.wash;
    return `<g class="fpp-scene-route feature-${esc(style.kind || "contour")}" style="--route-ink:${esc(ink)};--route-accent:${esc(accent)};--route-width:${Number(style.width || 3)}"><path class="fpp-route-accent" d="${pathD(points)}"/><path class="fpp-route-line" d="${pathD(points)}"/></g>`;
  }

  function figureSvg(panel) {
    const routeIndex = panel.route_index;
    if (model.stage !== routeIndex) return "";
    const pointIndex = routeIndex === 3 ? panel.path_points.length - 1 : 0;
    const point = applyPoint(panel.path_points[pointIndex], model.transforms[panel.id]);
    return `<g class="fpp-pilgrim ${model.walking ? "is-walking" : ""}" transform="translate(${round(point[0])} ${round(point[1] - 9)})"><circle cy="-7" r="4"/><path d="M0-3v12m0-7-7 7m7-7 7 7M0 9l-6 10m6-10 6 10"/></g>`;
  }

  function shrineSvg(panel) {
    if (!panel.has_shrine) return "";
    const point = applyPoint(panel.path_points.at(-1), model.transforms[panel.id]);
    return `<g class="fpp-shrine ${model.stage === 3 ? "is-reached" : ""}" transform="translate(${round(point[0])} ${round(point[1] - 14)})"><path d="M-16 12V-8h32v20M-21-8h42L12-20h-24Z"/><circle cy="-8" r="4"/></g>`;
  }

  function visibleBoundPlates(panelId) {
    return model.state.plates.filter(plate => plate.source_panel_id === panelId && plate.unlock_stage <= model.stage && model.plates[plate.id].status === "bound");
  }

  function poseStyle(pose) {
    return {x: `${Number(pose?.[0] ?? 150) / 3}%`, y: `${Number(pose?.[1] ?? 100) / 2}%`};
  }

  function apertureRecess(panelId) {
    const join = model.state.joins[model.stage];
    if (!join?.required_plate_id || join.target_panel_id !== panelId) return "";
    const plate = plateById(join.required_plate_id);
    const position = poseStyle(plate.target_pose);
    return `<div class="fpp-aperture-target" data-plate-target="${esc(plate.id)}" data-target-panel="${esc(panelId)}" style="--aperture-x:${position.x};--aperture-y:${position.y}" aria-label="Torn opening in illustrated pane">${targetFragmentSvg(plate, 68)}</div>`;
  }

  function stackedPlateSvg(panelId) {
    return model.state.plates.filter(plate => {
      const status = model.plates[plate.id];
      return status.status === "stacked" && status.target_panel_id === panelId;
    }).map((plate, index) => {
      const position = poseStyle(model.plates[plate.id].pose);
      return `<div class="fpp-stacked-plate" style="--plate-index:${index};--aperture-x:${position.x};--aperture-y:${position.y}" data-plate-id="${esc(plate.id)}">${fragmentSvg(plate, 72)}</div>`;
    }).join("");
  }

  function boundPlateTemplate(plate, panel) {
    const point = applyPoint(plate.source_anchor, model.transforms[panel.id]);
    return `<button type="button" class="fpp-bound-plate" data-plate-id="${esc(plate.id)}" style="--plate-x:${point[0] / 3}%;--plate-y:${point[1] / 2}%" aria-label="Loose edge in illustrated pane">${fragmentSvg(plate, 62)}</button>`;
  }

  function panelTemplate(panelId, slotIndex) {
    const panel = panelById(panelId);
    const transform = model.transforms[panelId];
    const bound = visibleBoundPlates(panelId).map(plate => boundPlateTemplate(plate, panel)).join("");
    const clipId = `fpp-clip-${panelId}`;
    return `<article class="fpp-slot" data-slot="${slotIndex}" data-panel-id="${esc(panelId)}">
      <header class="fpp-pane-grip" data-panel-id="${esc(panelId)}"><span class="fpp-pane-sigil">${["◐", "◇", "◒", "△"][panel.landmark_variant % 4]}</span><i></i><b>${interaction() === "simplified" ? `PANE ${slotIndex + 1}` : ""}</b></header>
      <div class="fpp-canvas-wrap">
        <svg class="fpp-canvas" data-panel-id="${esc(panelId)}" viewBox="0 0 300 200" preserveAspectRatio="none" role="img" aria-label="Illustrated pane ${slotIndex + 1}">
          <defs><clipPath id="${clipId}"><rect width="300" height="200" rx="1"/></clipPath></defs>
          <rect class="fpp-paper" width="300" height="200"/>
          <g clip-path="url(#${clipId})" transform="${transformAttr(transform)}">
            ${sceneSvg(panel)}
            ${routeSvg(panel)}
          </g>
          ${shrineSvg(panel)}${figureSvg(panel)}
        </svg>
        ${apertureRecess(panelId)}${stackedPlateSvg(panelId)}${bound}
        <div class="fpp-transform-mark"><span>${Math.round(transform.zoom * 100)}</span><i style="--pan-x:${transform.pan_x};--pan-y:${transform.pan_y}"></i></div>
      </div>
    </article>`;
  }

  function trayTemplate() {
    const loose = model.state.plates.filter(plate => model.plates[plate.id].status !== "bound");
    const rows = loose.map(plate => {
      const status = model.plates[plate.id];
      return `<button type="button" class="fpp-loose-plate" data-plate-id="${esc(plate.id)}" data-status="${status.status}">${fragmentSvg(plate, 58)}</button>`;
    }).join("");
    return rows || `<div class="fpp-empty-tray"><span>◌</span></div>`;
  }

  function simplifiedControls() {
    if (interaction() !== "simplified") return "";
    const selected = model.selectedPanel || model.slots[0];
    const currentJoin = model.state.joins[model.stage];
    const visibleTarget = currentJoin?.required_plate_id ? currentJoin.target_panel_id : null;
    const plateRows = model.state.plates.filter(plate => plate.unlock_stage <= model.stage).map(plate => {
      const status = model.plates[plate.id];
      if (status.status === "bound") {
        return `<div class="fpp-proxy-plate">${fragmentSvg(plate, 31)}<button type="button" data-proxy-peel="${esc(plate.id)}" aria-label="Lift fragment">↥</button></div>`;
      }
      return `<div class="fpp-proxy-plate">${fragmentSvg(plate, 31)}${visibleTarget ? `<button type="button" data-proxy-stack="${esc(plate.id)}" data-target-panel="${esc(visibleTarget)}">${slotForPanel(visibleTarget) + 1}</button>` : ""}</div>`;
    }).join("");
    return `<section class="fpp-proxy-controls"><div class="fpp-proxy-panes">${model.slots.map((panelId, index) => `<button type="button" data-select-panel="${esc(panelId)}" aria-pressed="${panelId === selected}">${index + 1}</button>`).join("")}</div><div class="fpp-proxy-grid"><button data-pan="0,-1">↑</button><button data-zoom="1">＋</button><button data-pan="-1,0">←</button><button data-pan="1,0">→</button><button data-zoom="-1">−</button><button data-pan="0,1">↓</button></div><div class="fpp-proxy-slots">${[0, 1, 2, 3].map(slot => `<button type="button" data-move-slot="${slot}">S${slot + 1}</button>`).join("")}</div><div class="fpp-proxy-plates">${plateRows}</div></section>`;
  }

  function updateStateAttributes() {
    const root = document.querySelector(".four-pane-pilgrimage");
    if (!root) return;
    root.dataset.stage = String(model.stage);
    root.dataset.walking = String(model.walking);
  }

  function bindBoard() {
    const root = document.querySelector(".four-pane-pilgrimage");
    if (!root) return;
    root.querySelectorAll(".fpp-pane-grip").forEach(grip => {
      grip.addEventListener("pointerdown", event => {
        if (interaction() !== "full" || model.walking || model.terminal) return;
        event.preventDefault();
        const panelId = grip.dataset.panelId;
        const board = root.querySelector(".fpp-board");
        model.drag = {kind: "panel", panel_id: panelId, pointer_id: event.pointerId, start_slot: slotForPanel(panelId), start_board: normalizedPoint(event, board), trace: [tracePoint(event)]};
        grip.setPointerCapture?.(event.pointerId);
        startGhost(event, `<span class="fpp-ghost-pane">${grip.querySelector(".fpp-pane-sigil")?.textContent || "◇"}</span>`);
      });
    });
    root.querySelectorAll(".fpp-canvas").forEach(canvas => {
      canvas.addEventListener("pointerdown", event => {
        if (interaction() !== "full" || model.walking || model.terminal || event.button !== 0) return;
        event.preventDefault();
        const panelId = canvas.dataset.panelId;
        const transform = model.transforms[panelId];
        model.drag = {kind: "pan", panel_id: panelId, pointer_id: event.pointerId, start_x: event.clientX, start_y: event.clientY, before: [transform.pan_x, transform.pan_y], rect: canvas.getBoundingClientRect(), start_local: normalizedPoint(event, canvas), trace: [tracePoint(event)]};
        canvas.setPointerCapture?.(event.pointerId);
      });
      canvas.addEventListener("wheel", event => {
        if (interaction() !== "full" || model.walking || model.terminal) return;
        event.preventDefault();
        zoomPanel(canvas.dataset.panelId, event.deltaY < 0 ? 1 : -1, {type: "wheel", point: normalizedPoint(event, canvas), delta_y: round(event.deltaY)});
      }, {passive: false});
    });
    root.querySelectorAll(".fpp-bound-plate,.fpp-loose-plate").forEach(node => {
      node.addEventListener("pointerdown", event => {
        if (interaction() !== "full" || model.walking || model.terminal || event.button !== 0) return;
        event.preventDefault(); event.stopPropagation();
        const plateId = node.dataset.plateId;
        const status = model.plates[plateId].status;
        model.drag = {kind: "plate", plate_id: plateId, was_bound: status === "bound", pointer_id: event.pointerId, start_local: normalizedPoint(event, node), trace: [tracePoint(event)]};
        node.setPointerCapture?.(event.pointerId);
        startGhost(event, motifSvg(plateById(plateId).outline, 52));
      });
    });
    bindProxyControls(root);
  }

  function bindProxyControls(root) {
    if (interaction() !== "simplified") return;
    root.querySelectorAll("[data-select-panel]").forEach(button => button.addEventListener("click", () => { model.selectedPanel = button.dataset.selectPanel; paintBoard(); }));
    root.querySelectorAll("[data-move-slot]").forEach(button => button.addEventListener("click", () => movePanel(model.selectedPanel, Number(button.dataset.moveSlot), {type: "button", control: "move_slot", selected_panel_id: model.selectedPanel, value: Number(button.dataset.moveSlot)})));
    root.querySelectorAll("[data-pan]").forEach(button => button.addEventListener("click", () => {
      const [x, y] = button.dataset.pan.split(",").map(Number); panPanel(model.selectedPanel, x * model.state.limits.pan_step, y * model.state.limits.pan_step, null, {type: "button", control: "pan", selected_panel_id: model.selectedPanel, vector: [x, y]});
    }));
    root.querySelectorAll("[data-zoom]").forEach(button => button.addEventListener("click", () => zoomPanel(model.selectedPanel, Number(button.dataset.zoom), {type: "button", control: "zoom", selected_panel_id: model.selectedPanel, direction: Number(button.dataset.zoom)})));
    root.querySelectorAll("[data-proxy-peel]").forEach(button => button.addEventListener("click", () => peelPlate(button.dataset.proxyPeel, {type: "button", control: "peel", plate_id: button.dataset.proxyPeel})));
    root.querySelectorAll("[data-proxy-stack]").forEach(button => button.addEventListener("click", () => {
      const targetPose = model.state.joins[model.stage]?.target_pose;
      stackPlate(button.dataset.proxyStack, button.dataset.targetPanel, targetPose, {type: "button", control: "stack", plate_id: button.dataset.proxyStack, target_panel_id: button.dataset.targetPanel});
    }));
  }

  function startGhost(event, content) {
    const ghost = document.querySelector(".fpp-drag-ghost");
    if (!ghost) return;
    ghost.innerHTML = content; ghost.dataset.visible = "true";
    ghost.style.left = `${event.clientX}px`; ghost.style.top = `${event.clientY}px`;
  }

  function moveGhost(event) {
    const ghost = document.querySelector(".fpp-drag-ghost");
    if (!ghost || ghost.dataset.visible !== "true") return;
    ghost.style.left = `${event.clientX}px`; ghost.style.top = `${event.clientY}px`;
  }

  function hideGhost() {
    const ghost = document.querySelector(".fpp-drag-ghost");
    if (ghost) { ghost.dataset.visible = "false"; ghost.innerHTML = ""; }
  }

  function movePanel(panelId, toSlot, proof = null) {
    if (!panelId || !Number.isInteger(toSlot) || toSlot < 0 || toSlot > 3 || model.walking) return;
    const fromSlot = slotForPanel(panelId);
    if (fromSlot < 0 || fromSlot === toSlot) return;
    const displaced = model.slots[toSlot];
    model.slots[fromSlot] = displaced; model.slots[toSlot] = panelId;
    record("panel_move", {panel_id: panelId, from_slot: fromSlot, to_slot: toSlot, displaced_panel_id: displaced, input_source: inputSource(), interaction_proof: proof});
    paintBoard(); checkProgress();
  }

  function panPanel(panelId, dx, dy, beforeOverride = null, proof = null) {
    if (!panelId || model.walking) return;
    const transform = model.transforms[panelId];
    const before = beforeOverride || [transform.pan_x, transform.pan_y];
    const limit = model.state.limits.pan_limit;
    const after = [round(clamp(before[0] + dx, -limit, limit)), round(clamp(before[1] + dy, -limit, limit))];
    if (after[0] === before[0] && after[1] === before[1]) return;
    transform.pan_x = after[0]; transform.pan_y = after[1];
    record("pan", {panel_id: panelId, before: before.map(round), after, input_source: inputSource(), interaction_proof: proof});
    paintBoard(); checkProgress();
  }

  function zoomPanel(panelId, direction, proof = null) {
    if (!panelId || model.walking) return;
    const transform = model.transforms[panelId];
    const before = transform.zoom;
    const after = round(clamp(before + Math.sign(direction) * model.state.limits.zoom_step, model.state.limits.zoom_min, model.state.limits.zoom_max));
    if (after === before) return;
    transform.zoom = after;
    record("zoom", {panel_id: panelId, before: round(before), after, input_source: inputSource(), interaction_proof: proof});
    paintBoard(); checkProgress();
  }

  function peelPlate(plateId, proof = null) {
    const plate = plateById(plateId), status = model.plates[plateId];
    if (!plate || status?.status !== "bound" || plate.unlock_stage > model.stage) return;
    status.status = "peeled"; status.target_panel_id = null; status.pose = null;
    record("plate_peel", {plate_id: plateId, source_panel_id: plate.source_panel_id, input_source: inputSource(), interaction_proof: proof});
    paintBoard();
  }

  function stackPlate(plateId, targetPanelId, pose, proof = null) {
    const status = model.plates[plateId];
    if (!status || !["peeled", "stacked"].includes(status.status) || !panelById(targetPanelId) || !Array.isArray(pose)) return;
    const boundedPose = [round(clamp(Number(pose[0]), 0, 300)), round(clamp(Number(pose[1]), 0, 200))];
    status.status = "stacked"; status.target_panel_id = targetPanelId; status.pose = boundedPose;
    record("plate_stack", {plate_id: plateId, target_panel_id: targetPanelId, pose: boundedPose, input_source: inputSource(), interaction_proof: proof});
    paintBoard(); checkProgress();
  }

  function checkProgress() {
    if (model.walking || model.terminal) return;
    const result = eligible();
    if (!result.accepted) return;
    const join = model.state.joins[model.stage];
    record("crossing", {stage: model.stage, source_panel_id: join.source_panel_id, target_panel_id: join.target_panel_id, alignment_error: {source: round(result.source), target: round(result.target)}});
    model.stage += 1; model.walking = true;
    paintBoard();
    setTimeout(() => {
      if (!model) return;
      model.walking = false; paintBoard();
      if (model.stage < model.state.joins.length) checkProgress();
    }, 520);
  }

  function currentFinalState() {
    return {
      slots: [...model.slots],
      transforms: Object.fromEntries(Object.entries(model.transforms).map(([panelId, transform]) => [panelId, {zoom: round(transform.zoom), pan_x: round(transform.pan_x), pan_y: round(transform.pan_y)}])),
      stage: model.stage,
      plate_targets: Object.fromEntries(Object.entries(model.plates).filter(([, status]) => status.status === "stacked").map(([plateId, status]) => [plateId, status.target_panel_id])),
      plate_poses: Object.fromEntries(Object.entries(model.plates).filter(([, status]) => status.status === "stacked").map(([plateId, status]) => [plateId, status.pose])),
    };
  }

  async function submit() {
    if (model.submitting || model.terminal || model.walking) return;
    model.submitting = true;
    record("submit", {input_source: "shared_control"});
    const payload = {mechanic_id: model.state.mechanic_id, task_id: model.state.task_id, challenge_id: model.state.challenge_id, interaction_mode: interaction(), events: model.events, final_state: currentFinalState(), completed: model.stage === model.state.joins.length};
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true;
        document.querySelector(".four-pane-pilgrimage")?.insertAdjacentHTML("beforeend", `<div class="fpp-verdict"><strong>PASS</strong></div>`);
        model.helpers.setReadout("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        const root = document.querySelector(".four-pane-pilgrimage");
        root?.setAttribute("data-fresh-failure", "true");
        root?.insertAdjacentHTML("afterbegin", `<div class="fpp-fresh-stamp"><b>FAIL</b></div>`);
        model.helpers.setReadout("FAIL", "error");
        setTimeout(() => {
          document.querySelector(".fpp-fresh-stamp")?.remove();
          if (document.querySelector(".readout")?.textContent?.trim() === "FAIL") {
            model?.helpers?.setReadout("", "idle");
          }
        }, 1700);
      } else {
        model.submitting = false;
        model.helpers.setReadout("FAIL", "error");
      }
    } catch (_error) {
      model.submitting = false;
      model.helpers.setReadout("FAIL", "error");
    }
  }

  function reset() {
    if (model.terminal || model.walking) return;
    record("reset", {input_source: "shared_control"});
    model.slots = [...model.state.initial_slots];
    model.transforms = copy(model.state.initial_transforms);
    model.plates = Object.fromEntries(model.state.plates.map(plate => [plate.id, {status: "bound", target_panel_id: null, pose: null}]));
    model.stage = 0; model.selectedPanel = model.slots[0];
    model.helpers.setReadout("", "idle");
    paintBoard();
  }

  function paintBoard() {
    const board = document.querySelector(".fpp-board");
    const workbench = document.querySelector(".fpp-workbench");
    if (!board || !workbench) return;
    board.innerHTML = model.slots.map((panelId, index) => panelTemplate(panelId, index)).join("");
    workbench.innerHTML = `<div class="fpp-tray-heading"><span>LAYERS</span></div><div class="fpp-layer-tray" data-drop-zone="tray">${trayTemplate()}</div>${simplifiedControls()}`;
    bindBoard(); updateStateAttributes();
  }

  function handlePointerMove(event) {
    if (!model?.drag) return;
    moveGhost(event);
    appendTrace(model.drag, event);
    if (model.drag.kind !== "pan") return;
    const drag = model.drag;
    const transform = model.transforms[drag.panel_id];
    const limit = model.state.limits.pan_limit;
    transform.pan_x = round(clamp(drag.before[0] + (event.clientX - drag.start_x) / drag.rect.width * 300, -limit, limit));
    transform.pan_y = round(clamp(drag.before[1] + (event.clientY - drag.start_y) / drag.rect.height * 200, -limit, limit));
    const group = document.querySelector(`.fpp-canvas[data-panel-id="${CSS.escape(drag.panel_id)}"] > g[clip-path]`);
    if (group) group.setAttribute("transform", transformAttr(transform));
  }

  function handlePointerUp(event) {
    if (!model?.drag) return;
    const drag = model.drag;
    appendTrace(drag, event);
    model.drag = null; hideGhost();
    const target = document.elementFromPoint(event.clientX, event.clientY);
    if (drag.kind === "panel") {
      const slot = target?.closest?.(".fpp-pane-grip")?.closest?.(".fpp-slot");
      if (slot) {
        const board = document.querySelector(".fpp-board");
        movePanel(drag.panel_id, Number(slot.dataset.slot), {type: "header_drag", start_slot: drag.start_slot, end_slot: Number(slot.dataset.slot), start_board: drag.start_board, end_board: normalizedPoint(event, board), trace: drag.trace});
      }
      else paintBoard();
      return;
    }
    if (drag.kind === "pan") {
      const transform = model.transforms[drag.panel_id];
      const after = [transform.pan_x, transform.pan_y];
      transform.pan_x = drag.before[0]; transform.pan_y = drag.before[1];
      const canvas = document.querySelector(`.fpp-canvas[data-panel-id="${CSS.escape(drag.panel_id)}"]`);
      panPanel(drag.panel_id, after[0] - drag.before[0], after[1] - drag.before[1], drag.before, {type: "canvas_drag", start: drag.start_local, end: normalizedPoint(event, canvas), trace: drag.trace});
      return;
    }
    if (drag.kind === "plate") {
      if (drag.was_bound && target?.closest?.(".fpp-layer-tray")) {
        const tray = target.closest(".fpp-layer-tray");
        peelPlate(drag.plate_id, {type: "plate_drag", start_region: "bound_fragment", end_region: "tray", start_local: drag.start_local, end_local: normalizedPoint(event, tray), trace: drag.trace});
      }
      else if (!drag.was_bound) {
        const aperture = target?.closest?.(".fpp-aperture-target");
        const slot = aperture?.closest?.(".fpp-slot");
        if (aperture && slot) {
          const wrap = slot.querySelector(".fpp-canvas-wrap");
          const local = normalizedPoint(event, wrap);
          const pose = [round(local[0] * 300), round(local[1] * 200)];
          stackPlate(drag.plate_id, slot.dataset.panelId, pose, {type: "plate_drag", start_region: "tray_fragment", end_region: "aperture", start_local: drag.start_local, end_local: normalizedPoint(event, aperture), trace: drag.trace, target_plate_id: aperture.dataset.plateTarget});
        }
        else paintBoard();
      } else paintBoard();
    }
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "four-pane-pilgrimage";
    const mode = state?.control_condition?.interaction || "full";
    const palette = state.palette || {};
    const paletteStyle = `--paper:${esc(palette.paper || "#e8dfc7")};--paper-deep:${esc(palette.paper_deep || "#d7c79d")};--ink:${esc(palette.ink || "#172a2b")};--path:${esc(palette.path || "#b8523d")};--wash:${esc(palette.wash || "#658e82")};--gold:${esc(palette.gold || "#c69a4b")};`;
    helpers.app.innerHTML = `<section class="four-pane-pilgrimage" style="${paletteStyle}" data-interaction="${esc(mode)}" data-challenge-id="${esc(state.challenge_id)}"><header class="fpp-head"><div><span>THE ERRANT FOLIO · PLATE IV</span><h1>${esc(state.display_prompt || state.prompt)}</h1></div></header><main class="fpp-stage"><div class="fpp-board"></div><aside class="fpp-workbench"></aside></main><footer class="fpp-foot"><b class="readout" data-status="idle"></b><button type="button" class="fpp-reset" aria-label="Reset">↶</button><button type="button" class="fpp-submit">${esc(state.submit_label)}</button></footer><div class="fpp-drag-ghost" data-visible="false"></div>${helpers.cheatPanelTemplate()}</section>`;
    model = {state, helpers, slots: [...state.initial_slots], transforms: copy(state.initial_transforms), plates: Object.fromEntries(state.plates.map(plate => [plate.id, {status: "bound", target_panel_id: null, pose: null}])), events: [], stage: 0, walking: false, selectedPanel: state.initial_slots[0], drag: null, submitting: false, terminal: false};
    window.fourPanePilgrimageModel = model;
    const root = document.querySelector(".four-pane-pilgrimage");
    root.addEventListener("pointermove", handlePointerMove);
    root.addEventListener("pointerup", handlePointerUp);
    root.addEventListener("pointercancel", handlePointerUp);
    root.querySelector(".fpp-reset").addEventListener("click", reset);
    root.querySelector(".fpp-submit").addEventListener("click", submit);
    helpers.installCheatPanel();
    paintBoard();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {rootSelector: ".four-pane-pilgrimage", render};
})();
