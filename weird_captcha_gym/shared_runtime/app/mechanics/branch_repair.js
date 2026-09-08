(function () {
  "use strict";

  const VIEWS = ["xy", "xz", "yz"];
  const AXES = {xy: [0, 1, 2], xz: [0, 2, 1], yz: [1, 2, 0]};
  const AXIS_INDEX = {x: 0, y: 1, z: 2};
  const esc = (value) => String(value == null ? "" : value).replace(/[&<>\"']/g, (ch) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"}[ch]));
  const round = (value) => {
    const result = Math.round(Number(value) * 1000) / 1000;
    return Object.is(result, -0) ? 0 : result;
  };
  const edgeKey = (a, b) => String(a) < String(b) ? `${a}|${b}` : `${b}|${a}`;
  const pair = (key) => key.split("|");

  function records(state, focus, view) {
    const axes = AXES[view];
    const count = Number(state.slice_contract.index_count || 1);
    const level = -4 + 8 * Number(focus[axes[2]]) / Math.max(1, count - 1);
    return (state.nodes || []).filter((node) => Math.abs(Number(node.p[axes[2]]) - level) <= 0.72)
      .map((node) => ({id: node.id, u: round(node.p[axes[0]]), v: round(node.p[axes[1]])}))
      .sort((a, b) => a.id.localeCompare(b.id));
  }

  function digestFor(state, focus) {
    return VIEWS.map((view) => `${view}=${records(state, focus, view).map((item) => `${item.id}:${Number(item.u).toFixed(3)}:${Number(item.v).toFixed(3)}`).join("|")}`).join(";");
  }

  function topologyDigestFor(state, focus, viewEdges) {
    return VIEWS.map((view) => {
      const visible = new Set(records(state, focus, view).map((item) => item.id));
      const edges = Array.from(viewEdges).filter((key) => {
        const [left, right] = pair(key);
        return visible.has(left) && visible.has(right);
      }).sort();
      return `${view}=${edges.join(",")}`;
    }).join(";");
  }

  function colourIndex(identifier, size) {
    let value = 0;
    for (const character of String(identifier)) value = (value * 31 + character.charCodeAt(0)) >>> 0;
    return value % Math.max(1, size);
  }

  function project(point, yaw, pitch) {
    const x = Number(point[0]);
    const y = Number(point[1]);
    const z = Number(point[2]);
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    const rx = cy * x + sy * z;
    const rz = -sy * x + cy * z;
    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    const ry = cp * y - sp * rz;
    return [round(360 + rx * 34), round(145 - ry * 34)];
  }

  function screenFor(state, view, record) {
    const spec = state.views[view] || {};
    return [round(Number(spec.width || 230) / 2 + Number(record.u) * Number(spec.scale || 24)), round(Number(spec.height || 154) / 2 - Number(record.v) * Number(spec.scale || 24))];
  }

  function component(edges, start) {
    const graph = new Map();
    edges.forEach((key) => {
      const [a, b] = pair(key);
      if (!graph.has(a)) graph.set(a, new Set());
      if (!graph.has(b)) graph.set(b, new Set());
      graph.get(a).add(b); graph.get(b).add(a);
    });
    const seen = new Set([start]);
    const pending = [start];
    while (pending.length) {
      const current = pending.pop();
      (graph.get(current) || []).forEach((next) => {
        if (!seen.has(next)) { seen.add(next); pending.push(next); }
      });
    }
    return seen;
  }

  function nearestMesh(model, x, y) {
    let result = null;
    (model.state.nodes || []).forEach((node) => {
      const point = project(node.p, model.yaw, model.pitch);
      const distance = Math.hypot(point[0] - x, point[1] - y);
      if (distance <= 23 && (!result || distance < result.distance)) result = {id: node.id, point, distance};
    });
    return result;
  }

  function nearestSlice(model, view, x, y) {
    let result = null;
    records(model.state, model.focus, view).forEach((record) => {
      const point = screenFor(model.state, view, record);
      const distance = Math.hypot(point[0] - x, point[1] - y);
      if (distance <= 20 && (!result || distance < result.distance)) result = {record, point, distance};
    });
    return result;
  }

  function selectedOptions(state) {
    // Menu order must not reveal the generator's fibre/continuation order.
    return Array.from(state.nodes || []).sort((a, b) => a.label.localeCompare(b.label))
      .map((node) => `<option value="${esc(node.id)}">${esc(node.label)}</option>`).join("");
  }

  function drawSlice(canvas, model, view) {
    const ctx = canvas.getContext("2d");
    const width = canvas.width, height = canvas.height;
    const spec = model.state.views[view] || {};
    const axes = AXES[view];
    const scale = Number(spec.scale || 24);
    const centre = [width / 2, height / 2];
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = model.state.palette.glass || "#122235";
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = "rgba(173,225,238,.22)";
    ctx.lineWidth = 1;
    for (let x = 15; x < width; x += 24) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke(); }
    for (let y = 10; y < height; y += 24) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); }
    ctx.strokeStyle = "rgba(244,224,137,.46)";
    ctx.beginPath(); ctx.moveTo(centre[0], 0); ctx.lineTo(centre[0], height); ctx.moveTo(0, centre[1]); ctx.lineTo(width, centre[1]); ctx.stroke();
    const visible = new Map(records(model.state, model.focus, view).map((record) => [record.id, record]));
    model.edges.forEach((key) => {
      const [a, b] = pair(key);
      const left = visible.get(a), right = visible.get(b);
      if (!left || !right) return;
      ctx.strokeStyle = "rgba(143,222,246,.65)"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(centre[0] + left.u * scale, centre[1] - left.v * scale); ctx.lineTo(centre[0] + right.u * scale, centre[1] - right.v * scale); ctx.stroke();
    });
    const marked = component(model.edges, model.state.seed_segment_id);
    visible.forEach((record, id) => {
      const x = centre[0] + record.u * scale, y = centre[1] - record.v * scale;
      ctx.fillStyle = marked.has(id) ? model.state.palette.target : model.state.palette.fibre[colourIndex(id, model.state.palette.fibre.length)];
      ctx.beginPath(); ctx.arc(x, y, marked.has(id) ? 5 : 4, 0, Math.PI * 2); ctx.fill();
      if (model.selected.has(id)) { ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2); ctx.stroke(); }
      if (id === model.state.seed_segment_id) { ctx.strokeStyle = model.state.palette.target; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, 11, 0, Math.PI * 2); ctx.stroke(); }
      if (model.seeds.red === id || model.seeds.green === id) { ctx.strokeStyle = model.seeds.red === id ? "#ff596d" : "#6dffb0"; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI * 2); ctx.stroke(); }
    });
    ctx.fillStyle = "rgba(232,247,251,.88)"; ctx.font = "11px ui-monospace, monospace";
    ctx.fillText(view.toUpperCase(), 8, 14);
    ctx.fillStyle = "rgba(232,247,251,.62)"; ctx.fillText(`focus ${model.focus[axes[2]] + 1}/${model.state.slice_contract.index_count}`, 8, height - 8);
  }

  function drawMesh(canvas, model) {
    const ctx = canvas.getContext("2d");
    const width = canvas.width, height = canvas.height;
    ctx.clearRect(0, 0, width, height);
    const gradient = ctx.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, model.state.palette.glass || "#142238"); gradient.addColorStop(1, "#080f1d");
    ctx.fillStyle = gradient; ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = "rgba(172,221,232,.12)"; ctx.lineWidth = 1;
    for (let x = 0; x < width; x += 36) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke(); }
    for (let y = 0; y < height; y += 36) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); }
    const byId = Object.fromEntries((model.state.nodes || []).map((node) => [node.id, node]));
    model.edges.forEach((key) => {
      const [a, b] = pair(key); if (!byId[a] || !byId[b]) return;
      const left = project(byId[a].p, model.yaw, model.pitch), right = project(byId[b].p, model.yaw, model.pitch);
      ctx.strokeStyle = "rgba(119,220,243,.72)"; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(left[0], left[1]); ctx.lineTo(right[0], right[1]); ctx.stroke();
    });
    const marked = component(model.edges, model.state.seed_segment_id);
    (model.state.nodes || []).forEach((node) => {
      const point = project(node.p, model.yaw, model.pitch);
      const isMarked = marked.has(node.id);
      ctx.fillStyle = isMarked ? model.state.palette.target : model.state.palette.fibre[colourIndex(node.id, model.state.palette.fibre.length)];
      ctx.shadowColor = ctx.fillStyle; ctx.shadowBlur = isMarked ? 13 : 5;
      ctx.beginPath(); ctx.arc(point[0], point[1], isMarked ? 7 : 5, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0;
      if (model.selected.has(node.id)) { ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(point[0], point[1], 11, 0, Math.PI * 2); ctx.stroke(); }
      if (node.id === model.state.seed_segment_id) { ctx.strokeStyle = model.state.palette.target; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(point[0], point[1], 13, 0, Math.PI * 2); ctx.stroke(); }
      ctx.fillStyle = "rgba(230,245,249,.74)"; ctx.font = "10px ui-monospace, monospace"; ctx.fillText(node.label, point[0] + 8, point[1] - 7);
    });
    ctx.fillStyle = "rgba(236,249,252,.9)"; ctx.font = "12px ui-monospace, monospace"; ctx.fillText("RECONSTRUCTION / ORBIT", 14, 20);

  }

  function redraw(model) {
    VIEWS.forEach((view) => drawSlice(model.root.querySelector(`canvas[data-view="${view}"]`), model, view));
    drawMesh(model.root.querySelector(".branch-mesh"), model);
    model.root.querySelectorAll(".branch-selection").forEach((element) => {
      element.textContent = Array.from(model.selected).map((id) => model.state.nodes.find((node) => node.id === id).label).join(" · ");
    });
    model.root.querySelector(".branch-seed-readout").textContent = ["red", "green"].map((color) => {
      const node = model.state.nodes.find((item) => item.id === model.seeds[color]);
      return node ? `${color.toUpperCase()}: ${node.label}` : "";
    }).filter(Boolean).join(" · ");
    model.root.querySelectorAll(".branch-select-pair, .branch-merge, .branch-place-seed, .branch-cut, .branch-certify").forEach((button) => {
      button.disabled = model.needsInspection;
    });
    const fresh = model.root.querySelector(".fresh-banner");
    if (fresh) fresh.hidden = !model.fresh;
  }

  function render(state, helpers) {
    const interaction = String((state.control_condition || {}).interaction || state.interaction || "full");
    const model = {
      state, interaction, focus: Array.from(state.focus || [0, 0, 0]), events: [],
      edges: new Set((state.initial_edges || []).map((edge) => edgeKey(edge[0], edge[1]))),
      selected: new Set(), seeds: {}, yaw: 0, pitch: 0.35, orbitCount: 0,
      observations: new Set(), postEditInspections: 0, needsInspection: false, pointer: null, activeSeedColor: "red", fresh: state._fresh_failure === true,
      root: null,
    };
    const targetOptions = selectedOptions(state);
    const slices = VIEWS.map((view) => `
      <div class="branch-slice-panel"><div class="branch-slice-title">${view.toUpperCase()} · linked plane</div><canvas class="branch-slice" data-view="${view}" width="230" height="154" aria-label="${view} cross section"></canvas></div>
    `).join("");
    const simplified = interaction === "simplified";
    document.body.dataset.mechanic = "branch-repair";
    document.body.dataset.interaction = interaction;
    document.body.dataset.cheatMode = "false";
    const app = document.getElementById("app");
    app.innerHTML = `
      <section class="branch-repair-captcha" data-mechanic="branch_repair" data-interaction="${esc(interaction)}" data-fresh-failure="${model.fresh ? "true" : "false"}">
        <header class="branch-header"><div><p class="branch-kicker">GLASS SPECIMEN / TOPOLOGY LAB</p><h1>Branch Repair</h1><p class="branch-prompt">${esc(state.prompt || "Repair the marked fibre without absorbing its neighbours.")}</p></div><div class="branch-target"><span>MARKED FIBRE</span><strong>${esc(state.target_label)}</strong></div></header>
        <div class="fresh-banner" ${model.fresh ? "" : "hidden"}>FAIL</div>
        <main class="branch-layout">
          <section class="branch-scans"><div class="branch-section-label">01 / LINKED CROSS-SECTIONS </div><div class="branch-slice-grid">${slices}</div><div class="branch-slice-tools ${simplified ? "" : "is-hidden"}"><div class="branch-tool-row"><span>slice</span><button class="branch-slice-step" data-axis="x" data-delta="-1">X −</button><button class="branch-slice-step" data-axis="x" data-delta="1">X +</button><button class="branch-slice-step" data-axis="y" data-delta="-1">Y −</button><button class="branch-slice-step" data-axis="y" data-delta="1">Y +</button><button class="branch-slice-step" data-axis="z" data-delta="-1">Z −</button><button class="branch-slice-step" data-axis="z" data-delta="1">Z +</button></div></div></section>
          <section class="branch-mesh-panel"><div class="branch-section-label">02 / REGENERATED MESH </div><canvas class="branch-mesh" width="720" height="290" aria-label="three-dimensional fibre reconstruction"></canvas><div class="branch-mesh-tools ${simplified ? "" : "is-hidden"}"><button class="branch-orbit" data-direction="left">◀ orbit</button><button class="branch-orbit" data-direction="right">orbit ▶</button><button class="branch-orbit" data-direction="up">▲ tilt</button><button class="branch-orbit" data-direction="down">▼ tilt</button></div></section>
        </main>
        <section class="branch-actions"><div class="branch-section-label">03 / REPAIR ACTIONS </div><div class="branch-action-grid"><div class="branch-card ${simplified ? "" : "is-hidden"}"><h2>MERGE</h2><div class="branch-select-row"><select id="branch-merge-a" aria-label="first merge segment"><option value="">first segment</option>${targetOptions}</select><select id="branch-merge-b" aria-label="second merge segment"><option value="">second segment</option>${targetOptions}</select></div><button class="branch-select-pair ${simplified ? "" : "is-hidden"}">SELECT PAIR</button><button class="branch-merge ${simplified ? "" : "is-hidden"}">MERGE SELECTED</button><p class="branch-selection">no segment pair selected</p></div><div class="branch-card"><h2>SPLIT</h2><div class="branch-seed-row"><button class="branch-seed-color active" data-color="red">RED SEED</button><button class="branch-seed-color" data-color="green">GREEN SEED</button><select class="${simplified ? "" : "is-hidden"}" id="branch-seed-view" aria-label="seed slice view"><option value="xy">XY plane</option><option value="xz">XZ plane</option><option value="yz">YZ plane</option></select></div><select class="${simplified ? "" : "is-hidden"}" id="branch-seed-segment" aria-label="seed segment"><option value="">seed segment</option>${targetOptions}</select><button class="branch-place-seed ${simplified ? "" : "is-hidden"}">PLACE ACTIVE SEED</button><button class="branch-cut">CUT BETWEEN SEEDS</button><p class="branch-seed-readout">no split seeds placed</p></div><div class="branch-card branch-certify-card"><h2>VERIFY THE SPECIMEN</h2><button class="branch-certify">CERTIFY REPAIRED BRANCH</button><div class="readout" data-status="idle">READY</div></div></div></section>
        
      </section>`;
    model.root = app.querySelector(".branch-repair-captcha");
    window.branchRepairModel = model;

    function push(event) {
      if (model.fresh) {
        model.fresh = false;
        model.root.dataset.freshFailure = "false";
        helpers.setReadout("READY", "idle");
      }
      if (event.kind === "merge" || event.kind === "split") model.needsInspection = true;
      event.sequence = model.events.length + 1;
      model.events.push(event);
      redraw(model);
    }
    function changeSlice(axis, delta, source) {
      const before = Array.from(model.focus);
      const index = AXIS_INDEX[axis];
      const next = Math.max(0, Math.min(Number(state.slice_contract.index_count) - 1, model.focus[index] + Number(delta)));
      if (next === model.focus[index]) return;
      model.focus[index] = next;
      const linked = Object.fromEntries(VIEWS.map((view) => [view, records(state, model.focus, view)]));
      const inspection = model.needsInspection ? "after_edit" : "initial";
      const topology = topologyDigestFor(state, model.focus, model.edges);
      model.observations.add(topology);
      push({kind: "slice_change", source, axis, index: next, before, focus: Array.from(model.focus), views: linked, digest: digestFor(state, model.focus), topology, inspection});
      if (inspection === "after_edit") model.postEditInspections += 1;
      model.needsInspection = false;
      redraw(model);
    }
    function orbit(direction) {
      const before = [round(model.yaw), round(model.pitch)];
      const deltas = {left: [-0.25, 0], right: [0.25, 0], up: [0, -0.18], down: [0, 0.18]};
      const delta = deltas[direction]; if (!delta) return;
      model.yaw = round(model.yaw + delta[0]); model.pitch = round(Math.max(-1, Math.min(1, model.pitch + delta[1])));
      model.orbitCount += 1;
      push({kind: "orbit", source: "orbit_controls", direction, before, after: [round(model.yaw), round(model.pitch)]});
    }
    function selectPair() {
      if (!simplified || model.needsInspection) return;
      const a = model.root.querySelector("#branch-merge-a").value, b = model.root.querySelector("#branch-merge-b").value;
      if (!a || !b || a === b) return;
      model.selected = new Set([a, b]);
      push({kind: "select_segment", source: "segment_palette", node_id: a});
      push({kind: "select_segment", source: "segment_palette", node_id: b});
    }
    function mergeSimplified() {
      if (!simplified || model.needsInspection) return;
      const values = [model.root.querySelector("#branch-merge-a").value, model.root.querySelector("#branch-merge-b").value];
      if (!values[0] || !values[1] || values[0] === values[1]) return;
      const key = edgeKey(values[0], values[1]); model.edges.add(key); model.selected.clear();
      push({kind: "merge", source: "merge_button", a: values[0], b: values[1]});
    }
    function placeSeed(nodeId, view, color, screen, source) {
      if (model.needsInspection || !nodeId || !color || !view) return;
      model.seeds[color] = nodeId;
      push({kind: "seed", source, color, node_id: nodeId, view, ...(screen ? {screen: screen.map(round)} : {})});
    }
    function placeSimplifiedSeed() {
      if (!simplified || model.needsInspection) return;
      const nodeId = model.root.querySelector("#branch-seed-segment").value, view = model.root.querySelector("#branch-seed-view").value;
      if (!nodeId) return;
      const visible = records(state, model.focus, view).find((record) => record.id === nodeId);
      if (visible) placeSeed(nodeId, view, model.activeSeedColor, null, "seed_palette");
    }
    function cut() {
      if (model.needsInspection || !model.seeds.red || !model.seeds.green) return;
      const red = model.seeds.red, green = model.seeds.green;
      model.edges.delete(edgeKey(red, green));
      model.seeds = {};
      push({kind: "split", source: "split_button", red, green});
    }
    function finish() {
      if (model.needsInspection) return;
      const event = {kind: "submit", source: "certify_button"};
      const events = model.events.concat([{...event, sequence: model.events.length + 1}]);
      const payload = {mechanic_id: "branch_repair", task_id: state.task_id, challenge_id: state.challenge_id, interaction: model.interaction, events, final_edges: Array.from(model.edges).map(pair).sort((a, b) => `${a[0]}|${a[1]}`.localeCompare(`${b[0]}|${b[1]}`)), focus: Array.from(model.focus), orbit: [round(model.yaw), round(model.pitch)], summary: {slice_observations: model.observations.size, post_edit_inspections: model.postEditInspections, orbit_actions: model.orbitCount, component_size: component(model.edges, state.seed_segment_id).size}};
      helpers.beginAction?.("certify branch repair");
      fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)}).then((response) => response.json().then((outcome) => ({response, outcome}))).then(async ({response, outcome}) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        if (outcome.passed === true) {
          model.fresh = false;
          model.root.dataset.freshFailure = "false";
          const banner = model.root.querySelector(".fresh-banner");
          if (banner) banner.hidden = true;
          helpers.setReadout("PASS", "passed");
          return;
        }
        if (outcome.passed === false && outcome.state) { outcome.state._fresh_failure = true; await helpers.render(outcome.state); helpers.setReadout("FAIL", "error"); return; }
        helpers.setReadout("FAIL", "error");
      }).catch(() => helpers.setReadout("FAIL", "error"));
    }

    model.root.querySelectorAll(".branch-slice-step").forEach((button) => button.addEventListener("click", () => changeSlice(button.dataset.axis, button.dataset.delta, "slice_controls")));
    model.root.querySelectorAll(".branch-orbit").forEach((button) => button.addEventListener("click", () => orbit(button.dataset.direction)));
    model.root.querySelector(".branch-select-pair").addEventListener("click", selectPair);
    model.root.querySelector(".branch-merge").addEventListener("click", mergeSimplified);
    model.root.querySelectorAll(".branch-seed-color").forEach((button) => button.addEventListener("click", () => { model.activeSeedColor = button.dataset.color; model.root.querySelectorAll(".branch-seed-color").forEach((item) => item.classList.toggle("active", item === button)); }));
    model.root.querySelector(".branch-place-seed").addEventListener("click", placeSimplifiedSeed);
    model.root.querySelector(".branch-cut").addEventListener("click", cut);
    model.root.querySelector(".branch-certify").addEventListener("click", finish);

    const mesh = model.root.querySelector(".branch-mesh");
    mesh.addEventListener("pointerdown", (event) => {
      if (simplified || event.button !== 0) return;
      const rect = mesh.getBoundingClientRect();
      const x = (event.clientX - rect.left) * mesh.width / rect.width, y = (event.clientY - rect.top) * mesh.height / rect.height;
      const hit = nearestMesh(model, x, y);
      model.pointer = {mode: hit ? "merge" : "orbit", startX: x, startY: y, lastX: x, lastY: y, startYaw: model.yaw, startPitch: model.pitch, startNode: hit && hit.id};
      mesh.setPointerCapture(event.pointerId);
    });
    mesh.addEventListener("pointermove", (event) => {
      if (!model.pointer || model.pointer.mode !== "orbit") return;
      const rect = mesh.getBoundingClientRect();
      model.pointer.lastX = (event.clientX - rect.left) * mesh.width / rect.width; model.pointer.lastY = (event.clientY - rect.top) * mesh.height / rect.height;
      model.yaw = round(model.pointer.startYaw + (model.pointer.lastX - model.pointer.startX) * 0.012); model.pitch = round(Math.max(-1, Math.min(1, model.pointer.startPitch + (model.pointer.lastY - model.pointer.startY) * 0.008))); redraw(model);
    });
    mesh.addEventListener("pointerup", (event) => {
      if (!model.pointer) return;
      const pointer = model.pointer; const rect = mesh.getBoundingClientRect();
      const x = (event.clientX - rect.left) * mesh.width / rect.width, y = (event.clientY - rect.top) * mesh.height / rect.height;
      if (pointer.mode === "merge") {
        const hit = nearestMesh(model, x, y);
        if (!model.needsInspection && hit && hit.id !== pointer.startNode) {
          model.edges.add(edgeKey(pointer.startNode, hit.id));
          push({kind: "merge", source: "mesh_drag_merge", a: pointer.startNode, b: hit.id, start: project((state.nodes.find((node) => node.id === pointer.startNode) || {}).p, pointer.startYaw, pointer.startPitch), end: project((state.nodes.find((node) => node.id === hit.id) || {}).p, pointer.startYaw, pointer.startPitch)});
        }
      } else {
        const dx = x - pointer.startX, dy = y - pointer.startY;
        model.yaw = round(pointer.startYaw); model.pitch = round(pointer.startPitch); model.yaw = round(model.yaw + dx * 0.012); model.pitch = round(Math.max(-1, Math.min(1, model.pitch + dy * 0.008)));
        if (Math.abs(dx * 0.012) + Math.abs(dy * 0.008) < 0.01) {
          model.yaw = pointer.startYaw; model.pitch = pointer.startPitch;
          model.pointer = null; redraw(model); return;
        }
        model.orbitCount += 1;
        push({kind: "orbit", source: "orbit_drag", dx: round(dx), dy: round(dy), before: [round(pointer.startYaw), round(pointer.startPitch)], after: [round(model.yaw), round(model.pitch)]});
      }
      model.pointer = null; redraw(model);
    });
    function cancelPointer() {
      if (!model.pointer) return;
      model.yaw = model.pointer.startYaw; model.pitch = model.pointer.startPitch;
      model.pointer = null; redraw(model);
    }
    mesh.addEventListener("pointercancel", cancelPointer);
    mesh.addEventListener("lostpointercapture", cancelPointer);
    mesh.addEventListener("wheel", (event) => event.preventDefault(), {passive: false});
    model.root.querySelectorAll(".branch-slice").forEach((canvas) => {
      const view = canvas.dataset.view;
      canvas.addEventListener("wheel", (event) => {
        if (model.interaction !== "full") return;
        event.preventDefault();
        const axis = AXES[view][2]; changeSlice(["x", "y", "z"][axis], event.deltaY > 0 ? 1 : -1, "slice_scroll");
      }, {passive: false});
      canvas.addEventListener("click", (event) => {
        if (model.interaction !== "full" || !model.activeSeedColor) return;
        const rect = canvas.getBoundingClientRect(); const x = (event.clientX - rect.left) * canvas.width / rect.width, y = (event.clientY - rect.top) * canvas.height / rect.height;
        const hit = nearestSlice(model, view, x, y);
        if (hit) placeSeed(hit.record.id, view, model.activeSeedColor, hit.point, "slice_seed");
      });
    });
    model.seedScreen = (view, nodeId) => { const record = records(state, model.focus, view).find((item) => item.id === nodeId); return record ? screenFor(state, view, record) : null; };
    model.projectNode = (nodeId) => { const node = (state.nodes || []).find((item) => item.id === nodeId); return node ? project(node.p, model.yaw, model.pitch) : null; };
    redraw(model);
    helpers.setReadout(model.fresh ? "FAIL" : "READY", model.fresh ? "error" : "idle");
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.branch_repair = {rootSelector: ".branch-repair-captcha", render};
})();
