# Revived infrastructure pilots v2

Date: 2026-07-14

The original `moving_checkbox_evasive_button` and `reverse_identity_gate`
tasks proved runner, browser, export, and verifier plumbing.  They were then
correctly rejected: one was a moving click target and the other was an
inverted-label/checksum form.  Neither original acceptance contract survives
this rebuild.

Both environment identities and source anchors are retained so the repository
keeps its provenance and launch history.  Promotion changes the catalog from
73 built plus two rejected pilots to 75 built candidates.  It does not place
either task on the verified split and it does not constitute human approval.

## Scroll-Cage Checkbox

Visible prompt: **Check the box.**

The checkbox is a finite-radius moving body inside four independently
scrollable shafts.  Each boundary has two physical portal halves, one attached
to each neighboring scroll surface.  Passage exists only where the rendered
halves overlap.  The cursor creates a visible repulsive field and the checkbox
responds through fixed-step integer dynamics.  The operator must alter portal
topology with ordinary wheel/scroll-grip input, continuously shepherd the body
through the shafts, and settle it into a permanent clamp before it can be
clicked.

The browser records primitive cursor, scroll, fixed-tick, capture, check, and
verify events.  The server reconstructs offsets, portal overlap, acceleration,
velocity, wall/portal collision, and clamp capture.  Client-reported body
positions or a terminal `checked` bit are never sufficient.

Natural difficulty comes from active tracking, indirect cursor control,
changing scroll topology, occlusion, and recovery.  It may not be increased by
shrinking the checkbox, shortening an arbitrary click window, hiding portal
state, or rejecting sparse but geometrically valid pointer delivery.

## Four-Tab Robot Handshake

Visible prompt: **Prove you are a robot.**

The master gate deploys four real same-origin browser tabs, one per robot limb.
The limbs share a generated eight-relay challenge but each tab renders only its
own receiver.  During an active relay a pulse orbits continuously while the
operator drives a receiver with left/right keys and holds a mouse contact.
Charge accumulates only while the receiver and pulse remain physically aligned;
the next limb is revealed as a visual handoff glyph.  Completing the two
generated circuits requires real tab/focus management and repeated live
tracking, not an identity answer.

Child tabs are created by explicit user gestures and inherit the already loaded
challenge through a same-origin bridge; they do not fetch or select independent
static-browser attempts.  Input transitions and every fixed tick are merged
into one challenge-bound ledger.  The server independently replays pulse
motion, receiver motion, contact charge, station order, relay transitions, and
the final master verification.

Natural difficulty comes from distributed transient state, browser-tab
navigation, dual-channel keyboard/mouse control, and temporal phase tracking.
Tab focus is never accepted as ceremonial evidence, and missing a phase merely
loses visible charge rather than silently failing or regenerating.

## Binding gates

- Both generators must demonstrate structural variation and reachability over
  many fresh seeds.
- Visible geometry, browser hit testing/dynamics, server grading, and exported
  verification must implement the same equations.
- Deliberate early verification must produce an unmistakable failure and a
  fresh challenge; the canonical passing transcript contains no forced miss.
- Ordinary Playwright mouse, wheel, keyboard, and real page/tab actions must
  pass the browser, live server, direct grader, and exported verifier across
  multiple seeds.
- Static browser play must retain the complete mechanics and exact Python
  graders; it is an exploration surface, not an authoritative secret endpoint.
- Solution films are captured only after task-facing hashes are frozen.
- Both revived tasks enter the human ledger as `pending` and remain outside the
  verified split until real human and agent evidence exists.

## Verification outcome

The frozen v2 implementations passed the canonical browser failure/reset/solve
cycle, live server grading, a separately loaded direct grader, and the exported
Gym-Anything verifier. A 100-seed audit then reproduced a clean accepted solve
for every seed and rejected 100/100 stale-challenge payloads plus 100/100 forged
replay states for each mechanic. The task-facing hashes remained unchanged
while the 1280 × 720 solution films were recorded. These results promote both
records into the built catalog. Both entered human review as pending and were
later marked `looks_good`; neither is approved.
