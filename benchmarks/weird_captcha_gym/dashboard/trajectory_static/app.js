const state = {
  index: null,
  filtered: [],
  detail: null,
  activeRunId: null,
  turn: 0,
  frame: 0,
  playing: false,
  timer: null,
};

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatSeconds(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function formatMs(value) {
  const ms = Number(value);
  if (!Number.isFinite(ms)) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

function humanize(value) {
  return String(value ?? "—").replaceAll("_", " ");
}

function setOptions(select, values) {
  [...new Set(values.filter(Boolean))].sort().forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = humanize(value);
    select.append(option);
  });
}

function filters() {
  return {
    query: $("#search").value.trim().toLowerCase(),
    time: $("#filter-time").value,
    interaction: $("#filter-interaction").value,
    reason: $("#filter-reason").value,
  };
}

function applyFilters() {
  const selected = filters();
  state.filtered = state.index.runs.filter((run) => {
    const haystack = `${run.title} ${run.id} ${run.feedback} ${run.mechanic_id}`.toLowerCase();
    return (!selected.query || haystack.includes(selected.query))
      && (!selected.time || run.time_mode === selected.time)
      && (!selected.interaction || run.interaction === selected.interaction)
      && (!selected.reason || run.reason === selected.reason);
  });
  renderRunList();
}

function renderRunList() {
  $("#visible-count").textContent = `${state.filtered.length} / ${state.index.runs.length}`;
  if (!state.filtered.length) {
    $("#run-list").innerHTML = '<div class="empty-list">No trajectories match these filters.</div>';
    return;
  }
  $("#run-list").innerHTML = state.filtered.map((run) => `
    <button class="run-card ${run.id === state.activeRunId ? "is-active" : ""}"
      type="button" role="option" aria-selected="${run.id === state.activeRunId}"
      data-run-id="${escapeHtml(run.id)}">
      <span class="run-index">${String(run.index + 1).padStart(3, "0")}</span>
      <span class="run-copy">
        <strong>${escapeHtml(run.title)}</strong>
        <span class="run-meta">
          <span>L${escapeHtml(run.difficulty)}</span>
          <span>${escapeHtml(run.interaction)}</span>
          <span class="${escapeHtml(run.time_mode)}">${escapeHtml(run.time_mode)}</span>
          <span>${escapeHtml(run.turn_count)} turns</span>
        </span>
      </span>
    </button>
  `).join("");
  $("#run-list").querySelectorAll("[data-run-id]").forEach((button) => {
    button.addEventListener("click", () => selectRun(button.dataset.runId));
  });
}

function parsedMetadata(turn) {
  return turn?.parsed?.metadata && typeof turn.parsed.metadata === "object"
    ? turn.parsed.metadata
    : {};
}

function activeFrame(turn) {
  if (!turn?.frames?.length) return null;
  const index = Math.max(0, Math.min(state.frame, turn.frames.length - 1));
  return turn.frames[index];
}

function marker(turn, frame) {
  if (!turn?.click || frame?.kind !== "current") return "";
  const left = Math.max(0, Math.min(100, turn.click.x / 1280 * 100));
  const top = Math.max(0, Math.min(100, turn.click.y / 720 * 100));
  return `<span class="action-marker" title="Action coordinate" style="left:${left}%;top:${top}%"></span>`;
}

function telemetry(detail) {
  const setup = detail.setup || {};
  const limit = setup.task_play_time_limit_enabled === false
    ? "NONE"
    : setup.task_play_time_limit_seconds ?? setup.settings?.play_time_seconds ?? "—";
  return `
    <div><small>STOPPING REASON</small><strong>${escapeHtml(humanize(detail.reason))}</strong></div>
    <div><small>WALL DURATION</small><strong>${escapeHtml(formatSeconds(detail.duration_seconds))}</strong></div>
    <div><small>MODEL</small><strong title="${escapeHtml(detail.model)}">${escapeHtml(detail.model)}</strong></div>
    <div><small>TASK TIME LIMIT</small><strong>${escapeHtml(limit === "NONE" ? limit : `${limit}s`)}</strong></div>
  `;
}

