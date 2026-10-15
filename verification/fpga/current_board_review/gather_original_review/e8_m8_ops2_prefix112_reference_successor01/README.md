# Original E8/M8 VI0 Prefix112 Reference Successor

Status: **complete software reference, pending independent raw review; NOT DUT**.
The old `../e8_m8_ops2_prefix112_prepare01` remains immutable and
`NOT_COMPLETED_WITHIN_BOUND`; no old READY was created.

## Authorization And Identity

- Admission: `../e8_m8_ops2_prefix112_reference_admission01/review.json`, SHA256
  `05c5c38d985229b2e9a6133786a11a373b6a9d02ecad6c98e8b7c9bf2bcbf3c8`.
- One new Spike execution; ceiling 5,050,000 debug steps (+1% independently
  approved), 120 seconds, 805,306,368 bytes per output file. No retry.
- Reused original Spike ELF SHA256
  `93cfba245d048b057891ed94db7feacac71cd41a2076569de4d130c9917e0f78`.
- Reused original SoC ELF SHA256
  `a0445bcb877799d488e40f37d7bcbc038d9f0e36a7a60e147ed8baf3c5ea5f74`.
- No compilation, source/oracle changes, RTL changes, DUT execution, or live
  simulation queries. The checker is byte-identical to the old checker except
  `MAX_RETIRED` changing from 5,000,000 to 5,050,000. Paths derive from its new
  directory. The old Host12 and source/ELF/13-instruction proof were hash-reused.

## Measured Result

`reference/command.json`, `execution.json`, `commits.log`, `reference.json`, and
`runtime.log` preserve the actual command, execution, full raw and checked result.

| Check | Measured |
|---|---:|
| Spike wall time / process return | 8.289970975 seconds / 0 |
| Total commits through successful HTIF store | 5,002,737 |
| Firmware retired, excluding five boot records | 5,002,732 |
| Original target calls / predecessors | 112 / 111 |
| Retirements of each of 13 original helper instructions | 112 |
| Full scalar result checks / guards | 114,688 / 224 |
| Actual complete vector input/result/store checks | 112 each |
| Returned vstart zero | 112 |
| Raw log bytes | 327,291,090 |

The successful HTIF store value is 1; all three actual software PASS markers
are reconstructed from committed console writes, without a failure marker.
`30803c57` remains VI0, not VX0; original input[0] is 185. All source setup,
RNG, ordinary indices, original instruction order and full-capacity checks are
retained. Natural endpoint is `[0,2,0,6,3,3]`; VL1024 starts remain
`1,512,1023,1023`. This is the complete first seed/scalar-slot block only,
not full2688, Linux execution, or proof of an unknown historical stopped tuple.

Measured completion requires exactly 2,737 commits beyond the old 5M boundary,
matching the prior independent disassembly estimate. This is not an RTL timeout
adjustment and no oracle was removed.

## Negative Controls And Preservation

`host/host_gate.json`: **7/7 rejected as expected**: old5M/noHTIF, wrong encoding,
wrong result, either guard, nonzero returned vstart, and missing scalar oracle.
The first5M bytes of the new raw hash exactly to the pinned old raw SHA256
`af0735ff3e02120d96dd93cd79f157a5ed754a62731a6f1a4ec5d0548fe7d5b3`.
The old-bound negative uses a labeled semantic projection of those new raw
bytes, retaining all relevant setup/register/vector/CSR/oracle state; the old
raw was hashed but not reparsed. The projection still lacks the final78 results,
two guards and HTIF success, and is rejected by the unchanged completeness gate.

410 input pins, including old artifacts and both ELFs, were checked unchanged.
22 successor artifacts are bound by `artifact_pins.json`; this later README and
READY itself are intentionally outside that nonrecursive artifact list.
The initial Python compatibility preflight error is preserved in `error.json`
and explained in `PREFLIGHT_NOTE.md`: no Spike subprocess was started by that
failed preflight. Only one actual reference execution occurred.

## Handoff And Cost

- `READY.json` SHA256:
  `e6962c38c215ec69ec0f0b3aaf5ebadaa9fb33341027a6c8d7f31fba0f135520`.
- `reference/reference.json` SHA256:
  `0d5c635b2d60da8faed7dc2ee7b3f613368c2ad4b552e53104d228e076fb5e12`.
- Full raw SHA256:
  `d193e349e23df14e39c6e58671748849bbba3688f30f012c0cca3aff02b91ba6`.
- Host7 gate SHA256:
  `bc25d1c01b81b948ba0d6261d97084fe0f6742713d7eac99c7583752896dd1a5`.

DUT time is not measured. At the conservative historical 273 retired/s,
5,002,732 instructions estimate 18,325s, or 21,990s with20% headroom, above
the unchanged9000s DUT budget. Conditionally reusing the previous M6 E8 VX
rate (2,672,460 retired / 4052.291789s) gives 7586s, or9103s with20%; this
different operation is not a runtime guarantee. Independent source/raw review
and a separate parent DUT decision remain required. No DUT was admitted here.
