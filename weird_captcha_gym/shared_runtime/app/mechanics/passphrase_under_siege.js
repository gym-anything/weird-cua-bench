(() => {
  "use strict";

  const DEFAULT_SIZE = 18;
  const VOWELS = new Set(Array.from("AEIOUaeiou"));
  let model = null;

  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

  const taskNow = () => Math.max(0, Math.floor(performance.now() - model.startedAt));

  function record(kind, details = {}) {
    const event = {
      sequence: model.events.length + 1,
      kind,
      t_ms: taskNow(),
      ...details,
    };
    model.events.push(event);
    model.lastEventTime = event.t_ms;
    return event;
  }

  function textValue() {
    return model.glyphs.map((glyph) => glyph.char).join("");
  }

  function digitSum(text) {
    return Array.from(text).filter((char) => /[0-9]/.test(char)).reduce((sum, char) => sum + Number(char), 0);
  }

  function oneOccurrence(text, token) {
    if (!token) return null;
    const start = text.indexOf(token);
    if (start < 0 || text.indexOf(token, start + 1) >= 0) return null;
    return [start, start + token.length];
  }

  function styleExactly(range, attribute, value) {
    if (!range) return false;
    const [start, end] = range;
    return model.glyphs.every((glyph, index) => {
      let expected = value;
      if (index < start || index >= end) {
        if (attribute === "bold" || attribute === "italic") expected = false;
        else if (attribute === "font") expected = "mono";
        else expected = DEFAULT_SIZE;
      }
      return glyph[attribute] === expected;
    });
  }

  function fontRangesExactly(required, allowed = null) {
    if (!required) return false;
    const [start, end] = required;
    return model.glyphs.every((glyph, index) => {
      if (index >= start && index < end) return glyph.font === "serif";
      if (allowed && index >= allowed[0] && index < allowed[1]) return glyph.font === "mono" || glyph.font === "serif";
      return glyph.font === "mono";
    });
  }

  function rulePassed(ruleId) {
    const text = textValue();
    const stamp = String(model.state.clues.stamp || "");
    const color = String(model.state.clues.color || "");
    const gauge = String(model.state.clues.gauge_token || "");
    const stampRange = oneOccurrence(text, stamp);
    const colorRange = color ? oneOccurrence(text, color) : null;
    const gaugeRange = gauge ? oneOccurrence(text, gauge) : null;
    switch (ruleId) {
      case "minimum_length": return text.length >= Number(model.contract.minimum_length);
      case "uppercase": return /[A-Z]/.test(text);
      case "special_mark": return text.includes("!");
      case "digit_sum": return digitSum(text) === Number(model.contract.digit_sum_target);
      case "stamp": return stampRange !== null;
      case "color": return colorRange !== null;
      case "gauge": return gaugeRange !== null;
      case "clue_order": {
        if (!stampRange) return false;
        const starts = [stampRange[0]];
        if (color) {
          if (!colorRange) return false;
          starts.push(colorRange[0]);
        }
        if (gauge) {
          if (!gaugeRange) return false;
          starts.push(gaugeRange[0]);
        }
        return starts.every((value, index) => index === 0 || starts[index - 1] < value);
      }
      case "exact_length": return text.length === Number(model.contract.exact_length);
      case "bold_vowels": return model.glyphs.length > 0 && model.glyphs.every((glyph) => glyph.bold === VOWELS.has(glyph.char));
      case "stamp_bold": return styleExactly(stampRange, "bold", true);
      case "stamp_italic": return styleExactly(stampRange, "italic", true);
      case "stamp_font": return fontRangesExactly(stampRange, model.contract.color_font ? colorRange : null);
      case "gauge_size": {
        if (!gaugeRange) return false;
        const [start, end] = gaugeRange;
        const digitIndices = [];
        for (let index = start; index < end; index += 1) if (/[0-9]/.test(model.glyphs[index].char)) digitIndices.push(index);
        if (!digitIndices.length) return false;
        return model.glyphs.every((glyph, index) => glyph.size === (digitIndices.includes(index) ? Number(model.contract.gauge_size_px) : DEFAULT_SIZE));
      }
      case "color_font": return fontRangesExactly(colorRange, stampRange);
      case "hatchling": return !model.starved && model.feedCount >= Number(model.contract.feed_required);
      case "embers": {
        const expected = new Set(model.state.embers.map((ember) => ember.id));
        return model.damaged.size === 0 && model.quenched.size === expected.size && [...expected].every((id) => model.quenched.has(id));
      }
      default: return false;
    }
  }

  function ruleResults() {
    return model.state.rules.map((rule) => rulePassed(rule.id));
  }

  function updateProgress(results) {
    let prefix = 0;
    for (const passed of results) {
      if (!passed) break;
      prefix += 1;
    }
    model.highestPrefix = Math.max(model.highestPrefix, prefix);
    let unlocked = model.unlocked;
    while (unlocked < results.length && results.slice(0, unlocked).every(Boolean)) unlocked += 1;
    model.unlocked = unlocked;
  }

  function maybeStartHazards() {
    if (model.hazardStartedAt !== null) return;
    if (!model.state.embers.length && !Number(model.contract.feed_required)) return;
    const staticRules = model.state.rules.filter((rule) => !["hatchling", "embers"].includes(rule.id));
    if (!staticRules.every((rule) => rulePassed(rule.id))) return;
    model.hazardStartedAt = model.lastEventTime;
    if (Number(model.contract.feed_required)) {
      model.hungerDeadline = model.hazardStartedAt + Number(model.contract.hunger_ms);
      model.nextFeedReadyAt = model.hazardStartedAt;
    }
    document.querySelector(".siege-editor-shell")?.classList.add("is-under-siege");
  }

  function glyphMarkup(glyph, index) {
    const selected = model.selection && index >= model.selection[0] && index < model.selection[1];
    const caret = model.selection === null && model.cursor === index;
    const classes = ["siege-char"];
    if (selected) classes.push("is-selected");
    if (caret) classes.push("is-caret");
    if (glyph.bold) classes.push("is-bold");
    if (glyph.italic) classes.push("is-italic");
    if (glyph.font === "serif") classes.push("is-serif");
    return `<span class="${classes.join(" ")}" data-index="${index}" style="--char-size:${Number(glyph.size)}px">${esc(glyph.char === " " ? "\u00a0" : glyph.char)}</span>`;
  }

  function renderDocument() {
    const editor = document.querySelector(".siege-editor");
    if (!editor) return;
    const glyphs = model.glyphs.map(glyphMarkup).join("");
    const endCaret = model.selection === null && model.cursor === model.glyphs.length ? '<i class="siege-end-caret"></i>' : "";
    editor.innerHTML = glyphs || '<span class="siege-placeholder">TYPE INTO THE LIVE LEDGER…</span>';
    editor.insertAdjacentHTML("beforeend", endCaret);
    editor.setAttribute("aria-label", `${model.glyphs.length} character passphrase editor`);
  }

  function stampWidget() {
    return `<div class="siege-stamp" aria-hidden="true">${Array.from(model.state.clues.stamp).map((char, index) => `<b style="--smudge:${index % 2 ? -2 : 2}deg">${esc(char)}</b>`).join("")}</div>`;
  }

  function colorWidget() {
    const color = String(model.state.clues.color || "");
    return `<div class="siege-chip" style="--chip:${esc(color)}" aria-label="Colour chip register ${esc(color)}">
      <span aria-hidden="true"><i></i><i></i><i></i></span><code class="siege-chip-code">${esc(color)}</code>
    </div>`;
  }

  function gaugeWidget() {
    const value = Number(model.state.clues.gauge_value);
    const angle = -180 + (value / 12) * 180;
    const ticks = Array.from({length: 13}, (_unused, tickValue) => {
      const tickAngle = -180 + (tickValue / 12) * 180;
      const radians = tickAngle * Math.PI / 180;
      const labelX = 50 + Math.cos(radians) * 40;
      const labelY = 88 + Math.sin(radians) * 67;
      const major = tickValue % 3 === 0 ? " is-major" : "";
      return `<i class="siege-gauge-tick${major}" style="--tick:${tickAngle}deg"></i><b class="siege-gauge-label" style="--label-x:${labelX}%;--label-y:${labelY}%">${tickValue}</b>`;
    }).join("");
    return `<div class="siege-gauge-widget">
      <div class="siege-gauge" style="--needle:${angle}deg" aria-label="Analogue integer pressure gauge from 0 to 12; read the needle against the labelled scale">
        ${ticks}
        <i class="siege-gauge-needle"></i><b class="siege-gauge-hub"></b>
      </div>
      <span class="siege-gauge-caption">PRESSURE<br>INTEGER SCALE</span>
    </div>`;
  }

  function feedIsReady(nowMs = taskNow()) {
    return model.nextFeedReadyAt !== null && nowMs >= model.nextFeedReadyAt;
  }

  function feedPhaseLabel(nowMs = taskNow()) {
    const required = Number(model.contract.feed_required);
    if (model.feedCount >= required) return "FED";
    if (feedIsReady(nowMs)) return "GRAIN READY";
    const seconds = Math.max(0, (Number(model.nextFeedReadyAt) - nowMs) / 1000);
    return `NEXT GRAIN ${seconds.toFixed(1)}s`;
  }

  function ruleWidget(rule) {
    if (rule.widget === "stamp") return stampWidget();
    if (rule.widget === "color") return colorWidget();
    if (rule.widget === "gauge") return gaugeWidget();
    if (rule.widget === "hatchling") return `<div class="siege-mini-status"><span>FEED ${model.feedCount}/${Number(model.contract.feed_required)}</span><span class="siege-feed-phase">${model.starved ? "STARVED" : feedPhaseLabel()}</span></div>`;
    if (rule.widget === "ember") return `<div class="siege-mini-status"><span>QUENCHED ${model.quenched.size}/${model.state.embers.length}</span><span>${model.damaged.size ? "BREACH" : "CLEAR"}</span></div>`;
    return "";
  }

  function renderRules(results) {
    const column = document.querySelector(".siege-rules");
    if (!column) return;
    column.innerHTML = model.state.rules.slice(0, model.unlocked).map((rule, index) => `
      <article class="siege-rule ${results[index] ? "is-green" : "is-red"}" data-rule-id="${esc(rule.id)}">
        <strong><span>${String(index + 1).padStart(2, "0")}</span>${esc(rule.title)}</strong>
        <p>${esc(rule.text)}</p>
        ${ruleWidget(rule)}
        <i aria-hidden="true">${results[index] ? "✓" : "×"}</i>
      </article>
    `).join("");
    column.scrollTop = column.scrollHeight;
  }

  function renderCounters(results) {
    const text = textValue();
    const allGreen = results.length > 0 && results.every(Boolean);
    const chars = document.querySelector(".siege-char-count");
    const digits = document.querySelector(".siege-digit-count");
    const ruleCounter = document.querySelector(".siege-rule-count");
    if (chars) chars.textContent = `${text.length}${Number(model.contract.exact_length) ? ` / ${Number(model.contract.exact_length)}` : ""} CHARS`;
    if (digits) digits.textContent = `Σ DIGITS ${digitSum(text)} / ${Number(model.contract.digit_sum_target)}`;
    if (ruleCounter) ruleCounter.textContent = `${results.filter(Boolean).length} / ${results.length} GREEN`;
    const seal = document.querySelector(".siege-seal");
    if (seal) seal.disabled = !allGreen || model.phase !== "edit";
    const quench = document.querySelector(".siege-quench-proxy");
    if (quench) quench.hidden = model.interaction !== "simplified" || activeEmbers(taskNow()).length === 0;
  }

  function updateAll() {
    if (!model || model.disposed) return;
    let results = ruleResults();
    updateProgress(results);
    maybeStartHazards();
    results = ruleResults();
    updateProgress(results);
    renderDocument();
    renderRules(results);
    renderCounters(results);
    renderHatchling();
  }

  function characterIndexFromPoint(x, y) {
    const node = document.elementFromPoint(x, y)?.closest?.(".siege-char");
    if (!node) return null;
    return Number(node.dataset.index);
  }

  function finishSelection(anchor, focus, source) {
    const start = Math.min(anchor, focus);
    const end = Math.max(anchor, focus) + 1;
    model.selection = [start, end];
    model.selectionSource = source;
    model.cursor = end;
    record("select", {start, end, input_source: source});
    updateAll();
  }

  function installEditorInteractions() {
    const editor = document.querySelector(".siege-editor");
    if (!editor) return;
    editor.addEventListener("keydown", (event) => {
      if (model.phase !== "edit" || event.metaKey || event.altKey) return;
      if (event.ctrlKey && event.key.toLowerCase() === "a") {
        event.preventDefault();
        if (model.glyphs.length) finishSelection(0, model.glyphs.length - 1, "keyboard_select_all");
        return;
      }
      if (event.key === "ArrowLeft" || event.key === "ArrowRight" || event.key === "Home" || event.key === "End") {
        event.preventDefault();
        if (event.key === "ArrowLeft") model.cursor = Math.max(0, model.cursor - 1);
        if (event.key === "ArrowRight") model.cursor = Math.min(model.glyphs.length, model.cursor + 1);
        if (event.key === "Home") model.cursor = 0;
        if (event.key === "End") model.cursor = model.glyphs.length;
        model.selection = null;
        model.selectionSource = null;
        renderDocument();
        return;
      }
      if (event.key === "Backspace") {
        event.preventDefault();
        record("backspace", {input_source: "physical_keyboard"});
        if (model.selection) {
          const [start, end] = model.selection;
          model.glyphs.splice(start, end - start);
          model.cursor = start;
        } else if (model.cursor > 0) {
          model.glyphs.splice(model.cursor - 1, 1);
          model.cursor -= 1;
        }
        model.selection = null;
        model.selectionSource = null;
        updateAll();
        return;
      }
      if (event.key.length === 1 && !event.ctrlKey && event.key.charCodeAt(0) >= 32 && event.key.charCodeAt(0) <= 126) {
        event.preventDefault();
        record("type", {text: event.key, index: model.cursor, input_source: "physical_keyboard"});
        if (model.selection) {
          const [start, end] = model.selection;
          model.glyphs.splice(start, end - start);
          model.cursor = start;
        }
        model.glyphs.splice(model.cursor, 0, {char: event.key, bold: false, italic: false, font: "mono", size: DEFAULT_SIZE});
        model.cursor += 1;
        model.selection = null;
        model.selectionSource = null;
        updateAll();
      }
    });

    editor.addEventListener("pointerdown", (event) => {
      if (model.phase !== "edit") return;
      const index = characterIndexFromPoint(event.clientX, event.clientY);
      if (index === null) {
        model.cursor = model.glyphs.length;
        model.selection = null;
        model.selectionSource = null;
        renderDocument();
        return;
      }
      event.preventDefault();
      editor.focus();
      if (model.interaction === "simplified") {
        if (model.endpointAnchor === null) {
          model.endpointAnchor = index;
          model.selection = [index, index + 1];
          model.selectionSource = null;
          model.helpers.setReadout(`RANGE START ${index + 1} · CLICK ENDPOINT`, "idle");
          renderDocument();
        } else {
          const anchor = model.endpointAnchor;
          model.endpointAnchor = null;
          finishSelection(anchor, index, "endpoint_clicks");
          model.helpers.setReadout(`RANGE ${Math.min(anchor, index) + 1}–${Math.max(anchor, index) + 1} SELECTED`, "idle");
        }
        return;
      }
      const anchor = index;
      model.dragAnchor = anchor;
      model.dragFocus = anchor;
      editor.setPointerCapture(event.pointerId);
      const move = (moveEvent) => {
        const focus = characterIndexFromPoint(moveEvent.clientX, moveEvent.clientY);
        if (focus === null) return;
        model.dragFocus = focus;
        model.selection = [Math.min(anchor, focus), Math.max(anchor, focus) + 1];
        renderDocument();
      };
      const up = (upEvent) => {
        editor.removeEventListener("pointermove", move);
        editor.removeEventListener("pointerup", up);
        const focus = characterIndexFromPoint(upEvent.clientX, upEvent.clientY);
        finishSelection(anchor, focus === null ? model.dragFocus : focus, "range_drag");
        model.dragAnchor = null;
        model.dragFocus = null;
      };
      editor.addEventListener("pointermove", move);
      editor.addEventListener("pointerup", up);
    });
  }

  function applyFormat(style, value) {
    if (!model.selection || !model.selectionSource || model.phase !== "edit") {
      model.helpers.setReadout("SELECT A VISIBLE RANGE FIRST", "error");
      return;
    }
    const [start, end] = model.selection;
    record("format", {
      style,
      value,
      start,
      end,
      selection_source: model.selectionSource,
      input_source: "toolbar_button",
    });
    for (let index = start; index < end; index += 1) model.glyphs[index][style] = value;
    updateAll();
  }

  function installToolbar() {
    document.querySelectorAll(".siege-tool").forEach((button) => {
      button.addEventListener("pointerdown", (event) => event.preventDefault());
      button.addEventListener("click", () => {
        const style = button.dataset.style;
        let value = button.dataset.value;
        if (style === "bold" || style === "italic") value = value === "true";
        if (style === "size") value = Number(value);
        applyFormat(style, value);
      });
    });
  }

  function normalizedPoint(event) {
    const shell = document.querySelector(".siege-editor-shell");
    const rect = shell.getBoundingClientRect();
    return {
      x_norm: Number(((event.clientX - rect.left) / rect.width).toFixed(5)),
      y_norm: Number(((event.clientY - rect.top) / rect.height).toFixed(5)),
    };
  }

  function activeEmbers(nowMs) {
    if (model.hazardStartedAt === null) return [];
    return model.state.embers.filter((ember) => {
      if (model.quenched.has(ember.id) || model.damaged.has(ember.id)) return false;
      const local = nowMs - model.hazardStartedAt - Number(ember.spawn_offset_ms);
      return local >= 0 && local < Number(ember.ttl_ms);
    });
  }

  function emberPosition(ember, nowMs) {
    const local = nowMs - model.hazardStartedAt - Number(ember.spawn_offset_ms);
    const phase = Math.max(0, Math.min(1, local / Number(ember.ttl_ms)));
    return {
      x: Number(ember.start[0]) + (Number(ember.end[0]) - Number(ember.start[0])) * phase,
      y: Number(ember.start[1]) + (Number(ember.end[1]) - Number(ember.start[1])) * phase,
      phase,
    };
  }

  function quenchEmber(ember, source, point = {}) {
    if (!activeEmbers(taskNow()).some((item) => item.id === ember.id)) return;
    record("quench", {ember_id: ember.id, input_source: source, ...point});
    model.quenched.add(ember.id);
    document.querySelector(`.siege-ember[data-ember-id="${CSS.escape(ember.id)}"]`)?.remove();
    model.helpers.setReadout(`EMBER ${model.quenched.size}/${model.state.embers.length} QUENCHED`, "idle");
    updateAll();
  }

  function ensureEmberElement(ember, nowMs) {
    const layer = document.querySelector(".siege-ember-layer");
    if (!layer) return;
    let button = layer.querySelector(`.siege-ember[data-ember-id="${CSS.escape(ember.id)}"]`);
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.className = "siege-ember";
      button.dataset.emberId = ember.id;
      button.setAttribute("aria-label", "Moving ember");
      button.innerHTML = "<i></i><b></b>";
      button.addEventListener("click", (event) => {
        if (model.interaction !== "full") return;
        quenchEmber(ember, "ember_click", normalizedPoint(event));
      });
      layer.appendChild(button);
    }
    const position = emberPosition(ember, nowMs);
    button.style.left = `${position.x * 100}%`;
    button.style.top = `${position.y * 100}%`;
    button.style.setProperty("--ember-life", String(1 - position.phase));
  }

  function feed(tokenId, source, point) {
    if (model.hazardStartedAt === null || model.usedGrains.has(tokenId) || model.starved) return;
    const required = Number(model.contract.feed_required);
    const expectedToken = model.state.hatchling.grain_tokens[model.feedCount];
    if (model.feedCount >= required || tokenId !== expectedToken) return;
    if (!feedIsReady()) {
      model.helpers.setReadout("THE NEXT GRAIN IS STILL RIPENING", "error");
      return;
    }
    const target = model.state.hatchling;
    const dx = (Number(point.x_norm) - Number(target.x_norm)) / Number(target.radius_x_norm);
    const dy = (Number(point.y_norm) - Number(target.y_norm)) / Number(target.radius_y_norm);
    if ((dx * dx) + (dy * dy) > 1) {
      model.helpers.setReadout("THE GRAIN MISSED THE HATCHLING", "error");
      return;
    }
    record("feed", {token_id: tokenId, input_source: source, ...point});
    model.usedGrains.add(tokenId);
    model.feedCount += 1;
    model.nextFeedReadyAt = model.feedCount < required
      ? model.lastEventTime + Number(model.contract.feed_interval_ms)
      : null;
    model.hungerDeadline = model.lastEventTime + Number(model.contract.hunger_ms);
    document.querySelector(`.siege-grain[data-token-id="${CSS.escape(tokenId)}"]`)?.remove();
    model.selectedGrain = null;
    model.helpers.setReadout(`HATCHLING FED ${model.feedCount}/${Number(model.contract.feed_required)}`, "idle");
    updateAll();
  }

  function renderHatchling() {
    const hatchling = document.querySelector(".siege-hatchling");
    const tray = document.querySelector(".siege-grain-tray");
    const active = model.hazardStartedAt !== null && Number(model.contract.feed_required) > 0;
    if (hatchling) {
      hatchling.hidden = !active;
      hatchling.style.left = `${Number(model.state.hatchling.x_norm) * 100}%`;
      hatchling.style.top = `${Number(model.state.hatchling.y_norm) * 100}%`;
      hatchling.style.setProperty("--hatchling-width", `${Number(model.state.hatchling.radius_x_norm) * 200}%`);
      hatchling.style.setProperty("--hatchling-height", `${Number(model.state.hatchling.radius_y_norm) * 200}%`);
      hatchling.dataset.fed = String(model.feedCount >= Number(model.contract.feed_required));
    }
    if (!tray) return;
    tray.hidden = !active;
    if (!active) return;
    const nowMs = taskNow();
    const required = Number(model.contract.feed_required);
    tray.querySelectorAll(".siege-grain").forEach((grain) => {
      const tokenIndex = model.state.hatchling.grain_tokens.indexOf(grain.dataset.tokenId);
      const current = model.feedCount < required && tokenIndex === model.feedCount;
      grain.classList.toggle("is-selected", grain.dataset.tokenId === model.selectedGrain);
      grain.hidden = model.usedGrains.has(grain.dataset.tokenId) || !current;
      grain.disabled = !current || !feedIsReady(nowMs);
      grain.setAttribute("aria-label", grain.disabled ? "Grain token ripening" : "Grain token ready");
    });
    if (model.selectedGrain && model.selectedGrain !== model.state.hatchling.grain_tokens[model.feedCount]) {
      model.selectedGrain = null;
    }
  }

  function installFeedInteractions() {
    const hatchling = document.querySelector(".siege-hatchling");
    hatchling.addEventListener("click", (event) => {
      if (model.interaction !== "simplified" || !model.selectedGrain) return;
      feed(model.selectedGrain, "token_click_hatchling", normalizedPoint(event));
    });
    document.querySelectorAll(".siege-grain").forEach((grain) => {
      const tokenId = grain.dataset.tokenId;
      grain.addEventListener("click", () => {
        if (model.interaction !== "simplified" || model.usedGrains.has(tokenId) || !feedIsReady()) return;
        model.selectedGrain = tokenId;
        renderHatchling();
      });
      grain.addEventListener("pointerdown", (event) => {
        if (model.interaction !== "full" || model.usedGrains.has(tokenId) || !feedIsReady()) return;
        event.preventDefault();
        grain.setPointerCapture(event.pointerId);
        const startX = event.clientX;
        const startY = event.clientY;
        const move = (moveEvent) => {
          grain.style.transform = `translate(${moveEvent.clientX - startX}px, ${moveEvent.clientY - startY}px)`;
        };
        const up = (upEvent) => {
          grain.removeEventListener("pointermove", move);
          grain.removeEventListener("pointerup", up);
          grain.style.removeProperty("transform");
          feed(tokenId, "token_drag", normalizedPoint(upEvent));
        };
        grain.addEventListener("pointermove", move);
        grain.addEventListener("pointerup", up);
      });
    });
  }

  function processAutonomous(nowMs) {
    if (model.hazardStartedAt === null || model.terminal || model.disposed) return;
    for (const ember of model.state.embers) {
      const expires = model.hazardStartedAt + Number(ember.spawn_offset_ms) + Number(ember.ttl_ms);
      if (nowMs >= expires && !model.quenched.has(ember.id) && !model.damaged.has(ember.id)) {
        model.damaged.add(ember.id);
        if (model.glyphs.length) {
          const index = Number(ember.damage_slot) % model.glyphs.length;
          model.glyphs.splice(index, 1);
          model.cursor = Math.min(model.cursor, model.glyphs.length);
        }
        model.helpers.setReadout("BREACH · AN EMBER ATE THE LEDGER", "error");
        updateAll();
        void submitAttempt();
        return;
      }
    }
    if (model.hungerDeadline !== null && nowMs >= model.hungerDeadline) {
      model.starved = true;
      model.helpers.setReadout("HATCHLING STARVED", "error");
      updateAll();
      void submitAttempt();
    }
  }

  function tick() {
    if (!model || model.disposed) return;
    const nowMs = taskNow();
    processAutonomous(nowMs);
    const active = activeEmbers(nowMs);
    active.forEach((ember) => ensureEmberElement(ember, nowMs));
    document.querySelectorAll(".siege-ember").forEach((element) => {
      if (!active.some((ember) => ember.id === element.dataset.emberId)) element.remove();
    });
    const quench = document.querySelector(".siege-quench-proxy");
    if (quench) {
      quench.hidden = model.interaction !== "simplified" || active.length === 0;
      quench.dataset.emberId = active[0]?.id || "";
    }
    const hunger = document.querySelector(".siege-hunger-fill");
    if (hunger && model.hungerDeadline !== null) {
      const ratio = Math.max(0, Math.min(1, (model.hungerDeadline - nowMs) / Number(model.contract.hunger_ms)));
      hunger.style.setProperty("--hunger", String(ratio));
    }
    const feedPhase = document.querySelector(".siege-feed-phase");
    if (feedPhase && !model.starved) feedPhase.textContent = feedPhaseLabel(nowMs);
    renderHatchling();
    requestAnimationFrame(tick);
  }

  function beginConfirmation() {
    if (!ruleResults().every(Boolean) || model.phase !== "edit") return;
    record("begin_confirmation", {input_source: "seal_button"});
    model.phase = "confirm";
    model.confirmationExpected = textValue();
    document.querySelector(".siege-captcha")?.classList.add("is-sealed");
    document.querySelector(".siege-confirm-panel")?.removeAttribute("hidden");
    document.querySelector(".siege-confirm-input")?.focus();
    model.helpers.setReadout("LEDGER SEALED · RETYPE FROM MEMORY", "idle");
  }

  function installConfirmation() {
    const input = document.querySelector(".siege-confirm-input");
    input.addEventListener("keydown", (event) => {
      if (model.phase !== "confirm" || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "Backspace") {
        event.preventDefault();
        record("confirm_backspace", {input_source: "physical_keyboard"});
        model.confirmation = model.confirmation.slice(0, -1);
        input.value = model.confirmation;
        return;
      }
      if (event.key.length === 1 && event.key.charCodeAt(0) >= 32 && event.key.charCodeAt(0) <= 126) {
        event.preventDefault();
        record("confirm_type", {text: event.key, input_source: "physical_keyboard"});
        model.confirmation += event.key;
        input.value = model.confirmation;
      }
    });
  }

  function showFailure(outcome = {}) {
    model.terminal = true;
    const root = document.querySelector(".siege-captcha");
    if (!root) return;
    root.querySelector(".siege-verdict")?.remove();
    const verdict = document.createElement("section");
    verdict.className = "siege-verdict is-failure";
    verdict.setAttribute("role", "alert");
    const retry = outcome.state
      ? '<button class="siege-retry" type="button">OPEN FRESH DOSSIER →</button>'
      : '<button class="siege-retry" type="button" disabled>FRESH DOSSIER UNAVAILABLE</button>';
    verdict.innerHTML = `<span>CLERK'S TERMINAL FINDING</span><strong>FAIL</strong><p>${esc(outcome.feedback || "The ledger could not be certified.")}</p>${retry}`;
    root.appendChild(verdict);
    if (outcome.state) {
      verdict.querySelector(".siege-retry").addEventListener("click", () => {
        model.disposed = true;
        model.helpers.render(outcome.state);
      });
    }
    model.helpers.setReadout("FAIL", "error");
  }

  function showPass(outcome = {}) {
    model.terminal = true;
    const root = document.querySelector(".siege-captcha");
    root.classList.add("is-passed");
    const verdict = document.createElement("section");
    verdict.className = "siege-verdict is-pass";
    verdict.innerHTML = `<span>CLERK'S TERMINAL FINDING</span><strong>PASS</strong><p>${esc(outcome.feedback || "Every live constraint survived independent replay.")}</p>`;
    root.appendChild(verdict);
    model.helpers.setReadout("PASS", "passed");
  }

  async function submitAttempt() {
    if (model.submitting || model.terminal) return;
    model.submitting = true;
    record("submit", {input_source: "certify_button"});
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({
          mechanic_id: model.state.mechanic_id,
          task_id: model.state.task_id,
          challenge_id: model.state.challenge_id,
          interaction_mode: model.interaction,
          events: model.events,
        }),
      });
      const outcome = await response.json();
      if (outcome.passed === true) showPass(outcome);
      else showFailure(outcome);
    } catch (_error) {
      model.submitting = false;
      showFailure({feedback: "The sealed ledger could not reach the grading desk."});
    }
  }

  async function render(state, helpers) {
    if (model) model.disposed = true;
    document.body.dataset.mechanic = "passphrase-under-siege-v1";
    const interaction = state.control_condition?.interaction || "full";
    const grains = state.hatchling.grain_tokens.map((tokenId) => `<button class="siege-grain" type="button" data-token-id="${esc(tokenId)}" aria-label="Grain token"><i></i></button>`).join("");
    model = {
      state,
      helpers,
      contract: state.contract,
      interaction,
      glyphs: [],
      cursor: 0,
      selection: null,
      selectionSource: null,
      endpointAnchor: null,
      dragAnchor: null,
      dragFocus: null,
      events: [],
      lastEventTime: 0,
      highestPrefix: 0,
      unlocked: 1,
      hazardStartedAt: null,
      hungerDeadline: null,
      nextFeedReadyAt: null,
      feedCount: 0,
      usedGrains: new Set(),
      selectedGrain: null,
      quenched: new Set(),
      damaged: new Set(),
      starved: false,
      phase: "edit",
      confirmation: "",
      confirmationExpected: "",
      submitting: false,
      terminal: false,
      disposed: false,
      startedAt: performance.now(),
    };
    helpers.app.innerHTML = `<section class="siege-captcha" data-interaction="${esc(interaction)}" data-challenge-id="${esc(state.challenge_id)}" style="--siege-ink:${esc(state.theme.ink)};--siege-paper:${esc(state.theme.paper)};--siege-seal:${esc(state.theme.seal)};--siege-night:${esc(state.theme.night)}">
      <header class="siege-head">
        <div><span>NIGHT CLERK / ACTIVE FILE ${esc(state.challenge_id)}</span><h1>Passphrase Under Siege</h1></div>
        <p>Satisfy every card. Green can turn red. Seal only when the whole ledger holds.</p>
        <div class="siege-rule-count">0 / ${state.rules.length} GREEN</div>
      </header>
      <main class="siege-main">
        <section class="siege-desk">
          <div class="siege-toolbar" aria-label="Rich text formatting toolbar">
            <span>SELECTED INK</span>
            <button class="siege-tool tool-bold" type="button" data-style="bold" data-value="true" aria-label="Apply bold">B</button>
            <button class="siege-tool tool-unbold" type="button" data-style="bold" data-value="false" aria-label="Remove bold">B̸</button>
            <button class="siege-tool tool-italic" type="button" data-style="italic" data-value="true" aria-label="Apply italic">I</button>
            <button class="siege-tool tool-unitalic" type="button" data-style="italic" data-value="false" aria-label="Remove italic">I̸</button>
            <button class="siege-tool tool-serif" type="button" data-style="font" data-value="serif">Ledger Serif</button>
            <button class="siege-tool tool-mono" type="button" data-style="font" data-value="mono">Clerk Mono</button>
            <button class="siege-tool" type="button" data-style="size" data-value="24">24</button>
            <button class="siege-tool" type="button" data-style="size" data-value="28">28</button>
            <button class="siege-tool" type="button" data-style="size" data-value="32">32</button>
            <button class="siege-tool" type="button" data-style="size" data-value="18">18</button>
          </div>
          <div class="siege-editor-shell">
            <div class="siege-paper-lines"></div>
            <div class="siege-editor" role="textbox" aria-multiline="false" tabindex="0"></div>
            <div class="siege-ember-layer"></div>
            <button class="siege-hatchling" type="button" hidden aria-label="Hatchling"><i></i><b></b><span class="siege-hunger"><em class="siege-hunger-fill"></em></span></button>
            <div class="siege-grain-tray" hidden>${grains}</div>
            <button class="siege-quench-proxy" type="button" hidden>QUENCH ACTIVE EMBER</button>
            <div class="siege-selection-note">${interaction === "full" ? "DRAG ACROSS CHARACTERS TO SELECT" : "CLICK A START CHARACTER, THEN AN END CHARACTER"}</div>
          </div>
          <footer class="siege-desk-foot">
            <span class="siege-char-count">0 CHARS</span><span class="siege-digit-count">Σ DIGITS 0 / ${Number(state.contract.digit_sum_target)}</span>
            <button class="siege-attempt" type="button">CERTIFY CURRENT ATTEMPT</button>
            <button class="siege-seal" type="button" disabled>SEAL GREEN LEDGER →</button>
          </footer>
        </section>
        <aside class="siege-rule-column"><header><span>LIVE CONSTRAINT STACK</span><b>EVERY EDIT RECHECKS EVERY CARD</b></header><div class="siege-rules"></div></aside>
      </main>
      <section class="siege-confirm-panel" hidden>
        <div class="siege-wax"><i></i><b>SEALED</b></div>
        <div><span>THE ORIGINAL IS NOW UNDER WAX</span><h2>Retype the finished passphrase exactly.</h2><input class="siege-confirm-input" type="text" autocomplete="off" spellcheck="false"><button class="siege-confirm" type="button">CONFIRM SEALED COPY</button></div>
      </section>
      <footer class="siege-foot"><div class="readout" data-status="idle"></div><span>FILE ${esc(state.challenge_id)} · ${esc(interaction.toUpperCase())} INPUT</span></footer>
    </section>`;
    installEditorInteractions();
    installToolbar();
    installFeedInteractions();
    installConfirmation();
    document.querySelector(".siege-quench-proxy").addEventListener("click", () => {
      const ember = activeEmbers(taskNow())[0];
      if (ember) quenchEmber(ember, "quench_button");
    });
    document.querySelector(".siege-attempt").addEventListener("click", submitAttempt);
    document.querySelector(".siege-seal").addEventListener("click", beginConfirmation);
    document.querySelector(".siege-confirm").addEventListener("click", submitAttempt);
    updateAll();
    requestAnimationFrame(tick);
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.passphrase_under_siege = {render, rootSelector: ".siege-captcha"};
})();
