# Unchanged-Image RVV Findings

These findings are retained for a later coordinated RTL repair. No RTL change
or new bitstream is part of this coverage campaign.

## RVV-01: Indexed Load Overlap Across Page Faults

Confirmed board failures: four width/overlap cases terminate with SIGSEGV;
one additional case stops retirement. Resident and non-overlap controls pass.
An erroneous address contains two adjacent 32-bit halves of intended 64-bit
indices. The exact replay/layout pipeline stage remains unproven.

Evidence directory: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
See `HARDWARE_FINDINGS.md`, `width_fault_timeout02.json`,
`campaign03_fault_evidence.json`, and `width_restart04_live.json`.
Do not report the hypothesized EEW bookkeeping mechanism as a captured
cycle-level cause.

## RVV-02: Arithmetic Restart Mask Supply Mismatch

The original 22-shape matrix finishes with 19 passing shapes and three
no-retirement failures: e8/m4, e8/m8, e16/m8. Passing configurations total
94,815. All identical reference ELFs pass QEMU VLEN512 and VLEN1024.

The drained trace confirms the first e8/m4 failing trial:
`seed=0, VL=512, mask=all-on, vstart=256`, following 55 completed trials.
The deployed archived lane sequencer trims the mask request to one word
starting at mask word one. MASKU/arithmetic still consume the zero-based
two-word prefix. This source contract mismatch agrees with the measured
boundary and lack of retirement; internal queue register values have not
been captured in a waveform.

Evidence: `rvv_trace02/report.json`, `rvv_trace02/uart.bin`, and
`rvv_stall_archived_rtl/SHA256SUMS`. Final original-matrix results are in
`rvv_extended04/report.json`, `m8_report.json`, `resume02_report.json`, and
`resume03_report.json` under the evidence directory above.

Additional arithmetic suites intentionally use vstart=0 to reach independent
opcodes on this unchanged image. This is an explicit coverage exclusion,
not a fix, workaround acceptance, or conversion of the original failures
into passes. Later restart regression must rerun the original failing ELFs.

Recovery14 adds a masked multiply-add restart scene at the same e8/m4,
VL512/vstart256 boundary. The exact ELF
`rvv_integer_macc_accumulators_restart_e8_m4` has SHA256
`608e941760443563f055058d60f18ce466a06d016fb277989fc332ed9cdb347d`.
The drained trial records seed0/mask0/completed481; disassembly at0x108e0
is `vmacc.vv v24,v8,v16,v0.t`, followed by `csrr a0,vstart` at0x108e4.
Two snapshots advance cycles265789050780 to266323267050 while retired139112889938,
trap_count13497857 and last/head PCs0x108e0/0x108e4 stay fixed. Both DDR
channels have no outstanding transactions or response errors, live halt
flags are clear and neither capture is watchdog-halted. The unqualified
head-PC probe is not a commit-validity signal.

`rvv_recovery08_14/terminal_scene` retains full UART/report/snapshots,
the exact ELF, disassembly, gap plan and file hashes. This is an additional
instruction scenario consistent with RVV-02's boundary, not an independently
captured internal queue proof or a numerical pass. The five earlier
additions42 shapes pass112000 configurations with exact reference outputs
(`rvv_recovery14_release42_partial01`); the release remains incomplete.
Authorized recovery15 retains476 unattempted cases and47 verified observation
gaps, with the masked accumulator restart family deferred rather than omitted.

Recovery15 records a second multiply-add scene with first-source aliasing:
`rvv_integer_macc_accumulators_alias_first_restart_e8_m4`, SHA256
`2a12ae383475920c035d3e0458a7dbb0f5a19a97a7983b667096d3b87db06cd6`.
The last drained trial again has seed0/VL512/mask0/vstart256/completed481.
The exact ELF has `vmacc.vv v24,v24,v16,v0.t` at0x108d6 followed by
`csrr a0,vstart` at0x108da. Cycles66018979299 to66536233905 advance while
retired28583704919,trap_count3170525 and last/head PCs0x108d6/0x108da remain
unchanged. Both DDR channels have zero outstanding transactions/errors;
live halt flags and watchdog status are clear. Complete evidence is in
`rvv_recovery08_15/terminal_scene`. This adds an alias scenario consistent
with the recorded mask restart boundary; it does not independently prove
the internal queue state or introduce an assumed distinct RTL cause.
Recovery16 retains all448 unattempted ELF identities and defers only the
newly stalled masked first-alias family in addition to prior deferrals.

Recovery16 records a masked second-source alias scene:
`rvv_integer_macc_accumulators_alias_second_restart_e8_m4`, SHA256
`10e5be00fbd9bae3d1ab131522daa49db37aa59c76d3f884a0ab17b8b4544d51`.
The drained trial is seed0/VL512/mask0/vstart256/completed481. Disassembly
shows `vmacc.vv v24,v8,v24,v0.t` at0x1088c and `csrr a0,vstart` at0x10890.
Cycles25180784993 to25695022852 advance while retired8270858463,
trap_count1044259 and last/head PCs0x1088c/0x10890 remain unchanged.
Both DDR channels have zero outstanding transactions/errors; live halt
flags and watchdog status are clear. The head-PC probe has no validity bit.
`rvv_recovery08_16/terminal_scene` preserves the exact ELF, UART, reports,
disassembly, snapshots and hashes. This is another measured boundary scene,
not independent internal queue proof. Recovery17 retains all420 unattempted
cases and additionally defers the masked second-alias family. The preceding
27 completed ELFs pass548800 configurations in
`rvv_recovery16_release42_partial01`; the stalled ELF is excluded.

Recovery17 records a masked both-source alias scene:
`rvv_integer_macc_accumulators_alias_both_restart_e8_m4`, SHA256
`169776b6ff29b2bd421b9fb9af33ab9aa944076e0530d3d9bbbe2588b79d68d1`.
The drained trial is seed0/VL512/mask0/vstart256/completed481. The exact
ELF decodes `vmacc.vv v24,v24,v24,v0.t` at0x10880 and `csrr a0,vstart`
at0x10884. Cycles19762613070 to20283386175 advance while retired5219137093,
trap_count768759 and last/head PCs0x10880/0x10884 remain unchanged.
`rvv_recovery08_17/terminal_scene` preserves the exact ELF and complete
diagnostic evidence. The existing restart boundary is reproduced with both
sources aliased; internal queue state is not independently captured.
Its27 completed ELFs pass302400 configurations in
`rvv_recovery17_release42_partial01`. Recovery18 retains392 unattempted
ELFs and additionally defers the masked both-source alias family.

Recovery66 adds an e8/m8 masked both-source alias completion stall:
`rvv_integer_macc_accumulators_alias_both_restart_e8_m8`, SHA256
`671ca656d016c194f83f301de208083dd2c201244b9cf49b2c2df38a7a561487`.
The last drained trial prints seed0/VL512/mask0/vstart256/completed321.
Last retired/head PCs0x10880/0x10884 decode `vmacc.vv v24,v24,v24,v0.t`
and `csrr a0,vstart`. Cycles11329517641 to11858955326 advance while
retired1660490106, trap_count244376 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_66/terminal_scene`. This
is consistent with the existing mask restart boundary, not independent
internal queue proof; head validity is unavailable and the last retired
PC does not prove the multiply-add never retired. No completed numerical
marker exists. The continuation retains42 pending exact ELFs.

Recovery67 adds an e16/m8 masked both-source alias completion stall:
`rvv_integer_macc_accumulators_alias_both_restart_e16_m8`, SHA256
`bd7b1a0aa50fe7cc4957ab1681026b0d9fd920aae367b27f87b3b666fd70032c`.
The last drained trial prints seed0/VL512/mask0/vstart256/completed481.
Last retired/head PCs0x108bc/0x108c0 decode `vmacc.vv v24,v24,v24,v0.t`
and `csrr a0,vstart`. Cycles11324399337 to11848894506 advance while
retired1659343895, trap_count244965 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_67/terminal_scene`. This
is consistent with the recorded mask restart boundary, not independent
internal queue proof; head validity is unavailable and the last retired
PC does not prove the multiply-add never retired. No completed numerical
marker exists. The continuation retains41 pending exact ELFs.

Recovery68 completes the both-source alias restart e32/m8 and e64/m8
ELFs with11200 configurations each, errors0 and exit0. The frozen
`rvv_recovery68_active_snapshot01.json` and
`rvv_recovery68_release42_partial01` bind the exact released ELF hashes,
batch nonce and both VLEN references; the board completion lines match
the VLEN1024 references exactly. These shapes have VLMAX256/128 and do
not exercise the VL512/vstart256 boundary retained above. Their22400
passing configurations do not negate the e8/m8 or e16/m8 stalls, establish
whole-release acceptance, or cover the stalled ELFs' unexecuted trials.

Recovery68 also records an e8/m8 masked second-source alias stall:
`rvv_integer_macc_accumulators_alias_second_restart_e8_m8`, SHA256
`6b55b73eb0a53f9e3b0410a6de62b3970b0f9ee1095ca5c3e66128e4da8315cd`.
The retained trial trace reaches seed0/VL512/mask0/vstart256/completed321.
Last retired/head PCs0x1088c/0x10890 decode `vmacc.vv v24,v8,v24,v0.t`
and `csrr a0,vstart`. Cycles11993369022 to12512068440 advance while
retired1963560028, trap_count285041 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_68/terminal_scene`. This
is consistent with the recorded mask restart boundary, not independent
internal queue proof; head validity is unavailable and the last retired
PC does not prove the multiply-add never retired. No completed numerical
marker exists for this ELF. The continuation retains38 pending exact ELFs.

Recovery69 records an e16/m8 masked second-source alias stall:
`rvv_integer_macc_accumulators_alias_second_restart_e16_m8`, SHA256
`30acb3cf76fa4bb350d0ce676746f8ac089a1c61c7ae3153b7cc464f4b6b498a`.
The retained trial trace reaches seed0/VL512/mask0/vstart256/completed481.
Last retired/head PCs0x108b8/0x108bc decode `vmacc.vv v24,v8,v24,v0.t`
and `csrr a0,vstart`. Cycles11333628200 to11852321780 advance while
retired1659456931, trap_count244719 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_69/terminal_scene`. This
is consistent with the recorded mask restart boundary, not independent
internal queue proof; head validity is unavailable and the last retired
PC does not prove the multiply-add never retired. No completed numerical
marker exists for this ELF. The continuation retains37 pending exact ELFs.

Recovery70 completes the second-source alias restart e32/m8 and e64/m8
ELFs with11200 configurations each, errors0 and exit0. The frozen
`rvv_recovery70_active_snapshot01.json` and
`rvv_recovery70_release42_partial01` bind the exact released ELF hashes,
batch nonce and both VLEN references; board completion lines match the
VLEN1024 references exactly. VLMAX256/128 excludes the retained
VL512/vstart256 stall boundary. These22400 passing configurations do not
establish whole-release acceptance or cover stalled ELFs' unexecuted trials.

Recovery70 also records an e8/m8 masked first-source alias stall:
`rvv_integer_macc_accumulators_alias_first_restart_e8_m8`, SHA256
`ea462fb74c96c5d2a11fc0992eb45c781a1ebe8d3ce27f6392a11c5b5ab45b68`.
The retained trial trace reaches seed0/VL512/mask0/vstart256/completed321.
Last retired/head PCs0x108d6/0x108da decode `vmacc.vv v24,v24,v16,v0.t`
and `csrr a0,vstart`. Cycles12071895815 to12610007067 advance while
retired1978627250, trap_count287755 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_70/terminal_scene`. This
is consistent with the recorded mask restart boundary, not independent
internal queue proof; head validity is unavailable and the last retired
PC does not prove the multiply-add never retired. No completed numerical
marker exists for this ELF. The continuation retains34 pending exact ELFs.

Recovery71 records an e16/m8 masked first-source alias stall:
`rvv_integer_macc_accumulators_alias_first_restart_e16_m8`, SHA256
`89022d01e58af1ad2391d6fdf7dcf6b63c84dc9a6f38d78f38bee0bc24934c76`.
The retained trial trace reaches seed0/VL512/mask0/vstart256/completed481.
Last retired/head PCs0x10904/0x10908 decode `vmacc.vv v24,v24,v16,v0.t`
and `csrr a0,vstart`. Cycles11322210272 to11900920662 advance while
retired1658251171, trap_count243318 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_71/terminal_scene`. This
is consistent with the recorded mask restart boundary, not independent
internal queue proof; head validity is unavailable and the last retired
PC does not prove the multiply-add never retired. No completed numerical
marker exists for this ELF. The continuation retains33 pending exact ELFs.

Recovery72 completes the first-source alias restart e32/m8 and e64/m8
ELFs with44800 passing configurations in total, errors0 and exit0.
The frozen `rvv_recovery72_active_snapshot01.json` and
`rvv_recovery72_release42_partial01` bind the exact released ELF hashes,
batch nonce and both VLEN references; board completion lines match the
VLEN1024 references exactly. VLMAX256/128 excludes the retained
VL512/vstart256 stall boundary. These passes do not establish whole-release
acceptance or cover stalled ELFs' unexecuted trials.

Recovery72 also records an e8/m8 masked disjoint-source multiply-add stall:
`rvv_integer_macc_accumulators_restart_e8_m8`, SHA256
`b5a3892705e057c5c4e2424184ee530509ef8de681bfaacc749a5be3d5003b9f`.
The retained trial trace reaches seed0/VL512/mask0/vstart256/completed321.
Last retired/head PCs0x108e0/0x108e4 decode `vmacc.vv v24,v8,v16,v0.t`
and `csrr a0,vstart`. Cycles12614144120 to13189794589 advance while
retired2263594115, trap_count315466 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_72/terminal_scene`. This
is consistent with the recorded mask restart boundary, not independent
internal queue proof; head validity is unavailable and the last retired
PC does not prove the multiply-add never retired. No completed numerical
marker exists for this ELF. The continuation retains30 pending exact ELFs.

Recovery73 records an e16/m8 masked disjoint-source multiply-add stall:
`rvv_integer_macc_accumulators_restart_e16_m8`, SHA256
`962c5ee7a1550529d21cfb6397e961efd53c0de2c6fa443083bf57df6ae2fca0`.
The retained trial trace reaches seed0/VL512/mask0/vstart256/completed481.
Last retired/head PCs0x10910/0x10914 decode `vmacc.vv v24,v8,v16,v0.t`
and `csrr a0,vstart`. Cycles11276994555 to11828716594 advance while
retired1654948047, trap_count242778 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_73/terminal_scene`. This
is consistent with the recorded mask restart boundary, not independent
internal queue proof; head validity is unavailable and the last retired
PC does not prove the multiply-add never retired. No completed numerical
marker exists for this ELF. The continuation retains29 pending exact ELFs.

Recovery74 completes the disjoint-source restart e32/m8 and e64/m8
ELFs with44800 passing configurations in total, errors0 and exit0.
The frozen `rvv_recovery74_active_snapshot01.json` and
`rvv_recovery74_release42_partial01` bind the exact released ELF hashes,
batch nonce and both VLEN references; board completion lines match the
VLEN1024 references exactly. VLMAX256/128 excludes the retained
VL512/vstart256 stall boundary. These passes do not establish whole-release
acceptance or cover stalled ELFs' unexecuted trials.

Recovery19 records a fixed-point multiply restart scene:
`rvv_fixed_restart_e8_m4`, SHA256
`ca6937f7969cb2664becfe53fac5e49111415929e96220874568964b293b85cc`.
The drained trace reaches seed0/VL512/mask0/vstart256/completed776.
Disassembly at0x1094e is `vsmul.vv v24,v8,v16,v0.t`, followed by
`csrr a0,vstart` at0x10952. Cycles12850781809 to13380665377 advance
while retired2061212570,trap_count346790 and last/head PCs stay fixed.
Both DDR channels have zero outstanding transactions/errors, live halt
flags are clear and snapshots are not watchdog-halted. The unqualified
head-PC is not a valid-request probe. This is an additional fixed-point
scenario at the known masked arithmetic restart boundary, not an
independently captured internal queue explanation.
`rvv_recovery08_19/terminal_scene` retains the full report/UART/snapshots,
exact ELF/disassembly and hashes. The preceding five additions33 ELFs
pass53760 configurations (`rvv_recovery19_release33_partial01`).
Recovery20 retains363 unattempted exact ELF identities, with this vector
fixed-point restart family deferred; scalar/immediate restart is distinct.

Recovery20 independently records the scalar fixed-point scene
`rvv_fixed_scalar_restart_e8_m4`, SHA256
`e3cc6bbc47f50d700e89711d37dfe38baf42f68c8a68a6ca28271ffa930dd7d0`.
The drained boundary is seed0/VL512/mask0/vstart256/completed776.
The exact ELF decodes `vsmul.vx v24,v8,t3,v0.t` at0x10aee and
`csrr a0,vstart` at0x10af2. Cycles13955386534 to14475189543 advance
while retired2754153391,trap_count402906 and these last/head PCs stay fixed.
Both DDR channels have zero outstanding transactions/errors; halt flags
and watchdog status are clear. The recorded cause2 trap is historical,
not evidence that this VSMUL trapped. The head-PC probe has no validity bit.
`rvv_recovery08_20/terminal_scene` preserves the independent exact ELF,
full UART/report/snapshots/disassembly and hashes. This adds a scalar
scenario at the known restart boundary, not proof that all scalar or
immediate fixed-point opcodes fail. Five earlier ELFs pass201600
configurations (`rvv_recovery20_release33_partial01`). Recovery21 retains
all357 unattempted ELFs and additionally defers scalar fixed-point restart.

Recovery31 independently records the m8 shape
`rvv_fixed_scalar_restart_e8_m8`, SHA256
`85c65f7ba33ebcad6e0f8eac0732c350057810fba68699691e7b3dfa0a341937`.
The last trial marker is seed0/VL512/mask0/vstart256/completed520.
last_pc0x10aee decodes `vsmul.vx v24,v8,t3,v0.t`; unqualified head
PC0x10af2 is `csrr a0,vstart`. Cycles11796895109 to12335213624 advance,
while retired1748975267, trap_count274670 and both PCs stay fixed.
Both DDR channels have zero outstanding transactions/errors; halt flags
and watchdog status are clear. The recorded cause9 trap is historical.
This establishes another completion/restart boundary, not an independently
proven internal mask-queue cause or failure of the later scalar/immediate
operations blocked by this stall. The exact ELF, full UART, snapshots,
report and disassembly are preserved in `rvv_recovery08_31/terminal_scene`.
No completed numerical result exists for this ELF. Recovery32 retains all301
unattempted exact ELF identities and continues the scalar restart family.

Recovery32 records the independent SEW16 scene
`rvv_fixed_scalar_restart_e16_m8`, SHA256
`870d31e04fd2cd01f9adced45ca94f8033878f45b4e09026dd27a0935625d5a3`.
The last trial marker is seed0/VL512/mask0/vstart256/completed776.
last_pc0x10b1a decodes `vsmul.vx v24,v8,t3,v0.t`; unqualified head
PC0x10b1e is `csrr a0,vstart`. Cycles14017026759 to14537094562 advance,
while retired2770245824, trap_count405131 and the PCs remain fixed.
Both DDR channels have zero outstanding transactions/errors; live halt
flags and watchdog status are clear. The historical cause9 trap does not
establish a VSMUL trap. Internal mask/execution queue state remains unobserved.
`rvv_recovery08_32/terminal_scene` preserves exact ELF/UART/report/snapshots
and disassembly. Five preceding e16/mf4,mf2,m1,m2,m4 ELFs pass201600
configurations, checked against exact references in
`rvv_recovery32_release33_partial02`. This does not accept the stalled m8
ELF or its later operations. Recovery33 retains295 unattempted exact ELFs.

Recovery33 records the vector form `rvv_fixed_restart_e8_m8`, SHA256
`b92d1825415f36a05e9cde9bd865f8ca9d624dd79e45de966889abd7ab4fdbf9`.
The last trial marker is seed0/VL512/mask0/vstart256/completed520.
last_pc0x1094e decodes `vsmul.vv v24,v8,v16,v0.t`; unqualified head
PC0x10952 is `csrr a0,vstart`. Cycles15490351824 to16017603689 advance,
while retired3263699180, trap_count490507 and the PCs remain fixed.
Halt flags/watchdog are clear and both DDR channels have zero outstanding
transactions/errors. Historical cause9 does not prove this instruction
trapped. This independently captures the vector restart/completion boundary;
it does not establish internal queue identity with the scalar scenes.
`rvv_recovery08_33/terminal_scene` preserves exact ELF/UART/report/snapshots
and disassembly. Nine preceding scalar SEW32/64 ELFs pass362880 configurations
(`rvv_recovery33_release33_partial01`). Recovery34 retains285 unattempted
exact ELF identities; later vector operations blocked by this stall stay gaps.

Recovery34 adds `rvv_fixed_restart_e16_m8`, SHA256
`6782a7be8a0a4e15a46f65ddc213245474105f6870ba54dfb750406fe0e35774`.
The last trial marker is seed0/VL512/mask0/vstart256/completed776.
last_pc0x10958 decodes `vsmul.vv v24,v8,v16,v0.t`; unqualified head
PC0x1095c is `csrr a0,vstart`. Cycles12623844843 to13160626666 advance
while retired2033054885, trap_count333341 and PCs stay fixed. Both DDR
channels have zero outstanding transactions/errors, with clear halt flags
and no watchdog halt. Historical cause9 is not proof this VSMUL trapped.
The complete exact-ELF scene is preserved in
`rvv_recovery08_34/terminal_scene`; internal queue attribution is still pending.
Five earlier e16/mf4,mf2,m1,m2,m4 vector ELFs pass53760 configurations,
verified in `rvv_recovery34_release33_partial01`. Later operations in the
stalled m8 ELF remain uncovered. Recovery35 retains279 unattempted exact ELFs.

## TEST-01: Deployment Permissions

The first combined archive lost ELF execute permissions through copyfile.
Board commands returned 126/Permission denied before executing instructions.
This is a host packaging failure, not an RTL finding. combine.py now preserves
mode bits and refuses a non-executable reference ELF. The existing guest
files are reused only after per-ELF hash verification and chmod, avoiding
another unnecessary UART transfer. Original deployment failure evidence is
retained in Windows ara_rvv_additions_20261009_01/deployment_issue.json.

## REF-01: QEMU10.2 Whole-Register Restart Beyond EVL

rvv_whole01/reference_512.log records a QEMU host abort in probe_access_flags.
The installed source's vext_ldst_whole lacks the early vstart>=EVL exit used
by the ordinary unit-stride helper. It computes unsigned elems=evl-vstart;
for vstart>EVL this underflows and an oversized page probe asserts.
The installed reference source is under SDK buildroot/output/build/
host-qemu-10.2.0/target/riscv/vector_helper.c, around line 815.
This is not board evidence and no RTL correction follows from it.
The validated whole-register release excludes >EVL, retains ==EVL where
representable, and records the gap instead of calling it a pass.

## TEST-02: Live-State Signal Oracle ABI Boundary

rvv_context01 initially expected vector state to survive self-kill/yield
syscalls. The syscall ABI permits vector clobber; its failed QEMU outputs
are not hardware findings. The corrected test forks a sender before loading
the live state. A shared ready flag triggers an asynchronous signal while
the parent performs no syscall in the live-state window. The handler clobbers
all 32 vector registers and vcsr, and sigreturn must restore the saved state.
rvv_context02 passes both QEMU VLEN512 and VLEN1024.

## TEST-03: Sticky Flag Parameter Leaked Into Rounding CSR

rvv_fixed01 encoded the initial saturation flag in argument bit 2 but wrote
the entire argument into vxrm. Its scalar model used only the low two bits.
The installed QEMU write_vxrm preserves the full written value, making its
rounding dispatch differ for values 4..7. This is a test input error, not
board evidence. The wrapper now masks the vxrm field explicitly and shifts
the vxsat field separately. Original failed reference reports are retained.

## RVV-03: Whole-Register Move Restart Width

additions05 completes the whole-register suite with exit 1: 1134 trials,
18415 byte/CSR mismatches. Diagnostics identify op16..19 (vmv1r/2r/4r/8r),
configuration modes 1/2/3 (SEW16/32/64); no aggregate failure is printed for
SEW8 or the whole-load instructions. Identical ELFs pass both references.

The test first loads the source as EEW8, then changes architectural SEW
before setting nonzero vstart. Current FPGA dispatcher source chooses its
move EEW and effective length from the stored source-layout metadata. This
is a falsifiable width-scaling hypothesis, not yet a captured byte-level
board cause: distinguish restart at vstart bytes from restart at
vstart*(architectural SEW/8) bytes. The detail release prints the first
mismatched byte addresses without changing RTL. The archived input package
referenced by the deployed bitgen inputs.json has the same dispatch logic;
its collected dispatcher SHA256 is
9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43.
Source is preserved in rvv_new_findings_archived_rtl. additions07 supplies
byte-level confirmation: vmv1r under SEW16 with vstart=1 changes output
byte 33 from sentinel 91 to source byte 1 (40), although the first two
destination bytes must be preserved. With vstart=32, output bytes 64..74
contain source bytes 32..42 although the first 64 destination bytes must
be preserved. Output has a 32-byte prefix guard. These observations match
restart at raw vstart bytes rather than architectural-SEW-scaled bytes.
This confirms the visible restart offset defect; no internal waveform or
repair is included. Evidence: rvv_additions07/board_report.json/board_uart.bin.

## RVV-04: Protected-Page Mask/FOF Scenarios

All four SEWs in additions05 complete with exit 1, 96 child scenarios,
80 failures each. The 16 deliberately faulting first-element FOF children
are correctly recognized as SIGSEGV; the remaining scenario failures are
not expected passes. Kernel evidence includes traps at ordinary and
fault-only-first vector loads with badaddr equal to the protected page.
All identical reference ELFs pass VLEN512/1024.

The original aggregate does not distinguish unexpected signals from
returned VL/output mismatches for each scenario. A new detail release
counts those independently for each of the six scenarios; do not equate
80 failed scenarios with 80 captured unexpected page faults. No exact MMU,
mask or FOF queue-stage cause has been established, and no RTL repair is
included in this coverage campaign.

The additions07 detailed reproduction now distinguishes the outcomes:
for each SEW, scenarios 0/1/2/3/5 each report 16 unexpected signals,
zero nonzero child exits and zero wait failures. Scenario 4, the deliberate
first-element FOF fault, reports zero unexpected signals. Thus all 80
unexpected outcomes per SEW are signal exits, not returned numeric/VL
mismatches. This includes all-off unit and all-off FOF protected-page loads.
The deployed MMU/FOF path still needs cycle-level attribution before repair;
the signal counters alone do not identify an internal queue stage.

Evidence for both new findings: rvv_additions05/board_report.json and
board_uart.bin under the unchanged-image campaign evidence directory.

Recovery11's immutable `resume/board_report_live04.json` additionally
records all four NF2/m1 segment fault-replay widths completing with exit1:
each reports96 configurations,96 signals and64 errors. Identical additions52
ELFs pass both reference VLENs with96 configurations,72 repaired signals
and zero errors. The signal counter counts actual handler entries; the
error counter includes trap metadata, returned vstart, memory and result
checks, so64 errors are not64 distinct faults. This is a related protected-page
replay symptom to retain, not proof that every extra signal shares RVV-04's
internal cause. Phase-specific diagnostics are still needed to separate
all-off faults, trap metadata and replay-result errors. Ordinary failures
continue to later shapes; no RTL modification or board restart was made.

Recovery12 also fully executes additions54's108 positive-strided shapes:
all exit1. Exact released hashes and both VLEN references are bound in
`rvv_recovery12_release54_results01/summary.json` under the campaign directory.
All22 NF1 shapes report96 cases/96 signals/64 errors, versus96/72/0 in
references. Of86 segmented shapes,85 report192/192/128, versus192/144/0.
`rvv_fault_replay_segment_nf8_strided_e32_mf2` reports192/192/169 instead;
its ELF SHA256 is
`c90e2ac2ab90fba392ca887842ce07c78244405ef41428f7e8f760373e658282`.
Preserve this distinct additional-error pattern rather than flattening
all failures into the common128-error group. The aggregate does not yet
locate those extra41 errors or prove a shared RTL cause. Execution continues
normally into negative-stride coverage without modifying the current image.

Additions55's108 negative-strided cases subsequently all finish with exit1.
The independent release audit is `rvv_recovery12_release55_results01`:
22 NF1 shapes report96/96/64 and86 segmented shapes report192/192/128
(cases/signals/errors). In particular, the negative-stride NF8/e32/mf2
shape has128 errors, not the positive-stride run's169. This is a measured
direction/ELF-specific difference, not proof that direction alone causes
the additional errors. The positive-stride outlier has not been rerun or
reclassified. Both groups remain failures; indexed segment tests proceed
without a board reset.

## RVV-05: Legal m8 Widening FP Reduction Rejected

additions06 completes all 54 ELFs: 53 pass, while
rvv_reduction_fpwide_e32_m8 exits 132 (SIGILL). The kernel reports cause 2,
epc 0x10480 and instruction 0xcc881c57. Disassembly identifies
vfwredosum.vs v24,v8,v16,v0.t, after vsetvli e32,m8. Source v8 is m8-aligned;
seed v16 and destination v24 are single-register scalar operands. Identical
ELFs pass both VLEN512 and VLEN1024 references. This first failure prevents
the remaining operations in that ELF from executing; they are not passes.

The archived deployed dispatcher assigns next_lmul(m8), i.e. LMUL_RSVD,
to ara_req.emul for both VFWREDUSUM and VFWREDOSUM (lines 3654/3672).
Its common FP destination legality case then unconditionally sets
illegal_insn for LMUL_RSVD (around line 3766), unlike the alignment cases
which already exempt single-register results. This is a concrete decode
rejection path matching the observed illegal instruction. Widening
reduction output/seed are scalar register operands, not an EMUL=16 vector
destination. A future fix must also audit downstream reduction execution
semantics; merely suppressing this rejection is not validated here.

Evidence: rvv_additions06/board_report.json and board_uart.bin;
rvv_new_findings_archived_rtl/ara_dispatcher.sv, SHA256
9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43.
No RTL changes or rebuilds were performed for this finding.

## RVV-06: Legal High-End Extension Overlap Stalls

Recovery95 snapshot01 completes the remaining12 ordinary zero/sign
extension partitions for the six selected m8 shapes:1008 configurations,
all passed. Combined with recovery94, all28 ordinary op0/op1 children
pass2352 configurations. Exact-ELF/reference/protocol audit:
`rvv_extension_partition_board_audit95_partial01`, immutable snapshot
`rvv_recovery95_active_snapshot01.json`. The next signed overlap
e16/m4/vf2 child is running and excluded. Ordinary-operation passes do
not validate overlap or supersede the14 original blocked parent ELFs.

Recovery94 isolates the14 blocked parent shapes into56 operation partitions.
The first16 completed children, ordinary zero/sign extension (`op0`/`op1`)
for all eight non-m8 selected shapes, pass1344 configurations on the FPGA.
Exact-ELF/reference and nonce-protocol audit:
`rvv_extension_partition_board_audit94_partial01`, with immutable snapshot
`rvv_recovery94_active_snapshot01.json`. Terminal audit
`rvv_extension_partition_board_audit94_terminal01` confirms the same16
passes. The high-end overlapping signed e16/m2/vf2 partition (`op3`)
then stalls; selected m8 shapes and all overlap partitions remain
unaccepted by these results.
These child passes do not replace the original full-ELF stall records.

Recovery94 terminal scene preserves the exact op3 ELF (SHA256
cbf7707645a5249e99751c841ada2b9d14926c3f8c5f19dffdc04d385c07d76b).
All20 archived scene hashes were independently verified. Two snapshots
show cycles12061269018 ->12605214346 while retired1776168510,
trap_count288360 and both PCs remain unchanged. last_pc0x1049e is
`vsetvli t0,a3,e16,m2,tu,mu`; head_pc0x104a2 disassembles to
`vsext.vf2 v24,v25,v0.t`. Neither snapshot is watchdog-halted, live
flags are0, and both DDR channels have0 outstanding reads/writes and0
response errors. This isolates signed high-end overlap separately from
the original zero-extension stall; it does not prove an internal queue
root cause or the exact current VL/mask. No RTL repair is claimed.
Evidence: `rvv_recovery08_94/terminal_scene`. Recovery95 preserves all67
unexecuted partition names/hashes; unified inventory
`rvv_partition_inventory03` records58 passed,46 numerical failures,
5 stalls and67 unattempted, without superseding parent ELF outcomes.

Recovery95 also confirms signed high-end overlap e16/m4/vf2 stalls:
`rvv_extension_e16_m4_vf2_ops3`, SHA256
727dbc08558f4475ac0aa89d900dbdaa72082e097e3b63699a6b516e1527b097.
All20 scene hashes verify in `rvv_recovery08_95/terminal_scene`. Cycles
12566223624 ->13108085950 advance while retired2050369356,
trap_count315543 and PCs remain fixed. Last retired0x104a2 is
`vsetvli t0,a3,e16,m4,tu,mu`; head0x104a6 disassembles to
`vsext.vf2 v24,v26,v0.t`. Both samples are unhalted with flags0 and
both DDR channels have0 outstanding transactions and0 response errors.
This is a separate m4 reproduction, not proof that every overlap shape
stalls or that a particular internal dependency is responsible.
Recovery96 retains the52 unexecuted partitions. Unified terminal
inventory `rvv_partition_inventory05` records72 passed,46 numerical
failures,6 stalls and52 never attempted;118 have completed numerical
results. Original parent outcomes remain unchanged.

