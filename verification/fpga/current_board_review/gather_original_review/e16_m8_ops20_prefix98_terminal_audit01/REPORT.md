# Independent EI16 prefix98 terminal acceptance

Verdict: **EI16_PREFIX98_DUT_CASE_INDEPENDENTLY_ACCEPTED_NOT_FULL2688**.
This is an offline acceptance of the actual M6 DUT case, not an inference from the worker PASS gate or a garbage-collected service.

## Raw terminal and identity

- Both `console.log` and `work/run.vcs.log` pass the first-error veto, with one exact BEGIN, `RVV_GATHER_PREFIX_PASS sew=16 cases=98 errors=0`, CASE_PASS, REPLAY_PASS and Core SUCCESS/tohost0. No failure, detail, trap or abort marker.
- Actual frozen runner summary: numeric case returncode **0**, elapsed **3365.877068196889s**, status PASS; run state **COMPLETE**, aborted false, retries0. Within the sealed 9000s/case and 10200s/service budgets.
- Independently reread and hashed **disk** `prepared01/plan.json` before and after analysis: `711e1f5ff862e9da4697ad3b6b2dfd278e78ec079f011b14665f4bfebb84d510`. This is not only the old runner's in-memory plan validation.
- All **786 plan pins**, **11 exact raw evidence pins**, reference evidence and launch approval pins verified. Original plan, terminal and raw artifacts remained unchanged.
- M6 image SHA `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`; snapshot SHA `3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438`; configuration SHA `6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785`.

## Complete raw CSV reconstruction

One strict traversal of the original CSV, plus generic trace validation; **73.512s** offline analysis. The lossless observer yields every original row unchanged to the frozen strict checker. No oracle substitution or checker edit.

- **98 natural source calls**, including all **97 predecessors**, cap512; endpoint tuple `[0,20,0,6,0,1]`, VL512/vstart256.
- All original **13 instructions retired 98 times each**, exact encodings/order, including `38880c57` at actual PC `0x80000aac`; full actual call arguments, setup/RNG scalar stores, predicate, original VL returns and returned vstart0 for every call.
- **50176 result values + 196 guards = 50372 actual LHU oracle loads**, complete and unique per call after the full helper. All prestart, inactive and tail values retain91, both guards retain91, all active values obey the original scalar oracle.
- **2133661 CSV rows**, **2129359 retirements**, final cycle **3218114**; no accelerator exception or trap. Actual CTRL exit store0 and subsequent original `a001` parking checked.
- Recomputed report equals stored report structurally and **byte for byte** (`cmp` exit0); both SHA `a6fadda67c1c7880ab9db498ffda59d67c40e2bfd7ebded5d147419561616929`.

## Actual EI16 / Dynamic OOR Evidence

Actual helper-entry `a1=indices16=0x80000da8` checked **98 times**, distinct from plain `indices=0x80001db0`. The original C selects `indices16[i]` for op20 and tests `index < cap512`, not `index < VL`. The two arrays having equal values does not waive pointer identity.

All observations below are actual LHU retirements at `0x8000051a`, with source-derived indices and original scalar expected values:

| Discriminator | Actual and expected | Raw cycle / CSV line |
|---|---|---|
| call49 element2, index511 valid despite VL3 | 44879 | 1645752 / 1090705 |
| call66 last active element255, index512 OOR, VL256/start128 | **0** | 2150281 / 1430426 |
| call66 fullcap last element511, tail | **91**, not active OOR0 | 2154051 / 1433242 |
| call98 last active element511, index1, VL512/start256 | **538** | 3215571 / 2132530 |

Call98 checks all512: **256 prestart retained91 + 171 active in-range values + 85 active OOR zeros**. Each of the85 zero observations is preserved with actual load PC/cycle/CSV line/index. Call74 inactive element129/index512 remains91 at cycle2399392, CSV line1596348; OOR does not overwrite inactive state. Dynamic values are not replaced by constant input0 (61881).

## Authenticity and Scope Boundary

- Original archived C SHA `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`.
- Original Linux ELF SHA `21a28efe2ef7b79f9511c9b793bf0235bbc81944b27f1196179642f2a5a8c888`.
- Executed SoC ELF SHA `c4d681ad58bf1e46e121ffc3c3652cabc1b2a62100fc3987012c502e53fc89fd`.
- Actual archive, SoC and Spike disassembly preserve the original13 encodings. The archive target PC is `0x10994`; this is a source-derived SoC/runtime port, **not execution of the original Linux ELF** or proof of rebuilding that entire binary.
- Acceptance covers this authentic bounded child prefix98 only. It does **not** close all2688 child calls (2590 remain outside scope), full parent histories, Linux scheduling or an unknown historical stopped tuple.
- Parent reports unit GC. **Outer worker/service actual exit is unavailable**, not verified0. GC/not-found is never positive exit evidence. Numeric case rc0, frozen runner COMPLETE, actual raw CTRL0 and full oracle are the independent DUT-case acceptance evidence.

## Owned Artifacts

- `audit.py`: offline auditor; imports frozen helpers read-only.
- `audit.json`: verdict, exact identities, unchanged-artifact checks and evidence pins; SHA `60e1c45a737e1850fc93061f8c419213f90053348de29e65be2b0f63796dbbd3`.
- `recomputed_strict_prefix.json`: the single strict reconstruction.
- `dynamic_oor_actual_evidence.json`: actual98 a1 entries, selected discriminators and85 active OOR loads; SHA `072eb6b20e1de52aab535aa93b5698a705811a87a2e77a9fbd921fa0e5747f1c`.

No DUT/Host rerun, process/service query, active VI31 observation, RTL edit or sealed artifact write. Only this new owned audit directory was written.
