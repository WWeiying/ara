# Corrected Reference Entry: No Blocker

The group8 successor is admitted for the single bounded software reference,
not DUT. Exact entry SHA:
`a0a73080e501711dc40d4ea63798a5f7f3b8b120d0b9abed4601469ace7dfdeb`.

All138 successor pins were independently hashed; the original130 inputs and
both ELFs remain unchanged. The observer delta is exclusively group4-to-group8,
the source-directory adjustment, and trailing newline. No comparison was
weakened. Four actual AST-extracted group tests exited0, covering v8/v16/v24,
high-half differences and missing high registers. The earlier text-only
newline-test failure remains preserved; no reference was attempted under the
blocked entry.

The runner consumes the successor observer, entry and private reference01
directory while retaining original model/lifecycle/ELFs. Executor and observer
both enforce4M total steps, not6M. Full acceptance requires all4095 original
calls/4193280 results/8190 guards/4095 vstarts/53235 helper instructions and
528255 actual scalar output reads, actual HTIF1/software return0. Per-call
output footprint remains1026 bytes including the exact final2-byte access.

Reference bounds: one attempt,120s,768MiB per-file; separate <=3M firmware
cost target. A complete numerical reference above3M is HOLD, not DUT admission.
Incomplete hard-limit output remains NOT_ACCEPTED without retries. Parent
READY/HOLD, if generated, must explicitly refer to this successor's entry and
raw directory rather than retroactively accepting the old blocked entry.

The source/ELF/UB/Host/layout conclusions in REVIEW01 carry forward except
that its physical-group blocker is now resolved. No Host/reference/CSV parse
was repeated by this reviewer. Independent pin/delta verification actually
exited0. Aquinas may perform the sole reference under the existing user
authorization; no additional parent approval is required.
