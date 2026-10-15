# First Cause: Missing Reset GPR State In Strict Checker

**Confirmed checker false rejection at main's initial callee-save, not an
observed arithmetic mismatch. Old e8 ERROR/e32 CANCELLED/whole2 NOT_PASS remain.**

One diagnostic traversal stopped immediately at the unchanged checker's first
exception. Actual command exit0;0.388411s. Only1661 CSV data rows/179347 bytes
were consumed from the528198059-byte e8 CSV. No full CSV parse, second traversal,
e32 CSV access, patched-checker replay, DUT, build or RTL/helper edit occurred.

## Exact First Failure

| Field | Actual / Expected |
| --- | --- |
| CSV row / physical line |1661 /1662|
| cycle / retire order |2239 /1656|
| PC / instruction |0x80000c96 /0x0000e022|
| decoded |C.SDSP s0,0(sp), width8, base x2, source x8, offset0|
| expanded instruction |0x00813023 (`sd x8,0(x2)`)|
| known sp / expected address |0x800fffe0 /0x800fffe0|
| actual address |0x800fffe0|
| rmask / wmask / expected wmask |0 /0xff /0xff|
| actual wdata |0|
| checker-known rs2 / expected value |absent /unknown, NOT a measured mismatch|
| helper calls before failure |0|

checker.py:197 rejects because `desc['register'] in self.regs` is false.
The address/enable/read-mask clauses pass; value comparison is not reached.
first_failure.json preserves the original row, decoded descriptor, pre-row
register map, last writes, preceding16 retirements and individual predicates.
Its consumed-prefix SHA is
`91347d2c2b7fef869c8f44c819a604f6fb5db182da6bff37b94b960a19cb3479`.

## Static Source And Encoder Chain

- Actual e8 SoC disassembly `main`:0x80000c92 decrements sp by16,
  0x80000c94 saves ra at8(sp),0x80000c96 saves s0 at0(sp). The preceding ra save
  passes; the first s0 assignment occurs later. The original runtime main is
  ordinary compiled C, so this ABI prologue is legitimate.
- Frozen `compressed_decoder.sv:895` expands C.SDSP with rs2=bits6:2,
  base=x2 and immediate assembled from bits12:10/9:7. The reviewed Python
  decoder gives exactly the same x8/offset0/width8 for0xe022. No decoder error.
- `store_unit.sv:117` sets result_o=lsu_ctrl_i.data, not rotated memory data;
  `cva6.sv:818` routes it to STORE_WB. `cva6_rvfi.sv:294` records that value,
  lines345/348/349 export address/mask/data. `ara_commit_monitor.sv:253`
  prints these fields directly. This aligned8-byte store needs no lane shift.
- Frozen `cv64a6_imafdcv_sv39_config_pkg.sv:85` sets FpgaEn=0;
  `ara_soc.sv:534` configuration adaptation does not override it.
  `issue_read_operands.sv:881` therefore selects ariane_regfile implemented
  by `ariane_regfile_ff.sv`; lines62-64 reset all entries to zero.
  `ara_tb.sv:774` asserts reset before execution. The actual checked trace starts
  at original _start and has no x8 write before the failing save. Thus this M6
  reset-profile expected x8 is0, matching actual store0, while the checker starts
  with only `{0:0}` and incorrectly treats it as unavailable.

## Minimal Successor Direction, Not Implemented

Bind initial integer-register knowledge to the proven frozen-M6 reset profile
and complete from-reset trace, rather than learning it from the failing store.
Seeding the hardware-proven reset GPR zeros would retain the existing equality
check; it must not become an ISA-generic reset assumption. Do not skip arbitrary
unknown-register stores or relax setup/result/guard checks. Add the real main
prologue prefix to a small Host regression with incorrect-value/mask/address
negatives; existing synthetic positives bypassed this uninitialized callee-save.
No successor has been patched, tested or parsed here; main must review it first.

e8's durable simulator rc0/6279.050261s and firmware4095-call/65520-element
zero-error marker are preserved but are not independent fullCSV acceptance.
e32's durable cancellation remains incomplete. This first-error diagnosis does
not establish that there are no later checker or DUT errors.
