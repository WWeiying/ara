# Two Original FOF Singles, M6 Prepare Only

Two unchanged SoC ELFs from `../fof_original_two_singles01/READY.json`
(`502c78d6...`) with all 118 original pins. Confucius's actual decision
`3b51f0b4...` and REVIEW `cdaf718e...` accept static source/adapter and reference
metadata only, not an independent full raw parse or DUT acceptance.

Scope: original e8/scenario0 and e64/scenario5 source singles. Each retains the
original 11-instruction helper, 3-instruction capacity query, full initialization,
130 physical output elements, 16 mask bytes, 8192 data bytes, 12288 page-table
bytes and guards. Full original defined checks plus saved/restored CSR values
are mandatory. e8 output indices 5..8 remain undefined; return VL4 is distinct
from restored/store/completion VL8. e64 old-vd is uint64 value 0x5b, not a byte
fill. Unused helper internal PCs, repeated windows and unexpected target traps
are rejected. Only the source completion S-ECALL is allowed.

RVFI scalar reads after the original vector store prove defined output bytes.
No direct vector payload is invented. Architectural target exceptions must be
zero; zero MMU/physical transactions is **not measured or claimed**. No FSDB is
requested. This is neither Linux signal equivalence nor acceptance of all eight
historical FOF ELFs or the parent matrix.

## Fixed Execution Contract

- Frozen M6 image; no build, ELF changes, references or retry.
- Jobs2, each sim1800s, worker3000s, direct owning service3600s.
- Existing 169885/172547 firmware-record references imply about747/759s at the
  slower273 retired/s proxy with20% margin. This is an estimate, not a guarantee.
- Raw failures cancel dispatch and affected live jobs. Timeout alone is not an
  RTL bug. Numeric monitored wait outcome is fsynced before generic validation;
  child outcome is fsynced before case-specific validation.
- Runtime TESTCASE uses the port id. Historical names remain separate source
  provenance. Fresh plan SHA/pins, exact COMPLETE results, no sticky abort and
  raw failure veto are required before publication.
- Runtime cap24 and available memory>=32GiB are checked only at authorized run;
  unused reservations are explicit, live workers counted once. Prepare/dryrun
  do not query live simulators or services.

## Commands

Run Host using `python3 -B test_host.py --out host04` (synthetic Host evidence,
not DUT). Prepare using:

```sh
python3 -B replay.py prepare --authorize-prepare \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image \
  --out "$PWD/prepared01" --reserved-slots 0
python3 -B replay.py dryrun \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image \
  --out "$PWD/prepared01" --plan-sha256 ACTUAL_PLAN_SHA
```

`prepared01/ready.json` supplies the actual service command. Main must provide
a new pinned JSON with `decision=AUTHORIZE_FOF_TWO_ORIGINAL_M6_ONCE`, exact
`plan_sha256`, `unit`, `reference_ready_sha256`, `review_pins`, and
`budget_risk_accepted=true`. No service is launched by preparation or dryrun.
Only new files in this directory are writable; reference files stay immutable.
