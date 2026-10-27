#pragma once

#include "tiled_candidate.h"

namespace m4_packed_candidate {

#if GGML_RISCV_Q8_K_M4_VECTOR
// GNU/Clang alias-qualified accesses permit word stores into the existing byte
// payload. Its base and each block/qs offset satisfy the word alignment contract.
typedef uint32_t alias_word __attribute__((__may_alias__));
inline vuint32m4_t widen(vint8m1_t q,size_t vl) {
    return __riscv_vzext_vf4_u32m4(__riscv_vreinterpret_v_i8m1_u8m1(q),vl);
}
inline void store(int8_t *destination,vint8m1_t q0,vint8m1_t q1,
                  vint8m1_t q2,vint8m1_t q3,size_t vl) {
    auto words=widen(q0,vl);
    words=__riscv_vor_vv_u32m4(words,__riscv_vsll_vx_u32m4(widen(q1,vl),8,vl),vl);
    words=__riscv_vor_vv_u32m4(words,__riscv_vsll_vx_u32m4(widen(q2,vl),16,vl),vl);
    words=__riscv_vor_vv_u32m4(words,__riscv_vsll_vx_u32m4(widen(q3,vl),24,vl),vl);
    __riscv_vse32_v_u32m4(reinterpret_cast<alias_word *>(destination),words,vl);
}
#endif

inline bool quantize(const float *GGML_RESTRICT x,void *GGML_RESTRICT output,int64_t k) {
    static_assert(QK_K==256,"native block layout changed");
    assert(k>=0 && k%QK_K==0 && k/QK_K<=INT_MAX);
#if GGML_RISCV_Q8_K_M4_VECTOR && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    static_assert(offsetof(block_q8_Kx4,qs)%4==0 && sizeof(block_q8_Kx4)%4==0,"unaligned word payload");
    unsigned frm;asm volatile("frrm %0":"=r"(frm)::"memory");
    const size_t span=__riscv_vsetvl_e32m4(128);
    if(frm || !k || span<16 || span%16 || !ggml_riscv_q8_K_m4::vector_domain(x,k)) {
        ggml_quantize_mat_q8_K_4x1_ara_generic(x,output,k);return false;
    }
    auto *y=static_cast<block_q8_Kx4 *>(output);
    for(int64_t b=0;b<k/QK_K;++b) {
        float scale[4];
        for(int row=0;row<4;++row) {
            float absolute;
            const float maximum=ggml_riscv_q8_K_signed_max(x+row*k+b*QK_K,QK_K,&absolute);
            scale[row]=absolute ? -127.0f/maximum:0.0f;
            y[b].d[row]=absolute ? 1.0f/scale[row]:0.0f;
        }
        for(size_t first=0;first<QK_K;first+=span) {
            const size_t vl=__riscv_vsetvl_e32m4(span);
            const auto q0=m4_tiled_candidate::encode(x+b*QK_K+first,scale[0],vl);
            m4_tiled_candidate::sums(q0,y[b].bsums+4*(first/16),vl);
            const auto q1=m4_tiled_candidate::encode(x+k+b*QK_K+first,scale[1],vl);
            m4_tiled_candidate::sums(q1,y[b].bsums+4*(first/16)+1,vl);
            const auto q2=m4_tiled_candidate::encode(x+2*k+b*QK_K+first,scale[2],vl);
            m4_tiled_candidate::sums(q2,y[b].bsums+4*(first/16)+2,vl);
            const auto q3=m4_tiled_candidate::encode(x+3*k+b*QK_K+first,scale[3],vl);
            m4_tiled_candidate::sums(q3,y[b].bsums+4*(first/16)+3,vl);
            store(y[b].qs+4*first,q0,q1,q2,q3,vl);
        }
    }
    return true;
#else
    ggml_quantize_mat_q8_K_4x1_ara_generic(x,output,k);return false;
#endif
}

} // namespace m4_packed_candidate