Recovery96 extends the signed-overlap stall evidence to e32/m2/vf2:
`rvv_extension_e32_m2_vf2_ops3`, SHA256
bdbfa14a994e3304be13232990c1de8896576bc10d11fb4766ff8fe94edcc853.
All20 hashes verify in `rvv_recovery08_96/terminal_scene`. Two snapshots
show cycles11356225636 ->11879852022 with retired1640674174,
trap_count239817 and PCs fixed. Last retired0x104b8 is
`vsetvli t0,a3,e32,m2,tu,mu`; head0x104bc disassembles to
`vsext.vf2 v24,v25,v0.t`, with source EEW16/m1. Both samples are
unhalted, flags0, and both DDR channels have0 outstanding reads/writes
and0 response errors. This is not restricted to source EEW8, but the
active VL/mask and internal dependency cause remain unproven.
Recovery97 preserves all51 remaining partitions. Terminal inventory
`rvv_partition_inventory06` has72 passed,46 numerical failures,
7 stalls and51 never attempted; no original result is superseded.

Recovery97's observer first stops as incomplete because the snapshot command
fails during owned Windows process-tree cleanup, after writing snapshot data.
The cleanup output reports a disappeared child PID while its parent is killed;
this host error alone is not stall evidence. The immutable observer report is
`rvv_recovery97_observer_incomplete01.json`. With the observer/wrapper stopped,
two independent read-only snapshots succeed (`manual_progress_0001/0002`).
They show cycles18162810506 ->18860147167 with retired1640165326,
trap_count239213 and PCs fixed; both are unhalted with flags0 and both DDR
channels have0 outstanding transactions/errors. The independently verified
stall report is `rvv_recovery97_verified_stall01.json`, with source hashes,
not an overwrite of the original observer result.

The affected ELF is `rvv_extension_e32_m4_vf2_ops3`, SHA256
b365416a9332e3d186369f7c1b2109c340740488a986c9e736b2ecd12fe03768.
Last retired0x104bc is `vsetvli t0,a3,e32,m4,tu,mu`; head0x104c0
disassembles to `vsext.vf2 v24,v26,v0.t`. The terminal scene preserves the
failed capture and both successful follow-ups, all28 file hashes verified.
Recovery98 retains50 remaining partitions after the confirmed stall. The
old launcher's default prioritized-count assertion stopped preparation after
archival; a separate verified-scene finish uses the same preparation gates
and exact pending-name/hash checks, without changing the immutable archive.
`rvv_partition_inventory07` records72 passed,46 numerical failures,
8 confirmed stalls and50 never attempted. Internal dependency cause remains
unproven; no RTL or process-cleanup repair is claimed by this recovery.

Recovery98 confirms signed high-end overlap at factor4 also stalls:
`rvv_extension_e32_m4_vf4_ops3`, SHA256
26e9a2c4fbdd2643b71241b854b4719d7369ecd9494ba1a1df525a7a0f0108e4.
All20 archived hashes verify in `rvv_recovery08_98/terminal_scene`.
Cycles11379787848 ->11961568749 advance with retired1640366639,
trap_count239521 and PCs fixed. Last retired0x104b8 is
`vsetvli t0,a3,e32,m4,tu,mu`; head0x104bc disassembles to
`vsext.vf4 v24,v27,v0.t` (source EEW8/m1). Both samples have0 DDR
outstanding reads/writes and0 response errors. This extends the captured
overlap symptoms beyond factor2, without proving an internal cause.
Recovery99 preserves49 pending partitions. Its new observer includes the
bounded read-only snapshot-pair retry for the observed cleanup error; source
identity was checked against `batch_serial.py`,124 host tests pass, and the
two-successful-snapshot retirement gate is unchanged. No running observer
was modified. `rvv_partition_inventory08` records72 passed,46 numerical
failures,9 stalls and49 never attempted; whole coverage remains incomplete.

Recovery99 confirms signed high-end overlap e64/m2/vf2 also stalls:
`rvv_extension_e64_m2_vf2_ops3`, SHA256
23f1593606746fa8cab474dfa5d56681f9bc1b8e72b3b077f9ad367835b7083c.
All20 archived hashes verify in `rvv_recovery08_99/terminal_scene`.
Cycles11355150127 ->11895454924 advance while retired1639909848,
trap_count239296 and PCs remain fixed. Last retired0x104ce is
`vsetvli t0,a3,e64,m2,tu,mu`; head0x104d2 disassembles to
`vsext.vf2 v24,v25,v0.t`, source EEW32/m1. Both DDR channels show0
outstanding transactions and0 response errors in both samples. This extends
the captured signed-overlap symptoms to destination SEW64/source EEW32;
the exact active VL/mask and internal cause remain unproven. Recovery100
preserves48 pending partitions. `rvv_partition_inventory09` records72
passed,46 numerical failures,10 stalls and48 never attempted. No parent
outcome is replaced and no RTL repair is claimed.

Recovery100 confirms signed high-end overlap e64/m4/vf2 stalls:
`rvv_extension_e64_m4_vf2_ops3`, SHA256
fea5474ff321fda60356bf433693258d081c07c1d90fdd6ecdf3d8a6a9b21cf0.
All34 archived file hashes verify in `rvv_recovery08_100/terminal_scene`.
Capture0001 succeeds,0002 fails during cleanup, and the bounded whole-pair
retry collects0003/0004 successfully. The accepted diagnosis uses only
0003/0004; the failed capture remains archived. Thus the new host retry
has real campaign evidence, not only unit tests, without weakening the gate.
Cycles12475251623 ->13006974398 advance while retired1641083397,
trap_count240518 and PCs remain fixed. Last retired0x104d2 is
`vsetvli t0,a3,e64,m4,tu,mu`; head0x104d6 disassembles to
`vsext.vf2 v24,v26,v0.t`, source EEW32/m2. Both DDR channels show0
outstanding transactions and0 response errors in both accepted samples.
`rvv_partition_inventory10` records72 passed,46 numerical failures,
11 stalls and47 never attempted. The remaining47 are preserved for the
next recovery; no RTL fix or original-parent acceptance is implied.

Recovery101 confirms signed high-end overlap e64/m4/vf4 stalls:
`rvv_extension_e64_m4_vf4_ops3`, SHA256
14d618187fbd7534e6e1f03e6185b52d0d035d530b1dfdcc44ad7b198127e715.
All20 archived file hashes verify in `rvv_recovery08_101/terminal_scene`.
Cycles11323885337 ->11865692781 advance while retired1639331909,
trap_count238973 and PCs remain fixed. Last retired0x104be is
`vsetvli t0,a3,e64,m4,tu,mu`; unqualified head0x104c2 disassembles to
`vsext.vf4 v24,v27,v0.t`, source EEW16/m1. Both accepted snapshots
have clear halt flags and zero outstanding transactions and response
errors on both DDR channels. Active VL/mask and internal cause remain
unobserved. `rvv_partition_inventory11` records72 passed,46 numerical
failures,12 stalls and46 never attempted. Recovery102 preserves the
exact46 pending case records; no original-parent acceptance is implied.

Recovery102 confirms zero-extension high-end overlap e16/m2/vf2 stalls:
`rvv_extension_e16_m2_vf2_ops2`, SHA256
c1ec11fdf1017888415fef6ff467b84594f3454efcb7bb1174d8ce36137ad7e1.
All20 archived file hashes verify in `rvv_recovery08_102/terminal_scene`.
Cycles11320585698 ->11884670636 advance while retired1639119353,
trap_count238808 and PCs remain fixed. Last retired0x1046c is
`vsetvli t0,a3,e16,m2,tu,mu`; unqualified head0x10470 disassembles to
`vzext.vf2 v24,v25,v0.t`, source EEW8/m1. Both samples have clear halt
flags, no watchdog snapshot, and zero outstanding transactions and
response errors on both DDR channels. Active VL/mask and internal cause
remain unobserved. `rvv_partition_inventory12` records72 passed,
46 numerical failures,13 stalls and45 never attempted. Recovery103
preserves the exact45 pending records without changing RTL or acceptance.

Recovery103 confirms zero-extension high-end overlap e16/m4/vf2 stalls:
`rvv_extension_e16_m4_vf2_ops2`, SHA256
9ce0768af802021e796732158a5ae29ef7a22c526bf781b64e7593a1745682b7.
All23 archived file hashes verify in `rvv_recovery08_103/terminal_scene`.
Cycles11334447905 ->11887910501 advance while retired1639551662,
trap_count238810 and PCs remain fixed. Last retired0x10470 is
`vsetvli t0,a3,e16,m4,tu,mu`; unqualified head0x10474 disassembles to
`vzext.vf2 v24,v26,v0.t`, source EEW8/m2. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory13` records72 passed,
46 numerical failures,14 stalls and44 never attempted. Recovery104
preserves the exact44 pending records; this does not accept original parents.

Recovery104 confirms zero-extension high-end overlap e32/m2/vf2 stalls:
`rvv_extension_e32_m2_vf2_ops2`, SHA256
f3b34a892da2163e94526ddca3b41e559b9cc68be7207b3c667a676bfe0e3580.
All20 archived file hashes verify in `rvv_recovery08_104/terminal_scene`.
Cycles11322306820 ->11858002681 advance while retired1638284638,
trap_count238711 and PCs remain fixed. Last retired0x1048c is
`vsetvli t0,a3,e32,m2,tu,mu`; unqualified head0x10490 disassembles to
`vzext.vf2 v24,v25,v0.t`, source EEW16/m1. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory14` records72 passed,
46 numerical failures,15 stalls and43 never attempted. Recovery105
preserves the exact43 pending records; no original-parent acceptance is implied.

Recovery105 confirms zero-extension high-end overlap e32/m4/vf2 stalls:
`rvv_extension_e32_m4_vf2_ops2`, SHA256
69807c916ca606c3c93cb18fa1b3ff65ffdf93db7a0a7469fb9de782496b1060.
All20 archived file hashes verify in `rvv_recovery08_105/terminal_scene`.
Cycles11365471786 ->11903304442 advance while retired1639715538,
trap_count240484 and PCs remain fixed. Last retired0x10490 is
`vsetvli t0,a3,e32,m4,tu,mu`; unqualified head0x10494 disassembles to
`vzext.vf2 v24,v26,v0.t`, source EEW16/m2. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory15` records72 passed,
46 numerical failures,16 stalls and42 never attempted. Recovery106
preserves the exact42 pending records; no original-parent acceptance is implied.

Recovery106 confirms zero-extension high-end overlap e32/m4/vf4 stalls:
`rvv_extension_e32_m4_vf4_ops2`, SHA256
458ca3c2cc47682d5316966024303005911a1456debc92c3a0bdf803ef79c736.
All20 archived file hashes verify in `rvv_recovery08_106/terminal_scene`.
Cycles16533674595 ->17069824066 advance while retired1809090623,
trap_count440089 and PCs remain fixed. Last retired0x1048c is
`vsetvli t0,a3,e32,m4,tu,mu`; unqualified head0x10490 disassembles to
`vzext.vf4 v24,v27,v0.t`, source EEW8/m1. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory16` records72 passed,
46 numerical failures,17 stalls and41 never attempted. Recovery107
preserves the exact41 pending records; no original-parent acceptance is implied.

Recovery107 confirms zero-extension high-end overlap e64/m2/vf2 stalls:
`rvv_extension_e64_m2_vf2_ops2`, SHA256
3d9cdc996536457da9db65b22ef6a2c3176a6edcf1989278d3c2df7d2143c812.
All34 archived file hashes verify in `rvv_recovery08_107/terminal_scene`.
Capture0001 succeeds,0002 fails in owned-tree cleanup, and the bounded
whole-pair retry succeeds with0003/0004. The accepted diagnosis matches
only0003/0004; the failed capture remains archived.
Cycles12432369507 ->12973372336 advance while retired1637195111,
trap_count238383 and PCs remain fixed. Last retired0x104a4 is
`vsetvli t0,a3,e64,m2,tu,mu`; unqualified head0x104a8 disassembles to
`vzext.vf2 v24,v25,v0.t`, source EEW32/m1. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory17` records72 passed,
46 numerical failures,18 stalls and40 never attempted. Recovery108
preserves the exact40 pending records; no original-parent acceptance is implied.

Recovery108 confirms zero-extension high-end overlap e64/m4/vf2 stalls:
`rvv_extension_e64_m4_vf2_ops2`, SHA256
e94b888cc8957b7c6117489b65f22eec48d254186ea07e6c9335bb0f42d75ecc.
All20 archived file hashes verify in `rvv_recovery08_108/terminal_scene`.
Cycles11323698282 ->11905413281 advance while retired1638143679,
trap_count238946 and PCs remain fixed. Last retired0x104a8 is
`vsetvli t0,a3,e64,m4,tu,mu`; unqualified head0x104ac disassembles to
`vzext.vf2 v24,v26,v0.t`, source EEW32/m2. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory18` records72 passed,
46 numerical failures,19 stalls and39 never attempted. Recovery109
preserves the exact39 pending records; no original-parent acceptance is implied.

Recovery109 confirms zero-extension high-end overlap e64/m4/vf4 stalls:
`rvv_extension_e64_m4_vf4_ops2`, SHA256
4e2acda8efd3eede1f57fb7281a316b8229d35e913499b031863ac6b8cb50270.
All20 archived file hashes verify in `rvv_recovery08_109/terminal_scene`.
Cycles11348967501 ->11895316941 advance while retired1638344110,
trap_count239534 and PCs remain fixed. Last retired0x10492 is
`vsetvli t0,a3,e64,m4,tu,mu`; unqualified head0x10496 disassembles to
`vzext.vf4 v24,v27,v0.t`, source EEW16/m1. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory19` records72 passed,
46 numerical failures,20 stalls and38 never attempted. Recovery110
preserves the exact38 pending records; no original-parent acceptance is implied.

Recovery110 confirms signed-extension high-end overlap e16/m8/vf2 stalls:
`rvv_extension_e16_m8_vf2_ops3`, SHA256
cbabc892d0bbd6c7df51128f8eee2a281d71ba0aa37596da47dc12ef8f193c52.
All20 archived file hashes verify in `rvv_recovery08_110/terminal_scene`.
Cycles11336577162 ->11863062239 advance while retired1637709943,
trap_count239074 and PCs remain fixed. Last retired0x104a2 is
`vsetvli t0,a3,e16,m8,tu,mu`; unqualified head0x104a6 disassembles to
`vsext.vf2 v24,v28,v0.t`, source EEW8/m4. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory20` records72 passed,
46 numerical failures,21 stalls and37 never attempted. Recovery111
preserves the exact37 pending records; no original-parent acceptance is implied.

Recovery111 confirms signed-extension high-end overlap e32/m8/vf2 stalls:
`rvv_extension_e32_m8_vf2_ops3`, SHA256
bcb4e2854413e25315323ef57ed5a114a5328f644ee7a863c83bcba6deeb7a18.
All20 archived file hashes verify in `rvv_recovery08_111/terminal_scene`.
Cycles11310521939 ->11845764925 advance while retired1636706582,
trap_count237862 and PCs remain fixed. Last retired0x104bc is
`vsetvli t0,a3,e32,m8,tu,mu`; unqualified head0x104c0 disassembles to
`vsext.vf2 v24,v28,v0.t`, source EEW16/m4. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory21` records72 passed,
46 numerical failures,22 stalls and36 never attempted. Recovery112
preserves the exact36 pending records; no original-parent acceptance is implied.

Recovery112 confirms signed-extension high-end overlap e32/m8/vf4 stalls:
`rvv_extension_e32_m8_vf4_ops3`, SHA256
a3315852d99f9693be12a6b095d9150860fb7db66f5892425d8cf79f8ec0d21d.
All23 archived file hashes verify in `rvv_recovery08_112/terminal_scene`.
Cycles11350279846 ->11933056909 advance while retired1635419091,
trap_count237418 and PCs remain fixed. Last retired0x104b8 is
`vsetvli t0,a3,e32,m8,tu,mu`; unqualified head0x104bc disassembles to
`vsext.vf4 v24,v30,v0.t`, source EEW8/m2. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory22` records72 passed,
46 numerical failures,23 stalls and35 never attempted. Recovery113
preserves the exact35 pending records; no original-parent acceptance is implied.

Recovery113 confirms signed-extension high-end overlap e64/m8/vf2 stalls:
`rvv_extension_e64_m8_vf2_ops3`, SHA256
711a9743f7a5952561fef9ea55341d869b7905d98865fa3ab6a58a10eb5361ed.
All20 archived file hashes verify in `rvv_recovery08_113/terminal_scene`.
Cycles11349283925 ->11909919779 advance while retired1636348612,
trap_count238038 and PCs remain fixed. Last retired0x104d2 is
`vsetvli t0,a3,e64,m8,tu,mu`; unqualified head0x104d6 disassembles to
`vsext.vf2 v24,v28,v0.t`, source EEW32/m4. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory23` records72 passed,
46 numerical failures,24 stalls and34 never attempted. Recovery114
preserves the exact34 pending records; no original-parent acceptance is implied.

Recovery114 confirms signed-extension high-end overlap e64/m8/vf4 stalls:
`rvv_extension_e64_m8_vf4_ops3`, SHA256
2b50d4997b342b65026a339145f93fd743dad1247378b469ce9c5528e2f8034a.
All20 archived file hashes verify in `rvv_recovery08_114/terminal_scene`.
Cycles11340194261 ->11905779224 advance while retired1636170311,
trap_count238512 and PCs remain fixed. Last retired0x104be is
`vsetvli t0,a3,e64,m8,tu,mu`; unqualified head0x104c2 disassembles to
`vsext.vf4 v24,v30,v0.t`, source EEW16/m2. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory24` records72 passed,
46 numerical failures,25 stalls and33 never attempted. Recovery115
preserves the exact33 pending records; no original-parent acceptance is implied.

Recovery115 confirms signed-extension high-end overlap e64/m8/vf8 stalls:
`rvv_extension_e64_m8_vf8_ops3`, SHA256
27f78d21712136de2450bf9347495739ccf2f099d37cd023d2277903dff502d8.
All20 archived file hashes verify in `rvv_recovery08_115/terminal_scene`.
Cycles11319356131 ->11867824450 advance while retired1635238751,
trap_count237573 and PCs remain fixed. Last retired0x104b8 is
`vsetvli t0,a3,e64,m8,tu,mu`; unqualified head0x104bc disassembles to
`vsext.vf8 v24,v31,v0.t`, source EEW8/m1. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory25` records72 passed,
46 numerical failures,26 stalls and32 never attempted. Recovery116
preserves the exact32 pending records; no original-parent acceptance is implied.
All14 released signed high-end-overlap shapes have now stalled, whereas
all14 ordinary signed shapes passed. The zero-extension overlap subgroup
still has6 unattempted m8 shapes; this comparison is not an internal RTL
root-cause proof or complete internal-trial coverage of the stalled ELFs.

Recovery116 confirms zero-extension high-end overlap e16/m8/vf2 stalls:
`rvv_extension_e16_m8_vf2_ops2`, SHA256
ba7777606273ee9c36bbcf07cd4f24aa88173f19c1bb0ecb724670702fa6e614.
All20 archived file hashes verify in `rvv_recovery08_116/terminal_scene`.
Cycles11300768510 ->11896289818 advance while retired1635054922,
trap_count237415 and PCs remain fixed. Last retired0x10470 is
`vsetvli t0,a3,e16,m8,tu,mu`; unqualified head0x10474 disassembles to
`vzext.vf2 v24,v28,v0.t`, source EEW8/m4. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory26` records72 passed,
46 numerical failures,27 stalls and31 never attempted. Recovery117
preserves the exact31 pending records; no original-parent acceptance is implied.

Recovery117 confirms zero-extension high-end overlap e32/m8/vf2 stalls:
`rvv_extension_e32_m8_vf2_ops2`, SHA256
b7a3698b248275c91d55fed1fc4e9177712035e7dfb4189ceeb632fe53771cf1.
All20 archived file hashes verify in `rvv_recovery08_117/terminal_scene`.
Cycles11294778786 ->11891006856 advance while retired1634724277,
trap_count237450 and PCs remain fixed. Last retired0x10490 is
`vsetvli t0,a3,e32,m8,tu,mu`; unqualified head0x10494 disassembles to
`vzext.vf2 v24,v28,v0.t`, source EEW16/m4. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory27` records72 passed,
46 numerical failures,28 stalls and30 never attempted. Recovery118
preserves the exact30 pending records; no original-parent acceptance is implied.

Recovery118, after cleanup-only startup reattachment without another reset,
confirms zero-extension high-end overlap e32/m8/vf4 stalls:
`rvv_extension_e32_m8_vf4_ops2`, SHA256
d190fc1b86db399b9035c0e9dd3e5cf7115b4719cf1a466293872422a2958382.
All20 archived file hashes verify in `rvv_recovery08_118/terminal_scene`.
Cycles16340733232 ->16872385064 advance while retired1798030074,
trap_count429931 and PCs remain fixed. Last retired0x1048c is
`vsetvli t0,a3,e32,m8,tu,mu`; unqualified head0x10490 disassembles to
`vzext.vf4 v24,v30,v0.t`, source EEW8/m2. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory28` records72 passed,
46 numerical failures,29 stalls and29 never attempted. Recovery119
preserves the exact29 pending records; no original-parent acceptance is implied.

Recovery119 confirms zero-extension high-end overlap e64/m8/vf2 stalls:
`rvv_extension_e64_m8_vf2_ops2`, SHA256
7f68dda10bf3c07d95d4ac44441289a0e6f66e266489c70ed71985ceabf6ff1e.
All20 archived file hashes verify in `rvv_recovery08_119/terminal_scene`.
Cycles11304074095 ->11905961598 advance while retired1634781474,
trap_count237458 and PCs remain fixed. Last retired0x104a8 is
`vsetvli t0,a3,e64,m8,tu,mu`; unqualified head0x104ac disassembles to
`vzext.vf2 v24,v28,v0.t`, source EEW32/m4. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory29` records72 passed,
46 numerical failures,30 stalls and28 never attempted. Recovery120
preserves the exact28 pending records; no original-parent acceptance is implied.

Recovery120 confirms zero-extension high-end overlap e64/m8/vf4 stalls:
`rvv_extension_e64_m8_vf4_ops2`, SHA256
ae59d86573e6ebe0c01d4cbaf3732be423685865d6f499bfefe9fa1044399ea4.
All20 archived file hashes verify in `rvv_recovery08_120/terminal_scene`.
Cycles11271701787 ->11815605886 advance while retired1633536003,
trap_count236854 and PCs remain fixed. Last retired0x10492 is
`vsetvli t0,a3,e64,m8,tu,mu`; unqualified head0x10496 disassembles to
`vzext.vf4 v24,v30,v0.t`, source EEW16/m2. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory30` records72 passed,
46 numerical failures,31 stalls and27 never attempted. Recovery121
preserves the exact27 pending records; no original-parent acceptance is implied.

Recovery121 confirms zero-extension high-end overlap e64/m8/vf8 stalls:
`rvv_extension_e64_m8_vf8_ops2`, SHA256
6d86f5393700da189fae35479e3151b346d9a42cec523fc40d7ba95585bbc223.
All20 archived file hashes verify in `rvv_recovery08_121/terminal_scene`.
Cycles11293320610 ->11864148692 advance while retired1632956211,
trap_count236337 and PCs remain fixed. Last retired0x1048c is
`vsetvli t0,a3,e64,m8,tu,mu`; unqualified head0x10490 disassembles to
`vzext.vf8 v24,v31,v0.t`, source EEW8/m1. Both accepted samples have
clear halt flags, no watchdog snapshot, and zero outstanding transactions
and response errors on both DDR channels. Active VL/mask and internal
cause remain unobserved. `rvv_partition_inventory31` records72 passed,
46 numerical failures,32 stalls and26 never attempted. Recovery122
preserves the exact26 pending FP-move records.
The complete56-ELF extension partition membership now has28 ordinary
passes (14 zero,14 signed) and28 high-end-overlap stalls (14 zero,14 signed).
This completes attempts, not internal numerical trials of stalled ELFs,
original-parent acceptance or an internal RTL root-cause proof.

additions08 passes its first three ELFs, then rvv_extension_e16_m2_vf2
stalls with no retirement. Both references pass the identical ELF. The
deployed board's two snapshots show 561352265 additional cycles while
retired remains 35878544937 and both PCs/trap count are unchanged. Neither
sample is watchdog-halted and live flags are zero.

last_pc=0x1047e is vsetvli e16,m2; head_pc=0x10482 is instruction
0x49932c57, vzext.vf2 v24,v25,v0.t. The test intentionally uses source
EEW8/EMUL1 in the high-end v25 register of destination v24..v25 EMUL2,
which is a legal widening overlap. This is vstart=0 and is not evidence
that the older nonzero-restart mask stall is its cause. Exact scalar VL,
predicate and internal queue state have not been captured; do not invent
them from the last retired PC. No pipeline repair is claimed.

Evidence: rvv_additions08/board_report.json and board_uart.bin;
progress_b599fc1664a1 and progress_629ca67db0c7 contain snapshot.json and
Vivado diagnostics. Three passing ELFs contribute 504 configurations;
the stalled ELF's internal partial work is not counted as passed coverage.

The corrected recovery04 preload succeeds and Linux reports freeing 10392
KiB of initrd. Its first pending ELF, `rvv_extension_e16_m4_vf2`, then also
stalls. Two snapshots advance cycles from 11840591735 to 12418423929 while
retired stays 1692494324; trap_count stays 270923, live flags are zero and
neither sample is watchdog-halted. last_pc=0x10482 is vsetvli e16,m4;
head_pc=0x10486 is `vzext.vf2 v24,v26,v0.t` (0x49a32c57). Source EMUL2
occupies v26..v27, the high end of destination EMUL4 v24..v27. This confirms
a second legal overlap shape with no retirement, not an inferred internal
queue cause or a passed continuation. No other ELF executed in recovery04.
Evidence: `rvv_recovery08_04/resume/board_report.json`, board_uart.bin and
both progress snapshot directories. Recovery05 preserves this report and
puts independent queued families before the remaining overlap cases.

Recovery05 completes all 160 independent additions09..17 cases before
the next pending overlap ELF, `rvv_extension_e16_m8_vf2`, stalls. Live
cycles advance from 115644684284 to 116199040816 while retired remains
22668294830 and trap_count remains 6690967. Both snapshots have live
flags0, no watchdog halt, zero DDR outstanding transactions and zero
DDR errors. last_pc=0x10482 is vsetvli e16,m8; head_pc=0x10486 is
`vzext.vf2 v24,v28,v0.t` (0x49c32c57). Source EEW8/EMUL4 occupies
v28..v31, the legal high end of destination EMUL8 v24..v31. This is a
third observed legal overlap shape, not proof of the internal queue cause.
Evidence: `rvv_recovery08_05/resume/board_report.json`, board_uart.bin,
progress_a8291918bc3b and progress_d79b5fb6116c, plus the immutable ELF.
The observer stops after confirming no retirement instead of waiting
for the full case timeout. Recovery06 skips these 161 attempted cases,
preloads 314 never-attempted ELFs and retains every preceding failure.

Recovery06 completes all 254 independent additions18..25 and four more
extension cases, then `rvv_extension_e32_m2_vf2` stalls. Snapshots advance
cycles from 154525222791 to 155081829387 while retired remains 19310008454
and trap_count remains 9318174. Both have live flags0, no watchdog halt,
zero outstanding DDR transactions and zero DDR errors. last_pc=0x1049c
is vsetvli e32,m2; head_pc=0x104a0 is `vzext.vf2 v24,v25,v0.t`
(0x49932c57). Source EEW16/EMUL1 occupies v25 at the legal high end of
destination EEW32/EMUL2 v24..v25. This extends the observed failure to
SEW32; it does not identify the exact blocked internal queue.
Evidence: `rvv_recovery08_06/resume/report.json`, uart.bin,
progress_229c971f08a4 and progress_e142cea3d682, and the immutable ELF.
The report has 258 passes, one stall and 55 never-attempted cases.

Recovery21 adds `rvv_extension_e32_m4_vf2`, SHA256
`0c4a9b9ffd7664de4385deb89fc54d48c82a47a7fd32df8d1aebb3c35fd1db2f`.
last_pc0x104a0 is `vsetvli e32,m4`; the unqualified head PC0x104a4
decodes `vzext.vf2 v24,v26,v0.t`. Source EEW16/EMUL2 occupies v26..v27
at the legal high end of destination EMUL4 v24..v27. Cycles11945984791
to12477094712 advance while retired1754993576,trap_count280630 and PCs
remain fixed. Both DDR channels have zero outstanding transactions/errors;
halt flags and watchdog status are clear. Exact VL/predicate and internal
queue state are unobserved, and head-PC is not a valid-request signal.
The preceding `rvv_extension_e32_m2_vf4` passes168 configurations with
exact reference-marker equality (`rvv_recovery21_release08_partial01`).
`rvv_recovery08_21/terminal_scene` preserves the new exact ELF, full
UART/report/snapshots/disassembly and hashes. Recovery22 retains355
unattempted exact ELFs and additionally defers extension overlap cases,
without deleting them or claiming the broader extension suite passes.

Recovery22 separately records `rvv_extension_e32_m4_vf4`, SHA256
`d4ebc3c636ffce4e4a5dda670f13a7c21ed92209ec543b2620291d0dff57d473`.
last_pc0x104a4 is `vsetvli e32,m4`; unqualified head PC0x104a8 decodes
`vzext.vf4 v24,v27,v0.t`. Source EEW8/EMUL1 occupies the high-end v27
of destination EMUL4 v24..v27. Cycles23809066775 to24333570196 advance
while retired7973204739,trap_count907243 and PCs stay fixed. Both DDR
channels have zero outstanding transactions/errors; halt flags and watchdog
status are clear. Actual VL/predicate and internal queue state are unobserved.
`rvv_recovery08_22/terminal_scene` preserves the independent exact ELF,
UART/report/snapshots/disassembly and hashes. This extends the observed
legal-overlap boundary to vf4, not an independently proven common RTL cause.
Its38 preceding ELF passes belong to separate narrow/FP/segment source
subgroups; they do not accept this stalled ELF. Recovery23 retains316
unattempted exact ELFs without rerunning completed cases.

Recovery23 adds `rvv_extension_e32_m8_vf2`, SHA256
`edb20a459ccc2c4cbcfc2d1826047116e67ce2f543071da3538ffa3726f68353`.
last_pc0x104a0 is `vsetvli e32,m8`; unqualified head PC0x104a4 decodes
`vzext.vf2 v24,v28,v0.t`. Source EEW16/EMUL4 occupies v28..v31 at
the legal high end of destination EMUL8 v24..v31. Cycles11856854805
to12380733048 advance while retired1734011087,trap_count273812 and PCs
remain fixed. Both DDR channels have zero outstanding transactions/errors;
halt flags and watchdog status are clear. No exact VL/predicate or internal
queue state is captured. `rvv_recovery08_23/terminal_scene` preserves the
exact ELF and complete diagnostic artifacts. Recovery24 retains315
unattempted exact ELFs; the failed ELF is not numerically accepted.

Recovery24 independently records `rvv_extension_e32_m8_vf4`, SHA256
`4fe7d39ddab2efcea490c20cc7bf511a52b1f85e37596e511dfaff11db090794`.
last_pc0x104a4 is `vsetvli e32,m8`; unqualified head PC0x104a8 decodes
`vzext.vf4 v24,v30,v0.t`. Source EEW8/EMUL2 occupies v30..v31 at
the legal high end of destination EMUL8 v24..v31. Cycles11834577118
to12360331489 advance while retired1733731463,trap_count272779 and PCs
stay fixed. Both DDR channels have zero outstanding transactions/errors,
halt flags are clear and neither snapshot is watchdog-halted. Actual
VL/predicate and internal queue state are unobserved; head-PC has no
validity bit. Complete independent evidence is preserved in
`rvv_recovery08_24/terminal_scene`. The automatic evidence-gated launcher
continues314 unattempted exact ELFs in recovery25; this scene is not a
completed numerical pass or proof of a specific internal queue cause.

Recovery25 adds the SEW64 overlap scene `rvv_extension_e64_m2_vf2`, SHA256
`4c383ffcfdf197edf55da8163817291422d61c174246686a74cb659ffd6f8ae3`.
last_pc0x104b0 is `vsetvli e64,m2`; unqualified head PC0x104b4 decodes
`vzext.vf2 v24,v25,v0.t`. Source EEW32/EMUL1 occupies the high-end v25
of destination EMUL2 v24..v25. Cycles11955951920 to12474895927 advance
while retired1756453832,trap_count279720 and PCs stay fixed. Both DDR
channels have zero outstanding transactions/errors; halt flags and watchdog
status are clear. Exact VL/predicate and internal queue state are unobserved.
`rvv_recovery08_25/terminal_scene` preserves the independent exact ELF,
UART/report/snapshots/disassembly and hashes. This extends the measured
legal-overlap boundary to SEW64, not a newly proven distinct RTL cause.
Three earlier fractional-source m1 shapes pass504 configurations
(`rvv_recovery25_release08_partial01`). Recovery26 retains310 unattempted
exact ELFs after automatic evidence-gated original-image recovery.

Recovery26 independently records `rvv_extension_e64_m4_vf2`, SHA256
`fc9ac786b83ef3b2f1adeb2a269bebd44c26b8307ee3f2adc17262841b1906ea`.
last_pc0x104b4 is `vsetvli e64,m4`; unqualified head PC0x104b8 decodes
`vzext.vf2 v24,v26,v0.t`. Source EEW32/EMUL2 v26..v27 is the high-end
of destination EMUL4 v24..v27. Cycles29082097052 to29599294545 advance,
while retired2297850853, trap_count932134 and these PCs remain unchanged.
Both DDR channels have zero outstanding transactions/errors, halt flags
are clear, and neither snapshot is watchdog-halted. Exact active VL/mask
and internal execution state remain unobserved; this is another measured
external boundary, not proof of a distinct internal RTL cause.
The exact ELF/UART/report/snapshots/disassembly are preserved in
`rvv_recovery08_26/terminal_scene`. Before the stall, e64/m2/vf4 and
e64/m2/vf8 pass336 configurations (`rvv_recovery26_release08_partial01`).
Recovery27 retains all307 unattempted exact ELF identities.

