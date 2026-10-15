# Reference Terminal Acceptance

Decision: **ACCEPTED_FULL4095_REFERENCE_METADATA_ONLY_NOT_DUT_NOT_LINUX**.
The uniquely authorized software reference and its one closed audit completed
successfully. This satisfies the reference prerequisite only; DUT is not
authorized or accepted, and the old e8/m8 timeout remains unchanged.

## Exact Chain

Producer: `../full_e8_m8_sentinel_mask_reference_entry01/`.

| Evidence | SHA256 |
| --- | --- |
| ENTRY.json | 6e1591fafa4a90c637a1db9f71c34f090f7b52090c8a2436351d826c8c1ba832 |
| Independent entry review JSON | 4b21b0b556d6a9ad2bc7febd3d82d748e6a38a79d8346bc75d290b8425bc6a60 |
| Parent execution authorization | 03823e9b74053232c0748a1ef16d5566c86e73bb1d9d5ae36217f3b27c579066 |
| READY.json | 23b23bd530e012519d1cbbd1ccabe5c1a2fad270669bab037c21fc734c49ab37 |
| reference01/result.json | be211f0408a8b0098b5fa8cc523b9c514b54685dffa24353f44cf57d26975688 |
| reference01/execution.json | 0fc4758a9dccb0b29f96e7a9810f06533d80cda1cb8b4525e27ba4619ae1a812 |
| reference01/audit_execution.json | e970afc7dfd20f948edb378b15245f03823c229a441cb78127085873965d7ff9 |
| outer_execution01.json | 3ed6d72a2bd6198a197a5fbbe436fdf3c03244fe6c25510cb3aa74d2d873d44f |
| reference01/preflight_pins.json | e41c14622253e72499ece8e5a74dcc64ad9844680da7dd658c6a2ed3dc8ebed1 |

Actual Spike ELF remains
`b1cd154e319211187f8e6e34f7e8f40398ebdc65f035e033ed7b8f8141d15c0c`.
Command uses rv64gcv_zvl1024b, rs4000000;quit,120s/768MiB and600s closed
audit. The recorded outer command binds the exact executor, entry review and
parent authorization; execution_driver01.py records a real Popen.wait outcome.
It is not a fabricated systemd/service exit receipt.

## Actual Exits

| Process | PID | Actual wait | Seconds | Limit |
| --- | ---: | ---: | ---: | ---: |
| Spike | 3650311 | 0 | 15.054346 | 120 |
| Closed audit | 3650366 | 0 | 263.512189 | 600 |
| Sealed executor, observed by outer driver | 3650260 | 0 | 285.007928 | 780 |

All numeric statuses are integer0, timeoutfalse/retries0. The original numeric
journals deliberately retain validated:false; independent acceptance here
does not overwrite them. READY/result/receipts agree, and small outer log says
READY2559063; audit and Spike console logs are empty. No contradictory failure
marker occurs in the exact source console captured by the accepted audit.

## Complete Source Scope

- 4095 original calls;4193280 result bytes;8190 guards;4095 returned-vstart0.
- Thirteen helper-position counts each4095, totaling53235; capacity counts
  exactly[1,1,1]. These are actual recorded audit counts, not planned counts.
- Complete1026-byte output and2B tail;528255 scalar output reads.
- Inputs each1024B, physical8/vtype3, full128B predicate;8832 original RNG
  stores,1575 mask groups and25200 mask stores.
- Comparator1686072 instruction visits, exact linked PC counts;528255 actual
  loads,109575 gold loads,69615 ID loads and zero other comparator loads.
- The audit reports20475 source helper memory retirements, explicitly not DUT
  allocation/completion-token evidence.

Actual firmware_to_exit=2559057 and firmware_to_HTIF=2559063. The latter is
below3000000 and comes from the closed retirement ledger, not the static cost
upper or debugger instruction counter. Final HTIF context is call4095,
PC0x8000007a/code0x00a2b023. Five boot rows are separate. EOF includes932 exact
purepark rows:2559063+932=2559995 firmware rows; plus5 boot=2560000 total,
within the4M finite bound. Full EOF is accepted, not an early PASS-marker stop.

## Pin And Raw Boundary

The257-entry execution pin map is exactly the254-entry prepared set plus entry,
independent review and parent authorization, with no differing hashes. Current
hashes of256 small pinned files were independently checked, including source,
helpers, checker/profile, actual ELFs and prior receipts. The192MiB frozen Spike
tool binary was not rehashed in this metadata-only review; its identity is
inherited from the previously accepted entry verification and successful audit's
pre/post pin checks. No raw path occurs in the checked pin map.

Raw semantic/hash evidence is inherited solely through the reviewed checker,
successful numeric audit and sealed result:
631940998 bytes, SHA256
`465fdd35487d95eb301295afecfd2fb035403a333200b10a9967a071c9a721eb`,
one semantic parse, pre/post pins unchanged. This reviewer did not stat, read,
hash or parse commits.log. No reference, Host, compile or DUT was rerun.

Host01 failures, Host02 success, old software/reference artifacts and old DUT
timeout remain preserved. Full4095 reference acceptance is not current DUT
acceptance, a3h runtime guarantee, or closure of the original Linux stall.
