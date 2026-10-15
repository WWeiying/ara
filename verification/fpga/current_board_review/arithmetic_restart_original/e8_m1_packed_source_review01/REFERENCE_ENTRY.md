# E8 M1 Exact Reference Entry

**NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT**.
The machine entry is `reference_entry.json`, bound to producer entry SHA
`2871d328c6a4119e92775407b49949a90a10e3b982974efb5b99726a72399ce2`.
Aquinas may execute the single already-authorized bounded reference. No DUT
authorization or reference PASS is inferred here.

## Actual Artifacts

Independent read-only artifact audit exited0 (session19790/completionaae265).
All133 preparation pins match. Twenty existing Host outcomes are numerically
as expected: original and packed each have positive0, eight negatives1 and
deliberate UBSan trap-4. Corresponding original/packed logs are byte-identical.
Four compile receipts are0. No tests or compilation were repeated by reviewer.

Both ELF executable sections were parsed independently. All328 capacity/helper
instructions match original archived ELF bytes, with no other RVV. Complete
4095 ledger order and actual556920B ROM match. Artifact result SHA:
`2e98e94eb8e612a21f0c6cdb4718a0cb5769e8966b55ab77d89a68893c5e9330`.

| Actual ELF | SHA256 | BSS-to-stack gap |
| --- | --- | --- |
| SoC | 60ce49d374a4b8491d503f3159d3d13c32489e30141b3a52192ea8f47eb01621 | 481448B |
| Spike | ca9d5e5011fe085239aae2432b0a3a91dc98d3bf1adc80f20f6ce3c26011c71b | 473056B |

Actual SoC text4932B/rodata558792B/BSS3272B and Spike
text5052B/rodata558800B/tohost72B/BSS11472B fit the1MiB link region.
Actual arithmetic frame is304B, not a ROM-sized stack allocation. Source has
no recursive call path; small number/failure/runtime frames do not consume
the reserved64KiB. These are compiled layout facts, not measured high-water.

The actual compiler uses s6 output base, SH FIRST at offset128, then16 SD.
SoC SH is800004fe; SD80000502..8000053e. First output LD8000056e,
remaining15 LD8000083a..800008c6, tail LHU800008d6. Spike shifts these
sites by12 bytes: SH8000050a, SD8000050e..8000054a, first LD8000057a,
remaining15 LD80000846..800008d2, tail LHU800008e2. The preceding LHU
reads ROM and is not an output read. No padded130..135 output access is
accepted. Source helpers initialize/read the full128B physical group.

## Reference Gate

All150 final entry pins were independently rehashed; numeric metadata audit
exited0 (session32197/completion54e8fb). Existing observer Host19 actual
PID3140442 wait0/1.269312542s, timeoutfalse,attempt1, with1.048s unittest
internal duration. No new Host/reference/raw parse by this reviewer.

The lifecycle binds actual Spike PC/code/width/order:1104 original RNG and
special-value stores,1575 full128B software mask setups,17 fresh output
stores per call and69615 output reads. Original mask loads only16B;
upper112 software bytes still checked. Target vtype0,VL,vstart, scalar7,
full128B source/old-vd/result, complete vector store and all original guards
remain checked. No mf2 truncation or new tail exemption exists.

Negative Host coverage includes each missing output store/read, stale-input
and missing/extra-owner mask setup, upper mask corruption, wrong scalar
PC/code/address/width, full-register upper-half corruption, incomplete BSS,
post-HTIF helper/CSR/memory/GPR activity, wrong park opcode, partial boot and
nonzero success value. The parser recognizes all25 helper interiors and
requires exact contiguous13-instruction call windows and complete counts.

The sole entry uses rv64gcv_zvl1024b and `rs 4000000` then `quit`,120s,
768MiB file limit; parser child600s. Numeric execution receipt precedes
semantic audit; nonzero/timeout retains failure. Raw is closed and parsed
through EOF, with only exact original8000007e/a001 side-effect-free parking
after the8000007a HTIF success store. It does not stop checking on success.
Firmware-to-HTIF above3M is HOLD, not acceptance or automatic budget growth.
Fresh reference01 creation and immutable pins prevent overwrite/retry.

The2M conservative firmware envelope is static, not measured reference cost.
Full source scope remains4095/524160/8190/4095, not Linux execution or all22
shape closure. A future DUT observer must separately apply the actual VI2
slideup no-op exception, not blanket slide/owner exemption. Neither the
running mf2 task nor its sealed checker was inspected or changed.
