# e32/m4 Static Source Plan Review

Verdict: SOURCE_NO_BLOCKER_STATIC_PLAN_COST_NOT_ADMITTED. The exact plan is suitable for the next model-preparation decision. This is not acceptance of a generated model, rewritten C, compiled port, reference or DUT. No Host, compilation, reference, DUT, live query or large raw read was performed.

Reviewed ../full_e32_m4_static_feasibility01/PLAN.md SHA6f5c84473b9c7ef7ee30e7df61d4b37d278f64bfa91348bad3b22039769b0b98 and SOURCE_PINS.json SHA859975428067f9f8635bac88137a7a3372ded3bf0a8c4295d3aa26ea07bdeb02. All12 source/evidence pins freshly match.

## Actual Provenance And Shape

Original archived and recovery22 ELF SHA4e537be1270d607f847b8c7d3d4e7be76b9b7408d184effc33a9c066cb811cf9 match. Reconstructed C is binary-equivalent source, not authenticated original C text or a Linux execution. Independently read original assembly, disassembly, ELF bytes and ELF program headers. The458 contiguous helper instructions at10906..10f9c occupy1688 bytes and match actual ELF bytes; SHA d44dea9535d297c3c6dc1894db7086c82ca5fb1ec8c32a4f891450b7676c417e. Capacity/full/target vsets encode e32,m4,tu,mu, not m2.

At VLEN1024, CAP128/vtype18 requires FOUR physical128B registers per group,512 bytes. Source order is35ops/3seeds/7 lengths/3 masks with original trial multiplicities:5985 calls,1890 FP calls,766080 uint32 results,11970 guards and77805 executed helper instructions. Integer RNG must run128 steps per seed with original overrides (1104 source assignments overall), not repeat CAP64 data. Gather b[3]=32 is valid; all gather and slide boundaries use CAP128.

Output520B means65 complete eight-byte comparisons. Offset0 contains leading u32 guard plus element0; offset512 contains element127 plus rear u32 guard. There is no short tail or padding read. Sentinel packing is0000005b0000005b; not e64's scalar000000000000005b or e16's repeated005b. Each FP call must write a[0],b[0],...,a[127],b[127] as256 ordered four-byte SW operations,483840 total, even for VL0/equal contents. Proposed immutable-table refresh is eight four-byte reads per FP call; actual compiler behavior remains unproven.

Full mask backing is128B, cleared each of2205 groups; actual vlm uses16B. Selected indices give128/64/18 SB assignments by mode,154350 total; upper112 mask bytes must remain freshly zeroed. All result, guard, returned-vstart and predecessor history obligations remain. No original fflags result oracle is invented.

## FP Bit Identity

Independently packed all640 original uint32 expected constants and compared actual ELF file0x15b0..0x1faf: exact unique occurrence, SHA b6ba4a7cb146e697a04723349b9e023e2210dc0714b717f70eb8bfb6c3a8438a. Eight input uint32 values match file0x1590..0x15af, SHA0fc58c7e3dce546882fe0310427254fa002b61964299ca3e90a9b264e4805c65, with five occurrences. No false uniqueness claim is used.

Readelf LOAD maps these bytes to VA=file+0x10000. Original103ce..103dc builds0x112d0 and saves it at stack120;10496/104ae use displacement0x2c0 with four-byte indices, binding inputs0x11590. Original1082e binds expected-table0x115b0. Full table identity is not exhaustive640-pair execution: exact original seed/index selection must remain, not expand coverage claims.

## ROM And Cost Qualification

For fixed seed/op/mode, the33 non-reduction/non-compress operations have per-element values independent of VL/start; only active interval changes. Checked the plan's block index boundaries and interval possibilities:7,2,3,2,4,2,2,2,2 sum26. Excluding reduction/compress from this argument is necessary; their separate conservative7-VL allowance remains. This supports the analytic8856-block upper and674514B pool-plus-IDs estimate, not an observed unique count. Block8 has only8 accessible output bytes; its56 padding bytes are ROM-only. The842610B planning envelope includes64KiB stack reserve but is not a linker map or no-spill guarantee.

The proposed uint32 memcpy/barrier stores have valid distinct source/destination objects and offsets0..508; the eight-period identity preserves FP bits and ordered refresh. The future actual header, Host and ELF still need proof. In particular do not merge stores to SD, reduce complete input refresh, inherit m2 gold, or assume e64 register allocation/leaf cost.

Cost3384640/3699825 values are explicitly analogy-based scenarios. Four instructions per additional bitset,282/320 FP-phase counts and unchanged other CFG are assumptions, not actual m4 bounds or lower bounds. Neither analogy proves runtime failure nor satisfies the inherited3M reference gate. Actual generated model/dictionary size, stack map, compiler paths/spills, full CFG and later measured firmware remain unavailable. Cost and <=3h DUT admission stay HOLD; next model preparation must not silently authorize compile/reference or raise a budget.

No source correctness blocker was found in this static plan. No existing running task or producer file was changed.
