# Decode block-sum compiler review

The first candidate is functionally equivalent in the completed helper and
captured-input gates, but its vector-valued conditional introduces redundant
work in the measured ELF. This was found by inspecting the sealed
`verification/out/q8k-decode-soc-build-20261026-01/disassembly.log`, not by
assuming intrinsic count predicts executed instructions.

In `decode_candidate.constprop.0`, each 16-byte group executes:

| Address | Instruction | Role |
| --- | --- | --- |
| 0x80000248 | `vslidedown.vx v2,v8,a3` | low subregister candidate |
| 0x8000024c | `vslidedown.vx v1,v9,a2` | high subregister candidate |
| 0x80000254 | `vwredsum.vs v2,v2,v3` | low sum |
| 0x80000258 | `vwredsum.vs v1,v1,v3` | high sum |
| 0x80000266 | `vmv.x.s a7,v2` | low scalar result |
| 0x8000026a | `vmv.x.s a6,v1` | high scalar result |
| 0x8000026e | `bgeu a3,s1,...` | select which result to store |

Both alternatives execute before the scalar branch. The original has one
reduction per group; the first candidate has two. At VLEN1024 and 256 values,
the old loop issues 15 full-range slides and 16 reductions; the candidate
issues 32 short slides and 32 reductions. Shorter slides therefore do not
establish a net benefit. The VCS run is retained unchanged to measure it.

The successor `sums_split.h` processes the low and high subregisters in two
separate loops. This removes the per-group vector select. Full production-TU
compilation passed in `q8k-decode-split-compile-20261026-01`. Disassembly of
`quantize_row_q8_K` shows one slide/reduction/scalar extraction in each loop
body (0x7848/0x7852/0x785e and 0x7882/0x788c/0x789a), rather than both
alternatives per iteration. It also introduces a `vmv1r.v` at each half's
entry, so this is not claimed to be free or faster without measurement.

The original VCS inputs remain sealed. The successor has separate helper and
captured-input gates; no runtime source or RTL has been changed. After those
gates, inspect the actual bare-metal successor disassembly too, because the
Linux production object and bare-metal compilation are different contexts.

Both successor gates completed successfully on 2026-10-26:

- `verification/out/q8k-decode-split-helper-20261026-01`: 33,280 checks at
  each of VLEN128/256/512/1024, 133,120 total.
- `verification/out/q8k-decode-split-real-20261026-01`: seven real Decode
  captures, 280 comparisons per VLEN, 1,120 total; exact output bytes and
  matching FCSR/VCSR, with independent block sums and guard checks.

These results do not replace the pending latency test or establish complete
model correctness for an integrated successor. Keep this candidate private.
