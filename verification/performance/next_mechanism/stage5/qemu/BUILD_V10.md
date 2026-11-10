# V10 AKV Trap and EOC Repairs

BUILD06 and every original firmware, numerical oracle, checker, failing run and
source variant remain unchanged. The copied successor changes exactly two C
files, with registered before/after hashes and a unified patch:

- AKV illegal helper: restore CPU state using the real helper return PC first,
  set bins to the model-supplied tval, then raise with return PC zero to avoid
  a second restoration. Frontend opcode and backend zero remain distinct.
- Ara bare-metal transport: accept EOC writes at offset zero of size four or
  eight. Preserve the complete 64-bit value when determining success/failure.
  The accepts callback permits new four-byte accesses only for that write,
  preserving the old policy for all other control registers and reads.

The QBS helper is byte-identical. No new arithmetic or RTL behavior is modeled.
The old QBS checker correction/audit is BUILD06-only historical evidence; every
required gate must actually execute against the newly built image before a
same-image four-gate aggregate can pass.

The V9 source-copy/tree/mode/no-hardlink policy and exact generated empty lock
and scratch directory rules remain in force. V10 reuses the sealed V9/V7
infrastructure, V5 exact command validator, and V4 minimal tool environment.
No configure options or timeouts change: Python3.11, offline wheels, internal
FDT, downloads disabled, configure900s, Ninja1800s/-j4, direct Type=exec worker
with total3000s and 8GiB. James's finite real-GCC syntax receipts are pinned.

Host tests execute the exact repaired illegal-helper and transport callback
bodies under mocks. They verify restore ordering, zero/nonzero tval, 32/64-bit
EOC success/failure including high-only 64-bit failure, rejected wrong access
sizes/directions/offsets, unchanged register reads, and strict build-receipt
mutations. Host checks and compilation alone are not native guest acceptance.
