# e32/m4 Full5985 M9 Terminal Acceptance

**ACCEPTED**, limited to the complete original source-derived e32/m4 matrix on
frozen M9. No original Linux historical-stall closure or dedicated fflags oracle
is claimed. No DUT/reference rerun, CSV semantic reparse or live query occurred.

Actual independent metadata command:

```sh
python3 -B verification/fpga/current_board_review/arithmetic_restart_original/full_e32_m4_terminal_review01/review_metadata.py
```

The command exited **0** (exec session37583, completion chunkbb0975).
Result SHA256:
`08032aedc12e65781f7455bb34c1715c68f50e70109f7ba28c4e70ac349245b6`.
The full call/owner ledgers were checked as sealed report metadata; only their
small summaries are emitted. An initial notification inspection revealed that
the notification embeds the full strict report; subsequent inspection used
explicit field projections. This did not cause a raw/CSV reparse.

## Real Outcomes

| Evidence | Outcome |
| --- | --- |
| Simulator durable monitor receipt | Integer0,9010.677922162227s; no timeout, failure or cancellation |
| Whole worker | Exact one member PASS; aborted=false,retries=0,pins_unchanged=true |
| Actual systemd ExecStopPost environment | SERVICE_RESULT=success,EXIT_CODE=exited,EXIT_STATUS=0 |
| Collector actual subprocess wait | Integer0,16.913076642900705s; no timeout/retry |
| Existing event notification | TERMINAL_COLLECTOR_ACCEPTED; wait_exit.json records exit path0 |

The service evidence comes from the actual stop hook, not GC defaults. No fresh
systemctl query was needed. The event wait_exit record is the observer's own
exit-path receipt, not a newly observed external waitpid result.

## Full Scope And Owners

- Original5985 calls in exact order: all3 seeds and35 operations,766080 results,
  11970 guards and5985 returned-vstart-zero checks. Each call retained all65
  actual output reads over520 bytes. All13 helper positions appear5985 times:
  77805 dynamic helper instructions, with no prefix/partition substitution.
- FP1890 calls:483840 ordered fresh SW and15120 source LW; mask35280 clear SD
  and154350 ordered constant SB. Original RNG/source1104 writes are retained.
- Expected-cache lifecycle:389025 actual LD/BEQ comparisons,124041 expected LD,
  53865 ID reads,33123 hits and14757 misses. No actual-result read was cached away.
- The producer's one lossless CSV pass records3036242 rows,2771357 retirements,
  last cycle12394429,65837 CVX requests/responses/architecture entries and zero
  exceptions. This review checks its pinned report, not those CSV rows again.
- Independently checked all65837 owner-ledger entries against the bound model
  and actual helper PCs/codes. Each of5985 calls has the full11 offload entries
  in order. All29925 required memory helpers and3762 required targets have a
  real balanced owner, totaling33687 alloc/done pairs. This includes all117
  nonempty op24 target loads. The2205 baseline vstart no-ops are separate from
  only18 additional exact VSLIDEUP.VI2 no-ops; there is no general slide waiver.

Original source has no dedicated fflags oracle. No added final CSR-state
readback or physical register snapshot is inferred from the accepted output.

## Identity

- Plan `7dcf6503906b5c50e09e9fa6d681f0664d3f69c3fae31095606621863ec2e5cc`.
- Private/source SoC ELF `6adde60cb19b74d8aa1e1c44a2219042d2a482da18e824772ba2cdf47bd940bf`.
- Complete `2c41b606366f94ad720066fc76f99a4e83d0959fe1d0fa4ec8ac48a5c4f49252`.
- Strict report `67a41ba3cf370763793c237e89ad6c790e126ce8eb3c15cfd14a13513663e21d`.
- Collector result `2f6c88905e349c718e4c1e15eab5a754af835bc6a3536a43e7c7fe798c32fcd0`.
-1192 plan pins;1205 unique input/evidence/approval pins. All1203 non-raw files
  independently rehashed with no mismatch. Two large raw artifacts, reference
  commits.log and DUT commit_trace.csv, inherit the sealed producer/collector
  verification chain without rereading; their exact hashes and sizes are in
  result.json. Notification snapshots match their current sealed metadata.

This adds one complete shape and5985 calls to the existing mixed-image union:
**18/22 shapes,86940 calls accepted;4 shapes/20160 calls remain**. The remaining
shapes are e8/m8,e16/m8,e32/m8,e64/m8. This is not all22 on M9 and does not close
the separate original Linux/runtime-history obligations.
