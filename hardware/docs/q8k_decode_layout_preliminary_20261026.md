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

## Direct model A/B and complete projection follow-up

`verification/out/q8k-layout-model-pair-20261026-01` passed the direct model
comparison. M4 preparation remains enabled in both processes; only the Decode
quantizer changes. The wrapper counted 682 original calls in one process and
682 candidate calls in the other. Six full-vocabulary comparisons, totalling
911616 logit pairs, are bitwise equal with matching tokens and FCSR/VCSR.
Native QBS work counts match. Raw log hash:
`3b0b80a112672a6c82a2d27bc6696efd1c2bc13dd709731de37f70046a7158b3`.
This model test does not measure RTL timing.

The complete Decode Q projection pair uses real M1/N1536/K1536 tensors,
48 native commands per invocation, and identical context fill/reuse/release
in both paths. Preparation, descriptor construction, execution and output
stores are timed; comparisons and guard checks are outside the interval.
The captured original GGML output supplies an independent tolerance check,
and ABBA output bytes and CSR must match exactly.

The first build/run (`q8k-decode-projection-*-20261026-01`) stopped at the
short QEMU preflight, before any VCS launch. GNU Linux compilation specialized
the embedded static original quantizer and emitted `vfmv.v.f` after
`vsetvli ... e8,m2`, without a new floating-compatible vtype. QEMU trapped at
PC 0x10e94, instruction 0x5e04dc57. This is evidence about that generated
test executable, not an RTL failure or a claim about every compiler version.
The harness now compiles the two quantizers in a separate translation unit,
like the runtime's externally called functions, without changing the algorithm
or compiler optimization flags. The failed artifacts are preserved.

Successor build `q8k-decode-projection-build-20261026-02` passed QEMU preflight:
all four output digests are `64337d9fac6cceba`, FCSR=1, VCSR=3, guards and
captured-output comparison pass. The dummy QEMU cycle values are not timing.
The independent VCS run is
`verification/out/q8k-decode-projection-pair-20261026-02`, systemd service
`q8k-decode-projection-pair-20261026-02.service`; actual simv execution was
confirmed. Complete-projection performance remains pending.
