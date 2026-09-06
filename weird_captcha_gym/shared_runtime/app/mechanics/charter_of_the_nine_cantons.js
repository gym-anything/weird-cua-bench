(() => {
  "use strict";

  let model = null;
  let cleanup = null;
  const deep = (value) => JSON.parse(JSON.stringify(value));
  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"];
  const interaction = () => model.state.control_condition?.interaction || "full";
  const parcelMap = () => Object.fromEntries(model.parcels.map((parcel) => [parcel.id, parcel]));
  const brushRequirements = () => ({
    changes: Number(model.parameters.minimum_brush_changes ?? 2),
    path: Number(model.parameters.minimum_brush_path ?? 4),
  });

  function centroid(polygon) {
    return [
      polygon.reduce((sum, point) => sum + Number(point[0]), 0) / polygon.length,
      polygon.reduce((sum, point) => sum + Number(point[1]), 0) / polygon.length,
    ];
  }

  function connected(canton) {
    const members = new Set(Object.keys(model.assignment).filter((parcelId) => model.assignment[parcelId] === canton));
    if (!members.size) return false;
    const first = members.values().next().value; const seen = new Set([first]); const queue = [first];
    while (queue.length) {
      const current = queue.shift();
      (model.adjacency[current] || []).forEach((neighbor) => {
        if (members.has(neighbor) && !seen.has(neighbor)) { seen.add(neighbor); queue.push(neighbor); }
      });
    }
    return seen.size === members.size;
  }

  function evaluate() {
    const cantons = []; const seatSplit = Object.fromEntries(model.guilds.map((guild) => [guild.id, 0]));
    for (let canton = 0; canton < 9; canton += 1) {
      const members = Object.keys(model.assignment).filter((parcelId) => model.assignment[parcelId] === canton);
      const counts = Object.fromEntries(model.guilds.map((guild) => [guild.id, 0]));
      members.forEach((parcelId) => { counts[model.parties[parcelId]] += 1; });
      const ordered = Object.entries(counts).sort((left, right) => right[1] - left[1]);
      const winner = ordered.length && (ordered.length === 1 || ordered[0][1] > ordered[1][1]) ? ordered[0][0] : "tie";
      if (winner !== "tie") seatSplit[winner] += 1;
      cantons.push({
        id: canton,
        population: members.length,
        population_ok: Math.abs(members.length - model.idealPopulation) <= model.tolerance,
        connected: connected(canton),
        guild_counts: counts,
        winner,
      });
    }
    const completed = cantons.every((item) => item.population_ok && item.connected)
      && model.guilds.every((guild) => seatSplit[guild.id] === Number(model.targetSplit[guild.id]));
    return {cantons, seat_split: seatSplit, completed};
  }

  function sharedEdge(left, right) {
    const keys = new Map(left.map((point) => [`${Number(point[0]).toFixed(3)}:${Number(point[1]).toFixed(3)}`, point]));
    return right.filter((point) => keys.has(`${Number(point[0]).toFixed(3)}:${Number(point[1]).toFixed(3)}`));
  }

  function mapMarkup() {
    const parcels = parcelMap();
    const cells = model.parcels.map((parcel) => {
      const points = parcel.polygon.map((point) => point.join(",")).join(" ");
      const [x, y] = centroid(parcel.polygon); const selected = parcel.id === model.selectedParcel ? "is-selected" : "";
      return `<g class="cn-parcel ${selected}" data-parcel-group="${esc(parcel.id)}">
        <polygon data-parcel="${esc(parcel.id)}" points="${points}" style="--parcel-fill:${model.colors[model.assignment[parcel.id]]}" aria-label="Map parcel"></polygon>
        <g class="cn-house guild-${esc(parcel.guild)}" transform="translate(${x.toFixed(3)} ${y.toFixed(3)})" pointer-events="none"><path d="M-6 0 L0-6 L6 0 V6 H-6 Z"></path><rect x="-1.5" y="1" width="3" height="5"></rect></g>
      </g>`;
    }).join("");
    const seen = new Set(); const boundaries = [];
    Object.entries(model.adjacency).forEach(([parcelId, neighbors]) => {
      neighbors.forEach((neighbor) => {
        const key = [parcelId, neighbor].sort().join(":");
        if (seen.has(key)) return; seen.add(key);
        if (model.assignment[parcelId] === model.assignment[neighbor]) return;
        const edge = sharedEdge(parcels[parcelId].polygon, parcels[neighbor].polygon);
        if (edge.length >= 2) boundaries.push(`<line x1="${edge[0][0]}" y1="${edge[0][1]}" x2="${edge[1][0]}" y2="${edge[1][1]}"></line>`);
      });
    });
    const labels = [];
    for (let canton = 0; canton < 9; canton += 1) {
      const points = model.parcels.filter((parcel) => model.assignment[parcel.id] === canton).map((parcel) => centroid(parcel.polygon));
      if (!points.length) continue;
      const x = points.reduce((sum, point) => sum + point[0], 0) / points.length;
      const y = points.reduce((sum, point) => sum + point[1], 0) / points.length;
      labels.push(`<g class="cn-map-label" transform="translate(${x.toFixed(2)} ${y.toFixed(2)})"><circle r="18" style="--seal:${model.colors[canton]}"></circle><text y="5">${roman[canton]}</text></g>`);
    }
    return `<svg class="cn-map" viewBox="0 0 1000 600" preserveAspectRatio="none" role="application" aria-label="Irregular parcel map">
      <defs><filter id="cn-paper"><feTurbulence type="fractalNoise" baseFrequency=".025" numOctaves="2" seed="8" result="noise"/><feBlend in="SourceGraphic" in2="noise" mode="multiply"/></filter></defs>
      <g class="cn-parcels">${cells}</g><g class="cn-boundaries">${boundaries.join("")}</g><g class="cn-map-labels">${labels.join("")}</g>
      <rect class="cn-coast" x="2" y="2" width="996" height="596" rx="10"></rect>
    </svg>`;
  }

  function cantonPalette() {
    return roman.map((label, canton) => {
      const active = interaction() === "full" && model.brushCanton === canton ? "is-active" : "";
      return `<button class="cn-canton-row ${active}" data-canton-action="${canton}" aria-label="Canton ${label}" ${model.passed || model.submitting ? "disabled" : ""}>
        <i class="cn-canton-swatch" style="--seal:${model.colors[canton]}">${label}</i>
      </button>`;
    }).join("");
  }

  function toolCopy() {
    if (interaction() === "simplified") {
      return model.selectedParcel
        ? `<b>PARCEL SELECTED</b>`
        : `<b>NO PARCEL SELECTED</b>`;
    }
    return `<b>BRUSH ${roman[model.brushCanton]}</b>`;
  }

  function verdictMarkup() {
    if (model.passed) return `<div class="cn-verdict is-pass"><b>PASS</b></div>`;
    if (model.serverFailure) return `<div class="cn-verdict is-fail"><b>FAIL</b></div>`;
    return "";
  }

  function renderAll() {
    const root = document.querySelector(".nine-cantons"); if (!root) return;
    const stats = evaluate(); model.stats = stats;
    root.querySelector(".cn-map-slot").innerHTML = mapMarkup();
    root.querySelector(".cn-canton-list").innerHTML = cantonPalette();
    root.querySelector(".cn-tool-state").innerHTML = toolCopy();
    root.querySelector("#cn-undo").disabled = model.passed || model.submitting || !model.history.length;
    root.querySelector("#cn-certify").disabled = model.passed || model.submitting;
    root.querySelector(".cn-verdict-layer").innerHTML = verdictMarkup();
    bindMap(); bindPanel();
  }

  function updateDuringStroke() {
    model.stats = null;
  }

  function recordAssignment(parcelId, canton) {
    if (model.passed || model.submitting || model.spent >= Number(model.parameters.change_budget)) return;
    const from = model.assignment[parcelId]; if (from === canton) return;
    const before = deep(model.assignment);
    model.assignment[parcelId] = canton;
    model.history.push({assignment: before, cost: 1, qualifiedBrush: false});
    model.spent += 1;
    model.events.push({sequence: model.events.length + 1, type: "assign", parcel_id: parcelId, from_canton: from, to_canton: canton, input_source: "canton_proxy_button"});
    model.serverFailure = false; model.helpers.setReadout("", "idle"); renderAll();
  }

  function polygonAt(x, y) {
    const hit = document.elementFromPoint(x, y)?.closest?.("[data-parcel]");
    return hit?.dataset.parcel || null;
  }

  function brushParcel(parcelId) {
    const stroke = model.stroke; if (!stroke || !parcelId) return;
    const previous = stroke.path.at(-1);
    if (previous && previous !== parcelId && !(model.adjacency[previous] || []).includes(parcelId)) return;
    if (previous !== parcelId) stroke.path.push(parcelId);
    if (model.assignment[parcelId] === stroke.canton || stroke.changed.has(parcelId)) return;
    if (model.spent + stroke.changes.length >= Number(model.parameters.change_budget)) return;
    const from = model.assignment[parcelId]; model.assignment[parcelId] = stroke.canton; stroke.changed.add(parcelId);
    stroke.changes.push({parcel_id: parcelId, from_canton: from, to_canton: stroke.canton});
    const polygon = document.querySelector(`[data-parcel="${CSS.escape(parcelId)}"]`);
    if (polygon) polygon.style.setProperty("--parcel-fill", model.colors[stroke.canton]);
    updateDuringStroke();
  }

  function sampleBrush(x, y) {
    const stroke = model.stroke; if (!stroke) return;
    const distance = Math.hypot(x - stroke.lastX, y - stroke.lastY);
    const steps = Math.max(1, Math.ceil(distance / 6));
    for (let step = 1; step <= steps; step += 1) {
      const px = stroke.lastX + (x - stroke.lastX) * step / steps;
      const py = stroke.lastY + (y - stroke.lastY) * step / steps;
      brushParcel(polygonAt(px, py));
    }
    stroke.travel += distance; stroke.lastX = x; stroke.lastY = y; stroke.samples += 1;
  }

  function finishStroke(event, cancelled = false) {
    const stroke = model.stroke; if (!stroke || event.pointerId !== stroke.pointerId) return;
    sampleBrush(event.clientX, event.clientY);
    const map = document.querySelector(".cn-map"); const rect = map.getBoundingClientRect();
    const endParcel = stroke.path.at(-1);
    const valid = !cancelled && stroke.travel >= 8 && stroke.samples >= 1 && stroke.changes.length && endParcel && polygonAt(event.clientX, event.clientY) === endParcel;
    if (valid) {
      const requirements = brushRequirements();
      const qualifiedBrush = new Set(stroke.path).size >= requirements.path && stroke.changes.length >= requirements.changes;
      model.history.push({assignment: stroke.before, cost: stroke.changes.length, qualifiedBrush}); model.spent += stroke.changes.length;
      if (qualifiedBrush) model.qualifiedBrushes += 1;
      model.events.push({
        sequence: model.events.length + 1, type: "stroke", brush_canton: stroke.canton,
        path: stroke.path, changes: stroke.changes, input_source: "map_brush_drag",
        gesture: {
          start_u: Math.max(0, Math.min(1, (stroke.startX - rect.left) / rect.width)),
          start_v: Math.max(0, Math.min(1, (stroke.startY - rect.top) / rect.height)),
          end_u: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
          end_v: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
          travel_px: Number(stroke.travel.toFixed(3)), sample_count: stroke.samples,
        },
      });
      model.serverFailure = false; model.helpers.setReadout("", "idle");
    } else {
      model.assignment = stroke.before;
    }
    model.stroke = null; renderAll();
  }

  function bindMap() {
    const map = document.querySelector(".cn-map"); if (!map) return;
    if (interaction() === "simplified") {
      map.querySelectorAll("[data-parcel]").forEach((polygon) => polygon.addEventListener("click", () => {
        if (model.passed || model.submitting) return;
        model.selectedParcel = polygon.dataset.parcel; renderAll();
      }));
      return;
    }
    map.querySelectorAll("[data-parcel]").forEach((polygon) => polygon.addEventListener("pointerdown", (event) => {
      if (model.passed || model.submitting || model.spent >= Number(model.parameters.change_budget) || event.button !== 0) return;
      event.preventDefault(); map.setPointerCapture?.(event.pointerId);
      model.stroke = {
        pointerId: event.pointerId, canton: model.brushCanton, before: deep(model.assignment),
        startX: event.clientX, startY: event.clientY, lastX: event.clientX, lastY: event.clientY,
        travel: 0, samples: 0, path: [], changes: [], changed: new Set(),
      };
      brushParcel(polygon.dataset.parcel);
    }));
    map.addEventListener("pointermove", (event) => { if (model.stroke?.pointerId === event.pointerId) sampleBrush(event.clientX, event.clientY); });
    map.addEventListener("pointerup", (event) => finishStroke(event));
    map.addEventListener("pointercancel", (event) => finishStroke(event, true));
  }

  function bindPanel() {
    document.querySelectorAll("[data-canton-action]").forEach((button) => button.addEventListener("click", () => {
      const canton = Number(button.dataset.cantonAction);
      if (interaction() === "simplified") {
        if (model.selectedParcel) recordAssignment(model.selectedParcel, canton);
      } else {
        model.brushCanton = canton; renderAll();
      }
    }));
  }

  function undo() {
    if (model.passed || model.submitting || !model.history.length) return;
    const previous = model.history.pop(); model.assignment = previous.assignment; model.spent -= previous.cost;
    if (previous.qualifiedBrush) model.qualifiedBrushes -= 1;
    model.events.push({sequence: model.events.length + 1, type: "undo", input_source: "undo_button"});
    model.serverFailure = false; model.helpers.setReadout("", "idle"); renderAll();
  }

  async function submit() {
    if (!model || model.submitting || model.passed) return;
    const current = model; current.submitting = true; renderAll();
    try {
      const stats = evaluate();
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({
        mechanic_id: current.state.mechanic_id, task_id: current.state.task_id, challenge_id: current.state.challenge_id,
        interaction_mode: interaction(), events: current.events, final_assignment: current.assignment,
        metrics: stats, completed: stats.completed,
      })});
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.passed = true; current.submitting = false; renderAll(); current.helpers.setReadout("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        const helpers = current.helpers; await render(outcome.state, helpers, {serverFailure: true}); model.helpers.setReadout("FAIL", "error");
      } else {
        current.submitting = false; current.serverFailure = true; renderAll(); current.helpers.setReadout("FAIL", "error");
      }
    } catch (_error) {
      if (model === current) { current.submitting = false; current.serverFailure = true; renderAll(); current.helpers.setReadout("FAIL", "error"); }
    }
  }

  async function render(state, helpers, options = {}) {
    cleanup?.(); document.body.dataset.mechanic = "charter-of-the-nine-cantons";
    model = {
      state, helpers, parcels: deep(state.parcels), adjacency: deep(state.adjacency), assignment: deep(state.initial_assignment),
      guilds: deep(state.guilds), colors: deep(state.canton_colors), targetSplit: deep(state.target_seat_split),
      parameters: deep(state.parameters), idealPopulation: Number(state.ideal_population), tolerance: Number(state.population_tolerance),
      parties: Object.fromEntries(state.parcels.map((parcel) => [parcel.id, parcel.guild])),
      events: [], history: [], spent: 0, qualifiedBrushes: 0, brushCanton: 0, selectedParcel: null, stroke: null,
      passed: false, submitting: false, serverFailure: Boolean(options.serverFailure), stats: null,
    };
    const populationRule = model.tolerance === 0
      ? `POP EXACTLY ${model.idealPopulation}`
      : `POP ${model.idealPopulation - model.tolerance}–${model.idealPopulation + model.tolerance}`;
    const requirements = brushRequirements();
    const brushRule = interaction() === "full"
      ? ` · BRUSH ${requirements.path}+ JOINED / ${requirements.changes}+ REPAINTED`
      : "";
    helpers.app.innerHTML = `<section class="nine-cantons mode-${interaction()}" data-interaction="${interaction()}" data-mechanic="${esc(state.mechanic_id)}" data-challenge-id="${esc(state.challenge_id)}" data-fresh-failure="${options.serverFailure ? "true" : "false"}">
      <header class="cn-masthead"><div class="cn-title"><small>OFFICE OF THE CADASTRE</small><h1>${esc(state.prompt)}</h1><p>NINE CONNECTED · ${populationRule} · 5 GILT / 2 TIDE / 2 PLUM · ${model.parameters.change_budget} CHANGES MAX${brushRule}</p></div></header>
      <main><section class="cn-atlas"><div class="cn-map-slot"></div><div class="cn-map-legend"><span><i class="guild-gilt"></i>GILT HOUSE</span><span><i class="guild-tide"></i>TIDE HOUSE</span><span><i class="guild-plum"></i>PLUM HOUSE</span></div></section>
      <aside class="cn-ledger"><header><small>CANTON SEALS</small></header><div class="cn-canton-list"></div><div class="cn-tool-state"></div></aside></main>
      <footer><div></div><div class="cn-actions"><strong class="readout" data-status="idle"></strong><button id="cn-undo">UNDO</button><button id="cn-certify">CERTIFY CHARTER</button></div></footer>
      <div class="cn-verdict-layer"></div>${helpers.cheatPanelTemplate()}
    </section>`;
    document.getElementById("cn-undo")?.addEventListener("click", undo);
    document.getElementById("cn-certify")?.addEventListener("click", submit);
    renderAll(); helpers.installCheatPanel(); cleanup = () => { model = null; };
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.charter_of_the_nine_cantons = {rootSelector: ".nine-cantons", render};
})();
