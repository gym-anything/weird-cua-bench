(() => {
  "use strict";

  const SUBJECTS = new Set(["STATUE", "LANTERN", "GATE", "CISTERN"]);
  const PROPERTIES = new Set(["YOU", "EXIT", "DEADLY", "STOP"]);
  const DIRECTIONS = {
    UP: [0, -1], RIGHT: [1, 0], DOWN: [0, 1], LEFT: [-1, 0],
  };
  const KEYS = {
    arrowup: "UP", w: "UP", arrowright: "RIGHT", d: "RIGHT",
    arrowdown: "DOWN", s: "DOWN", arrowleft: "LEFT", a: "LEFT",
  };
  let model = null;
  let activeCleanup = null;

  function pointKey(x, y) { return `${Number(x)},${Number(y)}`; }
  function clonePositions(items) { return items.map((item) => ({id: String(item.id), x: Number(item.x), y: Number(item.y)})); }
  function positionMap(items) { return new Map(items.map((item, index) => [pointKey(item.x, item.y), index])); }

  function activeRules() {
    const at = new Map(model.words.map((word, index) => [pointKey(word.x, word.y), model.yard.words[index].text]));
    const rules = new Set();
    model.words.forEach((word, index) => {
      if (model.yard.words[index].text !== "IS") return;
      const x = Number(word.x);
      const y = Number(word.y);
      [
        [at.get(pointKey(x - 1, y)), at.get(pointKey(x + 1, y))],
        [at.get(pointKey(x, y - 1)), at.get(pointKey(x, y + 1))],
      ].forEach(([subject, property]) => {
        if (SUBJECTS.has(subject) && PROPERTIES.has(property)) rules.add(`${subject} IS ${property}`);
      });
    });
    return [...rules].sort();
  }

  function kindsWith(rules, property) {
    const suffix = ` IS ${property}`;
    return new Set(rules.filter((rule) => rule.endsWith(suffix)).map((rule) => rule.slice(0, -suffix.length)));
  }

  function snapshot() {
    const rules = activeRules();
    return {
      entities: clonePositions(model.entities),
      words: clonePositions(model.words),
      active_rules: rules,
      controlled_kinds: [...kindsWith(rules, "YOU")].sort(),
      broken_opening_rules: [...model.broken].sort(),
    };
  }

  function predicateState(rules) {
    const controlled = kindsWith(rules, "YOU");
    const exits = kindsWith(rules, "EXIT");
    const deadly = kindsWith(rules, "DEADLY");
    const controlledCells = new Set(
      model.entities.filter((entity, index) => controlled.has(model.yard.entities[index].kind)).map((entity) => pointKey(entity.x, entity.y)),
    );
    const won = controlledCells.size > 0 && model.entities.some(
      (entity, index) => exits.has(model.yard.entities[index].kind) && controlledCells.has(pointKey(entity.x, entity.y)),
    );
    const dead = model.entities.some(
      (entity, index) => deadly.has(model.yard.entities[index].kind) && controlledCells.has(pointKey(entity.x, entity.y)),
    );
    return {won, dead};
  }

  function record(event) {
    model.actions.push({seq: model.actions.length + 1, ...event});
  }

  function clearTransientVerdict() {
    const root = document.querySelector(".statute-yard");
    if (!root?.classList.contains("is-failed")) return;
    root.classList.remove("is-failed");
    const panel = document.querySelector(".statute-verdict");
    if (panel) panel.replaceChildren();
  }

  function move(direction, inputSource) {
    if (!model || model.terminal || model.submitting || !(direction in DIRECTIONS)) return;
    clearTransientVerdict();
    const [dx, dy] = DIRECTIONS[direction];
    const beforeRules = activeRules();
    const controlled = kindsWith(beforeRules, "YOU");
    const stopped = kindsWith(beforeRules, "STOP");
    const controlledIndices = model.yard.entities
      .map((entity, index) => controlled.has(entity.kind) ? index : -1)
      .filter((index) => index >= 0);
    let pushed = false;
    let moved = false;

    controlledIndices.forEach((entityIndex) => {
      const entity = model.entities[entityIndex];
      const target = {x: entity.x + dx, y: entity.y + dy};
      if (model.walls.has(pointKey(target.x, target.y))) return;
      let wordByCell = positionMap(model.words);
      const firstWord = wordByCell.get(pointKey(target.x, target.y));
      if (firstWord !== undefined) {
        const chain = [];
        let cursor = {x: target.x, y: target.y};
        while (wordByCell.has(pointKey(cursor.x, cursor.y))) {
          chain.push(wordByCell.get(pointKey(cursor.x, cursor.y)));
          cursor = {x: cursor.x + dx, y: cursor.y + dy};
        }
        const objectStops = model.entities.some((other, index) =>
          other.x === cursor.x && other.y === cursor.y && stopped.has(model.yard.entities[index].kind));
        if (model.walls.has(pointKey(cursor.x, cursor.y)) || objectStops) return;
        [...chain].reverse().forEach((wordIndex) => {
          model.words[wordIndex].x += dx;
          model.words[wordIndex].y += dy;
        });
        pushed = true;
        wordByCell = positionMap(model.words);
      }
      const targetStopped = model.entities.some((other, index) =>
        other.x === target.x && other.y === target.y && stopped.has(model.yard.entities[index].kind));
      if (targetStopped) return;
      entity.x = target.x;
      entity.y = target.y;
      moved = true;
    });

    const afterRules = activeRules();
    model.openingRules.forEach((rule) => { if (!afterRules.includes(rule)) model.broken.add(rule); });
    const predicates = predicateState(afterRules);
    model.won = !predicates.dead && predicates.won;
    model.dead = predicates.dead;
    model.terminal = model.won || model.dead;
    let outcome = "blocked";
    if (model.dead) outcome = "deadly_contact";
    else if (model.won) outcome = "exit_reached";
    else if (pushed) outcome = "law_shift";
    else if (moved) outcome = "move";
    else if (controlledIndices.length === 0) outcome = "no_subject_bound";
    record({type: "move", direction, input_source: inputSource, outcome});
    renderState(outcome);
  }

  function resetYard() {
    if (!model || model.terminal || model.submitting) return;
    clearTransientVerdict();
    model.entities = clonePositions(model.yard.entities);
    model.words = clonePositions(model.yard.words);
    model.broken = new Set();
    model.resetCount += 1;
    model.won = false;
    model.dead = false;
    const inputSource = model.interaction === "full" ? "keyboard" : "direction_buttons";
    record({type: "reset", input_source: inputSource, outcome: "reset"});
    renderState("reset");
  }

  function statusCopy(outcome, rules) {
    if (model.dead) return ["DEADLY CONTACT", "error"];
    if (model.won) return ["EXIT PREDICATE TRUE · SEAL THE VERDICT", "passed"];
    if (outcome === "law_shift") return [`LAW SHIFT · ${rules.length} ACTIVE`, "idle"];
    if (outcome === "blocked") return ["STONEWORK BLOCKED", "error"];
    if (outcome === "no_subject_bound") return ["NO OBJECT IS YOU", "error"];
    if (outcome === "reset") return ["YARD RESTORED · TRANSCRIPT RETAINED", "idle"];
    return ["MOVEMENT ENTERED", "idle"];
  }

  function tokenMarkup(kind, count, index) {
    const labels = {STATUE: "S", LANTERN: "L", GATE: "G", CISTERN: "C"};
    const extras = count > 1 ? `<i>${count}</i>` : "";
    const shiftX = index * 5;
    const shiftY = index * -4;
    return `<span class="yard-object object-${kind.toLowerCase()}" style="--object-shift-x:${shiftX}px;--object-shift-y:${shiftY}px"><b>${labels[kind]}</b>${extras}</span>`;
  }

  function renderBoard() {
    const rules = activeRules();
    const controlled = kindsWith(rules, "YOU");
    const exits = kindsWith(rules, "EXIT");
    const deadly = kindsWith(rules, "DEADLY");
    const wordAt = new Map(model.words.map((word, index) => [pointKey(word.x, word.y), model.yard.words[index]]));
    const cells = [];
    for (let y = 0; y < Number(model.yard.height); y += 1) {
      for (let x = 0; x < Number(model.yard.width); x += 1) {
        const key = pointKey(x, y);
        const wall = model.walls.has(key);
        const crack = model.cracks.has(key);
        const word = wordAt.get(key);
        const objects = model.entities
          .map((entity, index) => ({entity, kind: model.yard.entities[index].kind}))
          .filter((entry) => entry.entity.x === x && entry.entity.y === y);
        const grouped = new Map();
        objects.forEach((entry) => grouped.set(entry.kind, (grouped.get(entry.kind) || 0) + 1));
        const objectMarkup = [...grouped].map(([kind, count], index) => tokenMarkup(kind, count, index)).join("");
        const flags = objects.map((entry) => entry.kind);
        cells.push(`<div class="yard-cell${wall ? " is-wall" : ""}${crack ? " is-cracked" : ""}${word ? " has-word" : ""}${flags.some((kind) => controlled.has(kind)) ? " has-you" : ""}${flags.some((kind) => exits.has(kind)) ? " has-exit" : ""}${flags.some((kind) => deadly.has(kind)) ? " has-deadly" : ""}" data-cell="${key}">
          ${word ? `<span class="law-stone word-${word.text.toLowerCase()}"><i></i><b>${model.helpers.text(word.text)}</b></span>` : ""}
          ${objectMarkup}
        </div>`);
      }
    }
    const board = document.querySelector(".statute-board");
    if (board) board.innerHTML = cells.join("");
    document.querySelectorAll(".rule-ledger-list").forEach((ledger) => {
      ledger.innerHTML = rules.map((rule) => {
        const brokenOpening = model.openingRules.has(rule) ? " opening" : " enacted";
        return `<li class="${brokenOpening.trim()}"><i></i><span>${model.helpers.text(rule)}</span><b>ACTIVE</b></li>`;
      }).join("") || "<li class=\"empty\">NO LAW RESOLVES</li>";
    });
    const broken = document.querySelector(".broken-law-count b");
    if (broken) broken.textContent = String(model.broken.size);
    const moves = document.querySelector(".yard-move-count b");
    if (moves) moves.textContent = String(model.actions.filter((action) => action.type === "move").length).padStart(2, "0");
    const identity = document.querySelector(".current-you b");
    if (identity) identity.textContent = [...controlled].sort().join(" + ") || "NONE";
    document.querySelectorAll(".yard-direction, .yard-reset, .yard-seal").forEach((button) => {
      button.disabled = model.submitting;
    });
    const root = document.querySelector(".statute-yard");
    root?.classList.toggle("is-won", model.won);
    root?.classList.toggle("is-dead", model.dead);
  }

  function renderState(outcome = "initial") {
    renderBoard();
    const rules = activeRules();
    const [message, status] = statusCopy(outcome, rules);
    model.helpers.setReadout(message, status);
  }

  function verdict(kind, title, detail) {
    const root = document.querySelector(".statute-yard");
    const panel = document.querySelector(".statute-verdict");
    if (!root || !panel) return;
    root.classList.toggle("is-passed", kind === "pass");
    root.classList.toggle("is-failed", kind === "fail");
    panel.innerHTML = `<b>${title}</b><span>${detail}</span>`;
  }

  async function sealVerdict() {
    if (!model || model.submitting) return;
    model.submitting = true;
    renderBoard();
    const payload = {
      mechanic_id: model.state.mechanic_id,
      task_id: model.state.task_id,
      challenge_id: model.state.challenge_id,
      completed: model.won === true,
      actions: model.actions,
      reset_count: model.resetCount,
      final_state: snapshot(),
    };
    try {
      const response = await fetch("/result", {
        method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(payload),
      });
      const outcome = await response.json();
      if (outcome.passed === true) {
        verdict("pass", "RATIFIED", "PASS · EXIT LAW SATISFIED");
        model.helpers.setReadout("PASS · STATUTE RATIFIED", "passed");
      } else if (outcome.state) {
        const helpers = model.helpers;
        await render(outcome.state, helpers);
        verdict("fail", "REPEALED", "FAIL · FRESH YARD ISSUED");
        model.helpers.setReadout("FAIL · FRESH YARD ISSUED", "error");
      } else {
        model.submitting = false;
        verdict("fail", "REJECTED", "FAIL · VERDICT DID NOT VERIFY");
        model.helpers.setReadout("FAIL · VERDICT DID NOT VERIFY", "error");
      }
    } catch (_error) {
      model.submitting = false;
      model.helpers.setReadout("CLERK LINK LOST", "error");
      renderBoard();
    }
  }

  function installDeveloperReveal() {
    const form = document.getElementById("cheat-form");
    const input = document.getElementById("cheat-password");
    const output = document.getElementById("cheat-output");
    if (!form || !input || !output) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const response = await fetch("/cheat", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({password: input.value})});
      if (!response.ok) { output.textContent = response.status === 404 ? "Disabled." : "Denied."; return; }
      const data = await response.json();
      output.textContent = `Route: ${(data.route || []).join(" ")} · minimum ${(data.minimum_solution_steps || 0)}`;
    });
  }

  async function render(state, helpers) {
    if (activeCleanup) activeCleanup();
    document.body.dataset.mechanic = "statute-yard";
    document.body.dataset.cheatMode = helpers.isCheatMode() ? "true" : "false";
    const yard = state.yard;
    const interaction = state.control_condition?.interaction || "full";
    model = {
      state, helpers, yard, interaction,
      entities: clonePositions(yard.entities), words: clonePositions(yard.words),
      walls: new Set((yard.walls || []).map((point) => pointKey(point[0], point[1]))),
      cracks: new Set((yard.cracks || []).map((point) => pointKey(point[0], point[1]))),
      openingRules: new Set(state.opening_rules || []), broken: new Set(),
      actions: [], resetCount: 0, won: false, dead: false, terminal: false, submitting: false,
    };
    helpers.app.innerHTML = `
      <section class="statute-yard palette-${helpers.text(yard.palette || "verdigris")}" data-interaction="${helpers.text(interaction)}" tabindex="0">
        <div class="statute-verdict" aria-live="assertive"></div>
        <header class="statute-head">
          <div><span>OFFICE OF MUTABLE ORDINANCES · YARD ${helpers.text(state.challenge_id)}</span><h1>${helpers.text(state.prompt)}</h1></div>
          <div class="yard-seal-mark"><i>SY</i><b>STATUTE<br>YARD</b></div>
        </header>
        <main class="statute-workbench">
          <section class="yard-map-panel">
            <div class="yard-map-label"><span>REGISTERED GROUNDS</span><b>${Number(yard.width)} × ${Number(yard.height)} · ${helpers.text(String(yard.orientation || "landscape").toUpperCase())}</b></div>
            <div class="statute-board" style="--yard-columns:${Number(yard.width)};--yard-rows:${Number(yard.height)};--yard-object-size:${Number(yard.height) > 10 ? 26 : 42}px"></div>
            <div class="yard-map-footer">
              ${interaction === "simplified" ? `<div class="yard-directions" aria-label="Direction controls">
                <button class="yard-direction" type="button" data-direction="UP" aria-label="Move up">↑</button>
                <button class="yard-direction" type="button" data-direction="LEFT" aria-label="Move left">←</button>
                <button class="yard-direction" type="button" data-direction="DOWN" aria-label="Move down">↓</button>
                <button class="yard-direction" type="button" data-direction="RIGHT" aria-label="Move right">→</button>
                <button class="yard-reset" type="button">RESET</button>
              </div>` : `<span class="key-legend">ARROWS / WASD TO MOVE · R TO RESET</span>`}
              <b>WORD-STONES PUSH · LAWS RECOMPUTE AFTER EVERY MOVE</b>
            </div>
          </section>
          <aside class="statute-ledger">
            <div class="ledger-title"><span>ACTIVE LAW LEDGER</span><i>LIVE</i></div>
            <ol class="rule-ledger-list"></ol>
            <div class="law-syntax"><span>VALID FORM</span><b>NOUN</b><i>IS</i><b>PROPERTY</b><small>horizontal or vertical</small></div>
            <div class="yard-tallies">
              <span class="current-you">YOU <b>—</b></span>
              <span class="broken-law-count">OPENING LAWS BROKEN <b>0</b></span>
              <span class="yard-move-count">MOVES <b>00</b></span>
            </div>
          </aside>
        </main>
        <footer class="statute-foot"><div class="readout" data-status="idle">YARD ENTERED · OPENING LAWS REGISTERED</div><button class="yard-seal" type="button">${helpers.text(state.submit_label || "SEAL VERDICT")}</button></footer>
        ${helpers.cheatPanelTemplate()}
      </section>`;

    const keydown = (event) => {
      if (!model || model.interaction !== "full" || event.repeat) return;
      const key = String(event.key || "").toLowerCase();
      if (key === "r") { event.preventDefault(); resetYard(); return; }
      const direction = KEYS[key];
      if (!direction) return;
      event.preventDefault();
      move(direction, "keyboard");
    };
    window.addEventListener("keydown", keydown);
    document.querySelectorAll(".yard-direction").forEach((button) => button.addEventListener("click", () => move(button.dataset.direction, "direction_buttons")));
    document.querySelector(".yard-reset")?.addEventListener("click", resetYard);
    document.querySelector(".yard-seal")?.addEventListener("click", sealVerdict);
    activeCleanup = () => window.removeEventListener("keydown", keydown);
    installDeveloperReveal();
    renderState("initial");
    document.querySelector(".statute-yard")?.focus();
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.statute_yard = {rootSelector: ".statute-yard", render};
})();
