# M9 Memory-Owner Checker Successor

## Decision

The reported checker gap was still present. The independent successor implements
the missing source-bound, nonempty memory-owner gate. Offline Host tests and the
original full pin preflight passed. This is checker preparation, not DUT acceptance
or authorization to launch. No RTL, sealed input, reference, old output or original
worker was edited. No simulator, Spike, build or service was launched.

## Existing State

- Original prepared plan SHA256:
  `0e73362c293a7b4937f8a03a580371e0b92c1b3ae21303f50d800af5c19eafdf`.
- No other strided-alignment checker successor was found before creating this one.
- Original `vcs_m9_prepared01` contains only `plan.json`; no launch/complete record.
- One read-only `systemctl show ara-strided-alignment-m9-01.service` returned
  `LoadState=not-found`, `ActiveState=inactive`, `MainPID=0`. Its default
  `Result=success` is **not** historical service-exit evidence. This observation
  cannot exclude an unrecorded earlier, garbage-collected run under another name.
- Separate completed `memory_candidate09_controls16` evidence was discovered;
  this task did not rerun or relabel it as the four directed alignment cases.

## Change

`checker.py` subclasses the unchanged original checker. Every CSV row is passed
unmodified to both the added owner observer and the sealed checker in one traversal.
The original 697/698 scalar checks, complete initialization/results/guards, precise
trap and same-PC retry, saved CSR/readback, target lifecycle and exit requirements
remain enforced by `super().finish()`.

The new observer derives the source path from the actual compiled spec/ELF sites:
seed v24, seed v8, first target, fault snapshot, target retry, result snapshot,
successor load, successor store, next snapshot. These are nine architectural memory
owners, seven of which are non-target helpers. This is a source-derived path, not
an arbitrary total-backend-uop count. Extra legitimate allocations for a single
owner are allowed but must all complete; each nonempty owner must have at least one.

The M9 frozen monitor supplies architecture sequence in `order`, VID in `port`,
and allocation-preserved instruction/transaction identity on completion. The new
gate checks sequence, actual VID occupancy/reuse, exact owner/encoding/transaction,
request/response pairing and fault qualification. Actual memory retirement PCs and
encodings must follow the source path. Returned vset VL, vtype immediate and tracked
actual vstart CSR operand/read values establish nonempty contexts. The first target
setup is checked before the actual handler entry; the sealed oracle independently
requires its precise trap captures. This does not claim direct backend VL signal
measurement: the commit CSV has no such field.

Harmless CSR replay does not require a memory backend allocation. A completed store
need not precede its architectural retirement; the gate does not invent that order.
The original generic trace validator must remain part of the runner admission.

## Offline Results

Executed, actual exit **0**:

```sh
python3 -B verification/fpga/current_board_review/unmasked_strided_alignment_soc_m9_checker_successor01/test_checker.py verification/fpga/current_board_review/unmasked_strided_alignment_soc_m9_checker_successor01/host01.json
python3 -B verification/fpga/current_board_review/unmasked_strided_alignment_soc_m9_checker_successor01/prepare.py verification/fpga/current_board_review/unmasked_strided_alignment_soc_m9_checker_successor01/READY.json
```

- Four actual SoC spec layouts, four synthetic positive protocol controls, **80**
  negative rejections. These synthetic rows are not advertised as DUT or full-data
  oracle execution; no CVX events were manufactured for a Spike acceptance result.
- In all four layouts, removing each of the seven complete non-target alloc/done
  pairs preserves every retire/CVX/arch event, target owner and other uop. The
  existing generic validator accepts all 28 mutated traces and the original target
  state is unchanged. The successor rejects each with the missing helper's name.
- Further negatives cover missing single endpoints, wrong owner/transaction/VID/
  instruction, duplicate endpoints, zero actual VL, wrong helper PC, lost target
  fault and zero retry vstart. Positive controls include VID reuse and a
  zero-destination CSR read with no backend allocation.
- Actual tool command-exit receipts: Host chunk `ca66bf`, exit 0; preflight chunk
  `479fe1`, exit 0 (exec session 38217 completed). No test process remains running.
- **926 pins** verified, including inherited plan inputs, four unchanged SoC ELFs,
  original reference receipts, M9 image/source, frozen monitor/package and unchanged
  M8 control baseline. No raw reference traversal or simulation rerun was performed.

## Review Pins

- `checker.py`: `797d0f0457110ae2b0e9c91b09ff81e7f1d0adf4762fbfc2c01a74c725170092`
- `test_checker.py`: `46fcc4cc8c0c33937da41a0112478f18d0a202a8774200c0552746343fc2f24e`
- `host01.json`: `3a13f5a2da08cbb99179b77aeeae46ed001e87ab8610cdb6cf6c9e2ed2c80574`
- `READY.json`: `bd37b47445dcd99565055ead9f7d8f1303beecd700f7bfdd83284816025f171a`

## Next Admission

Review the successor and bind its exact hash in a **new** worker/plan. The sealed
original worker still invokes the old checker and must not be launched as though
it includes this fix. `READY.json` supplies the closed-CSV checker command template.
Retain all original numeric child-exit, command/private ELF, image/config, generic
protocol, first-failure, pin and fresh resource gates. Keep directed budgets 900 s,
controls 180 s, jobs 2 and service 4200 s unchanged. The already completed separate
M9 normal-controls campaign should be reviewed for reuse rather than blindly rerun.
If an existing directed run is later found, preserve it and use a separately bound
offline successor check of its closed CSV, not another simulation solely for this
postchecker change. New DUT launch remains outside this turn's authorization.
