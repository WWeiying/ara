# e32/m1 Full5985 Static Proposal

Status: SOURCE/MODEL/FEASIBILITY ONLY. No model generation, Host, compile,
reference, DUT, or live-job query. Independent source review requested.
Even source NO_BLOCKER does not authorize Host/compile; parent authorizes next.

## Exact Source And Scope

Archive: /home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04.
Original and recovery22 rebuilt Linux ELF both
0c11f7a2d6bcf0fa0ee27e5f4eb3f9d1fc567d29ad638c5e2c9675d0dc2785e4.
Original .S834ea0fdd38dfc9f948477f7daf8de462fcbe00d4983e71302846703982055f3.
Original e32/operations.h2b3cce9dcdaaa6bc6e556ae4d2c013325ed48c473858c1984751c867a58f4b7b.
C reconstruction7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91,
binary-equivalent reconstruction, not original C bytes or Linux replay.
recovery22/report.json b11efd30ec97318d8d4cb37468ae39fea7085f6235fd79a68589e2a6455b8266.

Actual .S capacity uses e32,m1,tu,mu. At VLEN1024 this is CAP32/vtype16,
one full128B physical register per input/output group; all35 helper windows
retain13 instructions, plus capacity3 =458 static instructions.
Op0..24 are original integer/memory/movement/reduction/compress,
op25..34 are vfadd/vfsub/vfmul/vfdiv/vfmin/vfmax/vfsgnj/vfsgnjn/vfsgnjx/vfsqrt.
The original35 kinds give30 ordinary three-start ops and5 one-start ops.
3seeds*7VL*3masks*(30*3+5)=5985, not4095; VL order0,1,2,3,16,31,32.
Original start0,VL/2,(VL<CAP?VL:CAP-1), including duplicate starts, all retained.

Scope arithmetic derived from source, not an execution receipt:
191520 result elements (766080 bytes);11970 guards each32bit (47880 bytes);
5985 returned-vstart checks;77805 helper instructions;101745 packed reads.
Physical mask buffer128B remains initialized per seed/op/VL/mask group,
2205 such groups; actual helper vlm at VL32 reads4B, upper124 software bytes0.
Gather op21 uses unsigned32bit b[i]<CAP32; b[2]=0xffffffff is out of range.
Do not inherit e8/m2 b255-valid assumptions. Slidedown bounds use CAP, not VL.

## Fresh Input And History

Three seeds regenerate32 xorshift64 values each before op0, preserving all
original corner overrides. Full backing a[1024],b[1024],out[1026] is uint32_t:
4096+4096+4104 bytes, not the e8 byte counts.
Op25..34 rewrite all32 a/b words before EACH helper invocation, including
VL0, all masked selected-element emptiness and vstart>=VL. This is1890 FP
calls and120960 source-level word assignments, not once-per-seed setup.
Never hoist or remove these source loops manually, and never skip them in the
future fresh lifecycle merely because old bytes already match.
Next seed performs original RNG stores again before its integer block.
The original seed/op/VL/mask/start nesting and cumulative fflags history remain.

Draft model.py reads the pinned original FP table and names/kinds, regenerates
CAP32 integer RNG, uses only the accepted small2 integer function, and assigns
original FP source bits each call. It is not executed yet. Later Host must
compare all5985 rows against original C, including ordinal and exact inputs,
not just final outputs. Seed-init and per-FP-call input writes need separately
derived actual compiled sites/coverage before any dynamic admission.

## Floating Point Contract

Golden is the original640 exact32bit entries, indexed exactly
fp_expected[op-25][((i+seed)%8)*8+(3*i+seed)%8]. No hostfloat replaces it.
Inputs are -8,-2,-0,+0,0.5,1,2,8. The fixed table includes signed zeros,
canonical qNaN0x7fc00000, infinities and rounded binary32 square roots.
For these source inputs, each seed accesses8 index pairs,24 distinct across
three seeds; full table existence is not execution of all64 pairs per op.

Use existing startup fcsr=0 (RNE, flags initially clear), no per-call flag
clears/reads/restores added. Original C/helpers assert only data/guards and
returned vstart; they contain NO fflags/frm result oracle. NV/DZ/NX may accrue.
Neither table equality nor future programPASS proves fflags correctness.
Future reference must verify actual bootstrap/target CSR context and exact
full32bit results, preserving all original helpers and no added vector code.
No half-precision profile is needed; ordinary rv64gcv supports this source.
The accepted e32/mf2 model/terminal is a reuse authority, NOT m1 acceptance:
full_e32_mf2_terminal_audit01/run01/TERMINAL.json
35a6f06b6be566ac5c60e13ab70e27768c5a527bdab87c5ffb6f69f2dc961fcf,
INDEPENDENT_FULL_E32_MF2_TERMINAL_ACCEPTED; its historical service exit is
UNCONFIRMED_NOT_INFERRED. Do not promote that to an observed exit0.

## Minimal Scalar Representation

Choose flat5985*17 uint64 expected words =813960B. No dictionary needed.
Exact output is34 uint32 words =136B, hence17 scalar words with NO tail2.
First64bit word contains frontguard+element0; final word element31+rearguard.
The fill constant is0x0000005b0000005b, not a byte-wide0x5b fill.
Draft packed.h uses fixed17 memcpy stores/loads, each8B, offsets0..128,
no alias cast dereference and no read/write beyond136B.
Original a/b/out backing, mask loop, FP per-call initialization and exact
original per-element failure fallback/counters remain. Optimize only output
fill and positive packed comparison; all original error checks remain.

Planned Host negatives: every result/guard byte, prestart/masked/tail changes,
signedzero/NaN-payload/lowbit FP mismatch, vstart nonzero, missing FP refresh
even with matching shadow, next-seed RNG restoration, exact protected-page/
unaligned memcpy footprint. Host32bit unsigned arithmetic is defined; original
signed casts/right shifts are implementation-defined, use same RISC-V GCC.
Keep original FP inputs/table in C for fallback, no hostfloat oracle substitution.
Disable tree and SLP vectorization; verify all36 helper routines and no extraRVV.

## Memory And Cost Feasibility

Observed original Linux ELF size only (read-only size -A):
text3710,rodata4112,BSS12448,eh_frame224. These are NOT new linked dimensions.
Static planned storage: expected813960 + physical mask table384 +
original source rodata<=4112 allowance + backingBSS12448 +
Spike console/HTIF allowance12288 + text allowance32768 +
layout allowance4096 + stack65536 =945592B; remainder102984B under1MiB.
The mask table is optional for generation, but this upper budget reserves it.
Actual new ELF must satisfy linker __bss_end < __stack_top-65536 and inspected
maximum stack/frame. We cannot claim actual stack gap before authorized compile.
No original model/host tables may leak into the DUT image.

Packed output cost is fixed17stores+17loads per5985call; FP initialization
retains1890*32 original iterations. Actual instruction cost is not measured.
A source-level hypothesis of250..400 scalar instructions/call plus10..20 per
FP input iteration gives roughly2.3..3.9M including mask/control allowance.
This is deliberately not a <=3M admission claim. Actual compiler sites and
positive control paths must establish a bound before proposing one reference.
No prefix substitution, no automatic optimization variants, no timeout raise.
Current task ends with static source review; future Host/compile requires
parent authorization. Reference/DUT are not authorized.
