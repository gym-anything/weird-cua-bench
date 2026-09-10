# Codex action contract

The benchmark's Codex adapter accepts the keyboard/mouse action structures used
by `GymAnythingEnv.step`. It does not use the shared Qwen action parser.
Implementation and prompts live in this repository, not in Gym Anything.

POST to `GATEWAY_URL` with `X-Gateway-Token: GATEWAY_TOKEN` and JSON body
`{"command": "<JSON-encoded object or list>"}`. The command accepts a native
action, an action list, or `{"actions": [...]}`. Lists are delivered to one
`env.step` in order and cost one step. The only coordinate conversion maps
displayed screenshot pixels back to the native display. Every pointer field
undergoes that conversion, including both endpoints of either drag.

| Input | Native fields |
| --- | --- |
| Keyboard | `text`, `keys`, `keys_down`, `keys_up` |
| Pointer | `move`, `left_click`, `right_click`, `middle_click`, `double_click`, `triple_click` |
| Drag | `left_click_drag`, `right_click_drag`, each with two endpoints |
| Button state | `buttons` containing `left_down/up`, `right_down/up`, `middle_down/up` booleans |
| Wheel | `scroll`, signed integer wheel notches, positive down |
| Wait | `{"action":"wait","time":seconds}` (`type`/`seconds` aliases accepted) |
| Observe | `{"action":"screenshot"}` or `[]`, no action-budget cost |

For curved drags, compose button-down, pointer moves, optional waits, and
button-up. For modifier-held input, put key-down, mouse input, and key-up in
separate list entries. Combined mouse/keyboard objects retain the runner's
mouse-before-keyboard order. A screenshot inside a batch does not split the
batch or return an intermediate observation, matching `env.step`.

Holds survive requests and screenshot capture. In live modes, a down/wait/up
batch is a timed hold. In paused mode, waits do not advance task time. Send
down in one request, let its observation window advance, then release in a
later request. More observations advance more windows without releasing the
input. This preserves the benchmark's existing paused clock contract.

`live_timestamped_execution` additionally accepts `execute_at_s` on the request
object. It schedules the start of the whole batch, not its duration. Timing
receipts refer to completion of the batch. Use separate scheduled down/up
requests when their acknowledgement times must be measured individually.
The other timing modes reject scheduled execution. Environment-origin time,
frame timestamps, and observe-to-execute latency fields remain unchanged.

Unknown fields/actions, malformed coordinates, invalid durations, duplicate
JSON keys, and invalid batches are rejected before any input, observation
capture, or budget use. The old flat click/tap/drag/type commands remain usable
with strict validation. Their unsupported duration fields now produce errors
instead of being discarded. The old scroll `pixels` name retains its historic
wheel-notch behavior for compatibility and is not advertised to new agents.

Parity is for screenshot-driven keyboard/mouse interaction. Runner commands,
clock overrides, filesystem/DOM access, shell execution inside the task VM,
and arbitrary service calls are not exposed. Programs in the separate agent
sandbox may call the HTTP API freely.

## Validation

`tests/test_codex_action_contract.py` checks all native inputs in all four
temporal modes, coordinate conversions, ordered batches, held inputs,
authentication, scheduling, strict rejection, and the generated prompt.
It also checks the pinned runner's dispatched fields for contract drift.

`python -m weird_captcha_gym.tools.smoke_codex_action_gateway` runs an opt-in
no-model check in fresh task VMs. Inputs travel through the real HTTP gateway
and `env.step`. A read-only guest X11 probe checks that keys and mouse buttons
are actually held, survive observation/movement, and release. Artifacts belong
under ignored `outputs/`. These are harness checks, not benchmark scores.

### Validation on 2026-09-05

All four VM smoke checks passed on CPU allocation 10324548, step 10324548.4
(exit 0:0). Each mode checked 32 action batches, with two extra scheduled
press/release batches in timestamped-execution mode. In paused LIDAR D5/full,
the screenshot travel counter increased from 0.0 to 1.2 while W stayed held
across observation windows. Guest X11 state independently confirmed presses,
continued holds, and releases for W, modifiers, and all three mouse buttons.
The scheduled press and release acknowledgements were 7 ms and 3 ms late.
No model evaluations were rerun and no previous scores were changed.

The targeted tests passed (236). The full suite reported 652 passed, 5 skipped,
and 5 failures, all reproduced with the pre-change Codex adapter loaded:

- Three frozen-sample tests in `test_agent_sample_runner.py` reject the changed
  task population.
- The hook-count test in `test_weird_captcha_benchmark.py` counts generated
  controlled-task hooks as well as the base tasks (2040 versus 340).
- The legacy browser/server grader test in `test_weird_captcha_dashboard.py`
  disagrees on the feedback for an invalid ghost-jigsaw submission.

Those unrelated failures were left unchanged. VM results, gateway transcripts,
X11 state checks, screenshots, timing records, and pytest XML are preserved at
`outputs/codex_action_parity_smoke_20260905/` (Git-ignored). The CPU allocation
remains on its original keepalive; only the diagnostic VMs were closed.
