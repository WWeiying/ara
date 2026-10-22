# Code and Host Preparation Only

Status: `HOST_PASS_AWAIT_ACTUAL_INDEPENDENT_ACCEPTANCE_NOT_PREPARED_PLAN`.

Only this new directory was written. No VCS, simulator, image build, Spike,
systemd launch or RTL edit occurred. Source, predecessor plans and shared
helpers remain untouched. No `plan.json`, `ready.json` or parent approval was
generated. Actual independent acceptance and parent authorization remain
unresolved, not inferred from producer READY status.

## Evidence

- `python3 -B test_host.py`:43 tests,0 failures,0 errors;24.730s.
- `host01.json` SHA:
  `ddda582d8925f50f3232aca5ef26d10085753bce9c799cdf4a87d8d273a8f4ff`.
- `replay.py` SHA:
  `c47aedb952e06cea9cc0108560a4c25772412f273d9b70503dedb8aac3912c82`.
- `checker.py` SHA:
  `959689ad2d2a26d1a879b5c0f9fe7d1b1b8f7f03071a8101a5058fa5a5841b59`.
- Separate read-only SoC disassembly/specification check:13 original helper
  instructions, capacity512, physical predicate128,840 ELF instruction map
  entries. No instruction engine was executed; this is not reference acceptance.

## Bound Prerequisites

Actual READY02 SHA:
`11aec353de588baa6981aa0e46757b76efdbcf7c0656585d5174e96aca523ebc`.
Actual original full-Linux byte-identical proof SHA:
`7cc7582e71120bce71e5c29de897c271330ce0fa7a5c32dd6dad97dfb5c9cddd`.
Historical original/rebuilt ELF SHA:
`a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b`.
Unchanged SoC ELF SHA:
`4d2f9139a8edfe482d95386c8a50a5ba2bebde1c1b0ee50bd598a1f7572f0249`.
Independent audit path/status/schema/SHA: **PENDING main's actual report**.
Parent accepted-plan/run authorization: **PENDING**, no placeholder hash.

When the actual independent report arrives, bind and review its real schema;
do not loosen the accepted-reference gate to match missing fields. Only then
may an explicitly authorized no-run prepare freeze M6 image/source/worker
pins. A new pinned parent review is additionally required before any run.

## Contract

Original source label `rvv_permute_restart_e8_m4_ops3` is never used as runtime
`+TESTCASE`; runtime is `gather_prefix_e8_m4_ops3`. Exact66 calls,33792 results,
132 guards,33924 scalar LBU oracle reads,66 returned vstart0 checks,858 helper
retirements;2178 setup values/2690 initialized bytes per call. Actual two
vlenb128 reads and one m4 capacity512 return are required. All bytes in the
initialized scope are checked on every call; unused static tails are not claimed.

Numeric unvalidated child exits0/17 survive metadata and checker exceptions;
write-once first cause survives later errors. Exact console/FAIL veto, PC/code,
source-model scalar oracle, membership/COMPLETE, late abort/pending-signal and
pin gates apply. Future direct systemd-owned worker:jobs1, fixed5400s case,
6600s outer, no retry, resource total<=24 and available>=32GiB.1353294 source
retirements at a600/s proxy is about2256s, not a completion guarantee.
