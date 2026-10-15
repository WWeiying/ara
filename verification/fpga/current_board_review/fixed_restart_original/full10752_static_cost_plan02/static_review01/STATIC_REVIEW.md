# Independent Static Review: Full10752 Fixed e8/m4

Decision: **NO_BLOCKER_NEXT_SOURCE_IMPLEMENTATION_AND_SOURCE_REVIEW_ONLY**.
No compiled cost, Host/reference acceptance, runtime budget acceptance, or DUT launch is authorized by this review. The complete <=3M cost gate remains **UNPROVEN / HOLD for execution**.

## Evidence And Scope

Reviewed the author's README.md, GEOMETRY.md, COSTS.json and INPUT_PINS.json against `recovery01/successor_oracle.c`, `scenario.S`, `operations.h`, and recovery report; inspected the existing prefix777 disassembly and adaptation only as historical cost/oracle evidence. All 22 pinned inputs match (202713 bytes total); no large raw/CSV was read. The four reviewed plan hashes are bound in STATIC_REVIEW.json.

The reconstructed C SHA `ab82b489...` is not the missing historical C SHA `b50d3298...`. Its recorded fixed-flags build is byte-equivalent to the retained original ELF SHA `ca6937f7969cb2664becfe53fac5e49111415929e96220874568964b293b85cc`, and the original assembly bytes match. I verified those extant file identities, not a new build. The plan states this distinction correctly.

Source lines 244-304 and operations.h establish 3 seeds * 4 operations * 7 VL slots * 4 masks * 4 starts * 8 controls = **10752**, without deduplicating repeated starts. At VLENB128, capacity is 512 and the four physical-register groups use e8/m4; max_start is 1023, not 511. Starts are 1, VL/2, VL, 511, including VL0 and repeated cases. The result domain is 5505024 bytes plus 21504 individual guard checks; a guard failure still generates only the original single combined diagnostic.

Each original operation has 24 instructions, including all three source/destination loads, mask load, final output store, CSR save/set/sample/restore, and ret. Thus 258048 operation instructions plus capacity3 are required. The five capacity-sized memory operations per call remain mandatory even for VL0 or an all-off predicate. There are 4608 vstart<VL targets, not merely the 2976 calls with a selected active element. No source-level all-off ownership waiver is valid here.

## History And Side Effects

1. **Input RNG and overrides:** source lines 253-264 initialize only a[0:512] and b[0:512] once per seed. Each of 1536 xorshift iterations must still occur, even when its random writes are subsequently overridden. Per eight indices, the 16 initial writes and seven override writes give 4416 ordered byte assignments to retain in the proposed port. This is a source-assignment count, not a measurement that the old optimized ELF retired 4416 SB instructions. In particular i%8==3 changes only b[i] to 8; a[i] remains random. Neither FIXED_SCALAR_SUITE nor INTEGER_SCALAR_SUITE is enabled, so the scalar b[0] overrides at lines 265-273 must not be imported. The higher halves of the 1024-byte backing arrays are not per-seed initialized.
2. **Mask history:** lines 285-287 reconstruct the mask once per seed/op/VL/mode, then share it across 32 helper calls. All 336 epochs must remain. Replacing 128 clear SB with 16 exact aligned zero SD is valid for the scalar port, but all 70644 selected cumulative SB values/addresses/order must remain. Mode2 selects 2,9,...,506 (73 elements). The optimized construction must not replace this sequence with one final mask copy or skip the clear for all-off groups. The upper 64 mask bytes must remain zero even though the helper consumes only 64 bytes.
3. **CSR history:** scenario.S saves incoming vxrm and vxsat each call, sets rm=control&3 and initial saturation=control>>2, samples vstart/vxsat, then restores the saved operands. Preserve these exact 21504 restoration operands and every helper call; do not substitute zero, reset between rows/seeds, or deduplicate sticky/control variants. Returned vstart is checked as a complete low32 value and saturation as the complete high32 value. The arithmetic output is independent of initial sticky state; the saturation oracle is not.
4. **Output freshness:** merging the two adjacent identical output initialization loops is safe because there is no intervening observer, and initial_destination is always 0x5b in this build. Every call must still fresh-write exactly 514 bytes: 64 aligned SD plus SH at offset512. out+1 remains the vector destination. The first word includes the front guard; the final LHU includes result511 and the rear guard. No actual tail LD/SD may extend this footprint to 520 bytes. Padding an immutable dictionary block is not permission to access extra output bytes.
5. **Failure behavior:** the original order is vstart failure, ascending per-element comparisons and elements increments, saturation failure, combined guard failure, checks increment. failure() increments every error but prints only the first20. On packed mismatch the original byte-level fallback must run over the existing output, without reinitializing or reexecuting the helper; do not increment counters twice. Preserve the unusual guard diagnostic that prints the rear value even when only the front guard is corrupt. The prefix777 generic mismatch collapse is explicitly unsuitable for this new full-parent contract.

