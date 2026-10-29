# Complete Q/V/K projection gate

The preparation-only RTL gain is 1.7114x. This successor measures its net effect
on the complete accepted Qwen2.5 projection slice, not a product of ratios.

Both ABBA paths use the same exact-byte activation cache. Each trial has one
cold production, two hits, one fill and explicit release. Only the cold producer
changes from the current packed RVV quantizer to the parallel group-sum version.
The cache does not persist across trials. Namespace producer labels do not
permit reuse between numerically unverified producers.

Work is M=4, K=1536, with Q/V/K output widths 1536/256/256. Q and K use Q4_K;
V uses Q6_K. Every trial computes all 8192 FP32 outputs using 64 QBS commands.
All four trials retain packed-byte equality to the accepted golden, per-output
model-reference tolerance checks, bit-exact paired outputs, FCSR/VCSR equality,
input/weight integrity, output guards and SDK/plan status checks.

The separate trace checker requires exactly 256 native M4 commands and 512
result bytes per command, without duplicate or missing result byte addresses.
Independent UVM protocol acceptance and immutable input/image checks are also
required. A preparation-only or functional-only log cannot satisfy this gate.

`build.py` uses the old archive for command recipes, data and golden identity;
it recompiles all 12 bare-metal objects from their current sources. It does not
reuse archived RTL or quantizer object files. Compilation uses production-style
FP contraction equally for both candidate and baseline.

The standalone preparation result used a smaller program and must not be
subtracted directly from earlier projection timings to claim measured gain.
Only paired timing from this executable is accepted. Until final validation,
the production quantizer and hardware remain unchanged.
