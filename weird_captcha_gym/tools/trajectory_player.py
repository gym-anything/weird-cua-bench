#!/usr/bin/env python3
"""Trajectory player for Gym-Anything style run artifacts.

Serves runs laid out as <runs-root>/<exp>/<model...>/<task>/run_N containing
observation_<step>.png plus parsed_responses.json (Qwen agents) or
trajectory.json (Gemini computer-use agent). Playback UI: screenshot on top,
reasoning/actions below, play/pause, seek slider, 1x/2x/4x speed.

    python -m weird_captcha_gym.tools.trajectory_player \
        --runs-root all_runs --host 0.0.0.0 --port 8891
"""
import argparse
import difflib
import json
import re
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file

app = Flask(__name__)
RUNS_ROOT = Path("all_runs")
# Only the corrected-code campaigns are shown by default: the Aug-2026
# Qwen3.5 sweep and the Gemini 3.6 sample. Earlier experiments (July
# "exp", the wrong-path weird_collect_v0, one-off probes) are excluded;
# pass --experiments to override.
EXPERIMENTS = ("weird_full_v1", "gemini36_d1_sample30")


_INSTRUCTION_INDEX = None
_VARIANT_INDEX = None
_RUNS_CACHE = None
_IDENT_CACHE = {}


def _variant_index():
    """instruction -> {(env, difficulty)} taken from controls.json, which is the
    source the guest actually renders (task.json wording is the baseline text and
    mislabels difficulty ~1 time in 3; measured 85/85 correct from controls)."""
    global _VARIANT_INDEX
    if _VARIANT_INDEX is not None:
        return _VARIANT_INDEX
    import collections
    rows = collections.defaultdict(set)
    bench = Path(__file__).resolve().parents[1] / "environments"
    for ctrl in bench.glob("*_env/controls.json"):
        env = ctrl.parent.name[:-4]
        try:
            cc = json.loads(ctrl.read_text())
        except Exception:
            continue
        for lvl, row in (cc.get("difficulty") or {}).items():
            nl = (row.get("natural_language") or "").strip()[:70]
            if nl:
                try:
                    rows[nl].add((env, int(lvl)))
                except (TypeError, ValueError):
                    pass
    _VARIANT_INDEX = dict(rows)
    return _VARIANT_INDEX


def _variant_label(env, inst):
    """Append the difficulty when the instruction pins it unambiguously."""
    hits = {h for h in _variant_index().get(inst[:70], set()) if h[0] == env}
    if len(hits) == 1:
        return f"{env}_d{next(iter(hits))[1]}"
    return env


def _instruction_index():
    """Map every instruction string the corpus can present -> environment name."""
    global _INSTRUCTION_INDEX
    if _INSTRUCTION_INDEX is not None:
        return _INSTRUCTION_INDEX
    idx = {}
    bench = Path(__file__).resolve().parents[1] / "environments"
    for envdir in sorted(bench.glob("*_env")):
        env = envdir.name[:-4]
        ctrl = envdir / "controls.json"
        if ctrl.exists():
            try:
                cc = json.loads(ctrl.read_text())
            except Exception:
                cc = {}
            for lvl in (cc.get("difficulty") or {}).values():
                for key in ("natural_language", "summary"):
                    v = (lvl.get(key) or "").strip()
                    if v:
                        idx.setdefault(v[:70], env)
        for tj in envdir.glob("tasks/*/task.json"):
            try:
                d = json.loads(tj.read_text())
            except Exception:
                continue
            for v in ((d.get("metadata") or {}).get("natural_language"), d.get("description")):
                if v:
                    idx.setdefault(v.strip()[:70], env)
    _INSTRUCTION_INDEX = idx
    return idx


_VOCAB = None


def _toks(text):
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower())}


