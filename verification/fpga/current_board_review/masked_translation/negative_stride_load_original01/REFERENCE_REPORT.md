# Negative Stride Load: Source And Reference

Status: **own Host/Spike checker passed; independent terminal/source-adapter
review pending. No DUT, RTL/image build, Linux execution or parent96 acceptance.**
Exactly one reference invocation; no retry, no changed limit or ELF.

## Identity

Archive `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_negative_stride_handoff01`.
Single `singles/rvv_small_fault_strided_negative_stride_e16_m1_u1_s0_b3_m2_f0_g3`.

| Input | SHA256 |
| --- | --- |
| Original diagnostic ELF | 4c10f89aeb0d400412b15115b48ad3f11d9296fc881fb2645e573a5807d0e907 |
| Original C | 90996937a77228ac31baf0323079d97e8c5004fad163e80a950ac670b82eb563 |
| Original assembly | 597a58a41e73941a90e3ccc015676dca606d9f6f74436b2965dede15bfab3039 |
| New SoC ELF | 04e25a1fa3b6ba094af6d60d50f8ec0dd60f2ec2503f47dda05fd2011c5a0a43 |
| New Spike ELF | 19ec8c12d4b4f4a0974319a550bea7348d4dd890babcf1fe65afb90945abd60b |

`software01/source_proof.json` retains actual case.json and all helper PCs and
encodings. Capacity3 instructions and both10-instruction helpers match the
actual stripped archived ELF byte-for-byte. The whole new ELF is a Sv39
derivative, **not** byte-identical to the original Linux program. The unused
store helper remains linked but its entire PC range is rejected if executed.
No invented predecessor, RNG, source instruction or warm-up was added.

Historical single evidence: exit1, one signal/handler error, actualvstart3
versus5 and fault address16 bytes above the expected address. No separate
returned-data error was established by that historical log. Static source
review is bound to `gather_original_review/negative_stride_load_source_review01.md`
SHA4da9e161979573d7e23b1d92d904cfff4b1d0cfcfa08dc725b2e5ed594087353.
That review is source-selection evidence, not independent acceptance of this run.

## Actual Reference

`reference01/execution.json` persists numeric child returncode0 before parsing;
`wrapper_wait.json` records observed wrapper wait exit0, not absence-of-PID
inference. Actual command uses `rv64gcv_zfh_zvfh_zvl1024b --priv=msu
--pmpregions=0 -m2 --instructions=1500000 -l --log-commits`.

- Hard limits unchanged: 1500000 instructions,120 seconds,256MiB raw.
- Measured child time15.25614191s, raw101219616 bytes, timeoutfalse.
- Full observer:836976 commit-format records,836971 firmware records;
  17274 scalar comparisons; one capacity call and one original load-helper entry.
- Host:17152 independent C/Python rows;30 negative controls, including original
  wrong tval/start, prefix/reload/poison, fullmemory, inactive/tail, both original
  guards, missing bytes, wrong base/stride, same-PC and actual MRET context.
- Raw SHA2616cfd2f69f2b3775302b213f09b751c0dad1df3e0d6179293b40622f97af9d.
- Initial/fault/repaired/final checkpoints at firmware records159992/264016/
  546894/826702 check23236/23228/23228/23220 exact bytes respectively, plus
  separately masked real trap mstatus words. These include all8KiB data,
  complete page tables/neighbors, input, offsets, mask, snapshots and outputs.
- HTIF actual value1 (software exit0), completion magic, zero errors/unexpected
  traps and CSR restoration all verified. Input pins checked before and after.

Raw first fault at trace lines324213..324216:
PC0x80000e28, instruction09c55c07, partial load onlyVA0x40001006 (P+6),
vstart5, load-page-fault tval0x40000fee (P-18). The actual retry MRET record
546933 has mepc0x80000e28, mstatus0x8000000a00002e00 (MPP=S), VL8/vtype8/start5,
a0=0x40001016 (P+22), t3=fffffffffffffff8. Its restored other arguments point
to original input/output+1/mask/cap64/stride storage, not an adjusted base.
The retry target at546934 reads only0x40000fee. No helper reload occurred.

Final vector element2=0x287a and element5=0x26be; memory[P+6]=0x2821 after
lower-page2048-halfword refill and single-prefix poison. All other62 results
remain0x005b. Original guards are output[0]/output[65], not output[129].
All16 mask bytes and128 offsets are preserved; physical input128 has only
first64 source-initialized. Completion ecall is distinct from the one load fault.

## Accounting And Admission Limits

The existing result key `helper_retirements=11` means **Spike commit-format
records**, including the faulting partial target plus its successful retry.
There are ten original helper instructions, one entry, and two target attempts.
A future RVFI checker must not require11 architecturally retired helper
instructions. This accounting is not a hardware retirement measurement.

The original handler checks saved v24 elements0..4; this adapter additionally
checks the full saved snapshot and neighboring registers, extra output storage
66..129, page-table neighbors and four checkpoints. These are labelled
strengthened adapter safeguards, not original historical oracle counts. A
future DUT disagreement limited to such extra fault-snapshot data requires
separate architectural review, not automatic attribution of the old bug.

Linux mmap/sigaction/signal-frame parsing is replaced by actual Sv39 leaf
invalidation and M-mode trap/repair. The numeric geometry, source initialization,
original helper bytes, prefix poisoning and final64+2/full8KiB oracle are
retained. This does not establish Linux SIGSEGV/signal-frame equivalence or
full96-parent/history acceptance. No current unfixed RTL cause is demonstrated.

Only observer/executor finalization followed software compilation, before the
reference; the exact old/new hashes are retained in
`reference01/pre_reference_checker_delta.json`. No compiled source or ELF
changed. Final checker, compressed-memory decoder, runtime/compiler, original
source and all software artifacts are bound in `reference01/input_pins.json`.

## Cost And Next Step

The static upper estimate1100000 instructions fit the original resource gate;
actual836971 is lower. Prior M6 NF2pilot4 measured1307708 instructions in
1759.4446s (~743/s). Scaling the current count gives about18.8min, or22.5min
with20% margin. A deliberately slow273/s proxy with20% margin gives61.3min.
Neither is a promise: fixture checks and traffic differ. No DUT timeout or
launch has been authorized here. Hand the frozen software/reference to main
and the independent reviewer before any VCS adapter/admission decision.
