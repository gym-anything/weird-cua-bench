(() => {
  "use strict";

  const MECHANIC_ID = "nonogram_denouement";
  const VALUE = {reset: 0, ink: 1, clear: -1};
  const SYMBOL = {NORTH: "↑", EAST: "→", SOUTH: "↓", WEST: "←"};
  let model = null;
  let cleanup = null;

  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const interaction = () => model.state.control_condition?.interaction || "full";

  function lineClues(line) {
    const result = [];
    let run = 0;
    [...line, 0].forEach((value) => {
      if (value === 1) run += 1;
      else if (run) { result.push(run); run = 0; }
    });
    return result;
  }

  function sameArray(left, right) {
    return left.length === right.length && left.every((value, index) => value === right[index]);
  }

  function plateStatus() {
    const size = model.puzzle.size;
    const decided = model.grid.flat().filter((value) => value !== 0).length;
    const complete = decided === size * size;
    const rowsValid = model.grid.every((row, index) => sameArray(lineClues(row), model.puzzle.row_clues[index]));
    const colsValid = Array.from({length: size}, (_, col) => (
      sameArray(lineClues(model.grid.map((row) => row[col])), model.puzzle.col_clues[col])
    )).every(Boolean);
    return {decided, complete, valid: complete && rowsValid && colsValid};
  }

  function clearFreshFailure() {
    if (!model.freshFailure) return;
    model.freshFailure = false;
    const verdict = document.querySelector(".nd-verdict");
    if (verdict) { verdict.className = "nd-verdict"; verdict.innerHTML = ""; }
    model.helpers.setReadout("", "idle");
  }

  function record(event) {
    clearFreshFailure();
    model.events.push({sequence: model.events.length + 1, ...event});
  }

  function cellClass(row, col, value, proof = false) {
    const classes = [proof ? "nd-proof-cell" : "nd-cell"];
    classes.push(value === 1 ? "is-ink" : value === -1 ? "is-clear" : "is-unknown");
    if ((col + 1) % 5 === 0 && col + 1 < model.puzzle.size) classes.push("is-major-col");
    if ((row + 1) % 5 === 0 && row + 1 < model.puzzle.size) classes.push("is-major-row");
    if (!proof && model.selected?.row === row && model.selected?.col === col) classes.push("is-selected");
    return classes.join(" ");
  }

  function clueText(clues) {
    return clues.length ? clues.map((value) => `<b>${value}</b>`).join("") : "<b>0</b>";
  }

  function plateMarkup() {
    const size = model.puzzle.size;
    const cells = model.grid.flatMap((line, row) => line.map((value, col) => `
      <button class="${cellClass(row, col, value)}" data-cell="${row}:${col}"
        aria-label="row ${row + 1}, column ${col + 1}, ${value === 1 ? "ink" : value === -1 ? "clear" : "undecided"}"
        ${model.developed ? "disabled" : ""}>
        <span></span>
      </button>`)).join("");
    return `<div class="nd-plate" style="--size:${size}">
      <div class="nd-plate-corner"><span>RUN</span><b>INDEX</b></div>
      <div class="nd-col-clues" style="--size:${size}">
        ${model.puzzle.col_clues.map((clues, index) => `<div data-col-clue="${index}">${clueText(clues)}</div>`).join("")}
      </div>
      <div class="nd-row-clues" style="--size:${size}">
        ${model.puzzle.row_clues.map((clues, index) => `<div data-row-clue="${index}">${clueText(clues)}</div>`).join("")}
      </div>
      <div class="nd-cells mode-${interaction()}" style="--size:${size}" data-grid>${cells}</div>
    </div>`;
  }

  function proxyMarkup() {
    if (interaction() !== "simplified" || model.developed) return "";
    const selected = model.selected ? `R${model.selected.row + 1} · C${model.selected.col + 1}` : "—";
    return `<div class="nd-mark-proxy" aria-label="selected cell mark controls">
      <span><b>${selected}</b></span>
      <button data-proxy-mark="ink" ${model.selected ? "" : "disabled"}><i></i>INK</button>
      <button data-proxy-mark="clear" ${model.selected ? "" : "disabled"}><i>×</i>CLEAR</button>
      <button data-proxy-mark="reset" ${model.selected ? "" : "disabled"}>RESET</button>
    </div>`;
  }

  function pressPanelMarkup() {
    return `<section class="nd-compose-panel">
      <div class="nd-section-label"><span>01</span><div><small>RUN MATRIX</small><h2>Plate</h2></div></div>
      <div class="nd-compose-body">
        ${plateMarkup()}
      </div>
      ${proxyMarkup()}
      <button class="nd-develop" data-develop ${model.developed ? "disabled" : ""}>
        <span>DEVELOP</span><i>→</i>
      </button>
    </section>`;
  }

  function markerFor(row, col) {
    return model.puzzle.markers.find((marker) => marker.row === row && marker.col === col) || null;
  }

  function proofGridMarkup() {
    const size = model.puzzle.size;
    const cells = model.grid.flatMap((line, row) => line.map((value, col) => {
      const marker = markerFor(row, col);
      return `<div class="${cellClass(row, col, value, true)}" data-proof-cell="${row}:${col}">
        ${marker ? `<span class="nd-ring" data-ring="${esc(marker.id)}"><i></i><b>${esc(marker.label.replace("RING ", ""))}</b></span>` : ""}
      </div>`;
    })).join("");
    return `<div class="nd-proof-frame">
      <div class="nd-proof-grid" data-proof-grid style="--size:${size}">${cells}<i class="nd-pulse" data-pulse></i></div>
    </div>`;
  }

  function answerMarkup() {
    if (!model.developed) return "";
    const options = model.puzzle.answer_options;
    if (interaction() === "simplified") {
      return `<div class="nd-answer-bank mode-simplified">
        ${options.map((direction) => `<button class="${model.answer === direction ? "is-selected" : ""}" data-answer-proxy="${direction}"><i>${SYMBOL[direction]}</i><span>${direction}</span></button>`).join("")}
      </div>`;
    }
    return `<div class="nd-answer-bank mode-full">
      <div class="nd-slug-rack">
        ${options.map((direction) => `<button class="nd-direction-slug ${model.answer === direction ? "is-selected" : ""}" data-direction-slug="${direction}"><i>${SYMBOL[direction]}</i><span>${direction}</span></button>`).join("")}
      </div>
      <div class="nd-answer-well" data-answer-well aria-label="direction answer well"><b>${model.answer ? `${SYMBOL[model.answer]} ${model.answer}` : "◇"}</b></div>
    </div>`;
  }

  function theatreMarkup() {
    return `<section class="nd-theatre-panel ${model.developed ? "is-developed" : "is-waiting"}">
      <div class="nd-section-label"><span>02</span><div><small>AFTERIMAGE</small><h2>Proof field</h2></div></div>
      ${model.developed ? proofGridMarkup() : `<div class="nd-waiting-well" aria-label="inactive proof field"><i></i></div>`}
      ${model.developed ? `<div class="nd-question"><h3>${esc(model.puzzle.question)}</h3></div>` : ""}
      ${answerMarkup()}
    </section>`;
  }

  function footerMarkup() {
    return `<footer class="nd-footer">
      <div class="nd-footer-seal" aria-hidden="true"><i></i><i></i><i></i></div>
      <div class="readout" data-status="idle"></div>
      <button data-certify ${model.answer && !model.terminal ? "" : "disabled"}>CERTIFY <i>↗</i></button>
    </footer>`;
  }

  function renderUi() {
    const start = model.loopStartedAt;
    model.helpers.app.innerHTML = `<section class="nonogram-denouement mode-${interaction()}" data-interaction="${interaction()}" data-challenge-id="${esc(model.state.challenge_id)}" data-fresh-failure="${model.freshFailure ? "true" : "false"}">
      <div class="nd-verdict"></div>
      <header class="nd-masthead">
        <div class="nd-mark"><i></i><span>THE<br>AFTERIMAGE<br>OFFICE</span></div>
        <div><h1>${esc(model.state.prompt)}</h1></div>
        <div class="nd-mode"><small>PLATE</small><b>${model.puzzle.size} × ${model.puzzle.size}</b></div>
      </header>
      <main>${pressPanelMarkup()}${theatreMarkup()}</main>
      ${footerMarkup()}
      ${model.helpers.cheatPanelTemplate()}
    </section>`;
    model.loopStartedAt = start;
    bindControls();
    model.helpers.installCheatPanel();
    if (model.freshFailure) showVerdict("fail");
    if (model.terminal) showVerdict("pass");
    ensureAnimation();
  }

  function applyCells(mode, coordinates, inputSource, pointerButton = null) {
    if (model.developed || !coordinates.length) return;
    const after = VALUE[mode];
    const cells = coordinates.map(({row, col}) => ({row, col, before: model.grid[row][col], after}));
    if (cells.every((cell) => cell.before === after)) return;
    cells.forEach((cell) => { model.grid[cell.row][cell.col] = after; });
    record({type: "mark", mode, cells, input_source: inputSource, ...(pointerButton ? {pointer_button: pointerButton} : {})});
    model.helpers.setReadout("", "idle");
    renderUi();
  }

  function segment(start, end) {
    if (!end) return [start];
    if (start.row === end.row) {
      const low = Math.min(start.col, end.col); const high = Math.max(start.col, end.col);
      return Array.from({length: high - low + 1}, (_, index) => ({row: start.row, col: low + index}));
    }
    if (start.col === end.col) {
      const low = Math.min(start.row, end.row); const high = Math.max(start.row, end.row);
      return Array.from({length: high - low + 1}, (_, index) => ({row: low + index, col: start.col}));
    }
    return null;
  }

  function parseCell(node) {
    if (!node?.dataset.cell) return null;
    const [row, col] = node.dataset.cell.split(":").map(Number);
    return {row, col};
  }

  function clearPreview() {
    document.querySelectorAll(".nd-cell.is-preview-ink,.nd-cell.is-preview-clear,.nd-cell.is-preview-reset").forEach((node) => {
      node.classList.remove("is-preview-ink", "is-preview-clear", "is-preview-reset");
    });
  }

  function paintPreview(cells, mode) {
    clearPreview();
    (cells || []).forEach(({row, col}) => document.querySelector(`[data-cell="${row}:${col}"]`)?.classList.add(`is-preview-${mode}`));
  }

  function bindFullGrid() {
    const grid = document.querySelector("[data-grid]");
    if (!grid || model.developed) return;
    let stroke = null;
    grid.addEventListener("contextmenu", (event) => event.preventDefault());
    grid.addEventListener("pointerdown", (event) => {
      const node = event.target.closest("[data-cell]");
      if (!node || ![0, 2].includes(event.button)) return;
      event.preventDefault();
      const mode = event.shiftKey ? "reset" : event.button === 2 ? "clear" : "ink";
      const pointerButton = event.shiftKey ? "shift" : event.button === 2 ? "right" : "left";
      const start = parseCell(node);
      stroke = {start, end: start, mode, pointerButton, pointerId: event.pointerId};
      grid.setPointerCapture?.(event.pointerId);
      paintPreview([start], mode);
    });
    grid.addEventListener("pointermove", (event) => {
      if (!stroke) return;
      const node = document.elementFromPoint(event.clientX, event.clientY)?.closest?.("[data-cell]");
      const end = parseCell(node);
      const cells = segment(stroke.start, end);
      if (cells) { stroke.end = end; paintPreview(cells, stroke.mode); }
    });
    const finish = () => {
      if (!stroke) return;
      const cells = segment(stroke.start, stroke.end) || [stroke.start];
      const {mode, pointerButton} = stroke;
      stroke = null;
      clearPreview();
      applyCells(mode, cells, "direct_grid_stroke", pointerButton);
    };
    grid.addEventListener("pointerup", finish);
    grid.addEventListener("pointercancel", () => { stroke = null; clearPreview(); });
  }

  function bindSimplifiedGrid() {
    if (model.developed) return;
    document.querySelectorAll("[data-cell]").forEach((button) => button.addEventListener("click", () => {
      model.selected = parseCell(button);
      clearFreshFailure();
      renderUi();
    }));
    document.querySelectorAll("[data-proxy-mark]").forEach((button) => button.addEventListener("click", () => {
      if (!model.selected) return;
      applyCells(button.dataset.proxyMark, [model.selected], "proxy_mark_button");
    }));
  }

  function startDeveloping() {
    if (model.developed) return;
    const status = plateStatus();
    if (!status.valid) return;
    model.developed = true;
    model.loopStartedAt = performance.now();
    record({type: "develop", input_source: "develop_button"});
    model.helpers.setReadout("", "pending");
    renderUi();
  }

  function chooseAnswer(direction, inputSource, gesture = null) {
    if (!model.developed || !model.puzzle.answer_options.includes(direction)) return;
    model.answer = direction;
    record({type: "answer", direction, input_source: inputSource, ...(gesture ? {gesture} : {})});
    model.helpers.setReadout("", "pending");
    renderUi();
  }

  function bindAnswerDrags() {
    const well = document.querySelector("[data-answer-well]");
    if (!well) return;
    document.querySelectorAll("[data-direction-slug]").forEach((slug) => {
      let drag = null;
      slug.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        drag = {lastX: event.clientX, lastY: event.clientY, travel: 0, samples: 0, pointerId: event.pointerId};
        slug.setPointerCapture?.(event.pointerId);
        slug.classList.add("is-dragging");
      });
      slug.addEventListener("pointermove", (event) => {
        if (!drag) return;
        drag.travel += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY);
        drag.lastX = event.clientX; drag.lastY = event.clientY; drag.samples += 1;
        const box = slug.getBoundingClientRect();
        slug.style.transform = `translate(${event.clientX - (box.left + box.width / 2)}px, ${event.clientY - (box.top + box.height / 2)}px) rotate(-3deg)`;
      });
      slug.addEventListener("pointerup", (event) => {
        if (!drag) return;
        drag.travel += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY);
        drag.samples += 1;
        const box = well.getBoundingClientRect();
        const dropped = event.clientX >= box.left && event.clientX <= box.right && event.clientY >= box.top && event.clientY <= box.bottom;
        const proof = {start_direction: slug.dataset.directionSlug, travel_px: Number(drag.travel.toFixed(3)), sample_count: drag.samples, dropped_in_well: dropped};
        drag = null;
        slug.classList.remove("is-dragging"); slug.style.transform = "";
        if (dropped && proof.travel_px >= 40 && proof.sample_count >= 2) chooseAnswer(slug.dataset.directionSlug, "direction_slug_drag", proof);
      });
      slug.addEventListener("pointercancel", () => { drag = null; slug.classList.remove("is-dragging"); slug.style.transform = ""; });
    });
  }

  function bindControls() {
    if (interaction() === "full") bindFullGrid();
    else bindSimplifiedGrid();
    document.querySelector("[data-develop]")?.addEventListener("click", startDeveloping);
    document.querySelectorAll("[data-answer-proxy]").forEach((button) => button.addEventListener("click", () => chooseAnswer(button.dataset.answerProxy, "direction_proxy_button")));
    if (interaction() === "full") bindAnswerDrags();
    document.querySelector("[data-certify]")?.addEventListener("click", submit);
  }

  function animateProof() {
    model.animationFrame = null;
    if (!model?.developed || model.terminal) return;
    const pulse = document.querySelector("[data-pulse]");
    if (!pulse) return;
    const route = model.puzzle.route;
    const segmentMs = model.puzzle.pulse_segment_ms;
    const segmentCount = route.length - 1;
    const phase = ((performance.now() - model.loopStartedAt) % (segmentCount * segmentMs)) / segmentMs;
    const index = Math.min(segmentCount - 1, Math.floor(phase));
    const fraction = phase - index;
    const start = route[index]; const end = route[index + 1];
    const row = start.row + (end.row - start.row) * fraction;
    const col = start.col + (end.col - start.col) * fraction;
    pulse.style.left = `${(col + 0.5) / model.puzzle.size * 100}%`;
    pulse.style.top = `${(row + 0.5) / model.puzzle.size * 100}%`;
    pulse.dataset.segment = String(index);
    model.animationFrame = requestAnimationFrame(animateProof);
  }

  function ensureAnimation() {
    if (model.developed && !model.animationFrame && !model.terminal) model.animationFrame = requestAnimationFrame(animateProof);
  }

  function showVerdict(kind) {
    const node = document.querySelector(".nd-verdict");
    if (!node) return;
    node.className = `nd-verdict is-${kind}`;
    node.innerHTML = `<b>${kind.toUpperCase()}</b>`;
  }

  async function submit() {
    if (!model || model.submitting || model.terminal || !model.answer) return;
    const current = model;
    current.submitting = true;
    current.helpers.setReadout("", "pending");
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
          final_grid: current.grid,
          final_answer: current.answer,
          completed: true,
        }),
      });
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.terminal = true;
        if (current.animationFrame) cancelAnimationFrame(current.animationFrame);
        current.animationFrame = null;
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
    document.body.dataset.mechanic = "nonogram-denouement";
    model = {
      state,
      helpers,
      puzzle: JSON.parse(JSON.stringify(state.puzzle)),
      grid: Array.from({length: state.puzzle.size}, () => Array(state.puzzle.size).fill(0)),
      events: [],
      selected: null,
      developed: false,
      answer: null,
      loopStartedAt: 0,
      animationFrame: null,
      freshFailure: Boolean(options.freshFailure),
      terminal: false,
      submitting: false,
    };
    renderUi();
    cleanup = () => {
      if (model?.animationFrame) cancelAnimationFrame(model.animationFrame);
    };
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {rootSelector: ".nonogram-denouement", render};
})();
