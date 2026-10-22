# Host Fixture Compile Failure

Actual Host compiler exit1. `replay_write` asserted a nonnegative signed `long`
length, then compared a signed sum against unsigned `sizeof(transcript)` under
`-Werror=sign-compare`. The successor casts this already nonnegative length to
`unsigned long`. This is only the Host output-capture fixture, not the pinned
candidate/source oracle. Original failed sources, command, log and wait receipt
are retained here. No SoC or Spike ELF compilation was dispatched in this run.
Fixed flags remain unchanged; no target-compiler retry or tuning occurred.
