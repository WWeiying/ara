# VFDSU Round Timing Patch

`vfdsu_round_prefix.patch` applies to the OpenC910 rounding module vendored by
fpnew at commit `e5aa6a01b5bbe1675c3aa8872e1203413ded83d1`. It replaces two
55-bit carry-propagating additions with four-bit groups and a group-prefix
carry network. It does not change rounding decisions, exception flags, clock
gates, registers, or pipeline latency.

The dependency checkout is not tracked by the parent repository. Keep this
patch when recreating dependencies; do not reset other local fpnew changes.
From the repository root, check whether it is already applied:

```sh
git -C hardware/deps/fpnew apply --reverse --check "$PWD/hardware/patches/fpnew/vfdsu_round_prefix.patch"
```

If the reverse check passes, no action is needed. On an unpatched checkout,
first check, then apply:

```sh
git -C hardware/deps/fpnew apply --check "$PWD/hardware/patches/fpnew/vfdsu_round_prefix.patch"
git -C hardware/deps/fpnew apply "$PWD/hardware/patches/fpnew/vfdsu_round_prefix.patch"
```

If neither check passes, inspect the dependency diff instead of forcing the
patch. Existing changes to `fpnew_cast_multi.sv` and `fpnew_divsqrt_multi.sv`
are separate from this patch and must be preserved.

The focused `round-check` target in `verification/timing/Makefile` compares
all 25 outputs of the complete rounding module with its pre-edit source for
30,000 cycles. `BEFORE_DIR` must contain that pre-edit `ct_vfdsu_round.v` and
the other closure-test source snapshots. The timing experiment uses the real
gated-clock cell, not an ungated arithmetic-only model.
