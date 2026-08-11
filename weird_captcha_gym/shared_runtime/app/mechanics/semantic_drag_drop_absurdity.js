(() => {
  "use strict";

  let model = null;
  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

  function clearReaction(node) {
    node.classList.remove("reaction-active");
    delete node.dataset.thermal;
    delete node.dataset.polarity;
  }

  function showReaction(node, signature, duration, channel = "all") {
    clearReaction(node);
    if (channel === "all" || channel === "thermal") node.dataset.thermal = signature.thermal;
    if (channel === "all" || channel === "polarity") node.dataset.polarity = signature.polarity;
    void node.offsetWidth;
    node.classList.add("reaction-active");
    setTimeout(() => clearReaction(node), duration);
  }

  function sourceFor(kind) {
    return model.interaction === "simplified"
      ? (kind === "probe" ? "proxy_probe" : "proxy_pair_click")
      : (kind === "probe" ? "direct_probe_drag" : "direct_specimen_drag");
  }

  function objectFor(id) {
    return model.state.objects.find((item) => item.id === id) || null;
  }

  function hasRequiredSamples(objectId) {
    return model.probed.has(`${objectId}:thermal`) && model.probed.has(`${objectId}:polarity`);
  }

  function recordProbe(objectId, kind, holdMs, node) {
    const object = objectFor(objectId);
    if (!object) return;
    showReaction(node, object.runtime_signature, Number(model.state.response_ms), kind);
    model.probes.push({
      sequence: model.probes.length + 1,
      object_id: object.id,
      probe: kind,
      hold_ms: Math.round(holdMs),
      input_source: sourceFor("probe"),
    });
    model.probed.add(`${object.id}:${kind}`);
    model.helpers.setReadout("", "idle");
  }

  function markSelected() {
    document.querySelectorAll(".causal-specimen").forEach((node) => {
      node.dataset.selected = String(node.dataset.objectId === model.selectedObjectId);
    });
  }

  function rejectPlacement(objectNode, source) {
    const object = objectFor(objectNode.dataset.objectId);
    if (object) {
      objectNode.style.left = `${object.x}px`;
      objectNode.style.top = `${object.y}px`;
    }
    objectNode.classList.remove("probe-rejected");
    void objectNode.offsetWidth;
    objectNode.classList.add("probe-rejected");
    if (model.interaction === "simplified") {
      model.helpers.setReadout("SAMPLE BOTH CHANNELS BEFORE ROUTING", "error");
      model.selectedObjectId = null;
      markSelected();
    }
    return source;
  }

  function placeObject(objectNode, receiver) {
    const stage = document.querySelector(".causal-stage");
    const stageRect = stage.getBoundingClientRect();
    const target = receiver.getBoundingClientRect();
    const rect = objectNode.getBoundingClientRect();
    objectNode.style.left = `${target.left - stageRect.left + target.width / 2 - rect.width / 2}px`;
    objectNode.style.top = `${target.top - stageRect.top + target.height / 2 - rect.height / 2}px`;
    const objectId = objectNode.dataset.objectId;
    model.placements[objectId] = receiver.dataset.receiverId;
    model.placementSources[objectId] = sourceFor("placement");
    objectNode.dataset.placed = "true";
    model.selectedObjectId = null;
    markSelected();
    model.helpers.setReadout("", "idle");
  }

  function installDirectProbe(tool) {
    tool.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      tool.setPointerCapture(event.pointerId);
      const kind = tool.dataset.probe;
      const origin = tool.getBoundingClientRect();
      let target = null;
      let enteredAt = 0;
      const move = (moveEvent) => {
        tool.style.setProperty("--probe-x", `${moveEvent.clientX - (origin.left + origin.width / 2)}px`);
        tool.style.setProperty("--probe-y", `${moveEvent.clientY - (origin.top + origin.height / 2)}px`);
        tool.dataset.dragging = "true";
        const under = document.elementsFromPoint(moveEvent.clientX, moveEvent.clientY)
          .map((node) => node.closest?.(".causal-specimen"))
          .find(Boolean) || null;
        if (under !== target) {
          target = under;
          enteredAt = model.helpers.interactionNow();
          document.querySelectorAll(".causal-specimen").forEach((node) => {
            node.dataset.probeHover = String(node === target);
          });
        }
      };
      const up = () => {
        tool.removeEventListener("pointermove", move);
        tool.removeEventListener("pointerup", up);
        tool.removeAttribute("style");
        tool.dataset.dragging = "false";
        document.querySelectorAll(".causal-specimen").forEach((node) => { node.dataset.probeHover = "false"; });
        if (target && model.helpers.interactionNow() - enteredAt >= Number(model.state.probe_hold_ms)) {
          recordProbe(target.dataset.objectId, kind, model.helpers.interactionNow() - enteredAt, target);
        }
        target = null;
      };
      tool.addEventListener("pointermove", move);
      tool.addEventListener("pointerup", up);
    });
  }

  function installSimplifiedProbe(button) {
    button.addEventListener("click", () => {
      const objectId = model.selectedObjectId;
      const specimen = objectId && document.querySelector(`.causal-specimen[data-object-id="${CSS.escape(objectId)}"]`);
      if (!objectId || !specimen) {
        model.helpers.setReadout("SELECT A SPECIMEN FIRST", "error");
        return;
      }
      recordProbe(objectId, button.dataset.proxyProbe, Number(model.state.probe_hold_ms), specimen);
    });
  }

  function installObject(objectNode) {
    if (model.interaction === "simplified") {
      objectNode.addEventListener("click", () => {
        model.selectedObjectId = objectNode.dataset.objectId;
        markSelected();
        model.helpers.setReadout("SPECIMEN SELECTED / SAMPLE OR ROUTE", "idle");
      });
      return;
    }
    const stage = document.querySelector(".causal-stage");
    objectNode.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      objectNode.setPointerCapture(event.pointerId);
      const stageRect = stage.getBoundingClientRect();
      const rect = objectNode.getBoundingClientRect();
      const dx = event.clientX - rect.left;
      const dy = event.clientY - rect.top;
      objectNode.dataset.dragging = "true";
      const move = (moveEvent) => {
        objectNode.style.left = `${moveEvent.clientX - stageRect.left - dx}px`;
        objectNode.style.top = `${moveEvent.clientY - stageRect.top - dy}px`;
      };
      const up = () => {
        objectNode.removeEventListener("pointermove", move);
        objectNode.removeEventListener("pointerup", up);
        objectNode.dataset.dragging = "false";
        const objectId = objectNode.dataset.objectId;
        const rectNow = objectNode.getBoundingClientRect();
        const point = [rectNow.left + rectNow.width / 2, rectNow.top + rectNow.height / 2];
        let receiver = null;
        document.querySelectorAll(".causal-receiver").forEach((node) => {
          const bounds = node.getBoundingClientRect();
          if (point[0] >= bounds.left && point[0] <= bounds.right && point[1] >= bounds.top && point[1] <= bounds.bottom) receiver = node;
        });
        if (!receiver || !hasRequiredSamples(objectId)) {
          rejectPlacement(objectNode, "direct");
          return;
        }
        placeObject(objectNode, receiver);
      };
      objectNode.addEventListener("pointermove", move);
      objectNode.addEventListener("pointerup", up);
    });
  }

  function installReceiver(receiver) {
    const pulse = receiver.querySelector("button");
    pulse.addEventListener("click", (event) => {
      event.stopPropagation();
      showReaction(receiver, {
        thermal: receiver.dataset.thermal,
        polarity: receiver.dataset.polarity,
      }, Number(model.state.response_ms));
    });
    if (model.interaction !== "simplified") return;
    receiver.addEventListener("click", () => {
      const objectId = model.selectedObjectId;
      const objectNode = objectId && document.querySelector(`.causal-specimen[data-object-id="${CSS.escape(objectId)}"]`);
      if (!objectNode) {
        model.helpers.setReadout("SELECT A SPECIMEN FIRST", "error");
        return;
      }
      if (!hasRequiredSamples(objectId)) {
        rejectPlacement(objectNode, "proxy");
        return;
      }
      placeObject(objectNode, receiver);
    });
  }

  async function submit() {
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
          interaction_mode: model.interaction,
          placements: model.placements,
          placement_sources: model.placementSources,
          probes: model.probes,
        }),
      });
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.helpers.setReadout("PASS", "passed");
        document.querySelector(".causal-captcha").classList.add("is-passed");
      } else {
        model.helpers.setReadout("FAIL", "error");
        setTimeout(() => outcome.state && model.helpers.render(outcome.state), 850);
      }
    } catch (_error) {
      model.submitting = false;
      model.helpers.setReadout("FAIL", "error");
    }
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "semantic-causal-lab-v2";
    const interaction = state.control_condition?.interaction || "full";
    model = {
      state,
      helpers,
      interaction,
      placements: {},
      placementSources: {},
      probes: [],
      probed: new Set(),
      selectedObjectId: null,
      submitting: false,
    };
    const proxyControls = interaction === "simplified"
      ? `<div class="causal-proxy-controls"><button type="button" data-proxy-probe="thermal">THERMAL SAMPLE</button><button type="button" data-proxy-probe="polarity">POLARITY SAMPLE</button></div>`
      : "";
    helpers.app.innerHTML = `<section class="causal-captcha" data-interaction="${esc(interaction)}"><header><span>UNKNOWN MATERIALS / RESPONSE LAB</span><h1>${esc(state.prompt)}</h1></header><section class="causal-stage"><div class="specimen-bank">${state.objects.map((item) => `<button class="causal-specimen" type="button" data-object-id="${esc(item.id)}" style="left:${item.x}px;top:${item.y}px"><i>${esc(item.glyph)}</i><b></b><span></span></button>`).join("")}</div><div class="causal-divider"><i></i></div><div class="receiver-bank">${state.receivers.map((item) => `<div class="causal-receiver" data-receiver-id="${esc(item.id)}" data-thermal="${esc(item.signature.thermal)}" data-polarity="${esc(item.signature.polarity)}" style="left:${item.x}px;top:${item.y}px"><i>${esc(item.glyph)}</i><b></b><button type="button" aria-label="Pulse receiver">◉</button></div>`).join("")}</div></section><footer><div class="probe-dock">${interaction === "full" ? `<button class="probe-tool thermal-probe" data-probe="thermal" type="button"><i></i><span>♨</span></button><button class="probe-tool polarity-probe" data-probe="polarity" type="button"><i></i><span>↔</span></button>` : proxyControls}</div><div class="readout" data-status="idle"></div><button class="causal-submit" type="button">CERTIFY</button></footer></section>`;
    if (interaction === "full") document.querySelectorAll(".probe-tool").forEach(installDirectProbe);
    else document.querySelectorAll("[data-proxy-probe]").forEach(installSimplifiedProbe);
    document.querySelectorAll(".causal-specimen").forEach(installObject);
    document.querySelectorAll(".causal-receiver").forEach(installReceiver);
    document.querySelector(".causal-submit").addEventListener("click", submit);
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.semantic_drag_drop_absurdity = {render, rootSelector: ".causal-captcha"};
})();
