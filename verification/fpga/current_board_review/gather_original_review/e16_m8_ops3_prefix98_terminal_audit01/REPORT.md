# Independent VI31 prefix98 terminal acceptance

Verdict: **VI31_PREFIX98_DUT_CASE_INDEPENDENTLY_ACCEPTED_NOT_FULL2688**.
This is acceptance of the actual frozen M6 DUT case from original raw artifacts, not a restatement of the worker PASS gate or an exit inferred from absent processes.

## Terminal / Disk Identity

- Both raw logs pass the first-error veto, with exactly one case BEGIN, `RVV_GATHER_PREFIX_PASS sew=16 cases=98 errors=0`, CASE_PASS, REPLAY_PASS and Core SUCCESS/tohost0. No failure, detail, mismatch, trap or abort marker.
- Actual numeric case **returncode0**, elapsed **2856.3962695291266s**, PASS1, runner **COMPLETE**, aborted false, retries0; within fixed9000s/case and10200s/service budgets.
- Independently hashed original **disk** `prepared01/plan.json` before and after analysis: `d35fd8ce0a1a74854ad6d230c2c9f467f7c633fa5d9f4f3d1ca52619fb23d0a5`. Not only the sealed worker's in-memory plan validation.
- All **855 plan pins**, **11 exact raw evidence pins**, reference and launch approval pins verified. Original terminal, disk plan and raw artifacts remained unchanged.
- M6 image SHA `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`; snapshot SHA `3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438`; configuration SHA `6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785`.

## Full Raw CSV Reconstruction

Exactly **one strict original CSV traversal**, plus generic trace validation, took **62.823s** offline. The supplemental observer yields every input row unchanged; no oracle replacement or frozen checker edit.

- All **98 source calls / 97 natural predecessors**, cap512, exact original tuples/order; end98 tuple `[0,3,0,6,0,1]`, VL512/start256.
- **13 original helper instructions retired98 times each**, with exact encoding/order, all actual arguments, source RNG/setup scalar stores (2178 setup values per call), predicate, output initialization, VL returns and returned vstart0.
- Actual target `308fbc57` at PC `0x80000764`: unsigned immediate31. All98 entry pointers are **ordinary indices `0x80001db0`**, distinct from indices16 `0x80000da8`; a6=0 at entry and target, t3=0 at target. This is not scalar vx0 or EI16.
- **50176 fullcap results +196 guards =50372 actual unique LHU oracle loads**, after complete original helpers. All output bytes required by the original oracle, including prestart/inactive/tail and both guards, are checked.
- Actual result categories over all98 calls: **2669 active**, **17177 prestart**, **2722 inactive**, **27608 tail**. Active values are32689; every retained value and both guards are91.
- **1904350 CSV rows**, **1900048 retirements**, last cycle **2746409**; no accelerator exception/trap. Original CTRL exit store0 and original post-exit `a001` parking checked.
- Recomputed analysis matches stored analysis **structurally and byte for byte**; both SHA `fa77a9d11c84abffee7455efddb12b73c71c94d48842945c7c3622a96381b692`.

## Discriminating Actual Loads

Original C op3 chooses source index31 and tests `index < cap`, not `index < VL`. The complete source setup matches original xorshift: **input31=32689**, whereas input0=61881. Thus VL1 still permits source31; zero from a VL-bound check or61881 from vx scalar0 would both fail.

All loads below are actual retired LHU at PC `0x80000504`:

| Call / element | Original condition and actual value | Cycle / CSV line |
|---|---|---|
| 18 /0 | VL1/start0, source31>VL but<cap512: **32689** | 525563 /363310 |
| 18 /1 | Tail preserved: **91** | 525575 /363320 |
| 98 /255 | Last prestart preserved: **91** | 2736407 /1897081 |
| 98 /256 | First active: **32689** | 2736483 /1897105 |
| 98 /511 | Last active: **32689** | 2743836 /1903225 |

End98 checks all512:256 prestart retained91 +256 active32689. Supplemental evidence retains all98 actual entry/target identities and these actual read locations; the strict checker covers all50372 results/guards, not only these spots.

## Authenticity / Scope

- Original archived C SHA `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`.
- Original Linux ELF SHA `16a715c87479c206545de7e5e9173fcd5ac93a48fe71a6c9dcfd7466993bd853`.
- Executed SoC ELF SHA `c1064255efa0ff19d492d263723d1c7b88ad9521983ae07d12ecf8a753b5cf44`.
- Actual archive, SoC and Spike helper disassembly preserves all13 original encodings. This is an authentic source-derived bounded SoC/runtime port, **not execution of the original Linux ELF** or proof of rebuilding the entire Linux binary.
- Accept only this98-call child prefix; **not full2688** (2590 calls outside scope), full parents, Linux schedule or the unknown historical stopped tuple.
- Outer worker/service actual exit is **UNKNOWN** after GC. Not-found/no process is not positive exit0. Independent DUT-case evidence is numeric case rc0, COMPLETE/PASS1, actual raw CTRL0 and complete original oracle.

## Owned Outputs

- `audit.py`: offline auditor, frozen helpers imported read-only.
- `audit.json`: verdict, identity and evidence pins; SHA `0e6aba788041a16f3279f97bd36fe759e67ff4c467c1209d6224b35853c74fa2`.
- `recomputed_strict_prefix.json`: single strict reconstruction, byte-identical to stored.
- `vi31_actual_evidence.json`:98 actual argument/target records, complete category counts and selected actual reads; SHA `39079fa74fb90ff7b805f82ae947c679ed29332a2df1a4eca5e38ca730d49131`.

No DUT/Host rerun, live e8 observation, process/service query, RTL edit or old/sealed write. Only this new owned audit directory was written.
