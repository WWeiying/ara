# Negative-Stride Load Terminal Acceptance

Status: **PASS for one source-derived real Sv39 single on frozen M6**.
Case: `e16_m1_u1_s0_b3_m2_f0_g3`; no predecessor cases.
Worker elapsed: **996.6796678779647 s**, below the fixed 3600 s case budget.
Worker and durable monitor/child records have actual numeric exit 0, no timeout,
failure or abort; no retry. Independent waiter: `PASS_INDEPENDENT_TERMINAL_SINGLE`.

## Metadata-Only Closeout

This closeout read terminal/source-proof JSON only and verified their hash links.
It did not reopen CSV, reference raw, ELF/image payloads, or rerun any oracle.
All 64 original reference pins remain represented unchanged in the 690 plan pins;
current payload pin verification and the one full CSV pass belong to the sealed
terminal waiter, not to this metadata-only check.

Worker and independent reports agree on 17274 scalar checks, 64 original results,
2 original guards plus 64 additional storage guards, four full 4096-halfword
memory phases, and the 2048-halfword lower-page refill. The original ten-helper
instruction sequence and full source oracle remain bound by `strict_prefix.json`.
Generic counts agree: 827948 CSV rows, 827772 retirements, final cycle 1118832,
50 CVX requests/responses, one exception, and 13 backend allocations/completions.

The fault has cause 13, `mepc=0x80000e20`, `mtval=0x40000fee` (P-18), VL8,
vtype8 and vstart5. Retry at cycle 731504 preserves the same PC, vstart5,
original base `0x40001016` (P+22), and stride -8. Completion context is ecall9,
vstart0; raw CTRL exit is 0. This matches the original single's expected context,
not its historical incorrect vstart3/P-2 observation. Prefix preservation,
poison, result and guard checks passed within the source-derived fixture.

## Service Provenance

Main reports direct capture, while both units still existed, of `MainPID=0`,
`ActiveState=inactive`, `Result=success`, `ExecMainStatus=0` for
`ara-negative-stride-load-m6-01.service` and
`ara-negative-stride-load-m6-terminal01.service`.
This is attributed to Main's observation, not a query performed by this closeout.
The waiter's historical `service_exit=NOT_QUERIED_NOT_PROVEN` is left unchanged;
no collected-unit/GC default is used as exit evidence.

## Bound Evidence

Paths below are relative to `negative_stride_load_vcs_m6_plan01/`.

| Artifact | SHA-256 |
| --- | --- |
| `terminal_waiter01/terminal01/result.json` | `74e71b439a3a9586c875ef078f1ff4c2e1f0852d8e35f00bf979396de9fd50ce` |
| `prepared01/complete.json` | `812fe100a941e5fa407a452f2ce9c2f5619343aa16004c38a916dbe75b00054a` |
| `prepared01/plan.json` | `aa4c92d225e275b79626d8b732d97363ff5bcc85b71d4a29a1def3b9e367906f` |
| Runtime `strict_prefix.json` | `79d13d9b6ee12861824bc20f4317bde0a7b44f533bc2a1f5c5743485f630714e` |
| Runtime CSV, recorded hash only | `c414d29e1d34583ff015124b9c9d98d2f22538136ee25646af2e7677c683faf3` |

Runtime artifacts are under `prepared01/replay/tests/negative_stride_load_e16_m1_u1_s0_b3_m2_f0_g3/`.
The original SoC ELF remains `04e25a1fa3b6ba094af6d60d50f8ec0dd60f2ec2503f47dda05fd2011c5a0a43`;
the plan binds M6 image identity and the canonical source proof.

Scope is not original Linux ELF byte identity, Linux signal-frame equivalence,
or the full parent96. No new RTL change, build, reference or DUT run was needed.
