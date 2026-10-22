# Full Small2 Memory Contract Review01

Independent static review, 2026-10-12. No actual CSV/reference raw was opened;
no tests, compilation, reference, DUT or RTL/shared-checker edits occurred.
Hilbert owns the sole first-error diagnostic. His REPORT.md supplies the
actual row facts below; they were not independently reread from CSV here.

## Confirmed Cause

The first rejection is a missing initial GPR-state model, not shifted store
data, a compressed decoder error, or an observed arithmetic mismatch.

Frozen e8 SoC disassembly:

```text
80000c92: 1141  addi sp,sp,-16
80000c94: e406  sd ra,8(sp)
80000c96: e022  sd s0,0(sp)
```

Startup writes gp/sp/t0/t1 and ra but never x8 before this main prologue.
checker.py:94 initializes only `{0:0}`. Its line195 requires source-register
membership before its line196 value comparison. Thus this legitimate C.SDSP
necessarily encounters absent x8 in the tracker, independently of store data.

Hilbert's actual diagnostic confirms row1661/physical line1662, cycle2239,
retire order1656, PC80000c96/insne022. It decodes x8 to0(x2), width8; known sp
and actual address both800fffe0; rmask0/wmaskff; wdata0; source x8 absent;
zero original helper calls. Address/mask clauses pass; value equality is not
reached. The preceding ra save passes. Do not describe unknown expected x8
as an observed register-value mismatch.

The old e8 ERROR/e32 CANCELLED/whole2 NOT_PASS must remain unchanged. Parent
reports durable simulator rc0/6279s and firmware4095-call PASS, but these are
not independent full-CSV acceptance or proof that no later error exists.

## M6 Store Data Contract

The frozen paths establish **shifted byte enables, unshifted RVFI store data**:

1. load_store_unit.sv:851 places fu_data_i.operand_b into lsu_ctrl data;
   line693 uses be_gen(vaddr[2:0],size). ariane_pkg.sv:710..750 emits the
   address-lane mask, e.g. aligned SW at offset4 givesf0, SB at offset3 gives08.
2. store_unit.sv:117 exposes result_o=lsu_ctrl_i.data. Its separate
   data_align/st_data_n path at89..114/250..255 rotates data for the cache.
   Cache lane-aligned data is not the RVFI STORE_WB value.
3. load_store_unit.sv:610 uses NrStorePipeRegs; the frozen configuration has0.
   cva6.sv:818 maps store_result to wbdata[STORE_WB].
4. cva6_rvfi.sv:177..180 selects LSU address/masks; line294 stores STORE_WB
   data by the LSU transaction id. Lines345/348/349 export address/mask/data.
   ara_commit_monitor.sv:253..264 prints those fields without shifting them.

For a naturally aligned scalar store of size N at address A:

```text
wmask = ((1 << N) - 1) << (A % 8)
rmask = 0
mem_wdata & ((1 << (8*N)) - 1) = GPR[rs2] & ((1 << (8*N)) - 1)
byte_memory[A+j] = (mem_wdata >> (8*j)) & 255
```

The current checker's store comparison and memory reconstruction use this
contract correctly. Do not extract wdata by enabled lane position. For the
actual first fault N=8/A%8=0/data0, shifting would be numerically identical
anyway, and cannot repair the missing-register predicate. The established
NF2/extended8 and indexed-overlap checkers also use this unshifted contract;
their comments alone are not the proof, the frozen RTL chain above is.

If a later store has correct address/mask and a known rs2 but wrong data,
separate source-register tracking from RVFI transaction/value attribution.
Do not learn rs2 from that same store or silently try both data layouts. A
different image's pipeline/layout must be proved rather than inherited from
this frozen M6 profile. No RVFI transaction-attribution defect is demonstrated
by this first failure.

## Decoder And Register Tracking Alternatives

`memory_op` correctly derives scalar store rs2, sign-extended S-immediate and
size from SB/SH/SW/SD, and delegates integer compressed operations. The local
RV64C decoder's C0 LW/SW/LD/SD and C2 LWSP/SWSP/LDSP/SDSP fields agree with
frozen compressed_decoder.sv wiring: C.SDSP rs2=bits6:2, base=x2,
offset=bits12:10 mapped to5:3 plus bits9:7 mapped to8:6. Thus e022 expands
to00813023 (`sd x8,0(x2)`), not another register, offset or width.

