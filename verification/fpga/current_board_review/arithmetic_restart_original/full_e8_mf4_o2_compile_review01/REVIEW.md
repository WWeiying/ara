# e8 mf4 O2 compilation review

Verdict: NO_BLOCKER for the reviewed software compilation/equivalence delta.
Not reference completion, budget acceptance, worker admission or DUT acceptance.
No Host/reference/build/simulation was rerun. No producer file was edited.

Reviewed successor: `../full_e8_mf4_optimized_compile01`.
Equivalence JSON SHA256:
`ae3f60ea1bfd5e1f8fa86d482c607a96a6bfdb2f58af84218df4f4c403dbf84f`.

- Independently compared both actual compiler command arrays against the Os
  predecessor: only -Os -> -O2 and successor-directory substitutions differ.
  Both retain -fno-tree-vectorize and -fno-tree-slp-vectorize, with no LTO.
- All 15 declared identical source/model/runtime files freshly hash-identical
  to predecessor and equivalence digests, including original C, case.c,
  scenario.S, operations.h, full model and Host rows.
- Compared all 26 routines (capacity + 25 operations) in each backend's
  sourceproof against predecessor instruction encodings, then checked each
  successor instruction against actual ELF PT_LOAD bytes. All match.
- Full scope remains 4095 ordered calls, 131040 result bytes, 8190 guard bytes,
  4095 returned-vstart checks; no reduced matrix or reordered seeds introduced.
- Prior static C review found no blocking UB/alias/volatile issue for SEW8.
  External assembly calls retain writable output arguments and ordinary ABI;
  implementation-defined signed conversion/right-shift behavior remains tied
  to the existing compiler/target, not claimed universally portable.
- Existing Host positive exits0; eight negative runs exit1. Ordinary UBSAN
  compile exits1 because /usr/lib64/libubsan.so.1.0.0 is unavailable. Preserved
  trap-mode successor uses -fsanitize=undefined, -fno-sanitize-recover=undefined,
  -fsanitize-undefined-trap-on-error: compile exits0 (1.270609s), execution exits0
  (0.018253s), log reports cases4095/elements131040/errors0 and
  HOST_END calls=4095 injected=0 result=0. This is finite Host coverage, not a
  universal UB proof, and the failed ordinary link is not relabeled PASS.
- Reference checker delta only recognizes actual compiler-generated failure
  entries named failure or failure.*, requires a nonempty set, and rejects
  any such entry. Actual sourceproof symbols contain failure.part.0 at
  SoC 2147483876 / Spike 2147483888. The scalar failure rejection is retained
  rather than removed because O2 renamed the function. Full reference outcome
  and raw stream were not re-audited in this compilation review.

Actual reviewed successor ELF SHA256:

```text
soc   33fac90cb3c541657ede2d3b01e2cbd52d7ddd97cd0b78599ac237f237c16f44
spike 7537121418e47ecf7003c833403171701973f0f4cd2fd9308b6f13c09830ba80
```

Independent read/hash/ELF comparison process exited0. No new performance or
functional execution claim is made. Aquinas may continue the existing
reference/budget/preparation workflow without a compilation-review blocker.
