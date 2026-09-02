(() => {
  "use strict";

  let model = null;
  let cleanup = null;
  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const interaction = () => model.state.control_condition?.interaction || "full";

  function itemById(id) {
    return model.terrarium.modules.find((item) => item.id === id) || null;
  }

  function causalOrder() {
    const links = model.terrarium.runtime_causal_links || [];
    const targets = new Set(links.map((link) => link.target));
    let current = model.terrarium.modules.find((item) => !targets.has(item.id))?.id;
    const order = [];
    while (current && !order.includes(current)) {
      order.push(current);
      current = links.find((link) => link.source === current)?.target;
    }
    return order;
  }

  function predecessor(id) {
    return (model.terrarium.runtime_causal_links || []).find((link) => link.target === id)?.source || null;
  }

  function finalState() {
    const result = {};
    model.terrarium.modules.forEach((item) => {
      const state = model.habitats[item.id];
      result[item.id] = {active: Boolean(state.active), scarred: Boolean(state.scarred), stage: Number(state.stage)};
    });
    return result;
  }

  function stageMarkup(item, state) {
    if (model.parameters.stage_mode === "rings") {
      return `<div class="too-stage-rings" aria-label="growth stage ${state.stage} of 3">${[1, 2, 3].map((stage) => `<i class="${state.stage >= stage ? "is-lit" : ""}"></i>`).join("")}</div>`;
    }
    return `<div class="too-silhouette-meter" aria-label="growth silhouette stage ${state.stage} of 3"><i style="--growth:${state.stage}"></i></div>`;
  }

  function rootLinesMarkup() {
    return (model.terrarium.runtime_causal_links || []).map((link) => {
      const source = itemById(link.source); const target = itemById(link.target);
      const sourceState = model.habitats[source.id]; const targetState = model.habitats[target.id];
      const active = sourceState.active && targetState.active && !sourceState.scarred && !targetState.scarred;
      const pulsing = model.lastPulse?.includes(source.id) && model.lastPulse?.includes(target.id);
      return `<line class="${active ? "is-alive" : ""} ${pulsing ? "is-pulsing" : ""}" x1="${source.habitat.x}" y1="${source.habitat.y}" x2="${target.habitat.x}" y2="${target.habitat.y}"></line>`;
    }).join("");
  }

  function habitatMarkup(item) {
    const state = model.habitats[item.id];
    const active = state.active ? "is-active" : "";
    const scarred = state.scarred ? "is-scarred" : "";
    const growing = model.lastPulse?.includes(item.id) ? "is-growing" : "";
    const echo = model.echo === item.id ? "is-echo" : "";
    return `<article class="too-habitat ${active} ${scarred} ${growing} ${echo}" data-habitat="${esc(item.id)}" style="--x:${item.habitat.x}%;--y:${item.habitat.y}%;--hue:${item.hue};--accent:${item.accent};--stage:${state.stage}">
      <div class="too-organism kind-${esc(item.kind)}"><i></i><i></i><i></i><b>${esc(item.sigil)}</b></div>
      <div class="too-habitat-label"><span>${state.active ? esc(item.name) : `BAY ${item.habitat.bay}`}</span>${stageMarkup(item, state)}</div>
    </article>`;
  }

  function climateMarkup() {
    const totals = [0, 0, 0];
    model.terrarium.modules.forEach((item) => {
      const state = model.habitats[item.id];
      if (!state.active || state.scarred) return;
      item.climate.forEach((value, index) => { totals[index] += value * state.stage; });
    });
    const maximum = Math.max(1, model.terrarium.modules.length * 6);
    const labels = ["HUMID", "SPORE", "LUMEN"];
    return totals.map((value, index) => `<div><span>${labels[index]}</span><i><b style="width:${clamp(12 + (value / maximum) * 86, 4, 100)}%"></b></i></div>`).join("");
  }

  function chamberMarkup() {
    return `<section class="too-chamber" aria-label="living terrarium">
      <div class="too-glass-cap"><span>BIOSPHERE / ${esc(model.terrarium.season)}</span><b>${model.order.length}/${model.terrarium.modules.length} INOCULATED</b></div>
      <div class="too-glass">
        <div class="too-condensation"></div>
        <svg class="too-root-network" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">${rootLinesMarkup()}</svg>
        <div class="too-soil"></div>
        ${model.terrarium.modules.map(habitatMarkup).join("")}
        <div id="too-hatch" class="too-hatch" aria-label="terrarium capsule delivery hatch"><i></i><b>INOCULATION HATCH</b><span>DROP CAPSULE</span></div>
      </div>
      <div class="too-climate">${climateMarkup()}</div>
    </section>`;
  }

  function capsuleMarkup(item) {
    const used = model.habitats[item.id].active;
    const echo = model.echo === item.id && model.parameters.echo_mode !== "sigil" ? "is-echo" : "";
    const controls = interaction() === "simplified"
      ? `<button data-proxy-add="${esc(item.id)}" ${used || model.busy ? "disabled" : ""}>INOCULATE</button>`
      : `<small>${used ? "DELIVERED" : "DRAG TO HATCH"}</small>`;
    return `<article class="too-capsule ${used ? "is-used" : ""} ${echo}" data-capsule="${esc(item.id)}" style="--hue:${item.hue};--accent:${item.accent}" aria-label="${esc(item.name)} capsule">
      <div class="too-vial"><i></i><b>${esc(item.sigil)}</b></div>
      <div class="too-capsule-copy"><strong>${esc(item.name)}</strong><span>${esc(item.kind.toUpperCase())} CULTURE</span>${controls}</div>
    </article>`;
  }

  function orderMarkup() {
    const slots = Array.from({length: model.terrarium.modules.length}, (_, index) => {
      const id = model.order[index]; const item = id ? itemById(id) : null;
      return `<i class="${item ? "is-filled" : ""}" style="${item ? `--hue:${item.hue}` : ""}">${item ? esc(item.sigil) : index + 1}</i>`;
    }).join("");
    return `<div class="too-order"><span>RUN ORDER</span><div>${slots}</div></div>`;
  }

  function trayMarkup() {
    const modules = model.terrarium.tray_order.map(itemById);
    return `<aside class="too-rack">
      <header><div><small>CRYOBANK / RACK 03</small><h2>INOCULATION CAPSULES</h2></div><b>${interaction().toUpperCase()}</b></header>
      <div class="too-rack-grid">${modules.map(capsuleMarkup).join("")}</div>
      ${orderMarkup()}
      <div class="too-attempt-stats"><span>ATTEMPT <b>${model.attempt}</b></span><span>BEST BLOOM <b>${model.best}/${model.terrarium.modules.length}</b></span></div>
    </aside>`;
  }

  function echoMessage(required) {
    if (!required) return "";
    const item = itemById(required);
    if (model.parameters.echo_mode === "named") return `ROOT ECHO · ${item.name} WAS NEEDED EARLIER`;
    if (model.parameters.echo_mode === "sigil") return `ROOT ECHO · MATCH PRECURSOR ${item.sigil}`;
    return `ROOT ECHO · A PRECURSOR ANSWERED FROM THE RACK`;
  }

  function outcomeMarkup() {
    if (model.serverFailure) return `<div class="too-verdict is-fail"><small>SERVER REPLAY REJECTED</small><b>FAIL</b><span>NEW SPECIMEN LOADED</span></div>`;
    if (model.passed) return `<div class="too-verdict is-pass"><small>CAUSAL REPLAY ACCEPTED</small><b>PASS</b><span>ALL HABITATS MAX</span></div>`;
    if (model.ready) return `<div class="too-verdict is-ready"><small>FINAL CASCADE STABLE</small><b>FULL BLOOM</b><span>CERTIFICATION READY</span></div>`;
    if (model.failed) return `<div class="too-verdict is-fail"><small>FINAL CASCADE STALLED</small><b>WILTED RUN</b><span>RETRY THE SAME WORLD</span></div>`;
    return "";
  }

  function renderSurface() {
    const root = document.querySelector(".terrarium-order");
    if (!root) return;
    root.querySelector(".too-workbench").innerHTML = chamberMarkup() + trayMarkup();
    const certifyAllowed = (model.ready || model.failed) && !model.busy && !model.submitting;
    const status = model.passed ? "passed" : model.serverFailure || model.failed ? "error" : model.submitting ? "pending" : "idle";
    root.querySelector(".too-status").innerHTML = `<div class="readout" data-status="${status}"><small>LIVE ROOT TRACE</small><b>${esc(model.message)}</b></div><button id="too-reset" ${model.order.length === 0 || model.ready || model.passed ? "disabled" : ""}>${model.failed ? "RETRY SAME WORLD" : "RESET RUN"}</button><button id="too-certify" ${certifyAllowed ? "" : "disabled"}>${model.failed ? "SEAL FAILED RUN" : "CERTIFY ECOSYSTEM"}</button>`;
    root.querySelector(".too-verdict-layer").innerHTML = outcomeMarkup();
    bindControls();
  }

  function resetAttempt() {
    if (!model || model.passed || model.ready) return;
    const maxed = Object.values(model.habitats).filter((state) => state.stage === 3 && !state.scarred).length;
    model.best = Math.max(model.best, maxed);
    model.attempt += 1;
    model.order = [];
    model.events = [];
    model.echoesUsed = 0;
    model.echo = null;
    model.lastPulse = [];
    model.failed = false;
    model.ready = false;
    model.message = "SAME WORLD · RUN CLEARED · DEPENDENCIES UNCHANGED";
    model.terrarium.modules.forEach((item) => { model.habitats[item.id] = {active: false, scarred: false, stage: 0}; });
    renderSurface();
  }

  function inoculate(moduleId, inputSource, gesture = null) {
    if (!model || model.busy || model.failed || model.ready || model.passed || model.habitats[moduleId]?.active) return;
    model.serverFailure = false;
    const required = predecessor(moduleId);
    const healthyPredecessor = !required || (model.habitats[required].active && !model.habitats[required].scarred);
    const scarred = !healthyPredecessor;
    model.habitats[moduleId] = {active: true, scarred, stage: 0};
    model.order.push(moduleId);
    const cascade = [];
    causalOrder().forEach((id) => {
      const state = model.habitats[id];
      if (!state.active || state.scarred) return;
      const before = state.stage; const after = Math.min(2, before + 1);
      state.stage = after;
      if (before !== after) cascade.push({module_id: id, before, after});
    });
    const clueShown = Boolean(scarred && model.echoesUsed < model.parameters.echo_budget);
    const echoModuleId = clueShown ? required : null;
    if (clueShown) { model.echoesUsed += 1; model.echo = required; }
    const finalCascade = [];
    if (model.order.length === model.terrarium.modules.length) {
      causalOrder().forEach((id) => {
        const state = model.habitats[id];
        if (!state.active || state.scarred) return;
        const before = state.stage; state.stage = 3;
        if (before !== 3) finalCascade.push({module_id: id, before, after: 3});
      });
    }
    const result = {scarred, clue_shown: clueShown, echo_module_id: echoModuleId, cascade, final_cascade: finalCascade};
    model.events.push({sequence: model.events.length + 1, type: "inoculate", module_id: moduleId, input_source: inputSource, ...(gesture ? {gesture} : {}), result});
    model.lastPulse = [...new Set([...cascade, ...finalCascade].map((item) => item.module_id))];
    const item = itemById(moduleId);
    model.message = scarred ? (clueShown ? echoMessage(required) : `${item.name.toUpperCase()} STALLED · NO ECHO REMAINS THIS RUN`) : `${item.name.toUpperCase()} ROOTED · CASCADE ${model.order.length}`;
    if (model.order.length === model.terrarium.modules.length) {
      const allMax = Object.values(model.habitats).every((state) => state.active && !state.scarred && state.stage === 3);
      model.ready = allMax; model.failed = !allMax;
      model.best = Math.max(model.best, Object.values(model.habitats).filter((state) => state.stage === 3 && !state.scarred).length);
      model.message = allMax ? "EVERY HABITAT REACHED FULL BLOOM · CERTIFY THE RUN" : "CASCADE STALLED · COMPARE THE SCARRED HABITATS AND RETRY";
    }
    model.busy = true;
    renderSurface();
    const current = model;
    current.timers.push(setTimeout(() => {
      if (model !== current) return;
      current.busy = false; current.lastPulse = [];
      if (current.parameters.echo_mode === "transient") current.echo = null;
      renderSurface();
    }, current.parameters.cascade_ms));
  }

  function bindFullDrags() {
    document.querySelectorAll(".too-capsule:not(.is-used)").forEach((capsule) => {
      let drag = null;
      capsule.addEventListener("pointerdown", (event) => {
        if (event.button !== 0 || model.busy) return;
        event.preventDefault();
        const rect = capsule.getBoundingClientRect();
        drag = {pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, lastX: event.clientX, lastY: event.clientY, travel: 0, samples: 0, rect};
        capsule.classList.add("is-dragging"); capsule.setPointerCapture?.(event.pointerId);
      });
      capsule.addEventListener("pointermove", (event) => {
        if (!drag || event.pointerId !== drag.pointerId) return;
        drag.travel += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY);
        drag.lastX = event.clientX; drag.lastY = event.clientY; drag.samples += 1;
        capsule.style.transform = `translate(${event.clientX - drag.startX}px, ${event.clientY - drag.startY}px) rotate(-2deg)`;
      });
      const finish = (event) => {
        if (!drag || event.pointerId !== drag.pointerId) return;
        drag.travel += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY); drag.samples += 1;
        const hatch = document.getElementById("too-hatch"); const hatchRect = hatch?.getBoundingClientRect();
        const inside = hatchRect && event.clientX >= hatchRect.left && event.clientX <= hatchRect.right && event.clientY >= hatchRect.top && event.clientY <= hatchRect.bottom;
        const proof = inside ? {
          start_u: Number(clamp((drag.startX - drag.rect.left) / drag.rect.width, 0, 1).toFixed(6)),
          start_v: Number(clamp((drag.startY - drag.rect.top) / drag.rect.height, 0, 1).toFixed(6)),
          end_u: Number(clamp((event.clientX - hatchRect.left) / hatchRect.width, 0, 1).toFixed(6)),
          end_v: Number(clamp((event.clientY - hatchRect.top) / hatchRect.height, 0, 1).toFixed(6)),
          travel_px: Number(drag.travel.toFixed(3)), sample_count: drag.samples,
        } : null;
        capsule.classList.remove("is-dragging"); capsule.style.transform = ""; drag = null;
        if (inside && proof && proof.travel_px >= 80 && proof.sample_count >= 1) inoculate(capsule.dataset.capsule, "direct_capsule_drag", proof);
      };
      capsule.addEventListener("pointerup", finish);
      capsule.addEventListener("pointercancel", () => { capsule.classList.remove("is-dragging"); capsule.style.transform = ""; drag = null; });
    });
  }

  function bindControls() {
    document.getElementById("too-reset")?.addEventListener("click", resetAttempt);
    document.getElementById("too-certify")?.addEventListener("click", submit);
    if (interaction() === "simplified") {
      document.querySelectorAll("[data-proxy-add]").forEach((button) => button.addEventListener("click", () => inoculate(button.dataset.proxyAdd, "tray_inoculate_button")));
    } else bindFullDrags();
  }

  async function submit() {
    if (!model || (!model.ready && !model.failed) || model.busy || model.submitting || model.passed) return;
    const current = model; current.submitting = true; current.message = "SERVER REPLAYING THE CAUSAL TRANSCRIPT…"; renderSurface();
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({
        mechanic_id: current.state.mechanic_id, task_id: current.state.task_id, challenge_id: current.state.challenge_id,
        interaction_mode: interaction(), events: current.events, order: current.order, final_state: finalState(), completed: current.ready,
      })});
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.passed = true; current.submitting = false; current.message = "PASS · INDEPENDENT CAUSAL REPLAY ACCEPTED"; current.helpers.setReadout("PASS", "passed"); renderSurface();
      } else if (outcome.passed === false && outcome.state) {
        const helpers = current.helpers; await render(outcome.state, helpers, {serverFailure: true}); model.helpers.setReadout("FAIL", "error");
      } else {
        current.submitting = false; current.message = "CERTIFICATION REJECTED"; current.helpers.setReadout("FAIL", "error"); renderSurface();
      }
    } catch (_error) {
      if (model === current) { current.submitting = false; current.message = "CERTIFICATION LINK OFFLINE"; current.helpers.setReadout("FAIL", "error"); renderSurface(); }
    }
  }

  async function render(state, helpers, options = {}) {
    cleanup?.();
    document.body.dataset.mechanic = "terrarium-order-of-operations";
    const habitats = {};
    state.terrarium.modules.forEach((item) => { habitats[item.id] = {active: false, scarred: false, stage: 0}; });
    model = {
      state, helpers, terrarium: JSON.parse(JSON.stringify(state.terrarium)), parameters: JSON.parse(JSON.stringify(state.parameters)),
      habitats, order: [], events: [], attempt: 1, best: 0, echoesUsed: 0, echo: null, lastPulse: [], timers: [],
      message: options.serverFailure ? "SERVER REJECTED THE PRIOR TRANSCRIPT · NEW SPECIMEN READY" : "OBSERVE EACH CASCADE · RETRIES KEEP THIS WORLD",
      busy: false, failed: false, ready: false, passed: false, submitting: false, serverFailure: Boolean(options.serverFailure),
    };
    helpers.app.innerHTML = `<section class="terrarium-order mode-${interaction()} stage-${esc(model.parameters.stage_mode)}" data-interaction="${interaction()}" data-mechanic="${esc(state.mechanic_id)}" data-challenge-id="${esc(state.challenge_id)}" data-fresh-failure="${options.serverFailure ? "true" : "false"}">
      <header class="too-masthead"><div><small>WARDIAN RESEARCH STATION · CAUSAL CULTURE 07</small><h1>${esc(state.prompt)}</h1></div><div class="too-mode"><i></i><span>${interaction().toUpperCase()} INPUT</span><b>D${state.control_condition?.difficulty || 3} · ${state.terrarium.season}</b></div></header>
      <main class="too-workbench"></main>
      <footer class="too-status"></footer>
      <div class="too-verdict-layer"></div>
      ${helpers.cheatPanelTemplate()}
    </section>`;
    renderSurface(); helpers.installCheatPanel();
    cleanup = () => { if (model) model.timers.forEach((timer) => clearTimeout(timer)); };
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.terrarium_order_of_operations = {rootSelector: ".terrarium-order", render};
})();
