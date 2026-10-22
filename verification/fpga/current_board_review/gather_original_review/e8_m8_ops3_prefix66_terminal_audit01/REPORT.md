# Independent e8 VI31 prefix66 terminal acceptance

Verdict: **E8_VI31_PREFIX66_DUT_CASE_INDEPENDENTLY_ACCEPTED_NOT_FULL2688**.
Acceptance independently reconstructs the actual M6 DUT case from raw logs and CSV. Worker PASS or absent processes are not the basis of acceptance.

## Raw Terminal and Disk Identity

- Both `console.log` and `work/run.vcs.log` pass the first-error veto. Exact unique BEGIN, `RVV_GATHER_PREFIX_PASS sew=8 cases=66 errors=0`, CASE_PASS, REPLAY_PASS and Core SUCCESS/tohost0; no failure/detail/trap/mismatch/abort marker.
- Actual numeric **case returncode0**, **COMPLETE/PASS1**, elapsed **3559.06748504797s**, aborted false, retries0; within fixed9000s/case and10200s/service budgets.
- Independently hashed original **disk** `prepared01/plan.json` before and after analysis: `edfd2c2f33fdbf76b9604efb6d98718a8f645fb0c8455ccda4cf9b8a2bf28d13`. Not merely its sealed runner's in-memory validation.
- All **931 plan pins**, **11 exact raw evidence pins**, reference evidence and launch approval pins verified. Original plan, terminal and artifacts remained unchanged.
- Actual executed SoC ELF SHA **`88b154a9a1c68f2a25706eb7b8587237335b34d3bc69590f970fec0074fca841`**, bound to actual input/command/runner artifacts.
- M6 image SHA `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`; snapshot SHA `3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438`; config SHA `6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785`.

## Complete Raw Reconstruction

Exactly **one strict original CSV traversal**, plus generic trace validation, took **85.469s** offline. A lossless observer forwards every original row unchanged; no oracle substitution or sealed checker edit.

- **66 original calls /65 natural predecessors**, cap1024, every original tuple/order; end66 `[0,3,0,4,0,1]`, VL512/start256.
- All original **13 helper instructions retired66 times each**, exact encodings/order; all actual call arguments,4226 setup values/call including byte input/ordinary indices,16bit indices16, predicate and old output; original VL returns and returned vstart0.
- Actual target **`308fbc57` at `0x80000758`**, unsigned immediate31. Actual `a1=ordinary indices=0x80001970`, distinct from indices16 `0x80000d68`; a6/t3zero verified at all66 targets (a6 also at entry). Not vx0 or EI16.
- **67584 fullcap byte outputs +132 guard values =67716 actual unique LBU oracle loads**, after complete original helpers. LBU decoding is required; a halfword oracle is rejected, and the complete1024-element output is checked on every call.
- All-result partition: **780 active177**, **16673 prestart91**, **15 inactive91**, **50116 tail91**, plus both guards91 for every call. No active-only or endpoint-only reduction.
- **2551108 CSV rows**, **2548214 retirements**, final cycle **3626003**; no accelerator exception or trap. Actual original CTRL store0 and post-exit original `a001` parking verified.
- Recomputed report equals stored analysis **structurally and byte for byte**; both SHA `4ba12de7a21c885423004705a00a7637c10a6b47aff65fa770b73ae53a811fad`.

## Actual Byte / VL / Tail Discriminators

Original C op3 chooses source31 and tests `31 < cap1024`, not `31 < VL`. Original e8 xorshift setup has **input31=177**, not vx0 input0=185 or e16 halfword32689. All active output reads return177.

The following are actual LBU retirements at PC **`0x800004fc`**, not only expected-model fields:

| Call / element | Actual original-oracle value | Cycle / CSV line |
| --- | --- | --- |
| 18 /0, VL1/start0 | **177**; source31>VL is still legal | 1044789 /719381 |
| 18 /1 | Tail91 | 1044801 /719391 |
| 66 /255 | Last prestart91 | 3609830 /2538747 |
| 66 /256 | First active177 | 3609911 /2538771 |
| 66 /511 | Last active177 | 3617165 /2544891 |
| 66 /512 | First tail91 | 3617182 /2544901 |
| 66 /1023 | Fullcap last tail91 | 3623527 /2550011 |

End66 checks all1024 values: **256 prestart retained91 +256 active177 +512 tail retained91**, and both guards. The supplemental records are discriminating spots; the strict reconstruction checks all67716 result/guard loads and all predecessor oracles.

## Provenance and Acceptance Boundary

- Original archived C SHA `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`.
- Original Linux ELF SHA `ef3a7ff6d6dc48a7e5f20adbb7954490c08c7cbbdcd03afe9bbd4859dee7580c`.
- Actual archive, SoC and Spike helper disassembly preserves all13 original encodings. This source-derived bounded SoC/runtime port is **not execution of the original Linux ELF** or proof of rebuilding the entire binary.
- Only this66-call child prefix is accepted. **Not full2688** (2622 calls outside scope), full parent histories, historical stopped tuple or Linux scheduling. Target coverage stops atVL512 all-on; fullcap setup/store/tail checking does not establish targetVL1023/1024 execution.
- Outer worker/service exit is **UNKNOWN** after parent-reported GC. No process/unit query was performed. GC/not-found is not positive exit0 evidence; actual numeric case rc0, COMPLETE/PASS1, CTRL0 and complete original oracle establish DUT-case acceptance only.

## New Owned Outputs

- `audit.py`: offline auditor importing frozen helpers read-only.
- `audit.json`: exact verdict/identities and evidence pins; SHA `459a253763c1227d07efe65594a11d5e527b66f9f5c50a34c10c216519bfa8d4`.
- `recomputed_strict_prefix.json`: the single strict reconstruction, byte-identical to stored report.
- `vi31_actual_evidence.json`:66 actual entry/target records, full result partitions and selected actual LBU loads; SHA `96fdf2cd3478c5bf5c528fdf9f229a5f01fb45726961ff1934b54ac7209f1ee9`.

Only this new owned audit directory was written. No DUT/Host rerun, other live-task query, RTL edit or old/sealed write.
