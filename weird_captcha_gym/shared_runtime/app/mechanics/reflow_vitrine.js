(() => {
  "use strict";

  let model = null;
  let cleanup = null;
  const deep = (value) => JSON.parse(JSON.stringify(value));
  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const interaction = () => model.state.control_condition?.interaction || "full";
  const frameMap = () => Object.fromEntries(model.frames.map((frame) => [frame.id, frame]));
  const itemMap = () => Object.fromEntries(model.items.map((item) => [item.id, item]));

  function baseSize(id, frames, items) {
    return frames[id] ? [Number(frames[id].base_w), Number(frames[id].base_h)] : [Number(items[id].w), Number(items[id].h)];
  }

  function solveLayout(config) {
    const frames = frameMap(); const items = itemMap(); const boxes = {};
    function arrange(frameId, x, y, width, height) {
      const frame = frames[frameId]; const props = config[frameId];
      boxes[frameId] = {x, y, w: width, h: height, kind: "frame"};
      const pad = Number(props.padding);
      const padX = Math.min(pad, Math.max(0, (width - 8) / 2));
      const padY = Math.min(pad, Math.max(0, (height - 8) / 2));
      const ix = x + padX; const iy = y + padY;
      const iw = Math.max(8, width - 2 * padX); const ih = Math.max(8, height - 2 * padY);
      const row = props.axis === "row";
      const mainAvailable = row ? iw : ih; const crossAvailable = row ? ih : iw;
      const ordered = props.order.filter((child) => frame.children.includes(child));
      frame.children.forEach((child) => { if (!ordered.includes(child)) ordered.push(child); });
      if (!ordered.length) return;
      const gap = Number(props.gap); const lines = [[]]; let used = 0;
      ordered.forEach((child) => {
        const size = baseSize(child, frames, items); const childMain = row ? size[0] : size[1];
        let needed = lines.at(-1).length ? gap + childMain : childMain;
        if (props.wrap === "wrap" && lines.at(-1).length && used + needed > mainAvailable) {
          lines.push([]); used = 0; needed = childMain;
        }
        lines.at(-1).push(child); used += needed;
      });
      let lineCross = lines.map((line) => Math.max(8, ...line.map((child) => baseSize(child, frames, items)[row ? 1 : 0])));
      let crossGap = lines.length > 1 ? gap : 0;
      if (lines.length > 1) crossGap = Math.min(crossGap, Math.max(0, (crossAvailable - 2 * lines.length) / (lines.length - 1)));
      const crossSpace = Math.max(0.001 * lines.length, crossAvailable - crossGap * (lines.length - 1));
      if (props.cross === "stretch") {
        const share = crossSpace / lines.length;
        lineCross = lines.map(() => share);
      } else {
        const naturalCross = lineCross.reduce((sum, value) => sum + value, 0);
        if (naturalCross > crossSpace) lineCross = lineCross.map((value) => value * crossSpace / naturalCross);
      }
      const totalCross = lineCross.reduce((sum, value) => sum + value, 0) + crossGap * (lines.length - 1);
      const crossExtra = Math.max(0, crossAvailable - totalCross);
      let crossCursor = ["start", "stretch"].includes(props.cross) ? 0 : props.cross === "center" ? crossExtra / 2 : crossExtra;
      lines.forEach((line, lineIndex) => {
        const bases = line.map((child) => baseSize(child, frames, items));
        let mainSizes = bases.map((size) => row ? size[0] : size[1]);
        let mainGap = line.length > 1 ? gap : 0;
        if (line.length > 1) mainGap = Math.min(mainGap, Math.max(0, (mainAvailable - 2 * line.length) / (line.length - 1)));
        const itemSpace = Math.max(0.001 * line.length, mainAvailable - mainGap * (line.length - 1));
        const naturalMain = mainSizes.reduce((sum, value) => sum + value, 0);
        if (naturalMain > itemSpace) mainSizes = mainSizes.map((value) => value * itemSpace / naturalMain);
        const extra = Math.max(0, itemSpace - mainSizes.reduce((sum, value) => sum + value, 0));
        const grows = line.map((child) => frames[child] ? Number(config[child].grow) : 0);
        const growTotal = grows.reduce((sum, value) => sum + value, 0);
        let mainCursor = 0;
        if (growTotal) mainSizes = mainSizes.map((value, index) => value + extra * grows[index] / growTotal);
        else if (props.main === "space" && line.length > 1) mainGap = gap + extra / (line.length - 1);
        else mainCursor = ["start", "space"].includes(props.main) ? 0 : props.main === "center" ? extra / 2 : extra;
        line.forEach((child, index) => {
          const base = bases[index]; const naturalCross = row ? base[1] : base[0];
          const crossSize = props.cross === "stretch" ? lineCross[lineIndex] : Math.min(naturalCross, lineCross[lineIndex]);
          const localCross = ["start", "stretch"].includes(props.cross) ? 0 : props.cross === "center" ? (lineCross[lineIndex] - crossSize) / 2 : lineCross[lineIndex] - crossSize;
          const values = row
            ? [ix + mainCursor, iy + crossCursor + localCross, mainSizes[index], crossSize]
            : [ix + crossCursor + localCross, iy + mainCursor, crossSize, mainSizes[index]];
          if (frames[child]) arrange(child, ...values);
          else boxes[child] = {x: values[0], y: values[1], w: values[2], h: values[3], kind: items[child].kind, tone: items[child].tone};
          mainCursor += mainSizes[index] + mainGap;
        });
        crossCursor += lineCross[lineIndex] + crossGap;
      });
    }
    arrange("window", 0, 0, 360, 260);
    return boxes;
  }

  function raster(boxes, width = 120, height = 86) {
    const pixels = Array(width * height).fill(14);
    const edge = (value, span, size, upper) => {
      let scaled = Number(value) / span * size;
      const nearest = Math.round(scaled);
      if (Math.abs(scaled - nearest) < 1e-9) scaled = nearest;
      return upper ? Math.ceil(scaled) : Math.floor(scaled);
    };
    const entries = Object.entries(boxes).sort((a, b) => Number(a[1].kind !== "frame") - Number(b[1].kind !== "frame") || a[0].localeCompare(b[0]));
    entries.forEach(([_id, box]) => {
      const rawLeft = edge(box.x, 360, width, false);
      const rawTop = edge(box.y, 260, height, false);
      const rawRight = edge(Number(box.x) + Number(box.w), 360, width, true);
      const rawBottom = edge(Number(box.y) + Number(box.h), 260, height, true);
      const left = clamp(rawLeft, 0, width); const top = clamp(rawTop, 0, height);
      const right = clamp(rawRight, 0, width); const bottom = clamp(rawBottom, 0, height);
      if (right <= left || bottom <= top) return;
      if (box.kind === "frame") {
        if (rawTop >= 0 && rawTop < height) for (let px = left; px < right; px += 1) pixels[rawTop * width + px] = 48;
        if (rawBottom > 0 && rawBottom <= height) for (let px = left; px < right; px += 1) pixels[(rawBottom - 1) * width + px] = 48;
        if (rawLeft >= 0 && rawLeft < width) for (let py = top; py < bottom; py += 1) pixels[py * width + rawLeft] = 48;
        if (rawRight > 0 && rawRight <= width) for (let py = top; py < bottom; py += 1) pixels[py * width + rawRight - 1] = 48;
      } else {
        for (let py = top; py < bottom; py += 1) for (let px = left; px < right; px += 1) pixels[py * width + px] = Number(box.tone || 180);
      }
    });
    return pixels;
  }

  function similarity(left, right) {
    if (!left.length || left.length !== right.length) return 0;
    const count = left.length;
    const meanL = left.reduce((sum, value) => sum + value, 0) / count;
    const meanR = right.reduce((sum, value) => sum + value, 0) / count;
    const varL = left.reduce((sum, value) => sum + (value - meanL) ** 2, 0) / count;
    const varR = right.reduce((sum, value) => sum + (value - meanR) ** 2, 0) / count;
    const covariance = left.reduce((sum, value, index) => sum + (value - meanL) * (right[index] - meanR), 0) / count;
    const c1 = (0.01 * 255) ** 2; const c2 = (0.03 * 255) ** 2;
    return ((2 * meanL * meanR + c1) * (2 * covariance + c2)) / ((meanL ** 2 + meanR ** 2 + c1) * (varL + varR + c2));
  }

  function scoreCurrent() {
    return similarity(raster(model.targetLayout), raster(solveLayout(model.config)));
  }

  function itemMarkup(item, box) {
    const style = `--x:${box.x / 3.6}%;--y:${box.y / 2.6}%;--w:${box.w / 3.6}%;--h:${box.h / 2.6}%;--accent:${item.accent}`;
    const symbols = {mannequin: "◒", lamp: "◜", card: "▧", scarf: "≈", vase: "♙", shoe: "◡", orb: "◉", banner: "▰", box: "▣"};
    return `<div class="rv-prop kind-${esc(item.kind)}" style="${style}" aria-label="${esc(item.name)}"><i>${symbols[item.kind] || "◆"}</i><small>${esc(item.name)}</small></div>`;
  }

  function vitrineMarkup(boxes, target) {
    const frames = model.frames.filter((frame) => frame.id !== "window").map((frame) => {
      const box = boxes[frame.id]; if (!box) return "";
      const selected = !target && frame.id === model.selectedFrame ? "is-selected" : "";
      return `<div class="rv-frame ${selected}" style="--x:${box.x / 3.6}%;--y:${box.y / 2.6}%;--w:${box.w / 3.6}%;--h:${box.h / 2.6}%"></div>`;
    }).join("");
    const items = model.items.map((item) => itemMarkup(item, boxes[item.id])).join("");
    return `<div class="rv-glass ${target ? "is-target" : "is-live"}"><div class="rv-curtain"></div>${frames}${items}<div class="rv-floor"></div></div>`;
  }

  function valuesFor(prop) { return model.state.allowed_values[prop] || []; }

  function propLabel(prop) {
    return {axis: "STACK AXIS", main: "MAIN ALIGN", cross: "CROSS ALIGN", gap: "GAP", padding: "PADDING", wrap: "WRAP", grow: "GROWTH"}[prop] || prop.toUpperCase();
  }

  function simpleProperty(frameId, prop) {
    const current = model.config[frameId][prop];
    return `<div class="rv-rule"><label>${propLabel(prop)}<em>${esc(current)}</em></label><div class="rv-values">${valuesFor(prop).map((value) => `<button data-set-frame="${esc(frameId)}" data-set-prop="${prop}" data-set-value="${esc(value)}" class="${value === current ? "is-current" : ""}" ${model.locked ? "disabled" : ""}>${esc(value)}</button>`).join("")}</div></div>`;
  }

  function fullProperty(frameId, prop) {
    const current = model.config[frameId][prop];
    if (["gap", "padding", "grow"].includes(prop)) {
      const values = valuesFor(prop); const index = values.indexOf(current); const left = values.length > 1 ? index / (values.length - 1) * 100 : 0;
      return `<div class="rv-rule"><label>${propLabel(prop)}<em>${esc(current)}</em></label><div class="rv-fader" data-fader-frame="${esc(frameId)}" data-fader-prop="${prop}" style="--fader:${left}%" aria-label="${propLabel(prop)} ${esc(current)}"><i></i><b></b><span>${values.map(esc).join(" · ")}</span></div></div>`;
    }
    return `<div class="rv-rule"><label>${propLabel(prop)}<em>${esc(current)}</em></label><select data-select-frame="${esc(frameId)}" data-select-prop="${prop}" ${model.locked ? "disabled" : ""}>${valuesFor(prop).map((value) => `<option value="${esc(value)}" ${value === current ? "selected" : ""}>${esc(value).toUpperCase()}</option>`).join("")}</select></div>`;
  }

  function childName(id) { return model.frames.find((frame) => frame.id === id)?.name || model.items.find((item) => item.id === id)?.name || id; }

  function orderMarkup(frameId) {
    const order = model.config[frameId].order;
    if (order.length < 2 || !model.mutable.includes("order")) return "";
    if (interaction() === "simplified") return `<div class="rv-rule rv-order"><label>CHILD ORDER<em>${order.length}</em></label><div>${order.map((id, index) => `<article><span>${index + 1}</span><b>${esc(childName(id))}</b><button data-order-frame="${esc(frameId)}" data-order-index="${index}" data-order-delta="-1" ${index === 0 || model.locked ? "disabled" : ""}>←</button><button data-order-frame="${esc(frameId)}" data-order-index="${index}" data-order-delta="1" ${index === order.length - 1 || model.locked ? "disabled" : ""}>→</button></article>`).join("")}</div></div>`;
    return `<div class="rv-rule rv-order"><label>CHILD ORDER<em>${order.length}</em></label><div>${order.map((id, index) => `<article data-order-chip="${esc(id)}" data-order-frame="${esc(frameId)}" data-order-index="${index}"><span>${index + 1}</span><b>${esc(childName(id))}</b><i>⠿</i></article>`).join("")}</div></div>`;
  }

  function inspectorMarkup() {
    const frame = model.frames.find((entry) => entry.id === model.selectedFrame) || model.frames[0];
    const props = model.mutable.filter((prop) => prop !== "order" && !(prop === "grow" && frame.id === "window"));
    return `<aside class="rv-inspector"><header><small>FRAME RULES</small><h2>${esc(frame.name)}</h2></header><div class="rv-rules">${props.map((prop) => interaction() === "simplified" ? simpleProperty(frame.id, prop) : fullProperty(frame.id, prop)).join("")}${orderMarkup(frame.id)}</div></aside>`;
  }

  function verdictMarkup() {
    if (model.passed) return `<div class="rv-verdict is-pass"><b>PASS</b></div>`;
    if (model.serverFailure) return `<div class="rv-verdict is-fail"><b>FAIL</b></div>`;
    return "";
  }

  function renderSurface() {
    const root = document.querySelector(".reflow-vitrine"); if (!root) return;
    const liveBoxes = solveLayout(model.config);
    model.locked = model.passed || model.submitting || model.events.length >= Number(model.parameters.edit_budget);
    root.querySelector(".rv-stage").innerHTML = `<section class="rv-photo"><header><span>TARGET</span></header>${vitrineMarkup(model.targetLayout, true)}</section><div class="rv-comparator"><i></i><i></i></div><section class="rv-photo"><header><span>CURRENT</span><b>${model.events.length} / ${model.parameters.edit_budget} EDITS</b></header>${vitrineMarkup(liveBoxes, false)}</section>`;
    root.querySelector(".rv-frame-list").innerHTML = model.frames.map((frame, index) => `<button data-frame-select="${esc(frame.id)}" class="${frame.id === model.selectedFrame ? "is-selected" : ""}"><span>${String(index + 1).padStart(2, "0")}</span><b>${esc(frame.name)}</b></button>`).join("");
    root.querySelector(".rv-inspector-slot").innerHTML = inspectorMarkup();
    root.querySelector(".rv-ledger span").textContent = `${model.events.length} OF ${model.parameters.edit_budget} EDITS USED`;
    root.querySelector("#rv-revert").disabled = model.locked || model.history.length === 0;
    root.querySelector("#rv-certify").disabled = model.submitting || model.passed;
    root.querySelector(".rv-verdict-layer").innerHTML = verdictMarkup();
    bindControls();
  }

  function record(before, event) {
    model.history.push(before); model.events.push({sequence: model.events.length + 1, ...event});
    model.serverFailure = false;
    renderSurface();
    model.helpers.setReadout("", "idle");
  }

  function setProperty(frameId, prop, value, inputSource, gesture = null) {
    if (model.locked || !model.mutable.includes(prop)) return;
    const allowed = valuesFor(prop); const normalized = ["gap", "padding", "grow"].includes(prop) ? Number(value) : value;
    if (!allowed.includes(normalized) || model.config[frameId]?.[prop] === normalized) return;
    const before = deep(model.config); model.config[frameId][prop] = normalized;
    record(before, {type: "set", frame_id: frameId, property: prop, value: normalized, input_source: inputSource, ...(gesture ? {gesture} : {})});
  }

  function reorder(frameId, fromIndex, toIndex, inputSource, gesture = null) {
    if (model.locked || !model.mutable.includes("order")) return;
    const order = model.config[frameId]?.order; if (!order || fromIndex === toIndex || !order[fromIndex] || !order[toIndex]) return;
    const before = deep(model.config); const childId = order[fromIndex]; order.splice(toIndex, 0, order.splice(fromIndex, 1)[0]);
    record(before, {type: "reorder", frame_id: frameId, property: "order", child_id: childId, from_index: fromIndex, to_index: toIndex, input_source: inputSource, ...(gesture ? {gesture} : {})});
  }

  function revert() {
    if (model.locked || !model.history.length) return;
    model.config = model.history.pop(); model.events.push({sequence: model.events.length + 1, type: "revert", input_source: "revert_button"});
    model.serverFailure = false;
    renderSurface();
    model.helpers.setReadout("", "idle");
  }

  function bindFaders() {
    document.querySelectorAll("[data-fader-frame]").forEach((fader) => {
      let drag = null;
      fader.addEventListener("pointerdown", (event) => {
        if (model.locked || event.button !== 0) return;
        event.preventDefault(); const rect = fader.getBoundingClientRect();
        drag = {pointerId: event.pointerId, rect, startX: event.clientX, startY: event.clientY, lastX: event.clientX, lastY: event.clientY, travel: 0, samples: 0};
        fader.setPointerCapture?.(event.pointerId); fader.classList.add("is-dragging");
      });
      fader.addEventListener("pointermove", (event) => {
        if (!drag || event.pointerId !== drag.pointerId) return;
        drag.travel += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY); drag.lastX = event.clientX; drag.lastY = event.clientY; drag.samples += 1;
        fader.style.setProperty("--preview", `${clamp((event.clientX - drag.rect.left) / drag.rect.width * 100, 0, 100)}%`);
      });
      const finish = (event) => {
        if (!drag || event.pointerId !== drag.pointerId) return;
        drag.travel += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY); drag.samples += 1;
        const values = valuesFor(fader.dataset.faderProp); const ratio = clamp((event.clientX - drag.rect.left) / drag.rect.width, 0, 1);
        const value = values[Math.round(ratio * (values.length - 1))];
        const proof = {start_u: clamp((drag.startX - drag.rect.left) / drag.rect.width, 0, 1), start_v: clamp((drag.startY - drag.rect.top) / drag.rect.height, 0, 1), end_u: ratio, end_v: clamp((event.clientY - drag.rect.top) / drag.rect.height, 0, 1), travel_px: Number(drag.travel.toFixed(3)), sample_count: drag.samples};
        fader.classList.remove("is-dragging"); fader.style.removeProperty("--preview"); drag = null;
        if (proof.travel_px >= 12) setProperty(fader.dataset.faderFrame, fader.dataset.faderProp, value, "inspector_fader_drag", proof);
      };
      fader.addEventListener("pointerup", finish); fader.addEventListener("pointercancel", () => { drag = null; fader.classList.remove("is-dragging"); });
    });
  }

  function bindOrderDrags() {
    document.querySelectorAll("[data-order-chip]").forEach((chip) => {
      let drag = null;
      chip.addEventListener("pointerdown", (event) => {
        if (model.locked || event.button !== 0) return;
        event.preventDefault(); const rect = chip.getBoundingClientRect();
        drag = {pointerId: event.pointerId, rect, startX: event.clientX, startY: event.clientY, lastX: event.clientX, lastY: event.clientY, travel: 0, samples: 0};
        chip.setPointerCapture?.(event.pointerId); chip.classList.add("is-dragging");
      });
      chip.addEventListener("pointermove", (event) => {
        if (!drag || event.pointerId !== drag.pointerId) return;
        drag.travel += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY); drag.lastX = event.clientX; drag.lastY = event.clientY; drag.samples += 1;
      });
      chip.addEventListener("pointerup", (event) => {
        if (!drag || event.pointerId !== drag.pointerId) return;
        drag.travel += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY); drag.samples += 1;
        const peers = [...document.querySelectorAll(`[data-order-frame="${CSS.escape(chip.dataset.orderFrame)}"][data-order-chip]`)];
        let target = peers.reduce((best, peer) => {
          const rect = peer.getBoundingClientRect(); const distance = Math.hypot(event.clientX - (rect.left + rect.width / 2), event.clientY - (rect.top + rect.height / 2));
          return !best || distance < best.distance ? {peer, rect, distance} : best;
        }, null);
        const fromIndex = Number(chip.dataset.orderIndex); const toIndex = Number(target?.peer.dataset.orderIndex);
        const proof = target ? {start_u: clamp((drag.startX - drag.rect.left) / drag.rect.width, 0, 1), start_v: clamp((drag.startY - drag.rect.top) / drag.rect.height, 0, 1), end_u: clamp((event.clientX - target.rect.left) / target.rect.width, 0, 1), end_v: clamp((event.clientY - target.rect.top) / target.rect.height, 0, 1), travel_px: Number(drag.travel.toFixed(3)), sample_count: drag.samples} : null;
        chip.classList.remove("is-dragging"); drag = null;
        if (proof && proof.travel_px >= 20) reorder(chip.dataset.orderFrame, fromIndex, toIndex, "child_strip_drag", proof);
      });
      chip.addEventListener("pointercancel", () => { drag = null; chip.classList.remove("is-dragging"); });
    });
  }

  function bindControls() {
    document.querySelectorAll("[data-frame-select]").forEach((button) => button.addEventListener("click", () => { model.selectedFrame = button.dataset.frameSelect; renderSurface(); }));
    document.getElementById("rv-revert")?.addEventListener("click", revert);
    document.getElementById("rv-certify")?.addEventListener("click", submit);
    if (interaction() === "simplified") {
      document.querySelectorAll("[data-set-frame]").forEach((button) => button.addEventListener("click", () => setProperty(button.dataset.setFrame, button.dataset.setProp, button.dataset.setValue, "value_button")));
      document.querySelectorAll("[data-order-delta]").forEach((button) => button.addEventListener("click", () => { const from = Number(button.dataset.orderIndex); reorder(button.dataset.orderFrame, from, from + Number(button.dataset.orderDelta), "order_nudge_button"); }));
    } else {
      document.querySelectorAll("[data-select-frame]").forEach((select) => select.addEventListener("change", () => setProperty(select.dataset.selectFrame, select.dataset.selectProp, select.value, "inspector_dropdown")));
      bindFaders(); bindOrderDrags();
    }
  }

  async function submit() {
    if (!model || model.submitting || model.passed) return;
    const current = model; current.submitting = true; renderSurface();
    try {
      const score = scoreCurrent();
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({
        mechanic_id: current.state.mechanic_id, task_id: current.state.task_id, challenge_id: current.state.challenge_id,
        interaction_mode: interaction(), events: current.events, final_config: current.config,
        similarity: Number(score.toFixed(8)), completed: score >= Number(current.parameters.similarity_threshold),
      })});
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.passed = true; current.submitting = false; renderSurface(); current.helpers.setReadout("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        const helpers = current.helpers; await render(outcome.state, helpers, {serverFailure: true}); model.helpers.setReadout("FAIL", "error");
      } else {
        current.submitting = false; current.serverFailure = true; renderSurface(); current.helpers.setReadout("FAIL", "error");
      }
    } catch (_error) {
      if (model === current) { current.submitting = false; renderSurface(); current.helpers.setReadout("FAIL", "error"); }
    }
  }

  async function render(state, helpers, options = {}) {
    cleanup?.(); document.body.dataset.mechanic = "reflow-vitrine";
    model = {
      state, helpers, frames: deep(state.frames), items: deep(state.items), config: deep(state.initial_config), targetLayout: deep(state.target_layout),
      parameters: deep(state.parameters), mutable: deep(state.mutable_properties), selectedFrame: state.frames[0].id,
      events: [], history: [], locked: false, passed: false, submitting: false,
      serverFailure: Boolean(options.serverFailure),
    };
    helpers.app.innerHTML = `<section class="reflow-vitrine mode-${interaction()}" data-interaction="${interaction()}" data-mechanic="${esc(state.mechanic_id)}" data-challenge-id="${esc(state.challenge_id)}" data-fresh-failure="${options.serverFailure ? "true" : "false"}">
      <header class="rv-masthead"><div><small>MAISON ORDINATE · WINDOW COMMISSION ${String(state.visual_seed).slice(-4)}</small><h1>${esc(state.prompt)}</h1></div><div class="rv-seal"><i>RV</i><span>${interaction().toUpperCase()} INSPECTOR</span><b>D${state.control_condition?.difficulty || 4}</b></div></header>
      <main><div class="rv-left"><div class="rv-stage"></div><div class="rv-frame-list"></div></div><div class="rv-inspector-slot"></div></main>
      <footer><div class="rv-ledger"><strong class="readout" data-status="idle"></strong><span></span></div><button id="rv-revert">REVERT</button><button id="rv-certify">CERTIFY</button></footer>
      <div class="rv-verdict-layer"></div>${helpers.cheatPanelTemplate()}
    </section>`;
    renderSurface(); helpers.installCheatPanel(); cleanup = () => {};
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.reflow_vitrine = {rootSelector: ".reflow-vitrine", render};
})();
