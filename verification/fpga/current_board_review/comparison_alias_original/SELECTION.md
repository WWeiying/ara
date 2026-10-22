# RVV-13 Comparison-Alias Selection

## Static Conclusion

Select the genuine archived **e16/m1, seed0, raw_op0, VL32, vstart16,
mask-mode0** single: `vmseq.vv v8,v8,v16,v0.t`. It already reproduces the
measured prefix's first wrong prestart bit and nine-error total. No new abstract
alias test is needed. Candidate03 contains a directly relevant old-vd read-origin
correction, so first establish whether this exact source point already passes.
There is **no current RVV-13 failure/root-cause claim** from this static review.

Read-only source/RTL inspection, hash checks and ELF disassembly only. No program,
host oracle, Spike, VCS, build or production modification was performed.
The parent's candidate03 original47 FP-move PASS is a different instruction
family and is not RVV-13 evidence. Neither are the ongoing `vmand.mm` alias jobs.

Paths below use archive root
`C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01` and frozen RTL root
`R=/home/wangwy/fpga_runs/current_board_memory_candidate03/frozen/sources`.

## Original19 And Measured Tuples

`C/all_failure_scope_audit02/audit.json` identifies19 **failed** original
`rvv_masks_cmp_alias_restart_*` ELFs. The separate e8/m4, e8/m8, e16/m8
completion-stall records are not included. Each original numerical program
has4032 configurations: three seeds,12 operations, seven lengths, four mask
modes and four start choices. Ops0..5 compare into source v8; ops6..11 into
source v16. They are six integer vv comparisons, not scalar comparisons,
floating-point comparisons or mask-logic operations.

All19 archived first failures have seed0/raw_op0/mode0, returned_vstart=0 and
both guards=0x5b5b5b5b5b5b5b5b. Mode0 means predicate bytes0xff, **not all-off**.
All first wrong bits are prestart, so permitted inactive/tail agnostic choices
do not explain those particular mismatches. Raw-op0 aliases vd=vs2=v8; these
first points do not exercise the second-source destination v16.
All selected VLs are at most128 and starts at most64, within the first256-bit
aggregate mask word on four lanes; a generic VL512 starvation test would not
replay these numerical triggers.

| Shape suffix | VL / start | First bit | Old=expected -> actual | Trial errors | Old vd layout |
| --- | --- | ---: | --- | ---: | --- |
| e8_mf8 | 8 / 4 | 3 | 0 -> 1 | 1 | EW8 |
| e8_mf4 | 16 / 8 | 3 | 0 -> 1 | 4 | EW8 |
| e8_mf2 | 32 / 16 | 3 | 0 -> 1 | 7 | EW8 |
| e8_m1 | 64 / 32 | 3 | 0 -> 1 | 15 | EW8 |
| e8_m2 | 128 / 64 | 3 | 0 -> 1 | 28 | EW8 |
| e16_mf4 | 8 / 4 | 3 | 0 -> 1 | 1 | EW16 |
| e16_mf2 | 16 / 8 | 3 | 0 -> 1 | 4 | EW16 |
| e16_m1 | 32 / 16 | 3 | 0 -> 1 | 9 | EW16 |
| e16_m2 | 64 / 32 | 3 | 0 -> 1 | 16 | EW16 |
| e16_m4 | 128 / 64 | 3 | 0 -> 1 | 32 | EW16 |
| e32_mf2 | 8 / 4 | 0 | 1 -> 0 | 4 | EW32 |
| e32_m1 | 16 / 8 | 0 | 1 -> 0 | 6 | EW32 |
| e32_m2 | 32 / 16 | 1 | 1 -> 0 | 9 | EW32 |
| e32_m4 | 64 / 32 | 1 | 1 -> 0 | 19 | EW32 |
| e32_m8 | 128 / 64 | 2 | 1 -> 0 | 34 | EW32 |
| e64_m1 | 8 / 4 | 0 | 1 -> 0 | 4 | EW64 |
| e64_m2 | 16 / 8 | 0 | 1 -> 0 | 5 | EW64 |
| e64_m4 | 32 / 16 | 0 | 1 -> 0 | 11 | EW64 |
| e64_m8 | 64 / 32 | 1 | 1 -> 0 | 16 | EW64 |

