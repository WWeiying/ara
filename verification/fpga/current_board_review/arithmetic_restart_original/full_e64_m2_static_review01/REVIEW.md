# e64/m2 Static Review

NO_BLOCKER_STATIC_SOURCE_MODEL_PLAN_ONLY. This is a proposal/model review, not a runnable-source or Host/compile/reference/DUT admission. Eleven source pins freshly match; no model/test/compiler/simulator execution.

Actual original ELF1ac38fee... and binary-equivalent reconstruction are identified separately from unrecovered original C bytes. Independent static byte comparison confirms640 FP64 words/5120B uniquely at file1560/vaddr11560 and35 full48-byte helper slices. Capacity3 +35*13 gives458 static helper instructions; full5985 execution requires77805. Actual vtype0x19/group2 cannot inherit e64m1 CAP16.

Input constants occur five times; original LUI/ADDI/stack120/indexed704 chain binds11520. Model takes expected FP bits from original header, not host floating point. It preserves1890 FP calls, every-call32 a then b pairs (120960 u64 writes), and original RNG initialization at each next seed. Original source has no fflags/frm oracle: preserve state, do not claim flags validation.

Full272B =34 u64 words: eight-byte leading guard,32 results,eight-byte trailing guard. Four full64B blocks plus final16B cover last result256 and guard264; no LWtail4/padded48B access. Full physical group256B; initialized128B mask with actualvlm4B and upper124zero. CAP32 gather/order/restart semantics agree with original source. Proposed ROM147466B is plausible, not actual linker/stack proof.

Cost remains unresolved: original FP refresh alone22*32*1890=1330560 instructions. Illustrative total2998560..3297810 is neither measured nor a bound, and can exceed3M. Do not launch reference or claim <=3h from this estimate. Next stage requires parent authorization and actual implementation/Host/compile/helper/lowering/map evidence. Existing accepted e64m1 is only contextual evidence, not this workload's acceptance.
