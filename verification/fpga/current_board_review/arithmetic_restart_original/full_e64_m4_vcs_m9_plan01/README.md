# Original e64/m4 full5985 on frozen M9

Worker preparation; not DUT acceptance. No source compilation or reference
replay. Actual reference READY lives at
`../full_e64_m4_block_prepare01/reference_entry01/READY.json`, not inside its
`reference01` execution directory. The exact terminal review is pinned.

Full continuous35ops/3seeds/5985 original calls,383040 result words,
11970 typed u64 guard0x5b words,5985 returned-vstart and77805 helper
instructions. CAP64, four128B physical registers/group,528B fresh output.
All history/RNG/FP transitions retained. Original source has no fflags oracle.
Historical resume03 board PASS is not this current M9 source-port acceptance.

Own SoC spec is byte-verified against ELF
`7ad99ec2e99b1eab9183e82934f09f29b3322a9c82093935dea3771f6d7d1620`.
The line-local horizontal-whitespace parser includes all2832 instructions,
including failure entries80001c72/80001caa/8000237e; each explicitly rejects.
No Spike-only replay_log/HTIF contract is imported. SoC CTRL raw0 and UART
byte transport are distinct from reference HTIF1.

The source observer consumes actual RVFI PC/code/address/BE/data and GPR
effects, with phase order enter -> effects -> leave. Each call requires66
actual plus66 dictionary LD,9 actual IDs including the final16B block,
66 equal BEQ and one sticky-zero initialization. Expected values/addresses
come from this shape's original source model, not shadowing the DUT output.
Every FP call requires128 ordered SD, including VL0/equal repeated values;
total241920. Masks require35280 clear SD and77175 cumulative selected SB.

Generic lossless six-event protocol validation and source-qualified ownership
are complementary:29925 compulsory helper-memory owners,3762 required
targets including117 op24;18 exact unsigned VI2 null targets are optional.
This is not a fixed total allocation count: every actual token must complete,
including tokens belonging to optional targets. No alloff exception waiver.

Full constructed Host input is not executed firmware or DUT evidence. Final
entry binds actual Host exits, code identities, negative tests, accepted
reference and image pins. Any small Host successor retains old receipts and
must prove its exact delta; no old hash is attributed to new code.

Fixed case10800s/worker12000s/service13200s, jobs1,reserved0, livecap24,
memory>=32GiB. No FSDB/retry/build or runtime budget extension. Child numeric
outcome is saved before postchecks; late abort/pin drift prevents PASS.
Actual ExecStopPost records systemd exit facts and runs the bounded terminal
metadata collector, without semantic CSV reparse or GC-default inference.

Timing is uncertain: reference firmware2804792 is not a VCS measurement.
Accepted M9 e16/m2 metadata reports1075958 retires/3914.3474769704044s;
applying that different-shape throughput without margin estimates about
10204s, while20% margin exceeds10800s. Vector shape and FP mix differ, so
neither estimate guarantees completion. Keep the authorized hard limit and
classify any timeout from actual progress evidence, not as an automatic bug.

Exact independent entry JSON schema consumed by the mature run gate:

```
status: NO_BLOCKER_ENTRY_REVIEW
plan_sha256: actual prepared plan hash
image_sha256: plan.image_sha256
reference_ready_sha256: 156d039c5009f31b4ae4e6928ccf57e3284f2153926522aa01b84a02dd8e8737
scope: [arithmetic_original_e64_m4_full5985_sticky]
pins: exact plan.pins
```

After actual NO_BLOCKER, use `launch_once.py --out prepared01 --entry
/absolute/review.json --entry-sha256 ACTUAL_SHA`. The launcher validates the
fresh plan, submits once, captures real unit/process/privateELF identity and
two bounded startup CPU/trace-size samples, then leaves the task in background.
No placeholder review or extra parent approval loop is used.
