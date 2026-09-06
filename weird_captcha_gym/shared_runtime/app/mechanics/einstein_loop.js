(() => {
  "use strict";

  const MECHANIC_ID = "einstein_loop";
  const STATE = {clear: 0, loop: 1, cross: -1};
  let model = null;
  let cleanup = null;

  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const interaction = () => model.state.control_condition?.interaction || "full";
  const vertexMap = () => new Map(model.puzzle.vertices.map((vertex) => [vertex.id, vertex]));
  const edgeMap = () => new Map(model.puzzle.edges.map((edge) => [edge.id, edge]));

  function clearFreshFailure() {
    if (!model.freshFailure) return;
    model.freshFailure = false;
    const verdict = document.querySelector(".el-verdict");
    if (verdict) { verdict.className = "el-verdict"; verdict.innerHTML = ""; }
    model.helpers.setReadout("", "idle");
  }

  function record(event) {
    clearFreshFailure();
    model.events.push({sequence: model.events.length + 1, ...event});
  }

  function points(face) {
    const vertices = vertexMap();
    return face.vertices.map((id) => `${vertices.get(id).x},${vertices.get(id).y}`).join(" ");
  }

  function line(edge, className, attributes = "") {
    const vertices = vertexMap();
    const start = vertices.get(edge.vertices[0]);
    const end = vertices.get(edge.vertices[1]);
    return `<line class="${className}" x1="${start.x}" y1="${start.y}" x2="${end.x}" y2="${end.y}" ${attributes}/>`;
  }

  function crossMarkup(edge) {
    const vertices = vertexMap();
    const start = vertices.get(edge.vertices[0]);
    const end = vertices.get(edge.vertices[1]);
    const x = (start.x + end.x) / 2;
    const y = (start.y + end.y) / 2;
    return `<g class="el-cross" transform="translate(${x} ${y})"><path d="M-6 -6L6 6M6 -6L-6 6"/></g>`;
  }

  function boardMarkup() {
    const clueByFace = new Map(model.puzzle.clues.map((clue) => [clue.face_id, clue.value]));
    const faces = model.puzzle.faces.map((face) => `<polygon class="el-face tone-${face.tone}" data-face="${face.id}" points="${points(face)}"/>`).join("");
    const clues = model.puzzle.faces.map((face) => clueByFace.has(face.id) ? `
      <g class="el-clue" transform="translate(${face.label_point.x} ${face.label_point.y})">
        <circle r="15"></circle><text y="1">${clueByFace.get(face.id)}</text>
      </g>` : "").join("");
    const baseEdges = model.puzzle.edges.map((edge) => line(edge, `el-edge-base ${model.selectedEdge === edge.id ? "is-focus" : ""}`)).join("");
    const loopEdges = model.puzzle.edges.filter((edge) => model.edgeState[edge.id] === 1).map((edge) => line(edge, "el-edge-loop")).join("");
    const crosses = model.puzzle.edges.filter((edge) => model.edgeState[edge.id] === -1).map(crossMarkup).join("");
    const hits = model.puzzle.edges.map((edge) => line(edge, "el-edge-hit", `data-edge-hit="${edge.id}"`)).join("");
    const vertexHits = interaction() === "full" ? model.puzzle.vertices.map((vertex) => `
      <circle class="el-vertex-hit" data-vertex-hit="${vertex.id}" cx="${vertex.x}" cy="${vertex.y}" r="16"/>`).join("") : "";
    const dots = model.puzzle.vertices.map((vertex) => `<circle class="el-dot" cx="${vertex.x}" cy="${vertex.y}" r="3.1"/>`).join("");
    return `<div class="el-board-frame">
      <svg class="el-board" data-board viewBox="0 0 ${model.puzzle.view_width} ${model.puzzle.view_height}" role="img" aria-label="irregular hat-tile loop board">
        <g class="el-faces">${faces}</g>
        <g class="el-grid">${baseEdges}</g>
        <g class="el-loops">${loopEdges}</g>
        <g class="el-crosses">${crosses}</g>
        <g class="el-clues">${clues}</g>
        <g class="el-hits">${hits}${vertexHits}</g>
        <g class="el-dots">${dots}</g>
      </svg>
      <span class="el-plate-code">HAT / ${model.puzzle.faces.length.toString().padStart(2, "0")}</span>
    </div>`;
  }

  function proxyMarkup() {
    if (interaction() !== "simplified") return "";
    const selected = model.selectedEdge;
    const state = selected ? model.edgeState[selected] : 0;
    return `<aside class="el-proxy" aria-label="edge mark controls">
      <div><small>EDGE</small><b>${selected ? selected.toUpperCase() : "—"}</b></div>
      <button data-proxy="loop" ${selected ? "" : "disabled"} class="${state === 1 ? "is-active" : ""}"><i></i>LOOP</button>
      <button data-proxy="cross" ${selected ? "" : "disabled"} class="${state === -1 ? "is-active" : ""}"><i>×</i>RULE OUT</button>
      <button data-proxy="clear" ${selected ? "" : "disabled"}>CLEAR</button>
    </aside>`;
  }

  function renderUi() {
    model.helpers.app.innerHTML = `<section class="einstein-loop mode-${interaction()}" data-interaction="${interaction()}" data-challenge-id="${esc(model.state.challenge_id)}" data-fresh-failure="${model.freshFailure ? "true" : "false"}">
      <div class="el-verdict"></div>
      <header class="el-header">
        <div class="el-sigil" aria-hidden="true"><i></i><i></i><i></i></div>
        <div class="el-title"><small>APERIODIC SURVEY / ONE CONTINUOUS BOUNDARY</small><h1>Einstein Loop</h1></div>
        <div class="el-condition"><small>TILES</small><b>${model.puzzle.faces.length}</b><span>${interaction().toUpperCase()}</span></div>
      </header>
      <main>
        <section class="el-board-panel">${boardMarkup()}</section>
        <aside class="el-ledger">
          <div class="el-ledger-head"><small>ACTIVE PLATE</small><h2>${esc(model.state.prompt)}</h2></div>
          <div class="el-swatches" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
          ${proxyMarkup()}
          <div class="el-ledger-foot"><span>SMITH · MYERS · KAPLAN · GOODMAN-STRAUSS / 2023</span></div>
        </aside>
      </main>
      <footer class="el-footer">
        <button data-reset>RESET PLATE</button>
        <div class="readout" data-status="idle"></div>
        <button class="el-certify" data-certify ${model.terminal ? "disabled" : ""}>CERTIFY LOOP <i>↗</i></button>
      </footer>
      ${model.helpers.cheatPanelTemplate()}
    </section>`;
    bindControls();
    model.helpers.installCheatPanel();
    if (model.freshFailure) showVerdict("fail");
    if (model.terminal) showVerdict("pass");
  }

  function applyUpdates(mode, edgeIds, inputSource, gesture = null) {
    if (model.terminal || !edgeIds.length) return;
    const after = STATE[mode];
    const updates = edgeIds.map((id) => ({id, before: model.edgeState[id], after}));
    if (updates.every((update) => update.before === after)) return;
    updates.forEach((update) => { model.edgeState[update.id] = after; });
    record({type: "edge_update", mode, input_source: inputSource, edges: updates, ...(gesture ? {gesture} : {})});
    model.helpers.setReadout("", "idle");
    renderUi();
  }

  function svgPoint(svg, event) {
    const rect = svg.getBoundingClientRect();
    const scale = Math.min(rect.width / model.puzzle.view_width, rect.height / model.puzzle.view_height);
    const insetX = (rect.width - model.puzzle.view_width * scale) / 2;
    const insetY = (rect.height - model.puzzle.view_height * scale) / 2;
    return {
      x: (event.clientX - rect.left - insetX) / scale,
      y: (event.clientY - rect.top - insetY) / scale,
    };
  }

  function closestVertex(point, radius = 24) {
    let best = null;
    let distance = radius;
    model.puzzle.vertices.forEach((vertex) => {
      const candidate = Math.hypot(point.x - vertex.x, point.y - vertex.y);
      if (candidate <= distance) { best = vertex.id; distance = candidate; }
    });
    return best;
  }

  function edgeBetween(start, end) {
    return model.puzzle.edges.find((edge) => edge.vertices.includes(start) && edge.vertices.includes(end))?.id || null;
  }

  function bindFullBoard() {
    const svg = document.querySelector("[data-board]");
    if (!svg) return;
    let stroke = null;

    const advance = (event) => {
      if (!stroke) return;
      const point = svgPoint(svg, event);
      stroke.travel += Math.hypot(point.x - stroke.last.x, point.y - stroke.last.y);
      stroke.last = point;
      stroke.samples += 1;
      const candidate = closestVertex(point);
      const current = stroke.vertices[stroke.vertices.length - 1];
      if (!candidate || candidate === current) return;
      const edgeId = edgeBetween(current, candidate);
      if (!edgeId || stroke.edgeIds.includes(edgeId)) return;
      stroke.vertices.push(candidate);
      stroke.edgeIds.push(edgeId);
      document.querySelector(`[data-edge-hit="${edgeId}"]`)?.classList.add("is-preview");
    };

    svg.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || model.terminal) return;
      const point = svgPoint(svg, event);
      const start = closestVertex(point);
      if (!start) return;
      event.preventDefault();
      clearFreshFailure();
      stroke = {vertices: [start], edgeIds: [], last: point, travel: 0, samples: 1, pointerId: event.pointerId};
      svg.setPointerCapture?.(event.pointerId);
    });
    svg.addEventListener("pointermove", advance);
    svg.addEventListener("pointerup", (event) => {
      if (!stroke) return;
      advance(event);
      const finished = stroke;
      stroke = null;
      document.querySelectorAll(".el-edge-hit.is-preview").forEach((node) => node.classList.remove("is-preview"));
      if (!finished.edgeIds.length) return;
      const allLoop = finished.edgeIds.every((edgeId) => model.edgeState[edgeId] === 1);
      applyUpdates(allLoop ? "clear" : "loop", finished.edgeIds, "direct_edge_drag", {
        start_vertex_id: finished.vertices[0],
        end_vertex_id: finished.vertices[finished.vertices.length - 1],
        travel_px: Number(finished.travel.toFixed(3)),
        sample_count: finished.samples,
      });
    });
    svg.addEventListener("pointercancel", () => { stroke = null; });
    svg.addEventListener("contextmenu", (event) => {
      const hit = event.target.closest?.("[data-edge-hit]");
      if (!hit || model.terminal) return;
      event.preventDefault();
      const edgeId = hit.dataset.edgeHit;
      applyUpdates(model.edgeState[edgeId] === -1 ? "clear" : "cross", [edgeId], "direct_edge_context");
    });
  }

  function bindSimplifiedBoard() {
    document.querySelectorAll("[data-edge-hit]").forEach((edge) => edge.addEventListener("click", (event) => {
      event.preventDefault();
      if (model.terminal) return;
      clearFreshFailure();
      model.selectedEdge = edge.dataset.edgeHit;
      renderUi();
    }));
    document.querySelectorAll("[data-proxy]").forEach((button) => button.addEventListener("click", () => {
      if (!model.selectedEdge) return;
      applyUpdates(button.dataset.proxy, [model.selectedEdge], "edge_proxy_button");
    }));
  }

  function resetPlate() {
    if (model.terminal) return;
    model.edgeState = Object.fromEntries(model.puzzle.edges.map((edge) => [edge.id, 0]));
    model.selectedEdge = null;
    record({type: "reset", input_source: "reset_button"});
    model.helpers.setReadout("", "idle");
    renderUi();
  }

  function bindControls() {
    if (interaction() === "full") bindFullBoard();
    else bindSimplifiedBoard();
    document.querySelector("[data-reset]")?.addEventListener("click", resetPlate);
    document.querySelector("[data-certify]")?.addEventListener("click", submit);
  }

  function showVerdict(kind) {
    const node = document.querySelector(".el-verdict");
    if (!node) return;
    node.className = `el-verdict is-${kind}`;
    node.innerHTML = `<span>FIELD OFFICE</span><b>${kind.toUpperCase()}</b>`;
  }

  async function submit() {
    if (!model || model.submitting || model.terminal) return;
    const current = model;
    current.submitting = true;
    current.helpers.setReadout("", "pending");
    const sortIds = (ids) => ids.sort((left, right) => Number(left.slice(1)) - Number(right.slice(1)));
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({
          mechanic_id: current.state.mechanic_id,
          task_id: current.state.task_id,
          challenge_id: current.state.challenge_id,
          interaction_mode: interaction(),
          events: current.events,
          final_loop_edge_ids: sortIds(Object.keys(current.edgeState).filter((id) => current.edgeState[id] === 1)),
          final_crossed_edge_ids: sortIds(Object.keys(current.edgeState).filter((id) => current.edgeState[id] === -1)),
          completed: true,
        }),
      });
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.terminal = true;
        current.helpers.setReadout("PASS", "passed");
        showVerdict("pass");
      } else if (outcome.passed === false && outcome.state) {
        const helpers = current.helpers;
        await render(outcome.state, helpers, {freshFailure: true});
        model.helpers.setReadout("FAIL", "error");
        showVerdict("fail");
      } else {
        current.submitting = false;
        current.helpers.setReadout("FAIL", "error");
        showVerdict("fail");
      }
    } catch (_error) {
      if (model === current) {
        current.submitting = false;
        current.helpers.setReadout("", "idle");
      }
    }
  }

  async function render(state, helpers, options = {}) {
    cleanup?.();
    document.body.dataset.mechanic = "einstein-loop";
    model = {
      state,
      helpers,
      puzzle: JSON.parse(JSON.stringify(state.puzzle)),
      edgeState: Object.fromEntries(state.puzzle.edges.map((edge) => [edge.id, 0])),
      events: [],
      selectedEdge: null,
      freshFailure: Boolean(options.freshFailure),
      terminal: false,
      submitting: false,
    };
    renderUi();
    cleanup = () => {};
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {rootSelector: ".einstein-loop", render};
})();
