# Actual M6 Startup

Status: **two real M6 simulations started and progressing, NOT DUT PASS**.
No further polling is scheduled by this agent. The worker automatically
performs each terminal CSV/oracle check and stops on the first failure.

- Service: `ara-negative-stride-remaining38-m6-02.service`.
- Worker PID: `1944549`; direct owner cgroup checked.
- group00 simv PID `1945454`: cycle67513 ->69053, retire55336 ->56656.
- group01 simv PID `1945453`: cycle67602 ->69143, retire55409 ->56730.
- Observed executable: frozen candidate06 `campaign/image/_build/vcs/simv`.
- Both actual private ELF hashes, working directories, testcase names,
  NO_FSDB flags and private CSV paths matched. Two-second startup sample only.
- Complete original10-group order is retained: 9x4 + 1x2 =38 source singles.
- jobs2; per-group simulation timeout10800s; separate terminal checker bound900s.
- Five-wave worker bound58500s, service RuntimeMaxSec59400s,
  KillMode=control-group, Restart=no. No DUT build or automatic retry.
- Estimated four-case simulation duration167-172.3minutes, last two-case
  group86.1minutes; approximately14hours total at jobs2 before postchecks.
  Estimates use measured M6 throughput plus20%; they are not guarantees.

## Frozen Evidence

| Artifact | SHA256 |
| --- | --- |
| `../READY.json` | `07ed5a60755b197b907cfbaf2038692093e357b2e7c2149b51106944af14d2c4` |
| `../REPORT.md` | `dbb1a20adb0ebd114582d1ead8815b2364d86bbd249851b85ecf0072a7522aa4` |
| `prepared01/plan.json` | `7be8022de6dda35da836fede4e907d31c9e329a1e7608a8c080a70a81aeb76d1` |
| `prepared01/startup_confirmation.json` | `e0db32b9367276d691930e168bf1d76d0be154f175b80b0e35f2c375c311ba23` |

Plan pins1229 inputs. Host CSV9 (unchanged checker/source, original receipt
reused), successor runner Host9 and exact10 dryrun passed. All38 Spike
references accepted with actual numeric waits0,650641 scalar checks and
62318070 firmware commit records. Source/ELFs/reference pins are unchanged.

`prepared01/complete.json` is the future worker terminal record, not an
already observed PASS. Original child and monitor numeric outcomes are saved
before postcheck; raw logs, private ELF and CSV are retained on failure.
Terminal acceptance requires full38 membership, exact counts/CSRs/data,
raw failure veto, successful child/observer exits, no abort and unchanged pins.

Intermediate undefined fault suffix is not forced to an initial value.
Completed prefixes, inactive/tail/neighbor/guard state and final full64 results
and8KiB memory remain checked. Preserved earlier fault snapshots can retain
their original undefined suffix even at the final checkpoint.

Plan01's pre-DUT user-bus startup failure remains intact; see
`STARTUP_RECOVERY.md`. No testcase was dispatched there. This new service
does not restart an existing simulation or change sealed plan01 files.
M7 boundary acceptance is separate. No Linux/full-parent closure is claimed.
