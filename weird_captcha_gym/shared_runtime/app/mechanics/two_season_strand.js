(() => {
  "use strict";

  const SEASONS = ["spring", "winter"];
  const model = {
    state: null,
    sequence: [],
    edits: [],
    editCount: 0,
    brush: 0,
    drag: null,
    activeSeason: "spring",
    interaction: "full",
    terminal: false,
    busy: false,
    ready: false,
    helpers: null,
  };

  const clean = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
  const pairKey = (pair) => `${pair[0]}:${pair[1]}`;
  const clonePairs = (pairs) => (pairs || []).map((pair) => [...pair]);

  function fold(sequence, order) {
    const stacks = {0: [], 1: []};
    const pairs = [];
    order.forEach((index) => {
      const color = sequence[index];
      if (color === 0 || color === 1) {
        stacks[color].push(index);
      } else {
        const opener = color === 2 ? 1 : 0;
        if (stacks[opener].length) {
          pairs.push([stacks[opener].pop(), index].sort((left, right) => left - right));
        }
      }
    });
    return pairs.sort((left, right) => left[0] - right[0] || left[1] - right[1]);
  }

  function currentFolds() {
    return Object.fromEntries(SEASONS.map((season) => [
      season,
      fold(model.sequence, model.state.season_orders[season]),
    ]));
  }

  function pairProgress() {
    const folds = currentFolds();
    return Object.fromEntries(SEASONS.map((season) => {
      const target = new Set(model.state.target_pairs[season].map(pairKey));
      const matched = folds[season].filter((pair) => target.has(pairKey(pair))).length;
      return [season, {paired: folds[season].length, matched, target: target.size}];
    }));
  }

  function isExact() {
    const folds = currentFolds();
    return SEASONS.every((season) => JSON.stringify(folds[season]) === JSON.stringify(model.state.target_pairs[season]));
  }

  function layout(season) {
    const order = model.state.season_orders[season];
    const result = {};
    order.forEach((index, rank) => {
      const angle = -Math.PI / 2 + (rank / order.length) * Math.PI * 2;
      if (season === "spring") {
        const radiusX = 158 + 24 * Math.sin(angle * 3);
        const radiusY = 108 + 9 * Math.cos(angle * 2);
        result[index] = {
          x: 260 + radiusX * Math.cos(angle),
          y: 143 + radiusY * Math.sin(angle),
        };
      } else {
        const radius = 112 + 24 * Math.cos(angle * 6);
        result[index] = {
          x: 260 + radius * Math.cos(angle),
          y: 143 + radius * Math.sin(angle),
        };
      }
    });
    return result;
  }

  function edgeMarkup(pair, positions, className) {
    const left = positions[pair[0]];
    const right = positions[pair[1]];
    const bend = Math.min(44, Math.hypot(right.x - left.x, right.y - left.y) * 0.14);
    const midpointX = (left.x + right.x) / 2;
    const midpointY = (left.y + right.y) / 2;
    const towardCenterX = (260 - midpointX) * 0.34;
    const towardCenterY = (143 - midpointY) * 0.34;
    const controlX = midpointX + towardCenterX + bend * 0.04;
    const controlY = midpointY + towardCenterY;
    return `<path class="${className}" d="M ${left.x.toFixed(2)} ${left.y.toFixed(2)} Q ${controlX.toFixed(2)} ${controlY.toFixed(2)} ${right.x.toFixed(2)} ${right.y.toFixed(2)}" />`;
  }

  function foldMarkup(season) {
    const positions = layout(season);
    const current = currentFolds()[season];
    const target = model.state.target_pairs[season];
    const currentKeys = new Set(current.map(pairKey));
    const targetKeys = new Set(target.map(pairKey));
    const mismatchNodes = new Set();
    current.filter((pair) => !targetKeys.has(pairKey(pair))).forEach((pair) => pair.forEach((index) => mismatchNodes.add(index)));
    target.filter((pair) => !currentKeys.has(pairKey(pair))).forEach((pair) => pair.forEach((index) => mismatchNodes.add(index)));
    const guidance = model.state.parameters.blueprint_guidance;
    const labelStride = Number(model.state.parameters.index_label_stride || 4);
    const order = model.state.season_orders[season];
    const backbone = order.map((index) => `${positions[index].x.toFixed(2)},${positions[index].y.toFixed(2)}`).join(" ");
    const blueprintEdges = target.map((pair) => edgeMarkup(pair, positions, currentKeys.has(pairKey(pair)) ? "fold-edge blueprint matched" : "fold-edge blueprint missing")).join("");
    const liveEdges = current.map((pair) => edgeMarkup(pair, positions, targetKeys.has(pairKey(pair)) ? "fold-edge live matched" : "fold-edge live extra")).join("");
    const nodes = order.map((index, rank) => {
      const point = positions[index];
      const color = model.state.palette[model.sequence[index]];
      const mismatch = mismatchNodes.has(index);
      const showLabel = index % labelStride === 0 || (mismatch && guidance !== "sparse") || (guidance === "strong" && rank % 2 === 0);
      return `<g class="fold-node${mismatch ? " is-mismatch" : ""}" transform="translate(${point.x.toFixed(2)} ${point.y.toFixed(2)})">
        <circle r="${mismatch ? 6.2 : 4.5}" fill="${clean(color.color)}" />
        ${showLabel ? `<text x="7" y="-5">${index + 1}</text>` : ""}
      </g>`;
    }).join("");
    const matchedCount = current.filter((pair) => targetKeys.has(pairKey(pair))).length;
    return `
      <article id="strand-panel-${season}" class="season-card season-${season}" data-season="${season}" role="tabpanel" aria-labelledby="strand-tab-${season}">
        <header><div><small>${season === "spring" ? "I · OUTWARD READING" : "II · BRAIDED READING"}</small><h2>${season.toUpperCase()}</h2></div><strong>${matchedCount}<i>/ ${target.length}</i></strong></header>
        <svg class="fold-map" viewBox="0 0 520 286" role="img" aria-label="${season} current fold over target blueprint">
          <polyline class="fold-backbone" points="${backbone}" />
          <g class="blueprint-layer">${blueprintEdges}</g>
          <g class="live-layer">${liveEdges}</g>
          <g class="node-layer">${nodes}</g>
        </svg>
        <footer><span><i class="legend-line target"></i>GHOST BLUEPRINT</span><span><i class="legend-line live"></i>CURRENT STEM</span><span><i class="legend-line wrong"></i>DISPLACED</span></footer>
      </article>`;
  }

  function seasonTabsMarkup() {
    const progress = pairProgress();
    return `<nav class="strand-season-tabs" role="tablist" aria-label="Season fold views">
      ${SEASONS.map((season, position) => {
        const active = model.activeSeason === season;
        const tally = progress[season];
        return `<button type="button" id="strand-tab-${season}" class="strand-season-tab season-${season}${active ? " is-active" : ""}" data-season-tab="${season}" role="tab" aria-selected="${active}" aria-controls="strand-panel-${season}" tabindex="${active ? "0" : "-1"}">
          <small>${position === 0 ? "I · OUTWARD" : "II · BRAIDED"}</small>
          <strong>${season.toUpperCase()}</strong>
          <span>${tally.matched}/${tally.target} STEMS</span>
        </button>`;
      }).join("")}
      <p>SWITCH VIEWS TO CHECK BOTH READINGS</p>
    </nav>`;
  }

  function beadMarkup(colorIndex, index) {
    const color = model.state.palette[colorIndex];
    return `<button type="button" class="strand-bead" data-index="${index}" data-color="${colorIndex}" style="--bead:${clean(color.color)}" aria-label="bead ${index + 1}, ${clean(color.name)}">
      <span>${clean(color.short)}</span><small>${index + 1}</small>
    </button>`;
  }

  function strandMarkup() {
    return model.sequence.map(beadMarkup).join("");
  }

  function paletteMarkup() {
    return model.state.palette.map((color) => `
      <button type="button" class="strand-swatch${model.brush === color.id ? " is-active" : ""}" data-palette-color="${color.id}" style="--swatch:${clean(color.color)}">
        <i></i><span>${clean(color.name)}</span><b>${clean(color.short)}</b>
      </button>`).join("");
  }

  function refresh() {
    const folds = document.getElementById("strand-folds");
    const strand = document.getElementById("strand-ribbon");
    const palette = document.getElementById("strand-palette");
    if (folds) folds.innerHTML = seasonTabsMarkup() + foldMarkup(model.activeSeason);
    if (strand) strand.innerHTML = strandMarkup();
    if (palette) palette.innerHTML = paletteMarkup();
    bindControls();
    const remaining = document.getElementById("strand-edits-left");
    if (remaining) remaining.textContent = String(Number(model.state.parameters.edit_budget) - model.editCount);
    model.ready = isExact();
    const seal = document.getElementById("strand-seal");
    seal?.classList.toggle("is-ready", model.ready);
    document.querySelector(".two-season-strand")?.classList.toggle("is-ready", model.ready);
  }

  function clearFreshFailure() {
    document.querySelector(".strand-verdict-fail")?.remove();
    document.querySelector(".two-season-strand")?.classList.remove("is-fresh-fail");
  }

  async function submit(completed) {
    if (model.busy || model.terminal) return;
    model.busy = true;
    document.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    model.helpers.setReadout("CHECKING BOTH SEASONS…", "pending");
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      interaction_mode: model.interaction,
      edits: model.edits,
      events: model.edits,
      final_sequence: [...model.sequence],
      folds: currentFolds(),
      edit_count: model.editCount,
      completed,
    };
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify(payload),
      });
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true;
        document.querySelector(".two-season-strand")?.classList.add("is-pass");
        document.querySelector(".two-season-strand")?.insertAdjacentHTML("beforeend", '<div class="strand-verdict strand-verdict-pass"><small>DUAL FOLD ACCEPTED</small><strong>PASS</strong></div>');
        model.helpers.setReadout("PASS · BOTH SEASONS HOLD", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        const shell = document.querySelector(".two-season-strand");
        shell?.classList.add("is-fresh-fail");
        shell?.insertAdjacentHTML("beforeend", '<div class="strand-verdict strand-verdict-fail"><small>FOLD REJECTED · FRESH STRAND</small><strong>FAIL</strong></div>');
        model.helpers.setReadout("FAIL · FRESH STRAND ISSUED", "error");
      } else {
        model.busy = false;
        document.querySelectorAll("button").forEach((button) => { button.disabled = false; });
        model.helpers.setReadout("FAIL · FOLD SERVICE OFFLINE", "error");
      }
    } catch (_error) {
      model.busy = false;
      document.querySelectorAll("button").forEach((button) => { button.disabled = false; });
      model.helpers.setReadout("FAIL · FOLD SERVICE OFFLINE", "error");
    }
  }

  function applyColor(indices, color, inputSource, gesture = null) {
    if (model.busy || model.terminal) return;
    clearFreshFailure();
    const changed = indices.filter((index) => model.sequence[index] !== color);
    if (!changed.length) {
      model.helpers.setReadout("NO CHANGE · THAT COLOUR IS ALREADY SET", "idle");
      return;
    }
    const projected = model.editCount + changed.length;
    if (projected > Number(model.state.parameters.edit_budget)) {
      document.querySelector(".two-season-strand")?.insertAdjacentHTML("beforeend", '<div class="strand-verdict strand-verdict-fail strand-verdict-snap"><small>EDIT ALLOWANCE EXHAUSTED</small><strong>SNAP</strong></div>');
      model.helpers.setReadout("THREAD SNAP · EDIT ALLOWANCE EXCEEDED", "error");
      void submit(false);
      return;
    }
    indices.forEach((index) => { model.sequence[index] = color; });
    model.editCount = projected;
    const event = {
      sequence: model.edits.length + 1,
      indices: [...indices],
      color,
      changed_count: changed.length,
      input_source: inputSource,
      pair_progress_after: pairProgress(),
    };
    if (gesture) event.gesture = gesture;
    model.edits.push(event);
    refresh();
    document.querySelectorAll(".season-card").forEach((card) => {
      card.classList.remove("is-refolding");
      void card.offsetWidth;
      card.classList.add("is-refolding");
    });
    const progress = pairProgress();
    if (model.ready) {
      model.helpers.setReadout(`BOTH SEASONS HOLD · ${model.editCount} EDITS · SEAL IT`, "passed");
    } else {
      model.helpers.setReadout(`REFOLDED · SPRING ${progress.spring.matched}/${progress.spring.target} · WINTER ${progress.winter.matched}/${progress.winter.target}`, "idle");
    }
  }

  function paintSimplified(index) {
    if (model.interaction !== "simplified" || model.busy || model.terminal) return;
    applyColor([index], model.brush, "palette_apply");
  }

  function chooseSeason(season) {
    if (!SEASONS.includes(season) || season === model.activeSeason || model.busy || model.terminal) return;
    model.activeSeason = season;
    refresh();
    model.helpers.setReadout(`${season.toUpperCase()} VIEW · CHECK THE LIVE FOLD AGAINST ITS GHOST BLUEPRINT`, "idle");
  }

  function startDrag(event, node) {
    if (model.interaction !== "full" || event.button !== 0 || model.busy || model.terminal || model.drag) return;
    event.preventDefault();
    const index = Number(node.dataset.index);
    model.drag = {
      pointerId: event.pointerId,
      origin: index,
      visited: [index],
      startX: event.clientX,
      startY: event.clientY,
      lastX: event.clientX,
      lastY: event.clientY,
      travel: 0,
      samples: 1,
      node,
    };
    node.classList.add("is-dragging");
    node.style.setProperty("--stroke", model.state.palette[model.brush].color);
    model.helpers.setReadout(`BRUSH DOWN · ${model.state.palette[model.brush].name} · STROKE CONTIGUOUS BEADS`, "idle");
    try { node.setPointerCapture(event.pointerId); } catch (_error) { /* optional */ }
  }

  function moveDrag(event) {
    const drag = model.drag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    drag.travel += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY);
    drag.lastX = event.clientX;
    drag.lastY = event.clientY;
    drag.samples += 1;
    const hit = document.elementsFromPoint(event.clientX, event.clientY).find((candidate) => (
      candidate.classList?.contains("strand-bead") && candidate !== drag.node
    ));
    if (!hit) return;
    const index = Number(hit.dataset.index);
    const last = drag.visited[drag.visited.length - 1];
    if (index !== last && Math.abs(index - last) === 1 && !drag.visited.includes(index)) {
      drag.visited.push(index);
      model.helpers.setReadout(`STROKE ${drag.visited.length} BEADS · RELEASE TO PAINT`, "idle");
    }
  }

  function endDrag(event, cancelled = false) {
    const drag = model.drag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    model.drag = null;
    drag.node.classList.remove("is-dragging");
    drag.node.style.removeProperty("--stroke");
    try { drag.node.releasePointerCapture(event.pointerId); } catch (_error) { /* optional */ }
    if (cancelled) return;
    if (drag.travel < 12) {
      model.helpers.setReadout("NO PAINT · HOLD AND STROKE THE LOADED BRUSH", "idle");
      return;
    }
    applyColor(drag.visited, model.brush, "strand_drag", {
      sample_count: drag.samples,
      travel_px: Math.round(drag.travel * 100) / 100,
      start_index: drag.origin,
      end_index: drag.visited[drag.visited.length - 1],
    });
  }

  function choosePalette(color) {
    if (model.busy || model.terminal) return;
    clearFreshFailure();
    model.brush = color;
    refresh();
    model.helpers.setReadout(`BRUSH LOADED · ${model.state.palette[color].name}`, "idle");
  }

  function bindControls() {
    document.querySelectorAll(".strand-season-tab").forEach((node) => {
      node.addEventListener("click", () => chooseSeason(String(node.dataset.seasonTab)));
      node.addEventListener("keydown", (event) => {
        if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
        event.preventDefault();
        const next = model.activeSeason === "spring" ? "winter" : "spring";
        chooseSeason(next);
        document.getElementById(`strand-tab-${next}`)?.focus();
      });
    });
    document.querySelectorAll(".strand-bead").forEach((node) => {
      if (model.interaction === "simplified") node.addEventListener("click", () => paintSimplified(Number(node.dataset.index)));
      node.addEventListener("pointerdown", (event) => startDrag(event, node));
      node.addEventListener("pointermove", moveDrag);
      node.addEventListener("pointerup", (event) => endDrag(event));
      node.addEventListener("pointercancel", (event) => endDrag(event, true));
    });
    document.querySelectorAll(".strand-swatch").forEach((node) => {
      node.addEventListener("click", () => choosePalette(Number(node.dataset.paletteColor)));
    });
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "two-season-strand";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const interaction = state.control_condition?.interaction || "full";
    Object.assign(model, {
      state,
      sequence: [...state.initial_sequence],
      edits: [],
      editCount: 0,
      brush: 0,
      drag: null,
      activeSeason: "spring",
      interaction,
      terminal: false,
      busy: false,
      ready: false,
      helpers,
    });
    const columns = Math.ceil(state.initial_sequence.length / 2);
    helpers.app.innerHTML = `
      <section class="two-season-strand" data-interaction="${clean(interaction)}" data-guidance="${clean(state.parameters.blueprint_guidance)}" data-challenge-id="${clean(state.challenge_id)}" style="--strand-columns:${columns}">
        <header class="strand-head">
          <div class="strand-title"><small>DUAL-SEASON WEAVING OFFICE · FOLD DESK 07</small><h1>TWO-SEASON STRAND</h1><p>${clean(state.prompt)}</p></div>
          <div class="strand-budget"><small>EDITS LEFT</small><strong id="strand-edits-left">${Number(state.parameters.edit_budget)}</strong><span>${state.initial_sequence.length} BEADS</span></div>
        </header>
        <main>
          <section class="strand-folds" id="strand-folds"></section>
          <section class="strand-console">
            <div class="strand-rule"><b>ONE STRAND · TWO READINGS</b><span>SUN↔NIGHT · MOSS↔BERRY · LAST OPEN STEM CLOSES FIRST</span></div>
            <div class="strand-ribbon" id="strand-ribbon">${strandMarkup()}</div>
            <aside class="strand-palette" id="strand-palette">${paletteMarkup()}</aside>
            <div class="strand-mode-note">${interaction === "full" ? "CHOOSE A COLOUR · HOLD AND STROKE THE BRUSH ACROSS ONE OR MORE CONTIGUOUS BEADS" : "CHOOSE A COLOUR · CLICK EACH BEAD TO PAINT IT"}</div>
          </section>
        </main>
        <footer class="strand-foot">
          <div class="strand-readout readout" data-status="idle">REFOLD DESK READY · REPAIR BOTH BLUEPRINTS</div>
          <button type="button" id="strand-seal">${clean(state.submit_label || "SEAL BOTH SEASONS")}</button>
        </footer>
        ${helpers.cheatPanelTemplate()}
      </section>`;
    refresh();
    document.getElementById("strand-seal")?.addEventListener("click", () => submit(model.ready));
    helpers.installCheatPanel();
    window.twoSeasonStrandModel = model;
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.two_season_strand = {
    rootSelector: ".two-season-strand",
    render,
  };
})();
