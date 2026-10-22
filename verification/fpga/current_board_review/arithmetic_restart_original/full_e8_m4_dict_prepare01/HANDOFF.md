# Software Reference Ready, No DUT

Authoritative `READY.json` SHA256:
`d6e07cf6c0a4a3a193feaab29025987007ae2f22a645248d6aaa4bd9c8018555`.

- Full original e8/m4 sequence: 4095 calls, 2096640 result bytes, 8190 guards,
  4095 returned vstart zeros and 53235 original helper instructions.
- Per-call fresh514 output initialization and65 scalar reads are accepted:
  266175 actual complete reads, including both guards and the two-byte tail.
  Original RNG inputs,128B physical predicate and full512B physical output
  are checked against the exact source sequence and independent model.
- Dictionary10172 words, max uint16 index10171, total ROM614110 bytes.
  Actual minimum linker stack gap416416 bytes, reserved stack64KiB.
- Original/packed full Host03 positives and seven corruption classes match
  exact original diagnostics. Both UBSan shift64 negatives actually trap.
- Exactly one Spike execution: wait0,10.546864655334502s,no timeout/retry.
  Actual minstret2646654 includes5 boot instructions; firmware2646649.
- Exactly one completed offline full raw audit: wait0,125.74457491794601s,
  no timeout/retry. Result SHA256
  `869b08a4d2a2a2151dc32a76626ebf835d126a4ae8ca416655cb8bfb3063a9ee`.
  Source/ELF/executor/raw and first-failure pins remain unchanged.

The initial observer rejected startup BSS zeroing as per-call initialization.
Its `reference01/STOPPED.json` and unvalidated numeric receipt remain intact.
Tesla independently reviewed the exact successor lifecycle/initializer gate;
16 focused Host checks passed before the single offline audit. This is
architectural reference acceptance by the successor, not retrospective PASS
for the original failed observer.

Actual executed source review is `full_e8_m4_dict_reference_entry01/review.json`
SHA `ad414d879181c2a85d74acdb1db4c6d99523e80e545f4a0b12f9f9e7875378dc`.
The executed reference adapter hash is
`b19fba8bc50f2c474b0d4d0f469e9170597355d0b8972c2d40edd34fd04e5387`;
it reads that actual review schema rather than the earlier proposed placeholder
schema. Do not claim it is byte-identical to the later cross-message
reference-entry draft's executor hash06c497c8.
Actual offline successor review is `offline_entry02.json`, SHA
`15c25614dfac6fd1c5297abea6816d4bd8be09e00a98fc27330369ceabf26397`.

At the measured packed482 scalar retirement proxy403.97 instructions/s,
firmware plus20% margin projects7861.917s (about2h11m). This is a feasibility
projection, not an M9 throughput guarantee, especially for vector division.
Three million instruction target is met. No DUT permission, RTL/image build,
original Linux timing closure or full parent acceptance is asserted.
