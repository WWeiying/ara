# Exact e64/m4 full5985 reference entry

Preparation only until the exact independent entry JSON below is bound.
Reuses the one software02 pair, with no recompilation or old Host replay:

- Spike ELF `42e53dc666391e88db7c2d436f7972cda362b575ca9e26806110841fecce51ae`.
- SoC ELF `7ad99ec2e99b1eab9183e82934f09f29b3322a9c82093935dea3771f6d7d1620`.
- Independent software review `../../e64_m4_source_review01/SOFTWARE02_ARTIFACT_REVIEW.md`
  (actual absolute path is pinned in entry.json), SHA
  `f0ce4352e238ddd7d7e0a6005a9e618e7b1952a7178c23bc63e7e3095c19d7c1`.
- Actual linked success CFG upper2,863,981, not measured retirement.

`derive.py` derives `soc_spec.json` and `spike_spec.json` from each actual ELF,
symbols and disassembly, and verifies linked bytes. No m2 PCs/capacity/gold
are reused. `context.py` binds all5,985 original rows/seed inputs to this
shape's gold bytes and1986-block dictionary. Full scope is383,040 result
words,11,970 guards,5,985 returned-vstart,77,805 original helper instructions,
35ops/3seeds/complete history. Physical groups are four128B registers each.
Old resume03 board PASS is historical, not current-image acceptance.

## Actual raw checks

- Every helper is the original contiguous13-instruction window, with exact
  arguments, capacity64, vtype26, original VL/vstart, RNE bootstrap, physical
  input/oldvd/predicate and full stored output. Capacity3 executes once.
- Actual scalar init/data addresses, values and full backing arrays are
  checked, including528B fresh typed0x5b output, both guards and full128B mask.
- Each call has9 real uint16 ID reads and66 actual/66 expected LD pairs at
  their actual ELF PCs and addresses. The ninth block reads only16B.
  All66 actual BEQ pairs are equal, with sticky register0; every call has its
  actual initial-zero instruction and the final decision after all132 LDs.
  Missing values, cached expected reads, wrong IDs or early branches reject.
- Every FP call, including VL0/repeated equal values, executes the complete
  actual seed-specific path: one real seed-slot LD, eight table LDs,128
  alternating a/b SDs. Total241,920 FP SDs,15,120 table LDs,1,890 FP calls.
  Three original184-store RNG initializations preserve next-seed history.
- Every original mask group executes16 SD clears followed by the actual
  cumulative LBU/ORI/SB path:35,280 SD and77,175 selected SB total. Ownership
  and phase completion are checked after the final instruction's effects.
- Exact actual software return0 and HTIF1, counters, original full marker,
  fatal veto, known console bytes, exact reset ROM and pure post-HTIF park
  through EOF. No partial prefix acceptance. This source has no fflags oracle.

The parser is reference-specific; SoC has a separately derived spec and CTRL
exit transport, not a fictitious HTIF reference execution. No DUT acceptance.

## Host and preserved diagnostic

Host02 actual wait0;19 tests pass. Tests use explicit synthetic prior-call
checkpoints for small observer negatives, not DUT/internal-force evidence.
Positives cover first integer, first FP, next-seed FP and final call. Negatives
cover missing actual/expected loads, wrong ID/address/value, rear guard,
stale flag, omitted/cached/cross-seed FP, mask clear/selected deletion,
two-versus-four physical registers, incomplete scope, invalid exit/marker,
and non-pure post-HTIF activity.

Host01 wait1/9errors is a checker event-order defect, not a fixture-only
correction or a reference failure. It is retained in `host.log`/`host_receipt.json` and
`host01_source/lifecycle.py`. Its mask completion test ran before the last
mode0 SB effect. The correction adds an explicit post-effect `leave` call
to observer/parser/test event delivery. All required events remain; no
source/oracle/ELF changed. No reference has been executed.
Host03 retains all19 tests and adds seven final-instruction event-order tests;
its own command/receipt bind actual checker source hashes before/after.

## Exact conditional execution

Independent review JSON must have:

```json
{
  "status": "NO_BLOCKER_ONE_BOUNDED_REFERENCE_ENTRY_NOT_DUT",
  "entry_sha256": "actual entry.json hash",
  "one_attempt": true,
  "DUT_authorized": false
}
```

After exact NO_BLOCKER, the already authorized single command is:

```sh
python3 -B reference.py execute --review /absolute/review.json --review-sha ACTUAL_SHA
```

The runner creates a fresh `reference01` once. Exact profile:
`rv64gcv_zvl1024b`, `-m2`, commit logging, debug script `rs 4000000; quit`.
Limits120s/768MiB raw; offline full parser600s. Actual numeric child wait is
durably saved before interpretation, and the parser has its own real wait
receipt. Input pins are checked before/after, and closed raw SHA/stat are
checked across the one full parse. Actual firmware<=3M is required for READY;
a full reference over3M becomes HOLD without increasing any limit.
Any failure is retained; no automatic retry, compile, VCS or RTL edit.
