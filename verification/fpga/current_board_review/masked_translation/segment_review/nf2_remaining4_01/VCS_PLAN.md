# NF2 Remaining Four: Prepare Only

One private SoC ELF, four exact singles, original source identities in
`source_manifest.json`. Reference READY is separate from DUT admission.
No Linux sigframe, full parent matrix, or completed DUT claim is made.

`replay.py` reuses the frozen generic merge runner read-only. Only its in-memory
case/checker/service bindings change. `checker.py` maps a copied case's runtime
`original_name` to `nf2_remaining4_sv39`; historical names remain pinned in the
plan. The actual execution wrapper persists numeric child rc, elapsed time and
command identity in `child_outcome.unvalidated.json` BEFORE artifact validation.
A checker exception never turns that record into architectural acceptance.

One M6 job, parent-fixed 6300s case / 6900s direct service, no build/retry/FSDB. This is a new
pre-execution budget, not a timeout increase after a DUT failure. Reference has
1,315,037 parsed records; 273 records/s plus 20% gives 5780.4s. Fault attempts
and workload mix make this only a conservative planning proxy, not a guarantee.
Earlier same-family reference/VCS scaling suggests a shorter runtime; do not
claim that ratio proves this job can finish. Stop on first failure, no retries.

Preparation and dryrun perform no live process/service queries. Actual launch
requires a new plan-SHA-bound parent decision `AUTHORIZE_NF2_REMAINING4_ONCE`,
explicit acceptance of independently pinned reference REVIEW/result evidence,
budget-risk acceptance, exact M6 image/source pins, direct service ownership,
and the existing cap24 / free-memory resource check. `reserved-slots` counts
only unused external reservations; launch coordination remains with parent.

The CSV observer enforces original target encodings, retired firmware PC/code,
full firmware scalar oracle counts/equality, six handler records, same-PC
restart, exact start2/5, both-field completed-prefix poison, sequential 2048-word
refills only for unmapped cases, eight checkpoints, PTE/CSR/guard state and
CTRL exit0. The two nofault cases must have only the S-ecall handler and a
precleanup checkpoint; repair/refill cannot precede that check. RVFI does not
expose vector payload, so full output/memory evidence is from pinned firmware's
complete scalar oracle, not invented CSV vector writes.

Host synthetic rows are checker tests only. The source/reference input pins
and originals are immutable; the new observer/worker are independently pinned
in the prepared plan. Generated service command is NOT executed here.

```sh
python3 -B replay.py prepare --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --out "$PWD/prepared01" --reserved-slots 0 --authorize-prepare
python3 -B replay.py dryrun --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --out "$PWD/prepared01" --plan-sha256 PLAN_SHA
```

The exact future direct-service command, new review placeholders, plan SHA and
pin count are emitted in `prepared01/ready.json`. Do not run without the new
parent authorization. No independent acceptance is fabricated during prepare.

Actual reference audit is `../nf2_remaining4_reference_audit01/`: REVIEW SHA
`47fc85fe429f9be67ae48b5c0bc73b979a808ed60e6750e5bdf21b954abab582`,
result SHA `f7c60873358baeeea6d8a0798a6ec8e0bdf5ad0f9daeb2750784ec0f23c918e6`.
Its status is `ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT`, not worker acceptance.
The old metadata Host01 error (str passed to Path-only SHA helper) remains
recorded; subsequent Host outputs are fresh files, not overwritten results.