These old-vd layouts follow the actual full-capacity `vleSEW.v v8` immediately
before each comparison. Old packed mask bits are raw bits of source array a,
not the output-buffer poison and not an independently initialized EW8 mask.
Both source groups are reloaded on every call, so the first target does not
inherit a prior comparison's destination layout. Fractional LMUL leaves the
rest of the physical register outside that loaded capacity; do not invent a
full-register oracle for those bytes.

## Provenance And Oracle

The following retained artifacts form the original -> measured prefix -> single
chain, with19/19 `confirmed=true` in the symptom comparison:

- `C/rvv_additions35/binaries/rvv_masks_cmp_alias_restart_<shape>`: original ELF.
- `C/rvv_mask_alias_restart01/`: original assembly, operations.h and manifest.
- `C/rvv_mask_first_trace01/`: per-case scenario.c/S, original_rebuilt.elf,
  binaries and manifest. Instrumentation preserves original trial order/oracle.
- `C/rvv_small_masks02/`: genuine reduced scenarios, binaries and manifest;
  `prefix_board_report.json` preserves actual prefix failures.
- `C/rvv_mask_symptoms02/sampled_report.json`: actual single board failures;
  `symptoms.json` matches first bit, stimulus, error count, vstart and guards.

This review rehashed190 case files: for each shape, original/rebuilt/prefix/single
ELFs plus both sets of three source files. All matched their recorded identities;
all19 single assemblies also equal the original assembly. Report/manifest hash
links and all38 retained VLEN512/1024 single reference PASS records were checked.
No new reference execution was performed. The manifest's preparation-time
`board_reproduction_confirmed=false` is superseded by these later measured
single reports, not silently edited. Original parent reports contain aggregate
errors, not raw first-bit evidence; that precision comes from the measured prefix.

Selected identity:

| Artifact | SHA256 |
| --- | --- |
| Original e16/m1 ELF | 7eea6bfd58e3ff6e33e6297001d9ff16452e97e22b0b93c42b1fadcda4e13731 |
| Prefix e16/m1 ELF | b1e72e87fbc24a3c7bf70149ffdc43f8877bf9aab914a02b04586b1790cb9ce9 |
| Single e16/m1 ELF | 7e062e44d8dbefc116e08d8aaca49af9e99007fa2895ba1987cf69bf561f2106 |
| Single scenario.c | 40c76957679212a1fbbb37798406aad76f1b845a87ac74cddeca1586e8f7422a |
| Single/original scenario.S | 0043fefc356e80e0617d096ca3ed810ad68e5b33fa0881f25e71d1a196edd02d |
| operations.h | 7ad053f7e7679fd88c32af657b9f48543ceaeeda48b149181985121f7f6a22d5 |
| small02 manifest | eaafd63d14aa2a0d2019a49bb566d1983b2a1b94c15cbfbe17619185b9936ae8 |
| symptoms02 | 1c7017790bd6953d6a6095ff793d1744d4a6c08a2ebca4d5d11a8cb7372f4409 |

The archived single's op0 starts at0x10558; target PC0x10570/opcode60880457,
csrr vstart at0x10574, vsm at0x1057c. These are **Linux single ELF addresses**,
not the original parent or any future SoC port address.

Preserve the original xorshift RNG seed0xc274caf34727a125, full cap source
generation/loading, every-eighth-element equality, mask128 bytes0xff, tu/mu,
target VL32/start16, immediate vstart sampling and packed `vsm.v` readback.
At VLEN1024 cap=64: oracle checks all64 packed result bits and the two original
64-bit guards at output[0]/output[1025], not all1024 bits of v8. Active bits must
match equality; prestart/no-body bits must equal old source bits; inactive body
allows old or1 for comparison overlap; tail allows old,1 or computed expected.
Do not strengthen or discard that original agnostic policy.

