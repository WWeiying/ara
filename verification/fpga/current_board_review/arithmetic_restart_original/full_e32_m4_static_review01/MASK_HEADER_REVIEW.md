# Exact Constant-Mask Header Review

Verdict: SOURCE_NO_BLOCKER_STATIC_HEADER_COST_HOLD. Reviewed the actual new mask_constant.h and SOURCE_PLAN.md; no compiler, Host, reference or DUT execution. All27 proposal pins freshly match. This is not acceptance of an integrated caller or actual machine lowering.

The header clears offsets0,8,...,120 using16 exact eight-byte memcpy operations and compiler memory barriers. Access ends at127; no alias-punning cast or padded access. The volatile uint8 selected stores also have per-store memory clobbers. No mask reads, RVV or hardware fence are expressed by this header. Future ELF must establish the intended16 SD and selected SB lowering.

Mode0 visits bytes0..15 in order, storing1,3,7,15,31,63,127,255 at each byte:128 ordered stores. Mode1 stores2,10,42,170 at each byte:64 stores. Mode2's18 explicit pairs match original selected indices2,9,16,23,...,121. In particular byte2 and byte9 each retain separate1 then129 stores; there is no final-mask-only substitution. Across735 groups per mode this preserves154350 selected SBs after every group's full128B clear. Upper112 bytes remain zero.

The previous per-step induction applies to these exact constants under exclusive access: mask is private ordinary RAM, fully zeroed first, with no aliasing/concurrent CPU/handler/DMA/vector writer between clear and updates. The original source and helper placement support that premise; future integrated runtime/layout must retain it. Invalid mode traps. The header does NOT itself validate hardware CAP: its caller must perform the promised actual CAP128 check before use. That is an explicit integration prerequisite, not a currently implemented gate.

Unchanged obligations remain all5985 calls/history,483840 FP SW, full520B initialization and65 actual output LD per call, including element127 plus rear guard in the final word, and original typed fallback. The expected-cache part is still a plan, not an implementation checked here. New observer must check the actual clear/SB sequence and must not claim removed LBU retirements. Other sealed shape contracts are untouched.

2965306 is subtraction of assumed gross savings from a previous analogy. It excludes unknown cache decisions, constant materialization, addressing, spills and other compiler changes. It is neither actual GCC upper nor measured firmware; it does not admit3M or a DUT budget. SOURCE_NO_BLOCKER only supports the next parent decision, not autonomous execution.

Exact identities:
- SOURCE_PLAN.md: ec27a618096fe855b9b47ec0079bf9dfd043e5c6b926540fe5d6c045ba2a15e0
- mask_constant.h: e6ec36ec1b75d8353f318cd8418d26ee686cbedc73866bffb124311e8b19c1c9

No producer or sealed input was changed.
