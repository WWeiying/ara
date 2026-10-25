# Storage Unit Acceptance

Current state: **generic and real-macro functional VCS units PASS**, with parent
raw-log replay and all source/evidence hashes independently rechecked. Receipt:
`verification/akv/results/unified-storage-unit-20261025.json`.

The preparation README and test inputs are frozen by both accepted manifests;
its original pending-execution statement describes preparation, not current
acceptance. No accepted source or earlier evidence was edited to record PASS.

Both runs executed105 completed rows,105 final-write-latency checks,1361
repacked writes,2048 direct writes,2704 row-word comparisons,72 column-output
comparisons,9 aborts and2 Q-drain/direct-KV overlap cycles. The old independent
legacy/v2 stores and a logical-coordinate byte oracle agree with the candidate.
Original v2 bank request/address/data/byte-enable controls match cycle-for-cycle
on direct writes. Functional macro models use the same byte-enable conventions
as the existing stores; specify/timing checks are disabled by design.

The candidate logically stores34 KiB rather than38 KiB, removing4 KiB of duplicate
legacy K/V payload while preserving the separate eight-row Q capacity and all
64 K/64 V token slots. This is a capacity fact, not measured area savings.

The next gate is actual engine integration: fault-driven transient abort,
write-busy/success drain, context invalidation, legacy/v2 replay selection and
SoC/runtime regression. A storage unit alone cannot establish those properties.
Neither canonical RTL nor a physical implementation was changed by these tests.
