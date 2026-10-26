# Combined preparation and cross-operation reuse

This gate links the accepted integrated production repack object, not the
unaccepted signed-max candidate. It addresses a gap in the isolated M4 model
test, which explicitly disabled cross-operation context reuse.

The existing `test-ara-q4k-repack.cpp` context, alias and barrier suites remain
unchanged. The private init adds `GGML_RISCV_QBS_M4_PREPARE=1` and preparation
tracing to their existing four-policy matrix: segments 0/3/256 with cross-op
context enabled, then segment 256 with cross-op disabled. All use native QBS
QEMU under combined RVV/Zfh/Zvfh, VLEN1024.

Coverage includes shared/nonshared input, worker counts, M1/M3/M4, graph
epochs, activation mutation/aliasing and an intervening expert operation.
Existing independent output and exact dispatch/lifetime checkers are reused.
The context suite additionally must actually select vector M4 preparation;
alias/barrier suites must not unexpectedly invoke M4 preparation.

Build libraries are checked against the accepted model manifest. The changed
repack object is independently checked against its production integration
receipt and takes precedence over the archive member. No user executable,
production source, RTL or default dispatch policy is modified.

This is a synthetic GGML correctness and coexistence gate, not a replacement
for real-model numerical comparisons or same-ELF RTL performance measurement.
Passing this gate does not establish performance gain from cross-op reuse.

The worker runs the three suites sequentially with a 900-second bound per
suite and fails on the first rejected suite. Run it under a directly owning
systemd service. Inspect `status.json` and `result.json` in its private output;
READY build state is not a simulation PASS.
