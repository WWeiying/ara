# Independent Merge98 M6 Terminal Acceptance

**ACCEPTED for this source-derived natural98 prefix only.** No discrepancy found in the complete DUT CSV reconstruction. This report summarizes generated audit JSON and the actual command exit response; it does not reopen CSV or rerun reference/Host/DUT/audit.

## Actual Exit and Identity

- Auditor PID1389942, original execution session41228: **actual command exit_code=0**, observed in final tool chunk5b1b67. This is not inferred from PID disappearance or service GC. [Invocation](TERMINAL01_INVOCATION.md) and [persisted exit observation](terminal01/command_exit_observation.json) retain the exact command and same-process runpy wrapper method.
- Audit cost231.834 s. Actual recorded simulator child rc0, elapsed3145.854479315225 s within9000 s, retries0, aborted=false, COMPLETE run/summary membership and matching private ELF/command. Both raw console and run.vcs.log passed original markers, firsterror/failure/timeout vetoes and real simulator finish checks.
- Prepared SHA `373561d4fcdf916e1b505748b7498da3b173823f2a01b935ae4dad28e377e741`; complete SHA `6c010fba28fcada854af4c79e08f76e1f36e074dda9b74370d24d624bcdb2c74`.
- Plan SHA `f97d3e2a933bfde527b1dd06b54f0055cb1bc2fca103d97308b1d0d45104b079`; frozen M6 image SHA `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`; private/source SoC ELF SHA `4e495abc1ec6b553554c5ddee992db88234c969adcba2f92b90ed6c78ea245ab`.
- **746 unique pins verified before/after, unchanged**, incorporating725 batch-plan pins,11 terminal evidence pins and preparation/approval bindings (sets overlap). This includes539 frozen sources,66 image files and explicit configuration/manifest identity gates.
- Outer DUT service terminal returncode/result remains unknown/null in this audit. Historical launch ownership is bound, but auditor exit0 and recorded child rc0 are not substituted for an unobserved outer service exit.

## Complete Reconstruction

| Actual Check | Count / Result |
| --- | --- |
| Full CSV parses | 1 |
| Original CSV rows delivered unchanged | 2019442 |
| Retired instructions, all actual PC/encoding checked | 2015140 |
| First / last CSV cycle | 82 / 2998730 |
| Natural target calls / retained predecessors | 98 / 97 |
| Consecutive original13 helper retirements | 1274; each instruction exactly98 times |
| Unused helper retirements | 0 across all20 complete ranges |
| Original returned-vstart reads | 98, all0 |
| Full-capacity result-element checks | 50176 |
| Guard-element checks | 196 |
| Total original scalar LHU oracle checks | 50372 |
| Selector-zero / selector-one body checks | 2722 / 2669 |
| Capacity / legal bootstrap-C CSR instructions | 3 / 7 |

- All2019442 same original row objects were passed unfiltered/in order to the sealed checker and checked unchanged afterward. Observer before/after ordered row digests both `1e0d159f237c8cd7923bda326884d6aca3c93ec1e583849e3378ee4afe5ebd3e`. CSV SHA `60514bc76b089a6179dbb765d856a676b8e98c6331305d075dc93bff7768aa24` matched before/after.
- Reconstructed generic and strict dictionaries exactly match producer JSON, not merely PASS labels. CVX1082 requests/1082 responses, architecture1082, uop528 allocations/528 completions, no outstanding ownership/replay/exception. Actual RVV883 excludes vector-CSR instructions counted by generic vector classification.
- Actual setup writes: input512, indices512, indices16=512, predicate-clear12544, predicate-pack21208, output-init50372. Addresses/order/values/BE, full setup arguments, original capacity512 and bootstrap CSR operands checked. Capacity lies between the sixth and seventh original bootstrap/C CSR instructions. Original filter count3682 preserves3584 excluded-op iterations plus98 calls.
- All result/guard counts above are **16-bit elements**, not bytes. Full512-element output and both guards are checked for every call; no old-destination prefix/tail oracle was shortened. Selector-zero chooses input and selector-one chooses indices, not gather mask-off preservation.
- Architectural CTRL exit0 at PC80000072, cycle2998721, order2015133, followed only by six original parking retirements. No premature exit or extra target call.

## Exact Scope and Limits

First tuple `[0,4,0,0,0,0]`, last `[0,4,0,6,0,1]`, ordered as seed/op/scalar-slot/length-index/mask-mode/start-trial. This retains the original natural98 history: all16 combinations at each of the first six VL choices, then the first two all-on VL512 starts. It does not cover the remaining VL512 masks/starts or the full2688 child.

The original13 helper, source formulas, setup and full oracle are preserved on frozen M6. Full original Linux C-to-ELF rebuild identity/timing equivalence is not claimed; the historical stopped tuple remains unknown. Reference results are not DUT evidence. CSR evidence here is the original bootstrap operand checks and98 actual returned-vstart reads; no additional CSR readback, reference-only CSR state or direct vector-port/wave observation is claimed.

- [result.json](terminal01/result.json): `INDEPENDENT_M6_MERGE98_FULL_ORACLE_ACCEPTED_NOT_FULL_CHILD`, SHA `ec838311b3c153252878fae6b96173b20a9164048b2d3701f602d4ef93d30e31`.
- [verified_pins.json](terminal01/verified_pins.json): SHA `c030bb7333fbc97eb716b2f2fadd601937509d40dd55400c569e161a58a22c30`.

No sealed code/source/reference/DUT output was modified. No additional run is authorized by this acceptance.
