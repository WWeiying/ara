# Indexed LOAD Misalignment Recovery, M8

New Sv39 software boundary, derived from the already accepted indexed STORE
fixture. Not an original Linux replay or original16 root-closure claim.
The sealed20 worker, its source/pins, and all earlier results are unchanged.

## Architectural Contract

- `vloxei64.v v24,(a0),v16,v0.t`, e64/m1/VL5, tu/mu, initial vstart1.
- Predicate0x17: e0 is prestart, e1 completes a mapped prefix read, e2 faults
  at0x40000011 (cause4/vstart2), e3 is inactive, e4 is later active. Tail e5..15.
- All target pages are mapped/readable; there is no page-fault repair or delay hint.
- The fault snapshot checks complete v16/v23/v25/v20/v8/v17, v24 prestart e0,
  completed prefix e1, inactive e3 and tail e5..15, plus all buffer guards.
- ONLY fault-snapshot v24 e2/e4 are undefined. Their16 bytes are omitted from
  the snapshot value oracle, not replaced with assumed zero/old values.
- Handler first reads vstart, snapshots registers/full8KiB memory, poisons the
  prefix backing word, repairs only index2 from17 to16, restores saved vstart2,
  and MRETs to the same PC. It must not reload the committed prefix.
- Retry must read only0x40000010 and0x400000a0. Final v24, all six other full
  registers/tails, guards, full8KiB memory, all12KiB PTEs, flags, vstart and14
  explicit CSR restore readbacks are strict. No final-result undefined holes.
- Different-owner indexed store, masked load and complementary masked add
  follow retry and are included in the complete final oracle.

## Actual Software Results

`reference_load01/READY.json`: HOST_SPIKE_PASS_NOT_DUT, one Spike invocation.

- Actual reference rc0,3.175724s,175070 raw commit records/175069 nonpartial.
- All962 checks, cause4+S-ecall, two same-PC target attempts, HTIF1 exit.
- Whole-memory checkpoints32584/32576 constrained bytes. The16-byte difference
  from the STORE-derived snapshot scope is exactly the two undefined elements.
- Host2544 formula rows. The34 oracle policy checks comprise30 rejection tests
  and4 positive arbitrary-value tests for undefined fault-active destination;
  final e2/e4 corruption remains explicitly rejected.
- ISA rv64gcv_zfh_zvfh_zvl1024b;500000 instructions,120s,128MiB raw hard limits.
- SoC ELF SHA `24340386eead9bbe3a85e1b4ab6a54f6f5ac3353d14733189445b2f2e69e710f`.
- Raw SHA `57072c5c0e0a4abee1d304b8a3630c47d7a4ccffc2d14846685c11755341d273`.

`host_actual_reference_bridge02/result.json`: the same already closed reference
drives every scalar row through the actual DUT checker, all962 checks and14
restore readbacks, with5 additional rejection tests. Its pseudo-cycles and
HTIF1-to-CTRL0 Host endpoint adaptation are explicit, NOT RVFI/DUT evidence.
Bridge01's module-name collision failed before raw parsing and remains saved;
bridge02 uses an explicit local import. No Spike/reference rerun occurred.

## One Background Run

- Service `ara-indexed-load-m8-01.service`, submitted once; Restart=no and
  KillMode=control-group. Output `vcs_m8_load01/`, local append-only service log.
- Plan SHA `29489578cd804e254cfff89d3a58920d6afd860dc4670602a9feb0af8ce62313`.
- Same accepted M8 image SHA
  `bd27bf6f7bb90b2b05c4546faaed8a8e32b8e545c182167fef72c170e40bdfd0`.
- This does not start a fourth simulator alongside sealed20's three workers.
  It uses inotify CLOSE_WRITE/MOVED_TO for that campaign's complete.json,
  bounded6600s, then requires exact20 PASS, durable numeric child rc0, no abort,
  no retry, unchanged pins and absent predecessor simv before admission.
- Unique LOAD simulator budget900s, no wave, no build, no retry. Outer8000s
  includes the predecessor wait; it does not extend the900s DUT allowance.
- Actual child returncode is saved before postchecking. Acceptance requires
  raw success/finish, unchanged full962-check checker, post-run hashes and no
  cancellation. Any predecessor failure/unknown outcome holds without a DUT.
- The worker records one45s+10s startup CPU/trace-growth observation after actual
  simv launch. No manual simulation polling or active CSV analysis is needed.

Status must come from `wait_started.json`, `launch.json`,
`startup_observation.json`, and ultimately `complete.json`; reference readiness
and service submission alone are not DUT PASS or proof of simulator launch.
