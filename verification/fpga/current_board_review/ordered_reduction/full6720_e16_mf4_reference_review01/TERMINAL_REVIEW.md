# Full6720 Reference Terminal Review

Decision: **ACCEPTED_REFERENCE_ONLY_NOT_DUT**. The previously reviewed exact entry has completed its single authorized reference and closed semantic audit. No blocking discrepancy was found in the terminal metadata binding. This permits subsequent DUT preparation, not DUT launch or hardware acceptance.

## Scope and Actual Receipts

The original e16/mf4 reduction order remains 8 scenarios x 7 VL x 4 masks x 5 rounding modes x 3 operations x 2 sticky states = 6720 calls. Ordered sum/min/max retain the original fixture oracle, flags and vstart checks. The 144-byte output includes the complete 128-byte destination and both 8-byte guards, not a fractional-source-sized destination.

The accepted closed audit reports 6720 calls, 967680 output bytes, 6720 flags and vstarts, 141120 helper instructions (21 per call), and 3 capacity instructions. It checks 128 input SH, 128 seed SD, 6720 fixture fields, 26880 mask SD, and 120960 output SD plus 120960 output LD. Console reports cases=6720, flags_seen=21, errors=0 and exact board success markers.

Actual persisted numeric waits, all without timeout:

| Process | Exit | Seconds |
| --- | ---: | ---: |
| Spike | 0 | 3.525748300831765 |
| Closed audit | 0 | 78.85188695602119 |
| Outer controller | 0 | 89.83249486098066 |

Firmware through HTIF is 1126049 instructions, below the authorized 2M-step reference bound. The 1130000 raw rows comprise 5 reset rows, firmware, and 3946 pure-park rows. EOF_pure_park=true. The entry review bound the actual HTIF store at 0x8000007a and parking instruction 0xa001 at 0x8000007e, as well as the three actual helper windows and capacity PCs. There was one reference attempt and one semantic parse; no retry.

## Identity and Pins

- COMPLETE SHA256: `aaf1e2d3c33157f8b72bc808eeeed8502aac839367f0054f172d8e0059dd333e`.
- Audit result SHA256: `d9043307b07b5594608b8b81d21870d3fba6e8dfc0f82260e407c0cf98583e6e`.
- Entry SHA256: `0c7febdeffdb16f3d71cbd633105a7598a41b211046fe1518248439e3ccf17f7`.
- Our entry review JSON SHA256: `0dbcca16826f6fff4a24d6c4e49cbd44ef3a44b6451e224fd0625987e334d091`.
- Actual Spike ELF SHA256: `0326cc068509dd6a42a8840426de99fd251dcefe04e552bda5135c36040c7d1e`.
- Original archived ELF SHA256: `0e20bf3cf1449d2d4ce4b9dbf482d107154966554031bcd02cd35f9008e282ec`.

The execution maps contain 180 identical pre/post pins and retain all 177 sealed entry inputs unchanged. Both execution-map files hash to `08e952bab3b41ec833a101f96adc03bebca07a8ae7b4273976b07250a84437b6`. Terminal review independently rehashed seven key current inputs: checker, executor, audit wrapper, Spike ELF, entry, entry pins and our entry review. Other input identities inherit the executor's recorded full pre/post checks. Receipt log hashes and command identities were checked; COMPLETE's result and raw-record objects agree with their recorded artifacts. No NOT_ACCEPTED or FIRST_FAILURE artifact was present when checked.

## Limits

This is a metadata-only terminal review inheriting the sealed entry review and the sole closed raw semantic audit. It did not reread, stat or hash the raw trace, rerun Host/reference/compiler, or start a DUT. The recorded raw identity is 127144742 bytes, SHA256 `99b7f55b894d1fc33ceea75712cce0809cfe94bae3dbf98b33e23fd0e2365276`; this identity is inherited, not independently recomputed here. Source reference acceptance does not establish hardware behavior, original Linux closure, or any change to aggregate DUT PASS counts.
