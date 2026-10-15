# e32/m4 Software01 Artifact Finish: COST HOLD

This finishes the existing fixed candidate, not a second software variant.
No Host rerun, original ELF rebuild, SoC rebuild, Spike execution, or DUT run
was performed. No RTL or reviewed candidate source was changed.

## Actual outcomes

- Original `execution_receipt.json`: **rc1**, 33.048811s. Host finished and
  SoC compilation returned numeric0 before `KeyError: 'capacity'`: the archived
  ELF is stripped and its disassembly has a `.text` label, not helper symbols.
  This original failure and all its inputs remain unchanged.
- `host_result.json`: **46 actual runs**, comprising 30 complete5985
  original/candidate histories and 16 structural negatives. Expected negative
  exits are not mislabeled positive execution. All full-history original/new
  transcripts match, including the original byte fallback/error count.
- `soc/compile.log.exit.json`: **rc0**, 1.773165s, the only SoC build, using
  the original fixed flags. Host C results do not stand in for RV64 lowering.
- Independent finish command: `python3 -B finish_assets03.py`.
  `finish_execution03/exit.json`: **actual child rc0**, no timeout,
  **29.443394s**. `closed_audit03/RESULT.json` SHA256:
  `5c3eab6d42a69442002f8efb65c30e85347ca8d1d3eed52bc9fbf3e38f5b834e`.
  **260 pins** checked before and after; `INPUT_PINS.json` / `PINS.json` retained.
- Finish01 separately failed because the offline leaf analyzer did not yet
  model startup `gp`; finish02 had a generated Python quoting SyntaxError.
  Both numeric failure receipts and tools are retained. Finish03 fixes only
  the analyzer, deriving GP from actual `_start` AUIPC/ADDI and checking no
  other compiled GP writer. No unknown business register is defaulted to zero.

## Exact helper identity

All three identities are tied together, not just an arbitrary byte occurrence:

1. Pinned original `.S`, exact instruction text and source order:
   `capacity`, then `op_0` through `op_34`.
2. Pinned archived ELF, file-backed executable PT_LOAD bytes at
   **[0x10906,0x10f9e)**, not reliance on stripped symbol names.
3. Actual compiled ELF, file-backed executable bytes at
   **[0x80002268,0x80002900)**.

The capacity window has 3 instructions, each operation 13. All **36** windows
are individually unique in the original decoded text and consecutive in both
ELFs, in source order, without gaps. Total **458 instructions / 1688 bytes**,
SHA256 `d44dea9535d297c3c6dc1894db7086c82ca5fb1ec8c32a4f891450b7676c417e`.
Every decoded instruction used is checked against the underlying executable
file bytes. Extra RVV: **0**. Added candidate scalar CSR/fence: **0**; inherited
startup/exit instructions are not falsely claimed absent.

## Actual GCC cost, not a constructed schedule

The offline analyzer traverses only finite acyclic linked scalar leaf CFGs.
It is not Spike or a retired reference. Its positive cost assumes correct
oracle bytes; cache branches and addresses are independently restricted to
immutable IDs, so mismatches cannot skip actual output reads.

| Mandatory component | Actual compiled instruction count over full history |
| --- | ---: |
| Cache/compare leaf, all hit/miss paths | 2,014,890 |
| Output initialization, 71 x5985 | 424,935 |
| FP setup, (281+279+281) x630 | 529,830 |
| Mask setup, (167+98+56) x735 | 235,935 |
| Original operation helper bodies, 13 x5985 | 77,805 |
| **Disjoint mandatory subtotal** | **3,283,395** |

The full source ledger independently contains 5985 rows, 630 FP calls per
seed, and 735 mask groups per mode. This subtotal omits main/caller, RNG,
startup, capacity and remaining scalar control costs; all add nonnegative
work. It is therefore a sufficient **whole-program lower-bound rejection** of
3M, not an invented exact firmware total or a claim that the whole CFG upper
bound passed. No reference is authorized by this result.

The cache function has 392 static instructions, with seven optional
10-instruction refresh paths. Exact dynamic count:
`392*5985 - 10*33123 = 2014890`. GCC uses 65 SUB, 65 SNEZ and 64 OR per call,
plus seven ZEXT.B, rather than the cheap comparison branches of the earlier
constructive hypothesis. Its 48-byte frame saves/restores six callee-saved
GPRs: **35910 SD +35910 LD**, all included. Those are ABI saves/restores;
they are not mislabeled expected-cache spills. There is no stack write of
gold cache values in this leaf.

## Exact data and footprint evidence

- All **389025 actual LD**: 65 per call, offsets0..512, exact520B.
  All **124041 expected LD**, **53865 ID LHU**, **33123 adjacent hits** and
  **14757 full-block misses** match the pinned 9-ID ledger. Each call fills
  block0 afresh; changed IDs refresh eight words, identical IDs retain exact
  values; block8 reads only its final8B. No padded actual-output read.
- FP: eight immutable input words loaded each FP call, **483840 ordered SW**
  (a[i], b[i]), exact original bit patterns. No merged SD. Every seed path
  checked; the 640-word expected table is byte-identical in the ELF.
- Mask: **35280 clear SD** then **154350 cumulative SB**, exact selected
  address/value/order and zero upper112B. This candidate intentionally has
  no selected-mask LBU requirement. The actual SB obligations are preserved.
- Full Host data scope: **766080 results /11970 guards /5985 vstart**;
  original source has **no fflags oracle**. Freshness negatives include
  missing same-value FP writes, clears, selected stores, initialization,
  and fresh immutable FP input loads. Cache/tag/value/read omissions,
  first/middle/last and guard errors, dual errors, dirty mask, unaligned
  memcpy and PROT_NONE exact boundary checks are retained in Host receipts.
- ELF map: `.text=0x2af4`, `.rodata=0x3e89a`, `.bss=0x30c8`.
  BSS-to-stack-top gap **768872 bytes**, exceeding64KiB. Conservative sum
  of all decoded negative-SP adjustments is520B (includes startup's final
  SP adjustment); cache48B and arithmetic_main272B are included.
- `per_call_cache.json`, `cache_PC_visits.json`, `leaf_paths.json` retain
  actual PC/path counts and memory events. Source/model and dictionary
  bindings are retained in input pins. This is source-derived preparation,
  not Linux replay, DUT acceptance, or an executed full reference.

**Decision: HOLD >3M.** Preserve this one compiled candidate and prior errors.
Do not compile another variant or launch reference/DUT under this authorization.
Hilbert's independent finish-asset review is requested; no result is attributed
to him before his actual review arrives.
