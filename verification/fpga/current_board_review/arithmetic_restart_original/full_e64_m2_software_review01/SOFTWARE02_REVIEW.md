# Software02 Actual Artifact Review

Verdict: NO_BLOCKER_SOFTWARE02_HOST_COMPILED_CFG. The exact new compiled artifact satisfies the static cost gate (upper <=3M and net saving >=75000). Reference execution still requires parent authorization; this is not a reference, DUT or Linux acceptance. Software01's historical HOLD and both software02 observer ERROR records remain unchanged.

## Actual Evidence

Reviewed root: ../full_e64_m2_block_software02/.
Final evidence: audit_artifacts02/RESULT.json, pins.json and execution_receipt.json.
Fresh independent hash verification: all 444 pinned inputs/artifacts match. All 35 Host log hashes and numeric expected outcomes match, with no timeout. No Host/compiler/auditor/reference rerun was performed by this reviewer; source/disassembly/metadata reads and hash checks only.

Original wrapper actual rc1/42.1293829260394s is retained: hardcoded refresh symbol did not recognize the real constprop clone. finish_artifacts01 actual rc1/2.070385154336691s is retained: the inherited cross-line whitespace parser swallowed original helper entry after ret. Neither is relabeled PASS. audit_artifacts02 uses per-line horizontal-whitespace parsing and explicitly retains ret 0x10898=0x8082 plus vset 0x1089a=0x019772d7. Its actual wait is rc0/1.4190587433986366s, timeout60s, PID3317398.

Both actual GCC receipts are rc0/no timeout: SoC PID3312856/1.269350397400558s and compiled-reference artifact PID3313874/1.3197452500462532s. The latter is only an ELF, not a Spike execution. The final audit consumes these existing artifacts without recompilation.

## Source, Host And ELF

- Actual case.c is byte-identical to reviewed case_proposal.c. Only the approved FP refresh replacement is carried from software01; source/helper/oracle/RNG/history remain full 35op/3seed/5985 calls, 1890 FP calls, 191520 results, 11970 guards. No original fflags oracle is invented.
- Host observes each actual source store and checks alternating bank/index order plus per-index count, not just final input values. Full original/packed positive and eleven result/state-negative histories match; UB trap is retained. Nine missing-state/sequence negatives bring the total to 35. Swap and duplicate reject at ordinal1367 with sequence error; VL0 omission rejects at ordinal1366; stale FP seed rejects at ordinal3361. Equal-value a/b deletion, next-seed RNG omission, output fresh-init and upper-mask clearing negatives remain. Positive scope checks include exactly 120960 FP destination stores.
- The actual sole function is refresh_fp_period.constprop.0, not the unassembled witness. Its complete extent is SoC 0x8000007a..0x80000346 and reference ELF 0x80000082..0x8000034e (end exclusive). Audited static paths accept only known decoded scalar operations and exact addresses/values. Each seed path has eight fresh table loads followed by 64 exact a[i],b[i] SDs in original index/bit order. Path lengths are 83/81/83 instructions. The constant-propagated ABI uses a0=seed; a/b/table addresses are linked globals, not stale cached arguments.
- There is one main JAL to this clone. In the reference ELF, op>24 gate at 0x8000083c reaches caller 0x80000d84..0x80000d92: load seed, two SD spills, JAL, two LD restores, jump back to fresh output initialization. All three later-trial branches return through the gate. There is no VL/start/equal-data bypass. Thus all 1890 FP calls refresh inputs, including VL0 and repeated contents.
- The 458 original static helper instructions remain byte-matched with no extra RVV. Original input/table bit provenance is inherited through exact pinned source and linked file-backed bytes; the expected 640-word/5120-byte table remains unique. Dictionary82048B and indices59850B are fully bound. No table identity claim relies on the five duplicate original input strings.
- Both ELF inspections retain exact 128-byte mask clearing, 34 SD output initialization and 34 LD full272-byte comparison. Last dictionary block reads only bytes256..271; guards are u64 0x5b. No mask-region fence/call/branch/RVV. Main frame288B; actual map gaps SoC868448/reference860056 bytes. No reduced oracle or padded-tail access.

## Cost Gate

The final accounting uses actual compiled reference-ELF PCs, not lowering_witness.S. FP calls are 630 per seed, so leaf paths total (83+81+83)*630=155610. The seven-instruction caller/spill/return sequence contributes13230. Main prologue, seed/RNG setup, masks, fresh output, full comparisons, dispatch, original helpers and control-flow unions are separately included. BSS16493 and terminal/runtime allowance20000 remain included.

Mandatory core:2159325. Successful-path conservative upper:2330297. Prior software01 upper:3074202. Net static saving:743905. Therefore both fixed gates are met without increasing budget. This upper concerns the successful oracle path, not failure-print behavior or VCS wall time. Actual retired firmware count remains null; a real bounded reference is still needed before any subsequent DUT decision. No <3h runtime guarantee is made.

## Bound Identities

Machine-readable hashes and decision are in SOFTWARE02_REVIEW.json. No producer input, historical receipt, main ledger, RTL or active task was modified.