def _env_vocab():
    """Per-env instruction vocabulary + document frequency."""
    global _VOCAB
    if _VOCAB is None:
        import collections
        env_tokens = collections.defaultdict(set)
        for k, env in _instruction_index().items():
            env_tokens[env] |= _toks(k)
        df = collections.Counter()
        for ts in env_tokens.values():
            for t in ts:
                df[t] += 1
        _VOCAB = (dict(env_tokens), df)
    return _VOCAB


def _identify(run_dir: Path):
    key = str(run_dir)
    if key in _IDENT_CACHE:
        return _IDENT_CACHE[key]
    out = _identify_uncached(run_dir)
    _IDENT_CACHE[key] = out
    return out


def _identify_uncached(run_dir: Path):
    """Recover (environment, instruction) for runs whose path carries no task
    identity -- the early campaign wrote every episode to exp/<model>/task/run_N."""
    f = run_dir / "messages_step_0.json"
    if not f.exists():
        return None, ""
    try:
        msgs = json.loads(f.read_text())
    except Exception:
        return None, ""
    inst = ""
    for m in msgs:
        c = m.get("content")
        text = (" ".join(b.get("text", "") for b in c if isinstance(b, dict))
                if isinstance(c, list) else (c if isinstance(c, str) else ""))
        if "Instruction:" in text:
            inst = text.split("Instruction:")[1].split("\n")[0].strip()
            break
    if not inst:
        return None, ""
    idx = _instruction_index()
    key = inst[:70]
    if key in idx:
        return idx[key], inst
    near = difflib.get_close_matches(key, list(idx), n=1, cutoff=0.55)
    if near:
        return idx[near[0]], inst
    # sequence matching is brittle on truncated prompts; fall back to content
    # words, which identify an env reliably ("gear train", "clutch", ...)
    # Rare words carry the env ("clutch", "cascade", "echo"); score each
    # environment by inverse document frequency over its instruction vocabulary.
    env_tokens, df = _env_vocab()
    want = _toks(inst)
    if want and env_tokens:
        ranked = sorted(((sum(1.0 / df[t] for t in want & ts), env)
                         for env, ts in env_tokens.items()), reverse=True)
        if ranked and ranked[0][0] >= 1.2 and ranked[0][0] >= 1.5 * (ranked[1][0] if len(ranked) > 1 else 0):
            return ranked[0][1], inst
    return None, inst


# Verdicts live in three places depending on the driver: info.json (batch CLI),
# info.pkl (agents that pickle), and the evaluation summaries written by
# weird-cua-evaluate. Read whichever exists.
_SUMMARY_DIRS = (
    Path("/compute/babel-p9-16/pranjala/weird_cua_bench/evaluations/qwen35_9b_full1500_temp1_v1/summaries"),
    Path("/compute/babel-p9-16/pranjala/weird_cua_bench/evaluations/gemini36_flash_d1_sample30/summaries"),
)


def _verdict(run_dir: Path, rel: Path):
    f = run_dir / "info.json"
    if f.exists():
        try:
            v = (json.loads(f.read_text()).get("verifier") or {})
            return v.get("passed"), (v.get("feedback") or "")[:120]
        except Exception:
            pass
    f = run_dir / "info.pkl"
    if f.exists():
        try:
            import pickle
            v = (pickle.loads(f.read_bytes()).get("verifier") or {})
            return v.get("passed"), (v.get("feedback") or "")[:120]
        except Exception:
            pass
    task = rel.parts[-2] if len(rel.parts) >= 2 else ""
    for sd in _SUMMARY_DIRS:
        cand = sd / f"{task}.json"
        if cand.exists():
            try:
                v = ((json.loads(cand.read_text()).get("info") or {}).get("verifier") or {})
                return v.get("passed"), (v.get("feedback") or "")[:120]
            except Exception:
                pass
    return None, ""


