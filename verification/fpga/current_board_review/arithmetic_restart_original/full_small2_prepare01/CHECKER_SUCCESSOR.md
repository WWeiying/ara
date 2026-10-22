# Startup Console-Buffer Classification

Both sole authorized reference invocations completed with actual wait rc0:
e8 7.737235s /293505471 raw bytes; e32 10.543294s /396412404 raw bytes.
Their executor `execution.json` was persisted before any postcheck. Both old
postchecks stopped in startup BSS clearing with `Runtime console scalar byte`;
the old NOT_ACCEPTED files and scripts are immutable. This was not an original
oracle failure, a DUT failure, a timeout or a reference retry.

Actual compiled startup PC0x80000046 is instruction0002b023,
`sd zero,0(t0)`, inside the original BSS zero loop, before `main` and before
all helper calls. It legitimately initializes the whole console buffer in
8-byte zero writes. The initial checker incorrectly allowed only later
runtime one-byte writes when reconstructing that buffer.

`reference_check02.py` is a narrowly scoped offline successor. It differs only
by accepting this pinned startup instruction, zero value, width8, address fully
inside the8192B log, zero prior calls and PC in `_start..trap_entry`.
Later/nonzero/wrong-instruction wide writes still reject. All original setup,
helper/PC/order/RNG, full result/guards, vstart, counters, HTIF and raw failure
checks are unchanged. Host verifies one valid clear and four rejected variants.

`offline02.py` checks original commands/ELFs/profile/limits/actual wait0 and all
input pins, then parses each complete raw file once. Original postcheck attempts
ended during BSS initialization before any original helper call; they were not
complete raw passes. No reference process, new software build or DUT is invoked
by the offline successor. Its reports do not retroactively turn the original
executor ERROR into PASS; reference acceptance, if obtained, is attributed
explicitly to the new offline checker and awaits independent review.
