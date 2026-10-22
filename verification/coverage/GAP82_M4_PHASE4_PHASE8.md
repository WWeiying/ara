# GAP82: M4 activation phase4/8 directed coverage

## Purpose and evidence boundary

This test extends the phase12 witness with two specific alignment combinations,
not additional random seeds. Processor RTL and the frozen VCS image are unchanged.
The inputs are known native Q5_K/Q8_K fixtures, not captured model activations.
Host preflight cannot establish RTL correctness or measured coverage gain.

## Static prediction

Both commands use M=4, N=1, K=256, DIRECT and M4-interleaved activation data.
The custom instruction word is `0x06b5045b`, with VL=1.

| Activation address mod16 | First boundary range offset | Saved native offset | Remaining mask | Condition raw index |
|---|---:|---:|---|---:|
| 4 | 140 | 35 | `0xfff0` | 408 |
| 8 | 136 | 34 | `0xff00` | 404 |

The scope is block adapter bank0, condition checksum `2250470448`.
Both target bits are zero in the historical687 aggregate and in the actual
GAP81 single-test VDB. This latter check only prevents duplicate targeting;
it does not admit GAP81 into the aggregate. Pending-mask predictions assume
no older pending-bank interference and must be confirmed by actual coverage.

## Independent preflight

Artifacts: `verification/out/gap82-m4-phase4-phase8-preflight-20261006-02/`.
The native-byte oracle independently checks integer MAC, Q8_K bsums and M4
packing. The host test passes 44 checks and rejects 44 injected faults.
The DUT contract differs intentionally: 17 checks per command and 41 final
checks, with complete VRF, initial-state, CSR and source-buffer guards.

The parent session independently ran:

```bash
python3 -B verification/tests/admit_gap82_m4_phase4_phase8.py \
  --preflight verification/out/gap82-m4-phase4-phase8-preflight-20261006-02
```

Result: host-reference-only PASS. ELF SHA256:
`7b68a1a8e4f5f9e72beb19726024f54ea8dab1e4fd5b3ccdc6a94d08d9af5c7f`.

## Pending RTL acceptance

The runner must distinguish two command activities, validate both retire PCs,
request/response and allocation/completion conservation, exact destination
writeback, and the full-state DUT selfchecks. Only a completed successful run
may enter a PASS-only coverage input list. A target miss is not itself an RTL
functional failure, but does not substantiate the predicted coverage gain.
No measured RTL result or aggregate percentage is claimed here yet.

## Actual launch

The independent service `ara-gap82-old-image-20261006-01` started the frozen
`repaired-aligned-build-20260930-01/sim/simv` with this ELF and
`-cm line+cond+fsm+tgl+branch`, timeout 600 seconds, FSDB disabled.
Output: `verification/out/gap82-old-image-20261006-01/`.
The parent confirmed runner PID2333145 and simv PID2333554 were live; the
agent observed both commit and vector trace growth. This is launch/progress
evidence only. Final functional acceptance and raw408/404 hits remain pending.
The single-test result will be kept separate until accepted for aggregation.

## Offline acceptance and measured gain

The initial runner completed simulation but saved FAIL because it incorrectly
required backend activity VL=1. The pinned old dispatcher instead sets the QBS
reservation length to `qbs_m * (VLEN / 32)`: 128 for this M4 configuration.
This internal request length is not the software architectural VL CSR.
`gap82-offline-verified-20261006-01` binds that historical dispatcher and checks
both complete 512-byte destination groups, both command lifecycles and the
41 final software checks. Offline acceptance passed without RTL changes or a
simulation rerun. The original FAIL remains unchanged.

Both raw408 and raw404 are hit in the actual single-test VDB. The parent
collected its raw bitmap and compared it against the completed GAP81 688-test
union. New condition bits: adapter bank0 40, payload bank0 117, adapter bank1 16,
payload bank1 68, total241. Line, branch and FSM gain are zero.
These are diagnostic positions, not official DVE percentages.

The original combine preparation referenced the failed GAP81 DVE predecessor.
Although its member list is identical, the parent regenerated preparation with
the completed `gap81-dve-only-retry-20261006-01` baseline, in
`gap82-combine-complete-baseline-20261006-01`. Its proposed list contains689
test VDBs plus the design VDB. A completed combined DVE report is still required
before publishing this as the new aggregate.

The parent then executed `combine_gap82_bitmap.py` against that completed
baseline and prepared list. It checks original metric hashes before and after
the union, parses only the new single-test VDB, and combines it with the existing
688-test bitmap. The output `gap82-raw-union-689-20261006-01` contains the exact
690-line input list, combined bitmap, measured241 condition-bit delta and
provenance. This avoids repeatedly parsing the entire historical XML corpus.
It remains a raw diagnostic union, not a completed DVE or waived report.
