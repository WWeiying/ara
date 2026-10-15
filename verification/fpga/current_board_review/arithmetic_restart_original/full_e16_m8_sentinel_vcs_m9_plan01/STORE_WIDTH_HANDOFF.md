# Actual RVFI Store-Width Successor

Host01: actual27 tests/0 failures, wait0/506.708230578s, one full4095 constructed
stream. host01_preflight.json and postflight.json match. Its actual consumed
checker/replay bytes are preserved in host01_frozen_code, with original hashes.

Frozen LSU passes the full XLEN operand through STORE_WB into RVFI mem_wdata.
SH/SW inactive bits are not memory contents. The narrow successor changes only
source RNG comparison to wd&bits and typed initializer comparison to wd&bits.
The preceding decoded known-GPR/BE/width check remains; SD still checks64 bits.
Actual PC/address/order and all fresh/call/owner/output/CSR semantics are unchanged.

width_successor_result.json: five short tests, zero errors/failures; actual wait0
8.686744178s, no fullstream rerun. The actual compiled SH source_register_value
has nonzero high bits. SW uses the real PC/active original005b005b bytes with a
constructed nonzero inactive carrier: an RVFI interface boundary, not a new C
fixture or an observed execution claim. Low-bit, BE, unknown-source and epoch
negatives reject. AST normalization checks the two width changes and allows
only preparation-evidence binding changes in the worker; execution code is same.

The original whole Host and current narrow result are both bound by prepared
plan pins. Original source/profile/oracle and all old m8 timeout evidence remain.
