# Negative-Stride Store M6 Plan

**Prepare/dryrun only. No DUT, reference rerun, build, RTL or old sealed-file
change.** After prepared01/ready.json is generated, helpers/Host/plan are
sealed; actual execution still requires new main approval matching that plan.

One source single: `e16_m1_u1_s1_b3_m2_f0_g3`, original diagnostic ELF
07d285218316422ea69480c764c09fe17e7ebca6a49e31c5abc7e4ff6cae5578.
The unchanged prepared SoC ELF is
`../negative_stride_store_original01/software01/soc.elf`, SHA
`bdeaefcb2a25106578d2c78ca4bcb30f634dc73db9a4be03ac1607f2989235fb`.
This is the source-derived real-Sv39 port, not original Linux/parent96.

## Exact Inputs And Budget

- M6 image `/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image`;
  image.json SHA `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
- Reference READY SHA `af47366282d50441056b62740801f754615b31eec82f35083b538bade7a61f65`;
  preserve every original66 pin plus frozen source/image/configuration/imports.
- Actual Aquinas `../store_entry_review01/ENTRY.json` SHA
  `e8f1d31fcf521c988178e20ac07052329d7cb654d66795f2274b03db68e6e55e`,
  decision `ACCEPTED_FOR_WORKER_PREPARATION_REFERENCE_ONLY_NOT_DUT`.
  ENTRY.md SHA `e77981f68f4e0df9d144b25dddb6e39805c1935f2f06e61bdbf1b851e5374cf6`.
  The actual schema/links are checked; no independent raw reparse or launch
  authority is attributed to this entry review.
- **jobs1, sim5400s, worker7200s, service7800s**, no retry/FSDB/build/extension.
  The monotonic worker timer remains sticky through expensive postchecks;
  final publication rejects abort, expiry and fresh disk-plan drift.
- Unit `ara-negative-stride-store-m6-01.service` must directly own the worker
  (MainPID/cgroup), RuntimeMax2h10min, KillMode=control-group, Restart=no.
  Trusted UID user-bus environment is explicit even after runtime sanitization.
- Prepare/dryrun do not query live simulators. Authorized run alone checks
  memory>=32GiB and total simulator capacity24 using existing resource logic.
  `reserved-slots` means unused reservation only; live workers count once.

Reference858371 firmware instructions imply about3773s at273/s plus20%,
below the fixed5400s case ceiling. This is a proxy, not a promised completion
time. A timeout retains progress evidence and is not automatically an RTL bug.

## Store-Specific CSV Contract

`checker.py` binds actual store ELF symbols/PC/encoding09c55c27. It uses the
sealed store reference oracle, not the load oracle. `csv_check.py` preserves
the original ten-instruction store window, capacity3 once, one same-PC fault/
retry, full unused-load-helper rejection, actual CSR context and original
arguments. The fault must be cause15/P-18/start5; retry keeps a0=P+22 and
t3=-8, no adjusted-base double application or helper reload.

RVFI has no vector store payload. When a target store can alter a location,
only that location's cached initialization bytes are invalidated; **real
scalar readbacks** must establish the new bytes. Do not synthesize vector
data from the expected oracle. All other bytes remain checked for unwanted
changes, including the poisoned completed prefix on retry.

- Before fault snapshot fences/page repair, the actual marked scalar LHU
  must observe memory[P+6]=127. Its recorded result is subsequently checked
  against the entire fault-state byte map.
- Backend allocations/completions for this exact target encoding are paired
  by architecture ordinal/VID. Before each handler entry all target-store
  owners allocated so far must be complete. This complements the generic
  CVX/arch/uop ledger, not a count of unqualified valid cycles.
- Lower-page remap/PTE/SFENCE, all2048 refill halfwords, prefix poison36,
  actual MRET and retry are ordered and checked. Final P+6 remains36;
  P-18 becomes166. A replayed earlier store or wrong data ordinal is rejected.
- Four full8KiB scalar scans,64 original outputs/two guards, extra storage
  sentinels, source/input/mask/offsets, neighbors, CSR and17275 comparison
  calls are mandatory. Store-source v24 is unchanged, not a loaded vector.
- Exit is raw CTRL0 at its pinned store PC and only exact parking thereafter,
  not Spike HTIF1. Missing raw PASS, any first failure, extra CVX exception,
  lost completion, wrong ELF/command/seed/cwd/preload or incomplete oracle
  prevents acceptance.

**B-channel scope:** this validates architectural prefix visibility and
same-owner backend completion before fault observation. The CSV does not
contain AW/W/B handshakes; arbitrary delayed-B timing is not claimed. A later
failure may justify a separately authorized focused bus probe, not a new
image or forced internal state. The present worker has no such probe enabled.

## Durable Execution And Approval

The accepted load worker's runtime-name adapter and persistence mechanism are
retained. Historical name and runtime testcase name remain distinct. Actual
numeric monitor outcome is fsynced before parent postchecks, and the returned
child outcome is independently persisted before the strict checker. Neither
unvalidated record is itself architectural PASS. Checker exceptions or a
late abort preserve these original receipts and cannot silently publish PASS.

Preparation and dryrun commands (no simulation):

```sh
python3 replay.py prepare --authorize-prepare --reserved-slots 0 \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image \
  --out "$PWD/prepared01"
python3 replay.py dryrun \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image \
  --out "$PWD/prepared01" --plan-sha256 PLAN_SHA256
```

`prepared01/ready.json` contains the exact direct-service command. **Do not
execute it until main approval.** The pinned approval JSON must have decision
`AUTHORIZE_NEGATIVE_STRIDE_STORE_SINGLE_M6_ONCE`, matching plan SHA/unit,
reference READY, exact `adapter_review_pins` and `budget_risk_accepted=true`.
It is supplied with `--authorize-run --parent-review PATH
--parent-review-sha256 SHA`; no approval is created by this preparation.

Host receipts are `host01.json` and `csv_host01/status.json`. The latter is
explicitly synthetic: actual SoC PC/code plus full oracle in213559 rows,
positive pass and16 rejected altered/missing-event fixtures, not DUT evidence.
Metadata Host covers distinct names, wrong seed/preload/cwd, ELF/plan/budget
drift, actual partial failure-line cancellation, checker-throw receipt
preservation, late cancellation, expired worker and entry/parent gates.
