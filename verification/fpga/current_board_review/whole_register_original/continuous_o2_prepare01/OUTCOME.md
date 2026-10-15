# Sole O2 Outcome

REFERENCE ACCEPTED; DUT HOLD ON COST. No DUT was started. No Spike rerun.
The packed candidate remains design-only in `PACKING_DESIGN.md`.

## Authentic Scope And Identity

Only whole_all SoC/Spike were compiled, with -Os replaced by -O2 and automatic
vectorization disabled. Nine copied source/runtime/wrapper inputs are unchanged.
Original 1134 calls and 366 exclusions retain their exact order; all 20 complete
helper windows match old machine encodings (620 instructions per backend, not
620 bytes). This is continuous source/reference evidence, not DUT closure.

SoC ELF SHA256: `3f02c7531dd7fd97f75c8f457b3efbf1708672a114da86d81be05cf7f3b3b2a0`.
Spike ELF SHA256: `1c14e9a41f522c13da4836090cc4161f7232cb5cbbc5439d39d0150e3338f688`.
The earlier preparation-path typo and non-recompiling resume remain documented
in `PREP_ERRATA.md`; successful SoC compile was not repeated.

## Actual Terminal Evidence

- Original Spike: PID2866664, wait0, 36.558409s, one execution, 40M-step/120s bound.
- Old parser: PID2866891, timeout600.017414s, wait-9; original driver wait1 and
  `reference01/NOT_ACCEPTED.json` are preserved, never relabeled PASS.
- Authorized offline successor: PID2875019, wait0, 359.902194s, timeout=false.
- Successor driver: PID2875018, wait0, 362.811888s, timeout=false.
- Host7: PID2873928, wait0/0.267901s, before the successor was frozen.
- Original reference bound: `bfc5d224fb820f354ee11bc04c779f21093dbdece6baf22ef20a2d6da96bc0b6`.
- Successor bound: `d719cd9431a831e4fb6648425259c6dccef0f28ddb4ceaf0b2e0118e95ba5573`;
  54 pins checked before/after and closed raw stat unchanged.

The successor only caches a fully checked immutable completion, bound to active
identity and status/CSR/count/PC snapshots. Missing/duplicate reads, premature
write, wrong returned status, post-completion mutation and incomplete next call
remain rejected. Tesla's independent narrow review is
`../continuous_o2_static_review01/SUCCESSOR02_REVIEW.md`, SHA256
`5f972d50523740278eb922bfb0d17515cdade56b66d88f656b949c56fc7f6e68`.

The closed 1,496,354,799-byte raw SHA256, computed during the sole completed
successor pass, is `72bf66f80505f3872449ee272d8147f1d111dc5340a13b4b1edcb70322326733`.
There was one incomplete timed-out parse, then one authorized completed parse;
the result's `full_raw_parses=1` describes the successor, not absence of the old
attempt. No third parse or separate raw hashing was performed.

All 1134 calls, 366 exclusions, 1,233,792 output-byte checks and 2268 vstart
readbacks passed. Actual vlenb=128, exact helper paths/arguments/return status,
original counters [1134,366,0], raw firmware exit0 and HTIF1 were checked.
Firmware through successful HTIF: 23,215,118 instructions. Logged steps:
23,220,000, including 5 boot and 4877 subsequent parking instructions.

`audit_successor02/run01/RESULT.json` SHA256:
`26c4207ece67416b6c7c53f7e67c00c388f860c50b016cb04eadd062968a6389`.
`audit_successor02/run01/reference.json` SHA256:
`5bc6dc2086f23c0ab74a6ca26a74ffd79c151ced8eaded037a46198db4c82caf`.
Numeric receipts are `audit_successor02/run01/audit.log.exit.json` and
`audit_successor02/offline_driver.log.exit.json`; their adjacent command files
record actual argv. The one-shot successor command was:

```sh
python3 -B audit_successor02/run.py run d719cd9431a831e4fb6648425259c6dccef0f28ddb4ceaf0b2e0118e95ba5573
```

## Cost Decision

Using already-accepted historical whole-partition retire/elapsed metadata in
`../terminal_audit01.json`, rates range 644.450802 to 784.101710 retired/s.
For this continuous firmware, nominal proxy time is 29,607 to 36,023 seconds
(8.22 to 10.01 hours). Slower rate plus 20% and explicit 300s planning allowance
is 43,528 seconds (12.09 hours). These are NOT measured current DUT runtimes;
partition parallelism cannot shorten one continuous execution.

The measured reference cost is far above the approximately 5.639M-instruction
three-hour planning limit. Therefore HOLD: no DUT launch or timeout extension.
Proceed only with the static packed design, not implementation in this turn.

## Evidence Boundary

Pinned source and actual scalar-memory shadow establish setup values, but this
observer does not separately ledger every fresh equal-valued setup store per
call. It does not claim that stronger dynamic property. A future packed/DUT
observer must add fresh full-array write coverage and corresponding negatives.
Preserve the original helpers, history, full oracle and diagnostic counts;
packing is a new equivalence transformation, never original C byte identity.
