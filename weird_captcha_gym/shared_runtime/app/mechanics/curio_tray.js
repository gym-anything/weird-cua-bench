(() => {
  "use strict";

  const CAPACITY = 7;
  const model = {
    state: null,
    items: [],
    remaining: new Set(),
    tray: [],
    picks: [],
    triples: 0,
    busy: false,
    terminal: false,
    ready: false,
    interaction: "full",
    helpers: null,
  };

  const clean = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

  const overlap = (first, second) => (
    Number(first.x) < Number(second.x) + Number(second.width)
    && Number(second.x) < Number(first.x) + Number(first.width)
    && Number(first.y) < Number(second.y) + Number(second.height)
    && Number(second.y) < Number(first.y) + Number(first.height)
  );

  function accessibleIds() {
    return model.items.filter((item) => model.remaining.has(item.id) && !model.items.some((other) => (
      other.id !== item.id
      && model.remaining.has(other.id)
      && Number(other.z) > Number(item.z)
      && overlap(item, other)
    ))).map((item) => item.id);
  }

  function itemById(itemId) {
    return model.items.find((item) => item.id === itemId) || null;
  }

  function iconMarkup(item) {
    return `<span class="curio-icon curio-tone-${clean(item.tone)}" aria-hidden="true">${clean(item.icon)}</span>`;
  }

  function pileMarkup() {
    const exposed = new Set(accessibleIds());
    return model.items.filter((item) => model.remaining.has(item.id)).map((item) => {
      const accessible = exposed.has(item.id);
      const classes = `curio-item curio-tone-${clean(item.tone)}${accessible ? " is-exposed" : " is-occluded"}`;
      return `<button type="button" class="${classes}" data-item-id="${clean(item.id)}" data-accessible="${accessible ? "true" : "false"}" style="left:${Number(item.x)}px;top:${Number(item.y)}px;width:${Number(item.width)}px;height:${Number(item.height)}px;z-index:${Number(item.z)}" aria-label="${clean(item.name)}${accessible ? " exposed" : " occluded"}">
        <span class="curio-rim"></span>${iconMarkup(item)}<span class="curio-name">${clean(item.name)}</span><span class="curio-depth">${accessible ? "EXPOSED" : "UNDER GLASS"}</span>
      </button>`;
    }).join("");
  }

  function proxyMarkup() {
    const visible = accessibleIds();
    if (!visible.length) return '<p class="proxy-empty">NO EXPOSED CURIOS</p>';
    return visible.map((itemId, index) => {
      const item = itemById(itemId);
      return `<button type="button" class="curio-proxy" data-item-id="${clean(itemId)}" aria-label="Pick exposed ${clean(item.name)}"><b>${String(index + 1).padStart(2, "0")}</b>${iconMarkup(item)}<span><strong>${clean(item.name)}</strong><small>EXPOSED PICK</small></span></button>`;
    }).join("");
  }

  function trayMarkup() {
    const slots = [];
    for (let index = 0; index < CAPACITY; index += 1) {
      const item = model.tray[index];
      slots.push(item
        ? `<div class="tray-slot is-filled curio-tone-${clean(item.tone)}" data-slot-index="${index}">${iconMarkup(item)}<small>${clean(item.name)}</small></div>`
        : `<div class="tray-slot" data-slot-index="${index}"><span>${String(index + 1).padStart(2, "0")}</span></div>`);
    }
    return slots.join("");
  }

  function updatePanels() {
    const exposed = document.getElementById("curio-exposed-count");
    const remaining = document.getElementById("curio-remaining-count");
    const trayCount = document.getElementById("curio-tray-count");
    const tripleCount = document.getElementById("curio-triple-count");
    const tray = document.getElementById("curio-tray");
    const proxy = document.getElementById("curio-proxy-list");
    const submit = document.getElementById("curio-submit");
    if (exposed) exposed.textContent = String(accessibleIds().length).padStart(2, "0");
    if (remaining) remaining.textContent = String(model.remaining.size).padStart(2, "0");
    if (trayCount) trayCount.textContent = `${model.tray.length} / ${CAPACITY}`;
    if (tripleCount) tripleCount.textContent = String(model.triples).padStart(2, "0");
    if (tray) tray.innerHTML = trayMarkup();
    if (proxy) proxy.innerHTML = proxyMarkup();
    if (submit) submit.disabled = model.busy || model.terminal;
  }

  function flash(message, status = "idle") {
    model.helpers.setReadout(message, status);
    const shell = document.querySelector(".curio-tray-captcha");
    shell?.classList.remove("is-jolt");
    void shell?.offsetWidth;
    shell?.classList.add("is-jolt");
  }

  function clearFailure() {
    document.querySelector(".curio-verdict-fail")?.remove();
    document.querySelector(".curio-tray-captcha")?.classList.remove("is-fresh-fail");
  }

  function bindPickButtons() {
    document.querySelectorAll(".curio-item.is-exposed").forEach((button) => {
      button.addEventListener("click", () => {
        if (model.interaction === "full") attemptPick(button.dataset.itemId, "pile_click");
      });
    });
    document.querySelectorAll(".curio-proxy").forEach((button) => {
      button.addEventListener("click", () => {
        if (model.interaction === "simplified") attemptPick(button.dataset.itemId, "proxy_pick");
      });
    });
  }

  async function submit(completed) {
    if (!model.state || model.busy && !model.terminal) return;
    model.busy = true;
    document.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    model.helpers.setReadout(completed ? "APPRAISING EMPTY TRAY…" : "VOIDING ATTEMPT…", "pending");
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      picks: model.picks,
      tray: model.tray.map((item) => item.type),
      remaining_ids: Array.from(model.remaining).sort(),
      pick_count: model.picks.length,
      triple_count: model.triples,
      completed,
    };
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify(payload),
      });
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true;
        const shell = document.querySelector(".curio-tray-captcha");
        shell?.classList.add("is-pass");
        shell?.insertAdjacentHTML("beforeend", '<div class="curio-verdict curio-verdict-pass"><small>CABINET INVENTORY RECONCILED</small><strong>PASS</strong></div>');
        model.helpers.setReadout("PASS · EMPTY TRAY CERTIFIED", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        const shell = document.querySelector(".curio-tray-captcha");
        shell?.classList.add("is-fresh-fail");
        shell?.insertAdjacentHTML("beforeend", '<div class="curio-verdict curio-verdict-fail"><small>ATTEMPT VOID · NEW DRAW</small><strong>FAIL</strong></div>');
        model.helpers.setReadout("FAIL · NEW CABINET DRAWN", "error");
        window.setTimeout(() => document.querySelector(".curio-verdict-fail")?.remove(), 1800);
      } else {
        model.busy = false;
        model.terminal = false;
        model.helpers.setReadout("FAIL · TRAY NOT CERTIFIED", "error");
        document.querySelectorAll("button").forEach((button) => { button.disabled = false; });
      }
    } catch (_error) {
      model.busy = false;
      model.terminal = false;
      model.helpers.setReadout("FAIL · REGISTER OFFLINE", "error");
      document.querySelectorAll("button").forEach((button) => { button.disabled = false; });
    }
  }

  function overflowFailure() {
    model.terminal = true;
    const shell = document.querySelector(".curio-tray-captcha");
    shell?.classList.add("is-fresh-fail");
    shell?.insertAdjacentHTML("beforeend", '<div class="curio-verdict curio-verdict-fail"><small>SEVEN UNMATCHED CURIOS</small><strong>VOID</strong></div>');
    flash("TRAY FULL · CABINET DRAW VOID", "error");
    submit(false);
  }

  function attemptPick(itemId, inputSource) {
    if (model.busy || model.terminal) return;
    clearFailure();
    const exposed = accessibleIds();
    if (!exposed.includes(itemId)) {
      flash("THAT CURIO IS UNDER ANOTHER", "error");
      return;
    }
    const item = itemById(itemId);
    if (!item || !model.remaining.has(itemId)) return;
    model.remaining.delete(itemId);
    model.tray.push(item);
    let outcome = "pick";
    let clearedType = null;
    if (model.tray.filter((entry) => entry.type === item.type).length === 3) {
      model.tray = model.tray.filter((entry) => entry.type !== item.type);
      model.triples += 1;
      outcome = "triple_clear";
      clearedType = item.type;
    }
    const event = {
      sequence: model.picks.length + 1,
      item_id: itemId,
      input_source: inputSource,
      outcome,
      cleared_type: clearedType,
      tray_after: model.tray.map((entry) => entry.type),
      tray_size_after: model.tray.length,
      remaining_count: model.remaining.size,
    };
    model.picks.push(event);
    renderBoard();
    updatePanels();
    bindPickButtons();
    if (model.tray.length >= CAPACITY && model.remaining.size) {
      overflowFailure();
      return;
    }
    if (!model.remaining.size) {
      model.ready = model.tray.length === 0;
      document.querySelector(".curio-tray-captcha")?.classList.add("is-ready");
      flash("CABINET CLEAR · APPRAISE THE EMPTY TRAY", "passed");
    } else if (outcome === "triple_clear") {
      flash(`TRIPLE CLEAR · ${item.name} VANISHED`, "idle");
    } else {
      flash(`${item.name} STORED · ${model.tray.length} / ${CAPACITY} SLOTS`, "idle");
    }
  }

  function renderBoard() {
    const pile = document.getElementById("curio-pile");
    if (pile) pile.innerHTML = pileMarkup();
  }

  function resetAttempt() {
    if (model.busy) return;
    model.remaining = new Set(model.items.map((item) => item.id));
    model.tray = [];
    model.picks = [];
    model.triples = 0;
    model.terminal = false;
    model.ready = false;
    document.querySelector(".curio-tray-captcha")?.classList.remove("is-pass", "is-ready", "is-fresh-fail");
    document.querySelectorAll(".curio-verdict").forEach((node) => node.remove());
    renderBoard();
    updatePanels();
    bindPickButtons();
    flash("DRAW RESET · SELECT AN EXPOSED CURIO", "idle");
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "curio-tray";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const cabinet = state.cabinet || {};
    Object.assign(model, {
      state,
      items: (cabinet.items || []).map((item) => ({...item, id: String(item.id)})),
      remaining: new Set((cabinet.items || []).map((item) => String(item.id))),
      tray: [],
      picks: [],
      triples: 0,
      busy: false,
      terminal: false,
      ready: false,
      interaction: state.control_condition?.interaction || "full",
      helpers,
    });
    const interaction = model.interaction;
    helpers.app.innerHTML = `
      <section class="curio-tray-captcha" data-interaction="${clean(interaction)}" data-challenge-id="${clean(state.challenge_id)}">
        <header class="curio-head">
          <div class="curio-brand"><span>THE CURIO CABINET · INTAKE DESK 07</span><h1>${clean(state.prompt)}</h1></div>
          <div class="curio-ticket"><small>TRAY CAPACITY</small><strong>07</strong><i>UNMATCHED SLOTS</i></div>
        </header>
        <main class="curio-workbench">
          <section class="curio-cabinet-panel">
            <div class="curio-panel-label"><span>GLASS CABINET / LAYERED DRAW</span><b>${Number(cabinet.stack_count || 0)} STACKS</b></div>
            <div class="curio-cabinet" id="curio-cabinet" style="--cabinet-h:${Number(cabinet.height || 455)}px"><div class="curio-pile" id="curio-pile">${pileMarkup()}</div><div class="cabinet-glare"></div></div>
            <div class="curio-cabinet-foot"><span><i class="legend-dot exposed"></i> EXPOSED</span><span><i class="legend-dot occluded"></i> UNDER ANOTHER CURIO</span><b>CLICK ONLY WHAT IS ON TOP</b></div>
          </section>
          <aside class="curio-side-panel">
            <div class="curio-stat-row"><span>EXPOSED NOW</span><b id="curio-exposed-count">00</b></div>
            <div class="curio-stat-row"><span>LEFT IN CABINET</span><b id="curio-remaining-count">00</b></div>
            <div class="curio-stat-row"><span>TRIPLES CLEARED</span><b id="curio-triple-count">00</b></div>
            <section class="curio-proxy-wrap" data-proxy="${interaction === "simplified" ? "true" : "false"}">
              <header><span>${interaction === "simplified" ? "EXPOSED PICKS / PROXY" : "EXPOSED PICKS / MAP"}</span><small>${interaction === "simplified" ? "CLICK A ROW TO LIFT IT" : "USE THE CABINET"}</small></header>
              <div class="curio-proxy-list" id="curio-proxy-list">${proxyMarkup()}</div>
            </section>
            <section class="curio-rule-card"><b>TRIPLE RULE</b><p>Three matching curios disappear together and free their slots.</p><b>LOSS RULE</b><p>Seven unmatched curios fill the tray and void the draw.</p></section>
          </aside>
          <section class="curio-tray-panel">
            <div class="curio-panel-label"><span>THE SEVEN-SLOT TRAY</span><b id="curio-tray-count">0 / 7</b></div>
            <div class="curio-tray" id="curio-tray">${trayMarkup()}</div>
            <div class="curio-tray-note"><span>Matching sets clear automatically.</span><b>KEEP A SLOT OPEN FOR THE THIRD</b></div>
          </section>
        </main>
        <footer class="curio-foot">
          <button type="button" class="curio-reset" id="curio-reset">↺ RESET DRAW</button>
          <div class="readout" data-status="idle">SELECT AN EXPOSED CURIO TO BEGIN</div>
          <button type="button" class="curio-submit" id="curio-submit">${clean(state.submit_label || "APPRAISE EMPTY TRAY")}</button>
        </footer>
        ${helpers.cheatPanelTemplate()}
      </section>`;
    updatePanels();
    bindPickButtons();
    document.getElementById("curio-reset")?.addEventListener("click", resetAttempt);
    document.getElementById("curio-submit")?.addEventListener("click", () => submit(model.ready));
    helpers.installCheatPanel();
    window.curioTrayModel = model;
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.curio_tray = {rootSelector: ".curio-tray-captcha", render};
})();
