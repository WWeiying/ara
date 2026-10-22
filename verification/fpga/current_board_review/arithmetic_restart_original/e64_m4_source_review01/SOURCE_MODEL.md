# e64/m4 Independent Source-Model Review

2026-10-14: NO_BLOCKER for the existing source/model representation and periodic FP proposal at the STATIC stage. This is not acceptance of an integrated software artifact, Host equivalence, compiled lowering/cost, reference or DUT execution. e32/m2 worker entry remains the higher-priority review.

## Identity And Historical Status

Reviewed `full_e64_m4_source_model01/model.py`, README, the periodic header and existing generated01 metadata/artifacts against the reconstructed original C and source identity. Original and reconstructed ELF identity is `c8e9bad5a0247cb63c9b908a316b5b0f775b242984e187d66f1aa7b3137720f6`. Reconstruction is binary-equivalent, not a claim that original C text was recovered.

Independently read the exact archived resume03 record: `rvv_matrix_e64_m4` passed, actual exit_code 0, 3.2308120001107454 seconds, original complete5985/383040/errors0 marker. This historical board PASS is not current M9 full regression acceptance and must not be relabeled as an unresolved measured arithmetic failure.

## Source And Model Findings

- The source translation preserves uint64 modular arithmetic, signed division/remainder truncation and overflow/divide-by-zero cases, original xorshift and overrides, and source nested call order. The separate mathematical path uses restoring division, bit-level RNG and independent tuple/predicate construction. No discrepancy was found by static inspection; those model functions were not reexecuted by this reviewer.
- Both FP paths deliberately use the same original 640 uint64 golden bit table. That checks transcription/indexing, not independent IEEE754 execution. The generated input and golden binary tables independently match the designated original ELF offsets 0x1520 and 0x1560; no host-float replacement is present.
- Source CAP64/e64m4 means four physical registers per input/output group, 512 data bytes and 528 output bytes including two full uint64 guards. Original helpers are disjoint v8..11/v16..19/v24..27. Gather/slidedown bounds use CAP64, not VL or another shape's capacity. In particular b[3]=64 is OOR at this CAP, unlike e32/m2's b[3]=32.
- Original sequence remains 5985 calls / 35 operations / 3 seeds, with 4095 integer and 1890 FP calls. Each FP call independently rewrites both arrays in a0,b0,...,a63,b63 order, including VL0 and unchanged values. Next-seed integer RNG initialization is retained. Returned-vstart zero in generated calls is an expected value, not a measured CSR.
- The periodic header has the correct three seed rotations, B permutation 0,3,6,1,4,7,2,5 and eight period bases 0,8,...,56. It retains 128 uint64 destination writes per call with per-store compiler barriers, and explicitly volatile eight-word input-table loads inside every call. Future compiled code must prove actual SD widths/order/counts; this uncompiled header is not that proof.

## Existing Artifact Consistency

Independently rehashed all eleven input pins and ten generated artifacts. Existing execution receipt records one model-construction wait exit 0, elapsed model time 2.776706757955253 seconds; it is not C/helper/Spike execution.

Independently reconciled all 5985 persisted call records, flattened ID array and binary golden output without executing the model: U=1986 blocks, 127104 dictionary bytes, 53865 uint16 IDs / 107730 bytes. Every nine-ID row reconstructs all 528 original gold bytes and its recorded output hash. The final block has exactly 16 valid bytes (result63, rear guard) followed by 48 zero representation-padding bytes. Both full uint64 guards equal 0x5b. Padding is not licensed as an output read. Total recorded FP-write obligations sum to 241920.

Key identities:

| Artifact | SHA256 |
| --- | --- |
| model.py | `04b39ab4fbf49c11a48532498636fb9ea0d454013610d472fbf8cc238f3e884c` |
| generated01/result.json | `984e9bfa457dd1178b4fe60e7b0c3e4aef7114190b4ec4439a8f554785635a43` |
| generated01/input_pins.json | `06cda105ceb6dfd7c3563c3d07a6602f7e2a525fcd63dd4c7975a5b8b12e4898` |
| gold_u64le.bin | `c3c9938a41a189115180b08e8e61c34220da268ee49102d3d17fcbc81be3cc31` |
| dictionary64.bin | `86c1fbe7dac7157c3943f4a538f12868f220103173c39d123bb50ba97bfa41e6` |
| indices_u16le.bin | `2c066b751c4ec632cce78622bc567277257fe6ac9fb539bc1be65b4b9b9d01ea` |

## Integration Still Pending

The complete scalar integration proposal must separately preserve 16 full mask-clear SD spans then 64/32/9 cumulative selected byte updates, complete 66-word output fill/read, original fallback/error accounting, all helper bytes and original history. Its ninth dictionary block may read only offsets512 and520, never the 48 padding bytes. Runtime must not link the offline full gold/call records as an oversized table.

The 240402-byte modeled ROM components and 412602-byte reserved envelope are planning arithmetic, not actual map/stack proof. The 142-instruction conceptual FP leaf is not GCC lowering or a full-firmware bound. No compile, Host, reference or DUT admission follows; an exact integrated-source review and separate parent authorization remain necessary. No test/compile/model rerun, raw trace or live query was performed, and no producer/RTL/sealed file was changed.