Recovery27 adds the vf4 form `rvv_extension_e64_m4_vf4`, SHA256
`571920b8d3ea038cfd13f6e7be2d93d2613af27ae8a8f129b5af613294004b1c`.
last_pc0x104a2 is `vsetvli e64,m4`; unqualified head PC0x104a6 decodes
`vzext.vf4 v24,v27,v0.t`. Source EEW16/EMUL1 v27 is the high-end
of destination EMUL4 v24..v27. Cycles11782140798 to12305660252 advance,
while retired1728331466, trap_count270345 and the PCs remain unchanged.
Both DDR channels have zero outstanding transactions/errors, clear halt
flags and no watchdog halt. The captured historical cause9 trap is not
proof this instruction trapped. Active VL/mask and internal request state
are still unobserved. `rvv_recovery08_27/terminal_scene` contains the
exact ELF, UART, report, two snapshots and disassembly. This shape joins
RVV-06's measured boundaries; no numerical result was completed in this
round. Recovery28 retains all306 unattempted exact ELF identities.

Recovery28 adds `rvv_extension_e64_m8_vf2`, SHA256
`8e2ae6476c32a2ab1806b60b10e1c155a2fe9602f805e75e0244a56390313212`.
last_pc0x104b4 is `vsetvli e64,m8`; unqualified head PC0x104b8 decodes
`vzext.vf2 v24,v28,v0.t`. Source EEW32/EMUL4 v28..v31 occupies the
high-end of destination EMUL8 v24..v31. Cycles11824344713 to12346641093
advance, with retired1738398864, trap_count273447 and PCs unchanged.
Halt flags/watchdog are clear and both DDR channels have zero outstanding
transactions/errors. This establishes the external vf2/m8 stall boundary,
not the active VL/mask or internal request/queue cause.
`rvv_recovery08_28/terminal_scene` preserves the complete independent scene.
The earlier e64/m4/vf8 ELF passes168 configurations, verified in
`rvv_recovery28_release08_partial01`. Recovery29 retains all304 unattempted
exact ELF identities; no pending or stalled case becomes a pass.

Recovery29 independently records `rvv_extension_e64_m8_vf4`, SHA256
`c415c6e42447e20b88f93cd5c3255a2366d6bc9297dfadb481be2e896f7ca7ae`.
last_pc0x104a2 is `vsetvli e64,m8`; unqualified head PC0x104a6 decodes
`vzext.vf4 v24,v30,v0.t`. Source EEW16/EMUL2 v30..v31 is the high-end
of destination EMUL8 v24..v31. Cycles11790600170 to12313927252 advance
while retired1728230281, trap_count270176 and these PCs remain fixed.
Both DDR channels have zero outstanding transactions/errors; halt flags
and watchdog status are clear. The exact ELF, UART, snapshots, report and
disassembly are retained in `rvv_recovery08_29/terminal_scene`. No numerical
result completes in this round. Active VL/mask and internal queue state are
not measured, so this is an additional RVV-06 external boundary rather than
a newly proven distinct cause. Recovery30 retains303 unattempted exact ELFs.

Recovery30 adds `rvv_extension_e64_m8_vf8`, SHA256
`9e3d219ab0c0502be057f4529baa739fb0b5f0ab78130ba54a0d579ca68c3114`.
last_pc0x104a4 is `vsetvli e64,m8`; unqualified head PC0x104a8 decodes
`vzext.vf8 v24,v31,v0.t`. Source EEW8/EMUL1 v31 is the high-end of
destination EMUL8 v24..v31. Cycles11810205214 to12345419468 advance,
while retired1729749267, trap_count271311 and the PCs remain fixed.
Both DDR channels have zero outstanding transactions/errors and neither
snapshot is watchdog-halted; live halt flags are clear. The independent
scene is preserved in `rvv_recovery08_30/terminal_scene`, including exact
ELF/UART/report/snapshots/disassembly. No completed numerical result exists
for this ELF. Active VL/mask and internal execution state remain unobserved.
Recovery31 retains302 unattempted exact ELFs from the other queued families.
All released extension ELFs have now been attempted, but operations after
a stalled instruction remain uncovered; this is not extension acceptance.

The original scene remains immutable. The authorized original-image
continuation skips only the four already attempted ELFs, retaining the
stall as a failure and all 62 never-attempted cases as pending work. Tests
are preloaded with a test-only rootfs overlay to avoid repeated UART
transfer after recovery. No RTL change or synthesis is included.

## TEST-04: Recovery Overlay Not Available To Guest

The first recovery boot passes the Linux init marker but executes zero test
ELFs. Guest `/proc/mounts` confirms tmpfs over `/tmp`; a nonrecursive root
bind also shows no overlay directory. Guest device-tree `linux,initrd-end`
is still 0x886f7400 and the kernel frees only 7132 KiB of initrd, rather than
the supplied extended rootfs. Thus the overlay was not unpacked, not merely
hidden by the tmpfs mount.

The original firmware contains exactly one byte-identical DTB at file
offset 0x22000, symbol `fw_fdt_bin=0x80021000` in `.rodata`. Disassembly
shows the startup DTB relocation to `fw_next_arg1`, replacing the external
DTB. Updating only the external DTB therefore has no effect on initrd bounds.
The corrected package updates the embedded DTB too (two data bytes changed,
all executable sections unchanged), and places preloads in `/opt/rvv-preload`
before copying them to visible `/tmp` after boot. Guest ELF hashes remain
mandatory before execution. No RTL change or synthesis is involved.

Evidence: `rvv_recovery08_01/linux_report.json`, remote `mount_diagnosis01`,
`inspect_root_view01` and preserved zero-attempt `resume/report.json`.
The bounded bind diagnostic did not reset the board or run RVV instructions.
Corrected recovery preparation: `rvv_recovery08_04`; board result pending.
Preparation03 used an older local payload and was rejected by the original
rootfs hash gate before board programming. Preparation04 uses the verified
`payloads_complete_v3` files matching the deployed Windows payload hashes.

## TEST-05: Mask VL=0 Preservation Check Was Too Permissive

The packed-mask oracle previously allowed retained, all-one or computed
tail bits even at VL=0. That permitted legitimate nonzero-VL mask tail
choices but did not prove the separate zero-VL preservation requirement.
The source now requires the complete checked bit range to retain its
preimage when VL=0. New comparison-alias ELFs use this stronger check and
pass both reference VLENs. Previously released immutable ELFs/results are
not rewritten or advertised as validating the stronger check. This is a
test-oracle gap, not evidence that the FPGA modifies masks at VL=0.

## CAP-01: Nonaligned Setup Load Traps Before Segment Instruction

Recovery05 live03 contains SIGBUS/exit135 for
`rvv_segments_misaligned_e16_mf4`, `e16_mf2` and `e16_m1`.
At epc=0x1059c, instruction 0x02085c07 is `vle16.v v24,(a6)`;
badaddr=0x130c1 and cause=4 identify a load-address-misaligned exception.
This is the destination preimage load at VLMAX in the wrapper, not the
target `vlseg3e16.v` at 0x105b6. The requested target VL is zero in this
first trial, but setup still loads a full register group. Thus these
results do not prove that the segmented instruction violates zero-VL
suppression or masking.

Vector misaligned element accesses may either complete or raise an
address-misaligned exception; scalar support does not imply vector support.
QEMU completion and FPGA SIGBUS therefore indicate a capability difference,
not by themselves a confirmed RTL bug. Future test preparation should
initialize through aligned staging and distinguish unsupported misaligned
target accesses from numerical errors. The original failures remain recorded;
no supported/skip/pass relabeling is applied retroactively.

Additions32 now provides a separate aligned-staging diagnostic release.
The target address alone may be misaligned; shared phase markers are set
immediately before and after its segmented instruction. Children isolate
SIGBUS and continue all scenarios, including VL=0/all-off controls. An active
misaligned phase1 SIGBUS is recorded as unsupported with exit77, not a pass;
other traps and numerical mismatches remain failures. Both reference VLENs
pass its 3816 scenarios, but FPGA results are pending. This adds instrumentation
without asserting that the original capability difference is repaired.

Evidence: `rvv_recovery08_05/resume/board_report_live03.json`, immutable
additions14 ELFs and their disassembly. The live snapshot has 99 passes,
three failures and one running case out of 221 planned. Later outcomes
must be read from the final report, not inferred from this snapshot.

## RVV-07: Sparse Ordered FP Reduction Loses Invalid Flag

Recovery05 live04 records numerical failures (exit1) in all five FP32
ordered-special-reduction shapes and the first completed FP16 shape.
The first discrepancies are scenario3, op0 (`vfredosum.vs`), mask3,
VL>=8. Mask byte0x24 enables elements2 and5: the input alternates positive
and negative infinity, starting from a positive-infinity seed. Combining
the enabled opposite-sign infinities must raise NV (fflags bit4).
The oracle uses sequential Berkeley SoftFloat additions; identical ELFs
pass QEMU VLEN512 and VLEN1024.

The board reports flags0 instead of16, or flags1 instead of17 when prior
NX is set, across all five rounding modes. Thus the observed mismatch
specifically includes missing NV, not loss of the preexisting NX bit.
The wrapper saves/restores caller fflags and reads the tested flags directly
after the reduction. Mask3 is sparse, not all-off; the no-active-element
seed-copy rule does not explain these cases. Detailed output does not
identify which additional errors are value/tail checks, so do not claim
that every result bit is correct based on these flag lines.

This is a measured board/reference flag discrepancy, not a proven internal
RTL location. Distinguishing reduction execution/flag aggregation from
completion visibility requires a focused instruction trace with FPU
exception outputs, masked element acceptance, reduction completion and
scalar fflags commit. No RTL modification or speculative fix is made.
Original failing reports stay failures while independent tests continue.

Evidence: `rvv_recovery08_05/resume/board_report_live04.json`, immutable
additions15 ELFs, `fp_reduction_inputs.h`, `fp_reduction_fixture.c` and
`fp_reduction_oracle.c`. This snapshot has 103 passes (191860 configurations),
15 failures, one running case and 102 never-attempted cases. Nine failures
are CAP-01 preparation traps; six are reduction numerical failures.

The preserved terminal recovery05 report confirms all five FP32 and six
FP16 shape ELFs fail, while all four FP64 shape ELFs pass. The independent
prefix contains 140 passes (464020 configurations), eleven FP reduction
failures and nine nonaligned preparation traps. The following extension
overlap case stalls; 60 old cases remain never attempted. These terminal
counts replace neither the earlier immutable snapshots nor their evidence.

## TEST-06: Different-EEW Comparison Alias Oracle Too Strict

A source audit identifies a potential false-positive condition in the old
integer comparison-alias oracle: inactive body bits were required to retain
their preimage even when the packed-mask destination overlaps a vector source.
The RVV register-overlap rule treats mask EEW as 1; different-EEW source and
destination overlap forces mask/tail agnostic behavior regardless of vtype.
For VL>0 an inactive bit may therefore retain its old value or become one.
VL=0 still must leave the entire destination unchanged.

All old comparison-alias board cases passed on this image. No captured board
failure is being reclassified, and this source-audit risk is not an RTL defect.
The immutable additions19 ELFs/results remain untouched. Future reruns of
that integer family need a corrected oracle, not a retroactive green report.
The shared mask oracle now implements that correction for newly built
releases: prestart and start>=VL remain unchanged, only inactive body bits
with comparison source overlap permit one. Additions35 reference/board
results will be recorded separately; original additions19 ELFs stay unchanged.
New FP comparison-alias tests already permit the legal agnostic inactive
bits. For vf with destination v16, the source register is ft0 rather than v16,
so ordinary mask-undisturbed checks still apply there. A v0 mask destination
is also legal but does not itself constitute different-EEW vector-source overlap.

Primary semantics: local RISC-V vector specification `v-st-ext.adoc`,
register group overlap and agnostic-policy sections. Implementation evidence:
`mask_oracle.c` inactive comparison check and `fp_compare_oracle.c` overlap
classification. This is test-oracle coverage debt, separate from RVV-01..07.

## RVV-14: Masked Slideup Restart Stalls

Recovery199 isolates `rvv_permute_restart_e16_m1_ops18`, SHA256
578ab3c828a51c36d68e2b409c46c38156ed1f6c60e93daa2b0d390c3a59821f.
Two details show prestart element0 expected91 becoming0 at VL2, vstart1,
seed0/scalar0/mask0. No final2688-case marker exists; the exact stalled
trial and complete numerical outcome remain unknown. All20 terminal
hashes verify in `rvv_recovery08_199/terminal_scene`.
Cycles11558808972 ->12127869406 advance while retired1668921815,
trap_count251211 and PCs remain fixed. Last retired0x10930 is
`vslide1up.vx v24,v8,t3,v0.t`; unqualified head0x10934 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. This proves no retirement, not that
slide1up never retired or a specific internal completion cause; trap9 is
historical. Inventory68 records140 passes,80 complete failures,53 stalls
and125 unattempted children. Recovery200 retains exactly all125 pending
records after the one-result prefix; original parent outcomes remain
unchanged.

Recovery195 isolates `rvv_permute_restart_e16_mf2_ops18`, SHA256
dedc547782dec98f5f20cbfd6b3de86d46beb9fd1ebc3e0e5203d9cf60591aab.
Nine details show prestart elements expected91 becoming0,61881,538 or
44702 at VL2/3/16, vstart1/8, seed0/scalar0/mask0. No final2688-case
marker exists; the exact stalled trial and complete numerical outcome
remain unknown. All20 terminal hashes verify in
`rvv_recovery08_195/terminal_scene`. Cycles11549152682 ->12167092983
advance while retired1673868457, trap_count253658 and PCs remain fixed.
Last retired0x10930 is `vslide1up.vx v24,v8,t3,v0.t`; unqualified
head0x10934 is `csrr a0,vstart`. Both samples have flags0, no watchdog
snapshot and zero DDR outstanding transactions or response errors.
This proves no retirement, not that slide1up never retired or a specific
internal completion cause; trap9 is historical. The exact ELF passes both
reference VLENs. Inventory64 records140 passes,80 complete failures,
49 stalls and129 unattempted children. Recovery196 retains exactly all129
pending records after the one-result prefix; original parent outcomes
remain unchanged.

Recovery191 isolates `rvv_permute_restart_e8_m4_ops18`, SHA256
c5d2e22cc503e5526507d5e865d510aa0f65e5e930ecfe1f301fce8d289f28cf.
Two details show prestart element0 expected91 becoming0 at VL2,
vstart1, seed0/scalar0/mask0. No final2688-case marker exists; the exact
stalled trial and complete numerical outcome remain unknown. All20
terminal hashes verify in `rvv_recovery08_191/terminal_scene`.
Cycles11550608900 ->12123714864 advance while retired1671953586,
trap_count250808 and PCs remain fixed. Last retired0x1091a is
`vslide1up.vx v24,v8,t3,v0.t`; unqualified head0x1091e is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. This proves no retirement, not that
slide1up never retired or any specific internal completion cause. Trap9
is historical. The exact ELF passes both reference VLENs. Inventory60
records140 passes,80 complete failures,45 stalls and133 unattempted
children. Recovery192 retains exactly all133 pending records after the
one-result prefix; original parent outcomes remain unchanged.

Recovery187 isolates `rvv_permute_restart_e8_m2_ops18`, SHA256
5ddbb2fb83dc90a260cc12f1385ae6215be82d54d1827d308cdcddf04bc22eb8.
Two details show prestart element0 expected91 becoming0 at VL2,
vstart1, seed0/scalar0/mask0. No final2688-case marker exists; the exact
stalled trial and complete numerical outcome remain unknown. All20
terminal hashes verify in `rvv_recovery08_187/terminal_scene`.
Cycles11541913237 ->12115344966 advance while retired1671782146,
trap_count250864 and PCs remain fixed. Last retired0x1091a is
`vslide1up.vx v24,v8,t3,v0.t`; unqualified head0x1091e is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. Historical trap2, tval3222283635 and
trap PC18446744071571536408 remain unchanged; this does not establish
a new illegal instruction during the observation interval. These samples
prove no retirement, not that slide1up never retired or a specific
internal completion cause. The exact ELF passes both reference VLENs.
Inventory56 records140 passes,80 complete failures,41 stalls and137
unattempted children. Recovery188 retains exactly all137 pending records
after the one-result prefix; original parent outcomes remain unchanged.

Recovery183 isolates `rvv_permute_restart_e8_m1_ops18`, SHA256
70f9d9c9428b173e995d1bb92a8a997d92af6727f2325024fd43dc912048e564.
Two details show prestart element0 expected91 becoming0 at VL2,
vstart1, seed0/scalar0/mask0. No final2688-case marker exists; the exact
stalled trial and complete numerical outcome remain unknown. All20
terminal hashes verify in `rvv_recovery08_183/terminal_scene`.
Cycles11525035677 ->12087650031 advance while retired1673448465,
trap_count252559 and PCs remain fixed. Last retired0x1091a is
`vslide1up.vx v24,v8,t3,v0.t`; unqualified head0x1091e is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. This proves no retirement, not that
slide1up never retired or any specific internal completion cause. Trap9
is historical. The exact ELF passes both reference VLENs. Inventory52
records140 passes,80 complete failures,37 stalls and141 unattempted
children. Recovery184 retains exactly all141 pending records after the
one-result prefix; original parent outcomes remain unchanged.

Recovery179 completes ten gather children before stalling in
`rvv_permute_restart_e8_mf2_ops18`, SHA256
336795308c85bb669b6a3290d81e85c946bcf7f4f4b10fc2f5a1d8f9e531c615.
Nine details show prestart elements expected91 becoming0,185,26 or158 at
VL2/3/32, vstart1/16, seed0/scalar0/mask0. No final2688-case marker exists;
the exact stalled trial and complete numerical outcome remain unknown.
All27 terminal hashes verify in `rvv_recovery08_179/terminal_scene`.
Cycles15014956676 ->15572519655 advance while retired2086619327,
trap_count416216 and PCs remain fixed. Last retired0x1091a is
`vslide1up.vx v24,v8,t3,v0.t`; unqualified head0x1091e is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. This proves no retirement, not that
slide1up never retired or any specific internal completion cause. Trap9
is historical. The exact ELF passes both reference VLENs. Inventory48
records140 passes,80 complete failures,33 stalls and145 unattempted
children. Recovery180 retains exactly all145 pending records after the
eleven-result prefix; original parent outcomes remain unchanged.

Recovery150 isolates `rvv_permute_restart_e8_mf2_ops15` (immediate31),
SHA2564fc26c0a0e4613a194cd9ab67f5135d3543a02e58d221367e1308c955e6c17f8.
No numerical output or final2688-case marker was retained, so the stalled
trial and numerical outcome remain unknown. All20 archived hashes verify in
`rvv_recovery08_150/terminal_scene`. Cycles11968817085 ->12524894926
advance while retired1746239833, trap_count280170 and PCs remain fixed.
Last retired0x10880 is `vslideup.vi v24,v8,31,v0.t`; unqualified head0x10884
is `csrr a0,vstart`. Both snapshots have flags0, no watchdog snapshot and
zero outstanding transactions or response errors on both DDR channels.
This establishes no retirement, not that the slide never retired or a
particular internal completion cause. Historical trap9 is not a new trap
during the interval. The exact ELF passes both reference VLENs.
`rvv_permute_partition_inventory06` records8 passes,4 numerical failures,
4 stalls and382 unattempted children. Recovery151 preserves exactly the382
pending records; original parent results and test conditions are unchanged.

Recovery149 isolates `rvv_permute_restart_e8_mf2_ops14` (immediate0),
SHA25675ca8ed8fde0546e0a923d7dbca1828adee161f56cd860068d452096ffe44f2f.
Nine retained seed0/scalar0/mask0 details at VL2/3/32 and vstart1/16
show prestart sentinel91 overwritten (first element actual185); no final
2688-case numerical marker exists. The last detail does not identify the
stalled trial. All20 hashes verify in `rvv_recovery08_149/terminal_scene`.
Cycles11970574830 ->12506834343 advance while retired1749994479,
trap_count283500 and PCs remain fixed. Last retired0x10844 is
`vslideup.vi v24,v8,0,v0.t`; unqualified head0x10848 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
or response errors. These probes establish no retirement, not that the slide
never retired or any particular internal completion cause. Historical trap9
is separate evidence. The exact op14 ELF passes both reference VLENs.
`rvv_permute_partition_inventory05` records8 passes,4 numerical failures,
3 stalls and383 unattempted children. Recovery150 preserves exactly all383
pending records, continuing with e8/mf2 op15; no parent outcome is replaced.

Recovery147 isolates `rvv_permute_restart_e8_mf2_ops12` (`vslideup.vx`),
SHA2564e8f51d3f36f591594efe781927f13da99dc19cf6986a21f5ef633bde4809deb.
Nine retained seed0/scalar0/mask0 details at VL2/3/32 and vstart1/16
show prestart sentinel91 overwritten (first element actual185); no final
2688-case numerical marker exists. The last detail does not identify the
stalled trial. All20 hashes verify in `rvv_recovery08_147/terminal_scene`.
Cycles12836338691 ->13401358621 advance while retired1968473262,
trap_count347976 and PCs remain fixed. Last retired0x107ec is
`vslideup.vx v24,v8,t3,v0.t`; unqualified head0x107f0 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
or response errors. These probes confirm no retirement, not that the slide
never retired or any particular internal completion cause. Historical trap9
is not evidence of a new trap during the interval.
`rvv_permute_partition_inventory03` records8 passes,4 full numerical
failures,1 stall and385 unattempted children. Recovery148 preserves exactly
the385 pending records after the13-result prefix; no result is substituted.

Recovery11 stopped in `rvv_permute_restart_e8_mf2`. The immutable scene is
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_recovery08_11/terminal_scene`.
The exact ELF disassembly puts `vslideup.vx v24,v8,t3,v0.t` at `0x109de`,
after `csrw vstart,a7`; the next instruction at `0x109e2` reads `vstart`.
Both live snapshots report those same last/head PCs, retired count
63000642055 and trap count 16268135. Cycles increase from 269732483589 to
270124301391; neither snapshot is watchdog-frozen or software-halted.
Both DDR ports have zero outstanding transactions and zero response errors.

This establishes a no-retirement stall at the slideup/restart boundary,
not the internal RTL cause or the exact operand/mask configuration.
Do not merge this stall with RVV-08's numerical mismatch without further
cycle-level evidence. Remaining permutation-restart cases are deferred to
the end of recovery12, not removed from coverage.

Recovery42 extends this measured boundary to integer LMUL in
`rvv_permute_restart_e8_m1`, exact ELF SHA256
`1810df5395e654a3dbc249e652245bc24cd9b77a1d025ef942adcf47d88540c4`.
last/head PCs0x109de/0x109e2 decode the same masked slideup followed by
`csrr a0,vstart`. Cycles28942512209 to29495475366 advance while
retired9615048811, trap_count1237142 and both PCs remain unchanged;
halt flags/watchdog are clear and both DDR channels have zero outstanding
transactions/errors. The last cause9 trap is historical, not proof of a
slideup trap. All20 archived scene files pass their recorded hashes in
`rvv_recovery08_42/terminal_scene`. The final printed trial VL128/start127
belongs to op0's earlier gather diagnostic: the source prints trial records
only for op0/seed0/scalar0/mask0. It does not identify the active slideup
VL/vstart/mask/scalar. This is no longer a fractional-LMUL-only observed
stall, but a common internal cause remains unproven. Recovery43 retains98
pending exact ELF identities.

Recovery43 also stalls `rvv_permute_restart_e8_m2`, exact ELF SHA256
`f5a2aea1effe819f184ec0ce367b28998321ef1be19d458f7f0efadd1dec3238`.
The last/head PCs remain0x109de/0x109e2, masked slideup followed by
`csrr a0,vstart`. Cycles11450483992 to11970487411 advance while
retired1805352793 and trap_count265685 remain fixed. Halt flags/watchdog
are clear; both DDR channels have zero outstanding transactions/errors.
All20 recorded scene hashes verify in `rvv_recovery08_43/terminal_scene`.
The printed gather trials still do not identify the active slideup operands.
Recovery44 retains97 pending exact ELFs; this adds an observed LMUL shape,
not a proven independent internal root cause.

Recovery45 extends this boundary to SEW16 in
`rvv_permute_restart_e16_mf2`, exact ELF SHA256
`9210403c48bc9eec9b65fbd9d15385acec7e73d9ea883dc640df0a98eb206126`.
Last PC0x109fa decodes masked `vslideup.vx v24,v8,t3,v0.t`; head
PC0x109fe decodes `csrr a0,vstart`. Cycles11727143897 to12254687960
advance while retired1799349979, trap_count275293 and both PCs stay fixed.
Halt flags/watchdog are clear and both DDR ports have zero outstanding
transactions/errors. All20 archived scene hashes verify. As in earlier
scenes, op0-only trial logging does not identify the active slideup operands.
Recovery46 retains94 pending exact ELFs; the preceding e16/mf4 completed
with numerical failure and is not rerun. The measured boundary is broader
than SEW8, but its internal RTL cause remains unproven.

Recovery46 also stalls `rvv_permute_restart_e16_m1`, exact ELF SHA256
`7ab835ae2eee17e963ca2a95bb47b642e9bc3d5e68c9e7e59366fc9eff300d37`.
Last/head PCs0x109fa/0x109fe decode the same slideup/CSR boundary, now
with e16,m1. Cycles11454237967 to12008909158 advance while
retired1705106167 and trap_count256563 remain fixed. Halt flags/watchdog
are clear; both DDR ports have zero outstanding transactions/errors.
All20 scene hashes verify in `rvv_recovery08_46/terminal_scene`.
The active operand configuration and internal cause remain unproven;
the ELF has no completed numerical marker. Recovery47 retains93 pending
exact ELFs without removing any unattempted test.

Recovery47 also stalls `rvv_permute_restart_e16_m2`, exact ELF SHA256
`fa25c4e0a0cdbd55cae1a704ab9ce200a4f74a25abc82a85c652ac230b10a8ae`.
Last/head PCs0x109fa/0x109fe decode masked slideup followed by the
vstart read. Cycles11472276271 to12053609317 advance while
retired1738142360 and trap_count260272 remain fixed. Halt flags/watchdog
are clear and both DDR ports have zero outstanding transactions/errors.
All20 archived scene hashes verify in `rvv_recovery08_47/terminal_scene`.
No completed numerical marker or active slideup operands are established;
the internal cause remains unproven. Recovery48 retains92 pending ELFs.

Recovery48 also stalls `rvv_permute_restart_e16_m4`, exact ELF SHA256
`273d499c3d28d61554c4f2a7712be4c4878e2d09ce3b87723c6e64f12310a222`.
Last/head PCs0x109fa/0x109fe decode masked slideup and the vstart read,
with e16,m4. Cycles11375626856 to11907165809 advance while
retired1794651256 and trap_count264298 remain fixed. Halt flags/watchdog
are clear; both DDR channels have zero outstanding transactions/errors.
All20 archived hashes verify in `rvv_recovery08_48/terminal_scene`.
Active operands/internal cause remain unproven and the numerical marker
is incomplete. Recovery49 retains91 pending exact ELFs.

Recovery49 extends the measured boundary to SEW32 in
`rvv_permute_restart_e32_mf2`, exact ELF SHA256
`2d638e44ffd710e5ada22c7405b05b47fccbeae5baafed3614e7af03546ac903`.
Last PC0x109ea decodes masked slideup; head PC0x109ee reads vstart.
Cycles11470051875 to11996321597 advance while retired1684349034,
trap_count255809 and both PCs remain fixed. Halt flags/watchdog are clear;
both DDR ports have zero outstanding transactions/errors. All20 recorded
scene hashes verify in `rvv_recovery08_49/terminal_scene`. Active slideup
operands/internal cause are not established and no numerical completion
marker exists. Recovery50 retains90 pending exact ELFs.

Recovery50 also stalls `rvv_permute_restart_e32_m1`, exact ELF SHA256
`2586c06a6964bf93c7a35288b70b4b9dbbbf289823839ecef411cc25ec4a82f2`.
Last/head PCs0x109ea/0x109ee decode masked slideup and the vstart read.
Cycles11421592344 to11971012759 advance while retired1689696251,
trap_count256028 and both PCs stay fixed. Halt flags/watchdog are clear;
both DDR channels have zero outstanding transactions/errors. All20 scene
hashes verify in `rvv_recovery08_50/terminal_scene`. The active slideup
operands/internal cause are not established and numerical completion is
unproven. Recovery51 retains89 pending exact ELFs.

Recovery51 also stalls `rvv_permute_restart_e32_m2`, exact ELF SHA256
`15137dbe17aa52791289ed3afa3b339ffeeb1ee0cc8898778598d885a84b4670`.
Last/head PCs0x109ea/0x109ee decode masked slideup and the vstart read.
Cycles11392078667 to11916912752 advance while retired1703486636,
trap_count255976 and both PCs remain fixed. Halt flags/watchdog are clear;
both DDR ports have zero outstanding transactions/errors. All20 recorded
scene hashes verify in `rvv_recovery08_51/terminal_scene`. Active operands
and the internal cause remain unproven; no numerical completion marker
exists. Recovery52 retains88 pending exact ELFs.

Recovery52 also stalls `rvv_permute_restart_e32_m4`, exact ELF SHA256
`10f8db81d3149ba6b616d8236c5717f765c8ed65405e2afebca1f8e9b9d6f47f`.
Last/head PCs0x109ea/0x109ee decode masked slideup and the vstart read.
Cycles11409100020 to11938801849 advance while retired1734640594,
trap_count259365 and both PCs remain fixed. Halt flags/watchdog are clear;
both DDR ports have zero outstanding transactions/errors. All20 recorded
scene hashes verify in `rvv_recovery08_52/terminal_scene`. No active
slideup operands, internal cause or numerical completion are established.
Recovery53 retains87 pending exact ELFs.

Recovery53 extends the measured boundary to SEW64 in
`rvv_permute_restart_e64_m1`, exact ELF SHA256
`b90212f8e1f8235b587ed91eb7db8b2fb2fa6287b40f4e57de2907ddca90632d`.
Last PC0x109e2 decodes masked slideup; head PC0x109e6 reads vstart.
Cycles11425475038 to11959351807 advance while retired1681142897,
trap_count255048 and both PCs remain fixed. Halt flags/watchdog are clear;
both DDR ports have zero outstanding transactions/errors. All20 recorded
scene hashes verify in `rvv_recovery08_53/terminal_scene`. Active operands
and the internal cause remain unproven; no numerical completion exists.
Recovery54 retains86 pending exact ELFs. Observed stalls now span all four
SEWs, without implying that all LMUL/configuration combinations stall.

Recovery54 also stalls `rvv_permute_restart_e64_m2`, exact ELF SHA256
`bf3f21a3382da9f59a23d0a9cb839eb6e132bae9e10c7fca5a7cfaac9010242f`.
Last/head PCs0x109e2/0x109e6 decode masked slideup and the vstart read.
Cycles11394628947 to11922166496 advance while retired1687776743,
trap_count254968 and both PCs remain fixed. Halt flags/watchdog are clear;
both DDR ports have zero outstanding transactions/errors. All20 recorded
scene hashes verify in `rvv_recovery08_54/terminal_scene`. Active operands
and the internal cause remain unproven; no numerical completion exists.
Recovery55 retains85 pending exact ELFs.

Recovery55 also stalls `rvv_permute_restart_e64_m4`, exact ELF SHA256
`47d45f450839146b81e21757e30c5c3b5dbf74d9d4470ab096f568d09d8b3630`.
Last/head PCs0x109e2/0x109e6 decode masked slideup and the vstart read.
Cycles11455540047 to11981436710 advance while retired1706262989,
trap_count256423 and both PCs remain fixed. Halt flags/watchdog are clear;
both DDR ports have zero outstanding transactions/errors. All20 recorded
scene hashes verify in `rvv_recovery08_55/terminal_scene`. Active operands
and the internal cause remain unproven; no numerical completion exists.
Recovery56 retains84 pending exact ELFs.

Recovery79 stalls `rvv_permute_restart_e32_m8`, exact ELF SHA256
`c387cd15d77b9e8c495513e62a0897b3693578459f54447c2279c57a89a0fe81`.
Last/head PCs0x109ea/0x109ee decode `vslideup.vx v24,v8,t3,v0.t`
and `csrr a0,vstart`. Cycles11275329456 to11800118959 advance while
retired1769966972, trap_count256885 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_79/terminal_scene`. The only
per-trial trace covers the first gather, not active slideup operands;
it cannot identify the stalled VL/start/offset/mask. Head validity and
internal cause remain unproven. Preceding gather prestart corruption is
recorded separately under RVV-19. No completed numerical marker exists,
and later trials remain uncovered. Recovery80 retains16 pending exact ELFs.

