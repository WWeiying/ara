# Linux Kernel CSR / NF8 Residual Diagnostic Plan

2026-10-14. Read-only primary-evidence review; only this new document written.
No OS/board boot, compiler, reference, VCS, RTL edit, active-job query or CSV
reparse. This is a reproduction plan, not symptom reproduction or acceptance.

## Decision

The three historical kernel waits and the NF8 169-versus128 difference remain
open. Do not repeat their already accepted real-Sv39 counterparts to claim
closure. The smallest existing executable with relevant Linux semantics is
the sealed NF8 prefix13 fatal-output successor described below. It preserves
the first12 in-process predecessors, original syscalls/signal-frame access,
page repair, poison and full oracle. It is NOT a proven reduction of extra41
errors, and does not preserve the preceding cross-process board batch.

For the kernel stalls no exact inner tuple or architectural checkpoint is
available. A standalone CSR loop, fabricated signal frame or direct PTE
fixture would not be a same-symptom reproducer. Retain full original16 if a
later Linux experiment is authorized; extract an internal VCS trigger only
after an actual accepted request and its incomplete owner are captured.

## Primary Evidence: Three Kernel Boundaries

C = /home/wangwy/fpga_runs/ara_hw_campaign_20261007_01.
R = /home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix.
G = /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review.

Each scene is C/rvv_recovery08_N/terminal_scene. Its report records stalled,
empty program output, and "Confirmed no retirement; scene preserved".
Report, both snapshot JSONs and source ELF were freshly checked against the
scene's hashes.json. The paired snapshots have identical retired/trap counts,
advancing cycles, zero DDR read/write outstanding and zero DDR response errors.
These observations do not exclude internal vector/MMU ownership deadlock.

| Recovery / original program suffix | Fixed retired | Advancing cycle delta | Last recorded trap |
| --- | ---: | ---: | --- |
| 12 / zero_stride_e64_m2 | 181622395802 | 572408693 | cause15, kernel PC0xffffffff80b8754e, tval0x3ff1b91000; scalar sd t3,48(a0) |
| 41 / zero_stride_e64_m4 | 15459365213 | 583474970 | cause13, user PC0x10846, tval0x3f87fed000; masked vlse64.v v24,(a0),t3,v0.t |
| 76 / zero_stride_e64_m8 | 1855145852 | 554341885 | cause15, kernel PC0xffffffff80b8759e, tval0x3fc45447d0; raw opcode00f50023 (scalar sb a5,0(a0)) |

All three last-retired/head PCs are0xffffffff80013a16/0xffffffff80013a18.
Fresh raw accepted-Image bytes are97ba and00802573: add a5,a5,a4 followed by
csrr a0,vstart. Subsequent CSR reads are vtype/vl. Head PC has NO captured
valid bit; neither accepted CSR request nor active faulting transaction is
proved. The last trap is historical, not necessarily the current stall cause.
In particular the m2/m8 kernel scalar stores are not vector STORE attribution.

Original ELF hashes (full basename rvv_fault_replay_strided_zero_stride_e64_mN):
- m2: 3fc3207f555099fce31489fa5e4e93b0aa178bef89b3ad11cb30caa600babf60.
- m4: f9ef7eecca757fe9f006a325e73fcd814afc89ea6b615afbd20fc357846b30ec.
- m8: 1979cc198f109b637048ec55c35f57e6ae8686910632166ccf6d5d93f5029744.

Last phase limitation: no printed tuple, current mapping, saved signal frame,
process GPR/VRF, task identity, actual page-table dump or owner-valid trace is
established by these snapshots. Report result counts through the stalled
program are568/79/6 respectively. In each report the preceding result is the
corresponding e32/m2,m4,m8 zero-stride program, cases16/signals16/errors16.
Do not assert this one predecessor is sufficient or that result-index order
captures every scheduler/context transition.

