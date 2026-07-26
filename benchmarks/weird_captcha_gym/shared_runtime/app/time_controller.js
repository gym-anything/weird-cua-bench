(() => {
  "use strict";

  const native = {
    dateNow: Date.now.bind(Date),
    performanceNow: performance.now.bind(performance),
    setTimeout: window.setTimeout.bind(window),
    clearTimeout: window.clearTimeout.bind(window),
    setInterval: window.setInterval.bind(window),
    clearInterval: window.clearInterval.bind(window),
    requestAnimationFrame: window.requestAnimationFrame.bind(window),
    cancelAnimationFrame: window.cancelAnimationFrame.bind(window),
    fetch: window.fetch.bind(window),
  };
  const parameters = new URLSearchParams(window.location.search);
  const initialMode = parameters.get("time_mode") === "paused" ? "paused" : "live";
  const startPaused = parameters.get("start_paused") === "1";
  const controlEnabled = parameters.get("time_control") === "1";
  const nativePerformanceOrigin = native.performanceNow();
  const nativeDateOrigin = native.dateNow();
  const clientId = `${nativeDateOrigin}-${Math.random().toString(16).slice(2)}`;

  let running = initialMode === "live" && !startPaused;
  let accumulatedMs = 0;
  let runStartedAt = running ? native.performanceNow() : null;
  let ready = false;
  let lastCommandSequence = 0;
  let commandPhase = running ? "running" : "paused";
  let windowStartedWallMs = null;
  let windowCompletedWallMs = null;
  let runWindowToken = 0;
  let nextTimerId = 1;
  let nextAnimationFrameId = 1;

  const timers = new Map();
  const animationFrames = new Map();
  const controllerPausedAnimations = new Set();
  const audioContexts = new Set();
  const controllerPausedAudioContexts = new Set();

  function elapsedMs() {
    return accumulatedMs + (running && runStartedAt != null ? native.performanceNow() - runStartedAt : 0);
  }

  function virtualPerformanceNow() {
    return nativePerformanceOrigin + elapsedMs();
  }

  function virtualDateNow() {
    return Math.round(nativeDateOrigin + elapsedMs());
  }

  function pauseDocumentAnimations(root = document) {
    if (typeof root.getAnimations !== "function") return;
    for (const animation of root.getAnimations({subtree: true})) {
      if (animation.playState !== "running" && animation.playState !== "pending") continue;
      try {
        animation.pause();
        controllerPausedAnimations.add(animation);
      } catch (_error) {
        // A detached animation can disappear between enumeration and pause.
      }
    }
    if (root === document) {
      for (const child of window.WeirdCaptchaTime?.childWindows || []) {
        if (!child.closed) pauseDocumentAnimations(child.document);
      }
    }
  }

  function resumeDocumentAnimations() {
    for (const animation of controllerPausedAnimations) {
      try {
        animation.play();
      } catch (_error) {
        // Detached animations need no further work.
      }
    }
    controllerPausedAnimations.clear();
  }

  function pauseAudio() {
    for (const context of audioContexts) {
      if (context.state !== "running") continue;
      controllerPausedAudioContexts.add(context);
      context.suspend().catch(() => {});
    }
  }

  function resumeAudio() {
    for (const context of controllerPausedAudioContexts) {
      if (context.state === "suspended") context.resume().catch(() => {});
    }
    controllerPausedAudioContexts.clear();
  }

  function pause() {
    if (!running) return status();
    accumulatedMs = elapsedMs();
    runStartedAt = null;
    running = false;
    commandPhase = "paused";
    pauseDocumentAnimations();
    pauseAudio();
    return status();
  }

  function resume() {
    if (running) return status();
    runStartedAt = native.performanceNow();
    running = true;
    commandPhase = "running";
    resumeDocumentAnimations();
    resumeAudio();
    return status();
  }

  function status() {
    return {
      client_id: clientId,
      mode: initialMode,
      state: running ? "running" : "paused",
      phase: commandPhase,
      ready,
      sequence: lastCommandSequence,
      task_time_ms: Math.round(elapsedMs() * 1000) / 1000,
      native_time_ms: native.performanceNow(),
      native_date_ms: native.dateNow(),
      window_started_wall_ms: windowStartedWallMs,
      window_completed_wall_ms: windowCompletedWallMs,
    };
  }

  function markReady() {
    ready = true;
    postStatus();
  }

  function normalizeCallback(callback) {
    if (typeof callback === "function") return callback;
    return () => window.eval(String(callback));
  }

  function scheduleTimer(callback, delay, interval, args) {
    const id = nextTimerId++;
    const delayMs = Math.max(0, Number(delay) || 0);
    timers.set(id, {
      callback: normalizeCallback(callback),
      args,
      dueMs: elapsedMs() + delayMs,
      intervalMs: interval ? Math.max(1, delayMs) : null,
    });
    return id;
  }

  window.setTimeout = (callback, delay = 0, ...args) => scheduleTimer(callback, delay, false, args);
  window.setInterval = (callback, delay = 0, ...args) => scheduleTimer(callback, delay, true, args);
  window.clearTimeout = (id) => timers.delete(Number(id));
  window.clearInterval = window.clearTimeout;

  window.requestAnimationFrame = (callback) => {
    const id = nextAnimationFrameId++;
    animationFrames.set(id, callback);
    return id;
  };
  window.cancelAnimationFrame = (id) => animationFrames.delete(Number(id));

  Date.now = virtualDateNow;
  try {
    Object.defineProperty(performance, "now", {configurable: true, value: virtualPerformanceNow});
  } catch (_error) {
    try {
      Object.defineProperty(Performance.prototype, "now", {configurable: true, value: virtualPerformanceNow});
    } catch (_ignored) {
      // The compatibility test fails if a browser prevents both replacements.
    }
  }

  for (const name of ["AudioContext", "webkitAudioContext"]) {
    const Constructor = window[name];
    if (typeof Constructor !== "function") continue;
    window[name] = new Proxy(Constructor, {
      construct(target, argumentsList, newTarget) {
        const context = Reflect.construct(target, argumentsList, newTarget);
        audioContexts.add(context);
        if (!running && context.state === "running") {
          controllerPausedAudioContexts.add(context);
          context.suspend().catch(() => {});
        }
        return context;
      },
    });
  }

  function drainTimers() {
    if (!running) return;
    const now = elapsedMs();
    const due = [...timers.entries()]
      .filter(([, timer]) => timer.dueMs <= now)
      .sort((left, right) => left[1].dueMs - right[1].dueMs);
    for (const [id, timer] of due) {
      if (!timers.has(id)) continue;
      if (timer.intervalMs == null) timers.delete(id);
      else timer.dueMs += timer.intervalMs * Math.max(1, Math.floor((now - timer.dueMs) / timer.intervalMs) + 1);
      try {
        timer.callback(...timer.args);
      } catch (error) {
        native.setTimeout(() => { throw error; }, 0);
      }
    }
  }

  function animationLoop() {
    if (running && animationFrames.size) {
      const callbacks = [...animationFrames.values()];
      animationFrames.clear();
      const timestamp = virtualPerformanceNow();
      for (const callback of callbacks) {
        try {
          callback(timestamp);
        } catch (error) {
          native.setTimeout(() => { throw error; }, 0);
        }
      }
    }
    native.requestAnimationFrame(animationLoop);
  }

  native.setInterval(drainTimers, 4);
  native.requestAnimationFrame(animationLoop);

  const observer = new MutationObserver(() => {
    if (!running) native.setTimeout(() => pauseDocumentAnimations(), 0);
  });
  observer.observe(document.documentElement, {childList: true, subtree: true});

  async function postStatus() {
    if (!controlEnabled) return;
    try {
      await native.fetch("/time-control/status", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify(status()),
        cache: "no-store",
      });
    } catch (_error) {
      // The next polling cycle retries after transient server startup races.
    }
  }

  function runFor(milliseconds, startDelayMs, sequence) {
    const duration = Math.max(0, Number(milliseconds) || 0);
    const startDelay = Math.max(0, Number(startDelayMs) || 0);
    const token = ++runWindowToken;
    pause();
    commandPhase = "scheduled";
    windowStartedWallMs = null;
    windowCompletedWallMs = null;
    postStatus();
    native.setTimeout(() => {
      if (token !== runWindowToken || sequence !== lastCommandSequence) return;
      resume();
      commandPhase = "running_window";
      windowStartedWallMs = native.dateNow();
      postStatus();
      native.setTimeout(() => {
        if (token !== runWindowToken || sequence !== lastCommandSequence) return;
        pause();
        commandPhase = "completed";
        windowCompletedWallMs = native.dateNow();
        postStatus();
      }, duration);
    }, startDelay);
  }

  async function applyCommand(command) {
    const sequence = Number(command.sequence) || 0;
    if (sequence <= lastCommandSequence) return;
    lastCommandSequence = sequence;
    const kind = String(command.command || "status");
    if (kind === "pause") {
      runWindowToken += 1;
      pause();
    } else if (kind === "resume") {
      runWindowToken += 1;
      resume();
    }
    else if (kind === "run_for") {
      runFor(command.milliseconds, command.start_delay_ms, sequence);
      return;
    }
    commandPhase = running ? "running" : "paused";
    await postStatus();
  }

  async function pollCommands() {
    if (!controlEnabled) return;
    try {
      const response = await native.fetch(`/time-control?after=${lastCommandSequence}`, {cache: "no-store"});
      if (response.ok) await applyCommand(await response.json());
    } catch (_error) {
      // Polling continues. The task clock is independent of server availability.
    }
  }

  const originalOpen = window.open.bind(window);
  const childWindows = new Set();
  window.open = (...args) => {
    const child = originalOpen(...args);
    if (child) childWindows.add(child);
    return child;
  };

  window.WeirdCaptchaTime = {
    pause,
    resume,
    status,
    markReady,
    childWindows,
    native,
  };

  if (!running) native.setTimeout(() => pauseDocumentAnimations(), 0);
  if (controlEnabled) {
    native.setInterval(pollCommands, 20);
    native.setInterval(postStatus, 250);
    pollCommands();
  }
})();
