# e32/m2 Reference Terminal Binding Review

2026-10-14: ACCEPTED_REFERENCE_TERMINAL_METADATA_NOT_DUT. Exact original full5985 e32/m2 source-port reference completed; no DUT or original Linux historical closure is claimed.

Input: `../full_e32_m2_block_prepare01/reference_entry01/reference01/`, with parent `READY.json` and the independently approved entry. All 246 preflight pins were independently rehashed and match. No raw semantic parse, reference rerun, Host run, compile, simulation or live-process query was performed by this reviewer.

## Actual Outcomes

- Spike PID 3331285: actual numeric returncode 0, no timeout/retry, 5.9376331102102995 seconds.
- Offline audit PID 3331778: actual numeric returncode 0, no timeout/retry, 89.53480652719736 seconds. PID matches audit_started.json; one raw parse is recorded.
- Firmware through HTIF: 2262610 instructions, below 3000000. Including five boot rows and 2385 actual parking rows: 2265000 total, below finite 4000000. The six-instruction difference from firmware-to-exit 2262604 is retained, not conflated with boot or parking.
- Full 5985 calls, 383040 result elements, 11970 uint32 guards, 5985 zero-vstart returns, 77805 helper instructions and 197505 whole-word output reads. All thirteen helper-position counts are 5985; capacity counts are [1,1,1].
- Seed RNG stores 552; seed cache LW/SW 24/24; FP calls 1890 with 241920 cache loads and 241920 source stores. Mask groups 2205, clear stores 35280, cumulative bit stores 77175. Per-call fresh output is 264B, physical register group is two registers / 256B. All 27 VI2 short-VL no-op calls retain their helper/setup/oracle checks.
- Exact original success console, zero errors, completed EOF, single HTIF success at PC 0x8000007a / instruction 0x00a2b023, and approved parking behavior are recorded by the accepted checker. The existing full oracle is not rerun or weakened here.
- Command binds the approved reference JSON, exact Spike ELF `cbe657411501c8cf974d3c6830caea39847563cfa5f6451ef335eca6e5e809e7`, ISA `rv64gcv_zvl1024b`, 2MiB memory, `rs 4000000` / `quit`, 120s / 768MiB raw budget and 600s offline audit. Attempt count is one; DUT count is zero.

## Hash Bindings

| Artifact | SHA256 |
| --- | --- |
| entry.json | `3d0fba95fad58da26cc1cd5b49a8c0f85e4a9522479da4a3dda19d45e6a0bff3` |
| Independent reference_entry.json | `fef31599adb8a91fe27ca0dd6f2548794137ce8f64703b415038bca9370d69fd` |
| READY.json | `e48688057ac67a1452ef5d9e901f2e99dd8ba8a500fbdf3adf0d2e6777bba17e` |
| reference01/result.json | `93e93545ce7107b81f417ba37f6c4217c63121f49653071aa4992b34ce596999` |
| execution.json | `c7d8335d3341100f1e54737f2341049658e20b11db9a50a033e3d724175158bd` |
| audit_execution.json | `be55ba49325473df8d1f0928c3b9a8f349caccccdcaf519e3b319de52cd4f807` |
| preflight_pins.json | `bf63bc23cb8b7e3da3c473d7bf08ac0a9c0dccca6f8a7c90135c5ebe5b8f9528` |
| command.json | `add8948dafa4f8eb36d57685e6669818f412f7bbedec5c5fd719ba42d146788b` |
| audit_started.json | `6036eb7a7b43d28911747f70a42d94d47d2d45e3f9f145fcdd0b3493075e07a7` |

READY's result and entry hashes, embedded actual execution, command review hash, numeric receipts, scope counts and final arithmetic all match. Raw size 223479471 bytes was checked by stat only. Raw SHA `a41be31e078c54403159e8bc9b83bdd2f9a458cbedb692315e76bb1cc9fba1b4` is the existing completed audit's hash, not a new reviewer hash or reparse.

The projected 6721.1229 seconds with the existing rate/margin is a planning estimate, not measured DUT time or a guarantee. Spike helper/source ownership does not establish DUT generic CVX/uop token pairing. Original source has no fflags oracle. All prior files, failures/HOLDs and sealed artifacts remain unchanged.
