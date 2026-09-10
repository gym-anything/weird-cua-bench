(() => {
  "use strict";
  let model = null;
  const VIEWS = ["overhead", "front", "side"];
  const AXIS = {x: 0, y: 1, z: 2};
  const clean = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const round = (value) => Math.round(Number(value) * 10000) / 10000;
  const clone = (value) => JSON.parse(JSON.stringify(value));
  function record(kind, details = {}) {
    const event = {sequence: model.events.length + 1, kind, ...details};
    model.events.push(event);
    return event;
  }
  function clearFresh() {
    const root = document.querySelector(".survey-captcha");
    const wasFresh = root?.dataset.freshFailure === "true";
    document.querySelector(".survey-fresh")?.remove();
    root?.removeAttribute("data-fresh-failure");
    if (wasFresh && model && !model.terminal) setMessage("FRESH DEPOT PLATE ACTIVE · FIT THE REQUESTED CUBOIDS");
  }
  function setMessage(message, status = "idle") { model.helpers.setReadout(message, status); }
  function normalizeBox(box) {
    return {
      center: box.center.map(round),
      half: box.half.map((value) => round(Math.max(0.18, Math.min(1.1, value)))),
      yaw: round(box.yaw),
    };
  }
  function corners(box) {
    const angle = Number(box.yaw) * Math.PI / 180, cosine = Math.cos(angle), sine = Math.sin(angle);
    const result = [];
    for (const sx of [-1, 1]) for (const sy of [-1, 1]) for (const sz of [-1, 1]) {
      const lx = sx * box.half[0], lz = sz * box.half[2];
      result.push([box.center[0] + lx * cosine - lz * sine, box.center[1] + sy * box.half[1], box.center[2] + lx * sine + lz * cosine]);
    }
    return result;
  }
  function projectCamera(view, point, bias) {
    const axes = {x: 0, y: 1, z: 2};
    return [
      Number(view.origin[0]) + Number(bias[0]) + Number(view.scale) * Number(view.signs[0]) * point[axes[view.axes[0]]],
      Number(view.origin[1]) + Number(bias[1]) + Number(view.scale) * Number(view.signs[1]) * point[axes[view.axes[1]]],
    ];
  }
  function cloudPoint(point) {
    const angle = model.orbit * Math.PI / 180, cosine = Math.cos(angle), sine = Math.sin(angle);
    const horizontal = point[0] * cosine - point[2] * sine;
    const depth = point[0] * sine + point[2] * cosine;
    return [260 + horizontal * 52 * model.zoom + model.panX, 320 + (-point[1] * 48 + depth * 8) * model.zoom + model.panY];
  }
  function cloudHandles(targetId) {
    const box = model.annotations[targetId];
    if (!box) return null;
    const points = corners(box).map(cloudPoint);
    const xs = points.map((point) => point[0]), ys = points.map((point) => point[1]);
    const left = Math.min(...xs), right = Math.max(...xs), top = Math.min(...ys), bottom = Math.max(...ys);
    const center = [(left + right) / 2, (top + bottom) / 2];
    return {left, right, top, bottom, center, cy: [left - 18, top - 18], hy: [right + 18, top - 18], hx: [right + 18, center[1]], hz: [center[0], bottom + 18], yaw: [center[0], bottom + 42]};
  }
  function cloudCanvasPoint(canvas, event) {
    const rect = canvas.getBoundingClientRect();
    return [(event.clientX - rect.left) / rect.width * canvas.width, (event.clientY - rect.top) / rect.height * canvas.height];
  }
  function near(a, b, radius = 13) { return Math.hypot(a[0] - b[0], a[1] - b[1]) <= radius; }
  function cloudPointerDown(event) {
    if (model.interaction !== "full" || model.terminal || model.submitting) return;
    clearFresh();
    const canvas = event.currentTarget, point = cloudCanvasPoint(canvas, event), handles = cloudHandles(model.selectedTarget);
    let kind = event.shiftKey ? "pan" : "orbit";
    if (!event.shiftKey && handles) {
      if (near(point, handles.yaw)) kind = "yaw";
      else if (near(point, handles.cy)) kind = "cy";
      else if (near(point, handles.hy)) kind = "hy";
      else if (near(point, handles.hx)) kind = "hx";
      else if (near(point, handles.hz)) kind = "hz";
      else if (point[0] >= handles.left - 10 && point[0] <= handles.right + 10 && point[1] >= handles.top - 10 && point[1] <= handles.bottom + 10) kind = "center";
    }
    model.drag = {kind, targetId: model.selectedTarget, start: point, current: point, startBox: clone(model.annotations[model.selectedTarget]), startPanX: model.panX, startPanY: model.panY};
    canvas.setPointerCapture?.(event.pointerId);
    canvas.dataset.dragging = "true";
  }
  function cloudPointerMove(event) {
    if (!model.drag) return;
    const point = cloudCanvasPoint(event.currentTarget, event), drag = model.drag;
    drag.current = point;
    const dx = point[0] - drag.start[0], dy = point[1] - drag.start[1];
    if (drag.kind === "orbit") model.orbit = (model.orbit + dx / 1.7) % 360;
    else if (drag.kind === "pan") {
      model.panX = Math.max(-150, Math.min(150, dx + (drag.startPanX || 0)));
      model.panY = Math.max(-110, Math.min(110, dy + (drag.startPanY || 0)));
    } else {
      const box = clone(drag.startBox);
      if (drag.kind === "center") { box.center[0] += dx / 52; box.center[2] -= dy / 42; }
      if (drag.kind === "cy") box.center[1] -= dy / 42;
      if (drag.kind === "hx") box.half[0] += dx / 80;
      if (drag.kind === "hy") box.half[1] -= dy / 80;
      if (drag.kind === "hz") box.half[2] += dx / 80;
      if (drag.kind === "yaw") box.yaw += dx * .5;
      model.annotations[drag.targetId] = normalizeBox(box);
    }
    drawCloud(); updateHUD();
  }
  function cloudPointerUp(event) {
    if (!model.drag) return;
    const drag = model.drag;
    if (drag.kind === "orbit") {
      record("orbit", {delta: round(drag.current[0] - drag.start[0]), input_source: "direct_drag"});
      setMessage("POINT CLOUD ORBIT UPDATED · RECHECK DEPTH AGAINST THE CAMERAS");
    } else if (drag.kind === "pan") {
      record("pan", {delta_x: round(drag.current[0] - drag.start[0]), delta_y: round(drag.current[1] - drag.start[1]), input_source: "direct_drag"});
      setMessage("POINT CLOUD PAN UPDATED · KEEP THE ACTIVE CUBOID IN VIEW");
    } else if (drag.kind === "center") {
      const before = drag.startBox, after = model.annotations[drag.targetId];
      const deltaX = round(after.center[0] - before.center[0]), deltaZ = round(after.center[2] - before.center[2]);
      if (Math.abs(deltaX) > .0001) record("adjust_box", {target_id: drag.targetId, field: "cx", delta: deltaX, input_source: "direct_drag"});
      if (Math.abs(deltaZ) > .0001) record("adjust_box", {target_id: drag.targetId, field: "cz", delta: deltaZ, input_source: "direct_drag"});
      setMessage(`DIRECT CUBOID MOVE · X ${deltaX >= 0 ? "+" : ""}${deltaX} · Z ${deltaZ >= 0 ? "+" : ""}${deltaZ}`);
    } else {
      const field = {center: "cx", cy: "cy", hx: "hx", hy: "hy", hz: "hz", yaw: "yaw"}[drag.kind];
      const before = drag.startBox, after = model.annotations[drag.targetId];
      const beforeValue = field === "cx" ? before.center[0] : field === "cy" ? before.center[1] : field === "cz" ? before.center[2] : field === "hx" ? before.half[0] : field === "hy" ? before.half[1] : field === "hz" ? before.half[2] : before.yaw;
      const afterValue = field === "cx" ? after.center[0] : field === "cy" ? after.center[1] : field === "cz" ? after.center[2] : field === "hx" ? after.half[0] : field === "hy" ? after.half[1] : field === "hz" ? after.half[2] : after.yaw;
      const delta = round(afterValue - beforeValue);
      if (Math.abs(delta) > .0001) record("adjust_box", {target_id: drag.targetId, field, delta, input_source: "direct_drag"});
      setMessage(`DIRECT CUBOID EDIT · ${field.toUpperCase()} ${delta >= 0 ? "+" : ""}${delta}`);
    }
    model.drag = null; event.currentTarget.releasePointerCapture?.(event.pointerId); event.currentTarget.dataset.dragging = "false";
  }
  function viewAction(action) {
    if (!model || model.terminal || model.submitting) return;
    clearFresh();
    const source = model.interaction === "full" ? "direct_drag" : "proxy_controls";
    if (action === "zoom-in" || action === "zoom-out") {
      const delta = action === "zoom-in" ? 0.1 : -0.1;
      model.zoom = Math.max(0.7, Math.min(1.5, round(model.zoom + delta)));
      record("zoom", {delta: round(delta), input_source: source});
      setMessage(`POINT CLOUD ZOOM ${Math.round(model.zoom * 100)}%`);
    } else {
      const deltas = {"pan-left": [-28, 0], "pan-right": [28, 0], "pan-up": [0, -24], "pan-down": [0, 24]};
      const [deltaX, deltaY] = deltas[action] || [0, 0];
      model.panX = Math.max(-150, Math.min(150, model.panX + deltaX));
      model.panY = Math.max(-110, Math.min(110, model.panY + deltaY));
      record("pan", {delta_x: deltaX, delta_y: deltaY, input_source: source});
      setMessage("POINT CLOUD PAN UPDATED · KEEP THE ACTIVE CUBOID IN VIEW");
    }
    drawCloud();
  }
  function adjust(field, delta) {
    if (model.interaction !== "simplified" || !model.selectedTarget || model.terminal || model.submitting) return;
    clearFresh();
    const box = model.annotations[model.selectedTarget];
    if (field === "cx") box.center[0] += delta;
    else if (field === "cy") box.center[1] += delta;
    else if (field === "cz") box.center[2] += delta;
    else if (field === "hx") box.half[0] += delta;
    else if (field === "hy") box.half[1] += delta;
    else if (field === "hz") box.half[2] += delta;
    else if (field === "yaw") box.yaw += delta;
    model.annotations[model.selectedTarget] = normalizeBox(box);
    record("adjust_box", {target_id: model.selectedTarget, field, delta: round(delta), input_source: "proxy_controls"});
    drawCloud(); updateHUD(); setMessage(`PROXY CUBOID EDIT · ${field.toUpperCase()} ${delta >= 0 ? "+" : ""}${delta}`);
  }
  function selectTarget(targetId) {
    if (!model.annotations[targetId]) return;
    model.selectedTarget = targetId; model.pendingMark = null; drawCloud(); drawCameras(); updateHUD();
    setMessage(`ACTIVE CUBOID ${targetId.toUpperCase()} · MATCH ITS SCAN CLUSTER TO THE PHOTOGRAPHS`);
  }
  function selectFrame(frame) {
    frame = Number(frame);
    if (!Number.isInteger(frame) || frame < 0 || frame >= model.state.camera_frames.length) return;
    clearFresh(); model.frame = frame; model.pendingMark = null; record("frame_select", {frame}); renderMarkProxies(); drawCameras(); updateHUD();
    setMessage(`SYNCHRONIZED FRAME ${frame + 1} · COMPARE ALL THREE CAMERA PROJECTIONS`);
  }
  function selectMark(viewId, markId, inputSource) {
    const frame = model.state.camera_frames[model.frame], marks = frame.views[viewId]?.marks || [];
    if (!marks.some((mark) => mark.id === markId)) return;
    model.pendingMark = {frame: model.frame, view: viewId, mark_id: markId};
    drawCameras(); updateHUD(); setMessage(`MARK SELECTED · LINK IT TO ${model.selectedTarget.toUpperCase()}`);
  }
  function linkSelected() {
    if (!model.selectedTarget || !model.pendingMark || model.terminal || model.submitting) return;
    clearFresh();
    const mark = model.pendingMark;
    const inputSource = model.interaction === "full" ? "direct_mark" : "proxy_controls";
    record("link", {target_id: model.selectedTarget, frame: mark.frame, view: mark.view, mark_id: mark.mark_id, input_source: inputSource});
    model.links[`${mark.frame}:${mark.view}:${model.selectedTarget}`] = mark.mark_id;
    setMessage(`LINK RECORDED · ${mark.view.toUpperCase()} FRAME ${mark.frame + 1} → ${model.selectedTarget.toUpperCase()}`, "pending");
    updateHUD(); drawCameras();
  }
  function drawCloud() {
    const canvas = document.querySelector(".survey-cloud"), ctx = canvas?.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height); gradient.addColorStop(0, "#152b32"); gradient.addColorStop(1, "#071216"); ctx.fillStyle = gradient; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#83d9ca28"; ctx.lineWidth = 1;
    for (let x = 28; x < canvas.width; x += 44) { ctx.beginPath(); ctx.moveTo(x, 18); ctx.lineTo(x, canvas.height - 18); ctx.stroke(); }
    for (let y = 34; y < canvas.height; y += 42) { ctx.beginPath(); ctx.moveTo(18, y); ctx.lineTo(canvas.width - 18, y); ctx.stroke(); }
    ctx.strokeStyle = "#d9f8e733"; ctx.setLineDash([5, 5]); ctx.beginPath(); ctx.moveTo(18, 320); ctx.lineTo(canvas.width - 18, 320); ctx.stroke(); ctx.setLineDash([]);
    for (const point of model.state.point_cloud) {
      const [x, y] = cloudPoint([point.x, point.y, point.z]); ctx.fillStyle = point.color || "#9bad9f"; ctx.globalAlpha = .88; ctx.beginPath(); ctx.arc(x, y, model.state.world.point_radius, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;
    for (const target of model.state.targets) {
      const box = model.annotations[target.id], handles = cloudHandles(target.id); if (!box || !handles) continue;
      const active = target.id === model.selectedTarget; ctx.strokeStyle = active ? "#fff8d8" : `${target.color}99`; ctx.lineWidth = active ? 2.5 : 1.2; ctx.setLineDash(active ? [] : [4, 5]); ctx.strokeRect(handles.left, handles.top, handles.right - handles.left, handles.bottom - handles.top); ctx.setLineDash([]);
      ctx.fillStyle = target.color; ctx.font = "700 12px ui-monospace"; ctx.fillText(target.glyph, handles.left + 4, handles.top - 5);
      if (active) {
        for (const key of ["cy", "hy", "hx", "hz"]) { const p = handles[key]; ctx.fillStyle = "#fff8d8"; ctx.fillRect(p[0] - 5, p[1] - 5, 10, 10); }
        ctx.strokeStyle = "#ffbd63"; ctx.beginPath(); ctx.arc(handles.yaw[0], handles.yaw[1], 8, 0, Math.PI * 2); ctx.stroke(); ctx.fillStyle = "#ffbd63"; ctx.font = "700 9px ui-monospace"; ctx.fillText("↻", handles.yaw[0] - 4, handles.yaw[1] + 3);
      }
    }
    ctx.fillStyle = "#d8f4e9"; ctx.font = "700 11px ui-monospace"; ctx.fillText(`SCAN POINTS ${model.state.point_cloud.length} · ORBIT ${Math.round(model.orbit)}°`, 16, 17);
  }
  function drawCamera(viewId) {
    const canvas = document.querySelector(`.survey-camera[data-view="${viewId}"]`), ctx = canvas?.getContext("2d"); if (!ctx) return;
    const view = model.state.camera_frames[model.frame].views[viewId]; ctx.clearRect(0, 0, canvas.width, canvas.height);
    const gradient = ctx.createLinearGradient(0, 0, canvas.width, canvas.height); gradient.addColorStop(0, model.state.palette.paper); gradient.addColorStop(1, "#bdc9bf"); ctx.fillStyle = gradient; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#2b554f35"; ctx.lineWidth = 1;
    for (let x = 12; x < canvas.width; x += 28) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke(); }
    for (let y = 12; y < canvas.height; y += 28) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke(); }
    ctx.strokeStyle = "#18383288"; ctx.beginPath(); ctx.moveTo(0, canvas.height - 32); ctx.lineTo(canvas.width, canvas.height - 32); ctx.stroke();
    const calibration = model.state.views[viewId], bias = view.bias || [0, 0];
    const sceneObjects = view.scene_objects || [];
    sceneObjects.forEach((subject) => {
      const r = subject.rect, inset = Math.max(1, Math.min(5, Math.min(r.w, r.h) * 0.12));
      const x = r.x + inset, y = r.y + inset, w = Math.max(5, r.w - inset * 2), h = Math.max(6, r.h - inset * 2);
      ctx.save();
      ctx.fillStyle = subject.tone || "#718079"; ctx.strokeStyle = "#314c49"; ctx.lineWidth = 1.2;
      ctx.beginPath();
      if (subject.style === "drum") {
        ctx.ellipse(x + w / 2, y + h / 2, Math.max(3, w / 2), Math.max(4, h / 2), 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        ctx.strokeStyle = subject.accent || "#c8b88d"; ctx.beginPath(); ctx.ellipse(x + w / 2, y + h * 0.35, Math.max(2, w * .36), Math.max(2, h * .12), 0, 0, Math.PI * 2); ctx.stroke();
      } else if (subject.style === "van" || subject.style === "rover") {
        ctx.roundRect(x, y + h * .2, w, h * .8, 3); ctx.fill(); ctx.stroke();
        ctx.fillStyle = subject.accent || "#b9c9bb"; ctx.fillRect(x + w * .12, y + h * .3, w * .48, h * .25);
        ctx.fillStyle = "#263f43"; ctx.beginPath(); ctx.arc(x + w * .24, y + h * .92, Math.max(2, h * .08), 0, Math.PI * 2); ctx.fill(); ctx.beginPath(); ctx.arc(x + w * .78, y + h * .92, Math.max(2, h * .08), 0, Math.PI * 2); ctx.fill();
      } else if (subject.style === "pallet") {
        ctx.fillRect(x, y + h * .28, w, h * .72); ctx.strokeRect(x, y + h * .28, w, h * .72);
        ctx.strokeStyle = subject.accent || "#c8b88d"; for (let beam = 1; beam < 4; beam += 1) { ctx.beginPath(); ctx.moveTo(x + w * beam / 4, y + h * .35); ctx.lineTo(x + w * beam / 4, y + h * .92); ctx.stroke(); }
      } else {
        ctx.roundRect(x, y, w, h, 2); ctx.fill(); ctx.stroke();
        ctx.fillStyle = subject.accent || "#d1b27b"; ctx.fillRect(x + w * .12, y + h * .18, w * .7, Math.max(2, h * .12));
      }
      ctx.restore();
    });
    for (const target of model.state.targets) {
      const projected = corners(model.annotations[target.id]).map((point) => projectCamera(calibration, point, bias));
      const xs = projected.map((point) => point[0]), ys = projected.map((point) => point[1]);
      const left = Math.min(...xs), right = Math.max(...xs), top = Math.min(...ys), bottom = Math.max(...ys);
      ctx.strokeStyle = target.id === model.selectedTarget ? "#fff8d8aa" : `${target.color}55`; ctx.lineWidth = target.id === model.selectedTarget ? 2 : 1; ctx.setLineDash([4, 3]); ctx.strokeRect(left, top, right - left, bottom - top); ctx.setLineDash([]);
    }
    const marks = view.marks || [];
    marks.forEach((mark, index) => {
      const r = mark.rect, selected = model.pendingMark && model.pendingMark.frame === model.frame && model.pendingMark.view === viewId && model.pendingMark.mark_id === mark.id;
      ctx.fillStyle = selected ? "#fff8d866" : "#ed815e22"; ctx.strokeStyle = selected ? "#fff" : "#ed815e"; ctx.lineWidth = selected ? 3 : 1.4; ctx.setLineDash(selected ? [] : [5, 3]); ctx.fillRect(r.x, r.y, r.w, r.h); ctx.strokeRect(r.x, r.y, r.w, r.h); ctx.setLineDash([]);
      ctx.fillStyle = selected ? "#fff" : "#8f3f2c"; ctx.font = "700 10px ui-monospace"; ctx.fillText(`M${index + 1}`, Math.max(3, r.x + 3), Math.max(11, r.y + 11));
    });
    ctx.fillStyle = model.state.palette.ink; ctx.font = "700 10px ui-monospace"; ctx.fillText(`${view.label} · FRAME ${model.frame + 1}`, 9, 15);
  }
  function drawCameras() { VIEWS.forEach(drawCamera); document.querySelectorAll(".survey-frame").forEach((button) => button.dataset.active = Number(button.dataset.frame) === model.frame ? "true" : "false"); }
  function renderMarkProxies() {
    if (model.interaction !== "simplified") return;
    for (const viewId of VIEWS) {
      const holder = document.querySelector(`.survey-mark-proxies[data-view="${viewId}"]`); if (!holder) continue;
      const marks = model.state.camera_frames[model.frame].views[viewId].marks || [];
      holder.innerHTML = marks.map((mark, index) => `<button type="button" class="survey-mark-choice" data-view="${viewId}" data-mark-id="${clean(mark.id)}"><i style="--swatch:${clean(mark.color)}"></i>M${index + 1}</button>`).join("");
      holder.querySelectorAll("button").forEach((node) => node.addEventListener("click", () => selectMark(node.dataset.view, node.dataset.markId, "proxy_controls")));
    }
  }
  function updateHUD() {
    const total = model.state.requirements.required_links, done = Object.keys(model.links).length;
    const links = document.querySelector(".survey-links"); if (links) links.textContent = `${done}/${total}`;
    const active = document.querySelector(".survey-active-target"); if (active) active.textContent = model.selectedTarget ? model.selectedTarget.toUpperCase() : "—";
    const box = model.selectedTarget ? model.annotations[model.selectedTarget] : null;
    const boxText = document.querySelector(".survey-box-readout"); if (boxText && box) boxText.textContent = `C ${box.center.map((v) => v.toFixed(2)).join("/")} · H ${box.half.map((v) => v.toFixed(2)).join("/")} · YAW ${box.yaw.toFixed(1)}°`;
    document.querySelectorAll(".survey-target").forEach((node) => node.dataset.active = node.dataset.targetId === model.selectedTarget ? "true" : "false");
  }
  async function submit() {
    if (model.submitting || model.terminal) return;
    model.submitting = true; setMessage("REPLAYING ORIENTED VOLUMES AND CROSS-VIEW LINKS…", "pending");
    const payload = {mechanic_id: model.state.mechanic_id, task_id: model.state.task_id, challenge_id: model.state.challenge_id, interaction_mode: model.interaction, annotations: model.annotations, links: model.links, events: model.events};
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)}), outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true; document.querySelector(".survey-captcha").insertAdjacentHTML("beforeend", '<div class="survey-verdict"><small>CROSS-MODAL DEPOT INSPECTION VERIFIED</small><strong>PASS</strong><span>3D VOLUME · PHOTO LINKING · OBJECT IDENTITY</span></div>'); setMessage("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state); const root = document.querySelector(".survey-captcha"); root.dataset.freshFailure = "true"; root.insertAdjacentHTML("afterbegin", '<div class="survey-fresh"><b>FAIL</b><span>REPORT REJECTED · FRESH DEPOT PLATE ISSUED</span></div>'); setMessage("FAIL · FRESH SURVEY PLATE ISSUED", "error"); setTimeout(clearFresh, 2200);
      } else { model.submitting = false; setMessage("FAIL · NO AUTHORITATIVE SURVEY GRADE", "error"); }
    } catch (_) { model.submitting = false; setMessage("FAIL · SURVEY VERIFIER OFFLINE", "error"); }
  }
  async function render(state, helpers) {
    document.body.dataset.mechanic = "surveyors-toybox";
    const interaction = state.control_condition?.interaction || "full";
    if (!["simplified", "full"].includes(interaction)) throw new Error("Surveyor's Toybox interaction is invalid");
    const viewTools = `<div class="survey-view-tools"><b>VIEW</b><button type="button" class="survey-view-tool" data-view-action="zoom-out">− ZOOM</button><button type="button" class="survey-view-tool" data-view-action="zoom-in">+ ZOOM</button><button type="button" class="survey-view-tool" data-view-action="pan-left">← PAN</button><button type="button" class="survey-view-tool" data-view-action="pan-right">PAN →</button><button type="button" class="survey-view-tool" data-view-action="pan-up">↑</button><button type="button" class="survey-view-tool" data-view-action="pan-down">↓</button></div>`;
    const proxy = interaction === "simplified" ? `<section class="survey-proxy"><b>PROXY BOX CONTROLS</b>${viewTools}<div class="survey-control-grid"><span>POSITION</span><button data-field="cx" data-delta="-0.1">X−</button><button data-field="cx" data-delta="0.1">X+</button><button data-field="cy" data-delta="0.1">Y+</button><button data-field="cy" data-delta="-0.1">Y−</button><button data-field="cz" data-delta="-0.1">Z−</button><button data-field="cz" data-delta="0.1">Z+</button><span>EXTENT</span><button data-field="hx" data-delta="-0.05">W−</button><button data-field="hx" data-delta="0.05">W+</button><button data-field="hy" data-delta="-0.05">H−</button><button data-field="hy" data-delta="0.05">H+</button><button data-field="hz" data-delta="-0.05">D−</button><button data-field="hz" data-delta="0.05">D+</button><span>HEADING</span><button data-field="yaw" data-delta="-5">↶ 5°</button><button data-field="yaw" data-delta="5">↷ 5°</button></div></section>` : `<section class="survey-direct"><b>DIRECT 3D HANDLE MANIPULATION</b><span>MOVE = box center · LIFT = top-left · HEIGHT = top-right</span><span>WIDTH = right · DEPTH = bottom · HEADING = ring · drag background to orbit</span>${viewTools}<small>SHIFT + DRAG BACKGROUND = PAN</small></section>`;
    const targets = state.targets.map((target) => `<button class="survey-target" type="button" data-target-id="${clean(target.id)}"><i style="--swatch:${clean(target.color)}">${clean(target.glyph)}</i><span><b>${clean(target.label)}</b><small>${clean(target.id)} · requested cuboid</small></span></button>`).join("");
    const frames = state.camera_frames.map((frame) => `<button class="survey-frame" type="button" data-frame="${frame.frame_index}">${clean(frame.label)}</button>`).join("");
    const cameras = VIEWS.map((viewId) => `<article class="survey-camera-card"><header><b>${clean(state.views[viewId].label)}</b><span class="survey-camera-status" data-view="${viewId}">SYNC IMAGE</span></header><canvas class="survey-camera" data-view="${viewId}" width="340" height="230"></canvas>${interaction === "simplified" ? `<div class="survey-mark-proxies" data-view="${viewId}"></div>` : ""}</article>`).join("");
    helpers.app.innerHTML = `<section class="survey-captcha" data-interaction="${clean(interaction)}" data-challenge-id="${clean(state.challenge_id)}"><header class="survey-head"><div><span>FIELD NOTE 088 / CROSS-MODAL TOY DEPOT</span><h1>${clean(state.prompt)}</h1></div><p>POINT CLOUD + CALIBRATED IMAGES<br><b>FIT VOLUME · LINK IDENTITY</b></p></header><main class="survey-main"><section class="survey-scan"><div class="survey-panel-title"><b>ROTATABLE LIDAR SCAN</b><span>SPARSE SURFACE RETURNS</span></div><canvas class="survey-cloud" width="520" height="380"></canvas><div class="survey-cloud-legend"><span>● scan return</span><span>□ active cuboid</span><span>↻ orbit · pan · zoom</span></div><div class="survey-target-list"><b class="survey-section-label">REQUESTED OBJECTS</b>${targets}</div>${proxy}<div class="survey-box-readout"></div></section><section class="survey-evidence"><div class="survey-panel-title"><b>SYNCHRONIZED CAMERA IMAGES</b><span>3 VIEWS / ${state.camera_frames.length} FRAME${state.camera_frames.length === 1 ? "" : "S"}</span></div><div class="survey-frame-tabs">${frames}</div><div class="survey-camera-grid">${cameras}</div><div class="survey-linkbar"><div><span>ACTIVE CUBOID</span><b class="survey-active-target">—</b><small>select a target, then a camera mark</small></div><button type="button" class="survey-link-button">LINK SELECTED MARK → BOX</button><div><span>LINKS</span><b class="survey-links">0/${state.requirements.required_links}</b><small>every view in every frame</small></div></div>${interaction === "full" ? '<div class="survey-note">Match each neutral mark to the same physical subject in the scan and all three calibrated projections.</div>' : '<div class="survey-note">Proxy controls change the same annotation fields; neutral image marks must still be matched to the same depot subjects.</div>'}</section></main><footer class="survey-foot"><div><span>${interaction === "full" ? "FULL INPUT SURFACE · DIRECT POINTER" : "SIMPLIFIED INPUT SURFACE · PROXY CONTROLS"}</span><div class="readout" data-status="idle">SELECT A REQUESTED OBJECT TO BEGIN</div></div><button type="button" class="survey-submit">${clean(state.submit_label)}</button></footer>${helpers.cheatPanelTemplate()}</section>`;
    model = {state, helpers, interaction, annotations: clone(state.initial_annotations), links: {}, events: [], selectedTarget: state.targets[0]?.id || null, pendingMark: null, frame: 0, orbit: 0, panX: 0, panY: 0, zoom: 1, drag: null, terminal: false, submitting: false};
    model.cloudHandles = (targetId) => cloudHandles(targetId);
    window.surveyorsToyboxModel = model;
    document.querySelectorAll(".survey-target").forEach((node) => node.addEventListener("click", () => selectTarget(node.dataset.targetId)));
    document.querySelectorAll(".survey-frame").forEach((node) => node.addEventListener("click", () => selectFrame(node.dataset.frame)));
    document.querySelectorAll(".survey-control-grid button").forEach((node) => node.addEventListener("click", () => adjust(node.dataset.field, Number(node.dataset.delta))));
    document.querySelectorAll(".survey-view-tool").forEach((node) => node.addEventListener("click", () => viewAction(node.dataset.viewAction)));
    document.querySelector(".survey-link-button")?.addEventListener("click", linkSelected);
    const cloud = document.querySelector(".survey-cloud"); cloud?.addEventListener("pointerdown", cloudPointerDown); cloud?.addEventListener("pointermove", cloudPointerMove); cloud?.addEventListener("pointerup", cloudPointerUp); cloud?.addEventListener("pointercancel", cloudPointerUp); cloud?.addEventListener("wheel", (event) => { event.preventDefault(); viewAction(event.deltaY < 0 ? "zoom-in" : "zoom-out"); }, {passive: false});
    document.querySelectorAll(".survey-camera").forEach((canvas) => canvas.addEventListener("click", (event) => {
      const rect = canvas.getBoundingClientRect(), x = (event.clientX - rect.left) / rect.width * canvas.width, y = (event.clientY - rect.top) / rect.height * canvas.height;
      const marks = model.state.camera_frames[model.frame].views[canvas.dataset.view].marks || [];
      const candidates = marks.filter((mark) => { const r = mark.rect; return x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h; });
      if (candidates.length) {
        candidates.sort((first, second) => {
          const firstR = first.rect, secondR = second.rect;
          const firstDistance = Math.hypot(x - (firstR.x + firstR.w / 2), y - (firstR.y + firstR.h / 2));
          const secondDistance = Math.hypot(x - (secondR.x + secondR.w / 2), y - (secondR.y + secondR.h / 2));
          return firstDistance - secondDistance;
        });
        selectMark(canvas.dataset.view, candidates[0].id, "direct_mark"); return;
      }
    }));
    renderMarkProxies();
    document.querySelector(".survey-submit").addEventListener("click", submit);
    helpers.installCheatPanel(); drawCloud(); drawCameras(); updateHUD();
  }
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.surveyors_toybox = {rootSelector: ".survey-captcha", render};
})();
