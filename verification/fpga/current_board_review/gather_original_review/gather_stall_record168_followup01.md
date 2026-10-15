# Gather Recovery168: New Recovery Handle And Next Scope

Static-only follow-up to `gather_stall_exact_trigger_review01/REPORT.md` (SHA `ec438e600f3d430a187b3d98263f7c7492bd98162a938b3262686edda599ac08`). No compilation, reference, simulation, active CSV/process query, RTL edit or original-record modification. All11 historical stalls remain open.

## Selected Original And Actual Recovery Result

Selected `rvv_permute_restart_e8_m4_ops3`, recovery168: original ELF SHA `a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b`, target1063e/next-vstart-CSR10642. Source/13 original helper instructions and full Linux binary equivalence are already established by `e8_m4_ops3_prefix66_prepare01/original_linux_rebuild02/proof.json`, SHA `7cc7582e71120bce71e5c29de897c271330ce0fa7a5c32dd6dad97dfb5c9cddd`; no rebuild was repeated.

`C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`; `R=C/rvv_recovery08_168`. Target ELF exists identically in `R/terminal_scene/<name>`, `R/resume/binaries/<name>`, `R/overlay/opt/rvv-preload/width_6ff6916366f1/<name>` and `C/rvv_permute_partitions01/release/binaries/<name>`.

The four full predecessor programs are recoverable as actual files, not merely names. Their `R/resume/binaries/` copies equal the overlay and canonical release copies and match transfer/protocol hashes:

| Original suffix, in actual process order | ELF SHA256 |
| --- | --- |
| e8_m4_ops8 | 34c0cea904dbb8f480ce7df87757a3bed9954a4d9e6a7bfefe85bac409697e97 |
| e8_m4_ops9 | 2a833ea587ee6142cb98d2c8ed449bc80789a982db2cd0bb3f8a0154db66be62 |
| e8_m4_ops10 | a22eed0d19feeee34c6fe675707dcd58ac7e0856a916d986365658e79583feaa |
| e8_m4_ops11 | b408f52b4939a1b82f9145868a62f44101a47fa5862a3037c03a75d5e0a5c3d5 |

`R/resume/batch.sh` SHA `7a55770431c816069fb5d9209133b504d87d413f2e03bb95581317af24a546fb` is the exact executable Linux ordering recipe; each predecessor's recorded numeric exit is0 with2688 cases. `batch_protocol.json` SHA `f263499c52e15c8f2ebcb51e89070f5ceb4033f8af77d1b10b89b7179450b179`; `transfer_manifest.json` SHA `4c725f77b48031a2ef5f8f8d2c36726723a88c9c97f27b28efb91882f293f7ec`. These establish process order, not captured vector state across Linux exec/context switches.

A cross-check of actual `rvv_recovery08_*/terminal_scene/report.json` result membership found only R168 executing this exact named child. Later name occurrences in remaining/continuation lists are not another trace. Selected R168 state-artifact inventory still contains only the two snapshot JSON/CSV files and busD transport logs. No saved GPR, stack, page-table/RAM dump or accepted-VID trace was recovered. DDR last accepted addresses are not process virtual mappings or payload dumps. Boot overlay/CPIO contains original programs, not stopped process memory. The returned-error tuple remains a prior returned call; no call67 or later stopped tuple is inferred.

## New Exact Recovery Recipe From The Original ELF

Read-only disassembly of the hash-matched original, not a new build, exposes a useful existing software checkpoint:

- Caller allocates336 bytes at101ae; op3 is a leaf and does not change SP. Its caller return PC is103ce.
- At104d2..104d6 the original loads/increments/stores `cases` at **SP+24**, only after the complete oracle and guards. At10548 it prints that same32-bit count. At an independently established stopped helper context, its value k means original current ordinal k+1, not total hardware retirement.
- SP+8 is seed; SP+0 is mode. `s4` is trial; scalar-slot = `(s7-(SP+160))/8`; length-slot = `(s9-(SP+128))/4`. `s8` should be3. `a3/a4/a6/a7` retain helper VL/capacity/scalar/start, respectively; the helper does not overwrite them before the blocked vstart read.
- For this single-op child, zero-based k decodes seed=`k//896`, scalar-slot=`(k%896)//112`, length-slot=`(k%112)//16`, mode=`(k%16)//4`, trial=`k%4`. Cross-check these against the actual saved loop fields, capacity and helper PC/RA before asserting an ordinal.

