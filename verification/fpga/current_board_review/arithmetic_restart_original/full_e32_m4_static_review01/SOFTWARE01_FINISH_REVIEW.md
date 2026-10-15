# Software01 Finish03 Review

Decision: ACCEPTED_CLOSED_ARTIFACT_EVIDENCE_COST_HOLD. This fixed candidate does not meet3M. No reference or DUT admission; no parameter search, recompile or test rerun follows.

Reviewed actual software01/closed_audit03.py, RESULT, pins, receipts, Host outcomes and linked-function metadata. All260 pinned inputs/artifacts freshly match. All46 Host log hashes and expected numeric outcomes match, no timeout. SoC's only compile returned0/1.7731651607900858s. Finish03 actual child0/29.443394404370338s binds exact result5c3eab6d42a69442002f8efb65c30e85347ca8d1d3eed52bc9fbf3e38f5b834e. No5985-path analysis, Host, compiler, reference or raw parse was rerun by this reviewer.

Historical receipts remain distinct: original supervisor1/33.04881114931777s (stripped capacity symbol), finish01=1/29.28741545183584s (GP analyzer omission), finish02=1/0.06703571695834398s (generated syntax error). Finish03 derives gp0x80041b9a from real startup AUIPC/ADDI and checks no other writer; unknown business registers reject. Opaque callee-saved entry values are permitted only for ABI stack save/restore, not used as invented data. No old error is relabeled PASS.

## Actual Source And Memory Contract

Original assembly order, individually unique decoded windows and actual executable PT_LOAD bytes bind capacity plus35 helpers:458 instructions/1688B, original10906..10f9e and compiled80002268..80002900, ends exclusive. Helper SHA d44dea9535d297c3c6dc1894db7086c82ca5fb1ec8c32a4f891450b7676c417e. Extra RVV/new scalar CSR or fence in candidate routines:0. Actual SoC ELF SHA1a106b67ced352f957c29e0a5327d22ab0169fcc399daaf8bc6a25943ea72e4b.

The closed analyzer consumes pinned call IDs and assumes correct actual outputs only to derive positive cost. It restricts cache branches to immutable-ID provenance and prevents actual-result/expected-value-dependent cache addressing. Thus data mismatch cannot skip remaining actual reads. All5985 finite paths retain389025 actual LD (65/call, offsets0..512),124041 expected LD,53865 ID LHU,33123 hits and14757 full-block fills. Each call starts with its own first fill; last block reads exactly8 bytes, element127 plus rear guard. Fullgold table, ID and dictionary payload identities are retained; no actual-result cache or cross-call reuse.

FP paths retain8 fresh32-bit inputs and256 ordered a/b SW per call,483840 total. Mask paths retain16 clear SD followed by exact cumulative selected SB,35280 clear and154350 selected overall; no old selected-LBU claim. Output initializer is65 SD/call,389025 total, typed0000005b0000005b. Full original fallback and all766080 results/11970 guards are covered by existing Host source/model evidence, not an executed RVV reference. Original fflags oracle is absent.

Host46 comprises30 full original/candidate histories and16 structural negatives. Negative outcomes are expected rejection, not positive architectural passes. Existing mutation evidence addresses freshness, sequence, cache/tag/value/read omissions, guard/dual-error fallback, dirty mask and exact boundary handling. This review does not replay those tests.

## Sufficient Cost Rejection

Actual cache function has392 static instructions, with seven optional10-instruction ID-miss refresh paths. The pinned33123 hits yield392*5985-10*33123=2014890 dynamic cache instructions. Independently inspected function metadata confirms65 SUB,65 SNEZ,64 OR,7 ZEXT.B and7 tag branches, not the hypothetical cheap equality-branch schedule. Its48-byte frame saves/restores six callee-saved registers:35910 SD plus35910 LD are INCLUDED. They are ABI saves/restores, not gold-cache-value spills.

Disjoint mandatory terms: cache2014890 +output initialization424935 +FP529830 +mask235935 +original helpers77805 =3283395. This exceeds3M by283395 before main/caller/RNG/startup/capacity/control work. For the required complete successful source history, those omitted terms cannot reduce the subtotal. Consequently a whole-program upper or actual Spike measurement is unnecessary to reject this candidate under the unchanged gate. This is compiled CFG evidence, not an exact retired firmware total, VCS runtime prediction or RTL defect.

Actual BSS-to-stack gap768872B and summed static negative-SP adjustments520B satisfy the planned reserve; cache48B/main272B are included. These memory results do not override cost HOLD. No reference backend was compiled after the sufficient rejection. Preserve this candidate and its receipts without another variant under the exhausted one-compile authorization.

Bound hashes and explicit decision are in SOFTWARE01_FINISH_REVIEW.json. No producer/sealed/RTL file was changed.
