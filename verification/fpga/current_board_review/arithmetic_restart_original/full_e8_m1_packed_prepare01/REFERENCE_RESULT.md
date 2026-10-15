# E8/M1 Full4095 Software Reference

Status: REFERENCE_FULL4095_PASS_SOFTWARE_ONLY_NOT_DUT. One reference attempt,
one complete raw parse, no retries, no new DUT or RTL changes. Existing running
tasks were neither queried nor modified.

## Identity And Preparation

The source is the authentic rvv_extended04 e8/m1 assembly plus the byte-equivalent
reconstructed original C, not original C text recovery or Linux execution.
Archived/rebuilt ELF SHA:
199a69e4394959e73f0b7458359c06f0e39a09f4c621028eb356723684dd1f9a.
All26 helper routines (328 static instructions) match original machine bytes;
no extra RVV. Original three seeds,4095 calls, input generation, ordering,
1024-byte a/b backing,1026-byte output backing,128-byte mask, failure fallback
and returned-vstart checks remain intact.

Host original/packed20 executions have actual expected outcomes: two positives,
16 detected-error runs and two deliberate UBSan traps. All comparable original/
packed logs match. No alias/OOB workaround or oracle truncation was introduced.
Preparation actual exit0: session20543, terminal chunk c5b136.
Compiled inspection actual exit0: session64495, terminal chunk752727.
The19 lifecycle/EOF tests exited0, PID3140442,1.269312542s.

SoC ELF SHA:
60ce49d374a4b8491d503f3159d3d13c32489e30141b3a52192ea8f47eb01621.
Spike ELF SHA:
ca9d5e5011fe085239aae2432b0a3a91dc98d3bf1adc80f20f6ce3c26011c71b.
Actual SoC text4932B/rodata558792B/BSS3272B, stack gap481448B;
Spike stack gap473056B. Actual main frame304B fits the reserved64KiB.
The flat expected table is556920B, mask table384B, inside the1MiB image.

## Exact Reference Admission And Outcomes

Source gate: ../e8_m1_packed_source_review01/REVIEW.md,
SHA574feec6248a4912693fe507003cbf5688fbc31906d5726931d53fa8172743cf.
Final independent reference gate:
../e8_m1_packed_source_review01/reference_entry.json,
SHA8c6ecace29f346b6935d0484c655c1cdbd87ed829d9f55f1ccd1e27b837cbe96.
It binds entry.json SHA2871d328c6a4119e92775407b49949a90a10e3b982974efb5b99726a72399ce2.

Actual invocation:
```sh
python3 -B reference.py execute --review /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/arithmetic_restart_original/e8_m1_packed_source_review01/reference_entry.json --review-sha 8c6ecace29f346b6935d0484c655c1cdbd87ed829d9f55f1ccd1e27b837cbe96
```

Wrapper session68755 exited0 (terminal chunk132b0e). Spike PID3144341:
numeric0,2.674039303s, timeoutfalse, retries0. Raw auditor PID3144397:
numeric0,33.758930113s, timeoutfalse, retries0. Actual ISA rv64gcv_zvl1024b.
Finite rs4000000 plus quit,120s and768MiB limits stayed unchanged.
The numeric-first execution receipt intentionally remains validated:false;
validation is separately proved by audit_execution.json/result.json, not by
rewriting the child receipt.

Complete evidence:

- 699836 firmware retirements through actual HTIF1;699830 through exit entry.
- 700000 raw rows:5 reset-ROM +699836 firmware +159 exact side-effect-free
  post-HTIF park; full EOF checked, not early-success truncation.
- 4095 calls,524160 result bytes,8190 guards,4095 actual zero returned-vstart.
- 53235 helper instructions: each of13 positions executed4095 times;
  capacity three positions each once.
- 69615 output reads: each call16 LD plus one LHU, exact130 bytes. First SH
  precedes16 SD in real compiled initializer; all17 writes are required.
- 1104 original scalar seed writes and1575 complete128-byte software mask
  initializations; actual vlm consumes16 bytes. Input and destination groups
  are full128-byte physical registers, vtype0, not mf2 low64-byte slices.
- All152 preflight pins unchanged, console exact full-scope success.

Raw108320800B SHA80e1f0d351e0ddabc40bbf4aceae8e5585b09d215c2170d5f650bb521b8ebed9.
Result SHA6e46a6e2f37ce61fc0579af4c1d8712c9d0ebec535c31bb4eaa629d811abb8ba.
READY SHA6c3205d65f484f5455776e29031813ae945bb338e68a3ce1bfac033323a318ca.

## Scope And Next Gate

Measured firmware699836 is below the approved3M acceptance limit. READY's
403.97-retire/s proxy plus20% margin projects2078.875s; this is not measured
DUT time or a guarantee. No DUT worker was created or launched.

Any later DUT worker must bind its own actual ABI/memory/owner evidence.
The exact op19 VSLIDEUP.VI offset2 with VL1/2 can retire without an Ara target
owner in frozen M9; this does not waive full oracle, returned-vstart, memory
helpers, active VL3 slideup, slidedown, or nonempty op24. No active predecessor
checker was changed and no older closed CSV was recovered in this task.
