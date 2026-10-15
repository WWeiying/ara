# STORE Terminal Acceptance

Metadata-only closeout. No CSV/reference-raw reread or new test. Verification
command exited0 (tool chunk d58b61). Producer, independent result, supervisor
completion, actual wait receipt, numeric monitor/child outcomes and strict
result hash links agree. The17 sealed waiter pins were rehashed here; the692
original input pins were verified unchanged by the completed producer and
terminal audit, not reread en masse during this closeout.

- Exact M6 source single: `e16_m1_u1_s1_b3_m2_f0_g3`.
- Producer PASS, durable monitor and child rc0,1111.6245557051152s;
  no timeout, no abort, no retry.
- Independent terminal PASS; actual audit-child wait0, not interrupted or
  timed out. Its424.156896866858s includes event waiting plus audit, not just
  CSV parsing. Supervisor complete.json binds that actual receipt and result.
- 17275 scalar checks;64 original outputs/two guards plus64 extra sentinels;
  four complete8KiB memory checkpoints,16384 halfword reads,2048 refill writes.
- Original capacity3 and10-instruction STORE helper preserved. Fault cause15,
  tval0x40000fee, vstart5; retry at the same PC0x80000e0a keeps base0x40001016
  and stride-8. MRET cycle757062. Prefix127 was observed at cycle209337 before
  repair; the full later memory oracle preserves poisoned prefix36 and
  requires retry destination166.
- Single closed CSV pass:851880 rows,851704 retired instructions,
  last cycle1151782. Six event counts: retire851704, cvx_req50, cvx_resp50,
  arch_start50, uop_alloc13, uop_done13. Exactly one expected CVX exception.
  Target owner16/VID1 allocated208177 and completed208293; retry owner27/VID0
  allocated757070 and completed757132. Full protocol and numerical event
  coordinates agree with the producer strict result.

The original initialization/full-source oracle remains bound to the producer
strict result. The independent pass checked protocol and separate numerical
arithmetic, not a second execution of that source-oracle implementation.
This accepts one source-derived real-Sv39 STORE fault/retry single, not the
Linux signal-frame, original96-case parent, or direct AXI B handshake timing.
Systemd historical exit was not queried/proven in this closeout; no
garbage-collected default properties are used. Actual subprocess waits are
durably recorded independently of service provenance.

## Exact Evidence

Paths below are relative to `negative_stride_store_vcs_m6_plan01/`.

| File | SHA256 |
| --- | --- |
| prepared01/plan.json | ea7add04987278b6c92bdcb720663ee5689021b26384f23111204b6938ed7a81 |
| prepared01/complete.json | 27cf50903086e07f526ce5e8f7d306c5832f54432a827da345892cc80c0bb7bc |
| terminal_waiter01/READY.json | 5bffde8df05035dd95e0d9b0ebda0145a503129fd3d71c7920aea79b33fc0742 |
| terminal_waiter01/terminal01/result.json | 8e56827652dc4af1290b16754882002c56fe934b9b23fb50d96fa22352fb8c25 |
| terminal_waiter01/terminal01/complete.json | 6829307bef70fb496794ac7e7d06823d7d889320defd6df2e915151369f818aa |
| terminal_waiter01/terminal01/wait_receipt.json | d5a6198d7a34373d46f4bfc8cf5c2d1e010d5fdecdd527d68cc19e572ff62286 |

Producer test directory:
`prepared01/replay/tests/negative_stride_store_e16_m1_u1_s1_b3_m2_f0_g3/`.

| File in test directory | SHA256 |
| --- | --- |
| monitor_outcome.unvalidated.json | 38061bb9918d3b46e6c2ef89d634a9fecd19a578f113de6e10d6f9f2a15999ea |
| child_outcome.unvalidated.json | 0030cde47b32de3b6249a70cc3e8339f38fa012c5e3cc9bcc7c0ddc0b8710ab8 |
| strict_prefix.json | 77b02f48d01aa9d6c99383aa46131eca9ab0961ede8e3458b741899063940b53 |
| commit_trace.csv (hash from matching terminal receipts; not reread here) | 3d65b7880b96986fcdb414d5aaef912e306bf8030661a46b4395930308693429 |
