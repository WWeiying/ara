# Boundary Single-Run Owner

Only `run.py`, `test_run.py`, and this document belong to this runner change.
The ten build02 firmware/oracle files, ELF, old checker, SDK and production RTL
remain frozen. The only allowed pairing is reviewed boundary build02 / SoC03.

## Successor Gate

The actual frozen `cva6_rvfi.sv` does not assert RVFI valid for illegal cause2.
The old `check.py` incorrectly requires those instructions as 12 trapped retires;
its synthetic fixture PASS is not VCS evidence. **Never execute that old checker
as boundary acceptance.** The runner binds James's successor CLI
`--build/--log/--vector/--commit`, which returns one JSON object with
`schema=resident-pv-soc-boundary-vcs-v1`. It uses 21 successful PV retires and
actual handler CSR-read evidence for the 12 faults, with exact attempt
order/PC/cause and unchanged numerical/write/recovery obligations.

Bound SHA256 identities (a change blocks preparation/launch):
- `check_vcs.py`: `6a30948ddf58b08f3a9233b589d88dfee029bcd973facc2e2ee5ac2a3e3fef9e`
- `test_check_vcs.py`: `9f46cfaedc95e426e8ec3744723f1477442706dcd5ce09680a8bf9a3b6e77b0d`

No global checker is changed or weakened. The existing `ara_verify.uvm_dut`
already treats exception counts as informational; it must PASS on the untouched
raw log with zero issues and events/backend/AXI-read/AXI-write all required.
Runner scope additionally binds the 31 PV CVXIF requests and their ten exception
responses; the two FS/VS-off cases must stay CPU-only. Ordinary accelerator
exceptions, orphan responses and fabricated illegal RVFI retires are rejected.
No expected-error filter, assertion waiver, or issue-string whitelist exists.

## Prepare And Review

Once the successor API/hash is reviewed, run:

```sh
python3 -B verification/performance/resident_rvv/soc_boundary/run.py prepare --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_soc_boundary_vcs_20261109_01
```

Prepare performs frozen runner and successor host tests and the readelf/image-contract shell
preflight only, never simv, systemd launch, recompilation, or SDK regeneration.
It snapshots exactly the three new files and pins originals, snapshots, build02
receipt/artifact inventory, SoC03 full compiled image, successor checker, immutable
smoke owner/image helpers, tools, and complete `ara_verify/*.py` inventory.
The prepared state is NOT_EXECUTED and requires explicit parent review.

Parent reviews selection, prepared receipt, preflight logs and source-pins SHA.
The following prints a command only; execution requires separate parent approval:

```sh
python3 -B verification/performance/resident_rvv/soc_boundary/run.py service-command --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_soc_boundary_vcs_20261109_01 --review-sha256 REVIEWED_SOURCE_PINS_SHA256
```

## Bounded Ownership

Systemd directly owns frozen Python as MainPID; the worker checks that and its
expected CGroup before executing children. Dedicated stdout/stderr, control-group
kill, 20-second stop timeout, and a 7200-second service limit apply. Limits are
5400 seconds simulation, 900 seconds global protocol audit, 300 seconds boundary
audit and 180 seconds runtime image preflight. Existing execute helper records
argv/phase/child PID and kills the child process group on timeout or interruption.
There is exactly one ELF execution, no retries, ABBA, successor, or automatic
fallback. An exclusive attempt marker prevents reuse even before simulation.

All original build02 pins/artifacts and full SoC03 image inventory are checked
before and after work; the protocol proof independently binds executable and
compiled .so libraries, raw log, vector trace and ELF. Added image members fail
the full inventory gate. Failures/timeouts preserve terminal result and artifacts;
mutable status/service logs are excluded from stable pins. SIGKILL/service expiry
can leave only the retained attempt marker and systemd failure, never a PASS.

The single ELF contains 21 PV scenarios / 33 attempts plus one QBS/RVV postlude.
Overall PASS needs the unmodified global protocol audit, successor numerical/work
and real handler audit, scoped exceptions, and final identity checks. Host tests,
prepare, smoke/ABBA results, and build-only PASS are not boundary DUT acceptance.
