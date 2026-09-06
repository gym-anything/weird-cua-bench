(function () {
  const MECHANIC_ID = "leaning_tower_of_panels";
  const WIDTH = 880;
  const HEIGHT = 540;
  const TAU = Math.PI * 2;

  function mod(value, size) {
    return ((value % size) + size) % size;
  }

  function wrapAngle(value) {
    return mod(value + Math.PI, TAU) - Math.PI;
  }

  function pointInPolygon(point, polygon) {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const xi = polygon[i][0], yi = polygon[i][1];
      const xj = polygon[j][0], yj = polygon[j][1];
      const cross = (yi > point.y) !== (yj > point.y)
        && point.x < (xj - xi) * (point.y - yi) / ((yj - yi) || 0.00001) + xi;
      if (cross) inside = !inside;
    }
    return inside;
  }

  function neighbors(blank, rows, sectors) {
    const row = Math.floor(blank / sectors);
    const sector = blank % sectors;
    const result = [row * sectors + mod(sector - 1, sectors), row * sectors + mod(sector + 1, sectors)];
    if (row > 0) result.push((row - 1) * sectors + sector);
    if (row + 1 < rows) result.push((row + 1) * sectors + sector);
    return Array.from(new Set(result));
  }

  function sameGrid(left, right) {
    return left.length === right.length && left.every((item, index) => item === right[index]);
  }

  function logicalPoint(canvas, event) {
    const box = canvas.getBoundingClientRect();
    return {
      x: (event.clientX - box.left) * WIDTH / box.width,
      y: (event.clientY - box.top) * HEIGHT / box.height,
    };
  }

  function bilinear(polygon, u, v) {
    const topX = polygon[0][0] + (polygon[1][0] - polygon[0][0]) * u;
    const topY = polygon[0][1] + (polygon[1][1] - polygon[0][1]) * u;
    const bottomX = polygon[3][0] + (polygon[2][0] - polygon[3][0]) * u;
    const bottomY = polygon[3][1] + (polygon[2][1] - polygon[3][1]) * u;
    return [topX + (bottomX - topX) * v, topY + (bottomY - topY) * v];
  }

  function renderMechanic(state, api) {
    const interaction = state.control_condition?.interaction || "simplified";
    const rows = Number(state.floor_count);
    const sectors = Number(state.sector_count);
    const tiles = new Map((state.tiles || []).map((tile) => [tile.id, tile]));
    const goal = Array.from({length: rows * sectors}, (_, index) => index === rows * sectors - 1
      ? null
      : `panel-${Math.floor(index / sectors) + 1}-${index % sectors + 1}`);
    const model = {
      state,
      interaction,
      rows,
      sectors,
      tiles,
      goal,
      grid: [...state.start_grid],
      view: 0,
      viewFloat: 0,
      events: [],
      moveCount: 0,
      renderedCells: [],
      drag: null,
      submitting: false,
      retryState: null,
    };
    window.leaningTowerModel = model;
    document.body.dataset.mechanic = MECHANIC_ID;

    api.app.innerHTML = `
      <main class="ltp-shell" data-interaction="${api.text(interaction)}" data-fresh-failure="false">
        <header class="ltp-header">
          <div>
            <p class="ltp-kicker">PISA RESTORATION OFFICE · WRAP SURVEY 13</p>
            <h1>The Leaning Tower of Panels</h1>
          </div>
          <div class="ltp-header-mark" aria-hidden="true"><span></span><b>⅓</b></div>
        </header>
        <p class="ltp-prompt">${api.text(state.prompt)}</p>
        <section class="ltp-workbench">
          <div class="ltp-stage-wrap">
            <canvas id="ltp-stage" width="${WIDTH}" height="${HEIGHT}" aria-label="Rotatable cylindrical panel tower"></canvas>
            <div class="ltp-mode-strip">
              <span>${interaction === "simplified" ? "BUTTON + PANEL MODE" : "DIRECT STONE MODE"}</span>
              <span>${interaction === "simplified" ? "ROTATE, THEN CLICK A NEIGHBOR" : "DRAG SKY TO TURN · DRAG PANEL INTO OPENING"}</span>
            </div>
            <div class="ltp-verdict" aria-live="assertive"><strong></strong><span></span><button id="ltp-fresh-retry" type="button">OPEN FRESH COMMISSION</button></div>
          </div>
          <aside class="ltp-docket">
            <div class="ltp-docket-title"><small>ENGINEER'S DOCKET</small><strong id="ltp-view-label">FACE 1 / ${sectors}</strong></div>
            <dl class="ltp-metrics">
              <div><dt>FLOORS</dt><dd>${rows}</dd></div>
              <div><dt>SECTORS</dt><dd>${sectors}</dd></div>
              <div><dt>BFS PAR</dt><dd>${Number(state.optimal_move_count)}</dd></div>
              <div><dt>LIMIT</dt><dd>${Number(state.allowed_moves)}</dd></div>
            </dl>
            <div class="ltp-progress">
              <div><span>ALIGNED PANELS</span><b id="ltp-aligned">0/${rows * sectors - 1}</b></div>
              <div><span>SLIDES</span><b id="ltp-moves">0/${Number(state.allowed_moves)}</b></div>
              <i><em id="ltp-progress-bar"></em></i>
            </div>
            ${interaction === "simplified" ? `
              <div class="ltp-rotate-controls" aria-label="Tower rotation controls">
                <button id="ltp-turn-left" type="button" aria-label="Rotate tower left">‹</button>
                <span>TURN TOWER</span>
                <button id="ltp-turn-right" type="button" aria-label="Rotate tower right">›</button>
              </div>` : `
              <div class="ltp-direct-seal"><span>☞</span><b>TURN THE STONE</b><small>Drag sky to turn. Drag an edge panel offscreen toward a remembered opening.</small></div>`}
            <div class="ltp-rule">
              <span class="ltp-rule-swatch"></span>
              <p><b>Completion mark</b> Floors read 1 downward; every painted seam continues around the hidden back; the opening rests in the brass bay.</p>
            </div>
            <div class="ltp-actions">
              <button id="ltp-reset" class="ltp-reset" type="button">RESET LAYOUT</button>
              <button id="ltp-certify" class="ltp-certify" type="button">CERTIFY TOWER</button>
            </div>
            <p class="readout ltp-readout" data-status="idle" aria-live="polite"></p>
          </aside>
        </section>
      </main>`;

    const shell = api.app.querySelector(".ltp-shell");
    const canvas = api.app.querySelector("#ltp-stage");
    const ctx = canvas.getContext("2d");
    const verdict = api.app.querySelector(".ltp-verdict");

    function event(kind, values) {
      model.events.push({sequence: model.events.length + 1, kind, ...values});
    }

    function normalizedTrace(points) {
      const compact = [];
      for (const point of points) {
        const normalized = {
          x: Number((point.x / WIDTH).toFixed(6)),
          y: Number((point.y / HEIGHT).toFixed(6)),
        };
        const previous = compact[compact.length - 1];
        if (!previous || previous.x !== normalized.x || previous.y !== normalized.y) compact.push(normalized);
      }
      return {coordinate_space: "normalized_canvas_v1", points: compact};
    }

    function alignedCount() {
      return model.grid.reduce((count, item, index) => count + (item && item === goal[index] ? 1 : 0), 0);
    }

    function leanAmount() {
      const total = rows * sectors - 1;
      return 28 * (1 - alignedCount() / total);
    }

    function cellGeometry(row, sector, viewValue = model.viewFloat) {
      const angle = wrapAngle((sector - viewValue) * TAU / sectors);
      const halfArc = Number(state.visible_arc_degrees) * Math.PI / 360;
      if (Math.abs(angle) > halfArc + 0.0001) return null;
      const halfPanel = TAU / sectors * 0.47;
      const centerX = 440;
      const radiusX = 252;
      const top = 68;
      const towerHeight = 414;
      const rowHeight = towerHeight / rows;
      const depth = Math.cos(angle);
      const perspectiveLift = (1 - depth) * 7;
      const lean = leanAmount();
      const leanTop = -lean * (1 - row / Math.max(1, rows));
      const leanBottom = -lean * (1 - (row + 1) / Math.max(1, rows));
      const leftAngle = angle - halfPanel;
      const rightAngle = angle + halfPanel;
      const x1 = centerX + Math.sin(leftAngle) * radiusX + leanTop;
      const x2 = centerX + Math.sin(rightAngle) * radiusX + leanTop;
      const y1 = top + row * rowHeight + perspectiveLift;
      const y2 = top + (row + 1) * rowHeight + perspectiveLift;
      return {
        index: row * sectors + sector,
        row,
        sector,
        depth,
        polygon: [[x1, y1], [x2, y1], [x2 + leanBottom - leanTop, y2], [x1 + leanBottom - leanTop, y2]],
      };
    }

    function tracePolygon(polygon) {
      ctx.beginPath();
      ctx.moveTo(polygon[0][0], polygon[0][1]);
      for (let index = 1; index < polygon.length; index++) ctx.lineTo(polygon[index][0], polygon[index][1]);
      ctx.closePath();
    }

    function muralHeight(tile, band, boundary) {
      const rowPhase = Number(state.mural.row_phases[tile.floor - 1]);
      const bandPhase = Number(state.mural.band_phases[band]);
      return 0.34 + band * 0.22
        + Math.sin(TAU * boundary / sectors + rowPhase + bandPhase) * (0.055 + band * 0.012);
    }

    function drawPanel(cell, tileId) {
      const polygon = cell.polygon;
      tracePolygon(polygon);
      ctx.save();
      ctx.clip();
      if (!tileId) {
        const opening = ctx.createLinearGradient(0, polygon[0][1], 0, polygon[2][1]);
        opening.addColorStop(0, "#101a1b");
        opening.addColorStop(1, "#020607");
        ctx.fillStyle = opening;
        ctx.fillRect(0, 0, WIDTH, HEIGHT);
        ctx.strokeStyle = "rgba(208,160,75,.28)";
        ctx.lineWidth = 3;
        for (let offset = -120; offset < 180; offset += 28) {
          ctx.beginPath();
          ctx.moveTo(polygon[0][0] + offset, polygon[0][1]);
          ctx.lineTo(polygon[3][0] + offset + 85, polygon[3][1]);
          ctx.stroke();
        }
        const middle = bilinear(polygon, 0.5, 0.54);
        ctx.fillStyle = "#d3aa61";
        ctx.font = "700 12px Georgia";
        ctx.textAlign = "center";
        ctx.fillText("OPENING", middle[0], middle[1]);
        ctx.restore();
        return;
      }
      const tile = tiles.get(tileId);
      const light = Math.round(29 + cell.depth * 20);
      const gradient = ctx.createLinearGradient(polygon[0][0], polygon[0][1], polygon[1][0], polygon[2][1]);
      gradient.addColorStop(0, `hsl(${tile.hue} 28% ${light + 9}%)`);
      gradient.addColorStop(0.52, `hsl(${tile.hue} 32% ${light + 2}%)`);
      gradient.addColorStop(1, `hsl(${tile.hue} 24% ${Math.max(18, light - 8)}%)`);
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, WIDTH, HEIGHT);
      ctx.globalAlpha = 0.17;
      ctx.strokeStyle = "#fff6df";
      ctx.lineWidth = 1;
      for (let y = polygon[0][1] + 8; y < polygon[3][1]; y += 11) {
        ctx.beginPath(); ctx.moveTo(polygon[0][0] - 8, y); ctx.lineTo(polygon[1][0] + 8, y - 5); ctx.stroke();
      }
      ctx.globalAlpha = 1;
      const bandColors = ["#f6c867", "#77d0c5", "#dc6d5f"];
      for (let band = 0; band < Number(state.mural.band_count); band++) {
        const leftV = muralHeight(tile, band, tile.mural_sector);
        const rightV = muralHeight(tile, band, tile.mural_sector + 1);
        const left = bilinear(polygon, 0, leftV);
        const right = bilinear(polygon, 1, rightV);
        const middle = bilinear(polygon, 0.5, (leftV + rightV) / 2 + Math.sin((tile.mural_sector + 0.5) * 1.7 + band) * 0.022);
        ctx.beginPath(); ctx.moveTo(left[0], left[1]); ctx.quadraticCurveTo(middle[0], middle[1], right[0], right[1]);
        ctx.strokeStyle = "rgba(22,22,20,.52)"; ctx.lineWidth = 10 - band; ctx.stroke();
        ctx.strokeStyle = bandColors[band]; ctx.lineWidth = 6 - band * 0.4; ctx.stroke();
      }
      const center = bilinear(polygon, 0.5, 0.72);
      const panelWidth = Math.abs(polygon[1][0] - polygon[0][0]);
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.font = `700 ${Math.max(18, Math.min(42, panelWidth * 0.34))}px Georgia`;
      ctx.lineWidth = 4;
      ctx.strokeStyle = "rgba(25,18,10,.68)";
      ctx.strokeText(String(tile.floor), center[0], center[1]);
      ctx.fillStyle = "#fff8e8";
      ctx.fillText(String(tile.floor), center[0], center[1]);
      ctx.restore();
    }

    function draw() {
      const sky = ctx.createLinearGradient(0, 0, 0, HEIGHT);
      sky.addColorStop(0, "#11282c"); sky.addColorStop(0.53, "#38645f"); sky.addColorStop(1, "#d5b76e");
      ctx.fillStyle = sky; ctx.fillRect(0, 0, WIDTH, HEIGHT);
      ctx.fillStyle = "rgba(255,239,184,.72)";
      ctx.beginPath(); ctx.arc(722, 102, 48, 0, TAU); ctx.fill();
      ctx.fillStyle = "rgba(11,25,25,.42)";
      for (let x = -20; x < WIDTH + 80; x += 110) {
        ctx.beginPath(); ctx.moveTo(x, HEIGHT); ctx.lineTo(x + 65, 430); ctx.lineTo(x + 145, HEIGHT); ctx.closePath(); ctx.fill();
      }
      ctx.fillStyle = "rgba(6,12,12,.54)"; ctx.fillRect(0, 493, WIDTH, 47);
      ctx.fillStyle = "rgba(0,0,0,.28)"; ctx.beginPath(); ctx.ellipse(438, 496, 282, 30, 0, 0, TAU); ctx.fill();

      model.renderedCells = [];
      for (let row = 0; row < rows; row++) {
        for (let sector = 0; sector < sectors; sector++) {
          const cell = cellGeometry(row, sector);
          if (cell) model.renderedCells.push(cell);
        }
      }
      model.renderedCells.sort((a, b) => a.depth - b.depth);
      for (const cell of model.renderedCells) {
        drawPanel(cell, model.grid[cell.index]);
        tracePolygon(cell.polygon);
        const blank = model.grid.indexOf(null);
        const actionable = model.grid[cell.index] && neighbors(blank, rows, sectors).includes(cell.index);
        ctx.strokeStyle = actionable ? "rgba(255,223,139,.94)" : "rgba(22,17,13,.72)";
        ctx.lineWidth = actionable ? 2.6 : 1.35;
        ctx.stroke();
        const rivets = [bilinear(cell.polygon, 0.06, 0.08), bilinear(cell.polygon, 0.94, 0.08), bilinear(cell.polygon, 0.06, 0.92), bilinear(cell.polygon, 0.94, 0.92)];
        ctx.fillStyle = "rgba(240,204,128,.66)";
        for (const rivet of rivets) { ctx.beginPath(); ctx.arc(rivet[0], rivet[1], 1.8, 0, TAU); ctx.fill(); }
      }
      const lean = leanAmount();
      ctx.strokeStyle = "#e8d7ae"; ctx.lineWidth = 8;
      ctx.beginPath(); ctx.ellipse(440 - lean, 65, 258, 31, 0, Math.PI, TAU); ctx.stroke();
      ctx.strokeStyle = "#b98a3d"; ctx.lineWidth = 10;
      ctx.beginPath(); ctx.ellipse(440, 486, 262, 28, 0, 0, Math.PI); ctx.stroke();
      ctx.fillStyle = "rgba(247,215,145,.8)"; ctx.font = "italic 14px Georgia"; ctx.textAlign = "left";
      ctx.fillText("Only the front third is observable", 22, 29);

      if (model.drag?.kind === "panel") {
        const startCell = model.renderedCells.find((cell) => cell.index === model.drag.sourceIndex);
        if (startCell) {
          const center = bilinear(startCell.polygon, 0.5, 0.5);
          ctx.strokeStyle = "#fff0b6"; ctx.lineWidth = 4; ctx.setLineDash([8, 7]);
          ctx.beginPath(); ctx.moveTo(center[0], center[1]); ctx.lineTo(model.drag.current.x, model.drag.current.y); ctx.stroke();
          ctx.setLineDash([]);
          ctx.beginPath(); ctx.arc(model.drag.current.x, model.drag.current.y, 10, 0, TAU); ctx.stroke();
        }
      }
      updateDocket();
    }

    function updateDocket() {
      const aligned = alignedCount();
      api.app.querySelector("#ltp-view-label").textContent = `FACE ${model.view + 1} / ${sectors}`;
      api.app.querySelector("#ltp-aligned").textContent = `${aligned}/${rows * sectors - 1}`;
      const moves = api.app.querySelector("#ltp-moves");
      moves.textContent = `${model.moveCount}/${Number(state.allowed_moves)}`;
      moves.dataset.over = model.moveCount > Number(state.allowed_moves) ? "true" : "false";
      api.app.querySelector("#ltp-progress-bar").style.width = `${aligned / (rows * sectors - 1) * 100}%`;
      shell.dataset.solved = sameGrid(model.grid, goal) ? "true" : "false";
    }

    function rotate(delta, source, pointerTrace = null) {
      if (model.submitting) return;
      const action = api.beginAction?.("rotate tower");
      const before = model.view;
      model.view = mod(model.view + delta, sectors);
      model.viewFloat = model.view;
      event("rotate", {
        input_source: source,
        view_before: before,
        delta,
        view_after: model.view,
        ...(pointerTrace ? {pointer_trace: pointerTrace} : {}),
      });
      api.setReadout("", "idle");
      draw();
      action?.settle();
    }

    function slide(tileId, source, pointerTrace = null) {
      if (model.submitting) return false;
      const from = model.grid.indexOf(tileId);
      const blank = model.grid.indexOf(null);
      if (from < 0 || !neighbors(blank, rows, sectors).includes(from)) {
        api.setReadout("That panel does not border the opening.", "idle");
        return false;
      }
      const action = api.beginAction?.("slide panel");
      model.grid[blank] = tileId;
      model.grid[from] = null;
      model.moveCount += 1;
      event("slide", {
        input_source: source,
        tile_id: tileId,
        from_index: from,
        to_index: blank,
        ...(pointerTrace ? {pointer_trace: pointerTrace} : {}),
      });
      api.setReadout(sameGrid(model.grid, goal) ? "All visible seams agree. Certify the hidden back." : "", "idle");
      draw();
      action?.settle();
      return true;
    }

    function visibleCell(point) {
      const ordered = [...model.renderedCells].sort((a, b) => b.depth - a.depth);
      return ordered.find((cell) => pointInPolygon(point, cell.polygon)) || null;
    }

    function droppedIntoHiddenOpening(point, sourceIndex) {
      const blank = model.grid.indexOf(null);
      if (!neighbors(blank, rows, sectors).includes(sourceIndex)) return false;
      if (cellGeometry(Math.floor(blank / sectors), blank % sectors)) return false;
      const sourceSector = sourceIndex % sectors;
      const blankSector = blank % sectors;
      if (mod(blankSector - sourceSector, sectors) === 1) return point.x > WIDTH;
      if (mod(sourceSector - blankSector, sectors) === 1) return point.x < 0;
      return false;
    }

    function reset() {
      if (model.submitting) return;
      const action = api.beginAction?.("reset tower");
      event("reset", {input_source: "reset_button", grid_before: [...model.grid]});
      model.grid = [...state.start_grid];
      model.view = 0;
      model.viewFloat = 0;
      model.moveCount = 0;
      shell.dataset.solved = "false";
      api.setReadout("Layout restored to the issued scramble.", "idle");
      draw();
      action?.settle();
    }

    async function certify() {
      if (model.submitting) return;
      model.submitting = true;
      const action = api.beginAction?.("certify tower");
      api.setReadout("Checking every hidden seam…", "idle");
      const payload = {
        mechanic_id: MECHANIC_ID,
        task_id: state.task_id,
        challenge_id: state.challenge_id,
        interaction_mode: interaction,
        events: model.events,
        final_grid: model.grid,
        move_count: model.moveCount,
        view_sector: model.view,
        optimal_move_count: Number(state.optimal_move_count),
        allowed_moves: Number(state.allowed_moves),
      };
      try {
        const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
        const outcome = await response.json();
        if (outcome.passed === true) {
          verdict.querySelector("strong").textContent = "STRUCTURE TRUE";
          verdict.querySelector("span").textContent = `${model.moveCount} slides · hidden seam audit passed`;
          verdict.className = "ltp-verdict is-pass";
          api.setReadout("PASS", "passed");
          shell.dataset.terminal = "pass";
          draw();
          action?.settle();
          return;
        }
        verdict.querySelector("strong").textContent = "STRUCTURE REJECTED";
        verdict.querySelector("span").textContent = sameGrid(model.grid, goal)
          ? "Move allowance exceeded. A fresh commission follows."
          : "A floor, mural seam, or foundation opening is misplaced.";
        verdict.className = "ltp-verdict is-fail";
        shell.dataset.terminal = "fail";
        shell.dataset.freshFailure = "true";
        api.setReadout("FAIL", "error");
        if (outcome.state) {
          model.retryState = outcome.state;
          action?.settle();
        } else {
          model.submitting = false;
          action?.settle();
        }
      } catch (_error) {
        model.submitting = false;
        api.setReadout("Certification unavailable.", "error");
        action?.settle();
      }
    }

    if (interaction === "simplified") {
      api.app.querySelector("#ltp-turn-left").addEventListener("click", () => rotate(-1, "rotation_buttons"));
      api.app.querySelector("#ltp-turn-right").addEventListener("click", () => rotate(1, "rotation_buttons"));
      canvas.addEventListener("click", (eventObject) => {
        const cell = visibleCell(logicalPoint(canvas, eventObject));
        const tileId = cell ? model.grid[cell.index] : null;
        if (tileId) slide(tileId, "panel_click");
      });
    } else {
      canvas.addEventListener("pointerdown", (eventObject) => {
        if (model.submitting) return;
        const point = logicalPoint(canvas, eventObject);
        const cell = visibleCell(point);
        const tileId = cell ? model.grid[cell.index] : null;
        if (cell && !tileId) return;
        canvas.setPointerCapture(eventObject.pointerId);
        model.drag = tileId
          ? {kind: "panel", tileId, sourceIndex: cell.index, start: point, current: point, points: [point]}
          : {kind: "tower", start: point, current: point, baseView: model.view, points: [point]};
        draw();
      });
      canvas.addEventListener("pointermove", (eventObject) => {
        if (!model.drag) return;
        model.drag.current = logicalPoint(canvas, eventObject);
        if (model.drag.points.length < 96) model.drag.points.push(model.drag.current);
        if (model.drag.kind === "tower") {
          model.viewFloat = model.drag.baseView - (model.drag.current.x - model.drag.start.x) / 155;
        }
        draw();
      });
      const release = (eventObject) => {
        if (!model.drag) return;
        const drag = model.drag;
        const point = logicalPoint(canvas, eventObject);
        drag.points.push(point);
        const pointerTrace = normalizedTrace(drag.points);
        model.drag = null;
        model.viewFloat = model.view;
        if (drag.kind === "tower") {
          const dx = point.x - drag.start.x;
          if (Math.abs(dx) >= 64) rotate(dx > 0 ? -1 : 1, "tower_drag", pointerTrace);
          else draw();
          return;
        }
        draw();
        const destination = visibleCell(point);
        if (
          (destination && model.grid[destination.index] === null)
          || droppedIntoHiddenOpening(point, drag.sourceIndex)
        ) slide(drag.tileId, "panel_drag", pointerTrace);
        else api.setReadout("Release the panel inside the opening.", "idle");
      };
      canvas.addEventListener("pointerup", release);
      canvas.addEventListener("pointercancel", () => { model.drag = null; model.viewFloat = model.view; draw(); });
    }

    api.app.querySelector("#ltp-reset").addEventListener("click", reset);
    api.app.querySelector("#ltp-certify").addEventListener("click", certify);
    api.app.querySelector("#ltp-fresh-retry").addEventListener("click", () => {
      if (!model.retryState) return;
      const action = api.beginAction?.("open fresh commission");
      api.render(model.retryState);
      action?.settle();
    });
    draw();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {render: renderMechanic};
})();
