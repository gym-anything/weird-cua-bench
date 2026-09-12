# Orchard Exchange

A finite orchard delivery task grounded in survey record XAGT-216 (Melting Pot: Fruit Market). Harvest apples, stay fed, bargain with independently harvesting and eating farmers, then bring the requested inventory to the stall. Offers settle only when reciprocal terms, distance, both stocks and basket capacities agree.

The baseline is L3/full. `controls.json` supplies all five difficulty profiles and both input modes. Full uses arrow/WASD presses; simplified uses direction buttons. Both retain the same offer and meal controls and generate the same world for a fixed seed and difficulty. The shared framework supplies live/paused time with a 500 ms, three-frame observation window.

Implementation modules use the `orchard_exchange` plugin name. The task verifier independently replays exported primitive input and autonomous economic transitions. Source provenance, rendered checks, solvability witnesses, audits and solution films are documented in [evidence_docs/construction_report.md](evidence_docs/construction_report.md).

Status: prototype visual candidate. Automated solvability and browser evidence do not establish human usability or calibrated agent difficulty.
