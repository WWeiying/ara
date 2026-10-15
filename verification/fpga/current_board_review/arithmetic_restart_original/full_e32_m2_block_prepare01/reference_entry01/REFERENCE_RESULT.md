# e32/m2 Full5985 Reference Accepted

2026-10-14. Exactly one authorized bounded reference and one complete closed-raw audit passed. This is a source-port software reference, not a DUT run or Linux execution closure. No compiler, original Host suite, reference or raw audit was repeated. No RTL or sealed predecessor was changed.

## Actual Outcomes

- Entry SHA `3d0fba95fad58da26cc1cd5b49a8c0f85e4a9522479da4a3dda19d45e6a0bff3`; Averroes final entry review JSON SHA `fef31599adb8a91fe27ca0dd6f2548794137ce8f64703b415038bca9370d69fd`.
- New observer Host:18 tests, actual child0,15.207016593s. Constructed lifecycle and focused negatives only, not an ISA reference.
- Actual Spike PID3331285: returncode0,5.937633110s, timeoutfalse/retries0. `reference01/execution.json` persists the child result before validation; its initial `validated:false` is intentionally not rewritten. Final acceptance is in the separate audit result and READY.
- Actual audit PID3331778: returncode0,89.534806527s, timeoutfalse/retries0. One semantic raw parse, with pre/post source/ELF/image-independent software pins and raw hash checks.
- Outer execute command exited0, observed tool chunk `94c383`, output `READY 2262610`.

The actual command is recorded in `reference01/command.json`: pinned Spike, `--isa=rv64gcv_zvl1024b`, `-m2`, finite `rs 4000000` then `quit`,120s,768MiB. Offline audit remained600s. Firmware through success HTIF was2262610 instructions,737390 below3M. The complete raw stream has2265000 rows:5 reset-ROM +2262610 firmware +2385 exact side-effect-free park rows. EOF was checked; the configured4M is a maximum, not a demand to continue past normal HTIF termination. Raw223479471B is below805306368B.

## Complete Scope

All5985 original calls/35ops/3seeds,383040 results,11970 uint32 guards,5985 returned-vstart0 checks,77805 exact helper instructions and197505 scalar output reads passed. Every output is exactly264B/33 full LD words; last word contains element63 and rear guard. Both128B physical registers in each LMUL2 group were checked, with actual8B predicate and128B software mask backing.

Actual scalar lifecycle passed:552 original RNG/corner writes;24 seed-cache source LW and24 ordered cache SW;241920 per-call cache LW paired with241920 interleaved a/b SW;35280 mask-clear SD before77175 cumulative selected SB. All2205 mask groups retained their original owner/order. All1890 FP calls refreshed inputs, including equal-old-value and no-op cases. Source FP table is bitwise gold; no host floating-point replacement was used.

Capacity helper ran exactly once,3 instructions. Legal bootstrap fcsr0 instruction, vtype17, source ABI, target vstart and full13-instruction helper windows were checked. The27 original VI2 short-VL no-op calls were not waived: each retained setup/helper/oracle/returned-vstart obligations. Spike has no CVX allocation/completion token stream; this proves helper/source ownership, not DUT token pairing. Original source has no fflags oracle; this report does not add one.

The original software console was reconstructed from actual scalar stores and matched exactly:

```text
RVV_MATRIX_PASS sew=32 vlmax=64 cases=5985 elements=383040 errors=0 seeds=3 guard_tail_mask_vstart=checked
```

246 preflight pins remained unchanged, including both compiled ELFs and the independent entry review. The companion SoC ELF was only pinned, never run. The existing projection is6721.12s using403.97 firmware instructions/s and20% margin; this is not a measured DUT duration or a runtime guarantee. There is no VCS authorization in this task.

## Hashes

| Evidence | SHA256 |
| --- | --- |
| `READY.json` | `e48688057ac67a1452ef5d9e901f2e99dd8ba8a500fbdf3adf0d2e6777bba17e` |
| `reference01/result.json` | `93e93545ce7107b81f417ba37f6c4217c63121f49653071aa4992b34ce596999` |
| `reference01/execution.json` | `c7d8335d3341100f1e54737f2341049658e20b11db9a50a033e3d724175158bd` |
| `reference01/audit_execution.json` | `be55ba49325473df8d1f0928c3b9a8f349caccccdcaf519e3b319de52cd4f807` |
| Actual raw | `a41be31e078c54403159e8bc9b83bdd2f9a458cbedb692315e76bb1cc9fba1b4` |
| Reference ELF | `cbe657411501c8cf974d3c6830caea39847563cfa5f6451ef335eca6e5e809e7` |
| Pinned, unexecuted SoC ELF | `b9a09a69f9ae8d93b38f5a3f8de1049967a79127ebb473da7f321e73143039f6` |
