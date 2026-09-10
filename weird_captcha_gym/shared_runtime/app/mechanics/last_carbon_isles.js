(() => {
  "use strict";

  const MECHANIC_ID = "last_carbon_isles";
  let model = null;

  function esc(value) {
    return String(value ?? "").replace(/[&<>\"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[char]));
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function root() {
    return document.querySelector(".carbon-captcha");
  }

  function cardById(cardId) {
    return model.cards.find((card) => String(card.id) === String(cardId)) || null;
  }

  function regionById(regionId) {
    return model.regions.find((region) => String(region.id) === String(regionId)) || null;
  }

  function elapsed() {
    return Math.max(0, Math.round(performance.now() - model.startedAt));
  }

  function record(kind, fields = {}) {
    model.events.push({
      sequence: model.events.length + 1,
      elapsed_ms: elapsed(),
      kind,
      ...fields,
    });
  }

  function snapshot() {
    const output = {};
    for (const region of model.regions) {
      output[region.id] = {
        emissions: Number(region.emissions),
        jobs: Number(region.jobs),
      };
    }
    return output;
  }

  function smokeTotal() {
    return model.regions.reduce((sum, region) => sum + Number(region.emissions || 0), 0);
  }

  function weakestJobs() {
    return Math.min(...model.regions.map((region) => Number(region.jobs || 0)));
  }

  function isSolved() {
    return model.regions.every((region) => Number(region.emissions) <= 0 && Number(region.jobs) >= 100);
  }

  function formatEffect(effect) {
    const emissions = Number(effect?.emissions || 0);
    const jobs = Number(effect?.jobs || 0);
    const e = `${emissions <= 0 ? "−" : "+"}${Math.abs(emissions)} smoke`;
    const j = `${jobs >= 0 ? "+" : "−"}${Math.abs(jobs)} crews`;
    return `${e} · ${j}`;
  }

  function cardMarkup(card, mode) {
    const home = regionById(card.home_region);
    const accent = esc(card.accent || "#d7e6d2");
    const homeCue = model.showHomeLabels ? `HOME · ${esc(home?.name || card.home_name)}` : "MATCH BY READOUT";
    return `<button class="carbon-card${model.selectedCardId === card.id ? " is-selected" : ""}" type="button" data-card-id="${esc(card.id)}" style="--card-accent:${accent}" aria-label="${esc(card.title)} for ${esc(card.home_name)}">
      <span class="carbon-card-top"><b>${esc(card.eyebrow)}</b><em>−${Number(card.cost)}B</em></span>
      <strong>${esc(card.title)}</strong>
      <small>${esc(card.description)}</small>
      <span class="carbon-card-bottom"><i>${homeCue}</i><b>${esc(formatEffect(card.target_effect))}</b></span>
      ${mode === "full" ? "<span class=\"drag-mark\">DRAG ↗</span>" : "<span class=\"drag-mark\">CLICK TO ARM</span>"}
    </button>`;
  }

  function regionMarkup(region) {
    const safeE = Math.max(0, Number(region.emissions || 0));
    const jobs = Number(region.jobs || 0);
    const clear = safeE <= 0 && jobs >= 100;
    const tired = jobs < 100;
    return `<button class="carbon-isle${clear ? " is-clear" : ""}" type="button" data-region-id="${esc(region.id)}" style="--isle-x:${region.x}%;--isle-y:${region.y}%;--isle-w:${region.width}%;--isle-h:${region.height}%;--isle-rot:${region.rotation}deg;--isle-color:${esc(region.color)}" aria-label="${esc(region.name)}: ${safeE} smoke, ${jobs} crews">
      <span class="isle-name">${esc(region.name)}</span>
      <span class="isle-glyph">${clear ? "✦" : tired ? "◌" : "◈"}</span>
      <span class="isle-readouts"><b>${safeE} <small>SMOKE</small></b><b class="${tired ? "is-tired" : ""}">${jobs}<small>CREWS</small></b></span>
      <span class="isle-glint"></span>
    </button>`;
  }

  function researchMarkup() {
    const stage = model.researchStage;
    if (stage >= model.researchTracks.length) {
      return `<div class="research-empty"><span>DECK COMPLETE</span><b>All research routes have been charted.</b></div>`;
    }
    const track = model.researchTracks[stage];
    return `<div class="research-head"><span>RESEARCH ${String(stage + 1).padStart(2, "0")} / ${String(model.researchTracks.length).padStart(2, "0")}</span><b>Choose one blueprint · −${Number(track.cost)}B</b></div>
      <div class="research-offers">${(track.offers || []).map((card) => `<button class="research-card" type="button" data-research-id="${esc(card.id)}" style="--card-accent:${esc(card.accent || "#a2c8b2")}">
        <span>${esc(card.eyebrow)}</span><strong>${esc(card.title)}</strong><small>${model.showHomeLabels ? `HOME · ${esc(card.home_name)}` : "MATCH BY READOUT"}</small><em>${esc(formatEffect(card.target_effect))}</em>
        ${model.state.network ? `<small>${esc(card.description)}</small><b>PLAY COST ${Number(card.cost)}B</b>` : ''}
      </button>`).join("")}</div>`;
  }

  function renderShell() {
    const state = model.state;
    const mode = model.interaction;
    const hand = model.hand;
    const allClear = isSolved();
    model.helpers.app.innerHTML = `<section class="carbon-captcha" data-network="${state.network ? 'true' : 'false'}" data-interaction="${esc(mode)}" data-challenge-id="${esc(state.challenge_id)}">
      <header class="carbon-header">
        <div class="brand-lockup"><span class="eyebrow">LAST CARBON ISLES / POLICY ATLAS</span><h1>${esc(state.world?.name || "The Last Carbon Isles")}</h1><p>${esc(state.world?.subtitle || "One shared budget. No clean air left to waste.")}</p></div>
        <div class="header-meters"><div class="meter"><span>SHARED BUDGET</span><b>${Number(model.budget)}<i>B</i></b></div><div class="meter"><span>POLICY TURNS</span><b>${Number(model.turns)}<i> / ${Number(model.maxTurns)}</i></b></div><div class="meter"><span>INPUT</span><b>${mode === "full" ? "DIRECT DRAG" : "CLICK / PLACE"}</b></div></div>
      </header>
      <main class="carbon-main">
        <section class="atlas-panel">
          <div class="atlas-title"><div><span class="eyebrow">THE ARCHIPELAGO</span><h2>Keep the islands lit. Keep the crews aboard.</h2></div><div class="goal-chip"><span>JOINT GOAL</span><b>0 SMOKE <i>+</i> 100 CREWS</b></div></div>
          <div class="atlas-map" aria-label="Carbon Isles policy map">${model.regions.map(regionMarkup).join("")}<span class="map-compass">N<br><i>⌄</i></span><span class="map-scale">each isle reports its own burden</span></div>
          <div class="atlas-legend"><span><i class="legend-dot smoke"></i>SMOKE TO CLEAR</span><span><i class="legend-dot crews"></i>CREWS TO PROTECT</span>${state.network ? '<button class="atlas-open" type="button">POLICY ATLAS · ALL CONNECTIONS</button>' : '<span class="legend-note">Every placement redraws the ledger.</span>'}</div>
        </section>
        <aside class="policy-panel">
          <div class="panel-kicker"><span>THE HAND</span><b>${hand.length} POLIC${hand.length === 1 ? "Y" : "IES"} REMAIN</b></div>
          <p class="panel-hint">${mode === "full" ? "Drag a policy from the hand onto its home isle." : "Click a policy, then click the isle where it belongs."}</p>
          <div class="hand" aria-label="Policy hand">${hand.length ? hand.map((card) => cardMarkup(card, mode)).join("") : "<div class=\"hand-empty\">THE HAND IS EMPTY<br><small>Research another route or certify the map.</small></div>"}</div>
          <section class="research-panel"><div class="research-label"><span>DECK RESEARCH</span><i>${model.researchTracks.length - model.researchStage} ROUTES UNCHARTED</i></div>${researchMarkup()}</section>
          <button class="certify-button" type="button" ${allClear ? "" : ""}>CERTIFY ISLES <span>→</span></button>
          <div class="policy-caption"><span>POLICIES ARE PUBLIC.</span><b>THE ORDER IS YOURS.</b></div>
        </aside>
      </main>
      <footer class="carbon-footer"><div class="footer-ledger"><span>LEDGER</span><b>${smokeTotal()} <i>SMOKE REMAINING</i></b><b>${weakestJobs()} <i>LOWEST CREW LEVEL</i></b></div><div class="footer-state">${allClear ? "ALL READOUTS ALIGNED · READY TO CERTIFY" : "MAP ACTIVE · OBSERVE THE CHANGE AFTER EACH POLICY"}</div></footer>
    </section>`;
    bindControls();
  }

  function showAtlas() {
    const panel = document.createElement('section');
    panel.className = 'carbon-atlas-dialog';
    panel.innerHTML = `<header><h2>Policy atlas · plan before researching</h2><button type="button">CLOSE ATLAS</button></header>
      <p>Each research stage adds ONE policy for its destination. Research may be completed before placing. A relay consumes its donor's spare crews. All isles must retain 100 crews. Budget: ${model.budget}B; remaining research costs ${model.researchTracks.slice(model.researchStage).reduce((n,t)=>n+Number(t.cost),0)}B.</p>
      <div class="atlas-table-scroll"><table><thead><tr><th>Destination</th><th>Policy / cost</th><th>Donor requirement and transfer</th><th>Destination effect</th></tr></thead><tbody>${model.cards.map(c=>`<tr><td>${esc(c.home_name)}</td><td>${esc(c.title)} · ${c.cost}B</td><td>${esc(c.description)}</td><td>${esc(formatEffect(c.target_effect))}</td></tr>`).join('')}</tbody></table></div>`;
    panel.querySelector('button').addEventListener('click',()=>panel.remove());
    root().appendChild(panel);
  }

  function setReadout(text, status = "idle") {
    model.helpers.setReadout(text, status);
    const node = root()?.querySelector(".footer-state");
    if (node) {
      node.textContent = text;
      node.dataset.status = status;
      node.setAttribute("aria-live", "polite");
    }
  }

  function playCard(cardId, regionId, cardSource, regionSource) {
    if (model.submitting) return;
    const card = cardById(cardId);
    const region = regionById(regionId);
    if (!card || !region || !model.hand.some((item) => item.id === cardId)) {
      setReadout("POLICY / ISLE MISMATCH", "error");
      return;
    }
    const effect = card.effects?.[regionId];
    if (!effect || Number(model.budget) < Number(card.cost) || model.turns >= model.maxTurns) {
      setReadout("THE LEDGER CANNOT FUND THAT MOVE", "error");
      return;
    }
    if ((card.requirements || []).some(req => {
      const donor = regionById(req.region_id);
      return !donor || Number(donor.emissions) > req.emissions || Number(donor.jobs) < req.jobs;
    })) {
      setReadout("DONOR NEEDS CLEAN AIR AND ENOUGH SPARE CREWS · POLICY RETURNED", "error");
      return;
    }
    const before = snapshot();
    model.budget -= Number(card.cost);
    region.emissions = Math.max(0, Number(region.emissions) + Number(effect.emissions || 0));
    region.jobs = Math.max(0, Math.min(120, Number(region.jobs) + Number(effect.jobs || 0)));
    for (const [donorId, transfer] of Object.entries(card.side_effects || {})) {
      const donor = regionById(donorId);
      donor.jobs += Number(transfer.jobs);
      donor.emissions += Number(transfer.emissions);
    }
    model.turns += 1;
    model.hand = model.hand.filter((item) => item.id !== cardId);
    record("play", {
      card_id: cardId,
      region_id: regionId,
      cost: Number(card.cost),
      card_source: cardSource,
      region_source: regionSource,
      before,
      after: snapshot(),
    });
    model.selectedCardId = null;
    setReadout(`${card.title.toUpperCase()} LANDED ON ${region.name.toUpperCase()}`, "idle");
    renderShell();
  }

  function research(cardId) {
    const track = model.researchTracks[model.researchStage];
    const card = cardById(cardId);
    if (!track || !card || !(track.offers || []).some((offer) => offer.id === cardId)) {
      setReadout("THAT BLUEPRINT IS NOT ON THE TABLE", "error");
      return;
    }
    if (Number(model.budget) < Number(track.cost)) {
      setReadout("NOT ENOUGH BUDGET TO RESEARCH", "error");
      return;
    }
    model.budget -= Number(track.cost);
    model.hand.push(clone(card));
    record("research", {stage: model.researchStage, card_id: cardId, cost: Number(track.cost), source: "research_button"});
    model.researchStage += 1;
    setReadout(`${card.title.toUpperCase()} ADDED TO THE HAND`, "idle");
    renderShell();
  }

  async function submit() {
    if (model.submitting) return;
    model.submitting = true;
    record("finish");
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({
        mechanic_id: MECHANIC_ID,
        task_id: model.state.task_id,
        challenge_id: model.state.challenge_id,
        events: model.events,
      })});
      const outcome = await response.json();
      if (outcome.passed === true) {
        setReadout("PASS", "passed");
        showVerdict(true, outcome.feedback || "Every isle is clear.");
      } else {
        setReadout("FAIL", "error");
        showVerdict(false, outcome.feedback || "The ledger rejected the plan.", outcome.state);
      }
    } catch (_error) {
      setReadout("SUBMISSION ERROR", "error");
      showVerdict(false, "The ledger could not be reached.");
    } finally {
      model.submitting = false;
    }
  }

  function showVerdict(passed, feedback, freshState = null) {
    const currentRoot = root();
    if (!currentRoot) return;
    currentRoot.querySelector(".carbon-verdict")?.remove();
    const verdict = document.createElement("section");
    verdict.className = `carbon-verdict ${passed ? "is-pass" : "is-fail"}`;
    verdict.setAttribute("role", "alert");
    verdict.innerHTML = `<span>CARBON ISLES LEDGER / FINAL READ</span><strong>${passed ? "CLEAR" : "REPAIR"}</strong><p>${esc(feedback)}</p><button type="button" ${freshState ? "" : "disabled"}>${freshState ? "OPEN A FRESH ARCHIPELAGO →" : passed ? "LEDGER ACCEPTED" : "LEDGER UNAVAILABLE"}</button>`;
    currentRoot.appendChild(verdict);
    if (freshState) verdict.querySelector("button").addEventListener("click", () => model.helpers.render(freshState));
  }

  function bindControls() {
    const currentRoot = root();
    if (!currentRoot) return;
    currentRoot.querySelector('.atlas-open')?.addEventListener('click', showAtlas);
    currentRoot.querySelectorAll(".research-card").forEach((button) => {
      button.addEventListener("click", () => research(button.dataset.researchId));
    });
    currentRoot.querySelector(".certify-button")?.addEventListener("click", submit);
    currentRoot.querySelectorAll(".carbon-isle").forEach((isle) => {
      isle.addEventListener("click", () => {
        if (model.interaction === "simplified" && model.selectedCardId) {
          playCard(model.selectedCardId, isle.dataset.regionId, "card_click", "region_click");
        } else if (model.interaction === "simplified") {
          setReadout("CHOOSE A POLICY FROM THE HAND FIRST", "idle");
        }
      });
    });
    currentRoot.querySelectorAll(".carbon-card").forEach((card) => {
      const cardId = card.dataset.cardId;
      if (model.interaction === "simplified") {
        card.addEventListener("click", () => {
          model.selectedCardId = model.selectedCardId === cardId ? null : cardId;
          setReadout(model.selectedCardId ? "NOW CHOOSE ITS HOME ISLE" : "POLICY DISARMED", "idle");
          renderShell();
        });
        return;
      }
      card.addEventListener("pointerdown", (event) => {
        if (event.button !== 0 || model.submitting) return;
        event.preventDefault();
        card.setPointerCapture(event.pointerId);
        card.classList.add("is-dragging");
        currentRoot.dataset.dragging = "true";
        setReadout("DROP THE POLICY ON ITS HOME ISLE", "idle");
      });
      card.addEventListener("pointermove", (event) => {
        if (card.hasPointerCapture(event.pointerId)) {
          const target = document.elementFromPoint(event.clientX, event.clientY)?.closest(".carbon-isle");
          currentRoot.querySelectorAll(".carbon-isle").forEach((node) => node.classList.toggle("is-drop-target", node === target));
        }
      });
      card.addEventListener("pointerup", (event) => {
        if (!card.hasPointerCapture(event.pointerId)) return;
        const target = document.elementFromPoint(event.clientX, event.clientY)?.closest(".carbon-isle");
        card.releasePointerCapture(event.pointerId);
        card.classList.remove("is-dragging");
        currentRoot.dataset.dragging = "false";
        currentRoot.querySelectorAll(".carbon-isle").forEach((node) => node.classList.remove("is-drop-target"));
        if (target) playCard(cardId, target.dataset.regionId, "card_drag", "region_drop");
        else setReadout("POLICY RETURNED TO THE HAND", "idle");
      });
      card.addEventListener("pointercancel", () => {
        card.classList.remove("is-dragging");
        currentRoot.dataset.dragging = "false";
      });
    });
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "last-carbon-isles";
    const condition = state.control_condition || {};
    model = {
      state,
      helpers,
      interaction: String(condition.interaction || "full"),
      regions: clone(state.regions || []),
      cards: clone(state.cards || []),
      hand: clone(state.hand || []),
      researchTracks: clone(state.research_tracks || []),
      researchStage: Number(state.research_stage || 0),
      budget: Number(state.budget || 0),
      maxTurns: Number(state.max_turns || 1),
      turns: Number(state.turns || 0),
      showHomeLabels: condition.difficulty_parameters?.show_home_labels !== false,
      selectedCardId: null,
      events: [],
      submitting: false,
      startedAt: performance.now(),
    };
    helpers.app.innerHTML = "";
    renderShell();
    setReadout("MAP ACTIVE · READ THE LEDGER", "idle");
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {render, rootSelector: ".carbon-captcha"};
})();
