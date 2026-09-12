(() => {
  "use strict";
  let model = null;

  function corners(x, y, length, width, angle) {
    const ca = Math.cos(angle), sa = Math.sin(angle);
    return [[-length / 2, -width / 2], [length / 2, -width / 2], [length / 2, width / 2], [-length / 2, width / 2]]
      .map(([dx, dy]) => [x + ca * dx - sa * dy, y + sa * dx + ca * dy]);
  }
  function axes(points) {
    const result = [];
    for (let i = 0; i < points.length; i += 1) {
      const a = points[i], b = points[(i + 1) % points.length];
      const dx = b[0] - a[0], dy = b[1] - a[1], length = Math.hypot(dx, dy);
      if (length > 1e-9) result.push([-dy / length, dx / length]);
    }
    return result;
  }
  function overlaps(first, second) {
    for (const [ax, ay] of axes(first).concat(axes(second))) {
      const a = first.map(point => point[0] * ax + point[1] * ay);
      const b = second.map(point => point[0] * ax + point[1] * ay);
      if (Math.max(...a) <= Math.min(...b) + 1e-7 || Math.max(...b) <= Math.min(...a) + 1e-7) return false;
    }
    return true;
  }
  function wrapAngle(value) { return ((value + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI; }
  function angleError(a, b) { return Math.abs(wrapAngle(a - b)); }
  function setControl(command, inputSource) {
    if (!model || model.done) return;
    applyCommand(command);
    model.actions.push({sequence: model.actions.length + 1, tick: model.tick, type: "control", command, input_source: inputSource});
    model.helpers.setReadout("", "idle");
  }
  function applyCommand(command) {
    if (command === "steer_left") model.controls.steer = -1;
    else if (command === "steer_right") model.controls.steer = 1;
    else if (command === "steer_center") model.controls.steer = 0;
    else if (command === "forward") { model.controls.throttle = 1; model.controls.brake = false; }
    else if (command === "reverse") { model.controls.throttle = -1; model.controls.brake = false; }
    else if (command === "coast") model.controls.throttle = 0;
    else if (command === "brake_on") { model.controls.brake = true; model.controls.throttle = 0; }
    else if (command === "brake_off") model.controls.brake = false;
  }
  function carCorners() {
    const physics = model.state.world.physics;
    return corners(model.car.x, model.car.y, physics.car_length, physics.car_width, model.car.heading);
  }
  function collisionReason() {
    const world = model.state.world, physics = world.physics, car = carCorners();
    if (car.some(([x, y]) => x < 0 || x > Number(world.width) || y < 0 || y > Number(world.height))) return "KERB COLLISION";
    for (const obstacle of world.obstacles) {
      const other = corners(Number(obstacle.x), Number(obstacle.y), Number(obstacle.width), Number(obstacle.height), Number(obstacle.angle || 0));
      if (overlaps(car, other)) return `COLLISION — ${obstacle.id.toUpperCase()}`;
    }
    return null;
  }
  function advance() {
    const physics = model.state.world.physics;
    let speed = model.car.speed;
    if (model.controls.brake) speed *= Number(physics.brake_factor);
    else if (model.controls.throttle > 0) speed = Math.min(Number(physics.max_forward_speed), speed + Number(physics.acceleration));
    else if (model.controls.throttle < 0) speed = Math.max(-Number(physics.max_reverse_speed), speed - Number(physics.reverse_acceleration));
    else speed *= Number(physics.coast_factor);
    const fraction = Math.min(1, Math.abs(speed) / Math.max(Number(physics.max_forward_speed), 0.001));
    const direction = speed < 0 ? -1 : 1;
    model.car.heading = wrapAngle(model.car.heading + Number(model.controls.steer) * Number(physics.turn_rate) * (0.25 + 0.75 * fraction) * direction);
    model.car.x += Math.cos(model.car.heading) * speed;
    model.car.y += Math.sin(model.car.heading) * speed;
    model.car.speed = speed;
    model.tick += 1;
    return collisionReason();
  }
  function draw() {
    if (!model) return;
    const world = model.state.world, car = document.querySelector(".vv-car");
    if (car) {
      car.style.left = `${model.car.x / Number(world.width) * 100}%`;
      car.style.top = `${model.car.y / Number(world.height) * 100}%`;
      car.style.transform = `translate(-50%, -50%) rotate(${model.car.heading * 180 / Math.PI}deg)`;
      car.dataset.x = model.car.x.toFixed(3); car.dataset.y = model.car.y.toFixed(3);
      car.dataset.heading = model.car.heading.toFixed(5); car.dataset.speed = model.car.speed.toFixed(4);
    }
    const tick = document.querySelector(".vv-tick b"), speed = document.querySelector(".vv-speed b"), pose = document.querySelector(".vv-pose b");
    if (tick) tick.textContent = String(model.tick).padStart(4, "0");
    if (speed) speed.textContent = `${model.car.speed.toFixed(2)} px/tick`;
    if (pose) pose.textContent = `${Math.round(model.car.x)}, ${Math.round(model.car.y)} · ${Math.round(model.car.heading * 180 / Math.PI)}°`;
  }
  function parked() {
    const world = model.state.world, physics = world.physics, target = world.target;
    if (Math.hypot(model.car.x - Number(target.x), model.car.y - Number(target.y)) > Number(physics.position_tolerance)) return false;
    if (angleError(model.car.heading, Number(target.heading)) > Number(physics.heading_tolerance_deg) * Math.PI / 180) return false;
    if (Math.abs(model.car.speed) > Number(physics.speed_tolerance)) return false;
    const ca = Math.cos(Number(target.heading)), sa = Math.sin(Number(target.heading));
    return carCorners().every(([x, y]) => {
      const localX = (x - Number(target.x)) * ca + (y - Number(target.y)) * sa;
      const localY = -(x - Number(target.x)) * sa + (y - Number(target.y)) * ca;
      return Math.abs(localX) <= Number(target.width) / 2 && Math.abs(localY) <= Number(target.length) / 2;
    });
  }
  async function finish(completed, reason) {
    if (!model || model.done) return;
    model.done = true; clearInterval(model.timer);
    model.helpers.setReadout(reason === "park" ? "CHECKING PARKED POSE…" : reason, reason === "park" ? "busy" : "error");
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({
        mechanic_id: model.state.mechanic_id, task_id: model.state.task_id, challenge_id: model.state.challenge_id,
        events: model.actions, final_tick: model.tick, completed, reason,
      })});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.helpers.setReadout("PARKED · PASS", "passed");
        document.querySelector(".vv")?.classList.add("is-passed");
      } else {
        model.helpers.setReadout(`FAIL · ${outcome.feedback || reason}`, "error");
        document.querySelector(".vv")?.classList.add("is-failed");
        if (outcome.state) setTimeout(() => model.helpers.render(outcome.state), 850);
      }
    } catch (_error) {
      model.done = false; model.helpers.setReadout("RESULT CONNECTION FAILED", "error");
    }
  }
  function controlMarkup(interaction) {
    if (interaction === "simplified") return `<div class="vv-controls vv-buttons" aria-label="valet proxy controls">
      <button data-vv-command="steer_left">TURN LEFT</button><button data-vv-command="steer_center">WHEELS STRAIGHT</button><button data-vv-command="steer_right">TURN RIGHT</button>
      <button data-vv-command="forward">FORWARD</button><button data-vv-command="coast">COAST</button><button data-vv-command="reverse">REVERSE</button><button data-vv-command="brake_on">BRAKE</button>
    </div>`;
    return `<div class="vv-controls vv-key-guide"><span>FULL INPUT</span><b>↑ DRIVE</b><b>↓ REVERSE</b><b>← → STEER</b><b>SPACE BRAKE</b></div>`;
  }
  async function render(state, helpers) {
    document.body.dataset.mechanic = "velvet-valet";
    if (model?.timer) clearInterval(model.timer);
    if (model?.keyHandler) window.removeEventListener("keydown", model.keyHandler);
    if (model?.keyUpHandler) window.removeEventListener("keyup", model.keyUpHandler);
    const interaction = state.control_condition?.interaction || "full", world = state.world, physics = world.physics;
    model = {state, helpers, interaction, tick: 0, actions: [], done: false, started: false, timer: null,
      controls: {steer: 0, throttle: 0, brake: false}, car: {...world.start, speed: 0}, keyHandler: null, keyUpHandler: null};
    const obstacles = world.obstacles.map(item => `<div class="vv-obstacle shade-${item.shade}" style="left:${Number(item.x) / Number(world.width) * 100}%;top:${Number(item.y) / Number(world.height) * 100}%;width:${Number(item.width) / Number(world.width) * 100}%;height:${Number(item.height) / Number(world.height) * 100}%" data-obstacle="${item.id}"><i></i><b></b></div>`).join("");
    const bay = `<div class="vv-bay" style="left:${Number(world.target.x) / Number(world.width) * 100}%;top:${Number(world.target.y) / Number(world.height) * 100}%;width:${Number(world.target.width) / Number(world.width) * 100}%;height:${Number(world.target.length) / Number(world.height) * 100}%"><span>REVERSE IN</span><b>▼</b></div>`;
    helpers.app.innerHTML = `<section class="vv" tabindex="0"><header><div><small>THEATRE COURTYARD · NONHOLONOMIC PARKING</small><h1>Velvet Valet</h1><p>${state.prompt}</p></div><div class="vv-readouts"><span class="vv-tick">TICK <b>0000</b></span><span class="vv-speed">SPEED <b>0.00 px/tick</b></span><span class="vv-pose">POSE <b>—</b></span></div></header>
      <main class="vv-courtyard" style="--world-w:${world.width};--world-h:${world.height}"><div class="vv-kerb vv-kerb-top"></div><div class="vv-kerb vv-kerb-bottom"></div><div class="vv-kerb vv-kerb-left"></div><div class="vv-kerb vv-kerb-right"></div>${bay}${obstacles}<div class="vv-car" data-x="${world.start.x}" data-y="${world.start.y}" data-heading="${world.start.heading}" data-speed="0"><i></i><b></b></div><button class="vv-start" type="button">START ENGINE</button></main>
      <footer><div class="readout vv-status" data-status="idle"></div><button class="vv-submit" type="button" disabled>CHECK PARKING</button>${controlMarkup(interaction)}</footer></section>`;
    const shell = document.querySelector(".vv"), startButton = document.querySelector(".vv-start"), submit = document.querySelector(".vv-submit");
    function start() { if (model.started || model.done) return; model.started = true; startButton.remove(); submit.disabled = false; shell.focus(); model.timer = setInterval(step, Number(physics.tick_ms)); model.helpers.setReadout("ENGINE RUNNING", "idle"); }
    function step() { if (!model || model.done || !model.started) return; const collision = advance(); draw(); if (collision) finish(false, collision); else if (model.tick >= Number(physics.max_ticks)) finish(false, "TIME LIMIT"); }
    model.keyHandler = event => {
      if (interaction !== "full" || event.repeat) return;
      const map = {ArrowLeft: "steer_left", ArrowRight: "steer_right", ArrowUp: "forward", ArrowDown: "reverse", " ": "brake_on"};
      if (!map[event.key]) return; event.preventDefault(); if (!model.started) start(); setControl(map[event.key], "keyboard");
    };
    model.keyUpHandler = event => {
      if (interaction !== "full") return;
      const map = {ArrowLeft: "steer_center", ArrowRight: "steer_center", ArrowUp: "coast", ArrowDown: "coast", " ": "brake_off"};
      if (!map[event.key]) return; event.preventDefault(); setControl(map[event.key], "keyboard");
    };
    window.addEventListener("keydown", model.keyHandler); window.addEventListener("keyup", model.keyUpHandler);
    startButton.addEventListener("click", start);
    document.querySelectorAll("[data-vv-command]").forEach(button => button.addEventListener("click", () => { if (!model.started) start(); setControl(button.dataset.vvCommand, "control_button"); }));
    submit.addEventListener("click", () => { if (model.started && !model.done) finish(parked(), "park"); });
    shell.focus(); draw();
  }
  function step() {}
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.velvet_valet = {render, rootSelector: ".vv"};
})();
