# NF7 M6 Plan02 Independent Entry Review

**No blocking findings. Accepted for future admission only; no DUT launch approval.**
The plan01 P1 is resolved by this pinned successor. Actual NF2 terminal acceptance,
fresh resource admission and a new parent authorization remain mandatory.

## P1 Resolution

- `nf2_gate.py:70` requires the exact evidence schema and fixed NF2 plan/prepared/result
  paths. Replaying the prior HOLD's exact payload rejects with
  `Exact independent NF2 evidence schema required; no text attestation` before any
  terminal file read. No actual NF2 gate/admission was executed in this review.
- `nf2_gate.py:155` first rejects nonaccepted/stale independent results, then invokes
  the byte-pinned actual auditor `admission()`. That unchanged function verifies all10
  members, real COMPLETE/run/summary, durable strict-integer rc0, retries0/noabort,
  original source/current M6 identities, exact commands/private ELFs, original oracle
  reports/raw-log veto, complete evidence-pin membership and current hashes.
- `nf2_gate.py:88` checks accepted status AND boolean true, exact complete/plan/prepared/
  parent/image binding, full verified-map equality with freshly admitted evidence,
  coverage40 with prior pilot4, all10 independent case reports and numeric0 audit exits,
  lossless-row counts/digests, unchanged generic/strict reports and exact aggregates.
- Required wait evidence is content-checked, not only hash-attested: actual audit exit0,
  invocation PID and exact command/prepared/complete, successful wait completion,
  matching result/review/complete SHA and output-log hashes. Every acceptance payload
  and case-result/exit/log dependency read by this layer is returned in approval pins
  and reverified by the parent worker before final publication.
  Outer service rc remains null/UNKNOWN; no PID/GC inference is introduced.
- `replay.py:149` invokes the gate in a separate interpreter, so NF2 imports cannot
  replace NF7 checker globals. Parent review SHA is rechecked afterward; dynamic NF2
  evidence pins join the final verification. Real CSVs may be hashed at future
  admission, but are not parsed by the gate. This review read none of those artifacts.

## Scope And Worker

- All878 plan02 pins match before/after;908 review pins including24 dryrun commands.
  All840 sealed plan01 pins still match. Current M6 has539 frozen source files/66
  image files, with exact image/snapshot/configuration identities.
- Cases equal plan01 exactly;24 byte-identical original SoC ELFs preserve groups0..23
  and trials0..95:284816 comparisons,168 checkpoints and168 trap records.
  The checker/observer are byte-identical; original CSV oracle/reference/ledgers remain
  pinned to prior acceptance, including fractional tails, guards, memory, partial-field
  allowances, restart/prefix poison, trap and CSR context. No source/oracle reduction.
- AST comparison confirms unchanged simulator outcome persistence, monitor wrapper,
  failure/abort/timer/terminal handling, direct service ownership and runner options.
  Only contract validation, preparation and authorization functions changed, plus
  isolated prerequisite wiring and successor unit `ara-nf7-current96-m6-02.service`.
  Jobs4 and2400/2700/16200/16800-second limits are unchanged.
- Existing Host58 and24 dryrun records verified, not rerun. The30 NF2 tests include
  false/partial/stale schemas, nonzero/boolean exits and retry values, missing/drifting
  pins and wait/result mismatches. Their positive fixture is explicitly synthetic,
  not architectural acceptance. Only the old P1 schema rejection was directly replayed.

## Exact Evidence

Plan: `eebd310b9b9ccdf5b5ca398d556b2a7b6d07746c0f4149972130716ab7481cc0`.
Ready: `d212cd10f4e25293ea4780997601f57ca71863149f6f9082a007c2f19d49234a`.
Image: `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
Worker: `40f5540b211c8ee9e8ef6a0d134c86e4888b32de64d607f5a441774cde924c50`.
NF2 gate: `b3757b9eda73298d4bc6ba5047e5e46f830ba8f3e3bb2098652edc3ac2f42a3d`.
Evidence: `47c877980b5383ec4c538a73ae5afbd3df74e14c772d191b1b561247d2c15626`.
Verified pins: `01244cad138f92da56645ffd1336ce4f87b003ecba87a699c78b7b709412f8a9`.

Actual command: `python3 -B .../nf7_m6_entry_review02/verify_entry.py`.
Actual exit0,6.336617s; exec session19058 completion chunkca3d7b.
No active NF2 output/CSV read, process/service query, simulation/reference/build,
Host-suite/dryrun repetition or sealed-file edit. Existing NF2 event audit untouched.
This is entry review, not M6 NF7 PASS or original Linux failure closure.
