# Decode activation preparation: register-layout evidence

The first two candidates completed both real captured shapes and passed the
functional/UVM gates, but are rejected for performance. Their complete reports
are `verification/out/q8k-decode-soc-vcs-20261026-01/result.json` and
`verification/out/q8k-decode-split-soc-vcs-20261026-01/result.json`.

| Candidate | K | Original cycles, two trials | Candidate cycles, two trials |
| --- | ---: | ---: | ---: |
| Vector selection | 1536 | 19660 | 45618 |
| Vector selection | 8960 | 111914 | 263400 |
| Split loop | 1536 | 19669 | 28028 |
| Split loop | 8960 | 111891 | 160571 |

The distinct-register candidate is still running. Its completed K1536 ABBA
records are original 9923/9797 and candidate 8767/8583 cycles: summed cycles
19720 versus 17350, a 12.02% reduction (1.137x). Both paths report digest
`30ba8689f5196189`, FCSR=1, VCSR=3. These records are not the final two-shape
test verdict and are not a projection/model speedup.

The first K1536 trace snapshot is frozen at
`verification/out/q8k-decode-layout-trace-analysis-20261026-01`; snapshot hash
`c2786c7165273de9ab83f0d5bc7b1fb845e42410f69c2d9ac91f7459f697e742`.
The analyzer verifies the exact ELF before applying opcode mappings.

| Selected instructions | Split-loop internal uops | Distinct-register internal uops |
| --- | ---: | ---: |
| 192 short slides | 384 | 204 |
| 192 widening reductions | 588 | 216 |

The compiler originally reused the slide destination as the widened reduction
destination. Repeated e8/e16 register-layout transitions caused internal
reshuffling. Keeping the narrow source live alongside the widened result
prevents that reuse without changing the numerical algorithm or removing RTL
correctness checks. The new reduction uop count matches the original path's
216; short slides now write 4608 enabled bytes including internal work rather
than the original long slides' 46080. Two half-register copies add 3072 bytes.
These are vector-register writes, not external-memory traffic. Residence
times overlap and must not be summed as a stall breakdown.

No Decode candidate has been installed into production. Promotion still needs
the complete K8960 functional/protocol result, input-provenance checks, and
whole-projection/runtime validation beyond the preparation-only measurement.
