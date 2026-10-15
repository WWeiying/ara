# Original Remaining Nine

Software-only preparation of the canonical RVV-07 reduced singles. Excludes
already covered e32/m1 and separately active e16/mf4. No RTL build, DUT launch,
live-job query, original archive modification, or old reference rerun.

## Exact Scope

| Shape | Capacity | Requested VL | Input bytes | Mask load bytes |
| --- | ---: | ---: | ---: | ---: |
| e16/mf2 | 32 | 16 | 64 | 4 |
| e16/m1 | 64 | 32 | 128 | 8 |
| e16/m2 | 128 | 64 | 256 | 16 |
| e16/m4 | 256 | 128 | 512 | 32 |
| e16/m8 | 512 | 256 | 1024 | 64 |
| e32/mf2 | 16 | 8 | 64 | 2 |
| e32/m2 | 64 | 32 | 256 | 8 |
| e32/m4 | 128 | 64 | 512 | 16 |
| e32/m8 | 256 | 128 | 1024 | 32 |

Each source selects scenario3/l4/mode3/rm0/op0/sticky0. The archived selector is
unchanged, including every surrounding loop and its post-target work. Each
program traverses all3360 bank1 fixture rows (6720 field reads), initializes
8*capacity input elements and512 seed elements, fills215040 mask bytes, calls
one original21-instruction helper and executes144 original output-byte checks.
The original full Linux child has6720 operation calls; these singles do not
accept that full child or establish additional independent RTL roots.

Canonical: handoff03/rvv_small_redspecial02. `manifest.json` binds inventory and
archival hashes; each sourceproof compares01/02/canonical files, both archived
ELFs, original C plus exact selector, and all21 machine encodings for all three
helpers in each actual software ELF. The only C port is the sealed integration
wrapper adapter. Shared batch scripts are new and are not imported by active
VCS runners. Existing source/reference/runner seals are untouched.

## Reference And Checks

Explicit uniform actual profile: `rv64gcv_zfh_zvfh_zvl1024b`. One reference
attempt per ELF, sequential first-error stop,3M steps/256MiB per raw file/120s.
No retry or automatic limit change. These are reference limits, not DUT budgets.
Each compiled normal-path conservative upper envelope is2,129,632..2,562,144
instructions. `static_admission.json` and per-shape static_cost.json bind actual
mask CFG (1,612,800 instructions), seed32-byte memcpy and12-instruction callsite,
complete loop controls, startup, fulloracle and generous input-init slack.
The exact input binaries have no input memcpy calls. Bytes/walltime remain
independent hard bounds, not a static performance guarantee.

The shared checker validates the exact five Spike boot instructions separately
from firmware. Unused helper PCs are all forbidden; op0's21 retirements must
be consecutive from its one entry. Original capacity is one contiguous3-step
window; actual RVV PCs are restricted to capacity and op0. Seven original CSR
prelude sites and the helper's save/request/read/restore sites are phase-bound.

Raw scalar stores are checked by original address/order/value for every input,
seed and mask fill, not only counted. Snapshot is taken at helper entry. Full
v8 register groups, exact mask-load footprint, seed m1 and old-vd128-byte loads,
NaN/NV16/vstart0, restored frm/fflags, complete128-byte output store and all144
LBU oracle reads are mandatory. e32 initializes256 seed bytes but loads128;
e16 loads128. Bank1 identity uses actual addresses even where bank0 has the same
NaN/NV numerical tuple. Post-HTIF only the original empty park is allowed.

Each shape has13 native original-C oracle tests. Its historically named bank0
mode is only a missing-NV mutation, not a bank identity proof; the raw checker's
wrong_bank_same_value test verifies wrong addresses even with equal results.
Shared checker preflight03 contains20 ledger checks,62 illegal helper-PC tests with authentic boot prefix,
and3 malformed/repeated boot tests per shape. Reference raw receives the same
ledger checks after extraction. These are Host checks, not architectural runs.
Actual capacity CSR state seeds vtype tracking. Spike does not rewrite vtype
when unchanged, notably e16/m1's first helper vset. Positive Host witnesses
omit unchanged writes and negative cases remove/corrupt the capacity state.

Commands, once only:

```sh
python3 -B prepare.py
python3 -B static_cost.py
python3 -B test_host.py
python3 -B reference.py prepare
python3 -B reference.py run
```

Exclusive attempt sentinels and create-only records prevent reruns. Any first
execution, parser, oracle or pin failure writes STOPPED.json and stops remaining
dispatch. A successful batch writes READY.json with pending-independent-review
status. No reference result is labeled a DUT or full-Linux PASS.
