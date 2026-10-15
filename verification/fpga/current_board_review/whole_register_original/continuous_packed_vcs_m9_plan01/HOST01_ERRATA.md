# Host01 Retained NOT_PASS

Host01 completed 12 tests with one fixture error (actual child exit1, no DUT).
At the first final UART byte, its synthetic store selector chose `sb zero,31(sp)`
but supplied a nonzero byte. Strict correctly rejected row1276733 / PC80000086.
All1134 helper/oracle iterations preceded this fixture error. This is not DUT
acceptance and the old NOT_PASS receipt remains unchanged.

Host02 excludes x0 as a synthetic data/base register when selecting actual
scalar instruction PCs. A second reporting-only issue is corrected: the
reviewed stream identity is a list and byte size is element2, not key `size`.
No production checker, scalar oracle, reference, software ELF or RTL changed.
Old fixture/driver sources are retained in host01_sources with original hashes.
