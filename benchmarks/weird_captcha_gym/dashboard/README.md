# CAPTCHA Bench Dashboard

The dashboard is the visual control plane for Weird CAPTCHA Gym. It presents 75 evidence-backed built environment folders with screenshots, solution reels, task contracts, human reviews, local launches, VNC sessions, and evaluation controls tied to the same environment identities.

The shared dashboard is zero-setup for ordinary exploration. Every built puzzle opens as a static browser app; its existing Python grader runs in a dedicated Pyodide/WebAssembly worker. No repository checkout, terminal command, pairing key, localhost helper, or VNC is required. The optional authenticated companion on `127.0.0.1` remains responsible for persistent review writes, fresh authoritative generation, VNC guests, evaluations, paths, and process control.

The mined Survey corpus is deliberately excluded from this product and from static exports.

## Star and share a shortlist

Use the star on any environment card or dossier to keep a personal shortlist. Stars are stored only in that browser's `localStorage`; they do not alter the review ledger or require a companion. The **Starred only** control composes with search, collection, stage, and review filters.

From the Environment collection, **Share stars** creates a public dashboard URL containing only the selected environment IDs. A collaborator opening it sees exactly that shortlist and can either save those entries into their own browser stars or leave the shared view and browse the full catalog. Opening a shared link never overwrites existing personal stars, and the URL carries no review notes, credentials, filesystem paths, or process state.

The local dashboard deliberately generates links against the canonical GitHub Pages site. A static deployment generates links against its own host and path, so the feature remains portable to mirrors.

## Run the complete dashboard locally

From the repository root:

```bash
python run.py
```

The launcher opens <http://127.0.0.1:8767>. The server binds to localhost by default, and local mode requires no endpoint or pairing key.

`avf` is the normal runner on Apple Silicon. `qemu`, `qemu_native`, `docker`, and `local` remain available when the corresponding Gym-Anything runner is configured.

## Build the shared static dashboard

```bash
python benchmarks/weird_captcha_gym/dashboard/export_static.py \
  --output dist/captcha-bench-dashboard
```

The export contains:

- the full 75-environment catalog;
- the seven-capability working annotation for every environment;
- every catalog screenshot and all 75 solution reels;
- Observatory, Environments, Review queue, Live sessions, and Evaluations;
- four deterministic generated challenges for each of the 75 built environments;
- the shared puzzle runtime, Matter.js mechanics, and the exact Python graders executed by pinned Pyodide;
- a shared-mode configuration pointing at `http://127.0.0.1:8767`;
- no Survey APIs, records, artifacts, or navigation.

The resulting directory is ordinary static HTML/CSS/JavaScript and can be served by any HTTPS-capable static host. For a local deployment rehearsal:

```bash
python -m http.server 8080 --directory dist/captcha-bench-dashboard
```

The repository's GitHub Pages workflow publishes this export as the standalone project site at:

<https://gym-anything.github.io/weird-cua-bench/>

It deploys automatically after changes reach `main`. All frontend and media URLs are relative, so the same artifact remains portable to another static host.

## Play directly in the hosted dashboard

Choose any built environment and click **Try in browser**. A new tab loads the same interaction UI used by the local task server. `/state` and `/result` are fulfilled by a browser adapter; the first submission initializes the pinned Python/WebAssembly runtime, and a failed submission rotates to another real bundled challenge.

This is an exploration surface, not an authoritative evaluation endpoint. A fully static app must ship its challenge truth to the browser, so a user or agent with developer-tools/network access can inspect it. Screenshot-and-input behavior remains faithful, but secure/fresh agent evaluation still belongs on the local or VNC path.

## Connect optional advanced controls

No connection is needed for browser play. To enable persistent review changes, fresh server-backed tasks, VNC, evaluation execution, and administration, the simplest path is the local launcher above: `python run.py` opens the same dashboard locally with no pairing at all.

If a collaborator wants to keep using the public GitHub Pages dashboard, they run:

```bash
python run.py --hosted
```

This starts the loopback companion and opens a newly paired public-dashboard tab. The secret is carried in the URL fragment, which is not sent to GitHub, and the frontend removes it from the address bar immediately. Copying a pairing key is only a manual recovery path.

For another static host, use the explicit advanced command:

```bash
python benchmarks/weird_captcha_gym/dashboard/server.py \
  --companion \
  --allow-origin https://your-dashboard.example \
  --dashboard-url https://your-dashboard.example/path/ \
  --open
```

For the local rehearsal above, use `--allow-origin http://127.0.0.1:8080` and its matching `--dashboard-url`.

For the GitHub Pages deployment, use `--allow-origin https://gym-anything.github.io` (the browser `Origin` excludes `/weird-cua-bench/`).

