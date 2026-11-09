# Real-Model Preparation Cost Diagnostic

This uses the frozen, unchanged full SoC image and accepted Qwen3 D128/H2/T137
complete call, with 64+64+9 token tiles. Both ABBA arms execute the stronger
rotated-register, two-row-loop PV control. The candidate redundantly prepares
the proposed resident source before calling that same control; there is no new
instruction or hardware behavior in this experiment.

The timed issue interval surrounds `resident_pv_prepare`, including its final
EEW normalization request. It is not proof that every source word is already
available: vector work may continue after helper return. A second interval adds
a diagnostic six-register store and memory fence, so it includes work a real
resident command would not need. Report both, without calling either an exact
future instruction overhead. Input snapshots also warm data before timing.

All full-call numerical/CSR/guard/input and independent protocol checks remain.
The extra captures mean candidate full-call latency is **not** an optimization
speedup. Six captures must have expected shapes and repeat identical active bits.
The first three raw captures contain real probabilities, accumulators, scales,
and the proposed source. Independent Spike SoftFloat checks both FP16 casts,
seed multiplies, source interleaving and sticky exception flags. The second three
must match the first three active captures exactly. Inactive source bits are
not interpreted, and no inactive floating-point operation is allowed.

The independent numerical check uses three raw captures; the other three rely
on target-side bitwise repeat comparisons. This real call is D128/H2, RNE, not
an all-rounding-mode or exceptional-input campaign. Sticky flags cannot expose
an exception whose bit was already set. Host geometry tests are separate from
RTL execution and do not enlarge that numerical acceptance scope.

The selected SDK and dependency objects come from accepted frozen build inputs,
not the dirty SDK assembly or live dependency copies. `prepare.S` is an
experimental leaf helper, not an enabled production backend. `experiment.py`
reuses the accepted build/process owner while declaring its own source pins and
stronger-control vector signatures. A passing capture gate is a prerequisite,
not a substitute for the new instruction's complete-call performance test.

Run host tests and build first. Start simulation using a direct-owner systemd
service with explicit stdout/stderr paths and a fresh signoff output directory;
confirm a real `simv` process and do not poll a long run. No synthesis,
Verilator, URG, bus change, or FPGA deployment is involved.
