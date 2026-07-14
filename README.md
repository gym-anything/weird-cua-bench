# Weird CUA Bench

Interaction-first visual puzzles for evaluating screenshot-driven computer-use agents.

The benchmark starts from CAPTCHA-like and internet puzzle mechanics, but its target is broader: strange, human-manageable tasks whose real difficulty comes from acting over time. The current candidate corpus contains 63 built puzzle environments and two rejected infrastructure pilots retained as an honest archive.

[Explore the dashboard](https://gym-anything.github.io/weird-cua-bench/)

## Repository scope

This is the standalone home of the Weird CUA benchmark. It contains only:

- the Weird CUA environment and task folders;
- procedural generators, browser runtime, graders, and exported verifiers;
- the evidence-backed dashboard and solution media;
- benchmark-specific tests and design documentation.

It deliberately excludes CUA-World, other Gym-Anything environments, the mined Survey archive, and Gym-Anything's core source tree. Gym-Anything remains an optional runtime dependency for isolated VNC sessions and agent evaluations.

The `verified` split is intentionally empty. Scripted browser success proves wiring, not human usability or agent difficulty.

## Run the dashboard locally

The dashboard and ordinary local-browser puzzles use the Python standard library:

```bash
python run.py
```

This opens the complete dashboard at <http://127.0.0.1:8767>. There is no pairing step in local mode. To enable runner-backed VNC sessions, install the optional runtime:

```bash
python -m pip install -e ".[runtime]"
```

To keep using the hosted dashboard while execution stays on this computer:

```bash
python run.py --hosted
```

The launcher starts the authenticated loopback companion and opens an automatically paired dashboard tab. No pairing key needs to be copied. The hosted site is static: every puzzle launch, review, evaluation, filesystem path, and VNC session remains on the collaborator's own computer.

## Validate

```bash
python -m pip install -e ".[test]"
python -m pytest tests -q
```

The strict promotion audit is deliberately red while the corpus remains candidate-only:

```bash
python benchmarks/weird_captcha_gym/tools/audit_quality.py --strict
```

Its blockers are the human/VNC/agent evidence still required before anything enters the empty `verified` split; do not weaken task status merely to make this command green.

Read [`benchmarks/weird_captcha_gym/docs/interaction-puzzle-field-notes.md`](benchmarks/weird_captcha_gym/docs/interaction-puzzle-field-notes.md) before changing any puzzle. It records the binding interaction-first doctrine, human feedback, prohibited shortcuts, and current validation limits.

## License

The repository is MIT licensed. Third-party runtime notices, including Matter.js, are stored beside the vendored assets that use them.
