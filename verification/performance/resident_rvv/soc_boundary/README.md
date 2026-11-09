# Resident PV SoC Boundary Firmware

Scope: **21 PV scenarios + 1 QBS/RVV compatibility postlude** in one ELF, no SoC
reset between scenarios. This directory builds software/oracle evidence only.
No VCS prepare/launch, production RTL/SDK edit, capability advertisement,
performance conclusion, or hardware acceptance is authorized here.

## Matrix

| IDs (zero-based) | Purpose |
| --- | --- |
| 0..5 | D/H/T/RM = 64/1/1/0, 64/2/64/1, 96/1/9/2, 96/2/64/3, 128/1/64/4, 128/2/9/0 |
| 0, 2 | After preparation, establish VL0/e8m1 or vill/VL0; capture unchanged VL/VTYPE after PV before result-store reconfiguration |
| 6, 7 | Explicit IEEE patches: NV plus preexisting DZ; UF/NX plus inactive H1-head sNaN poison |
| 8..11 | Upper control, Dcode3, vstart1, frm5; each trap then next-good |
| 12..14 | No context, mismatched dimension, context T9/request T64; each backend error then next-good |
| 15 | Real prepared 384-half snapshot loaded as 192 e32 elements/LMUL8 into v8..v13, with distinct EW64 v14/v15 guards |
| 16..20 | FS off, VS off, rd2, vs2v4, rd8/vs2v8 alias; each exact-PC illegal then next-good |

There are 33 PV attempts: 21 successes, 9 frontend rejects and 3 backend rejects.
FS/VS-off must not reach CVXIF; other frontend rejects must have no backend alloc.
Backend rejects allocate but drain 96 source words, never launch lane arithmetic,
and have no PV writes. They must preserve old destination interpretation.

Recovery is **field/software-CSR recovery on the same resident context**, not a
reload-based test. After raw trap CSR capture and software access restoration,
11 rejected scenarios issue next-good without RELEASE/FILL/REFILL/reset. D
mismatch recovers with the existing D128/T9/H2 context; T overshoot recovers with
the existing D96/T9/H2 context. Both have separate SoftFloat output/flags for the
correct next-good geometry, using the same input arrays. Only no-context, which
already executed RELEASE, performs one replacement FILL. The independent checker
requires the exact retired command order: 22 FULLs and 22 RELEASEs in total, and
rejects hidden reloads between bad/next-good. Counts remain 21 scenarios/33 PV
attempts plus one compatibility postlude.

## Input And Oracle Identity

Raw FP32 probability/scale and F16 seeds come from the receipt-pinned first three
`PV_PREP_DATA` captures in `resident_pv_prepare_vcs_20261109_01/work/run.vcs.log`.
The parser verifies its repeated call and original preparation with SoftFloat.
Q/K/V use the pinned `e2e_qwen3_f16_native_data_20261106_02` Qwen3 capture.
D64/D96 are labeled prefix crops of D128, not native-model shapes; token stride
remains 256 bytes. H1 selects the first head. Tile starts are 0,64,128.

The mixed-source case cross-checks the helper's full 384-half snapshot against
`resident_pv_real_operands_20261108_01.json`, including inversion of the four-lane
EW16 permutation. It does not rescale/narrow already-prepared data again.
`ordered_reference.py` and Spike SoftFloat independently calculate all outputs,
preparation flags, FMA-only flags and lane flag unions; no host FP approximation
or RTL result is an oracle. IEEE patches are explicitly labeled synthetic.

Generated C arrays are content-deduplicated, including all five added rejection
cases. Firmware does not repeatedly hash the full capture; the host binds source,
generated data, archive, ELF and oracle identities. Device-side checks cover
active results, output-memory guards, failure destination and mixed source guards.

## Fault And Layout Boundaries

The sealed `pv_prepare/prepare.S` stays unchanged. New assembly fixes normal
vd0/vs2v8, supports H1/H2, and stores only active D/H using a 512B memory stride.
Successful inactive v0..v3 elements are undefined and never read for comparison.
On failure all four destination registers were previously defined with a
nonuniform EW32 pattern; the first subsequent vector operation captures them at
EW32. Uniform a5 sentinels would not detect an erroneous retag and are not used.

The private `rvtest_init` uses the archived CRT hook to select M-mode and install
a strict trap entry. Only armed exact PC/cause2 returns to its explicit label.
mtval is raw evidence, not required to equal the instruction (backend may use 0).
vstart1/frm5 are recorded before software clears them. FS/VS-off trap entry reads
only mstatus/mepc/mcause, restores access on return before FCSR/vector-CSR reads;
its unavailable trap CSR fields are marked invalid, not claimed observed.

Only mixed-source case15 permits PV-labeled maintenance uops: exactly vd8..13,
EW16/VL64, source3 SLDU actual grants, exact addresses/data. The final PV alloc
must remain vd0/EW16/VL256, with source4 LDU actual writes limited to active slots.
v14/v15 stay EW64 and bitwise unchanged. Maintenance permission never extends the
final destination, other scenarios, or rejected commands.

After PV, the postlude clears FCSR only, executes exact `0x00b5045b` QBS m1/N3/K1
on known Q4_K weights 1/2/3 and Q8_K activation 1, then checks all 32 outputs:
43800000/44000000/44400000 and 29 zeros. Ordinary RVV vadd follows. Both retain
FCSR0, and the checker requires actual alloc/write/done data for both operations.
There is no capability-disabled skip or permissive trap handler.

## Build And Freeze

```sh
python3 -B verification/performance/resident_rvv/soc_boundary/build.py --parent-reviewed --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_soc_boundary_build_20261109_02
```

The builder uses only the sealed b7c9e6c SDK/common tar archive and its copied
inputs, a new generated header and unchanged prepare helper. GNU compiler,
subtools/libraries, transitive dependencies, SoC03 full image, all new sources,
receipts and artifacts are pinned. Host tests include real-operand SoftFloat,
strict parser/work mutations and GNU disassembly/ELF checks, not dynamic admission
evidence. The receipt is `BOUNDARY_SOFTWARE_BUILT_NOT_EXECUTED` only on success.

Future execution needs parent review and an independent CPU/backend/AXI protocol
audit in addition to `check.py`. No old smoke checker is relaxed. `check.py` only
claims numerical/work checks, not overall hardware PASS. Frozen inputs must not
be edited while any consumer uses them; retain failed builds under their first
output names and use a fresh successor directory.
