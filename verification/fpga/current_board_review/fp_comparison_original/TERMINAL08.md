# FP08 Independent Terminal Recheck

Accepted scope: exactly two original 130-call prefixes, 260 target calls on
candidate04 (M4). This is not acceptance of either full original parent,
the held682 alias prefix, or all942 prepared calls. No simulation was launched
or repeated for this audit; fixed2 was not polled. Existing terminal files,
plans, runners and sealed inputs were not changed.

## Raw Acceptance

Read-only Python `-B` imports reused only the no-write contract, identity,
hash, console, CSV and terminal-input validators. Both entire CSVs were
revalidated with the frozen M4 `ara_verify.trace.validate_trace`, not merely
accepted from the driver's PASS label. Independent source/tuple and CSR scans
supplemented those validators.

- `candidate04_restart_run04/complete.json`: exact two PASS/rc0 results,
  status `PASS_2_ORIGINAL_PREFIXES_260_CALLS_M4`, `aborted=false`, finished
  `1791721486.1324906`; SHA256
  `ef2eb50bdf0e4f4eb35e9af794d2fdf26cca99286623723818507265ab650747`.
- `replay/run.json`: COMPLETE, exactly `PASS:2`, jobs2, correct frozen simv.
  Summary membership, rc0, artifact paths and both recorded runner evidence
  hashes match. No interrupted/cancelled result was counted.
- Both consoles contain exactly one original
  `RVV_FP_COMPARE_PASS sew=16 cases=130 errors=0`, their exact BOARD_CASE_PASS,
  BOARD_REPLAY_PASS, tohost0 success and `$finish`. Strict raw failure veto
  and the frozen runner failure regex both found no failures.
- Both private `input.elf` hashes match the original prepared SoC ELFs;
  command.json selects exactly that private PRELOAD, frozen M4 executable,
  and separate expected work directory.
- All2750 plan pins were rehashed unchanged, including original sources,
  executed helpers and frozen image inputs. Image identity verification
  rechecked snapshot, compiled-source manifest, configuration and image files.

Plan SHA256: `011540f110776d0c9296924f6d677f6c43ce8619ebaabd1f4b93d8f77b5b054a`.
Approval SHA256: `f60b02bef9fb251da06fa2093f4c6da97c95cbbd591a3eb86ba5964cd536ad2d`.
M4 image.json SHA256: `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.

## Original Scope and Oracle

The parents are `rvv_fp_compare_restart_e16_m2` and
`rvv_fp_compare_restart_unmasked_e16_m2`. Their archival ELF hashes match
the byte-identical original rebuilds:

- Masked: `a6252640e00b2dcf9562eaea163d06f9c3847c5aa70cad110e3962ca958cde65`.
- Unmasked: `54c642f02d9ea0b036b0d4004553250af50001095b3a69fe055f796b8587d76e`.

Original assembly matches the archival files. Re-enumerating the authentic
loop order reproduces each exact130-entry call_sequence.json: capacity128,
seed0/op0, first VL0/start1 and last VL64/start32/mask0/sticky0. Each has
66 initial-sticky0 and64 initial-sticky1 calls. Only the Linux wrapper and
post-oracle prefix bound differ; this is not execution of the Linux ELF.

The complete per-call oracle remains an exact substring of each port, SHA256
`603ef982f376499e7e370d565d90dd7ef4f689f1f3c130798c2c9d94d5593272`.
It checks returned vstart, every result bit, prestart preservation, original
allowed mask/tail agnostic alternatives, sticky plus active-element fflags,
and both output guards before incrementing the prefix count.

| Measurement | Masked restart | Unmasked restart |
| --- | ---: | ---: |
| Exact target PC | 0x800005cc | 0x800005ae |
| Exact opcode | 0x60881c57 | 0x62881c57 |
| Target retirements | 130 | 130 |
| Other nine comparison targets | 0 each | 0 each |
| Complete CSV rows | 1152966 | 1152231 |
| Retired instructions | 1147283 | 1146548 |
| First / final cycle | 82 / 1420292 | 82 / 1366383 |
| Vector requests / responses | 1433 / 1433 | 1433 / 1433 |
| Backend allocations / completions | 692 / 692 | 692 / 692 |
| CVX exceptions / replays | 0 / 0 | 0 / 0 |
| Simulator elapsed seconds | 1647.307188 | 1633.254852 |
| Retired instructions/second | 696.459657 | 702.001894 |

Retirement order is contiguous, cycles monotonic and retire traps absent.
Both raw post-target CSR scans found130 returned vstart values, all0, and
130 fflags values: 0 on64 calls, 1 on64 calls, 16 on2 calls. The original
oracle's zero-error result includes comparison against expected flags, not
just numerical data.

Private ELF SHA256, masked / unmasked:
`5e8bcf641bec113dcab79a12687560bbd62cffde1c2f6eb78e5080a191d3dfab` /
`60b4969704be7e08055a261a7c729a76c7e616ba11d59c4744305a4682a9091f`.
Console SHA256, same order:
`37210a05900b914e67e2b9c5b6014186509778d738ba0076081b6a3cc2f7e3aa` /
`9416f1b1bc9b21e50dc5517bf3c575473dda77d324d242a2e857ef80cc378095`.
CSV SHA256, same order:
`6922ca1f4791a1b78090488db077ebe6ecff47481af677ea7daec4959d18c54c` /
`3fed0c78253b868ffc75025083ecb3ea0d2843a70e78d75a79fbeb3b558310f9`.

## Service and Slot Release

Each test finished below its unchanged3600-second limit. Recorded launch to
terminal publication was1700.698495 seconds, below the parent-recorded4500s
service limit. `candidate04_restart_plan08/service.log` retains both PASS
lines; no service failure is recorded there.

One bounded terminal query using the trusted explicit user-bus environment
found `ara-fp-original-restart-candidate04-02.service` already collected:
rc0, LoadState=not-found, inactive/dead, MainPID=ControlPID=0, empty ControlGroup.
The all-process/cgroup absence check at1791721929.1703188 examined1210
processes and found no owned processes or matching unit cgroup directories.
The FP2 occupancy is therefore released for parent-coordinated Gather98x2
admission; this does not itself launch Gather or waive its resource gate.

Service-exit limitation: the collected unit's default ExecMainCode=0 and
RuntimeMaxUSec=infinity are NOT retained execution facts. Journal access
returned rc1/insufficient permissions, so a numeric systemd main-process
exit code could not independently be recovered. Test rc0, runner COMPLETE,
no-abort terminal acceptance and process/cgroup absence are independently
verified; do not relabel the missing service exit code as measured0.

## Held682 Cost Only

The unchanged held prefix has20260288 Spike-retired instructions. Dividing
by the two measured M4 rates gives28860.73 to29090.40 seconds, about8.02 to
8.08 hours. This is a throughput extrapolation, not a runtime upper bound:
the held case is e16m8 alias-v8, has different operations and vector activity,
and host contention may change. Spike and SoC retired totals also differ.
It does not establish that the prior61200-second budget is necessary or
sufficient. The682 ELF, full oracle, sealed plan and HOLD_NOT_RUN status
remain unchanged; no682 launch or942-call acceptance is authorized here.
