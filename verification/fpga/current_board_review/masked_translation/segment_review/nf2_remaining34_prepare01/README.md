# Remaining34 NF2 Software Preparation

This directory owns one shared configuration-driven fixture/oracle/reference
implementation for nine ELF groups. It does not launch VCS, rebuild RTL, run
Linux, or query the active pilot. Every archived standalone source identity,
case.json SHA and measured independent board failure is in source_manifest.json.

## Exact Scope And Versions

There are40 distinct original failed singles. Exclusions from **software
preparation** are exactly:

- J2: `u0_s0_b3_m2_f1`, `u0_s1_b3_m2_f1`, accepted previously on **M2 only**.
  This is NOT current M6 acceptance. The other two old J4 cases are historical
  positive controls and do not belong to the40.
- Pilot4: `u0_s0_b1_m2_f1`, `u1_s1_b3_m2_f0`, `u0_s1_b5_m3_f1`,
  `u1_s0_b1_m3_f0`, compiled separately for the ongoing M6 pilot. No terminal
  state is inferred here and no active pilot is polled.

The remaining34 preserve manifest order and are partitioned4*8+2. They are
standalone archived failures; this batch does not claim byte-identical original
parent Linux execution or its process history. Current-M6 closure of40 would
require independent pilot4 and remaining34 DUT acceptance plus one unchanged
existing J4 M2 ELF replay on M6 (two original failed singles and two positive
controls). No new J4 compile or VCS job is started by this package.

## Preserved Oracle

Per case:128 halfword outputs,2 output guards,8192 memory bytes, all PTE
neighbors and physical guards, seed/saved/result register snapshots, CSR
save/restore, same-PC fault retries, completed active-prefix two-field poison.
Unmapped cases refill before poison. All-off cases must only take S-ecall,
never fault/retry, and check full memory/PTE/guards BEFORE cleanup/refill.
The faulting segment's source-allowed partial fields remain allowed.

Original Linux mask array128B, fixture16B, cap64 helper consumes8B. This input
domain mapping does not prove Linux saved-context/SEGV/sigreturn behavior.
Both protection and unmapped variants use a denied Sv39 leaf; only the latter
add original refill behavior. These limits are not hidden by fullmemory checks.

`fixture.c` differs from accepted pilot C only in comment and marker names.
`fixture.S` is unchanged. `fixture.h` uses `group_config.h` with literal original
tuples and MX_N. Every ELF checks actual array symbol sizes and page guard
addresses; group09 uses two slots, not four with skipped oracle entries.

## Bounded Reference

`batch.py build-all` compiles software only. `host.py` performs one shared full
34-input C-versus-Python oracle check and negative suite; the observer is shared
and parameterized, with representative protected4/unmapped4/final2 Host shapes.
Future CSV analyses use `observer_cli.py` one group per process, so concurrent
groups cannot race the module's configuration. This is an offline observer,
not a VCS execution or admission command.
`batch.py references` permits at most three reference processes and one Spike
invocation per ELF, fixed3M instructions/120s/512MiB raw. See STATIC_COST.md and
each `groupNN/reference02/bound.json` for pre-execution budget evidence.

Reference/raw/oracle failure stops new dispatch. Independent pilot failure
events at `STOP_DISPATCH.json` or the auditor's `wait01/firstfailure.json` also
stop new dispatch, without reading pilot live output. In-flight references
remain bounded and their logs are retained; there is no automatic retry.

The partial software build in group01/reference01 is retained with
BUILD_ATTEMPT01.md. Its failure was a missing ELF size for an assembly label,
not a reference or DUT failure. All final compiled/reference paths consistently
use reference02. No reference was executed against the partial build.

READY is emitted only after all nine original complete references are accepted
by the local checker and all pins remain unchanged. That status is reference
preparation only, pending independent audit, never DUT admission or PASS40.
