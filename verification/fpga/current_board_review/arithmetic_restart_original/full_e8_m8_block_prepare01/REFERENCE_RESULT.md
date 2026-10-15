# Full4095 Reference Accepted, Cost Held

Final disposition: **REFERENCE_FULL4095_PASS_HOLD_COST_OVER_3M**.
One actual Spike execution, one complete raw semantic parse, zero DUT runs.
No timeout/budget increase, reference retry, prefix substitution or RTL change.

## Actual Outcomes

- Spike PID2991086, numeric exit0,16.746144s, no timeout, retries0.
- Independent fullraw parser PID2991141, numeric exit0,190.388889s, no timeout,
  retries0. Actual outer execute command exited0, exec session72994 completion
  chunkf84223. Numeric source execution and parser outcomes are separate files;
  the original execution receipt's validated=false is preserved, not rewritten.
- Firmware before replay_exit:3271926; firmware through actual HTIF1:3271932;
  boot5. Actual HTIF store PC0x8000007a, insn0x00a2b023, raw line3271937.
- Full4095 original ordered calls,4193280 result elements,8190 guards,
  4095 returned-vstart zero,13 helper positions each4095 =53235 instructions.
-528255 exact output/guard loads; fresh exact1026B setup each call;
  full128B physical masks and original3seed/CAP1024 input bytes checked.
- Full raw684293609B, below768MiB; hard4M debug steps and120s wall bounds held.
  Raw SHA13d93f081e22a7ad38cc56aa8ef8a9cc403c8e3227741aac748540e7e72ec7fc.
- Source/ELF/reference/review pins unchanged before/after execution and parse.
  All8 physical registers per v8/v16/v24 group are checked, not only the low4.

Actual console:
`RVV_MATRIX_PASS sew=8 vlmax=1024 cases=4095 elements=4193280 errors=0 seeds=3 guard_tail_mask_vstart=checked`

## Entry And Artifact Ownership

The original entry130pins was held BEFORE reference because its observer joined
only4 physical registers. It remains unchanged. The sole execution belongs to
`reference_successor01/entry.json`, SHA
a0a73080e501711dc40d4ea63798a5f7f3b8b120d0b9abed4601469ace7dfdeb,
and `reference_successor01/reference01/`. Its138 entry pins, corrected group8,
four new Host tests and unchanged original Host/ELF/source were independently
approved by Tesla:
`../full_e8_m8_block_reference_entry01/REVIEW02.json`, SHA
d9682edfcaa0bf6e8301c90989bdb2c55429ad8613e32aac822e3ecea1eb4463.

The execute command was:

```sh
python3 -B reference_successor01/reference.py execute \
  --review /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/arithmetic_restart_original/full_e8_m8_block_reference_entry01/REVIEW02.json \
  --review-sha d9682edfcaa0bf6e8301c90989bdb2c55429ad8613e32aac822e3ecea1eb4463
```

Parent-directory `HOLD.json` belongs to this successor entry, not old entry
acceptance. Its exclusive publication did not overwrite any prior result.

## Boundaries

3271926 exceeds the3M target by271926 (9.0642%). The recorded historical403.97
retire/s proxy with20% margin projects9719.31s, but this is NOT a measured DUT
runtime or launch clearance; m8 vector/division latency remains unmeasured here.
Honor the explicit target: HOLD, no automatic DUT or second optimization trial.
All source calls and byte oracle were retained. This reference acceptance does
not establish current RTL PASS, original unmodified Linux execution, historical
stall root-cause closure, or e16/m8 execution.

## Terminal Hashes

- HOLD.json:5810fde35a84bdccdc752797362160f70775a5ac34b11870280c02a09d48f5ae.
- reference_successor01/reference01/result.json:4d665c6ca2cf4fe1cc1a389cf45c13403dfa6c84176bfde5d965d83ba5c02605.
- execution.json:e238dc16b0f586f0c40eb1e8c3c70d2faef9179859ba211b2ad36591e2fbf7a6.
- audit_execution.json:48dfbdbe5a25e1505218bbf45843f3309307ff1873803d2b8f62d45dd3b088b6.
