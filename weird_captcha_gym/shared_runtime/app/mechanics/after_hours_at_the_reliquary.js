(() => {
  "use strict";

  const MECHANIC_ID = "after_hours_at_the_reliquary";
  const COLORS = {
    vermilion: "#d94a36", amber: "#e7a62f", verdigris: "#3e9a82",
    cobalt: "#3568b2", ivory: "#e6ddc5", violet: "#7d5799",
  };
  let model = null;
  let cleanup = null;

  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const interaction = () => model.state.control_condition?.interaction || "full";
  const view = () => model.state.views[model.viewId];
  const target = (id) => model.state.targets.find((item) => item.id === id);
  const hasFlag = (flag) => model.flags.has(flag);
  const activeLock = (id) => model.state.active_locks.includes(id);
  const lockReleased = (id) => model.released.has(id);
  const allReleased = () => model.state.active_locks.every((id) => model.released.has(id));

  function available(item) {
    return item && item.view_id === model.viewId
      && item.requires_flags.every((flag) => model.flags.has(flag))
      && item.forbids_flags.every((flag) => !model.flags.has(flag));
  }

  function pointIn(event, node) {
    const rect = node.getBoundingClientRect();
    return [
      Number(((event.clientX - rect.left) / rect.width).toFixed(6)),
      Number(((event.clientY - rect.top) / rect.height).toFixed(6)),
    ];
  }

  function record(event) {
    clearFreshFailure();
    model.events.push({sequence: model.events.length + 1, ...event});
  }

  function clearFreshFailure() {
    if (!model?.freshFailure) return;
    model.freshFailure = false;
    document.querySelector(".rel-fresh-failure")?.remove();
    model.helpers.setReadout("NIGHT REGISTER OPEN", "idle");
  }

  function itemGlyph(itemId) {
    const glyph = model.state.items[itemId]?.glyph || "pin";
    return `<span class="rel-item-glyph glyph-${esc(glyph)}"><i></i></span>`;
  }

  function itemCard(itemId, index) {
    const item = model.state.items[itemId];
    const selected = model.selectedItem === itemId;
    const layout = model.state.item_card_layout;
    const left = Number(layout.left) + index * (Number(layout.width) + Number(layout.gap));
    const style = `left:${left * 100}%;top:${Number(layout.top) * 100}%;width:${Number(layout.width) * 100}%;height:${Number(layout.height) * 100}%`;
    return `<button class="rel-item ${selected ? "is-selected" : ""}" data-item-id="${esc(itemId)}" aria-pressed="${selected}" style="${style}">
      ${itemGlyph(itemId)}<span><b>${esc(item.name)}</b><small>OBJECT ${String(model.inventory.indexOf(itemId) + 1).padStart(2, "0")}</small></span>
    </button>`;
  }

  function targetStyle(id) {
    const item = target(id);
    if (!item) return "";
    const [x, y, width, height] = item.rect;
    return `left:${x * 100}%;top:${y * 100}%;width:${width * 100}%;height:${height * 100}%`;
  }

  function hotspot(id, classes, inner) {
    const item = target(id);
    if (!available(item)) return "";
    // Scene discoveries are pointer affordances, not a hidden tab-order index.
    // Keeping them out of sequential focus prevents keyboard focus rings from
    // revealing the baseline's deliberately unmarked hotspots.
    return `<button class="rel-hotspot ${classes}" data-hotspot-id="${esc(id)}" style="${targetStyle(id)}" aria-label="Room object" tabindex="-1">${inner}</button>`;
  }

  function directionCard() {
    if (!hasFlag("order_revealed")) return "";
    const digitArrow = model.state.read_directions.digit === "forward" ? "→" : "←";
    const colorArrow = model.state.read_directions.color === "forward" ? "→" : "←";
    return `<div class="rel-order-card"><span><b>1·2·3</b><i>${digitArrow}</i></span><span><b class="rel-mini-colors"><i></i><i></i><i></i></b><i>${colorArrow}</i></span></div>`;
  }

  function doorScene() {
    const lockPlate = (kind, label) => !activeLock(kind) ? "" : `<button class="rel-lock-plate lock-${kind} ${lockReleased(kind) ? "is-open" : ""}" data-lock-panel="${kind}">
      <small>${label}</small><b>${lockReleased(kind) ? "OPEN" : "WARD"}</b><span>${model.wrong[kind] || 0} / ${model.state.parameters.max_wrong_entries}</span>
    </button>`;
    return `<div class="rel-door-hall"><div class="rel-column left"></div><div class="rel-column right"></div>
      <div class="rel-vault-door ${allReleased() ? "is-unwarded" : ""} ${hasFlag("door_open") ? "is-open" : ""}">
        <div class="rel-door-ribs"></div>
      </div>${hotspot("door_handle", "door-handle", "<span></span>")}${hotspot("keyhole", "keyhole", '<span><em class="rel-key-slot"><i></i></em></span>')}<div class="rel-lock-bank">${lockPlate("digit", "I · NUMBER")}${lockPlate("color", "II · GLASS")}${lockPlate("key", "III · KEY")}</div>
    </div>`;
  }

  function deskScene() {
    const flipped = hasFlag("label_flipped");
    const digitClue = hasFlag("digit_revealed")
      ? `<strong class="rel-digit-clue">${esc(model.state.raw_digit_clue)}</strong>`
      : '<span class="rel-faint-script">╱  ·  ╲  ·  ╱</span>';
    return `<div class="rel-desk-room"><div class="rel-window"><i></i><i></i><i></i></div><div class="rel-long-desk"><span></span></div>
      ${!flipped ? hotspot("label_frame", "label-frame", '<span class="rel-label-face"><i>R–17</i><b>UNTITLED RELIC</b></span>') : `
        <div class="rel-label-back" style="${targetStyle("label_code")}">${digitClue}</div>
        ${hotspot("empty_frame", "empty-frame", '<span class="rel-empty-ring"></span>')}
        ${hotspot("label_code", "label-code", '<span></span>')}`}
      <div class="rel-ledger-stack"><i></i><i></i><i></i></div><div class="rel-desk-lamp"><i></i></div>
    </div>`;
  }

  function cabinetScene() {
    const drawerOpen = hasFlag("lens_drawer_open");
    const floorOpen = hasFlag("floor_open");
    return `<div class="rel-cabinet-room"><div class="rel-tall-cabinet"><div class="rel-cabinet-glass"><i></i><i></i><i></i></div>
      ${drawerOpen ? `<div class="rel-open-drawer" style="${targetStyle("lens_drawer")}"></div>${hotspot("lens", "loose-lens", '<span></span>')}` : hotspot("lens_drawer", "lens-drawer", '<span><i></i></span>')}
      ${hotspot("ready_hook", "ready-hook", '<span></span>')}</div>
      ${floorOpen ? `<div class="rel-floor-void" style="${targetStyle("floor_tile")}"></div>${hotspot("handle", "ivory-handle", '<span></span>')}` : hotspot("floor_tile", "floor-tile", '<span></span>')}
      <div class="rel-crates"><i></i><i></i><i></i></div><div class="rel-tag-rain"><i>44</i><i>08</i><i>31</i></div>
    </div>`;
  }

  function galleryScene() {
    const revealed = hasFlag("color_revealed");
    const beads = model.state.raw_color_clue.map((color) => `<i style="--bead:${COLORS[color]}" data-color="${esc(color)}"></i>`).join("");
    return `<div class="rel-gallery-room"><div class="rel-vitrine"><div class="rel-vitrine-crown"></div>
      ${revealed ? `<div class="rel-color-clue">${beads}</div><div class="rel-reliquary-form"><i></i><i></i><i></i></div>` : hotspot("dust_sheet", "dust-sheet", '<span></span>')}
      </div>${hotspot("wax_seal", "wax-seal", '<span></span>')}<div class="rel-packing-straw"></div><div class="rel-frames"><i></i><i></i></div>
    </div>`;
  }

  function radiatorScene() {
    return `<div class="rel-radiator-room"><div class="rel-radiator"><span></span><span></span><span></span><span></span><span></span><span></span></div>
      ${hotspot("radiator_wire", "radiator-wire", '<span></span>')}${hotspot("bone_pin", "bone-pin", '<span></span>')}
      <div class="rel-pipe a"></div><div class="rel-pipe b"></div><div class="rel-shadow-crates"><i></i><i></i></div><div class="rel-wall-stain"></div>
    </div>`;
  }

  function reliquaryScene() {
    const grateOpen = hasFlag("collected_ward_key");
    const orderOpen = hasFlag("order_revealed");
    return `<div class="rel-reliquary-room"><div class="rel-apse"></div><div class="rel-plinth"><div class="rel-glass-dome"><i></i></div></div>
      ${grateOpen ? `<div class="rel-open-grate" style="${targetStyle("grate")}"></div>` : hotspot("grate", "floor-grate", '<span><i></i><i></i><i></i><i></i></span>')}
      ${orderOpen ? `<div class="rel-open-order" style="${targetStyle("order_drawer")}">${directionCard()}</div>` : hotspot("order_drawer", "order-drawer", '<span><i></i></span>')}
      <div class="rel-chain-curtain"><i></i><i></i><i></i><i></i><i></i></div><div class="rel-censer"></div>
    </div>`;
  }

  function sceneMarkup() {
    const functions = {door: doorScene, desk: deskScene, cabinet: cabinetScene, gallery: galleryScene, radiator: radiatorScene, reliquary: reliquaryScene};
    return (functions[view().role] || (() => ""))();
  }

  function lockDialog() {
    if (!model.openLock || lockReleased(model.openLock)) return "";
    const blocked = model.state.parameters.cross_view_order && !hasFlag("order_revealed");
    if (model.openLock === "digit") {
      const wheels = model.digitInput.map((digit, index) => `<button data-digit-index="${index}"><span>▲</span><b>${digit}</b><small>▼</small></button>`).join("");
      return `<section class="rel-lock-dialog digit"><header><small>WARD I</small><b>NUMBER REGISTER</b><button data-close-lock>×</button></header><div class="rel-digit-wheels">${wheels}</div>
        <footer><span>${blocked ? "ORDER CARD SEALED" : `${model.wrong.digit || 0} WRONG`}</span><button id="rel-submit-digit" ${blocked ? "disabled" : ""}>SET DIAL</button></footer></section>`;
    }
    if (model.openLock === "color") {
      const palette = Object.entries(COLORS).map(([id, value]) => `<button data-color-key="${id}" style="--key-color:${value}" aria-label="${id}"><i></i></button>`).join("");
      const sequence = Array.from({length: Number(model.state.parameters.color_length)}, (_, index) => {
        const id = model.colorInput[index];
        return `<i style="--chosen:${id ? COLORS[id] : "transparent"}"></i>`;
      }).join("");
      return `<section class="rel-lock-dialog color"><header><small>WARD II</small><b>GLASS REGISTER</b><button data-close-lock>×</button></header><div class="rel-color-entry">${sequence}</div><div class="rel-color-keys">${palette}</div>
        <footer><button id="rel-clear-color">CLEAR</button><span>${blocked ? "ORDER CARD SEALED" : `${model.wrong.color || 0} WRONG`}</span><button id="rel-submit-color" ${blocked || model.colorInput.length !== Number(model.state.parameters.color_length) ? "disabled" : ""}>SET GLASS</button></footer></section>`;
    }
    return "";
  }

  function renderRoot() {
    const root = document.querySelector(".reliquary-root");
    if (!root) return;
    const dots = model.state.views.map((item) => `<i class="${item.id === model.viewId ? "is-current" : ""}"></i>`).join("");
    const inventory = model.inventory.length ? model.inventory.map(itemCard).join("") : '<div class="rel-empty-tray">NO OBJECTS CATALOGUED</div>';
    root.innerHTML = `${model.freshFailure ? '<div class="rel-fresh-failure"><b>WARD SEIZED</b><span>FRESH NIGHT REGISTER ISSUED</span></div>' : ""}
      <header class="rel-masthead"><div class="rel-monogram"><b>AR</b><small>03:17</small></div><div><small>WEST ANNEX · AFTER CLOSING</small><h1>${esc(model.state.prompt)}</h1></div>
        <div class="rel-tally"><span><small>WARDS</small><b>${model.released.size}/${model.state.active_locks.length}</b></span><span><small>OBJECTS</small><b>${model.collected.size}/${model.state.collectible_item_ids.length}</b></span><span><small>MISSES</small><b>${model.misses}</b></span></div></header>
      <main class="rel-work"><section class="rel-scene-shell"><div class="rel-view-index"><span>FIXED VIEW ${model.viewId + 1}</span><b>${dots}</b><span>${interaction() === "full" ? "EDGE TURN" : "CONTROL TURN"}</span></div>
        <div class="rel-scene role-${esc(view().role)} cue-${esc(model.state.parameters.cue_level)}" data-view-id="${model.viewId}" style="--room-palette:${view().palette}">${sceneMarkup()}
          ${interaction() === "full" ? '<button class="rel-turn edge left" data-direction="left" aria-label="Turn left">‹</button><button class="rel-turn edge right" data-direction="right" aria-label="Turn right">›</button>' : ""}
          ${lockDialog()}</div>
        ${interaction() === "simplified" ? '<div class="rel-turn-controls"><button class="rel-turn" data-direction="left">TURN LEFT</button><button class="rel-turn" data-direction="right">TURN RIGHT</button></div>' : ""}
      </section><section class="rel-inventory"><header><small>OBJECT TRAY</small><b>${interaction() === "full" ? "DRAG OBJECTS TO USE OR JOIN" : "SELECT, THEN CLICK A PLACE OR OBJECT"}</b></header><div class="rel-item-rack">${inventory}</div></section></main>
      <footer class="rel-footer"><div><small>NIGHT REGISTER</small><b>AH · ${esc(model.state.challenge_id.slice(-6).toUpperCase())}</b></div><div class="readout" data-status="${model.terminal ? "passed" : "idle"}">${model.terminal ? "PASS" : model.status}</div><div><small>WRONG ENTRIES</small><b>${Object.values(model.wrong).reduce((sum, value) => sum + value, 0)}</b></div></footer>
      ${model.helpers.cheatPanelTemplate()}`;
    bind();
    model.helpers.installCheatPanel();
  }

  function navigate(direction) {
    if (model.terminal || model.submitting) return;
    const from = model.viewId;
    const delta = direction === "left" ? -1 : 1;
    model.viewId = (model.viewId + delta + model.state.views.length) % model.state.views.length;
    model.openLock = null;
    model.selectedItem = null;
    record({type: "turn", from_view: from, to_view: model.viewId, direction, input_source: interaction() === "full" ? "edge_arrow" : "turn_button"});
    model.status = "VIEW CHANGED";
    renderRoot();
  }

  function collect(flag, itemId) {
    model.flags.add(flag);
    if (itemId) {
      model.inventory.push(itemId);
      model.collected.add(itemId);
    }
  }

  function sceneAction(item, event) {
    const action = item.action;
    if (action === "open_door") {
      if (!allReleased()) {
        record({type: "miss", point: pointIn(event, document.querySelector(".rel-scene")), input_source: "scene_background"});
        model.misses += 1;
        model.status = "THE WARDS HOLD";
        renderRoot();
        return;
      }
      record({type: "scene", target_id: item.id, point: pointIn(event, document.querySelector(".rel-scene")), input_source: "scene_click"});
      model.flags.add("door_open");
      submit(true);
      return;
    }
    const direct = {
      flip_label: ["label_flipped", null], collect_empty_frame: ["collected_empty_frame", "empty_frame"],
      open_lens_drawer: ["lens_drawer_open", null], collect_lens: ["collected_lens", "lens"],
      remove_dust_sheet: ["color_revealed", null], collect_hook: ["collected_hook", "hook"],
      lift_floor_tile: ["floor_open", null], collect_handle: ["collected_handle", "handle"],
      collect_wire: ["collected_wire", "wire"], reveal_order: ["order_revealed", null],
      collect_wax_seal: ["collected_wax_seal", "wax_seal"], collect_bone_pin: ["collected_bone_pin", "bone_pin"],
    }[action];
    if (!direct) return;
    record({type: "scene", target_id: item.id, point: pointIn(event, document.querySelector(".rel-scene")), input_source: "scene_click"});
    collect(direct[0], direct[1]);
    model.status = direct[1] ? "OBJECT CATALOGUED" : "ROOM STATE CHANGED";
    renderRoot();
  }

  function performCombine(first, second, source, gesture = null) {
    const recipe = model.state.recipes.find((item) => item.inputs.includes(first) && item.inputs.includes(second));
    if (!recipe || first === second) {
      record({type: "misuse", item_id: first, target_id: `item:${second}`, input_source: source, ...(gesture ? {gesture} : {})});
      model.misses += 1;
      model.status = "OBJECTS DO NOT JOIN";
      model.selectedItem = null;
      renderRoot();
      return;
    }
    record({type: "combine", first, second, result: recipe.output, input_source: source, ...(gesture ? {gesture} : {})});
    model.inventory.splice(model.inventory.indexOf(first), 1);
    model.inventory.splice(model.inventory.indexOf(second), 1);
    model.inventory.push(recipe.output);
    model.flags.add(`crafted_${recipe.output}`);
    model.selectedItem = null;
    model.status = "OBJECTS JOINED";
    renderRoot();
  }

  function performUse(itemId, targetId, source, gesture = null) {
    const sceneTarget = target(targetId);
    const expected = {use_loupe: "loupe", use_hook: "hook", use_key: "ward_key"}[sceneTarget?.action];
    if (!sceneTarget || expected !== itemId) {
      record({type: "misuse", item_id: itemId, target_id: targetId, input_source: source, ...(gesture ? {gesture} : {})});
      model.misses += 1;
      model.selectedItem = null;
      if (sceneTarget?.action === "use_key" && activeLock("key") && !lockReleased("key")) {
        model.wrong.key += 1;
        model.status = `KEY WARD · STRIKE ${model.wrong.key}/${model.state.parameters.max_wrong_entries}`;
        if (model.wrong.key >= Number(model.state.parameters.max_wrong_entries)) {
          model.seized = "key";
          submit(false);
          return;
        }
      } else {
        model.status = "NO RESPONSE";
      }
      renderRoot();
      return;
    }
    record({type: "use", item_id: itemId, target_id: targetId, input_source: source, ...(gesture ? {gesture} : {})});
    if (sceneTarget.action === "use_loupe") model.flags.add("digit_revealed");
    if (sceneTarget.action === "use_hook") {
      model.flags.add("collected_ward_key");
      model.inventory.push("ward_key");
      model.collected.add("ward_key");
    }
    if (sceneTarget.action === "use_key") {
      model.released.add("key");
      model.flags.add("key_released");
      model.inventory.splice(model.inventory.indexOf("ward_key"), 1);
    }
    model.selectedItem = null;
    model.status = sceneTarget.action === "use_key" ? "KEY WARD OPEN" : sceneTarget.action === "use_hook" ? "OBJECT RECOVERED" : "INSCRIPTION RESOLVED";
    renderRoot();
  }

  function selectItem(itemId) {
    if (model.terminal || model.submitting) return;
    if (model.selectedItem && model.selectedItem !== itemId) {
      performCombine(model.selectedItem, itemId, "inventory_select_pair");
      return;
    }
    model.selectedItem = model.selectedItem === itemId ? null : itemId;
    model.status = model.selectedItem ? "OBJECT SELECTED" : "NIGHT REGISTER OPEN";
    renderRoot();
  }

  function submitWard(lock, guess) {
    if (model.submitting || model.terminal) return;
    const answer = model.state.runtime_lock_answers[lock];
    const accepted = lock === "digit" ? guess === answer : JSON.stringify(guess) === JSON.stringify(answer);
    record({type: `${lock}_submit`, guess, accepted, input_source: `${lock}_controls`});
    if (accepted) {
      model.released.add(lock);
      model.flags.add(`${lock}_released`);
      model.openLock = null;
      model.status = `${lock.toUpperCase()} WARD OPEN`;
    } else {
      model.wrong[lock] += 1;
      model.status = `${lock.toUpperCase()} WARD · STRIKE ${model.wrong[lock]}/${model.state.parameters.max_wrong_entries}`;
      if (lock === "digit") model.digitInput = model.digitInput.map(() => 0);
      else model.colorInput = [];
      if (model.wrong[lock] >= Number(model.state.parameters.max_wrong_entries)) {
        model.seized = lock;
        submit(false);
        return;
      }
    }
    renderRoot();
  }

  function finalState() {
    return {
      view_id: model.viewId,
      flags: [...model.flags].sort(),
      inventory: [...model.inventory],
      released_locks: model.state.active_locks.filter((lock) => model.released.has(lock)),
      wrong_entries: Object.fromEntries(model.state.active_locks.map((lock) => [lock, model.wrong[lock]])),
      seized_lock: model.seized,
      completed: hasFlag("door_open"),
    };
  }

  function counters() {
    return {
      locks_released: model.released.size,
      items_collected: model.collected.size,
      items_total: model.state.collectible_item_ids.length,
      misses: model.misses,
      wrong_lock_entries: Object.values(model.wrong).reduce((sum, value) => sum + value, 0),
    };
  }

  async function submit(completed) {
    if (model.submitting || model.terminal) return;
    const current = model;
    current.submitting = true;
    if (completed) current.status = "OPENING EXIT…";
    current.helpers.setReadout(completed ? "REPLAYING NIGHT REGISTER…" : "WARD SEIZED…", "pending");
    try {
      const response = await fetch("/result", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({
        mechanic_id: current.state.mechanic_id, task_id: current.state.task_id, challenge_id: current.state.challenge_id,
        interaction_mode: interaction(), events: current.events, final_state: finalState(), counters: counters(), completed,
      })});
      const outcome = await response.json();
      if (outcome.passed === true) {
        current.terminal = true;
        current.status = "PASS";
        current.helpers.setReadout("PASS", "passed");
        renderRoot();
        document.querySelector(".reliquary-root")?.setAttribute("data-terminal", "passed");
      } else if (outcome.passed === false && outcome.state) {
        await render(outcome.state, current.helpers, {freshFailure: true});
        model.helpers.setReadout("FAIL", "error");
      } else {
        current.submitting = false;
        current.status = "REGISTER REJECTED";
        current.helpers.setReadout("FAIL", "error");
        renderRoot();
      }
    } catch (_error) {
      if (model === current) {
        current.submitting = false;
        current.status = "ARCHIVE LINK OFFLINE";
        current.helpers.setReadout("ARCHIVE LINK OFFLINE", "error");
        renderRoot();
      }
    }
  }

  function bindDrag(card) {
    let drag = null;
    card.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || model.terminal || model.submitting) return;
      event.preventDefault();
      clearFreshFailure();
      const root = document.querySelector(".reliquary-root");
      const rack = document.querySelector(".rel-item-rack");
      card.setPointerCapture?.(event.pointerId);
      drag = {startRoot: pointIn(event, root), startInventory: pointIn(event, rack), x: event.clientX, y: event.clientY, travel: 0, samples: 0};
      card.classList.add("is-dragging");
    });
    card.addEventListener("pointermove", (event) => {
      if (!drag) return;
      drag.travel += Math.hypot(event.clientX - drag.x, event.clientY - drag.y);
      drag.x = event.clientX; drag.y = event.clientY; drag.samples += 1;
      card.style.setProperty("--drag-x", `${event.clientX - card.getBoundingClientRect().left - card.offsetWidth / 2}px`);
      card.style.setProperty("--drag-y", `${event.clientY - card.getBoundingClientRect().top - card.offsetHeight / 2}px`);
    });
    card.addEventListener("pointerup", (event) => {
      if (!drag) return;
      drag.travel += Math.hypot(event.clientX - drag.x, event.clientY - drag.y); drag.samples += 1;
      const root = document.querySelector(".reliquary-root");
      const scene = document.querySelector(".rel-scene");
      const rack = document.querySelector(".rel-item-rack");
      const under = document.elementFromPoint(event.clientX, event.clientY);
      const targetItem = under?.closest?.("[data-item-id]");
      const targetHotspot = under?.closest?.("[data-hotspot-id]");
      const proof = {start_root: drag.startRoot, start_inventory: drag.startInventory, end_root: pointIn(event, root), travel_px: Number(drag.travel.toFixed(3)), sample_count: drag.samples};
      const sourceId = card.dataset.itemId;
      drag = null; card.classList.remove("is-dragging"); card.style.removeProperty("--drag-x"); card.style.removeProperty("--drag-y");
      if (targetItem && targetItem.dataset.itemId !== sourceId) {
        proof.end_inventory = pointIn(event, rack);
        performCombine(sourceId, targetItem.dataset.itemId, "inventory_drag_item", proof);
      }
      else if (targetHotspot && available(target(targetHotspot.dataset.hotspotId))) {
        proof.end_scene = pointIn(event, scene);
        performUse(sourceId, targetHotspot.dataset.hotspotId, "inventory_drag_scene", proof);
      } else {
        record({type: "misuse", item_id: sourceId, target_id: "scene:none", input_source: "inventory_drag_scene", gesture: proof});
        model.misses += 1; model.status = "NO RESPONSE"; renderRoot();
      }
    });
    card.addEventListener("pointercancel", () => { drag = null; card.classList.remove("is-dragging"); });
  }

  function bind() {
    document.querySelectorAll(".rel-turn").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.direction)));
    document.querySelectorAll("[data-hotspot-id]").forEach((node) => node.addEventListener("click", (event) => {
      event.stopPropagation();
      const item = target(node.dataset.hotspotId);
      if (interaction() === "simplified" && model.selectedItem) performUse(model.selectedItem, item.id, "inventory_select_scene");
      else sceneAction(item, event);
    }));
    document.querySelectorAll("[data-lock-panel]").forEach((button) => button.addEventListener("click", () => {
      const lock = button.dataset.lockPanel;
      if (lock === "key" || lockReleased(lock)) return;
      model.openLock = lock; model.selectedItem = null; renderRoot();
    }));
    document.querySelectorAll("[data-close-lock]").forEach((button) => button.addEventListener("click", () => { model.openLock = null; renderRoot(); }));
    document.querySelectorAll("[data-digit-index]").forEach((button) => button.addEventListener("click", () => {
      const index = Number(button.dataset.digitIndex); model.digitInput[index] = (model.digitInput[index] + 1) % 10; renderRoot();
    }));
    document.getElementById("rel-submit-digit")?.addEventListener("click", () => submitWard("digit", model.digitInput.join("")));
    document.querySelectorAll("[data-color-key]").forEach((button) => button.addEventListener("click", () => {
      if (model.colorInput.length < Number(model.state.parameters.color_length)) model.colorInput.push(button.dataset.colorKey);
      renderRoot();
    }));
    document.getElementById("rel-clear-color")?.addEventListener("click", () => { model.colorInput = []; renderRoot(); });
    document.getElementById("rel-submit-color")?.addEventListener("click", () => submitWard("color", [...model.colorInput]));
    document.querySelectorAll("[data-item-id]").forEach((card) => interaction() === "simplified"
      ? card.addEventListener("click", () => selectItem(card.dataset.itemId)) : bindDrag(card));
    document.querySelector(".rel-scene")?.addEventListener("click", (event) => {
      if (event.target.closest("button") || model.openLock) return;
      record({type: "miss", point: pointIn(event, event.currentTarget), input_source: "scene_background"});
      model.misses += 1; model.status = "NOTHING THERE"; renderRoot();
    });
  }

  function showFreshFailure() {
    model.status = "FAIL · FRESH NIGHT REGISTER";
    renderRoot();
  }

  async function render(state, helpers, options = {}) {
    cleanup?.();
    document.body.dataset.mechanic = "after-hours-at-the-reliquary";
    model = {
      state, helpers, viewId: 0, flags: new Set(), inventory: [], collected: new Set(), released: new Set(),
      wrong: Object.fromEntries(state.active_locks.map((lock) => [lock, 0])), seized: null, misses: 0,
      selectedItem: null, openLock: null, digitInput: Array.from({length: Number(state.parameters.digit_length)}, () => 0),
      colorInput: [], events: [], status: "NIGHT REGISTER OPEN", submitting: false, terminal: false,
      freshFailure: Boolean(options.freshFailure),
    };
    helpers.app.innerHTML = `<section class="reliquary-root mode-${esc(interaction())}" data-interaction="${esc(interaction())}" data-challenge-id="${esc(state.challenge_id)}"></section>`;
    renderRoot();
    if (options.freshFailure) showFreshFailure();
    cleanup = () => {};
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics[MECHANIC_ID] = {rootSelector: ".reliquary-root", render};
})();