function renderViewer() {
  const detail = state.detail;
  const turn = detail.turns[state.turn] || { frames: [], timing: {} };
  const frame = activeFrame(turn);
  const metadata = parsedMetadata(turn);
  const timing = turn.timing || {};
  const taskTime = timing.task_time_before_model_ms;
  const request = (timing.request_attempts || []).at(-1) || {};
  const totalTurns = detail.turns.length;
  const frameDots = (turn.frames || []).map((item, index) => `
    <button class="frame-dot ${index === state.frame ? "is-active" : ""}" type="button"
      data-frame="${index}" title="Observation frame ${index + 1}">${index + 1}</button>
  `).join("");
  const turnTabs = detail.turns.map((item, index) => `
    <button class="turn-tab ${index === state.turn ? "is-active" : ""}" type="button" data-turn="${index}">
      ${String(index + 1).padStart(2, "0")} · ${item.frames.length || 0}F
    </button>
  `).join("");
  const thought = metadata.thought ? `
    <div class="thought-block"><small>EXPLICIT REASONING</small><p>${escapeHtml(metadata.thought)}</p></div>
  ` : "";

  $("#viewer").innerHTML = `
    <article class="trajectory">
      <header class="trajectory-head">
        <div>
          <p class="kicker">RUN ${String(detail.index + 1).padStart(3, "0")} · SEED ${escapeHtml(detail.seed)}</p>
          <h1>${escapeHtml(detail.title)}</h1>
        </div>
        <div class="condition-line">
          <span class="condition">L${escapeHtml(detail.difficulty)}</span>
          <span class="condition">${escapeHtml(detail.interaction)}</span>
          <span class="condition ${escapeHtml(detail.time_mode)}">${escapeHtml(detail.time_mode)}</span>
        </div>
      </header>

      <div class="inspection-grid">
        <section class="screen-column">
          <div class="screen-toolbar">
            <div class="step-control">
              <button class="icon-button" id="previous-turn" type="button" aria-label="Previous turn">←</button>
              <button class="play-button" id="play-turns" type="button" aria-label="Play trajectory">${state.playing ? "Ⅱ" : "▶"}</button>
              <button class="icon-button" id="next-turn" type="button" aria-label="Next turn">→</button>
            </div>
            <div class="turn-readout"><b>MODEL TURN ${state.turn + 1} / ${totalTurns}</b><small>ARROW KEYS TO STEP</small></div>
            <div class="frame-dots">${frameDots}</div>
          </div>
          <div class="screen-stage">
            ${frame ? `<img src="${escapeHtml(frame.url)}" alt="Screenshot shown to the model on turn ${state.turn + 1}">${marker(turn, frame)}` : '<span class="screen-placeholder">NO SCREENSHOT RECORDED</span>'}
          </div>
          <div class="screen-caption">
            <span>${frame ? `FRAME ${state.frame + 1} OF ${turn.frames.length}` : "NO FRAME"}</span>
            <span class="${frame?.kind === "current" ? "current-frame" : ""}">${frame?.kind === "current" ? "CURRENT STATE" : "OBSERVATION WINDOW"}</span>
          </div>
        </section>

        <aside class="verdict-column">
          <div class="verdict">
            <span class="status ${detail.passed ? "pass" : ""}">${detail.passed ? "PASS" : "BENCHMARK FAILURE"}</span>
            <blockquote>${escapeHtml(detail.feedback)}</blockquote>
          </div>
          <div class="telemetry">${telemetry(detail)}</div>
          <div class="instruction"><small>TASK INSTRUCTION</small><p>${escapeHtml(detail.instruction || "No task instruction recorded.")}</p></div>
        </aside>
      </div>

      <nav class="turn-strip" aria-label="Model turns">${turnTabs}</nav>

      <div class="trace-grid">
        <section class="trace-panel">
          <div class="section-title"><h2>MODEL RESPONSE</h2><span>RAW OUTPUT</span></div>
          <pre class="model-response">${escapeHtml(turn.response || "No response recorded.")}</pre>
          ${thought}
        </section>
        <section class="trace-panel">
          <div class="section-title"><h2>PARSED CONTROL</h2><span>${escapeHtml(metadata.action_type || "NO ACTION TYPE")}</span></div>
          <pre class="parsed-response">${escapeHtml(turn.parsed ? JSON.stringify(turn.parsed.actions ?? turn.parsed, null, 2) : "No parsed response recorded.")}</pre>
          <div class="timing-row">
            <div><small>MODEL WALL</small><b>${escapeHtml(formatMs(timing.model_ms))}</b></div>
            <div><small>REQUEST WALL</small><b>${escapeHtml(formatMs(request.wall_ms))}</b></div>
            <div><small>TASK CLOCK</small><b>${escapeHtml(formatMs(taskTime))}</b></div>
          </div>
        </section>
      </div>
    </article>
  `;

  $("#previous-turn").addEventListener("click", () => changeTurn(-1));
  $("#next-turn").addEventListener("click", () => changeTurn(1));
  $("#play-turns").addEventListener("click", togglePlayback);
  $("#viewer").querySelectorAll("[data-turn]").forEach((button) => {
    button.addEventListener("click", () => setTurn(Number(button.dataset.turn)));
  });
  $("#viewer").querySelectorAll("[data-frame]").forEach((button) => {
    button.addEventListener("click", () => {
      state.frame = Number(button.dataset.frame);
      renderViewer();
    });
  });
  $(".turn-tab.is-active")?.scrollIntoView({ block: "nearest", inline: "center" });
}

