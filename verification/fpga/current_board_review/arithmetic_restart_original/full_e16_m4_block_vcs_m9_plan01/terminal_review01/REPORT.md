# e16/m4 Terminal Metadata Review

Verdict: ACCEPTED_M9_ORIGINAL_E16_M4_FULL4095_NOT_LINUX.
No blocking metadata or identity discrepancy found. Parent may incorporate this acceptance into its inventory after its review; this report does not edit the ledger or increment a global count.

## Binding And Actual Outcomes

Plan SHA e009a0cf87c3d818d688e17873b882ccb1fd780ae946dcacb1bff43c02b0e095 matches launch, complete and collector. Entry approval remains f465ca9625db06535e5cefd931c2cec14e512c1b8ac762ed28c64077e27e0f9e. Original SoC ELF and private input.elf both bind SHA3bbb10ca814fd46c66dff89dd6604c0238c957fe0d7ff6ce86275c356e511a56. Frozen M9 image48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a and snapshotda19a3f298adc7453600db2cc931693a5329e2ad593569136bc0b797578cbe6e remain bound.

Freshly checked829 unique non-CSV plan/evidence/approval pins, all matching. Actual monitor rc0/7082.896850509569s, no timeout/failure/cancellation; exact command uses the M9 simv and this case's private ELF, seed1, NO_FSDB and private trace path. Complete reports PASS, retries0, abortedfalse. Actual ExecStopPost service evidence is success/exited/0, not an inferred exit. Collector PID3356762 actual wait0/11.603272153064609s, no timeout/retry. Collector binds exact complete and strict report hashes. No firstfailure/STOPPED/abort marker was found in the closed prepared directory; no live process query was performed.

## Full Shape And Existing Semantic Evidence

The pinned spec is SEW16/LMULm4/CAP256, physical4, vtype10. Each output is516 bytes with typed16 sentinel005b:64 full LDs at offsets0..504 plus the4-byte tail at512. This is not e16/m1's132-byte or mf2's68-byte footprint. Existing full strict report contains4095 ordered calls,1048320 results,8190 guards,4095 zero-vstart returns,13*4095=53235 helper instructions and65*4095=266175 reads. Checked every call-ledger entry has all65 read indices and returned_vstart0; no missing entries.

Generic/strict metadata agree on1838995 rows,1657720 retirements and last cycle11084933. Existing six-event validation reports45047 CVX requests/responses/architectural owners,23067 alloc/done, zero replay/exception. Inspected all45047 owner-ledger entries: alloc==done for every entry and alloc>0 for every required owner. Required scope is20475 setup-memory helpers +2592 targets =23067, including117 op24 targets;18 exact VI2 slide-up targets are legally optional. This is per-owner evidence, not acceptance by a total count alone.

Strict report SHA0c28ea343d0dd70105c1c1f92373e8c81af135b4aeace2667eb676a0076a6ecf binds existing full CSV SHA4639e7cb00860a8b41ba32bc98abad00d3e7e12e996b0d7617fe41d4ac0a59df. This review did not read, hash or reparse the CSV, rerun reference/VCS, or query processes. It consumes the previously executed full checker and collector evidence, not a new semantic parse.

Host01 remains actual rc1/4.476159656886011s,0 tests, fixture KeyError18. Its cause and code snapshot are retained; Host02 actual rc0/250.70392133807763s is separate. No failure was relabeled. No original Linux historical stall, fflags result oracle, other shape, or other image is accepted here.
