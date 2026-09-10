(() => {
  "use strict";
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};

  const esc = (value) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;", "'":"&#39;"}[char]));
  const TAU = Math.PI * 2;
  const normDeg = (value) => ((Number(value) % 360) + 360) % 360;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const MAT_ID = [[1,0,0],[0,1,0],[0,0,1]];
  const AXIS_ROTATIONS = {
    x: {1:[[1,0,0],[0,0,-1],[0,1,0]], '-1':[[1,0,0],[0,0,1],[0,-1,0]]},
    y: {1:[[0,0,1],[0,1,0],[-1,0,0]], '-1':[[0,0,-1],[0,1,0],[1,0,0]]},
    z: {1:[[0,-1,0],[1,0,0],[0,0,1]], '-1':[[0,1,0],[-1,0,0],[0,0,1]]},
  };

  function matMul(a, b) {
    return a.map((row, i) => row.map((_, j) => a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j]));
  }
  function matVec(matrix, vector) {
    return matrix.map((row) => row[0] * vector[0] + row[1] * vector[1] + row[2] * vector[2]);
  }
  function transformedCells(piece, orientation = piece.orientation, origin = piece.origin) {
    return (piece.shape || []).map((cell) => {
      const rotated = matVec(orientation, cell);
      return rotated.map((value, axis) => Number(value) + Number(origin[axis]));
    });
  }
  function project(point, camera) {
    const yaw = Number(camera.yaw || 0) * Math.PI / 180;
    const pitch = Number(camera.pitch || 0.48);
    const x = Number(point[0]); const y = Number(point[1]); const z = Number(point[2]);
    const rx = x * Math.cos(yaw) - z * Math.sin(yaw);
    const rz = x * Math.sin(yaw) + z * Math.cos(yaw);
    const py = y * Math.cos(pitch) - rz * Math.sin(pitch);
    const depth = y * Math.sin(pitch) + rz * Math.cos(pitch);
    return {x: 460 + rx * 68, y: 326 - py * 68, depth};
  }
  function cellCorners(cell) {
    const [x, y, z] = cell;
    return [[x,y,z],[x+1,y,z],[x+1,y+1,z],[x,y+1,z],[x,y,z+1],[x+1,y,z+1],[x+1,y+1,z+1],[x,y+1,z+1]];
  }
  function cubeMarkup(cell, camera, fill, opacity, extraClass = "") {
    const corners = cellCorners(cell).map((point) => project(point, camera));
    const faces = [[0,1,2,3],[4,7,6,5],[0,4,5,1],[3,2,6,7],[0,3,7,4],[1,5,6,2]];
    const fills = [fill, fill, fill, fill, fill, fill];
    const faceData = faces.map((face, index) => ({face, depth: face.reduce((sum, at) => sum + corners[at].depth, 0) / face.length, index})).sort((a, b) => a.depth - b.depth);
    return faceData.map(({face, index}) => {
      const points = face.map((at) => `${corners[at].x.toFixed(1)},${corners[at].y.toFixed(1)}`).join(" ");
      return `<polygon class="pp-cube-face ${extraClass}" points="${points}" fill="${fills[index]}" fill-opacity="${opacity}"/>`;
    }).join("");
  }
  function cellKey(cell) { return cell.map((value) => Math.round(Number(value))).join(","); }
  function integerCells(piece, orientation = piece.orientation, origin = piece.origin) {
    return transformedCells(piece, orientation, origin).map((cell) => cell.map((value) => Math.round(value)));
  }

  function render(state, helpers) {
    const app = helpers.app;
    const interaction = state.control_condition?.interaction || state.interaction || "full";
    const world = state.world || {};
    const model = {
      state, world, interaction, pieces: clone(world.pieces || []),
      camera: clone(world.camera || {yaw: 0, pitch: 0.48}), selected: null,
      events: [], cameraDrag: null, pieceDrag: null, submitting: false,
    };
    const byId = new Map(model.pieces.map((piece) => [String(piece.id), piece]));
    document.body.dataset.mechanic = "polycube-parcel";
    document.body.dataset.cheatMode = helpers.isCheatMode?.() ? "true" : "false";
    app.innerHTML = `
      <section class="pp-shell" data-interaction="${esc(interaction)}" data-challenge-id="${esc(state.challenge_id)}">
        <header class="pp-header"><div><p class="pp-kicker">VOLUME PACKING / POLYCUBE PARCEL</p><h1>Fill the parcel without a hidden gap.</h1><p class="pp-prompt">${esc(state.prompt)}</p></div><div class="pp-progress"><span>OCCUPIED CELLS</span><strong class="pp-count">0</strong><small>/ 27 · <b class="pp-piece-count">0</b> / 7 pieces</small></div></header>
        <main class="pp-main">
          <section class="pp-stage-card"><div class="pp-stage-top"><span class="pp-mode">${interaction === "full" ? "DIRECT CAMERA / PIECE DRAG" : "PROXY CAMERA / CELL SELECTORS"}</span><span class="pp-camera-readout">YAW <b>0°</b> · PITCH <b>28°</b></span></div><div class="pp-stage-wrap"><svg class="pp-stage" viewBox="0 0 920 560" role="application" aria-label="Three-dimensional polycube parcel and loose pieces"></svg><div class="pp-stage-caption">Rotate the view to inspect the back. The gold wire parcel is a volume, not a flat outline.</div></div></section>
          <aside class="pp-sidebar">
            <section><p class="pp-label">SUPPLIED PIECES</p><div class="pp-piece-list"></div></section>
            <section class="pp-piece-controls"><p class="pp-label">SELECTED PIECE</p><div class="pp-selected" aria-live="polite">Choose a loose polycube.</div><div class="pp-axis-buttons"><button class="pp-rotate-x-minus" type="button">X −90°</button><button class="pp-rotate-x-plus" type="button">X +90°</button><button class="pp-rotate-y-minus" type="button">Y −90°</button><button class="pp-rotate-y-plus" type="button">Y +90°</button><button class="pp-rotate-z-minus" type="button">Z −90°</button><button class="pp-rotate-z-plus" type="button">Z +90°</button></div><p class="pp-hint">Turn the selected rigid piece about a world axis.</p></section>
            <section class="pp-camera-controls"><p class="pp-label">CAMERA</p><div class="pp-camera-proxies"${interaction === "full" ? " hidden aria-hidden=\"true\"" : ""}><button data-camera="left" type="button">← ORBIT</button><button data-camera="right" type="button">ORBIT →</button><button data-camera="up" type="button">↑ TILT</button><button data-camera="down" type="button">TILT ↓</button></div><p class="pp-hint">${interaction === "full" ? "Drag an empty part of the scene to orbit around the parcel." : "Use the proxy orbit buttons to inspect the parcel."}</p></section>
            <section class="pp-placement-controls"${interaction === "full" ? " hidden aria-hidden=\"true\"" : ""}><p class="pp-label">PLACE ON LATTICE</p><div class="pp-selectors"><label>X <select class="pp-origin-x"><option>0</option><option>1</option><option>2</option></select></label><label>Y <select class="pp-origin-y"><option>0</option><option>1</option><option>2</option></select></label><label>Z <select class="pp-origin-z"><option>0</option><option>1</option><option>2</option></select></label></div><button class="pp-place-proxy" type="button">PLACE AT CELL</button></section>
            <div class="pp-actions"><button class="pp-clear" disabled type="button">CANCEL SELECTION</button><button class="pp-abandon" type="button">ABANDON ATTEMPT</button><button class="pp-submit" type="button">${esc(state.submit_label || "CERTIFY PARCEL")}</button></div><div class="readout pp-readout" data-status="idle">INSPECT THE VOLUME, THEN PACK EVERY CELL.</div>
          </aside>
        </main>
      </section>`;
    const shell = app.querySelector(".pp-shell");
    const svg = app.querySelector(".pp-stage");
    const readout = app.querySelector(".pp-readout");
    const selectedReadout = app.querySelector(".pp-selected");
    const clearButton = app.querySelector(".pp-clear");
    const submitButton = app.querySelector(".pp-submit");
    const abandonButton = app.querySelector(".pp-abandon");

    function say(message, status = "idle") { readout.dataset.status = status; readout.textContent = message; }
    function addEvent(event) { model.events.push({...event, seq: model.events.length + 1}); }
    function placedCells(exclude = null) {
      const occupied = new Set();
      model.pieces.forEach((piece) => {
        if (!piece.placed || piece.id === exclude) return;
        integerCells(piece).forEach((cell) => occupied.add(cellKey(cell)));
      });
      return occupied;
    }
    function validOrigin(piece, origin) {
      const cells = integerCells(piece, piece.orientation, origin);
      if (cells.some((cell) => cell.some((value) => value < 0 || value >= 3))) return false;
      if (new Set(cells.map(cellKey)).size !== cells.length) return false;
      const occupied = placedCells(piece.id);
      return !cells.some((cell) => occupied.has(cellKey(cell)));
    }
    function selectedPiece() { return model.selected ? byId.get(model.selected) : null; }
    function updateLedger() {
      const occupied = placedCells();
      app.querySelector(".pp-count").textContent = String(occupied.size);
      app.querySelector(".pp-piece-count").textContent = String(model.pieces.filter((piece) => piece.placed).length);
      selectedReadout.textContent = model.selected ? `${selectedPiece()?.label || model.selected} SELECTED · ${selectedPiece()?.placed ? "DRAG TO REPOSITION" : "ROTATE THEN PLACE"}` : "Choose a loose polycube.";
      clearButton.disabled = !model.selected;
      app.querySelector(".pp-camera-readout").innerHTML = `YAW <b>${Math.round(normDeg(model.camera.yaw))}°</b> · PITCH <b>${Math.round(model.camera.pitch * 180 / Math.PI)}°</b>`;
      shell.dataset.occupied = String(occupied.size);
    }
    function pieceCentroid(piece, orientation = piece.orientation, origin = piece.origin) {
      const cells = transformedCells(piece, orientation, origin);
      return cells.reduce((sum, cell) => sum.map((value, axis) => value + cell[axis]), [0,0,0]).map((value) => value / cells.length);
    }
    function svgPoint(event) {
      const box = svg.getBoundingClientRect();
      return {x: (event.clientX - box.left) * 920 / box.width, y: (event.clientY - box.top) * 560 / box.height};
    }
    function projectCandidate(piece, origin) { return project(pieceCentroid(piece, piece.orientation, origin), model.camera); }
    function bestDrop(piece, point) {
      let best = null;
      for (let x = 0; x < 3; x += 1) for (let y = 0; y < 3; y += 1) for (let z = 0; z < 3; z += 1) {
        const origin = [x,y,z];
        if (!validOrigin(piece, origin)) continue;
        const target = projectCandidate(piece, origin);
        const distance = Math.hypot(target.x - point.x, target.y - point.y);
        if (!best || distance < best.distance) best = {origin, distance};
      }
      return best;
    }
    function renderPieceList() {
      app.querySelector(".pp-piece-list").innerHTML = model.pieces.map((piece) => `<button type="button" class="pp-piece-row ${piece.placed ? "is-placed" : ""} ${model.selected === piece.id ? "is-selected" : ""}" data-piece-row="${esc(piece.id)}"><i style="--piece-color:${esc(piece.color)}"></i><b>${esc(piece.id)}</b><span>${esc(piece.label)}</span><em>${piece.placed ? "IN PARCEL" : "LOOSE"}</em></button>`).join("");
      app.querySelectorAll(".pp-piece-row").forEach((node) => node.addEventListener("click", () => selectPiece(String(node.dataset.pieceRow))));
    }
    function renderScene() {
      const parcel = [];
      for (let x = 0; x < 3; x += 1) for (let y = 0; y < 3; y += 1) for (let z = 0; z < 3; z += 1) parcel.push(cubeMarkup([x,y,z], model.camera, "#e9bf73", Number(world.parcel_opacity || 0.15), "pp-parcel-face"));
      // Keep the actively selected piece on top of the translucent parcel and
      // other geometry.  This makes the direct-manipulation affordance remain
      // visible after selecting from the piece ledger.
      const renderPieces = model.pieces.slice().sort((a, b) => (a.id === model.selected ? 1 : 0) - (b.id === model.selected ? 1 : 0));
      const pieces = renderPieces.map((piece) => {
        const cells = transformedCells(piece);
        const content = cells.map((cell) => cubeMarkup(cell, model.camera, piece.color, Number(world.piece_opacity || 0.93), "pp-piece-face")).join("");
        const center = project(pieceCentroid(piece), model.camera);
        const selected = model.selected === piece.id;
        return `<g class="pp-piece ${selected ? "is-selected" : ""} ${piece.placed ? "is-placed" : "is-loose"}" data-piece-id="${esc(piece.id)}" tabindex="0" role="button" aria-label="Piece ${esc(piece.id)}"><g>${content}</g><circle class="pp-piece-ring" cx="${center.x.toFixed(1)}" cy="${center.y.toFixed(1)}" r="${selected ? 28 : 22}"/><text class="pp-piece-label" x="${center.x.toFixed(1)}" y="${(center.y - 25).toFixed(1)}">${esc(piece.id)}</text></g>`;
      }).join("");
      svg.innerHTML = `<defs><filter id="pp-glow"><feGaussianBlur stdDeviation="4"/></filter></defs><rect class="pp-scene-back" x="0" y="0" width="920" height="560"/><g class="pp-parcel">${parcel.join("")}</g><g class="pp-pieces">${pieces}</g><path class="pp-horizon" d="M20 488 Q460 456 900 488"/>`;
      svg.querySelectorAll(".pp-piece").forEach((node) => {
        const id = String(node.dataset.pieceId);
        node.addEventListener("pointerdown", (event) => beginPiece(event, id));
        node.addEventListener("click", (event) => { if (model.interaction === "simplified" && !event.defaultPrevented) selectPiece(id); });
        node.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectPiece(id); } });
      });
      updateLedger(); renderPieceList();
    }
    function selectPiece(id) {
      const piece = byId.get(id);
      if (!piece || piece.locked || model.submitting) return;
      if (model.selected && model.selected !== id) { say("CANCEL THE CURRENT PIECE BEFORE SELECTING ANOTHER.", "error"); return; }
      if (model.selected === id) return;
      model.selected = id; addEvent({type: "select_piece", input_source: "piece_click", piece_id: id}); renderScene(); say(`${piece.label} SELECTED · ROTATE IT OR PLACE IT ON THE GOLD LATTICE.`);
    }
    function clearSelection() { if (!model.selected) return; addEvent({type:"clear_selection", input_source:"piece_click", piece_id:model.selected}); model.selected = null; renderScene(); say("SELECTION CLEARED."); }
    function rotateSelected(axis, direction) {
      const piece = selectedPiece(); const rotation = AXIS_ROTATIONS[axis]?.[String(direction)];
      if (!piece || !rotation || model.submitting) return;
      const before = clone(piece.orientation); piece.orientation = matMul(rotation, piece.orientation);
      addEvent({type:"rotate_piece", input_source:"axis_rotation_button", piece_id:piece.id, axis, direction, before_orientation:before, after_orientation:clone(piece.orientation)});
      renderScene(); say(`${piece.id} TURNED ON ${axis.toUpperCase()} · CHECK THE NEW SILHOUETTE.`);
    }
    function placePiece(piece, origin, source, extra = {}) {
      if (!piece || !validOrigin(piece, origin)) { say("THAT ROTATION LEAVES A COLLISION OR AN EMPTY CELL.", "error"); return false; }
      const beforeOrigin = clone(piece.origin); piece.origin = origin.map((value) => Number(value)); piece.placed = true;
      addEvent({type:"place_piece", input_source:source, piece_id:piece.id, before_origin:beforeOrigin, after_origin:clone(piece.origin), orientation:clone(piece.orientation), ...extra});
      say(`${piece.id} SET INTO THE PARCEL · ROTATE THE VIEW TO CHECK THE CAVITY.`); renderScene(); return true;
    }
    function placeProxy() {
      const piece = selectedPiece(); if (!piece) return;
      const origin = ["x","y","z"].map((axis) => Number(app.querySelector(`.pp-origin-${axis}`).value));
      placePiece(piece, origin, "placement_proxy", {proxy:{surface:"axis_cell_selectors", origin}});
    }
    function beginPiece(event, id) {
      const piece = byId.get(id); if (!piece || piece.locked || model.submitting) return;
      event.preventDefault(); event.stopPropagation();
      if (!model.selected) { model.selected = id; addEvent({type:"select_piece", input_source:"piece_click", piece_id:id}); renderScene(); }
      if (model.interaction !== "full" || model.selected !== id) return;
      const point = svgPoint(event);
      model.pieceDrag = {pieceId:id, startX:point.x, startY:point.y, path:[[point.x,point.y]], beforeOrigin:clone(piece.origin), moved:false};
      svg.setPointerCapture?.(event.pointerId);
      say(`${piece.id} IN HAND · DRAG IT TO A GOLD CELL.`);
    }
    function movePiece(event) {
      if (!model.pieceDrag) return;
      const point = svgPoint(event); const drag = model.pieceDrag; drag.path.push([point.x,point.y]); drag.moved = drag.moved || Math.hypot(point.x-drag.startX, point.y-drag.startY) > 5; say("DRAGGING RIGID PIECE · RELEASE ON THE GOLD LATTICE.");
    }
    function finishPiece(event) {
      if (!model.pieceDrag) return;
      const drag = model.pieceDrag; model.pieceDrag = null; svg.releasePointerCapture?.(event.pointerId);
      const point = svgPoint(event); const piece = byId.get(drag.pieceId);
      if (!drag.moved) { renderScene(); return; }
      const candidate = bestDrop(piece, point);
      if (!candidate || candidate.distance > 105) { say("THE PIECE MISSED THE PARCEL; TRY A CLEARER DROP.", "error"); renderScene(); return; }
      placePiece(piece, candidate.origin, "piece_drag", {path:drag.path, drop_path:[[point.x,point.y]]});
    }
    function beginCamera(event) {
      if (model.interaction !== "full" || event.target.closest?.(".pp-piece")) return;
      const point = svgPoint(event); model.cameraDrag = {before:clone(model.camera), path:[[point.x,point.y]], startX:point.x, startY:point.y, moved:false}; svg.setPointerCapture?.(event.pointerId);
    }
    function moveCamera(event) {
      if (!model.cameraDrag) return;
      const point = svgPoint(event); const drag=model.cameraDrag; drag.path.push([point.x,point.y]); drag.moved = drag.moved || Math.hypot(point.x-drag.startX,point.y-drag.startY)>4;
      model.camera.yaw = normDeg(drag.before.yaw + (point.x-drag.startX)*0.55); model.camera.pitch = clamp(drag.before.pitch + (point.y-drag.startY)*0.004, 0.18, 0.82); renderScene();
    }
    function finishCamera(event) {
      if (!model.cameraDrag) return;
      const drag=model.cameraDrag; model.cameraDrag=null; svg.releasePointerCapture?.(event.pointerId);
      if (!drag.moved) { model.camera=drag.before; renderScene(); return; }
      addEvent({type:"camera_orbit", input_source:"direct_camera_drag", before:drag.before, after:clone(model.camera), path:drag.path}); say("CAMERA ORBITED · INSPECT THE REAR CELLS.");
    }
    function proxyCamera(direction) {
      const before=clone(model.camera); if(direction==="left") model.camera.yaw=normDeg(model.camera.yaw-24); if(direction==="right") model.camera.yaw=normDeg(model.camera.yaw+24); if(direction==="up") model.camera.pitch=clamp(model.camera.pitch-0.10,0.18,0.82); if(direction==="down") model.camera.pitch=clamp(model.camera.pitch+0.10,0.18,0.82); addEvent({type:"camera_orbit",input_source:"camera_proxy_button",before,after:clone(model.camera),direction}); renderScene(); say("CAMERA ORBITED · INSPECT THE REAR CELLS.");
    }
    async function postResult(completed) {
      if (model.submitting) return; model.submitting=true; submitButton.disabled=true; abandonButton.disabled=true; clearButton.disabled=true; addEvent({type:"submit",input_source:"certify_button",completed});
      const payload={mechanic_id:state.mechanic_id,task_id:state.task_id,challenge_id:state.challenge_id,control_condition:state.control_condition,events:model.events,completed};
      try { const response=await fetch("/result",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(payload)}); const outcome=await response.json(); if(outcome.passed===true){helpers.setReadout("PASS","passed");return;} if(outcome.state){render(outcome.state,helpers);helpers.setReadout("FAIL · NEW PARCEL READY","error");return;} model.submitting=false;submitButton.disabled=false;abandonButton.disabled=false;say("FAIL · THE OCCUPANCY REPLAY DID NOT PASS.","error"); } catch(_error){model.submitting=false;submitButton.disabled=false;abandonButton.disabled=false;say("LINK UNAVAILABLE · RETRY.","error");}
    }
    [["x",-1,".pp-rotate-x-minus"],["x",1,".pp-rotate-x-plus"],["y",-1,".pp-rotate-y-minus"],["y",1,".pp-rotate-y-plus"],["z",-1,".pp-rotate-z-minus"],["z",1,".pp-rotate-z-plus"]].forEach(([axis,direction,selector]) => app.querySelector(selector).addEventListener("click",()=>rotateSelected(axis,direction)));
    app.querySelectorAll("[data-camera]").forEach((button)=>button.addEventListener("click",()=>proxyCamera(String(button.dataset.camera))));
    app.querySelector(".pp-place-proxy").addEventListener("click",placeProxy); clearButton.addEventListener("click",clearSelection); submitButton.addEventListener("click",()=>postResult(true)); abandonButton.addEventListener("click",()=>postResult(false));
    svg.addEventListener("pointerdown",beginCamera); svg.addEventListener("pointermove",(event)=>{movePiece(event);moveCamera(event);}); svg.addEventListener("pointerup",(event)=>{finishPiece(event);finishCamera(event);}); svg.addEventListener("pointercancel",(event)=>{finishPiece(event);finishCamera(event);});
    renderScene(); say(interaction === "full" ? "DRAG AN EMPTY SCENE TO ORBIT; SELECT AND DRAG A PIECE." : "USE THE CAMERA BUTTONS, THEN SELECT A PIECE AND CELL.");
  }

  window.WeirdCaptchaMechanics.polycube_parcel = {rootSelector: ".pp-shell", render};
})();
