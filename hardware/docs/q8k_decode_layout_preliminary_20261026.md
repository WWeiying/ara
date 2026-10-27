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

The distinct-register candidate has completed both shapes. Its K1536 ABBA
records are original 9923/9797 and candidate 8767/8583 cycles: summed cycles
19720 versus 17350, a 12.02% reduction (1.137x). Both paths report digest
`30ba8689f5196189`, FCSR=1, VCSR=3.

For K8960, the original trials are 56141/56134 cycles and the candidate trials
49082/49062: summed cycles 112275 versus 98144, a 12.59% reduction (1.144x).
Both paths report digest `f8b770b2c6a5781c`, FCSR=1, VCSR=3. All eight trials
match the independent QEMU golden records, including numerical digests and
CSR state. The final result and UVM protocol check are PASS, with no pending
AXI read/write transactions and all 8869 backend allocations completed.
These are complete preparation measurements, not projection/model speedups.

Final report: `verification/out/q8k-decode-layout-soc-vcs-20261026-01/result.json`,
SHA256 `59e06b7fec2ce2fd7f55698390b41956abe7b3a8d091aae432558c12e75da5fb`.
The raw VCS log hash is
`c69bf6bacadd442907308f6bc37f1dc1904f42fdf076577015ecc62c1771316c`.
The runner rechecked its input/image manifest after execution; its hash is
`9d3859ab710d0b2df767846956af2e4bb09fcaa71198f3d7795ba82b87694d80`.

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
whole-projection/runtime validation beyond the preparation-only measurement.
In particular, paired model runs must compare the original and candidate
Decode implementation, not merely toggle M4 preparation while both processes
use the same new Decode implementation.