Original full16 is unmapped0/1, load/store, modes ff/aa/24/00 in original
order, VL8, stride in t3=0 (not x0),12 expected faults and4 all-off cases.
Source/generator identity is R/fault_replay_oracle.c SHA
631da853fe5939e2a812145d23155767d4e803f3d9aa22133187d6455905588a and
R/fault_replay.py SHA47765b894cde708521c8a32ce02539e9bd140ebc1be464824252817a05755ff9.
Do not drop compiler-generated vector bootstrap or original final scalar
reads. Existing m4 full16 M6 acceptance and m2/m8 full16 M7 offline acceptance
already cover the source-derived Sv39 paths; old producer NOT_PASS records
for m2/m8 remain preserved. They do not reproduce the Linux waits.

## Original Linux Materials: Available Versus Missing

Freshly verified C/source/Image,27412480 bytes, SHA
716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285.
Its fixed-link base0xffffffff80000000 follows the archived configuration
(relocation/KASLR disabled); historical annotations use this actual image.
For each recovery12/41/76, initramfs.cpio, ara_vcu118.dtb and fw_jump.elf
freshly match that recovery.json. They are NOT interchangeable: test overlays
and embedded DTB/initrd-end differ. Their recovery.json/launch.json preserve
the exact identities and resume batch manifests/protocols/scripts.

The local buildroot linux-6.19.6 tree contains vmlinux SHA
f1e7878c152da780630da650370dfcdfb85a65c44c1dfd2ec75d74abc87fb630,
but its arch/riscv/boot/Image SHA is
0daba745ad9d7ee7527caf3681847c218a597a40db3ede065db53232d1ba3615,
NOT the accepted Image. Do not infer historical function symbols from it.
A byte-matched vmlinux/System.map and source/build provenance were not located
in this targeted inventory. This is a symbol/source mapping gap, not a missing
bootable raw Image; matching vmlinux is not mandatory just to execute Linux.

Original recovery scripts name remote release
D:\fpga_runs\ara_dual_bitgen_20261006_01\bitstream\ara_dsa_vcu118.bit/.ltx,
and load Image at0x80200000, DTB0x80100000, initrd0x88000000 using fw_jump.elf.
No matching local ara_dual_bitgen* directory was found under /home/wangwy/fpga_runs.
Original bit/LTX/deployed-state identity must be recovered/checked on that
archive before claiming same-hardware reproduction; no remote access was made.
An M9/M10 simulation image is not the historical FPGA image.

## NF8: What 169 / 128 Actually Proves

Original rvv_fault_replay_segment_nf8_strided_e32_mf2 ELF SHA
c90e2ac2ab90fba392ca887842ce07c78244405ef41428f7e8f760373e658282.
Identity57 ties current C/generator and archived assembly to this exact ELF.
Original target load/store PCs0x109c4/0x10a4e, opcodes e9c56c07/e9c56c27.

- Recovery12 report: cases192/signals192/errors169, exit1,20.017818s.
  Report SHA966130db6161b215c3586e9bcf6a929a536cdf36f433b2de1388d26b662192e8.
  Recovery13 previous_report is byte-identical, not a second observation.
- Retest supervisor04/latest_report.json: same ELF,192/192/128, exit1,
  20.236929s, run69dbca9c7803589118d7625f30051734; report SHA
  0e4a0216ebfbe6c6d3950164b234f3186af036687b4b2cd9457ba49dae895ec1.
- Original report result index103 follows NF8 strided e16/mf2; retest index396
  follows NF8 strided e32/m1. Same executable does not prove same process/kernel
  history. These differences do not establish why41 extra errors occurred.
- Archived QEMU Linux references at VLEN512/1024 report192/144/0, exit0.
  No new reference run was performed.

The original handler exits2 on a second signal in one case. Thus192 completed
cases and192 signals imply one signal per case, including all48 all-off cases,
IF counters are intact. This is an inference, not measured per-case PC evidence;
counter corruption is not ruled out. Error count aggregates signal metadata,
frame/vector prefix, returned status, full output/memory and guards. Neither169
nor128 counts failed tuples or numerical-only mismatches. No last failing
tuple/check/phase or extra41 attribution exists in these aggregate records.

Full192 real-Sv39 acceptance on M4 already covers the original tuple geometry,
144 required faults and48 no-fault all-off cases. Its M-mode observer, fixed VA,
direct PTE repair and four-case partitions do not exercise Linux PROT_NONE
encoding, siginfo/sc_extdesc/datap, rt_sigreturn or continuous192 Linux history.
Do not rerun that closed matrix as a proxy for these missing semantics.

