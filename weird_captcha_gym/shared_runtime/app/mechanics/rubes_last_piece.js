(() => {
  "use strict";

  let model = null;
  const clean = value => String(value == null ? "" : value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const round = value => Math.round(Number(value) * 1000) / 1000;
  const record = (kind, details = {}) => { const event = {sequence: model.events.length + 1, kind, ...details}; model.events.push(event); return event; };
  const toolMap = () => Object.fromEntries(model.state.tools.map(tool => [tool.id, tool]));
  const bayMap = () => Object.fromEntries(model.state.bays.map(bay => [bay.id, bay]));
  const poseArray = item => [round(item.x), round(item.y), round(item.angle)];

  function setMessage(message, status = "idle") {
    model.helpers.setReadout(message, status);
    const note = document.querySelector(".rube-status-copy");
    if (note) note.textContent = message;
  }

  function canvasPoint(event, clamp = true) {
    const box = model.canvas.getBoundingClientRect();
    const point = [
      (event.clientX - box.left) / box.width * model.state.stage.width,
      (event.clientY - box.top) / box.height * model.state.stage.height,
    ];
    return clamp ? [
      Math.max(0, Math.min(model.state.stage.width, point[0])),
      Math.max(0, Math.min(model.state.stage.height, point[1])),
    ] : point;
  }

  function pointInZone(point, zone) {
    return point[0] >= Number(zone[0]) && point[0] <= Number(zone[0]) + Number(zone[2])
      && point[1] >= Number(zone[1]) && point[1] <= Number(zone[1]) + Number(zone[3]);
  }

  function bayAtDrop(point) {
    return model.state.bays.find(bay => pointInZone(point, bay.work_zone)) || null;
  }

  function appendDragSample(drag, point) {
    if (point[0] < 0 || point[0] > model.state.stage.width || point[1] < 0 || point[1] > model.state.stage.height) return;
    const sample = [round(point[0]), round(point[1])];
    const previous = drag.samples_stage[drag.samples_stage.length - 1];
    if (!previous || Math.hypot(sample[0] - previous[0], sample[1] - previous[1]) >= 1) drag.samples_stage.push(sample);
    if (drag.samples_stage.length > 32) drag.samples_stage.splice(1, drag.samples_stage.length - 32);
  }

  function dragGesture(drag, release) {
    appendDragSample(drag, release);
    const roundedRelease = [round(release[0]), round(release[1])];
    if (!drag.samples_stage.length || Math.hypot(drag.samples_stage[drag.samples_stage.length - 1][0] - roundedRelease[0], drag.samples_stage[drag.samples_stage.length - 1][1] - roundedRelease[1]) > 0.05) {
      drag.samples_stage.push(roundedRelease);
    }
    return {
      origin: drag.origin,
      start_tool_id: drag.toolId,
      start_stage: drag.start_stage ? drag.start_stage.map(round) : null,
      samples_stage: drag.samples_stage.map(point => point.map(round)),
      release_stage: roundedRelease,
    };
  }

  function rejectDrop(drag, release) {
    const gesture = dragGesture(drag, release);
    record("drop_rejected", {tool_id: drag.toolId, gesture, input_source: "direct_drag"});
    setMessage("DROP THE DEFLECTOR INSIDE A DASHED FLIGHT STATION", "pending");
    updateRack(); draw(false);
  }

  function updateRack() {
    document.querySelectorAll(".rube-tool").forEach(button => {
      const placed = model.placements[button.dataset.toolId];
      button.dataset.selected = button.dataset.toolId === model.selected ? "true" : "false";
      button.dataset.placed = placed && placed.bay_id !== "unassigned" ? "true" : "false";
    });
    document.querySelectorAll(".rube-bay-card").forEach(card => {
      const item = Object.values(model.placements).find(placement => placement.bay_id === card.dataset.bayId);
      card.dataset.filled = item ? "true" : "false";
      const value = card.querySelector("strong");
      if (value) value.textContent = item ? toolMap()[item.tool_id].glyph : "—";
    });
    const count = Object.values(model.placements).filter(item => item.bay_id !== "unassigned").length;
    const placed = document.querySelector(".rube-placed-count");
    if (placed) placed.textContent = `${count}/${model.state.bays.length}`;
    document.querySelectorAll(".rube-edit-only button").forEach(button => { button.disabled = model.mode !== "edit"; });
    const run = document.querySelector(".rube-run");
    if (run) run.disabled = model.mode !== "edit" || count < model.state.bays.length;
    const rewind = document.querySelector(".rube-rewind");
    if (rewind) rewind.disabled = model.mode !== "failed";
    const certify = document.querySelector(".rube-submit");
    if (certify) certify.disabled = model.submitting || model.terminal;
  }

  function assignPlacement(toolId, bayId, inputSource, gesture = null) {
    if (model.mode !== "edit") return;
    const bay = bayMap()[bayId];
    const tool = toolMap()[toolId];
    if (!bay || !tool) return;
    for (const [otherId, other] of Object.entries(model.placements)) {
      if (otherId !== toolId && other.bay_id === bayId) other.bay_id = "unassigned";
    }
    const previous = model.placements[toolId];
    const angle = previous ? previous.angle : 45;
    model.placements[toolId] = {tool_id: toolId, bay_id: bayId, x: round(bay.anchor[0]), y: round(bay.anchor[1]), angle: round(angle)};
    model.selected = toolId;
    const details = {tool_id: toolId, bay_id: bayId, pose: poseArray(model.placements[toolId]), input_source: inputSource};
    if (gesture) details.gesture = gesture;
    record("place", details);
    setMessage(`${tool.glyph} DEFLECTOR LOCKED IN ${bay.label} · RUN TO TEST ITS FLIGHT`, "pending");
    updateRack(); draw(false);
  }

  function rotateSelected(delta, inputSource) {
    if (model.mode !== "edit" || !model.selected || !model.placements[model.selected] || model.placements[model.selected].bay_id === "unassigned") {
      setMessage("SELECT A PLACED DEFLECTOR BEFORE ROTATING", "pending");
      return;
    }
    const item = model.placements[model.selected];
    item.angle = round(item.angle + delta);
    record("rotate", {tool_id: model.selected, delta_degrees: delta, pose: poseArray(item), input_source: inputSource});
    setMessage(`${toolMap()[model.selected].glyph} FACE ROTATED TO ${((item.angle % 180) + 180) % 180}°`);
    draw(false); updateRack();
  }

  function distanceToSegment(point, first, second) {
    const dx = second[0] - first[0], dy = second[1] - first[1];
    const lengthSq = dx * dx + dy * dy;
    if (lengthSq <= 1e-12) return Math.hypot(point[0] - first[0], point[1] - first[1]);
    const amount = Math.max(0, Math.min(1, ((point[0] - first[0]) * dx + (point[1] - first[1]) * dy) / lengthSq));
    return Math.hypot(point[0] - (first[0] + dx * amount), point[1] - (first[1] + dy * amount));
  }

  function newBall(bay) {
    return {
      x: Number(bay.launcher[0]), y: Number(bay.launcher[1]),
      vx: Number(model.state.contract.initial_velocity[0]), vy: Number(model.state.contract.initial_velocity[1]),
      tick: 0, bounced: false, crossing: null, receiverEncountered: false, impactError: null, hidden: false,
      trail: [[Number(bay.launcher[0]), Number(bay.launcher[1])]],
    };
  }

  function resetFlight(preserve) {
    if (model.timer) clearInterval(model.timer);
    model.timer = null;
    if (preserve) {
      const finished = model.balls.filter(ball => ball.trail.length > 1).map((ball, index) => ({lane: index, points: ball.trail.slice()}));
      if (model.state.trail_mode === "persistent") model.historyTrails.push(...finished);
      else if (model.state.trail_mode === "last") model.historyTrails = finished.length ? [finished[finished.length - 1]] : [];
      else model.historyTrails = [];
      if (model.historyTrails.length > 12) model.historyTrails = model.historyTrails.slice(-12);
    }
    model.balls = model.state.bays.map(newBall);
    model.activeLane = 0;
    model.tick = 0;
    model.releaseIndex = 0;
    model.lastSequence = [];
    document.querySelectorAll(".rube-lane").forEach(lane => { lane.dataset.live = "false"; lane.dataset.fired = "false"; });
  }

  function stepBall(ball, bay, tool, placement) {
    const first = [Number(ball.x), Number(ball.y)];
    let vx = Number(ball.vx), vy = Number(ball.vy);
    if (ball.bounced) {
      vy += Number(bay.wind_y);
      vx *= Number(model.state.contract.flight_drag);
      vy *= Number(model.state.contract.flight_drag);
    }
    let next = [first[0] + vx, first[1] + vy];
    if (!ball.bounced) {
      const physicalAngle = ((Number(placement.angle) % 180) + 180) % 180;
      const radians = (physicalAngle + Number(tool.facet_deg)) * Math.PI / 180;
      const tangent = [Math.cos(radians), Math.sin(radians)];
      const normal = [-tangent[1], tangent[0]];
      const center = [Number(placement.x), Number(placement.y)];
      const threshold = -(Number(model.state.contract.ball_radius) + Number(tool.thickness) / 2);
      const before = (first[0] - center[0]) * normal[0] + (first[1] - center[1]) * normal[1];
      const after = (next[0] - center[0]) * normal[0] + (next[1] - center[1]) * normal[1];
      if (before < threshold && threshold <= after && after - before > 1e-9) {
        const amount = (threshold - before) / (after - before);
        const contact = [first[0] + (next[0] - first[0]) * amount, first[1] + (next[1] - first[1]) * amount];
        const along = (contact[0] - center[0]) * tangent[0] + (contact[1] - center[1]) * tangent[1];
        if (Math.abs(along) <= Number(tool.length) / 2 + Number(model.state.contract.ball_radius)) {
          const projection = vx * normal[0] + vy * normal[1];
          const impulse = (1 + Number(tool.restitution)) * projection;
          vx -= impulse * normal[0]; vy -= impulse * normal[1];
          const remaining = 1 - amount;
          next = [contact[0] + vx * remaining, contact[1] + vy * remaining];
          ball.bounced = true; ball.bounceTick = Number(ball.tick) + 1;
        }
      }
    }
    ball.tick += 1; ball.x = next[0]; ball.y = next[1]; ball.vx = vx; ball.vy = vy;
    ball.trail.push([next[0], next[1]]);
    if (ball.trail.length > 150) ball.trail.shift();
    const receiver = [Number(bay.receiver[0]), Number(bay.receiver[1])];
    const geometryHit = ball.bounced && distanceToSegment(receiver, first, next) <= Number(bay.receiver_radius) + Number(model.state.contract.ball_radius);
    let receiverSuccess = false;
    if (geometryHit && !ball.receiverEncountered) {
      ball.receiverEncountered = true;
      const contactSpeed = Math.hypot(vx, vy);
      ball.impactError = contactSpeed - Number(bay.impact_speed);
      receiverSuccess = Math.abs(ball.impactError) <= Number(bay.impact_tolerance);
    }
    if (!ball.crossing && first[0] < receiver[0] && receiver[0] <= next[0]) {
      const amount = (receiver[0] - first[0]) / Math.max(1e-9, next[0] - first[0]);
      ball.crossing = [receiver[0], first[1] + (next[1] - first[1]) * amount];
    }
    return receiverSuccess;
  }

  function missOffset(ball, bay) {
    return ball.crossing ? round(Number(ball.crossing[1]) - Number(bay.receiver[1])) : null;
  }

  function finishRollout(passed) {
    if (model.mode !== "running") return;
    if (model.timer) clearInterval(model.timer);
    model.timer = null;
    if (passed) {
      model.bellRung = true;
      model.lastSequence.push("bell:ring");
      record("bell", {tick: model.tick});
      const bell = document.querySelector(".rube-bell");
      bell?.setAttribute("data-ringing", "true");
      if (bell?.querySelector("em")) bell.querySelector("em").textContent = "RINGING";
      document.querySelector(".rube-machine")?.setAttribute("data-outcome", "pass");
      setMessage("THE BELL RANG · ALL PHYSICAL FLIGHTS REACHED THEIR RECEIVERS", "passed");
      model.mode = "solved";
      record("rollout_end", {bell_rung: true, tick: model.tick, stalled_bay: null, miss_offset: 0});
    } else {
      const bay = model.state.bays[model.activeLane];
      const ball = model.balls[model.activeLane];
      const miss = missOffset(ball, bay);
      const impact = ball.impactError == null ? null : round(ball.impactError);
      model.mode = "failed";
      record("rollout_end", {bell_rung: false, tick: model.tick, stalled_bay: bay.id, miss_offset: miss, impact_error: impact});
      const root = document.querySelector(".rube-machine");
      root?.setAttribute("data-outcome", "fail");
      const direction = miss == null ? "NO DEFLECTOR CONTACT" : `${Math.abs(Math.round(miss))} PX ${miss < 0 ? "ABOVE" : "BELOW"} RECEIVER`;
      const exactCause = impact == null ? direction : `IMPACT ${Math.abs(impact).toFixed(2)} ${impact < 0 ? "TOO SOFT" : "TOO LIVELY"}`;
      const feedback = model.state.feedback_mode;
      const message = feedback === "generic" ? "CHAIN SILENT · FLIGHT ENERGY DIED BEFORE THE BELL"
        : feedback === "first_stall" ? `FIRST UNFIRED SECTION: ${bay.label}`
          : feedback === "exact" ? `${bay.label} MISSED · ${exactCause}`
            : `STALL AT ${bay.label}`;
      if (model.state.trail_mode === "last") {
        model.balls.forEach((item, index) => {
          if (index !== model.activeLane) { item.trail = []; item.hidden = true; }
        });
      } else if (model.state.trail_mode === "live") {
        model.balls.forEach(item => { item.trail = []; item.hidden = true; });
        model.historyTrails = [];
        document.querySelectorAll(".rube-lane").forEach(lane => { lane.dataset.live = "false"; lane.dataset.fired = "false"; });
      }
      root?.setAttribute("data-trace-visible", model.state.trail_mode === "live" ? "false" : "true");
      setMessage(message, "error");
    }
    updateRack(); draw(false);
  }

  function advanceFlight() {
    if (model.mode !== "running") return;
    const bay = model.state.bays[model.activeLane];
    const placement = Object.values(model.placements).find(item => item.bay_id === bay.id);
    const tool = placement ? toolMap()[placement.tool_id] : null;
    model.tick += 1;
    if (!placement || !tool) { finishRollout(false); return; }
    const ball = model.balls[model.activeLane];
    const hit = stepBall(ball, bay, tool, placement);
    if (hit) {
      model.releaseIndex += 1;
      model.lastSequence.push(`release:${bay.id}`);
      const contact = [round(ball.x), round(ball.y)];
      record("release", {bay_id: bay.id, tool_id: placement.tool_id, tick: model.tick, contact});
      const lane = document.querySelector(`.rube-lane[data-lane-index="${model.activeLane}"]`);
      lane?.setAttribute("data-fired", "true"); lane?.setAttribute("data-live", "false");
      setMessage(`${bay.label} RECEIVER STRUCK · ${model.releaseIndex}/${model.state.bays.length} FLIGHTS`, "pending");
      if (model.releaseIndex === model.state.bays.length) finishRollout(true);
      else {
        model.activeLane += 1;
        document.querySelector(`.rube-lane[data-lane-index="${model.activeLane}"]`)?.setAttribute("data-live", "true");
      }
    } else if (ball.tick >= Number(model.state.contract.lane_timeout_ticks)) finishRollout(false);
    draw(false);
  }

  function beginRollout() {
    if (model.mode !== "edit") return;
    const filled = Object.values(model.placements).filter(item => item.bay_id !== "unassigned").length;
    if (filled < model.state.bays.length) { setMessage("EVERY FLIGHT STATION NEEDS A DEFLECTOR BEFORE RUNNING", "pending"); return; }
    model.attempts += 1;
    model.mode = "running";
    model.bellRung = false;
    model.tick = 0; model.releaseIndex = 0; model.activeLane = 0; model.lastSequence = [];
    model.balls = model.state.bays.map(newBall);
    record("run_start", {attempt: model.attempts});
    document.querySelector(".rube-machine")?.setAttribute("data-outcome", "running");
    document.querySelector(".rube-machine")?.setAttribute("data-trace-visible", "true");
    document.querySelectorAll(".rube-lane").forEach((lane, index) => { lane.dataset.live = index === 0 ? "true" : "false"; lane.dataset.fired = "false"; });
    setMessage("ROLLOUT LIVE · WATCH IMPACT, CROSSWIND, AND RECEIVER CONTACT", "pending");
    updateRack();
    model.timer = setInterval(advanceFlight, 20);
  }

  function rewind() {
    if (model.mode !== "failed") return;
    const completedTick = model.tick;
    const completedSequence = model.lastSequence.slice();
    record("rewind");
    model.rewinds += 1;
    model.mode = "edit";
    model.bellRung = false;
    document.querySelector(".rube-machine")?.setAttribute("data-outcome", "edit");
    document.querySelector(".rube-bell")?.setAttribute("data-ringing", "false");
    resetFlight(true);
    model.tick = completedTick;
    model.lastSequence = completedSequence;
    setMessage(model.state.trail_mode === "live" ? "MECHANISM REWOUND · REBUILD FROM THE FLIGHT YOU OBSERVED" : "MECHANISM REWOUND · THE LAST FLIGHT TRACE REMAINS FOR REPAIR");
    updateRack(); draw(false);
  }

  function payloadPlacements() {
    return Object.fromEntries(Object.entries(model.placements).sort(([a], [b]) => a.localeCompare(b)).map(([toolId, item]) => [toolId, {bay_id: item.bay_id, pose: poseArray(item)}]));
  }

  async function submit() {
    if (model.submitting || model.terminal) return;
    model.submitting = true;
    updateRack(); setMessage("CERTIFYING THE INDEPENDENT FLIGHT REPLAY…", "pending");
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      events: model.events,
      placements: payloadPlacements(),
      release_sequence: model.lastSequence,
      bell_rung: model.bellRung,
      rollout_ticks: model.tick,
      attempts: model.attempts,
      rewinds: model.rewinds,
      physics_engine: model.state.contract.physics_engine,
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true;
        document.querySelector(".rube-machine")?.insertAdjacentHTML("beforeend", '<div class="rube-verdict"><span>FLIGHT CHAIN REPLAYED</span><strong>PASS</strong><small>ALL RECEIVER CONTACTS VERIFIED</small></div>');
        model.helpers.setReadout("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        const root = document.querySelector(".rube-machine");
        root?.setAttribute("data-fresh-failure", "true");
        root?.insertAdjacentHTML("afterbegin", '<div class="rube-fresh"><b>FAIL</b><span>UNVERIFIED FLIGHT · FRESH BENCH ISSUED</span></div>');
        setTimeout(() => { document.querySelector(".rube-fresh")?.remove(); root?.removeAttribute("data-fresh-failure"); }, 1100);
        const readout = document.querySelector(".readout");
        if (readout) { readout.textContent = "FAIL · FRESH CONTRAPTION ISSUED"; readout.dataset.status = "error"; }
      } else {
        model.submitting = false; setMessage("FAIL · NO AUTHORITATIVE FLIGHT GRADE", "error"); updateRack();
      }
    } catch (_error) {
      model.submitting = false; setMessage("FAIL · CHAIN VERIFIER OFFLINE", "error"); updateRack();
    }
  }

  function drawTrail(ctx, points, color, width, dash = []) {
    if (!points || points.length < 2) return;
    ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash); ctx.beginPath();
    points.forEach((point, index) => index ? ctx.lineTo(point[0], point[1]) : ctx.moveTo(point[0], point[1]));
    ctx.stroke(); ctx.restore();
  }

  function drawDeflector(ctx, placement, selected) {
    const tool = toolMap()[placement.tool_id];
    const physicalAngle = ((Number(placement.angle) % 180) + 180) % 180;
    const angle = (physicalAngle + Number(tool.facet_deg)) * Math.PI / 180;
    ctx.save(); ctx.translate(placement.x, placement.y); ctx.rotate(angle);
    ctx.fillStyle = tool.color; ctx.shadowColor = tool.color; ctx.shadowBlur = selected ? 18 : 7;
    ctx.fillRect(-tool.length / 2, -tool.thickness / 2, tool.length, tool.thickness); ctx.shadowBlur = 0;
    ctx.strokeStyle = selected ? "#fff8db" : "#07100e"; ctx.lineWidth = selected ? 3 : 2;
    ctx.strokeRect(-tool.length / 2, -tool.thickness / 2, tool.length, tool.thickness);
    ctx.fillStyle = "#07100e"; ctx.fillRect(-3, -tool.thickness / 2 - 4, 6, tool.thickness + 8);
    ctx.restore();
    ctx.fillStyle = tool.color; ctx.font = "900 10px ui-monospace, monospace"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(tool.glyph, placement.x, placement.y - 14);
  }

  function draw(schedule = true) {
    if (!model) return;
    const ctx = model.canvas.getContext("2d");
    const state = model.state;
    ctx.clearRect(0, 0, state.stage.width, state.stage.height);
    const gradient = ctx.createLinearGradient(0, 0, 0, state.stage.height);
    gradient.addColorStop(0, "#13211f"); gradient.addColorStop(1, "#07110f");
    ctx.fillStyle = gradient; ctx.fillRect(0, 0, state.stage.width, state.stage.height);
    ctx.strokeStyle = "rgba(205,237,210,.07)"; ctx.lineWidth = 1;
    for (let x = 0; x <= state.stage.width; x += 20) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, state.stage.height); ctx.stroke(); }
    for (let y = 0; y <= state.stage.height; y += 20) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(state.stage.width, y); ctx.stroke(); }

    state.bays.forEach((bay, index) => {
      const active = index < model.releaseIndex;
      const live = model.mode === "running" && index === model.activeLane;
      const zone = bay.work_zone;
      ctx.save(); ctx.setLineDash([6, 5]); ctx.strokeStyle = live ? "#e8c966" : active ? "#c8ff5f" : "rgba(191,223,198,.3)"; ctx.lineWidth = 2;
      ctx.strokeRect(zone[0], zone[1], zone[2], zone[3]); ctx.restore();
      ctx.strokeStyle = "rgba(224,237,226,.5)"; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(bay.launcher[0], bay.launcher[1] - 12); ctx.lineTo(bay.launcher[0], bay.launcher[1] + 8); ctx.stroke();
      ctx.fillStyle = "rgba(224,237,226,.58)"; ctx.beginPath(); ctx.moveTo(bay.launcher[0] - 7, bay.launcher[1] - 12); ctx.lineTo(bay.launcher[0] + 7, bay.launcher[1] - 12); ctx.lineTo(bay.launcher[0], bay.launcher[1] - 2); ctx.closePath(); ctx.fill();
      if (state.guide_mode === "angle_ticks") {
        ctx.strokeStyle = "rgba(232,201,102,.5)"; ctx.lineWidth = 1;
        for (const angle of state.contract.allowed_angles_deg) {
          const radians = angle * Math.PI / 180;
          ctx.beginPath(); ctx.moveTo(bay.anchor[0] + Math.cos(radians) * 42, bay.anchor[1] + Math.sin(radians) * 42); ctx.lineTo(bay.anchor[0] + Math.cos(radians) * 48, bay.anchor[1] + Math.sin(radians) * 48); ctx.stroke();
        }
      }
      ctx.strokeStyle = active ? "#c8ff5f" : "#d8bd62"; ctx.fillStyle = "rgba(5,14,11,.9)"; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(bay.receiver[0], bay.receiver[1], bay.receiver_radius, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.save(); ctx.strokeStyle = active ? "rgba(200,255,95,.72)" : "rgba(255,115,83,.6)"; ctx.lineWidth = 1.5; ctx.setLineDash([2, 3]);
      ctx.beginPath(); ctx.arc(bay.receiver[0], bay.receiver[1], Math.max(3, bay.receiver_radius - 5), 0, Math.PI * 2); ctx.stroke(); ctx.restore();
      ctx.beginPath(); ctx.moveTo(bay.receiver[0] - bay.receiver_radius - 4, bay.receiver[1]); ctx.lineTo(bay.receiver[0] + bay.receiver_radius + 4, bay.receiver[1]); ctx.moveTo(bay.receiver[0], bay.receiver[1] - bay.receiver_radius - 4); ctx.lineTo(bay.receiver[0], bay.receiver[1] + bay.receiver_radius + 4); ctx.stroke();
      const now = performance.now() / 900 + Number(bay.wind_phase);
      for (let particle = 0; particle < 7; particle += 1) {
        const phase = ((now + particle / 7) % 1 + 1) % 1;
        const x = bay.anchor[0] + 62 + phase * (bay.receiver[0] - bay.anchor[0] - 85);
        const y = bay.anchor[1] + Math.sin(phase * Math.PI * 2 + bay.wind_phase) * 3 + Math.sign(bay.wind_y) * phase * phase * 10;
        ctx.fillStyle = "rgba(129,184,157,.42)"; ctx.fillRect(x, y, 7, 1.5);
      }
      ctx.fillStyle = "rgba(213,237,219,.52)"; ctx.font = "800 10px ui-monospace, monospace"; ctx.textAlign = "left"; ctx.fillText(`${String(index + 1).padStart(2, "0")} / ${bay.label}`, 18, bay.anchor[1] - 24);
      if (index < state.bays.length - 1) {
        const next = state.bays[index + 1];
        ctx.strokeStyle = active ? "rgba(200,255,95,.72)" : "rgba(191,223,198,.14)"; ctx.lineWidth = 2; ctx.setLineDash([3, 5]);
        ctx.beginPath(); ctx.moveTo(bay.receiver[0] + bay.receiver_radius + 5, bay.receiver[1]); ctx.lineTo(bay.receiver[0] + 38, bay.receiver[1]); ctx.lineTo(bay.receiver[0] + 38, next.launcher[1]); ctx.lineTo(next.launcher[0] - 12, next.launcher[1]); ctx.stroke(); ctx.setLineDash([]);
      }
    });

    for (const history of model.historyTrails) drawTrail(ctx, history.points, "rgba(255,123,83,.42)", 2, [4, 4]);
    if (model.mode === "running" || model.mode === "solved" || model.mode === "failed" && state.trail_mode !== "live") {
      model.balls.forEach((ball, index) => {
        if (index <= model.activeLane || index < model.releaseIndex) drawTrail(ctx, ball.trail, index < model.releaseIndex ? "rgba(200,255,95,.62)" : "rgba(255,211,102,.82)", 2.5);
      });
    }
    for (const placement of Object.values(model.placements)) if (placement.bay_id !== "unassigned") drawDeflector(ctx, placement, placement.tool_id === model.selected);
    model.balls.forEach((ball, index) => {
      if (ball.hidden || model.mode === "edit" && !model.historyTrails.length || index > model.activeLane && index >= model.releaseIndex) return;
      ctx.beginPath(); ctx.arc(ball.x, ball.y, state.contract.ball_radius, 0, Math.PI * 2);
      ctx.fillStyle = index < model.releaseIndex ? "#c8ff5f" : "#ff6d46"; ctx.shadowColor = ctx.fillStyle; ctx.shadowBlur = 12; ctx.fill(); ctx.shadowBlur = 0; ctx.strokeStyle = "#34140d"; ctx.lineWidth = 2; ctx.stroke();
    });
    if (schedule) model.raf = requestAnimationFrame(draw);
  }

  function hitDeflector(point) {
    const entries = Object.values(model.placements).filter(item => item.bay_id !== "unassigned").reverse();
    for (const item of entries) {
      const tool = toolMap()[item.tool_id];
      const physicalAngle = ((Number(item.angle) % 180) + 180) % 180;
      const radians = (physicalAngle + Number(tool.facet_deg)) * Math.PI / 180;
      const tangent = [Math.cos(radians), Math.sin(radians)];
      const first = [item.x - tangent[0] * tool.length / 2, item.y - tangent[1] * tool.length / 2];
      const second = [item.x + tangent[0] * tool.length / 2, item.y + tangent[1] * tool.length / 2];
      if (distanceToSegment(point, first, second) <= Number(tool.thickness) / 2 + 7) return item;
    }
    return null;
  }

  function bindFullPointer() {
    const canvas = model.canvas;
    canvas.addEventListener("pointerdown", event => {
      if (event.button !== 0 || model.mode !== "edit" || model.drag) return;
      const item = hitDeflector(canvasPoint(event));
      if (!item) return;
      event.preventDefault(); model.selected = item.tool_id;
      model.drag = {pointerId: event.pointerId, toolId: item.tool_id, origin: "canvas", start_stage: [round(item.x), round(item.y)], samples_stage: [[round(item.x), round(item.y)]]};
      try { canvas.setPointerCapture(event.pointerId); } catch (_) {}
      updateRack();
    });
    canvas.addEventListener("pointermove", event => {
      if (!model.drag || event.pointerId !== model.drag.pointerId) return;
      event.preventDefault(); const raw = canvasPoint(event, false); appendDragSample(model.drag, raw); const point = canvasPoint(event); const item = model.placements[model.drag.toolId];
      item.x = round(point[0]); item.y = round(point[1]); draw(false);
    });
    const end = event => {
      if (!model.drag || event.pointerId !== model.drag.pointerId) return;
      event.preventDefault(); const drag = model.drag; model.drag = null; const item = model.placements[drag.toolId];
      const release = canvasPoint(event, false); const bay = bayAtDrop(release);
      if (!bay) {
        item.x = drag.start_stage[0]; item.y = drag.start_stage[1];
        rejectDrop(drag, release);
      } else {
        assignPlacement(drag.toolId, bay.id, "direct_drag", dragGesture(drag, release));
      }
      try { canvas.releasePointerCapture(event.pointerId); } catch (_) {}
    };
    canvas.addEventListener("pointerup", end); canvas.addEventListener("pointercancel", end);
    canvas.addEventListener("contextmenu", event => {
      if (model.mode !== "edit") return;
      const item = hitDeflector(canvasPoint(event));
      if (!item) return; event.preventDefault(); model.selected = item.tool_id; rotateSelected(event.shiftKey ? -5 : 5, "direct_right_click");
    });
    document.querySelectorAll(".rube-tool").forEach(button => button.addEventListener("pointerdown", event => {
      if (event.button !== 0 || model.mode !== "edit") return;
      event.preventDefault(); model.selected = button.dataset.toolId; updateRack();
      const drag = {toolId: model.selected, origin: "rack", start_stage: null, samples_stage: []};
      const ghost = document.createElement("div"); ghost.className = "rube-drag-ghost"; ghost.textContent = toolMap()[model.selected].glyph; ghost.style.setProperty("--tool-color", toolMap()[model.selected].color); document.body.appendChild(ghost);
      const move = moveEvent => { ghost.style.left = `${moveEvent.clientX}px`; ghost.style.top = `${moveEvent.clientY}px`; appendDragSample(drag, canvasPoint(moveEvent, false)); };
      const up = upEvent => {
        document.removeEventListener("pointermove", move); ghost.remove();
        const release = canvasPoint(upEvent, false); const bay = bayAtDrop(release);
        if (!bay) { rejectDrop(drag, release); return; }
        assignPlacement(drag.toolId, bay.id, "direct_drag", dragGesture(drag, release));
      };
      move(event); document.addEventListener("pointermove", move); document.addEventListener("pointerup", up, {once: true});
    }));
  }

  async function render(state, helpers) {
    if (model?.raf) cancelAnimationFrame(model.raf); if (model?.timer) clearInterval(model.timer);
    document.body.dataset.mechanic = "rubes-last-piece";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const interaction = state.control_condition?.interaction || "full";
    const instruction = interaction === "full" ? "DRAG A DEFLECTOR TO A STATION · RIGHT-CLICK ITS FACE TO ROTATE 5°" : "SELECT A DEFLECTOR · PLACE IT BY LINK · ROTATE WITH THE STEP BUTTONS";
    const simplified = interaction === "simplified" ? `<div class="rube-simple-controls rube-edit-only"><div>${state.bays.map(bay => `<button type="button" data-place-bay="${clean(bay.id)}">PLACE IN ${clean(bay.label)}</button>`).join("")}</div><div><button type="button" data-rotate="-5">↶ 5°</button><button type="button" data-rotate="5">5° ↷</button></div></div>` : "";
    const stalledInstruction = state.trail_mode === "live" ? "TRACE ERASED · RECALL THE FLIGHT · REBUILD" : state.trail_mode === "last" ? "ONLY LAST TRACE RETAINED · REBUILD" : "REWIND · STUDY TRACE · REBUILD";
    helpers.app.innerHTML = `<section class="rube-machine" data-interaction="${clean(interaction)}" data-outcome="edit" data-trace-visible="false" data-challenge-id="${clean(state.challenge_id)}"><header class="rube-head"><div><p>DEPARTMENT OF NEEDLESS CONSEQUENCES / FLIGHT BENCH ${clean(state.challenge_id)}</p><h1>RUBE'S <i>LAST PIECE</i></h1><span>${clean(state.prompt)}</span></div><div class="rube-bell" data-ringing="false"><i>◖</i><b>FINAL BELL</b><em>SILENT</em></div></header><main class="rube-main"><section class="rube-stage"><canvas class="rube-canvas" width="${state.stage.width}" height="${state.stage.height}"></canvas><div class="rube-lane-leds">${state.bays.map((bay, index) => `<span class="rube-lane" data-lane-index="${index}" data-live="false" data-fired="false"><i></i>${clean(bay.label)}</span>`).join("")}</div><div class="rube-stamp"><b>FLIGHT STALLED</b><span>${clean(stalledInstruction)}</span></div></section><aside class="rube-console"><p>MIXED DEFLECTOR RACK</p><h2>Faces differ in length, bevel, and rebound. A calibrated receiver trips only when contact arrives inside its impact band.</h2><div class="rube-tools rube-edit-only">${state.tools.map(tool => `<button type="button" class="rube-tool" data-tool-id="${clean(tool.id)}" data-selected="false" data-placed="false" style="--tool:${clean(tool.color)};--facet:${clean(tool.facet_deg)}deg;--face-size:${clean(Math.max(30, Math.round(tool.length * .48)))}px"><i>${clean(tool.glyph)}</i><span>${clean(tool.kind.replaceAll("_", " "))}</span><small>${tool.restitution < .9 ? "SOFT REBOUND" : tool.restitution > 1.05 ? "LIVELY REBOUND" : "BALANCED REBOUND"}</small></button>`).join("")}</div><div class="rube-bays">${state.bays.map(bay => `<div class="rube-bay-card" data-bay-id="${clean(bay.id)}" data-filled="false"><i>↘</i><span>${clean(bay.label)}</span><strong>—</strong></div>`).join("")}</div>${simplified}<p class="rube-direct-note">${clean(instruction)}</p></aside></main><footer class="rube-foot"><div class="rube-status"><span>BENCH TELETYPE · <b class="rube-placed-count">0/${state.bays.length}</b> STATIONS FILLED</span><div class="readout" data-status="idle">PLACE THE DEFLECTORS, THEN TEST THE FLIGHT</div><small class="rube-status-copy">TRAJECTORY AND IMPACT ENERGY ARE REVEALED BY THE ROLLOUT.</small></div><button type="button" class="rube-rewind" disabled>REWIND</button><button type="button" class="rube-run" disabled>PULL RUN</button><button type="button" class="rube-submit">${clean(state.submit_label)}</button></footer>${helpers.cheatPanelTemplate()}</section>`;
    model = {state, helpers, interaction, events: [], placements: {}, selected: null, drag: null, balls: [], historyTrails: [], timer: null, raf: null, tick: 0, activeLane: 0, releaseIndex: 0, lastSequence: [], bellRung: false, attempts: 0, rewinds: 0, mode: "edit", submitting: false, terminal: false, canvas: document.querySelector(".rube-canvas")};
    window.rubesLastPieceModel = model;
    resetFlight(false);
    if (interaction === "full") bindFullPointer();
    else {
      document.querySelectorAll(".rube-tool").forEach(button => button.addEventListener("click", () => { if (model.mode === "edit") { model.selected = button.dataset.toolId; updateRack(); setMessage(`${toolMap()[model.selected].glyph} DEFLECTOR SELECTED`); } }));
      document.querySelectorAll("[data-place-bay]").forEach(button => button.addEventListener("click", () => { if (!model.selected) { setMessage("SELECT A DEFLECTOR FROM THE RACK FIRST", "pending"); return; } assignPlacement(model.selected, button.dataset.placeBay, "bay_place_button"); }));
      document.querySelectorAll("[data-rotate]").forEach(button => button.addEventListener("click", () => rotateSelected(Number(button.dataset.rotate), "rotation_buttons")));
    }
    document.querySelector(".rube-run").addEventListener("click", beginRollout);
    document.querySelector(".rube-rewind").addEventListener("click", rewind);
    document.querySelector(".rube-submit").addEventListener("click", submit);
    helpers.installCheatPanel(); updateRack(); model.raf = requestAnimationFrame(draw);
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.rubes_last_piece = {rootSelector: ".rube-machine", render};
})();