Thus a same-incident GPR capture with actual halted PC/SP/RA plus **32 bytes at SP** can recover the precise current call and complete intra-child predecessor sequence without adding prints or changing the original ELF. Full VRF is not required merely to identify the call. GPR slot pointers/trial and relevant CSR state supply consistency checks; backend VID/acceptance/completion is still needed for an RTL cause. Such bytes are not present in the inspected archive. If an external original crash/halt dump is located, this gives exact offsets to inspect rather than another counter guess. A physical DDR dump additionally needs the original process page-table mapping; the supplied boot images cannot replace that mapping.

Original full child is2688 calls, with1376256 fullcap results,5376 guards and34944 helper instructions at current cap512. Existing M6 first66 monitor1639.143s gives an18.54h naive full-child scaling, not a valid upper bound; R168's four full Linux predecessor processes add separate history. No credible short exact historical-trigger replay is currently ready. The Linux ELF/batch can be restored on an appropriately qualified Linux environment, but the existing M6 bare-metal integration runner cannot be labelled an unchanged Linux replay.

## Most Useful Next Preparation: Two Authentic VI0 Numerical Gaps

These two exact children are absent from `inventory83.json` and have no accepted exact-child prefix in the reused review ledger. This is numerical/source-history coverage, **not reproduction of either stall**:

| Original child | Original Linux ELF SHA256 | Archived target |
| --- | --- | --- |
| rvv_permute_restart_e8_m4_ops2 | 498805cf438a11729e74f0ac7b74068fa5e19bbcf56318790b01afc798d18b65 | 10600,30803c57 |
| rvv_permute_restart_e16_m8_ops2 | 13a9b694ade91e25687108b4bf93b50ecc2d80c3a2a6fd532b269dac3b4aafcf | 1060e,30803c57 |

Sources: the same genuine original C (`b6e5fa03...`), each child's `rvv_permute_partitions01/<name>/operations.S` and header; opmask4/restart1. Do not change VI31's immediate in a sealed ELF. Build a fresh source-faithful adapter per child only after preparation authorization, using the existing first112 VI0 preparation/checker as a template and cap512 m4/m8 assembly as applicable. Require each full original Linux source rebuild proof before adaptation; retain old evidence untouched.

Select **first112 natural calls**, seed0/scalar-slot0, all seven original VLs `{0,1,2,3,256,511,512}`, four masks and four trials, with111 predecessors. This is a complete first scalar block, not an endpoint guessed from a stall print. Endpoint `[0,2,0,6,3,3]` is VL512/all-off/start511; full-VL trials also include1/256/512. It covers both packed predicate source beats and full-cap completion/inactive boundaries beyond an all-on half-VL prefix.

Per case: actual vlenb128/cap512,57344 complete results +224 guards,112 returned-vstart0 checks,1456 original helper retirements,2178 setup scalar values per call (physical predicate128 bytes; logical window64). Preserve original RNG/arrays, ordinary indices, full scalar oracle and continue-after-error loop behavior. VI0 active source0 is byte185 or halfword61881 for seed0; prestart/inactive/tail/guards remain91. A VI31/source31 or active-only oracle is not equivalent.

Available execution target is frozen M6 image `current_board_memory_candidate06/campaign/image`, image SHA `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`; reuse integration runtime/GCC, six-event strict protocol and durable actual monitor outcomes. A later image must be explicitly substituted only after sealed identity review, not chosen automatically. **No new SoC ELF/reference/runner plan is prepared or runnable yet.**

Proposed subsequent execution envelope after source/reference preparation: jobs2, fixed9000s per case, independent fresh outputs/unit, fail-stop/no retry, no RTL build. Cap512 first112 has a rough2800..3300s proxy from accepted66/98 cases; this is not a completion guarantee. Measure full112 Spike retired/raw cost during authorized preparation before sealing the plan. Current recommendation is to prepare these two scopes, not start VCS or rerun the accepted66 prefix. Acceptance would close only the two explicit112 numerical histories; all11 original unreturned tuples, full2688 children and Linux histories remain unresolved.
