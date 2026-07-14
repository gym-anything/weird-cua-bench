(() => {
  "use strict";

  const nativeFetch = window.fetch.bind(window);
  const parameters = new URLSearchParams(window.location.search);
  const environmentId = String(parameters.get("environment") || "");
  const requestedAttempt = Number.parseInt(parameters.get("attempt") || "", 10);
  const validEnvironment = /^[a-z0-9_]+_env$/.test(environmentId);
  const pageBase = new URL("./", window.location.href);
  const runtimeBase = new URL("runtime/", pageBase);
  const challengeUrl = new URL(`challenges/${encodeURIComponent(environmentId)}.json`, pageBase);

  window.WEIRD_CAPTCHA_ASSET_BASE = runtimeBase.href;
  window.WEIRD_CAPTCHA_BROWSER_PLAY = true;

  let bundle = null;
  let bundleError = null;
  let challengeIndex = 0;
  let stateReadCount = 0;
  let lastResult = null;
  let worker = null;
  let messageId = 0;
  const pendingGrades = new Map();

  function jsonResponse(payload, status = 200) {
    return new Response(JSON.stringify(payload), {
      status,
      headers: {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"},
    });
  }

  function browserPlayError(message) {
    document.body.dataset.mechanic = "waiting";
    const app = document.getElementById("app");
    if (app) {
      app.innerHTML = `<section class="runtime-panel"><p>${String(message).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")}</p></section>`;
    }
  }

  const bundlePromise = (validEnvironment
    ? nativeFetch(challengeUrl, {headers: {accept: "application/json"}})
        .then((response) => {
          if (!response.ok) throw new Error(`browser challenge unavailable (${response.status})`);
          return response.json();
        })
        .then((value) => {
          if (!Array.isArray(value.challenges) || !value.challenges.length) throw new Error("browser challenge pool is empty");
          bundle = value;
          challengeIndex = Number.isInteger(requestedAttempt)
            ? Math.abs(requestedAttempt) % bundle.challenges.length
            : crypto.getRandomValues(new Uint32Array(1))[0] % bundle.challenges.length;
          document.title = `${bundle.title || "Weird CUA Bench"} · Browser Play`;
          return bundle;
        })
    : Promise.reject(new Error("A valid environment was not selected")))
    .catch((error) => {
      bundleError = error;
      browserPlayError(error.message);
      return null;
    });

  function currentChallenge() {
    if (bundleError) throw bundleError;
    if (!bundle) throw new Error("browser challenge is not ready");
    return bundle.challenges[challengeIndex];
  }

  function ensureWorker() {
    if (worker) return worker;
    worker = new Worker(new URL("grader_worker.js", runtimeBase), {type: "module"});
    worker.addEventListener("message", (event) => {
      const pending = pendingGrades.get(event.data?.id);
      if (!pending) return;
      pendingGrades.delete(event.data.id);
      clearTimeout(pending.timeout);
      if (event.data.ok) pending.resolve(event.data.grade);
      else pending.reject(new Error(event.data.error || "browser grader failed"));
    });
    worker.addEventListener("error", (event) => {
      for (const pending of pendingGrades.values()) {
        clearTimeout(pending.timeout);
        pending.reject(new Error(event.message || "browser grader worker crashed"));
      }
      pendingGrades.clear();
      worker?.terminate();
      worker = null;
    });
    return worker;
  }

  function gradeInBrowser(payload, challenge) {
    const id = ++messageId;
    const activeWorker = ensureWorker();
    return new Promise((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        if (!pendingGrades.delete(id)) return;
        worker?.terminate();
        worker = null;
        reject(new Error("browser grader initialization timed out"));
      }, 90_000);
      pendingGrades.set(id, {resolve, reject, timeout});
      activeWorker.postMessage({
        id,
        graderUrl: new URL(bundle.grader, pageBase).href,
        payload,
        groundTruth: challenge.ground_truth,
        publicState: challenge.public_state,
      });
    });
  }

  async function handleState() {
    await bundlePromise;
    if (stateReadCount > 0) challengeIndex = (challengeIndex + 1) % bundle.challenges.length;
    stateReadCount += 1;
    return jsonResponse(currentChallenge().public_state);
  }

  function failedResult(feedback, grade = null) {
    challengeIndex = (challengeIndex + 1) % bundle.challenges.length;
    if (grade) window.dispatchEvent(new CustomEvent("weird-cua-browser-grade", {detail: {passed: false, grade}}));
    return jsonResponse({
      ok: true,
      passed: false,
      feedback,
      state: currentChallenge().public_state,
    });
  }

  async function handleResult(options) {
    await bundlePromise;
    if (String(options.method || "GET").toUpperCase() !== "POST") {
      return lastResult ? jsonResponse(lastResult) : jsonResponse({error: "no result submitted"}, 404);
    }
    let payload;
    try {
      payload = JSON.parse(String(options.body || "{}"));
    } catch (_error) {
      return jsonResponse({error: "invalid JSON body"}, 400);
    }
    const challenge = currentChallenge();
    if (String(payload.mechanic_id || "") !== String(challenge.ground_truth.mechanic_id || "")) {
      return failedResult("mechanic mismatch");
    }
    if (String(payload.challenge_id || "") !== String(challenge.ground_truth.challenge_id || "")) {
      return failedResult("stale challenge");
    }
    try {
      const grade = await gradeInBrowser(payload, challenge);
      const passed = grade?.passed === true;
      lastResult = {...payload, browser_grade: grade, submitted_at: new Date().toISOString()};
      if (passed) {
        const storageKey = `weird-cua-browser-results:${environmentId}`;
        localStorage.setItem(storageKey, JSON.stringify(lastResult));
        window.dispatchEvent(new CustomEvent("weird-cua-browser-grade", {detail: {passed: true, grade}}));
        return jsonResponse({ok: true, passed: true, feedback: grade.feedback || "pass"});
      }
      return failedResult(grade?.feedback || "failed", grade);
    } catch (error) {
      console.error("Browser verifier failed", error);
      return jsonResponse({error: `browser verifier failed: ${error.message}`}, 500);
    }
  }

  window.fetch = async (input, options = {}) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, window.location.href);
    if (url.origin === window.location.origin && url.pathname === "/state") return handleState();
    if (url.origin === window.location.origin && url.pathname === "/result") return handleResult(options);
    if (url.origin === window.location.origin && url.pathname === "/cheat") return jsonResponse({error: "not found"}, 404);
    return nativeFetch(input, options);
  };

  window.WEIRD_CAPTCHA_BROWSER_READY = bundlePromise;
})();