## Geometry Deduplication

Independently counted only the source-domain index sets, without generating RNG values, gold outputs, or executing a numerical oracle. The 7*4*4 VL/mask/start domain has 31 nonempty visits, 21 distinct nonempty active sets, and 34 distinct nonempty (block position, active indices) keys. Nonempty visits by VL are 0,1,4,6,6,6,8. There are 105 nonempty full-block visits and six nonempty tail visits in that base domain.

Only op0 depends on rounding; the actual FRACTIONAL_SUITE mapping sends op1/2/3 to signed-add / unsigned-add / signed-sub saturation, without rounded(). Arrays a/b do not change within a seed and the helpers store only to out. Therefore:

- Rows: 1 sentinel + 3 seeds * (4 rounding variants + 3 other operations) * 21 = **442**.
- Blocks: 2 distinct padded sentinel variants + 3 * 7 * 34 = **716**.
- Active calls: 31 * 3 * 4 * 8 = **2976**; active element visits: 3164 * 96 = **303744**.
- Non-sentinel expected-word load bound: (105*8+6)*96 = **81216**.
- Proposed ROM: 716*64 + 442*9*2 + 10752*2 + 10752 = **86036 bytes**, before alignment and other metadata/text/stack.

These are conservative symbolic bounds, not measured numerical uniqueness. Equal keys imply equal expected bytes; value dedup can reduce storage but cannot remove any tuple, RNG step, source/helper side effect, actual result read, or separate per-call saturation entry. Preserve all 65 actual loads and comparisons even on row0 and after an earlier mismatch. A non-sentinel value that happens to equal 0x5b does not license a call omission.

## Cost Assessment

The old prefix disassembly directly supports the 3-instruction x64 initialization loop and 7-instruction x64 equality loop. Its recorded measurements cannot establish full10752 cost. The 3053568 figure is a lower floor only for the specific implementation class doing 65 fresh stores, 65 actual loads, 65 expected loads, 65 branches and 24 helper instructions per call; the plan does not mislabel it as a universal bound.

The proposed **2698536** subtotal is arithmetically consistent and explicitly incomplete. The remaining **301464 (28.04/call)** must cover all uncharged caller/counters/status logic, address and constant setup, tail constants, branch joins, ABI spills, RNG control, bootstrap, trace text and exit. Mask constant-register reuse could recover 68964 only if the actual code proves that lowering without compensating spill/rematerialization costs. A source memcpy or comparison expression does not guarantee the proposed SD/SH/LD/LHU or one-branch equality lowering. No source statement in this review turns that subtotal into a GCC upper bound.

Next source implementation should retain the original byte fallback and explicit fresh/read/store requirements; then independent source equivalence review must precede any separately authorized fixed-flags compile/whole-CFG cost gate. Preserve a real 64KiB stack allocation and check linked ROM/text/BSS/stack fit. No compiler experiment or reference execution is authorized here.

The 53760 full-capacity memory helpers are also a distinct simulator-time risk. Neither the old 777-call M8 time nor a future <=3M firmware count proves full-parent <=3h. Linux tty drain, scheduling and the historical stall environment are not reproduced by a bare source port. All 28 original boundary markers and a precise explanation of runtime substitutions remain required; a source-port PASS must not close the original Linux parent automatically.

## Conclusion

No blocking static defect found for **the next source implementation/review stage only**. Geometry, history preservation and the limited cost claim are internally consistent. Numerical model equivalence, actual lowering, complete <=3M cost, bounded reference and DUT admission remain separate unperformed gates. No author plan or old artifact was changed.
