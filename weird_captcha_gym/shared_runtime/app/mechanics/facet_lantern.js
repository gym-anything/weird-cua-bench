(() => {
  "use strict";
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};

  const TAU = Math.PI * 2;
  const esc = (value) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;", "'":"&#39;"}[char]));
  const norm = (value) => ((Number(value) % 360) + 360) % 360;
  const edgeKey = (a, b) => [String(a), String(b)].sort().join("|");

  function project(vertex, yaw, width, height) {
    const radians = Number(yaw) * Math.PI / 180;
    const x = Number(vertex.x || 0);
    const y = Number(vertex.y || 0);
    const z = Number(vertex.z || 0);
    const rotatedX = x * Math.cos(radians) - z * Math.sin(radians);
    const depth = x * Math.sin(radians) + z * Math.cos(radians);
    return {x: width / 2 + rotatedX * 150, y: height / 2 - y * 150, depth};
  }

  function visible(vertex, yaw, world) {
    return project(vertex, yaw, 920, 560).depth >= -Number(world.occlusion_band ?? 0.25) - 1e-7;
  }

  function score(state, connections) {
    const targets = state.targets || [];
    let complete = 0;
    let polygonPoints = 0;
    targets.forEach((target) => {
      const ids = target.vertices || [];
      const needed = ids.map((id, index) => edgeKey(id, ids[(index + 1) % ids.length]));
      if (needed.every((edge) => connections.has(edge))) {
        complete += 1;
        polygonPoints += ids.length * 10;
      }
    });
    const degree = new Map((state.world.vertices || []).map((vertex) => [String(vertex.id), 0]));
    connections.forEach((edge) => {
      const [first, second] = edge.split("|");
      degree.set(first, (degree.get(first) || 0) + 1);
      degree.set(second, (degree.get(second) || 0) + 1);
    });
    const isolated = Array.from(degree.values()).filter((value) => value === 0).length;
    return {value: connections.size * 10 + polygonPoints - isolated, complete, isolated};
  }

  function render(state, helpers) {
    const app = helpers.app;
    const interaction = state.control_condition?.interaction || state.interaction || "full";
    const world = state.world || {};
    const vertices = world.vertices || [];
    const byId = new Map(vertices.map((vertex) => [String(vertex.id), vertex]));
    const model = {
      state,
      helpers,
      interaction,
      yaw: Number(world.initial_yaw || 0),
      connections: new Set((world.connections || []).map((edge) => edgeKey(edge[0], edge[1]))),
      selected: null,
      events: [],
      drag: null,
      submitting: false,
    };

    document.body.dataset.mechanic = "facet-lantern";
    document.body.dataset.cheatMode = helpers.isCheatMode?.() ? "true" : "false";
    app.innerHTML = `
      <section class="fl-shell" data-interaction="${esc(interaction)}" data-challenge-id="${esc(state.challenge_id)}">
        <header class="fl-header">
          <div><p class="fl-kicker">OPTICAL COMMISSION / FACET LANTERN</p><h1>Close the lantern’s requested facets.</h1><p class="fl-prompt">${esc(state.prompt)}</p></div>
          <div class="fl-score" aria-live="polite"><span>SCORE</span><strong class="fl-score-value">0</strong><small>target <b>${esc(state.target_score)}</b></small></div>
        </header>
        <main class="fl-main">
          <section class="fl-stage-card">
            <div class="fl-stage-top"><span class="fl-mode">${interaction === "full" ? "DIRECT POINTER / DRAG TO TURN" : "PROXY TURN / BUTTON CONTROL"}</span><span class="fl-angle">YAW <b>0°</b></span></div>
            <div class="fl-stage-wrap"><svg class="fl-stage" viewBox="0 0 920 560" role="application" aria-label="Rotatable three-dimensional facet lantern"></svg><div class="fl-stage-caption">Each glowing stud keeps its letter when the lantern turns. Pale studs are behind the solid.</div></div>
          </section>
          <aside class="fl-sidebar">
            <section class="fl-brief"><p class="fl-section-label">REQUESTED OUTLINES</p><div class="fl-target-list"></div></section>
            <section class="fl-controls"><p class="fl-section-label">TURN THE SOLID</p><div class="fl-turns"${interaction === "full" ? " hidden aria-hidden=\"true\"" : ""}><button type="button" class="fl-turn-left" aria-label="Turn lantern left">← LEFT</button><button type="button" class="fl-turn-right" aria-label="Turn lantern right">RIGHT →</button></div><p class="fl-hint">${interaction === "full" ? "Hold on an empty part of the solid and drag left or right." : `Each button turns the solid ${esc(world.rotation_step_degrees)} degrees.`}</p></section>
            <section class="fl-ledger"><p class="fl-section-label">CONNECTION LEDGER</p><div class="fl-selection" aria-live="polite">Choose a glowing stud.</div><div class="fl-live-stats"><span><b class="fl-complete-count">0</b> / ${esc((state.targets || []).length)} facets closed</span><span><b class="fl-connection-count">${esc(model.connections.size)}</b> connections</span></div></section>
            <div class="fl-actions"><button type="button" class="fl-clear" disabled>CANCEL STUD</button><button type="button" class="fl-abandon">ABANDON ATTEMPT</button><button type="button" class="fl-submit">${esc(state.submit_label || "CERTIFY LANTERN")}</button></div>
            <div class="readout fl-readout" data-status="idle">TURN THE LANTERN TO FIND THE LABELLED STUDS.</div>
          </aside>
        </main>
      </section>`;

    const shell = app.querySelector(".fl-shell");
    const svg = app.querySelector(".fl-stage");
    const readout = app.querySelector(".fl-readout");
    const scoreValue = app.querySelector(".fl-score-value");
    const angleValue = app.querySelector(".fl-angle b");
    const selection = app.querySelector(".fl-selection");
    const clearButton = app.querySelector(".fl-clear");
    const submitButton = app.querySelector(".fl-submit");
    const abandonButton = app.querySelector(".fl-abandon");

    function say(message, status = "idle") {
      if (readout) {
        readout.dataset.status = status;
        readout.textContent = message;
      }
    }

    function projectedMap() {
      return new Map(vertices.map((vertex) => [String(vertex.id), project(vertex, model.yaw, 920, 560)]));
    }

    function addEvent(event) {
      model.events.push({...event, seq: model.events.length + 1});
    }

    function updateLedger() {
      const current = score(state, model.connections);
      scoreValue.textContent = String(current.value);
      angleValue.textContent = `${Math.round(model.yaw)}°`;
      app.querySelector(".fl-complete-count").textContent = String(current.complete);
      app.querySelector(".fl-connection-count").textContent = String(model.connections.size);
      selection.textContent = model.selected ? `STUD ${byId.get(model.selected)?.label || model.selected} SELECTED · CHOOSE ITS NEIGHBOUR` : "Choose a glowing stud.";
      clearButton.disabled = !model.selected;
      shell.dataset.yaw = String(Math.round(model.yaw));
      shell.dataset.score = String(current.value);
    }

    function targetDone(target) {
      const ids = target.vertices || [];
      return ids.every((id, index) => model.connections.has(edgeKey(id, ids[(index + 1) % ids.length])));
    }

    function renderTargets() {
      app.querySelector(".fl-target-list").innerHTML = (state.targets || []).map((target) => `
        <div class="fl-target ${targetDone(target) ? "is-done" : ""}" data-target-id="${esc(target.id)}"><span class="fl-target-light"></span><b>${esc(target.id)}</b><span>${(target.vertices || []).map((id) => esc(byId.get(id)?.label || id)).join(" · ")}</span><em>${targetDone(target) ? "CLOSED" : "OPEN"}</em></div>`).join("");
    }

    function renderScene() {
      const projected = projectedMap();
      const faces = (world.faces || []).map((ids, index) => ({ids, index, depth: ids.reduce((sum, id) => sum + (projected.get(String(id))?.depth || 0), 0) / Math.max(1, ids.length)})).sort((a, b) => a.depth - b.depth);
      const faceMarkup = faces.map((face) => {
        const points = face.ids.map((id) => { const point = projected.get(String(id)); return `${point.x.toFixed(1)},${point.y.toFixed(1)}`; }).join(" ");
        const opacity = face.depth > -0.06 ? 0.42 : 0.08;
        const palette = ["#ffbd68", "#86e0cb", "#b49bff", "#ff8ca8", "#65b9ff", "#edda7e"];
        return `<polygon class="fl-face" points="${points}" fill="${palette[face.index % palette.length]}" opacity="${opacity}"/>`;
      }).join("");
      const edgeSet = new Set();
      const edgeMarkup = [];
      (world.faces || []).forEach((ids) => ids.forEach((id, index) => {
        const key = edgeKey(id, ids[(index + 1) % ids.length]);
        if (edgeSet.has(key)) return;
        edgeSet.add(key);
        const [first, second] = key.split("|");
        const a = projected.get(first); const b = projected.get(second);
        edgeMarkup.push(`<line class="fl-wire" x1="${a.x.toFixed(1)}" y1="${a.y.toFixed(1)}" x2="${b.x.toFixed(1)}" y2="${b.y.toFixed(1)}"/>`);
      }));
      const connectionMarkup = Array.from(model.connections).map((key) => {
        const [first, second] = key.split("|"); const a = projected.get(first); const b = projected.get(second);
        return `<line class="fl-connection" data-edge="${esc(key)}" x1="${a.x.toFixed(1)}" y1="${a.y.toFixed(1)}" x2="${b.x.toFixed(1)}" y2="${b.y.toFixed(1)}"/>`;
      }).join("");
      const studMarkup = vertices.map((vertex) => {
        const id = String(vertex.id); const point = projected.get(id); const isVisible = visible(vertex, model.yaw, world); const isSelected = model.selected === id;
        return `<g class="fl-stud ${isSelected ? "is-selected" : ""}" data-vertex-id="${esc(id)}" data-visible="${isVisible ? "true" : "false"}" style="display:${isVisible ? "" : "none"}" transform="translate(${point.x.toFixed(1)} ${point.y.toFixed(1)})" tabindex="0" role="button" aria-label="Stud ${esc(vertex.label)}"><circle class="fl-stud-halo" r="${isSelected ? 22 : 17}"/><circle class="fl-stud-dot" r="${isSelected ? 10 : 8}"/><text y="-18">${esc(vertex.label)}</text></g>`;
      }).join("");
      svg.innerHTML = `<defs><radialGradient id="fl-glow"><stop offset="0" stop-color="#fff4c2"/><stop offset="0.45" stop-color="#ffcf70"/><stop offset="1" stop-color="#db7a4e"/></radialGradient><filter id="fl-shadow"><feGaussianBlur stdDeviation="3"/></filter></defs><ellipse class="fl-shadow" cx="460" cy="490" rx="210" ry="22"/><g class="fl-solid">${faceMarkup}${edgeMarkup.join("")}${connectionMarkup}</g><g class="fl-studs">${studMarkup}</g>`;
      svg.querySelectorAll(".fl-stud").forEach((node) => {
        const activate = (event) => { event.preventDefault(); event.stopPropagation(); handleVertex(String(node.dataset.vertexId)); };
        node.addEventListener("click", activate);
        node.addEventListener("pointerdown", (event) => event.stopPropagation());
        node.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") activate(event); });
      });
      updateLedger();
      renderTargets();
    }

    function rotateBy(delta, source, extra = {}) {
      if (model.submitting) return;
      if (source === "direct_pointer" && model.interaction !== "full") return;
      if (source === "proxy_button" && model.interaction !== "simplified") return;
      const before = model.yaw; const after = norm(before + delta);
      model.yaw = after;
      addEvent({type: "rotate", input_source: source, from_yaw: before, to_yaw: after, delta, ...extra});
      renderScene();
      say(`YAW ${Math.round(after)}° · INSPECT THE NEWLY EXPOSED STUDS.`);
    }

    function handleVertex(id) {
      if (model.submitting || !byId.has(id)) return;
      if (!visible(byId.get(id), model.yaw, world)) { say("THAT STUD IS BEHIND THE SOLID.", "error"); return; }
      if (!model.selected) {
        model.selected = id;
        addEvent({type: "select_vertex", input_source: "vertex_click", vertex_id: id});
        renderScene();
        say(`STUD ${byId.get(id).label} SELECTED · CLICK A NEIGHBOUR TO CONNECT.`);
        return;
      }
      if (model.selected === id) return;
      const edge = edgeKey(model.selected, id);
      if (model.connections.has(edge)) { say("THAT CONNECTION ALREADY EXISTS.", "error"); return; }
      const first = model.selected;
      model.connections.add(edge);
      addEvent({type: "connect", input_source: "vertex_click", vertex_id: id, from_vertex_id: first});
      model.selected = null;
      renderScene();
      say(`CONNECTED ${byId.get(first).label} ↔ ${byId.get(id).label}.`);
    }

    function beginPointer(event) {
      if (model.interaction !== "full" || event.target.closest?.(".fl-stud")) return;
      model.drag = {startX: event.clientX, lastX: event.clientX, before: model.yaw, moved: false, path: [[event.clientX, event.clientY]]};
      svg.setPointerCapture?.(event.pointerId);
    }

    function movePointer(event) {
      if (!model.drag) return;
      const drag = model.drag; const dx = event.clientX - drag.startX;
      drag.lastX = event.clientX; drag.path.push([event.clientX, event.clientY]);
      if (Math.abs(dx) > 3) drag.moved = true;
      model.yaw = norm(drag.before + dx * 0.55);
      renderScene();
    }

    function finishPointer(event) {
      if (!model.drag) return;
      const drag = model.drag; model.drag = null;
      svg.releasePointerCapture?.(event.pointerId);
      const delta = ((model.yaw - drag.before + 180) % 360 + 360) % 360 - 180;
      if (drag.moved && Math.abs(delta) >= 1) {
        addEvent({type: "rotate", input_source: "direct_pointer", from_yaw: drag.before, to_yaw: model.yaw, delta, path: drag.path.slice()});
        say(`YAW ${Math.round(model.yaw)}° · INSPECT THE NEWLY EXPOSED STUDS.`);
      } else {
        model.yaw = drag.before;
        renderScene();
      }
    }

    function clearSelection() {
      if (!model.selected) return;
      addEvent({type: "clear_selection", input_source: "vertex_click", vertex_id: model.selected});
      model.selected = null; renderScene(); say("SELECTION CLEARED.");
    }

    async function postResult(completed) {
      if (model.submitting) return;
      model.submitting = true; submitButton.disabled = true; abandonButton.disabled = true; clearButton.disabled = true;
      addEvent({type: "submit", input_source: "certify_button", completed});
      const current = score(state, model.connections);
      const payload = {mechanic_id: state.mechanic_id, task_id: state.task_id, challenge_id: state.challenge_id, control_condition: state.control_condition, events: model.events, connections: Array.from(model.connections).map((key) => key.split("|")), completed, reported_score: current.value};
      try {
        const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
        const outcome = await response.json();
        if (outcome.passed === true) { helpers.setReadout("PASS", "passed"); submitButton.disabled = true; return; }
        if (outcome.state) { render(outcome.state, helpers); helpers.setReadout("FAIL · NEW LANTERN READY", "error"); return; }
        model.submitting = false; submitButton.disabled = false; abandonButton.disabled = false; say("FAIL · KEEP WORKING ON THE OPEN FACETS.", "error");
      } catch (_error) {
        model.submitting = false; submitButton.disabled = false; abandonButton.disabled = false; say("LINK UNAVAILABLE · RETRY.", "error");
      }
    }

    app.querySelector(".fl-turn-left").addEventListener("click", () => rotateBy(-Number(world.rotation_step_degrees || 15), "proxy_button", {direction: "left"}));
    app.querySelector(".fl-turn-right").addEventListener("click", () => rotateBy(Number(world.rotation_step_degrees || 15), "proxy_button", {direction: "right"}));
    clearButton.addEventListener("click", clearSelection);
    submitButton.addEventListener("click", () => postResult(true));
    abandonButton.addEventListener("click", () => postResult(false));
    svg.addEventListener("pointerdown", beginPointer);
    svg.addEventListener("pointermove", movePointer);
    svg.addEventListener("pointerup", finishPointer);
    svg.addEventListener("pointercancel", finishPointer);
    renderScene();
    say(interaction === "full" ? "DRAG THE SOLID, THEN CLICK A GLOWING STUD." : "USE LEFT OR RIGHT TURN, THEN CLICK A GLOWING STUD.");
  }

  window.WeirdCaptchaMechanics.facet_lantern = {rootSelector: ".fl-shell", render};
})();
