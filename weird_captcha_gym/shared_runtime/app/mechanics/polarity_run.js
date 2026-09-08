(() => {
  "use strict";
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};

  const MECHANIC_ID = "polarity_run";

  const copyBody = (body) => ({
    x: Number(body.x),
    y: Number(body.y),
    vx: Number(body.vx),
    vy: Number(body.vy),
  });

  function polarityGlyph(value) {
    return Number(value) < 0 ? "−" : Number(value) > 0 ? "+" : "0";
  }

  function closeEnough(value, fallback = 0) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function circleHitsRect(body, rect, radius) {
    const left = Number(rect.x);
    const top = Number(rect.y);
    const right = left + Number(rect.width);
    const bottom = top + Number(rect.height);
    const x = Math.max(left, Math.min(body.x, right));
    const y = Math.max(top, Math.min(body.y, bottom));
    return Math.hypot(body.x - x, body.y - y) < radius;
  }

  function render(state, helpers) {
    const app = helpers.app;
    const condition = state.control_condition || {difficulty: 3, interaction: "full", real_time: "live"};
    const interaction = condition.interaction === "simplified" ? "simplified" : "full";
    const initial = state.initial_bead || {x: 70, y: 260, vx: 2.6, vy: 0, radius: 10};
    const physics = state.physics || {};
    const canvasWidth = Number(state.canvas?.width || 900);
    const canvasHeight = Number(state.canvas?.height || 480);
    const palette = {
      aurora: ["#0b1730", "#123d57", "#8be0c8", "#fbdb75"],
      ember: ["#211424", "#532438", "#ffb36c", "#ffd27c"],
      "violet-night": ["#17132d", "#30235a", "#cf9bff", "#f4dbff"],
      "sea-glass": ["#092b35", "#0e5a59", "#8de4cc", "#d5f1ba"],
    }[state.palette] || ["#0b1730", "#123d57", "#8be0c8", "#fbdb75"];

    app.innerHTML = `
      <section class="polarity-run-shell" data-interaction="${interaction}">
        <header class="polarity-run-header">
          <div>
            <p class="polarity-run-kicker">ELECTROSTATIC MAZE / RUN ${helpers.text(state.challenge_id || "")}</p>
            <h1>Polarity Run</h1>
            <p class="polarity-run-prompt">${helpers.text(state.prompt || "Guide the bead to the exit.")}</p>
          </div>
          <div class="polarity-run-readout readout" data-status="idle">OBSERVE THE TRAJECTORY</div>
        </header>
        <div class="polarity-run-layout">
          <div class="polarity-run-stage">
            <canvas class="polarity-run-canvas" width="${canvasWidth}" height="${canvasHeight}" aria-label="Live electrostatic maze"></canvas>
            <div class="polarity-run-legend">
              <span><i class="legend-dot legend-positive"></i>positive pole</span>
              <span><i class="legend-dot legend-negative"></i>negative pole</span>
              <span><i class="legend-line"></i>bead trail</span>
            </div>
          </div>
          <aside class="polarity-run-console">
            <div class="polarity-run-instruction">
              <span class="console-label">CONTROL</span>
              <strong>${interaction === "full" ? "Drag the charge dial" : "Choose a bead charge"}</strong>
              <p>${interaction === "full" ? "Pull the physical knob to one of the three detents. The bead keeps its momentum between corrections." : "Use −, 0, or + to change the bead's charge while it is moving."}</p>
            </div>
            <div class="polarity-run-metrics">
              <div><span>BEAD CHARGE</span><strong class="polarity-run-charge">0</strong></div>
              <div><span>GATES CLEARED</span><strong class="polarity-run-gates">0 / ${state.gates?.length || 0}</strong></div>
              <div><span>FIELD CLOCK</span><strong class="polarity-run-clock">0.0 s</strong></div>
            </div>
            ${interaction === "simplified" ? `
              <div class="polarity-run-buttons" aria-label="Charge buttons">
                <button type="button" class="polarity-button" data-polarity="-1" aria-label="Set negative charge">−</button>
                <button type="button" class="polarity-button polarity-button-neutral" data-polarity="0" aria-label="Set neutral charge">0</button>
                <button type="button" class="polarity-button" data-polarity="1" aria-label="Set positive charge">+</button>
              </div>
            ` : `
              <div class="polarity-dial-wrap">
                <div class="polarity-dial-labels"><span>−</span><span>0</span><span>+</span></div>
                <div class="polarity-dial" role="slider" tabindex="0" aria-valuemin="-1" aria-valuemax="1" aria-valuenow="0" aria-valuetext="neutral" aria-label="Charge polarity dial">
                  <div class="polarity-dial-track"><span></span><span></span><span></span></div>
                  <div class="polarity-dial-knob" data-dial-polarity="0"></div>
                  <input class="polarity-dial-range" type="range" min="-1" max="1" step="1" value="0" aria-label="Drag charge polarity">
                </div>
                <small>three physical detents · drag only</small>
              </div>
            `}
            <div class="polarity-run-note"><span class="console-label">FIELD NOTE</span><p>Like signs repel. Opposite signs attract. Neutral coasts on the velocity already earned.</p></div>
          </aside>
        </div>
      </section>
    `;

    const canvas = app.querySelector(".polarity-run-canvas");
    const context = canvas.getContext("2d");
    const chargeReadout = app.querySelector(".polarity-run-charge");
    const gatesReadout = app.querySelector(".polarity-run-gates");
    const clockReadout = app.querySelector(".polarity-run-clock");
    const readout = app.querySelector(".polarity-run-readout");
    const shell = app.querySelector(".polarity-run-shell");
    const model = {
      state,
      body: copyBody(initial),
      activePolarity: 0,
      displayPolarity: 0,
      events: [],
      gateCrossings: [],
      trail: [],
      lastTick: -1,
      eventIndex: 0,
      gateIndex: 0,
      previousX: Number(initial.x),
      startedAt: null,
      submitted: false,
      failed: false,
      dragging: false,
      pendingDial: 0,
      dialPointerId: null,
      dialPointerActive: false,
      dialPointerStartX: 0,
      dialPointerStartY: 0,
      dialDragMoved: false,
      dialAcceptedValue: null,
      raf: null,
    };

    const setReadout = (message, status = "idle") => {
      if (readout) {
        readout.textContent = message;
        readout.dataset.status = status;
      }
      helpers.setReadout(message, status);
    };

    const currentTaskMs = () => model.startedAt == null ? 0 : Math.max(0, helpers.interactionNow() - model.startedAt);
    const currentTick = () => Math.floor(currentTaskMs() / Number(physics.tick_ms || 40));
    const inputTick = () => {
      const observed = Math.max(0, currentTick());
      const lastEventTick = model.events.length ? Number(model.events[model.events.length - 1].tick) : -1;
      const next = Math.max(observed, model.lastTick >= observed ? observed + 1 : observed, lastEventTick + 1);
      return Math.min(Math.max(0, next), Number(physics.ticks || 1) - 1);
    };

    const updateReadouts = () => {
      chargeReadout.textContent = polarityGlyph(model.displayPolarity);
      gatesReadout.textContent = `${model.gateIndex} / ${(state.gates || []).length}`;
      clockReadout.textContent = `${(currentTaskMs() / 1000).toFixed(1)} s`;
      shell.dataset.polarity = String(model.displayPolarity);
      const dial = app.querySelector(".polarity-dial");
      const knob = app.querySelector(".polarity-dial-knob");
      const range = app.querySelector(".polarity-dial-range");
      if (dial) {
        dial.setAttribute("aria-valuenow", String(model.displayPolarity));
        dial.setAttribute("aria-valuetext", model.displayPolarity < 0 ? "negative" : model.displayPolarity > 0 ? "positive" : "neutral");
      }
      if (knob) {
        knob.dataset.dialPolarity = String(model.displayPolarity);
        knob.style.left = `${model.displayPolarity < 0 ? 0 : model.displayPolarity > 0 ? 100 : 50}%`;
      }
      if (range) range.value = String(model.displayPolarity);
      app.querySelectorAll(".polarity-button").forEach((button) => {
        button.classList.toggle("is-selected", Number(button.dataset.polarity) === model.displayPolarity);
      });
    };

    const setPolarity = (polarity, inputSource) => {
      const next = Number(polarity);
      if (![ -1, 0, 1 ].includes(next) || model.submitted) return;
      if (next === model.displayPolarity && model.events.length) return;
      if (model.startedAt == null) model.startedAt = helpers.interactionNow();
      const tick = inputTick();
      if (tick < 0 || tick >= Number(physics.ticks || 1)) return;
      model.displayPolarity = next;
      model.events.push({
        seq: model.events.length + 1,
        type: "polarity_change",
        tick,
        polarity: next,
        input_source: inputSource,
      });
      updateReadouts();
      setReadout(`CHARGE ${polarityGlyph(next)} · WATCH THE CURVE`, "active");
    };

    const stepBody = (tick) => {
      while (model.eventIndex < model.events.length && model.events[model.eventIndex].tick === tick) {
        model.activePolarity = Number(model.events[model.eventIndex].polarity);
        model.eventIndex += 1;
      }
      let fx = 0;
      let fy = 0;
      (state.charges || []).forEach((charge) => {
        const dx = Number(charge.x) - model.body.x;
        const dy = Number(charge.y) - model.body.y;
        const distance = Math.hypot(dx, dy);
        if (distance <= 0.001 || distance >= Number(physics.influence_radius)) return;
        let coefficient = -Number(physics.force_strength) * model.activePolarity * Number(charge.charge);
        coefficient /= distance + Number(physics.softening);
        fx += coefficient * dx;
        fy += coefficient * dy;
      });
      model.body.vx = (model.body.vx + fx * Number(physics.integration)) * Number(physics.damping);
      model.body.vy = (model.body.vy + fy * Number(physics.integration)) * Number(physics.damping);
      const speed = Math.hypot(model.body.vx, model.body.vy);
      if (speed > Number(physics.max_speed)) {
        const scale = Number(physics.max_speed) / speed;
        model.body.vx *= scale;
        model.body.vy *= scale;
      }
      model.body.x += model.body.vx;
      model.body.y += model.body.vy;
      if (tick % 2 === 0 || tick < 12) model.trail.push({x: model.body.x, y: model.body.y, polarity: model.activePolarity});
      if (!Number.isFinite(model.body.x) || !Number.isFinite(model.body.y)) return "non-finite bead state";
      if (model.body.y < Number(physics.world_padding) || model.body.y > canvasHeight - Number(physics.world_padding)) return "bead left the chamber";
      if ((state.walls || []).some((wall) => circleHitsRect(model.body, wall, Number(physics.bead_radius)))) return "bead struck a maze rail";
      const gate = (state.gates || [])[model.gateIndex];
      if (gate && model.previousX < Number(gate.x) && Number(gate.x) <= model.body.x) {
        model.gateCrossings.push({
          tick: tick + 1,
          gate_id: gate.id,
          x: Number(model.body.x.toFixed(4)),
          y: Number(model.body.y.toFixed(4)),
          polarity: model.activePolarity,
        });
        model.gateIndex += 1;
      }
      model.previousX = model.body.x;
      if (model.body.x >= Number(state.target.x)) {
        if (model.gateIndex !== (state.gates || []).length) return "exit reached before every gate";
        if (Math.hypot(model.body.x - Number(state.target.x), model.body.y - Number(state.target.y)) <= Number(state.target.radius)) return "passed";
        return "bead passed the exit ring";
      }
      return null;
    };

    const terminalBody = () => ({
      x: Number(model.body.x.toFixed(5)),
      y: Number(model.body.y.toFixed(5)),
      vx: Number(model.body.vx.toFixed(5)),
      vy: Number(model.body.vy.toFixed(5)),
    });

    const submit = async (passed, reason = "") => {
      if (model.submitted) return;
      model.submitted = true;
      const terminal = {
        passed,
        tick: Math.max(0, model.lastTick + 1),
        gates: model.gateCrossings.map((item) => item.gate_id),
        bead: terminalBody(),
      };
      try {
        const response = await fetch("/result", {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify({
            mechanic_id: MECHANIC_ID,
            task_id: state.task_id,
            challenge_id: state.challenge_id,
            interaction_mode: interaction,
            events: model.events,
            gate_crossings: model.gateCrossings,
            terminal,
            completed: passed,
          }),
        });
        const outcome = await response.json();
        if (outcome.passed === true) {
          setReadout("PASS · EXIT RING REACHED", "passed");
          return;
        }
        setReadout(`FAIL · ${helpers.text(outcome.feedback || reason || "TRY THE NEXT RUN")}`, "error");
        if (outcome.state) await helpers.render(outcome.state);
      } catch (_error) {
        setReadout("SUBMISSION ERROR · RUN AGAIN", "error");
      }
    };

    const draw = () => {
      const gradient = context.createLinearGradient(0, 0, canvasWidth, canvasHeight);
      gradient.addColorStop(0, palette[0]);
      gradient.addColorStop(1, palette[1]);
      context.fillStyle = gradient;
      context.fillRect(0, 0, canvasWidth, canvasHeight);
      context.fillStyle = "rgba(255,255,255,0.04)";
      for (let y = 0; y < canvasHeight; y += 18) context.fillRect(0, y, canvasWidth, 1);
      context.strokeStyle = "rgba(163,240,221,0.12)";
      context.lineWidth = 1;
      for (let x = 20; x < canvasWidth; x += 40) {
        context.beginPath(); context.moveTo(x, 0); context.lineTo(x - 80, canvasHeight); context.stroke();
      }
      (state.walls || []).forEach((wall) => {
        context.fillStyle = "rgba(5,15,29,0.9)";
        context.fillRect(Number(wall.x), Number(wall.y), Number(wall.width), Number(wall.height));
        context.fillStyle = "rgba(139,224,200,0.25)";
        context.fillRect(Number(wall.x), Number(wall.y), Number(wall.width), 3);
      });
      (state.gates || []).forEach((gate, index) => {
        const active = index === model.gateIndex;
        context.strokeStyle = active ? "rgba(255,219,117,0.62)" : "rgba(139,224,200,0.17)";
        context.setLineDash([5, 8]);
        context.beginPath(); context.moveTo(Number(gate.x) + 8, Number(gate.gap_center) - Number(gate.gap_half)); context.lineTo(Number(gate.x) + 8, Number(gate.gap_center) + Number(gate.gap_half)); context.stroke();
        context.setLineDash([]);
        context.fillStyle = active ? "#ffdb75" : "rgba(139,224,200,0.5)";
        context.font = "600 10px ui-monospace, monospace";
        context.fillText(`G${index + 1}`, Number(gate.x) - 4, Number(gate.gap_center) - Number(gate.gap_half) - 8);
      });
      const target = state.target || {x: 858, y: 300, radius: 40};
      context.strokeStyle = palette[3];
      context.lineWidth = 3;
      context.beginPath(); context.arc(Number(target.x), Number(target.y), Number(target.radius), 0, Math.PI * 2); context.stroke();
      context.strokeStyle = "rgba(255,255,255,0.55)";
      context.lineWidth = 1;
      context.beginPath(); context.arc(Number(target.x), Number(target.y), Math.max(6, Number(target.radius) - 9), 0, Math.PI * 2); context.stroke();
      context.fillStyle = palette[3]; context.font = "700 11px ui-monospace, monospace"; context.fillText("EXIT", Number(target.x) - 14, Number(target.y) + 4);
      (state.charges || []).forEach((charge) => {
        const x = Number(charge.x); const y = Number(charge.y); const positive = Number(charge.charge) > 0;
        context.strokeStyle = positive ? "rgba(255,219,117,0.27)" : "rgba(207,155,255,0.27)";
        context.lineWidth = 1; context.beginPath(); context.arc(x, y, 25, 0, Math.PI * 2); context.stroke();
        context.fillStyle = positive ? "#ffdb75" : "#cf9bff";
        context.beginPath(); context.arc(x, y, 12, 0, Math.PI * 2); context.fill();
        context.fillStyle = "#0b1730"; context.font = "800 15px ui-monospace, monospace"; context.textAlign = "center"; context.textBaseline = "middle"; context.fillText(positive ? "+" : "−", x, y + 1); context.textAlign = "left"; context.textBaseline = "alphabetic";
      });
      if (model.trail.length > 1) {
        context.lineWidth = 2; context.strokeStyle = "rgba(141,228,204,0.72)"; context.beginPath();
        model.trail.forEach((point, index) => { if (index === 0) context.moveTo(point.x, point.y); else context.lineTo(point.x, point.y); });
        context.stroke();
      }
      const beadColor = model.activePolarity < 0 ? "#cf9bff" : model.activePolarity > 0 ? "#ffdb75" : "#eef7f1";
      context.shadowColor = beadColor; context.shadowBlur = 18; context.fillStyle = beadColor;
      context.beginPath(); context.arc(model.body.x, model.body.y, Number(initial.radius || 10), 0, Math.PI * 2); context.fill(); context.shadowBlur = 0;
      context.fillStyle = "#0b1730"; context.font = "800 12px ui-monospace, monospace"; context.textAlign = "center"; context.textBaseline = "middle"; context.fillText(polarityGlyph(model.activePolarity), model.body.x, model.body.y + 1); context.textAlign = "left"; context.textBaseline = "alphabetic";
      context.fillStyle = "rgba(238,247,241,0.6)"; context.font = "600 11px ui-monospace, monospace"; context.fillText(`vx ${model.body.vx.toFixed(2)} · vy ${model.body.vy.toFixed(2)}`, 18, 22);
    };

    const frame = () => {
      if (!model.submitted) {
        const targetTick = model.startedAt == null ? -1 : Math.min(Number(physics.ticks || 1) - 1, currentTick());
        while (model.lastTick < targetTick) {
          const nextTick = model.lastTick + 1;
          model.lastTick = nextTick;
          const result = stepBody(nextTick);
          if (result) {
            if (result === "passed") {
              updateReadouts(); draw(); submit(true);
              return;
            }
            model.failed = true;
            updateReadouts(); draw(); submit(false, result);
            return;
          }
        }
        if (model.lastTick >= Number(physics.ticks || 1) - 1) {
          model.failed = true; draw(); submit(false, "time expired"); return;
        }
      }
      updateReadouts();
      draw();
      model.raf = requestAnimationFrame(frame);
    };

    const detentFromPointer = (event) => {
      const dial = app.querySelector(".polarity-dial");
      const rect = dial.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
      return ratio < 1 / 3 ? -1 : ratio > 2 / 3 ? 1 : 0;
    };

    app.querySelectorAll(".polarity-button").forEach((button) => {
      button.addEventListener("click", () => setPolarity(Number(button.dataset.polarity), "polarity_button"));
    });
    const dial = app.querySelector(".polarity-dial");
    if (dial) {
      const range = app.querySelector(".polarity-dial-range");
      const restoreDialRange = () => {
        if (range) range.value = String(model.displayPolarity);
      };
      const rejectDialKeyboard = (event) => {
        // The full surface is deliberately a pointer-drag interaction. A
        // native range still emits keyboard events when focused, so guard the
        // browser default as well as the input/change handlers below.
        event.preventDefault();
        event.stopPropagation();
        restoreDialRange();
      };
      const beginDialPointer = (event) => {
        if (event.isPrimary === false || !["mouse", "pen", "touch"].includes(event.pointerType)) return;
        model.dialPointerId = event.pointerId;
        model.dialPointerActive = true;
        model.dialPointerStartX = event.clientX;
        model.dialPointerStartY = event.clientY;
        model.dialDragMoved = false;
        model.dialAcceptedValue = null;
        range.setPointerCapture?.(event.pointerId);
      };
      const moveDialPointer = (event) => {
        if (!model.dialPointerActive || event.pointerId !== model.dialPointerId) return;
        if (Math.hypot(event.clientX - model.dialPointerStartX, event.clientY - model.dialPointerStartY) >= 4) {
          model.dialDragMoved = true;
        }
      };
      const finishDialPointer = (event) => {
        if (event.pointerId !== model.dialPointerId) return;
        // Native range controls dispatch `change` around pointer release in
        // different browser versions. Keep the provenance marker through the
        // current event turn so the guarded change handler can see it.
        window.setTimeout(() => {
          if (model.dialPointerId === event.pointerId) {
            model.dialPointerId = null;
            model.dialPointerActive = false;
            model.dialDragMoved = false;
            model.dialAcceptedValue = null;
            restoreDialRange();
          }
        }, 0);
      };
      const handleDialValue = (event) => {
        const next = Number(event.target.value);
        if (!model.dialPointerActive || !model.dialDragMoved) {
          restoreDialRange();
          return;
        }
        if (model.dialAcceptedValue === next) return;
        model.dialAcceptedValue = next;
        setPolarity(next, "polarity_dial_drag");
      };
      dial.addEventListener("keydown", rejectDialKeyboard);
      range?.addEventListener("keydown", rejectDialKeyboard);
      range?.addEventListener("pointerdown", beginDialPointer);
      range?.addEventListener("pointermove", moveDialPointer);
      range?.addEventListener("pointerup", finishDialPointer);
      range?.addEventListener("pointercancel", finishDialPointer);
      range?.addEventListener("input", handleDialValue);
      range?.addEventListener("change", handleDialValue);
      range?.addEventListener("click", (event) => {
        if (!model.dialDragMoved) {
          event.preventDefault();
          restoreDialRange();
        }
      });
    }

    updateReadouts();
    draw();
    document.body.dataset.mechanic = MECHANIC_ID;
    model.raf = requestAnimationFrame(frame);
  }

  window.WeirdCaptchaMechanics[MECHANIC_ID] = {rootSelector: ".polarity-run-shell", render};
})();