## One Executable Minimum: Existing NF8 Linux Prefix13

Reuse, without rebuilding or editing:
G/masked_translation/nf8_strided_review/nf8_linux_prefix13_diagnostic01/fatal_successor01/build01/nf8_linux_prefix13_diagnostic.elf
SHA e7ce9267d6bdba32cdfe23af2f511bf50e7c0be662b19eebdf3a72438f283659.
All31 entries across this successor's external_pins/artifact_pins freshly
matched (some paths occur in both maps). Its original rebuilt ELF matches
the original c90e... identity. Preparation/formatter Host is not Linux execution;
ARTIFACTS.json still states NOT_RUN. No duplicate compilation is needed.

Preserve natural trials0..12, with all12 predecessors, original maps/protection,
signal action, all scalar input/output/memory/guards, assembly, kernel frame
access, page repair, prefix poison and return. Trial12 is
(unmapped0,store0,boundary1,mode3,gap1,split0), e32/mf2,NF8,VL8,mask00,
stride36,base=mapping+4060; it must not fault. Expected prefix result is
cases13/signals12/errors0. The cut is after its original oracle and munmap,
not before checking data. This is not the byte-identical full192 ELF.

For a separately authorized run in a verified original-ABI RV64 Linux guest,
stage this exact ELF and use a fresh regular-file output destination:

```sh
./nf8_linux_prefix13_diagnostic.elf > nf8-prefix13.log 2>&1
rc=$?
printf 'process_rc=%s\n' "$rc"
```

This command was NOT run. Use an external bounded observer, with no automatic
retry and no assumption that guest timeout/signals can recover a kernel stall.
Original manifest180s can be a predeclared board observation ceiling, not a
derived full-system VCS budget. If retirement stops, capture once and preserve
the scene rather than resetting automatically. No new OS/VCS runtime estimate
is justified from the historical20-second user program result.

Normal path requires13 complete diagnostic rows, exact tuple order and expected
summary/exit0. Any signal at trial12 must be attributed by actual PC; do not
assume the target. Read first-error check/field/index/got/want, si_code/si_addr,
saved VL/vtype/vstart/vlenb and frame validity. Diagnostic load/store PCs are
0x113de/0x11468, not original or build03 PCs. Fatal exit2 remains failure and
attempts one bounded841-byte scalar write; it does not longjmp or repair again.
The write may fail/block, and fatal output retains only the current first-signal
record, not all predecessor records. Lost output never becomes a PASS.

Interpretation: this one run can locate the earliest all-off Linux discrepancy
with in-process predecessors preserved. A clean result closes only this bounded
current Linux path, not the extra41, full192, original external batch, or kernel
stall. If exact historical history is required, use the archived ordered batch
or a captured checkpoint; neither may be replaced with invented warmup. Batch
replay is not authorized here, and absence of a full machine/process checkpoint
prevents deterministic restoration of the old stopped state.

## Kernel Stall Follow-up, Only After Material Recovery/Authorization

Best representative is recovery41 m4 because its recorded fault is genuinely
the user vector-load target. Keep full16 original calls and Linux signal ABI;
do not select an unknown inner call. Record original batch context separately.
At exception entry, before any vector instrumentation, retain trap PC/cause/
tval, task/privilege state, satp and relevant PTEs, saved vector-state/frame
pointers and first architectural CSR access. Capture actual request valid&&ready,
VID/owner, response and consumer completion, global ara_idle and CSR response.

Falsifiers: (1) no accepted CSR means head-PC attribution is insufficient;
(2) accepted CSR plus nonempty vector owner after fault points to cleanup/idle
dependency, but owner/queue must identify the unit; (3) drained owners and a
completed CSR response with bad kernel frame moves investigation to context
handling. Zero external DDR outstanding alone distinguishes none of these.
Only a captured failing internal sequence may justify a narrow VCS replay.

Outstanding materials are matched deployment bit/LTX and kernel symbol/source
provenance, a usable same-ABI Linux execution environment, and actual task/
page-table/frame/owner state at failure. Existing raw Image, original ELFs and
boot blobs are available; do not misreport them as missing. No present evidence
establishes a new RTL defect or closes any of these original Linux symptoms.