Macros are SEW=16, SCALAR_FORMS=0, ALIASES=0, COMPARISON_ALIASES=1,
CARRY_FORMS=0, RESTART_MASKS=1. Original tools `mask_oracle.c`, `masks.py`,
`repro/trace_masks.py` still match the archived source hashes; `reduce_masks.py`
matches the recorded reducer hash. Future adaptation should replace Linux
write/ioctl/exit/startup only, retaining asm/data/oracle and recording new PCs.

## Candidate03 Path And Discriminator

Six inspected frozen RTL files match the candidate03 snapshot manifest.
Dispatcher SHA256 is05e9a4633d3d3a989fc5433fbf647c26c9d21ec1837b210ee84b6c712f6815fd;
lane_sequencer SHA256 is60137df7264ccd09b2a9a1548d2e522c4785bd43c26a06a27024a0c8eb114da0.
The candidate03 scalar-move decode delta itself does not touch this operation.

1. `R/hardware/src/ara_dispatcher.sv:2134` decodes VMSEQ with use_vd_op=1,
   source EEWs=CSR SEW, old-vd EEW and output layout from eew_q[vd]. Thus this
   source-derived e16/m1 point requests EW16 old vd, not EW8. Same-base source
   overlap remains legal at5288; full source loads have already established the
   requested layouts, so the layout gate at5359 should require no conversion.
2. `lane/lane_sequencer.sv:968,1007` routes vector sources through ALU queues;
   their lane-local start is16/4=4 data elements. At1104, **MaskB start=0**,
   EEW64, length=ceil(32/(4*64))=1 word/lane. MaskM also begins at aggregate
   word0. `lane/operand_requester.sv:423` forms base+start>>(EW64-EEW).
3. The pinned deployed lane at
   `C/rvv_verification_handoff02/deployed_rtl/lane_sequencer.sv:1095` clears
   MaskB start only for mask-logical/carry operations, **not VMSEQ**. For the
   selected point its static formula yields start4 with EEW64: v8 base32+4=36,
   which is v9 word0 under4 lanes/VLEN1024. Candidate03 yields v8 word0/base32.
   This is a concrete absent-old-prefix mechanism, not measured cycle proof
   that it alone explains all nine errors or all19 original programs.
4. `masku/masku_operands.sv:104` deshuffles old vd with eew_vd_op;
   `masku/masku.sv:798,1008,1036` gates the packed update window to[start,VL),
   forces AND identity outside it, and merges with the correct old background.
   These prefix-merge protections already exist in the deployed masku too:
   do not credit a new alias repair merely from their presence. ALU comparison
   results, old-vd fetch origin, layout interpretation and accepted queue write
   remain separately observable contracts. Result descriptor allocation and
   writeback at1458 onward must preserve that ownership under backpressure.

After separate authorization, first run **only the genuine single**, unchanged
oracle, on candidate03. If a cycle probe is needed, capture target VID/op, stored
eew8/eew16, accepted MaskB command and granted VRF address/data on all lanes,
masku_operand_vd_seq, compressed result, active mask, accepted input slice,
result queue address/data/BE/grants and final readback. Correct old data followed
by wrong merge falsifies the read-origin explanation; correct merge followed by
wrong memory result directs attention to writeback/store layout instead.
Existing ARA_DEBUG_MASKCMP filters VMSGTU; ARA_DEBUG_MASKB filters registers v2/v24;
ARA_DEBUG_MASK_VSTART filters mask-logical ops. They do **not** prove this VMSEQ
v8 scene. Use a bounded UCLI signal capture with actual handshakes, not an empty
filtered log or forced internal state; no new RTL probe/build is proposed now.

The measured e16/m1 prefix failed at configuration66 (zero-based65), with the
same nine errors. Its archived source only stops **on failure**; a repaired DUT
would continue through4032 configurations. Do not launch that ELF as a bounded
66-call control. If predecessor history becomes necessary, separately authorize
an explicit first66-call source port preserving exact order/setup/oracle and label
the changed wrapper/loop boundary. A passing single would not accept that prefix,
all19 full parents, vd=v16 operations, the three stalls or original Linux ABI.
