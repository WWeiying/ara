# Full10752 Linked Artifact and Cost: HOLD

The complete successful-path linked instruction count exceeds the fixed 3M
reference gate. No reference, DUT, alternative flags, or target recompilation
was run. These are conditional scalar CFG counts, NOT measured Spike retirement
or hardware results. Numerical source equivalence remains the separately
accepted original-C Host composite.

## Actual Receipts

- SoC compile: numeric0, 1.720010s; Spike compile: numeric0, 1.769570s.
- First offline auditor: numeric1, 2.020577s, no timeout. It incorrectly checked
  the temporary startup `auipc sp` result against the final stack top. No case
  was entered. `cfg_receipt01/` and `linked_cfg01/FIRST_FAILURE.json` are retained.
- Independent successor: numeric0, 152.667892s, 600s hard limit, no timeout.
  `cfg_receipt02/wait.json` SHA256:
  `8b3f99558edc5f8157cddd8c5f66796037d4fc88f0ef94a2a6ee39fc64b5159c`.
- The successor changes only the actual contiguous startup AUIPC/ADDI SP pair
  handling. Both instructions remain counted. Its final address must equal
  `__stack_top`; all subsequent stack bounds remain strict. The original
  auditor, linked binaries, generator, source and tables are unchanged.
- All 165 input pins match before/after the complete analysis.

## Full Positive Cost

| Charged linked instructions | Spike backend | SoC backend |
| --- | ---: | ---: |
| Startup including actual BSS loop | 5,756 | 1,655 |
| Adapter main | 21 | 20 |
| Full source main/caller/control/oracle | 3,371,758 | 3,394,271 |
| Capacity | 3 | 3 |
| Four helpers, 24 x 10752 | 258,048 | 258,048 |
| text + number + replay_write + replay_text | 40,068 | 28,552 |
| Finite exit through completion store | 6 | 4 |
| **Total** | **3,675,660** | **3,682,553** |

The Spike-backend positive count is 675,660 instructions (22.522%) above 3M.
The walk did not stop at the first crossing. Both complete all 10752 calls,
scalar checks, final diagnostics, callee restores, and their real finite exit
store. Spike: PC `0x8000007a`, tohost `0x80014740`, SD1. SoC: PC `0x8000006e`,
CTRL `0xd0000000`, SD0. The post-completion park loop is excluded explicitly.

All 28 source boundary messages and final success counters are traversed;
both backends produce the same 1704 hypothetical positive text bytes. The
runtime contains no device-ready polling or variable external wait loop.
All 146 decimal number calls and 321 text calls are charged. Each backend's
actual relocation/layout is used, explaining the differing scalar totals.
No assumed fixed per-call overhead replaces caller, branch, spill, or address
instructions. `extra_value`, `selected`, and `failure` remain in the binary but
are not invoked on the successful packed fast path; their error semantics were
tested in the separately accepted Host stage, not erased by this accounting.

## Identity and Geometry

- Original stripped ELF SHA256:
  `ca6937f7969cb2664becfe53fac5e49111415929e96220874568964b293b85cc`.
  Its executable segment contains the source-ordered capacity + op_0..3 byte
  sequence exactly once at `0x10910`: 368 bytes, 99 instructions. The named
  source-port windows are independently bound to their ELF bytes. Both new
  ELFs match all five windows exactly; no arbitrary substring or missing-symbol
  exemption is used. Helper concatenation SHA256:
  `6ef8ae8efe6c52758d48b8f230420fb8b0455d3e98b749c059a3fddb5c4d9dd8`.
- SoC ELF `a3690d0ba3954bf8c043cb456b28084214559c542ee5fcdf4ba18ce323aeb852`;
  Spike ELF `e6c826b4dbda92fc79f2b7ca1d532329776fe83d0152213887ee4701a7bee20e`.
- All 10752 eight-argument helper invocations match original model order:
  3 seeds, 4 operations, 7 VLs, 4 masks, 4 starts, 8 rounding/sticky controls;
  each original helper is invoked 2688 times. CAP512/e8m4/VLENB128/physical4,
  original pointers, start, VL, and control are checked, including empty calls.
- Exactly 37 static vector instructions exist, all in the original helpers:
  one capacity instruction and nine per operation. No extra RVV is introduced.
- Every operation retains nine CSR instructions, including four instructions
  saving/restoring vxrm/vxsat. The 24-instruction accounting includes all of
  these and the returned vstart/saturation samples. This is code/path identity,
  not physical CSR readback or observed hardware state.

## Complete Memory and Runtime Scope

Both positive paths verify these exact ordered event counts:

| Event | Complete count |
| --- | ---: |
| Original RNG/override input SB | 4,416 |
| Mask epochs | 336 |
| Full128-byte mask clear SD | 5,376 |
| Original cumulative selected mask SB | 70,644 |
| Fresh output stores, 64SD + SH per call | 698,880 |
| Actual output reads, 64LD + LHU per call | 698,880 |
| Result bytes represented by original oracle | 5,505,024 |
| Guards | 21,504 |
| Expected call-index / saturation reads | 10,752 / 10,752 |
| Expected block-ID / expected payload reads | 26,784 / 81,216 |
| Scalar stack stores / loads | 55,818 / 130,233 |

The exact footprint is 514 bytes, not rounded to 520: tail LHU/SH covers result
511 and rear guard, and the first LD/SD covers the front guard. Out retains its
original 1026-byte backing; upper input backing remains zero. All per-call
initialization and actual reads remain fresh, including repeated sentinel-only
outputs. A metadata-only projection of the completed PC ledger finds exactly
698,880 executed compare BEQs (189 visited static sites), each skipping the
sticky `li bad,1` on the assumed successful path. No actual-read cache is used.

The immutable expected rows/indices/blocks/saturation in both ELF images match
the full Host-validated model. This reuses the accepted numeric oracle; it is
not a second independent numerical reference. The success summary only deposits
512 hypothetical result bytes, never a guard or scalar counter.

The positive stack high-water is 336 bytes in both backends, including caller
and printing frames; 64KiB is reserved. SoC image through BSS: 86,920 bytes;
Spike: 95,312 bytes. Both fit 1MiB with the reserved stack. BSS SD counts are
409 and 1434 respectively. Unknown entry callee-saved registers are opaque
spill/restore values, not fabricated zeros; 13 saves and 13 restores are tracked.

## Review Entry and Limits

`linked_cfg02/complete.json` status `HOLD_LINKED_POSITIVE_CFG_OVER_3M`, SHA256
`8a5c2187374c33be54be7b9046620ace57bccd9cc3f344735ac53b69bbd31db9`.
Per-backend `_cfg.json`, `_PC_visits.json`, `_branches.json`, `_event_PCs.json`,
and `_all10752_arguments.json` retain the complete accounting. Input pre/post
manifests and the original-helper identity proof are alongside them. Actual
analyzer exit is in `cfg_receipt02/`, not inferred from artifact presence.

Tesla independent result review requested. This stage does not establish a
reference PASS, DUT PASS, full Linux replay, or a <=3h DUT budget. The linked
positive cost itself fails the requested 3M gate, so further execution remains
on HOLD. No automatic optimization, reference run, or budget increase follows.
