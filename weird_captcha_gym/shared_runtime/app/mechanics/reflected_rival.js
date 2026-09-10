(() => {
  "use strict";

  let model = null;

  const sourceFor = interaction => interaction === "simplified" ? "direction_buttons" : "keyboard";
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

  function cellAt(progress, lane) {
    const board = model.state.board;
    const segment = clamp(Math.floor(progress), 0, Number(board.segment_count) - 1);
    return board.course[segment].cells[lane];
  }

  function progressSegment(progress) {
    return clamp(Math.floor(progress), 0, Number(model.state.board.segment_count) - 1);
  }

  function record(direction, inputSource) {
    model.actions.push({
      sequence: model.actions.length + 1,
      tick: model.tick,
      direction,
      input_source: inputSource,
    });
  }

  function move(direction, inputSource) {
    if (!model || model.done || !["left", "right"].includes(direction)) return;
    record(direction, inputSource);
    const delta = direction === "left" ? -1 : 1;
    const lanes = Number(model.state.board.lane_count);
    model.playerLane = clamp(model.playerLane + delta, 0, lanes - 1);
    model.rivalLane = clamp(model.rivalLane - delta, 0, lanes - 1);
    model.lastMove = direction;
    model.helpers.setReadout("", "idle");
    draw();
  }

  function advance() {
    if (!model || model.done) return;
    const board = model.state.board;
    const segments = Number(board.segment_count);
    if (model.playerFinishTick === null) {
      model.playerProgress += Number(board.base_rate) * Number(cellAt(model.playerProgress, model.playerLane).multiplier);
    }
    if (model.rivalFinishTick === null) {
      model.rivalProgress += Number(board.base_rate) * Number(cellAt(model.rivalProgress, model.rivalLane).multiplier);
    }
    model.tick += 1;
    if (model.playerFinishTick === null && model.playerProgress >= segments) model.playerFinishTick = model.tick;
    if (model.rivalFinishTick === null && model.rivalProgress >= segments) model.rivalFinishTick = model.tick;
    draw();
    if ((model.playerFinishTick !== null && model.rivalFinishTick !== null) || model.tick >= Number(board.max_ticks)) {
      finish();
    }
  }

  async function submitPending() {
    const race = model;
    if (!race?.pendingResult || race.submitting) return;
    race.submitting = true;
    const retry = document.querySelector("[data-rr-retry]");
    if (retry) retry.hidden = true;
    race.helpers.setReadout("VERIFYING RACE", "idle");
    try {
      const response = await fetch("/result", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify(race.pendingResult),
      });
      if (!response.ok) throw new Error(`Result request failed: ${response.status}`);
      const outcome = await response.json();
      if (model !== race) return;
      if (outcome.passed === true) {
        race.helpers.setReadout("PASS — WHITE FINISHED FIRST", "passed");
        document.querySelector(".rr-shell")?.classList.add("is-passed");
      } else if (outcome.state) {
        race.helpers.setReadout("FAIL — A FRESH COURSE IS LOADING", "error");
        document.querySelector(".rr-shell")?.classList.add("is-failed");
        setTimeout(() => {
          if (model === race) race.helpers.render(outcome.state);
        }, 760);
      } else {
        throw new Error("Result response has no verdict or fresh course");
      }
      race.pendingResult = null;
      draw();
    } catch (error) {
      if (model !== race) return;
      // Preserve the exact terminal transcript; steering and time stay stopped.
      race.helpers.setReadout("SUBMISSION ERROR — RETRY RESULT", "error");
      if (retry) retry.hidden = false;
    } finally {
      race.submitting = false;
    }
  }

  async function finish(abandoned = false) {
    const race = model;
    if (!race || race.done) return;
    race.done = true;
    if (race.timer) clearInterval(race.timer);
    const completed = !abandoned && race.playerFinishTick !== null && race.rivalFinishTick !== null && race.playerFinishTick < race.rivalFinishTick;
    race.pendingResult = {
      mechanic_id: race.state.mechanic_id,
      task_id: race.state.task_id,
      challenge_id: race.state.challenge_id,
      actions: race.actions.slice(),
      final_tick: race.tick,
      completed,
      player_finish_tick: race.playerFinishTick,
      rival_finish_tick: race.rivalFinishTick,
      ...(abandoned ? {reason: "abandoned"} : {}),
    };
    race.helpers.setReadout(completed ? "WHITE WINS — VERIFYING" : abandoned ? "RUN ABANDONED — LOADING A FRESH COURSE" : "RIVAL AHEAD — REBUILDING COURSE", completed ? "passed" : "error");
    draw();
    if (!completed && !abandoned) await new Promise(resolve => window.setTimeout(resolve, 900));
    if (model === race) await submitPending();
  }

  function abandon() {
    return finish(true);
  }

  function racerTop(progress, worldHeight, rowHeight) {
    return worldHeight - rowHeight - progress * rowHeight;
  }

  function draw() {
    if (!model) return;
    const board = model.state.board;
    const lanes = Number(board.lane_count);
    const segments = Number(board.segment_count);
    const rowHeight = 58;
    const worldHeight = (segments + 2) * rowHeight;
    const viewport = document.querySelector(".rr-track-viewport");
    const world = document.querySelector(".rr-track-world");
    if (!viewport || !world) return;
    const maxCamera = Math.max(0, worldHeight - viewport.clientHeight);
    const playerY = racerTop(Math.min(model.playerProgress, segments), worldHeight, rowHeight);
    const rivalY = racerTop(Math.min(model.rivalProgress, segments), worldHeight, rowHeight);
    const camera = clamp(((playerY + rivalY) / 2) - viewport.clientHeight * 0.54, 0, maxCamera);
    world.style.transform = `translate3d(0, ${-camera}px, 0)`;
    const player = document.querySelector(".rr-racer.is-player");
    const rival = document.querySelector(".rr-racer.is-rival");
    if (player) {
      player.style.left = `${(model.playerLane + 0.5) / lanes * 100}%`;
      player.style.top = `${playerY}px`;
      player.dataset.segment = String(progressSegment(model.playerProgress));
    }
    if (rival) {
      rival.style.left = `${(model.rivalLane + 0.5) / lanes * 100}%`;
      rival.style.top = `${rivalY}px`;
      rival.dataset.segment = String(progressSegment(model.rivalProgress));
    }
    const root = document.querySelector(".rr-shell");
    if (root) {
      root.dataset.tick = String(model.tick);
      root.dataset.playerSegment = String(progressSegment(model.playerProgress));
      root.dataset.rivalSegment = String(progressSegment(model.rivalProgress));
      root.dataset.playerLane = String(model.playerLane);
      root.dataset.rivalLane = String(model.rivalLane);
    }
    const tickNode = document.querySelector(".rr-tick b");
    const playerSector = document.querySelector(".rr-player-sector b");
    const rivalSector = document.querySelector(".rr-rival-sector b");
    const gapNode = document.querySelector(".rr-gap b");
    if (tickNode) tickNode.textContent = String(model.tick).padStart(3, "0");
    if (playerSector) playerSector.textContent = model.playerFinishTick === null ? `${progressSegment(model.playerProgress) + 1}/${segments}` : "FINISH";
    if (rivalSector) rivalSector.textContent = model.rivalFinishTick === null ? `${progressSegment(model.rivalProgress) + 1}/${segments}` : "FINISH";
    if (gapNode) gapNode.textContent = `${(model.playerProgress - model.rivalProgress).toFixed(2)} sectors`;
    document.querySelectorAll(".rr-cell").forEach(node => {
      const segment = Number(node.dataset.segment);
      const lane = Number(node.dataset.lane);
      node.classList.toggle("is-player-sector", segment === progressSegment(model.playerProgress) && lane === model.playerLane);
      node.classList.toggle("is-rival-sector", segment === progressSegment(model.rivalProgress) && lane === model.rivalLane);
    });
  }

  function courseMarkup(board) {
    const lanes = Number(board.lane_count);
    const segments = Number(board.segment_count);
    const cells = [];
    for (const segment of board.course) {
      for (let lane = 0; lane < lanes; lane += 1) {
        const cell = segment.cells[lane];
        cells.push(`<div class="rr-cell terrain-${cell.kind}" data-segment="${segment.index}" data-lane="${lane}" style="left:${lane / lanes * 100}%;top:${(segments - segment.index) * 58}px;width:${100 / lanes}%"><span>${cell.kind === "boost" ? "↗" : cell.kind === "slow" ? "↘" : "·"}</span></div>`);
      }
    }
    return cells.join("");
  }

  async function render(state, helpers) {
    document.body.dataset.mechanic = "reflected-rival";
    if (model?.timer) clearInterval(model.timer);
    if (model?.keyHandler) window.removeEventListener("keydown", model.keyHandler);
    const board = state.board;
    const interaction = state.control_condition?.interaction || "full";
    const lanes = Number(board.lane_count);
    const segments = Number(board.segment_count);
    model = {
      state,
      helpers,
      interaction,
      tick: 0,
      actions: [],
      playerLane: Number(board.player_start_lane),
      rivalLane: Number(board.rival_start_lane),
      playerProgress: 0,
      rivalProgress: 0,
      playerFinishTick: null,
      rivalFinishTick: null,
      lastMove: "",
      timer: null,
      done: false,
      keyHandler: null,
    };
    const controls = interaction === "simplified"
      ? `<div class="rr-proxy-controls" aria-label="Visible steering controls"><button type="button" data-rr-direction="left" aria-label="Steer left">← LEFT</button><button type="button" data-rr-direction="right" aria-label="Steer right">RIGHT →</button></div>`
      : `<div class="rr-key-controls"><span>FULL INPUT</span><b>←</b><b>→</b><small>Arrow keys steer both racers in mirrored directions.</small></div>`;
    helpers.app.innerHTML = `<main class="rr-shell" data-interaction="${interaction}" data-lanes="${lanes}" data-segments="${segments}" tabindex="0">
      <header class="rr-header">
        <div class="rr-title"><span class="rr-kicker">MIRROR CIRCUIT / COUPLED CONTROL</span><h1>Reflected Rival</h1><p>${state.prompt}</p></div>
        <div class="rr-stat rr-tick"><span>WORLD TICK</span><b>000</b></div>
        <div class="rr-stat rr-gap"><span>WHITE − BLUE</span><b>0.00 sectors</b></div>
      </header>
      <section class="rr-body">
        <div class="rr-track-viewport" aria-label="Visible mirrored race course">
          <div class="rr-track-world" style="height:${(segments + 2) * 58}px">${courseMarkup(board)}
            <div class="rr-finish-line">FINISH / WHITE MUST ARRIVE FIRST</div>
            <div class="rr-racer is-rival" data-racer="blue"><i></i><b>BLUE</b></div>
            <div class="rr-racer is-player" data-racer="white"><i></i><b>WHITE</b></div>
            <div class="rr-start-line">START</div>
          </div>
        </div>
        <aside class="rr-sidepanel">
          <div class="rr-legend"><div><i class="legend-white"></i><span>WHITE / YOU</span><strong class="rr-player-sector">SECTOR <b>1/${segments}</b></strong></div><div><i class="legend-blue"></i><span>BLUE / MIRROR</span><strong class="rr-rival-sector">SECTOR <b>1/${segments}</b></strong></div></div>
          <div class="rr-rule"><span>ONE COMMAND</span><strong>two racers react</strong><p>Every left or right action moves WHITE that way and BLUE the opposite way. Green strips accelerate; red strips drain speed.</p></div>
          <div class="rr-terrain-key"><span class="key-boost">↗ BOOST</span><span class="key-slow">↘ SLOW</span><span class="key-plain">· PLAIN</span></div>
          ${controls}
          <button class="rr-abandon" type="button" data-rr-abandon>ABANDON / NEW COURSE</button>
          <button class="rr-abandon" type="button" data-rr-retry hidden>RETRY RESULT</button>
          <div class="readout" data-status="idle" aria-live="polite"></div>
        </aside>
      </section>
      <footer class="rr-footer"><span>READ BOTH TRAJECTORIES</span><span>DO NOT OPTIMIZE WHITE ALONE</span><span>CHALLENGE ${String(state.challenge_id).slice(0, 8).toUpperCase()}</span></footer>
    </main>`;
    model.keyHandler = event => {
      if (interaction !== "full" || event.repeat) return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        move(event.key === "ArrowLeft" ? "left" : "right", "keyboard");
      }
    };
    window.addEventListener("keydown", model.keyHandler);
    document.querySelectorAll("[data-rr-direction]").forEach(button => button.addEventListener("click", () => move(button.dataset.rrDirection, "direction_buttons")));
    document.querySelector("[data-rr-abandon]")?.addEventListener("click", abandon);
    document.querySelector("[data-rr-retry]")?.addEventListener("click", submitPending);
    document.querySelector(".rr-shell")?.focus();
    draw();
    model.timer = setInterval(advance, Number(board.tick_ms));
  }

  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.reflected_rival = {render, rootSelector: ".rr-shell"};
})();