Recovery80 stalls `rvv_permute_restart_e64_m8`, exact ELF SHA256
`137b393c59a6fa58faf88c8d2d3d79c09a65b88912436d5d93fce4f8ef54877c`.
Last/head PCs0x109e2/0x109e6 decode `vslideup.vx v24,v8,t3,v0.t`
and `csrr a0,vstart`. Cycles11254891777 to11826739452 advance while
retired1707896579, trap_count251086 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_80/terminal_scene`. As in
recovery79, the first-gather trace does not identify the active slideup
VL/start/offset/mask. Head validity and internal cause remain unproven;
preceding gather prestart corruption is a separate measured symptom.
No completed numerical marker exists and later trials remain uncovered.
Recovery81 retains15 pending exact ELFs.

## RVV-20: Integer Masked Slidedown Restart Result Errors And Stalls

Recovery200 isolates `rvv_permute_restart_e16_m1_ops19`, SHA256
31f1770c0fe44052e0a84552ba13c65df85f90375ec1f6d7aa7d2427ef1cc4dc.
Two details show prestart element0 expected91 becoming538 at VL2,
vstart1, seed0/scalar0/mask0. No final2688-case marker exists; the exact
stalled trial and complete numerical outcome remain unknown. All20
terminal hashes verify in `rvv_recovery08_200/terminal_scene`.
Cycles11536937541 ->12109613680 advance while retired1667762860,
trap_count250879 and PCs remain fixed. Last retired0x10964 is
`vslide1down.vx v24,v8,t3,v0.t`; unqualified head0x10968 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. Historical trap2, tval3222283635 and
trap PC18446744071571536408 remain unchanged; this does not establish a
new illegal-instruction event. No retirement is proven, but head validity
and a specific internal completion cause remain unproven. Inventory69
records140 passes,80 complete failures,54 stalls and124 unattempted
children. Recovery201 retains exactly all124 pending records after the
one-result prefix; original parent outcomes remain unchanged.

Recovery198 isolates `rvv_permute_restart_e16_m1_ops17`, SHA256
ee6f8a1d9257b56a74f8b143fbbe92e1c6b1d86aaa8c7d51e9624e7e0cfdc7ad.
Two details show prestart element0 expected91 becoming32689 at VL2,
vstart1, seed0/scalar0/mask0. No final2688-case marker exists; the exact
stalled trial and complete numerical outcome remain unknown. All20
terminal hashes verify in `rvv_recovery08_198/terminal_scene`.
Cycles11573273486 ->12171007024 advance while retired1671648863,
trap_count250782 and PCs remain fixed. Last retired0x10922 is
`vslidedown.vi v24,v8,31,v0.t`; unqualified head0x10926 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. Historical trap2, tval3222283635 and
trap PC18446744071571536408 remain unchanged; this does not establish a
new illegal-instruction event. No retirement is proven, but head validity
and a specific internal completion cause remain unproven. Inventory67
records140 passes,80 complete failures,52 stalls and126 unattempted
children. Recovery199 retains exactly all126 pending records after the
one-result prefix; original parent outcomes remain unchanged.

Recovery197 isolates `rvv_permute_restart_e16_m1_ops16`, SHA256
ed4cc660ae52fb2126d86d706b18ebfdc776d2b3bc1d918a8a3f77c1eb85fa23.
There are no numerical details or final2688-case marker; the exact stalled
trial and complete numerical outcome remain unknown. All20 terminal hashes
verify in `rvv_recovery08_197/terminal_scene`. Cycles11592241821
->12175147751 advance while retired1670440972, trap_count250131 and PCs
remain fixed. Last retired0x108c4 is `vslidedown.vi v24,v8,0,v0.t`;
unqualified head0x108c8 is `csrr a0,vstart`. Both samples have flags0,
no watchdog snapshot and zero DDR outstanding transactions or response
errors. This proves no retirement, not that slidedown never retired or a
specific internal completion cause; trap9 is historical. The exact ELF
passes both reference VLENs. Inventory66 records140 passes,80 complete
failures,51 stalls and127 unattempted children. Recovery198 retains exactly
all127 pending records after the one-result prefix; original parent
outcomes remain unchanged.

Recovery196 isolates `rvv_permute_restart_e16_mf2_ops19`, SHA256
1b6c6e585c083085baafcea0ce8bc8dd8c8c5acc37f686edf572260000acce86.
Nine details show prestart elements expected91 becoming538,44702,20547
or33827 at VL2/3/16, vstart1/8, seed0/scalar0/mask0. No final2688-case
marker exists; the exact stalled trial and complete numerical outcome
remain unknown. All20 terminal hashes verify in
`rvv_recovery08_196/terminal_scene`. Cycles11548240268 ->12112738397
advance while retired1671823666, trap_count254177 and PCs remain fixed.
Last retired0x10964 is `vslide1down.vx v24,v8,t3,v0.t`; unqualified
head0x10968 is `csrr a0,vstart`. Both samples have flags0, no watchdog
snapshot and zero DDR outstanding transactions or response errors.
This proves no retirement, not that slide1down never retired or a specific
internal completion cause; trap9 is historical. The exact ELF passes both
reference VLENs. Inventory65 records140 passes,80 complete failures,
50 stalls and128 unattempted children. Recovery197 retains exactly all128
pending records after the one-result prefix; original parent outcomes
remain unchanged.

Recovery194 isolates `rvv_permute_restart_e16_mf2_ops17`, SHA256
8ce83f1acb6fcf00b8fdbe2adf2b4c2ec4018ee13c7a8571a454b981762bd131.
Nine details show prestart elements expected91 becoming32689 or0 at
VL2/3/16, vstart1/8, seed0/scalar0/mask0. No final2688-case marker exists;
the exact stalled trial and complete numerical outcome remain unknown.
All20 terminal hashes verify in `rvv_recovery08_194/terminal_scene`.
Cycles11484841633 ->12060744460 advance while retired1671641765,
trap_count252882 and PCs remain fixed. Last retired0x10922 is
`vslidedown.vi v24,v8,31,v0.t`; unqualified head0x10926 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. This proves no retirement, not that
slidedown never retired or any specific internal completion cause. Trap9
is historical. The exact ELF passes both reference VLENs. Inventory63
records140 passes,80 complete failures,48 stalls and130 unattempted
children. Recovery195 retains exactly all130 pending records after the
one-result prefix; original parent outcomes remain unchanged.

Recovery193 isolates `rvv_permute_restart_e16_mf2_ops16`, SHA256
01a7e42f1a172ed350493dd3c6dbea71814028236b4a0368bb2fc5bf66a0227d.
Eight details show active elements8..15 retaining initialization91 at
VL16/vstart8, seed0/scalar0/mask0, instead of expected
36427/57239/49128/51863/16066/50239/33399/52403. No final2688-case
marker exists; the exact stalled trial and complete numerical outcome
remain unknown. All20 terminal hashes verify in
`rvv_recovery08_193/terminal_scene`. Cycles11495447469 ->12065049668
advance while retired1671774197, trap_count253016 and PCs remain fixed.
Last retired0x108c4 is `vslidedown.vi v24,v8,0,v0.t`; unqualified
head0x108c8 is `csrr a0,vstart`. Both samples have flags0, no watchdog
snapshot and zero DDR outstanding transactions or response errors.
This proves no retirement, not that slidedown never retired or a specific
internal completion cause; trap9 is historical. The exact ELF passes both
reference VLENs. Inventory62 records140 passes,80 complete failures,
47 stalls and131 unattempted children. Recovery194 retains exactly all131
pending records after the one-result prefix; original parent outcomes
remain unchanged.

Recovery192 isolates `rvv_permute_restart_e8_m4_ops19`, SHA256
1a4d82cb1eea29a6d0ffdf0964374b3d69169f39fa9acae2ed8611ff7ad4250e.
Two details show prestart element0 expected91 becoming26 at VL2,
vstart1, seed0/scalar0/mask0. No final2688-case marker exists; the exact
stalled trial and complete numerical outcome remain unknown. All20
terminal hashes verify in `rvv_recovery08_192/terminal_scene`.
Cycles11565123929 ->12128335769 advance while retired1672592071,
trap_count252111 and PCs remain fixed. Last retired0x10950 is
`vslide1down.vx v24,v8,t3,v0.t`; unqualified head0x10954 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. Historical trap2, tval3222283635 and
trap PC18446744071571536408 remain unchanged; this does not establish
a new illegal instruction during the observation interval. These samples
prove no retirement, not that slide1down never retired or a specific
internal completion cause. The exact ELF passes both reference VLENs.
Inventory61 records140 passes,80 complete failures,46 stalls and132
unattempted children. Recovery193 retains exactly all132 pending records
after the one-result prefix; original parent outcomes remain unchanged.

Recovery190 isolates `rvv_permute_restart_e8_m4_ops17`, SHA256
d085d1c2ad719b31951f3466e8d20c927a17046b694ed6a12ed845b8aeb5355e.
Three details show prestart element0 expected91 becoming177 at VL2/3,
vstart1, seed0/scalar0/mask0. No final2688-case marker exists; the exact
stalled trial and complete numerical outcome remain unknown. All20
terminal hashes verify in `rvv_recovery08_190/terminal_scene`.
Cycles11555679545 ->12129121391 advance while retired1672432724,
trap_count252416 and PCs remain fixed. Last retired0x1090c is
`vslidedown.vi v24,v8,31,v0.t`; unqualified head0x10910 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. This proves no retirement, not that
slidedown never retired or any specific internal completion cause. Trap9
is historical. The exact ELF passes both reference VLENs. Inventory59
records140 passes,80 complete failures,44 stalls and134 unattempted
children. Recovery191 retains exactly all134 pending records after the
one-result prefix; original parent outcomes remain unchanged.

Recovery189 isolates `rvv_permute_restart_e8_m4_ops16`, SHA256
20ec3eec52650bfea21e177fb5ec309fcf81cbff581b378d01dece195c027c3a.
The retained output is empty; no final2688-case marker exists. The exact
stalled trial and numerical outcome remain unknown. All20 terminal
hashes verify in `rvv_recovery08_189/terminal_scene`.
Cycles11534981457 ->12094873569 advance while retired1671938074,
trap_count251046 and PCs remain fixed. Last retired0x108ae is
`vslidedown.vi v24,v8,0,v0.t`; unqualified head0x108b2 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. This proves no retirement, not that
slidedown never retired or any specific internal completion cause. Trap9
is historical. The exact ELF passes both reference VLENs. Inventory58
records140 passes,80 complete failures,43 stalls and135 unattempted
children. Recovery190 retains exactly all135 pending records after the
one-result prefix; original parent outcomes remain unchanged.

Recovery188 isolates `rvv_permute_restart_e8_m2_ops19`, SHA256
cbfe26334457f587bbe71a59ba3a735ab8de1ab2bab61d424ce8a018457df907.
Two details show prestart element0 expected91 becoming26 at VL2,
vstart1, seed0/scalar0/mask0. No final2688-case marker exists; the exact
stalled trial and complete numerical outcome remain unknown. All20
terminal hashes verify in `rvv_recovery08_188/terminal_scene`.
Cycles11535127641 ->12100924821 advance while retired1670975245,
trap_count250485 and PCs remain fixed. Last retired0x10950 is
`vslide1down.vx v24,v8,t3,v0.t`; unqualified head0x10954 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. Historical trap2, tval3222283635 and
trap PC18446744071571536408 remain unchanged; this does not establish
a new illegal instruction during the observation interval. These samples
prove no retirement, not that slide1down never retired or a specific
internal completion cause. The exact ELF passes both reference VLENs.
Inventory57 records140 passes,80 complete failures,42 stalls and136
unattempted children. Recovery189 retains exactly all136 pending records
after the one-result prefix; original parent outcomes remain unchanged.

Recovery186 isolates `rvv_permute_restart_e8_m2_ops17`, SHA256
ee3e3546a1526af0dd11a96ac17b6aae932413283004f1b1c6a000115bf4b5eb.
Two details show prestart element0 expected91 becoming177 at VL2,
vstart1, seed0/scalar0/mask0. No final2688-case marker exists; the exact
stalled trial and complete numerical outcome remain unknown. All20
terminal hashes verify in `rvv_recovery08_186/terminal_scene`.
Cycles11525981030 ->12076991299 advance while retired1671082312,
trap_count250630 and PCs remain fixed. Last retired0x1090c is
`vslidedown.vi v24,v8,31,v0.t`; unqualified head0x10910 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. Historical trap2, tval3222283635 and
trap PC18446744071571536408 remain unchanged; this does not establish
a new illegal instruction during the observation interval. These samples
prove no retirement, not that slidedown never retired or a specific
internal completion cause. The exact ELF passes both reference VLENs.
Inventory55 records140 passes,80 complete failures,40 stalls and138
unattempted children. Recovery187 retains exactly all138 pending records
after the one-result prefix; original parent outcomes remain unchanged.

Recovery185 isolates `rvv_permute_restart_e8_m2_ops16`, SHA256
872ee21917c0b0a80c77759974a5794818ab2941644df5296d5425db092ddb17.
The retained output is empty; no final2688-case marker exists. The exact
stalled trial and numerical outcome remain unknown. All20 terminal
hashes verify in `rvv_recovery08_185/terminal_scene`.
Cycles11528446104 ->12093588877 advance while retired1672096165,
trap_count249565 and PCs remain fixed. Last retired0x108ae is
`vslidedown.vi v24,v8,0,v0.t`; unqualified head0x108b2 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. This proves no retirement, not that
slidedown never retired or any specific internal completion cause. Trap9
is historical. The exact ELF passes both reference VLENs. Inventory54
records140 passes,80 complete failures,39 stalls and139 unattempted
children. Recovery186 retains exactly all139 pending records after the
one-result prefix; original parent outcomes remain unchanged.

Recovery184 isolates `rvv_permute_restart_e8_m1_ops19`, SHA256
63088b467ed6c02d4b0949e10f362a8dc28bbe3b7de6403626e53cee72d60e8e.
Two details show prestart element0 expected91 becoming26 at VL2,
vstart1, seed0/scalar0/mask0. No final2688-case marker exists; the exact
stalled trial and complete numerical outcome remain unknown. All20
terminal hashes verify in `rvv_recovery08_184/terminal_scene`.
Cycles11499326307 ->12054433049 advance while retired1671574772,
trap_count250809 and PCs remain fixed. Last retired0x10950 is
`vslide1down.vx v24,v8,t3,v0.t`; unqualified head0x10954 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. Historical trap2, tval3222283635 and
trap PC18446744071571536408 remain unchanged; this does not establish
a new illegal instruction during the observation interval. These samples
prove no retirement, not that slide1down never retired or a specific
internal completion cause. The exact ELF passes both reference VLENs.
Inventory53 records140 passes,80 complete failures,38 stalls and140
unattempted children. Recovery185 retains exactly all140 pending records
after the one-result prefix; original parent outcomes remain unchanged.

Recovery182 isolates `rvv_permute_restart_e8_m1_ops17`, SHA256
7780429e77d225ce4cf67437df34c43bba69821652fc7ffe39be65b3b38517ae.
Two details show prestart element0 expected91 becoming177 at VL2,
vstart1, seed0/scalar0/mask0. No final2688-case marker exists; the exact
stalled trial and complete numerical outcome remain unknown. All20
terminal hashes verify in `rvv_recovery08_182/terminal_scene`.
Cycles11599603114 ->12201076898 advance while retired1674160092,
trap_count252795 and PCs remain fixed. Last retired0x1090c is
`vslidedown.vi v24,v8,31,v0.t`; unqualified head0x10910 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. Historical trap2, tval3222283635 and
trap PC18446744071571536408 remain unchanged; this does not establish
a new illegal instruction during the observation interval. These samples
prove no retirement, not that slidedown never retired or a specific
internal completion cause. The exact ELF passes both reference VLENs.
Inventory51 records140 passes,80 complete failures,36 stalls and142
unattempted children. Recovery183 retains exactly all142 pending records
after the one-result prefix; original parent outcomes remain unchanged.

Recovery181 isolates `rvv_permute_restart_e8_m1_ops16`, SHA256
36ee32b037de892c9bf0caa750083ad9b92feb153092b708837323e96c57753d.
The retained case output is empty; no final2688-case marker exists. The
exact stalled trial and numerical outcome remain unknown. All20 terminal
hashes verify in `rvv_recovery08_181/terminal_scene`.
Cycles11580636387 ->12198614046 advance while retired1673307890,
trap_count251337 and PCs remain fixed. Last retired0x108ae is
`vslidedown.vi v24,v8,0,v0.t`; unqualified head0x108b2 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. This proves no retirement, not that
slidedown never retired or any specific internal completion cause. Trap9
is historical. The exact ELF passes both reference VLENs. Inventory50
records140 passes,80 complete failures,35 stalls and143 unattempted
children. Recovery182 retains exactly all143 pending records after the
one-result prefix; original parent outcomes remain unchanged.

Recovery180 isolates `rvv_permute_restart_e8_mf2_ops19`, SHA256
55044f25aea74bd4685be0fbf159dd7f281db378557dc848282813fc401bc3a0.
Nine details show prestart elements expected91 becoming26,158,67 or35 at
VL2/3/32, vstart1/16, seed0/scalar0/mask0. No final2688-case marker exists;
the exact stalled trial and complete numerical outcome remain unknown.
All20 terminal hashes verify in `rvv_recovery08_180/terminal_scene`.
Cycles11560427712 ->12131441988 advance while retired1676983810,
trap_count255961 and PCs remain fixed. Last retired0x10950 is
`vslide1down.vx v24,v8,t3,v0.t`; unqualified head0x10954 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. This proves no retirement, not that
slide1down never retired or any specific internal completion cause. Trap9
is historical. The exact ELF passes both reference VLENs. Inventory49
records140 passes,80 complete failures,34 stalls and144 unattempted
children. Recovery181 retains exactly all144 pending records after the
one-result prefix; original parent outcomes remain unchanged.

Recovery152 isolates `rvv_permute_restart_e8_mf2_ops17` (immediate31), SHA256
fa712b828948788c6114693670dbddf3fccb5608715743948685f57520233f9e.
Eight retained seed0/scalar0/mask0/VL2/3/32/vstart1/16 details show prestart
sentinel91 overwritten (first element actual177). This differs from the
active-element sentinel retention in op13/op16; a shared internal cause is
not established. No final2688-case marker exists and the last detail does
not identify the stalled trial. All20 archived hashes verify in
`rvv_recovery08_152/terminal_scene`. Cycles12019396203 ->12612071432
advance while retired1748426910, trap_count282865 and PCs remain fixed.
Last retired0x1090c is `vslidedown.vi v24,v8,31,v0.t`; unqualified head0x10910
is `csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding transactions or response errors. This establishes no retirement,
not that the slide never retired or a particular internal completion cause.
Historical trap9 is not a new trap during the interval. The exact ELF passes
both reference VLENs. `rvv_permute_partition_inventory08` records8 passes,
4 numerical failures,6 stalls and380 unattempted children. Recovery153 retains
exactly all380 pending records, deferring the masked slide family after other
operations; no test conditions or parent outcomes are changed. Untested slide
variants are not classified as failed by this scheduling policy.

Recovery151 isolates `rvv_permute_restart_e8_mf2_ops16` (immediate0), SHA256
6b8b9c66cadf2828ebed2e4926aa31d63d64237b956df94916cba6d7ebdc65b6.
Eight retained seed0/scalar0/VL32/mask0/vstart16 details show active
elements16..23 remaining at sentinel91 rather than expected234,241,158,167,
224,135,2,162. No final2688-case numerical marker exists; the last detail
does not identify the stalled trial. All20 hashes verify in
`rvv_recovery08_151/terminal_scene`. Cycles11992219291 ->12607458215
advance while retired1747488631, trap_count281270 and PCs remain fixed.
Last retired0x108ae is `vslidedown.vi v24,v8,0,v0.t`; unqualified head0x108b2
is `csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding transactions or response errors. These establish no retirement,
not that the slide never retired or any specific internal completion cause.
Historical trap9 is not a new trap during the interval. The exact ELF passes
both reference VLENs. `rvv_permute_partition_inventory07` records8 passes,
4 numerical failures,5 stalls and381 unattempted children. Recovery152
preserves exactly all381 pending records; no parent outcome is replaced.

Recovery148 isolates `rvv_permute_restart_e8_mf2_ops13`, SHA256
ed8395f286717a1608b61a78062701175ac979dbdcf4c6669fb93f7aad24c47f.
Eight retained op13/seed0/scalar0/VL32/mask0/vstart16 details show active
elements16..23 left at sentinel91 instead of expected234,241,158,167,
224,135,2,162. There is no final2688-case numerical marker; the last
detail does not identify the stalled trial. This symptom remains distinct
from slideup/gather prestart corruption pending internal cause evidence.
All20 hashes verify in `rvv_recovery08_148/terminal_scene`.
Cycles11974773593 ->12536234138 advance while retired1749012022,
trap_count283553 and PCs remain fixed. Last retired0x10830 is
`vslidedown.vx v24,v8,t3,v0.t`; unqualified head0x10834 is `csrr a0,vstart`.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
or response errors. No retirement is confirmed, but these probes neither
prove the slide never retired nor identify the internal completion cause.
Historical trap9 is separate from the current no-retirement interval.
`rvv_permute_partition_inventory04` records8 passes,4 numerical failures,
2 stalls and384 unattempted children. Recovery149 preserves every pending
case exactly once and continues with e8/mf2 op14; original parent stalls
remain unchanged. The exact op13 ELF passes both reference VLENs.

## RVV-21: Integer Merge Restart Stalls At Large e8/e16 Groups

Recovery168 `resume/board_report_live01.json` records e8/m4 move ops8..11
passing all2688 configurations each. The separate e8/m4 merge ops4..7
stalls therefore do not justify classifying all e8/m4 operations as failed.
This is a measured operation boundary, not proof of the internal cause.
Inventory32 audits exact identities and final markers:140 passes,55 complete
numerical failures,21 stalls,1 running and181 unattempted children (195
complete numerical results). The running e8/m4 gather op3 has emitted
numerical mismatch details but has no final result in this report.

Recovery167 terminates in `rvv_permute_restart_e8_m4_ops7`, SHA256
6f52f7932c02beef8bda51827f41bebd7f913eb4d4598cd22f5d34a85d4ffaf1.
No numerical output or final2688-case marker exists; the stalled trial
and numerical outcome remain unknown. All20 terminal hashes verify in
`rvv_recovery08_167/terminal_scene`. Cycles11638294323 ->12198716703
advance while retired1688813399, trap_count255995 and PCs remain fixed.
Last retired0x106f4 is `vmerge.vim v24,v8,15,v0`; unqualified head0x106f8
is `csrr a0,vstart`, with e8/m4 vtype in the exact ELF disassembly.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. These establish no retirement, not that
merge never retired or a specific internal cause; trap9 is historical.
The exact ELF passes both reference VLENs. Inventory31 records136 passes,
55 complete numerical failures,21 stalls and186 unattempted children.
Recovery168 retains exactly all186 pending records after the one-result
prefix; original parent outcomes remain unchanged.

Recovery166 terminates in `rvv_permute_restart_e8_m4_ops6`, SHA256
938d9c50c3cee46236d6469559de7557a0e5c447e3180f28608e7c37c376c5a5.
No numerical output or final2688-case marker exists for this child; the
stalled trial and numerical outcome remain unknown. All20 terminal hashes
verify in `rvv_recovery08_166/terminal_scene`. Cycles12547959298
->13083838586 advance while retired2183159520, trap_count308229 and PCs
remain fixed. Last retired0x106c6 is `vmerge.vim v24,v8,-16,v0`;
unqualified head0x106ca is `csrr a0,vstart`, with e8/m4 vtype in the exact
ELF disassembly. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding transactions or response errors. This establishes no
retirement, not that merge never retired or a specific internal cause;
trap9 is historical. The exact ELF passes both reference VLENs. The four
preceding move children retain their full2688-case passes. Inventory30
records136 passes,55 complete numerical failures,20 stalls and187
unattempted children. Recovery167 retains exactly all187 pending records
after the five-result prefix; original parent outcomes remain unchanged.

Recovery166 `resume/board_report_live01.json` records e8/m8 move ops8..11
passing all2688 configurations each. The separate e8/m8 merge ops4..7
stalls therefore do not justify classifying all e8/m8 operations as failed.
This is an operation boundary, not proof of the internal root cause.
Inventory29 audits exact identities and final markers:136 passes,55 complete
numerical failures,19 stalls,1 running and187 unattempted children (191
complete numerical results). The running e8/m4 op6 remains unclassified.

Recovery165 terminates in `rvv_permute_restart_e8_m8_ops7`, SHA256
40d2dd50083bee424679ce2cb7c79b1cdf89b37ae0015dc3c99d42962155d3e1.
No numerical output or final2688-case marker exists; the stalled trial
and numerical outcome remain unknown. All20 terminal hashes verify in
`rvv_recovery08_165/terminal_scene`. Cycles11680084162 ->12258311720
advance while retired1693955153, trap_count256356 and PCs remain fixed.
Last retired0x106f4 is `vmerge.vim v24,v8,15,v0`; unqualified head0x106f8
is `csrr a0,vstart`, with e8/m8 vtype in the exact ELF disassembly.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. Unlike nearby records, the retained
historical trap cause is2 (tval3222283635), but its count and trap PC remain
unchanged across both samples; no new trap during the interval is proved.
These establish no retirement, not that merge never retired or a specific
internal cause. The exact ELF passes both reference VLENs. Inventory28
records132 passes,55 complete numerical failures,19 stalls and192
unattempted children. Recovery166 retains exactly all192 pending records
after the one-result prefix; original parent outcomes remain unchanged.

Recovery164 terminates in `rvv_permute_restart_e8_m8_ops6`, SHA256
685086c17c4c5d824b6b5586fbb33c0d6eda72ee6a598998aecf312b33493650.
No numerical output or final2688-case marker exists; the stalled trial
and numerical outcome remain unknown. All20 terminal hashes verify in
`rvv_recovery08_164/terminal_scene`. Cycles11656273977 ->12180061528
advance while retired1693511464, trap_count256262 and PCs remain fixed.
Last retired0x106c6 is `vmerge.vim v24,v8,-16,v0`; unqualified head0x106ca
is `csrr a0,vstart`, with e8/m8 vtype in the exact ELF disassembly.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. These establish no retirement, not that
merge never retired or a specific internal cause; trap9 is historical.
The exact ELF passes both reference VLENs. Inventory27 records132 passes,
55 complete numerical failures,18 stalls and193 unattempted children.
Recovery165 retains exactly all193 pending records after the one-result
prefix; original parent outcomes remain unchanged.

Recovery163 terminates in `rvv_permute_restart_e8_m8_ops5`, SHA256
266b324b9a8ea18dd46736ff9a9efaa95b65e25f8152e4d51287acbc00ed887a.
No numerical output or final2688-case marker exists for this child; the
stalled trial and numerical outcome remain unknown. All20 terminal hashes
verify in `rvv_recovery08_163/terminal_scene`. Cycles12196446083
->12726219467 advance while retired1946727664, trap_count290384 and PCs
remain fixed. Last retired0x1069a is `vmerge.vxm v24,v8,t3,v0`;
unqualified head0x1069e is `csrr a0,vstart`, with e8/m8 vtype in the exact
ELF disassembly. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding transactions or response errors. This establishes no
retirement, not that merge never retired or a specific internal cause;
trap9 is historical. The exact ELF passes both reference VLENs.
Inventory26 records132 passes,55 complete numerical failures,17 stalls
and194 unattempted children. Recovery164 retains exactly all194 pending
records after the five-result prefix; original parent results are unchanged.

Recovery163 `resume/board_report_live01.json` records e16/m8 move ops8..11
passing all2688 configurations each. Together with the separate e16/m8
merge ops4..7 stalls, this is a measured operation boundary, not evidence
that all e16/m8 operations fail or proof of an internal root cause.
Inventory25 audits exact identities and final markers:132 passes,55 complete
numerical failures,16 stalls,1 running and194 unattempted children (187
complete numerical results). The running e8/m8 op5 remains unclassified.

Recovery162 terminates in `rvv_permute_restart_e16_m8_ops7`, SHA256
ef0d797b4d64c9d9c3e4af986230bec7c4cb1c2b1fdc346cad3fe5bd73bd96b5.
No numerical output or final2688-case marker was retained; the stalled
trial and numerical outcome remain unknown. All20 terminal hashes verify
in `rvv_recovery08_162/terminal_scene`. Cycles11628801985 ->12186400835
advance while retired1690951365, trap_count256869 and PCs remain fixed.
Last retired0x1070a is `vmerge.vim v24,v8,15,v0`; unqualified head0x1070e
is `csrr a0,vstart`, with e16/m8 vtype in the exact ELF disassembly.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. These establish no retirement, not that
merge never retired or a specific internal cause; trap9 is historical.
The exact ELF passes both reference VLENs. Inventory24 records128 passes,
55 complete numerical failures,16 stalls and199 unattempted children.
Recovery163 continues the pending queue using the original image.

Recovery161 terminates in `rvv_permute_restart_e16_m8_ops6`, SHA256
dc2ac9c8d3ce66c5f59fceef44d68fbc07ee0eeb1e5ae27a573eb753d34142eb.
No numerical output or final2688-case marker was retained for this child;
the stalled trial and numerical outcome remain unknown. All20 terminal
hashes verify in `rvv_recovery08_161/terminal_scene`. Cycles13063216395
->13649988319 advance while retired2190959499, trap_count342503 and PCs
remain fixed. Last retired0x106dc is `vmerge.vim v24,v8,-16,v0`; unqualified
head0x106e0 is `csrr a0,vstart`, with e16/m8 vtype in the exact disassembly.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. These establish no retirement, not that
merge never retired or a specific internal cause. Historical trap9 is not
a new trap during the interval. The exact ELF passes both reference VLENs.
The16 preceding children in this recovery pass their full2688-case checks.
`rvv_permute_partition_inventory23` records128 passes,55 complete numerical
failures,15 stalls and200 unattempted children. Recovery162 preserves exactly
all200 pending records after the17-result prefix; no completed result is
rerun or replaced, and original parent outcomes remain unchanged.

Recovery161 `resume/board_report_live01.json` records all eight merge/move
ops4..11 passing at both e32/m8 and e64/m8 (2688 configurations per child).
This measured boundary rules out classifying all m8 merge/move as failed;
it does not establish the internal cause of e8/m8 or e16/m8 stalls. Exact
identities, nonce and final numerical markers are audited in
`rvv_permute_partition_inventory22`, which records128 passes,55 numerical
failures,14 stalls,1 running and200 unattempted children (183 complete numerical
results). The running e16/m8 op6 is unclassified and remains a separate case.

Recovery160 also isolates `rvv_permute_restart_e16_m8_ops5`, SHA256
511f1ca07332fdf5759cfcc4c7ae12fc78845ec82246827c52876a39711269b3.
No numerical output or final2688-case marker exists; the stalled trial and
numerical outcome remain unknown. All20 hashes verify in
`rvv_recovery08_160/terminal_scene`. Cycles11651386487 ->12211702570
advance while retired1696607037, trap_count259139 and PCs remain fixed.
Last retired0x106b0 is `vmerge.vxm v24,v8,t3,v0`; unqualified head0x106b4
is `csrr a0,vstart`, with e16/m8 vtype in the exact ELF disassembly.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. These establish no retirement, not that
merge never retired or a specific internal cause. Historical trap9 is not
a new trap during the interval. The exact ELF passes both reference VLENs.
`rvv_permute_partition_inventory21` records112 passes,55 complete numerical
failures,14 stalls and217 unattempted children. Recovery161 retains exactly
all217 pending records and starts e32/m8 ops4..8; e16/m8 remaining cases are
deferred, not omitted or classified as failed. Original parent outcomes and
all case conditions remain unchanged.

Recovery159 isolates `rvv_permute_restart_e16_m8_ops4`, SHA256
275c9d872111a37c28e7466b7fbd7f263a545918315b8a98284d456950d22118.
No numerical output or final2688-case marker was retained; the stalled
trial and numerical outcome remain unknown. All20 archived hashes verify
in `rvv_recovery08_159/terminal_scene`. Cycles11702226023 ->12266422923
advance while retired1696841672, trap_count259704 and PCs remain fixed.
Last retired0x10684 is `vmerge.vvm v24,v8,v16,v0`; unqualified head0x10688
is `csrr a0,vstart`, with e16/m8 vtype in the exact ELF disassembly.
Both snapshots have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. These establish no retirement, not that
merge never retired or a shared internal cause with e8 stalls. Historical
trap9 is not a new trap during the interval. The exact ELF passes both
reference VLENs; passing e16/m4 is not substituted for e16/m8 coverage.
`rvv_permute_partition_inventory20` records112 passes,55 complete numerical
failures,13 stalls and218 unattempted children. Recovery160 preserves exactly
all218 pending records. Its already-frozen order precedes the e16/m8 shape
risk change, which applies only to future ordering; no case, configuration
or original parent outcome is changed. The ordering regression explicitly
retains e32/m8 and e64/m8 ordinary moves ahead of this measured risk shape.

Recovery158 terminates in `rvv_permute_restart_e8_m8_ops4`, SHA256
dbb3abd19082a3e8f572b5a74d765d84d6b9a48ca6c35952908c576a65f2c881.
No numerical output or final2688-case marker was retained for this child;
the stalled trial and numerical outcome remain unknown. All20 terminal
hashes verify in `rvv_recovery08_158/terminal_scene`. Cycles20921378039
->21485037088 advance while retired4111118916, trap_count939687 and PCs
remain fixed. Last retired0x1066a is `vmerge.vvm v24,v8,v16,v0`; unqualified
head0x1066e is `csrr a0,vstart`, with e8/m8 vtype in the exact disassembly.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. These establish no retirement, not that
merge never retired or a shared internal cause with e8/m4. Historical trap9
is not a new trap during the interval. The exact ELF passes both reference
VLENs. The128 preceding children in this recovery have full numerical markers:
88 pass and40 fail. `rvv_permute_partition_inventory19` records112 passes,
55 complete numerical failures,12 stalls and219 unattempted children.
Recovery159 preserves exactly all219 pending records after the129-result
prefix and starts e16/m8 merge/move; remaining e8/m8 cases are deferred by
scheduling risk only. No case or configuration is omitted and original parent
outcomes remain unchanged.

Recovery158 `resume/board_report_live03.json` also records all eight
merge/move ops4..11 passing at e32/m4 and e64/m4 (2688 configurations per
child). Together with e16/m4, this is measured evidence against treating
LMUL=m4 alone as the stall cause. It does not establish any internal cause.
Exact identities and markers are audited in `rvv_permute_partition_inventory18`.

Recovery158 `resume/board_report_live01.json` records all eight e16/m4
merge/move children ops4..11 passing2688 configurations each. Thus the e8/m4
stall must not be generalized to every m4 shape. The exact identities and
numerical markers are bound by `rvv_permute_partition_inventory16`; no shared
internal cause or untested-shape correctness is inferred from this boundary.

Recovery157 also isolates `rvv_permute_restart_e8_m4_ops5`, SHA256
a3173f446f270106549ba4d8ce3bbb835dbbb17c84d648dc4174db8093144b8e.
No numerical output or final2688-case marker was retained; the stalled trial
and numerical outcome remain unknown. All20 archived hashes verify in
`rvv_recovery08_157/terminal_scene`. Cycles11922609198 ->12526525609
advance while retired1736288321, trap_count275009 and PCs remain fixed.
Last retired0x1069a is `vmerge.vxm v24,v8,t3,v0`; unqualified head0x1069e
is `csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding transactions or response errors. These establish no retirement,
not that merge never retired or a specific internal cause. Historical trap9
is not a new trap during the interval. The exact ELF passes both reference
VLENs. `rvv_permute_partition_inventory15` records24 passes,15 complete
numerical failures,11 stalls and348 unattempted children. Recovery158 preserves
exactly all348 pending records and starts e16/mf2 ops0..4, with the e8/m4
shape risk policy now active. No case is omitted or declared failed by ordering.

