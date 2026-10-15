# Original e32/m1 Full5985 M9

One continuous source-derived original history, not Linux replay. Reuses the
accepted software02 ELF unchanged, no compile/reference/build. Source/reference
identity is pinned through the complete reference entry and terminal review.

SEW32 CAP32 physical1/128B, vtype16, 35 ops/5985 calls/3 seeds. Full191520
uint32 results,11970 uint32 guards,5985 vstart,77805 helper instructions.
Output is136B with17 whole SD/LD, including two0x0000005b guards. There is no
short tail. Exact original640 FP table entries and fallback remain unchanged;
the original program has no fflags oracle.

Every1890 FP call has64 fresh SW, even equal-old-value writes. Lifecycle binds
actual SoC sites, independently listed rather than a Spike address offset:
original seed writes276, mask16zeroSD then selected-bit SB for2205 groups,
35280clearSD/38955bitSB. Complete prior oracle precedes next initialization.
Actual memory address/BE/source GPR/data and full output footprint are checked.
128B software mask is initialized; actual vlm reads4B.

Image-proven GPR reset, five actual startup CSRs, exact BSS and ABI prologue,
capacity and all13 helper PCs are checked. The full unchanged CSV goes to the
mature generic protocol and strict scalar/oracle/owner observers. All actual
tokens pair; missing whole alloc/done pairs for necessary helpers/targets fail.
Model-derived minimum:29925 memory-helper owners+3762 targets=33687; includes
117op24 and1170FP targets. Only18 actual vslideup.vi offset2 nonempty VL<=2
targets may omit ownership, not any existing token or helper owner.

Numeric-first runner, fail veto, late-abort veto, no retry; private ELF, source,
configuration/image pins before and after. Budget10800/case,12000/worker,
13200/service, jobs1. Fresh live capacity24/MemAvailable32GiB/reserved0.
ExecStopPost records real systemd exit and runs one bounded metadata collector;
the collector does not semantically reparse the CSV.

New Host uses a constructed full5985 scalar/protocol stream, not an ISA
emulator or captured DUT evidence. It tests fresh initialization omissions,
FP old-equal refresh deletion, ordered mask omissions, every-byte output/guard
corruption, whole last word, ABI, memory and nonempty-target owner deletion,
VI2 exact exception, wrong tokens, exit/console/abort/numeric outcomes.

Prepare: python3 -B replay.py prepare --image
/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image
--out <this-directory>/prepared01 --reserved-slots0 --authorize-prepare
(CLI spelling: --reserved-slots 0).
Dryrun uses the exact resulting plan SHA. Only after independent exact entry
NO_BLOCKER may launch_once.py --out prepared01 --entry <review.json>
--entry-sha256 <digest> submit the service and take its two startup samples.
