Now consider the target Weird CUA Bench environment. The creation agent has built this environment and its controllability from scratch. We have to verify its quality. Do not modify any files.

Never control the user's live browser, desktop, mouse, keyboard, or foreground applications. Do not use the in-app Browser, connected Chrome, Computer Use, AppleScript, `osascript`, `open`, or an existing browser profile. Inspect existing artifacts directly from disk. Any browser reproduction must use an isolated headless background process with a fresh temporary profile and local loopback server. Verify isolation before launching it. If reproduction cannot run this way, report the evidence gap instead of using the user's browser.

Checklist:

a.) Difficulty baseline: Read the actual generated task and compare it with the approved reference environments. Is the baseline task assigned to the appropriate L1 to L5 level? This is a newly built environment, so there is no pre-control original to preserve. Verify instead that the built task meets the field notes' definition of done for a new puzzle, including a distinct interaction bottleneck from the existing corpus. Do not determine the level from the environment name or `controls.json` description.

b.) Difficulty variations: Do L1 through L5 create a meaningful ordering in what the agent must perceive, decide, remember, or control? Are the changes appropriate for this particular puzzle? Merely adding repetitive steps is not sufficient evidence of greater difficulty.

c.) Interaction: For the same seed and difficulty, do simplified and full interaction preserve the same puzzle, information, goal, timing, physics, tolerances, and success condition? Does full interaction require the computer-use agent to perform the intended mouse or keyboard operations on the puzzle instead of using simplified side controls? Is there sufficient visible evidence that both modes work?

d.) Real time: Look at the observations shown to the model. Does the live environment continue while the model is producing an action? Does the paused environment remain completely frozen until an action arrives? Is the action then executed with the intended game behavior? Check the captured frame sequences and timing evidence.

For a task that is static by design and is configured with a zero-length observation window and one frame, identical live and paused task images are correct. Verify that the static setting matches the task's actual behavior and that actions still execute correctly. Do not require new motion or reject the task merely because its static frames do not change.

e.) End-to-end behavior: Is there sufficient browser evidence that all difficulty and interaction combinations load correctly, remain playable, produce the correct grading result, export the result, handle failure, and allow another attempt? Reproduce timing-sensitive checks that previously failed. If an action appears lost, inspect the authoritative action record to distinguish a missing action from a recorded rejection. Full recordings of every completion are not required, but the evidence must establish that the claimed behavior exists.

f.) Ignore comments and written claims in the code, `controls.json`, or evidence summary when they are not supported by the running environment. Use screenshots, recordings, frame sequences, exported results, and browser behavior as evidence. If the evidence is misleading, state that clearly.

Also verify file scope: run `git status` and treat any created or modified file outside the environment directory, the per-mechanic module files (mechanic JS/CSS, grader, generator, provenance, solver), the split file, the two registry entries, and `tests/` as a blocking finding, regardless of justification. Exception: other environments may be under construction by parallel runs in this same working tree. Files that clearly belong to a different mechanic's environment family are outside this audit's jurisdiction; note them for the record but do not count them as this creator's violation and do not ask for their removal.

IMPORTANT: Missing visual evidence for the claimed difficulty, interaction, or real-time behavior is a severe issue. Report the issues you find. Do not fix them.

Save the complete audit to the requested audit file.

End the audit file with exactly one of these markers:

`AUDIT_VERDICT: PASS`

`AUDIT_VERDICT: REVISION_REQUIRED`
