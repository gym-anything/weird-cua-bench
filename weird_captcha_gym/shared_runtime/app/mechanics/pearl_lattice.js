(() => {
  "use strict";
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};

  const ID = "pearl_lattice";
  const SIZE = 4;
  const PLAYER = 1;
  const OPPONENT = -1;
  let activeCleanup = null;

  const esc = (value) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;", "'":"&#39;"}[char]));
  const key = (x, y, z) => `${x},${y},${z}`;
  const columnKey = (column) => `${column[0]},${column[1]}`;
  const column = (value) => [Number(value[0]), Number(value[1])];
  const sameColumn = (first, second) => first && second && first[0] === second[0] && first[1] === second[1];

  function allLines() {
    const lines = [];
    for (let x = 0; x < SIZE; x += 1) for (let y = 0; y < SIZE; y += 1) for (let z = 0; z < SIZE; z += 1) {
      for (let dx = -1; dx <= 1; dx += 1) for (let dy = -1; dy <= 1; dy += 1) for (let dz = -1; dz <= 1; dz += 1) {
        if (dx === 0 && dy === 0 && dz === 0) continue;
        const end = [x + 3 * dx, y + 3 * dy, z + 3 * dz];
        const before = [x - dx, y - dy, z - dz];
        if (end.some((value) => value < 0 || value >= SIZE) || before.every((value) => value >= 0 && value < SIZE)) continue;
        lines.push([[x, y, z], [x + dx, y + dy, z + dz], [x + 2 * dx, y + 2 * dy, z + 2 * dz], end]);
      }
    }
    return lines;
  }
  const LINES = allLines();

  function project(x, y, z, yaw, tilt) {
    const radians = Number(yaw) * Math.PI / 180;
    const wx = (x - 1.5) * 86;
    const wz = (z - 1.5) * 86;
    const rotatedX = wx * Math.cos(radians) - wz * Math.sin(radians);
    const depth = wx * Math.sin(radians) + wz * Math.cos(radians);
    return {x: 375 + rotatedX, y: 258 - (y - 1.5) * 68 + depth * Number(tilt || 0.55) * 0.28, depth};
  }

  function render(state, helpers) {
    if (activeCleanup) activeCleanup();
    const interaction = state.control_condition?.interaction || state.interaction || "full";
    const world = state.world || {};
    const difficultyParameters = state.control_condition?.difficulty_parameters || {};
    const previewLabelDetail = world.preview_label_detail || difficultyParameters.preview_label_detail || "coordinates";
    const maxPlayerMoves = Number(world.max_player_moves || difficultyParameters.max_player_moves || 0);
    const rotationStepDegrees = Math.max(1, Number(world.rotation_step_degrees || difficultyParameters.rotation_step_degrees || 1));
    const model = {
      state,
      helpers,
      interaction,
      world,
      board: new Map((world.cells || []).filter((cell) => Number(cell.value)).map((cell) => [key(cell.x, cell.y, cell.z), Number(cell.value)])),
      preview: null,
      events: [],
      sequence: 0,
      pressureIndex: 0,
      terminal: false,
      resultSent: false,
      playerMoves: 0,
      yaw: Number(world.initial_yaw || 0),
      startedAt: performance.now(),
      raf: null,
    };

    document.body.dataset.mechanic = "pearl-lattice";
    document.body.dataset.cheatMode = helpers.isCheatMode?.() ? "true" : "false";
    helpers.app.innerHTML = `
      <section class="pl-shell" data-interaction="${esc(interaction)}" data-challenge-id="${esc(state.challenge_id)}">
        <header class="pl-header">
          <div><p class="pl-kicker">VOLUMETRIC GAMEBOARD / PEARL LATTICE</p><h1>Thread four pearls through the glass.</h1><p class="pl-prompt">${esc(state.prompt)}</p></div>
          <div class="pl-score"><span>BOARD</span><strong>4×4×4</strong><small>gravity axis <b>Y</b></small></div>
        </header>
        <main class="pl-main">
          <section class="pl-board-card">
            <div class="pl-board-top"><span class="pl-mode">${interaction === "full" ? "DIRECT BOARD CYCLE / CONFIRM BELOW" : "PROXY CYCLE / CONFIRM"}</span><span class="pl-yaw">TURN <b>0°</b></span><span class="pl-step">STEP <b>${rotationStepDegrees}°</b></span></div>
            <div class="pl-stage-wrap"><svg class="pl-board-surface" viewBox="0 0 750 530" role="application" aria-label="Rotating transparent four by four by four pearl lattice"></svg><div class="pl-stage-caption">The lattice turns continuously. Depth-crossing lines are real winning lines, not screen diagonals.</div></div>
            <button type="button" class="pl-confirm-zone" aria-label="Confirm the current preview below the lattice"><span>CONFIRM PREVIEW</span><b>CLICK BELOW THE LATTICE</b></button>
          </section>
          <aside class="pl-console">
            <section class="pl-brief"><p class="pl-label">COMMISSION</p><h2>Beat the clockwork rival.</h2><p>Cycle a glowing preview through legal ${previewLabelDetail === "layer" ? "columns" : "(x,z) columns"}. Gravity places it at the lowest open layer. Confirm only after reading the whole volume.</p><p class="pl-rival-rule">${esc(state.rules.opponent)}</p></section>
            <section class="pl-preview-card"><p class="pl-label">CURRENT PREVIEW</p><div class="pl-preview-line"><span class="pl-preview-pearl"></span><strong class="pl-preview-column">—</strong></div><div class="pl-preview-height">LANDING LAYER —</div></section>
            <section class="pl-move-limit"><p class="pl-label">PLAYER MOVE LIMIT</p><strong class="pl-moves">—</strong></section>
            <section class="pl-proxy-controls"${interaction === "full" ? " hidden aria-hidden=\"true\"" : ""}><p class="pl-label">SIMPLIFIED INPUT</p><button type="button" class="pl-next">NEXT LEGAL COLUMN ↻</button><button type="button" class="pl-confirm">CONFIRM PREVIEW</button></section>
            <section class="pl-full-note"${interaction === "simplified" ? " hidden aria-hidden=\"true\"" : ""}><p class="pl-label">FULL INPUT</p><p>Click the lattice field to cycle once. Click the separate confirmation zone below it to commit.</p></section>
            <div class="pl-actions"><button type="button" class="pl-abandon">ABANDON / TEST FAILURE</button><button type="button" class="pl-submit">${esc(state.submit_label || "CERTIFY WIN")}</button></div>
            <div class="readout pl-readout" data-status="idle">READ THE CROSS-LAYER ALIGNMENTS, THEN CYCLE THE PREVIEW.</div>
          </aside>
        </main>
      </section>`;

    const root = helpers.app.querySelector(".pl-shell");
    const svg = helpers.app.querySelector(".pl-board-surface");
    const confirmZone = helpers.app.querySelector(".pl-confirm-zone");
    const readout = helpers.app.querySelector(".pl-readout");
    const submit = helpers.app.querySelector(".pl-submit");
    const abandon = helpers.app.querySelector(".pl-abandon");
    const proxyNext = helpers.app.querySelector(".pl-next");
    const proxyConfirm = helpers.app.querySelector(".pl-confirm");

    function say(message, status = "idle") {
      if (readout) { readout.dataset.status = status; readout.textContent = message; }
    }
    function legalColumns() {
      const result = [];
      for (let z = 0; z < SIZE; z += 1) for (let x = 0; x < SIZE; x += 1) if (!model.board.has(key(x, SIZE - 1, z))) result.push([x, z]);
      return result;
    }
    function heightOf(target) {
      for (let y = 0; y < SIZE; y += 1) if (!model.board.has(key(target[0], y, target[1]))) return y;
      return SIZE;
    }
    function drop(target, mark) {
      const y = heightOf(target);
      if (y >= SIZE) return null;
      model.board.set(key(target[0], y, target[1]), mark);
      return {x: target[0], y, z: target[1]};
    }
    function hasLine(mark) {
      return LINES.some((line) => line.every((cell) => model.board.get(key(cell[0], cell[1], cell[2])) === mark));
    }
    function immediateColumns(mark) {
      return legalColumns().filter((candidate) => {
        const cell = drop(candidate, mark);
        const won = hasLine(mark);
        if (cell) model.board.delete(key(cell.x, cell.y, cell.z));
        return won;
      });
    }
    function opponentColumn() {
      const own = immediateColumns(OPPONENT);
      if (own.length) return own[0];
      const block = difficultyParameters.opponent_policy === "threat_then_block" ? immediateColumns(PLAYER) : [];
      if (block.length) return block[0];
      const pressure = (state.opponent?.pressure_columns || []).map(column);
      if (pressure.length) {
        for (let offset = 0; offset < pressure.length; offset += 1) {
          const candidate = pressure[(model.pressureIndex + offset) % pressure.length];
          if (legalColumns().some((legal) => sameColumn(legal, candidate))) {
            model.pressureIndex += offset + 1;
            return candidate;
          }
        }
      }
      model.pressureIndex += 1;
      return legalColumns()[0] || null;
    }
    function record(event) {
      model.sequence += 1;
      model.events.push({seq: model.sequence, ...event});
    }
    function normalizePreview() {
      const legal = legalColumns();
      if (!legal.length) { model.preview = null; return; }
      if (!model.preview || !legal.some((item) => sameColumn(item, model.preview))) model.preview = legal[0];
    }
    function previewDescription(target) {
      const layer = `LANDING LAYER Y${heightOf(target) + 1}`;
      if (previewLabelDetail === "layer") return layer;
      return `COLUMN X${target[0] + 1} / Z${target[1] + 1} · ${layer}`;
    }
    function cycle(source) {
      if (model.terminal || model.resultSent) return;
      const legal = legalColumns();
      normalizePreview();
      if (!legal.length || !model.preview) return;
      const before = [...model.preview];
      const after = legal[(legal.findIndex((item) => sameColumn(item, model.preview)) + 1) % legal.length];
      model.preview = after;
      record({type: "cycle_preview", input_source: source, from_column: before, to_column: [...after]});
      update();
      say(`PREVIEW CYCLED · ${previewDescription(after)} · INSPECT THE VOLUME.`);
    }
    function place(source) {
      if (model.terminal || model.resultSent) return;
      if (maxPlayerMoves > 0 && model.playerMoves >= maxPlayerMoves) {
        model.terminal = true;
        root.dataset.status = "lost";
        say(`PLAYER MOVE LIMIT REACHED · ${maxPlayerMoves} PLACEMENTS ALLOWED.`, "error");
        update();
        return;
      }
      normalizePreview();
      if (!model.preview) { say("NO LEGAL COLUMN REMAINS.", "error"); return; }
      const target = [...model.preview];
      const height = heightOf(target);
      const cell = drop(target, PLAYER);
      if (!cell) return;
      record({type: "place", input_source: source, mark: PLAYER, column: target, height});
      model.playerMoves += 1;
      if (hasLine(PLAYER)) {
        model.terminal = true;
        root.dataset.status = "won";
        say("FOUR PEARLS ALIGNED THROUGH THE VOLUME · CERTIFY THE WIN.", "pending");
        update();
        return;
      }
      if (maxPlayerMoves > 0 && model.playerMoves >= maxPlayerMoves) {
        model.terminal = true;
        root.dataset.status = "lost";
        say(`PLAYER MOVE LIMIT REACHED · ${maxPlayerMoves} PLACEMENTS ALLOWED.`, "error");
        update();
        return;
      }
      const rival = opponentColumn();
      if (!rival) { model.terminal = true; say("THE LATTICE IS FULL · CERTIFY THE FAILED BOARD.", "error"); update(); return; }
      const rivalHeight = heightOf(rival);
      const rivalCell = drop(rival, OPPONENT);
      if (!rivalCell) { model.terminal = true; say("CLOCKWORK RIVAL COULD NOT MOVE.", "error"); update(); return; }
      record({type: "opponent_place", input_source: "opponent_ai", mark: OPPONENT, column: [...rival], height: rivalHeight});
      if (hasLine(OPPONENT)) {
        model.terminal = true;
        root.dataset.status = "lost";
        say("THE CLOCKWORK RIVAL CLOSED A LINE · CERTIFY TO RECEIVE A FRESH LATTICE.", "error");
      } else {
        normalizePreview();
        say(previewLabelDetail === "layer" ? "RIVAL MOVED · RE-READ THE VOLUME." : `RIVAL MOVED TO X${rival[0] + 1} / Z${rival[1] + 1} · RE-READ THE VOLUME.`);
      }
      update();
    }
    async function submitResult(completed) {
      if (model.resultSent || !model.terminal) {
        if (!model.terminal) say("MAKE OR LOSE A LINE BEFORE CERTIFYING.", "error");
        return;
      }
      model.resultSent = true;
      record({type: "submit", input_source: "certify_button", completed: Boolean(completed)});
      const finalBoard = {};
      model.board.forEach((value, cellKey) => { finalBoard[cellKey] = value; });
      const payload = {mechanic_id: state.mechanic_id, task_id: state.task_id, challenge_id: state.challenge_id, control_condition: state.control_condition, events: model.events, completed: Boolean(completed), final_board: finalBoard};
      submit.disabled = true; abandon.disabled = true;
      try {
        const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
        const outcome = await response.json();
        if (outcome.passed === true) {
          helpers.setReadout("PASS", "passed");
          root.insertAdjacentHTML("beforeend", '<div class="pl-verdict"><span>VOLUMETRIC LINE VERIFIED</span><strong>PASS</strong><small>GRAVITY REPLAY · CROSS-LAYER WIN CHECK</small></div>');
          return;
        }
        if (outcome.state) {
          await helpers.render(outcome.state);
          helpers.setReadout("FAIL · FRESH LATTICE ISSUED", "error");
          return;
        }
        model.resultSent = false; submit.disabled = false; abandon.disabled = false; say("CERTIFICATION FAILED · RETRY.", "error");
      } catch (_error) {
        model.resultSent = false; submit.disabled = false; abandon.disabled = false; say("CERTIFICATION LINK LOST · RETRY.", "error");
      }
    }
    function update() {
      normalizePreview();
      root.dataset.previewX = model.preview ? String(model.preview[0]) : "";
      root.dataset.previewZ = model.preview ? String(model.preview[1]) : "";
      helpers.app.querySelector(".pl-preview-column").textContent = model.preview ? (previewLabelDetail === "layer" ? `LAYER Y${heightOf(model.preview) + 1}` : `X${model.preview[0] + 1}  /  Z${model.preview[1] + 1}`) : "NONE";
      helpers.app.querySelector(".pl-preview-height").textContent = model.preview ? (previewLabelDetail === "layer" ? "PREVIEW LABEL: LAYER ONLY" : `LANDING LAYER Y${heightOf(model.preview) + 1} · LOWEST FREE CELL`) : "NO LEGAL COLUMN";
      helpers.app.querySelector(".pl-moves").textContent = maxPlayerMoves > 0 ? `${model.playerMoves} / ${maxPlayerMoves}` : `${model.playerMoves}`;
      helpers.app.querySelector(".pl-yaw b").textContent = `${Math.round(model.yaw)}°`;
      if (model.preview) helpers.app.querySelector(".pl-preview-pearl").style.setProperty("--pearl", "#f5c86b");
      submit.disabled = !model.terminal || model.resultSent;
      abandon.disabled = !model.terminal || model.resultSent;
      if (proxyNext) proxyNext.disabled = model.terminal || model.resultSent;
      if (proxyConfirm) proxyConfirm.disabled = model.terminal || model.resultSent;
      draw();
    }
    function draw() {
      const nodes = [];
      const pointMap = new Map();
      for (let z = 0; z < SIZE; z += 1) for (let y = 0; y < SIZE; y += 1) for (let x = 0; x < SIZE; x += 1) pointMap.set(key(x, y, z), project(x, y, z, model.yaw, world.tilt));
      const edges = [];
      for (let z = 0; z < SIZE; z += 1) for (let y = 0; y < SIZE; y += 1) for (let x = 0; x < SIZE; x += 1) {
        [[1,0,0],[0,1,0],[0,0,1]].forEach(([dx,dy,dz]) => {
          const nx=x+dx, ny=y+dy, nz=z+dz; if (nx>=SIZE||ny>=SIZE||nz>=SIZE) return;
          const first=pointMap.get(key(x,y,z)), second=pointMap.get(key(nx,ny,nz));
          edges.push(`<line class="pl-wire ${first.depth + second.depth < 0 ? "is-back" : ""}" x1="${first.x.toFixed(1)}" y1="${first.y.toFixed(1)}" x2="${second.x.toFixed(1)}" y2="${second.y.toFixed(1)}"/>`);
        });
      }
      model.board.forEach((value, rawKey) => {
        const [x,y,z] = rawKey.split(",").map(Number); const point=pointMap.get(rawKey); nodes.push({depth:point.depth, html:`<g class="pl-pearl ${value===PLAYER?"is-player":"is-rival"}" transform="translate(${point.x.toFixed(1)} ${point.y.toFixed(1)})"><circle class="pl-pearl-halo" r="23"/><circle class="pl-pearl-core" r="14"/><text y="5">${value===PLAYER?"P":"R"}</text><title>X${x+1} Y${y+1} Z${z+1}</title></g>`});
      });
      if (model.preview) {
        const y=heightOf(model.preview); if (y<SIZE) { const point=pointMap.get(key(model.preview[0],y,model.preview[1])); nodes.push({depth:point.depth+1,html:`<g class="pl-pearl is-preview" transform="translate(${point.x.toFixed(1)} ${point.y.toFixed(1)})"><circle class="pl-pearl-halo" r="25"/><circle class="pl-pearl-core" r="15"/><text y="5">?</text></g>`}); }
      }
      nodes.sort((a,b)=>a.depth-b.depth);
      const axis = `<text class="pl-axis" x="646" y="454">X →</text><text class="pl-axis" x="98" y="438">Z ↗</text><text class="pl-axis" x="630" y="112">Y ↑</text>`;
      svg.innerHTML = `<defs><radialGradient id="pl-player"><stop offset="0" stop-color="#e5fff8"/><stop offset=".42" stop-color="#67e0c4"/><stop offset="1" stop-color="#1b776f"/></radialGradient><radialGradient id="pl-rival"><stop offset="0" stop-color="#fff2ef"/><stop offset=".42" stop-color="#fa9283"/><stop offset="1" stop-color="#8e3849"/></radialGradient><radialGradient id="pl-preview"><stop offset="0" stop-color="#fff4c0"/><stop offset=".46" stop-color="#f5c86b"/><stop offset="1" stop-color="#9c5f35"/></radialGradient></defs><g class="pl-edges">${edges.join("")}</g><g class="pl-pearls">${nodes.map((item)=>item.html).join("")}</g>${axis}`;
    }
    function animate() {
      const continuousYaw = Number(world.initial_yaw || 0) + (performance.now() - model.startedAt) * Number(world.rotation_rate || 0.0016) * 30;
      model.yaw = (Number(world.initial_yaw || 0) + Math.floor((continuousYaw - Number(world.initial_yaw || 0)) / rotationStepDegrees) * rotationStepDegrees) % 360;
      update();
      model.raf = requestAnimationFrame(animate);
    }

    model.preview = legalColumns()[0] || null;
    svg.addEventListener("click", () => { if (interaction === "full") cycle("board_surface"); });
    confirmZone.addEventListener("click", () => { if (interaction === "full") place("confirm_area"); });
    confirmZone.addEventListener("keydown", (event) => { if ((event.key === "Enter" || event.key === " ") && interaction === "full") { event.preventDefault(); place("confirm_area"); } });
    proxyNext?.addEventListener("click", () => cycle("proxy_next"));
    proxyConfirm?.addEventListener("click", () => place("confirm_button"));
    submit.addEventListener("click", () => submitResult(true));
    abandon.addEventListener("click", () => submitResult(false));
    activeCleanup = () => { if (model.raf) cancelAnimationFrame(model.raf); };
    update();
    say(interaction === "full" ? "CLICK THE LATTICE TO CYCLE, THEN CLICK BELOW TO CONFIRM." : "USE NEXT LEGAL COLUMN, THEN CONFIRM PREVIEW.");
    model.raf = requestAnimationFrame(animate);
  }

  window.WeirdCaptchaMechanics[ID] = {rootSelector: ".pl-shell", render};
})();
