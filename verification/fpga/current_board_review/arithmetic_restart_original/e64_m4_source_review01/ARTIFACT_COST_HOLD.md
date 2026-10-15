# e64/m4 Actual Artifact and CFG Review

Verdict: software01 artifacts are consistent with the accepted source contract,
but **COST_HOLD: no reference or DUT admission**. This reviews the one existing
compiled candidate, not a new optimization or measured firmware execution.

## Actual Evidence

- Host/compiler wrapper: PID3349637, actual numeric rc0,31.998270575422794s,
  timed_out=false. All41 Host outcomes match their intended return codes and
  log hashes:26 full-history runs,2 deliberate UB traps,13 setup negatives.
  Thirteen original/packed full-history transcript pairs independently match
  byte for byte. These are Host emulations, not actual RVV execution.
- Rehashed223 software pins and50 source-entry pins: no mismatch. Inspected
  read-only compiled-audit receipt records actual wait0/0.881680687s; that is
  tool execution time, not firmware runtime. No compiler or suite was rerun.
- Both backend disassemblies independently match the ELF file-backed bytes.
  All458 helper instructions match unique contiguous windows in the stripped
  archived original ELF disassembly; no extra RVV. An initial metadata reader
  assumed named original functions and stopped with KeyError('capacity');
  the original is stripped. Corrected read-only comparison used unique opcode
  windows, not invented labels. No producer artifact was changed.
- Linked dictionary127104B, IDs107730B, FP gold5120B and inputs64B independently
  match the already source-reviewed binaries. Original scalar fallback text
  is unchanged. Full5985/35ops/383040 results/11970 guards/history remains.

## Actual Lowering

Output initialization already consists of66 SD at offsets0..520 plus typed
LI91. The comparator reads all66 actual and66 expected u64 words: eight
64-byte blocks and a final16-byte pair. Actual offsets512/520 are result63
and rear guard. Expected ninth-block offsets0/8 do not read padding.
The linked XORs compare matching words and OR accumulation retains all66
differences through the final mismatch branch. Equal differences cannot
cancel. It reads every word before branching to original fallback.

Each of1890 FP calls still performs eight table LDs and128 alternating
a[i]/b[i] SDs, selecting slots (i+seed)%8 and (3*i+seed)%8. All restart
paths return to the op>24 gate, including VL0 and repeated equal values;
241920 stores remain, not seed-only initialization. The independent source
oracle uses original table bits and has no explicit fflags oracle.

Each mask group performs16 zero SDs before selected cumulative LBU/ORI/SB.
Modes retain64/32/9 ascending updates, including repeated writes to the same
byte:35280 clear SDs and77175 SBs. No final-mask copy substituted for them.
Static recorded paths were checked against actual instruction adjacency,
branch destinations and store counts; finite-path inspector logic was read,
not rerun. Main frame320B; static-frame sum552B. BSS-to-stack gaps are
764632B Spike and773152B SoC, comfortably beyond the64KiB reserve.

## Cost Decision

Independently counted Spike linked regions:

| Mandatory part | Whole original program |
| --- | ---: |
| LI +66 SD output fill | 400995 |
| Helper call setup/return test | 83790 |
| Original13 helper instructions | 77805 |
| Comparator366 instructions/call | 2190510 |
| Counters/end decision | 71820 |
| FP paths143/142/143 instructions | 269640 |
| Mask paths280/155/63 instructions | 366030 |
| Mandatory subtotal | **3460590** |

Core before FP/mask is472*5985=2824920. Thus even the deliberately incomplete
core+FP-stores-only lower bound3066840 exceeds3M. This is decisive without
depending on conservatism of remaining control/runtime terms.

The reported union-counted outer-control/RNG/prologue/capacity terms,
16493 BSS instructions and20000 finite successful-runtime allowance sum to
the complete conservative upper **3630058**, not measured retirement.
Instruction PCs/multiplicities and arithmetic were independently reconciled.
Failure fallback and post-completion parking are outside this successful-path
bound. Do not present the earlier3066840 partial lower as the total cost.

SoC is not instruction-count-identical: its core is474/call and mask paths
284/159/67, giving mandatory3481380. This reinforces the HOLD and must not
be mislabeled as Spike measured firmware or projected DUT wall time.

The previously proposed loop-only expansion/hoist identifies at most61
removed current instructions/call, conditional on no replacement work or
spills. Its365085 hypothetical savings leave mandatory3095505 and upper
3264973. No actual GCC savings or new compile is established. The parent's
new sticky-mismatch direction needs a separate source review and full bound;
it is not approved by this baseline report.

Historical e64/m4 board PASS remains distinct from current-image regression:
there is no current full5985 reference or DUT acceptance here.

## Bound Identities

- Compiled RESULT.json:
  c55f35e5dbf1e5f16d06c16ab65137d138b061c28db6ff353e25851900229c83
- SoC ELF:
  81d32bc48391b57c5dd0ea53d8ca10dd85040a6fd1ff89d092bb4f3cbad752dd
- Spike ELF:
  3c37c694c180fada587e034c2a513f6c0ed146fd2af658086d73d13c5e015f6c
- software01/proof.json:
  e1a81989b65c159ebfc1467e93606401894451471c897bc99855c9871a3ce1f8
- software01/execution_receipt.json:
  d37126f8dfe37c1f13342be77a667d29ca245a161e26e8f447d0013ff11130fc
- compiled_audit01/execution_receipt.json:
  1a097b960ecafd44ed6a5eecfa81ce7f0a872fbe8d113ac50718adbca19b5eee
- Existing unroll-only static proposal:
  060fe4e74d26c6fca341683e4be14d6f095da99d27c68e5aea26033833af63df
