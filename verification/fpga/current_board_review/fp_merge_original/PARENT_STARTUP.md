# Parent-Reported Startup

Status: **DUT started and advancing, not terminal acceptance.**
This note records evidence supplied by the parent, not a new independent
process/trace observation. No polling, launch, or additional preparation was
performed to write it. It is outside the sealed plan/preparation pin ledger.

- Service: `ara-fp-merge195-candidate04-01.service`.
- Actual M4 `simv` PID reported by parent: `177819`.
- Parent confirmed the exact private ELF and owning service cgroup.
- Parent confirmed actual service runtime limit9600s and control-group teardown.
- Parent approval SHA prefix supplied: `fea33b0b...`; the full digest was not
  supplied in this startup message and is not reconstructed here.
- Sealed plan SHA256:
  `c299582076496a50dbaa7a005c715f00a6a96b1d1e68c8f0438347cf72e1607c`.

Parent's two samples, approximately two seconds apart:

| Observation | First | Second | Increase |
| --- | ---: | ---: | ---: |
| CSV bytes | 1093632 | 1245184 | 151552 |
| Complete trace cycle | 12633 | 14148 | 1515 |
| Retirement count | 9959 | 11315 | 1356 |

This establishes reported startup advancement only. It does not establish
195-call completion, oracle PASS, final exit, or a full-runtime estimate.
The195-call ELF/oracle and757-pin plan remain unchanged and sealed. Parent
owns subsequent terminal inspection; no duplicate launch or ongoing polling
is requested. No further preparation is undertaken while current tests run.
