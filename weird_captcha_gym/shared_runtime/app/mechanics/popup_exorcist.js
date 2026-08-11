(() => {
  "use strict";

  let model = null;
  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
  const COPY = {
    update: ["OPTIONAL UPDATE", "A component may be available."],
    coupon: ["BONUS WINDOW", "Terms continue elsewhere."],
    cleaner: ["DESKTOP CARE", "Several pixels require attention."],
    forecast: ["LOCAL FORECAST", "A strong chance of more windows."],
    player: ["MEDIA HELPER", "Playback has not been requested."],
    survey: ["ONE QUESTION", "Closing is also an answer."],
    prize: ["CLAIM PENDING", "No prize was actually described."],
  };

  function record(kind, details = {}) {
    const event = {sequence: model.events.length + 1, kind, ...details};
    model.events.push(event);
    return event;
  }

  function windowMarkup(item, infected = false) {
    const copy = COPY[item.theme] || COPY.update;
    const cue = item.anomaly_cue || "none";
    const stageIndex = Number(item.stage_index || 0);
    const stageClass = stageIndex > 0 ? "is-awaiting-stage" : "";
    const cueText = cue === "explicit" ? '<em class="anomaly-label">UNSTABLE PROCESS</em>' : "";
    return `<article class="parasite-window theme-${esc(item.theme)} ${infected ? "is-infected" : ""} ${stageClass}" data-window-id="${esc(item.id)}" data-behavior="${esc(item.runtime_behavior || "echo")}" data-strain-id="${esc(item.strain_id || "")}" data-stage-index="${stageIndex}" data-cue="${esc(cue)}" style="left:${item.x}px;top:${item.y}px;width:${item.w}px;height:${item.h}px;z-index:${item.z}">
      <header><i></i><span>${esc(item.title)}</span><button type="button" class="parasite-close" aria-label="Close">×</button></header>
      <div class="parasite-body"><b>${esc(copy[0])}</b><p>${esc(copy[1])}</p>${cueText}<div class="fake-progress"><i></i></div></div>
    </article>`;
  }

  function liveWindows() {
    return Array.from(document.querySelectorAll(
      ".parasite-window:not(.is-dead):not(.is-awaiting-stage)",
    ));
  }

  function updateCount() {
    const node = document.querySelector(".parasite-count b");
    if (node) node.textContent = String(liveWindows().length);
  }

  function selectedWindow() {
    if (!model.selectedId) return null;
    return document.querySelector(`.parasite-window[data-window-id="${CSS.escape(model.selectedId)}"]:not(.is-dead)`);
  }

  function updateControls() {
    document.querySelectorAll(".parasite-window").forEach((node) => {
      node.dataset.selected = String(node.dataset.windowId === model.selectedId && !node.classList.contains("is-dead"));
    });
    const selected = selectedWindow();
    const status = document.querySelector(".popup-selection-status");
    if (status) status.textContent = selected ? "WINDOW SELECTED" : "SELECT A VISIBLE WINDOW";
    const close = document.querySelector(".popup-close-selected");
    const contain = document.querySelector(".popup-contain-selected");
    if (close) close.disabled = !selected;
    if (contain) contain.disabled = !selected || model.provokedParents.size === 0;
  }

  function focus(node, inputSource) {
    if (
      !node
      || node.classList.contains("is-dead")
      || node.classList.contains("is-awaiting-stage")
    ) return;
    node.style.zIndex = String(++model.topZ);
    model.selectedId = node.dataset.windowId;
    record("focus", {window_id: node.dataset.windowId, input_source: inputSource});
    updateControls();
  }

  function updateFieldSignal() {
    const signal = document.querySelector(".field-signal");
    if (!signal) return;
    if (model.provokedParents.size === 0) {
      signal.textContent = "CONTAINMENT FIELD: DORMANT";
      return;
    }
    const progress = model.parents.length > 1
      ? ` · STRAINS ${model.containedParents.size}/${model.parents.length}`
      : "";
    signal.textContent = `CONTAINMENT FIELD: RESONANT${progress}`;
  }

  function updateResistance() {
    const readout = document.querySelector(".resistance-count");
    if (readout) readout.textContent = `${model.strikes}/${model.maximumResistanceStrikes}`;
  }

  function setContainmentStage(index) {
    const stage = model.containmentStages[Math.min(index, model.containmentStages.length - 1)];
    const well = document.querySelector(".containment-well");
    well.dataset.stageIndex = String(index);
    well.style.left = `${stage.x}px`;
    well.style.top = `${stage.y}px`;
    well.style.width = `${stage.w}px`;
    well.style.height = `${stage.h}px`;
  }

  function activateStage(index) {
    const ids = model.stageBatches[index] || [];
    ids.forEach((id) => {
      const node = document.querySelector(
        `.parasite-window[data-window-id="${CSS.escape(id)}"]`,
      );
      if (!node) return;
      node.classList.remove("is-awaiting-stage");
      node.classList.add("is-arriving");
      node.style.zIndex = String(++model.topZ);
      setTimeout(() => node.classList.remove("is-arriving"), 320);
    });
    record("stage", {
      stage_index: index,
      activated_ids: [...ids],
      input_source: "containment_field",
    });
    model.activeStage = index;
    const root = document.querySelector(".parasite-captcha");
    if (root) root.dataset.activeStage = String(index);
    setContainmentStage(index);
    updateCount();
    updateControls();
  }

  function activateContainment() {
    document.querySelector(".containment-well").dataset.active = "true";
    document.querySelector(".popup-field").classList.add("is-contaminated");
    updateFieldSignal();
    updateControls();
  }

  async function failDesktop() {
    if (model.submitting) return;
    model.submitting = true;
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({
          mechanic_id: model.state.mechanic_id,
          task_id: model.state.task_id,
          challenge_id: model.state.challenge_id,
          events: model.events,
        }),
      });
      const outcome = await response.json();
      model.helpers.setReadout("FAIL", "error");
      setTimeout(() => outcome.state && model.helpers.render(outcome.state), 850);
    } catch (_error) {
      model.submitting = false;
      model.helpers.setReadout("FAIL", "error");
    }
  }

  function spawnEchoes(parent) {
    const field = document.querySelector(".popup-field");
    const parentId = parent.dataset.windowId;
    const echoIds = model.infectionGroups[parentId] || [];
    const base = {
      x: parseFloat(parent.style.left),
      y: parseFloat(parent.style.top),
      w: parent.offsetWidth,
      h: parent.offsetHeight,
      theme: parent.dataset.theme || "update",
      title: "DESKTOP MESSAGE",
    };
    echoIds.forEach((id, index) => {
      const horizontal = index % 2 ? 74 + Math.floor(index / 2) * 22 : -58 - Math.floor(index / 2) * 18;
      const item = {
        ...base,
        id,
        strain_id: parentId,
        x: Math.max(8, Math.min(690 - base.w, base.x + horizontal)),
        y: Math.max(10, Math.min(365 - base.h, base.y + 54 + index * 22)),
        z: ++model.topZ,
        runtime_behavior: "echo",
      };
      field.insertAdjacentHTML("beforeend", windowMarkup(item, true));
      const node = field.querySelector(`[data-window-id="${CSS.escape(id)}"]`);
      installWindow(node);
    });
    record("spawn", {
      parent_id: parentId,
      echo_ids: [...echoIds],
      input_source: "parasite_replication",
    });
    updateCount();
    updateControls();
  }

  async function submit(containedId) {
    if (model.submitting) return;
    model.submitting = true;
    record("purge", {
      contained_id: containedId,
      remaining_before: liveWindows().map((node) => node.dataset.windowId),
      input_source: "containment_field",
    });
    document.querySelector(".popup-field").classList.add("is-purging");
    liveWindows().forEach((node, index) => setTimeout(() => node.classList.add("is-dead"), index * 75));
    setTimeout(updateCount, 650);
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({
          mechanic_id: model.state.mechanic_id,
          task_id: model.state.task_id,
          challenge_id: model.state.challenge_id,
          events: model.events,
        }),
      });
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.helpers.setReadout("PASS", "passed");
        document.querySelector(".parasite-captcha").classList.add("is-passed");
      } else {
        model.helpers.setReadout("FAIL", "error");
        setTimeout(() => outcome.state && model.helpers.render(outcome.state), 850);
      }
    } catch (_error) {
      model.submitting = false;
      model.helpers.setReadout("FAIL", "error");
    }
  }

  function tryContain(node, inputSource) {
    if (model.provokedParents.size === 0 || !node.classList.contains("is-infected")) return false;
    const parentId = node.dataset.strainId || node.dataset.windowId;
    const activeParent = model.parents[model.containedParents.size];
    if (
      parentId !== activeParent
      || !model.provokedParents.has(parentId)
      || model.containedParents.has(parentId)
    ) return false;
    const well = document.querySelector(".containment-well").getBoundingClientRect();
    const rect = node.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    if (cx < well.left || cx > well.right || cy < well.top || cy > well.bottom) return false;
    record("contain", {window_id: node.dataset.windowId, input_source: inputSource});
    node.classList.add("is-contained");
    model.containedParents.add(parentId);
    const complete = model.containedParents.size === model.parents.length;
    if (complete) {
      updateFieldSignal();
      submit(node.dataset.windowId);
      return true;
    }
    const completedBatch = new Set(
      model.stageBatches[model.containedParents.size - 1] || [],
    );
    document.querySelectorAll(".parasite-window").forEach((candidate) => {
      const strainId = candidate.dataset.strainId || candidate.dataset.windowId;
      if (strainId === parentId || completedBatch.has(candidate.dataset.windowId)) {
        candidate.classList.remove("is-contained");
        candidate.classList.add("is-dead");
      }
    });
    model.selectedId = null;
    activateStage(model.containedParents.size);
    model.helpers.setReadout(`STRAIN ${model.containedParents.size}/${model.parents.length} CONTAINED`, "active");
    updateCount();
    updateFieldSignal();
    updateControls();
    return true;
  }

  function performClose(node, inputSource) {
    if (!node || model.submitting || node.classList.contains("is-dead")) return;
    focus(node, inputSource === "window_close_button" ? "window_pointer" : "window_select");
    const behavior = node.dataset.behavior;
    const parentId = node.dataset.strainId || node.dataset.windowId;
    record("close", {window_id: node.dataset.windowId, input_source: inputSource});
    if (behavior === "replicate" && !model.provokedParents.has(parentId)) {
      if (parentId !== model.parents[model.containedParents.size]) return;
      model.provokedParents.add(parentId);
      node.classList.add("is-infected");
      activateContainment();
      spawnEchoes(node);
      return;
    }
    if (node.classList.contains("is-infected")) {
      node.classList.remove("pulse");
      void node.offsetWidth;
      node.classList.add("pulse");
      model.strikes += 1;
      record("resist", {
        window_id: node.dataset.windowId,
        strike: model.strikes,
        input_source: inputSource,
      });
      updateResistance();
      if (model.strikes >= Number(model.state.maximum_resistance_strikes || 3)) failDesktop();
      return;
    }
    node.classList.add("is-dead");
    if (model.selectedId === node.dataset.windowId) model.selectedId = null;
    updateCount();
    updateControls();
  }

  function performContainProxy(node) {
    if (!node || model.submitting || model.provokedParents.size === 0) return;
    focus(node, "window_select");
    const well = model.containmentStages[model.containedParents.size];
    const origin = [parseFloat(node.style.left), parseFloat(node.style.top)];
    const target = [
      Math.max(0, Math.min(700 - node.offsetWidth, well.x + well.w / 2 - node.offsetWidth / 2)),
      Math.max(0, Math.min(390 - node.offsetHeight, well.y + well.h / 2 - node.offsetHeight / 2)),
    ];
    const samples = Array.from({length: 13}, (_, index) => {
      const amount = index / 12;
      return [
        Math.round(origin[0] + (target[0] - origin[0]) * amount),
        Math.round(origin[1] + (target[1] - origin[1]) * amount),
      ];
    });
    node.style.left = `${target[0]}px`;
    node.style.top = `${target[1]}px`;
    record("drag", {
      window_id: node.dataset.windowId,
      samples,
      input_source: "selected_contain_button",
    });
    tryContain(node, "selected_contain_button");
  }

  function installWindow(node) {
    if (!node) return;
    node.dataset.theme = node.className.match(/theme-([^ ]+)/)?.[1] || "update";
    if (node.dataset.behavior === "replicate" && !node.dataset.strainId) {
      node.dataset.strainId = node.dataset.windowId;
    }
    node.dataset.selected = "false";
    node.addEventListener("pointerdown", (event) => {
      if (event.target.closest("button")) return;
      focus(node, model.interaction === "full" ? "window_pointer" : "window_select");
    });
    const header = node.querySelector("header");
    if (model.interaction === "full") {
      header.addEventListener("pointerdown", (event) => {
        if (event.target.closest("button")) return;
        event.preventDefault();
        header.setPointerCapture(event.pointerId);
        const start = [event.clientX, event.clientY];
        const origin = [parseFloat(node.style.left), parseFloat(node.style.top)];
        const samples = [[Math.round(origin[0]), Math.round(origin[1])]];
        const move = (moveEvent) => {
          const x = Math.max(0, Math.min(700 - node.offsetWidth, origin[0] + moveEvent.clientX - start[0]));
          const y = Math.max(0, Math.min(390 - node.offsetHeight, origin[1] + moveEvent.clientY - start[1]));
          node.style.left = `${x}px`;
          node.style.top = `${y}px`;
          const target = [Math.round(x), Math.round(y)];
          const previous = samples[samples.length - 1];
          const distance = Math.hypot(target[0] - previous[0], target[1] - previous[1]);
          const steps = Math.max(1, Math.ceil(distance / 48));
          for (let index = 1; index <= steps; index += 1) {
            samples.push([
              Math.round(previous[0] + (target[0] - previous[0]) * index / steps),
              Math.round(previous[1] + (target[1] - previous[1]) * index / steps),
            ]);
          }
        };
        const up = () => {
          header.removeEventListener("pointermove", move);
          header.removeEventListener("pointerup", up);
          header.removeEventListener("pointercancel", up);
          if (samples.length > 1) {
            record("drag", {
              window_id: node.dataset.windowId,
              samples: samples.slice(-80),
              input_source: "window_drag",
            });
            tryContain(node, "window_drag");
          }
        };
        header.addEventListener("pointermove", move);
        header.addEventListener("pointerup", up);
        header.addEventListener("pointercancel", up);
      });
    }
    const close = node.querySelector(".parasite-close");
    if (model.interaction === "full") {
      close.addEventListener("click", () => performClose(node, "window_close_button"));
    } else {
      close.disabled = true;
      close.tabIndex = -1;
    }
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "popup-exorcist-v2";
    const interaction = state.control_condition?.interaction || "full";
    const parents = state.parasite_ids
      ? [...state.parasite_ids]
      : state.infection_groups
      ? Object.keys(state.infection_groups)
      : state.popups.filter((item) => item.runtime_behavior === "replicate").map((item) => item.id);
    const infectionGroups = state.infection_groups || {[parents[0]]: [...state.echo_ids]};
    const containmentStages = state.containment_stages || [state.containment];
    const stageBatches = state.stage_batches || [
      state.popups.map((item) => item.id),
    ];
    model = {
      state,
      helpers,
      interaction,
      events: [],
      topZ: 20,
      parents,
      infectionGroups,
      containmentStages,
      stageBatches,
      activeStage: 0,
      provokedParents: new Set(),
      containedParents: new Set(),
      maximumResistanceStrikes: Number(state.maximum_resistance_strikes || 3),
      strikes: 0,
      selectedId: null,
      submitting: false,
    };
    const proxyControls = interaction === "simplified" ? `<aside class="popup-proxy-controls">
      <span>SELECTED WINDOW CONTROL</span>
      <b class="popup-selection-status">SELECT A VISIBLE WINDOW</b>
      <button type="button" class="popup-close-selected" disabled>CLOSE SELECTED</button>
      <button type="button" class="popup-contain-selected" disabled>MOVE SELECTED TO CONTAINMENT</button>
    </aside>` : "";
    const resistance = state.control_condition?.difficulty === 2
      ? ""
      : `<span class="resistance-readout">RESISTANCE <b class="resistance-count">0/${model.maximumResistanceStrikes}</b></span>`;
    helpers.app.innerHTML = `<section class="parasite-captcha" data-interaction="${esc(interaction)}" data-multistrain="${parents.length > 1}" data-active-stage="0" data-challenge-id="${esc(state.challenge_id)}">
      <header class="parasite-head"><div><span>DESKTOP CONTAINMENT / LIVE FIELD</span><h1>${esc(state.prompt)}</h1></div><div class="parasite-count">WINDOWS <b>${stageBatches[0].length}</b></div></header>
      <main class="parasite-main">
        <section class="popup-field"><div class="field-wallpaper"><i></i><span>LOCAL DESKTOP</span></div><div class="containment-well" data-active="false" data-stage-index="0" style="left:${state.containment.x}px;top:${state.containment.y}px;width:${state.containment.w}px;height:${state.containment.h}px"><i></i><b>⌁</b></div>${state.popups.map((item) => windowMarkup(item)).join("")}</section>
        ${proxyControls}
      </main>
      <footer class="parasite-foot"><div class="readout" data-status="idle"></div><div class="parasite-foot-status">${resistance}<span class="field-signal">CONTAINMENT FIELD: DORMANT</span></div></footer>
    </section>`;
    document.querySelectorAll(".parasite-window").forEach(installWindow);
    if (interaction === "simplified") {
      document.querySelector(".popup-close-selected").addEventListener("click", () => performClose(selectedWindow(), "selected_close_button"));
      document.querySelector(".popup-contain-selected").addEventListener("click", () => performContainProxy(selectedWindow()));
    }
    updateFieldSignal();
    updateResistance();
    updateControls();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.popup_exorcist = {render, rootSelector: ".parasite-captcha"};
})();
