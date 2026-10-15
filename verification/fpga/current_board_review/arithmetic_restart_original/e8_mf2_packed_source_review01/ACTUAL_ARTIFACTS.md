# Actual Host And Compilation Acceptance

Decision: **ACCEPTED_HOST_COMPILE_ARTIFACTS_NOT_REFERENCE_NOT_DUT**.
This succeeds the source-only review, without changing its historical scope.
Read-only artifact audit actually exited0 (tool session88534, completion
chunk a2e307). No Host test, compiler, Spike or DUT was rerun. The audit script
imports only standard-library JSON/hash/ELF parsing, not producer executables.

Independent result: artifact_result.json, SHA
`de146b9ec5fe917dadd622bb09396b672550fe4cc37f9adcf701b64deb02bfef`.
All129 existing preparation pins freshly match. The20 stored Host numeric
receipts are2 positives at0,16 deliberate corruptions at1, and2 UBSan traps
at-4. Both variants' matching logs retain full4095/262080/8190 counters.
Mutation9 explicitly reports result63 expected91/actual90, so the tail2 low
byte cannot disappear behind the rear-guard test. Four actual compilation
receipts (two Host, SoC and Spike) are0. The producer's overall preparation
exit0 is recorded in compiled_review.json with its tool-session identifiers;
it is not a new independent wait on the original preparation process.

| Backend | ELF SHA256 | Independently verified |
| --- | --- | --- |
| SoC | 5e901ae235792e40de311713125a7a37a480a3e266c3a7c8d8d4887bb8433839 | 26 helpers/328 instructions match original binary; extra RVV0; ROM294840 bytes match all4095 rows; stack gap743656 |
| Spike | c2c8b69433dc357004904b8ddd8192681aef5b48d90df41b97f77ae5dd2d58a3 | 26 helpers/328 instructions match original binary; extra RVV0; ROM294840 bytes match all4095 rows; stack gap735200 |

The audit independently walks executable ELF sections and compares each helper
instruction with original Linux ELF at capacity10856 and opN1085e+0x30*N.
It also validates all4095 ledger tuples against the original loop order. It
does not treat proof.json alone as machine-code evidence. This still is not a
dynamic claim that every helper executed; the forthcoming reference must prove
the actual per-call sequence, including calls with empty active windows.

Actual SoC code, manually checked against program.dis:
- SH at800004f8 writes out+64, then eight SDs800004fc..80000518 write out+0..56.
  Compiler reordered independent initialization stores; all remain before helper.
- LD at80000548 plus80000812/81c/826/830/83a/844/84e reads all eight words.
- LHU at80000860 reads out+64;80000858 is the expected-ROM tail LHU, not another
  output read. No output read or initialization includes padded bytes66..71.
- out is80049ad8; helper destination remains out+1. The backing allocation is
  still1026 bytes, not66. Main's frame is304 bytes; it fits the retained reserve.

## CAP Versus VL

Original C uses i+2<cap for slidedown and b[i]<cap for gather, while destination
updates still require i<vl, i>=start and the original predicate. The original
helper loads source vectors at cap64 BEFORE setting target vl. Thus an active
destination can legally select initialized source data beyond current VL but
below64; replacing the source bound with VL changes the original oracle.
Conversely physical register bytes64..127 are not valid source elements for
this mf2 group: indices>=64 must follow the original zero-result bound.
The full-register width must not accidentally expand the gather/slidedown model.
Reduction scalar seed and compression retain their original distinct semantics.

Reference entry remains pending exact checker/lifecycle/driver review. The
newly communicated finite debugger command rs4000000 is a total execution
ceiling distinct from the <=3000000 firmware-to-HTIF cost gate; neither is a
measured retirement count. The agreed120s/768MiB/one-attempt limits and complete
4095 oracle must not be extended or reduced if insufficient. No DUT permission
or historical full-shape closure follows from this software acceptance.

Bindings: software_status.json
`c91456bb9c5104ef3749158382d290c5f62c09fc410b6bf5c378d48d33b9f579`;
proof.json `0d835cf9e2f394ab40bc43a7a6a090c1542872c717cc83bc9a04787f4c00e1f5`;
pins.json `c9f7b7b35458a3a836c0f53949dbd390d9c194eaa662b86fee5aafa1bd483c40`.
Existing source, terminal evidence and producer helpers remain unchanged.