The companion still prints its persistent pairing key for recovery. If automatic pairing is blocked, expand **Manual recovery only** in the local-execution dialog and paste it once. It is stored only in that browser's local storage and sent only to the loopback companion.

Chrome may ask whether the shared dashboard may connect to devices on the local network only after the collaborator explicitly enables the `127.0.0.1` companion. Browser play never probes loopback and must not trigger this permission. The shared deployment itself uses HTTPS; the companion intentionally remains HTTP and never leaves the collaborator's machine.

Companion mode has three safety boundaries:

- it refuses to bind to a non-loopback address;
- it accepts cross-origin requests only from exact origins passed with `--allow-origin`;
- every API except the non-sensitive health probe requires the pairing key.

The server keeps legacy Private Network Access preflight compatibility in addition to current Local Network Access behavior. No VNC password, filesystem path, review, or process control is published by the static host; those details arrive from the paired local machine and remain visible to the collaborator as requested.

## Launch modes

Every built environment supports three launch paths from the same dashboard:

- **Static browser play** — the default one-click path. A pre-generated task, the shared puzzle UI, and the exact Python grader run in the tab with no backend. It is faithful exploration, not secret evaluation.
- **Authoritative local browser** — the companion runs fresh seeded task setup, starts the shared puzzle UI and server grader on an ephemeral localhost port, and opens a normal browser tab. No VM is involved.
- **Isolated VNC guest** — the existing Gym-Anything path. The companion starts the selected runner, waits for `SessionInfo`, exposes the real VNC address/password, and can open TigerVNC.

The Live sessions page manages both kinds together. It keeps the existing two-active-session limit, prevents duplicate launches of one environment, exposes logs and local paths, supports reconnect/open, and terminates the owned process group on stop or companion shutdown.

## Product surfaces

- **Observatory** — screenshot-first overview of the interaction-first benchmark principles, all six packs, and the seven-capability distribution.
- **Environments** — searchable and filterable collection of all 75 built candidates, including primary-capability filters and two complete replacements whose rejected-pilot history remains documented.
- **Review queue** — pending, looks-good, approved, and revision-requested lanes with notes and decision history.
- **Environment dossier** — evidence filmstrip, solution reel when available, task instruction, working primary and supporting capability annotations, verifier state, launch controls, and review desk.
- **Live sessions** — local-browser and VNC process lifecycle, addresses, passwords, logs, reconnect, and teardown.
- **Evaluations** — safe command previews by default, with explicit opt-in to execute the existing `gym_anything.cli benchmark` path locally.

Review decisions default to the historical research ledger when it exists, preserving the current project's decisions. In a clean collaborator checkout they live at `~/.captcha-bench/environment-reviews.json`. Set `CAPTCHA_BENCH_REVIEW_PATH` or pass `--review-path` to relocate the ledger.

## Verification

Run the backend, export, security, catalog, and browser-launch tests:

```bash
python -m pytest tests/test_weird_captcha_dashboard.py -q
```

Run the dashboard browser smoke:

```bash
python benchmarks/weird_captcha_gym/tools/smoke_dashboard_ui.py \
  --base-url http://127.0.0.1:8767 \
  --exercise-reviews
```

Exercise all 75 static browser apps plus a real failure/fresh-challenge/WebAssembly-pass cycle:

```bash
python benchmarks/weird_captcha_gym/tools/smoke_static_browser_play.py
```

Exercise the complete shared-site boundary—including static export, browser pairing, localhost companion, a real Domino browser task, and teardown:

```bash
python benchmarks/weird_captcha_gym/tools/smoke_dashboard_shared.py
```

With a configured runner, the opt-in VNC smoke still exercises the real guest protocol and teardown path:

```bash
python benchmarks/weird_captcha_gym/tools/smoke_dashboard_live_vnc.py \
  --base-url http://127.0.0.1:8767
```

## Architecture

```text
75 built folders + task.json + evidence media ──► catalog.py ──► static export
            │                                          │             ├─► browser challenge pools
            │                                          │             └─► UI + Python graders / WASM
            │                                          └─► shared dashboard host ─► zero-setup play
            │
            ├─► setup_task.py ─► local puzzle server ◄──── optional paired companion
            │            authoritative browser tab                    │
            │                                                         ▼
            ├─► session_worker.py ─► Gym-Anything / VNC      reviews / paths / controls
            │
            └─► benchmark CLI ─► local evaluation process

local environment-reviews.json ─► reviews.py ─► review queue + dossier desk
```

The backend uses the Python standard library. The frontend remains dependency-free HTML, CSS, and JavaScript, so both the local dashboard and its static export boot without a package install or frontend build step.

See [`RESEARCH.md`](RESEARCH.md) for the visual product research behind the interface and [`docs/interaction-puzzle-field-notes.md`](../docs/interaction-puzzle-field-notes.md) for the binding interaction-quality doctrine.
