# Software02: Actual Linked CFG Below 3M, Pending Independent Review

Only the approved sticky comparator header changed. Its SHA256 remains
`b105cea283ce1f1a65a3cff4b37c9913e8ed24c797de54fa1c0717a41c95b3ac`.
All other candidate C/FP/mask/gold inputs are unchanged. Original software01
COST HOLD and all its failed preparation/finish receipts remain intact.
No Spike execution, VCS, RTL modification, alternative flags or second
candidate was used. Building the `spike` ELF is not running a reference.

## Actual outcomes

- `python3 -B execute.py`: **actual rc0 /35.356501s**, no timeout.
- Original full46 Host suite: 30 complete5985 original/new transcripts plus
  16 structural negatives, all expected numeric outcomes and exact positive
  or error transcripts checked. Old Host results were not silently inherited:
  the new Host macro expands with redundant parentheses, so raw preprocessed
  token identity is not claimed. `host_inheritance.json` and both `.i` files
  preserve that distinction. Fixed UBSan flags were retained.
- One additional short Host executable: **rc0**, six cases (equal,
  first/middle/last mismatch, two distinct double-error cases), unaligned exact
  520B backing with guards, all65 reads in order after every error. This tests
  the Host C branch, not RISC-V inline asm.
- Unique SoC compile: **rc0 /1.773091s**. ELF SHA256
  `6adde60cb19b74d8aa1e1c44a2219042d2a482da18e824772ba2cdf47bd940bf`.
- Unique Spike-backend compile: **rc0 /1.723690s**. ELF SHA256
  `a91b41df8ad8156243f0e79d998a0ec9783f2bc2113dfe6016404988abb9970f`.
  Same original flags; only the established `SPIKE_REFERENCE=1` backend
  define and output/runtime paths differ from the SoC command.
- `python3 -B audit_execute.py`: **actual rc0 /63.385392s**, no timeout.
  `artifact01/RESULT.json` SHA256
  `301e510e370c4c029f21195bd8b07593e020ecd82a93771346185011fea58a0a`.
  **489 input pins** verified pre/post; all scripts and closed artifacts bound.

## Linked code and memory proof

Both ELFs retain the original458 helper instructions /1688B, source-order
capacity3 plus35x13 windows. Their exact bytes match the sealed software01
original-ELF/source proof, whose pins are verified transitively. Every new
decoded instruction is checked against its file-backed executable segment.
No extra RVV or new candidate scalar CSR/fence. Startup and existing runtime
CSR/fence instructions are not falsely claimed absent.

GP is derived from each actual `_start` AUIPC/ADDI and matched to its linked
symbol; no other GP writer is permitted. Exact pool, IDs, original640 FP
patterns and eight FP inputs are checked at their linked symbols. BSS clear
register setup, loop, bounds and stride are proved from actual instructions,
not an unexplained assumption that unknown GPRs start at zero.

For every one of5985 source rows, the finite cache CFG confirms:

- **389025 actual LD**,65 each at offsets0..512, exact520B. The final8B
  contains result127 and the rear32-bit guard; no rounded output access.
- **124041 expected LD /53865 ID LHU /33123 adjacent hits /14757 misses**.
  First fill is unconditional each call; changed IDs refill eight words;
  identical IDs preserve exact cache values; final ID reads one word only.
- **483840 ordered FP SW**,256 per1890 FP calls, and eight fresh immutable
  input LW each call. Actual three seed permutations verified; no merged SD.
- **35280 mask zero SD then154350 cumulative SB**, exact address/value/order,
  preserving128B zeroing and upper112B zero. No obsolete mask LBU requirement.
- **389025 output initialization SD**, both32-bit halves91, no tail shortcut.

