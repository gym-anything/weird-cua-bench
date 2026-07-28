(() => {
  "use strict";

  let model = null;
  const esc = (value) => String(value == null ? "" : value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");

  function record(kind, details = {}) {
    const event = {
      sequence: model.events.length + 1,
      kind,
      elapsed_ms: Math.max(0, Math.floor(performance.now() - model.startedAt)),
      ...details,
    };
    model.events.push(event);
    return event;
  }

  function currentScene() {
    if (model.phase === "commit") return model.state.scenes[model.index];
    const id = model.state.boss_order[model.index];
    return model.state.scenes.find((scene) => scene.id === id);
  }

  function sceneMarkup(scene) {
    const sockets = model.socketOptions.map((socket, index) => `
      <div class="covenant-socket" data-socket="${esc(socket)}"><i>${esc(scene.socket_glyphs[index])}</i></div>
    `).join("");
    return `<div class="covenant-world world-${esc(scene.kind)} color-${esc(scene.color)}">
      <div class="covenant-moon"></div><div class="covenant-horizon"></div>
      <div class="covenant-figure"><i></i><b>${esc(scene.glyph)}</b></div>
      <div class="covenant-sockets" data-count="${model.socketOptions.length}">${sockets}</div>
      <button class="covenant-relic" type="button" aria-label="Relic"><span>${esc(scene.glyph)}</span></button>
    </div>`;
  }

  function setSeal(value) {
    model.draft.seal = ((Number(value) % model.sealPositions) + model.sealPositions) % model.sealPositions;
    const seal = document.querySelector(".covenant-seal");
    if (seal) seal.style.setProperty("--seal-angle", `${model.draft.seal * (360 / model.sealPositions)}deg`);
    updateCommitReady();
  }

  function updateCommitReady() {
    const button = document.querySelector(".covenant-bind");
    if (button) button.disabled = !model.draft.socket;
  }

  function placeRelic(scene, selected, inputSource) {
    const relic = document.querySelector(".covenant-relic");
    const world = document.querySelector(".covenant-world");
    if (!relic || !world || !selected) return;
    const worldRect = world.getBoundingClientRect();
    const rect = relic.getBoundingClientRect();
    model.draft.socket = selected.dataset.socket;
    model.draft.socketInputSource = inputSource;
    document.querySelectorAll(".covenant-socket").forEach((socket) => {
      socket.dataset.selected = String(socket === selected);
    });
    const target = selected.getBoundingClientRect();
    relic.style.left = `${target.left - worldRect.left + target.width / 2 - rect.width / 2}px`;
    relic.style.top = `${target.top - worldRect.top + target.height / 2 - rect.height / 2}px`;
    record("place", {
      phase: model.phase,
      scene_id: scene.id,
      socket: model.draft.socket,
      input_source: inputSource,
    });
    updateCommitReady();
  }

  function installRelicDrag(scene) {
    const relic = document.querySelector(".covenant-relic");
    const world = document.querySelector(".covenant-world");
    if (!relic || !world || model.interaction !== "full") return;
    relic.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      relic.setPointerCapture(event.pointerId);
      const worldRect = world.getBoundingClientRect();
      const relicRect = relic.getBoundingClientRect();
      const dx = event.clientX - relicRect.left;
      const dy = event.clientY - relicRect.top;
      relic.dataset.dragging = "true";
      const move = (moveEvent) => {
        relic.style.left = `${moveEvent.clientX - worldRect.left - dx}px`;
        relic.style.top = `${moveEvent.clientY - worldRect.top - dy}px`;
      };
      const up = (upEvent) => {
        relic.removeEventListener("pointermove", move);
        relic.removeEventListener("pointerup", up);
        relic.dataset.dragging = "false";
        const rect = relic.getBoundingClientRect();
        const point = [rect.left + rect.width / 2, rect.top + rect.height / 2];
        let selected = null;
        document.querySelectorAll(".covenant-socket").forEach((socket) => {
          const target = socket.getBoundingClientRect();
          if (point[0] >= target.left && point[0] <= target.right && point[1] >= target.top && point[1] <= target.bottom) selected = socket;
        });
        if (!selected) {
          relic.removeAttribute("style");
          return;
        }
        placeRelic(scene, selected, "relic_drag");
        void upEvent;
      };
      relic.addEventListener("pointermove", move);
      relic.addEventListener("pointerup", up);
    });
  }

  function installSealDrag(scene) {
    const seal = document.querySelector(".covenant-seal");
    if (!seal || model.interaction !== "full" || model.sealPositions === 1) return;
    seal.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      seal.setPointerCapture(event.pointerId);
      const update = (moveEvent) => {
        const rect = seal.getBoundingClientRect();
        const angle = Math.atan2(moveEvent.clientY - (rect.top + rect.height / 2), moveEvent.clientX - (rect.left + rect.width / 2));
        setSeal(Math.round((angle + Math.PI / 2) / ((Math.PI * 2) / model.sealPositions)));
      };
      const up = () => {
        seal.removeEventListener("pointermove", update);
        seal.removeEventListener("pointerup", up);
        model.draft.sealInputSource = "seal_drag";
        record("seal", {
          phase: model.phase,
          scene_id: scene.id,
          seal: model.draft.seal,
          input_source: "seal_drag",
        });
      };
      update(event);
      seal.addEventListener("pointermove", update);
      seal.addEventListener("pointerup", up);
    });
  }

  function installSimplifiedControls(scene) {
    if (model.interaction !== "simplified") return;
    document.querySelectorAll(".covenant-place-button").forEach((button) => {
      button.addEventListener("click", () => {
        const selected = document.querySelector(`.covenant-socket[data-socket="${button.dataset.socket}"]`);
        placeRelic(scene, selected, "socket_button");
      });
    });
    document.querySelectorAll(".covenant-seal-button").forEach((button) => {
      button.addEventListener("click", () => {
        setSeal(Number(button.dataset.sealValue));
        model.draft.sealInputSource = "seal_button";
        record("seal", {
          phase: model.phase,
          scene_id: scene.id,
          seal: model.draft.seal,
          input_source: "seal_button",
        });
      });
    });
  }

  function showFailure(outcome = {}) {
    const root = document.querySelector(".covenant-captcha");
    if (!root) return;
    root.classList.add("is-failed");
    root.querySelector(".covenant-verdict")?.remove();
    const verdict = document.createElement("section");
    verdict.className = "covenant-verdict";
    verdict.setAttribute("role", "alert");
    verdict.setAttribute("aria-live", "assertive");
    const retry = outcome.state
      ? `<button class="covenant-retry" type="button">OPEN FRESH LEDGER →</button>`
      : `<button class="covenant-retry" type="button" disabled>FRESH LEDGER UNAVAILABLE</button>`;
    verdict.innerHTML = `
      <span>CAUSAL LEDGER VERDICT</span>
      <strong>FAIL</strong>
      <p>${esc(outcome.feedback || "A covenant was broken. This ledger is closed.")}</p>
      ${retry}
    `;
    root.appendChild(verdict);
    if (outcome.state) {
      verdict.querySelector(".covenant-retry").addEventListener("click", () => {
        model.helpers.render(outcome.state);
      });
    }
    model.helpers.setReadout("FAIL", "error");
  }

  async function submit() {
    if (model.submitting) return;
    model.submitting = true;
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({
        mechanic_id: model.state.mechanic_id,
        task_id: model.state.task_id,
        challenge_id: model.state.challenge_id,
        events: model.events,
      })});
      const outcome = await response.json();
      if (outcome.passed === true) {
        document.querySelector(".covenant-captcha")?.classList.add("is-passed");
        model.helpers.setReadout("PASS", "passed");
      } else {
        showFailure(outcome);
      }
    } catch (_error) {
      model.submitting = false;
      showFailure({
        feedback: "The ledger could not be judged. No fresh challenge was issued.",
      });
    }
  }

  function bindDraft() {
    const scene = currentScene();
    if (!scene || !model.draft.socket) return;
    const event = record(model.phase === "commit" ? "commit" : "reconstruct", {
      scene_id: scene.id,
      socket: model.draft.socket,
      seal: model.draft.seal,
      order_index: model.index,
      place_input_source: model.draft.socketInputSource,
      seal_input_source: model.draft.sealInputSource,
    });
    if (model.phase === "commit") model.commitments[scene.id] = [event.socket, event.seal];
    model.index += 1;
    if (model.phase === "commit" && model.index >= model.state.scenes.length) {
      const distinct = new Set(Object.values(model.commitments).map((value) => `${value[0]}:${value[1]}`)).size;
      if (distinct < model.minimumDistinctStates) {
        model.helpers.setReadout(`FAIL · ${distinct}/${model.minimumDistinctStates} DISTINCT`, "error");
        submit();
        return;
      }
      model.phase = "storm";
      renderStorm();
      return;
    }
    if (model.phase === "reconstruct" && model.index >= model.state.boss_order.length) {
      submit();
      return;
    }
    renderStep();
  }

  function renderStorm() {
    const stage = document.querySelector(".covenant-stage");
    record("storm");
    stage.innerHTML = `<div class="covenant-storm"><i></i><i></i><i></i><strong>THE LEDGER CLOSES</strong></div>`;
    model.helpers.setReadout("", "idle");
    window.setTimeout(() => {
      record("judgment");
      model.phase = "reconstruct";
      model.index = 0;
      renderStep();
    }, Number(model.state.storm_ms));
  }

  function renderStep() {
    const scene = currentScene();
    model.draft = {
      socket: null,
      seal: Number(scene.initial_seal || 0) % model.sealPositions,
      socketInputSource: null,
      sealInputSource: "initial_state",
    };
    const stage = document.querySelector(".covenant-stage");
    const label = model.phase === "commit" ? "THE MAKING" : "THE RECKONING";
    document.querySelector(".covenant-phase").textContent = `${String(model.index + 1).padStart(2, "0")} / ${String(model.state.scenes.length).padStart(2, "0")} · ${label}`;
    const placementButtons = model.socketOptions.map((socket) => `
      <button class="covenant-place-button" type="button" data-socket="${esc(socket)}">${esc(socket.toUpperCase())}</button>
    `).join("");
    const sealButtons = Array.from({length: model.sealPositions}, (_, value) => `
      <button class="covenant-seal-button" type="button" data-seal-value="${value}">${value * (360 / model.sealPositions)}°</button>
    `).join("");
    const distinctStatus = model.phase === "commit" && model.minimumDistinctStates > 1
      ? `<em class="covenant-distinct">USE ${model.minimumDistinctStates} DISTINCT SOCKET + SEAL STATES</em>`
      : "";
    const proxies = model.interaction === "simplified"
      ? `<div class="covenant-proxies"><span>PLACE RELIC</span><div>${placementButtons}</div><span>SET SEAL</span><div>${sealButtons}</div></div>`
      : "";
    stage.innerHTML = `${sceneMarkup(scene)}<aside class="covenant-control">
      <span>${model.phase === "commit" ? "PLACE / SEAL / BIND" : "REBUILD / SEAL / ANSWER"}</span>
      ${distinctStatus}
      <div class="covenant-seal${model.sealPositions === 1 ? " is-fixed" : ""}" style="--seal-angle:${model.draft.seal * (360 / model.sealPositions)}deg"><i>${esc(scene.glyph)}</i><b></b></div>
      ${proxies}
      <button class="covenant-bind" type="button" disabled>${model.phase === "commit" ? "BIND" : "ANSWER"}</button>
    </aside>`;
    installRelicDrag(scene);
    installSealDrag(scene);
    installSimplifiedControls(scene);
    document.querySelector(".covenant-bind").addEventListener("click", bindDraft);
    model.helpers.setReadout("", "idle");
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "consequences-boss-v2";
    const parameters = state.control_condition?.difficulty_parameters || {};
    const interaction = state.control_condition?.interaction || "full";
    const socketOptions = Array.isArray(parameters.socket_options) && parameters.socket_options.length
      ? parameters.socket_options.map(String)
      : ["left", "right"];
    const sealPositions = Number(parameters.seal_positions || 4);
    model = {
      state,
      helpers,
      phase: "commit",
      index: 0,
      draft: null,
      events: [],
      submitting: false,
      commitments: {},
      interaction,
      socketOptions,
      sealPositions,
      minimumDistinctStates: Number(parameters.minimum_distinct_states || 1),
      startedAt: performance.now(),
    };
    helpers.app.innerHTML = `<section class="covenant-captcha" data-interaction="${esc(interaction)}" data-challenge-id="${esc(state.challenge_id)}">
      <header class="covenant-head"><span>CAUSAL LEDGER / COVENANT ENGINE</span><h1>${esc(state.prompt)}</h1><p class="covenant-phase"></p></header>
      <section class="covenant-stage"></section>
      <footer class="covenant-foot"><div class="readout" data-status="idle"></div><div class="covenant-orbit">◌　✦　◌</div></footer>
    </section>`;
    renderStep();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.consequences_boss = {render,rootSelector:".covenant-captcha"};
})();