The register update at checker.py:226 excludes all scalar FP major opcodes,
which is not a general integer-destination classifier (some FMV/FCVT operations
write GPRs). However neither sealed e8 nor e32 SoC code map contains such scalar
FP arithmetic opcodes; this is not the cause here and does not justify a broad
unrelated checker refactor. Vector helper FPU operations remain distinct.

Existing Host positives avoid the actual defect: test_host.py's synthetic
write() assigns a source register before every store, so initial callee-save
values are always made known artificially. A real compiled main prologue
regression is the relevant missing test, not a shifted-data workaround.

## Reset Profile Proof And Successor Boundary

M6 configuration cv64a6_imafdcv_sv39_config_pkg.sv:85 sets FpgaEn=0.
ara_soc.sv:534..562 adapts configuration without overriding this field;
build_config propagates it. issue_read_operands.sv:881 selects ariane_regfile,
implemented by the frozen filelisted ariane_regfile_ff.sv. Its lines62..64
reset all GPR entries to zero. ara_tb.sv:774..785 asserts reset before clocks
and execution; ara_soc.sv:628 boots from DRAMBase. The strict checker requires
original _start at retire order0 and continuous subsequent retirement order.

This supports a **specific fresh-M6 from-reset GPR profile**, not an ISA reset
guarantee, Linux entry convention, warm-resume state or arbitrary FPGA regfile.
Seeding all32 modeled integers from the proven zero profile preserves store
value equality and source-data checks. Guessing unknown values, accepting
arbitrary untracked stores, or using wdata to initialize their source does not.

The new full_small2_reset_gpr_recovery01/reset_profile.json was read and its10
RTL pins independently hashed. Actual M6 image.json hash, snapshot/configuration/
compiled-manifest identities and original plan SHA all match. Profile SHA:
`308784d27eaf81e2a608cd7cd37a9ac61a22a58ce9eda994715cec58dcd682a4`.
It explicitly allows only e8 and records all32 zero values with the full-start
trace premise. Its proof is sound as scoped; it does not authorize e32 recovery.

At the latest inspection only reset_profile.json existed in that successor
directory. New checker/Host results therefore remain **NOT YET REVIEWED**.
Final static review must establish the profile is actually fail-closed bound
to the same M6/plan/e8/full-start trace and that the only semantic change is
initial GPR knowledge. The original4095 ordered calls,16 results+2guards each,
all setup bytes/RNG/FP transitions, original13 helper sequence, vstart0,
capacity16/vlenb128, final counters/CTRL0/park and all error vetoes must remain.
Read real prologue Host evidence with wrong data/mask/address rejection; do not
rerun it here. No full offline traversal is approved by this static note.

## Evidence Identity

- Original checker: `18c9b86ab1a13b05d0f69823299d761a1f54a8d7c20c8b1ca30afd867ec8bf0f`.
- RV64C decoder: `dc68adbfd0b3614f2c81691b4a15210612c813271cc96922ef0145e7f8b61a88`.
- Original Host source: `21e96227ae5fc1e877c9c33650a7e4fc0ef009ade045109d78891eb7c80cd7d2`.
- Hilbert REPORT.md: `232f887d13df1149cd2c0c37b8b4a44352105aca1452ea591d84c09e2390993c`.
- Original plan: `7ec58e3f38f5877838c7edf898d4b85d4872437dcdc54e7542357e8f2736f9ee`.
- M6 image.json: `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
- M6 snapshot: `3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438`.
- M6 configuration: `6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785`.

Relevant live RTL was byte-compared to frozen M6: monitor, RVFI, store/LSU,
compressed decoder, FF regfile, operand issue, configuration and ara_soc all
match. Frozen individual hashes are also bound in the reviewed reset profile.
This concludes the memory-contract/root-cause static review, not a PASS gate
for any full program data or a repair of the preserved terminal metadata.
