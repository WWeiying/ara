# Full17920 Unboxed Parent: M9 Prepare Only

Prepared `prepared01/plan.json`:
`54f4fbbac1603f1742cbb6d6ad090aee20a9609f9d2efed2dc1c29dd85b0bbdd`.
746 input pins. Actual dryrun exited0 and produced no simulator/CSV/console output.
No DUT, reference, compilation or RTL build was launched in this preparation.

Host02: 28 tests, all passed, actual child0 in5.178458s. This is synthetic Host
coverage, not full dynamic reference or DUT evidence. It includes actual SoC
instruction windows for all10 operations at seeds0/1/16/31, all32 FPR payloads,
missing/wrong FMV/rd/t2/raw0/boxing/highbits, guard/active/VL0/tail/flags/vstart,
fresh mask/input/output-tail omissions, ABI opaque spills, owner-pair deletion,
partial EOF, command drift and numeric-outcome persistence. Host01 remains failed:
its one incorrect assertion counted182 op instructions as185; capacity3 completes
the185 static total. No checker or oracle was relaxed to fix that assertion.

## Source And Scope

Historical program: `rvv_fp_compare_unboxed_unmasked_e16_mf4`.
Runtime id: `fp_compare_unboxed_e16_mf4_full17920`.
Exact SoC ELF: `../fp_compare_unboxed_full17920_prepare01/compile01/run02/soc/program.elf`,
SHA `19afd0c6fd9c0810efbfdd9a635d092672554e6a1f3d4a3a537af00c4de13e37`.
Its own code/symbols/linked lowering derive every checker PC; no Spike relocation
or alias-m8 old destination/geometry is substituted.

Full contiguous32seed/10op/7VL/4mode/2sticky history:17920 calls,
286720 original result-bit checks,35840 guards,17920 flags and17920 returned
vstarts. Preserve each call's128mask bytes,64input bytes,130output bytes:
41 fresh stores,8 actual inputLD and one outputLWU. All2240 hoisted recordLDs
and326144 dynamic op helper instructions plus capacity3 are required.
DK0 old5b5b and original allowed tail sets remain unchanged. The source does
not postcheck output bytes4..129; the checker checks their full fresh stores,
without claiming an original post-result oracle on those bytes.

Reference acceptance is the independent
`../fp_compare_unboxed_full17920_source_review01/REFERENCE_TERMINAL01_REVIEW.json`
SHA `50a0025d6c03a2df9e4396631b8431b8a36535d45962cc3ac7c837228b9c13c9`.
Its actual2653044 firmware instructions and sole closed raw result are bound.
No reference semantic pass was repeated here.

## Architectural Evidence

The new strict adapter consumes actual scalar RVFI address/BE/data and checks
ELF control flow, source stores/loads, caller ABI, complete contiguous helper,
original flags/status, actual LWU result/guards and SoC CTRL0. It does not invent
Spike vector register effects or a nonexistent SoC `replay_log`/HTIF symbol.
Initial unknown callee-saved values are only opaque at exact first prologue
spill PCs; their actual stored bytes are retained and every later load compared.

One lossless closed CSV pass delivers every original row to both the mature
six-event observer and source checker. All actual CVX/architecture/uop
transactions must reconcile. Source instruction classification derives89600
mandatory memory owners and15360 nonempty comparison owners;2560 VL0 targets
may elide backend execution. Capacity-stage memory remains mandatory at VL0.
There is no all-mask-off exemption for an unmasked nonempty comparison.

`FPR_OBSERVABILITY01.json` from Aquinas and its14 frozen M9 source files are
pinned. Each actual `f2038053` helper retirement must have trap0,rd0 and full64
`rd_wdata == zeroextended original b[0]`, independently of LHU/t2 provenance.
Required total10752 committed FPR writes,336 per seed. Nonzero seed becoming0
or well-boxed is rejected even if the comparison result remains qNaN-equivalent.
This is **FPR committed writeback evidence**, not physical FPR readback or an
independent accelerator-operand snapshot. The row never updates GPR x0.

## Budget And Launch Gate

Fixed jobs1; simulator10800s, worker12000s, service13200s; cap24 concurrent
simulators and32GiB available memory at actual admission. No retry, FSDB, build
or automatic extension. A scalar instruction-rate estimate from older runs is
not a runtime guarantee for17920 FP comparisons; the3h simulator bound is fixed.
Timeout is NOT a demonstrated hardware stall without additional evidence.

Actual prepare/dryrun commands (already completed; do not repeat into this dir):

```sh
python3 -B replay.py prepare --out prepared01
python3 -B replay.py dryrun --out prepared01 --plan-sha256 54f4fbbac1603f1742cbb6d6ad090aee20a9609f9d2efed2dc1c29dd85b0bbdd
```

`prepared01/ready.json` contains the future service argv. Launch is disabled
until an actual independent `ENTRY_REVIEW.json` and separate new parent run
authorization are supplied with exact hashes. Preparation is not launch consent.
The entry schema is enforced by `replay.approval_gate`; parent approval must be
`AUTHORIZE_FULL17920_M9_ONCE`, bound to this plan, independent entry, exact unit,
jobs1 and budgets `[10800,12000,13200]`.

The mature runtime uses private ELF copies and runtime id for `+TESTCASE` while
retaining the historical source name separately. The numeric monitor outcome
is durably written before any postchecker; checker failures cannot erase it.
Abort remains latched through final publication, and the disk plan/pins are
freshly rechecked. `ExecStopPost` records actual systemd exit environment, not
GC-derived default success. Full source-port PASS would still not be Linux PASS.
