(() => {
  "use strict";

  const ID = "offcut_foundry";
  const directions = [[-1, 0], [1, 0], [0, -1], [0, 1]];

  function escapeText(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function shapeKey(points) {
    if (!points.length) return "";
    const minRow = Math.min(...points.map(point => point[0]));
    const minColumn = Math.min(...points.map(point => point[1]));
    return points
      .map(point => `${point[0] - minRow},${point[1] - minColumn}`)
      .sort()
      .join(";");
  }

  function renderPiecePreview(piece) {
    const height = Math.max(...piece.shape.map(point => point[0])) + 1;
    const width = Math.max(...piece.shape.map(point => point[1])) + 1;
    const occupied = new Set(piece.shape.map(point => `${point[0]},${point[1]}`));
    let cells = "";
    for (let row = 0; row < height; row += 1) {
      for (let column = 0; column < width; column += 1) {
        cells += `<i class="of-preview-cell ${occupied.has(`${row},${column}`) ? "occupied" : ""}"></i>`;
      }
    }
    return `<span class="of-piece-preview" style="--preview-cols:${width};--preview-rows:${height}">${cells}</span>`;
  }

  function render(state, helpers) {
    const root = helpers.app;
    const condition = state.control_condition || {};
    const interaction = condition.interaction || state.interaction || "full";
    const simplified = interaction === "simplified";
    const board = state.board || {};
    const cells = Array.isArray(board.cells) ? board.cells : [];
    const byId = new Map(cells.map(cell => [cell.id, cell]));
    const decoyMarks = new Map((Array.isArray(board.decoy_marks) ? board.decoy_marks : []).map(mark => [mark.cell_id, mark.mark]));
    const pieces = Array.isArray(state.pieces) ? state.pieces : [];
    const palette = board.palette || {};
    let active = new Set(cells.map(cell => cell.id));
    let selected = new Set();
    let trace = [];
    let selectedPiece = null;
    let cutPieces = new Set();
    let history = [];
    let events = [];
    let dragging = false;
    let dragPointer = null;
    let submitted = false;

    root.innerHTML = `<section class="offcut-shell" data-interaction="${escapeText(interaction)}">
      <header class="of-header">
        <div><div class="of-kicker">MATERIAL RECOVERY / BAY 07</div><h1>Offcut Foundry <span>✦</span></h1><p>Partition the live stock into the silhouettes on the cut list.</p></div>
        <div class="of-mode">${simplified ? "SIMPLIFIED · PROXY CUTTING" : "FULL · DIRECT TRACING"}<small>${board.rows} × ${board.columns} stock · ${pieces.length} requested offcuts</small></div>
      </header>
      <section class="of-brief"><div><b>FOUNDRY ORDER</b><span>Every cell belongs to exactly one offcut.</span></div><div><b>EDGE RULE</b><span>A cut must touch the stock edge or a previous cut.</span></div><div><b>RECOVERY</b><span>${state.requirements?.undo_budget ?? 0} undo token${Number(state.requirements?.undo_budget || 0) === 1 ? "" : "s"} available.</span></div></section>
      <main class="of-layout">
        <aside class="of-recipe"><div class="of-label">CUT LIST <small>${simplified ? "select a silhouette" : "read the silhouettes"}</small></div><div class="of-piece-list">${pieces.map(piece => `<button class="of-piece" data-piece="${escapeText(piece.id)}" type="button"><span class="of-piece-number">${escapeText(piece.id.replace("piece-", ""))}</span>${renderPiecePreview(piece)}<span class="of-piece-copy"><b>${escapeText(piece.label)}</b><small>${piece.area} CELLS · ${escapeText(piece.accent)}</small></span><span class="of-piece-state">OPEN</span></button>`).join("")}</div><p class="of-recipe-note">The board has no printed partition lines. Read the silhouettes, test an exposed cut, and inspect the remainder after every extraction.</p></aside>
        <section class="of-work-area"><div class="of-label"><span>ENAMEL STOCK / <strong id="of-stock-count"></strong> CELLS REMAIN</span><small id="of-trace-help"></small></div><div class="of-board-frame"><div class="of-board" role="grid" aria-label="Enamel stock board" style="--board-cols:${Number(board.columns || 1)};--board-rows:${Number(board.rows || 1)}">${cells.map(cell => { const mark = decoyMarks.get(cell.id); return `<button class="of-cell" type="button" role="gridcell" data-cell="${escapeText(cell.id)}" aria-label="Stock cell row ${cell.row + 1}, column ${cell.column + 1}" style="--tone:${cell.tone};--grain:${cell.grain}">${mark ? `<span class="of-decoy-mark" data-mark="${escapeText(mark)}" aria-hidden="true"></span>` : ""}</button>`; }).join("")}<div class="of-spark-layer" aria-hidden="true"></div></div></div><div class="of-work-status"><span class="of-led"></span><strong id="of-status">READY TO CUT</strong><small id="of-status-detail"></small></div></section>
        <aside class="of-controls"><div class="of-label">CONTROL CONSOLE</div><div class="of-selected"><small>ACTIVE SELECTION</small><strong id="of-selected-label">${simplified ? "Choose a cut-list silhouette" : "Hold on the stock to trace"}</strong><span id="of-selected-count">0 cells</span></div>${simplified ? `<button class="of-action of-extract" id="of-extract" type="button" disabled>EXTRACT SELECTED ↗</button><button class="of-secondary" id="of-clear" type="button">CLEAR SELECTION</button>` : `<div class="of-direct-card"><b>DIRECT TRACE</b><span>Press on a cell, hold, and pass through the connected cells of one requested silhouette. Release to cut.</span></div>`}<button class="of-undo" id="of-undo" type="button" disabled>UNDO LAST CUT <span>0 / ${Number(state.requirements?.undo_budget || 0)}</span></button><div class="of-key"><span class="of-key-swatch"></span> uncut stock <span class="of-key-swatch selected"></span> current trace <span class="of-key-swatch spent"></span> spent</div></aside>
      </main>
      <footer class="of-footer"><div class="readout" data-status="idle">READY — inspect the stock and cut list</div><button class="of-certify" id="of-certify" type="button">CERTIFY CUTS</button></footer>
    </section>`;
    document.body.dataset.mechanic = ID;

    const boardNode = root.querySelector(".of-board");
    const statusNode = root.querySelector("#of-status");
    const detailNode = root.querySelector("#of-status-detail");
    const selectedLabel = root.querySelector("#of-selected-label");
    const selectedCount = root.querySelector("#of-selected-count");
    const undoButton = root.querySelector("#of-undo");
    const extractButton = root.querySelector("#of-extract");
    const certifyButton = root.querySelector("#of-certify");
    const undoBudget = Number(state.requirements?.undo_budget || 0);
    let undoCount = 0;

    function log(kind, source, details = {}) {
      events.push({sequence: events.length + 1, kind, input_source: source, ...details});
    }

    function setMessage(message, detail = "", status = "idle") {
      statusNode.textContent = message;
      detailNode.textContent = detail;
      const readout = root.querySelector(".readout");
      if (readout) {
        readout.textContent = message + (detail ? ` — ${detail}` : "");
        readout.dataset.status = status;
      }
      helpers.setReadout(message + (detail ? ` — ${detail}` : ""), status);
    }

    function cellPoints(ids) {
      return ids.map(id => [Number(byId.get(id)?.row), Number(byId.get(id)?.column)]);
    }

    function isConnected(ids) {
      if (!ids.length) return false;
      const pool = new Set(ids);
      const seen = new Set([ids[0]]);
      const queue = [ids[0]];
      while (queue.length) {
        const current = byId.get(queue.shift());
        if (!current) return false;
        for (const candidate of cells) {
          if (pool.has(candidate.id) && !seen.has(candidate.id) && Math.abs(candidate.row - current.row) + Math.abs(candidate.column - current.column) === 1) {
            seen.add(candidate.id);
            queue.push(candidate.id);
          }
        }
      }
      return seen.size === pool.size;
    }

    function isExposed(ids) {
      const pool = new Set(ids);
      return ids.some(id => {
        const cell = byId.get(id);
        return directions.some(([dr, dc]) => {
          const row = cell.row + dr;
          const column = cell.column + dc;
          if (row < 0 || row >= Number(board.rows) || column < 0 || column >= Number(board.columns)) return true;
          const neighbor = `cell-${String(row).padStart(2, "0")}-${String(column).padStart(2, "0")}`;
          return !active.has(neighbor) && !pool.has(neighbor);
        });
      });
    }

    function pieceFor(ids) {
      const key = shapeKey(cellPoints(ids));
      return pieces.find(piece => shapeKey(piece.shape) === key && !cutPieces.has(piece.id)) || null;
    }

    function refresh() {
      root.querySelectorAll(".of-cell").forEach(cell => {
        const id = cell.dataset.cell;
        cell.classList.toggle("spent", !active.has(id));
        cell.classList.toggle("selected", selected.has(id));
      });
      root.querySelectorAll(".of-piece").forEach(pieceNode => {
        const piece = pieces.find(item => item.id === pieceNode.dataset.piece);
        pieceNode.classList.toggle("chosen", pieceNode.dataset.piece === selectedPiece);
        pieceNode.classList.toggle("cut", cutPieces.has(pieceNode.dataset.piece));
        pieceNode.querySelector(".of-piece-state").textContent = cutPieces.has(pieceNode.dataset.piece) ? "CUT" : (pieceNode.dataset.piece === selectedPiece ? "SELECTED" : "OPEN");
        if (piece) pieceNode.setAttribute("aria-label", `${piece.label}, ${piece.area} cells, ${cutPieces.has(piece.id) ? "cut" : "open"}`);
      });
      root.querySelector("#of-stock-count").textContent = String(active.size);
      selectedCount.textContent = `${selected.size} cell${selected.size === 1 ? "" : "s"}`;
      if (selectedPiece) {
        const piece = pieces.find(item => item.id === selectedPiece);
        selectedLabel.textContent = piece ? `${piece.label} · ${piece.area} cells` : "Unknown silhouette";
      } else if (!selected.size) {
        selectedLabel.textContent = simplified ? "Choose a cut-list silhouette" : "Hold on the stock to trace";
      } else {
        selectedLabel.textContent = pieceFor([...selected])?.label || "Trace in progress";
      }
      if (simplified) extractButton.disabled = !selectedPiece || selected.size === 0;
      undoButton.disabled = history.length === 0 || undoCount >= undoBudget;
      undoButton.querySelector("span").textContent = `${undoCount} / ${undoBudget}`;
      const complete = cutPieces.size === pieces.length && active.size === 0;
      if (!dragging && !selected.size && complete) setMessage("READY TO CERTIFY", "all requested offcuts are on the rack", "idle");
    }

    function addSelectedCell(id) {
      if (!id || !active.has(id)) return;
      if (!selected.has(id)) {
        selected.add(id);
        trace.push(id);
      }
      refresh();
    }

    function cellAt(x, y) {
      const node = document.elementFromPoint(x, y)?.closest?.(".of-cell");
      return node && boardNode.contains(node) ? node.dataset.cell : null;
    }

    function resetSelection(message = "SELECTION CLEARED", detail = "choose another connected cut") {
      selected.clear();
      trace = [];
      selectedPiece = simplified ? selectedPiece : null;
      setMessage(message, detail, "idle");
      refresh();
    }

    function extract(source) {
      const ids = [...selected];
      if (!ids.length) {
        setMessage("NOTHING SELECTED", "trace a connected silhouette first", "error");
        return;
      }
      const piece = pieceFor(ids);
      if (!piece) {
        setMessage("CUT REJECTED", "the traced cells do not match an open silhouette", "error");
        return;
      }
      if (!isConnected(ids)) {
        setMessage("CUT REJECTED", "the selected cells must touch edge to edge", "error");
        return;
      }
      if (!isExposed(ids)) {
        setMessage("CUT REJECTED", "that pocket is sealed; open the remainder first", "error");
        return;
      }
      log("cut", source, {piece_id: piece.id, cells: ids, trace: source === "direct_trace" ? trace.slice() : ids.slice()});
      history.push({piece_id: piece.id, cells: ids.slice()});
      ids.forEach(id => active.delete(id));
      cutPieces.add(piece.id);
      selected.clear();
      trace = [];
      selectedPiece = null;
      setMessage("OFFCUT EXTRACTED", `${piece.label} removed cleanly`, "idle");
      refresh();
    }

    function undo() {
      if (!history.length || undoCount >= undoBudget) return;
      const last = history.pop();
      last.cells.forEach(id => active.add(id));
      cutPieces.delete(last.piece_id);
      undoCount += 1;
      log("undo", simplified ? "proxy_undo" : "direct_undo", {piece_id: last.piece_id});
      resetSelection("LAST CUT RESTORED", `${last.piece_id} is back in the stock`);
    }

    root.querySelectorAll(".of-piece").forEach(pieceNode => {
      pieceNode.addEventListener("click", () => {
        if (!simplified || cutPieces.has(pieceNode.dataset.piece)) return;
        selectedPiece = pieceNode.dataset.piece;
        selected.clear();
        trace = [];
        log("piece_select", "proxy_piece_select", {piece_id: selectedPiece});
        setMessage("SILHOUETTE SELECTED", "click its cells, then extract", "idle");
        refresh();
      });
    });

    root.querySelectorAll(".of-cell").forEach(cell => {
      cell.addEventListener("click", () => {
        if (!simplified || dragging || !active.has(cell.dataset.cell)) return;
        const id = cell.dataset.cell;
        const shouldSelect = !selected.has(id);
        if (shouldSelect) selected.add(id); else selected.delete(id);
        log("select_cell", "proxy_cell", {cell_id: id, selected: shouldSelect});
        setMessage(shouldSelect ? "CELL MARKED" : "CELL UNMARKED", "assemble the selected silhouette", "idle");
        refresh();
      });
    });

    boardNode.addEventListener("pointerdown", event => {
      if (simplified || submitted || event.button !== 0) return;
      const id = event.target.closest?.(".of-cell")?.dataset.cell;
      if (!id || !active.has(id)) return;
      dragging = true;
      dragPointer = event.pointerId;
      trace = [];
      selected.clear();
      boardNode.setPointerCapture(event.pointerId);
      addSelectedCell(id);
      setMessage("TRACING CUT", "keep the pointer down through the connected cells", "idle");
      event.preventDefault();
    });
    boardNode.addEventListener("pointermove", event => {
      if (!dragging || event.pointerId !== dragPointer) return;
      addSelectedCell(cellAt(event.clientX, event.clientY));
    });
    boardNode.addEventListener("pointerup", event => {
      if (!dragging || event.pointerId !== dragPointer) return;
      dragging = false;
      dragPointer = null;
      extract("direct_trace");
      event.preventDefault();
    });
    boardNode.addEventListener("pointercancel", () => {
      if (!dragging) return;
      dragging = false;
      dragPointer = null;
      resetSelection("TRACE CANCELLED", "the stock was not changed");
    });
    boardNode.addEventListener("lostpointercapture", () => {
      if (dragging) {
        dragging = false;
        dragPointer = null;
        resetSelection("TRACE CANCELLED", "the stock was not changed");
      }
    });

    root.querySelector("#of-clear")?.addEventListener("click", () => resetSelection());
    extractButton?.addEventListener("click", () => extract("proxy_extract"));
    undoButton.addEventListener("click", undo);
    certifyButton.addEventListener("click", async () => {
      if (submitted) return;
      submitted = true;
      log("certify", "certify_button");
      certifyButton.disabled = true;
      try {
        const response = await fetch("/result", {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify({
            mechanic_id: state.mechanic_id,
            task_id: state.task_id,
            challenge_id: state.challenge_id,
            control_condition: state.control_condition,
            events,
          }),
        });
        const outcome = await response.json();
        if (outcome.passed) {
          root.querySelector(".offcut-shell").classList.add("of-passed");
          setMessage("PASS", "the board is fully partitioned with no waste", "passed");
        } else if (outcome.state) {
          render(outcome.state, helpers);
          helpers.setReadout("FAIL — fresh stock loaded", "error");
        } else {
          submitted = false;
          certifyButton.disabled = false;
          setMessage(outcome.feedback || "CERTIFICATION FAILED", "review the cut list and try again", "error");
        }
      } catch (_error) {
        submitted = false;
        certifyButton.disabled = false;
        setMessage("SUBMISSION ERROR", "certification can be retried", "error");
      }
    });

    root.querySelector("#of-trace-help").textContent = simplified ? "click cells → extract" : "hold + trace → release";
    refresh();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[ID] = {rootSelector: ".offcut-shell", render};
})();
