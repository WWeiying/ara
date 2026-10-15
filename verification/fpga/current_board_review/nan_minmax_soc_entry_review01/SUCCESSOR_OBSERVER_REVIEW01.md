# Successor observer entry review

Decision: **NO BLOCKER FOUND IN THE SCOPED CSR-DELTA FIX.** This is static
observer-code entry review, not acceptance of either complete reference and
not permission to launch a reference or DUT. The original STOPPED evidence
remains valid historical evidence. Full architectural reference acceptance is
pending; call1294 numeric process rc0 alone is insufficient.

Reviewed producer: `../nan_minmax_soc_prepare01/observer_recovery01/`.
Read source, its diff against the original checker, and small Host metadata.
No raw CSV/reference read, Host rerun, Spike run, compiler, or DUT invocation.
Read/hash commands completed with rc0; `diff -u` returned expected rc1 because
the successor differs. There is no independent test-execution rc to report.

## State-chain findings

- `checker.py:61-73`: omitted target fflags carries only the explicitly
  recorded zero from helper index 10. The predecessor PC, instruction encoding,
  retirement adjacency, actual CSR event, and source a7 operand are required.
  There is no missing-field default to zero.
- `checker.py:110-146`: state starts empty, saved CSR reads and actual request
  writes supply values, and a per-instruction CSR whitelist applies to all
  21 helper instructions. At index 11 the state must be known and zero.
  Unknown writes and writes on readback-only instructions fail. An fcsr alias
  is allowed only if its full value agrees with both known frm and fflags;
  it cannot silently overwrite or clear the tracked flags.
- `checker.py:222-227`: extraction binds each helper row to the exact ordered
  PC/code window and contiguous retirement ordinal, then performs both state
  and instruction-effect checks. There is no opportunity for an intervening
  flags-clear instruction before the required index-13 readback x6=0.
- `checker.py:303-335`: ledger validation independently reconstructs the state
  chain and then checks exact helper PC/code/order. Both old explicit-target-
  fflags assertions have been replaced, not just the first failing assertion.
- Raw `csrs` dictionaries remain unchanged. Added `observer_csr_before/after`
  fields are derived annotations; validation recomputes them, so they are not
  trusted substitutes for actual row evidence.

The fix is consistent with Spike's write-event logging contract documented in
`CSR_DELTA_REVIEW01.md`. It permits a legitimate absent target fflags event,
but still rejects missing clear, nonzero prior operand, an actual NV event,
conflicting fcsr alias, and missing/nonzero returned flags.

## Oracle preservation and Host evidence

The complete source diff is confined to carrying/checking CSR state and the
associated helper-call signatures. Original setup, bitwise independent NaN
oracle, entire 128-byte result, 144 ordered byte reads, input/seed/mask history,
6720 fixture-field reads, capacity/bootstrap checks, unused-helper PC exclusion,
full destination store, CSR restore operands/writes, exact console, diagnostic
veto, HTIF success, and retirement resource bound remain intact.

`host02.json` reports, for each of call1294 and call1234:

- Explicit-flags and omitted-flags ledger positives, with the old observer
  rejecting the same omission.
- 15 state-chain negatives, all rejected at relevant checks.
- All 33 original baseline negatives retained and rejected.
- One synthetic raw-line omission positive and inserted-NV negative.

`test_host.py:29-57` constructs that raw line from a synthetic witness and
decodes it using the production regexes. It does **not** parse the actual
2.1M-instruction reference. `raw_mutations.py:5-9` now inserts c1_fflags=16
when absent, fixing the old mutation's assumption that the field exists.
These are useful focused tests, not measured full-reference acceptance.
The Host report binds the reviewed checker SHA; this reviewer did not rerun it.

## Bounds and remaining admission work

No loop, source selector, ELF, oracle, or 3M/256 MiB/120 s reference limit was
changed by this observer diff. Full actual-run ledger/exit/pins and both
singles' source fidelity remain subject to the later sealed READY review.
The earlier actual exit metadata remains numeric rc0, timed_out=false,
validated=false for call1294. call1234 had not been dispatched in STOPPED.
This review does not change either record or authorize a rerun.

## Reviewed hashes

| File | SHA256 |
| --- | --- |
| observer_recovery01/checker.py | 783ca239cc93e90dc6579f75ed7f6cc92cd59bce9a1820dbf31ddd08d40f9958 |
| observer_recovery01/host02.json | 0956086ea83ac2562f8533f4b47f3e94d8d2879f3d1bc883a54305af2d1a3832 |
| observer_recovery01/test_host.py | 886e4da5e11354193691a57250c49f7c3dc0beece14bf103bed08ae36cc557a9 |
| observer_recovery01/raw_mutations.py | 49329c84bff150205f08472a3b06e09a4576b0fd27405435abc90e40f33c054d |
| Original check_reference.py, unchanged | 72d276601b3e3d8723ebb0abaf677096e50b09c077f56ec8478d137d86b9539b |
| Original STOPPED.json, unchanged | c649139a4e25a079f7f632b3a884caed15025712bd09cb51d0797317d00126de |

Only the new independent review file was written; producer files were not
modified. No claim of DUT pass, Linux closure, or all-reduction coverage.
