# E8 M1 Reference Terminal

**ACCEPTED_SOFTWARE_REFERENCE_NOT_DUT**. Metadata-only independent audit
exited0 (session22225/completion4debac):152 preflight pins match, exact
approved entry and terminal hashes agree. No raw semantic reparse, raw
rehash, Host/compiler/reference rerun, DUT action or mf2 polling occurred.

- Sole Spike PID3144341 actual wait0,2.674039303s, timeoutfalse/retries0.
- Sole parser PID3144397 actual wait0,33.758930113s, timeoutfalse/retries0.
- Full4095 original calls,524160 results,8190 guards,4095 vstart zeros,
  all13 helper positions4095 times,53235 helper instructions.
- Complete69615 packed output reads,1104 original scalar input writes,
  1575 mask groups; physical group1/full128B, actual vlm16B.
- Firmware-through-HTIF699836 <3M;5 boot +699836 firmware +159 original
  pure-park records =700000. EOF checked; one closed raw semantic pass.
- Raw108320800B stat matches result. Stored raw SHA
  80e1f0d351e0ddabc40bbf4aceae8e5585b09d215c2170d5f650bb521b8ebed9
  is backed by the reviewed sole parser execution, not a second audit pass.

| Evidence | SHA256 |
| --- | --- |
| READY.json | 6c3205d65f484f5455776e29031813ae945bb338e68a3ce1bfac033323a318ca |
| reference01/result.json | 6e46a6e2f37ce61fc0579af4c1d8712c9d0ebec535c31bb4eaa629d811abb8ba |
| reference01/execution.json | e6860d8434aed21a72a118b4954558feea0d2949d1b44a7cd7ee5b0301d35201 |
| reference01/audit_execution.json | 9ba5239015396e229c191d32ffa066018d99ea84c29bef9d5885e3d47150570e |
| reference01/command.json | 6b93ccdcc03e67d3a1f68d70e2bc52d0757051d61e3a638490722a86f505f784 |
| reference01/preflight_pins.json | ee9a657a0411d949696cd880431b9924accf75de414e5aa3b390467f7d430b4b |

The2078.875s (~34.65min) projection uses prior403.97retire/s with20% margin;
it is not measured DUT performance or a guarantee. This closes software
reference readiness only, not M9 DUT or original Linux acceptance. No DUT
authorization is supplied by this report. All prior sealed evidence remains.