Recovery156 isolates `rvv_permute_restart_e8_m4_ops4`, SHA256
b13041229f8f71db83ba106be4be868db4b02d1e65887a558271236ed26dd68f.
No numerical output or final2688-case marker was retained; the stalled trial
and numerical outcome remain unknown. All20 archived hashes verify in
`rvv_recovery08_156/terminal_scene`. Cycles11923670491 ->12518926058
advance while retired1736153580, trap_count274326 and PCs remain fixed.
Last retired0x1066a is `vmerge.vvm v24,v8,v16,v0`; unqualified head0x1066e
is `csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding transactions or response errors. These establish no retirement,
not that merge never retired or a particular internal completion cause.
Historical trap9 is not a new trap during the interval. The exact ELF passes
both reference VLENs. Smaller e8/mf2,m1,m2 merge/move results do not establish
the correctness of e8/m4. A shared cause with gather stalls is not established.
`rvv_permute_partition_inventory14` records24 passes,15 complete numerical
failures,10 stalls and349 unattempted children. Recovery157 retains exactly
all349 pending records. Its already-frozen order precedes the new e8/m4
shape-risk policy; future queues defer that shape while retaining every case
and configuration, without changing original parent results or declaring
untested forms failed.

## RVV-19: Gather Restart Corrupts Prestart Destination Elements

Recovery179 completes all2688 configurations in each of ten e32/m8 and
e64/m8 gather children, operation order0/1/2/3/20. The final error counts
are33688/22776/22776/22776/32064 for e32/m8 and
16552/11424/11424/11424/15400 for e64/m8. Retained details include
seed0/scalar0/VL2/mask0/vstart1, prestart element0 expected91 becoming
1784607161 (e32, op1/2/20),2839576497 (e32, op3),
10611818013476712889 (e64, op1/2/20) or1757655531243208625 (e64, op3).
The immutable raw `rvv_recovery08_179/resume/board_report_live02.json`
is verified by inventory47 against exact inputs and full-case markers.
These ten complete numerical failures are distinct from the e8/e16 wide
group stalls; each exact ELF passes both reference VLENs. Inventory47
records140 passes,80 complete failures,32 stalls, one running slide1up
child and145 unattempted children. No internal shared cause is inferred.

Recovery178 isolates `rvv_permute_restart_e16_m8_ops20`, SHA256
21a28efe2ef7b79f9511c9b793bf0235bbc81944b27f1196179642f2a5a8c888.
Nine retained details show prestart elements expected91 becoming61881,
44879,0 or26315 at VL2/3/256 with vstart1/128, seed0/scalar0/mask0.
No final2688-case marker exists; the exact stalled trial and complete
numerical outcome remain unknown. All20 terminal hashes verify in
`rvv_recovery08_178/terminal_scene`. Cycles11562694318 ->12123964265
advance while retired1681333534, trap_count256863 and PCs remain fixed.
Last retired0x10994 is `vrgatherei16.vv v24,v8,v16,v0.t`; unqualified
head0x10998 is `csrr a0,vstart`. Both samples have flags0, no watchdog
snapshot and zero DDR outstanding transactions or response errors.
This proves no retirement, not that gather never retired or a specific
internal cause; trap9 is historical. The exact ELF passes both reference
VLENs. Inventory45 records140 passes,70 complete numerical failures,
32 stalls and156 unattempted children. Recovery179 retains exactly all156
pending records after the one-result prefix; original parent outcomes
remain unchanged.

Recovery177 isolates `rvv_permute_restart_e16_m8_ops3`, SHA256
16a715c87479c206545de7e5e9173fcd5ac93a48fe71a6c9dcfd7466993bd853.
Nine retained details show prestart elements expected91 becoming32689 at
VL2/3/256 with vstart1/128, seed0/scalar0/mask0. No final2688-case marker
exists; the exact stalled trial and complete numerical outcome remain unknown.
All23 terminal hashes verify in `rvv_recovery08_177/terminal_scene`.
Cycles11630362383 ->12217263198 advance while retired1685606799,
trap_count257414 and PCs remain fixed. Last retired0x1064a is
`vrgather.vi v24,v8,31,v0.t`; unqualified head0x1064e is `csrr a0,vstart`,
with e16/m8 vtype in the exact ELF disassembly. Both samples have flags0,
no watchdog snapshot and zero DDR outstanding transactions or response
errors. This proves no retirement, not that gather never retired or a
specific internal cause; trap9 is historical. The exact ELF passes both
reference VLENs. Inventory44 records140 passes,70 complete numerical
failures,31 stalls and157 unattempted children. Recovery178 retains exactly
all157 pending records after the one-result prefix; original parent
outcomes remain unchanged.

Recovery176 isolates `rvv_permute_restart_e16_m8_ops2`, SHA256
13a9b694ade91e25687108b4bf93b50ecc2d80c3a2a6fd532b269dac3b4aafcf.
Nine retained details show prestart elements expected91 becoming61881 at
VL2/3/256 with vstart1/128, seed0/scalar0/mask0. No final2688-case marker
exists; the exact stalled trial and complete numerical outcome remain unknown.
All20 terminal hashes verify in `rvv_recovery08_176/terminal_scene`.
Cycles11595627634 ->12158935258 advance while retired1683120794,
trap_count258053 and PCs remain fixed. Last retired0x1060e is
`vrgather.vi v24,v8,0,v0.t`; unqualified head0x10612 is `csrr a0,vstart`,
with e16/m8 vtype in the exact ELF disassembly. Both samples have flags0,
no watchdog snapshot and zero DDR outstanding transactions or response
errors. This proves no retirement, not that gather never retired or a
specific internal cause; trap9 is historical. The exact ELF passes both
reference VLENs. Inventory43 records140 passes,70 complete numerical
failures,30 stalls and158 unattempted children. Recovery177 retains exactly
all158 pending records after the one-result prefix; original parent
outcomes remain unchanged.

Recovery175 isolates `rvv_permute_restart_e16_m8_ops1`, SHA256
25c6f4e22b01d0d1457c18e289cca6fe7cd3e85113175a3c9e5c82e3d56c3d2a.
Nine retained details show prestart elements expected91 becoming61881 at
VL2/3/256 with vstart1/128, seed0/scalar0/mask0. No final2688-case marker
exists; the exact stalled trial and complete numerical outcome remain unknown.
All20 terminal hashes verify in `rvv_recovery08_175/terminal_scene`.
Cycles11582170335 ->12170361648 advance while retired1683111710,
trap_count257661 and PCs remain fixed. Last retired0x105ee is
`vrgather.vx v24,v8,t3,v0.t`; unqualified head0x105f2 is `csrr a0,vstart`,
with e16/m8 vtype in the exact ELF disassembly. Both samples have flags0,
no watchdog snapshot and zero DDR outstanding transactions or response
errors. This proves no retirement, not that gather never retired or a
specific internal cause; trap9 is historical. The exact ELF passes both
reference VLENs. Inventory42 records140 passes,70 complete numerical
failures,29 stalls and159 unattempted children. Recovery176 retains exactly
all159 pending records after the one-result prefix; original parent
outcomes remain unchanged.

Recovery174 terminates in `rvv_permute_restart_e16_m8_ops0`, SHA256
15b24c0568fe61b3868437b8b35d67975d8e4390c84f3d6e41ec504a009bfb22.
Retained details show prestart destination corruption at VL2/3/256,
seed0/scalar0/mask0, vstart1/128: expected91 becomes61881 or other source
values. The last sparse trial trace is VL512/vstart256, not proof of the
precise stalled trial. No final2688-case marker exists. All20 terminal
hashes verify in `rvv_recovery08_174/terminal_scene`.
Cycles13759569784 ->14318760203 advance while retired1757850992,
trap_count345712 and PCs remain fixed. Last retired0x10630 is
`vrgather.vv v24,v8,v16,v0.t`; unqualified head0x10634 is `csrr a0,vstart`,
with e16/m8 vtype in the exact ELF disassembly. Both samples have flags0,
no watchdog snapshot and zero DDR outstanding transactions or response
errors. This proves no retirement, not that gather never retired or a
specific internal cause; trap9 is historical. The exact ELF passes both
reference VLENs. Inventory41 records140 passes,70 complete numerical
failures,28 stalls and160 unattempted children. Recovery175 retains exactly
all160 pending records after the one-result prefix; original parent
outcomes remain unchanged.

Recovery179 startup also exits before RVV observation because owned Vivado
tree cleanup fails: child9736 has already exited; parent25704 is terminated.
The raw report records execution_started/launch_attempted, the Linux-ready
UART marker (13484 bytes, SHA256
62303e763bfa17a1692971adcb5ac74dedc958cde04fccddd2107158859e3e80),
the unchanged kernel hash, locked/isolated Ethernet, AW=B=3209459,
AR=RLAST=39530822 and zero response errors. All10 files in
`rvv_recovery08_179/startup_cleanup_scene` verify. With the task terminal,
no active transport/observer and the board lock free, the byte-identical
recovery137 resume-only script exposes the156 preloaded pending cases on
the existing Linux. Observer22688 and supervisor21 resume without another
reset or reprogramming; the original failed loader report is preserved.
These checks are startup evidence, not numerical RVV acceptance.

Recovery174 startup exits before any RVV result because owned Vivado tree
cleanup reports child PID7016 already gone and parent PID16504 terminated.
The raw failed loader report records execution_started/launch_attempted,
the Linux-ready marker, the unchanged kernel hash, locked/isolated Ethernet,
balanced AW/B and AR/RLAST counts, and zero response errors. It is not a
confirmed board no-retirement stall. The loader report/UART/state and task
definition are archived with all10 hashes verified in
`rvv_recovery08_174/startup_cleanup_scene`. With the wrapper terminal, no
board transport/observer remaining and the exclusive board lock available,
the byte-identical recovery137 resume-only script validates startup gates
and reattaches the already booted Linux without reset or reprogramming.
Observer15660 and supervisor20 resume the161 pending cases. The original
failed loader report remains failed; this recovery is not an RVV result.

Recovery173 isolates `rvv_permute_restart_e8_m8_ops3`, SHA256
ef3a7ff6d6dc48a7e5f20adbb7954490c08c7cbbdcd03afe9bbd4859dee7580c.
Three retained details show prestart element0 expected91 becoming177 at
VL2/3 with vstart1, seed0/scalar0/mask0. No final2688-case marker exists;
the exact stalled trial and complete numerical outcome remain unknown.
All20 terminal hashes verify in `rvv_recovery08_173/terminal_scene`.
Cycles11615142821 ->12178722697 advance while retired1683081790,
trap_count256001 and PCs remain fixed. Last retired0x1063e is
`vrgather.vi v24,v8,31,v0.t`; unqualified head0x10642 is `csrr a0,vstart`,
with e8/m8 vtype in the exact ELF disassembly. Both samples have flags0,
no watchdog snapshot and zero DDR outstanding transactions or response
errors. This proves no retirement, not that gather never retired or a
specific internal cause; trap9 is historical. The exact ELF passes both
reference VLENs. Inventory40 records140 passes,70 complete numerical
failures,27 stalls and161 unattempted children. Recovery174 retains exactly
all161 pending records after the one-result prefix; original parent
outcomes remain unchanged.

Recovery172 isolates `rvv_permute_restart_e8_m8_ops2`, SHA256
cc5015d9e7838bfc4f0d4f2b0627e6a08930bd4058b12651a4f988a5c9b1d712.
Three retained details show prestart element0 expected91 becoming185 at
VL2/3 with vstart1, seed0/scalar0/mask0. No final2688-case marker exists;
the exact stalled trial and complete numerical outcome remain unknown.
All20 terminal hashes verify in `rvv_recovery08_172/terminal_scene`.
Cycles11602427796 ->12167503460 advance while retired1683445858,
trap_count253921 and PCs remain fixed. Last retired0x10600 is
`vrgather.vi v24,v8,0,v0.t`; unqualified head0x10604 is `csrr a0,vstart`,
with e8/m8 vtype in the exact ELF disassembly. Both samples have flags0,
no watchdog snapshot and zero DDR outstanding transactions or response
errors. This proves no retirement, not that gather never retired or a
specific internal cause; trap9 is historical. The exact ELF passes both
reference VLENs. Inventory39 records140 passes,70 complete numerical
failures,26 stalls and162 unattempted children. Recovery173 retains exactly
all162 pending records after the one-result prefix; original parent
outcomes remain unchanged.

Recovery171 isolates `rvv_permute_restart_e8_m8_ops1`, SHA256
7b6623f49a5aee9ae03a3365dc69e898b922ffc61a113c58aae71f96342c83cf.
Three retained details show prestart element0 expected91 becoming185 at
VL2/3 with vstart1, seed0/scalar0/mask0. No final2688-case marker exists;
the exact stalled trial and complete numerical outcome remain unknown.
All20 terminal hashes verify in `rvv_recovery08_171/terminal_scene`.
Cycles11583251930 ->12148995302 advance while retired1682631608,
trap_count254552 and PCs remain fixed. Last retired0x105dc is
`vrgather.vx v24,v8,t3,v0.t`; unqualified head0x105e0 is `csrr a0,vstart`,
with e8/m8 vtype in the exact ELF disassembly. Both samples have flags0,
no watchdog snapshot and zero DDR outstanding transactions or response
errors. This proves no retirement, not that gather never retired or a
specific internal cause; trap9 is historical. The exact ELF passes both
reference VLENs. Inventory38 records140 passes,70 complete numerical
failures,25 stalls and163 unattempted children. Recovery172 retains exactly
all163 pending records after the one-result prefix; original parent
outcomes remain unchanged.

Recovery170 terminates in `rvv_permute_restart_e8_m8_ops0`, SHA256
bcee9b246a8bc0a075a558510e356ccf72e2b80598ae7209731f3b9b8fc1deac.
Retained details show prestart element0 expected91 becoming185 at
VL2/3/512 with vstart1. The last sparse trial trace is VL512/vstart256;
it does not establish the precise stalled trial. No final2688-case marker
exists for this child. All20 terminal hashes verify in
`rvv_recovery08_170/terminal_scene`. Cycles13270019332 ->13838599670
advance while retired2149501152, trap_count398247 and PCs remain fixed.
Last retired0x1061c is `vrgather.vv v24,v8,v16,v0.t`; unqualified head0x10620
is `csrr a0,vstart`, with e8/m8 vtype in the exact ELF disassembly.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. This proves no retirement, not that
gather never retired or a specific internal cause; trap9 is historical.
The exact ELF passes both reference VLENs. The15 preceding gather children
retain their complete numerical failures. Inventory37 records140 passes,
70 complete numerical failures,24 stalls and164 unattempted children.
Recovery171 retains exactly all164 pending records after the16-result
prefix; original parent outcomes remain unchanged.

Recovery170 `resume/board_report_live02.json` records all five gather ops
0/1/2/3/20 completing2688 configurations each at e16/m4, e32/m4 and e64/m4.
All15 children fail numerically, without a stall among these completed
children. Error counts in that operation order are:

- e16/m4:32064,22776,22776,22776,32064.
- e32/m4:15824,11424,11424,11424,15400.
- e64/m4:7968,5760,5760,5760,8112.

First retained details use seed0/scalar0/VL2/mask0/vstart1, element0:
expected91 becomes61881 at e16 (op3:32689),1784607161 at e32
(op3:2839576497), and10611818013476712889 at e64
(op3:1757655531243208625). These independently demonstrate prestart
destination corruption; they do not establish a shared internal cause.
Inventory36 audits exact ELF identities, nonces and final markers and
records140 passes,70 complete numerical failures,23 stalls,1 running and164
unattempted children (210 complete numerical results). The running e8/m8
op0 has mismatch details but no final result in this report. Inventory35
preserves the earlier six-result prefix. Original parent results are unchanged.

Recovery169 isolates `rvv_permute_restart_e8_m4_ops20`, SHA256
15469ee7ca24fd7a7dac6e282358872a5d9c3dfc836e5de363661925fac70c18.
Ten retained details show prestart corruption for op20, seed0/scalar0/mask0:
VL2/3 with vstart1 and VL256 with vstart1/128 expect91 but return185,
79,0 or203 at reported prestart elements. No final2688-case marker exists;
the exact stalled trial and complete numerical outcome remain unknown.
All20 terminal hashes verify in `rvv_recovery08_169/terminal_scene`.
Cycles11600071253 ->12162646889 advance while retired1689379256,
trap_count260307 and PCs remain fixed. Last retired0x10980 is
`vrgatherei16.vv v24,v8,v16,v0.t`; unqualified head0x10984 is
`csrr a0,vstart`, with e8/m4 vtype in the exact ELF disassembly.
Both samples have flags0, no watchdog snapshot and zero DDR outstanding
transactions or response errors. This proves no retirement, not that
gather never retired or a specific internal cause; trap9 is historical.
The exact ELF passes both reference VLENs. Inventory34 records140 passes,
55 complete numerical failures,23 stalls and180 unattempted children.
Recovery170 retains exactly all180 pending records after the one-result
prefix; original parent outcomes remain unchanged.

Recovery168 isolates `rvv_permute_restart_e8_m4_ops3`, SHA256
a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b.
Nine retained details show prestart corruption for op3, seed0/scalar0/mask0:
VL2/3 with vstart1 and VL256 with vstart1/128 retain expected91 but return177
at reported prestart elements. No final2688-case marker exists; the exact
stalled trial and complete numerical outcome remain unknown. All20 terminal
hashes verify in `rvv_recovery08_168/terminal_scene`. Cycles12221031926
->12789029119 advance while retired1955925713, trap_count291152 and PCs
remain fixed. Last retired0x1063e is `vrgather.vi v24,v8,31,v0.t`;
unqualified head0x10642 is `csrr a0,vstart`, with e8/m4 vtype in the exact
ELF disassembly. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding transactions or response errors. This proves no retirement,
not that gather never retired or a specific internal cause; trap9 is
historical. The exact ELF passes both reference VLENs. Four preceding move
children pass all2688 configurations each. Inventory33 records140 passes,
55 complete numerical failures,22 stalls and181 unattempted children.
Recovery169 retains exactly all181 pending records after the five-result
prefix; original parent outcomes remain unchanged.

Recovery158 `resume/board_report_live03.json` completes all five gather
children ops0/1/2/3/20 at additional shapes, each over2688 configurations.
Errors in that operation order: e32/mf2 1624/1488/1488/1488/1488;
e32/m1 4096/2904/2904/2904/3328; e32/m2 7704/5760/5760/5760/8112;
e64/m1 2000/1488/1488/1488/1488; e64/m2 3856/2904/2904/2904/3328.
These are full numerical failures, not stalls. All eight merge/move ops4..11
pass for each of e16/mf2,m1,m2,m4; e32/mf2,m1,m2,m4; e64/m1,m2,m4,
adding88 complete passes in this recovery. The exact report, nonce, child
hashes and markers are audited in `rvv_permute_partition_inventory18`, which
records112 passes,55 numerical failures,11 stalls,1 running and219 unattempted
children (167 complete numerical results). The running e8/m8 op4 remains
unclassified; a smaller-group pass is not substituted for it.

Recovery158 `resume/board_report_live01.json` adds17 complete numerical
gather failures, each over2688 configurations. For ops0/1/2/3/20 respectively:
e16/mf2 errors3328/2904/2904/2904/3328; e16/m1 errors8112/5760/5760/5760/8112;
e16/m2 errors15400/11424/11424/11424/15400. e32/mf2 ops0/1 have1624/1488
errors. First retained VL2/vstart1/seed0/scalar0/mask0 details again show
prestart element0 sentinel91 overwritten: e16 actual61881 (32689 for op3),
e32 actual1784607161. All eight merge/move ops4..11 pass at each of
e16/mf2,m1,m2,m4, adding32 complete passes. The exact report, nonce, child
hashes and final numerical markers are audited in
`rvv_permute_partition_inventory16`, recording56 passes,32 numerical failures,
11 stalls,1 running and298 unattempted children (88 complete numerical results).
These failures extend the measured EEW coverage, not proof of an internal
cause. Original parent outcomes and test conditions remain unchanged.

Recovery155 terminates in `rvv_permute_restart_e8_m4_ops2` (immediate0), SHA256
498805cf438a11729e74f0ac7b74068fa5e19bbcf56318790b01afc798d18b65.
Retained seed0/scalar0/mask0/VL2/3/256 details show prestart sentinel91
overwritten (first element actual185); no final2688-case marker exists.
The last detail does not identify the stalled trial. All20 archived hashes
verify in `rvv_recovery08_155/terminal_scene`. Cycles11981587465 ->12541411883
advance while retired1743062888, trap_count280298 and PCs remain fixed.
Last retired0x10600 is `vrgather.vi v24,v8,0,v0.t`; unqualified head0x10604
is `csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding transactions or response errors. These establish no retirement,
not that gather never retired or a specific internal completion cause.
Historical trap9 is not a new trap during the interval. The exact ELF passes
both reference VLENs. `rvv_permute_partition_inventory13` records24 passes,
15 complete numerical failures,9 stalls and350 unattempted children.
Recovery156 retains exactly all350 pending records and starts e8/m4 ops4..11;
the wide-group gather risk ordering now takes effect without omitting any
pending case, changing conditions, or replacing original parent outcomes.

Recovery154 terminates in `rvv_permute_restart_e8_m4_ops1`, SHA256
8f5fd128fdc39014de31bd72f9e997f76d07382ee6268d7e6da83a59b7ddfcd8.
Retained seed0/scalar0/mask0/VL2/3/256 details show prestart sentinel91
overwritten (first element actual185); no final2688-case marker exists and
the last detail does not identify the stalled trial. All20 terminal hashes
verify in `rvv_recovery08_154/terminal_scene`. Cycles15721531273 ->16320222915
advance while retired1866992662, trap_count423693 and PCs remain fixed.
Last retired0x105dc is `vrgather.vx v24,v8,t3,v0.t`; unqualified head0x105e0
is `csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding transactions or response errors. These establish no retirement,
not that gather never retired or a specific internal completion cause.
Historical trap9 is not a new trap during the interval. The exact ELF passes
both reference VLENs. `rvv_permute_partition_inventory12` records24 passes,
15 complete numerical failures,8 stalls and351 unattempted children.
Recovery155 preserves exactly all351 pending records. Its already-frozen
order precedes the new wide-group gather risk policy; that policy changes
future ordering only, retaining every pending identity and configuration.
Recovery154's earlier startup cleanup error is separately archived with10
verified hashes in `startup_cleanup_scene`: Linux ready UART, original kernel
SHA256, balanced locked isolated Ethernet and no live board transport were
verified before reattaching, without reset. The failed loader report remains
failed; the resume script is byte-identical to recovery137's guarded script.

Recovery153 terminates in `rvv_permute_restart_e8_m4_ops0`, SHA256
b2d4f2377812195085e141b2a061443d5e7b88b956051e08cf37880018ece4e2.
Retained details show prestart corruption at VL2/3/256; the last retained
trace is VL512/vstart256. Sparse trace coverage does not identify the exact
stalled trial. No final2688-case marker exists. All20 archived hashes verify
in `rvv_recovery08_153/terminal_scene`. Cycles14547302387 ->15111322037
advance while retired2632262921, trap_count469362 and PCs remain fixed.
Last retired0x1061c is `vrgather.vv v24,v8,v16,v0.t`; unqualified head0x10620
is `csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
outstanding transactions or response errors on both DDR channels. These
establish no retirement, not that gather never retired or its internal cause.
Historical trap9 is not a new trap during this interval. The exact ELF passes
both reference VLENs. `rvv_permute_partition_inventory11` records24 passes,
15 complete numerical failures,7 stalls and352 unattempted children.
Recovery154 preserves exactly all352 pending records after the28-result prefix;
no completed result is rerun or substituted and no parent outcome is replaced.

Recovery153 `resume/board_report_live02.json` additionally completes e8/m2
op3 with22776 errors and op20 with31064 errors, each over2688 configurations.
All eight e8/m2 merge/move children ops4..11 pass2688 configurations each.
`rvv_permute_partition_inventory10` binds the exact report, nonce and child
identities and records24 passes,15 numerical failures,6 stalls,1 running and
352 unattempted children. There are39 complete numerical outcomes; the
running e8/m4 op0 is not classified from runtime duration alone.

Recovery153's immutable `resume/board_report_live01.json` adds nine full
numerical failures, each with2688 configurations: e8/mf2 op20 errors7832;
e8/m1 ops0/1/2/3 errors15600/10948/11424/11424 and op20 errors14880;
e8/m2 ops0/1/2 errors31760/21827/22776. This extends the observed symptom
to `vrgatherei16.vv`, not just ordinary gather. First retained details at
seed0/scalar0/VL2/mask0/vstart1 show prestart element0 sentinel91 replaced
by185 (177 for op3). Eight e8/m1 merge/move children ops4..11 instead pass
all2688 configurations each. The exact child identities, SHA256 values,
run nonce and full numerical markers are bound and audited in
`rvv_permute_partition_inventory09`; original parent outcomes remain unchanged.
This snapshot records16 passes,13 full numerical failures,6 stalls,1 running
and362 unattempted children. Scheduling risk is not a correctness verdict;
untested masked slides remain in the queue and no internal root cause is
claimed solely from these numerical symptoms.

Recovery147's immutable `resume/board_report_live01.json` completes four
e8/mf2 single-operation gather children, each with2688 configurations and
exit1: ops0 (`vrgather.vv`)6200 errors, ops1 (`vrgather.vx`)5520 errors,
ops2 (`vrgather.vi` index0)5760 errors and ops3 (index31)5760 errors.
Their SHA256 identities, respectively, are
3a20367a502d7b31ce731ab74af5a4c33afdb71d283f58358c27c9a76d0ef04d,
1e65a0e5d6a4ee47e879db8adcecc08474669e70a2942319102910d9fa6dde28,
eec5ee6baa00b6d408791725a9483dd223a0ff4d07a700d0da259180c518c5b9,
8106784dbc4ab0471dfd0752b884a10a9989efd7beefb00fbac5ac8d8f3b6285.
The retained seed0/scalar0/VL2/mask0/vstart1 details report element0
expected91 (loaded sentinel), actual185 for ops0/1/2 and177 for ops3.
VL32/vstart16 details also show prestart elements overwritten. These
full numerical results confirm prefix corruption across vv/vx/vi forms,
not an observation timeout; they do not establish an internal RTL cause.
The same exact ELFs pass both reference VLENs. Subsequent ops4..11 each
pass2688 configurations, demonstrating that partitioning exposes merge/move
coverage beyond the original parent stall without replacing that outcome.
`rvv_permute_partition_inventory02` binds12 completed numerical results
(4 failures,8 passes),1 running child and385 never attempted. This is a
frozen intermediate observation, not full398-child acceptance.

Before the recovery42 slideup stall, the same exact e8/m1 permutation ELF
records `op=0 seed=0 scalar=0 vl=2 mask=0 element=0 vstart=1
expected=91 actual=185`. Operation0 is `vrgather.vv v24,v8,v16,v0.t`
with disjoint register groups, tu/mu policy, destination initialized from
the0x5b output sentinel and vstart explicitly written before the operation.
Element0 is prestart and must retain91; this is a concrete prestart
destination corruption, not an inference from aggregate error counts.
VL3/start1 has the same element0 mismatch, and VL64/start32 logs multiple
prestart corruptions. The exact released ELF passes the bound VLEN512/1024
references with56448 configurations and zero errors. There is no completed
board numerical marker because a later operation stalls.

The full output and exact ELF remain in recovery42's terminal scene. The
observation does not prove that the later slideup stall shares its cause,
nor identify which internal lane, write-enable or queue is responsible.
Keep the numerical prestart symptom separate for a focused future repair;
do not count the stalled ELF as a completed numerical failure or pass.

Recovery43's exact e8/m2 ELF independently logs the same op0 VL2/start1
element0 expected91/actual185 corruption, also at VL3/start1. At
VL128/start64 it logs multiple corrupted prestart elements. Its later
slideup stall prevents a completed numerical marker; the numerical symptom
and stall are recorded separately, without claiming their internal causes.
The full output is preserved in `rvv_recovery08_43/terminal_scene/report.json`.

Recovery44's `rvv_permute_restart_e8_m4` records the same VL2/start1
element0 corruption, but stalls earlier at a gather boundary rather than
slideup: exact ELF SHA256
`ffcf7785c8bf6dcb553456b60df4240bd106855df4189193b3b635a20b3cb2d5`,
last PC0x1079e `vrgather.vv v24,v8,v16,v0.t`, head PC0x107a2
`csrr a0,vstart`. Cycles11430187769 to11944147025 advance while
retired1668341924, trap_count254439 and both PCs remain fixed. Halt flags
and watchdog are clear; both DDR channels have zero outstanding/errors.
All20 recorded hashes verify in `rvv_recovery08_44/terminal_scene`.
The final printed trial is not proof of active operands at the stall;
the head-PC probe has no validity bit. This establishes a no-retirement
gather/restart boundary, not a proven internal cause or numerical completion.
Recovery45 retains96 pending exact ELFs.

Recovery45 subsequently completes `rvv_permute_restart_e16_mf4` with
`RVV_PERMUTE_FAIL sew=16 cases=56448 errors=25422` and exit1, rather than
a stall. The scoped partial audit `rvv_recovery45_release36_partial01`
binds the exact released ELF, nonce/protocol inputs and both successful
VLEN512/1024 references. It also logs op0 VL2/start1 element0
expected91/actual61881, establishing prestart corruption at SEW16.
The total25422 includes other checks and is not a count attributed solely
to gather. Other permutation ELFs remain unaccepted by this partial audit.

Recovery49's exact e32/mf2 ELF also records op0 VL2/start1 element0
expected91/actual1784607161, extending the concrete gather prestart
corruption to SEW32. This output precedes the separately documented slideup
stall; it does not establish a shared internal cause or full numerical
completion. The immutable report is in `rvv_recovery08_49/terminal_scene`.

Recovery53's exact e64/m1 ELF records op0 VL2/start1 element0
expected91/actual10611818013476712889, extending measured gather prestart
corruption to SEW64. This precedes the separate slideup stall. Together
with the recorded SEW8/16/32 cases, the symptom spans all four SEWs, not
every configuration or a proven common internal root cause. The immutable
report is in `rvv_recovery08_53/terminal_scene`; no full numerical marker
was produced.

