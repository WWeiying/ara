# Exact Two Reference Attempts Authorized

Parent review approved this specific bound and software state before execution:

- bound.json SHA `809f8fcb36a0f736c07c8104e7db0858793724ebdcf356cc4e342db4e26d583d`.
- software_status.json SHA `b594d33cdbf7f8eca04ad32e03a8eb5243b39a76ca8fb09cf89192400d27036e`.
- e8 Spike ELF SHA `a9106c4d434894b700b473d4b7038e4dfe108068aaceec7c146366b1f109f1aa`.
- e32 Spike ELF SHA `0deb7f54c56e30decfa9661cecac80cb98377373f55bd35b13570fbe65c259c8`.

Exactly one invocation each, original full sequences, ISA rv64gcv_zvl1024b,
24M/32M debug steps,120 seconds,6/8GiB per-file limits. Complete raw retained;
actual wait returncode persisted before audit. Reference scripts are already
explicit bound input pins and will be verified before/after each invocation.
No DUT, RTL build, software rebuild, changed bound or reference retry is
authorized. Ordinary oracle failure in one case does not cancel the independent
other case; systemic identity drift stops dispatch. Hardware time estimates
must remain qualified proxies from the accepted M4 prefix5 measurements.