Each of65 comparator sites is an encoded RV64 BEQ with displacement6,
followed by exact compressed `C.LI a0,1` (0x4505). The BEQ skips only that LI.
Both source registers differ from a0; cache values/tag cannot be clobbered by
the sticky write. The only initial reset is `li a0,0`; the final
`sext.w a0,a0` preserves canonical0/1, so upper32-bit operand differences
still compare using the full64-bit BEQ. All four local cases are recorded:
incoming bad0/1 crossed with equal/unequal; equality retains bad and inequality
sets1. The implementation does not use `=r`, an undeclared scratch register,
fence, CSR, or mismatch-dependent branch around later reads.

Seven additional linked-CFG negative paths per backend mutate first, middle,
last, double/triple and opposite32-bit halves in a row containing both cache
hits and misses. They verify the incoming sticky bit at each comparator,
unchanged ID/cache decisions, return1, and all65 actual reads. These are
closed instruction/dataflow proofs, not execution on Spike or a DUT.

The new GCC comparator uses **no stack frame and no stack transfers**.
This is measured linked-code evidence, not a pre-credited optimization.
All other actual frames are included: arithmetic_main272B, number48B,
failure80B, inherited runtime frames and startup SP adjustment. Linked stack
gaps are **769192B SoC /760800B Spike**, both greater than64KiB; the conservative
sum of all negative-SP adjustments also remains below64KiB.

## Full positive CFG bound

The main CFG is traversed with explicit success summaries for vector/helper
results; it does not execute or validate vector instructions. It reconstructs
all5985 actual indirect helper targets and seven arguments from linked scalar
code, validates full original tuple order, mask2205 groups, per-call1890 FP
refreshes and one init/comparator per target. Actual RNG writes for all three
seeds match the source ledger. Scalar endpoints are checks5985,
elements766080,errors0 under the stated success hypothesis.

All caller instructions and stack traffic are counted. Every scalar leaf is
separately analyzed with full hit/miss costs. Actual formatter, runtime write,
startup BSS and exit code use conservative bounded weights, not omissions.
Decimal conversion/strlen loops are bounded by the actual uint64 digit count;
runtime write costs include every static PC per possible character iteration.
Startup counts every startup PC per BSS iteration (deliberately conservative).
Exit counts through the completion endpoint, not an infinite post-exit park.

| Component | SoC | Spike backend |
| --- | ---: | ---: |
| Capacity helper | 3 | 3 |
| Mask leaf | 235935 | 231525 |
| Output init leaf | 424935 | 424935 |
| Original helper bodies | 77805 | 77805 |
| Cache/compare leaf | 1123125 | 1123125 |
| FP setup leaf | 529830 | 529830 |
| Main, every caller instruction | 372492 | 360520 |
| Direct runtime write upper | 2744 | 4704 |
| Formatter + nested write upper | 2031 | 2451 |
| Startup upper | 35926 | 59501 |
| Main trampoline + exit | 6 | 8 |
| **Whole positive upper** | **2804832** | **2814407** |

Margins to3M: **195168 /185593**. The cache positive path count is
`(308-65)*5985 -33123*10 =1123125`: all65 successful BEQs skip their LI, and
each cache hit skips precisely one10-instruction refill. Old65SUB/65SNEZ/
64OR/7ZEXT.B and six ABI save/restore pairs are not present in the new leaf.
Caller/main and backend differences are independently recomputed rather than
subtracted from the old partial count.

This bound applies to a successful full source history, not an arbitrary
failure-printing run. The original fallback remains byte-identical, and
failure behavior has its own Host/linked checks. The original source has
data/guards/vstart oracles, **not an fflags oracle**. Static CFG is not a
retired-cost measurement or source/Linux/DUT acceptance.

Detailed per-PC counts,5985 actual call arguments, cache counts, truth tables,
negative paths, leaf memory events and frames are in `artifact01/soc.json`
and `artifact01/spike.json`; durable command/child receipts are in
`execution_*` and `audit_execution01/`. Submitted to Hilbert for independent
artifact review. No reference/DUT admission is claimed at this stage.
