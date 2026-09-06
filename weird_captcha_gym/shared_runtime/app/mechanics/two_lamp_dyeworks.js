(() => {
  "use strict";

  const LAMPS = ["daylight", "sodium"];
  const model = {
    state: null,
    helpers: null,
    interaction: "full",
    pigmentById: {},
    selectedPigment: null,
    composition: {},
    loadedUnits: 0,
    pendingPlungerGesture: null,
    lamp: "daylight",
    stirred: false,
    sampledComposition: null,
    viewed: new Set(),
    ready: false,
    events: [],
    vatIndex: 1,
    totalDispensed: 0,
    terminal: false,
    busy: false,
    plungerDrag: null,
    stirDrag: null,
    stripDrag: null,
  };

  const clean = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
  const cloneComposition = (value) => Object.fromEntries(Object.entries(value || {}).map(([key, units]) => [key, Number(units)]));
  const sameComposition = (left, right) => left && right
    && Object.keys(model.composition).every((key) => Number(left[key] || 0) === Number(right[key] || 0));
  const totalUnits = () => Object.values(model.composition).reduce((sum, value) => sum + Number(value || 0), 0);
  const activeDyes = () => Object.values(model.composition).filter((value) => Number(value || 0) > 0).length;
  const parameters = () => model.state.parameters || {};

  function recipeWithinSpec() {
    return activeDyes() >= Number(parameters().target_components_min)
      && activeDyes() <= Number(parameters().target_components_max)
      && totalUnits() >= Number(parameters().target_total_min)
      && totalUnits() <= Number(parameters().target_total_max);
  }

  function rangeLabel(minimum, maximum) {
    return Number(minimum) === Number(maximum) ? String(minimum) : `${minimum}–${maximum}`;
  }

  function addEvent(type, details = {}) {
    const event = {sequence: model.events.length + 1, type, vat: model.vatIndex, ...details};
    model.events.push(event);
    return event;
  }

  function reflectance(composition) {
    const spectral = model.state.spectral_model;
    return spectral.base_reflectance.map((base, band) => {
      const density = model.state.pigments.reduce(
        (sum, pigment) => sum + Number(composition[pigment.id] || 0) * Number(pigment.absorption[band]),
        0,
      );
      return Math.max(0.025, Number(base) * Math.exp(-Number(spectral.absorption_strength) * density));
    });
  }

  function xyz(spectrum, illuminant) {
    const spectral = model.state.spectral_model;
    const lamp = spectral.illuminants[illuminant];
    const normalizer = 1 / lamp.reduce(
      (sum, value, index) => sum + Number(value) * Number(spectral.cie_1931.y[index]),
      0,
    );
    return ["x", "y", "z"].map((channel) => normalizer * lamp.reduce(
      (sum, value, index) => sum + Number(value) * Number(spectrum[index]) * Number(spectral.cie_1931[channel][index]),
      0,
    ));
  }

  function labFor(composition, illuminant) {
    const spectrum = reflectance(composition);
    const measured = xyz(spectrum, illuminant);
    const white = xyz(model.state.spectral_model.base_reflectance.map(() => 1), illuminant);
    const transform = (value) => value > 216 / 24389
      ? value ** (1 / 3)
      : ((24389 / 27) * value + 16) / 116;
    const [fx, fy, fz] = measured.map((value, index) => transform(value / white[index]));
    return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
  }

  function displayFor(composition, illuminant) {
    const [lightness, greenRed, blueYellow] = labFor(composition, illuminant);
    const fy = (lightness + 16) / 116;
    const fx = fy + greenRed / 500;
    const fz = fy - blueYellow / 200;
    const delta = 6 / 29;
    const inverse = (value) => value > delta ? value ** 3 : 3 * delta * delta * (value - 4 / 29);
    const x = 0.95047 * inverse(fx);
    const y = inverse(fy);
    const z = 1.08883 * inverse(fz);
    const linear = [
      3.2406 * x - 1.5372 * y - 0.4986 * z,
      -0.9689 * x + 1.8758 * y + 0.0415 * z,
      0.0557 * x - 0.2040 * y + 1.0570 * z,
    ];
    const cast = model.state.spectral_model.lamp_casts[illuminant];
    const encode = (value, index) => {
      const bounded = Math.max(0, Math.min(1, value));
      const channel = bounded <= 0.0031308 ? 12.92 * bounded : 1.055 * bounded ** (1 / 2.4) - 0.055;
      return Math.round(255 * Math.max(0, Math.min(1, channel * Number(cast[index]))));
    };
    return `rgb(${linear.map(encode).join(", ")})`;
  }

  function deltaE(composition, illuminant) {
    const sample = labFor(composition, illuminant);
    const target = model.state.target.lab[illuminant];
    return Math.sqrt(sample.reduce((sum, value, index) => sum + (value - Number(target[index])) ** 2, 0));
  }

  function resetSample() {
    model.stirred = false;
    model.sampledComposition = null;
    model.viewed = new Set();
    model.ready = false;
  }

  function clearFreshFailure() {
    document.querySelector(".dyeworks-verdict-fail")?.remove();
    document.querySelector(".dyeworks")?.classList.remove("is-fresh-fail");
  }

  function setMessage(message, status = "idle") {
    model.helpers.setReadout(message, status);
  }

  function bottleMarkup() {
    return model.state.pigments.map((pigment, index) => `
      <button type="button" class="dye-bottle${model.selectedPigment === pigment.id ? " is-selected" : ""}" data-pigment="${clean(pigment.id)}" style="--pigment:${clean(pigment.bottle)}" aria-label="Select ${clean(pigment.name)}">
        <span class="dye-bottle-stopper"></span>
        <span class="dye-bottle-glass"><i>${clean(pigment.short)}</i><b>${clean(pigment.name)}</b></span>
        <small>LOT ${String(index + 1).padStart(2, "0")}</small>
      </button>`).join("");
  }

  function tickMarkup() {
    const maximum = Number(parameters().maximum_units_per_pigment);
    const support = String(parameters().graduation_support || "numbered");
    const ticks = [];
    for (let units = 0; units <= maximum; units += 1) {
      const hidden = support === "sparse" && units > 0 && units < maximum && units % 2 === 1;
      const label = support === "numbered" && units > 0 ? String(units) : units === maximum ? "MAX" : "";
      ticks.push(`<i class="${hidden ? "is-faint" : ""}" style="--tick:${units / maximum}"><span>${label}</span></i>`);
    }
    return ticks.join("");
  }

  function vatMarkup() {
    const maximum = Number(parameters().fresh_vats);
    const vats = [];
    for (let index = 1; index <= maximum; index += 1) {
      const state = index < model.vatIndex ? "spent" : index === model.vatIndex ? "active" : "sealed";
      vats.push(`<i data-state="${state}"><span>${String(index).padStart(2, "0")}</span></i>`);
    }
    return vats.join("");
  }

  function recipeMarkup() {
    return model.state.pigments.map((pigment) => `
      <li style="--pigment:${clean(pigment.bottle)}"><span>${clean(pigment.short)}</span><b>${clean(pigment.name)}</b><i>${Number(model.composition[pigment.id] || 0)}</i></li>`).join("");
  }

  function updateControls() {
    const maximum = Number(parameters().maximum_units_per_pigment);
    const capacity = Number(parameters().vat_capacity_units);
    const loaded = document.getElementById("dye-loaded-units");
    const composition = document.getElementById("dye-composition");
    const headroom = document.getElementById("dye-headroom");
    const vatBank = document.getElementById("dye-vats");
    const vatNumber = document.getElementById("dye-vat-number");
    const plunger = document.getElementById("dye-plunger-handle");
    const proxyUnits = document.getElementById("dye-loaded-proxy-units");
    const inject = document.getElementById("dye-inject");
    const certification = document.getElementById("dye-certify");
    const daylightProof = document.querySelector('[data-proof="daylight"]');
    const sodiumProof = document.querySelector('[data-proof="sodium"]');
    if (loaded) loaded.textContent = model.loadedUnits > 0 ? String(model.loadedUnits) : "—";
    if (proxyUnits) proxyUnits.textContent = String(model.loadedUnits || 1);
    if (composition) composition.innerHTML = recipeMarkup();
    if (headroom) headroom.textContent = `${Math.max(0, capacity - totalUnits())} / ${capacity}`;
    if (vatBank) vatBank.innerHTML = vatMarkup();
    if (vatNumber) vatNumber.textContent = String(model.vatIndex).padStart(2, "0");
    if (plunger) plunger.style.setProperty("--plunger-ratio", String(model.loadedUnits / maximum));
    if (inject) inject.disabled = model.terminal || model.loadedUnits <= 0 || !model.selectedPigment;
    if (daylightProof) daylightProof.dataset.state = model.viewed.has("daylight") ? "seen" : "unseen";
    if (sodiumProof) sodiumProof.dataset.state = model.viewed.has("sodium") ? "seen" : "unseen";
    const bothViewed = LAMPS.every((lamp) => model.viewed.has(lamp));
    if (certification) {
      certification.disabled = model.terminal || !bothViewed;
      certification.textContent = bothViewed ? "TEST TWO-LIGHT MATCH" : "VIEW BOTH LAMPS";
    }
    document.querySelectorAll(".dye-bottle").forEach((node) => node.classList.toggle("is-selected", node.dataset.pigment === model.selectedPigment));
  }

  function updateColours() {
    document.body.dataset.dyeLamp = model.lamp;
    const ribbon = document.getElementById("target-ribbon");
    const sample = document.getElementById("sample-strip");
    const liquid = document.getElementById("vat-liquid");
    const lampName = document.getElementById("lamp-name");
    const lampSwitch = document.getElementById("lamp-switch");
    if (ribbon) ribbon.style.setProperty("--swatch", model.state.target.display[model.lamp]);
    if (sample) {
      sample.style.setProperty("--swatch", model.sampledComposition ? displayFor(model.sampledComposition, model.lamp) : "#d8cfb4");
      sample.dataset.state = model.sampledComposition ? "dipped" : "blank";
    }
    if (liquid) {
      liquid.style.setProperty("--liquid", totalUnits() ? displayFor(model.composition, model.lamp) : "#b6aa83");
      liquid.style.setProperty("--fill", `${Math.max(8, Math.min(100, totalUnits() / Number(parameters().vat_capacity_units) * 100))}%`);
    }
    if (lampName) lampName.textContent = model.state.lamp_labels[model.lamp];
    if (lampSwitch) lampSwitch.dataset.lamp = model.lamp;
  }

  function recomputeReady() {
    const tolerance = Number(parameters().tolerance_delta_e);
    model.ready = Boolean(
      sameComposition(model.sampledComposition, model.composition)
      && LAMPS.every((lamp) => model.viewed.has(lamp))
      && recipeWithinSpec()
      && LAMPS.every((lamp) => deltaE(model.composition, lamp) <= tolerance),
    );
    updateControls();
  }

  function selectPigment(pigmentId) {
    if (model.busy || model.terminal || !model.pigmentById[pigmentId]) return;
    clearFreshFailure();
    model.selectedPigment = pigmentId;
    updateControls();
    setMessage(`${model.pigmentById[pigmentId].name} AT THE SYRINGE`, "idle");
  }

  function changeDose(delta) {
    if (model.interaction !== "simplified" || model.busy || model.terminal) return;
    clearFreshFailure();
    const maximum = Number(parameters().maximum_units_per_pigment);
    model.loadedUnits = Math.max(1, Math.min(maximum, model.loadedUnits + delta));
    updateControls();
  }

  function injectDose() {
    if (model.busy || model.terminal || !model.selectedPigment || model.loadedUnits <= 0) return;
    clearFreshFailure();
    const capacity = Number(parameters().vat_capacity_units);
    if (totalUnits() + model.loadedUnits > capacity) {
      setMessage("VAT HEADROOM REFUSES THAT DOSE", "error");
      return;
    }
    const details = {
      pigment: model.selectedPigment,
      units: model.loadedUnits,
      input_source: model.interaction === "full" ? "plunger_drag" : "dose_buttons",
    };
    if (model.interaction === "full") {
      if (!model.pendingPlungerGesture) {
        setMessage("DRAW THE PLUNGER TO A MARK FIRST", "error");
        return;
      }
      details.gesture = {...model.pendingPlungerGesture};
    }
    addEvent("dose", details);
    model.composition[model.selectedPigment] += model.loadedUnits;
    model.totalDispensed += model.loadedUnits;
    resetSample();
    setMessage(`${model.pigmentById[model.selectedPigment].name} INJECTED · STIR BEFORE DIPPING`, "idle");
    model.loadedUnits = model.interaction === "full" ? 0 : 1;
    model.pendingPlungerGesture = null;
    updateControls();
    updateColours();
  }

  function beginPlunger(event) {
    if (model.interaction !== "full" || model.busy || model.terminal || event.button !== 0) return;
    const track = document.getElementById("dye-plunger-track");
    if (!track) return;
    event.preventDefault();
    clearFreshFailure();
    const rect = track.getBoundingClientRect();
    model.loadedUnits = 0;
    model.pendingPlungerGesture = null;
    model.plungerDrag = {pointerId: event.pointerId, rect, lastX: event.clientX, lastY: event.clientY, travel: 0, samples: 1};
    try { event.currentTarget.setPointerCapture(event.pointerId); } catch (_error) { /* capture unsupported */ }
    updateControls();
  }

  function movePlunger(event) {
    const drag = model.plungerDrag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    drag.travel += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY);
    drag.lastX = event.clientX;
    drag.lastY = event.clientY;
    drag.samples += 1;
    const maximum = Number(parameters().maximum_units_per_pigment);
    const ratio = Math.max(1 / maximum, Math.min(1, (event.clientY - drag.rect.top) / drag.rect.height));
    model.loadedUnits = Math.max(1, Math.min(maximum, Math.round(ratio * maximum)));
    updateControls();
  }

  function endPlunger(event, cancelled = false) {
    const drag = model.plungerDrag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    model.plungerDrag = null;
    try { event.currentTarget.releasePointerCapture(event.pointerId); } catch (_error) { /* already released */ }
    if (cancelled || model.loadedUnits <= 0 || drag.travel < 18) {
      model.loadedUnits = 0;
      model.pendingPlungerGesture = null;
      updateControls();
      setMessage("PLUNGER RETURNED · DRAW TO A GRADUATION", "error");
      return;
    }
    const maximum = Number(parameters().maximum_units_per_pigment);
    model.pendingPlungerGesture = {
      travel_px: Number(drag.travel.toFixed(2)),
      sample_count: drag.samples,
      start_ratio: 0,
      end_ratio: Number((model.loadedUnits / maximum).toFixed(4)),
    };
    updateControls();
    setMessage(`${model.loadedUnits} GRADUATION${model.loadedUnits === 1 ? "" : "S"} DRAWN · INJECT WHEN READY`, "idle");
  }

  function completeStir(inputSource, gesture = null) {
    if (model.busy || model.terminal || totalUnits() <= 0) {
      setMessage("THE VAT IS EMPTY", "error");
      return;
    }
    const details = {input_source: inputSource};
    if (gesture) details.gesture = gesture;
    addEvent("stir", details);
    model.stirred = true;
    setMessage("DYE EVEN · DIP A FRESH STRIP", "idle");
    document.querySelector(".vat-basin")?.classList.add("is-stirred");
    window.setTimeout(() => document.querySelector(".vat-basin")?.classList.remove("is-stirred"), 480);
  }

  function beginStir(event) {
    if (model.interaction !== "full" || model.busy || model.terminal || event.button !== 0 || totalUnits() <= 0) return;
    const vat = document.querySelector(".vat-basin");
    if (!vat) return;
    event.preventDefault();
    clearFreshFailure();
    const rect = vat.getBoundingClientRect();
    const centerX = rect.x + rect.width / 2;
    const centerY = rect.y + rect.height / 2;
    const angle = Math.atan2(event.clientY - centerY, event.clientX - centerX);
    model.stirDrag = {pointerId: event.pointerId, centerX, centerY, lastAngle: angle, sweep: 0, lastX: event.clientX, lastY: event.clientY, travel: 0, samples: 1};
    try { event.currentTarget.setPointerCapture(event.pointerId); } catch (_error) { /* capture unsupported */ }
  }

  function moveStir(event) {
    const drag = model.stirDrag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    const angle = Math.atan2(event.clientY - drag.centerY, event.clientX - drag.centerX);
    let difference = angle - drag.lastAngle;
    while (difference > Math.PI) difference -= Math.PI * 2;
    while (difference < -Math.PI) difference += Math.PI * 2;
    drag.sweep += Math.abs(difference);
    drag.travel += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY);
    drag.lastAngle = angle;
    drag.lastX = event.clientX;
    drag.lastY = event.clientY;
    drag.samples += 1;
    event.currentTarget.style.setProperty("--stir-angle", `${drag.sweep}rad`);
  }

  function endStir(event, cancelled = false) {
    const drag = model.stirDrag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    model.stirDrag = null;
    try { event.currentTarget.releasePointerCapture(event.pointerId); } catch (_error) { /* already released */ }
    if (cancelled || drag.sweep < 5 || drag.travel < 180 || drag.samples < 8) {
      setMessage("STIR A COMPLETE CIRCLE THROUGH THE VAT", "error");
      return;
    }
    completeStir("stir_gesture", {
      angular_sweep_rad: Number(drag.sweep.toFixed(4)),
      travel_px: Number(drag.travel.toFixed(2)),
      sample_count: drag.samples,
    });
  }

  function completeDip(inputSource, gesture = null) {
    if (model.busy || model.terminal || !model.stirred || totalUnits() <= 0) {
      setMessage(totalUnits() <= 0 ? "THE VAT IS EMPTY" : "STIR BEFORE DIPPING", "error");
      return;
    }
    const details = {input_source: inputSource};
    if (gesture) details.gesture = gesture;
    addEvent("dip", details);
    model.sampledComposition = cloneComposition(model.composition);
    model.viewed = new Set([model.lamp]);
    updateColours();
    recomputeReady();
    setMessage(`${model.state.lamp_labels[model.lamp]} SAMPLE CLIPPED · SWITCH LAMPS`, "idle");
  }

  function beginStrip(event) {
    if (model.interaction !== "full" || model.busy || model.terminal || event.button !== 0) return;
    event.preventDefault();
    clearFreshFailure();
    model.stripDrag = {pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, lastX: event.clientX, lastY: event.clientY, travel: 0, samples: 1, node: event.currentTarget};
    event.currentTarget.classList.add("is-dragging");
    try { event.currentTarget.setPointerCapture(event.pointerId); } catch (_error) { /* capture unsupported */ }
  }

  function moveStrip(event) {
    const drag = model.stripDrag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    drag.travel += Math.hypot(event.clientX - drag.lastX, event.clientY - drag.lastY);
    drag.lastX = event.clientX;
    drag.lastY = event.clientY;
    drag.samples += 1;
    drag.node.style.setProperty("--strip-x", `${event.clientX - drag.startX}px`);
    drag.node.style.setProperty("--strip-y", `${event.clientY - drag.startY}px`);
  }

  function stripDropWitness(event, drag) {
    const opening = document.querySelector(".vat-rim")?.getBoundingClientRect();
    if (!opening) return null;
    // The dark rim is not liquid. Keep the accepted ellipse twelve pixels
    // inside its visible border so a release must land clearly in the opening.
    const inset = 12;
    const radiusX = opening.width / 2 - inset;
    const radiusY = opening.height / 2 - inset;
    if (radiusX <= 0 || radiusY <= 0) return null;
    const centerX = opening.left + opening.width / 2;
    const centerY = opening.top + opening.height / 2;
    const normalizedX = (event.clientX - centerX) / radiusX;
    const normalizedY = (event.clientY - centerY) / radiusY;
    const ellipseValue = normalizedX * normalizedX + normalizedY * normalizedY;
    const round = (value, places = 2) => Number(value.toFixed(places));
    return {
      inside: ellipseValue <= 1,
      gesture: {
        travel_px: round(drag.travel),
        sample_count: drag.samples,
        target_region: "vat_opening_inner_ellipse_v1",
        start_x: round(drag.startX),
        start_y: round(drag.startY),
        end_x: round(event.clientX),
        end_y: round(event.clientY),
        opening_left: round(opening.left),
        opening_top: round(opening.top),
        opening_width: round(opening.width),
        opening_height: round(opening.height),
        opening_inset_px: inset,
        endpoint_normalized_x: round(normalizedX, 5),
        endpoint_normalized_y: round(normalizedY, 5),
        endpoint_ellipse_value: round(ellipseValue, 5),
      },
    };
  }

  function endStrip(event, cancelled = false) {
    const drag = model.stripDrag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    model.stripDrag = null;
    drag.node.classList.remove("is-dragging");
    drag.node.style.removeProperty("--strip-x");
    drag.node.style.removeProperty("--strip-y");
    try { drag.node.releasePointerCapture(event.pointerId); } catch (_error) { /* already released */ }
    const witness = stripDropWitness(event, drag);
    if (cancelled || !witness?.inside || drag.travel < 70 || drag.samples < 2) {
      setMessage("STRIP MISSED THE VAT", "error");
      return;
    }
    completeDip("strip_drag", witness.gesture);
  }

  function toggleLamp() {
    if (model.busy || model.terminal) return;
    clearFreshFailure();
    model.lamp = model.lamp === "daylight" ? "sodium" : "daylight";
    addEvent("lamp", {illuminant: model.lamp, input_source: "lamp_switch"});
    if (sameComposition(model.sampledComposition, model.composition)) model.viewed.add(model.lamp);
    updateColours();
    recomputeReady();
    const bothViewed = LAMPS.every((lamp) => model.viewed.has(lamp));
    setMessage(
      bothViewed ? "BOTH LAMPS VIEWED · TEST OR ADJUST" : `${model.state.lamp_labels[model.lamp]} ENGAGED`,
      "idle",
    );
  }

  async function submit(completed) {
    if (model.busy) return;
    model.busy = true;
    document.querySelectorAll(".dyeworks button").forEach((button) => { button.disabled = true; });
    setMessage(completed ? "THE GUILD IS READING BOTH LAMPS…" : "NO FRESH VATS REMAIN…", "pending");
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      events: model.events,
      final_composition: cloneComposition(model.composition),
      vat_index: model.vatIndex,
      vats_consumed: model.vatIndex,
      total_dispensed: model.totalDispensed,
      lamp: model.lamp,
      completed,
    };
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload)});
      const outcome = await response.json();
      if (outcome.passed === true) {
        model.terminal = true;
        document.querySelector(".dyeworks")?.classList.add("is-pass");
        document.querySelector(".dyeworks")?.insertAdjacentHTML("beforeend", '<div class="dyeworks-verdict dyeworks-verdict-pass"><small>DYERS GUILD · BOTH LAMPS</small><strong>PASS</strong><span>LOT SEALED</span></div>');
        setMessage("PASS", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await model.helpers.render(outcome.state);
        const shell = document.querySelector(".dyeworks");
        shell?.classList.add("is-fresh-fail");
        shell?.insertAdjacentHTML("beforeend", '<div class="dyeworks-verdict dyeworks-verdict-fail"><small>VATS EXHAUSTED · FRESH LOT</small><strong>FAIL</strong><span>NEW RIBBON ISSUED</span></div>');
        model.helpers.setReadout("FAIL · FRESH DYE LOT", "error");
      } else {
        model.busy = false;
        model.terminal = false;
        updateControls();
        setMessage("LOT UNGRADED · BENCH REMAINS OPEN", "error");
      }
    } catch (_error) {
      model.busy = false;
      model.terminal = false;
      updateControls();
      setMessage("GUILD LINE OFFLINE · TRY AGAIN", "error");
    }
  }

  function certify() {
    if (model.busy || model.terminal) return;
    const bothViewed = LAMPS.every((lamp) => model.viewed.has(lamp));
    if (!bothViewed || !sameComposition(model.sampledComposition, model.composition)) {
      setMessage("DIP ONE CURRENT STRIP AND VIEW BOTH LAMPS", "error");
      return;
    }
    if (!model.ready) {
      addEvent("check", {input_source: "certify_button"});
      if (!recipeWithinSpec()) {
        const dyeRange = rangeLabel(parameters().target_components_min, parameters().target_components_max);
        const unitRange = rangeLabel(parameters().target_total_min, parameters().target_total_max);
        setMessage(`LOT SPEC MISSED · USE ${dyeRange} DYES / ${unitRange} TOTAL UNITS`, "error");
      } else {
        setMessage("RIBBON DISAGREES · ADD DYE OR DUMP THE VAT", "error");
      }
      return;
    }
    addEvent("certify", {input_source: "certify_button"});
    model.terminal = true;
    submit(true);
  }

  function dumpVat() {
    if (model.busy || model.terminal) return;
    clearFreshFailure();
    addEvent("dump", {input_source: "dump_valve"});
    const maximum = Number(parameters().fresh_vats);
    if (model.vatIndex >= maximum) {
      model.terminal = true;
      submit(false);
      return;
    }
    model.vatIndex += 1;
    model.composition = Object.fromEntries(model.state.pigments.map((pigment) => [pigment.id, 0]));
    model.loadedUnits = model.interaction === "full" ? 0 : 1;
    model.pendingPlungerGesture = null;
    resetSample();
    updateControls();
    updateColours();
    setMessage(`VAT ${String(model.vatIndex).padStart(2, "0")} OPEN · THE OLD MIX IS GONE`, "idle");
  }

  function bindInteractions() {
    document.querySelectorAll(".dye-bottle").forEach((button) => button.addEventListener("click", () => selectPigment(button.dataset.pigment)));
    document.getElementById("dose-minus")?.addEventListener("click", () => changeDose(-1));
    document.getElementById("dose-plus")?.addEventListener("click", () => changeDose(1));
    document.getElementById("dye-inject")?.addEventListener("click", injectDose);
    document.getElementById("dye-stir-button")?.addEventListener("click", () => completeStir("stir_button"));
    document.getElementById("dye-dip-button")?.addEventListener("click", () => completeDip("dip_button"));
    document.getElementById("lamp-switch")?.addEventListener("click", toggleLamp);
    document.getElementById("dye-certify")?.addEventListener("click", certify);
    document.getElementById("dump-vat")?.addEventListener("click", dumpVat);
    const plunger = document.getElementById("dye-plunger-handle");
    plunger?.addEventListener("pointerdown", beginPlunger);
    plunger?.addEventListener("pointermove", movePlunger);
    plunger?.addEventListener("pointerup", (event) => endPlunger(event));
    plunger?.addEventListener("pointercancel", (event) => endPlunger(event, true));
    const stirrer = document.getElementById("dye-stirrer");
    stirrer?.addEventListener("pointerdown", beginStir);
    stirrer?.addEventListener("pointermove", moveStir);
    stirrer?.addEventListener("pointerup", (event) => endStir(event));
    stirrer?.addEventListener("pointercancel", (event) => endStir(event, true));
    const strip = document.getElementById("test-strip-source");
    strip?.addEventListener("pointerdown", beginStrip);
    strip?.addEventListener("pointermove", moveStrip);
    strip?.addEventListener("pointerup", (event) => endStrip(event));
    strip?.addEventListener("pointercancel", (event) => endStrip(event, true));
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "two-lamp-dyeworks";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const interaction = state.control_condition?.interaction || "full";
    const visiblePrompt = String(state.prompt || "").split(" Solve only from screenshots")[0];
    const composition = Object.fromEntries(state.pigments.map((pigment) => [pigment.id, 0]));
    Object.assign(model, {
      state,
      helpers,
      interaction,
      pigmentById: Object.fromEntries(state.pigments.map((pigment) => [pigment.id, pigment])),
      selectedPigment: state.pigments[0]?.id || null,
      composition,
      loadedUnits: interaction === "full" ? 0 : 1,
      pendingPlungerGesture: null,
      lamp: state.initial_lamp || "daylight",
      stirred: false,
      sampledComposition: null,
      viewed: new Set(),
      ready: false,
      events: [],
      vatIndex: 1,
      totalDispensed: 0,
      terminal: false,
      busy: false,
      plungerDrag: null,
      stirDrag: null,
      stripDrag: null,
    });
    helpers.app.innerHTML = `
      <section class="dyeworks" data-interaction="${clean(interaction)}" data-challenge-id="${clean(state.challenge_id)}">
        <header class="dye-header">
          <div class="dye-title"><span>CHROMATIC GUILD · BENCH 02</span><h1>TWO-LAMP DYEWORKS</h1></div>
          <p>${clean(visiblePrompt)} <small>VISIBLE CONTROLS ONLY</small></p>
          <div class="dye-tolerance"><small>SEALED LOT SPEC</small><b>${rangeLabel(state.parameters.target_components_min, state.parameters.target_components_max)} DYES</b><span>${rangeLabel(state.parameters.target_total_min, state.parameters.target_total_max)} UNITS · ΔE ${Number(state.parameters.tolerance_delta_e).toFixed(1)}</span></div>
        </header>
        <main class="dye-bench">
          <section class="dye-mixing-console">
            <header><span>PIGMENT LOCKER</span><i>${state.pigments.length} ACTIVE LOTS</i></header>
            <div class="dye-bottle-rack">${bottleMarkup()}</div>
            <div class="dye-dose-console">
              <div class="dye-syringe">
                <span class="dye-syringe-cap">SYRINGE</span>
                <div class="dye-plunger-track" id="dye-plunger-track">${tickMarkup()}<button type="button" id="dye-plunger-handle" class="dye-plunger-handle" aria-label="Drag syringe plunger"></button></div>
                <div class="dye-syringe-barrel"><span id="dye-loaded-units">${model.loadedUnits || "—"}</span><i>DRAW</i></div>
              </div>
              <div class="dye-dose-proxy">
                <small>SET DRAW</small><div><button type="button" id="dose-minus">−</button><b id="dye-loaded-proxy">DRAW <span id="dye-loaded-proxy-units">${model.loadedUnits || 1}</span></b><button type="button" id="dose-plus">+</button></div>
              </div>
              <button type="button" class="dye-inject" id="dye-inject">INJECT INTO VAT</button>
            </div>
          </section>
          <section class="dye-centre-stage">
            <div class="dye-lamp-rig">
              <div class="dye-lamp dye-lamp-day"><i></i><span>NORTH-LIGHT</span></div>
              <button type="button" class="lamp-switch" id="lamp-switch" data-lamp="daylight" aria-label="Toggle inspection lamp"><i></i><b id="lamp-name">NORTH-LIGHT</b><span>FLIP LAMP</span></button>
              <div class="dye-lamp dye-lamp-sodium"><i></i><span>SODIUM</span></div>
            </div>
            <div class="dye-inspection-hood">
              <div class="dye-swatch-card dye-target-card"><small>PINNED MASTER</small><div class="target-ribbon" id="target-ribbon"><i></i></div><b>RIBBON</b></div>
              <div class="dye-comparison-mark"><span>≈</span><small>SAME LIGHT<br>SAME SILK</small></div>
              <div class="dye-swatch-card dye-sample-card"><small>WET PROOF</small><div class="sample-strip" id="sample-strip" data-state="blank"><i></i></div><b>TEST STRIP</b></div>
            </div>
            <div class="dye-vat-plinth">
              <div class="vat-basin"><div class="vat-rim"><div class="vat-liquid" id="vat-liquid"></div></div><button type="button" id="dye-stirrer" class="dye-stirrer" aria-label="Stir the vat in a complete circle"><i></i></button><span class="vat-number">VAT <b id="dye-vat-number">${String(model.vatIndex).padStart(2, "0")}</b></span></div>
              <div class="dye-strip-source"><button type="button" id="test-strip-source" class="test-strip-source" aria-label="Drag test strip into vat"><i></i><span>FRESH STRIP</span></button></div>
            </div>
          </section>
          <aside class="dye-process-panel">
            <header><span>LOT BOOK</span><i>IRREVERSIBLE</i></header>
            <div class="dye-vat-bank"><small>FRESH VATS</small><div id="dye-vats">${vatMarkup()}</div></div>
            <div class="dye-headroom"><span>VAT HEADROOM</span><b id="dye-headroom">${parameters().vat_capacity_units} / ${parameters().vat_capacity_units}</b></div>
            <ol class="dye-composition" id="dye-composition">${recipeMarkup()}</ol>
            <div class="dye-proof-ledger"><span data-proof="daylight" data-state="unseen"><i></i>NORTH-LIGHT</span><span data-proof="sodium" data-state="unseen"><i></i>SODIUM</span></div>
            <div class="dye-process-actions">
              <button type="button" id="dye-stir-button">STIR VAT</button>
              <button type="button" id="dye-dip-button">DIP STRIP</button>
            </div>
            <button type="button" class="dump-vat" id="dump-vat"><span>↯</span>DUMP THIS VAT</button>
          </aside>
        </main>
        <footer class="dye-footer"><div class="readout" data-status="idle">SELECT A PIGMENT · DRAW A DOSE</div><button type="button" id="dye-certify" class="dye-certify" disabled>VIEW BOTH LAMPS</button></footer>
        ${helpers.cheatPanelTemplate()}
      </section>`;
    bindInteractions();
    updateControls();
    updateColours();
    helpers.installCheatPanel();
    window.twoLampDyeworksModel = model;
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.two_lamp_dyeworks = {rootSelector: ".dyeworks", render};
})();
