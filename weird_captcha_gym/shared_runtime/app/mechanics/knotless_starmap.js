(() => {
  "use strict";

  const MECHANIC = "knotless_starmap";

  function render(state, helpers, options = {}) {
    document.body.dataset.mechanic = "knotless-starmap";
    const world = state.world || {};
    const mode = state.control_condition?.interaction || "full";
    const full = mode === "full";
    const initial = new Map((world.vertices || []).map((vertex) => [vertex.id, [Number(vertex.x), Number(vertex.y)]]));
    const positions = new Map([...initial].map(([id, point]) => [id, [...point]]));
    const vertices = (world.vertices || []).map((vertex) => ({...vertex}));
    const edges = (world.edges || []).map((edge) => [String(edge[0]), String(edge[1])]);
    const events = [];
    let selectedId = null;
    let drag = null;
    let terminal = false;
    let submitting = false;
    let failedNotice = Boolean(options.failed);
    let notice = null;

    helpers.app.innerHTML = `
      <section class="ks-shell" data-interaction="${helpers.text(mode)}" data-challenge-id="${helpers.text(state.challenge_id)}">
        <header class="ks-header">
          <div>
            <div class="ks-kicker">CELESTIAL CARTOGRAPHY / PLATE 07</div>
            <h1>Knotless Starmap</h1>
            <p>${full ? "Drag stars" : "Select a star, then click its destination"} to untangle the fixed edges. Keep stars separate and edges free of crossings or overlaps.</p>
          </div>
        </header>
        <main class="ks-main">
          <section class="ks-map-column">
            <div class="ks-map-topline"><span>LIVE EMBEDDING / ${vertices.length} STARS</span><b class="ks-crossing-readout">CROSSINGS <i>—</i></b></div>
            <div class="ks-canvas-wrap">
              <canvas class="ks-canvas" width="860" height="500" aria-label="Interactive star map"></canvas>
            </div>
            <div class="ks-legend"><span><i class="ks-dot ks-dot-star"></i> movable star</span><span><i class="ks-dot ks-dot-edge"></i> fixed luminous edge</span><span><i class="ks-dot ks-dot-cross"></i> crossing pair</span></div>
          </section>
          <aside class="ks-console">
            <div class="ks-console-label">THE CARTOGRAPHER'S CONSOLE</div>
            <div class="ks-metric"><span>REMAINING INTERSECTIONS</span><strong class="ks-count">—</strong><small class="ks-geometry">—</small></div>
            <button type="button" class="ks-submit">${helpers.text(state.submit_label || "CERTIFY MAP")} <span>↗</span></button>
            <button type="button" class="ks-reset">RESET THIS MAP</button>
            <button type="button" class="ks-abandon">ABANDON ATTEMPT</button>
            <div class="ks-status"><span>STATUS</span><div class="readout" data-status="idle">${failedNotice ? "FAIL · FRESH MAP READY" : "MAP IS TANGLED"}</div></div>
          </aside>
        </main>
        <footer class="ks-footer"><span>CELESTIAL CARTOGRAPHY</span><span class="ks-event-count">0 vertex moves</span></footer>
        <div class="ks-verdict" ${failedNotice ? "" : "hidden"}>
          <strong class="ks-verdict-title">${failedNotice ? "FAIL" : ""}</strong>
          <span class="ks-verdict-copy">${failedNotice ? "That embedding was rejected. A fresh map is ready." : ""}</span>
          <button type="button" class="ks-verdict-dismiss" ${failedNotice ? "" : "hidden"}>BEGIN FRESH MAP →</button>
        </div>
      </section>`;

    const root = helpers.app.querySelector(".ks-shell");
    const canvas = root.querySelector(".ks-canvas");
    const context = canvas.getContext("2d");
    const countNode = root.querySelector(".ks-count");
    const readout = root.querySelector(".readout");
    const submitButton = root.querySelector(".ks-submit");
    const resetButton = root.querySelector(".ks-reset");
    const abandonButton = root.querySelector(".ks-abandon");
    const verdict = root.querySelector(".ks-verdict");
    const geometryNode = root.querySelector(".ks-geometry");
    const eventCount = root.querySelector(".ks-event-count");

    function orientation(a, b, c) {
      return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
    }

    function onSegment(a, b, p) {
      return Math.min(a[0], b[0]) - 1e-7 <= p[0] && p[0] <= Math.max(a[0], b[0]) + 1e-7 &&
        Math.min(a[1], b[1]) - 1e-7 <= p[1] && p[1] <= Math.max(a[1], b[1]) + 1e-7 && Math.abs(orientation(a, b, p)) <= 1e-7;
    }

    function intersects(a, b, c, d) {
      const abC = orientation(a, b, c), abD = orientation(a, b, d);
      const cdA = orientation(c, d, a), cdB = orientation(c, d, b);
      const proper = ((abC > 1e-7 && abD < -1e-7) || (abC < -1e-7 && abD > 1e-7)) &&
        ((cdA > 1e-7 && cdB < -1e-7) || (cdA < -1e-7 && cdB > 1e-7));
      return proper || onSegment(a, b, c) || onSegment(a, b, d) || onSegment(c, d, a) || onSegment(c, d, b);
    }

    function crossingIndices() {
      const result = [];
      for (let first = 0; first < edges.length; first += 1) {
        for (let second = first + 1; second < edges.length; second += 1) {
          if (edges[first].some((id) => edges[second].includes(id))) continue;
          const a = positions.get(edges[first][0]), b = positions.get(edges[first][1]);
          const c = positions.get(edges[second][0]), d = positions.get(edges[second][1]);
          if (intersects(a, b, c, d)) result.push([first, second]);
        }
      }
      return result;
    }

    function geometryIssues() {
      const overlaps = [];
      for (let first = 0; first < edges.length; first += 1) {
        for (let second = first + 1; second < edges.length; second += 1) {
          const shared = edges[first].find((id) => edges[second].includes(id));
          if (!shared) continue;
          const origin = positions.get(shared);
          const a = positions.get(edges[first].find((id) => id !== shared));
          const b = positions.get(edges[second].find((id) => id !== shared));
          if (Math.abs(orientation(origin, a, b)) <= 1e-7 &&
              (a[0] - origin[0]) * (b[0] - origin[0]) + (a[1] - origin[1]) * (b[1] - origin[1]) > 1e-7) {
            overlaps.push([first, second]);
          }
        }
      }
      const crowded = new Set();
      for (let first = 0; first < vertices.length; first += 1) {
        for (let second = first + 1; second < vertices.length; second += 1) {
          const a = positions.get(vertices[first].id), b = positions.get(vertices[second].id);
          if (Math.hypot(a[0] - b[0], a[1] - b[1]) < Number(world.minimum_vertex_separation ?? 24) - .25) {
            crowded.add(vertices[first].id); crowded.add(vertices[second].id);
          }
        }
      }
      return {overlaps, crowded};
    }

    function pointFromEvent(event) {
      const bounds = canvas.getBoundingClientRect();
      return [
        Math.max(0, Math.min(860, (event.clientX - bounds.left) * 860 / bounds.width)),
        Math.max(0, Math.min(500, (event.clientY - bounds.top) * 500 / bounds.height)),
      ];
    }

    function pointOnCanvas(event) {
      const bounds = canvas.getBoundingClientRect();
      return [
        Math.max(0, Math.min(860, (event.clientX - bounds.left) * 860 / bounds.width)),
        Math.max(0, Math.min(500, (event.clientY - bounds.top) * 500 / bounds.height)),
      ];
    }

    function hitVertex(point) {
      let best = null;
      let bestDistance = 24;
      for (const vertex of vertices) {
        const candidate = positions.get(vertex.id);
        const distance = Math.hypot(point[0] - candidate[0], point[1] - candidate[1]);
        if (distance <= bestDistance) {
          best = vertex.id;
          bestDistance = distance;
        }
      }
      return best;
    }

    function palette() {
      const seed = Number(world.palette_seed || 0);
      return {
        background: ["#111d35", "#172a45", "#0f263a", "#241d3c"][seed % 4],
        line: ["#7ac4d7", "#8dd5bb", "#d5b77b", "#a9a0ed"][seed % 4],
        accent: ["#ef6f9a", "#ff8b66", "#f3c86b", "#d886e7"][seed % 4],
      };
    }

    function draw() {
      const colors = palette();
      root.querySelector(".ks-dot-edge").style.background = colors.line;
      root.querySelector(".ks-dot-cross").style.background = colors.accent;
      const crossing = crossingIndices();
      const {overlaps, crowded} = geometryIssues();
      const invalid = crossing.length || overlaps.length || crowded.size;
      const crossingEdges = new Set([...crossing.flat(), ...overlaps.flat()]);
      context.clearRect(0, 0, 860, 500);
      context.fillStyle = colors.background;
      context.fillRect(0, 0, 860, 500);
      const seed = Number(world.palette_seed || 1);
      for (let index = 0; index < 130; index += 1) {
        const x = (seed * 37 + index * 83) % 840 + 10;
        const y = (seed * 19 + index * 47) % 470 + 15;
        const radius = index % 9 === 0 ? 1.6 : (index % 3 === 0 ? 1 : .55);
        context.fillStyle = index % 5 === 0 ? "rgba(239,214,160,.75)" : "rgba(190,224,239,.48)";
        context.beginPath(); context.arc(x, y, radius, 0, Math.PI * 2); context.fill();
      }
      context.strokeStyle = "rgba(152,190,214,.12)";
      context.lineWidth = 1;
      for (let radius = 94; radius <= 300; radius += 52) {
        context.beginPath(); context.ellipse(430, 250, radius, radius * .54, 0, 0, Math.PI * 2); context.stroke();
      }
      edges.forEach((edge, index) => {
        const first = positions.get(edge[0]), second = positions.get(edge[1]);
        context.beginPath(); context.moveTo(first[0], first[1]); context.lineTo(second[0], second[1]);
        context.lineWidth = crossingEdges.has(index) ? 3.8 : 2.2;
        context.strokeStyle = crossingEdges.has(index) ? colors.accent : colors.line;
        context.shadowColor = context.strokeStyle;
        context.shadowBlur = crossingEdges.has(index) ? 12 : 7;
        context.globalAlpha = crossingEdges.has(index) ? .96 : .72;
        context.stroke();
      });
      context.shadowBlur = 0; context.globalAlpha = 1;
      vertices.forEach((vertex) => {
        const point = positions.get(vertex.id);
        const active = selectedId === vertex.id || (drag && drag.vertexId === vertex.id);
        context.save(); context.translate(point[0], point[1]);
        if (crowded.has(vertex.id)) {
          context.strokeStyle = colors.accent; context.lineWidth = 2;
          context.beginPath(); context.arc(0, 0, Number(world.minimum_vertex_separation ?? 24) / 2, 0, Math.PI * 2); context.stroke();
        }
        context.shadowColor = active ? "#fff2bb" : colors.line; context.shadowBlur = active ? 24 : 14;
        context.fillStyle = active ? "#fff1bd" : "#edf5f3";
        context.strokeStyle = active ? colors.accent : colors.line; context.lineWidth = active ? 3 : 1.8;
        context.beginPath();
        for (let arm = 0; arm < 8; arm += 1) {
          const angle = -Math.PI / 2 + arm * Math.PI / 4;
          const radius = arm % 2 === 0 ? 13 : 5.5;
          const x = Math.cos(angle) * radius, y = Math.sin(angle) * radius;
          if (arm === 0) context.moveTo(x, y); else context.lineTo(x, y);
        }
        context.closePath(); context.fill(); context.stroke(); context.shadowBlur = 0;
        context.fillStyle = colors.background; context.font = "bold 11px ui-monospace, monospace"; context.textAlign = "center"; context.textBaseline = "middle";
        context.fillText(String(vertex.label), 0, 0.5); context.restore();
      });
      countNode.textContent = String(crossing.length);
      root.querySelector(".ks-crossing-readout i").textContent = String(crossing.length);
      root.dataset.crossings = String(crossing.length);
      root.dataset.overlaps = String(overlaps.length);
      root.dataset.crowded = String(crowded.size);
      geometryNode.textContent = `${overlaps.length} edge overlaps · ${crowded.size} crowded stars`;
      eventCount.textContent = `${events.filter((item) => item.type === "vertex_move").length} vertex moves`;
      submitButton.disabled = submitting || terminal;
      resetButton.disabled = submitting || terminal;
      abandonButton.disabled = submitting || terminal;
      readout.textContent = terminal ? "PASS · STAR MAP KNOTLESS" : submitting ? "CHECKING EMBEDDING…" :
        notice ? notice : failedNotice ? "FAIL · FRESH MAP READY" : selectedId ?
        `STAR ${vertices.find((item) => item.id === selectedId)?.label} SELECTED` :
        invalid ? "MAP HAS CONFLICTS" : "MAP CLEAR";
      readout.dataset.status = terminal ? "passed" : notice || failedNotice ? "error" :
        submitting || selectedId ? "pending" : "idle";
    }

    function record(item) {
      events.push({seq: events.length + 1, ...item});
    }

    function clearFailureNotice() {
      notice = null;
      if (!failedNotice) return;
      failedNotice = false;
      verdict.hidden = true;
      root.classList.remove("ks-fresh-failure");
    }

    function moveProxy(vertexId, destination) {
      const before = [...positions.get(vertexId)];
      positions.set(vertexId, [...destination]);
      record({type: "vertex_move", vertex_id: vertexId, input_source: "proxy_click", before, after: [...destination]});
      selectedId = null; clearFailureNotice(); draw();
    }

    canvas.addEventListener("pointerdown", (event) => {
      if (!full || terminal || submitting || event.button !== 0) return;
      const point = pointFromEvent(event), vertexId = hitVertex(point);
      if (!vertexId) return;
      event.preventDefault();
      clearFailureNotice();
      drag = {pointerId: event.pointerId, vertexId, before: [...positions.get(vertexId)], path: [[...positions.get(vertexId)]]};
      canvas.setPointerCapture(event.pointerId);
      draw();
    });
    canvas.addEventListener("pointermove", (event) => {
      if (!drag || drag.pointerId !== event.pointerId) return;
      event.preventDefault();
      const point = pointFromEvent(event);
      positions.set(drag.vertexId, point);
      if (drag.path.length < 500) drag.path.push([...point]);
      draw();
    });
    canvas.addEventListener("pointerup", (event) => {
      if (!drag || drag.pointerId !== event.pointerId) return;
      event.preventDefault();
      const activeDrag = drag;
      const point = pointFromEvent(event);
      positions.set(activeDrag.vertexId, point);
      activeDrag.path.push([...point]);
      record({type: "vertex_move", vertex_id: activeDrag.vertexId, input_source: "direct_drag", before: activeDrag.before, after: [...point], path: activeDrag.path});
      drag = null;
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
      draw();
    });
    function cancelDrag() {
      if (!drag) return;
      const cancelled = drag;
      positions.set(cancelled.vertexId, [...cancelled.before]);
      drag = null;
      if (canvas.hasPointerCapture(cancelled.pointerId)) canvas.releasePointerCapture(cancelled.pointerId);
      draw();
    }
    canvas.addEventListener("pointercancel", cancelDrag);
    canvas.addEventListener("lostpointercapture", cancelDrag);

    canvas.addEventListener("click", (event) => {
      if (full || terminal || submitting) return;
      const point = pointOnCanvas(event);
      if (!selectedId) {
        const vertexId = hitVertex(point);
        if (!vertexId) return;
        selectedId = vertexId;
        record({type: "select", vertex_id: vertexId, input_source: "proxy_click"});
        clearFailureNotice();
        readout.textContent = `STAR ${vertices.find((item) => item.id === vertexId)?.label || ""} SELECTED · CHOOSE A DESTINATION`;
        readout.dataset.status = "pending";
        draw();
        return;
      }
      moveProxy(selectedId, point);
    });

    resetButton.addEventListener("click", () => {
      if (terminal || submitting) return;
      for (const [id, point] of initial) positions.set(id, [...point]);
      selectedId = null; drag = null; events.length = 0; clearFailureNotice();
      readout.textContent = "MAP RESTORED · FIND THE CROSSINGS"; readout.dataset.status = "idle"; draw();
    });
    root.querySelector(".ks-verdict-dismiss").addEventListener("click", () => { clearFailureNotice(); draw(); });

    async function submit(completed) {
      if (submitting || terminal) return;
      cancelDrag();
      notice = null; submitting = true; draw();
      readout.textContent = "CHECKING EMBEDDING…"; readout.dataset.status = "pending";
      const payload = {
        mechanic_id: MECHANIC,
        task_id: state.task_id,
        challenge_id: state.challenge_id,
        control_condition: state.control_condition || null,
        interaction_mode: mode,
        events,
        completed,
        reported_crossings: crossingIndices().length,
      };
      try {
        const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const outcome = await response.json();
        if (outcome.passed === true) {
          terminal = true; submitting = false;
          verdict.hidden = false; verdict.classList.add("is-pass");
          verdict.querySelector(".ks-verdict-title").textContent = "PASS";
          verdict.querySelector(".ks-verdict-copy").textContent = "A crossing-free embedding has been certified.";
          verdict.querySelector(".ks-verdict-dismiss").hidden = true;
          readout.textContent = "PASS · STAR MAP KNOTLESS"; readout.dataset.status = "passed"; draw();
        } else if (outcome.passed === false && outcome.state) {
          render(outcome.state, helpers, {failed: true});
        } else {
          submitting = false; notice = "FAIL · MAP REJECTED"; draw();
        }
      } catch (_error) {
        submitting = false; notice = "LINK UNAVAILABLE · RETRY"; draw();
      }
    }

    submitButton.addEventListener("click", () => submit(true));
    abandonButton.addEventListener("click", () => submit(false));
    draw();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC] = {rootSelector: ".ks-shell", render};
})();
