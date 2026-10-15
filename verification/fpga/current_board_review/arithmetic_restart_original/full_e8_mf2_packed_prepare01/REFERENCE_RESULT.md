# Full e8/mf2 Reference Accepted, Not DUT

The single authorized reference and single complete raw parse both finished
with actual numeric exit0. No reference retry, original Host/compile rerun,
RTL change, DUT launch, or running historical-trace inspection occurred.

## Actual Outcomes

| Evidence | Actual result |
|---|---|
| Spike PID3087560 | rc0,1.972304s, no timeout/retry |
| Fullraw auditor PID3087575 | rc0,24.226088s, one parse |
| `reference02.py execute` | rc0, completion chunk2aac5b, session26853 |
| Firmware through HTIF success | 561831 instructions, below3000000 |
| Whole raw | 565000 rows,71709283 bytes |
| Reset/after-HTIF | exact5 boot instructions;3164 pure park rows; EOF checked |
| Original scope | 4095 calls,3 complete seeds,25 ops in original order |
| Results/guards/vstart | 262080 /8190 /4095 zero returns |
| Helper instructions | 53235; each of13 slots4095; capacity slots each1 |
| Actual scalar oracle | 36855 reads:8 LD + tail LHU per call |
| Setup lifecycle | 552 original seed writes;1575 full128B mask writesets |
| Identity | all152 reference preflight pins unchanged |

Fractional mf2 occupies one128B physical register; the original helpers and
oracle observe only its low64B. The original output footprint is66B, and
tail2 contains result63 plus rear guard. Physical mask buffer128B is fully
initialized, while original vlm reads8B. No higher-half register oracle or
new fflags/CSR test has been invented.

`execution.json` preserves `validated:false` from the numeric-first child
receipt, before validation. Successful validation is separately recorded by
`audit_execution.json` and `result.json`; the child receipt was not rewritten.

## Admission And Hashes

Exact independent approval:
`../e8_mf2_packed_source_review01/reference_entry02.json`, SHA
`c9544db0e51ef8379bf70d80eb4efe5ed52d651a1b5c5ae2df75ca0bb4d80f08`.
Entry02 SHA:
`a19f81642a1932e1a7475bec6462c111f97255878ca337b947dde9337b673917`.

Actual command:
`python3 -B reference02.py execute --review ../e8_mf2_packed_source_review01/reference_entry02.json --review-sha c9544db0e51ef8379bf70d80eb4efe5ed52d651a1b5c5ae2df75ca0bb4d80f08`
(execution used the absolute equivalent review path).

READY SHA:
`7327fc1457c47dc44f16c9d9f556251e3184058084486293d494d54d423f3f18`.
Fullraw result SHA:
`73d17b49dae9051e870752d3b70a2d72ec03c203db3fa8a22e47dab33aa94cf9`.
Raw SHA:
`44869dee176b5925a5cb02864647a6ecb0f6f2a406566763e0cbf5b0d58e3b3c`.

Finite `rs4000000; quit`,120s,768MiB bounds were unchanged. Completion
was not inferred from numeric0: complete helpers/oracles/console/HTIF and
remaining pure park through EOF were all required. The initial early-HTIF
draft/entry and successor diff remain preserved, without executing that draft.

## Budget And Scope

Actual561831 instructions support a plausible sub3h DUT budget, not hardware
acceptance. The inherited conservative403.97 instructions/s proxy gives
1668.93s with20% margin, or1968.93s adding300s validation allowance. This is
not a measurement or guarantee of M9 performance. A reviewed exact M9 worker
and separate DUT authorization are still required; none has been launched.

Scope is full original4095 source-port history with binary-equivalent
reconstructed C provenance, not execution of the original Linux ELF and not
closure of the remaining arithmetic shapes.
