# Capability annotation guidelines

The benchmark uses three controllable knobs plus four core capabilities.

## Controllable knobs

### Real time

Record whether the current environment changes while the agent waits. Distinguish an environment that needs continuous frames only for observation from one whose actions depend on live state.

### Interaction

Describe the visible action surface in ordinary terms. Examples include clicking, dragging, holding, tracing, typing, switching views, or controlling several inputs together.

### Difficulty or complexity

List the per-environment variables that can scale the task. Examples include more stages, more objects, tighter tolerances, faster motion, longer procedures, or more simultaneous variables.

## Core capabilities

### Visual understanding

Classify this as 2D or 3D. Spatial understanding is included here.

### Temporal understanding and memory

Count this when solving requires change across frames, motion, duration, hidden past state, or another nontrivial temporal relationship. A simple visible sequence does not count.

### Reasoning and planning

Count this when solving requires inferring constraints or choosing actions whose consequences matter later. Do not add a second label merely because the task also contains spatial understanding.

### Exploration and interface understanding

Count this when the agent must interact to reveal relevant information or learn how the interface behaves before it can solve the task. Ordinary feedback, a routine state transition, or reacting to a new visible state does not count.

## Review procedure

Use the exact public environment name. Read the generator, visible browser implementation, grader, verifier, and solver where present. Classify what a normal screenshot-only UI solution requires rather than what a private-state test solver can do. Record continuous observation separately when the scene must move across frames but the action itself is untimed.

## Seed examples

| Environment | Real time | Visual | Temporal | Reasoning and planning | Exploration and interface understanding |
|---|---|---|---|---|---|
| Gyroscopic Tilt Board | Yes | 2D | Yes | Yes | No |
| Cursor-Controlled Constellation Hunt | No | 2D | No | No | Yes |
| Polarized Palimpsest | Yes | 2D | Yes | No | Yes |
| Exact-Change Candy Cascade | No | 2D | No | Yes | No |
| Flat-Pack Compliance Test | No | 2D | No | Yes | No |
| The Flat Prisoner | Yes | 3D | Yes | Yes | Yes |
| Input-Lag Forklift | No | 2D | No | Yes | No |
| Insider Trading CAPTCHA | Yes | 2D | Yes | Yes | No |
| Isometric Voxel Extraction Mine | No | 3D | No | Yes | Yes |
| Motion-Only Ghost Jigsaw | Observation only | 2D | Yes | No | No |
| Rotate The Wrong Thing Upright | No | 3D | No | Yes | Yes |
| Rotating On-Screen Keyboard | Yes | 3D | No | No | No |
| Slime Commute | Yes | 2D | Yes | Yes | No |
| Specular Lighthouse Relay | Yes | 2D | Yes | Yes | No |
| Parallax Orchard | No | 3D | No | No | Yes |
