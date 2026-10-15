# Original e16/mf4 M6 Checker Successor

Prepare only. Same source/SoC ELF/reference/M6 image, same5400-second case,
6600-second direct service, jobs1, no FSDB/retry/build. No live VI0 query.
The old plan and all reference READY/CONFIG/pins remain unchanged.

## Old Plan Not Admitted

`PREDECESSOR_STATUS.json` is a separate record marking plan01
`a9a60cc30f3d88d4b15441ec3d2da2bd7367f9334c9cb36731b262bbade50d3e`
as **NOT_ADMITTED_CHECKER_GAP**. It does not edit that seal. Hilbert's retained
`../original_e16_mf4_vcs_m6_plan01/independent_entry_review01/` proves the gap:
extra op1 `vfredmin` at0x80000754 or op2 `vfredmax` at0x800007a4 passed the
generic, strict and full artifact gates after all original144 output checks.
Entry-only exclusion missed instructions reached inside an unused function.
This was a checker counterexample using synthetic Host CSV, not a DUT failure.

## Static State Review And Narrow Repair

Every retired PC/encoding still must match the real pinned SoC ELF. The exact
original helper ranges come from the archived-byte-equivalent21-instruction
windows, with exclusive high bound immediately after the final return. **Every
instruction address in both unused op1/op2 ranges is rejected**, including
integer, CSR, load/store, return and vector instructions, not only entry/target.

Normal source phases are now explicit:

1. Startup CSR writes mie/mtvec/mstatus/fcsr/vstart, then wrapper vlenb and
   original-C vlenb reads: exact seven PCs/encodings, in order, one time before
   capacity. Both actual vlenb reads must return128. No blanket CSR prohibition.
2. Original capacity's three instructions execute consecutively once, including
   AVL=-1 and actual e16/mf4 VLMAX16. No interior entry or later replay.
3. Original scalar loops and fixture initialization remain fully checked.
   op0 starts at its actual entry only after the complete prelude/capacity,
   follows21 consecutive retirements once, and closes at its return. Every
   op0 internal PC is illegal outside that active window.
4. All RVV retirements are allowlisted to capacity's single vset and the ten
   original op0 RVV instructions; every allowed PC occurs once. Helper CSR
   save/read/write/restore PCs are legal only in their proper21-step window.
5. The original144-byte oracle, all remaining scalar loops, original CTRL exit0
   and only the original side-effect-free park remain mandatory.

CVX requests/responses do not advance architectural retirement state. The
unchanged generic trace validator checks their transport. Matched extra
requests/responses cannot legitimize an unauthorized retirement.

All old original args/input16/seed64/mask64/output144 checks,3360 fixture rows
and6720 field reads, original store counters, returned NV16/vstart0, packed
flags, saved frm/fflags and restore operands remain. Data/store correctness
uses the full scalar oracle; no CSV-only vector-payload or waveform claim.

## Host And Provenance

Retain all31 old Host test methods. Their synthetic positive setup now includes
the actual seven CSR instructions and full three-instruction capacity, rather
than the old abbreviated capacity entry. No source, ELF or oracle is reduced.
Ten new tests cover the two measured vector-interior gaps through generic+
strict+full artifacts, unused integer/return interiors, op0 internal execution
before entry/after return, capacity entry/internal replay and misplaced
vlenb/startup-vstart CSR. All are Host-only protocol fixtures, never DUT results.

Same canonical SoC ELF:
`eed20f08a98ac66766a66810b6f5f8fc829d0603477d37b3d59d48c32669f162`.
Same accepted reference READY:
`f858249f61dc7b9c4e3507f78bb483543d0439ef74942e838fc1251931a661de`.
Independent REVIEW:
`d9ad719158b37c9a1c1788b1e44fab5f84f06bc0d50a601128d8322cee91dc4c`.
Independent **result.json**, not audit.json:
`a0cfeb4214f5569092f6acf9cfd4c9539e275b5699e319aa2e36e0d567ba8678`.

The actual reference profile includes Zfh+Zvfh and is not exact-minimum-profile
acceptance. Independent raw review found zero scalar-FP consumers. Approval
history is parent coordination, not invented direct-user ISA instructions;
program correctness rests on source/ELF/raw/oracle evidence, not attribution.

## Fixed Runtime Contract

The runner is copied to this new owner directory with a new service name
`ara-redspecial-e16-mf4-original-m6-02.service`. It retains raw partial-DETAIL
immediate veto, private input/image pins, sticky cancellation, COMPLETE/exact
membership, terminal fresh disk-plan/hash validation and atomic no-abort
publication. Run still needs a new exact-plan parent review and direct service
ownership with trusted user-bus environment. No prepare path queries resources
or launches a simulator. Runtime cap24/32GiB admission remains deferred to a
separately authorized run; only unused reservations are added to live counts.

Reference1858335 instructions includes1612800 scalar mask-loop instructions.
About47min is a parent planning estimate, not a guarantee;273retired/s would
exceed the fixed5400s. No budget or oracle adjustment follows a timeout.

```sh
python3 -B test_host.py
python3 -B replay.py prepare \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image \
  --out "$PWD/prepared01" --reserved-slots 0 --authorize-prepare
```

Stop after Host/prepare/freeze and submit to Hilbert for independent entrance
review. Neither old nor successor plan is authorized for launch by this work.
