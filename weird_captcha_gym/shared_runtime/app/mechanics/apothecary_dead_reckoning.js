(() => {
  "use strict";

  const MECHANIC_ID = "apothecary_dead_reckoning";
  let model = null;
  const esc = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const round = (value, places = 3) => Math.round(Number(value) * 10 ** places) / 10 ** places;
  const distance = (first, second) => Math.hypot(first[0] - second[0], first[1] - second[1]);
  const angleDelta = (first, second) => Math.abs((Number(first) - Number(second) + 540) % 360 - 180);
  const ingredientMarks = {fern: "♧", cap: "◒", reed: "╱", rot: "✺", root: "⌁", bloom: "✿"};
  const effectMarks = {moth: "⋈", eye: "◉", thorn: "✣", wave: "≈", sun: "☼", drop: "◊"};

  function record(type, details = {}) {
    const event = {sequence: model.events.length + 1, type, ...details};
    model.events.push(event);
    return event;
  }

  function rootPoint(event) {
    const box = document.querySelector(".apothecary-root").getBoundingClientRect();
    return [round((event.clientX - box.left) / box.width, 6), round((event.clientY - box.top) / box.height, 6)];
  }

  function mapPoint(event) {
    const canvas = document.getElementById("apoth-map");
    const box = canvas.getBoundingClientRect();
    return [
      round(clamp((event.clientX - box.left) / box.width * canvas.width, 0, canvas.width), 3),
      round(clamp((event.clientY - box.top) / box.height * canvas.height, 0, canvas.height), 3),
    ];
  }

  function pathPoints(start, ingredient, grindStep) {
    const samples = Number(model.state.mechanics.path_samples);
    const notches = Number(model.state.parameters.grind_notches);
    const fraction = grindStep / Math.max(1, notches - 1);
    const angle = Number(ingredient.angle_deg) * Math.PI / 180;
    const turn = Number(ingredient.curve_degrees) * fraction * Number(ingredient.turn) * Math.PI / 180;
    const length = Number(ingredient.length);
    const points = [];
    for (let index = 0; index <= samples; index++) {
      const t = index / samples;
      let x, y;
      if (Math.abs(turn) < 1e-9) {
        x = start[0] + length * t * Math.cos(angle);
        y = start[1] + length * t * Math.sin(angle);
      } else {
        const radius = length / turn;
        x = start[0] + radius * (Math.sin(angle + turn * t) - Math.sin(angle));
        y = start[1] - radius * (Math.cos(angle + turn * t) - Math.cos(angle));
      }
      points.push([round(x, 4), round(y, 4)]);
    }
    return points;
  }

  function pathHeading(ingredient, grindStep, pathIndex) {
    const notches = Number(model.state.parameters.grind_notches);
    const samples = Number(model.state.mechanics.path_samples);
    const fraction = grindStep / Math.max(1, notches - 1);
    return (Number(ingredient.angle_deg) + Number(ingredient.curve_degrees) * fraction * Number(ingredient.turn) * pathIndex / samples + 3600) % 360;
  }

  function currentRouteGate() {
    return model?.state.route_gates?.[model.routeProgress] || null;
  }

  function previewAlignment() {
    const gate = currentRouteGate();
    if (!gate || !model?.activeId || model.path) return {aligned: false, centerError: Infinity, headingError: Infinity};
    const ingredient = model.ingredientMap[model.activeId];
    const points = pathPoints(model.position, ingredient, model.grindStep);
    let nearestIndex = 0;
    for (let index = 1; index < points.length; index++) {
      if (distance(points[index], gate.center) < distance(points[nearestIndex], gate.center)) nearestIndex = index;
    }
    const centerError = distance(points[nearestIndex], gate.center);
    const headingError = angleDelta(pathHeading(ingredient, model.grindStep, nearestIndex), gate.heading_deg);
    return {
      aligned: centerError <= Number(model.state.mechanics.gate_center_tolerance)
        && headingError <= Number(model.state.mechanics.gate_heading_tolerance_degrees),
      centerError,
      headingError,
    };
  }

  function insidePolygon(point, polygon) {
    let inside = false;
    for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index++) {
      const [xi, yi] = polygon[index], [xj, yj] = polygon[previous];
      if ((yi > point[1]) !== (yj > point[1])) {
        const crossing = (xj - xi) * (point[1] - yi) / (yj - yi) + xi;
        if (point[0] < crossing) inside = !inside;
      }
    }
    return inside;
  }

  function resolveMotion(points) {
    const newBones = [];
    const traversed = [];
    for (const point of points.slice(1)) {
      traversed.push(point.slice());
      for (const bone of model.state.bones) {
        if (!model.contactedBones.has(bone.id) && insidePolygon(point, bone.polygon)) {
          model.contactedBones.add(bone.id);
          newBones.push(bone.id);
        }
      }
      for (const vortex of model.state.vortices) {
        if (model.contactedVortices.has(vortex.id) || distance(point, vortex.center) > Number(vortex.radius)) continue;
        model.contactedVortices.add(vortex.id);
        const dx = point[0] - vortex.center[0], dy = point[1] - vortex.center[1];
        const warped = Number(vortex.spin) > 0
          ? [vortex.center[0] - dy, vortex.center[1] + dx]
          : [vortex.center[0] + dy, vortex.center[1] - dx];
        const destination = [round(warped[0], 4), round(warped[1], 4)];
        traversed.push(destination.slice());
        return {destination, traversed, newBones: newBones.sort(), vortexId: vortex.id, vortexSpin: Number(vortex.spin)};
      }
    }
    return {destination: points.at(-1).slice(), traversed, newBones: newBones.sort(), vortexId: null, vortexSpin: 0};
  }

  function linePoints(first, second, samples = 8) {
    return Array.from({length: samples + 1}, (_, index) => [
      round(first[0] + (second[0] - first[0]) * index / samples, 4),
      round(first[1] + (second[1] - first[1]) * index / samples, 4),
    ]);
  }

  function reveal(points) {
    for (const point of points) model.revealed.push(point.slice());
  }

  function drawEffect(context, effect) {
    const [x, y] = effect.center;
    context.save();
    context.translate(x, y);
    context.beginPath();
    context.arc(0, 0, Number(effect.radius), 0, Math.PI * 2);
    context.fillStyle = `${effect.color}26`;
    context.fill();
    context.setLineDash([4, 5]);
    context.strokeStyle = effect.color;
    context.lineWidth = 3;
    context.stroke();
    context.setLineDash([]);
    context.fillStyle = effect.color;
    context.font = "700 27px Georgia, serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(effectMarks[effect.glyph] || "◇", 0, 1);
    context.restore();
  }

  function drawBone(context, bone) {
    context.save();
    context.beginPath();
    context.moveTo(bone.polygon[0][0], bone.polygon[0][1]);
    bone.polygon.slice(1).forEach((point) => context.lineTo(point[0], point[1]));
    context.closePath();
    context.fillStyle = "#d2c09b";
    context.strokeStyle = "#5d4938";
    context.lineWidth = 3;
    context.fill();
    context.stroke();
    const center = bone.polygon.reduce((sum, point) => [sum[0] + point[0] / bone.polygon.length, sum[1] + point[1] / bone.polygon.length], [0, 0]);
    context.strokeStyle = "#6e3f37";
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(center[0] - 10, center[1] - 10);
    context.lineTo(center[0] + 10, center[1] + 10);
    context.moveTo(center[0] + 10, center[1] - 10);
    context.lineTo(center[0] - 10, center[1] + 10);
    context.stroke();
    context.restore();
  }

  function drawVortex(context, vortex) {
    context.save();
    context.translate(vortex.center[0], vortex.center[1]);
    context.strokeStyle = "#5b6175";
    context.lineWidth = 3;
    context.beginPath();
    const spin = Number(vortex.spin);
    for (let index = 0; index < 44; index++) {
      const t = index / 43;
      const radius = Number(vortex.radius) * t;
      const angle = spin * t * Math.PI * 4.5;
      const x = Math.cos(angle) * radius, y = Math.sin(angle) * radius;
      if (index) context.lineTo(x, y); else context.moveTo(x, y);
    }
    context.stroke();
    context.restore();
  }

  function drawRouteGate(context, gate) {
    const [x, y] = gate.center;
    const radius = Number(gate.radius);
    context.save();
    context.translate(x, y);
    context.rotate(Number(gate.heading_deg) * Math.PI / 180);
    context.shadowColor = "rgba(216,189,120,.55)";
    context.shadowBlur = 5;
    context.strokeStyle = "#765f35";
    context.fillStyle = "rgba(197,165,91,.12)";
    context.lineWidth = 3;
    context.beginPath();
    context.moveTo(-radius - 28, 0);
    context.lineTo(-radius - 5, 0);
    context.moveTo(radius + 5, 0);
    context.lineTo(radius + 28, 0);
    context.stroke();
    context.beginPath();
    context.arc(0, 0, radius, -.82, .82);
    context.arc(0, 0, radius, Math.PI - .82, Math.PI + .82);
    context.stroke();
    context.beginPath();
    context.moveTo(-radius - 7, -7); context.lineTo(-radius, 0); context.lineTo(-radius - 7, 7);
    context.moveTo(radius + 7, -7); context.lineTo(radius, 0); context.lineTo(radius + 7, 7);
    context.stroke();
    context.beginPath();
    context.arc(0, 0, 3, 0, Math.PI * 2);
    context.fillStyle = "#5a482c";
    context.fill();
    context.restore();
  }

  function drawFlask(context) {
    const [x, y] = model.position;
    context.save();
    context.translate(x, y);
    context.rotate((model.heading + 90) * Math.PI / 180);
    context.fillStyle = "rgba(224,244,231,.82)";
    context.strokeStyle = model.contactedBones.size ? "#a75442" : "#284f4a";
    context.lineWidth = 3;
    context.beginPath();
    context.moveTo(-4, -12);
    context.lineTo(4, -12);
    context.lineTo(4, -4);
    context.bezierCurveTo(12, 2, 11, 13, 0, 15);
    context.bezierCurveTo(-11, 13, -12, 2, -4, -4);
    context.closePath();
    context.fill();
    context.stroke();
    context.fillStyle = model.contactedBones.size ? "#9c4a3f" : "#5b9684";
    context.beginPath();
    context.ellipse(0, 7, 7, 5, 0, 0, Math.PI * 2);
    context.fill();
    context.restore();
  }

  function draw() {
    if (!model) return;
    const canvas = document.getElementById("apoth-map");
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    const parchment = context.createRadialGradient(410, 250, 20, 410, 250, 520);
    parchment.addColorStop(0, "#dcc999");
    parchment.addColorStop(1, "#aa8b60");
    context.fillStyle = parchment;
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.strokeStyle = "rgba(79,59,39,.12)";
    context.lineWidth = 1;
    for (let radius = 65; radius < 430; radius += 54) {
      context.beginPath(); context.arc(model.state.origin[0], model.state.origin[1], radius, 0, Math.PI * 2); context.stroke();
    }
    for (let angle = 0; angle < Math.PI * 2; angle += Math.PI / 12) {
      context.beginPath(); context.moveTo(model.state.origin[0], model.state.origin[1]);
      context.lineTo(model.state.origin[0] + Math.cos(angle) * 520, model.state.origin[1] + Math.sin(angle) * 520); context.stroke();
    }
    model.state.effects.forEach((effect) => drawEffect(context, effect));
    model.state.bones.forEach((bone) => drawBone(context, bone));
    model.state.vortices.forEach((vortex) => drawVortex(context, vortex));

    const fog = document.createElement("canvas");
    fog.width = canvas.width; fog.height = canvas.height;
    const fogContext = fog.getContext("2d");
    fogContext.fillStyle = "rgba(49,43,37,.965)";
    fogContext.fillRect(0, 0, fog.width, fog.height);
    for (let y = 0; y < fog.height; y += 22) {
      for (let x = 0; x < fog.width; x += 22) {
        const noise = ((x * 19 + y * 31 + model.fogSeed) % 37) / 37;
        fogContext.fillStyle = `rgba(133,112,79,${0.035 + noise * 0.055})`;
        fogContext.beginPath(); fogContext.arc(x + 8, y + 10, 4 + noise * 7, 0, Math.PI * 2); fogContext.fill();
      }
    }
    fogContext.globalCompositeOperation = "destination-out";
    model.revealed.forEach((point, index) => {
      const radius = index === 0 ? Number(model.state.parameters.initial_reveal_radius) : Number(model.state.parameters.reveal_radius);
      const gradient = fogContext.createRadialGradient(point[0], point[1], radius * .68, point[0], point[1], radius);
      gradient.addColorStop(0, "rgba(0,0,0,1)"); gradient.addColorStop(1, "rgba(0,0,0,0)");
      fogContext.fillStyle = gradient; fogContext.beginPath(); fogContext.arc(point[0], point[1], radius, 0, Math.PI * 2); fogContext.fill();
    });
    context.drawImage(fog, 0, 0);

    context.strokeStyle = "rgba(58,80,67,.72)";
    context.lineWidth = 3;
    context.lineCap = "round";
    context.beginPath();
    model.revealed.forEach((point, index) => index ? context.lineTo(point[0], point[1]) : context.moveTo(point[0], point[1]));
    context.stroke();
    context.fillStyle = "#3f4036";
    context.beginPath(); context.arc(model.state.origin[0], model.state.origin[1], 7, 0, Math.PI * 2); context.fill();
    context.strokeStyle = "#d8c38d"; context.lineWidth = 2; context.beginPath(); context.arc(model.state.origin[0], model.state.origin[1], 14, 0, Math.PI * 2); context.stroke();

    if (model.activeId) {
      const ingredient = model.ingredientMap[model.activeId];
      const preview = model.path || pathPoints(model.position, ingredient, model.grindStep);
      const remaining = model.path ? preview.slice(model.pathIndex) : preview;
      context.strokeStyle = ingredient.color;
      context.lineWidth = 3;
      context.setLineDash([8, 7]);
      context.beginPath();
      remaining.forEach((point, index) => index ? context.lineTo(point[0], point[1]) : context.moveTo(point[0], point[1]));
      context.stroke(); context.setLineDash([]);
    }
    const routeGate = currentRouteGate();
    if (routeGate) drawRouteGate(context, routeGate);
    drawFlask(context);
  }

  function targetEffectId() {
    const match = model.state.effects.find((effect) => effect.name === model.state.order.name && effect.glyph === model.state.order.glyph);
    return match?.id || null;
  }

  function effectAt(position) {
    const matches = model.state.effects.filter((effect) => distance(position, effect.center) <= Number(effect.radius));
    return matches.length === 1 ? matches[0].id : null;
  }

  function selectionReadout() {
    if (!model?.activeId) return "BREW THE ORDERED SIGIL";
    return `${model.ingredientMap[model.activeId].name.toUpperCase()} · NOTCH ${model.grindStep + 1}`;
  }

  function updateInterface(message = null, status = "idle") {
    if (!model) return;
    const root = document.querySelector(".apothecary-root");
    root.dataset.active = model.activeId ? "true" : "false";
    root.dataset.grinding = model.grinding ? "true" : "false";
    root.dataset.routeProgress = String(model.routeProgress);
    root.dataset.completed = effectAt(model.position) === targetEffectId()
      && model.routeProgress === model.state.route_gates.length
      && model.contactedBones.size <= Number(model.state.parameters.max_hazard_contacts) ? "true" : "false";
    document.querySelectorAll(".apoth-jar").forEach((jar) => jar.classList.toggle("is-selected", jar.dataset.ingredientId === model.activeId));
    const ingredient = model.activeId ? model.ingredientMap[model.activeId] : null;
    document.getElementById("apoth-mortar-name").textContent = ingredient ? ingredient.name.toUpperCase() : "EMPTY MORTAR";
    document.getElementById("apoth-grind-word").textContent = ingredient ? (model.grindStep === 0 ? "WHOLE" : model.grindStep === Number(model.state.parameters.grind_notches) - 1 ? "FINE" : "BENDING") : "NO PATH";
    document.querySelectorAll("[data-grind-step]").forEach((node) => {
      const step = Number(node.dataset.grindStep);
      node.classList.toggle("is-filled", step <= model.grindStep);
      node.classList.toggle("is-current", step === model.grindStep);
      node.disabled = !ingredient || model.interaction !== "simplified" || Boolean(model.path);
    });
    const remaining = (kind) => Number(model.state.parameters[`${kind}_budget`]) - model[`${kind}Spend`];
    document.getElementById("apoth-stock").textContent = String(Number(model.state.parameters.ingredient_budget) - model.ingredientSpend);
    document.getElementById("apoth-water-left").textContent = String(remaining("water"));
    document.getElementById("apoth-bellows-left").textContent = String(remaining("bellows"));
    document.getElementById("apoth-stir").disabled = !ingredient || model.grinding;
    document.getElementById("apoth-water").disabled = Boolean(ingredient) || remaining("water") <= 0;
    document.getElementById("apoth-bellows").disabled = Boolean(ingredient) || remaining("bellows") <= 0;
    document.getElementById("apoth-pestle").disabled = !ingredient || Boolean(model.path) || model.interaction !== "full";
    if (message !== null) model.helpers.setReadout(message, status);
    draw();
  }

  function loadIngredient(ingredientId, inputSource, gesture = null) {
    if (!model || model.terminal || model.submitting || model.grinding || model.path || model.ingredientSpend >= Number(model.state.parameters.ingredient_budget)) return;
    const replacing = Boolean(model.activeId);
    const details = {ingredient_id: ingredientId, input_source: inputSource};
    if (replacing) details.previous_ingredient_id = model.activeId;
    if (gesture) details.gesture = gesture;
    record(replacing ? "replace_ingredient" : "load_ingredient", details);
    model.activeId = ingredientId;
    model.grindStep = 0;
    model.path = null;
    model.pathIndex = 0;
    updateInterface(selectionReadout(), "idle");
  }

  function stopGrinding() {
    if (!model?.grinding) return;
    clearInterval(model.grindTimer);
    model.grindTimer = null;
    model.grinding = false;
    record("grind_release", {grind_step: model.grindStep, input_source: "pestle_hold"});
    updateInterface(selectionReadout(), "idle");
  }

  function startGrinding(event) {
    if (!model || model.interaction !== "full" || !model.activeId || model.path || model.grinding || model.terminal) return;
    model.grinding = true;
    record("grind_start", {grind_step: model.grindStep, input_source: "pestle_hold"});
    event.currentTarget.setPointerCapture?.(event.pointerId);
    model.grindTimer = setInterval(() => {
      if (!model?.grinding) return;
      const maximum = Number(model.state.parameters.grind_notches) - 1;
      if (model.grindStep < maximum) {
        model.grindStep += 1;
        record("grind_tick", {grind_step: model.grindStep, input_source: "pestle_hold"});
        updateInterface(selectionReadout(), "pending");
      }
    }, Number(model.state.mechanics.grind_tick_ms));
    updateInterface(selectionReadout(), "pending");
    event.preventDefault();
  }

  function stir() {
    if (!model?.activeId || model.grinding || model.terminal || model.submitting) return;
    const ingredientId = model.activeId;
    const ingredient = model.ingredientMap[ingredientId];
    if (!model.path) {
      model.pathAligned = previewAlignment().aligned;
      model.path = pathPoints(model.position, ingredient, model.grindStep);
      model.pathIndex = 0;
    }
    const before = model.position.slice();
    const beforeIndex = model.pathIndex;
    const nextIndex = Math.min(model.path.length - 1, beforeIndex + Number(model.state.mechanics.stir_stride));
    const segment = [model.position.slice(), ...model.path.slice(beforeIndex + 1, nextIndex + 1)];
    const resolved = resolveMotion(segment);
    model.position = resolved.destination;
    model.heading = pathHeading(ingredient, model.grindStep, nextIndex);
    model.pathIndex = nextIndex;
    const finished = nextIndex === model.path.length - 1 || Boolean(resolved.vortexId);
    if (resolved.vortexId) model.heading = (model.heading + resolved.vortexSpin * Number(model.state.mechanics.vortex_turn_degrees) + 3600) % 360;
    record("stir", {
      ingredient_id: ingredientId,
      grind_step: model.grindStep,
      path_index_before: beforeIndex,
      path_index_after: nextIndex,
      from: before.map((value) => round(value, 4)),
      to: model.position.map((value) => round(value, 4)),
      contact_ids: resolved.newBones,
      vortex_id: resolved.vortexId,
      path_finished: finished,
      input_source: "ladle_click",
    });
    reveal(resolved.traversed);
    if (finished) {
      model.ingredientSpend += 1;
      if (model.pathAligned && !resolved.vortexId) model.routeProgress += 1;
      model.activeId = null;
      model.grindStep = 0;
      model.path = null;
      model.pathIndex = 0;
      model.pathAligned = false;
    }
    updateInterface(selectionReadout(), "idle");
  }

  function utensil(kind) {
    if (!model || model.activeId || model.grinding || model.terminal || model.submitting) return;
    const budget = Number(model.state.parameters[`${kind}_budget`]);
    const spendKey = `${kind}Spend`;
    if (model[spendKey] >= budget) return;
    const before = model.position.slice();
    let destination;
    if (kind === "water") {
      const dx = model.state.origin[0] - before[0], dy = model.state.origin[1] - before[1];
      const length = Math.hypot(dx, dy), step = Math.min(length, Number(model.state.parameters.water_step));
      destination = length < 1e-9 ? before.slice() : [before[0] + dx / length * step, before[1] + dy / length * step];
      if (length >= 1e-9) model.heading = (Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360;
    } else {
      const radians = model.heading * Math.PI / 180;
      const margin = Number(model.state.mechanics.map_margin);
      destination = [
        clamp(before[0] + Math.cos(radians) * Number(model.state.parameters.bellows_step), margin, model.state.stage.width - margin),
        clamp(before[1] + Math.sin(radians) * Number(model.state.parameters.bellows_step), margin, model.state.stage.height - margin),
      ];
    }
    model[spendKey] += 1;
    const motion = linePoints(before, destination);
    const resolved = resolveMotion(motion);
    model.position = resolved.destination;
    if (resolved.vortexId) model.heading = (model.heading + resolved.vortexSpin * Number(model.state.mechanics.vortex_turn_degrees) + 3600) % 360;
    record(kind, {
      from: before.map((value) => round(value, 4)),
      to: model.position.map((value) => round(value, 4)),
      contact_ids: resolved.newBones,
      vortex_id: resolved.vortexId,
      input_source: `${kind}_button`,
    });
    reveal(resolved.traversed);
    updateInterface(selectionReadout(), "idle");
  }

  function payload(sealedEffect) {
    return {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      events: model.events,
      final_position: model.position.map((value) => round(value, 3)),
      heading_deg: round(model.heading, 3),
      ingredient_spend: model.ingredientSpend,
      water_spend: model.waterSpend,
      bellows_spend: model.bellowsSpend,
      hazard_contacts: [...model.contactedBones].sort(),
      vortex_contacts: [...model.contactedVortices].sort(),
      sealed_effect_id: sealedEffect,
      seal_count: model.sealCount,
      route_progress: model.routeProgress,
      completed: sealedEffect === targetEffectId()
        && model.routeProgress === model.state.route_gates.length
        && model.contactedBones.size <= Number(model.state.parameters.max_hazard_contacts),
    };
  }

  async function seal() {
    if (!model || model.grinding || model.terminal || model.submitting) return;
    const sealedEffect = effectAt(model.position);
    model.sealCount += 1;
    record("seal", {position: model.position.map((value) => round(value, 4)), effect_id: sealedEffect, input_source: "seal_button"});
    const current = model;
    current.submitting = true;
    current.helpers.setReadout("SEAL", "pending");
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload(sealedEffect))});
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.terminal = true;
        document.querySelector(".apothecary-root")?.setAttribute("data-verdict", "pass");
        document.querySelector(".apoth-verdict")?.classList.add("is-pass");
        document.querySelector(".apoth-verdict strong").textContent = "PASS";
        document.querySelector(".apoth-verdict span").textContent = "";
        current.helpers.setReadout("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await render(outcome.state, current.helpers, {freshFailure: true});
        model.helpers.setReadout("FAIL", "error");
      } else {
        current.submitting = false;
        current.helpers.setReadout(selectionReadout(), "idle");
      }
    } catch (_error) {
      if (model === current) {
        current.submitting = false;
        current.helpers.setReadout(selectionReadout(), "idle");
      }
    }
  }

  function installJarInteraction(root) {
    document.querySelectorAll(".apoth-jar").forEach((jar) => {
      jar.addEventListener("click", () => {
        if (model.interaction === "simplified") loadIngredient(jar.dataset.ingredientId, "jar_select");
      });
      jar.addEventListener("pointerdown", (event) => {
        if (model.interaction !== "full" || model.grinding || model.path || model.terminal || model.submitting) return;
        const point = rootPoint(event);
        model.jarDrag = {pointerId: event.pointerId, ingredientId: jar.dataset.ingredientId, start: point, last: [event.clientX, event.clientY], travel: 0, samples: 0};
        root.setPointerCapture?.(event.pointerId);
        root.insertAdjacentHTML("beforeend", `<div class="apoth-jar-ghost" style="--jar-color:${esc(model.ingredientMap[jar.dataset.ingredientId].color)}"><i>${esc(ingredientMarks[model.ingredientMap[jar.dataset.ingredientId].glyph] || "✿")}</i></div>`);
        const ghost = document.querySelector(".apoth-jar-ghost");
        ghost.style.left = `${event.clientX}px`; ghost.style.top = `${event.clientY}px`;
        event.preventDefault();
      });
    });
    root.addEventListener("pointermove", (event) => {
      if (!model?.jarDrag || model.jarDrag.pointerId !== event.pointerId) return;
      const dx = event.clientX - model.jarDrag.last[0], dy = event.clientY - model.jarDrag.last[1];
      model.jarDrag.travel += Math.hypot(dx, dy);
      model.jarDrag.samples += 1;
      model.jarDrag.last = [event.clientX, event.clientY];
      const ghost = document.querySelector(".apoth-jar-ghost");
      if (ghost) { ghost.style.left = `${event.clientX}px`; ghost.style.top = `${event.clientY}px`; }
      event.preventDefault();
    });
    const finishDrag = (event) => {
      if (!model?.jarDrag || model.jarDrag.pointerId !== event.pointerId) return;
      const drag = model.jarDrag, end = rootPoint(event);
      model.jarDrag = null;
      document.querySelector(".apoth-jar-ghost")?.remove();
      root.releasePointerCapture?.(event.pointerId);
      const rect = model.state.interaction_geometry.mortar_rect;
      const inMortar = end[0] >= rect[0] && end[0] <= rect[0] + rect[2] && end[1] >= rect[1] && end[1] <= rect[1] + rect[3];
      if (inMortar) loadIngredient(drag.ingredientId, "jar_drag", {start_root: drag.start, end_root: end, travel_px: round(drag.travel, 2), sample_count: drag.samples});
      else updateInterface(selectionReadout(), "idle");
      event.preventDefault();
    };
    root.addEventListener("pointerup", finishDrag);
    root.addEventListener("pointercancel", finishDrag);
  }

  function jarTemplate(ingredient) {
    const rect = model.state.interaction_geometry.jar_rects[ingredient.id];
    return `<button class="apoth-jar" data-ingredient-id="${esc(ingredient.id)}" style="left:${rect[0] * 100}%;top:${rect[1] * 100}%;width:${rect[2] * 100}%;height:${rect[3] * 100}%;--jar-color:${esc(ingredient.color)}"><i>${esc(ingredientMarks[ingredient.glyph] || "✿")}</i><span>${esc(ingredient.name)}</span></button>`;
  }

  async function render(state, helpers, options = {}) {
    if (model?.grindTimer) clearInterval(model.grindTimer);
    document.body.dataset.mechanic = "apothecary-dead-reckoning";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const interaction = state.control_condition?.interaction || "full";
    const notches = Number(state.parameters.grind_notches);
    model = {
      state, helpers, interaction,
      ingredientMap: Object.fromEntries(state.ingredients.map((ingredient) => [ingredient.id, ingredient])),
      events: [], position: state.origin.slice(), heading: 0, activeId: null, grindStep: 0,
      grinding: false, grindTimer: null, path: null, pathIndex: 0, pathAligned: false,
      ingredientSpend: 0, routeProgress: 0,
      waterSpend: 0, bellowsSpend: 0, contactedBones: new Set(), contactedVortices: new Set(),
      revealed: [state.origin.slice()], jarDrag: null, sealCount: 0, terminal: false, submitting: false,
      fogSeed: [...state.challenge_id].reduce((sum, char) => sum + char.charCodeAt(0), 0),
    };
    window.apothecaryDeadReckoningModel = model;
    const mortar = state.interaction_geometry.mortar_rect;
    const orderMark = effectMarks[state.order.glyph] || "◇";
    const interactionNote = interaction === "full" ? "FULL" : "SIMPLIFIED";
    helpers.app.innerHTML = `
      <section class="apothecary-root" data-interaction="${esc(interaction)}" data-fresh-failure="${options.freshFailure ? "true" : "false"}" data-verdict="">
        <header class="apoth-head">
          <div><span>DEAD RECKONING DISPENSARY</span><h1>Brew the ordered sigil.</h1></div>
          <aside><small>ORDERED SIGIL</small><i style="--effect-color:${esc(state.order.color)}">${esc(orderMark)}</i><b>${esc(state.order.name)}</b></aside>
        </header>
        <main class="apoth-map-frame"><canvas id="apoth-map" width="${state.stage.width}" height="${state.stage.height}"></canvas><div class="apoth-map-corner">ORIGIN ⊙</div></main>
        <aside class="apoth-bench"><header><span>INGREDIENT CABINET</span><b>${esc(interactionNote)}</b></header></aside>
        ${state.ingredients.map(jarTemplate).join("")}
        <section class="apoth-mortar" style="left:${mortar[0] * 100}%;top:${mortar[1] * 100}%;width:${mortar[2] * 100}%;height:${mortar[3] * 100}%">
          <div><small>MORTAR</small><b id="apoth-mortar-name">EMPTY MORTAR</b><span id="apoth-grind-word">NO PATH</span></div>
          <button id="apoth-pestle" aria-label="Pestle"><i></i><b>PESTLE</b></button>
        </section>
        <div class="apoth-grind-track" data-mode="${esc(interaction)}"><small>WHOLE</small><div>${Array.from({length: notches}, (_, step) => interaction === "simplified" ? `<button data-grind-step="${step}" aria-label="Curve notch ${step + 1}"></button>` : `<span data-grind-step="${step}"></span>`).join("")}</div><small>FINE</small></div>
        <section class="apoth-tools">
          <button id="apoth-stir"><i>⌁</i><span>STIR PATH</span></button>
          <button id="apoth-water"><i>▽</i><span>WATER <b id="apoth-water-left">0</b></span></button>
          <button id="apoth-bellows"><i>≋</i><span>BELLOWS <b id="apoth-bellows-left">0</b></span></button>
        </section>
        <footer class="apoth-foot"><div class="apoth-ledger"><span>STOCK <b id="apoth-stock">0</b></span></div><div class="readout" data-status="idle">${options.freshFailure ? "FAIL" : "BREW THE ORDERED SIGIL"}</div><button id="apoth-seal">SEAL</button></footer>
        <div class="apoth-verdict ${options.freshFailure ? "is-fresh" : ""}"><strong>${options.freshFailure ? "FAIL" : ""}</strong><span></span></div>
        ${helpers.cheatPanelTemplate()}
      </section>`;

    const root = document.querySelector(".apothecary-root");
    installJarInteraction(root);
    document.querySelectorAll("button[data-grind-step]").forEach((button) => button.addEventListener("click", () => {
      if (!model.activeId || model.path || model.interaction !== "simplified") return;
      model.grindStep = Number(button.dataset.grindStep);
      record("grind_set", {grind_step: model.grindStep, input_source: "curve_notches"});
      updateInterface(selectionReadout(), "idle");
    }));
    const pestle = document.getElementById("apoth-pestle");
    pestle.addEventListener("pointerdown", startGrinding);
    pestle.addEventListener("pointerup", stopGrinding);
    pestle.addEventListener("pointercancel", stopGrinding);
    pestle.addEventListener("lostpointercapture", stopGrinding);
    document.getElementById("apoth-stir").addEventListener("click", stir);
    document.getElementById("apoth-water").addEventListener("click", () => utensil("water"));
    document.getElementById("apoth-bellows").addEventListener("click", () => utensil("bellows"));
    document.getElementById("apoth-seal").addEventListener("click", seal);
    document.getElementById("apoth-map").addEventListener("pointermove", mapPoint);
    helpers.installCheatPanel();
    updateInterface(null);
    if (options.freshFailure) {
      const current = model;
      setTimeout(() => {
        if (model !== current) return;
        document.querySelector(".apothecary-root")?.setAttribute("data-fresh-failure", "false");
        document.querySelector(".apoth-verdict")?.classList.remove("is-fresh");
        if (!current.events.length) current.helpers.setReadout(selectionReadout(), "idle");
      }, 1800);
    }
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {rootSelector: ".apothecary-root", render};
})();
