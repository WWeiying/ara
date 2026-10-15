# Software02 Reference Terminal Binding

Verdict: **ACCEPTED_FULL5985_SPIKE_SOURCE_ONLY_NOT_DUT**.
Metadata-only independent review after the authorized unique finite reference.
No reference/Host rerun, no raw read/hash/semantic parse, and no DUT execution.
software01 cost HOLD remains unchanged; this acceptance binds software02 only.

## Identities

Producer base: `full_e32_m1_packed_prepare01/reference_entry01/`.

| Artifact | SHA256 |
|---|---|
| entry.json | `011a92d114214be61a6c376f352e140cb7e6cf76895fb5421165b452642b61a2` |
| Independent reference_entry_result.json | `d117c3552611543047b4e2ab090b689ce58ad3043f2956d832d88984d75f4ab9` |
| READY.json | `d1f70125ab071283390749323120204356e07da6a3a420f450e46c58e5859691` |
| reference01/result.json | `60bcfb49961f43021851fc2ea58b08269129ea4d457db7162c046e9953e9984c` |
| reference01/execution.json | `e6308125d508052e31657f9141ab3866818e68eb0a3bafad47a62f8799d785fa` |
| reference01/audit_execution.json | `7a72d7ccf384d9b522c821b267462642744d8d707a04860bc0da1c7a33e433b2` |
| reference01/preflight_pins.json | `006026d7c0e0ba2bf270e523a0cba44289718c615d86a1be975e5583a4e06545` |

All300 preflight pins independently rehashed: the298 entry pins plus exact entry
and independent review; no drift. Command binds the accepted software02 Spike
ELF `b4fba0b73d4fbd656f54769f7ea8047b3af6fec848de53d685fb209a89651d4f`
and `rv64gcv_zvl1024b`, not a rebuilt program or DUT image.

## Actual Results

- Actual Spike PID3272454: numeric wait0, no timeout/retry,
  5.2937432853505015s. Actual offline audit PID3272492: numeric wait0,
  no timeout/retry,76.16339029604569s. These are persisted direct child outcomes;
  no systemd/outer process exit is inferred or fabricated.
- Firmware-to-HTIF **2,472,244**, below3M and the reviewed static2,550,519 upper.
  Total rows2,475,000 =2,472,244 firmware +5 reset +2751 permitted park rows,
  below finite4M. Raw size197069053B, below768MiB. Actual time stays within120s
  execution/600s audit budgets. Cost is now measured reference retirement, not
  a VCS runtime measurement.
- Result records full5985/35-op source sequence,191520 results,11970 guards,
  5985 returned vstart0,13 slots each5985 (77805 helper instructions), one full
  capacity window, and101745 ordered17-word output reads with136B fresh output.
- FP1890 calls/120960 source SW; original seed writes276; mask2205 groups,
  35280 clear SD plus38955 bitset SB. Physical group1/full128B and vlm4B remain
  explicit. This binds original FP bit-gold; original source has no fflags oracle.
- Original exact PASS console, HTIF at `0x8000007a`/`00a2b023`, one semantic
  closed-raw parse and EOF checked are recorded by the accepted observer. READY
  and result hashes/counters agree and both retain software-only/not-DUT scope.

The completed audit records raw SHA
`8b8da8e8cc21eea3a4579abaf14a8a3fe004b8044fe064ce3ca8a2364d376e40`.
This review checked file size only and relies on the original audit's pre/post
raw hash and semantic validation, not a second raw audit. Tool completion
`fc4582` returned numeric0 in2.40254528s for metadata/pin checks.

VCS projection in READY is an estimate, not a guarantee or launch authorization.
No DUT run, original Linux/board closure, or aggregate shape count is added here.
