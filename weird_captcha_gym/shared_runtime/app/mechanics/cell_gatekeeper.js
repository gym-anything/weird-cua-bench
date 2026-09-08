(() => {
  "use strict";

  let cleanup = null;
  const clone = (value) => JSON.parse(JSON.stringify(value));

  function byId(state) {
    return Object.fromEntries((state.protein_catalog || []).map((item) => [String(item.id), item]));
  }

  function move(counts, species, source, target, capacity) {
    if (counts[species][source] <= 0 || counts[species][target] >= capacity) return false;
    counts[species][source] -= 1;
    counts[species][target] += 1;
    return true;
  }

  function advance(sim, state, ticks) {
    const params = state.parameters;
    const catalog = byId(state);
    const capacity = Number(state.surface.capacity);
    for (let step = 0; step < ticks && sim.status === "active"; step += 1) {
      sim.tick += 1;
      sim.slots.forEach((proteinId, slot) => {
        if (!proteinId) return;
        const protein = catalog[proteinId];
        if (!protein || protein.kind === "decoy") return;
        const species = String(protein.species);
        if (protein.kind === "leak") {
          const period = Math.max(1, Number(params.passive_period));
          if ((sim.tick + slot) % period !== 0) return;
          const counts = sim.counts[species];
          const source = counts.outside >= counts.inside ? "outside" : "inside";
          const target = source === "outside" ? "inside" : "outside";
          if (move(sim.counts, species, source, target, capacity)) {
            sim.crossings.passive[proteinId] = (sim.crossings.passive[proteinId] || 0) + 1;
            sim.last_crossing = `${protein.short} · passive ${source} → ${target}`;
          }
        }
      });
      const period = Math.max(1, Number(params.pump_period));
      if (sim.tick % period === 0) {
        const pumps = sim.slots.map((proteinId, slot) => ({proteinId, slot, protein: proteinId ? catalog[proteinId] : null})).filter((item) => item.protein?.kind === "pump");
        if (pumps.length && sim.atp >= pumps.length) {
          for (const item of pumps) {
            const protein = item.protein;
            const species = String(protein.species);
            const source = protein.direction === "inside_to_outside" ? "inside" : "outside";
            const target = source === "inside" ? "outside" : "inside";
            if (move(sim.counts, species, source, target, capacity)) {
              sim.atp -= 1;
              sim.crossings.active[item.proteinId] = (sim.crossings.active[item.proteinId] || 0) + 1;
              sim.last_crossing = `${protein.short} · ATP ${source} → ${target}`;
            }
          }
        }
      }
      if (sim.tick >= Number(params.max_ticks)) {
        sim.status = "timeout";
        break;
      }
      if (baseGoalOK(sim, state)) sim.stable_ticks = Number(sim.stable_ticks || 0) + 1;
      else sim.stable_ticks = 0;
    }
  }

  function baseGoalOK(sim, state) {
    for (const [speciesId, target] of Object.entries(state.goal || {})) {
      const counts = sim.counts[speciesId] || {};
      for (const side of ["outside", "inside"]) {
        if (Number(counts[side]) < Number(target[side][0]) || Number(counts[side]) > Number(target[side][1])) return false;
      }
    }
    const catalog = byId(state);
    const installed = new Set(sim.installed_history || []);
    for (const proteinId of state.required_proteins || []) {
      if (!installed.has(proteinId)) return false;
      const protein = catalog[proteinId];
      if (protein.kind === "pump" && Number(sim.crossings.active[proteinId] || 0) < Number(state.parameters.pump_cycles)) return false;
      if (protein.kind === "leak" && Number(sim.crossings.passive[proteinId] || 0) < 1) return false;
    }
    for (const proteinId of sim.slots) {
      if (proteinId && catalog[proteinId]?.kind === "leak" && (state.required_proteins || []).includes(proteinId)) return false;
    }
    return true;
  }

  function goalOK(sim, state) {
    return baseGoalOK(sim, state) && Number(sim.stable_ticks || 0) >= Number(state.parameters.observation_ticks || 0);
  }

  function render(state, helpers) {
    if (cleanup) cleanup();
    const mode = state.control_condition?.interaction || "full";
    const timeMode = new URLSearchParams(window.location.search).get("time_mode") === "paused" ? "paused" : "live";
    const observationLabel = timeMode === "paused" ? "PAUSED OBSERVATION" : "LIVE CLOCK";
    const initialTrace = timeMode === "paused"
      ? "Transport advances during each observation window · inspect the bars after every intervention."
      : "Particles evolve continuously · inspect the bars after every intervention.";
    const atpBatch = Math.max(1, Number(state.parameters.atp_batch || 1));
    const catalog = byId(state);
    const model = {
      state,
      mode,
      timeMode,
      sim: clone(state.initial_state),
      events: [],
      start: performance.now(),
      drag: null,
      terminal: false,
      submitting: false,
      raf: 0,
      flash: "",
    };
    window.cellGatekeeperModel = model;
    document.body.dataset.mechanic = "cell-gatekeeper";

    const recipe = (state.recipe || []).map((item) => {
      const protein = catalog[item.protein_id];
      return `<li data-recipe="${item.protein_id}"><span class="recipe-dot" style="--protein:${protein.color}"></span><b>${protein.short}</b><span>${item.instruction}</span></li>`;
    }).join("");
    const slotOptions = Array.from({length: Number(state.slot_count)}, (_, index) => `<option value="${index}">SLOT ${index + 1}</option>`).join("");
    const proteinCards = (state.protein_catalog || []).map((protein) => `
      <article class="protein-card ${protein.kind === "decoy" ? "is-decoy" : ""}" data-protein="${protein.id}" style="--protein:${protein.color}">
        <div class="protein-glyph">${protein.kind === "pump" ? "⇄" : protein.kind === "leak" ? "↔" : "×"}</div>
        <div class="protein-copy"><strong>${protein.label}</strong><small>${protein.rule}</small></div>
        ${mode === "full" ? "" : `<label class="proxy-slot"><span>DROP</span><select data-place-slot="${protein.id}" aria-label="Drop ${protein.label} into slot">${slotOptions}</select></label>`}
        <button class="proxy-place" data-place="${protein.id}" ${mode === "full" ? "hidden" : ""}>PLACE</button>
      </article>`).join("");
    const speciesRows = (state.species || []).map((species) => {
      const sid = species.id;
      const target = state.goal[sid];
      return `<div class="solute-row" style="--solute:${species.color}" data-species-row="${sid}">
        <div class="solute-name"><i class="solute-mark">${species.short.slice(0, 1)}</i><b>${species.label}</b></div>
        <div class="solute-target">OUT ${target.outside[0]}–${target.outside[1]} · IN ${target.inside[0]}–${target.inside[1]}</div>
        <div class="solute-actions ${mode === "full" ? "drag-actions" : "proxy-actions"}">
          ${mode === "full" ? `<span class="solute-token" data-solute="${sid}" data-delta="1">DRAG +1</span><span class="solute-token drain-token" data-solute="${sid}" data-delta="-1">DRAG −1</span>` : `<button data-adjust="${sid}" data-side="outside" data-delta="1">OUT +</button><button data-adjust="${sid}" data-side="outside" data-delta="-1">OUT −</button><button data-adjust="${sid}" data-side="inside" data-delta="1">IN +</button><button data-adjust="${sid}" data-side="inside" data-delta="-1">IN −</button>`}
        </div>
      </div>`;
    }).join("");
    const slots = Array.from({length: Number(state.slot_count)}, (_, index) => `<button class="membrane-slot" data-slot="${index}" aria-label="Membrane slot ${index + 1}"><span>${index + 1}</span><b>EMPTY</b><em class="slot-eject" data-eject-slot="${index}" ${mode === "full" ? "hidden" : ""}>EJECT</em></button>`).join("");
    const bars = (state.species || []).map((species) => {
      const sid = species.id;
      return `<div class="bar-card" data-bar-card="${sid}" style="--solute:${species.color}">
        <div class="bar-label"><span>${species.short}</span><small data-band-label="${sid}">target band</small></div>
        <div class="bar-pair"><div class="bar-side"><small>OUT</small><div class="bar-track"><span class="bar-band" data-bar-band="${sid}-outside" aria-hidden="true"></span><i data-bar-fill="${sid}-outside"></i></div><b class="bar-number" data-bar-number="${sid}-outside">0</b></div><div class="bar-side"><small>IN</small><div class="bar-track"><span class="bar-band" data-bar-band="${sid}-inside" aria-hidden="true"></span><i data-bar-fill="${sid}-inside"></i></div><b class="bar-number" data-bar-number="${sid}-inside">0</b></div></div>
      </div>`;
    }).join("");

    helpers.app.innerHTML = `
      <section class="cell-gatekeeper" data-mode="${mode}" data-interaction="${mode}">
        <header class="cg-header">
          <div><p class="cg-kicker">BIOLOGICAL SYSTEMS / CONTROL DESK 04</p><h1>Cell Gatekeeper</h1><p class="cg-prompt">${state.prompt}</p></div>
          <div class="cg-meta"><span class="cg-chip">${mode.toUpperCase()} INPUT</span><span class="cg-chip">${observationLabel}</span><strong data-tick>t+000</strong></div>
        </header>
        <div class="cg-layout">
          <main class="cg-main">
            <section class="cg-card cg-goal">
              <div class="cg-section-head"><span>01 / TARGET LOCK</span><b data-goal-state>UNSTABLE</b></div>
              <p>Every concentration pair must sit inside its amber band for the visible hold window. A pump consumes ATP; a leak keeps diffusing until it is ejected.</p>
              <ol class="recipe-list">${recipe}</ol>
            </section>
            <section class="cg-card cg-stage-card">
              <div class="cg-section-head"><span>02 / MEMBRANE WINDOW</span><b data-crossing>NO CROSSING YET</b></div>
              <div class="cg-stage">
                <canvas class="cg-canvas" width="900" height="430"></canvas>
                <div class="compartment-tag outside-tag">OUTSIDE<br><small>extracellular</small></div><div class="compartment-tag inside-tag">INSIDE<br><small>cytoplasm</small></div>
                <div class="slot-rail">${slots}</div>
                <div class="compartment-drop outside-drop" data-side="outside">DROP SOLUTE<br><small>OUTSIDE</small></div>
                <div class="compartment-drop inside-drop" data-side="inside">DROP SOLUTE<br><small>INSIDE</small></div>
              </div>
              <div class="crossing-strip"><span>TRANSPORT TRACE</span><b data-trace>${initialTrace}</b></div>
            </section>
            <section class="cg-card cg-bars"><div class="cg-section-head"><span>03 / CONCENTRATION BARS</span><b>CAPACITY ${state.surface.capacity}</b></div>${bars}</section>
          </main>
          <aside class="cg-side">
            <section class="cg-card cg-toolbox"><div class="cg-section-head"><span>04 / PROTEIN DRAWER</span><b>${mode === "full" ? "DRAG TO SLOT" : "CLICK PLACE"}</b></div><div class="protein-list">${proteinCards}</div><div class="eject-zone" data-eject-zone ${mode === "full" ? "" : "hidden"}>DRAG A MEMBRANE PROTEIN HERE TO EJECT</div></section>
            <section class="cg-card cg-solutes"><div class="cg-section-head"><span>05 / SOLUTE ADJUSTERS</span><b>${mode === "full" ? "DRAG TOKENS" : "BUTTON PROXY"}</b></div>${speciesRows}<p class="tool-note">Add or remove one visible particle at a time. Use this only as a calibration control; the transporter transcript still matters.</p></section>
            <section class="cg-card cg-atp"><div class="cg-section-head"><span>06 / ATP RESERVOIR</span><b data-atp>0 UNITS</b></div><div class="atp-gauge"><i data-atp-fill></i><span data-atp-lamp>UNFUELED</span></div>${mode === "full" ? `<div class="atp-token" data-atp-token>DRAG ATP BURST (+${atpBatch}) INTO THE WELL</div>` : `<button class="supply-button" data-supply>SUPPLY ATP BURST (+${atpBatch})</button>`}</section>
            <section class="cg-card cg-ledger"><div class="cg-section-head"><span>07 / CROSSING LEDGER</span><b data-ledger-count>0 EVENTS</b></div><div class="ledger-lines" data-ledger-lines><span>Waiting for a membrane event.</span></div></section>
          </aside>
        </div>
        <footer class="cg-footer"><div class="cg-status"><span class="readout" data-status="idle">READY</span><small>Do not lock until the bars hold inside their bands for the visible observation window.</small></div><button class="new-cell" data-new>NEW CELL</button><button class="lock-button" data-lock>LOCK GRADIENT</button><div class="cg-verdict" data-verdict></div></footer>
      </section>`;

    const canvas = document.querySelector(".cg-canvas");
    const ctx = canvas.getContext("2d");
    const tickMs = 100;
    const setFlash = (message, status = "error") => {
      model.flash = message;
      helpers.setReadout(message, status);
    };

    function record(type, data, mutate) {
      if (model.terminal || model.submitting) return false;
      sync();
      const event = Object.assign({seq: model.events.length + 1, type, tick: model.sim.tick}, data || {});
      model.events.push(event);
      if (mutate) mutate();
      if (type !== "certify") model.sim.stable_ticks = 0;
      update();
      return true;
    }

    function sync() {
      if (model.terminal || model.submitting) return;
      const target = Math.min(Number(state.parameters.max_ticks), Math.max(model.sim.tick, Math.floor((performance.now() - model.start) / tickMs + 1e-7)));
      if (target > model.sim.tick) advance(model.sim, state, target - model.sim.tick);
      update();
    }

    function install(proteinId, slot, source) {
      if (model.sim.slots[slot] != null) return setFlash("SLOT OCCUPIED · choose an empty slot");
      if (!catalog[proteinId]) return setFlash("UNKNOWN PROTEIN");
      record("install", {slot, protein_id: proteinId, input_source: source}, () => {
        model.sim.slots[slot] = proteinId;
        model.sim.installed_history.push(proteinId);
        setFlash(`${catalog[proteinId].short.toUpperCase()} INSTALLED`, "idle");
      });
    }

    function remove(slot, source) {
      if (model.sim.slots[slot] == null) return setFlash("EMPTY SLOT");
      const proteinId = model.sim.slots[slot];
      record("remove", {slot, input_source: source}, () => {
        model.sim.removed_history.push(proteinId);
        model.sim.slots[slot] = null;
        setFlash(`${catalog[proteinId].short.toUpperCase()} EJECTED`, "idle");
      });
    }

    function adjust(species, side, delta, source) {
      if (model.sim.counts[species][side] + delta < 0 || model.sim.counts[species][side] + delta > Number(state.surface.capacity)) return setFlash("CHAMBER CAPACITY LIMIT");
      record("solute", {species, side, delta, input_source: source}, () => {
        model.sim.counts[species][side] += delta;
        setFlash(`${species.toUpperCase()} ${side.toUpperCase()} ${delta > 0 ? "+1" : "−1"}`, "idle");
      });
    }

    function supply(amount, source) {
      record("atp", {amount, input_source: source}, () => {
        model.sim.atp += amount;
        setFlash(`ATP +${amount}`, "idle");
      });
    }

    function update() {
      const sim = model.sim;
      const goal = goalOK(sim, state);
      const tickNode = document.querySelector("[data-tick]");
      if (tickNode) tickNode.textContent = `t+${String(sim.tick).padStart(3, "0")}`;
      const goalNode = document.querySelector("[data-goal-state]");
      const baseReady = baseGoalOK(sim, state);
      const holdTicks = Number(state.parameters.observation_ticks || 0);
      const stableTicks = Math.min(holdTicks, Number(sim.stable_ticks || 0));
      if (goalNode) {
        goalNode.textContent = goal ? "READY TO LOCK" : baseReady ? `HOLD ${stableTicks}/${holdTicks}` : "UNSTABLE";
        goalNode.className = goal ? "is-good" : "";
      }
      const atpNode = document.querySelector("[data-atp]");
      if (atpNode) atpNode.textContent = `${sim.atp} UNITS`;
      const atpFill = document.querySelector("[data-atp-fill]");
      if (atpFill) atpFill.style.width = `${Math.min(100, sim.atp * 7)}%`;
      const lamp = document.querySelector("[data-atp-lamp]");
      if (lamp) lamp.textContent = sim.atp ? "FUELED" : "UNFUELED";
      (state.species || []).forEach((species) => {
        const sid = species.id;
        ["outside", "inside"].forEach((side) => {
          const value = Number(sim.counts[sid][side]);
          const fill = document.querySelector(`[data-bar-fill="${sid}-${side}"]`);
          const number = document.querySelector(`[data-bar-number="${sid}-${side}"]`);
          if (fill) fill.style.width = `${(value / Number(state.surface.capacity)) * 100}%`;
          if (number) number.textContent = state.parameters.numeric_readout ? value : "—";
        });
      });
      (state.species || []).forEach((species) => {
        const sid = species.id;
        const capacity = Number(state.surface.capacity);
        const target = state.goal[sid];
        ["outside", "inside"].forEach((side) => {
          const low = Number(target[side][0]);
          const high = Number(target[side][1]);
          const band = document.querySelector(`[data-bar-band="${sid}-${side}"]`);
          if (band) {
            band.style.left = `${(low / capacity) * 100}%`;
            band.style.width = `${((high - low + 1) / capacity) * 100}%`;
            band.setAttribute("aria-label", `target ${low} to ${high}`);
          }
        });
        const label = document.querySelector(`[data-band-label="${sid}"]`);
        if (label) label.textContent = `OUT ${target.outside[0]}–${target.outside[1]} · IN ${target.inside[0]}–${target.inside[1]}`;
      });
      document.querySelectorAll(".membrane-slot").forEach((node) => {
        const id = sim.slots[Number(node.dataset.slot)];
        node.classList.toggle("occupied", Boolean(id));
        node.dataset.protein = id || "";
        const b = node.querySelector("b");
        const eject = node.querySelector(".slot-eject");
        if (b) b.textContent = id ? catalog[id].short.toUpperCase() : "EMPTY";
        if (eject) eject.hidden = mode === "full" || !id;
      });
      document.querySelectorAll("[data-place-slot]").forEach((select) => {
        const selected = Number(select.value);
        [...select.options].forEach((option) => {
          option.disabled = Boolean(sim.slots[Number(option.value)]);
        });
        if (sim.slots[selected]) {
          const available = [...select.options].find((option) => !option.disabled);
          if (available) select.value = available.value;
        }
      });
      (state.required_proteins || []).forEach((id) => {
        const row = document.querySelector(`[data-recipe="${id}"]`);
        if (!row) return;
        const protein = catalog[id];
        const installed = (sim.installed_history || []).includes(id);
        const passive = Number(sim.crossings.passive[id] || 0);
        const active = Number(sim.crossings.active[id] || 0);
        row.classList.toggle("done", installed && (protein.kind === "leak" ? passive >= 1 : active >= Number(state.parameters.pump_cycles)) && (protein.kind !== "leak" || !sim.slots.includes(id)));
      });
      const crossing = document.querySelector("[data-crossing]");
      if (crossing) crossing.textContent = sim.last_crossing ? "CROSSING DETECTED" : "NO CROSSING YET";
      const trace = document.querySelector("[data-trace]");
      if (trace) trace.textContent = sim.last_crossing || (model.timeMode === "paused"
        ? "Transport advances during each observation window · inspect the bars after every intervention."
        : "Particles evolve continuously · inspect the bars after every intervention.");
      const ledger = document.querySelector("[data-ledger-count]");
      if (ledger) ledger.textContent = `${model.events.length} EVENTS`;
      const lines = document.querySelector("[data-ledger-lines]");
      if (lines) {
        const entries = [];
        Object.entries(sim.crossings.passive).forEach(([id, count]) => entries.push(`<span>PASSIVE <b>${catalog[id]?.short || id}</b> ×${count}</span>`));
        Object.entries(sim.crossings.active).forEach(([id, count]) => entries.push(`<span>ATP <b>${catalog[id]?.short || id}</b> ×${count}</span>`));
        lines.innerHTML = entries.length ? entries.slice(-5).join("") : "<span>Waiting for a membrane event.</span>";
      }
      draw();
    }

    function draw() {
      const width = canvas.width;
      const height = canvas.height;
      const theme = Number(state.surface.theme || 0);
      const bg = ["#081824", "#101b2c", "#0b2024", "#171a2d", "#0d1d28", "#172117"][theme % 6];
      ctx.fillStyle = bg; ctx.fillRect(0, 0, width, height);
      const split = Number(state.surface.membrane_x);
      const left = ctx.createLinearGradient(0, 0, split, height); left.addColorStop(0, "#143244"); left.addColorStop(1, "#102631");
      const right = ctx.createLinearGradient(split, 0, width, height); right.addColorStop(0, "#152e35"); right.addColorStop(1, "#233a31");
      ctx.fillStyle = left; ctx.fillRect(0, 0, split - 16, height);
      ctx.fillStyle = right; ctx.fillRect(split + 16, 0, width - split - 16, height);
      ctx.fillStyle = "rgba(255,255,255,.045)";
      for (let y = 22; y < height; y += 26) { ctx.fillRect(18, y, split - 42, 1); ctx.fillRect(split + 36, y, width - split - 56, 1); }
      ctx.fillStyle = "rgba(255,206,131,.18)"; ctx.fillRect(split - 16, 0, 32, height);
      ctx.strokeStyle = "#e4bf83"; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(split - 9, 0); ctx.lineTo(split - 9, height); ctx.moveTo(split + 9, 0); ctx.lineTo(split + 9, height); ctx.stroke();
      for (let y = 10; y < height; y += 26) { ctx.fillStyle = "#d9a56e"; ctx.beginPath(); ctx.arc(split - 9, y + Math.sin(y + model.sim.tick * .2) * 2, 4, 0, Math.PI * 2); ctx.fill(); ctx.beginPath(); ctx.arc(split + 9, y + Math.cos(y + model.sim.tick * .2) * 2, 4, 0, Math.PI * 2); ctx.fill(); }
      (state.species || []).forEach((species, speciesIndex) => {
        const sid = species.id;
        const color = species.color;
        ["outside", "inside"].forEach((side) => {
          const count = Number(model.sim.counts[sid][side]);
          const baseX = side === "outside" ? 28 : split + 28;
          const span = side === "outside" ? split - 64 : width - split - 54;
          const cap = Math.min(count, 28);
          for (let i = 0; i < cap; i += 1) {
            const seed = Number(state.surface.particle_seed) + speciesIndex * 101 + i * 37;
            const x = baseX + ((seed + i * 43 + model.sim.tick * (0.9 + speciesIndex * .16)) % Math.max(50, span));
            const y = 54 + ((seed * 1.71 + i * 29 + Math.sin(model.sim.tick * .08 + i) * 18) % (height - 74));
            ctx.fillStyle = color; ctx.globalAlpha = .56 + ((i % 3) * .14);
            if (species.shape === "diamond") { ctx.save(); ctx.translate(x, y); ctx.rotate(Math.PI / 4); ctx.fillRect(-4, -4, 8, 8); ctx.restore(); }
            else if (species.shape === "hex") { ctx.beginPath(); for (let k = 0; k < 6; k += 1) { const a = k * Math.PI / 3; const px = x + Math.cos(a) * 5; const py = y + Math.sin(a) * 5; k ? ctx.lineTo(px, py) : ctx.moveTo(px, py); } ctx.closePath(); ctx.fill(); }
            else { ctx.beginPath(); ctx.arc(x, y, 4.5, 0, Math.PI * 2); ctx.fill(); }
            ctx.globalAlpha = 1;
          }
        });
      });
      ctx.fillStyle = "rgba(228,191,131,.8)"; ctx.font = "700 10px ui-monospace,monospace"; ctx.fillText(`TASK CLOCK ${String(model.sim.tick).padStart(3, "0")}`, 24, height - 17); ctx.fillText(`ATP ${model.sim.atp}`, width - 90, height - 17);
    }

    function finishRequest(passed, response) {
      if (passed) {
        model.terminal = true;
        const verdict = document.querySelector("[data-verdict]");
        if (verdict) verdict.textContent = "MEMBRANE LOCKED · PASS";
        helpers.setReadout("PASS · GRADIENT HELD", "passed");
      } else if (response?.state) {
        const next = response.state;
        helpers.render(next).then(() => helpers.setReadout("FAIL · FRESH CELL", "error"));
      } else {
        model.submitting = false;
        helpers.setReadout("FAIL · RETRY", "error");
      }
    }

    async function lock(forceFailure = false) {
      sync();
      if (model.submitting || model.terminal) return;
      const accepted = goalOK(model.sim, state);
      record("certify", {accepted: forceFailure ? false : accepted, input_source: "lock_button"});
      model.submitting = true;
      helpers.setReadout("REPLAYING TRANSPORT…", "idle");
      try {
        const response = await (await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({mechanic_id: state.mechanic_id, task_id: state.task_id, challenge_id: state.challenge_id, interaction_mode: mode, events: model.events, terminal_tick: model.sim.tick, final_state: clone(model.sim), completed: !forceFailure && accepted})})).json();
        finishRequest(response.passed === true, response);
      } catch (_error) {
        model.submitting = false;
        helpers.setReadout("LINK UNAVAILABLE · RETRY", "error");
      }
    }

    const onPointerUp = (event) => {
      if (!model.drag) return;
      const dragged = model.drag; model.drag = null; document.body.classList.remove("cg-dragging");
      const target = document.elementFromPoint(event.clientX, event.clientY);
      if (dragged.kind === "protein") {
        const slot = target?.closest?.("[data-slot]");
        if (slot) install(dragged.proteinId, Number(slot.dataset.slot), "protein_drag"); else setFlash("DROP THE PROTEIN ON A MEMBRANE SLOT");
      } else if (dragged.kind === "slot") {
        if (target?.closest?.("[data-eject-zone]")) remove(dragged.slot, "protein_drag"); else setFlash("DRAG THE PROTEIN TO THE EJECT DOCK");
      } else if (dragged.kind === "solute") {
        const zone = target?.closest?.("[data-side]");
        if (zone) adjust(dragged.species, zone.dataset.side, dragged.delta, "solute_drag"); else setFlash("DROP THE PARTICLE IN A COMPARTMENT");
      } else if (dragged.kind === "atp") {
        if (target?.closest?.("[data-atp-token]") || target?.closest?.(".cg-atp")) supply(atpBatch, "atp_drag"); else setFlash("DROP ATP INTO THE FUEL WELL");
      }
    };
    const onPointerCancel = () => { model.drag = null; document.body.classList.remove("cg-dragging"); };

    if (mode === "full") {
      document.querySelectorAll("[data-protein]").forEach((node) => node.addEventListener("pointerdown", (event) => {
        if (event.button !== 0 || node.classList.contains("membrane-slot")) return;
        model.drag = {kind: "protein", proteinId: node.dataset.protein}; document.body.classList.add("cg-dragging"); event.preventDefault();
      }));
      document.querySelectorAll(".membrane-slot").forEach((node) => node.addEventListener("pointerdown", (event) => {
        const slot = Number(node.dataset.slot); if (!model.sim.slots[slot] || event.button !== 0) return;
        model.drag = {kind: "slot", slot}; document.body.classList.add("cg-dragging"); event.preventDefault();
      }));
      document.querySelectorAll(".solute-token").forEach((node) => node.addEventListener("pointerdown", (event) => { if (event.button !== 0) return; model.drag = {kind: "solute", species: node.dataset.solute, delta: Number(node.dataset.delta)}; document.body.classList.add("cg-dragging"); event.preventDefault(); }));
      document.querySelector("[data-atp-token]")?.addEventListener("pointerdown", (event) => { if (event.button !== 0) return; model.drag = {kind: "atp"}; document.body.classList.add("cg-dragging"); event.preventDefault(); });
      document.addEventListener("pointerup", onPointerUp);
      document.addEventListener("pointercancel", onPointerCancel);
    } else {
      document.querySelectorAll("[data-place]").forEach((node) => node.addEventListener("click", () => {
        const selector = document.querySelector(`[data-place-slot="${node.dataset.place}"]`);
        const slot = selector ? Number(selector.value) : model.sim.slots.findIndex((value) => value == null);
        if (slot < 0 || model.sim.slots[slot] != null) return setFlash("CHOOSE AN EMPTY MEMBRANE SLOT");
        install(node.dataset.place, slot, "protein_button");
      }));
      document.querySelectorAll("[data-eject-slot]").forEach((node) => node.addEventListener("click", () => remove(Number(node.dataset.ejectSlot), "protein_button")));
      document.querySelectorAll("[data-adjust]").forEach((node) => node.addEventListener("click", () => adjust(node.dataset.adjust, node.dataset.side, Number(node.dataset.delta), "solute_button")));
      document.querySelector("[data-supply]")?.addEventListener("click", () => supply(atpBatch, "atp_button"));
    }
    document.querySelector("[data-lock]")?.addEventListener("click", () => lock(false));
    document.querySelector("[data-new]")?.addEventListener("click", () => lock(true));
    window.addEventListener("blur", onPointerCancel);
    function frame() { sync(); model.raf = requestAnimationFrame(frame); }
    update(); model.raf = requestAnimationFrame(frame);
    cleanup = () => { cancelAnimationFrame(model.raf); model.terminal = true; document.removeEventListener("pointerup", onPointerUp); document.removeEventListener("pointercancel", onPointerCancel); window.removeEventListener("blur", onPointerCancel); };
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.cell_gatekeeper = {rootSelector: ".cell-gatekeeper", render};
})();
