(() => {
  "use strict";

  const ID = "ember_mosaic";
  const NEIGHBOURS = [[0, -1], [0, 1], [-1, 0], [1, 0]];
  const MATERIALS = {
    water: {label: "WATER", glyph: "≈", color: "#67d5dc"},
    sand: {label: "SAND", glyph: "·", color: "#d7af68"},
    stone: {label: "STONE", glyph: "◆", color: "#a4a6b6"},
  };
  const MOVABLE = new Set([".", "a", "w", "s"]);
  let current = null;

  function index(x, y, width) { return y * width + x; }
  function xy(value, width) { return [value % width, Math.floor(value / width)]; }
  function eachAdjacent(value, width, height, callback) {
    const [x, y] = xy(value, width);
    for (const [dx, dy] of NEIGHBOURS) {
      const nx = x + dx, ny = y + dy;
      if (nx >= 0 && nx < width && ny >= 0 && ny < height) callback(index(nx, ny, width));
    }
  }
  function number(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[char]));
  }
  function modeOf(state) {
    return String(state.control_condition?.interaction || "full");
  }
  function radiusOf(state) {
    return Math.max(1, Math.floor(number(state.parameters?.brush_radius, 1)));
  }

  function brushOne(model, x, y, material) {
    const {width, height, grid} = model;
    if (x < 0 || y < 0 || x >= width || y >= height) return;
    const cell = index(x, y, width);
    const value = grid[cell];
    if (material === "stone") {
      if (MOVABLE.has(value) || value === "f" || (value === "p" && !model.targetCells.has(cell))) {
        grid[cell] = "#";
        model.stoneAge[cell] = 0;
      }
    } else if (material === "water") {
      if ([".", "a", "w", "s", "f"].includes(value)) {
        grid[cell] = "w";
        model.age[cell] = 0;
      }
    } else if (material === "sand") {
      if ([".", "a", "w"].includes(value)) {
        grid[cell] = "s";
        model.age[cell] = 0;
      }
    }
  }
  function raster(first, second) {
    // Keep this integer Bresenham path byte-for-byte equivalent to the
    // independent Python replay grader; do not use language-specific round().
    let x1 = first.x, y1 = first.y;
    const x2 = second.x, y2 = second.y;
    const dx = Math.abs(x2 - x1), sx = x1 < x2 ? 1 : -1;
    const dy = -Math.abs(y2 - y1), sy = y1 < y2 ? 1 : -1;
    let error = dx + dy;
    const points = [];
    while (true) {
      points.push({x: x1, y: y1});
      if (x1 === x2 && y1 === y2) break;
      const twice = 2 * error;
      if (twice >= dy) { error += dy; x1 += sx; }
      if (twice <= dx) { error += dx; y1 += sy; }
    }
    return points;
  }
  function applyBrush(model, material, points) {
    const radius = radiusOf(model.state);
    const rasterPoints = [];
    for (let i = 0; i < points.length - 1; i += 1) rasterPoints.push(...raster(points[i], points[i + 1]));
    if (points.length) rasterPoints.push(points[points.length - 1]);
    for (const point of rasterPoints) {
      for (let dy = -radius; dy <= radius; dy += 1) {
        for (let dx = -radius; dx <= radius; dx += 1) {
          if (dx * dx + dy * dy <= radius * radius) brushOne(model, point.x + dx, point.y + dy, material);
        }
      }
    }
  }
  function record(model, event) {
    model.events.push({...event, seq: model.events.length + 1, tick: model.tick});
  }
  function brush(model, material, points, inputSource) {
    if (model.closed || model.failed || !points.length) return;
    applyBrush(model, material, points);
    record(model, {type: "brush", material, points: points.map((point) => ({x: Math.round(point.x), y: Math.round(point.y)})), input_source: inputSource});
    model.lastAction = `${MATERIALS[material].label} intervention at tick ${model.tick}`;
    model.notice = `${MATERIALS[material].label} applied.`;
    model.render();
  }

  function step(model) {
    if (model.closed) return;
    const {width, height, grid} = model;
    const next = grid.slice();
    const nextAge = model.age.slice();
    const nextStoneAge = model.stoneAge.slice();
    const nextOilHeat = model.oilHeat.slice();

    // Water extinguishes adjacent flame before the same flame can touch oil.
    for (let cell = 0; cell < grid.length; cell += 1) {
      if (grid[cell] !== "w") continue;
      eachAdjacent(cell, width, height, (neighbour) => {
        if (grid[neighbour] === "f") { next[neighbour] = "a"; nextAge[neighbour] = 0; }
      });
    }

    const oilHeatLimit = Math.max(1, number(model.state.parameters?.oil_heat_ticks, 3));
    for (let cell = 0; cell < grid.length; cell += 1) {
      if (grid[cell] !== "o") continue;
      let hot = false;
      eachAdjacent(cell, width, height, (neighbour) => { if (next[neighbour] === "f") hot = true; });
      if (hot) {
        nextOilHeat[cell] += 1;
        if (nextOilHeat[cell] >= oilHeatLimit) model.oilIgnited = true;
      } else {
        nextOilHeat[cell] = Math.max(0, nextOilHeat[cell] - 1);
      }
    }

    for (let cell = 0; cell < grid.length; cell += 1) {
      if (grid[cell] !== "f" || next[cell] === "a") continue;
      nextAge[cell] = model.age[cell] + 1;
      eachAdjacent(cell, width, height, (neighbour) => {
        if (grid[neighbour] === "p") {
          next[neighbour] = "f";
          nextAge[neighbour] = 0;
          if (model.targetCells.has(neighbour)) model.burned.add(neighbour);
        }
      });
      if (nextAge[cell] >= number(model.state.parameters?.fire_lifetime, 6)) {
        next[cell] = "a";
        nextAge[cell] = 0;
      }
    }

    const erosionLimit = number(model.state.parameters?.stone_erosion_ticks, 5);
    for (let cell = 0; cell < grid.length; cell += 1) {
      if (grid[cell] !== "#") continue;
      let hot = false;
      eachAdjacent(cell, width, height, (neighbour) => { if (grid[neighbour] === "f") hot = true; });
      if (hot) {
        nextStoneAge[cell] += 1;
        if (nextStoneAge[cell] >= erosionLimit) { next[cell] = "."; nextStoneAge[cell] = 0; }
      }
    }

    const bias = number(model.state.flow_bias, 1) || 1;
    const moving = [];
    for (let cell = 0; cell < grid.length; cell += 1) if (grid[cell] === "w" || grid[cell] === "s") moving.push(cell);
    moving.sort((a, b) => b - a);
    for (const cell of moving) {
      if (grid[cell] !== next[cell] || !["w", "s"].includes(next[cell])) continue;
      const [x, y] = xy(cell, width);
      const candidates = [[x, y + 1], [x + bias, y], [x - bias, y]];
      let moved = false;
      for (const [nx, ny] of candidates) {
        if (nx <= 0 || nx >= width - 1 || ny <= 0 || ny >= height - 1) continue;
        const destination = index(nx, ny, width);
        if (![".", "a"].includes(next[destination])) continue;
        next[destination] = grid[cell];
        nextAge[destination] = nextAge[cell];
        next[cell] = ".";
        nextAge[cell] = 0;
        moved = true;
        break;
      }
      if (moved) continue;
    }
    model.grid = next;
    model.age = nextAge;
    model.stoneAge = nextStoneAge;
    model.oilHeat = nextOilHeat;
    model.tick += 1;
  }

  function cellColor(model, cell) {
    const value = model.grid[cell];
    if (value === "#") return "#6e7487";
    if (value === "o") return model.oilHeat[cell] > 0 ? "#a65d36" : "#111b2c";
    if (value === "p") {
      const region = model.regionGrid[String(cell)] || "ember-0";
      const palette = {"ember-1": "#bd7864", "ember-2": "#d29a5d", "ember-3": "#aa6380", "ember-4": "#6d8f9e"};
      return palette[region] || "#b87569";
    }
    if (value === "f") return model.tick % 2 ? "#ffca55" : "#ff6e2f";
    if (value === "w") return "#5ecbd5";
    if (value === "s") return "#c9a365";
    if (value === "a") return "#4a4c59";
    return "#1b2933";
  }

  function renderCanvas(model) {
    const canvas = model.canvas;
    const context = canvas.getContext("2d");
    const scaleX = canvas.width / model.width, scaleY = canvas.height / model.height;
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "#0a151d";
    context.fillRect(0, 0, canvas.width, canvas.height);
    for (let y = 0; y < model.height; y += 1) {
      for (let x = 0; x < model.width; x += 1) {
        const cell = index(x, y, model.width);
        context.fillStyle = cellColor(model, cell);
        context.fillRect(x * scaleX, y * scaleY, scaleX + 0.35, scaleY + 0.35);
        if (model.gateCells.has(cell)) {
          context.strokeStyle = "rgba(105,224,236,0.95)";
          context.lineWidth = 1.5;
          context.setLineDash([2, 2]);
          context.strokeRect(x * scaleX + 1.5, y * scaleY + 1.5, scaleX - 3, scaleY - 3);
          context.setLineDash([]);
        }
        if (model.targetCells.has(cell) && model.grid[cell] !== "f" && model.grid[cell] !== "a") {
          context.strokeStyle = "rgba(255,237,157,0.45)";
          context.lineWidth = 0.8;
          context.strokeRect(x * scaleX + 1, y * scaleY + 1, scaleX - 2, scaleY - 2);
        }
        if (model.grid[cell] === "o") {
          context.fillStyle = model.oilHeat[cell] > 0 ? "rgba(255,164,76,0.42)" : "rgba(68,185,214,0.28)";
          context.fillRect(x * scaleX + 2, y * scaleY + 2, scaleX - 4, scaleY - 4);
        }
        if (model.grid[cell] === "f") {
          context.fillStyle = "rgba(255,235,137,0.75)";
          context.fillRect(x * scaleX + scaleX * 0.34, y * scaleY + scaleY * 0.12, scaleX * 0.25, scaleY * 0.55);
        }
      }
    }
    // A very light grid makes brush placement legible without turning the
    // scene into a static grid puzzle.
    context.strokeStyle = "rgba(180,217,215,0.08)";
    context.lineWidth = 1;
    for (let x = 0; x <= model.width; x += 1) { context.beginPath(); context.moveTo(x * scaleX, 0); context.lineTo(x * scaleX, canvas.height); context.stroke(); }
    for (let y = 0; y <= model.height; y += 1) { context.beginPath(); context.moveTo(0, y * scaleY); context.lineTo(canvas.width, y * scaleY); context.stroke(); }
  }

  function updateReadout(model) {
    const root = model.root;
    const oilWarm = model.oilHeat.some((value) => value > 0);
    root.querySelector("#em-oil").textContent = model.oilIgnited ? "IGNITED" : (oilWarm ? "WARM" : "DARK");
    root.querySelector("#em-last").textContent = model.notice || "";
    root.querySelector("#em-material-name").textContent = MATERIALS[model.selectedMaterial].label;
    root.querySelectorAll("[data-material]").forEach((button) => button.classList.toggle("is-selected", button.dataset.material === model.selectedMaterial));
    model.helpers.setReadout(model.oilIgnited ? "OIL IGNITED" : (model.notice || ""), model.oilIgnited ? "error" : "idle");
  }
  function render(model) {
    if (model.closed && model.verdict) return;
    renderCanvas(model);
    updateReadout(model);
  }
  function loop(model, now) {
    if (current !== model || model.closed) return;
    const elapsed = Math.max(0, now - model.lastNow);
    model.lastNow = now;
    model.accumulator += elapsed;
    const tickMs = Math.max(40, number(model.state.parameters?.tick_ms, 200));
    let iterations = 0;
    while (model.accumulator >= tickMs && iterations < 12 && !model.closed) {
      model.accumulator -= tickMs;
      step(model);
      iterations += 1;
    }
    render(model);
    model.animationFrame = requestAnimationFrame((nextNow) => loop(model, nextNow));
  }
  function eventPoint(model, event) {
    const box = model.canvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(model.width - 1, Math.floor((event.clientX - box.left) * model.width / box.width))),
      y: Math.max(0, Math.min(model.height - 1, Math.floor((event.clientY - box.top) * model.height / box.height))),
    };
  }
  function chooseMaterial(model, material) {
    if (!MATERIALS[material] || model.closed || model.dragging) return;
    model.selectedMaterial = material;
    model.notice = `${MATERIALS[material].label} selected.`;
    render(model);
  }
  function submit(model) {
    if (model.verdict || model.submitting || model.dragging) return;
    model.submitting = true;
    model.closed = true;
    if (model.events.at(-1)?.type !== "submit") {
      model.events.push({seq: model.events.length + 1, type: "submit", tick: model.tick, input_source: "certify_button", completed: true});
    }
    fetch("/result", {
      method: "POST",
      headers: {"content-type": "application/json"},
      body: JSON.stringify({
        mechanic_id: model.state.mechanic_id,
        task_id: model.state.task_id,
        challenge_id: model.state.challenge_id,
        control_condition: model.state.control_condition,
        interaction_mode: model.mode,
        events: model.events,
        completed: true,
        final_tick: model.tick,
      }),
    }).then((response) => response.json()).then(async (outcome) => {
      if (outcome.passed === true) {
        model.verdict = true;
        model.root.classList.add("is-passed");
        model.helpers.setReadout("PASS", "passed");
        const stamp = document.createElement("div");
        stamp.className = "em-verdict em-pass";
        stamp.innerHTML = "<strong>EMBER MOSAIC PASS</strong><span>Every marked patch burned · every oil pocket stayed dark.</span>";
        model.root.appendChild(stamp);
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        model.helpers.setReadout("FAIL · FRESH MOSAIC", "error");
      } else {
        model.submitting = false;
        model.notice = "Certification unavailable. Retry certification.";
        render(model);
      }
    }).catch(() => {
      model.submitting = false;
      model.notice = "Connection interrupted. Certification remains available.";
      render(model);
    });
  }

  function renderState(state, helpers) {
    document.body.dataset.mechanic = "ember-mosaic";
    if (current?.animationFrame) cancelAnimationFrame(current.animationFrame);
    if (current?.keyHandler) window.removeEventListener("keydown", current.keyHandler);
    const mode = modeOf(state);
    const width = number(state.width, 72), height = number(state.height, 42);
    const model = {
      state,
      helpers,
      mode,
      width,
      height,
      grid: Array.isArray(state.grid) ? state.grid.slice() : [],
      age: Array((state.grid || []).length).fill(0),
      stoneAge: Array((state.grid || []).length).fill(0),
      targetCells: new Set((state.target_cells || []).map((value) => Number(value))),
      gateCells: new Set((state.gate_cells || []).map((value) => Number(value))),
      regionGrid: state.region_grid || {},
      burned: new Set(),
      oilIgnited: false,
      oilHeat: Array((state.grid || []).length).fill(0),
      tick: 0,
      accumulator: 0,
      lastNow: performance.now(),
      events: [],
      selectedMaterial: "stone",
      dragging: null,
      closed: false,
      submitting: false,
      verdict: false,
      notice: "",
    };
    current = model;
    window.emberMosaicModel = model;
    helpers.app.innerHTML = `<main class="ember-mosaic" data-interaction="${esc(mode)}">
      <header class="em-header"><div><small>FIELD NOTE 07 / REACTIVE GARDEN</small><h1>Ember Mosaic <span>✦</span></h1><p>Burn the marked plant patches. Keep the oil dark.</p></div><div class="em-status"><div><small>OIL</small><b id="em-oil">DARK</b></div></div></header>
      <section class="em-work"><div class="em-canvas-wrap"><canvas id="em-canvas" width="720" height="420" aria-label="Reactive particle mosaic"></canvas><div class="em-canvas-caption"><span>EMBER FIELD / ${width} × ${height}</span><span>marked cells glow at the edge</span></div></div><aside class="em-sidebar"><div class="em-card em-goal"><small>THE COMMISSION</small><strong>Burn every marked ember patch.</strong><p>Keep every oil pocket unlit.</p><div class="em-legend"><span><i class="em-dot em-plant"></i>marked plant</span><span><i class="em-dot em-oil"></i>protected oil</span><span><i class="em-dot em-fire"></i>active fire</span></div></div><div class="em-card em-palette"><div class="em-card-head"><small>MATERIAL PALETTE</small><b id="em-material-name">STONE</b></div><div class="em-materials">${Object.entries(MATERIALS).map(([key, item]) => `<button type="button" data-material="${key}" title="Select ${item.label}"><i style="--material:${item.color}">${item.glyph}</i><span>${item.label}</span></button>`).join("")}</div><p id="em-last"></p></div>${mode === "simplified" ? `<div class="em-card em-proxy"><small>STAMP CONTROL / SIMPLIFIED</small><div class="em-coordinates"><label>X <input id="em-x" type="number" min="0" max="${width - 1}" value="36"></label><label>Y <input id="em-y" type="number" min="0" max="${height - 1}" value="21"></label></div><button id="em-stamp" type="button" class="em-action">STAMP SELECTED MATERIAL</button><p>Coordinates start at 0 in the upper-left corner.</p></div>` : `<div class="em-card em-direct"><small>DIRECT BRUSH / FULL</small><strong>Drag across the field</strong><p>Select a material, then drag to paint.</p><div class="em-swatch-row"><span class="em-swatch" style="--material:#67d5dc"></span><span class="em-swatch" style="--material:#d7af68"></span><span class="em-swatch" style="--material:#a4a6b6"></span></div></div>`}<button id="em-submit" type="button" class="em-certify">CERTIFY MOSAIC →</button></aside></section>
      <footer class="em-footer"><span>WATER · SAND · STONE</span><div class="readout" data-status="idle"></div></footer>
    </main>`;
    model.root = helpers.app.querySelector(".ember-mosaic");
    model.canvas = model.root.querySelector("#em-canvas");
    const legend = model.root.querySelector(".em-legend");
    if (legend) legend.insertAdjacentHTML("beforeend", '<span><i class="em-dot em-gate"></i>gate</span>');
    const caption = model.root.querySelector(".em-canvas-caption");
    if (caption?.lastElementChild) caption.lastElementChild.textContent = "cyan rings mark gates · gold rings mark targets";
    model.render = () => render(model);
    model.targetCells = new Set((state.target_cells || []).map((value) => Number(value)));
    model.gateCells = new Set((state.gate_cells || []).map((value) => Number(value)));
    model.root.querySelectorAll("[data-material]").forEach((button) => button.addEventListener("click", () => chooseMaterial(model, button.dataset.material)));
    model.root.querySelector("#em-submit").addEventListener("click", () => submit(model));
    if (mode === "simplified") {
      model.root.querySelector("#em-stamp").addEventListener("click", () => {
        const inputs = [model.root.querySelector("#em-x"), model.root.querySelector("#em-y")];
        if (inputs.some((input) => !input.value || !input.reportValidity())) return;
        const [x, y] = inputs.map((input) => Number(input.value));
        brush(model, model.selectedMaterial, [{x, y}], "stamp_controls");
      });
    } else {
      model.canvas.addEventListener("pointerdown", (event) => {
        if (model.closed || model.failed || model.dragging || event.button !== 0) return;
        event.preventDefault();
        model.canvas.setPointerCapture?.(event.pointerId);
        const point = eventPoint(model, event);
        model.dragging = {pointerId: event.pointerId, points: [point], material: model.selectedMaterial};
        brush(model, model.dragging.material, [point], "freehand_brush");
        model.notice = `${MATERIALS[model.selectedMaterial].label} stroke in progress.`;
        render(model);
      });
      model.canvas.addEventListener("pointermove", (event) => {
        if (model.closed || !model.dragging || model.dragging.pointerId !== event.pointerId) return;
        event.preventDefault();
        const point = eventPoint(model, event);
        const previous = model.dragging.points[model.dragging.points.length - 1];
        if (!previous || previous.x !== point.x || previous.y !== point.y) {
          model.dragging.points.push(point);
          brush(model, model.dragging.material, [previous || point, point], "freehand_brush");
          render(model);
        }
      });
      const finishDrag = (event) => {
        if (model.closed || !model.dragging || model.dragging.pointerId !== event.pointerId) return;
        const material = model.dragging.material;
        model.dragging = null;
        model.notice = `${MATERIALS[material].label} applied.`;
        render(model);
      };
      model.canvas.addEventListener("pointerup", finishDrag);
      model.canvas.addEventListener("pointercancel", finishDrag);
    }
    model.keyHandler = (event) => {
      if (event.target.closest?.("input, textarea, select, [contenteditable]")) return;
      if (event.key === "1") chooseMaterial(model, "water");
      if (event.key === "2") chooseMaterial(model, "sand");
      if (event.key === "3") chooseMaterial(model, "stone");
    };
    window.addEventListener("keydown", model.keyHandler);
    helpers.setReadout("", "idle");
    render(model);
    model.animationFrame = requestAnimationFrame((now) => loop(model, now));
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[ID] = {rootSelector: ".ember-mosaic", render: renderState};
})();
