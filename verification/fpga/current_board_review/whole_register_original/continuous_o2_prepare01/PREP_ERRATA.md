# Static tool-path correction

Initial prepare command exec session8799 exited1 after the SoC compile had
already exited0. describe() replaced gcc in the entire toolchain path, producing
the nonexistent install/riscv-nm/bin/... path. No Spike compile/reference had
run. Fix uses CC.with_name to replace the executable basename only.
Explicit --resume-static verifies copied inputs, tuples and the exact successful
SoC compile receipt; it does not rerun that compile. It completes static proof
and the not-yet-attempted Spike compile. No reference retry is permitted.
