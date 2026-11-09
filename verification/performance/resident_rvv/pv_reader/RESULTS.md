# Existing-context resident reader acceptance

Accepted host VCS run:
`ara_dsa_signoff_integration/verification/out/resident_pv_reader_gate_20261108_02`.
The actual frozen `akv_v2_context` and generic synchronous SRAM are used, not a
test-only combinational memory. This is a private stream prototype, not a new
architectural instruction or a production-enabled fast path.

| Check | Result |
| --- | ---: |
| Scenarios | 40 PASS |
| Successful shape/reuse scenarios | 21 |
| Invalid configurations rejected | 16 |
| Cancellation with a read outstanding | 3 |
| Context fill writes, 128-bit | 2048 |
| Read responses checked | 2829 |
| Delivered V words, 256-bit aggregate | 2826 |
| Delivered coefficient pairs | 474 |
| Maximum reserved read credits | 2 |
| Measured context read latency | 1 cycle |
| Host checker tests | 6 PASS |

The three read responses not delivered belong to explicitly cancelled calls.
They are discarded before reuse and are not counted as successful stream beats.
The test checks all D64/96/128 and T1/9/64 combinations with and without injected
stalls, coefficient/value order, independent EW16 lane permutation, distinct K/V
contents, final-word backpressure, latched command fields, and held completion.

The reader adds two 256-bit response slots with pre-reserved credits. It does
not duplicate the context store or add arithmetic. Data arrays have no reset;
valid/count state controls use. This capacity is not an area estimate.

Source, executable and completed-artifact hashes were rechecked independently
after PASS with no drift. The service output is not part of the immutable
artifact set because the worker can append to it after producing its receipt.

Reader completion means all requested private stream words were delivered.
It does not mean FMAs have returned, destination VRF writes have completed, or
the original CPU request may retire. Those obligations belong to the group and
SoC integration. No performance improvement is claimed from this transport gate.