Recovery77's exact e8/m8 restart ELF again records op0 VL2/start1
element0 expected91/actual185 corruption, then stalls at the gather
completion boundary. ELF SHA256 is
`8de6bc735648afacd704f3cdcc00c2a1bc86ca8183f6fee5146077610d75e1a3`.
The last drained trial is VL512/vstart256. Last retired/head PCs
0x1076e/0x10772 decode `vrgather.vv v24,v8,v16,v0.t` and
`csrr a0,vstart`. Cycles11259407396 to11784925444 advance while
retired1636015089, trap_count239035 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_77/terminal_scene`.
The head lacks validity and the last retired instruction does not prove
gather never retired. Numeric prestart corruption and completion stall
remain distinct symptoms without a captured internal queue explanation.
No completed numerical marker exists; subsequent operations and trials
in this ELF remain uncovered. Recovery78 retains18 pending exact ELFs.

Recovery78's frozen live output (`rvv_recovery78_active_snapshot01.json`)
extends the concrete gather prestart corruption to e16/m8: op0, seed0,
scalar0, VL2/start1, mask0, element0 expected91/actual61881. VL256/start128
also logs multiple corrupted prestart elements. The snapshot's inputs and
nonce match the recovery78 protocol and the exact pending ELF hash.
Its status is still running, with the last drained trial VL512/start256;
neither numerical completion nor a stall is implied by this live snapshot.

Recovery78's observer subsequently stops incomplete because the first
snapshot command's cleanup reports its owned PID16316 already absent.
The snapshot itself exists; this transport cleanup failure is not stall
proof. An independent second read-only snapshot succeeds, then comparison
confirms the same run identity and fixed retired1644078596, trap_count243741
and last/head PCs0x107ba/0x107be while cycles11322205330 to19741098962
advance. Flags are0, neither snapshot is watchdog-halted, and both DDR
channels have zero outstanding/errors. The exact ELF SHA256 is
`6440459edce6c313d1dbb3bcb0043cd372e10430a85dff4958b76703956634e1`;
the last/head instructions are the gather/completion boundary.
`rvv_recovery08_78/terminal_scene/observer_report.json` preserves the
original incomplete observation; its separate verified report binds both
raw snapshots and retains the prestart corruption output. This independently
confirms the stall without treating cleanup failure as reset authority.
Head validity and internal cause remain unproven. Recovery79 retains17
pending exact ELFs; unexecuted trials within this ELF remain uncovered.

Recovery79's frozen live report (`rvv_recovery79_active_snapshot01.json`)
adds the e32/m8 gather prestart symptom: op0, seed0, scalar0, VL2/start1,
mask0, element0 expected91/actual1784607161; VL128/start64 also logs
multiple overwritten prestart elements. Exact ELF SHA256 is
`c387cd15d77b9e8c495513e62a0897b3693578459f54447c2279c57a89a0fe81`.
The snapshot's inputs, nonce and ELF hash match the recovery79 protocol.
The first-gather trace reaches VL256/start255. This report is still running,
not a completed numerical result or proof of a stall in a later operation.

Recovery80's frozen live report (`rvv_recovery80_active_snapshot01.json`)
records the e64/m8 gather prestart symptom: op0, seed0, scalar0, VL2/start1,
mask0, element0 expected91/actual10611818013476712889. VL64/start32 also
logs multiple corrupted prestart elements. Inputs, nonce and the exact
pending ELF hash match the recovery80 protocol. The first-gather trace
reaches VL128/start127. The frozen status is running, not numerical
completion or proof of a subsequent stall; later operations remain unverified.

## RVV-08: Large-Offset Byte Slideup Last-Element Mask Mismatch

Recovery07 live02 records numerical failures in `rvv_permute_e8_m4` and
`rvv_permute_e8_m8`, both exit1 with nine mismatches. The identical ELFs
pass both reference VLENs. Operation12 is `vslideup.vx v24,v8,t3,v0.t`;
the wrapper loads full-XLEN a6 into t3, uses disjoint source/destination
groups, vstart0 and tu/mu. For VL=VLMAX and offset=VLMAX-1, only the last
element can copy input[0] when that destination's mask bit is enabled.

At e8/m4, offset511/VL512/element511 with all-on mask expects185 for seed0
but gets91 (old sentinel). Sparse/all-off expect91 but get185 instead.
Seeds1/2 show the same enable inversion with values248/59. e8/m8 reproduces
the same nine mismatches at offset1023/VL1024/element1023. This is measured
destination-mask/write-enable misbehaviour, not a confirmed internal queue
or pointer cause. No cycle trace or isolated sequence-order test exists yet;
do not infer that the current instruction alone or one RTL line is responsible.

Evidence: `rvv_recovery08_07/resume/board_report_live02.json`, immutable
additions26 binaries/manifest and both reference reports. The observer
continues after these ordinary failures, unlike a no-retirement stall.

Live03 additionally records `rvv_permute_e16_m8` exit1 with nine mismatches
at offset511/VL512/element511. All-on gets the old91 instead of input[0];
sparse/all-off get input[0] instead of91. The seed values are61881,53752,
45371. Thus the observed phenomenon is not limited to byte elements.
The other 19 additions26 shapes pass. No later suite pass relabels these
three failing shapes; no RTL repair or exact internal cause is established.

## RVV-09: All-Off FP Comparisons Add Invalid Flags

Recovery07 live07 records completed FP16 packed-comparison failures at
mf4,mf2,m1,m2,m4; each runs17920 configurations and exits1. Both reference
VLENs pass the identical additions28 ELFs. Captured op0 (`vmfeq.vv`) with
seed0, all-off predicate (mode3), and initial flags0 returns NV16; initial
NX1 returns17 instead of1. At mf4 this already occurs at VL8. All-off
comparisons have no active elements and must not contribute FP exceptions.
Seed0's second vector has signaling NaN0x7c55 at element5, but that element
is masked off. The wrapper writes initial fflags immediately before the
target and reads it immediately afterwards, before destination readback.

This is excess-invalid-flag evidence, distinct from RVV-07's missing flags
in ordered reductions. Do not infer a shared internal cause. The retained
details have one error each in these all-off trials, while the ELF totals
include5256/5496 errors across all rotations/operations. The twenty-line
detail cap does not prove that every other mismatch is flag-only or that
all result bits passed. No RTL fix or exact internal flag path is claimed.

Evidence: `rvv_recovery08_07/resume/board_report_live07.json`, immutable
additions28 manifest/ELFs and both reference reports, and the comparison
wrapper and pinned SoftFloat fixtures. Remaining widths/shapes are still
running; absence of their result is not a pass.
Live08 now completes all15 additions28 ELFs, all failed. FP32 e32/m1
with all-off mask at VL16 returns16/17 instead of0/1; FP64 e64/m1
at VL8 does the same. Thus the excess-invalid phenomenon is observed at
all three FP widths, not only FP16. Totals for those two ELFs are5496
and5256 errors respectively. The exact internal stage remains unproven.
Evidence: `rvv_recovery08_07/resume/board_report_live08.json`.
Live10 also records failures in unmasked FP16 comparison shapes mf4,mf2,
m1,m2. At mf4, op4 (`vmfeq.vf`), seed0 and VL15 returns NV16/17 instead
of0/1 for initial flags0/1. Scalar input0 is boxed +0; active input0..14
contains no signaling NaN, while tail element15 is0x7c55. Tail elements
must not contribute exceptions even though mask-result tails may be
agnostic. This is a concrete unmasked excess-NV trial, not evidence that
the mask encoding alone is responsible. The totals1216/1184 errors remain
aggregate errors, not proof that every mismatch has this one explanation.
Evidence: `rvv_recovery08_07/resume/board_report_live10.json`, additions30
unmasked release and its independent references. No internal RTL stage
or shared mask/tail cause has been established.
Live12 completes all15 unmasked comparison ELFs with failures across
FP16/32/64. Four completed v8-alias FP16 ELFs also fail; their first
retained all-off trials return16/17 instead of0/1. All three source/destination
alias subsets have not yet completed, so no conclusion about every alias
shape is warranted. Evidence: `rvv_recovery08_07/resume/board_report_live12.json`.
Live13 records78 passes and65 failures, with the observer still live at
`rvv_fp_compare_alias_v0_e16_m1`. All15 v8-alias and all15 v16-alias
comparison ELFs have now failed, in addition to all15 unmasked comparison
ELFs. Two completed v0-alias FP16 shapes also fail, including all-off
NV16/17 instead of0/1. Remaining v0-alias shapes are not yet accepted.
These are numerical exits, not confirmed retirement stalls. Evidence:
`rvv_recovery08_07/resume/board_report_live13.json`.

Live14 completes all15 v0-alias comparison shapes with failures: all60
additions30 ELFs have failed. The campaign has78 passes,79 failures and
one running result, with ordinary numerical failures continuing execution.
The additional failure is recorded separately below.

Recovery11 live01 records12 completed unmasked v8-source-alias comparison
failures, through e64/m1. The e16/mf4 op4/seed0/VL15 trial returns16/17
instead of0/1 with exactly one counted error, matching the previously
observed unmasked excess-NV symptom. At e16/mf2 op2/seed1/VL1 the same
flag mismatch is retained. These observations extend alias coverage, not
proof of a new internal cause or of flag-only errors throughout the ELF.
Evidence: `rvv_recovery08_11/resume/board_report_live01.json`. All results
remain failures; ordinary failures did not stop execution.

Recovery11 live02 completes all45 additions45 unmasked alias ELFs with
numerical failures, then records eight failed additions46 unboxed ELFs.
Their first retained errors are op0 `vmfeq.vv`, all-off masks, excessNV16/17
instead of0/1. Op0 uses two vector sources and does not exercise malformed
scalar boxing. These lines therefore do not prove that scalar NaN-box
handling is broken; the release also contains vv baseline comparisons.
Keep the exact failures, and separate vf-only evidence before assigning
a scalar-boxing cause. Evidence: `rvv_recovery08_11/resume/board_report_live02.json`.

## RVV-10: FP slide1 restart numerical failure (classification pending)

Recovery146 confirms masked FP slide-up e64/m8 stalls:
`rvv_fp_move_restart_e64_m8_ops2`, SHA256
13bdc44ae20ff64571d5f6beb790996e38f3260a482b57a5afbcf0853505197c.
Four retained op2/seed0/scalar0/full-width-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1; no final numerical
marker or element classification exists. The stalled trial's parameters
cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_146/terminal_scene`; final collection
does not reset the board or launch another test.
Cycles11254673373 ->11823786132 advance while retired1627414175,
trap_count235915 and PCs remain fixed. Last retired0x1064c is
`vfslide1up.vf v24,v8,ft0,v0.t`; unqualified head0x10650 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot
and zero DDR outstanding/response errors. This does not prove the slide
never retired or identify the internal completion cause; historical traps
remain separate evidence.
`rvv_partition_inventory57` records72 passed,47 numerical failures and
57 stalls across all176 attempted children, with119 complete numerical
results and zero pending children. All4 e64 masked-slide-up shapes stall.
The supervisor terminates without another reset. Original parent outcomes
and incomplete numerical coverage are not superseded.

Recovery145 confirms masked FP slide-up e64/m4 stalls:
`rvv_fp_move_restart_e64_m4_ops2`, SHA256
0c56a2c8e5ec9809c7686e4f18427f474782d572d42a75497a6038aeb9ce4cfb.
Four retained op2/seed0/scalar0/full-width-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1; no final numerical
marker or element classification exists. The stalled trial's parameters
cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_145/terminal_scene`.
Cycles11287484713 ->11846303124 advance while retired1629305699,
trap_count237600 and PCs remain fixed. Last retired0x1064c is
`vfslide1up.vf v24,v8,ft0,v0.t`; unqualified head0x10650 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot
and zero DDR outstanding/response errors. This does not prove the slide
never retired or identify the internal completion cause; historical traps
remain separate evidence.
`rvv_partition_inventory56` records72 passed,47 numerical failures,
56 stalls and1 never attempted, with119 complete numerical results.
Recovery146 preserves exactly the final pending e64/m8 masked-slide-up
record. Original parent outcomes and incomplete numerical coverage are
not superseded.

Recovery144 confirms masked FP slide-up e64/m2 stalls:
`rvv_fp_move_restart_e64_m2_ops2`, SHA256
78f9260b24d8b8423f487bf64f6a71aa338ab5ac267ad2179759c8117a34c76f.
Four retained op2/seed0/scalar0/full-width-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1; no final numerical
marker or element classification exists. The stalled trial's parameters
cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_144/terminal_scene`.
Cycles11302064311 ->11873181126 advance while retired1628438184,
trap_count237039 and PCs remain fixed. Last retired0x1064c is
`vfslide1up.vf v24,v8,ft0,v0.t`; unqualified head0x10650 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot
and zero DDR outstanding/response errors. This does not prove the slide
never retired or identify the internal completion cause; historical traps
remain separate evidence.
`rvv_partition_inventory55` records72 passed,47 numerical failures,
55 stalls and2 never attempted, with119 complete numerical results.
Recovery145 preserves exactly the2 pending e64 records, starting with
e64/m4 masked-slide-up. Original parent outcomes and incomplete numerical
coverage are not superseded.

Recovery143 confirms masked FP slide-up e64/m1 stalls:
`rvv_fp_move_restart_e64_m1_ops2`, SHA256
08a8a7d76cca162022c8e7e2ac7fafb6d251f3aa68b9971ab6c24f24b42d8a9a.
Four retained op2/seed0/scalar0/full-width-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1; no final numerical
marker or element classification exists. The stalled trial's parameters
cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_143/terminal_scene`.
Cycles11280166434 ->11840218902 advance while retired1628252103,
trap_count236967 and PCs remain fixed. Last retired0x1064c is
`vfslide1up.vf v24,v8,ft0,v0.t`; unqualified head0x10650 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot
and zero DDR outstanding/response errors. This does not prove the slide
never retired or identify the internal completion cause; historical traps
remain separate evidence.
`rvv_partition_inventory54` records72 passed,47 numerical failures,
54 stalls and3 never attempted, with119 complete numerical results.
Recovery144 preserves exactly the3 pending e64 records, starting with
e64/m2 masked-slide-up. Original parent outcomes and incomplete numerical
coverage are not superseded.

Recovery142 confirms masked FP slide-up e32/m8 stalls:
`rvv_fp_move_restart_e32_m8_ops2`, SHA256
4551175ecc3657cac00c58bee1fc38d067a0dac7eff5024d3a023f559f4c7479.
Four retained op2/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1; no final numerical
marker or element classification exists. The stalled trial's parameters
cannot be inferred from the last printed error.
All27 hashes verify in `rvv_recovery08_142/terminal_scene`.
The first capture's cleanup failure is retained as failed; exact JSON
comparison confirms diagnosis uses only successful fresh snapshots2/3.
Cycles11845398907 ->12378511516 advance while retired1628633054,
trap_count236119 and PCs remain fixed. Last retired0x10672 is
`vfslide1up.vf v24,v8,ft0,v0.t`; unqualified head0x10676 is
`csrr a0,vstart`. Both accepted samples have flags0, no watchdog snapshot
and zero DDR outstanding/response errors. This does not prove the slide
never retired or identify the internal completion cause; historical traps
remain separate evidence.
`rvv_partition_inventory53` records72 passed,47 numerical failures,
53 stalls and4 never attempted, with119 complete numerical results.
All5 e32 masked-slide-up shapes (mf2,m1,m2,m4,m8) now have confirmed
stall scenes. Recovery143 preserves exactly the4 pending e64 records,
starting with e64/m1 masked-slide-up. Original parent outcomes and incomplete
numerical coverage are not superseded.

Recovery141 confirms masked FP slide-up e32/m4 stalls:
`rvv_fp_move_restart_e32_m4_ops2`, SHA256
377dc3477022441ea4141b1b50a97f69ce67aaeea0cffc13c9c10e259c0891bf.
Four retained op2/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1; no final numerical
marker or element classification exists. The stalled trial's parameters
cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_141/terminal_scene`.
Cycles11299208324 ->11877577029 advance while retired1630355032,
trap_count237560 and PCs remain fixed. Last retired0x10672 is
`vfslide1up.vf v24,v8,ft0,v0.t`; unqualified head0x10676 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. This does not prove the slide never retired
or identify the internal completion cause; historical traps remain separate.
`rvv_partition_inventory52` records72 passed,47 numerical failures,
52 stalls and5 never attempted, with119 complete numerical results.
Recovery142 preserves exactly the5 pending records, starting with e32/m8
masked-slide-up. Original parent outcomes and incomplete numerical coverage
are not superseded.

Recovery140 confirms masked FP slide-up e32/m2 stalls:
`rvv_fp_move_restart_e32_m2_ops2`, SHA256
fbf0d6a67e8e0ecad6d2141dfd7004d01a63502c3f328391fcdf1281ad04fc48.
Four retained op2/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1; no final numerical
marker or element classification exists. The stalled trial's parameters
cannot be inferred from the last printed error.
All32 hashes verify in `rvv_recovery08_140/terminal_scene`.
The first capture's cleanup failure is retained as failed; exact JSON
comparison confirms diagnosis uses only successful fresh snapshots2/3.
Cycles11890849636 ->12445442037 advance while retired1630282658,
trap_count237535 and PCs remain fixed. Last retired0x10672 is
`vfslide1up.vf v24,v8,ft0,v0.t`; unqualified head0x10676 is
`csrr a0,vstart`. Both accepted samples have flags0, no watchdog snapshot
and zero DDR outstanding/response errors. This does not prove the slide
never retired or identify the internal completion cause; historical traps
remain separate evidence.
`rvv_partition_inventory51` records72 passed,47 numerical failures,
51 stalls and6 never attempted, with119 complete numerical results.
Recovery141 preserves exactly the6 pending records, starting with e32/m4
masked-slide-up. Original parent outcomes and incomplete numerical coverage
are not superseded.

Recovery139 confirms masked FP slide-up e32/m1 stalls:
`rvv_fp_move_restart_e32_m1_ops2`, SHA256
07c2eb8462abe16110d3570a483c4bdfe5ccbe523b2be1f6470f76ce45ebae3f.
Four retained op2/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1; no final numerical
marker or element classification exists. The stalled trial's parameters
cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_139/terminal_scene`.
Cycles11295040133 ->11924315326 advance while retired1630632492,
trap_count236752 and PCs remain fixed. Last retired0x10672 is
`vfslide1up.vf v24,v8,ft0,v0.t`; unqualified head0x10676 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. This does not prove the slide never retired
or identify the internal completion cause; historical traps remain separate.
`rvv_partition_inventory50` records72 passed,47 numerical failures,
50 stalls and7 never attempted, with119 complete numerical results.
Recovery140 preserves exactly the7 pending records, starting with e32/m2
masked-slide-up. Original parent outcomes and incomplete numerical coverage
are not superseded.

Recovery138 confirms masked FP slide-up e32/mf2 stalls:
`rvv_fp_move_restart_e32_mf2_ops2`, SHA256
38d8f1e12a1b9742ee23e2cab1ccd73b40361a2f35b0b68872047d16a37eb564.
Eight retained op2/seed0/scalar0/valid-box/mask0/vstart1 details at VL2/3
each report one error, with fflags matching sticky0/1; no final numerical
marker or element classification exists. The stalled trial's parameters
cannot be inferred from the last printed error.
All23 hashes verify in `rvv_recovery08_138/terminal_scene`.
Cycles11304727039 ->11938552491 advance while retired1632815355,
trap_count240252 and PCs remain fixed. Last retired0x10672 is
`vfslide1up.vf v24,v8,ft0,v0.t`; unqualified head0x10676 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. This does not prove the slide never retired
or identify the internal completion cause; historical traps remain separate.
`rvv_partition_inventory49` records72 passed,47 numerical failures,
49 stalls and8 never attempted, with119 complete numerical results.
Recovery139 preserves exactly the8 pending records, starting with e32/m1
masked-slide-up. Original parent outcomes and incomplete numerical coverage
are not superseded.

Recovery137, after cleanup-only Linux reattachment without another reset,
confirms masked FP slide-up e16/m8 stalls:
`rvv_fp_move_restart_e16_m8_ops2`, SHA256
319c185cf41043aa504309b566dd2c4eae5ea7050442bb709f9228ccb8178a75.
Five retained op2/seed0/scalar0/valid-box/mask0/vstart1 details at VL2/3
each report one error, with fflags matching sticky0/1; no final numerical
marker or element classification exists. The stalled trial's parameters
cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_137/terminal_scene`.
Cycles16297614207 ->16827184948 advance while retired1793358603,
trap_count428213 and PCs remain fixed. Last retired0x10684 is
`vfslide1up.vf v24,v8,ft0,v0.t`; unqualified head0x10688 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. This does not prove the slide never retired
or identify the internal completion cause; historical traps remain separate.
`rvv_partition_inventory48` records72 passed,47 numerical failures,
48 stalls and9 never attempted, with119 complete numerical results.
All6 e16 masked-slide-up shapes have been attempted: mf4 completes with
numerical failure, and mf2/m1/m2/m4/m8 stall. Recovery138 preserves exactly
the9 pending e32/e64 records, starting with e32/mf2 masked-slide-up.
Original parent outcomes and incomplete numerical coverage are not superseded.

Recovery136 confirms masked FP slide-up e16/m4 stalls:
`rvv_fp_move_restart_e16_m4_ops2`, SHA256
d6c577632da1b3bc77ff61c26a42293a903532d767a0de28dcbd576da9584aaa.
Four retained op2/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1; no final numerical
marker or element classification exists. The stalled trial's parameters
cannot be inferred from the last printed error.
All32 hashes verify in `rvv_recovery08_136/terminal_scene`.
The first capture's cleanup failure is retained as failed; exact JSON
comparison confirms diagnosis uses only successful fresh snapshots2/3.
Cycles11859475282 ->12417708917 advance while retired1631867480,
trap_count238135 and PCs remain fixed. Last retired0x10684 is
`vfslide1up.vf v24,v8,ft0,v0.t`; unqualified head0x10688 is
`csrr a0,vstart`. Both accepted samples have flags0, no watchdog snapshot
and zero DDR outstanding/response errors. This does not prove the slide
never retired or identify the internal completion cause; historical traps
remain separate evidence.
`rvv_partition_inventory47` records72 passed,47 numerical failures,
47 stalls and10 never attempted, with119 complete numerical results.
Recovery137 preserves exactly the10 pending records, starting with e16/m8
masked-slide-up. Original parent outcomes and incomplete numerical coverage
are not superseded.

Recovery135 confirms masked FP slide-up e16/m2 stalls:
`rvv_fp_move_restart_e16_m2_ops2`, SHA256
35d799a55bf19e1a663b3c7a74ff77e2dd78ecf249b8bfce48e1be86aea25ca5.
Four retained op2/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1; no final numerical
marker or element classification exists. The stalled trial's parameters
cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_135/terminal_scene`.
Cycles11265619845 ->11869550224 advance while retired1631284262,
trap_count237437 and PCs remain fixed. Last retired0x10684 is
`vfslide1up.vf v24,v8,ft0,v0.t`; unqualified head0x10688 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. This does not prove the slide never retired
or identify the internal completion cause; historical traps remain separate.
`rvv_partition_inventory46` records72 passed,47 numerical failures,
46 stalls and11 never attempted, with119 complete numerical results.
Recovery136 preserves exactly the11 pending records, starting with e16/m4
masked-slide-up. Original parent outcomes and incomplete numerical coverage
are not superseded.

Recovery134, after precheck-cleanup recovery without another reset, confirms
masked FP slide-up e16/m1 stalls: `rvv_fp_move_restart_e16_m1_ops2`, SHA256
21757f42ec363845529cc4c6c21611c0faf7582edee4357ef2614238113bbd5d.
Four retained op2/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1; no final numerical
marker or element classification exists. The stalled trial's parameters
cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_134/terminal_scene`.
Cycles11272635739 ->11835546002 advance while retired1631006837,
trap_count237346 and PCs remain fixed. Last retired0x10684 is
`vfslide1up.vf v24,v8,ft0,v0.t`; unqualified head0x10688 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. This does not prove the slide never retired
or identify the internal completion cause; historical traps remain separate.
`rvv_partition_inventory45` records72 passed,47 numerical failures,
45 stalls and12 never attempted, with119 complete numerical results.
Recovery135 preserves exactly the12 pending records, starting with e16/m2
masked-slide-up. Original parent outcomes and incomplete numerical coverage
are not superseded.

Recovery133 then confirms masked FP slide-up e16/mf2 stalls:
`rvv_fp_move_restart_e16_mf2_ops2`, SHA256
25fbf80dee19612e54626678b528d45874d729b16c564b5d07d012bc75598d83.
Eight retained op2/seed0/scalar0/valid-box/mask0/vstart1 details at VL2/3
each report one error, with fflags matching sticky0/1; no final numerical
marker or element classification exists. The stalled trial's parameters
cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_133/terminal_scene`, whose raw report
also retains the preceding e16/mf4 completed numerical failure.
Cycles11397823678 ->11945039295 advance while retired1683872525,
trap_count250351 and PCs remain fixed. Last retired0x10684 is
`vfslide1up.vf v24,v8,ft0,v0.t`; unqualified head0x10688 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. This does not prove the slide never retired
or identify the internal completion cause; historical traps remain separate.
`rvv_partition_inventory44` records72 passed,47 numerical failures,
44 stalls and13 never attempted, with119 complete numerical results.
Recovery134 preserves exactly the13 pending records after removing the
completed failure and stalled attempt, starting with e16/m1 masked-slide-up.
Original parent outcomes and incomplete numerical coverage are not superseded.

Recovery133's first masked-slide-up partition completes numerically and fails:
`rvv_fp_move_restart_e16_mf4_ops2`, SHA256
75bff1c51378cf28e4aded306592d07086dc27767c4e47a42342c926f7d6f855.
Raw SCP capture `rvv_recovery08_133/resume/board_report_live01.json` retains
`RVV_FP_MOVE_FAIL sew=16 cases=21504 errors=11070`, exit1. Immutable
release/reference identities and complete configuration counts verify through
`rvv_partition_inventory43`:72 passed,47 numerical failures,43 stalled,
1 running and13 not attempted. This first partition is a full numerical
failure, not a stall. Its retained details include VL2/3/8/15, all-on and
alternating predicates, and nonzero starts; printed fflags match sticky0/1.
The release does not print the first bad element or returned vstart, so
individual error categories cannot be inferred from aggregate error counts.
The observer continues e16/mf2 without a reset; these partial batch results
do not establish the remaining14 partitions' completion or parent acceptance.

Recovery132 confirms masked FP slide-down e64/m8 stalls:
`rvv_fp_move_restart_e64_m8_ops3`, SHA256
c2fac0b3d0d90a039826a7ad37fd614b4300186cd1cf08e95241f9955f965d10.
Four retained op3/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1; there is no final
numerical marker or element classification. The stalled trial's parameters
cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_132/terminal_scene`.
Cycles11254991834 ->11786589726 advance while retired1632308165,
trap_count237531 and PCs remain fixed. Last retired0x10692 is
`vfslide1down.vf v24,v8,ft0,v0.t`; unqualified head0x10696 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. This does not prove the slide never retired
or identify the internal completion cause; historical traps remain separate.
`rvv_partition_inventory42` records72 passed,46 numerical failures,
43 stalls and15 never attempted. All15 masked-slide-down shapes have now
been attempted: e16/mf4 completes with numerical failure; the other14 stall
(5 e16,5 e32,4 e64). No masked-slide-down shape passes, and14 lack full
internal-trial completion. Recovery133 preserves exactly the15 remaining
masked-slide-up records, starting with e16/mf4. Original parent outcomes
and incomplete numerical coverage are not superseded.

Recovery131 confirms masked FP slide-down e64/m4 stalls:
`rvv_fp_move_restart_e64_m4_ops3`, SHA256
73dccc838b286b1e91629c1cdadf150fbfc666976036e1418351681bce7320b9.
Four retained op3/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1; there is no final
numerical marker or element classification. The stalled trial's parameters
cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_131/terminal_scene`.
Cycles11270641924 ->11810840789 advance while retired1631923981,
trap_count237515 and PCs remain fixed. Last retired0x10692 is
`vfslide1down.vf v24,v8,ft0,v0.t`; unqualified head0x10696 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. This does not prove the slide never retired
or identify the internal completion cause; historical traps remain separate.
`rvv_partition_inventory41` records72 passed,46 numerical failures,
42 stalls and16 never attempted. Recovery132 preserves the exact16 pending
records:1 e64 masked-slide-down and15 masked-slide-up partitions, starting
with e64/m8 masked-slide-down. Original parent outcomes and incomplete
internal numerical coverage are not superseded.

Recovery130 confirms masked FP slide-down e64/m2 stalls:
`rvv_fp_move_restart_e64_m2_ops3`, SHA256
d2430fad16a4fce68ed3e75c6b489010eb4958ee0e5ce41f60df43197cbc6de9.
Four retained op3/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1; there is no final
numerical marker or element classification. The later stalled trial's
parameters cannot be inferred from the last printed error.
All27 hashes verify in `rvv_recovery08_130/terminal_scene`.
The first snapshot's transport cleanup fails and is retained as failed;
diagnosis uses only successful fresh snapshots2/3, verified by exact JSON
equality, not the failed capture. Cycles11848631258 ->12383272126 advance
while retired1631926288, trap_count237466 and PCs remain fixed.
Last retired0x10692 is `vfslide1down.vf v24,v8,ft0,v0.t`;
unqualified head0x10696 is `csrr a0,vstart`. Both accepted snapshots have
flags0, no watchdog snapshot and zero DDR outstanding/response errors.
This does not identify the internal completion cause or prove the slide
never retired; historical traps remain separate evidence.
`rvv_partition_inventory40` records72 passed,46 numerical failures,
41 stalls and17 never attempted. Recovery131 preserves the exact17 pending
records:2 e64 masked-slide-down and15 masked-slide-up partitions, starting
with e64/m4 masked-slide-down. Original parent outcomes and incomplete
internal numerical coverage are not superseded.

Recovery129 confirms masked FP slide-down e64/m1 stalls:
`rvv_fp_move_restart_e64_m1_ops3`, SHA256
e84983335d58b556407b5b29c4b9f1d65def724469c20ca69b609d4f281d622a.
Four retained op3/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1. No final numerical
marker or element classification exists; the stalled trial's parameters
cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_129/terminal_scene`.
Cycles11287037032 ->11855020952 advance while retired1633125721,
trap_count238593 and PCs remain fixed. Last retired0x10692 is
`vfslide1down.vf v24,v8,ft0,v0.t`; unqualified head0x10696 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. These PCs and the historical trap do not
prove the slide never retired or identify the internal completion cause.
`rvv_partition_inventory39` records72 passed,46 numerical failures,
40 stalls and18 never attempted. Recovery130 preserves the exact18 pending
records:3 e64 masked-slide-down and15 masked-slide-up partitions, starting
with e64/m2 masked-slide-down. Original parent results and their incomplete
internal numerical coverage remain unchanged.

Recovery128 confirms masked FP slide-down e32/m8 stalls:
`rvv_fp_move_restart_e32_m8_ops3`, SHA256
4f1908f450c087d71590d79f525fec8d7697132b2d3b4306673e2ef0ce2d04a1.
Four retained op3/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1. No final numerical
marker or element classification exists, and the later stalled trial's
VL/mask/start cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_128/terminal_scene`.
Cycles11257456179 ->11852108039 advance while retired1633552311,
trap_count237680 and PCs remain fixed. Last retired0x106ba is
`vfslide1down.vf v24,v8,ft0,v0.t`; unqualified head0x106be is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. The historical trap and these PCs do not
establish a current internal queue cause or prove the slide never retired.
`rvv_partition_inventory38` records72 passed,46 numerical failures,
39 stalls and19 never attempted. All5 released e32 masked-slide-down
partitions (mf2,m1,m2,m4,m8) have now stalled. Recovery129 preserves the
exact19 pending records:4 e64 masked-slide-down and15 masked-slide-up
partitions. No original parent result or internal numerical coverage is
superseded by these completed attempts.

Recovery127 confirms masked FP slide-down e32/m4 stalls:
`rvv_fp_move_restart_e32_m4_ops3`, SHA256
5d8722feafd1be4a985dfa9ebd03323476efbe2711108b80ec4694a558654ae9.
Four retained op3/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1. No final numerical
marker or element classification exists, and the later stalled trial's
VL/mask/start cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_127/terminal_scene`.
Cycles11278833309 ->11833879121 advance while retired1634013340,
trap_count238498 and PCs remain fixed. Last retired0x106ba is
`vfslide1down.vf v24,v8,ft0,v0.t`; unqualified head0x106be is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. The historical trap and these PCs do not
establish a current internal queue cause or prove the slide never retired.
`rvv_partition_inventory37` records72 passed,46 numerical failures,
38 stalls and20 never attempted. Recovery128 preserves the exact20 pending
FP-move records; no original parent result is superseded.

Recovery126 confirms masked FP slide-down e32/m2 stalls:
`rvv_fp_move_restart_e32_m2_ops3`, SHA256
c0af3f37f2d6dc9f358d4772050c7b7540733bc23312a2b2965c33484d76c0f6.
Four retained op3/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1. No final numerical
marker or element classification exists, and the later stalled trial's
VL/mask/start cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_126/terminal_scene`.
Cycles11279975097 ->11863667475 advance while retired1633520084,
trap_count238267 and PCs remain fixed. Last retired0x106ba is
`vfslide1down.vf v24,v8,ft0,v0.t`; unqualified head0x106be is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. The historical trap and these PCs do not
establish a current internal queue cause or prove the slide never retired.
`rvv_partition_inventory36` records72 passed,46 numerical failures,
37 stalls and21 never attempted. Recovery127 preserves the exact21 pending
FP-move records; no original parent result is superseded.

Recovery125 confirms masked FP slide-down e32/m1 stalls:
`rvv_fp_move_restart_e32_m1_ops3`, SHA256
725449fd1518bfbb9850a9ae6bf506235f24fa98ab20179d6d542d689892e781.
Four retained op3/seed0/scalar0/valid-box/mask0/vstart1 details at VL2
each report one error, with fflags matching sticky0/1. No final numerical
marker or element classification exists, and the later stalled trial's
VL/mask/start cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_125/terminal_scene`.
Cycles11301686071 ->11828177658 advance while retired1634291280,
trap_count239267 and PCs remain fixed. Last retired0x106ba is
`vfslide1down.vf v24,v8,ft0,v0.t`; unqualified head0x106be is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. The historical trap and these PCs do not
establish a current internal queue cause or prove the slide never retired.
`rvv_partition_inventory35` records72 passed,46 numerical failures,
36 stalls and22 never attempted. Recovery126 preserves the exact22 pending
FP-move records; no original parent result is superseded.

