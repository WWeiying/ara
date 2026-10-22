# Worker Narrow-Store RVFI Finding

Blocking until a successor corrects the active-width comparison; not an RTL finding. Current unsealed `full_e16_m8_sentinel_vcs_m9_plan01/checker.py:241` compares full RVFI mem_wdata with truncated SH profile value. Line232 similarly assumes unused upper bits of a tail SW are zero.

Frozen M9 source establishes the interface: `hardware/deps/cva6/core/load_store_unit.sv:851` puts operand_b into lsu request data; `store_unit.sv:117` returns the XLEN lsu_ctrl_i.data without SH truncation; `cva6_rvfi.sv:294,349` records STORE_WB data as RVFI mem_wdata. Inactive upper bits must not be required to equal zero.

Narrow remedy: retain exact decoded width, PC, address, epoch order, byte enable, known source register and existing line222 low-active-bit comparison. Compare the source/initializer expected payload against `wd & bits`, not raw wd. SD remains full width. Do not learn unknown registers or expected data from observed wdata.

Preserve the running Host01 and its receipt. After it ends, use a small successor fixture with actual full source-register SH data and nonzero-upper SW data, retaining rejection of wrong active value, byte enable/address, unknown source and wrong epoch. No need for another full constructed stream. Until that evidence and final plan are sealed, no exact-entry NO_BLOCKER.

Read-only static finding communicated to Zeno; no test or raw trace was run/read, and no producer file was changed.
