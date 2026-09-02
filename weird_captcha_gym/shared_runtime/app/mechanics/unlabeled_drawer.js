(() => {
  "use strict";

  let model = null;
  let cleanup = null;
  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const interaction = () => model.state.control_condition?.interaction || "full";
  const probeBudget = () => Number(model.state.parameters.probe_count);
  const currentFinal = () => model.state.final_specimens[Object.keys(model.assignments).length] || null;
  const specimenById = (id) => [...model.state.probe_specimens, ...model.state.final_specimens]
    .find((item) => item.id === id);

  function clearFreshFailure() {
    if (!model?.freshFailure) return;
    model.freshFailure = false;
    document.querySelector(".ud-fresh-failure")?.remove();
    model.helpers.setReadout("CABINET READY", "idle");
  }

  function record(event) {
    clearFreshFailure();
    model.events.push({sequence: model.events.length + 1, ...event});
  }

  function specimenGraphic(specimen) {
    const [hollow, spined, paired, crossed, balanced, banded] = specimen.features;
    const style = specimen.style;
    const palettes = [
      ["#db5e45", "#ffcf73", "#18333a"],
      ["#79a7a3", "#e7b66d", "#172d34"],
      ["#a779a8", "#edb275", "#2b2939"],
      ["#718da8", "#c85a48", "#182d35"],
      ["#7e9b55", "#d89861", "#1f3331"],
    ];
    const palette = palettes[Number(style.palette) % palettes.length];
    const outer = spined
      ? "M28 67 L34 53 L28 42 L42 35 L47 21 L61 27 L72 18 L82 31 L98 30 L99 46 L112 55 L102 67 L108 82 L91 86 L82 99 L69 91 L55 99 L47 86 L31 82 Z"
      : "M69 23 C94 23 108 39 108 62 C108 84 93 98 69 98 C45 98 30 84 30 62 C30 40 45 23 69 23 Z";
    const veins = crossed
      ? '<path d="M49 45 L89 81 M89 45 L49 81" class="ud-vein"/>'
      : '<path d="M48 50 Q68 59 90 50 M47 69 Q69 78 91 69" class="ud-vein"/>';
    const core = hollow
      ? `<circle cx="69" cy="62" r="15" fill="${palette[2]}"/><circle cx="69" cy="62" r="8" fill="#f2e6cb"/>`
      : `<circle cx="69" cy="62" r="15" fill="${palette[1]}"/><circle cx="69" cy="62" r="4" fill="${palette[2]}"/>`;
    const satellites = paired
      ? `<circle cx="23" cy="62" r="9" fill="${palette[1]}"/><circle cx="115" cy="62" r="9" fill="${palette[1]}"/>`
      : `<path d="M20 62 L29 53 L38 62 L29 71 Z" fill="${palette[1]}"/>`;
    const side = Number(style.asymmetry_side) < 0 ? -1 : 1;
    const arms = balanced
      ? `<path d="M35 58 Q20 43 11 49 M103 58 Q118 43 127 49" class="ud-arm"/>`
      : side < 0
        ? '<path d="M35 58 Q20 43 11 49" class="ud-arm"/>'
        : '<path d="M103 58 Q118 43 127 49" class="ud-arm"/>';
    const marks = banded
      ? '<path d="M52 35 Q69 42 86 35 M47 86 Q69 78 91 86" class="ud-mark"/>'
      : '<circle cx="57" cy="40" r="3" class="ud-dot"/><circle cx="81" cy="40" r="3" class="ud-dot"/><circle cx="57" cy="84" r="3" class="ud-dot"/><circle cx="81" cy="84" r="3" class="ud-dot"/>';
    return `<svg viewBox="0 0 138 120" aria-hidden="true" style="--rotation:${Number(style.rotation_deg)}deg;--scale:${Number(style.scale)}">
      <g class="ud-specimen-shape"><path d="${outer}" fill="${palette[0]}" stroke="${palette[2]}" stroke-width="4" stroke-linejoin="round"/>
      ${satellites}${arms}${veins}${core}${marks}</g></svg>`;
  }

  function specimenCard(specimen, zone, options = {}) {
    const selected = model.selectedId === specimen.id;
    const assigned = model.assignments[specimen.id];
    return `<button class="ud-specimen ${selected ? "is-selected" : ""} ${options.mini ? "is-mini" : ""} paper-${Number(specimen.style.paper) % 4}"
      data-specimen-id="${esc(specimen.id)}" data-zone="${esc(zone)}" aria-pressed="${selected}" aria-label="Specimen ${esc(specimen.style.serial)}${assigned ? ` filed ${esc(assigned)}` : ""}">
      <span class="ud-pin"></span>${specimenGraphic(specimen)}<b>${esc(specimen.style.serial)}</b><small>FIELD SPECIMEN</small>
    </button>`;
  }

  function archiveMarkup() {
    if (!model.tested.length) {
      return `<section class="ud-archive is-empty" aria-label="one-record calibration archive">
        <header><span>ONE-RECORD ARCHIVE</span><small>NO RECORDS YET</small></header>
        <div class="ud-archive-empty">NO RECORD</div>
      </section>`;
    }
    model.archiveIndex = Math.max(0, Math.min(model.archiveIndex, model.tested.length - 1));
    const record = model.tested[model.archiveIndex];
    const specimen = specimenById(record.specimen_id);
    return `<section class="ud-archive" aria-label="one-record calibration archive">
      <header><span>ONE-RECORD ARCHIVE</span><small>RECORD ${model.archiveIndex + 1} / ${model.tested.length}</small></header>
      <div class="ud-archive-viewer">
        <button class="ud-archive-nav" id="ud-archive-prev" ${model.archiveIndex === 0 ? "disabled" : ""} aria-label="Previous calibration record">←</button>
        <article class="ud-archive-record ${record.outcome ? "is-accept" : "is-reject"}">
          <div>${specimenGraphic(specimen)}</div>
          <span><small>${esc(specimen.style.serial)} · STORED RESPONSE</small><strong>${record.outcome ? "FILE" : "RETURN"}</strong></span>
        </article>
        <button class="ud-archive-nav" id="ud-archive-next" ${model.archiveIndex === model.tested.length - 1 ? "disabled" : ""} aria-label="Next calibration record">→</button>
      </div>
    </section>`;
  }

  function cabinetMarkup() {
    const ready = model.tested.length === probeBudget();
    if (!model.finalOpen) {
      return `<aside class="ud-cabinet calibration">
        <div class="ud-cabinet-crown"><i></i><b>DEPARTMENT OF IMPOSSIBLE NATURAL HISTORY</b><i></i></div>
        <section class="ud-oracle" data-drop="probe">
          <div class="ud-oracle-mouth"><span></span><b>CALIBRATION SLOT</b><small>${interaction() === "full" ? "DROP TO TEST" : "TEST"}</small></div>
          <div class="ud-oracle-answer">
            <small>CALIBRATION SEALS</small><strong>${model.tested.length} / ${probeBudget()}</strong>
          </div>
          ${interaction() === "simplified" ? `<button class="ud-action" id="ud-test" ${!model.selectedId || ready ? "disabled" : ""}>TEST SELECTED</button>` : ""}
        </section>
        <section class="ud-seal ${ready ? "is-ready" : ""}"><div><small>FINAL TRAY</small><b>${ready ? "UNSEALED" : "SEALED"}</b></div>
          <button id="ud-open-final" ${ready ? "" : "disabled"}>${ready ? "BREAK SEAL" : `${probeBudget() - model.tested.length} SEALS REMAIN`}</button>
        </section>
      </aside>`;
    }
    const drawer = (kind) => {
      const count = Object.values(model.assignments).filter((value) => value === kind).length;
      return `<section class="ud-final-drawer ${kind}" data-drop="${kind}">
      <header><small>FINAL DRAWER</small><b>${kind === "accept" ? "FILE" : "RETURN"}</b><span>${count}</span></header>
      <div><em>${count ? `${count} RECORD${count === 1 ? "" : "S"} CLOSED` : "EMPTY"}</em></div>
      ${interaction() === "simplified" ? `<button class="ud-action" data-file-button="${kind}" ${!model.selectedId ? "disabled" : ""}>FILE SELECTED</button>` : ""}
    </section>`;
    };
    return `<aside class="ud-cabinet final"><div class="ud-cabinet-crown"><i></i><b>FINAL CLASSIFICATION</b><i></i></div>${drawer("accept")}${drawer("reject")}</aside>`;
  }

  function workbenchMarkup() {
    if (!model.finalOpen) {
      const remaining = model.state.probe_specimens.filter((item) => !model.tested.some((entry) => entry.specimen_id === item.id));
      const ready = model.tested.length === probeBudget();
      return `<section class="ud-workbench"><header><div><small>CALIBRATION · ${model.state.probe_specimens.length} CANDIDATES · ${probeBudget()} SEALS</small><h2>SPECIMEN BANK</h2></div><span>${interaction() === "full" ? "DIRECT DRAG" : "SELECT + BUTTON"}</span></header>
        <div class="ud-probe-rack bank-${model.state.probe_specimens.length}" data-rack="probe-rack">${ready ? '<p class="ud-rack-empty">SEALED</p>' : remaining.map((item) => specimenCard(item, "probe-rack")).join("")}</div>
        ${archiveMarkup()}
      </section>`;
    }
    const specimen = currentFinal();
    return `<section class="ud-workbench"><header><div><small>SEALED TRAY · ONE SPECIMEN</small><h2>FINAL TRAY</h2></div><span>${Object.keys(model.assignments).length}/${model.state.final_specimens.length} FILED</span></header>
      <div class="ud-final-rack is-sequential" data-rack="final-rack">${specimen ? specimenCard(specimen, "final-rack") : '<p class="ud-rack-empty">CLOSED</p>'}</div>
      ${archiveMarkup()}
    </section>`;
  }

  function renderStage() {
    const stage = document.querySelector(".ud-stage");
    if (!stage) return;
    stage.innerHTML = `${workbenchMarkup()}${cabinetMarkup()}`;
    bindStage();
  }

  function normalizedPoint(event) {
    const root = document.querySelector(".unlabeled-drawer");
    const rect = root.getBoundingClientRect();
    return [
      Number(((event.clientX - rect.left) / rect.width).toFixed(6)),
      Number(((event.clientY - rect.top) / rect.height).toFixed(6)),
    ];
  }

  function dropKindAt(x, y) {
    for (const node of document.querySelectorAll("[data-drop]")) {
      const rect = node.getBoundingClientRect();
      if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) return node.dataset.drop;
    }
    return null;
  }

  function testProbe(specimenId, source, gesture = null) {
    const specimen = model.state.probe_specimens.find((item) => item.id === specimenId);
    if (
      !specimen
      || model.finalOpen
      || model.tested.length >= probeBudget()
      || model.tested.some((item) => item.specimen_id === specimenId)
    ) return;
    const outcome = model.state.runtime_probe_outcomes[specimenId] === true;
    record({type: "probe", specimen_id: specimenId, outcome, input_source: source, ...(gesture ? {start_zone: "probe-rack", gesture} : {})});
    model.tested.push({specimen_id: specimenId, outcome});
    model.archiveIndex = model.tested.length - 1;
    model.selectedId = null;
    renderStage();
  }

  function openFinal() {
    if (model.tested.length !== probeBudget() || model.finalOpen) return;
    record({type: "open_final", input_source: "seal_latch"});
    model.finalOpen = true;
    model.selectedId = null;
    renderStage();
  }

  function assign(specimenId, drawer, source, gesture = null) {
    const specimen = currentFinal();
    if (!model.finalOpen || !specimen || specimen.id !== specimenId || !["accept", "reject"].includes(drawer)) return;
    record({type: "assign", specimen_id: specimenId, drawer, before: null, input_source: source, ...(gesture ? {start_zone: "final-rack", gesture} : {})});
    model.assignments[specimenId] = drawer;
    model.selectedId = null;
    renderStage();
  }

  function chooseSpecimen(specimenId) {
    if (model.submitting || model.terminal) return;
    clearFreshFailure();
    model.selectedId = model.selectedId === specimenId ? null : specimenId;
    renderStage();
  }

  function bindStage() {
    document.querySelectorAll("[data-specimen-id]").forEach((card) => {
      if (interaction() === "simplified") {
        card.addEventListener("click", () => chooseSpecimen(card.dataset.specimenId));
        return;
      }
      let drag = null;
      card.addEventListener("pointerdown", (event) => {
        if (event.button !== 0 || model.submitting || model.terminal) return;
        event.preventDefault();
        clearFreshFailure();
        card.setPointerCapture?.(event.pointerId);
        drag = {start: normalizedPoint(event), lastX: event.clientX, lastY: event.clientY, travelPx: 0, sampleCount: 0};
        card.classList.add("is-dragging");
      });
      card.addEventListener("pointermove", (event) => {
        if (!drag) return;
        drag.travelPx += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY);
        drag.lastX = event.clientX; drag.lastY = event.clientY; drag.sampleCount += 1;
        card.style.transform = `translate(${event.clientX - card.getBoundingClientRect().left - card.offsetWidth / 2}px, ${event.clientY - card.getBoundingClientRect().top - card.offsetHeight / 2}px)`;
      });
      card.addEventListener("pointerup", (event) => {
        if (!drag) return;
        drag.travelPx += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY); drag.sampleCount += 1;
        const destination = dropKindAt(event.clientX, event.clientY);
        const proof = {start: drag.start, end: normalizedPoint(event), travel_px: Number(drag.travelPx.toFixed(3)), sample_count: drag.sampleCount};
        drag = null; card.classList.remove("is-dragging"); card.style.transform = "";
        if (destination === "probe" && card.dataset.zone === "probe-rack") testProbe(card.dataset.specimenId, "specimen_drag", proof);
        else if (["accept", "reject"].includes(destination) && card.dataset.zone === "final-rack") assign(card.dataset.specimenId, destination, "specimen_drag", proof);
      });
      card.addEventListener("pointercancel", () => { drag = null; card.classList.remove("is-dragging"); card.style.transform = ""; });
    });
    document.getElementById("ud-test")?.addEventListener("click", () => testProbe(model.selectedId, "selected_test_button"));
    document.getElementById("ud-open-final")?.addEventListener("click", openFinal);
    document.querySelectorAll("[data-file-button]").forEach((button) => button.addEventListener("click", () => assign(model.selectedId, button.dataset.fileButton, "selected_drawer_button")));
    document.getElementById("ud-archive-prev")?.addEventListener("click", () => {
      model.archiveIndex = Math.max(0, model.archiveIndex - 1);
      renderStage();
    });
    document.getElementById("ud-archive-next")?.addEventListener("click", () => {
      model.archiveIndex = Math.min(model.tested.length - 1, model.archiveIndex + 1);
      renderStage();
    });
  }

  function showFreshFailure() {
    const root = document.querySelector(".unlabeled-drawer");
    if (!root || root.querySelector(".ud-fresh-failure")) return;
    root.insertAdjacentHTML("afterbegin", '<div class="ud-fresh-failure"><b>RETURNED</b><span>NEW CASE · PRIOR RECORD REJECTED</span></div>');
  }

  async function submit() {
    if (!model || model.submitting || model.terminal) return;
    const current = model;
    current.submitting = true;
    current.helpers.setReadout("AUDITING DRAWER TRANSCRIPT…", "pending");
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({
        mechanic_id: current.state.mechanic_id,
        task_id: current.state.task_id,
        challenge_id: current.state.challenge_id,
        interaction_mode: interaction(),
        events: current.events,
        tested_probe_ids: current.tested.map((item) => item.specimen_id),
        final_assignments: current.assignments,
        completed: true,
      })});
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.terminal = true;
        current.helpers.setReadout("PASS", "passed");
        document.querySelector(".unlabeled-drawer")?.setAttribute("data-terminal", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await render(outcome.state, current.helpers, {freshFailure: true});
        model.helpers.setReadout("FAIL", "error");
        showFreshFailure();
      } else {
        current.submitting = false;
        current.helpers.setReadout("CABINET REJECTED THE RECORD", "error");
      }
    } catch (_error) {
      if (model === current) {
        current.submitting = false;
        current.helpers.setReadout("CABINET LINK OFFLINE", "error");
      }
    }
  }

  async function render(state, helpers, options = {}) {
    cleanup?.();
    document.body.dataset.mechanic = "unlabeled-drawer";
    model = {
      state,
      helpers,
      events: [],
      tested: [],
      assignments: {},
      selectedId: null,
      archiveIndex: 0,
      finalOpen: false,
      freshFailure: Boolean(options.freshFailure),
      submitting: false,
      terminal: false,
    };
    helpers.app.innerHTML = `<section class="unlabeled-drawer mode-${interaction()}" data-interaction="${esc(interaction())}" data-challenge-id="${esc(state.challenge_id)}" data-fresh-failure="${options.freshFailure ? "true" : "false"}">
      <header class="ud-masthead"><div class="ud-sealmark"><span>UD</span><small>19—27</small></div><div><small>DEPARTMENT OF IMPOSSIBLE NATURAL HISTORY · ANNEX IV</small><h1>${esc(state.prompt)}</h1></div><div class="ud-condition"><b>${interaction().toUpperCase()} INPUT</b><span>STATIC OBSERVATION</span></div></header>
      <main class="ud-stage"></main>
      <footer class="ud-footer"><div><small>ANNEX IV</small><b>UD · 19—27</b></div><div class="readout" data-status="idle">CABINET READY</div><button id="ud-certify">CERTIFY SORT</button></footer>
      ${helpers.cheatPanelTemplate()}
    </section>`;
    renderStage();
    document.getElementById("ud-certify").addEventListener("click", submit);
    helpers.installCheatPanel();
    if (options.freshFailure) showFreshFailure();
    cleanup = () => {};
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.unlabeled_drawer = {rootSelector: ".unlabeled-drawer", render};
})();