Recovery124 confirms masked FP slide-down e32/mf2 stalls:
`rvv_fp_move_restart_e32_mf2_ops3`, SHA256
3df1802304c54937719bc1d66cc8048d46b093af861b56989cd6f8934b57a832.
Eight retained op3/seed0/scalar0/valid-box/mask0/vstart1 details at VL2/3
each report one error, with fflags matching sticky0/1. No final numerical
marker or element classification exists, and the later stalled trial's
VL/mask/start cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_124/terminal_scene`.
Cycles11292979450 ->11858771824 advance while retired1636533162,
trap_count240930 and PCs remain fixed. Last retired0x106ba is
`vfslide1down.vf v24,v8,ft0,v0.t`; unqualified head0x106be is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. The historical trap and these PCs do not
establish a current internal queue cause or prove the slide never retired.
`rvv_partition_inventory34` records72 passed,46 numerical failures,
35 stalls and23 never attempted. Recovery125 preserves the exact23 pending
FP-move records; no original parent result is superseded.

Recovery123 confirms masked FP slide-down e16/m8 stalls:
`rvv_fp_move_restart_e16_m8_ops3`, SHA256
b7d51e84d2698b12a773a1037424576b183554f6fc2c279cc568b9c007beb73b.
Five retained op3/seed0/scalar0/valid-box/mask0/vstart1 details at VL2/3
each report one error, with fflags matching sticky0/1. No final numerical
marker or element classification exists, and the later stalled trial's
VL/mask/start cannot be inferred from the last printed error.
All20 hashes verify in `rvv_recovery08_123/terminal_scene`.
Cycles11295288437 ->11871556142 advance while retired1635972958,
trap_count238424 and PCs remain fixed. Last retired0x106ce is
`vfslide1down.vf v24,v8,ft0,v0.t`; unqualified head0x106d2 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. The historical trap and these PCs do not
establish a current internal queue cause or prove the slide never retired.
`rvv_partition_inventory33` records72 passed,46 numerical failures,
34 stalls and24 never attempted. Recovery124 preserves the exact24 pending
FP-move records; no original parent result is superseded.

Recovery122, after initializer precheck-cleanup recovery without another
bitstream download, confirms masked FP slide-down e16/m4 stalls:
`rvv_fp_move_restart_e16_m4_ops3`, SHA256
f5b34349585ea9346bea7fe3d204824fd9f8b582ddb7fa5da6fc0c52dbcc5dec.
Four retained detail lines at op3/seed0/scalar0/valid-box/VL2/mask0/vstart1
each report one error, with actual fflags matching sticky0/1. No final
numerical marker exists; these details do not identify the failing element,
guard, scalar result or returned-vstart check, or the later stalled trial.
All20 hashes verify in `rvv_recovery08_122/terminal_scene`.
Cycles11268809929 ->11838207803 advance while retired1635678077,
trap_count238495 and PCs remain fixed. Last retired0x106ce disassembles to
`vfslide1down.vf v24,v8,ft0,v0.t`; unqualified head0x106d2 is
`csrr a0,vstart`. Both samples have flags0, no watchdog snapshot and zero
DDR outstanding/response errors. The retained historical trap is not a
current causal attribution, and these PCs do not prove the slide never
retired or identify an internal queue cause. `rvv_partition_inventory32`
records72 passed,46 numerical failures,33 stalls and25 never attempted.
Recovery123 preserves the exact25 pending FP-move records; no original
parent result is superseded.

Recovery93's operation-isolated e16/m8 merge confirms a completion stall:
`rvv_fp_move_restart_e16_m8_ops0`, SHA256
`d8abfc1bfebe188b1045a786e2ce17ba571e523c363b365ed28b805c99881710`.
The last drained trace is VL512/vstart256 with194 completed configurations,
printed before invoking that trial. Last retired/head PCs0x10666/0x1066a
decode `vfmerge.vfm v24,v8,ft0,v0` and `csrr a0,vstart`.
Cycles21335857656 to21887362567 advance while retired6033228818,
trap_count888531 and both PCs remain fixed. Both snapshots have flags0,
no watchdog halt and zero DDR outstanding/errors. These observations do
not identify an internal queue cause or prove the merge never retired.
All20 scene hashes verify in `rvv_recovery08_93/terminal_scene`.
Recovery94 preserves all28 pending FP partitions and adds the56 separately
reference-validated extension partitions:84 exact cases, no omissions or
duplicates. The extension package is queued only once; subsequent recovery
batches retain pending cases rather than re-enqueueing the whole package.

Recovery93's reordered batch completes four unmasked slide-down (`op5`)
partitions: e16/mf4,mf2,m1,m2,21504 configurations each, respectively
28160,52224,100608,197384 numerical errors. These failures have full final
markers and exit1, and do not stop subsequent execution. Exact-ELF/reference
and nonce-protocol audit: `rvv_fp_move_partition_board_audit93_partial01`;
the immutable report snapshot is `rvv_recovery93_active_snapshot01.json`.
Only these four completed results are counted by that partial audit, not the
running e16/m4 partition or unexecuted siblings. No internal cause is inferred
from aggregate counts, and no RTL modification or corrective acceptance follows.

Recovery93 snapshot02 extends the audited completed prefix to25 partitions:
12 unmasked slide-down (`op5`) and12 unmasked slide-up (`op4`) all fail,
while the e16/mf4 merge (`op0`) passes21504 configurations. This is the
non-m8 prefix chosen by the scheduler, not acceptance of unexecuted m8
slide variants or other merges. Evidence:
`rvv_fp_move_partition_board_audit93_partial02` and
`rvv_recovery93_active_snapshot02.json`. This cumulative audit supersedes
partial01 for counting; do not add their overlapping completed prefixes.

Recovery93 snapshot03 extends that prefix to38 completed partitions:
all12 non-m8 merge (`op0`) shapes pass225792 configurations; the24
non-m8 unmasked slides remain numerical failures, and unmasked slide-down
e16/m8 and e32/m8 also complete with numerical failures. The e64/m8 slide
is still running and is excluded. Exact audit:
`rvv_fp_move_partition_board_audit93_partial03`,26 failures/12 passes;
`rvv_recovery93_active_snapshot03.json`. Use the newest cumulative audit
once, not the sum of overlapping snapshots. Other m8 operations, masked
slides and later trials remain unaccepted by these results.

Recovery93 snapshot04 completes all30 unmasked FP slide partitions
(`op4`/`op5`,15 shapes each), all numerical failures, including m8 for
FP16/32/64. The12 non-m8 merge passes are unchanged. This42-result prefix
covers784896 configurations,225792 passing; e16/m8 merge is running and
excluded. Evidence: `rvv_fp_move_partition_board_audit93_partial04` and
`rvv_recovery93_active_snapshot04.json`. Use this cumulative audit once;
the completed slide coverage is not evidence that the restart-result bug
has been fixed or that masked slides have completed.

Recovery95 snapshot01 completes merge op0 for e32/m8 and e64/m8,
both passing:21504 and10752 configurations respectively. Exact audit:
`rvv_fp_move_partition_board_audit95_partial01` against immutable
`rvv_recovery95_active_snapshot01.json`. Thus14 of15 merge shapes
have completed numerically with passes; e16/m8 remains a separately
archived completion stall, not a pass. These results do not validate
masked slides or override the original combined-operation ELF failures.

Recovery92 confirms masked slide-down e16/m2 also has a completion stall:
`rvv_fp_move_restart_e16_m2_ops3`, SHA256
`4daa0ea7695a1523b9c7234a57efc4e011c10cc38f205b7aa74914699a040678`.
Cycles11394462295 to11942035058 advance while retired1650186427,
trap_count245005 and last retired/head PCs0x106ce/0x106d2 remain fixed.
The PCs decode masked `vfslide1down.vf` and the vstart read. Both snapshots
have flags0, no watchdog halt and zero DDR outstanding/errors. Earlier
VL2/vstart1 errors do not identify the stalled operation's active operands;
historical traps and the retired-PC probe do not establish an internal cause.
All20 scene hashes verify in `rvv_recovery08_92/terminal_scene`.
Recovery93 retains all71 pending exact partitions and schedules unmasked
slide-down first, deferring masked-slide partitions without dropping any.

Recovery91 confirms the next masked slide-down partition also stalls:
`rvv_fp_move_restart_e16_m1_ops3`, SHA256
`d46bd62fad5d607dc0ac9edfa6dbf8d05c9fcc2b1c7c527f9d99f8d35538db3f`.
Last retired/head PCs0x106ce/0x106d2 decode masked `vfslide1down.vf`
and the vstart read. Cycles11393261491 to11927085878 advance while
retired1649857810, trap_count244606 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
Earlier VL2/vstart1 result errors do not identify active stalled operands.
The historical kernel trap is not current target-trap evidence, and the
retired-PC probe does not prove the slide never retired. All20 scene hashes
verify in `rvv_recovery08_91/terminal_scene`. Recovery92 retains all72
pending exact partitions, with no RTL changes and no inferred passes.

Recovery90 isolates FP move operations using the same oracle and assembly,
with exact-ELF references at VLEN512/1024 for every partition. All15 broadcast
(`op1`, `vfmv.v.f`) and15 scalar extraction (`op7`, `vfmv.f.s`) partitions
pass559104 configurations. All15 scalar insertion (`op6`, `vfmv.s.f`)
partitions complete with numerical failures:8184 errors per FP16/32 ELF and
3960 per FP64 ELF. The first retained details include VL2/vstart1; these
outputs are evidence of restart-result errors, not an internal RTL cause.
The e16/mf4 masked slide-down partition also completes with32074 errors.
Audit: `rvv_fp_move_partition_board_audit90`,46 completed partitions;
these results do not supersede full parent-ELF failures or stalls.

The next partition, `rvv_fp_move_restart_e16_mf2_ops3`, confirms a masked
slide-down completion-stall scene. SHA256
`6e446537a3b3c5400e7d80ed5b1f75e1132aa1e793db4c648558140f57ec3e87`.
Last retired/head PCs0x106ce/0x106d2 decode
`vfslide1down.vf v24,v8,ft0,v0.t` and `csrr a0,vstart`.
Cycles21433346975 to22008546388 advance while retired6385616831,
trap_count836815 and both PCs remain fixed. Both snapshots have flags0,
no watchdog halt and zero DDR outstanding/errors. Historical kernel trap
cause2 is not a current target-trap attribution. Earlier VL2/3,vstart1
details do not identify active operands at the stall, and last retired PC
does not prove the slide never retired. All20 immutable scene hashes
verify in `rvv_recovery08_90/terminal_scene`. Recovery91 retains all73
pending exact partitions in their original order, without RTL changes.

Recovery87 confirms e64/m8 FP slide1 completion stall:
`rvv_fp_move_restart_e64_m8`, SHA256
`a3c9063376945aac0ca3c7c3d77d6e4ba7f93ab87cd0ea49022a5af4e24032ab`.
Last retired/head PCs0x1077c/0x10780 decode masked
`vfslide1up.vf v24,v8,ft0,v0.t` and `csrr a0,vstart`.
Cycles11269156353 to11817556090 advance while retired1636342168,
trap_count239690 and both PCs remain fixed. Both snapshots have flags0,
no watchdog halt and zero DDR outstanding/errors. All20 scene hashes verify
in `rvv_recovery08_87/terminal_scene`. The first-operation trace reached
VL128/vstart127 and earlier op2 details report VL2/vstart1 result errors;
these do not identify active slide operands. Historical trap cause2 is not
proof of a current target trap; last retired PC does not prove the slide
never retired. No final marker exists and later trials remain uncovered.
Continuation preserves2 pending exact segment-alignment ELFs.

Recovery86 confirms an e32/m8 FP slide1 completion-stall scene:
`rvv_fp_move_restart_e32_m8`, SHA256
`8ef698364963c9949196096ebb1dda21efc9d7c10cb42cd4d12dfe69afb12555`.
Last retired/head PCs0x107b4/0x107b8 decode masked
`vfslide1up.vf v24,v8,ft0,v0.t` and `csrr a0,vstart`.
Cycles11256682011 to11833244248 advance while retired1638163770,
trap_count241247 and both PCs remain fixed. Both snapshots have flags0,
no watchdog halt and zero DDR outstanding/errors. All20 scene hashes verify
in `rvv_recovery08_86/terminal_scene`. The UART first-operation trace reached
VL256/vstart255, then op2 numerical details include VL2/vstart1; those earlier
lines do not identify the active slide operands. Historical trap cause2 is
not proof of a current target trap, and last retired PC does not prove the
slide never retired. No final numerical marker exists; later trials remain
uncovered. Continuation preserves3 pending exact ELFs.

Recovery85 adds a distinct FP merge restart completion-stall scene:
`rvv_fp_move_restart_e16_m8`, SHA256
`ac47026d279306f599dc590a7ef2bfd66cd076adcb47ec3bf7ee40f41550cb13`.
Last drained trial is VL512/vstart256 with194 completed configurations;
the source prints this count before calling the current operation.
Last retired/head PCs0x10716/0x1071a decode `vfmerge.vfm v24,v8,ft0,v0`
and `csrr a0,vstart`, not the later slide1 operation.
Cycles14902825067 to15431463340 advance while retired3516196247,
trap_count437374 and both PCs remain fixed. Both snapshots have flags0,
no watchdog halt and zero DDR outstanding/errors. All20 scene hashes verify
in `rvv_recovery08_85/terminal_scene`. The last retired PC does not prove
the merge never retired; no internal cause or equivalence to slide1 stalls
is established. Later operations/trials remain uncovered and no final
numerical marker exists. Continuation preserves4 pending exact ELFs.

Recovery56 confirms a completion-sequence stall in
`rvv_fp_move_restart_e16_m1`, exact ELF SHA256
`30058442f4b800d945db825a8fd51359047b4af0be89e5b3ca662eade02e983d`.
Last retired PC0x107b6 decodes masked `vfslide1up.vf v24,v8,ft0,v0.t`;
head PC0x107ba reads vstart, but the head probe has no validity bit.
Cycles19962394076 to20543290693 advance while retired5002332219,
trap_count805442 and both PCs remain fixed. Both snapshots have flags0,
no watchdog halt and zero DDR1/DDR2 outstanding transactions/errors.
All20 recorded scene hashes verify in `rvv_recovery08_56/terminal_scene`.
The last trap cause2 is historical; it does not establish a target-instruction
trap. Active slide operands and the internal cause remain unproven, and the
last retired PC does not prove the slide itself never retired. No completed
numerical marker exists for this ELF. Recovery57 retains52 pending ELFs;
the preceding31 numerical failures completed without intervening resets.

Recovery57 also confirms a completion-sequence stall in
`rvv_fp_move_restart_e16_m2`, exact ELF SHA256
`a9567e68ea5598ac0660921497e9060199b41ea280601fc705d626283591f46e`.
Last retired/head PCs0x107b6/0x107ba decode masked `vfslide1up.vf` and
the vstart read. Cycles11343642729 to11868399655 advance while
retired1650639821, trap_count246052 and both PCs remain fixed. Flags0,
no watchdog halt and both DDR outstanding/error counters0 exclude those
observed halt/DDR conditions, not all possible internal causes. All20
scene hashes verify in `rvv_recovery08_57/terminal_scene`. Head validity
and active operands remain unavailable; no completed numerical marker
exists. Recovery58 retains51 pending exact ELFs.

Recovery58 also confirms a completion-sequence stall in
`rvv_fp_move_restart_e16_m4`, exact ELF SHA256
`a7e8de720ea50706e8d8622e249f2402b01c859a93def74c999826a64752e045`.
Last retired/head PCs0x107b6/0x107ba decode masked `vfslide1up.vf` and
the vstart read. Cycles11317842299 to11841013301 advance while
retired1651711960, trap_count245388 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_58/terminal_scene`. These
matching boundaries do not prove one common internal cause or that the
slide never retired. Active operands/head validity and a completed
numerical marker remain unavailable. Recovery59 retains50 pending ELFs.

Recovery59 extends the observed completion-sequence stall to SEW32 in
`rvv_fp_move_restart_e32_mf2`, exact ELF SHA256
`36004f1816983fb6858fd00fb53d02c0699d1d9ff322fde607ba41a49aa20dfc`.
Last retired/head PCs0x107b4/0x107b8 decode masked `vfslide1up.vf` and
the vstart read. Cycles11352071181 to11893656965 advance while
retired1649736328, trap_count248116 and both PCs remain fixed. Flags0,
no watchdog halt and both DDR outstanding/error counters0 are observed.
All20 scene hashes verify in `rvv_recovery08_59/terminal_scene`. Head
validity, active operands and a common internal cause remain unproven;
the last retired PC does not prove the slide never retired. No numerical
completion exists for this ELF. Recovery60 retains49 pending exact ELFs.

Recovery60 also confirms a completion-sequence stall in
`rvv_fp_move_restart_e32_m1`, exact ELF SHA256
`c5b0d3b4a2cbafe63f5c5728db4eae124603e80d031419854d744dc31b9ca195`.
Last retired/head PCs0x107b4/0x107b8 decode masked `vfslide1up.vf` and
the vstart read. Cycles11335292917 to11854474106 advance while
retired1647860091, trap_count246125 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_60/terminal_scene`. Active
operands/head validity and the internal cause remain unavailable; the
last retired PC does not prove the slide itself never retired. No completed
numerical marker exists. Recovery61 retains48 pending exact ELFs.

Recovery61 also confirms a completion-sequence stall in
`rvv_fp_move_restart_e32_m2`, exact ELF SHA256
`31eff77bc5a88bd8af68883c88307dc337aafa234fff18eb762bee80fa49977f`.
Last retired/head PCs0x107b4/0x107b8 decode masked `vfslide1up.vf` and
the vstart read. Cycles11355973907 to11932656874 advance while
retired1649953212, trap_count245027 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_61/terminal_scene`. Active
operands/head validity and the internal cause remain unavailable; the
last retired PC does not prove the slide itself never retired. No completed
numerical marker exists. Recovery62 retains47 pending exact ELFs.

Recovery62 also confirms a completion-sequence stall in
`rvv_fp_move_restart_e32_m4`, exact ELF SHA256
`7f9dcf10949ff83a17767d27c55037ac21909539fad03cc47c4a1d4168786ceb`.
Last retired/head PCs0x107b4/0x107b8 decode masked `vfslide1up.vf` and
the vstart read. Cycles11409949297 to11955168901 advance while
retired1649539898, trap_count246401 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_62/terminal_scene`. Active
operands/head validity and the internal cause remain unavailable; the
last retired PC does not prove the slide itself never retired. No completed
numerical marker exists. Recovery63 retains46 pending exact ELFs.

Recovery63 extends the completion-sequence stall observation to SEW64 in
`rvv_fp_move_restart_e64_m1`, exact ELF SHA256
`06c769e407d158c47586a5270ded7229f8e68792c18099a3a786654759f97f93`.
Last retired/head PCs0x1077c/0x10780 decode masked `vfslide1up.vf` and
the vstart read. Cycles11312561413 to11841029061 advance while
retired1645699682, trap_count244699 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_63/terminal_scene`. Active
operands/head validity and a common internal cause remain unproven; the
last retired PC does not prove the slide itself never retired. No completed
numerical marker exists. Recovery64 retains45 pending exact ELFs.

