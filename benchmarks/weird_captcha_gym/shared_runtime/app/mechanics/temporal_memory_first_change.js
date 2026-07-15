(() => {
  "use strict";

  let model = null;
  const palette = ["#66d6ff", "#ff8d66", "#d8ff58", "#d889ff", "#ffd25a", "#7de3ad", "#f484c5", "#8aa7ff", "#f7a95e"];
  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");

  function record(kind, details = {}) {
    if (model.events.length >= 480) return;
    model.events.push({sequence: model.events.length + 1, kind, ...details});
  }

  function movingPosition(object, elapsed) {
    return [
      object.x0 + Math.sin(object.phase + elapsed * object.rate_x) * object.amp_x,
      object.y0 + Math.cos(object.phase * .83 + elapsed * object.rate_y) * object.amp_y,
    ];
  }

  function settledPosition(object) {
    const timeline = model.state.timeline;
    const index = timeline.settle_order.indexOf(object.id);
    const grid = timeline.settle_grid;
    return [grid.x0 + (index % grid.columns) * grid.dx, grid.y0 + Math.floor(index / grid.columns) * grid.dy];
  }

  function position(object, elapsed, settled = false) {
    return settled ? settledPosition(object) : movingPosition(object, elapsed);
  }

  function activeEvent(objectId, elapsed) {
    return model.state.timeline.events.find((event) => event.object_id === objectId && elapsed >= event.at_ms && elapsed <= event.at_ms + event.duration_ms);
  }

  function drawChangedGlyph(context, object, event) {
    context.save();
    if (event.effect === "quarter-turn") context.rotate(Math.PI / 2);
    if (event.effect === "mirror") context.scale(-1, 1);
    context.fillText(event.effect === "invert" ? "●" : object.glyph, 0, 1);
    if (event.effect === "split") {
      context.globalAlpha = .6;
      context.fillText(object.glyph, 8, -5);
    }
    if (event.effect === "blink") {
      context.strokeStyle = "#071015";
      context.lineWidth = 3;
      context.beginPath();
      context.moveTo(-12, 0);
      context.lineTo(12, 0);
      context.stroke();
    }
    context.restore();
  }

  function maybeRecordObservation(timelineMs, settled) {
    if (!model.lens || settled || !["live", "review"].includes(model.phase)) return;
    const now = performance.now();
    if (now - model.lastObservationAt < 145) return;
    model.lastObservationAt = now;
    record("observe", {
      mode: model.phase,
      timeline_ms: Math.round(timelineMs),
      cursor: [Number(model.lens[0].toFixed(2)), Number(model.lens[1].toFixed(2))],
    });
  }

  function draw() {
    if (!model) return;
    const canvas = document.querySelector(".tracking-canvas");
    if (!canvas) return;
    const context = canvas.getContext("2d");
    const timeline = model.state.timeline;
    if (model.phase === "live") {
      model.timelineMs = Math.min(timeline.settle_ms, performance.now() - model.startedAt);
      if (model.timelineMs >= timeline.settle_ms) {
        model.phase = "review";
        model.timelineMs = 0;
        model.reviewMs = 0;
        document.querySelector(".tracking-stage").dataset.phase = "review";
        document.querySelector(".tracking-review").dataset.visible = "true";
        document.querySelector(".tracking-return").disabled = false;
      }
    } else if (model.phase === "review") {
      model.timelineMs = model.reviewMs;
    } else if (model.phase === "select" || model.phase === "submitting" || model.phase === "pass") {
      model.timelineMs = timeline.settle_ms;
    } else {
      model.timelineMs = 0;
    }
    const settled = ["select", "submitting", "pass"].includes(model.phase);
    const elapsed = model.timelineMs;

    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "#07131a";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.strokeStyle = "rgba(125,193,210,.08)";
    for (let x = 0; x < canvas.width; x += 35) {
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x - 55, canvas.height);
      context.stroke();
    }
    timeline.objects.forEach((object, index) => {
      const [x, y] = position(object, elapsed, settled);
      const inside = model.lens && Math.hypot(model.lens[0] - x, model.lens[1] - y) <= timeline.lens_radius;
      const event = settled ? null : activeEvent(object.id, elapsed);
      context.save();
      context.translate(x, y);
      context.fillStyle = inside ? palette[index % palette.length] : "#14242b";
      context.strokeStyle = event && inside ? "#ffffff" : "#4c6873";
      context.lineWidth = event && inside ? 5 : 2;
      context.beginPath();
      context.arc(0, 0, event && inside ? 28 : 22, 0, Math.PI * 2);
      context.fill();
      context.stroke();
      if (inside) {
        context.fillStyle = "#071015";
        context.font = "700 21px Georgia,serif";
        context.textAlign = "center";
        context.textBaseline = "middle";
        if (event) drawChangedGlyph(context, object, event);
        else context.fillText(object.glyph, 0, 1);
      }
      context.restore();
    });
    if (!settled) {
      timeline.occluders.forEach(([left, right]) => {
        context.fillStyle = "rgba(3,7,9,.95)";
        context.fillRect(left, 0, right - left, canvas.height);
        context.strokeStyle = "#304750";
        context.strokeRect(left, 0, right - left, canvas.height);
      });
    }
    if (model.lens) {
      const gradient = context.createRadialGradient(model.lens[0], model.lens[1], timeline.lens_radius * .45, model.lens[0], model.lens[1], timeline.lens_radius);
      gradient.addColorStop(0, "rgba(102,214,255,.04)");
      gradient.addColorStop(1, "rgba(102,214,255,.22)");
      context.fillStyle = gradient;
      context.beginPath();
      context.arc(model.lens[0], model.lens[1], timeline.lens_radius, 0, Math.PI * 2);
      context.fill();
      context.strokeStyle = "#66d6ff";
      context.lineWidth = 1.5;
      context.stroke();
    }
    maybeRecordObservation(elapsed, settled);
    const status = document.querySelector(".tracking-status");
    if (status) status.textContent = model.phase === "ready" ? "FIELD SAFE" : model.phase === "live" ? "LIVE / ONE SHOT" : model.phase === "review" ? `REVIEW ${Number(elapsed / 1000).toFixed(2)}s` : "SETTLED / MARK IDENTITY";
    model.raf = requestAnimationFrame(draw);
  }

  async function select(event) {
    if (model.phase !== "select" || model.submitting) return;
    const canvas = event.currentTarget;
    const rect = canvas.getBoundingClientRect();
    const point = [(event.clientX - rect.left) / rect.width * canvas.width, (event.clientY - rect.top) / rect.height * canvas.height];
    let best = null;
    let distance = Infinity;
    model.state.timeline.objects.forEach((object) => {
      const candidate = settledPosition(object);
      const candidateDistance = Math.hypot(point[0] - candidate[0], point[1] - candidate[1]);
      if (candidateDistance < distance) {
        distance = candidateDistance;
        best = object;
      }
    });
    if (!best || distance > 38) return;
    model.submitting = true;
    model.phase = "submitting";
    record("select", {selected_object_id: best.id, point: point.map((value) => Number(value.toFixed(2)))});
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({
          mechanic_id: model.state.mechanic_id,
          challenge_id: model.state.challenge_id,
          selected_object_id: best.id,
          events: model.events,
        }),
      });
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.phase = "pass";
        model.helpers.setReadout("PASS", "passed");
        document.querySelector(".tracking-captcha").classList.add("is-passed");
      } else {
        model.helpers.setReadout("FAIL", "error");
        window.setTimeout(() => outcome.state && model.helpers.render(outcome.state), 850);
      }
    } catch (_error) {
      model.submitting = false;
      model.phase = "select";
      model.helpers.setReadout("FAIL", "error");
    }
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "first-change-tracking-v3";
    if (model?.raf) cancelAnimationFrame(model.raf);
    model = {
      state,
      helpers,
      phase: "ready",
      startedAt: 0,
      timelineMs: 0,
      reviewMs: 0,
      lens: null,
      raf: 0,
      submitting: false,
      events: [],
      lastObservationAt: 0,
    };
    const timeline = state.timeline;
    helpers.app.innerHTML = `<section class="tracking-captcha">
      <header><div><span>TRANSIENT IDENTITY FIELD / FORENSIC SPOOL</span><h1>${esc(state.prompt)}</h1></div><b class="tracking-status">FIELD SAFE</b></header>
      <section class="tracking-stage" data-phase="ready"><canvas class="tracking-canvas" width="700" height="330"></canvas><button class="tracking-arm" type="button">RUN FIELD ONCE</button></section>
      <section class="tracking-review" data-visible="false"><div class="tracking-spikes">${timeline.events.map((item) => `<i style="left:${item.at_ms / timeline.review_end_ms * 100}%"></i>`).join("")}</div><input class="tracking-spool" type="range" min="0" max="${timeline.review_end_ms}" step="${timeline.review_step_ms}" value="0" aria-label="recorded field time"><button class="tracking-return" type="button" disabled>RETURN TO SETTLED FIELD</button></section>
      <footer><div class="readout" data-status="idle"></div><span>SCRUB THE DISTURBANCE TRACE · THE LENS REVEALS IDENTITY</span><i></i></footer>
    </section>`;
    const canvas = document.querySelector(".tracking-canvas");
    canvas.addEventListener("pointermove", (event) => {
      const rect = canvas.getBoundingClientRect();
      model.lens = [(event.clientX - rect.left) / rect.width * canvas.width, (event.clientY - rect.top) / rect.height * canvas.height];
    });
    canvas.addEventListener("pointerleave", () => { model.lens = null; });
    canvas.addEventListener("click", select);
    document.querySelector(".tracking-arm").addEventListener("click", (event) => {
      model.phase = "live";
      model.startedAt = performance.now();
      model.lens = null;
      record("arm");
      document.querySelector(".tracking-stage").dataset.phase = "live";
      event.currentTarget.remove();
      helpers.setReadout("", "idle");
    });
    document.querySelector(".tracking-spool").addEventListener("input", (event) => {
      if (model.phase === "live") return;
      model.phase = "review";
      model.reviewMs = Number(event.currentTarget.value);
      document.querySelector(".tracking-stage").dataset.phase = "review";
    });
    document.querySelector(".tracking-return").addEventListener("click", () => {
      model.phase = "select";
      model.lens = null;
      document.querySelector(".tracking-stage").dataset.phase = "select";
      record("return_settled");
    });
    draw();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.temporal_memory_first_change = {render, rootSelector: ".tracking-captcha"};
})();