def _discover():
    """Every run dir: has observation_*.png, or only the agent's weird_input_*."""
    runs = []
    seen = set()
    for pat in ("**/observation_0.png", "**/weird_input_0.png"):
        for frame in RUNS_ROOT.glob(pat):
            run_dir = frame.parent
            if run_dir in seen:
                continue
            seen.add(run_dir)
            rel = run_dir.relative_to(RUNS_ROOT)
            parts = rel.parts  # exp / model... / task / run_N
            if EXPERIMENTS and (not parts or parts[0] not in EXPERIMENTS):
                continue
            n_steps = sum(1 for f in run_dir.glob("observation_*.png")
                          if re.match(r"observation_\d+\.png$", f.name))
            if not n_steps:
                n_steps = sum(1 for f in run_dir.glob("weird_input_*.png")
                              if re.match(r"weird_input_\d+\.png$", f.name))
            task = parts[-2] if len(parts) >= 2 else "?"
            inferred = ""
            if task in ("task", "?"):        # identity not in the path: recover it
                env, inst = _identify(run_dir)
                if env:
                    task = _variant_label(env, inst)
                    inferred = inst[:80]
                else:
                    task = "unidentified"
            verdict, feedback = _verdict(run_dir, rel)
            m = re.match(r"(.+?)_d(\d)_(simplified|full)_(live|paused)$", task)
            mech, diff, inter, tmode = (m.group(1), "d" + m.group(2), m.group(3),
                                        m.group(4)) if m else (task, "", "", "")
            runs.append({
                "mech": mech, "diff": diff, "inter": inter, "tmode": tmode,
                "verdict": verdict,
                "feedback": feedback,
                "path": str(rel),
                "exp": parts[0] if parts else "?",
                "task": task,
                "inferred": inferred,
                "run": parts[-1] if parts else "?",
                "model": "/".join(parts[1:-2]) if len(parts) > 3 else "",
                "steps": n_steps,
            })
    def natural(r):
        m = re.search(r"(\d+)$", r["run"])
        return (r["exp"], r["task"], int(m.group(1)) if m else 0)
    runs.sort(key=natural)
    return runs


def _safe_run_dir(rel: str) -> Path:
    p = (RUNS_ROOT / rel).resolve()
    if not str(p).startswith(str(RUNS_ROOT.resolve())):
        abort(403)
    if not p.is_dir():
        abort(404)
    return p


def _load_steps(run_dir: Path):
    """Merge screenshots with per-step reasoning/actions from either format."""
    obs = {}
    for f in run_dir.glob("observation_*.png"):
        m = re.match(r"observation_(\d+)\.png$", f.name)
        if m:
            obs[int(m.group(1))] = f.name
    if not obs:  # fall back to the agent's processed frames (same step indices)
        for f in run_dir.glob("weird_input_*.png"):
            m = re.match(r"weird_input_(\d+)\.png$", f.name)
            if m:
                obs[int(m.group(1))] = f.name
    meta = {}
    pr_file = run_dir / "parsed_responses.json"
    tj_file = run_dir / "trajectory.json"
    if pr_file.exists():
        try:
            parsed = json.load(open(pr_file))
        except Exception:
            parsed = []
        raw = []
        rj = run_dir / "responses.json"
        if rj.exists():
            try:
                raw = json.load(open(rj))
            except Exception:
                raw = []
        def raw_at(i):
            # responses.json is a list in some runs, a step-keyed dict in others
            if isinstance(raw, list):
                return raw[i] if i < len(raw) and isinstance(raw[i], str) else ""
            if isinstance(raw, dict):
                v = raw.get(str(i), raw.get(i, ""))
                return v if isinstance(v, str) else ""
            return ""

        for i, entry in enumerate(parsed):
            if not isinstance(entry, dict):
                continue
            md = entry.get("metadata") or {}
            meta[i] = {
                "reasoning": raw_at(i) or md.get("thought") or "",
                "conclusion": md.get("conclusion", ""),
                "actions": entry.get("actions") or [],
                "action_type": md.get("action_type", ""),
            }
    elif tj_file.exists():
        try:
            tj = json.load(open(tj_file))
            # key is "steps" in current agent builds, "transcript" in older ones
            transcript = tj.get("steps") or tj.get("transcript") or []
        except Exception:
            transcript = []
        for t in transcript:
            meta[t.get("step", -1)] = {
                "reasoning": t.get("reasoning", ""),
                "conclusion": (t.get("intent") or "") +
                              f"  [{t.get('action', '')} {json.dumps(t.get('args', {}))}]",
                "actions": t.get("env_actions") or [],
                "action_type": t.get("action", ""),
            }
    steps = []
    for i in sorted(obs):
        d = meta.get(i, {})
        steps.append({
            "step": i,
            "image": obs[i],
            "reasoning": d.get("reasoning", ""),
            "conclusion": d.get("conclusion", ""),
            "actions": d.get("actions", []),
            "action_type": d.get("action_type", ""),
            # Incomplete runs never wrote end-of-episode files; the reply to
            # step i sits in messages_step_{i+1}.json and is fetched lazily.
            "lazy": not meta and (run_dir / f"messages_step_{i}.json").exists(),
        })
    return steps


