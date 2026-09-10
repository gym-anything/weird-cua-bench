(() => {
  "use strict";

  const model = {
    state: null,
    helpers: null,
    interaction: "simplified",
    columns: {},
    events: [],
    score: null,
    drag: null,
    busy: false,
    terminal: false,
  };

  const clean = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

  function rowsForScore() {
    return (model.state.rows || []).map((row) => ({
      id: row.id,
      colors: (row.tiles || []).map((tile) => Number(tile.color)),
    }));
  }

  function scoreAlignment() {
    const rows = rowsForScore();
    const lookup = Object.fromEntries(rows.map((row) => [
      row.id,
      Object.fromEntries((model.columns[row.id] || []).map((column, index) => [column, index])),
    ]));
    const allColumns = Object.values(model.columns).flat();
    const minimum = Math.min(...allColumns);
    const maximum = Math.max(...allColumns);
    let matches = 0;
    let mismatches = 0;
    const columnScores = [];
    for (let column = minimum; column <= maximum; column += 1) {
      const tokens = rows.map((row) => {
        const index = lookup[row.id][column];
        return index == null ? null : row.colors[index];
      });
      let columnScore = 0;
      for (let leftIndex = 0; leftIndex < tokens.length; leftIndex += 1) {
        for (let rightIndex = leftIndex + 1; rightIndex < tokens.length; rightIndex += 1) {
          const left = tokens[leftIndex];
          const right = tokens[rightIndex];
          if (left == null || right == null) continue;
          if (left === right) {
            matches += 1;
            columnScore += 1;
          } else {
            mismatches += 1;
            columnScore -= 1;
          }
        }
      }
      columnScores.push(columnScore);
    }
    let gapOpenRuns = 0;
    let gapExtensions = 0;
    rows.forEach((row) => {
      const positions = new Set(model.columns[row.id]);
      const first = Math.min(...positions);
      const last = Math.max(...positions);
      let insideGap = false;
      for (let column = first + 1; column < last; column += 1) {
        if (!positions.has(column)) {
          if (insideGap) gapExtensions += 1;
          else {
            gapOpenRuns += 1;
            insideGap = true;
          }
        } else {
          insideGap = false;
        }
      }
    });
    const parameters = model.state.parameters;
    return {
      score: matches - mismatches - gapOpenRuns * Number(parameters.gap_open_penalty) - gapExtensions * Number(parameters.gap_extend_penalty),
      matches,
      mismatches,
      gap_open_runs: gapOpenRuns,
      gap_extensions: gapExtensions,
      column_scores: columnScores,
    };
  }

  function validShift(columns, breakIndex, delta) {
    if (!Number.isInteger(breakIndex) || breakIndex < 1 || breakIndex >= columns.length || ![-1, 1].includes(delta)) return null;
    const shifted = [...columns];
    for (let index = breakIndex; index < shifted.length; index += 1) shifted[index] += delta;
    const columnCount = Number(model.state.column_count);
    if (Math.min(...shifted) < 0 || Math.max(...shifted) >= columnCount) return null;
    for (let index = 1; index < shifted.length; index += 1) if (shifted[index - 1] >= shifted[index]) return null;
    return shifted;
  }

  function setReadout(message, status = "idle") {
    model.helpers.setReadout(message, status);
  }

  function updateSelectOptions() {
    const rowSelect = document.querySelector("#ribbon-row-select");
    const breakSelect = document.querySelector("#ribbon-break-select");
    if (!rowSelect || !breakSelect) return;
    const oldRow = rowSelect.value || model.state.rows[0]?.id;
    rowSelect.innerHTML = (model.state.rows || []).map((row) => `<option value="${clean(row.id)}">${clean(row.label)}</option>`).join("");
    rowSelect.value = model.state.rows.some((row) => row.id === oldRow) ? oldRow : model.state.rows[0]?.id;
    const row = model.state.rows.find((item) => item.id === rowSelect.value) || model.state.rows[0];
    const oldBreak = Number(breakSelect.value || 1);
    breakSelect.innerHTML = (row?.tiles || []).slice(1).map((tile) => `<option value="${tile.index}">after tile ${tile.index}</option>`).join("");
    const maximum = Math.max(1, (row?.tiles || []).length - 1);
    breakSelect.value = String(clamp(oldBreak, 1, maximum));
  }

  function updatePanel() {
    model.score = scoreAlignment();
    const scoreNode = document.querySelector(".ribbon-score-value");
    const floorNode = document.querySelector(".ribbon-score-floor");
    const movesNode = document.querySelector(".ribbon-moves-value");
    const matchNode = document.querySelector(".ribbon-match-value");
    const gapNode = document.querySelector(".ribbon-gap-value");
    if (scoreNode) scoreNode.textContent = String(model.score.score);
    if (floorNode) floorNode.textContent = `required ${model.state.score_floor}`;
    if (movesNode) movesNode.textContent = `${model.events.length} / ${model.state.max_edits} edits`;
    if (matchNode) matchNode.textContent = `${model.score.matches} matches · ${model.score.mismatches} mismatches`;
    if (gapNode) gapNode.textContent = `${model.score.gap_open_runs} opens · ${model.score.gap_extensions} extensions`;
    const progress = document.querySelector(".ribbon-score-progress i");
    if (progress) {
      const start = Number(model.state.score || 0);
      const required = Number(model.state.score_floor || 0);
      const fraction = required === start ? (model.score.score >= required ? 1 : 0) : (model.score.score - start) / (required - start);
      progress.style.width = `${clamp(fraction * 100, 0, 100)}%`;
    }
    document.querySelectorAll(".ribbon-column-score").forEach((node, index) => {
      const value = model.score.column_scores[index] || 0;
      node.textContent = value > 0 ? `+${value}` : String(value);
      node.dataset.tone = value > 0 ? "good" : value < 0 ? "bad" : "flat";
    });
    const ready = model.score.score >= Number(model.state.score_floor);
    const badge = document.querySelector(".ribbon-cert-badge");
    if (badge) {
      badge.textContent = ready ? "THRESHOLD REACHED · CERTIFY" : "ALIGNMENT IN PROGRESS";
      badge.dataset.ready = ready ? "true" : "false";
    }
    const exhausted = model.events.length >= Number(model.state.max_edits);
    setReadout(ready ? "THRESHOLD REACHED · CERTIFY THE LOOM" : exhausted ? "EDIT LIMIT REACHED · CERTIFY FOR A FRESH LOOM" : "SHIFT A TILE RUN TO IMPROVE COLUMN AGREEMENT", ready ? "ready" : exhausted ? "error" : "idle");
  }

  function tileMarkup(row, tile, rowIndex) {
    const color = model.state.colors[Number(tile.color)] || {};
    const column = model.columns[row.id][Number(tile.index)];
    const cell = Number(model.state.stage.cell_width);
    const labelWidth = 108;
    return `<button type="button" class="loom-tile" data-row-id="${clean(row.id)}" data-index="${tile.index}" aria-label="${clean(row.label)} tile ${Number(tile.index) + 1}, ${clean(tile.color_name)}" style="left:${labelWidth + column * cell + 3}px;top:6px;--tile-color:${clean(color.hex)};--tile-ink:${clean(color.ink)}"><span>${Number(tile.index) + 1}</span></button>`;
  }

  function renderBoard() {
    const board = document.querySelector(".loom-board");
    if (!board) return;
    board.innerHTML = (model.state.rows || []).map((row, rowIndex) => `
      <div class="loom-row" style="top:${rowIndex * Number(model.state.stage.row_height)}px;height:${Number(model.state.stage.row_height)}px">
        <div class="loom-row-label"><span>${clean(row.label)}</span><small>${row.tiles.length} TILES</small></div>
        <div class="loom-track"></div>
        ${(row.tiles || []).map((tile) => tileMarkup(row, tile, rowIndex)).join("")}
      </div>`).join("") + `<div class="loom-column-audit">${Array.from({length: Number(model.state.column_count)}, (_, index) => `<span class="ribbon-column-score" style="left:${108 + index * Number(model.state.stage.cell_width) + 2}px">0</span>`).join("")}</div>`;
    if (model.interaction !== "full") return;
    board.querySelectorAll(".loom-tile").forEach((tile) => {
      tile.addEventListener("pointerdown", (event) => {
        if (model.busy || model.terminal) return;
        const rowId = tile.dataset.rowId;
        const breakIndex = Number(tile.dataset.index);
        if (breakIndex < 1) {
          setReadout("GRAB A TILE AFTER THE FIRST · SUFFIX SHIFTS PRESERVE ORDER", "error");
          return;
        }
        const startColumn = Number(model.columns[rowId]?.[breakIndex]);
        if (!Number.isInteger(startColumn)) {
          setReadout("THAT TILE IS NOT AVAILABLE IN THE CURRENT LOOM", "error");
          return;
        }
        model.drag = {
          rowId,
          breakIndex,
          startColumn,
          startX: event.clientX,
          lastX: event.clientX,
          travelPx: 0,
          pointerPath: [{x: event.clientX, y: event.clientY}],
          pointerId: event.pointerId,
        };
        tile.classList.add("is-dragging");
        tile.setPointerCapture?.(event.pointerId);
        event.preventDefault();
      });
    });
    board.onpointermove = (event) => {
      if (!model.drag || event.pointerId !== model.drag.pointerId) return;
      model.drag.travelPx += Math.abs(event.clientX - model.drag.lastX);
      model.drag.lastX = event.clientX;
      model.drag.pointerPath.push({x: event.clientX, y: event.clientY});
    };
    board.onpointerup = (event) => finishDrag(event);
    board.onpointercancel = (event) => finishDrag(event, true);
  }

  function finishDrag(event, cancelled = false) {
    if (!model.drag || event.pointerId !== model.drag.pointerId) return;
    const drag = model.drag;
    model.drag = null;
    document.querySelectorAll(".loom-tile.is-dragging").forEach((node) => node.classList.remove("is-dragging"));
    if (cancelled) return;
    const cell = Number(model.state.stage.cell_width);
    const finalX = Number(event.clientX);
    const finalY = Number(event.clientY);
    drag.travelPx += Math.abs(finalX - drag.lastX);
    drag.pointerPath.push({x: finalX, y: finalY});
    const distance = finalX - drag.startX;
    const delta = Math.abs(distance) >= cell * 0.45 ? (distance > 0 ? 1 : -1) : 0;
    if (!delta || drag.travelPx < cell * 0.55 || drag.pointerPath.length < 3) {
      setReadout("DRAG ONE CELL LEFT OR RIGHT TO SHIFT THE TILE RUN", "error");
      return;
    }
    applyShift(drag.rowId, drag.breakIndex, delta, {
      sample_count: drag.pointerPath.length,
      travel_px: drag.travelPx,
      start_column: drag.startColumn,
      end_column: drag.startColumn + delta,
      pointer_path: drag.pointerPath,
    });
  }

  function applyShift(rowId, breakIndex, delta, gesture = null) {
    if (model.busy || model.terminal) return;
    if (model.events.length >= Number(model.state.max_edits)) {
      setReadout("EDIT LIMIT REACHED · CERTIFY TO FINISH OR RECEIVE A FRESH LOOM", "error");
      return;
    }
    document.querySelector(".ribbon-verdict-fail")?.remove();
    document.querySelector(".ribbon-consensus")?.classList.remove("is-fresh-fail");
    const shifted = validShift(model.columns[rowId], breakIndex, delta);
    if (!shifted) {
      setReadout("THAT RUN WOULD COLLIDE WITH THE LOOM EDGE OR BREAK ORDER", "error");
      return;
    }
    model.columns[rowId] = shifted;
    const after = scoreAlignment();
    model.events.push({
      sequence: model.events.length + 1,
      kind: "shift",
      row_id: rowId,
      break_index: breakIndex,
      delta,
      input_source: model.interaction === "full" ? "tile_run_drag" : "proxy_shift",
      ...(gesture ? {gesture} : {}),
      score_after: after,
      breakdown_after: after,
    });
    renderBoard();
    updateSelectOptions();
    updatePanel();
  }

  async function submit() {
    if (model.busy || model.terminal) return;
    model.busy = true;
    document.querySelectorAll("button,select").forEach((node) => { node.disabled = true; });
    const finalScore = scoreAlignment();
    setReadout("CERTIFYING THE RIBBON CONSENSUS…", "pending");
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      interaction_mode: model.interaction,
      events: model.events,
      final_columns: model.columns,
      final_score: finalScore.score,
      score_breakdown: finalScore,
      move_count: model.events.length,
      completed: finalScore.score >= Number(model.state.score_floor),
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
        document.querySelector(".ribbon-consensus")?.classList.add("is-pass");
        document.querySelector(".ribbon-consensus")?.insertAdjacentHTML("beforeend", '<div class="ribbon-verdict ribbon-verdict-pass"><small>LOOM CERTIFICATE ACCEPTED</small><strong>PASS</strong></div>');
        setReadout("PASS · RIBBON CONSENSUS CERTIFIED", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        const shell = document.querySelector(".ribbon-consensus");
        shell?.classList.add("is-fresh-fail");
        shell?.insertAdjacentHTML("beforeend", '<div class="ribbon-verdict ribbon-verdict-fail"><small>ALIGNMENT REJECTED · FRESH LOOM ISSUED</small><strong>FAIL</strong></div>');
        model.helpers.setReadout("FAIL · FRESH LOOM ISSUED", "error");
      } else {
        model.busy = false;
        document.querySelectorAll("button,select").forEach((node) => { node.disabled = false; });
        setReadout("FAIL · CERTIFICATION SERVICE OFFLINE", "error");
      }
    } catch (_error) {
      model.busy = false;
      document.querySelectorAll("button,select").forEach((node) => { node.disabled = false; });
      setReadout("FAIL · CERTIFICATION SERVICE OFFLINE", "error");
    }
  }

  function bindControls() {
    const rowSelect = document.querySelector("#ribbon-row-select");
    rowSelect?.addEventListener("change", updateSelectOptions);
    document.querySelector("[data-shift='1']")?.addEventListener("click", () => {
      applyShift(rowSelect.value, Number(document.querySelector("#ribbon-break-select").value), 1);
    });
    document.querySelector("[data-shift='-1']")?.addEventListener("click", () => {
      applyShift(rowSelect.value, Number(document.querySelector("#ribbon-break-select").value), -1);
    });
    document.querySelector(".ribbon-submit")?.addEventListener("click", submit);
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "ribbon-consensus";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    model.state = state;
    model.helpers = helpers;
    model.interaction = String((state.control_condition || {}).interaction || "simplified");
    model.columns = Object.fromEntries(Object.entries(state.initial_columns || {}).map(([key, value]) => [key, [...value]]));
    model.events = [];
    model.score = null;
    model.drag = null;
    model.busy = false;
    model.terminal = false;
    const colorLegend = (state.colors || []).map((color) => `<span class="ribbon-color-key"><i style="background:${clean(color.hex)}"></i>${clean(color.name)}</span>`).join("");
    const interactionCopy = model.interaction === "full"
      ? "Drag any tile one loom cell. Its suffix follows, preserving ribbon order."
      : "Choose a ribbon and boundary, then use the visible shift controls. The same suffix move is replayed.";
    helpers.app.innerHTML = `<section class="ribbon-consensus" data-interaction="${clean(model.interaction)}" data-challenge-id="${clean(state.challenge_id)}">
      <header class="ribbon-head">
        <div><span class="ribbon-kicker">OPEN-PHYLO / CONSENSUS LOOM</span><h1>${clean(state.prompt)}</h1><p>Every colored tile keeps its ribbon order. Only a suffix may move across a column gap.</p></div>
        <div class="ribbon-target-card"><small>CERTIFICATION FLOOR</small><strong>${clean(state.score_floor)}</strong><span>live sum-of-pairs score</span></div>
      </header>
      <section class="ribbon-legend"><span class="ribbon-legend-title">VISIBLE TILE PALETTE</span>${colorLegend}<span class="ribbon-id">LOOM ${clean(state.challenge_id)}</span></section>
      <main class="ribbon-main">
        <section class="loom-panel">
          <div class="loom-panel-head"><div><span>WEAVE FIELD / ${clean(state.rows.length)} RIBBONS</span><h2>Align the vertical consensus bands</h2></div><b class="ribbon-cert-badge" data-ready="false">ALIGNMENT IN PROGRESS</b></div>
          <div class="loom-scroll"><div class="loom-board" style="--loom-columns:${state.column_count};--loom-cell:${state.stage.cell_width}px;--loom-row-height:${state.stage.row_height}px;width:${108 + state.column_count * state.stage.cell_width}px;height:${state.rows.length * state.stage.row_height + 20}px"></div></div>
          <div class="loom-column-key"><span>VERTICAL COLUMN AUDIT</span><small>positive columns reward agreement · gap penalties are included in score</small></div>
        </section>
        <section class="ribbon-console-row">
          <aside class="ribbon-console">
            <span class="console-kicker">${model.interaction === "full" ? "DIRECT LOOM CONTROL" : "BOUNDARY CONTROL"}</span><h2>${model.interaction === "full" ? "Drag a tile run" : "Shift a tile run"}</h2><p>${interactionCopy}</p>
            ${model.interaction === "simplified" ? `<label>RIBBON<select id="ribbon-row-select"></select></label><label>BOUNDARY<select id="ribbon-break-select"></select></label><div class="ribbon-shift-buttons"><button type="button" data-shift="-1">← CLOSE GAP</button><button type="button" data-shift="1">OPEN GAP →</button></div>` : `<div class="direct-hint"><i>1</i><span>Press on any tile after the first.</span><i>2</i><span>Drag one cell left or right.</span><i>3</i><span>Release to replay the suffix shift.</span></div>`}
            <div class="ribbon-rule"><b>ORDER LOCK</b><span>Tiles never reorder; a move shifts this tile and everything after it in the row.</span></div>
          </aside>
          <aside class="ribbon-score-card"><span class="console-kicker">LIVE COLUMN FEEDBACK</span><div class="ribbon-score-line"><strong class="ribbon-score-value">0</strong><small class="ribbon-score-floor"></small></div><div class="ribbon-score-progress"><i></i></div><div class="ribbon-score-stats"><span class="ribbon-match-value"></span><span class="ribbon-gap-value"></span><span class="ribbon-moves-value"></span></div><div class="ribbon-score-note">The floor is reachable from this loom, but the target alignment is not shown.</div></aside>
        </section>
      </main>
      <footer class="ribbon-foot"><div><span>CONSENSUS STATUS</span><div class="readout" data-status="idle">SHIFT A TILE RUN TO IMPROVE COLUMN AGREEMENT</div></div><button type="button" class="ribbon-submit">${clean(state.submit_label || "CERTIFY ALIGNMENT")}</button></footer>
      ${helpers.cheatPanelTemplate()}
    </section>`;
    renderBoard();
    updateSelectOptions();
    bindControls();
    updatePanel();
    helpers.installCheatPanel();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.ribbon_consensus = {render};
})();
