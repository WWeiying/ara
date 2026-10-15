# Two VI0 Natural Prefixes

Reference-only acceptance: original e8/m4 ops2 and e16/m8 ops2, seed0/scalar-slot0, natural first112 calls with all111 predecessors. Both end at source loop coordinates `[0,2,0,6,3,3]`: VL512, all-off mask, vstart511. No excluded loop was shortened. Only the completed-case prefix stop and established bare-metal adapter are inserted; explicit diffs are retained.

Each scope has actual vlenb128/cap512, 57,344 complete scalar result checks, 224 guards, 112 returned-vstart checks, and 1,456 original helper instructions. Each call retains 2,178 initialized scalar values: three arrays of512 values, physical predicate128 bytes (logical64), and514 output values. Unused static array tails are not claimed independently audited. VI0 source0 is byte185 / halfword61881, not VI31 or VX-index0 inferred from unrelated software.

| Source | Original Linux ELF SHA256 | Actual reference retired | Spike elapsed |
|---|---|---:|---:|
| e8/m4 ops2 | `498805cf438a11729e74f0ac7b74068fa5e19bbcf56318790b01afc798d18b65` | 2,560,282 | 4.4353s |
| e16/m8 ops2 | `13a9b694ade91e25687108b4bf93b50ecc2d80c3a2a6fd532b269dac3b4aafcf` | 2,390,386 | 4.0786s |

Original full Linux binaries were rebuilt byte-identically with archived flags and the actual Buildroot14.3 compiler before adaptation. SoC/reference binaries are adapters, not those original Linux binaries. Both reference executions have durable actual numeric child rc0 and complete strict raw oracle/HTIF checks. Each original C Host fixture passed one positive and seven mutations: prestart, active, inactive, tail, each guard, and vstart. The original13 helper encodings match the Linux, SoC, and Spike ELFs.

Preparation failures remain preserved: prepare01 stopped on an adapter-unaware static comparison before Host/SoC/Spike; prepare02 e8 completed its one Spike execution and strict check but duplicate report keys prevented serialization. This fresh e8 report was recovered offline from the existing raw log; one recovery parse, no new Spike execution. The e16 reference ran once here. No source/ELF/oracle repair was used to convert a numerical failure into PASS.

At a conservative600 retired instructions/second, the measured firmware costs project to4267s/3984s (about71/66 minutes), not a completion guarantee. Actual M7 numerical regression uses two workers,9000s/case,9600s outer, no retries, no image/RTL rebuild. Frozen worker plan is `../vi0_missing2_vcs_m7_plan02/prepared01/plan.json`, SHA256 `1e4f0158e428efda28a652ba7e1958971fb971a16d48c4988aa353e141be7b8a`.

This closes only previously missing numerical VI0 prefix coverage if DUT acceptance subsequently passes. It does not identify an unreturned historical tuple, reproduce/close any of11 archived stalls, accept either full2688 child, or reproduce Linux execution/full parent history. R168 decoder remains a separate actual-dump-required tool; no archived dump has been recovered.