function setTurn(value) {
  if (!state.detail?.turns.length) return;
  state.turn = Math.max(0, Math.min(value, state.detail.turns.length - 1));
  state.frame = Math.max(0, (state.detail.turns[state.turn].frames?.length || 1) - 1);
  updateHash();
  renderViewer();
}

function changeTurn(delta) {
  const next = state.turn + delta;
  if (next >= state.detail.turns.length && state.playing) {
    stopPlayback();
    return;
  }
  setTurn(next);
}

function stopPlayback() {
  clearInterval(state.timer);
  state.timer = null;
  state.playing = false;
  renderViewer();
}

function togglePlayback() {
  if (state.playing) {
    stopPlayback();
    return;
  }
  if (state.turn >= state.detail.turns.length - 1) setTurn(0);
  state.playing = true;
  state.timer = setInterval(() => changeTurn(1), 1250);
  renderViewer();
}

function updateHash() {
  const params = new URLSearchParams({ run: state.activeRunId, turn: String(state.turn + 1) });
  history.replaceState(null, "", `#${params}`);
}

async function selectRun(runId, requestedTurn = 0) {
  const summary = state.index.runs.find((run) => run.id === runId);
  if (!summary) return;
  clearInterval(state.timer);
  state.playing = false;
  state.activeRunId = runId;
  state.turn = requestedTurn;
  state.frame = 0;
  renderRunList();
  $("#viewer").innerHTML = '<div class="initial-state"><span class="loading-sweep"></span><p>Reading trajectory…</p></div>';
  try {
    const response = await fetch(summary.detail_url);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    state.detail = await response.json();
    state.turn = Math.max(0, Math.min(requestedTurn, state.detail.turns.length - 1));
    state.frame = Math.max(0, (state.detail.turns[state.turn]?.frames?.length || 1) - 1);
    updateHash();
    renderViewer();
  } catch (error) {
    $("#viewer").innerHTML = `<div class="error-state"><strong>Trajectory unavailable</strong><pre>${escapeHtml(error.stack || error)}</pre></div>`;
  }
}

function bindControls() {
  ["#search", "#filter-time", "#filter-interaction", "#filter-reason"].forEach((selector) => {
    $(selector).addEventListener(selector === "#search" ? "input" : "change", applyFilters);
  });
  $("#clear-filters").addEventListener("click", () => {
    $("#search").value = "";
    $("#filter-time").value = "";
    $("#filter-interaction").value = "";
    $("#filter-reason").value = "";
    applyFilters();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && document.activeElement?.tagName !== "INPUT") {
      event.preventDefault();
      $("#search").focus();
    }
    if (document.activeElement?.tagName === "INPUT") return;
    if (event.key === "ArrowLeft") changeTurn(-1);
    if (event.key === "ArrowRight") changeTurn(1);
    if (event.key === " ") { event.preventDefault(); togglePlayback(); }
  });
}

async function boot() {
  try {
    const response = await fetch("data/index.json");
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    state.index = await response.json();
    state.filtered = state.index.runs;
    $("#evaluation-name").textContent = state.index.evaluation;
    $("#header-stats").innerHTML = `
      <span class="header-stat"><b>${state.index.stats.runs}</b><span>RUNS</span></span>
      <span class="header-stat"><b>${state.index.stats.screenshots}</b><span>SCREENSHOTS</span></span>
      <span class="header-stat is-fail"><b>${state.index.stats.failures}</b><span>FAILURES</span></span>
    `;
    setOptions($("#filter-time"), state.index.runs.map((run) => run.time_mode));
    setOptions($("#filter-interaction"), state.index.runs.map((run) => run.interaction));
    setOptions($("#filter-reason"), state.index.runs.map((run) => run.reason));
    bindControls();
    renderRunList();
    const hash = new URLSearchParams(location.hash.slice(1));
    const initial = state.index.runs.find((run) => run.id === hash.get("run")) || state.index.runs[0];
    await selectRun(initial.id, Math.max(0, Number(hash.get("turn") || 1) - 1));
  } catch (error) {
    $("#viewer").innerHTML = `<div class="error-state"><strong>Corpus unavailable</strong><pre>${escapeHtml(error.stack || error)}</pre></div>`;
  }
}

boot();
