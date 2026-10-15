# Recovered Process Evidence For Independent Review

This new disjoint receipt qualifies the existing software-reference evidence.
It does not replace old seals or manufacture a missing Spike child wait file.
No program, reference, Host test, build, or DUT was executed for this recovery.

The assistant's tool history directly records:

| Invocation in integration worktree | Tool session / completion chunk | Direct process exit |
| --- | --- | --- |
| `python3 -B .../fp_alias50_m6_prepare01/prepare.py` | 70225 / a82bde | 1, offline mask parser exception |
| `python3 -B .../fp_alias50_m6_prepare01/prepare.py --finish-offline` | 33133 / dffde7 | 0, completed offline checkpoint validation |

[receipt.json](receipt.json) contains full commands, preserved-script hashes,
tool identifiers, output excerpts and the exact tool wait-call timing fields.
It is a transcription from existing conversation tool responses, not an
original on-disk process transcript. No original outer stdout/wait file was
saved. Total process durations are unknown; the individual tool wait durations
must not be summed and called an execution time.

## Spike Evidence Boundary

The actual Spike command is saved at
`../prepared01/spike/alias_v8_e16m8_prefix50.spike.log.command.json`.
The unmodified raw output is
`../prepared01/spike/alias_v8_e16m8_prefix50.spike.log`.
The latter includes firmware exit-a0 zero, all three PASS markers and the
architectural snapshots checked by the offline finalization.

There is **no directly persisted numeric Spike wait receipt**. Its return0 is
supported only by the checked synchronous helper's control flow: the initial
process reached the later parser, and that helper raises on nonzero returncode.
Firmware a0=0 is separate architectural evidence, not a host wait status.
Accordingly, the old `actual_process_returncode: 0` fields in reference.json
and READY.json must be read as inferred, not directly saved numeric evidence.
Those sealed fields have not been edited. Initial Spike elapsed remains unknown.

For Confucius/parent: the independent software gate can explicitly qualify the
reference from unchanged ELF/source identities, the complete original50-call
oracle and actual per-call setup/input/result/CSR checkpoints, plus observed
offline-finalization exit0. This is not approval to waive a requirement for a
dedicated child wait receipt: if that is mandatory, the missing receipt remains
an evidence gap. No fabricated zero, new Spike run, or DUT acceptance follows.

The current tool exposes no identifiable Confucius subagent thread destination;
this artifact is the handoff for parent relay, not a claim of direct delivery.