Recovery64 also confirms a completion-sequence stall in
`rvv_fp_move_restart_e64_m2`, exact ELF SHA256
`f506a5664613bc8ac1978c9cf86806f320af3b8f5404bb42ce0d122a54878880`.
Last retired/head PCs0x1077c/0x10780 decode masked `vfslide1up.vf` and
the vstart read. Cycles11339474122 to11860110503 advance while
retired1646713773, trap_count245922 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_64/terminal_scene`. Active
operands/head validity and the internal cause remain unproven; the last
retired PC does not prove the slide itself never retired. No completed
numerical marker exists. The continuation retains44 pending exact ELFs.

Recovery65 also confirms a completion-sequence stall in
`rvv_fp_move_restart_e64_m4`, exact ELF SHA256
`c7b34e13395ea3a84a648572ff520006d1f050c8996e708eae49a4070decdf9d`.
Last retired/head PCs0x1077c/0x10780 decode masked `vfslide1up.vf` and
the vstart read. Cycles11338336214 to11864195571 advance while
retired1647070114, trap_count245674 and both PCs remain fixed. Both
snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All20 scene hashes verify in `rvv_recovery08_65/terminal_scene`. Active
operands/head validity and the internal cause remain unproven; the last
retired PC does not prove the slide itself never retired. No completed
numerical marker exists. The continuation retains43 pending exact ELFs.

The immutable additions31 `rvv_fp_move_restart_e16_mf4` exits1 on board,
while the identical ELF passes VLEN512 and1024 QEMU references. The first
retained failing trial is op2 (`vfslide1up.vf v24,v8,ft0,v0.t`), seed0,
scalar0 with valid boxing, VL2, all-on mask, vstart1 and initial fflags0.
It records one error and actual fflags0. The sticky-NX counterpart records
one error with actual fflags1. VL3/vstart1 also fails. The wrapper loads
all source/destination/mask state before setting vstart, captures vstart
and fflags before readback, and checks every logical destination element,
scalar-result sentinel and both memory guards.

The first-error summary does not print low status bits or the differing
element. Consequently it does NOT yet distinguish a nonzero completion
vstart from a data mismatch or guard failure. No exact RTL stage or common
cause with RVV-08 is established. A separate immutable diagnostic must
report returned vstart, element index and expected/actual raw bits before
assigning a root cause. At live14 the observer was still live; that snapshot
did not yet establish a stall. Evidence: `rvv_recovery08_07/resume/board_report_live14.json`,
additions31 ELF/reference manifests, `fp_moves.py` and `fp_move_oracle.c`.

The opt-in derivative uses `--restart --diagnostic-details --only e16_mf4`
and a distinct ELF name. It prints low returned vstart, first differing
element raw bits, scalar output and memory guards for the first20 failing
trials. The unreleased `rvv_fp_move_restart_detail01` references lacked
`zfh=true,zvfh=true` and exited132 at the first FP16 target after the first
trace. These capability-omission reports are preserved and are NOT evidence
against either hardware or the numerical oracle. Original additions31
references explicitly enabled both features. A fresh detail02 reference
uses the same required capability flags and passes both references. The
single diagnostic is released as additions43, not additional ISA coverage.

The terminal recovery07 report subsequently confirms no retirement in
`rvv_fp_move_restart_e16_mf2`. The raw debug counter semantics update last
PC only on nonzero retire_count; head PC is sampled independently. The
last retired PC0x107b6 disassembles as `vfslide1up.vf v24,v8,ft0,v0.t`,
and head PC0x107ba as `csrr a0,vstart`. Thus this is a stalled completion
sequence, NOT proof that the slide itself never retired. Cycles advance
133359660961->133913802970 over about11.08 seconds, while retired31635449167,
trap_count7737516 and both PCs are unchanged. Both snapshots have flags0,
no watchdog halt and zero DDR1/DDR2 outstanding transactions/errors.
The exact VL/start at the stall is not printed by the existing op0-only
boundary trace; do not infer it from the last partially flushed error line.
No exact Ara queue cause or identity with the mf4 numerical failure is
established. The scene is preserved under `rvv_recovery08_07/terminal_scene`,
and terminal report SHA256 is
`6352fd7cf3834eff0bff08b324b5b2ac2757f442b5f9bbf9e5d06b7951e60e4c`.

Recovery08 live01 runs the detail02 diagnostic first on the freshly
restarted original image and reproduces the mf4 numerical failure. For
op2/seed0/scalar0/valid-box/VL2/all-on/vstart1, completion vstart is0 and
fflags remains0 (or1 for initial NX). First bad element0 is expected31743
(0x7bff, its old destination bits), actual0 (0x0000, the inserted scalar).
Scalar output remains0x123456789abcdef0 and both memory guards remain91.
Thus the observed first failure is concretely a prestart destination
write, NOT an uncleared completion vstart, flag mismatch or memory guard
failure. VL8/start4 also reports a changed prestart element0; with alternating
mask, the first changed prestart element1 is expected32341 (0x7e55), actual0.
The complete diagnostic executes172032 cases and reports107128 errors,
not all classified by the first20 retained details. This fresh-image
reproduction does not prove the mf2 stall has the same internal cause.
Evidence: `rvv_recovery08_08/resume/board_report_live01.json` and additions43
exact ELF/dual-reference manifests. No RTL change is made during coverage.

## TEST-07: Page-Fault Replay Handler Read a Masked-Off Protected Address

The unreleased `rvv_fault_replay01` prototype terminated withSIGSEGV139 at
all four SEWs in both reference VLENs. A separately preserved traced ELF
localizes it to PROT_NONE/store/boundary1/sparse-mask (0x24): the target fault
frame reportsvstart2. While validating prefix0..1, the handler read address1
on the still-protected second page even though mask bit1 is zero. A nested
SIGSEGV during SIGSEGV handling terminates the process; this is a test
implementation bug, not board RTL evidence or a signal-frame ABI failure.

The corrected handler validates memory only for active completed stores;
masked-off memory is still checked in the full page scan after repair.
The immutable `rvv_fault_replay02` passes all four ELFs at both VLENs,
192 configurations and144 expected repaired signals per VLEN. The original
failure and `rvv_fault_replay_trace01` reports remain untouched. Deliberate
restart-from-zero controls report56 numerical errors per ELF at both VLENs,
with48 cases/36 signals completed, proving the oracle detects prefix replay.
These controls are excluded from coverage releases.

## RVV-12: Integer Scalar Comparison Restart Errors and Stalled Completion

Recovery85 completes scalar comparison restart e32/m8 and e64/m8:
4032 configurations each, numerical FAIL with52168 and21272 errors.
`rvv_recovery85_release35_partial01` binds completed results in
`rvv_recovery85_active_snapshot01.json` to exact release35 ELF/source hashes,
the nonce/native protocol and both zero-error VLEN512/1024 references.
This partial audit excludes the running FP comparison and does not isolate
packed-result, prestart, guard-bit or vstart-reset error contributions.
The numerical failures do not reset or stop the batch; RTL remains unchanged.

Recovery84 adds e16/m8 scalar comparison restart completion stall:
`rvv_masks_scalar_restart_e16_m8`, SHA256
`8c1ff5f76411e47cc3c29671f90d20cd741ca245fc46ad4fef9f9ebb616568fa`.
Last drained trial is VL512/vstart256; last retired/head PCs0x1062c/0x10630
decode `vmseq.vx v24,v8,t3,v0.t` and `csrr a0,vstart`.
Cycles11262284718 to11809633500 advance while retired1632024719,
trap_count237433 and both PCs remain fixed. Both snapshots have flags0,
no watchdog halt and zero DDR outstanding/errors. All20 scene hashes
verify in `rvv_recovery08_84/terminal_scene`. This is a no-retirement scene,
not proof of a common internal cause or that the comparison never retired.
Subsequent trials remain uncovered; continuation retains9 pending exact ELFs.

Recovery83 adds e8/m8 scalar comparison restart completion stall:
`rvv_masks_scalar_restart_e8_m8`, SHA256
`c77f749548114c772d39031ea464ae44e39156d2ef55e625fc0699b72378230d`.
The last drained trial is VL512/vstart256. Last retired/head PCs
0x1060c/0x10610 decode `vmseq.vx v24,v8,t3,v0.t` and `csrr a0,vstart`.
Cycles11703482836 to12232280858 advance while retired1769337043,
trap_count265845 and both PCs remain fixed. Both snapshots have flags0,
no watchdog halt and zero DDR outstanding/errors. All20 scene hashes
verify in `rvv_recovery08_83/terminal_scene`. This confirms no retirement,
not an internal queue cause or that the comparison never retired. Later
trials remain uncovered; the continuation retains10 pending exact ELFs.

Recovery56 completes all12 remaining non-m8 SEW16/32/64 scalar comparison
restart ELFs with numerical failures, exit1 and4032 configurations each
(48384 executed configurations). SEW16 mf4/mf2/m1/m2/m4 error totals are
2124/5068/11184/22904/55476; SEW32 mf2/m1/m2/m4 totals are
2396/5528/11268/22872; SEW64 m1/m2/m4 totals are2644/5644/11432.
`rvv_recovery56_release35_scalar_partial01` binds the frozen board report
to its nonce protocol, exact release35 ELF hashes and both zero-error
VLEN512/1024 references. This is a partial22-ELF source audit, not full
source acceptance. Aggregate errors do not isolate result-bit, prestart,
guard-bit or vstart-reset errors. The batch continues after numerical
failures without reset; no RTL change made.

Recovery09's unchanged accepted dual-DDR image completed five scalar/immediate
comparison restart ELFs (e8 mf8/mf4/mf2/m1/m2), all numerical failures, then
stalled at e8/m4. The first ELF reports4032 configurations and2124 errors;
per-operation totals alone do not distinguish incorrect packed result bits
from vstart/guard errors. Both reference VLENs passed these immutable ELFs.
Do not assign a specific result-bit cause without more detailed evidence.

The e8/m4 UART's last drained boundary is VL512/vstart256, with trace enabled
for op0/seed0/first mask. Exact ELF disassembly places `vmseq.vx v24,v8,t3,v0.t`
at0x1060c and the following `csrr a0,vstart` at0x10610. Snapshots agree on those
last/head PCs, retired2196805637 and traps529652; cycles advance from15528632409
to15952593812. Both DDR outstanding/error counters are zero, live flags are
zero and neither snapshot is a watchdog capture. This proves no-retirement
completion stall, not its internal mask queue cause or equivalence to RVV-02
or RVV-11. Preserve the original report, UART, ELF and both snapshots under
`rvv_recovery08_09/terminal_scene`; do not replace the failed attempts.

## RVV-13: Integer Vector Comparison Source-Alias Restart Failures

Recovery56 completes all12 remaining non-m8 SEW16/32/64 comparison-alias
restart ELFs with numerical failures, exit1 and4032 configurations each
(48384 executed configurations). SEW16 mf4/mf2/m1/m2/m4 error totals are
2352/5544/12092/24764/51360; SEW32 mf2/m1/m2/m4 totals are
3172/7764/13968/28410; SEW64 m1/m2/m4 totals are3414/7236/15438.
`rvv_recovery56_release35_alias_partial01` binds the frozen board report
to its nonce protocol, exact release35 ELF hashes and both zero-error
VLEN512/1024 references. This is a partial22-ELF source audit, not full
source acceptance. Aggregate errors do not distinguish active-result,
prestart, guard-bit or vstart-reset failures. The batch continues without
reset after these numerical failures; no RTL change made.

Recovery10 live snapshot08 records five completed numerical failures for
`rvv_masks_cmp_alias_restart_e8_` shapes mf8/mf4/mf2/m1/m2. All exit1,
each reports4032 configurations; error totals are2208/4512/10704/24364/51848
respectively. The e8/m4 case was still running when this snapshot was taken;
this observation alone is not a confirmed no-retirement stall.

Unlike RVV-12's scalar/immediate comparisons into v24, this family executes
six masked vector/vector comparisons with destination v8, then the same six
with destination v16. Each destination overlaps one vector source. The
generator loads both full source groups and v0 before setting target VL and
vstart, then captures post-operation vstart and packed destination bits.
The source-overlap inactive policy permits old or one where applicable;
prestart and no-body bits must remain unchanged. Numerical totals alone
do not identify whether prestart preservation, active results, guard bits
or vstart reset failed. Do not merge this finding with RVV-12 or assign an
internal queue cause without discriminating evidence. No RTL change made.

Evidence: immutable `rvv_recovery08_10/resume/board_report_live08.json` and
the release's exact ELF hashes/reference reports. Ordinary failures continue
to later cases; any eventual stall must preserve UART and live snapshots.

The subsequent terminal scene confirms e8/m4 no-retirement at VL512/start256.
ELF PC0x105dc is `vmseq.vv v8,v8,v16,v0.t`; head PC0x105e0 reads vstart.
Cycles284321037773->284720537380 advance while retired48519341823 and
trap_count17293864 remain fixed. Both snapshots have live flags0, no watchdog
halt, and both DDR channels have zero outstanding transactions/errors.
This establishes the completion stall but not the internal cause. Full UART,
report and telemetry are retained in `rvv_recovery08_10/terminal_scene`.
Recovery11 preserves all655 unattempted cases and adds the319 pending cases;
all974 exact case identities/hashes are checked, known restart-stall families
are deferred rather than omitted. Original bitstream/kernel remain unchanged.

Recovery81 adds an e8/m8 comparison-source-alias completion stall:
`rvv_masks_cmp_alias_restart_e8_m8`, SHA256
`81dbe6051bc49482b31867705647da8787a940cb7ce03f143ec2f233990999bf`.
The last drained trial is VL512/vstart256. Last retired/head PCs
0x105dc/0x105e0 decode `vmseq.vv v8,v8,v16,v0.t` and `csrr a0,vstart`.
Cycles11355911058 to11934079568 advance while retired1637819392,
trap_count239005 and both PCs remain fixed. Both snapshots have flags0,
no watchdog halt and zero DDR outstanding/errors. All20 scene hashes
verify in `rvv_recovery08_81/terminal_scene`. The head lacks validity;
the last retired PC does not prove the comparison never retired. This
confirms a separate completion-stall scene without an internal queue
explanation, completed numerical marker or coverage of subsequent trials.
Recovery82 retains14 pending exact ELFs.

Recovery82 adds the e16/m8 comparison-source-alias completion stall:
`rvv_masks_cmp_alias_restart_e16_m8`, SHA256
`7d94ce0563bf2a8f4af8e73959178211ead5e99872b64402baa866a44540552f`.
The last drained trial is VL512/vstart256. Last retired/head PCs
0x10600/0x10604 decode `vmseq.vv v8,v8,v16,v0.t` and `csrr a0,vstart`.
Cycles11255434600 to11829637878 advance while retired1633635733,
trap_count237744 and both PCs remain fixed. Both snapshots have flags0,
no watchdog halt and zero DDR outstanding/errors. All20 scene hashes
verify in `rvv_recovery08_82/terminal_scene`. Neither the invalidity-unqualified
head PC nor the last retired PC establishes an internal queue cause or
that the comparison never retired. Subsequent trials remain uncovered;
the continuation preserves the remaining13 exact ELF identities/hashes.

Recovery83 completes comparison-source-alias restart e32/m8 and e64/m8:
4032 configurations each, numerical FAIL with53630 and29272 errors.
`rvv_recovery83_release35_partial01` binds both completed results in
`rvv_recovery83_active_snapshot01.json` to exact release35 ELF/source hashes,
the nonce/native protocol and both zero-error VLEN512/1024 references.
The partial audit excludes the running scalar case and is not whole-release
acceptance. These smaller-VLMAX variants complete despite numerical errors;
the e8/e16 stalls and subsequent unexecuted trials remain separate evidence.

## RVV-11: FP Comparison Restart Result Errors and Stalled Completion

Recovery85 completes masked FP comparison restart e32/m8 and e64/m8:
71680 configurations each, numerical FAIL with974462 and409190 errors.
`rvv_recovery85_release34_partial02` binds both completed results in
`rvv_recovery85_active_snapshot03.json` to exact release34 ELF/source hashes,
the nonce/native protocol and both zero-error VLEN512/1024 references.
The earlier partial01 contains only e32/m8 and is superseded for counting,
not an additional execution. Detail lines include unexpected NV flags and
result errors; the aggregate totals do not establish a single internal cause.
The running FP move is excluded from the audit; numerical failures do not
stop the batch. No RTL or original-image change was made.

Recovery56 completes the seven pending non-m8 SEW32/64 masked comparison
restart ELFs with numerical failures, exit1 and71680 configurations each
(501760 executed configurations). SEW32 mf2/m1/m2/m4 error totals are
53258/106170/197698/386676; SEW64 m1/m2/m4 totals are
56916/106086/197614. `rvv_recovery56_release34_masked_partial01` binds
the frozen board report to its nonce protocol, exact release34 ELF hashes
and both zero-error VLEN512/1024 references. This partial15-ELF source
audit does not establish full source acceptance or an internal cause.
The batch continues to FP move restart without reset; no RTL change made.

Recovery08 terminates with six numerical failures, one confirmed stall
and667 unattempted cases. Besides the slide diagnostic, all five completed
masked FP16 comparison restart shapes mf4/mf2/m1/m2/m4 fail. This is more
than the excess-NV symptom RVV-09: e16/m2 op0/seed0/VL64/all-on/start32
reports12 errors while expected and actual fflags are both16 (or17 for
initial NX). The oracle counts at most one vstart error and one combined
guard error, so at least ten result-mask bits mismatch in that trial.
The retained summary does not identify their exact bit positions.

`rvv_fp_compare_restart_e16_m8` then stalls. The last drained boundary is
VL512/vstart256, for seed0/op0/all-on/initial-fflags0. Last retired PC0x1062c
is `vmfeq.vv v24,v8,v16,v0.t`; head PC0x10630 is `csrr a0,vstart` in the
immutable released ELF. Cycles advance20982861208->21400682645, but
retired4959643511, trap_count828307 and both PCs are unchanged. Neither
snapshot has watchdog halt or live flags, and both DDR channels have
zero outstanding transactions and response errors. This establishes a
stalled comparison-completion sequence, not the precise internal queue
cause or identity with RVV-02/RVV-10. Preserve separate failure identities
until a focused cycle trace distinguishes them.

Evidence: `rvv_recovery08_08/terminal_scene` (full UART/report/snapshots),
`rvv_recovery08_08/resume/board_report.json`, additions34 exact ELF and
dual-reference reports. Recovery09 preserves all667 pending names/hashes
and moves the37 remaining FP comparison/move restart cases to the tail;
no case is omitted or relabeled passed. Original bitstream/kernel only.

Recovery41 extends the evidence to completed unmasked FP16 comparison
restart shapes mf4/mf2/m1/m2/m4. Each exits1 after71680 configurations,
with total error counts35024/80816/170016/351520/796448 respectively.
`rvv_recovery41_release34_unmasked_partial02` binds these five exact
released ELF records to the identified board batch and both VLEN512/1024
references. All358400 configurations were executed with numerical
failures; they are not passing configurations. The scoped source is
`rvv_fp_compare_restart_unmasked01`, not the whole additions34 release.

For e16/mf4 op0/seed0/VL16/start15, expected and actual flags are both16,
yet the trial reports5 errors. The oracle can contribute at most one
vstart-status error and one combined buffer-guard error, and the flags
match, so at least three result-mask bits mismatch. Exact bit positions
remain unlogged. This proves the failure is not only incorrect fflags
and is not restricted to predicated comparisons. It does not establish
the internal RTL cause or equivalence with a stalled completion scene.
The unmasked e16/m8 case remains running in this partial audit; receiving
its trial output is not proof of completion or numerical correctness.

The later `rvv_recovery41_release34_unmasked_results01` audit completes
this selected unmasked source: all15 SEW16/32/64 ELFs finish with exit1
and numerical failures, each executing71680 configurations (1075200
total). Their recorded execution intervals sum to306.719 seconds; this
is observer wall time, not a hardware cycle benchmark. All three m8 ELFs
finish numerically failing rather than stalling. SEW32 error totals for
mf2/m1/m2/m4/m8 are40448/96992/181280/362784/910208; SEW64 totals for
m1/m2/m4/m8 are49232/97136/181424/413680. The complete source audit does
not mark the mixed masked/unmasked additions34 release fully executed.
Do not infer one shared RTL cause from these outcomes or use the completed
unmasked forms to accept the separately stalled masked m8 form.

## RVV-15: Ordered Indexed Segment Replay Check Mismatch

Recovery12's additions56 case
`rvv_fault_replay_segment_nf7_indexed_e32_mf2` finishes with exit1:
96 configurations,72 handler signals and one check error. Both VLEN512
and VLEN1024 references of the exact released ELF finish with exit0,
96 configurations,72 signals and zero errors. ELF SHA256:
`581a695b625716256771c14df272b7afa912b1fa55f6180822d5bc7d17c87b42`.

The immutable evidence is
`rvv_recovery12_indexed_failure01` under the campaign directory: full
report snapshot, exact ELF, generated assembly and both reference entries
with source-report hashes. NF7/e32/mf2 with index EEW32 is a legal shape;
the released index and data register groups are disjoint. No board reset,
RTL change or replay was made to collect this evidence.

The aggregate error includes trap metadata/vector state, completed-prefix
checks, completion vstart/signal counts and result/memory/guard checks.
It does not reveal which check failed or the offending configuration.
Thus this is a measured board/reference mismatch, not an established
internal RTL cause, a demonstrated reproducible failure or proof of
identity with RVV-04's excess-signal failures. Preserve it separately
for a phase-specific reproduction during the later unified repair.

## RVV-16: Zero-Stride Replay Stops At Kernel Vector-State CSR Boundary

Recovery12 attempts `rvv_fault_replay_strided_zero_stride_e64_m2` after13
zero-stride numerical failures. The observer confirms no retirement and
preserves the full UART/report and both hardware snapshots in
`rvv_recovery08_12/terminal_scene`. Cycles advance365796983075 to366369391768;
retired181622395802, trap_count19242939 and last/head PCs remain unchanged.
Both DDR ports have zero outstanding transactions and response errors;
the watchdog and live halt flags are clear.

Last/head PCs are `0xffffffff80013a16`/`0xffffffff80013a18`. Direct disassembly
of the accepted Image, not the different current vmlinux, maps these to
`add a5,a5,a4` followed by `csrr a0,vstart`. The accepted Image's extracted
configuration has64-bit RISC-V enabled and relocation/KASLR disabled;
the annotation uses its fixed RV64 kernel link base. The preceding recorded
store-page fault is at `0xffffffff80b8754e`, an `sd t3,48(a0)`, with
tval `0x3ff1b91000`. Its relation to the tested fault/replay phase is not
established by the aggregate output.

`zero_stride_stall_annotation.json`, accepted Image configuration and raw
instruction windows retain the evidence. The head probe is commit port0 PC
without a captured validity bit: this establishes the stopped PC boundary,
not an asserted-valid CSR request or an internal queue cause. Do not claim
identity with earlier user-mode restart stalls. Original-image recovery13
preserves all746 unattempted ELF identities, deferring the94 remaining
zero-stride shapes alongside other stall-prone families without omitting
them or marking this stalled case passed.

Recovery41 adds three completed single-field zero-stride replay failures:
SEW8/16/32 at m4 each report16 configurations,16 signals and16 errors
with exit1, while the bound references expect12 signals and zero errors.
`rvv_recovery41_release57_partial01` verifies their exact released ELF
metadata and both VLEN references. The aggregate output does not identify
which individual fault-state, vector-prefix, data or guard check failed.

The next case, `rvv_fault_replay_strided_zero_stride_e64_m4`, stalls without
a completed numerical marker. Exact ELF SHA256 is
`f9ef7eecca757fe9f006a325e73fcd814afc89ea6b615afbd20fc357846b30ec`.
Cycles41352661786 to41936136756 advance while retired15459365213,
trap_count2012486 and last/head PCs0xffffffff80013a16/0xffffffff80013a18
remain fixed; both DDR channels have zero outstanding transactions and
response errors, with clear halt flags and no watchdog halt.

`rvv_recovery41_zero_stride_annotation01` binds the unchanged accepted
Image SHA256716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285,
its extracted fixed-link RV64 configuration and exact instruction bytes:
last/head decode `add a5,a5,a4` and `csrr a0,vstart`. Unlike recovery12,
the last recorded trap is cause13 (load page fault) at user PC0x10846,
which the exact ELF decodes as `vlse64.v v24,(a0),t3,v0.t`, with
tval0x3f87fed000. This strengthens the measured vector-fault/kernel-CSR
boundary evidence without proving an asserted-valid CSR request, active
trial details or one common internal RTL cause. The19 original scene
files remain hash-verified in `rvv_recovery08_41/terminal_scene`;
annotations are separate and do not modify that archived scene.
Recovery42 retains all185 pending exact ELF identities.

Recovery42 completes all86 released zero-stride segment replay ELFs for
NF2..8: NF2 has18 shapes, NF3/4 have14 each and NF5..8 have10 each.
`rvv_recovery42_release57_segment_results01` binds every segment ELF
record to the identified board report and both references; the selected
set was checked against all additions57 records with fields greater than1.
Each exits1 after32 configurations, reporting32 signals and32 errors
instead of the reference24 signals and zero errors. All2752 segment
configurations were executed, with no newly stalled segment ELF in this
batch. Their similar aggregate output does not prove which individual
trial or handler/data/guard check failed, including all-off-mask and
field-split alternatives. Neither numerical acceptance nor a common RTL
root cause is established by completing execution.

Inventory45 shows the full108-ELF zero-stride release at102 numerical
failures,2 confirmed stalls and4 unattempted single-field m8 shapes.
The two stalls have unexecuted inner operations, so neither the release
nor its exception-replay coverage is accepted as complete.

Recovery76 completes the single-field m8 SEW8/16/32 zero-stride replay
ELFs: each exits1 after16 configurations with16 signals and16 errors,
versus12 signals and zero errors in the bound references.
`rvv_recovery76_active_snapshot02.json` and
`rvv_recovery76_release57_partial01` verify exact release records, batch
nonce and both VLEN references for these three failures. Aggregate output
does not identify the individual failing handler/data/prefix/guard checks.
The SEW64/m8 ELF is still running in that snapshot; it is not a failure
or completed result merely because narrower shapes failed.

Recovery76 subsequently stalls in the single-field SEW64/m8 zero-stride
ELF, SHA256
`1979cc198f109b637048ec55c35f57e6ae8686910632166ccf6d5d93f5029744`.
Cycles11928600425 to12482942310 advance while retired1855145852,
trap_count276203 and last/head PCs0xffffffff80013a16/0xffffffff80013a18
remain fixed. Both snapshots have flags0, no watchdog halt and zero DDR
outstanding/errors. All19 original scene hashes verify in
`rvv_recovery08_76/terminal_scene`.
`rvv_recovery76_zero_stride_annotation01` binds the exact ELF, report,
nonce protocol and unchanged accepted Image hash; the Image's fixed-link
configuration and actual bytes decode `add a5,a5,a4` then `csrr a0,vstart`.
The last recorded trap is cause15 at kernel PC0xffffffff80b8759e with
tval0x3fc45447d0; it is not proof of the active target fault. Head validity,
active trial and internal CSR/queue cause remain uncaptured. No completed
numerical marker exists. The108-ELF zero-stride release now has105 completed
failures and3 stalls, but stalled inner trials remain a coverage gap.
Recovery77 retains19 pending exact ELFs.

## RVV-17: Mask Logic Source-Alias Restart Stalls

Recovery13 passes its first five mask-logic restart ELFs, then preserves a
no-retirement stall in `rvv_masks_alias_restart_e8_m4`. The last drained
trial boundary is VL512/vstart256. Exact ELF disassembly shows
`vmand.mm v8,v8,v16` at0x105b8, following `csrw vstart,a6`, with
`csrr a0,vstart` at0x105bc. The destination aliases the first source;
the instruction is unmasked mask logic, not a predicated comparison.

Cycles advance13524538849 to14068291217 while retired2164401564,
trap_count380071 and last/head PCs0x105b8/0x105bc remain unchanged.
Neither snapshot is watchdog-halted, live halt flags are clear, and both
DDR channels have zero outstanding transactions and response errors.
The complete UART/report/snapshots, exact ELF and instruction window are
in `rvv_recovery08_13/terminal_scene`. This establishes a stalled mask-logic
restart/completion boundary, not its internal queue cause or identity with
RVV-13's comparison-alias stall.

Recovery14 retains all740 pending ELF identities and prioritizes132
reference-validated, non-restart multiply-add alias cases. Remaining
mask-logic restart cases join the known stall-prone families at the tail;
none are omitted or marked passed. Scheduling changes neither the ELF
code nor the original bitstream/kernel.

Recovery74 records an e8/m8 source-alias mask-logic restart stall:
`rvv_masks_alias_restart_e8_m8`, SHA256
`c0248bf088a20f66c141bc31d0029936cec655823f06a3460154e02502656998`.
The last drained trial is VL512/vstart256. Last retired/head PCs
0x105b8/0x105bc decode `vmand.mm v8,v8,v16` and `csrr a0,vstart`.
Cycles12581428879 to13118493453 advance while retired2243063377,
trap_count310654 and both PCs remain fixed. Both snapshots have flags0,
no watchdog halt and zero DDR outstanding/errors. All20 scene hashes
verify in `rvv_recovery08_74/terminal_scene`. The head probe lacks validity;
the last retired instruction is not proof that mask logic never retired.
This confirms another stalled restart/completion scene, not its internal
queue cause. No completed numerical marker exists for this ELF, and
unexecuted inner trials remain a coverage gap. Recovery75 retains26
pending exact ELFs; no RTL or original bitstream/kernel changes were made.

Recovery75 records the corresponding e16/m8 mask-logic alias scene:
`rvv_masks_alias_restart_e16_m8`, SHA256
`b81d1aa69ad7041f46657eefa39f45a6099bb1ea9d19da1890b074982844783e`.
The last drained trial is VL512/vstart256. Last retired/head PCs
0x105c4/0x105c8 decode `vmand.mm v8,v8,v16` and `csrr a0,vstart`.
Cycles11269996292 to11797223574 advance while retired1637711266,
trap_count239047 and both PCs remain fixed. Both snapshots have flags0,
no watchdog halt and zero DDR outstanding/errors. All20 scene hashes
verify in `rvv_recovery08_75/terminal_scene`. The head probe lacks validity
and the last retired instruction does not prove the mask operation never
retired. Internal queue attribution remains unproven; no completed
numerical marker exists and unexecuted inner trials remain uncovered.
The continuation retains25 pending exact ELFs.

Recovery76 completes the e32/m8 and e64/m8 mask-logic alias restart ELFs:
each exits0 with5376 configurations and errors0 (10752 in total).
`rvv_recovery76_active_snapshot01.json` and
`rvv_recovery76_release36_partial01` bind exact released ELF identities,
batch nonce and both VLEN references; board completion lines match the
VLEN1024 references exactly. VLMAX256/128 cannot reach the retained
VL512/vstart256 stall boundary. These two passes do not establish
whole-family acceptance or cover unexecuted trials in stalled ELFs.

## RVV-18: Segment Alignment Probe Stops At Segment Load Boundary

Recovery89 records the final queued e64/m2 segment alignment stall:
`rvv_segment_alignment_e64_m2`, SHA256
`09b447f99833b73b9e68457b6c565ce7aaafef838d3d704a8948c093293b4432`.
Last retired/head PCs0x1070c/0x10710 decode the phase-marker
`sd t3,0(a7)` and masked `vlseg3e64.v v24,(a5),v0.t`.
Cycles11234079549 to11804210221 advance while retired1632032417,
trap_count236386 and both PCs remain fixed. Both snapshots have flags0,
no watchdog halt and zero DDR outstanding/errors. Historical trap cause2
is not proof of a target fault; the unqualified head PC does not establish
an accepted segment request. Active offset/VL/mask and internal cause remain
unobserved. All20 hashes verify in `rvv_recovery08_89/terminal_scene`;
the final scene was archived read-only without launching another recovery.
There is no final numerical marker, so later internal trials are uncovered.

Recovery88 records e64/m1 segment alignment completion stall:
`rvv_segment_alignment_e64_m1`, SHA256
`8b916a0dd4c4dee84ccbfa098b2664bc4cf4fee03b656d33d3717fc4fd390a3d`.
Last retired/head PCs0x10706/0x1070a decode the phase-marker
`sd t3,0(a7)` and masked `vlseg3e64.v v24,(a5),v0.t`.
Cycles11253728231 to11784143469 advance while retired1631836712,
trap_count236537 and both PCs remain fixed. Historical trap cause15 has
PC0x10706/tval0x3fbbdfd000, the phase-marker store rather than segment load.
Both snapshots have flags0, no watchdog halt and zero DDR outstanding/errors.
All25 scene hashes verify in `rvv_recovery08_88/terminal_scene`. No final
numerical marker or per-trial output establishes active offset/VL/mask.
The unqualified head PC does not prove an accepted segment request, and
this scene does not prove a segment-load fault or internal RTL cause.
Continuation retains the one pending e64/m2 exact ELF.

Recovery18 stalls on the additions32 diagnostic ELF
`rvv_segment_alignment_e16_mf4`, SHA256
`4a4d90110888dda88834826dd0a65fc4dbc3ac567b1fde402ff8d307dee2ed0b`.
Both exact-ELF QEMU reference runs (VLEN512/1024) complete432 configurations
with432 numerical passes, zero target SIGBUS and zero errors. The board
produces no completed numerical marker or per-trial detail.

The exact ELF's last retired PC0x10718 is `sd t3,0(a7)`, marking phase1;
the unqualified head PC0x1071c decodes `vlseg3e16.v v24,(a5),v0.t`.
Cycles18601099431 to19122975903 advance while retired4723195984,
trap_count689055 and these PCs remain unchanged. Both DDR channels have
zero outstanding transactions and errors; halt flags are clear and neither
snapshot is watchdog-halted. The head-PC probe has no validity bit, so it
does not independently prove an accepted segment request or internal queue state.

The diagnostic uses aligned preparation/readback and vstart0, varying target
offset, VL and all-off masks in isolated children. Without a per-trial record,
the active offset/VL/mask are not established: do not label this a proven
misalignment, VL0 or all-off bug. The last recorded cause2 trap is historical,
not proof that this load trapped. Internal RTL attribution remains pending.
`rvv_recovery08_18/terminal_scene` preserves UART, exact ELF, disassembly,
two snapshots, report and hashes. Recovery19 retains all369 unattempted
ELFs and defers the segment-alignment family without marking it accepted.

Recovery35 independently records `rvv_segment_alignment_e16_mf2`, SHA256
`b6b0c2f4382e85246ce552611d49a50bde59b21bba6a64ea973323bc39f45ec7`.
last_pc0x10718 is the phase-marker `sd t3,0(a7)`; unqualified head
PC0x1071c decodes `vlseg3e16.v v24,(a5),v0.t`. Cycles13343565507 to
13871940534 advance while retired2175359669, trap_count375830 and these
PCs remain unchanged. Both DDR channels have zero outstanding transactions
and errors; halt flags/watchdog are clear. Unlike the earlier scene, the
last recorded trap is cause15 (store page fault) at0x10718 with
tval0x3fbb916000, the phase-marker store rather than the segment-load PC.
Trap count does not advance between snapshots. This does not prove a
segment-load fault, active misalignment, accepted segment request, or
internal queue cause; exact target offset/VL/mask remain unobserved.
The exact ELF, full UART/report, snapshots and disassembly are preserved in
`rvv_recovery08_35/terminal_scene`. Nine preceding vector SEW32/64 ELFs pass
96768 configurations (`rvv_recovery35_release33_partial01`). Recovery36
retains269 unattempted exact ELFs without accepting the stalled diagnostic.

Recovery36 independently records `rvv_segment_alignment_e16_m1`, SHA256
`58489bb95780201262a84bba04a6e1b7afb96216f7162134251787b212dfa8dc`.
The same phase-store/segment-load last/head boundary is0x10718/0x1071c,
with the exact ELF selecting e16/m1. Cycles11766778313 to12278849332
advance while retired1723531682, trap_count269517 and the PCs stay fixed.
The last recorded cause15 store page fault is at the phase-store PC0x10718
with tval272834875392, not the segment-load PC. Both DDR channels have
zero outstanding transactions/errors; halt flags/watchdog are clear.
`rvv_recovery08_36/terminal_scene` preserves exact ELF/UART/report/snapshots
and disassembly. No completed numerical result or per-trial target detail
exists; active offset/VL/mask, target acceptance and internal queue cause
remain unproven. Recovery37 retains268 unattempted exact ELF identities.

Recovery37 adds `rvv_segment_alignment_e16_m2`, SHA256
`cfcdabf6e7a378d789c01dde8864e4beb16a133712090e805841cb24648db1df`.
last_pc0x1071e is the phase-marker store and unqualified head PC0x10722
decodes `vlseg3e16.v v24,(a5),v0.t` with e16/m2. Cycles11734066823 to
12250290213 advance while retired1721865834, trap_count267681 and these
PCs remain fixed. The last recorded cause15 store page fault is at0x1071e,
with tval272818348032, rather than the segment-load PC. Both DDR channels
have zero outstanding transactions/errors, clear halt flags and no watchdog
halt. The independent exact ELF/UART/report/snapshots/disassembly are in
`rvv_recovery08_37/terminal_scene`. No numerical marker or per-trial target
detail exists; target acceptance, offset/VL/mask and internal cause remain
unproven. Recovery38 retains267 unattempted exact ELF identities.

Recovery38 adds the SEW32 scene `rvv_segment_alignment_e32_mf2`, SHA256
`c99bbaf553620955f840f4a176aed40d8b6798b164c70f3c320f2dd7a23c199b`.
last_pc0x10704 is the phase-marker store; unqualified head PC0x10708
decodes `vlseg3e32.v v24,(a5),v0.t`. Cycles11760680870 to12286996891
advance while retired1722680017, trap_count269152 and these PCs stay fixed.
The last recorded cause15 store page fault is at0x10704, with
tval273504047104, not at the segment-load PC. Both DDR channels have zero
outstanding transactions/errors, clear halt flags and no watchdog halt.
`rvv_recovery08_38/terminal_scene` retains exact ELF/UART/report/snapshots
and disassembly. This extends the measured external boundary to SEW32;
it does not prove target acceptance, active offset/VL/mask or a shared
internal cause. No completed numerical result exists. Recovery39 retains266
unattempted exact ELF identities.

Recovery39 independently records `rvv_segment_alignment_e32_m1`, SHA256
`915d1b55125923a45379f836f4c1002f5c16675f8c60ddd553376bf554759675`.
last_pc0x10704 is `sd t3,0(a7)` and unqualified head PC0x10708 decodes
`vlseg3e32.v v24,(a5),v0.t`. Cycles11808585008 to12326067106 advance,
while retired1724971673, trap_count268820 and these PCs remain fixed.
The last recorded cause15 store page fault is at0x10704 with
tval272930349056. Both DDR channels have zero outstanding transactions
and response errors; halt flags and watchdog halt are clear. The exact
ELF/UART/report/two snapshots/disassembly remain in
`rvv_recovery08_39/terminal_scene`. As with the preceding alignment scenes,
there is no completed numerical marker or per-trial offset/VL/mask record;
target acceptance and a common internal RTL cause are not established.
Recovery40 retains265 unattempted exact ELF identities. Inventory37 records
1819 passed,599 failed,37 stalled,265 not attempted and47 mixed outcomes
among2767 selected ELFs; these are execution outcomes, not ISA acceptance.

Recovery40 independently records `rvv_segment_alignment_e32_m2`, SHA256
`66099f6f1ace2abb2565a747bdc96aad20d3c56828b006838b5d3aeb77f41b03`.
The exact ELF has last_pc0x1070a at the phase-marker `sd t3,0(a7)` and
unqualified head PC0x1070e at `vlseg3e32.v v24,(a5),v0.t`.
Cycles11715788228 to12283447590 advance while retired1720442179,
trap_count267424 and these PCs stay fixed. The last recorded cause15
store page fault is at0x1070a with tval273014648832. Both DDR channels
have zero outstanding transactions and response errors; halt flags and
watchdog halt are clear. All20 preserved scene files pass their recorded
hashes in `rvv_recovery08_40/terminal_scene`. Active offset/VL/mask,
target acceptance and internal RTL attribution remain unobserved; there
is no completed numerical marker. Inventory38 records1819 passed,
599 failed,38 stalled,264 not attempted and47 mixed outcomes.

Recovery41's immutable manifest retains all264 pending exact ELF records.
Its explicit scheduling order places the15 unmasked FP comparison restart
ELFs first, then other non-m8 combinations, remaining m8 combinations,
and the two remaining SEW64 segment-alignment diagnostics last. The exact
pending set, order, batch script/hash and protocol inputs were checked
against recovery40's terminal report. This changes order only, not
test semantics or acceptance criteria; it does not accept stalled tests.

## Recovery14 Observer I/O Failure (Not an RTL Finding)

After105 recorded passes, Windows denied atomic replacement of `report.json`
with `WinError 5`. The preserved temporary report contains the precise exception;
this was not a confirmed board stall. The original report, temporary report and
UART are retained in `rvv_recovery08_14/observer_failure_scene`.

A separate read-only capture found continuing instruction retirement and live
batch UART. No restart, serial command, RTL change or image change was performed.
The observer now retries transient permission failures for at most5seconds;
110 native tests pass, including transient and persistent failure tests.

A separately hash-checked hidden reattachment task resumes observation without
restarting the guest batch. Its identified protocol parser retains105 previous
passes, marks47 cases with missing output as incomplete, and only accepts new
results with complete PREP/START/output/END boundaries. A focused gap-parser test
confirms missing results cannot become passes or a complete campaign. Live
results are in the Windows recovery14 `reattach01` directory, mirrored by
`rvv_recovery14_reattach_monitor01`. The47 gaps require selective later retesting;
the initial report remains immutable. The precise external reader denying
FILE_SHARE_DELETE has not been attributed.

## Recovery26 Loader Cleanup Failure (Not an RVV Finding)

Recovery137 stops after Linux startup because cleanup cannot find an already
exited Vivado process. The original loader report remains `state=failed`,
with `execution_started=true`, `launch_attempted=true`, the original kernel
hash and the Linux-ready UART marker. UART SHA256
42e405172c01b2e8ab76b9fcd13d46c2ac4df9bed3dd69e41292bb3e99fa43f5
verifies against the raw file. Ethernet is locked/isolated, AW/B3150782 and
AR/RLAST38071334 are balanced, and response errors are zero. No observer
report exists at this boundary. All10 file hashes verify in
`rvv_recovery08_137/startup_cleanup_scene`. After the old task is terminal,
no board transport/observer remains and the board lock is free, the
byte-identical recovery118 continuation validates kernel/loader/batch
identities and reconnects to the preloaded tests, without reprogramming,
redownloading Linux or another board reset. Supervisor17 monitors the
unchanged10-case queue. This recovery is not an RVV result and does not
rewrite the original failed report as passed.

Recovery134 also stops during initializer read-only precheck cleanup, before
initialization firmware or Linux launch. The original report remains failed
with `program_launched=false`, the pinned initializer ELF hash, cold status7
and clear flags. Loader locked/isolated are false and AW/B/AR/RLAST/errors
are all zero. All9 diagnostic/programming/task/state hashes verify in
`rvv_recovery08_134/precheck_cleanup_scene`. The old wrapper is terminal,
no board transport/observer remains and the board lock is free before task
replacement. A byte-identical copy of recovery122's guarded continuation
validates input identities and retries into `ethernet_init_retry01`, without
bitstream reprogramming or another board reset. Supervisor16 monitors the
unchanged13-case masked-slide-up queue. No RVV case has run at this boundary;
this cleanup recovery is not a board pass or an override of arbitrary errors.
The raw `rvv_recovery08_134/initializer_retry_report01.json` subsequently
confirms `state=firmware_ready`, `passed=true`, no error and the unchanged
initializer ELF hash. Linux resumes and the observer executes e16/m1;
the original failed initialization report remains immutable.

Recovery122 stops during initializer read-only precheck cleanup, before
initialization firmware or Linux launch. The original report remains failed
with `program_launched=false`, the pinned initializer ELF hash, cold status7
and clear flags. Loader locked/isolated are false and AW/B/AR/RLAST/errors
are all zero. All9 raw diagnostic/programming/task/state hashes verify in
`rvv_recovery08_122/precheck_cleanup_scene`. After the old task is terminal,
no board transport/observer remains and the board lock is free, the
byte-identical recovery107 precheck continuation validates input identities
and retries initialization into `ethernet_init_retry01`. No bitstream
reprogramming or additional board reset is requested; supervisor15 monitors
the unchanged26-case FP-move queue. This recovery is not an RVV result or
permission to ignore arbitrary initialization errors.

Recovery118 stops after Linux startup because owned Vivado process-tree
cleanup reports a taskkill failure. The original loader report remains
`state=failed`, but contains the unchanged kernel hash and Linux-ready UART
marker. Ethernet is locked/isolated, AW/B3158123 and AR/RLAST47170207 are
balanced, and response errors are zero. No observer report exists at this
boundary. All10 archived file hashes verify in
`rvv_recovery08_118/startup_cleanup_scene`, including the raw loader report,
UART, wrapper state and original task definition. After checking the old
task terminal, no active board transport/observer and the board lock free,
the byte-identical recovery26 resume-only script verifies startup gates and
batch identity, then exposes the preloaded30 cases on the already booted
Linux. No reprogramming, board reset or RTL modification is added.
Observer21448 starts `rvv_extension_e32_m8_vf4_ops2`; supervisor14 continues
the queue. This startup recovery is not a new RVV result, does not change
the original loader failure to a pass, and does not suppress generic errors.

Recovery107 stops earlier, during initializer read-only precheck cleanup.
The failed report has `program_launched=false`, the pinned initialization
ELF hash, valid cold identity/status, zero loader transaction counts and
zero response errors. The error is the owned Vivado tree cleanup race;
the initialization firmware and Linux have not yet been launched. No RVV
case result is inferred. The initializer report/precheck diagnostics,
programming log, task definition and state are retained with hashes in
`rvv_recovery08_107/precheck_cleanup_scene`.
After confirming the old task terminal, no Vivado/recovery Python remaining,
and the board lock available, a hidden precheck-only continuation checks
overlay/kernel/bitstream hashes and batch identity, then retries initialization
into the new `ethernet_init_retry01` directory. The failed original report
is not overwritten. It continues with the original Linux/test pipeline
without reprogramming the bitstream or adding a board reset; supervisor13
monitors the same41 pending cases. Arbitrary initialization failures are
not accepted or automatically converted to passes.

The retry report subsequently records `firmware_ready`, passed=true and
no error; the Linux loader records `passed_linux_init_marker`, passed=true
and the expected UART marker. These are startup results, not RVV passes.

Recovery106 encounters the same cleanup-only startup failure. The original
loader report records the unchanged kernel hash, the Linux-ready UART marker,
locked/isolated Ethernet, balanced AW/B and AR/RLAST counts and zero errors.
The wrapper stops before exposing tests, with no observer report. This is
not a confirmed board stall and does not authorize another board reset.
The raw loader report/UART/state and original task definition are archived;
all15 hashes verify in `rvv_recovery08_106/startup_cleanup_scene`.
With the original task terminal, no Vivado/recovery Python remaining and
the board lock available, the byte-identical recovery26 resume-only script
checks startup gates and batch identity, exposes the preloaded42 cases and
starts the observer on the already booted Linux. No reprogramming or reset
is performed. Observer17916 starts `rvv_extension_e32_m4_vf4_ops2`;
supervisor12 resumes monitoring recovery106. The original failure report
is not rewritten as a loader pass, and generic cleanup errors remain errors.

The loader reports `Owned Vivado tree cleanup failed` after successfully
launching Linux and capturing `Linux console, DDR and RVV handoff are alive`.
The taskkill diagnostic says child PID5136 had already exited and parent
PID1452 was terminated. This is not evidence of a board no-retirement stall.
The startup report records the original kernel SHA256
`716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285`,
balanced loader AW/B and AR/RLAST counts, zero response errors, and locked,
isolated Ethernet after launch.

The failed startup report/UART/state and original scheduled-task definition
are preserved in `rvv_recovery08_26/startup_cleanup_scene`. Before resuming,
the wrapper was terminal, no Vivado or recovery Python process remained,
and the exclusive board lock could be acquired. A hidden resume-only task
validated the original image/report gates and immutable batch identities,
exposed the preloaded test directory successfully, then started the observer
without reprogramming or resetting Linux. The first two resumed extension
ELFs pass336 configurations, verified against their exact-ELF references
in `rvv_recovery26_release08_partial01`. Remaining cases are not accepted
by these partial results. The generic transport cleanup implementation has
not been weakened to ignore arbitrary taskkill failures.
