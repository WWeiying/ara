# Host Stage Diagnosis

No VCS/DUT has been launched. This note does not change the frozen plan or checker.

## Actual Evidence

- host01_process_exit.json: PID3019709, exit-9, timed_out=true,300.024508s.
  host01.log is empty. No per-stage timing was instrumented.
- test_host.py:35-63 performs specification/model/reset/image checks, ABI construction,
  the entire4095 constructed row stream through lossless generic+Strict, and both
  finalizers plus owner_coverage in setUpClass. unittest prints individual test
  names only after this class setup returns. Thus empty output bounds the first
  timeout to pre-test/class setup, NOT to a particular row or owner phase.
  Import/setup subphase durations cannot be recovered from the existing receipts.
- host02_process_exit.json: same checker/test/generator, PID3026574, numeric1,
  timed_out=false,411.814141s, pre/post input hashes unchanged. The full setup
  completed,22 individual tests passed, including the full4095 positive, real
  ABI, lossless row-count/hash equality, original helpers/oracles and owner tests.
- The sole failing test expected a later fresh/initializer error. With28 SDs
  omitted after the middle SH, Strict correctly raised the earlier
  ValueError: Actual source initialized values out. This is a test message
  assertion error, not an accepted missing initialization.
- host_negative03_exit.json: PID3029839, numeric0,2.523335s,timed_out=false,
  same checker/generator/test hashes. Two short first-call tests independently
  verify the actual earlier value rejection AND missing fresh writes when all
 1026 shadow bytes are preloaded with the correct prior91 value.
  No full4095 stream was repeated after Host02.

## Static Cost And Limits Of Attribution

The old m4 Host took267.031592s. m8 doubles each call's explicit scalar memory
checking from65 to129 initializer stores and65 to129 output reads; seed input
length also doubles. The same constructed generator additionally supplies real
address/source GPR rows and all six generic event kinds for every call. All of
this occurs before the first unittest progress line. Copying the old300s Host
bound without scaling this work was insufficient preparation.

This supports a Host work-volume/budget issue; Host02 proves the same full
pipeline terminates. It does NOT measure whether the dominant portion was the
row loop, model initialization, image pin validation, final generic pass or
owner aggregation. No retrospective phase/row timing is claimed.

Host02 changes only the outer Host runner to a separate900s bound/receipts and
entry receipt selection. checker.py, test_host.py and host_records.py are unchanged.
No RTL, reference, target program, DUT budget or oracle changes. Original Host01
and Host02 unsuccessful numeric outcomes remain genuine and unchanged.

Strict clone at test_host.py:14-23 shares read-only gold/spec/code/helper tables;
only mutable regs/memory/fresh/calls/counts/console/offloads are cloned. The
lossless observer clones mutable counters/queues and both hash states. This
does not fall back to deep-copying the full gold table. Its isolation negative
and full lossless delivered-row/hash equality tests passed in Host02.

## Progress Diagnostics

The sealed completed tests will not be modified or rerun just to produce timing.
For any genuinely required future Host successor, diagnostics should emit
flushed monotonic timestamps at imports/spec/model/image completion, ABI end,
full-stream begin, each256 completed calls with row/retired/call counters,
Strict.finish, generic.finish, owner_coverage, and each negative start/stop.
These diagnostics must not filter or mutate any row, skip the full positive,
replace generic hashes, or change the read-only snapshot sharing contract.
They cannot fill the missing Host01 measurements retroactively.

Frozen prepared01 plan d5499f1b6d2db2f9cc8cd9300caf13fc571f7f9c2738a94f29c0fc66b8da0339
remains811pins. Its entry review is pending. No new Host/reference/DUT execution
is needed to report these already-closed observations.
