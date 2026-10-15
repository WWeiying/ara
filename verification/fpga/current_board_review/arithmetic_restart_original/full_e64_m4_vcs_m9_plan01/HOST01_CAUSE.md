# Preserved Host preparation failures

Host01 actual exit1/543.8862092820928s, no timeout. Constructed full5985
stream reached3706440 rows; setUpClass then failed the strict console marker
because the builder appended literal backslash+n, not a newline. Zero test
methods ran. This is not Host PASS, DUT failure or reference failure. Original
Host01 code/pins/receipts/log remain preserved in host01_source and host01*.
Successor changes that fixture terminator to the actual source newline;
the marker/oracle acceptance rule is unchanged.

Separately, frozen M9 store_unit.sv117 returns full lsu_ctrl_i.data;
cva6_rvfi.sv294/349 transports full XLEN into mem_wdata, and commit monitor
prints that field. Actual unrolled mask ORI -128 can leave upper bits set
while SB writes only its selected byte. The sole checker delta masks the
argument to life.store with bits=(1<<(8*decoded_size))-1, after unchanged
decoded address/alignment/exact BE/source-GPR low-bit checks. No BE-derived
arbitrary mask, no SD narrowing and no changes to owner/generic/oracle rules.
The new builder passes full source GPR for scalar phase stores, exercising
this transport case throughout the full positive.

Short preflight01 correctly exposed a test-selection mistake: the SD negative
selected an ABI save, where changing both caller GPR and corresponding data
does not violate a known source oracle. Its actual exit1 is preserved in
preflight01_receipt.json and original byte_preflight.py. Successor selects a
real RNG a/b SD, retaining the entire high-bit negative; no checker change.
Short preflight02 actual exit0 (tool session90799/chunk970227),7 tests in
3.362s: full-signextended SB and zero-upper equivalent pass; wrong enabled
byte/BE, changed high bit of source SD, literal marker newline and premature
last-store phase close reject. Full successor Host remains separately gated.

Host02 uses the same600s bound and retains every original test plus the seven
transport tests. No software compile, Spike/reference replay or DUT run.
