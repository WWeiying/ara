# Host01 Fixture Count

Host01 actually exited1: 28 tests, 27 passed, one assertion failed.
`test_actual_soc_spec_not_spike` expected 185 op-only instructions. Actual original
op windows are four17 + six19 = 182; the capacity window adds3, total185.
Dynamic op instruction count remains182 *1792 =326144, with capacity3 once.

The only semantic test correction adds `len(s['capacity'])` to this assertion.
Output receipt names move to Host02; the checker, helper bytes, oracle and all
other test conditions are unchanged. Host01 log/wait/report/input hashes remain.
This is a Host assertion error, not a DUT or reference failure; no DUT ran.
