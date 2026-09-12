(() => {
  "use strict";

  let model;
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;"}[char]));
  const ART_COLORS = ["#e7b44a", "#6d709f", "#58a8ae", "#c8894d", "#65936a", "#df786d", "#c49b4c", "#a17bc1", "#dc654f", "#d6c8a0", "#d978a0", "#6da9c2"];

  function glyphSvg(glyph, size = 54) {
    const strokes = (glyph?.strokes || []).map((stroke) => `<line x1="${stroke[0]}" y1="${stroke[1]}" x2="${stroke[2]}" y2="${stroke[3]}"/>`).join("");
    const seal = glyph?.seal === "dot" ? `<circle cx="24" cy="8" r="3"/>` : glyph?.seal === "diamond" ? `<path d="M24 3l5 5-5 5-5-5z"/>` : glyph?.seal === "arc" ? `<path d="M16 8q8-9 16 0"/>` : `<path d="M14 8h20"/>`;
    return `<svg class="gm-glyph-svg" viewBox="0 0 48 38" width="${size}" height="${Math.round(size * .79)}" aria-hidden="true"><g stroke="${escapeHtml(glyph?.ink || "#493b48")}" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round">${strokes}${seal}</g></svg>`;
  }

  function artSvg(art, variant = 0, size = "large") {
    const color = ART_COLORS[Number(art) % ART_COLORS.length];
    const accent = ART_COLORS[(Number(art) + 4 + Number(variant)) % ART_COLORS.length];
    const width = size === "small" ? 118 : 252;
    const height = size === "small" ? 92 : 176;
    const scale = size === "small" ? .62 : 1;
    const x = (value) => Math.round(value * scale + (width - 252 * scale) / 2);
    const y = (value) => Math.round(value * scale + (height - 176 * scale) / 2);
    let drawing = "";
    switch (Number(art) % 12) {
      case 0: drawing = `<circle cx="126" cy="78" r="42" fill="${color}"/><path d="M126 18v-12M126 138v12M66 78H54M198 78h12M84 36L75 27M168 120l9 9" stroke="${accent}" stroke-width="9" stroke-linecap="round"/>`; break;
      case 1: drawing = `<path d="M162 28a57 57 0 1 0 0 100 49 49 0 1 1 0-100z" fill="${color}"/><circle cx="102" cy="58" r="4" fill="${accent}"/><circle cx="88" cy="94" r="3" fill="${accent}"/>`; break;
      case 2: drawing = `<path d="M30 74q24-22 48 0t48 0 48 0 48 0" fill="none" stroke="${color}" stroke-width="16"/><path d="M30 112q24-22 48 0t48 0 48 0 48 0" fill="none" stroke="${accent}" stroke-width="10"/>`; break;
      case 3: drawing = `<path d="M54 76Q82 40 132 48q50-8 66 28l-11 43H70z" fill="${color}" stroke="${accent}" stroke-width="6"/><path d="M82 71q12 19 24 0m28 0q12 19 24 0" fill="none" stroke="${accent}" stroke-width="5"/>`; break;
      case 4: drawing = `<path d="M128 148C57 122 66 48 128 31c62 17 71 91 0 117z" fill="${color}"/><path d="M128 32v112M128 76q-29-22-52-17M128 96q29-22 52-17" fill="none" stroke="${accent}" stroke-width="7" stroke-linecap="round"/>`; break;
      case 5: drawing = `<path d="M42 84q37-45 89-6 43-31 79 6-36 39-79 4-52 39-89-4z" fill="${color}" stroke="${accent}" stroke-width="5"/><circle cx="164" cy="75" r="5" fill="${accent}"/>`; break;
      case 6: drawing = `<path d="M76 56h100v82H76z" fill="${color}" stroke="${accent}" stroke-width="7"/><path d="M68 57h116M86 34h84v22H86z" fill="${accent}"/><path d="M104 77v40m44-40v40" stroke="#f7edcf" stroke-width="7"/>`; break;
      case 7: drawing = `<circle cx="126" cy="92" r="30" fill="${color}" stroke="${accent}" stroke-width="7"/><path d="M126 62V28h42v28M168 56l-23 23" fill="none" stroke="${accent}" stroke-width="9" stroke-linecap="round"/><circle cx="158" cy="31" r="7" fill="${accent}"/>`; break;
      case 8: drawing = `<path d="M126 148C102 126 65 94 91 64c12-14 31-7 35 9 4-16 23-23 35-9 26 30-11 62-35 84z" fill="${color}" stroke="${accent}" stroke-width="6"/><path d="M126 60v-28" stroke="${accent}" stroke-width="8" stroke-linecap="round"/>`; break;
      case 9: drawing = `<path d="M126 30c-51 8-67 57-35 93 24 27 70 27 94 0 32-36 16-85-35-93z" fill="${color}" stroke="${accent}" stroke-width="7"/><path d="M93 53q33 19 66 0M84 83q42 22 84 0M98 113q28 14 56 0" fill="none" stroke="${accent}" stroke-width="5"/>`; break;
      case 10: drawing = `<circle cx="126" cy="92" r="33" fill="${color}"/>${[0,1,2,3,4,5].map((i) => `<ellipse cx="126" cy="49" rx="14" ry="34" transform="rotate(${i*60} 126 92)" fill="${i%2?accent:color}" stroke="#f9edcf" stroke-width="3"/>`).join("")}<circle cx="126" cy="92" r="13" fill="${accent}"/>`; break;
      default: drawing = `<path d="M126 22l64 42-15 81H77L62 64z" fill="${color}" stroke="${accent}" stroke-width="6"/><path d="M62 64l64 31 64-31M126 95v50" fill="none" stroke="${accent}" stroke-width="6"/>`; break;
    }
    return `<svg class="gm-art-svg" viewBox="0 0 252 176" role="img" aria-label="Illustrated market object"><rect x="7" y="7" width="238" height="162" rx="18" fill="#fbf1d8" stroke="#d7c59f" stroke-width="3"/><path d="M25 143q46-20 91 0t111 0" fill="none" stroke="#e7d8b7" stroke-width="5"/>${drawing}<path d="M22 24h28M202 24h28" stroke="${accent}" stroke-width="4" stroke-linecap="round" opacity=".7"/></svg>`;
  }

  function glyphById(id) { return model.w.glyphs.find((glyph) => glyph.id === id); }
  function allCollected() { return model.notebook.length === model.w.glyphs.length; }
  function pageById(id) { return model.w.pages.find((page) => page.id === id); }
  function ensurePageAssignments() { model.w.pages.forEach((page) => { if (!model.assignments[page.id]) model.assignments[page.id] = {}; }); }
  function event(type, data = {}) { model.events.push({type, ...data}); }
  function setMessage(message, kind = "idle") {
    const node = document.querySelector(".gm-message");
    if (node) { node.textContent = message; node.dataset.kind = kind; }
  }

  function shell(view) {
    const condition = model.state.control_condition || {};
    const mode = model.mode === "full" ? "FULL / DRAG" : "SIMPLIFIED / SELECT";
    return `<section class="gm-shell" data-mode="${model.mode}" data-view="${view}">
      <header class="gm-header"><div><div class="gm-kicker">THE PAPER MARKET · FIELD NOTE ${String(model.state.challenge_id).slice(0, 6).toUpperCase()}</div><h1>Glyph Market Notebook</h1></div><div class="gm-header-right"><span class="gm-mode">${mode}</span><span class="gm-progress">${model.notebook.length}/${model.w.lexicon_size} marks</span></div></header>
      <nav class="gm-nav"><button data-view="map" class="${view === "map" || view === "scene" ? "active" : ""}">MARKET MAP</button><button data-view="notebook" class="${view === "notebook" ? "active" : ""}">NOTEBOOK <b>${model.notebook.length}</b></button><button data-view="validate" class="${view === "validate" ? "active" : ""}>VALIDATE PAGES</button><span class="gm-condition">${condition.difficulty ? `DIFFICULTY ${condition.difficulty}` : "BASELINE"}</span></nav>
      <div class="gm-message" data-kind="idle">${escapeHtml(model.message || "The market is open. Look closely; meanings travel with context.")}</div><main class="gm-main">CONTENT</main>
      <footer class="gm-footer"><span>Invented marks · original illustrations · exact replay</span><span class="readout" data-status="idle">READY</span></footer>
    </section>`;
  }

  function renderMap() {
    const cards = model.w.scenes.map((scene, index) => `<button class="gm-scene-card" data-scene="${index}"><div class="gm-scene-thumb"><span>${escapeHtml(scene.stamp)}</span>${artSvg(scene.spots[0].art, scene.spots[0].variant, "small")}</div><strong>${escapeHtml(scene.title)}</strong><small>${scene.spots.length} marked contexts · ${scene.spots.filter((spot) => model.inspected.has(spot.id)).length} read</small><i>OPEN STALL →</i></button>`).join("");
    return `<section class="gm-map-view"><div class="gm-map-copy"><div class="gm-kicker">A MARKET OF PARTIAL READINGS</div><h2>Find the marks<br><em>where life happens.</em></h2><p>Every stall keeps a small piece of the picture-language. Inspect the marked moments, compare repeated marks across different scenes, and keep a provisional reading in your notebook.</p><div class="gm-legend"><span class="gm-dot amber"></span> context evidence <span class="gm-dot teal"></span> validation illustration</div><button data-view="notebook" class="gm-primary">OPEN NOTEBOOK <span>→</span></button></div><div class="gm-map-grid">${cards}</div></section>`;
  }

  function renderScene() {
    const scene = model.w.scenes[model.sceneIndex];
    const hotspotButtons = scene.spots.map((spot, index) => {
      const read = model.inspected.has(spot.id);
      return `<button class="gm-hotspot ${read ? "read" : ""}" data-spot="${spot.id}" style="left:${spot.x}%;top:${spot.y}%;transform:translate(-50%,-50%) rotate(${spot.rotation}deg)" title="${read ? "Context already recorded" : "Inspect marked context"}">${glyphSvg(glyphById(spot.glyph_id), 39)}<span>${read ? "READ" : `MARK ${String(index + 1).padStart(2, "0")}`}</span></button>`;
    }).join("");
    const proxy = scene.spots.map((spot, index) => `<button class="gm-proxy-row ${model.inspected.has(spot.id) ? "read" : ""}" data-proxy-spot="${spot.id}"><span class="gm-proxy-no">${String(index + 1).padStart(2, "0")}</span><span>${model.inspected.has(spot.id) ? "CONTEXT RECORDED" : "INSPECT MARKED CONTEXT"}</span><b>${model.inspected.has(spot.id) ? "✓" : "＋"}</b></button>`).join("");
    const clues = scene.spots.filter((spot) => model.inspected.has(spot.id)).map((spot, index) => `<article class="gm-clue"><div class="gm-clue-glyph">${glyphSvg(glyphById(spot.glyph_id), 62)}</div><div>${artSvg(spot.art, spot.variant + 1, "small")}</div><div><small>CONTEXT FRAGMENT ${String(index + 1).padStart(2, "0")}</small><p>Same mark, another moment. Compare its shape with the notebook.</p></div></article>`).join("");
    return `<section class="gm-scene-view"><div class="gm-scene-top"><button data-view="map" class="gm-back">← MARKET MAP</button><div><div class="gm-kicker">STALL ${String(model.sceneIndex + 1).padStart(2, "0")} · ${escapeHtml(scene.stamp)}</div><h2>${escapeHtml(scene.title)}</h2></div><span class="gm-scene-count">${scene.spots.filter((spot) => model.inspected.has(spot.id)).length}/${scene.spots.length} contexts</span></div><div class="gm-scene-layout"><div class="gm-diorama"><div class="gm-diorama-sky"></div><div class="gm-diorama-title">${escapeHtml(scene.stamp)} MARKET</div>${scene.spots.map((spot) => `<div class="gm-object" style="left:${spot.x}%;top:${spot.y}%;transform:translate(-50%,-50%) rotate(${spot.rotation}deg) scale(${spot.size})">${artSvg(spot.art, spot.variant, "small")}</div>`).join("")}${hotspotButtons}</div><aside class="gm-inspect-panel"><div class="gm-panel-head"><span>FIELD NOTES</span><small>${model.mode === "full" ? "Click a marked sign in the illustration" : "Use the inspect proxy below"}</small></div><div class="gm-proxy-list">${model.mode === "simplified" ? proxy : `<div class="gm-full-help">The marks are pinned to the illustrated objects. The notebook stays incomplete until every context is read.</div>`}</div><div class="gm-clues">${clues || `<div class="gm-empty">No context recorded yet.<br><span>One small observation can change the whole page.</span></div>`}</div><button class="gm-secondary" data-view="notebook">VIEW NOTEBOOK →</button></aside></div></section>`;
  }

  function renderNotebook() {
    const cards = model.w.glyphs.map((glyph) => {
      const note = model.annotations[glyph.id] || "";
      const collected = model.notebook.includes(glyph.id);
      return `<article class="gm-note-card ${collected ? "collected" : "missing"}" data-note-card="${glyph.id}"><div class="gm-note-mark">${glyphSvg(glyph, 68)}</div><div class="gm-note-body"><div class="gm-note-id">MARK ${String(model.w.glyphs.indexOf(glyph) + 1).padStart(2, "0")} <span>${collected ? "COLLECTED" : "NOT YET SEEN"}</span></div><input data-note-input="${glyph.id}" value="${escapeHtml(note)}" placeholder="a provisional reading…" ${collected ? "" : "disabled"}/><button data-save-note="${glyph.id}" ${collected ? "" : "disabled"}>SAVE NOTE</button></div></article>`;
    }).join("");
    return `<section class="gm-notebook-view"><div class="gm-book-head"><div><div class="gm-kicker">THE NOTEBOOK · PROVISIONAL READINGS</div><h2>Keep the marks close.</h2><p>Write a guess beside every collected mark. A note is allowed to change when a later context disagrees; the page only becomes permanent after the illustrated validation.</p></div><div class="gm-book-stats"><b>${model.notebook.length}<small>/ ${model.w.lexicon_size}</small></b><span>marks collected</span></div></div><div class="gm-notes-grid">${cards}</div><div class="gm-book-actions"><button data-view="map" class="gm-secondary">← RETURN TO MARKET</button><button data-view="validate" class="gm-primary" ${allCollected() ? "" : "disabled"}>TEST ILLUSTRATIONS →</button></div></section>`;
  }

  function renderValidation() {
    ensurePageAssignments();
    const page = model.w.pages[model.pageIndex];
    const assigned = model.assignments[page.id] || {};
    const cards = page.cards.map((card, index) => {
      const glyph = assigned[card.id] ? glyphById(assigned[card.id]) : null;
      const wrong = model.pageError === page.id && glyph && model.expectedMapping && model.expectedMapping[card.id] !== glyph.id;
      return `<div class="gm-validation-card ${glyph ? "assigned" : ""} ${wrong ? "wrong" : ""}" data-card="${card.id}" data-page="${page.id}"><div class="gm-card-number">PLATE ${String(index + 1).padStart(2, "0")}</div>${artSvg(card.art, card.variant, "large")}${glyph ? `<div class="gm-card-assigned">${glyphSvg(glyph, 42)}<span>MARK ATTACHED</span></div>` : `<div class="gm-card-drop">${model.mode === "full" ? "DROP A MARK HERE" : "SELECT A MARK, THEN TAP HERE"}</div>`}</div>`;
    }).join("");
    const chips = model.notebook.map((id) => { const glyph = glyphById(id); const used = Object.values(model.assignments).some((assignments) => Object.values(assignments).includes(id)); return `<button class="gm-match-chip ${used ? "used" : ""}" draggable="${model.mode === "full"}" data-glyph-chip="${id}">${glyphSvg(glyph, 58)}<span>MARK ${String(model.w.glyphs.indexOf(glyph) + 1).padStart(2, "0")}</span></button>`; }).join("");
    const pageTabs = model.w.pages.map((candidate, index) => `<button data-page="${candidate.id}" class="${index === model.pageIndex ? "active" : ""} ${model.validated.has(candidate.id) ? "done" : ""}">PAGE ${String(index + 1).padStart(2, "0")} ${model.validated.has(candidate.id) ? "✓" : ""}</button>`).join("");
    const feedback = model.pageError === page.id ? `<div class="gm-page-feedback error">The illustrations disagree with this reading. Revisit a stall or change a note, then replace the mark.</div>` : model.validated.has(page.id) ? `<div class="gm-page-feedback good">PAGE VALIDATED · the visual correspondence holds.</div>` : `<div class="gm-page-feedback">Fresh illustrations, same ideas. One mark belongs beside each plate.</div>`;
    return `<section class="gm-validation-view"><div class="gm-validation-head"><div><div class="gm-kicker">NOTEBOOK CHECK · ${model.w.pages.length} ILLUSTRATED PAGES</div><h2>Does the market agree?</h2></div><div class="gm-page-tabs">${pageTabs}</div></div>${feedback}<div class="gm-validation-layout"><div class="gm-plates gm-plates-${page.cards.length}">${cards}</div><aside class="gm-match-panel"><div class="gm-panel-head"><span>COLLECTED MARKS</span><small>${model.mode === "full" ? "Drag directly onto a plate" : "Select, then place with a click"}</small></div><div class="gm-match-rail">${chips || `<div class="gm-empty">Collect all marks in the market first.</div>`}</div><button class="gm-secondary" data-clear-page="${page.id}" ${Object.keys(assigned).length ? "" : "disabled"}>CLEAR THIS PAGE</button><button class="gm-primary gm-validate" data-validate-page="${page.id}" ${model.validated.has(page.id) ? "disabled" : ""}>${model.validated.has(page.id) ? "PAGE SEALED" : "VALIDATE PAGE"}</button>${model.pageError === page.id ? `<button class="gm-secondary" data-view="scene">RETURN TO MARKET</button>` : ""}</aside></div>${model.completed ? `<div class="gm-final"><div><span class="gm-kicker">ALL PAGES AGREE</span><h3>The notebook has a readable market.</h3><p>Every collected mark is attached to the right fresh illustration.</p></div><button class="gm-primary" data-submit>SUBMIT NOTEBOOK →</button></div>` : ""}</section>`;
  }

  function redraw(view = model.view) {
    model.view = view;
    const root = document.querySelector(".gm-shell");
    if (!root) return;
    root.outerHTML = shell(view);
    const next = document.querySelector(".gm-shell");
    const content = next.querySelector(".gm-main");
    content.innerHTML = view === "map" ? renderMap() : view === "scene" ? renderScene() : view === "notebook" ? renderNotebook() : renderValidation();
    bind();
  }

  function inspect(spotId, source) {
    const scene = model.w.scenes[model.sceneIndex];
    const spot = scene.spots.find((candidate) => candidate.id === spotId);
    if (!spot || model.inspected.has(spotId)) return;
    model.inspected.add(spotId);
    if (!model.notebook.includes(spot.glyph_id)) model.notebook.push(spot.glyph_id);
    event("inspect", {spot_id: spotId, glyph_id: spot.glyph_id, source});
    model.message = "Context recorded. Compare this mark with its other appearances.";
    redraw("scene");
  }

  function saveNote(id) {
    const input = document.querySelector(`[data-note-input="${CSS.escape(id)}"]`);
    const note = input?.value.trim();
    if (!note || !model.notebook.includes(id)) return;
    model.annotations[id] = note;
    event("annotate", {glyph_id: id, text: note, source: "notebook_input"});
    model.message = "Provisional note saved. A later page may ask you to revise it.";
    setMessage(model.message);
  }

  function assign(pageId, cardId, glyphId, source) {
    if (!model.notebook.includes(glyphId) || !pageById(pageId)) return;
    model.assignments[pageId] = model.assignments[pageId] || {};
    model.assignments[pageId][cardId] = glyphId;
    model.pageError = null;
    event("match", {page_id: pageId, card_id: cardId, glyph_id: glyphId, source});
    model.message = "Mark placed. Read the whole plate before sealing the page.";
    redraw("validate");
  }

  function validatePage(pageId) {
    const page = pageById(pageId);
    const actual = model.assignments[pageId] || {};
    const expected = model.expectedMapping || {};
    const pageExpected = Object.fromEntries(page.cards.map((card) => [card.id, expected[card.id]]));
    const passed = page.cards.length === Object.keys(actual).length && page.cards.every((card) => actual[card.id] === pageExpected[card.id]);
    event("validate_page", {page_id: pageId, passed});
    if (!passed) {
      model.pageError = pageId;
      model.message = "The page disagrees with this reading. Change a mark or return to a stall.";
      redraw("validate");
      return;
    }
    model.validated.add(pageId);
    model.pageError = null;
    if (model.validated.size === model.w.pages.length) {
      model.completed = true;
      model.message = "All pages agree. The notebook is ready to submit.";
      redraw("validate");
    } else {
      model.pageIndex = Math.min(model.w.pages.length - 1, model.pageIndex + 1);
      model.message = "Page sealed. The next illustration asks for another correspondence.";
      redraw("validate");
    }
  }

  async function submit() {
    if (model.submitting) return;
    model.submitting = true;
    const payload = {mechanic_id: model.state.mechanic_id, task_id: model.state.task_id, challenge_id: model.state.challenge_id, events: clone(model.events), inspected_spot_ids: Array.from(model.inspected).sort(), annotations: clone(model.annotations), assignments: clone(model.assignments), validated_pages: Array.from(model.validated).sort(), completed: model.completed === true};
    try {
      const response = await (await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)})).json();
      if (response.passed === true) {
        model.submitting = false;
        model.message = "PASS · every page agrees with the market vocabulary.";
        document.querySelector(".readout").textContent = "PASS";
        document.querySelector(".readout").dataset.status = "passed";
        setMessage(model.message, "good");
      } else if (response.state) {
        await window.WeirdCaptchaMechanics.glyph_market_notebook.render(response.state, window.__glyphHelpers);
      } else {
        model.submitting = false;
        model.message = "Grade unavailable. Try the validation again.";
        setMessage(model.message, "error");
      }
    } catch (_error) {
      model.submitting = false;
      setMessage("Connection interrupted. The notebook is still here; retry submit.", "error");
    }
  }

  function bind() {
    document.querySelectorAll("button[data-view]").forEach((node) => node.addEventListener("click", () => redraw(node.dataset.view)));
    document.querySelectorAll("[data-scene]").forEach((node) => node.addEventListener("click", () => { model.sceneIndex = Number(node.dataset.scene); event("navigate", {scene_id: model.w.scenes[model.sceneIndex].id}); redraw("scene"); }));
    document.querySelectorAll("[data-spot]").forEach((node) => node.addEventListener("click", () => inspect(node.dataset.spot, "hotspot_click")));
    document.querySelectorAll("[data-proxy-spot]").forEach((node) => node.addEventListener("click", () => inspect(node.dataset.proxySpot, "inspect_proxy")));
    document.querySelectorAll("[data-save-note]").forEach((node) => node.addEventListener("click", () => saveNote(node.dataset.saveNote)));
    document.querySelectorAll("[data-page]").forEach((node) => node.addEventListener("click", () => { model.pageIndex = model.w.pages.findIndex((page) => page.id === node.dataset.page); redraw("validate"); }));
    document.querySelectorAll("[data-clear-page]").forEach((node) => node.addEventListener("click", () => { const page = pageById(node.dataset.clearPage); Object.keys(model.assignments[page.id] || {}).forEach((cardId) => event("clear_match", {page_id: page.id, card_id: cardId})); model.assignments[page.id] = {}; model.pageError = null; redraw("validate"); }));
    document.querySelectorAll("[data-validate-page]").forEach((node) => node.addEventListener("click", () => validatePage(node.dataset.validatePage)));
    document.querySelectorAll("[data-submit]").forEach((node) => node.addEventListener("click", submit));
    document.querySelectorAll("[data-glyph-chip]").forEach((chip) => {
      chip.addEventListener("dragstart", (eventObject) => { model.dragGlyph = chip.dataset.glyphChip; eventObject.dataTransfer.setData("text/plain", model.dragGlyph); });
      chip.addEventListener("click", () => { if (model.mode === "simplified") { model.selectedGlyph = chip.dataset.glyphChip; document.querySelectorAll("[data-glyph-chip]").forEach((item) => item.classList.toggle("selected", item === chip)); setMessage("Mark selected. Place it beside the matching illustration."); } });
    });
    document.querySelectorAll("[data-card]").forEach((card) => {
      card.addEventListener("dragover", (eventObject) => { if (model.mode === "full") eventObject.preventDefault(); });
      card.addEventListener("drop", (eventObject) => { eventObject.preventDefault(); const id = eventObject.dataTransfer.getData("text/plain") || model.dragGlyph; if (id) assign(card.dataset.page, card.dataset.card, id, "drag_match"); });
      card.addEventListener("click", () => { if (model.mode === "simplified" && model.selectedGlyph) { assign(card.dataset.page, card.dataset.card, model.selectedGlyph, "select_match"); model.selectedGlyph = null; } });
    });
  }

  async function render(state, helpers) {
    window.__glyphHelpers = helpers;
    model = {state, w: state.world, mode: state.control_condition?.interaction || "full", view: "map", sceneIndex: 0, notebook: [], inspected: new Set(), annotations: {}, assignments: {}, validated: new Set(), events: [], expectedMapping: {}, selectedGlyph: null, dragGlyph: null, pageIndex: 0, pageError: null, completed: false, submitting: false, message: "The market is open. Look closely; meanings travel with context."};
    // The browser gets the art needed to render; the expected mapping comes
    // from the same visible glyph/art correspondence used by the solver.
    model.w.pages.forEach((page) => page.cards.forEach((card) => {
      const spot = model.w.scenes.flatMap((scene) => scene.spots).find((candidate) => candidate.art === card.art);
      if (spot) model.expectedMapping[card.id] = spot.glyph_id;
    }));
    window.glyphMarketNotebookModel = model;
    document.body.dataset.mechanic = "glyph-market-notebook";
    helpers.app.innerHTML = shell("map");
    document.querySelector(".gm-main").innerHTML = renderMap();
    bind();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.glyph_market_notebook = {rootSelector: ".gm-shell", render};
})();