@app.route("/api/runs")
def api_runs():
    global _RUNS_CACHE
    if _RUNS_CACHE is None or request.args.get("refresh"):
        _RUNS_CACHE = _discover()
    return jsonify(_RUNS_CACHE)


@app.route("/api/run")
def api_run():
    run_dir = _safe_run_dir(request.args.get("path", ""))
    info = {}
    for cand in (run_dir / "info.json",):
        if cand.exists():
            try:
                info = json.load(open(cand))
            except Exception:
                pass
    return jsonify({"steps": _load_steps(run_dir), "info": info})


@app.route("/api/step")
def api_step():
    run_dir = _safe_run_dir(request.args.get("path", ""))
    i = int(request.args.get("i", 0))
    for cand in (run_dir / f"messages_step_{i + 1}.json",
                 run_dir / f"messages_step_{i}.json"):
        if not cand.exists():
            continue
        try:
            msgs = json.load(open(cand))
        except Exception:
            continue
        for m in reversed(msgs):
            if m.get("role") != "assistant":
                continue
            c = m.get("content")
            if isinstance(c, list):
                text = "\n".join(b.get("text", "") for b in c
                                  if isinstance(b, dict) and b.get("type") == "text")
            else:
                text = c if isinstance(c, str) else ""
            m2 = re.search(r"<tool_call>(.*?)</tool_call>", text, re.S)
            return jsonify({"reasoning": text.strip(),
                            "actions_text": m2.group(1).strip() if m2 else ""})
    return jsonify({"reasoning": "", "actions_text": ""})


@app.route("/img/<path:rel>")
def img(rel):
    p = (RUNS_ROOT / rel).resolve()
    if not str(p).startswith(str(RUNS_ROOT.resolve())) or not p.is_file():
        abort(404)
    return send_file(p)


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Trajectory Player</title><style>
* { box-sizing: border-box; margin: 0; }
body { font-family: 'Segoe UI', sans-serif; background: #14181c; color: #e8eaed;
       display: flex; height: 100vh; }
#side { width: 340px; overflow-y: auto; background: #1c2127; padding: 12px;
        border-right: 1px solid #2d333b; flex-shrink: 0; }
#side h2 { font-size: 15px; margin: 8px 0; color: #9aa4af; }
#count { color: #6b7580; font-weight: 400; font-size: 12.5px; }
.filters { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-bottom: 8px; }
.filters select { width: 100%; background: #14181c; color: #e8eaed; border: 1px solid #2d333b;
                  border-radius: 6px; padding: 6px; font-size: 12.5px; }
#stats { font-size: 12px; color: #7ca8a1; margin: 0 0 8px 2px; min-height: 15px; }
#side input { width: 100%; padding: 7px; margin-bottom: 8px; background: #14181c;
              border: 1px solid #2d333b; color: #e8eaed; border-radius: 6px; }
.run { padding: 7px 9px; border-radius: 6px; cursor: pointer; font-size: 13px;
       line-height: 1.35; margin-bottom: 2px; }
