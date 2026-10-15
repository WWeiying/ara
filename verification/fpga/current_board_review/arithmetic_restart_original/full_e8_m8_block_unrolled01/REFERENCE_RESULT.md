# Full E8 M8 Unrolled Reference Result

Status: REFERENCE_FULL4095_PASS_SOFTWARE_ONLY_NOT_DUT.

One new complete reference, one full raw parse, no retries. Old measured3271926
reference/HOLD and original static-cost/Host text-only failure records preserved.

## Actual Outcomes

- Spike PID3004457: numeric exit0,15.303520s,timeout=false,retries0.
- Independent full-raw checker PID3004499: numeric exit0,168.324522s,timeout=false,retries0.
- Orchestrator command returned0 (exec session34649, completion chunk97887d).
- Firmware through replay_exit:2825046; through HTIF success:2825052 plus5 boot instructions.
- Raw661024396 bytes, below805306368 bound; hard-step/120s limits unchanged.
- Exact4095 source-order calls,4193280 output bytes,8190 guards,4095 returned-vstart0.
- All13 original helper positions occurred4095 times each:53235 helper instructions.
- Every call initialized exact1026 bytes; original1024-element inputs and128-byte mask checked.
- All528255 actual output reads verified:128 LD plus one2-byte tail per call.
- Full8 physical registers checked for each source/destination group. Actual PC/code,
  capacity1024, VL/vtype/vstart context, raw console and normal HTIF1 exit accepted.
-153 entry pins plus entry/review binding checked before/after; no drift. Raw inode/size/mtime/hash
  unchanged across its single parse.

Actual savings from old reference:446880 instructions (13.658%).
This confirms corrected static_cost02 prediction; initial450975 estimate was wrong and remains retained.
No source/helper/RNG/call/history/oracle changes beyond reviewed scalar full-unroll representation.
SoC/Spike allocated extent grew1984B; actual text +1998/+1994B respectively; frame304 unchanged.

## Identities

- READY.json: b5e5786c6fe09949f43db60abfca14f9507130bf45b41d81be318355e9394c6b
- reference01/result.json: dd980c9992df77c3606e42c759ec1435d730bda8c08f27dd0b6799e8c993f660
- reference01/execution.json: 50874f34b7916b805f32f9af16e3b91ac8fba7be68a055c7012a3df6838f455c
- reference01/audit_execution.json: 87617fbc8e3eeb32004d495a0cf3ba3d7473d13d9451b33a1b5cc8077dbda43d
- entry.json: bb5d14057c05f8f0d1e19894619d988f97f5a3e8844c8087ae21ff0efd68d777
- Tesla REVIEW03.json:30121ab835049fb7cfe4d9c87ec2e4ba3bfde316866b34f274c450390f14ed4f
- Raw SHA:a68a83f830e489ecb5c4a1fe11caa0252fe9f9581284629b5b3a9e44844eb588
- Preserved old HOLD:5810fde35a84bdccdc752797362160f70775a5ac34b11870280c02a09d48f5ae

Actual command, from this directory:

```sh
python3 -B reference.py execute --review ../full_e8_m8_block_reference_entry01/REVIEW03.json --review-sha 30121ab835049fb7cfe4d9c87ec2e4ba3bfde316866b34f274c450390f14ed4f
```

The actual invocation supplied the equivalent absolute review path, recorded in
reference01/command.json. Actual execution receipt deliberately retains
validated=false because it was persisted before the full parser; result.json and
READY.json provide the subsequent validation, not a rewrite of the numeric receipt.

## Budget And Limits

At prior planning rate403.97 firmware instructions/s plus20% margin, projected DUT
time8391.85s (~2h20m). This is an estimate, not a hardware runtime measurement.
Cost target <=3M satisfied; independent DUT runtime/checker/admission gates remain
separate. No DUT worker prepared or launched by this reference action, no RTL edits.
This is source-derived full4095 e8m8 bare-metal software validation, not original
Linux execution, not hardware acceptance, and not evidence for other shapes.
