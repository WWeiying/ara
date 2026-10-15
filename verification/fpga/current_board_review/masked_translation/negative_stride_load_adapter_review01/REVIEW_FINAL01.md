# Sealed Negative Stride Adapter Review01

Decision: APPROVED_SEALED_ADAPTER_STATIC_REVIEW_ONLY. No blocking findings.
This concludes the source-adapter static task, not independent raw-reference
recomputation, DUT acceptance or permission to launch a simulator.

## Bound Inputs

Producer `masked_translation/negative_stride_load_original01/READY.json`:
`d20a279ff09bbad626141a386a12160634b0ad36ca82ff6da661c1c7ddcc4d52`.
Its64 pins contain62 files whose current hashes were independently verified.
The two excluded files are reference01/spike.trace and reference01/stdout.log:
neither was opened. Their sizes were checked against the metadata (101219616
and0 bytes); the trace digest is bound by READY and reference result metadata,
not independently recomputed here. READY's own hash was checked before/after.

Fixture hashes match REVIEW_DRAFT01 and the generated prepared copies. Final
observer/executor code was reread, including ELF initialized-byte loading,
retry_context and exact17274 scalar-comparison gating. Loading only initialized
ELF segment bytes correctly leaves BSS absent until observed startup stores.
No scalar/full-byte oracle was weakened by finalization. The pre-reference
checker-delta record is preserved; compiled source/ELFs are unchanged.

- observer.py: `3a9c17855ee618b82d03f83189277ec6ea3e0f50937a44ecf6b01281c6b25405`.
- prepare.py: `1e94b31f7513a5af39ea586f12f4ba2252297f9d30f73e2c84ddd72dbf0aa2c5`.
- SoC ELF: `04e25a1fa3b6ba094af6d60d50f8ec0dd60f2ec2503f47dda05fd2011c5a0a43`.
- Spike ELF: `19ec8c12d4b4f4a0974319a550bea7348d4dd890babcf1fe65afb90945abd60b`.
- Source proof: `41a6a6b1196c4c08c851038b99711a7574fa94868d20c822f775e190ea0e2e0a`.

Both generated backend disassemblies independently match the actual archived
failed ELF disassembly for capacity3 instructions and each10-instruction
load/store helper, including load target09c55c07. This is original helper
encoding identity, not byte identity of the whole Linux program/new adapter.

## Static Scope Conclusion

REVIEW_DRAFT01's S/M, stack mapping, lower-page invalidation/repair/refill,
unchanged target base/GPRs/t3, v0/v24 preservation and exact-PC/vstart restore
analysis remains applicable. Source scope is the authentic independent e16/m1
negative-load single: VL8, cap64, baseP+22, stride-8, mask0x24; faultP-18/start5;
2048-halfword lower refill followed by poison only P+6; same-PC retry without
helper reentry. Final source oracle is64 results,2 original guards and all8192
data bytes. Physical input128/offset128/output130/mask16 storage is retained.

The final report correctly labels neighbor/full-fault-snapshot/extra-storage
checks as adapter safeguards, not original historical oracle fields. A future
disagreement confined to an additional fault-snapshot safeguard requires its
own architectural assessment, not automatic attribution to the historical bug.
No additional scope, control test or nonarchitectural timing rule is requested.

## Reference Metadata Consistency, Not A New Parse

- Producer's durable child result is integer rc0, timeoutfalse,15.2561419099s
  under120s/1500000-instruction/256MiB limits. Its embedded result execution
  equals execution.json. Wrapper witness records actual wait0/session88117,
  explicitly not missing-process inference; this reviewer did not wait it.
- Metadata agrees on836971 firmware commit-format records,17274 comparisons,
  four ordered full-byte checkpoints, one original helper entry and two target
  attempts. Reported target accesses are P+6/start0 and P-18/start5.
- Reported actual retry MRET has original target PC0x80000e28, a0=P+22,
  t3=fffffffffffffff8, VL8/vtype8/start5 and MPP=S; other arguments match the
  pinned input/output+1/mask/capacity/stride symbols. Fault13 and completion
  ecall9 are separate; final returned vstart is0 and HTIF reports exit0.
- host_final01 reports17152 C/Python oracle rows and30 rejected mutations.
  Its pins match final code/READY. Tests were read, not executed by reviewer.
- READY inherits reference input pins unchanged, binds actual result/exit/report,
  and retains one invocation/no retry/no DUT/no build. No not_completed.json
  is present. These are metadata checks, not independent raw-trace proof.

The draft accounting note is resolved in the sealed report:11 means Spike
records including partial fault, not11 RVFI retirements. Ten original helper
instructions, one entry and two attempts remain distinct.

## Evidence And Limits

- Reference result: `e50b627177bbb6561bb2e246871db656a9e44d52920cfc74eabb0e1b229dbaca`.
- Actual child exit: `d66eafbec563edf70bedaa570e4358647563bed2d7be20900c6d9ac2089da00c`.
- Wrapper witness: `6bc1376c21c4bae9f3881ea4d73a13a3ab519dc0c713e039375f06259039805f`.
- Reference input pins: `0aea0e9f799c1f2beb3431c76ec2164d391489073b9b0182d6897c73a4f05ae2`.
- Producer report: `6edefe5ed4adca1f2dbe8968889600a5f0ccdbd493e4020e4254d35d33feeca1`.

No reference raw read, tests, compilation, simulation, live queries or producer
edits occurred in this review. This permits the next plan review on the exact
sealed adapter without a static blocker; it does not certify DUT, full parent96,
Linux signal-frame equivalence, historical predecessor state or a new M6 bug.