.run:hover { background: #262c33; }
.run.active { background: #0f4c46; }
.run .t { font-weight: 600; }
.run .m { color: #9aa4af; font-size: 11.5px; }
.q { color: #7ca8a1; font-size: 11px; font-style: italic; margin-top: 2px;
     overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pass { color: #3ca951; font-size: 10.5px; font-weight: 700; }
.fail { color: #d0021b; font-size: 10.5px; font-weight: 700; }
.inf { color: #d8b45a; font-size: 10px; font-weight: 400; letter-spacing: .04em; }
#main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
#screen { flex: 1; display: flex; align-items: center; justify-content: center;
          background: #000; min-height: 0; }
#screen img { max-width: 100%; max-height: 100%; object-fit: contain; }
#controls { padding: 10px 18px; background: #1c2127; border-top: 1px solid #2d333b;
            display: flex; align-items: center; gap: 14px; }
button { background: #0f766e; color: #fff; border: 0; padding: 8px 18px;
         border-radius: 6px; font-size: 15px; cursor: pointer; }
button.sec { background: #2d333b; }
#slider { flex: 1; }
#stepno { font-variant-numeric: tabular-nums; font-size: 15px; min-width: 90px; }
select { background: #2d333b; color: #fff; border: 0; padding: 7px; border-radius: 6px; }
#detail { height: 240px; overflow-y: auto; padding: 14px 18px; background: #171b20;
          border-top: 1px solid #2d333b; font-size: 14px; }
#detail h3 { font-size: 12.5px; color: #7ca8a1; text-transform: uppercase;
             letter-spacing: .06em; margin: 10px 0 4px; }
#reason { white-space: pre-wrap; line-height: 1.45; }
#acts { font-family: 'JetBrains Mono', monospace; font-size: 12.5px;
        white-space: pre-wrap; color: #d8b45a; }
#title { padding: 10px 18px; background: #1c2127; font-size: 15px; font-weight: 600;
         border-bottom: 1px solid #2d333b; }
#title .sub { color: #9aa4af; font-weight: 400; font-size: 13px; }
</style></head><body>
<div id="side">
  <h2>Runs <span id="count"></span></h2>
  <input id="filter" placeholder="search: terms AND-ed, -word excludes">
  <div class="filters">
    <select id="f_model"><option value="">any model</option></select>
    <select id="f_verdict"><option value="">any result</option><option value="pass">PASS only</option><option value="fail">FAIL only</option></select>
    <select id="f_mech"><option value="">any env</option></select>
    <select id="f_diff"><option value="">any level</option></select>
    <select id="f_inter"><option value="">any interaction</option><option value="simplified">simplified</option><option value="full">full</option></select>
    <select id="f_tmode"><option value="">any clock</option><option value="live">live</option><option value="paused">paused</option></select>
    <select id="f_sort"><option value="task">sort: task</option><option value="steps_desc">sort: most steps</option><option value="steps_asc">sort: fewest steps</option><option value="verdict">sort: passes first</option></select>
  </div>
  <div id="stats"></div>
  <div id="runs"></div>
</div>
<div id="main">
  <div id="title">select a run <span class="sub"></span></div>
  <div id="screen"><img id="frame" alt=""></div>
  <div id="controls">
    <button id="play">&#9654;</button>
    <button class="sec" id="prev">&#9664;&#9664;</button>
    <button class="sec" id="next">&#9654;&#9654;</button>
    <input type="range" id="slider" min="0" max="0" value="0">
    <span id="stepno">– / –</span>
    <select id="speed"><option value="1">1x</option><option value="2">2x</option>
      <option value="4">4x</option></select>
  </div>
  <div id="detail">
    <h3>Model output</h3><div id="reason">–</div>
    <h3>Actions</h3><div id="acts">–</div>
  </div>
</div>
<script>
let runs = [], steps = [], cur = 0, playing = null, curPath = null, loadedPath = null;
const NOTE = 'no model output recorded — the episode ended before the model replied';
const $ = id => document.getElementById(id);
fetch('/api/runs').then(r => r.json()).then(d => {
  runs = d;
  const fill = (id, vals) => {
    const el = $(id);
    [...new Set(vals)].filter(Boolean).sort().forEach(v => {
      const o = document.createElement('option'); o.value = v; o.textContent = v; el.appendChild(o);
    });
  };
  fill('f_model', runs.map(r => r.model));
  fill('f_mech', runs.map(r => r.mech));
  fill('f_diff', runs.map(r => r.diff));
  ['model','verdict','mech','diff','inter','tmode','sort'].forEach(k => {
    $('f_' + k).onchange = e => { F[k] = e.target.value; renderRuns(); };
  });
  renderRuns();
});
function matches(r) {
  if (F.model && r.model !== F.model) return false;
  if (F.verdict === 'pass' && r.verdict !== true) return false;
  if (F.verdict === 'fail' && r.verdict !== false) return false;
  if (F.mech && r.mech !== F.mech) return false;
  if (F.diff && r.diff !== F.diff) return false;
  if (F.inter && r.inter !== F.inter) return false;
  if (F.tmode && r.tmode !== F.tmode) return false;
  const hay = (r.path + ' ' + r.exp + ' ' + r.task + ' ' + r.run + ' ' + r.model + ' ' +
    (r.verdict === true ? 'pass' : r.verdict === false ? 'fail' : '') + ' ' +
    (r.feedback || '') + ' ' + (r.inferred || '')).toLowerCase();
  // every term must match; a leading '-' excludes
  for (const term of $('filter').value.toLowerCase().split(/\s+/).filter(Boolean)) {
    if (term.startsWith('-')) { if (term.length > 1 && hay.includes(term.slice(1))) return false; }
    else if (!hay.includes(term)) return false;
  }
  return true;
}
const F = {model: '', verdict: '', mech: '', diff: '', inter: '', tmode: '', sort: 'task'};
function sortRuns(list) {
  const s = F.sort;
  if (s === 'steps_desc') return list.sort((a, b) => b.steps - a.steps);
  if (s === 'steps_asc') return list.sort((a, b) => a.steps - b.steps);
  if (s === 'verdict') return list.sort((a, b) => (b.verdict === true) - (a.verdict === true) ||
                                                  a.task.localeCompare(b.task));
  return list.sort((a, b) => a.task.localeCompare(b.task) || a.run.localeCompare(b.run));
}
function renderRuns() {
  const shown = sortRuns(runs.filter(matches));
  const passed = shown.filter(r => r.verdict === true).length;
  const scored = shown.filter(r => r.verdict !== null && r.verdict !== undefined).length;
  $('count').textContent = `(${shown.length} of ${runs.length})`;
  $('stats').textContent = scored
      ? `${passed} passed / ${scored} scored — ${(100 * passed / scored).toFixed(1)}%` : '';
  $('runs').innerHTML = shown
    .map(r => `<div class="run ${r.path===curPath?'active':''}" onclick="loadRun('${r.path}')">` +
        `<div class="t">${r.verdict === true ? '<span class="pass">PASS</span> ' :
                          r.verdict === false ? '<span class="fail">FAIL</span> ' : ''}` +
        `${r.task} / ${r.run}${r.inferred ? ' <span class="inf">inferred</span>' : ''}</div>` +
        `<div class="m">${r.exp}${r.model ? ' · ' + r.model : ''} · ${r.steps} steps</div>` +
        (r.inferred ? `<div class="q">“${r.inferred}”</div>` : '') + `</div>`).join('');
}
$('filter').oninput = renderRuns;
function loadRun(path) {
  curPath = path; stop();
  steps = []; loadedPath = null;
  $('title').innerHTML = path + '<span class="sub"> — loading…</span>';
  $('stepno').textContent = '… / …';
  fetch('/api/run?path=' + encodeURIComponent(path)).then(r => r.json()).then(d => {
    if (curPath !== path) return;            // a newer run was clicked meanwhile
    steps = d.steps; cur = 0;
    $('slider').max = Math.max(0, steps.length - 1);
    const meta0 = (runs.find(r => r.path === path) || {});
    const v = (d.info && d.info.verifier) || {};
    const passed = v.passed !== undefined ? v.passed : meta0.verdict;
    const verdict = passed === true ? ' — PASSED' : (passed === false ? ' — failed' : '');
    if (!v.feedback && meta0.feedback) v.feedback = meta0.feedback;
    const meta = (runs.find(r => r.path === path) || {});
    $('title').innerHTML = (meta.task && meta.inferred ? meta.task + ' <span class="inf">inferred</span> — ' : '')
      + path + `<span class="sub">${verdict}` + (v.feedback ? ' · ' + v.feedback : '')
      + (meta.inferred ? ' · “' + meta.inferred + '”' : '') + '</span>';
    loadedPath = path;
    show(0); renderRuns();
  });
}
function show(i) {
  if (!steps.length) return;
  cur = Math.max(0, Math.min(i, steps.length - 1));
  const s = steps[cur];
  $('frame').src = '/img/' + curPath + '/' + s.image;
  $('slider').value = cur;
  $('stepno').textContent = (cur + 1) + ' / ' + steps.length;
  const bare = !s.reasoning && !s.conclusion && !(s.actions && s.actions.length)
               && s.actionsText === undefined && !s.lazy;
  $('reason').textContent = bare ? NOTE : (s.reasoning || s.conclusion || '–');
  $('acts').textContent = bare ? '–'
      : (s.actionsText !== undefined ? s.actionsText
         : (s.action_type ? s.action_type + '\\n' : '') + JSON.stringify(s.actions, null, 1));
  if (s.lazy && !s.loaded) {
    s.loaded = true;
    fetch('/api/step?path=' + encodeURIComponent(curPath) + '&i=' + s.step)
      .then(r => r.json()).then(d => {
        const empty = !d.reasoning && !d.actions_text;
        s.reasoning = empty ? NOTE : d.reasoning;
        s.actionsText = empty ? '–' : (d.actions_text || '–');
        if (steps[cur] === s) {
          document.getElementById('reason').textContent = s.reasoning;
          document.getElementById('acts').textContent = s.actionsText;
        }
      });
  }
}
function tick() { if (cur >= steps.length - 1) { stop(); return; } show(cur + 1); }
function start() {
  if (!steps.length) return;
  if (cur >= steps.length - 1) show(0);   // replay from the top instead of idling
  const ms = 1000 / Number($('speed').value);
  playing = setInterval(tick, ms); $('play').innerHTML = '&#10074;&#10074;';
}
function stop() { clearInterval(playing); playing = null; $('play').innerHTML = '&#9654;'; }
$('play').onclick = () => playing ? stop() : start();
$('speed').onchange = () => { if (playing) { stop(); start(); } };
$('prev').onclick = () => { stop(); show(cur - 1); };
$('next').onclick = () => { stop(); show(cur + 1); };
$('slider').oninput = e => { stop(); show(Number(e.target.value)); };
document.addEventListener('keydown', e => {
  if (e.key === 'ArrowRight') { stop(); show(cur + 1); }
  if (e.key === 'ArrowLeft') { stop(); show(cur - 1); }
  if (e.key === ' ') { e.preventDefault(); playing ? stop() : start(); }
});
</script></body></html>"""


@app.route("/")
def index():
    return PAGE


def main():
    global RUNS_ROOT, EXPERIMENTS
    ap = argparse.ArgumentParser(description="Trajectory player")
    ap.add_argument("--runs-root", default="all_runs")
    ap.add_argument("--experiments", default=",".join(EXPERIMENTS),
                    help="comma-separated experiment dirs to show ('all' for every run)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8891)
    args = ap.parse_args()
    RUNS_ROOT = Path(args.runs_root)
    EXPERIMENTS = () if args.experiments.strip().lower() == "all" else tuple(
        e.strip() for e in args.experiments.split(",") if e.strip())
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
