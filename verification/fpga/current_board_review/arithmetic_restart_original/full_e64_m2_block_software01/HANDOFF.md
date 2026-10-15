# e64/m2 Full5985 Software Artifact

Status: HOST_COMPILED_STATIC_COST_HOLD. No Spike/reference or VCS/DUT execution.
Source/Host/GCC stage is complete; no architecture or Linux acceptance claimed.

## Actual Evidence

execution_receipt.json: actual child wait0,27.623255940619856s, no timeout.
execution_terminal.json records no input pin drift. proof.json and pins.json
retain every command, numeric child receipt and artifact hash.
31 Host runs: original/packed each positive+11 result negatives+one UB trap,
plus five missing-state negatives.12 paired complete transcripts are identical.
All non-UB result histories retain5985calls/191520results/11970guards and
1890FPcalls/120960input writes. Every output position uses the original C
calculation versus independently generated integer/FP bit-model values.
Mutation coverage includes active/prestart/masked/tail, each guard, vstart,
FP signed-zero/NaN/active bits and final result high bit. UBSan shift64 traps;
legal shifts63/64 and INT64_MIN/-1 division/remainder corners are checked.
Deleted equal-value FP a or b store rejects at actual call1367; missing fresh
output, next-seed RNG and mask upper clearing each reject with numeric90.
Full dirty mask is exercised across original mask-group transitions, plus
unaligned exterior guards and PROT_NONE boundaries for128B mask and272B output.
Host uses a mock helper, not vector execution; it establishes source/model
equivalence and instrumentation obligations, not RVV hardware correctness.

## Preserved Source and Actual ELF

source.diff has only CAP32 guard,34-word packed initialization/dictionary
comparison and16x8B mask clear. Original every-FP-call input loop, seed RNG,
full fallback/history and helper source remain. The mask helper is copied
from accepted e32 software02: empty compiler memory barriers are not emitted
hardware fences. Output guards are uint64 0x5b, not typed16 repeated005b.

Both GCC ELFs have458 byte-matched original helper instructions, no extraRVV,
original640 FP64 words uniquely matched and complete dictionary/indices linked.
Actual FP loop has15 scalar instructions, two ordered SD stores/iteration,
32 iterations/call, op>24 gate with all later trials returning through it.
This preserves1890 full64-word refreshes regardless of VL/start/equal data.
Both have34 SD initialization and34 LD comparison at offsets0..264.
Final dictionary block reads only result256 and guard264: no padded48B access.
Both mask clear regions decode to16 SD-zero at exact mask+0,8,...,120,
with only address formation and no hardware fence/call/branch/RVV.
Main frame288B; actual stack gaps SoC869088B, reference-artifact860696B.
Source FP CSR oracle remains absent; no new fflags acceptance or reset is claimed.

Actual sections:
- SoC: text5904B,rodata148728B,BSS24784B.
- Reference artifact (compiled only): text5976B,rodata148736B,BSS32984B.
No simulator was invoked for either artifact.

## Budget and Remaining Blocker

compiled_review.json binds actual per-PC regions and source multiplicities.
Successful-path mandatory core2888970 instructions; conservative upper3074202
including conditional union bounds,BSS zeroing and20000 terminal/runtime allowance.
This exceeds3M, so budget eligibility is HOLD. It is not a retired measurement:
actual firmware instruction count is unknown. The static upper exceeding3M
does not by itself prove actual execution exceeds3M. No automatic reference,
timeout extension, compile parameter search or input-refresh removal follows.

Next action: independent readonly artifact/CFG review by Hilbert. Any later
cost refinement must be justified from this exact compiled CFG; execution or
source changes require appropriate subsequent authorization. Old static files,
sealed materials, RTL and running tasks have not been modified.
